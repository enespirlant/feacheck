"""Gerçek Ansys koşularından (2024 R1) alınan ham veriye karşı regresyon testleri.

Her vaka için analitik referans ve aracın vermesi gereken karar sabitlenir.
analysis.py / gci.py değiştiğinde Ansys açmadan bu vakalar yeniden kontrol edilir.
"""
import json
from pathlib import Path

import pytest

from feacheck.analysis import evaluate

FIX = Path(__file__).parent / "fixtures"


def _run(name, yield_mpa=250):
    raw = json.loads((FIX / name).read_text(encoding="utf-8"))
    return evaluate(raw, {"exclusion_mm": raw["settings_used"]["exclusion_mm"], "gci_tol_pct": 5,
                          "yield_mpa": yield_mpa})


def _close(a, b, pct):
    return abs(a - b) / abs(b) * 100 <= pct


def test_aks_mesnet_tekilligi():
    """Ankastre aks, uçta 500 N. Kiriş teorisi: 113,3 MPa."""
    r = _run("aks.json")
    assert r["singularity"]["kind"] == "sınır şartı"
    ds = r["design_stress"]
    assert ds["source"] == "von_mises_probe"
    assert _close(ds["fine_mesh_mpa"], 113.3, 1.0)
    assert ds["value_mpa"] >= ds["fine_mesh_mpa"]          # ihtiyatlı değer
    assert ds["confidence"] == "düşük"                      # salınımlı seri
    assert r["decision_trace"][0]["accepted"] is False       # global maks. elendi


def test_lbraket_ust_sabit():
    """Üst sabit, uçta -X 1000 N. El hesabı z=51,5'te 92,9 MPa."""
    r = _run("lbraket_ust_sabit.json")
    assert r["singularity"]["kind"] == "sınır şartı"
    ds = r["design_stress"]
    assert ds["source"] == "von_mises_probe"
    assert _close(ds["fine_mesh_mpa"], 92.9, 3.0)
    assert ds["value_mpa"] >= ds["extrapolated_mpa"]         # azalan seri: ekstrapolasyon kullanılmaz


def test_lbraket_keskin_kose():
    """Keskin iç köşe: geometrik tekillik, probe tekil alanda olduğu için reddedilmeli."""
    r = _run("lbraket_keskin.json")
    s = r["singularity"]
    assert s["kind"] == "geometrik"
    assert 0.35 < s["growth_exponent"] < 0.65                # Williams 90°: 0,455
    probe = next(t for t in r["decision_trace"] if t["source"] == "von_mises_probe")
    assert not probe["accepted"] and "tekil" in probe["reason"]
    # Bu (eski) koşuda tepe dışı okuma mesnet kenarına düşmüştü: reddedilmeli, gösterge de verilmemeli
    assert "design_stress" not in r
    aw = next(t for t in r["decision_trace"] if t["source"] == "von_mises_away_from_peak")
    assert not aw["accepted"] and "mesnet" in aw["reason"]
    assert "indicative_stress" not in r


@pytest.mark.parametrize("name,ref", [("plaka_basinc.json", 125.3)])
def test_delikli_plaka(name, ref):
    """Delikli plaka, Peterson net kesit Kt: 125,3 MPa."""
    r = _run(name)
    assert not r["singularity"]["detected"]
    ds = r["design_stress"]
    assert _close(ds["fine_mesh_mpa"], ref, 3.0)
    assert ds["value_mpa"] >= ds["fine_mesh_mpa"]


def test_delikli_plaka_kuvvet_dogrusal():
    """Aynı plaka, farklı yükleme: tekillik yok, karar global maksimumdan."""
    r = _run("plaka_kuvvet.json")
    assert not r["singularity"]["detected"]
    assert r["design_stress"]["source"] == "max_von_mises"


