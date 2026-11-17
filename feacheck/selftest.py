"""Öz test: hata kataloğunu Mechanical içinde tek tıkla koşar.

Açık modeli sırayla bilerek bozar (lineer eleman, 5 kat yük, ikinci Fixed, eğri yüze Fixed, mesnetsiz),
her vakada feacheck'in tamamını çalıştırır, modeli geri alır ve ham sonuçları bir klasöre yazar.
Sonra `feacheck katalog <klasör>` her vakayı beklenen davranışla karşılaştırıp özet rapor üretir.

İki parça: KAT_TAIL (IronPython, Mechanical içinde; yalnız ASCII) ve run_catalog (CPython).
"""
from __future__ import annotations

import html
import json
from pathlib import Path

# ---------------------------------------------------------------- Mechanical tarafı (IronPython 2.7)
# Şablonun sonundaki 'R["ok"] = bool(main())\ntojson(R)' bu kodla değiştirilir.
KAT_TAIL = r'''
from System.IO import Directory
def _kat_clone(o):
    # Derin kopya: sablon CFG icindeki listeleri (sizes_mm) yerinde degistirebilir, vakalar birbirini bozmasin.
    if isinstance(o, dict):
        return dict((k, _kat_clone(v)) for k, v in o.items())
    if isinstance(o, list):
        return [_kat_clone(v) for v in o]
    return o


_KAT_A = active_analysis()
_KAT_CFG0 = _kat_clone(CFG)
_KAT_OUT = OUTDIR + "\\katalog_" + DateTime.Now.ToString("yyyyMMdd_HHmmss")
Directory.CreateDirectory(_KAT_OUT)


def active_analysis():
    # Oz test boyunca agacta secim degisse de baslangictaki analiz kullanilir.
    return _KAT_A


class _KatSkip(Exception):
    pass


def _kat_reset(case_id):
    R.clear()
    R.update({"ok": False, "errors": [], "warnings": [], "levels": []})
    ST.clear()
    ST.update({"mesh": None, "orig_size": None, "usz": [], "added": [], "orig_growth": None,
               "orig_adaptive": None})
    CFG.clear()
    CFG.update(_kat_clone(_KAT_CFG0))
    if case_id != "temel":
        # Bozuk vakalarda yalniz tespit sinaniyor: sureyi kisaltmak icin ek seriler kapali.
        CFG["radius_refine"] = False
        CFG["global_extra_level"] = False


def _kat_faces():
    sc = length_scale(None)
    out = []
    for b in Model.Geometry.GetChildren(DataModelObjectCategory.Body, True):
        if b.Suppressed:
            continue
        for f in b.GetGeoBody().Faces:
            out.append({"id": f.Id, "c": [float(v) * sc for v in f.Centroid],
                        "area": float(f.Area) * sc * sc, "surf": str(f.SurfaceType)})
    return out


def _kat_bc_faces():
    used, sup, load = set(), [], []
    for c in _KAT_A.Children:
        t = type(c).__name__
        if getattr(c, "Suppressed", False) or (t not in SUPPORT_TYPES and t not in LOAD_TYPES):
            continue
        loc = getattr(c, "Location", None)
        ids = list(getattr(loc, "Ids", None) or []) if loc is not None else []
        used.update(ids)
        if t in SUPPORT_TYPES:
            sup.extend(ids)
        else:
            load.extend(ids)
    return used, sup, load


def _kat_dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5


def _kat_add_fixed(fid, name):
    fs = _KAT_A.AddFixedSupport()
    sel = ExtAPI.SelectionManager.CreateSelectionInfo(SelectionTypeEnum.GeometryEntities)
    sel.Ids = [fid]
    fs.Location = sel
    fs.Name = name
    return fs


def kat_temel():
    return (lambda: None), "degisiklik yok (referans)"


def kat_lineer():
    mesh = Model.Mesh
    old = mesh.ElementOrder
    mesh.ElementOrder = ElementOrder.Linear

    def undo():
        mesh.ElementOrder = old
    return undo, "Mesh > Element Order = Linear"


def _kat_set_vals(fld, vals):
    # Once indeksle (SetDiscreteValue), olmazsa listeyi topluca ata.
    try:
        for i, v in enumerate(vals):
            fld.Output.SetDiscreteValue(i, v)
    except Exception:
        fld.Output.DiscreteValues = vals


def kat_yuk_x5():
    saved = []
    errs = []

    def undo():
        for fld, vals in saved:
            _kat_set_vals(fld, vals)
    for c in _KAT_A.Children:
        if type(c).__name__ != "Force" or getattr(c, "Suppressed", False):
            continue
        comp = "Component" in str(getattr(c, "DefineBy", ""))
        for prop in (("XComponent", "YComponent", "ZComponent") if comp else ("Magnitude",)):
            try:
                fld = getattr(c, prop)
                vals = list(fld.Output.DiscreteValues)
            except Exception:
                continue
            if not vals:
                continue
            try:
                _kat_set_vals(fld, [Quantity(v.Value * 5.0, v.Unit) for v in vals])
                saved.append((fld, vals))
            except Exception as _e:
                errs.append("%s.%s: %s" % (c.Name, prop, _e))
                undo()
                raise _KatSkip("yuk degistirilemedi (%s)" % "; ".join(errs)[:150])
    if not saved:
        raise _KatSkip("analizde Force yok")
    return undo, "tum Force buyuklukleri x5"


def kat_ikinci_fixed():
    used, sup, load = _kat_bc_faces()
    faces = _kat_faces()
    byid = dict((f["id"], f) for f in faces)
    sc_ = [byid[i]["c"] for i in sup if i in byid]
    lc_ = [byid[i]["c"] for i in load if i in byid]
    best = None
    for f in faces:
        if f["id"] in used or "Plane" not in f["surf"]:
            continue
        d = min([_kat_dist(f["c"], p) for p in sc_ + lc_] or [0.0])
        score = d * (f["area"] ** 0.5)
        if best is None or score > best[0]:
            best = (score, f)
    if best is None:
        raise _KatSkip("serbest duzlem yuz yok")
    fs = _kat_add_fixed(best[1]["id"], "FEACHECK_KATALOG_Fixed2")
    return fs.Delete, "ikinci Fixed Support: yuz merkezi (%.1f, %.1f, %.1f) mm" % tuple(best[1]["c"])


def kat_egri_yuze_fixed():
    used, sup, load = _kat_bc_faces()
    cand = [f for f in _kat_faces() if f["id"] not in used and
            ("Cylind" in f["surf"] or "Cone" in f["surf"] or "Torus" in f["surf"])]
    if not cand:
        raise _KatSkip("modelde silindirik/egri yuz yok")
    f = max(cand, key=lambda x: x["area"])
    fs = _kat_add_fixed(f["id"], "FEACHECK_KATALOG_EgriFixed")
    return fs.Delete, "egri yuze ek Fixed Support: %s, %.0f mm2" % (f["surf"], f["area"])


def kat_mesnetsiz():
    sups = [c for c in _KAT_A.Children if type(c).__name__ in SUPPORT_TYPES and not getattr(c, "Suppressed", False)]
    for c in sups:
        c.Suppressed = True

    def undo():
        for c in sups:
            c.Suppressed = False
    return undo, "tum mesnetler bastirildi"


_KAT_CASES = [("temel", kat_temel), ("lineer", kat_lineer), ("yuk_x5", kat_yuk_x5),
              ("ikinci_fixed", kat_ikinci_fixed), ("egri_yuze_fixed", kat_egri_yuze_fixed),
              ("mesnetsiz", kat_mesnetsiz)]
_KAT_SUM = []
if _KAT_A is None:
    MessageBox.Show("Agacta bir analiz secili degil. Oz test icin Static Structural analizine tikla.", "feacheck")
else:
    for _cid, _fn in _KAT_CASES:
        _kat_reset(_cid)
        _t0 = DateTime.Now
        _undo, _note = None, ""
        try:
            try:
                _undo, _note = _fn()
            except Exception as _s:
                _why = str(_s) if isinstance(_s, _KatSkip) else "kurulamadi: %s" % _s
                R["catalog_case"] = {"id": _cid, "skipped": _why}
                _KAT_SUM.append("%s: atlandi (%s)" % (_cid, _why))
                _f = open(_KAT_OUT + "\\raw_" + _cid + ".json", "w")
                _f.write(tojson(R))
                _f.close()
                continue
            try:
                R["ok"] = bool(main())
            except Exception as _e:
                R["errors"].append(str(_e))
        finally:
            if _undo is not None:
                try:
                    _undo()
                except Exception as _e:
                    R["warnings"].append("oz test geri alma hatasi: %s" % _e)
                    _KAT_SUM.append("%s: GERI ALMA HATASI %s" % (_cid, _e))
        R["catalog_case"] = {"id": _cid, "change": _note}
        R["duration_s"] = (DateTime.Now - _t0).TotalSeconds
        _f = open(_KAT_OUT + "\\raw_" + _cid + ".json", "w")
        _f.write(tojson(R))
        _f.close()
        _KAT_SUM.append("%s: %s" % (_cid, "tamam" if R["ok"] else "durdu (" + "; ".join(R["errors"])[:80] + ")"))
    from System.Diagnostics import Process, ProcessStartInfo
    _psi = ProcessStartInfo(PYEXE, '-m feacheck katalog "%s"' % _KAT_OUT)
    _psi.UseShellExecute = False
    _psi.CreateNoWindow = True
    Process.Start(_psi)
    MessageBox.Show("Oz test bitti, model eski haline getirildi.\n\n" + "\n".join(_KAT_SUM) +
                    "\n\nOzet rapor tarayicida acilacak. Kendi sonuclarin icin tekrar Solve et.", "feacheck")
'''

