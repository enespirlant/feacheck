"""Uygulama katmanı: Mechanical butonundan gelen ham sonucu raporlar; kurulum (setup)."""
from __future__ import annotations

import json
import sys
import traceback
import webbrowser
from datetime import datetime
from pathlib import Path

from .analysis import evaluate
from .report import write
from .store import Store


DEFAULT_SETTINGS = """# feacheck ayarlari - degistirip kaydet, bir sonraki calistirmada gecerli olur.
dugum_limiti: 128000        # ogrenci lisansi: 128000
gci_esigi_yuzde: 5          # bu belirsizligin altindaki sonuclar 'guvenilir'
mesh_seviye_sayisi: 3       # en az 3 (GCI icin)
incelme_orani: 1.5          # her seviyede eleman boyu bu oranla kuculur
yerel_siklastirma: false    # DENEYSEL: sadece kritik bolgeyi incelt (true/false)
radyus_siklastirma: true    # tepe bir radyustaysa ve cozulemiyorsa o yuze otomatik ek seri
radyus_ek_seviye: true      # radyus serisinde degisim gurultu duzeyinde ama yonu belirsizse 4. seviye
global_ek_seviye: true      # global seride ayni durumda, dugum limiti izin verirse 4. seviye
radyus_buyume_orani: 1.2    # radyus serisinde mesh buyume orani (radyus alti hacim de incelsin); 0 = kapali
"""


def load_settings(home: Path | None = None) -> dict:
    import yaml
    home = Path(home or Store.default().root)
    f = home / "ayarlar.yaml"
    if not f.exists():
        home.mkdir(parents=True, exist_ok=True)
        f.write_text(DEFAULT_SETTINGS, encoding="utf-8")
    d = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    return {"max_nodes": int(d.get("dugum_limiti", 128000)),
            "gci_tol_pct": float(d.get("gci_esigi_yuzde", 5)),
            "levels": max(3, int(d.get("mesh_seviye_sayisi", 3))),
            "ratio": float(d.get("incelme_orani", 1.5)),
            "local_refine": bool(d.get("yerel_siklastirma", False)),
            "radius_refine": bool(d.get("radyus_siklastirma", True)),
            "radius_extra_level": bool(d.get("radyus_ek_seviye", True)),
            "global_extra_level": bool(d.get("global_ek_seviye", True)),
            "radius_growth_rate": float(d.get("radyus_buyume_orani", 1.2) or 0)}


def template_cfg(st: dict, *, analysis, sizes=None, exclusion_mm=None, max_nodes=None) -> dict:
    """Mechanical şablonuna giden yapılandırma. Buton ve `feacheck converge` aynı kuralı kullanır:
    boyutlar boş bırakılırsa şablon Lc/8'i etkin kalınlıkla (2V/A) sınırlayarak kendisi hesaplar,
    dışlama mesafesi boşsa mesnet/yük yüz alanından (√A) hesaplanır."""
    return {"analysis": analysis, "sizes_mm": list(sizes or []), "exclusion_mm": exclusion_mm,
            "max_nodes": int(max_nodes or st["max_nodes"]), "top_k": 3000, "cleanup": True,
            "levels": st["levels"], "ratio": st["ratio"],
            "local_refine": st["local_refine"], "radius_refine": st["radius_refine"],
            "radius_extra_level": st.get("radius_extra_level", True),
            "global_extra_level": st.get("global_extra_level", True), "gci_tol_pct": st["gci_tol_pct"],
            "radius_growth_rate": st.get("radius_growth_rate", 1.2)}


ELHESAP_HELP = """# feacheck el hesabı karşılaştırmaları.
# Her giriş, adı Mechanical model adında geçen (büyük/küçük harf duyarsız) modele uygulanır.
# Tek değer:   deger: 113.3            (tolerans: 10  → ±%10)
# Aralık:      alt: 168, ust: 201      (iki bağımsız el hesabıyla sınırlanan durumlar için)
# Hesap için feacheck/handcalc.py: kiriş, burulma, Winkler eğri kiriş, delikli levha ve mil omzu Kt.
#
# L_braket_R5:
#   alt: 168
#   ust: 201
#   aciklama: "Alt: omuz radyusu Kt (Peterson). Üst: Winkler eğri kiriş iç lifi."
"""