def test_lbraket_r5_cozulmemis_radyus():
    """R5 radyuslu köşe, doğru sınır şartları. Gerilme 163 → 174 → 183 artıyor ama yavaşlıyor:
    tekillik DEĞİL, çözünürlük yetersiz. Tasarım değeri verilmemeli (başka noktalar ihtiyatsız olur)."""
    r = _run("lbraket_r5.json")
    s = r["singularity"]
    assert s["kind"] == "çözülmemiş radyus" and not s["detected"]
    assert r["vm_growth_steps"][-1] < r["vm_growth_steps"][0]
    assert "design_stress" not in r
    assert r["indicative_stress"]["value_mpa"] > 180
    assert all(not t["accepted"] for t in r["decision_trace"])


def test_lbraket_r5_ust_sabit_tutarli():
    """R5 parça, üst sabit / kuvvet uçta: köşeden uzak noktada keskin köşeli parçayla aynı sonuç (~%1)."""
    a = _run("lbraket_r5_ust_sabit.json")["design_stress"]["fine_mesh_mpa"]
    b = _run("lbraket_ust_sabit.json")["design_stress"]["fine_mesh_mpa"]
    assert _close(a, b, 2.0) and _close(a, 92.9, 4.0)


# ---- Yüz bilgisi okunan (Faz 1a) koşular. Not: cihazdaki `lbraket_r5_v2.json` aslında keskin köşe,
# `lbraket_keskin_v2.json` aslında R5 koşusudur; doğru adlı kopyaları aşağıda kullanılıyor.

def test_lbraket_keskin_yuz_bilgili():
    """Keskin köşe, maksimum düzlemsel yüzlerde: geometrik tekillik. Köşe hariç gerilme el hesabına
    (yatay kolda M = 65 N·m, W = 500 mm³ → 130 + 3,3 = 133,3 MPa) yakın olmalı."""
    r = _run("lbraket_keskin_yuzbilgili.json")
    assert r["singularity"]["kind"] == "geometrik"
    ds = r["design_stress"]
    assert ds["source"] == "von_mises_away_from_peak"
    assert _close(ds["value_mpa"], 133.3, 1.0)
    assert ds["value_mpa"] >= ds["fine_mesh_mpa"]


def test_lbraket_r5_yuz_bilgili():
    """R5 köşe, maksimum silindirik yüzde (R = 5 mm Ansys'ten okunuyor): tekillik değil, çözünürlük yetersiz."""
    r = _run("lbraket_r5_yuzbilgili.json")
    s = r["singularity"]
    assert s["kind"] == "çözülmemiş radyus" and not s["detected"]
    assert s["radius_mm"] == 5.0
    assert "design_stress" not in r
    assert r["indicative_stress"]["value_mpa"] > 180


# ---- Radyus yerel sıklaştırma serisi. Bu üç fixture SENTETİK: gerçek R5 koşusuna elle eklenmiş
# radius_series verisi. Yalnızca karar mantığını sınar; gerçek değer Ansys koşusundan gelecek.

def test_radyus_serisi_yakinsar():
    r = _run("sentetik_r5_radyus_serisi_yakinsar.json")
    assert r["singularity"].get("resolved_radius") and not r["singularity"]["detected"]
    ds = r["design_stress"]
    assert ds["source"] == "radius_peak"
    assert ds["value_mpa"] >= ds["fine_mesh_mpa"] == 192.4
    assert ds["confidence"] in ("orta", "düşük")
    assert r["decision_trace"][-1]["accepted"]


def test_radyus_serisi_yakinsamaz():
    r = _run("sentetik_r5_radyus_serisi_yakinsamaz.json")
    assert r["singularity"]["kind"] == "çözülmemiş radyus"
    assert "design_stress" not in r
    assert r["indicative_stress"]["source"] == "radius_peak"
    assert r["indicative_stress"]["value_mpa"] == 206.0


def test_radyus_serisi_tepe_kayarsa_kabul_edilmez():
    r = _run("sentetik_r5_radyus_serisi_kayar.json")
    assert "design_stress" not in r
    assert any("kaydı" in t["reason"] for t in r["decision_trace"])


