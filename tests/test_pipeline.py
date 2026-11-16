"""Ansys olmadan çalışan testler: python -m pytest"""
import ast
import json
from pathlib import Path

import pytest

cq = pytest.importorskip("cadquery", reason="cadfea boru hattı testleri cadquery ister (pip install -e .[cad])")
import yaml

from cadfea import advisor, gdt, geometry, handcalc, tolerances
from cadfea.config import ConfigError, config_for_part, load_config, validate
from cadfea.runner import analyze, summarize
from cadfea.script_builder import build_script


@pytest.fixture
def cfg(tmp_path):
    c = load_config()
    c["paths"]["runs"] = str(tmp_path / "runs")
    return c


@pytest.fixture
def part(tmp_path):
    p = tmp_path / "aks.step"
    cq.exporters.export(cq.Workplane("XY").circle(10).extrude(200), str(p))
    return p


@pytest.fixture
def bracket(tmp_path):
    p = tmp_path / "bracket.step"
    w = (cq.Workplane("XY").box(100, 60, 10).faces(">Z").workplane()
         .rect(80, 40, forConstruction=True).vertices().hole(6.4)
         .faces(">Z").workplane().circle(8).extrude(15))
    cq.exporters.export(w, str(p))
    return p


def _cfg_blob(script):
    from cadfea.script_builder import read_cfg
    return read_cfg(script)


# ---------------------------------------------------------------- script

def test_script_compiles_and_is_ironpython_safe(cfg, part, tmp_path):
    s = build_script(cfg, part, tmp_path)
    ast.parse(s)
    import re
    assert not re.search(r"(?<![A-Za-z0-9_])[fF][\"']", s)  # f-string yok
    assert "import json" not in s  # IronPython'da _json yok
    s.encode("ascii")


def test_windows_path_roundtrip(cfg, tmp_path):
    s = build_script(cfg, Path("C:/Users/enes/inbox/aks.step"), tmp_path)
    assert _cfg_blob(s)["geometry_path"].endswith("aks.step")


def test_validation(cfg):
    cfg["loads"]["fixed"] = []
    with pytest.raises(ConfigError):
        validate(cfg)


def test_missing_load_value_blocks(cfg, part):
    with pytest.raises(ConfigError, match="yük değeri"):
        config_for_part(cfg, part, {"loads": {"fixed": [{"axis": "z", "side": "min"}],
                                              "forces": [{"scope": {"axis": "z", "side": "max"},
                                                          "components_n": None}]}})


def test_part_loads_replace_defaults(cfg, part):
    c = config_for_part(cfg, part, {"loads": {"fixed": [{"axis": "z", "side": "min"}],
                                              "pressures": [{"scope": {"axis": "z", "side": "max"}, "mpa": 1}]}})
    assert c["loads"]["forces"] == []


# ---------------------------------------------------------------- geometri

def test_bracket_features(bracket):
    p = geometry.inspect(bracket)
    holes = geometry.hole_groups(p)
    assert holes[0]["count"] == 4 and holes[0]["diameter_mm"] == pytest.approx(6.4)
    r = geometry.resolve_scope(p, {"holes": {"diameter_mm": 6.4}})
    assert len(r["face_ids"]) == 4 and r["geo"][0]["kind"] == "cylinder"
    assert geometry.datum_suggestion(p)["C"]["type"] == "hole"


def test_advisor_never_guesses_load(bracket):
    prop = advisor.propose(geometry.inspect(bracket))
    assert prop["setup"]["loads"]["fixed"][0] == {"holes": {"diameter_mm": 6.4}}
    assert prop["setup"]["loads"]["forces"][0]["components_n"] is None


def test_scaled_material_and_mass(cfg, part):
    raw = {"ok": True, "runs": [{"element_size_mm": 2, "max_von_mises": 127.0, "max_deformation": 0.85}]}
    c = config_for_part(cfg, part, {"material": {"db": "Al6061-T6"}})
    s = summarize(raw, c)
    assert c["material"]["mode"] == "scaled"
    assert s["max_deformation_mm"] == pytest.approx(0.85 * 200 / 68.9)
    assert s["safety_factor"] == pytest.approx(276 / 127, rel=1e-3)