def load_handcalc(model: str, home: Path | None = None) -> dict | None:
    """elhesap.yaml içinde model adıyla eşleşen ilk girişi döndürür (yoksa dosyayı yardım metniyle oluşturur)."""
    import yaml
    home = Path(home or Store.default().root)
    f = home / "elhesap.yaml"
    if not f.exists():
        try:
            home.mkdir(parents=True, exist_ok=True)
            f.write_text(ELHESAP_HELP, encoding="utf-8")
        except OSError:
            pass
        return None
    data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    m = (model or "").lower()
    for key, v in data.items():
        if str(key).lower() in m and isinstance(v, dict):
            return {"key": str(key), **v}
    return None


def attach_handcalc(res: dict, hc: dict | None) -> None:
    """Tasarım değerini (yoksa gösterge değeri) el hesabıyla karşılaştırıp sonuca ekler."""
    if not hc:
        return
    from .handcalc import compare
    ds = res.get("design_stress") or {}
    ind = res.get("indicative_stress") or {}
    fea = ds.get("fine_mesh_mpa") or ind.get("value_mpa")
    if fea is None:
        return
    try:
        if hc.get("deger") is not None:
            c = compare(float(fea), value=float(hc["deger"]), tol_pct=float(hc.get("tolerans", 10)))
        else:
            c = compare(float(fea), low=float(hc["alt"]), high=float(hc["ust"]))
    except (KeyError, TypeError, ValueError) as e:
        res.setdefault("warnings", []).append(f"elhesap.yaml '{hc.get('key')}' girişi okunamadı: {e}")
        return
    c.update({"key": hc["key"], "note": hc.get("aciklama", ""), "fea_mpa": float(fea),
              "fea_kind": "ince mesh tasarım değeri" if ds else "gösterge değer"})
    res["hand_calc"] = c
    if not c["ok"]:
        res.setdefault("findings", []).append(
            f"El hesabıyla uyuşmuyor: {c['text']}. Ya FEA modelinde (yük, mesnet, malzeme) ya da el hesabının "
            "varsayımlarında bir fark var; ikisini de kontrol et.")


def finalize(raw: dict, *, model_name: str | None = None, yield_mpa: float | None = None, tol: float | None = None,
             store: Store | None = None, open_browser: bool = True, materials_xml: Path | None = None,
             yield_source: str | None = None, yuk_tipi: str | None = None):
    ysrc_override = yield_source
    if tol is None:
        tol = load_settings(store.root if store else None)["gci_tol_pct"]
    # Öncelik: kullanıcı girişi > malzeme API > Engineering Data XML. Tahmin yok.
    yield_source = (ysrc_override or "kullanıcı girişi") if yield_mpa else ""
    if not yield_mpa and raw.get("yield_mpa"):
        yield_mpa, yield_source = raw["yield_mpa"], "malzeme verisi (API)"
    elif not yield_mpa and materials_xml and Path(materials_xml).exists():
        from .matml import read_yields
        ys = read_yields(Path(materials_xml))
        mats = raw.get("materials", [])
        used = [ys[m] for m in mats if m in ys]
        if used and len(used) == len(mats):
            yield_mpa, yield_source = min(used), "malzeme verisi (Engineering Data)"
        else:
            raw.setdefault("warnings", []).append(
                "Modeldeki malzemelerin akma değeri malzeme dosyasında bulunamadı "
                f"({', '.join(m for m in mats if m not in ys) or '–'}); emniyet katsayısı hesaplanmadı. "
                "Akma değerini elle gir.")
    s = raw.get("settings_used", {})
    vol = raw.get("volume_mm3") or 0.0
    cfg = {"exclusion_mm": s.get("exclusion_mm", 0.0), "exclusion_rule": s.get("exclusion_rule"),
           "sizes_mm": s.get("sizes_mm"),
           "max_nodes": s.get("max_nodes", 128_000), "gci_tol_pct": tol, "yield_mpa": yield_mpa,
           "model_size_mm": vol ** (1 / 3) if vol > 0 else None}
    res = evaluate(raw, cfg)
    res["yield_source"] = yield_source
    res.update({"model": model_name or raw.get("model_name") or "Mechanical modeli", "volume_mm3": vol,
                "settings": cfg, "duration_s": round(raw.get("duration_s", 0.0), 1),
                "timestamp": datetime.now().isoformat(timespec="seconds")})
    if raw.get("materials"):
        res["materials"] = raw["materials"]
    store = store or Store.default()
    attach_handcalc(res, load_handcalc(res["model"], store.root))
    from .vehicle import attach_vehicle
    attach_vehicle(res, raw, store.root, yuk_tipi)
    rid, folder = store.save(res)
    html = write(res, folder / "report.html")
    if open_browser:
        webbrowser.open(html.as_uri())
    return rid, html, res