def test_lbraket_r5_radyus_serisi_gercek():
    """GERÇEK koşular (15.11.2026). Yerel radyus serisi 178,4 → 179,5 → 181,9 MPa, ardından 4. seviye 186,2.
    Adımlar küçük (%0,6 → %1,3 → %2,4) ama aynı yönde ve büyüyor: bu gürültü değil, seri yakınsama bölgesinde
    değil. Önceki sürüm bunu 'güvenilir (küçük değişim)' sayıyordu: YANLIŞTI. Doğru sonuç: tasarım değeri yok,
    son değer gösterge/alt sınır, bulguda denenen yerel boyutlar ve büyüyen adımlar yazılı."""
    for fx, last in (("lbraket_r5_radyus_serisi.json", 181.9), ("lbraket_r5_radyus_4seviye.json", 186.2)):
        r = _run(fx)
        assert not r.get("design_stress") and not r["singularity"].get("resolved_radius")
        ind = r["indicative_stress"]
        assert ind["source"] == "radius_peak" and _close(ind["value_mpa"], last, 0.5)
        msg = [f for f in r["findings"] if f.startswith("ÇÖZÜNÜRLÜK YETERSİZ")]
        assert len(msg) == 1 and "giderek büyüyor" in msg[0] and "yerel eleman boyuyla inceltildi" in msg[0]
        assert r["quantities"]["radius_peak"]["gci"]["accelerating"]
    r = _run("lbraket_r5_radyus_4seviye.json")
    assert len(r["radius_series"]["levels"]) == 4 and r["radius_series"]["extra_level"]


def test_kucuk_degisim_kurali_tekilligi_gizlemez():
    """Keskin köşedeki gibi adım başı > %4 artış 'küçük değişim' sayılmamalı; küçük ama hızlanan artış da."""
    from feacheck.analysis import _quantity
    q = _quantity("v", "MPa", [{"v": 137.2}, {"v": 159.0}, {"v": 195.6}], 5.0, [4.3, 2.9, 1.9])
    assert not q["verdict"].startswith("güvenilir")
    q = _quantity("v", "MPa", [{"v": 178.4}, {"v": 179.5}, {"v": 181.9}], 5.0, [1.25, 0.83, 0.56])
    assert not q["verdict"].startswith("güvenilir") and q["gci"]["accelerating"]
    q = _quantity("v", "MPa", [{"v": 180.0}, {"v": 181.5}, {"v": 181.0}], 5.0, [1.25, 0.83, 0.56])   # salınım
    assert q["verdict"].startswith("güvenilir")


def test_lineer_eleman_ve_kalinlik_uyarisi():
    import copy
    raw = json.loads((FIX / "lbraket_keskin_yuzbilgili.json").read_text(encoding="utf-8"))
    r = evaluate(raw, {"exclusion_mm": 17.38, "gci_tol_pct": 5})
    assert not any("LINEAR" in f or "kalınlık boyunca" in f for f in r["findings"])   # quadratic varsayılır, t/h ≈ 3,7
    assert r["elements_through_thickness"] > 2
    bad = copy.deepcopy(raw)
    bad["element_order"] = "Linear"
    bad["t_eff_mm"] = 3.0
    r = evaluate(bad, {"exclusion_mm": 17.38, "gci_tol_pct": 5})
    assert any("LINEAR" in f for f in r["findings"])
    assert any("kalınlık boyunca" in f for f in r["findings"])


def test_lbraket_r5_el_hesabi_sinirlari():
    """L köşesi için birebir abak yok; gerçek değer iki el hesabıyla sınırlanır (M = 65 N·m, t = 10, b = 30, r = 5):
    alt sınır  — kademeli düz çubuk omuz radyusu, eğilme (Peterson/Pilkey eğri uydurması, h/r = 12):
                 Kt ≈ 1,27 → 1,27 × 130 + 3,3 ≈ 168 MPa
    üst sınır  — Winkler eğri kiriş iç lifi (ri = 5, ro = 15): 198 + 3,3 ≈ 201 MPa
    Radyus henüz yakınsamadı; gösterge değerler yine de bu aralıkta ve artarak üst sınıra yaklaşıyor."""
    v = _run("lbraket_r5_radyus_4seviye.json")["quantities"]["radius_peak"]["values"]
    assert all(168 < x < 201 for x in v) and v == sorted(v)


