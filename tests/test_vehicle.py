"""Araç bilgisi (arac.yaml) + modeldeki kuvvetin teker yüküyle kıyası + buton scripti."""
import ast
import json
from pathlib import Path

import pytest

from feacheck import vehicle as V
from feacheck.app import build_button, finalize

FIX = Path(__file__).parent / "fixtures"
DOLU = "kutle: 50\nteker_sayisi: 4\nteker_capi: 200\nmotor_torku: 2\ndisli_orani: 10\nverim: 0.9\n"


def test_sablon_yazilir_ve_bos_none(tmp_path):
    assert V.load_vehicle(tmp_path) is None
    assert (tmp_path / "arac.yaml").read_text(encoding="utf-8").startswith("# feacheck arac")
    assert V.load_vehicle(tmp_path) is None  # "?" alanlar → kıyas yok


def test_dolu_arac_ve_kiyas(tmp_path):
    (tmp_path / "arac.yaml").write_text(DOLU, encoding="utf-8")
    v = V.load_vehicle(tmp_path)
    assert v["k_dyn"] == 2.5 and v["disli_orani"] == 10
    # düşey tasarım yükü 306,6 N
    assert V.check_load({"applied_force_n": [0, 0, -300]}, v, "duzey")["durum"] == "uygun"
    c = V.check_load({"applied_force_n": [-100, 0, 0]}, v, "duzey")
    assert not c["ok"] and c["durum"] == "düşük" and c["beklenen_n"] == pytest.approx(306.5625)
    assert V.check_load({"applied_force_n": [0, 0, 0], "applied_force_vector_mag_n": 1000}, v,
                        "cekis")["durum"] == "çok ihtiyatlı"  # 1000 / 98,1
    assert V.check_load({"applied_force_n": [0, 0, 0]}, v, "duzey") is None
    assert V.check_load({"applied_force_n": [1, 0, 0]}, v, "bilinmeyen") is None


def test_finalize_rapora_ekler(tmp_path):
    from feacheck.store import Store
    (tmp_path / "arac.yaml").write_text(DOLU, encoding="utf-8")
    raw = json.loads((FIX / "lbraket_r5_buyume_12.json").read_text(encoding="utf-8"))  # 1000 N
    _, html, res = finalize(raw, store=Store(tmp_path), open_browser=False, yuk_tipi="duzey", tol=5)
    assert res["vehicle_load"]["durum"] == "çok ihtiyatlı"
    assert "Araç yükü" in html.read_text(encoding="utf-8")
    _, _, res2 = finalize(raw, store=Store(tmp_path), open_browser=False, yuk_tipi=None, tol=5)
    assert "vehicle_load" not in res2


def test_finalize_bos_arac_uyarir(tmp_path):
    from feacheck.store import Store
    raw = json.loads((FIX / "lbraket_r5_buyume_12.json").read_text(encoding="utf-8"))
    _, _, res = finalize(raw, store=Store(tmp_path), open_browser=False, yuk_tipi="duzey", tol=5)
    assert "vehicle_load" not in res and any("arac.yaml" in w for w in res["warnings"])


def test_buton_ascii_ve_soru_var(tmp_path):
    p = build_button(home=tmp_path, pyexe="python")
    src = p.read_bytes().decode("ascii")  # Mechanical ASCII ister
    assert "--yuk-tipi" in src and '"\\\\arac.yaml"' in src
    ast.parse(src)  # sözdizimi (IronPython 2.7 ile ortak altküme)


def test_cekis_tasarim_ve_k_teker_yamldan(tmp_path):
    (tmp_path / "arac.yaml").write_text(DOLU + "k_teker: 1.2\ncekis_tasarim: 148\n", encoding="utf-8")
    v = V.load_vehicle(tmp_path)
    assert v["k_teker"] == 1.2 and v["cekis_tasarim"] == 148
    c = V.check_load({"applied_force_n": [150, 0, 0]}, v, "cekis")
    assert c["beklenen_n"] == 148 and c["durum"] == "uygun"
