import math

import pytest

from feacheck.analysis import evaluate
from feacheck.converge import auto_sizes
from feacheck.gci import gci3, rep_h
from feacheck.report import write
from feacheck.store import Store


def test_gci_recovers_order_and_exact_value():
    h = [1.0, 1.5, 2.25]
    phi = [10 + 0.3 * x ** 2 for x in h]           # p = 2, gerçek değer 10
    g = gci3(phi, h)
    assert g["status"] == "converging"
    assert g["p"] == pytest.approx(2.0, abs=1e-6)
    assert g["extrapolated"] == pytest.approx(10.0, abs=1e-9)


def test_gci_variable_ratio():
    h = [1.0, 1.4, 2.3]
    phi = [5 + 0.2 * x ** 1.5 for x in h]
    g = gci3(phi, h)
    assert g["p"] == pytest.approx(1.5, abs=1e-5) and g["extrapolated"] == pytest.approx(5, abs=1e-6)


def test_gci_flags_divergence():
    assert gci3([169.45, 138.87, 125.04], [1, 2, 4])["status"] == "diverging"   # gerçek aks verisi


def _aks_raw():
    """Aksın gerçekçi taklidi: tepe mesnette büyüyor, 20 mm ötesi kiriş teorisine yakınsıyor."""
    lv = []
    for size, n, vm, vmo, d, pr in [(4.97, 6100, 126.0, 113.2, 0.85030, 113.3),
                                    (3.31, 19800, 141.0, 114.1, 0.85055, 113.85),
                                    (2.21, 63000, 162.0, 114.45, 0.85068, 114.0)]:
        lv.append({"element_size_mm": size, "nodes": n, "elements": n // 4, "quality_min": 0.4, "quality_avg": 0.8,
                   "skewness_max": 0.6, "state": "Solved", "max_vm": vm, "max_def": d,
                   "max_location": {"value": vm, "xyz_mm": [0, 10, 0], "dist_to_bc_mm": 0.0},
                   "max_outside_zone": {"value": vmo, "xyz_mm": [0, 10, 20.1], "dist_to_bc_mm": 20.1},
                   "reaction_n": [0.0, 500.0, 0.0], "probe": {"value": pr, "dist_mm": 0.3}})
    return {"ok": True, "analysis": "CADFEA Static", "levels": lv, "probe_xyz_mm": [0, 10, 20.9], "warnings": [], "errors": [],
            "applied_force_n": [0.0, -500.0, 0.0]}


def test_aks_verdict():
    r = evaluate(_aks_raw(), {"exclusion_mm": 20, "gci_tol_pct": 5, "yield_mpa": 250, "model_size_mm": 39.7})
    assert r["singularity"]["detected"]
    ds = r["design_stress"]
    assert ds["source"] == "von_mises_probe"
    assert ds["value_mpa"] == pytest.approx(114.0, abs=0.3)       # el hesabı z=20.9 mm: 114.0 MPa
    assert ds["verdict"] == "güvenilir"
    assert r["quantities"]["max_deformation"]["verdict"] == "güvenilir"
    assert r["equilibrium"]["ok"]


def test_auto_sizes_aks():
    sizes, ex = auto_sizes(math.pi * 10 ** 2 * 200)
    assert sizes[0] == pytest.approx(4.97, abs=0.01) and ex == pytest.approx(19.9, abs=0.1)