def test_mesnet_basina_tepki_ve_ic_kuvvet_orani():
    import copy
    raw = json.loads((FIX / "lbraket_keskin_yuzbilgili.json").read_text(encoding="utf-8"))
    ok = copy.deepcopy(raw)
    ok["levels"][-1]["reactions_by_support"] = [{"name": "Fixed Support", "r_n": [1000.0, 0.0, 0.0]}]
    r = evaluate(ok, {"exclusion_mm": 17.38, "gci_tol_pct": 5})
    assert r["support_reactions"]["internal_force_ratio"] == 1.0
    assert not any("aşırı kısıtlanmış" in f for f in r["findings"])
    bad = copy.deepcopy(raw)   # iki uçtan Fixed: mesnetler 5000 N ile birbirini çekiyor, net 1000 N
    bad["levels"][-1]["reactions_by_support"] = [{"name": "A", "r_n": [500.0, 0.0, 5000.0]},
                                                 {"name": "B", "r_n": [500.0, 0.0, -5000.0]}]
    r = evaluate(bad, {"exclusion_mm": 17.38, "gci_tol_pct": 5})
    assert r["support_reactions"]["internal_force_ratio"] > 3
    assert any("aşırı kısıtlanmış" in f for f in r["findings"])


def test_silindirik_yuze_fixed_support_uyarisi():
    import copy
    raw = json.loads((FIX / "lbraket_keskin_yuzbilgili.json").read_text(encoding="utf-8"))
    # L-braketin mesnedi düz yüz: uyarı çıkmamalı (eski JSON'larda "surface" alanı yok)
    r = evaluate(copy.deepcopy(raw), {"exclusion_mm": 17.38, "gci_tol_pct": 5})
    assert not any("silindirik/eğri yüze" in f for f in r["findings"])
    bad = copy.deepcopy(raw)   # cıvata deliğine Fixed verilmiş gibi
    bad["tree"].append({"type": "FixedSupport", "name": "Delik Fixed", "state": "Solved", "suppressed": False,
                        "faces": [{"id": 77, "c": [0, 0, 0], "area_mm2": 157.1,
                                   "surface": "GeoSurfaceCylinder", "edge_radii_mm": [5.0]}]})
    r = evaluate(bad, {"exclusion_mm": 17.38, "gci_tol_pct": 5})
    msg = [f for f in r["findings"] if "silindirik/eğri yüze" in f]
    assert msg and "Delik Fixed" in msg[0] and "5 mm" in msg[0] and "Cylindrical Support" in msg[0]
    sup = copy.deepcopy(bad); sup["tree"][-1]["suppressed"] = True   # bastırılmışsa sayılmaz
    assert not any("silindirik/eğri yüze" in f for f in evaluate(sup, {"exclusion_mm": 17.38, "gci_tol_pct": 5})["findings"])


def test_radyus_cozulunce_celiskili_bulgu_yok():
    """Radyus çözülünce 'çözünürlük yetersiz' bulgusu kalmamalı (sentetik yakınsayan seri);
    çözülmezse tek bir, yerel seriyi anlatan bulgu olmalı."""
    r = _run("sentetik_r5_radyus_serisi_yakinsar.json")
    assert r["singularity"].get("resolved_radius")
    assert not any(f.startswith("ÇÖZÜNÜRLÜK YETERSİZ") for f in r["findings"])
    assert any(f.startswith("ÇÖZÜNÜRLÜK YETERSİZ") for f in _run("lbraket_r5.json")["findings"])
    assert sum(f.startswith("ÇÖZÜNÜRLÜK YETERSİZ") for f in _run("lbraket_r5_radyus_4seviye.json")["findings"]) == 1


