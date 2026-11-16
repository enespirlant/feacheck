"""El hesabı modülü: kapalı form çözümler ve doğrulanmış FEA vakalarıyla tutarlılık."""
import math

import pytest

from feacheck import handcalc as h


def test_kiris_ve_sehim_aks_vakasi():
    # Konsol aks Ø20, F = 500 N; probe kesitinde kol 178 mm → README'deki 113,3 MPa
    assert abs(h.bending_round(500 * 178, 20)["value"] - 113.3) < 0.1
    # Uç sehimi FL³/3EI, E = 200 GPa → 0,849 mm (FEA 0,8506)
    assert abs(h.cantilever_tip_deflection(500, 200, 200_000, h.I_round(20))["value"] - 0.849) < 0.001


def test_delikli_plaka_peterson():
    k = h.kt_plate_central_hole_tension(10, 50)
    assert abs(k["value"] - 2.51) < 0.01
    assert abs(k["value"] * 10_000 / ((50 - 10) * 5) - 125.3) < 0.2       # FEA 128,5 (%2,6)
    with pytest.raises(ValueError):
        h.kt_plate_central_hole_tension(40, 50)                              # d/W = 0,8 aralık dışı


def test_winkler_lbraket_ust_sinir():
    # L-braket R5: M = 65 N·m, ri = 5, ro = 15, b = 30 → iç lif 198 MPa (el hesabı üst sınırı)
    assert abs(h.winkler_rect_inner(65_000, 5, 15, 30)["value"] - 198.0) < 0.2
    # Düz kiriş limiti: ri → ∞ iken Winkler 6M/(bh²)'ye yaklaşır
    w = h.winkler_rect_inner(65_000, 5000, 5010, 30)["value"]
    assert abs(w - h.bending_rect(65_000, 30, 10)["value"]) / w < 0.002


def test_mil_omuz_radyusu_kt():
    # Ders kitabı grafikleriyle (Peterson/Shigley A-15-8, A-15-9) ±%7 içinde
    for D, d, r, load, chart in [(15, 10, 1.0, "bending", 1.68), (15, 10, 2.0, "bending", 1.42),
                                 (20, 10, 1.5, "bending", 1.60), (15, 10, 1.0, "torsion", 1.40),
                                 (15, 10, 2.0, "torsion", 1.22)]:
        kt = h.kt_shaft_shoulder(D, d, r, load)["value"]
        assert abs(kt - chart) / chart < 0.07, (D, d, r, load, kt)
    # Radyus büyüdükçe Kt azalır, her zaman ≥ 1
    ks = [h.kt_shaft_shoulder(15, 10, r)["value"] for r in (0.5, 1, 2, 3)]
    assert ks == sorted(ks, reverse=True) and min(ks) > 1
    with pytest.raises(ValueError):
        h.kt_shaft_shoulder(15, 10, 0.1)                                      # h/r = 25 > 20


def test_karsilastirma():
    c = h.compare(186.2, low=168, high=201)
    assert c["ok"] and 0.5 < c["pos"] < 0.6
    assert not h.compare(210, low=168, high=201)["ok"]
    c = h.compare(128.5, value=125.3)
    assert c["ok"] and abs(c["diff_pct"] - 2.55) < 0.05
    assert not h.compare(150, value=125.3)["ok"]
    assert math.isclose(h.von_mises(100, 0)["value"], 100)


def test_elhesap_yaml_eslesme_ve_karsilastirma(tmp_path):
    import json
    from pathlib import Path
    from feacheck.app import finalize, load_handcalc
    from feacheck.store import Store
    assert load_handcalc("herhangi", tmp_path) is None and (tmp_path / "elhesap.yaml").exists()  # yardım dosyası
    (tmp_path / "elhesap.yaml").write_text(
        "l_braket_r5:\n  alt: 168\n  ust: 201\n  aciklama: omuz Kt / Winkler\n"
        "aks:\n  deger: 100\n", encoding="utf-8")
    fx = Path(__file__).parent / "fixtures"
    raw = json.loads((fx / "lbraket_r5_radyus_4seviye.json").read_text(encoding="utf-8"))
    _, _, res = finalize(raw, model_name="L_braket_R5-FreeParts", store=Store(tmp_path), open_browser=False)
    hc = res["hand_calc"]
    assert hc["ok"] and hc["kind"] == "range" and hc["fea_kind"] == "gösterge değer"
    raw = json.loads((fx / "aks.json").read_text(encoding="utf-8"))
    _, html, res = finalize(raw, model_name="Konsol aks", store=Store(tmp_path), open_browser=False)
    assert not res["hand_calc"]["ok"]                                    # 113,8 vs 100: %13,8 > %10
    assert any(f.startswith("El hesabıyla uyuşmuyor") for f in res["findings"])


def test_rover_teker_yukleri_elle():
    # 50 kg, 4 teker, Ø200, 2 N·m × 10 × 0,9: motor 180 N verir, zemin 0,8·122,6 = 98,1 N → zemin sınırlar
    from feacheck import handcalc as h
    r = h.rover_wheel_loads(50, 4, 200, 2, gear_ratio=10, eta=0.9)
    v = r["value"]
    assert v["Fz_statik"] == pytest.approx(122.625)
    assert v["Fz_tasarim"] == pytest.approx(306.5625)
    assert v["Fx_cekis"] == pytest.approx(98.1) and r["cekis_siniri"] == "zemin"
    assert v["Fy_yanal"] == pytest.approx(61.3125)
    assert v["M_aks_Nmm"] == pytest.approx(9810)
    assert h.rover_wheel_loads(50, 4, 200, 0.5)["cekis_siniri"] == "motor"  # 0,5 N·m → 10 N < 98 N
    with pytest.raises(ValueError):
        h.rover_wheel_loads(0, 4, 200, 2)