def test_report_and_store(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = evaluate(_aks_raw(), {"exclusion_mm": 20, "gci_tol_pct": 5, "yield_mpa": 250, "model_size_mm": 39.7})
    r.update({"model": "aks.mechdb", "timestamp": "2026-11-14T08:00:00", "duration_s": 1,
              "settings": {"exclusion_mm": 20, "max_nodes": 128000, "gci_tol_pct": 5}})
    st = Store.find_or_here()
    st.init()
    rid, folder = st.save(r)
    html = write(r, folder / "report.html").read_text(encoding="utf-8")
    assert "Tekillik ayrıldı" in html and "<svg" in html
    assert st.log()[0]["id"] == rid


def test_oscillatory_small_spread_is_reliable():
    from feacheck.analysis import _quantity
    lv = [{"x": v} for v in (112.3, 114.6, 113.8)]       # gerçek aks bölge dışı değerleri
    q = _quantity("x", "MPa", lv, 5.0, [0.2, 0.13, 0.09])
    assert q["gci"]["status"] == "oscillatory" and q["verdict"] == "güvenilir (salınımlı)"


def test_singularity_with_oscillating_max():
    """Gerçek aks verisi: maks 125.9 -> 124.9 -> 138 (salınımlı ama sonunda büyüyor)."""
    from test_feacheck import _aks_raw
    raw = _aks_raw()
    for lv, v in zip(raw["levels"], (125.9, 124.9, 138.0)):
        lv["max_vm"] = v
    r = evaluate(raw, {"exclusion_mm": 20, "gci_tol_pct": 5, "yield_mpa": 250, "model_size_mm": 39.7})
    assert r["singularity"]["detected"] and r["design_stress"]["source"] == "von_mises_probe"


def test_setup_and_finalize(tmp_path):
    import ast
    from feacheck.app import finalize, setup
    r = setup(home=tmp_path / "fc", desktop=tmp_path / "desk", pyexe=r"C:\env\python.exe")
    loader = r["button"].read_text(encoding="ascii")
    ast.parse(loader)
    assert "build-button" in loader
    src = (tmp_path / "fc" / "feacheck_button_full.py").read_text(encoding="ascii")
    ast.parse(src)
    assert '"__ACTIVE__"' in src and "Process.Start" in src and "except Exception as _e" in src
    assert r["bat"].exists()
    raw = _aks_raw()
    raw.update({"volume_mm3": 62831.85, "duration_s": 24.0,
                "settings_used": {"sizes_mm": [4.97, 3.31, 2.21], "exclusion_mm": 19.9, "max_nodes": 128000}})
    rid, html, res = finalize(raw, yield_mpa=250, store=Store(tmp_path / "st"), open_browser=False, tol=5.0)
    assert res["singularity"]["detected"] and html.exists()


def _lbracket_raw(peak, away, sharp=True):
    """L-braket taklidi: keskin köşede tepe büyür (q≈0.46), köşeden uzakta yakınsar."""
    lv = []
    for (size, n), pk, aw in zip([(4.35, 6000), (2.9, 18000), (1.93, 56000)], peak, away):
        lv.append({"element_size_mm": size, "h_eff_mm": size, "nodes": n, "max_vm": pk, "max_def": 0.20,
                   "quality_min": 0.4, "quality_avg": 0.8, "skewness_max": 0.6, "aspect_max": 3.0,
                   "max_location": {"value": pk, "xyz_mm": [10, 15, 10], "dist_to_bc_mm": 55.0},
                   "max_outside_zone": {"value": pk, "xyz_mm": [10, 15, 10], "dist_to_bc_mm": 55.0},
                   "max_away_from_peak": {"value": aw, "xyz_mm": [40, 15, 0], "dist_to_bc_mm": 40.0},
                   "probe": {"value": pk}, "reaction_n": [1000.0, 0, 0]})
    return {"ok": True, "levels": lv, "warnings": [], "errors": [], "applied_force_n": [0, 0, 0],
            "applied_force_vector_mag_n": 1000.0, "applied_force_vector_count": 1, "probe_xyz_mm": [10, 15, 10]}


def test_geometric_singularity_sharp_corner():
    peak = [100 * (4.35 / h) ** 0.456 for h in (4.35, 2.9, 1.93)]           # 100, 120, 145
    r = evaluate(_lbracket_raw(peak, [60.0, 61.0, 61.3]),
                 {"exclusion_mm": 17, "gci_tol_pct": 5, "yield_mpa": 250, "model_size_mm": 35})
    assert r["singularity"]["detected"] and r["singularity"]["kind"] == "geometrik"
    assert r["design_stress"]["source"] == "von_mises_away_from_peak"
    assert r["equilibrium"]["ok"] and r["equilibrium"]["applied_n"] is None   # vektörle tanımlı kuvvet


def test_filleted_corner_converges():
    r = evaluate(_lbracket_raw([88.0, 92.0, 93.3], [60.0, 61.0, 61.3]),
                 {"exclusion_mm": 17, "gci_tol_pct": 5, "yield_mpa": 250, "model_size_mm": 35})
    assert not r["singularity"]["detected"]
    assert r["design_stress"]["source"] == "max_von_mises" and r["design_stress"]["verdict"].startswith("güvenilir")


def test_local_mode_uses_local_size():
    raw = _lbracket_raw([88.0, 92.0, 93.3], [60, 61, 61.3])
    raw["mode"] = "local"
    for lv, n in zip(raw["levels"], (6000, 7000, 9000)):    # yerel incelmede düğüm az artar
        lv["nodes"] = n
    r = evaluate(raw, {"exclusion_mm": 17, "gci_tol_pct": 5, "yield_mpa": 250, "model_size_mm": 35})
    assert r["mode"] == "local" and r["quantities"]["max_von_mises"]["gci"]["r21"] == pytest.approx(1.503, abs=0.01)


def test_matml_yield(tmp_path):
    from feacheck.matml import read_yields
    xml = """<?xml version="1.0"?><EngineeringData><Materials><MatML_Doc>
<Material><BulkDetails><Name>Structural Steel</Name>
 <PropertyData property="pr1"><Data format="string">-</Data>
  <ParameterValue parameter="pa1" format="float"><Data>250000000</Data></ParameterValue></PropertyData>
</BulkDetails></Material>
<Metadata><ParameterDetails id="pa1"><Name>Tensile Yield Strength</Name><Units><Unit><Name>Pa</Name></Unit></Units></ParameterDetails></Metadata>
</MatML_Doc></Materials></EngineeringData>"""
    f = tmp_path / "m.xml"
    f.write_text(xml)
    assert read_yields(f) == {"Structural Steel": pytest.approx(250.0)}


def test_settings_file(tmp_path):
    from feacheck.app import load_settings
    s = load_settings(tmp_path)
    assert s["max_nodes"] == 128000 and s["local_refine"] is False and (tmp_path / "ayarlar.yaml").exists()


def test_bc_locations_in_report(tmp_path):
    raw = _aks_raw()
    raw["tree"] = [{"type": "FixedSupport", "name": "Fixed Support", "state": "FullyDefined", "suppressed": False,
                    "faces": [{"id": 12, "c": [80.0, 15.0, 5.0], "area_mm2": 300.0}]},
                   {"type": "Force", "name": "Force", "state": "FullyDefined", "suppressed": False,
                    "faces": [{"id": 30, "c": [5.0, 15.0, 70.0], "area_mm2": 300.0}]},
                   {"type": "AnalysisSettings", "name": "Analysis Settings", "state": "FullyDefined"}]
    r = evaluate(raw, {"exclusion_mm": 20, "gci_tol_pct": 5})
    assert [b["name"] for b in r["bcs"]] == ["Fixed Support", "Force"]
    html = write(r, tmp_path / "r.html").read_text(encoding="utf-8")
    assert "Sınır şartları" in html and "(80; 15; 5)" in html and "(5; 15; 70)" in html


# ---- Faz 0: kenar durumları
from feacheck.gci import gci3 as _g3


def test_gci_guards():
    assert _g3([1.0, 1.1, 1.2], [1.0, 1.0, 1.5])["status"] == "invalid"        # r21 = 1
    assert _g3([1.0, 1.0, 1.0], [1.0, 1.5, 2.25])["status"] == "exact"
    assert _g3([1.0, 1.1, 0.95], [1.0, 1.5, 2.25])["status"] == "oscillatory"
    # oran ~1 -> p ~ 0: sıfıra bölme olmamalı, asimptotik değil işaretlenmeli
    g = _g3([1.0, 1.01, 1.0201], [1.0, 1.5, 2.25])
    assert g["status"] in ("converging", "diverging")
    if g["status"] == "converging":
        assert g.get("non_asymptotic") and g["fs"] == 3.0


def test_gci_non_asymptotic_uses_fs3():
    g = _g3([100.0, 100.5, 110.0], [1.0, 1.5, 2.25])     # p çok büyük
    assert g["non_asymptotic"] and g["fs"] == 3.0 and g["p"] <= 4.0


def test_quantity_missing_middle_level():
    from feacheck.analysis import _quantity
    levels = [{"probe": {"value": 100.0}}, {"probe": None}, {"probe": {"value": 101.0}}, {"probe": {"value": 101.2}}]
    q = _quantity("probe.value", "MPa", levels, 5, [4.0, 3.0, 2.0, 1.0])
    assert q["values"] == [100.0, 101.0, 101.2]
    assert q["gci"]["r21"] == 2.0 and q["gci"]["r32"] == 2.0    # h=[4,2,1], ortadaki 3 atıldı
    assert q["missing_levels"] == 1


def test_bc_singularity_rejects_unreliable_probe():
    raw = _aks_raw()
    for lv, v in zip(raw["levels"], (100.0, 120.0, 150.0)):      # probe ıraksıyor
        lv["probe"]["value"] = v
    r = evaluate(raw, {"exclusion_mm": 20, "gci_tol_pct": 5, "yield_mpa": 250})
    assert r["singularity"]["kind"] == "sınır şartı"
    probe = next(t for t in r["decision_trace"] if t["source"] == "von_mises_probe")
    assert not probe["accepted"]
    assert r.get("design_stress", {}).get("source") != "von_mises_probe"


def test_finalize_user_yield_wins(tmp_path):
    from feacheck.app import finalize
    from feacheck.store import Store
    raw = _aks_raw()
    raw["yield_mpa"] = 999.0
    _, _, res = finalize(raw, yield_mpa=250, store=Store(tmp_path / "st"), open_browser=False, tol=5.0)
    assert res["settings"]["yield_mpa"] == 250 and res["yield_source"] == "kullanıcı girişi"


def test_store_same_second_no_crash(tmp_path):
    from feacheck.store import Store
    st = Store(tmp_path / "st")
    a, _ = st.save({"model": "x"})
    b, _ = st.save({"model": "x"})
    assert a != b


def test_cli_comma_number():
    from feacheck.cli import _num
    assert _num("250,5") == 250.5


# ---- dışlama mesafesi (√A kuralı)
from feacheck.analysis import exclusion_distance  # noqa: E402


def test_dislama_kompakt_parca_eski_kuralla_ayni():
    # L-braket: mesnet ve yük yüzü 30×10 = 300 mm² → √A = 17,3; Lc/2 = 17,4
    ex, rule = exclusion_distance({"F": [{"area_mm2": 300.0}], "S": [{"area_mm2": 300.0}]}, 34.76, 4.345)
    assert ex == 17.32 and rule.startswith("√A")


def test_dislama_ince_parca_kuculur():
    # 500×40×3 mm şerit: uç yüzü 120 mm² → √A ≈ 11,0 (eski kural Lc/2 ≈ 19,6 mm idi)
    lc = (500 * 40 * 3) ** (1 / 3)
    ex, _ = exclusion_distance({"Fix": [{"area_mm2": 120.0}], "F": [{"area_mm2": 120.0}]}, lc, 2.8)
    assert 10.5 < ex < 11.5 and ex < lc / 2


def test_dislama_sinirlar():
    assert exclusion_distance({"F": [{"area_mm2": 1.0}]}, 40.0, 3.0)[0] == 6.0      # alt sınır 2·h0
    assert exclusion_distance({"F": [{"area_mm2": 1e5}]}, 40.0, 3.0)[0] == 20.0     # üst sınır Lc/2
    assert exclusion_distance({}, 40.0, 3.0) == (20.0, "Lc/2 (yüz alanı okunamadı)")


def test_dislama_sablonla_ayni_kural():
    """Mechanical şablonu aynı kuralı IronPython'da tekrarlıyor; şablon kodunu çalıştırıp karşılaştır."""
    from feacheck.mech_converge import TEMPLATE
    start = TEMPLATE.index('    if CFG.get("exclusion_mm") is None:')
    end = TEMPLATE.index('        R["exclusion_rule"] = rule') + len('        R["exclusion_rule"] = rule')
    block = "\n".join(l[4:] for l in TEMPLATE[start:end].splitlines())
    for bcl, lc, h0 in [({"a": [{"area_mm2": 300.0}], "b": [{"area_mm2": 300.0}]}, 34.76, 4.345),
                        ({"a": [{"area_mm2": 1.0}]}, 40.0, 3.0), ({"a": [{"area_mm2": 1e5}]}, 40.0, 3.0),
                        ({"a": [{"area_mm2": 120.0}, {"area_mm2": 80.0}]}, 39.1, 2.8)]:
        env = {"CFG": {"exclusion_mm": None, "sizes_mm": [h0]}, "R": {"bc_locations": bcl}, "lc": lc}
        exec(block, env)
        assert env["CFG"]["exclusion_mm"] == exclusion_distance(bcl, lc, h0)[0]


def test_converge_yolu_buton_ile_ayni_ayarlari_kullanir(monkeypatch, tmp_path):
    """`feacheck converge` boyutları kendisi hesaplamamalı (kalınlık sınırı şablonda) ve ayarlar.yaml'ı uygulamalı."""
    import json as _json
    from pathlib import Path as _P
    import feacheck.converge as cv
    from feacheck.app import template_cfg
    seen = {}
    monkeypatch.setattr(cv, "pylit", lambda c: seen.setdefault("cfg", dict(c)) and "{}")
    raw = _json.loads((_P(__file__).parent / "fixtures" / "lbraket_keskin_yuzbilgili.json").read_text(encoding="utf-8"))
    raw.setdefault("settings_used", {}).update({"sizes_mm": [4.345, 2.897, 1.931], "exclusion_mm": 17.38})

    class FakeSession:
        def run(self, code):
            if "names = [a.Name" in code:
                return "100000.0|1|Static Structural"
            if code.startswith("ExtAPI.DataModel.Project.Open"):
                return ""
            return _json.dumps(raw)

    st = {"max_nodes": 90000, "gci_tol_pct": 3.0, "levels": 4, "ratio": 1.4,
          "local_refine": False, "radius_refine": True}
    res = cv.run_converge(tmp_path / "m.mechdb", version=241, session=FakeSession(), settings=st, log=lambda *_: None)
    c = seen["cfg"]
    assert c["sizes_mm"] == [] and c["exclusion_mm"] is None          # şablon hesaplasın
    assert c["levels"] == 4 and c["ratio"] == 1.4 and c["max_nodes"] == 90000 and c["radius_refine"] is True
    assert c == template_cfg(st, analysis=None)                         # butonla aynı kural
    assert res["settings"]["gci_tol_pct"] == 3.0
    assert res["settings"]["sizes_mm"] == [4.345, 2.897, 1.931]       # raporda gerçekten kullanılan boyutlar


def _template_func(name):
    import ast
    from feacheck.mech_converge import TEMPLATE
    tree = ast.parse(TEMPLATE.replace("__CFG_LITERAL__", "{}"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    ns = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "<tpl>", "exec"), ns)
    return ns[name]


def test_radyus_ek_seviye_karari():
    f = _template_func("radius_needs_more")
    assert f([179.8, 180.9, 182.4], 5.0)        # küçük, son adım büyüyor → yön belirsiz, bir seviye daha
    assert f([180.0, 181.0, 180.5], 5.0)        # küçük salınım → bir seviye daha
    assert not f([170.0, 178.0, 181.0], 5.0)    # adım > eşik/2 → normal GCI kararına bırak
    assert not f([180.0, 181.0, 181.3], 5.0)    # küçük ve azalan → yeterli
    assert not f([180.0, 181.0], 5.0)


def test_radyus_dort_seviye_son_ucten_gci(tmp_path):
    """4 seviyeli yerel seride GCI son üç seviyeden; ek seviye raporda belirtilir."""
    import json as _json
    from pathlib import Path as _P
    raw = _json.loads((_P(__file__).parent / "fixtures" / "lbraket_r5_radyus_serisi.json").read_text(encoding="utf-8"))
    rs = raw["radius_series"]
    last = dict(rs["levels"][-1])
    v = [x["max_vm"] for x in rs["levels"] if "max_vm" in x]
    last.update({"element_size_mm": round(rs["sizes_mm"][-1] / 1.5, 4), "max_vm": v[-1] + 0.3 * (v[-1] - v[-2])})
    rs["levels"].append(last)
    rs["sizes_mm"] = rs["sizes_mm"] + [last["element_size_mm"]]
    rs["extra_level"] = "test"
    r = evaluate(raw, {"exclusion_mm": 17.38, "gci_tol_pct": 5})
    q = r["quantities"]["radius_peak"]
    assert len(q["values"]) == 4 and q["verdict"].startswith("güvenilir")
    assert r["radius_series"]["extra_level"]
    out = write(r, tmp_path / "r.html").read_text(encoding="utf-8")
    assert "bir seviye daha çözüldü" in out


def test_global_ek_seviye_karari():
    f = _template_func("global_needs_more")
    ns = f.__globals__
    ns["radius_needs_more"] = _template_func("radius_needs_more")
    def lv(n, vm, out):
        return {"nodes": n, "max_vm": vm, "max_def": 1.0, "max_outside_zone": {"value": out}}
    belirsiz = [lv(4000, 130.0, 130.0), lv(11000, 131.0, 131.0), lv(30000, 132.5, 132.5)]
    assert f(belirsiz, 5.0, 128000)
    assert not f(belirsiz, 5.0, 60000)              # bir sonraki seviye (~82k düğüm) limite sığmaz
    tekil = [lv(4000, 137.2, 133.0), lv(11000, 159.0, 133.6), lv(30000, 195.6, 133.7)]
    assert not f(tekil, 5.0, 128000)                # tekil tepe kuralı tetiklemez, aday azalarak yakınsıyor
    assert not f(belirsiz[:2], 5.0, 128000)


def test_global_dort_seviye_degerlendirme(tmp_path):
    import json as _json
    from pathlib import Path as _P
    raw = _json.loads((_P(__file__).parent / "fixtures" / "plaka_basinc.json").read_text(encoding="utf-8"))
    solved = [x for x in raw["levels"] if "max_vm" in x]
    last = _json.loads(_json.dumps(solved[-1]))
    last["element_size_mm"] = round(last["element_size_mm"] / 1.5, 3)
    last["nodes"] = int(last["nodes"] * 2.8)
    raw["levels"].append(last)
    raw["extra_level"] = "test"
    r = evaluate(raw, {"exclusion_mm": 5.0, "gci_tol_pct": 5})
    assert r["extra_level"] and len(r["quantities"]["max_von_mises"]["values"]) == 4
    assert "bir global seviye daha çözüldü" in write(r, tmp_path / "r.html").read_text(encoding="utf-8")


def test_gci_celik_2008_cozulmus_ornek():
    """Celik vd. (2008) J. Fluids Eng. 130, 078001, Tablo 1, durum 1 (yeniden bağlanma uzunluğu):
    N = 18000/8000/4500 hücre, r21 = 1,5, r32 = 1,333, φ = 6,063 / 5,972 / 5,863.
    Makalenin sonuçları: p = 1,53, φ_ext = 6,1685, e_a = %1,5, e_ext = %1,7, GCI_ince = %2,2."""
    from feacheck.gci import gci3
    g = gci3([6.063, 5.972, 5.863], [1.0, 1.5, 1.5 * 1.333])
    assert g["status"] == "converging" and not g.get("non_asymptotic")
    assert abs(g["p"] - 1.53) < 0.01
    assert abs(g["extrapolated"] - 6.1685) < 0.001
    assert round(g["rel_change_pct"], 1) == 1.5
    assert round(g["ext_rel_error_pct"], 1) == 1.7
    assert round(g["gci_fine_pct"], 1) == 2.2


def test_metinlerde_turkce_sayi():
    from feacheck.report_viz import tr_text
    assert tr_text("boyut [1.25, 0.8333] mm") == "boyut (1,25; 0,833) mm"
    assert tr_text("konum (61.08, 1.875, 10) mm") == "konum (61,08; 1,875; 10) mm"     # ayırıcı ';', karışmaz
    assert tr_text("GCI %3.351, 178.4 → 179.5") == "GCI %3,351, 178,4 → 179,5"
    assert tr_text("elhesap.yaml › L_braket_R5, Roache 1998") == "elhesap.yaml › L_braket_R5, Roache 1998"


def test_oz_test_scripti_uretilir(tmp_path):
    """Öz test scripti ASCII, Python olarak ayrıştırılabilir, tüm vakaları ve geri almayı içerir."""
    import ast
    from feacheck.app import build_selftest
    full = build_selftest(home=tmp_path, pyexe="python")
    src = full.read_text(encoding="ascii")
    ast.parse(src)
    for case in ("kat_lineer", "kat_yuk_x5", "kat_ikinci_fixed", "kat_egri_yuze_fixed", "kat_mesnetsiz"):
        assert f"def {case}()" in src and f'"{case[4:]}"' in src
    assert "finally:" in src and "_undo()" in src          # her vakada model geri alınır
    assert src.count('R["ok"] = bool(main())') == 1          # şablonun tek seferlik çağrısı döngüyle değişti


def test_oz_test_degerlendirme(tmp_path):
    """SENTETİK katalog klasörü: gerçek L-braket koşusundan türetilen 6 vaka, beklenen davranışlar."""
    import copy
    import json as _json
    from pathlib import Path as _P
    from feacheck.selftest import run_catalog
    fx = _P(__file__).parent / "fixtures"
    base = _json.loads((fx / "lbraket_keskin_yuzbilgili.json").read_text(encoding="utf-8"))
    base["ok"] = True
    base["yield_lib_mpa"] = 250.0

    def put(cid, raw, change):
        raw = copy.deepcopy(raw)
        raw["catalog_case"] = {"id": cid, "change": change}
        (tmp_path / f"raw_{cid}.json").write_text(_json.dumps(raw), encoding="utf-8")

    put("temel", base, "yok")
    lin = copy.deepcopy(base); lin["element_order"] = "Linear"; put("lineer", lin, "Linear")
    x5 = copy.deepcopy(base)
    for lv in x5["levels"]:
        for k in ("max_vm",):
            if k in lv:
                lv[k] *= 5
        for k in ("max_outside_zone", "probe", "max_away_from_peak"):
            if (lv.get(k) or {}).get("value") is not None:
                lv[k]["value"] *= 5
    put("yuk_x5", x5, "x5")
    put("ikinci_fixed", base, "ikinci Fixed")
    cyl = copy.deepcopy(base)
    cyl["tree"].append({"type": "FixedSupport", "name": "FEACHECK_KATALOG_EgriFixed", "state": "Solved",
                        "suppressed": False, "faces": [{"id": 9, "c": [15, 15, 15], "area_mm2": 236.0,
                                                        "surface": "GeoSurfaceCylinder", "edge_radii_mm": [5.0]}]})
    put("egri_yuze_fixed", cyl, "eğri yüze Fixed")
    put("mesnetsiz", {"ok": False, "errors": ["'Static Structural' analizinde mesnet yok (Fixed Support vb.); model serbest."],
                      "warnings": [], "levels": []}, "mesnetler bastırıldı")
    out = run_catalog(tmp_path, open_browser=False)
    page = out.read_text(encoding="utf-8")
    assert "5 geçti, 0 kaldı" in page, page[page.find("<h1>"):page.find("</h1>")]
    assert "ölçüm" in page and (tmp_path / "rapor_lineer.html").exists()


def test_oz_test_vakalar_ayari_paylasmaz(tmp_path):
    """Temel vaka CFG['sizes_mm'] listesine ekleme yapsa bile sonraki vakaların ayarı değişmemeli."""
    from feacheck.app import build_selftest
    src = build_selftest(home=tmp_path, pyexe="python").read_text(encoding="ascii")
    i = src.index("def _kat_clone(o):")
    ns = {}
    exec(src[i:src.index("\n\n\n", i)], ns)
    cfg0 = {"sizes_mm": [4.0, 2.7], "x": {"y": [1]}}
    snap = ns["_kat_clone"](cfg0)
    cfg0["sizes_mm"].append(1.8); cfg0["x"]["y"].append(2)
    assert snap == {"sizes_mm": [4.0, 2.7], "x": {"y": [1]}}