def finalize_file(path: Path, **kw):  # noqa: D401
    """Butondan çağrılır; pencere olmadığı için hatalar dosyaya yazılır."""
    log = Store.default().root / "last_error.txt"
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return finalize(raw, **kw)
    except Exception:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(traceback.format_exc(), encoding="utf-8")
        raise


# ------------------------------------------------------------------ kurulum

BUTTON_HEAD = r'''# feacheck Mechanical butonu - "feacheck setup" tarafindan uretildi, elle degistirme.
# Kullanim: agacta analizini sec, bu scripti calistir.
PYEXE = r"__PYEXE__"
OUTDIR = r"__OUTDIR__"
import clr
clr.AddReference("Microsoft.VisualBasic")
clr.AddReference("System.Windows.Forms")
from Microsoft.VisualBasic import Interaction
from System.Windows.Forms import MessageBox
from System import DateTime
_T0 = DateTime.Now
'''

BUTTON_FOOT = r'''
R["duration_s"] = (DateTime.Now - _T0).TotalSeconds
_raw = OUTDIR + "\\raw_" + DateTime.Now.ToString("yyyyMMdd_HHmmss") + ".json"
_f = open(_raw, "w")
_f.write(tojson(R))
_f.close()
from System.Diagnostics import Process, ProcessStartInfo
from System.IO import File
_YIELD = ""
_MATXML = ""
if R.get("yield_mpa"):
    _YIELD = "%.6g" % R["yield_mpa"]
elif R["ok"]:
    _exp = getattr(Model.Materials, "Export", None)
    if _exp is not None:
        _MATXML = OUTDIR + "\\materials_" + DateTime.Now.ToString("yyyyMMdd_HHmmss") + ".xml"
        _exp(_MATXML)
        if not File.Exists(_MATXML):
            _MATXML = ""
_YSRC = ""
if not _YIELD and not _MATXML and R["ok"]:
    _lib = R.get("yield_lib_mpa")
    if _lib:
        _msg = ("Malzeme: %s\nAnsys kutuphanesindeki akma dayanimi: %g MPa.\n\n"
                "Dogruysa OK'a bas; farkli bir malzeme verisi kullaniyorsan degeri degistir." % (", ".join(R.get("materials", [])), _lib))
        _YIELD = Interaction.InputBox(_msg, "feacheck", "%g" % _lib)
        if _YIELD.strip() == "%g" % _lib:
            _YSRC = "Ansys kutuphane degeri (onaylandi)"
    else:
        _YIELD = Interaction.InputBox(
            "Malzemede akma dayanimi bulunamadi (%s).\nAkma dayanimi (MPa)? Bos birakirsan guvenlik katsayisi hesaplanmaz."
            % ", ".join(R.get("materials", [])), "feacheck", "")
from System.IO import Path as _IOPath


def _arac_dolu(p):
    if not File.Exists(p):
        return False
    for _ln in File.ReadAllLines(p):
        _s = _ln.split("#")[0].strip()
        if _s.startswith("kutle:"):
            try:
                return float(_s[6:].strip()) > 0
            except Exception:
                return False
    return False


_HOME = _IOPath.GetDirectoryName(OUTDIR)
_TIP = ""
if R["ok"] and _arac_dolu(_HOME + "\\arac.yaml"):
    _mem = _HOME + "\\yuk_tipleri.txt"
    _key = (R.get("model_name", "") or "model").split("|")[0].strip()
    _old = {}
    if File.Exists(_mem):
        for _ln in File.ReadAllLines(_mem):
            if "|" in _ln:
                _k, _v = _ln.rsplit("|", 1)
                _old[_k] = _v.strip()
    _codes = {"1": "duzey", "2": "cekis", "3": "yanal", "0": "yok"}
    _rev = dict((_v, _k) for _k, _v in _codes.items())
    _ans = Interaction.InputBox(
        "Modeldeki kuvvet aracta neyi temsil ediyor? (teker basina)\n\n"
        "1 = teker dusey yuku\n2 = cekis kuvveti\n3 = yanal kuvvet\n0 = arac yuku degil\n\n"
        "Secim bu model icin hatirlanir; ayni kalacaksa OK'a bas.",
        "feacheck", _rev.get(_old.get(_key, ""), "1"))
    _TIP = _codes.get(_ans.strip(), "")
    if _TIP:
        _old[_key] = _TIP
        File.WriteAllLines(_mem, ["%s|%s" % (_k, _v) for _k, _v in _old.items()])
_args = '-m feacheck finalize "%s"' % _raw
if _TIP:
    _args += " --yuk-tipi %s" % _TIP
if _MATXML:
    _args += ' --materials-xml "%s"' % _MATXML
if _YIELD.strip():
    _args += " --yield %s" % _YIELD.strip().replace(",", ".")
if _YSRC:
    _args += ' --yield-source "%s"' % _YSRC
_psi = ProcessStartInfo(PYEXE, _args)
_psi.UseShellExecute = False
_psi.CreateNoWindow = True
Process.Start(_psi)
if R["ok"]:
    MessageBox.Show("Bitti. Rapor birkac saniye icinde tarayicida acilacak.\n\n"
                    "Not: modelin mesh ve cozumu artik guncel degil; kendi sonuclarin icin tekrar Solve et.",
                    "feacheck")
else:
    MessageBox.Show("Durdu: %s" % "; ".join(R["errors"]), "feacheck")
'''

