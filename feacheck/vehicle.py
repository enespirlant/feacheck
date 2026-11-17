"""Araç bilgisi (arac.yaml, araç başına bir kez) ve modeldeki kuvvetin araç yükleriyle otomatik kıyası.

Parçaya özgü bilgi (malzeme, mesnet, kuvvet) Mechanical modelinden okunur; burada yalnız aracın kendisi tutulur.
Buton, modeldeki kuvvetin neyi temsil ettiğini (düşey / çekiş / yanal) bir kez sorar ve model adına göre hatırlar.
"""
from __future__ import annotations

import math
from pathlib import Path

from .handcalc import rover_wheel_loads

ARAC_TEMPLATE = """# feacheck arac bilgisi - arac basina BIR KEZ doldur. Parca bilgisi Ansys modelinden okunur.
# Bos birakilan arac icin yuk kiyasi yapilmaz (rapor yine uretilir).
kutle:              # kg, tum arac, yuk dahil
teker_sayisi:       # adet
teker_capi:         # mm
motor_torku:        # N*m, motor cikisi (tepe)
disli_orani: 1      # motor -> teker, reduktor yoksa 1
verim: 1            # YALNIZ disli kaybi. Tork motor milinde olculuyorsa ve disli yoksa 1 birak.

# Varsayimlar (emin degilsen dokunma)
k_dyn: 2.5          # engel/cukur darbe katsayisi (2-3 tipik)
mu: 0.8             # cekis surtunmesi
mu_lat: 0.5         # yanal kayma surtunmesi
k_teker: 1          # en yuklu teker / ortalama teker yuku (rampa, fren, engel; duz zeminde 1)
# cekis_tasarim:    # N, istege bagli: aracin kendi hesabindan teker basi cekis (yazilirsa dogrudan kullanilir)
"""

ZORUNLU = ("kutle", "teker_sayisi", "teker_capi", "motor_torku")
YUK_TIPLERI = {"duzey": ("Fz_tasarim", "düşey tasarım yükü (k_dyn·k_teker·mg/n)"),
               "cekis": ("Fx_cekis", "çekiş kuvveti"),
               "yanal": ("Fy_yanal", "yanal kuvvet")}


def load_vehicle(home: Path) -> dict | None:
    """arac.yaml'ı okur; yoksa şablonu yazar. Zorunlu alanlardan biri boş/sayı değilse None."""
    import yaml
    f = Path(home) / "arac.yaml"
    if not f.exists():
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(ARAC_TEMPLATE, encoding="utf-8")
        except OSError:
            pass
        return None
    try:
        d = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        return {k: float(d[k]) for k in ZORUNLU} | {
            k: float(d.get(k, v)) for k, v in
            (("disli_orani", 1.0), ("verim", 1.0), ("k_dyn", 2.5), ("mu", 0.8), ("mu_lat", 0.5),
             ("k_teker", 1.0))} | {"cekis_tasarim": float(d["cekis_tasarim"]) if d.get("cekis_tasarim") else None}
    except (KeyError, TypeError, ValueError, yaml.YAMLError):
        return None


def wheel_loads(v: dict) -> dict:
    return rover_wheel_loads(v["kutle"], int(v["teker_sayisi"]), v["teker_capi"], v["motor_torku"],
                             gear_ratio=v["disli_orani"], eta=v["verim"], k_dyn=v["k_dyn"],
                             mu=v["mu"], mu_lat=v["mu_lat"], k_teker=v.get("k_teker", 1.0),
                             Fx_design=v.get("cekis_tasarim"))


def model_force(raw: dict) -> float | None:
    """Modelde uygulanan toplam kuvvetin büyüklüğü (N); okunamadıysa None."""
    app = raw.get("applied_force_n") or [0.0, 0.0, 0.0]
    mag = math.sqrt(sum(a * a for a in app))
    mag += raw.get("applied_force_vector_mag_n") or 0.0
    return mag if mag > 0 else None


def check_load(raw: dict, v: dict, tip: str) -> dict | None:
    """Modeldeki kuvveti teker başına araç yüküyle kıyaslar. tip: duzey / cekis / yanal."""
    if tip not in YUK_TIPLERI:
        return None
    F = model_force(raw)
    if F is None:
        return None
    wl = wheel_loads(v)
    key, label = YUK_TIPLERI[tip]
    beklenen = wl["value"][key]
    oran = F / beklenen
    if oran < 0.95:
        durum, ok = "düşük", False
    elif oran > 2.0:
        durum, ok = "çok ihtiyatlı", True
    else:
        durum, ok = "uygun", True
    n = lambda x: f"{x:.0f}"  # noqa: E731
    text = (f"Modeldeki kuvvet {n(F)} N, araçtan en yüklü teker için {label} {n(beklenen)} N "
            f"(oran {oran:.2f}".replace(".", ",") + f"): {durum}")
    return {"tip": tip, "model_n": F, "beklenen_n": beklenen, "oran": round(oran, 3), "durum": durum, "ok": ok,
            "text": text, "formula": wl["formula"], "varsayimlar": wl["varsayimlar"],
            "cekis_siniri": wl["cekis_siniri"], "yukler": wl["value"]}


def attach_vehicle(res: dict, raw: dict, home: Path, tip: str | None) -> None:
    if not tip or tip == "yok":
        return
    v = load_vehicle(home)
    if v is None:
        res.setdefault("warnings", []).append(
            "Araç yük kıyası yapılmadı: arac.yaml boş ya da eksik (kütle, teker sayısı, teker çapı, motor torku).")
        return
    try:
        c = check_load(raw, v, tip)
    except ValueError as e:
        res.setdefault("warnings", []).append(f"arac.yaml okunamadı: {e}")
        return
    if c is None:
        return
    res["vehicle_load"] = c
    if not c["ok"]:
        res.setdefault("findings", []).append(
            f"Yük araç verisine göre düşük: {c['text']}. Modeldeki kuvveti en az {c['beklenen_n']:.0f} N yap "
            "ya da arac.yaml'daki değerleri kontrol et.")
