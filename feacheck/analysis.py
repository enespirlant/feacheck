"""Mechanical'dan gelen ham yakınsama verisini yorumlar ve karar verir."""
from __future__ import annotations

import math

from .gci import gci3, rep_h


def _series(levels, key, sub=None):
    out = []
    for lv in levels:
        v = lv.get(key)
        if sub and isinstance(v, dict):
            v = v.get(sub)
        out.append(v)
    return out


def _quantity(name, unit, levels, tol_pct, h):
    """Bir büyüklüğün mesh serisi + GCI kararı. Değer ve h birlikte süzülür (eksik seviye = eksik veri)."""
    raw_vals = _series(levels, *name.split(".")) if "." in name else _series(levels, name)
    pairs = [(v, hh) for v, hh in zip(raw_vals, h) if v is not None]
    vals = [v for v, _ in pairs]
    hs = [hh for _, hh in pairs]
    q = {"values": vals, "unit": unit}
    missing = len(raw_vals) - len(vals)
    if missing and vals:
        q["missing_levels"] = missing
    if len(vals) >= 2:
        q["last_change_pct"] = round(100 * abs(vals[-1] - vals[-2]) / max(abs(vals[-1]), 1e-30), 3)
    if len(vals) >= 3:
        q["gci"] = gci3([vals[-1], vals[-2], vals[-3]], [hs[-1], hs[-2], hs[-3]])
    g = q.get("gci", {})
    st = g.get("status")
    # Değişimler gürültü düzeyindeyse (her adım ≤ eşik/2) ε oranı anlamsızlaşır: 0,6 → 1,3'lük iki artış
    # "ıraksıyor" sayılırdı. Tekillikte r = 1,5 ile adım başı artış > %4 (q > 0,1), yani bu kuralın üstünde.
    if st == "diverging" and len(vals) >= 3:
        rel = [100 * abs(vals[i + 1] - vals[i]) / max(abs(vals[i + 1]), 1e-30) for i in range(len(vals) - 3, len(vals) - 1)]
        d1, d2 = vals[-2] - vals[-3], vals[-1] - vals[-2]
        # Aynı yönde ve büyüyen adımlar gürültü değil: seri asimptotik bölgeye girmemiş (gerçek R5 koşusu:
        # 178,4 → 179,5 → 181,9 → 186,2; adımlar 1,0 → 2,4 → 4,4). Yalnız salınım ya da küçülen adım kabul.
        accelerating = d1 * d2 > 0 and abs(d2) > abs(d1)
        if accelerating and max(rel) <= tol_pct / 2:
            g["accelerating"] = True
            g["step_changes_pct"] = [round(x, 3) for x in rel]
            g["note"] = ("Değişimler küçük ama her incelmede aynı yönde büyüyor (hızlanan artış): seri henüz "
                         "yakınsama bölgesinde değil, değer artmaya devam edebilir. Gürültü sayılmadı.")
        if not accelerating and max(rel) <= tol_pct / 2:
            last3 = vals[-3:]
            spread = 100 * (max(last3) - min(last3)) / max(abs(vals[-1]), 1e-30)
            g["small_change"] = True
            g["step_changes_pct"] = [round(x, 3) for x in rel]
            g["gci_fine_pct"] = round(1.25 * spread, 3)
            g["note"] = ("Adım değişimleri gürültü düzeyinde; yakınsama yönü belirsiz. Belirsizlik, son üç "
                         "değerin aralığı × 1,25 olarak verildi.")
            q["verdict"] = "güvenilir (küçük değişim)"
            q["confidence"] = "düşük"
            q["design_value"], q["conservative_value"] = _design_values(q)
            return q
    if st == "oscillatory":
        last3 = vals[-3:]
        mean = sum(last3) / 3
        spread = 100 * (max(last3) - min(last3)) / max(abs(mean), 1e-30)
        g["spread_pct"] = round(spread, 3)
        g["gci_fine_pct"] = round(spread / 2, 3)  # Celik 2008: salinimli -> yari aralik
        if spread / 2 <= tol_pct:
            q["verdict"] = "güvenilir (salınımlı)"
            q["confidence"] = "düşük"
        else:
            q["verdict"] = "salınımlı, belirsiz"
    elif st == "converging" and g.get("gci_fine_pct") is not None and g["gci_fine_pct"] <= 2 * tol_pct:
        # Eşiğin 2 katına kadar: yakınsıyor ve belirsizlik ölçülmüş; düşük güvenle, bandın üst ucuyla kullanılır.
        wide = g["gci_fine_pct"] > tol_pct
        q["verdict"] = "güvenilir (geniş belirsizlik)" if wide else "güvenilir"
        q["confidence"] = ("düşük" if (wide or g.get("low_order")) else
                           "orta" if g.get("non_asymptotic") else "yüksek")
        if wide:
            g["wide"] = True
        if len(vals) >= 4:
            dirs = [b - a for a, b in zip(vals, vals[1:])]
            if any(d * dirs[-1] < 0 for d in dirs[:-2]):
                q["early_reversal"] = True
                g["note"] = ((g.get("note") + " ") if g.get("note") else "") + (
                    "Tüm seviyelere bakınca seri tek yönlü değil (önce ters yönde değişti); GCI son üç seviyeden "
                    "hesaplandı, kaba seviye asimptotik bölgenin dışında kalıyor olabilir.")
    elif st == "exact" or (st is None and len(vals) == 2 and q.get("last_change_pct", 99) <= tol_pct / 2):
        q["verdict"] = "güvenilir"
        q["confidence"] = "düşük" if st is None else "yüksek"
    elif st == "diverging":
        q["verdict"] = "yakınsamıyor"
    elif st == "converging":
        q["verdict"] = "yakınsıyor ama GCI yüksek"
    elif st == "invalid":
        q["verdict"] = "belirsiz"
    else:
        q["verdict"] = "belirsiz"
    if missing and vals and q["verdict"].startswith("güvenilir"):
        q["confidence"] = "düşük"
    q["design_value"], q["conservative_value"] = _design_values(q)
    return q