# ---------------------------------------------------------------- CPython tarafı: beklenen davranış
def _has(res, *keys):
    return any(any(k in f for k in keys) for f in res.get("findings", []) + res.get("errors", []))


EXPECT = {
    "temel": ("Referans: kurulum uyarısı yok, tasarım ya da gösterge değeri var",
              lambda r, base: not _has(r, "Bağlantı:", "Fixed Support'u", "LINEAR", "aşırı kısıtlanmış", "akmayı aşıyor")
              and bool(r.get("design_stress") or r.get("indicative_stress"))),
    "lineer": ("'Eleman derecesi LINEAR' uyarısı",
               lambda r, base: _has(r, "LINEAR")),
    "yuk_x5": ("Gerilme ~5 katına çıkar; akma aşılırsa 'akmayı aşıyor' uyarısı",
               lambda r, base: _ratio(r, base) is not None and 4.5 < _ratio(r, base) < 5.5),
    "ikinci_fixed": ("ÖLÇÜM: iç kuvvet oranı (aşırı kısıtlama eşiği bu vakayla ayarlanacak)",
                     None),
    "egri_yuze_fixed": ("'Fixed Support silindirik/eğri yüze' uyarısı",
                        lambda r, base: _has(r, "silindirik/eğri yüze")),
    "mesnetsiz": ("Hata: 'mesnet yok', çözüm yapılmaz",
                  lambda r, base: _has(r, "mesnet yok") and not r.get("levels")),
}