def test_katalog_11_12_akma_asimi_ve_buyuk_deformasyon():
    """Katalog 11: aynı aks, akma 100 MPa → tasarım gerilmesi (~114) akmayı aşar.
    Katalog 12: deformasyon parça boyutunun %5'ini aşınca Large Deflection uyarısı."""
    import copy
    raw = json.loads((FIX / "aks.json").read_text(encoding="utf-8"))
    r = evaluate(copy.deepcopy(raw), {"exclusion_mm": 20.0, "gci_tol_pct": 5, "yield_mpa": 100})
    assert r["design_stress"]["safety_factor"] < 1
    assert any("akmayı aşıyor" in f for f in r["findings"])
    r = evaluate(copy.deepcopy(raw), {"exclusion_mm": 20.0, "gci_tol_pct": 5, "yield_mpa": 250})
    assert not any("akmayı aşıyor" in f for f in r["findings"])
    big = copy.deepcopy(raw)
    for lv in big["levels"]:
        if "max_def" in lv:
            lv["max_def"] *= 20          # ~17 mm sehim, model boyu ~50 mm (V^1/3)
    r = evaluate(big, {"exclusion_mm": 20.0, "gci_tol_pct": 5, "model_size_mm": 50.0})
    assert any("Large Deflection" in f for f in r["findings"])


def test_buyume_orani_etkisiz_kalinca_durust_rapor(tmp_path):
    """GERÇEK koşu (15.11 22:34): büyüme oranı 1,2 hatasız atandı ama adaptive sizing açık olduğu için mesh hiç
    değişmedi (düğüm sayıları önceki koşuyla birebir aynı). Rapor 'uygulandı' dememeli."""
    from feacheck.report import write
    a = json.loads((FIX / "lbraket_r5_radyus_4seviye.json").read_text(encoding="utf-8"))
    b = json.loads((FIX / "lbraket_r5_buyume_etkisiz.json").read_text(encoding="utf-8"))
    assert [x["nodes"] for x in a["radius_series"]["levels"]] == [x["nodes"] for x in b["radius_series"]["levels"]]
    r = _run("lbraket_r5_buyume_etkisiz.json")
    msg = next(f for f in r["findings"] if f.startswith("ÇÖZÜNÜRLÜK YETERSİZ"))
    assert "etkin değildi" in msg
    assert "adaptive sizing açık" in write(r, tmp_path / "r.html").read_text(encoding="utf-8")
    b["radius_series"].update({"adaptive_sizing": "False", "growth_rate": 1.2})   # gerçekten uygulanmış olsaydı
    r = evaluate(b, {"exclusion_mm": 17.3, "gci_tol_pct": 5})
    assert "sphere of influence" in next(f for f in r["findings"] if f.startswith("ÇÖZÜNÜRLÜK YETERSİZ"))