def _design_values(q):
    """(ince mesh değeri, ihtiyatlı değer). İhtiyatlı: azalan seride ekstrapolasyon ince değerin altına
    düşer; emniyet katsayısını şişirmemek için büyük olan / GCI bandının üstü alınır."""
    if not q["values"]:
        return None, None
    f1 = q["values"][-1]
    g = q.get("gci", {})
    if g.get("status") == "converging" and (g.get("low_order") or g.get("wide")) and g.get("gci_fine_pct") is not None:
        # Düşük mertebede ekstrapolasyonun kendisi p'ye çok duyarlı: GCI bandının üst ucu alınır.
        return f1, max(f1 * (1 + g["gci_fine_pct"] / 100.0), g.get("extrapolated") or f1)
    if g.get("status") == "converging" and g.get("extrapolated") is not None:
        return f1, max(f1, g["extrapolated"])
    if g.get("gci_fine_pct") is not None:
        return f1, f1 * (1 + g["gci_fine_pct"] / 100.0)
    return f1, f1


_NONLINEAR_CONTACT = ("Frictional", "Frictionless", "NoSeparation", "Rough", "FrictionlessSurface")


def _connections(raw: dict, out: dict) -> None:
    """Montaj bağlantılarından bulgular. Bulgular 'Bağlantı:' ile başlar (rapor bunları kurulum uyarısı sayar)."""
    con = raw.get("connections")
    if not con:
        return
    active = {k: [c for c in con.get(k, []) if not c.get("suppressed")] for k in ("contacts", "joints", "beams")}
    out["connections"] = {"bodies": con.get("bodies"), **active}
    nb = con.get("bodies") or 1
    n_links = sum(len(v) for v in active.values())
    if nb > 1 and n_links == 0:
        out["findings"].append(
            f"Bağlantı: modelde {nb} gövde var ama aralarında temas, mafsal ya da kiriş bağlantısı yok. Gövdeler "
            "paylaşılan topolojiyle (multi-body part) birleştirilmediyse birbirine yük aktarmaz; serbest kalan gövde "
            "rijit cisim hareketi yapar ya da çözüm başarısız olur.")
    types = {}
    for c in active["contacts"]:
        t = str(c.get("contact_type", "?")).split(".")[-1]
        types.setdefault(t, []).append(c["name"])
    if types:
        out["connections"]["contact_types"] = {k: len(v) for k, v in types.items()}
    if types.get("Bonded"):
        out["findings"].append(
            f"Bağlantı: {len(types['Bonded'])} bonded temas var. Bonded yüzeyler kaymaz ve ayrılmaz: cıvatalı ya da "
            "geçme bir bağlantı için gerçekten daha rijittir ve yük yolunu değiştirebilir. Bonded yüzün bittiği "
            "kenar da keskin köşe gibi gerilme tekilliği üretebilir.")
    nl = [k for k in types if k in _NONLINEAR_CONTACT]
    if nl:
        out["findings"].append(
            f"Bağlantı: doğrusal olmayan temas var ({', '.join(f'{k}: {len(types[k])}' for k in nl)}). Her mesh "
            "seviyesi iteratif çözülür ve temas durumu (açık/kapalı, kayma) mesh ile değişebilir; GCI bu değişimi "
            "ayırt etmez. Her seviyede Contact Tool ile temas durumunun aynı kaldığını kontrol et.")
    # Tepe bir temas yüzünün yakınında mı?
    lv = [x for x in raw.get("levels", []) if "max_vm" in x]
    peak = ((lv[-1].get("max_location") or {}).get("xyz_mm")) if lv else None
    if not peak:
        return
    best = None
    for c in active["contacts"]:
        for f in (c.get("source") or []) + (c.get("target") or []):
            if not f.get("c") or not f.get("area_mm2"):
                continue
            d = math.dist(peak, f["c"])
            lim = math.sqrt(f["area_mm2"])
            if d <= lim and (best is None or d / lim < best[1]):
                best = (c["name"], d / lim, d, str(c.get("contact_type", "?")).split(".")[-1])
    if best:
        out["connections"]["peak_near_contact"] = {"name": best[0], "distance_mm": round(best[2], 2), "type": best[3]}
        out["findings"].append(
            f"Bağlantı: en yüksek gerilme '{best[0]}' ({best[3]}) temas yüzünün yakınında (yüz merkezine "
            f"{best[2]:.1f} mm). Temas kenarındaki tepe, bağlantının modellenme biçimine bağlıdır (mesnet tekilliği "
            "gibi düşün); tasarım değerini temas bölgesi dışından al ya da bağlantıyı daha gerçekçi modelle "
            "(ön yüklü cıvata, sürtünmeli temas).")