def _peak(r):
    lv = [x for x in r.get("levels", []) if "max_vm" in x]
    return lv[-1]["max_vm"] if lv else None


def _ratio(r, base):
    a, b = _peak(r), _peak(base) if base else None
    return a / b if a and b else None


def run_catalog(folder: Path, open_browser: bool = True) -> Path:
    """Klasördeki raw_<vaka>.json dosyalarını değerlendirir, her vakanın raporunu ve özet sayfayı yazar."""
    from .analysis import evaluate
    from .report import write
    from .report_viz import tr

    folder = Path(folder)
    raws = {p.stem[4:]: json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("raw_*.json"))}
    results, rows = {}, []
    for cid, raw in raws.items():
        if (raw.get("catalog_case") or {}).get("skipped") or not raw.get("ok") and not raw.get("errors"):
            results[cid] = None
            continue
        su = raw.get("settings_used", {})
        st = {"exclusion_mm": su.get("exclusion_mm"), "gci_tol_pct": 5.0, "yield_mpa": raw.get("yield_lib_mpa"),
              "model_size_mm": su.get("lc_mm")}
        try:
            res = evaluate(raw, st) if raw.get("levels") else {"findings": [], "errors": raw.get("errors", []),
                                                                "levels": [], "warnings": raw.get("warnings", [])}
        except Exception as e:  # değerlendirme çökerse vaka başarısız sayılır
            res = {"findings": [], "errors": [f"değerlendirme hatası: {e}"], "levels": []}
        res.setdefault("errors", raw.get("errors", []))
        res["model"] = raw.get("model_name") or "model"
        results[cid] = res
        if res.get("levels"):
            write(res, folder / f"rapor_{cid}.html")
    base = results.get("temel")
    n_ok = n_fail = 0
    for cid, (what, check) in EXPECT.items():
        raw = raws.get(cid)
        res = results.get(cid)
        change = ((raw or {}).get("catalog_case") or {}).get("change") or ((raw or {}).get("catalog_case") or {}).get("skipped", "")
        if raw is None:
            status, detail = "yok", "koşulmadı"
        elif res is None:
            status, detail = "atlandı", change
        elif check is None:
            sr = res.get("support_reactions") or {}
            status = "ölçüm"
            detail = (f"iç kuvvet oranı Σ|R|/|ΣR| = {tr(sr.get('internal_force_ratio'), 3)}; "
                      f"ham tepe {tr(_peak(res))} MPa (temel {tr(_peak(base) if base else None)})")
        else:
            ok = bool(check(res, base))
            status = "geçti" if ok else "KALDI"
            n_ok += ok
            n_fail += not ok
            r = _ratio(res, base) if cid == "yuk_x5" else None
            detail = "; ".join((res.get("errors") or []) + [f for f in res.get("findings", [])][:2])[:300]
            if r:
                detail = f"tepe oranı {tr(r, 3)}. " + detail
        rows.append((cid, change, what, status, detail))
    model = (next(iter(raws.values()), {}) or {}).get("model_name", "model")
    cls = {"geçti": "ok", "KALDI": "bad", "ölçüm": "mid", "atlandı": "mid", "yok": "mid"}
    trs = "".join(f"<tr class='{cls[s]}'><td>{html.escape(c)}</td><td>{html.escape(ch)}</td><td>{html.escape(w)}</td>"
                  f"<td><b>{s}</b></td><td>{html.escape(d)}"
                  + (f" <a href='rapor_{c}.html'>rapor</a>" if (folder / f'rapor_{c}.html').exists() else "")
                  + "</td></tr>" for c, ch, w, s, d in rows)
    page = f"""<!DOCTYPE html><html lang="tr"><meta charset="utf-8"><title>feacheck öz test: {html.escape(model)}</title>
<style>body{{font:15px/1.55 "Segoe UI",system-ui,sans-serif;background:#F6F8FA;color:#1E2B38;margin:0}}
main{{max-width:1100px;margin:0 auto;padding:36px 24px}} h1{{font:600 28px Bahnschrift,"Segoe UI",sans-serif;margin:0 0 6px}}
table{{border-collapse:collapse;width:100%;background:#fff;font-size:14px}} td,th{{border-bottom:1px solid #D9E0E7;padding:8px;
text-align:left;vertical-align:top}} th{{color:#5F6B78;font-weight:500}} tr.ok b{{color:#2E7D4F}} tr.bad b{{color:#B42318}}
tr.mid b{{color:#A8650F}} .sub{{color:#5F6B78}}</style><main>
<h1>Öz test: {n_ok} geçti, {n_fail} kaldı</h1>
<p class="sub">{html.escape(model)}. Model her vakada bilerek bozuldu, feacheck koşuldu ve model geri alındı.
"Ölçüm" satırları geçti/kaldı değil, eşik ayarı için veri.</p>
<table><tr><th>Vaka</th><th>Ne değişti</th><th>Beklenen</th><th>Sonuç</th><th>Ayrıntı</th></tr>{trs}</table></main></html>"""
    out = folder / "ozet.html"
    out.write_text(page, encoding="utf-8")
    if open_browser:
        import webbrowser
        webbrowser.open(out.as_uri())
    return out