def test_lbraket_r5_buyume_orani_ile_yakinsar():
    """GERÇEK koşu (15.11 23:04): adaptive sizing kapalı, büyüme oranı 1,2 → mesh gerçekten değişti
    (radyus serisi düğümleri 30.297 / 34.878 / 43.988 / 52.355; önceki koşularda 33.486 / ... / 83.204).
    Radyus tepesi 181,9 → 179,8 → 182,0 → 183,6: son üç seviye yakınsıyor ama p = 0,70 (kuadratik elemanda
    beklenen ≈ 2): Fs = 3, GCI %8, güven düşük, ihtiyatlı değer GCI bandının üstü 183,6 × 1,08 = 198,3 MPa.
    El hesabı aralığı 168–201 MPa içinde; Kt (köşe hariç 133,7'ye göre) ≈ 1,37."""
    raw = json.loads((FIX / "lbraket_r5_buyume_12.json").read_text(encoding="utf-8"))
    assert raw["radius_series"]["adaptive_sizing"] == "False" and raw["radius_series"]["growth_rate"] == 1.2
    r = _run("lbraket_r5_buyume_12.json")
    assert r["singularity"]["resolved_radius"]
    ds = r["design_stress"]
    assert ds["source"] == "radius_peak" and ds["confidence"] == "düşük"
    assert ds["verdict"] == "güvenilir (geniş belirsizlik)"
    g = r["quantities"]["radius_peak"]["gci"]
    assert g["low_order"] and g["fs"] == 3.0 and abs(g["p"] - 0.695) < 0.01
    assert r["quantities"]["radius_peak"].get("early_reversal")
    assert _close(ds["fine_mesh_mpa"], 183.6, 0.3) and _close(ds["value_mpa"], 198.3, 0.5)
    assert 168 < ds["fine_mesh_mpa"] < ds["value_mpa"] < 201
    aw = r["quantities"]["von_mises_away_from_peak"]["values"][-1]
    assert 1.3 < ds["fine_mesh_mpa"] / aw < 1.45


def test_r5_tekrarlanabilir():
    """Aynı R5 modeli iki ayrı günde (15.11 23:04 ve 16.11 19:33) koşuldu: global seri, radyus serisi, düğüm
    sayıları ve gerilmeler son haneye kadar aynı. feacheck'in mesh/çözüm adımları deterministik."""
    a = json.loads((FIX / "lbraket_r5_buyume_12.json").read_text(encoding="utf-8"))
    b = json.loads((FIX / "lbraket_r5_tekrar_1611.json").read_text(encoding="utf-8"))
    key = lambda r: ([(x["nodes"], round(x["max_vm"], 6)) for x in r["levels"] if "max_vm" in x],
                     [(x["nodes"], round(x["max_vm"], 6)) for x in r["radius_series"]["levels"]])
    assert key(a) == key(b)
    ra, rb = _run("lbraket_r5_buyume_12.json"), _run("lbraket_r5_tekrar_1611.json")
    assert ra["design_stress"]["value_mpa"] == rb["design_stress"]["value_mpa"]


def test_montaj_baglantilari_sentetik(tmp_path):
    """SENTETİK: gerçek L-braket koşusuna elle 'connections' eklendi (şablon Ansys'te bu alanı henüz okumadı)."""
    import copy
    from feacheck.report import write
    base = json.loads((FIX / "lbraket_keskin_yuzbilgili.json").read_text(encoding="utf-8"))
    st = {"exclusion_mm": 17.38, "gci_tol_pct": 5}
    peak = [x for x in base["levels"] if "max_vm" in x][-1]["max_location"]["xyz_mm"]
    bag = lambda r: [f for f in r["findings"] if f.startswith("Bağlantı:")]

    assert not bag(evaluate(copy.deepcopy(base), st))                       # eski JSON: alan yok, bulgu yok

    a = copy.deepcopy(base); a["connections"] = {"bodies": 2, "contacts": [], "joints": [], "beams": []}
    assert any("gövde var ama aralarında" in f for f in bag(evaluate(a, st)))

    b = copy.deepcopy(base)
    b["connections"] = {"bodies": 2, "joints": [], "beams": [], "contacts": [
        {"name": "Contact Region", "suppressed": False, "contact_type": "Bonded",
         "source": [{"c": [peak[0] + 3, peak[1], peak[2]], "area_mm2": 100.0}],
         "target": [{"c": [60, 15, 0], "area_mm2": 100.0}]},
        {"name": "Kapalı temas", "suppressed": True, "contact_type": "Frictional", "source": [], "target": []}]}
    r = evaluate(b, st)
    f = bag(r)
    assert any("1 bonded temas" in x for x in f)
    assert any("en yüksek gerilme 'Contact Region'" in x for x in f)
    assert not any("doğrusal olmayan" in x for x in f)                     # bastırılmış sürtünmeli sayılmaz
    assert r["connections"]["peak_near_contact"]["distance_mm"] == 3.0
    out = write(r, tmp_path / "r.html").read_text(encoding="utf-8")
    assert "Montaj bağlantıları" in out and "Bonded" in out

    c = copy.deepcopy(b); c["connections"]["contacts"][1]["suppressed"] = False
    c["connections"]["contacts"][0]["source"][0]["c"] = [200, 200, 200]   # tepe temastan uzak
    f = bag(evaluate(c, st))
    assert any("doğrusal olmayan temas var (Frictional: 1)" in x for x in f)
    assert not any("en yüksek gerilme" in x for x in f)