def _bcs(raw: dict) -> list:
    """Mesnet/yük nesneleri, seçili yüzlerin merkez koordinatları ve kuvvet bileşenleri."""
    out = []
    for e in raw.get("tree", []):
        if "faces" not in e:
            continue
        out.append({"name": e["name"], "type": e["type"], "faces": e["faces"],
                    "suppressed": e.get("suppressed", False)})
    return out


_LEVEL_KEY = {"von_mises_outside_zone": "max_outside_zone", "von_mises_away_from_peak": "max_away_from_peak"}


def _in_bc_zone(levels, key, excl):
    for lv in levels:
        rec = lv.get(_LEVEL_KEY[key]) or {}
        d = rec.get("dist_to_bc_mm")
        if d is not None and d <= excl:
            return True
    return False


def _max_face_radius(levels):
    for f in (levels[-1].get("max_faces") or []):
        if "Cylind" in f.get("type", "") or "Cone" in f.get("type", "") or "Torus" in f.get("type", ""):
            if f.get("radii_mm"):
                return min(f["radii_mm"])
    return None


def _looks_like_radius(levels, steps):
    """Keskin köşe mi, henüz çözülmemiş radyus mu? Önce maksimumun yüz tipine bakılır
    (silindirik/torus = radyus, yalnızca düzlemsel = keskin kenar). Yüz bilgisi yoksa
    büyüme hızına bakılır: tekillikte adım üssü sabit/artan, çözülmemiş yığılmada azalan."""
    faces = levels[-1].get("max_faces")
    if faces:
        curved = any(("Cylind" in f.get("type", "") or "Torus" in f.get("type", "") or "Cone" in f.get("type", ""))
                     for f in faces)
        return curved
    if steps and len(steps) >= 2 and steps[0] > 0:
        return steps[-1] < 0.9 * steps[0]
    return False


def _radius_series(raw, tol):
    """Radyus yüzüne yerel sıklaştırmayla yapılan ek seri (global boyut sabit, yalnız radyus incelir).
    h olarak radyustaki yerel eleman boyu kullanılır."""
    rs = raw.get("radius_series")
    if not rs:
        return None
    lv = [x for x in rs.get("levels", []) if "max_vm" in x]
    out = {"radius_mm": rs.get("radius_mm"), "global_size_mm": rs.get("global_size_mm"),
           "sizes_mm": rs.get("sizes_mm"), "levels": rs.get("levels", []),
           "elements_on_arc": [x.get("elements_on_arc") for x in lv]}
    if rs.get("skipped"):
        out["skipped"] = rs["skipped"]
    if rs.get("extra_level"):
        out["extra_level"] = rs["extra_level"]
    for k in ("growth_rate", "growth_rate_requested", "adaptive_sizing"):
        if rs.get(k) is not None:
            out[k] = rs[k]
    if len(lv) < 3:
        out["quantity"] = None
        return out
    out["quantity"] = _quantity("max_vm", "MPa", lv, tol, [float(x["element_size_mm"]) for x in lv])
    out["peak_on_radius"] = all(x.get("on_target", True) for x in lv)
    out["location_mm"] = (lv[-1].get("max_location") or {}).get("xyz_mm")
    return out


def exclusion_distance(bc_locations: dict, lc_mm: float, h0_mm: float) -> tuple[float, str]:
    """Saint-Venant dışlama mesafesi. Karakteristik boy parçanın değil yükün uygulandığı bölgenin boyudur:
    her mesnet/yük nesnesi için √(seçili yüz alanı); en büyüğü alınır. Alt sınır 2·h0 (en kaba mesh'te
    tekil alan en az iki eleman boyu), üst sınır Lc/2 (eski kural; ince parçada kritik bölgeyi yutmasın).
    mech_converge.py şablonundaki aynı kural bununla birebir tutulmalı (test_feacheck'te karşılaştırılır)."""
    areas = []
    for faces in (bc_locations or {}).values():
        a = sum(float(f.get("area_mm2") or 0.0) for f in faces)
        if a > 0:
            areas.append(a)
    if not areas:
        return round(lc_mm / 2.0, 2), "Lc/2 (yüz alanı okunamadı)"
    ex = max(a ** 0.5 for a in areas)
    rule = "√A (en büyük mesnet/yük yüzü)"
    if ex < 2.0 * h0_mm:
        ex, rule = 2.0 * h0_mm, "2·h0 (alt sınır)"
    if ex > lc_mm / 2.0:
        ex, rule = lc_mm / 2.0, "Lc/2 (üst sınır)"
    return round(ex, 2), rule


def _dist(a, b):
    return math.sqrt(sum((float(x) - float(y)) ** 2 for x, y in zip(a, b)))