BAT = r'''@echo off
chcp 65001 >nul
if "%~1"=="" (
  echo Bir .mechdb dosyasini bu dosyanin uzerine surukleyip birak.
  pause
  exit /b
)
__ACTIVATE__
set /p Y=Akma dayanimi MPa (bos birakabilirsin):
if "%Y%"=="" (
  "__PYEXE__" -m feacheck converge "%~1"
) else (
  "__PYEXE__" -m feacheck converge "%~1" --yield %Y%
)
pause
'''


def _desktop() -> Path:
    if sys.platform == "win32":
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(260)
            ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buf)  # CSIDL_DESKTOPDIRECTORY
            if buf.value:
                return Path(buf.value)
        except Exception:
            pass
    return Path.home() / "Desktop"


LOADER = r'''# feacheck butonu (yukleyici) - "feacheck setup" tarafindan uretildi.
# Her calistirmada en guncel feacheck kodunu uretir ve calistirir; setup'i tekrarlamaya gerek yok.
from System.Diagnostics import Process, ProcessStartInfo
_psi = ProcessStartInfo(r"__PYEXE__", "-m feacheck build-button")
_psi.UseShellExecute = False
_psi.CreateNoWindow = True
_p = Process.Start(_psi)
_p.WaitForExit()
if _p.ExitCode != 0:
    from System.Windows.Forms import MessageBox
    MessageBox.Show("feacheck guncel scripti uretemedi (cikis kodu %d). Eski surum calistirilmayacak.\n"
                    "Komut satirinda 'python -m feacheck build-button' calistirip hatayi gor." % _p.ExitCode,
                    "feacheck")
else:
    execfile(r"__FULL__")
'''