# ---------------------------------------------------------------- uçtan uca

class FakeSession:
    def run(self, script, fresh=False):
        c = _cfg_blob(script)
        assert c["loads"]["fixed"][0]["geo"][0]["kind"] == "plane"
        raw = {"ok": True, "warnings": [], "errors": [], "scopes": [],
               "runs": [{"element_size_mm": 2.0, "nodes": 10000, "elements": 6000,
                         "max_von_mises": 130.0, "max_deformation": 0.86}]}
        Path(c["out_dir"], "result_raw.json").write_text(json.dumps(raw))
        return json.dumps(raw)


def test_end_to_end_with_fake_session(cfg, part):
    part.with_suffix(".yaml").write_text(yaml.safe_dump({
        "material": {"db": "Structural Steel"},
        "loads": {"fixed": [{"axis": "z", "side": "min"}],
                  "forces": [{"scope": {"axis": "z", "side": "max"}, "components_n": [0, -500, 0]}]}}))
    s = analyze(part, cfg, session=FakeSession())
    assert s["ok"] and s["mass_kg"] == pytest.approx(62831.85e-9 * 7850, rel=1e-4)
    for f in ("report.html", "result.json", "mechanical_script.py"):
        assert (Path(s["dir"]) / f).exists()


def test_script_only(cfg, part):
    over = {"loads": {"fixed": [{"axis": "z", "side": "min"}],
                      "forces": [{"scope": {"axis": "z", "side": "max"}, "components_n": [0, -500, 0]}]}}
    assert analyze(part, cfg, overrides=over, script_only=True)["status"] == "script_ready"


def test_wrong_axis_gives_clear_error(cfg, part):
    with pytest.raises(ConfigError, match="eşleşmedi"):
        analyze(part, cfg, script_only=True)  # varsayılan x ekseni silindirik aksta düz yüz bulamaz


# ---------------------------------------------------------------- mühendislik araçları

def test_iso286_known_fits():
    f = tolerances.fit(20, "H7", "g6")
    assert (f["clearance_min_um"], f["clearance_max_um"]) == (7, 41)
    f = tolerances.fit(20, "H7", "p6")
    assert f["type"] == "sıkı" and f["clearance_max_um"] == -1


def test_stackup_worst_case():
    r = tolerances.stackup([{"name": "A", "nominal": 50, "tol": 0.1, "dir": 1},
                            {"name": "B", "nominal": 49.5, "tol": 0.1, "dir": -1}], {"min": 0.2, "max": 0.8})
    assert r["worst_case"] == [pytest.approx(0.3), pytest.approx(0.7)] and r["worst_case_ok"]


def test_handcalc_matches_aks():
    r = handcalc.beam("cantilever", 500, 200, 200, "round", d=20)
    assert r["sigma_max_mpa"] == pytest.approx(127.3, abs=0.1)
    assert r["deflection_max_mm"] == pytest.approx(0.849, abs=0.002)


def test_gdt_position():
    assert gdt.fastener_position(9, 8)["position_tol_at_mmc_mm"] == pytest.approx(1.0)
    assert gdt.fastener_position(9, 8, fixed=True)["position_tol_at_mmc_mm"] == pytest.approx(0.5)


def test_drawing(bracket, tmp_path):
    from cadfea.drawing import make_drawing
    svg = make_drawing(bracket, tmp_path / "b.svg").read_text(encoding="utf-8")
    assert "Delik tablosu" in svg and "4× Ø6.4" in svg


def test_tojson_in_template_roundtrip(cfg, part, tmp_path):
    """Şablondaki tojson Python'da da geçerli JSON üretmeli."""
    s = build_script(cfg, part, tmp_path)
    head = s.split("R = {\"ok\"")[0]
    ns = {}
    exec(head, ns)
    obj = {"a": [1, 2.5, None, True], "b": "ş\\x\"", "c": {"d": float("nan")}}
    assert json.loads(ns["tojson"](obj)) == {"a": [1, 2.5, None, True], "b": "ş\\x\"", "c": {"d": None}}