def test_r1_gercek_kosu_yakinsamaz_gosterge():
    """17.11 gerçek R1 koşusu: radyus 354,8 → 357,9 → 365,6 MPa (artış hızlanıyor), 4. seviye düğüm limitine takıldı.
    Araç güvenilir dememeli; gösterge ≈ 365,6 MPa (Winkler el hesabı ≈ 350 MPa, %4,5 içinde)."""
    import json as _j
    import tempfile as _t
    from pathlib import Path as _P

    from feacheck.app import finalize
    from feacheck.store import Store
    raw = _j.loads((_P(__file__).parent / "fixtures" / "lbraket_r1_radyus.json").read_text(encoding="utf-8"))
    _, _, r = finalize(raw, store=Store(_P(_t.mkdtemp())), open_browser=False, tol=5)
    assert not r.get("design_stress")
    ind = r["indicative_stress"]
    assert ind["value_mpa"] == pytest.approx(365.6, abs=0.1) and ind["verdict"] == "yakınsamıyor"
    assert raw["radius_series"]["levels"][-1]["skipped"].startswith("dugum limiti")


def test_oz_test_gercek_kosu_17_11(tmp_path):
    """GERÇEK öz test (Ansys, L-braket R5, 17.11): 6 vakanın 6'sı beklenen uyarıyı vermeli. İkinci Fixed yükün %99,9'unu
    alıyordu (tepkiler aynı yönde, iç kuvvet oranı 1) ve eski kontrol kaçırıyordu; 'mesnet neredeyse yüksüz' yakalar."""
    import re
    import shutil
    from pathlib import Path as _P

    from feacheck.selftest import run_catalog
    src = _P(__file__).parent / "fixtures" / "katalog_gercek_20261117"
    for f in src.glob("raw_*.json"):
        shutil.copy(f, tmp_path / f.name)
    html = run_catalog(tmp_path, open_browser=False).read_text(encoding="utf-8")
    assert re.search(r"6 geçti, 0 kaldı", html), re.findall(r"\d+ geçti, \d+ kaldı", html)
    assert "Mesnet neredeyse yüksüz" in html and "99,9" in html


def test_oz_test_gercek_r2_cozulemeyen_vakalar(tmp_path):
    """GERÇEK öz test, L-braket R2 (17.11): ikinci_fixed ve egri_yuze_fixed Ansys'te hiç çözülemedi (NotSolved).
    Bunlar feacheck'in tespitini sınamadığı için 'kaldı' değil 'çözülemedi' sayılmalı. Temel radyus serisi
    253,3 → 261,0 → 260,6 MPa (Winkler el hesabı 255,7)."""
    import json as _j
    import shutil
    from pathlib import Path as _P

    from feacheck.selftest import run_catalog
    src = _P(__file__).parent / "fixtures" / "katalog_gercek_r2_20261117"
    for f in src.glob("raw_*.json"):
        shutil.copy(f, tmp_path / f.name)
    html = run_catalog(tmp_path, open_browser=False).read_text(encoding="utf-8")
    assert "4 geçti, 0 kaldı, 2 çözülemedi" in html
    t = _j.loads((src / "raw_temel.json").read_text(encoding="utf-8"))
    assert [round(l["max_vm"], 1) for l in t["radius_series"]["levels"] if l.get("max_vm")] == [253.3, 261.0, 260.6]