def build_button(home: Path | None = None, pyexe: str | None = None) -> Path:
    """Güncel şablondan tam buton scriptini üretir (yükleyici her çalıştırmada çağırır)."""
    from cadfea.script_builder import pylit

    from .mech_converge import TEMPLATE
    home = Path(home or Store.default().root)
    inbox = home / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    pyexe = pyexe or sys.executable
    cfg = template_cfg(load_settings(home), analysis="__ACTIVE__")
    body = TEMPLATE.replace("__CFG_LITERAL__", pylit(cfg)).replace(
        'R["ok"] = bool(main())',
        'try:\n    R["ok"] = bool(main())\nexcept Exception as _e:\n    R["errors"].append(str(_e))')
    head = BUTTON_HEAD.replace("__PYEXE__", pyexe).replace("__OUTDIR__", str(inbox))
    full = home / "feacheck_button_full.py"
    full.write_text(head + body + BUTTON_FOOT, encoding="ascii")
    return full


def build_selftest(home: Path | None = None, pyexe: str | None = None) -> Path:
    """Öz test scripti: şablon + hata kataloğu döngüsü (yükleyici her çalıştırmada çağırır)."""
    from cadfea.script_builder import pylit

    from .mech_converge import TEMPLATE
    from .selftest import KAT_TAIL
    home = Path(home or Store.default().root)
    inbox = home / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    pyexe = pyexe or sys.executable
    cfg = template_cfg(load_settings(home), analysis="__ACTIVE__")
    tail = 'R["ok"] = bool(main())\ntojson(R)\n'
    if tail not in TEMPLATE:
        raise RuntimeError("şablonun son satırları beklenen biçimde değil; öz test eklenemedi")
    body = TEMPLATE.replace("__CFG_LITERAL__", pylit(cfg)).replace(tail, KAT_TAIL)
    head = BUTTON_HEAD.replace("__PYEXE__", pyexe).replace("__OUTDIR__", str(inbox))
    full = home / "feacheck_oztest_full.py"
    full.write_text(head + body, encoding="ascii")
    return full


def setup(home: Path | None = None, desktop: Path | None = None, pyexe: str | None = None) -> dict:
    home = Path(home or Store.default().root)
    inbox = home / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    pyexe = pyexe or sys.executable
    full = build_button(home, pyexe)
    button = home / "feacheck_button.py"
    button.write_text(LOADER.replace("__PYEXE__", pyexe).replace("__FULL__", str(full)), encoding="ascii")
    kat_full = build_selftest(home, pyexe)
    oztest = home / "feacheck_oztest.py"
    oztest.write_text(LOADER.replace("build-button", "build-selftest").replace("__PYEXE__", pyexe)
                      .replace("__FULL__", str(kat_full)), encoding="ascii")

    env = Path(pyexe).parent
    act = env.parent.parent / "Scripts" / "activate.bat"
    activate = f'call "{act}" {env.name}' if act.exists() and env.parent.name == "envs" else ""
    desktop = Path(desktop or _desktop())
    bat = desktop / "feacheck.bat"
    try:
        bat.write_text(BAT.replace("__PYEXE__", pyexe).replace("__ACTIVATE__", activate), encoding="utf-8")
    except OSError:
        bat = home / "feacheck.bat"
        bat.write_text(BAT.replace("__PYEXE__", pyexe).replace("__ACTIVATE__", activate), encoding="utf-8")
    return {"button": button, "oztest": oztest, "bat": bat, "home": home,
            "one_liner": f'execfile(r"{button}")', "oztest_one_liner": f'execfile(r"{oztest}")'}