def evaluate(raw: dict, cfg: dict) -> dict:
    levels = [lv for lv in raw.get("levels", []) if "max_vm" in lv]
    tol = float(cfg.get("gci_tol_pct", 5.0))
    out = {"analysis": raw.get("analysis"), "levels": raw.get("levels", []),
           "warnings": list(raw.get("warnings", [])), "errors": list(raw.get("errors", [])),
           "findings": [], "bcs": _bcs(raw)}
    if len(levels) < 2:
        out["errors"].append("En az iki çözülmüş mesh seviyesi gerekli.")
        return out
    # Temsili eleman boyu: yerel incelmede sicak bolgedeki eleman boyu, global incelmede (1/N)^(1/3)
    if raw.get("mode") == "local":
        h = [float(lv.get("h_eff_mm") or lv["element_size_mm"]) for lv in levels]
    else:
        h = [rep_h(lv["nodes"]) for lv in levels]
    out["mode"] = raw.get("mode", "global")
    if raw.get("extra_level"):
        out["extra_level"] = raw["extra_level"]

    dfm = _quantity("max_def", "mm", levels, tol, h)
    vm = _quantity("max_vm", "MPa", levels, tol, h)
    vmo = _quantity("max_outside_zone.value", "MPa", levels, tol, h)
    vpr = _quantity("probe.value", "MPa", levels, tol, h)
    vaw = _quantity("max_away_from_peak.value", "MPa", levels, tol, h)
    out["quantities"] = {"max_deformation": dfm, "max_von_mises": vm, "von_mises_outside_zone": vmo,
                         "von_mises_probe": vpr, "von_mises_away_from_peak": vaw}
    out["probe_xyz_mm"] = raw.get("probe_xyz_mm")

    # ---- tekillik kararı
    last = levels[-1]
    loc = last.get("max_location") or {}
    near_bc = loc.get("dist_to_bc_mm") is not None and loc["dist_to_bc_mm"] <= float(cfg["exclusion_mm"])
    # Büyüme üssü: sigma ~ h^(-q). 90° iç köşede elastisite teorisi q ≈ 0.455 (Williams 1952); yakınsayan
    # büyüklükte q -> 0. Hem uçtan uca hem adım adım hesaplanır (hızlanan artış = asimptotik değil).
    q_exp = None
    vv = vm["values"]
    if len(vv) >= 2 and vv[0] > 0 and h[0] != h[-1]:
        q_exp = math.log(vv[-1] / vv[0]) / math.log(h[0] / h[-1])
        out["vm_growth_exponent"] = round(q_exp, 3)
        out["vm_growth_steps"] = [round(math.log(vv[i + 1] / vv[i]) / math.log(h[i] / h[i + 1]), 3)
                                  for i in range(len(vv) - 1) if vv[i] > 0 and h[i] != h[i + 1]]
    unreliable = not vm["verdict"].startswith("güvenilir")
    # Sınır şartı kenarında mesnet yakınlığı zaten güçlü kanıt: eşik 0.05 (adım başı ~%2 artış).
    if unreliable and near_bc and q_exp is not None and q_exp > 0.05:
        out["singularity"] = {
            "detected": True, "kind": "sınır şartı",
            "location_mm": loc.get("xyz_mm"), "dist_to_bc_mm": round(loc["dist_to_bc_mm"], 3),
            "growth_exponent": round(q_exp, 3),
            "why": "Maksimum gerilme mesh inceldikçe artıyor, yakınsamıyor ve bir mesnet/yük yüzeyinin "
                   f"{cfg['exclusion_mm']:g} mm yakınında. Bu bir sınır şartı tekilliğidir; değeri fiziksel değil."}
        out["findings"].append("Maksimum von Mises bir TEKİLLİK: tasarım değeri olarak kullanılamaz. "
                               "Bağlantı bölgesi (cıvata, kaynak, yatak) bu modelle değerlendirilemez; ayrıca incele.")
    elif unreliable and q_exp is not None and q_exp > 0.1 and _looks_like_radius(levels, out.get("vm_growth_steps")):
        rad = _max_face_radius(levels)
        hf = float(levels[-1].get("element_size_mm") or 0.0)
        out["singularity"] = {
            "detected": False, "unresolved": True, "kind": "çözülmemiş radyus",
            "location_mm": loc.get("xyz_mm"), "growth_exponent": round(q_exp, 3), "radius_mm": rad,
            "why": ("Maksimum gerilme hâlâ artıyor ama artış hızı azalıyor (adım üsleri "
                    f"{out.get('vm_growth_steps')}); bu bir tekillik değil, mesh'in henüz çözemediği bir "
                    "gerilme yığılması (radyus/çentik)."
                    + (f" Radyus {rad:g} mm, en ince eleman {hf:g} mm: radyusta yalnızca ~{rad * 1.5708 / hf:.0f} "
                       "eleman var (en az 8 önerilir)." if rad and hf else ""))}
        out["findings"].append("ÇÖZÜNÜRLÜK YETERSİZ: kritik nokta bir radyusta ve gerilme henüz yakınsamadı. "
                               "Radyus yüzüne yerel eleman boyutu ver (yarıçap/4 ya da daha küçük) veya mesh seviyesi ekle. "
                               "Başka noktalardan okunan değerler bu noktadan düşük olduğu için tasarım değeri olarak kullanılmaz.")
    elif unreliable and q_exp is not None and q_exp > 0.1:
        out["singularity"] = {
            "detected": True, "kind": "geometrik",
            "location_mm": loc.get("xyz_mm"), "growth_exponent": round(q_exp, 3),
            "why": f"Maksimum gerilme mesh inceldikçe büyüyor (σ ∝ h^-{q_exp:.2f}) ve hiçbir mesnet/yük "
                   "yüzeyine yakın değil. Büyük ihtimalle radyussuz bir iç köşe (keskin kenar): elastik çözümde "
                   "gerilme sonsuz, mesh ne kadar incelirse o kadar büyür."}
        out["findings"].append("Maksimum von Mises bir GEOMETRİK TEKİLLİK (keskin köşe). Bu köşenin gerilmesi "
                               "bu modelle belirlenemez; gerçek imalat radyusunu modelleyip tekrar kontrol et. "
                               "Yorulma çatlakları genellikle böyle köşelerden başlar.")
    else:
        out["singularity"] = {"detected": False}

    # ---- güvenilir tasarım gerilmesi: aday listesi + karar izi
    kind = out["singularity"].get("kind")
    h_coarse = float(levels[0].get("element_size_mm") or 0.0)
    sing_xyz = out["singularity"].get("location_mm")
    cand_loc = {
        "von_mises_probe": raw.get("probe_xyz_mm"),
        "von_mises_outside_zone": (last.get("max_outside_zone") or {}).get("xyz_mm"),
        "von_mises_away_from_peak": (last.get("max_away_from_peak") or {}).get("xyz_mm"),
        "max_von_mises": loc.get("xyz_mm"),
    }
    names = {"max_von_mises": "Global maksimum", "von_mises_probe": "Sabit nokta (probe)",
             "von_mises_outside_zone": "Bölge dışı maksimum", "von_mises_away_from_peak": "Tepe dışı maksimum"}
    if kind == "sınır şartı":
        order = ["von_mises_probe", "von_mises_outside_zone", "von_mises_away_from_peak"]
    elif kind == "geometrik":
        order = ["von_mises_probe", "von_mises_away_from_peak", "von_mises_outside_zone"]
    else:
        order = ["max_von_mises", "von_mises_probe", "von_mises_outside_zone"]
    trace, design = [], None
    rsr = _radius_series(raw, tol) if kind == "çözülmemiş radyus" else None
    if rsr is not None:
        out["radius_series"] = rsr
    rq = (rsr or {}).get("quantity")
    if rq and rq["verdict"].startswith("güvenilir") and rsr.get("peak_on_radius"):
        # Radyus yerel sıklaştırmayla çözüldü: tepe gerçek bir gerilme yığılması, tasarım değeri o.
        out["quantities"]["radius_peak"] = rq
        cand_loc["radius_peak"] = rsr.get("location_mm")
        names["radius_peak"] = "Radyustaki tepe (yerel sıklaştırma)"
        if rq.get("confidence") == "yüksek":
            rq["confidence"] = "orta"   # yalnız radyus inceldi: GCI'nin sistematik incelme varsayımı kısmen
        rad = rsr.get("radius_mm")
        out["singularity"] = {
            "detected": False, "resolved_radius": True, "kind": None, "radius_mm": rad,
            "location_mm": rsr.get("location_mm"),
            "why": (f"Global seride radyusta çözünürlük yetersizdi; R = {rad:g} mm yüzüne yerel eleman boyu "
                    f"{rsr['sizes_mm']} mm verilerek gerilme yakınsatıldı (radyus boyunca "
                    f"{rsr['elements_on_arc'][-1]} eleman). Bu gerçek bir gerilme yığılmasıdır.")}
        # Global serinin "çözünürlük yetersiz" bulgusu artık geçersiz; raporda çelişki olmasın.
        out["findings"] = [f for f in out["findings"] if not f.startswith("ÇÖZÜNÜRLÜK YETERSİZ")]
        out["findings"].append("Kritik nokta radyusta; yerel sıklaştırma ile yakınsadı. Tasarım değeri bu "
                               "noktadan alındı (gerilme yığılması gerçek, tekillik değil).")
        kind = None
        trace.append({"source": "max_von_mises", "name": names["max_von_mises"], "accepted": False,
                      "reason": "global seride radyusta çözünürlük yetersiz; yerel seri kullanıldı"})
        order = ["radius_peak"]
    elif kind == "çözülmemiş radyus":
        trace.append({"source": "max_von_mises", "name": names["max_von_mises"], "accepted": False,
                      "reason": "kritik nokta, ama henüz yakınsamadı (çözünürlük yetersiz)"})
        if rsr is not None:
            why = ("yerel seri 3 seviyeye ulaşamadı" if not rq else
                   "tepe yerel seride radyustan kaydı" if not rsr.get("peak_on_radius") else
                   f"yerel seri de yakınsamadı ({rq['verdict']})")
            trace.append({"source": "radius_peak", "name": "Radyustaki tepe (yerel sıklaştırma)",
                          "accepted": False, "reason": why})
        for key in ("von_mises_probe", "von_mises_outside_zone", "von_mises_away_from_peak"):
            trace.append({"source": key, "name": names[key], "accepted": False,
                          "reason": "kritik noktadan düşük; tasarım değeri olarak kullanmak ihtiyatsız olur"})
        order = []
        if rq:
            out["quantities"]["radius_peak"] = rq
            steps = [round(b - a, 2) for a, b in zip(rq["values"][-3:], rq["values"][-2:])]
            accel = (rq.get("gci") or {}).get("accelerating")
            out["findings"] = [f for f in out["findings"] if not f.startswith("ÇÖZÜNÜRLÜK YETERSİZ")]
            out["findings"].append(
                f"ÇÖZÜNÜRLÜK YETERSİZ: radyus yüzü {rsr['sizes_mm']} mm yerel eleman boyuyla inceltildi "
                f"(radyus boyunca {rsr['elements_on_arc'][-1]} eleman), ama tepe gerilme yakınsamadı "
                f"({' → '.join(f'{v:.1f}' for v in rq['values'])} MPa"
                + (f"; son adımlar {steps} MPa, giderek büyüyor" if accel else "") + "). "
                + ("Hacim büyüme oranı düşürülmüş olmasına rağmen yakınsamadı: radyusa komşu yüzleri de inceltmek ya da "
                   "radyus merkezli bir etki küresi (sphere of influence) gerekir. "
                   if rsr.get("adaptive_sizing") == "False" and rsr.get("growth_rate") else
                   "Olası neden: yalnız radyus yüzeyi inceldiği için yüzeyin altındaki hacim kaba kalıyor ve gerilme "
                   "gradyanı içeri doğru çözülemiyor (bu koşuda hacim büyüme oranı etkin değildi). ")
                + "Son değer bir alt sınırdır, el hesabıyla karşılaştır.")
        mv = rq or out["quantities"]["max_von_mises"]
        out["indicative_stress"] = {"source": "radius_peak" if rq else "max_von_mises",
                                    "value_mpa": round(mv["values"][-1], 3),
                                    "gci_pct": mv.get("gci", {}).get("gci_fine_pct"), "verdict": mv["verdict"],
                                    "note": ("Yerel sıklaştırmaya rağmen yakınsamadı; değer gösterge niteliğinde. "
                                             "Mesh seviyesi ekle veya el hesabıyla karşılaştır." if rq else
                                             "Alt sınır: gerçek değer bundan yüksek. Radyusa yerel sıklaştırma "
                                             "yapıp tekrar çalıştır.")}
    elif kind:
        trace.append({"source": "max_von_mises", "name": names["max_von_mises"], "accepted": False,
                      "reason": f"tekillik ({kind}), q = {q_exp:.2f}"})
    for key in order:
        qq = out["quantities"][key]
        reason = None
        if len(qq["values"]) < 3:
            reason = "en az 3 seviyede değer yok" if qq["values"] else "veri yok"
        elif key in ("von_mises_outside_zone", "von_mises_away_from_peak") and _in_bc_zone(levels, key, float(cfg["exclusion_mm"])):
            reason = f"en az bir seviyede okuma mesnet/yük bölgesinde (< {float(cfg['exclusion_mm']):g} mm): tekil alan"
        elif kind == "geometrik" and sing_xyz and cand_loc.get(key) and h_coarse > 0 \
                and _dist(cand_loc[key], sing_xyz) <= 2 * h_coarse:
            reason = (f"konumu tekil noktaya {_dist(cand_loc[key], sing_xyz):.1f} mm uzaklıkta "
                      f"(< 2 × {h_coarse:g} mm): tekil alanın içinde")
        elif not qq["verdict"].startswith("güvenilir"):
            reason = qq["verdict"]
        gtxt = qq.get("gci", {}).get("gci_fine_pct")
        if reason or design:
            trace.append({"source": key, "name": names[key], "accepted": False,
                          "reason": reason or "daha öncelikli aday seçildi", "gci_pct": gtxt})
            continue
        design = (key, qq)
        trace.append({"source": key, "name": names[key], "accepted": True,
                      "reason": f"{qq['verdict']}, GCI %{gtxt}", "gci_pct": gtxt})
    out["decision_trace"] = trace
    if design:
        key, qq = design
        g = qq.get("gci", {})
        val = qq["conservative_value"]
        out["design_stress"] = {"source": key, "value_mpa": round(val, 3), "fine_mesh_mpa": round(qq["values"][-1], 3),
                                "extrapolated_mpa": round(g["extrapolated"], 3) if g.get("extrapolated") else None,
                                "gci_pct": g.get("gci_fine_pct"), "verdict": qq["verdict"],
                                "confidence": qq.get("confidence"), "location_mm": cand_loc.get(key)}
        if key == "von_mises_away_from_peak":
            out["design_stress"]["note"] = ("Tekil köşe hariç parçanın geri kalanındaki en yüksek gerilme. "
                                            "Köşenin kendisi bu modelle değerlendirilemez; radyuslu modelle tekrar kontrol et.")
        sy = cfg.get("yield_mpa")
        if sy:
            out["design_stress"]["safety_factor"] = round(float(sy) / val, 3)
            if val > float(sy):
                out["findings"].append("Tasarım gerilmesi akmayı aşıyor: doğrusal analiz geçersiz, plastisite gerekir.")
    elif kind == "geometrik":
        aw = out["quantities"]["von_mises_away_from_peak"]
        if aw["values"] and not _in_bc_zone(levels, "von_mises_away_from_peak", float(cfg["exclusion_mm"])):
            out["indicative_stress"] = {"source": "von_mises_away_from_peak", "value_mpa": round(aw["values"][-1], 3),
                                        "gci_pct": aw.get("gci", {}).get("gci_fine_pct"), "verdict": aw["verdict"],
                                        "note": "Güvenilir değil, yalnızca gösterge: tekil köşenin etki alanında "
                                                "kalan düğümler hâlâ bu değeri etkiliyor olabilir."}

    # ---- maksimum konumunun seviyeler arası kayması (GCI aynı noktayı varsayar)
    locs = [(lv.get("max_location") or {}).get("xyz_mm") for lv in levels]
    if all(locs) and len(locs) >= 2:
        shift = max(_dist(locs[i], locs[i + 1]) for i in range(len(locs) - 1))
        # Bilgi olarak raporlanır; simetrik ikiz tepelerde (delik iki yanı) büyük kayma normaldir.
        out["max_location_shift_mm"] = round(shift, 2)
    # ---- gerçek incelme oranı (Celik 2008: r > 1.3)
    if len(h) >= 2:
        rr = [h[i] / h[i + 1] for i in range(len(h) - 1) if h[i + 1] > 0]
        out["refinement_ratios"] = [round(r, 3) for r in rr]
        if rr and min(rr) < 1.3:
            out["warnings"].append(f"Gerçek incelme oranı {min(rr):.2f} < 1.3 (Celik 2008): GCI zayıf.")

    # ---- denge
    app = raw.get("applied_force_n")
    rea = last.get("reaction_n")
    vmag = raw.get("applied_force_vector_mag_n")
    other = raw.get("other_loads") or raw.get("reaction_incomplete")
    if app and rea and any(abs(a) > 0 for a in app) and not vmag and not other:
        resid = [a + r for a, r in zip(app, rea)]
        mag = math.sqrt(sum(a * a for a in app))
        err = 100 * math.sqrt(sum(x * x for x in resid)) / mag
        out["equilibrium"] = {"applied_n": app, "reaction_n": rea, "error_pct": round(err, 3),
                              "ok": err < 1.0}
        if err >= 1.0:
            out["findings"].append(f"Denge hatası %{err:.2f}: sınır şartı veya temas kurulumunu kontrol et.")
    elif rea and vmag and not other and not any(abs(a) > 0 for a in (app or [])) \
            and raw.get("applied_force_vector_count") == 1:
        rmag = math.sqrt(sum(r * r for r in rea))
        err = 100 * abs(rmag - vmag) / vmag
        out["equilibrium"] = {"applied_n": None, "applied_mag_n": vmag, "reaction_n": rea,
                              "reaction_mag_n": rmag, "error_pct": round(err, 3), "ok": err < 1.0,
                              "note": "Kuvvet vektörle tanımlı: büyüklükler karşılaştırıldı."}
        if err >= 1.0:
            out["findings"].append(f"Denge hatası %{err:.2f}: sınır şartı veya temas kurulumunu kontrol et.")
    elif rea and (other or (vmag and raw.get("applied_force_vector_count", 0) > 1)):
        out["equilibrium"] = {"skipped": True, "reaction_n": rea,
                              "note": ("Tepkisi okunamayan mesnet var" if raw.get("reaction_incomplete") else
                                       "Basınç/moment/kütle-atalet/termal ya da çoklu vektör yük var ("
                                       + ", ".join(raw.get("other_load_types", [])) + ")")
                                      + "; otomatik denge kontrolü yapılmadı. Toplam tepkiyi el hesabıyla karşılaştır."}

    # ---- mesnet başına tepki ve iç kuvvet oranı Σ|R_i| / |ΣR_i| (aşırı kısıtlama göstergesi)
    per = last.get("reactions_by_support") or []
    if per:
        mags = [math.sqrt(sum(c * c for c in s_["r_n"])) for s_ in per]
        tot = [sum(s_["r_n"][i] for s_ in per) for i in range(3)]
        tmag = math.sqrt(sum(c * c for c in tot))
        ratio = (sum(mags) / tmag) if tmag > 1e-9 else None
        out["support_reactions"] = {"supports": [{"name": s_["name"], "r_n": [round(c, 2) for c in s_["r_n"]],
                                                  "mag_n": round(m, 2)} for s_, m in zip(per, mags)],
                                    "internal_force_ratio": round(ratio, 2) if ratio else None}
        if len(per) >= 2 and (ratio is None or ratio > 3.0):
            out["findings"].append(
                "Mesnetler birbirine karşı çalışıyor: tek tek tepkilerin toplamı net tepkinin "
                + (f"{ratio:.1f} katı".replace(".", ",") if ratio else "çok üstünde (net tepki ≈ 0)")
                + ". Parça aşırı kısıtlanmış olabilir (ör. iki uçtan Fixed). Gerçek bağlantı gerçekten böyle mi? "
                  "Değilse mesnetlerden birini serbestlik bırakan bir tiple değiştir.")

        # Yük yolu kısa devresi: mesnetler aynı yönde çalışınca oran ≈ 1 kalır, ama biri neredeyse hiç yük
        # taşımıyorsa diğeri yükü parçaya uğramadan alıyor demektir (öz test 17.11: ikinci Fixed %99,9 aldı,
        # tepe 183 → 65 MPa). Eşik %5 ilk ayar.
        if len(per) >= 2 and sum(mags) > 1e-9:
            share = [m / sum(mags) for m in mags]
            out["support_reactions"]["shares"] = [round(x, 4) for x in share]
            idle = [s_["name"] for s_, x in zip(per, share) if x < 0.05]
            if idle:
                big = max(zip(share, per), key=lambda t: t[0])
                pct = f"{100 * big[0]:.1f}".replace(".", ",")
                out["findings"].append(
                    f"Mesnet neredeyse yüksüz: {', '.join(idle)} toplam tepkinin %5'inden azını taşıyor; yükün "
                    f"%{pct}'ini '{big[1]['name']}' alıyor. Ya bu mesnet gereksiz ya da diğeri yükü parçadan "
                    "geçirmeden kısa devre ediyor (aşırı kısıtlama); gerilme olduğundan düşük çıkabilir. "
                    "Gerçek bağlantıyı kontrol et.")

    # ---- montaj bağlantıları (temas, mafsal, kiriş bağlantısı)
    _connections(raw, out)

    # ---- silindirik/eğri yüze Fixed Support (cıvata deliği tipik hatası)
    for b in out["bcs"]:
        if b.get("suppressed") or b.get("type") != "FixedSupport":
            continue
        curved = [f for f in b.get("faces", []) if any(k in str(f.get("surface", "")) for k in ("Cylind", "Cone", "Torus"))]
        if curved:
            rad = sorted({r for f in curved for r in (f.get("edge_radii_mm") or [])})
            rtxt = f" (yarıçap ≈ {rad[0]:g} mm)" if rad else ""
            out["findings"].append(
                f"'{b['name']}' Fixed Support'u {len(curved)} silindirik/eğri yüze uygulanmış{rtxt}. "
                "Delik yüzeyini tamamen ankastre yapmak cıvata/pimin gerçek davranışından çok rijittir: "
                "deliğin kenarında yapay gerilme yığılması ve hatalı yük yolu oluşturur. Pim/mil için "
                "Cylindrical Support (teğetsel serbest), cıvata için ön yük + temas ya da rondela izi "
                "alanına Fixed/Remote Displacement daha gerçekçidir.")

    # ---- eleman derecesi ve kalınlık boyunca eleman sayısı
    eo = str(raw.get("element_order") or "")
    if "Linear" in eo:
        out["findings"].append("Eleman derecesi LINEAR: doğrusal tetrahedronlar eğilmede aşırı rijittir, gerilme ve "
                               "sehim düşük çıkar ve yakınsama çok yavaştır. Mesh > Element Order = Quadratic yap.")
    t_eff = raw.get("t_eff_mm")
    h_f = float(last.get("element_size_mm") or 0.0)
    if t_eff and h_f > 0:
        n_t = float(t_eff) / h_f
        out["elements_through_thickness"] = round(n_t, 2)
        if n_t < 2.0:
            out["findings"].append(f"En ince mesh'te kalınlık boyunca yalnızca ~{n_t:.1f} eleman var (etkin kalınlık "
                                   f"{float(t_eff):.3g} mm, eleman {h_f:g} mm). Eğilmede en az 2 kuadratik eleman "
                                   "önerilir; sonuç düşük çıkabilir.")

    # ---- mesh kalitesi
    qmin = last.get("quality_min")
    if qmin is not None and qmin < 0.1:
        out["findings"].append(f"Element Quality min {qmin:.3f} < 0.1: bozuk eleman var.")
    qavg = last.get("quality_avg")
    if qavg is not None and qavg < 0.7:
        out["findings"].append(f"Ortalama element quality {qavg:.3f} < 0.7: mesh kalitesi düşük.")
    sk = last.get("skewness_max")
    if sk is not None and sk > 0.9:
        out["findings"].append(f"Skewness maks {sk:.3f} > 0.9: bozuk elemanlar sonuçları etkileyebilir.")
    ar = last.get("aspect_max")
    if ar is not None and ar > 20:
        out["findings"].append(f"Aspect ratio maks {ar:.1f} > 20: uzamış elemanlar var.")

    # ---- büyük deformasyon
    size = cfg.get("model_size_mm")
    if size and dfm["values"] and dfm["values"][-1] > 0.05 * size:
        out["findings"].append("Deformasyon parça boyutunun %5'inden büyük: Large Deflection açılmalı.")

    if raw.get("user_sizings"):
        names = ", ".join(s["name"] for s in raw["user_sizings"])
        out["findings"].append(f"Kullanıcı lokal mesh kontrolleri ({names}) global boyutla orantılı ölçeklendi.")
    if dfm["verdict"].startswith("güvenilir"):
        out["findings"].append("Deformasyon yakınsadı: güvenilir.")
    out["ok"] = not out["errors"]
    return out
