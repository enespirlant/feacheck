"""Claude için MCP sunucusu: tasarım Ar-Ge asistanı.

Akış:  inspect_part -> propose_setup -> (Enes/Claude düzenler) -> save_setup -> run_analysis
Araçlar kısa, sayısal özet döndürür (token tasarrufu). Ham dosyalar diskte kalır.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml
from mcp.server.fastmcp import FastMCP

from . import gdt as G
from . import handcalc as HC
from . import materials as M
from . import tolerances as T
from .config import ConfigError, config_for_part, load_config
from .runner import MechanicalSession, analyze, list_runs

mcp = FastMCP("cad-fea-bridge", instructions=(
    "Enes'in tasarım Ar-Ge asistanı. Analizden önce DAİMA inspect_part ve propose_setup kullan, "
    "kurulumu Enes'e göster, onay alınca save_setup ile kaydet. Yük değerini asla uydurma. "
    "Sonuçları el hesabıyla (hand_calc) kıyasla, yakınsama ve tekillik uyarılarını açıkça söyle."))
STATE: dict = {"cfg_path": None, "session": None}


def _cfg() -> dict:
    return load_config(STATE["cfg_path"])


def _inbox() -> Path:
    return Path(_cfg()["paths"]["inbox"])


def _file(name: str) -> Path:
    p = _inbox() / name
    if not p.exists():
        raise FileNotFoundError(f"inbox'ta yok: {name}")
    return p


def _session(cfg) -> MechanicalSession:
    if STATE["session"] is None:
        STATE["session"] = MechanicalSession(int(cfg["ansys"]["version"]), bool(cfg["ansys"]["show_gui"]))
    return STATE["session"]


# ------------------------------------------------------------------ parça

@mcp.tool()
def list_inbox() -> list[dict]:
    """inbox'taki geometri dosyaları ve her birinin onaylı kurulumu (yaml) var mı."""
    cfg = _cfg()
    exts = {e.lower() for e in cfg["geometry"]["formats"]}
    inbox = Path(cfg["paths"]["inbox"])
    if not inbox.exists():
        return []
    return [{"file": p.name, "setup": p.with_suffix(".yaml").exists(),
             "proposal": p.with_suffix(".proposal.yaml").exists()}
            for p in sorted(inbox.iterdir()) if p.suffix.lower() in exts]


@mcp.tool()
def inspect_part(file_name: str, material: str = "Structural Steel") -> dict:
    """Parçayı okur: ölçüler, hacim, kütle, delik grupları, dış silindirler, en büyük düzlemler.
    Yüz numaraları (face_ids) save_setup'ta {face_ids: [...]} kapsamı olarak kullanılabilir."""
    from .geometry import inspect, summary
    return summary(inspect(_file(file_name)), M.get(material)["rho"])


@mcp.tool()
def face_info(file_name: str, face_ids: list[int]) -> list[dict]:
    """Belirli yüzlerin ayrıntısı (tip, alan, merkez, normal, yarıçap, eksen)."""
    from .geometry import face_details, inspect
    return face_details(inspect(_file(file_name)), face_ids)


@mcp.tool()
def propose_setup(file_name: str, material: str = "Structural Steel") -> dict:
    """Geometriye bakarak mesnet/yük/mesh ÖNERİR ve <parça>.proposal.yaml olarak kaydeder.
    Yük büyüklüğü boş bırakılır; Enes'e sor. Onay sonrası save_setup çağır."""
    from .advisor import propose
    from .geometry import inspect
    p = _file(file_name)
    r = propose(inspect(p), material)
    p.with_suffix(".proposal.yaml").write_text(r["yaml"], encoding="utf-8")
    return {"proposal_yaml": r["yaml"], "notes": r["notes"]}


@mcp.tool()
def save_setup(file_name: str, setup_yaml: str) -> dict:
    """Onaylanan kurulumu <parça>.yaml olarak kaydeder (doğrulayarak).
    Kapsam türleri: {holes: {diameter_mm}}, {cylinders: {diameter_mm}}, {planes: {normal, offset_mm}},
    {face_ids: [...]}, {axis: x|y|z, side: min|max}, {named_selection: NS_...}.
    Malzeme: material: {db: Al6061-T6} (liste: materials)."""
    p = _file(file_name)
    data = yaml.safe_load(setup_yaml) or {}
    try:
        cfg = config_for_part(_cfg(), p.with_suffix(".__none__"), data)
        from .runner import resolve_geometry
        geo = resolve_geometry(cfg, p)
    except (ConfigError, ValueError) as e:
        return {"saved": False, "error": str(e)}
    p.with_suffix(".yaml").write_text(setup_yaml, encoding="utf-8")
    scopes = [{"tag": "FIX", "faces": s.get("face_ids"), "area_mm2": s.get("area_mm2")} for s in cfg["loads"]["fixed"]]
    scopes += [{"tag": "FORCE", "faces": f["scope"].get("face_ids"), "area_mm2": f["scope"].get("area_mm2")}
               for f in cfg["loads"].get("forces") or []]
    return {"saved": True, "resolved_scopes": scopes, "geometry": geo}


# ------------------------------------------------------------------ analiz

@mcp.tool()
def get_config() -> str:
    """Varsayılan analiz ayarları (malzeme, mesh, yükler) YAML."""
    cfg = _cfg()
    return yaml.safe_dump({k: cfg[k] for k in ("material", "mesh", "loads")}, allow_unicode=True, sort_keys=False)


@mcp.tool()
def run_analysis(file_name: str, overrides_yaml: str = "", script_only: bool = False) -> dict:
    """Statik yapısal analiz. Parçanın onaylı <parça>.yaml kurulumu yoksa çalışmaz (önce propose/save).
    Dönüş: max von Mises [MPa], deformasyon [mm], güvenlik katsayısı, kütle [kg], kapsamlar, uyarılar."""
    p = _file(file_name)
    if not p.with_suffix(".yaml").exists() and not overrides_yaml.strip():
        return {"error": "Onaylı kurulum yok. Önce propose_setup -> Enes onayı -> save_setup."}
    cfg = _cfg()
    over = yaml.safe_load(overrides_yaml) if overrides_yaml.strip() else None
    try:
        s = analyze(p, cfg, overrides=over, session=None if script_only else _session(cfg),
                    script_only=script_only)
    except ConfigError as e:
        return {"error": str(e)}
    s.pop("steps", None)
    return s


@mcp.tool()
def recent_runs(limit: int = 10) -> list[dict]:
    """Son analizlerin kısa özeti."""
    return list_runs(Path(_cfg()["paths"]["runs"]), limit)


@mcp.tool()
def get_run(run_id: str) -> dict:
    """Bir analizin tam özeti (kapsamlar, yakınsama, uyarılar)."""
    d = Path(_cfg()["paths"]["runs"]) / run_id
    r = d / "result.json"
    if not r.exists():
        return {"error": "sonuç yok", "files": [p.name for p in d.glob("*")] if d.exists() else []}
    return json.loads(r.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ mühendislik araçları

@mcp.tool()
def make_drawing(file_name: str, material: str = "-", title: str = "") -> dict:
    """A3 teknik resim taslağı (ön/sol/üst + izometrik, delik tablosu, datum önerisi, antet). SVG yolu döner."""
    from .drawing import make_drawing as md
    from .geometry import inspect
    p = _file(file_name)
    mass = None
    if material != "-":
        mass = inspect(p).volume_mm3 * 1e-9 * M.get(material)["rho"]
    out = Path(_cfg()["paths"]["runs"]) / "drawings"
    out.mkdir(parents=True, exist_ok=True)
    svg = md(p, out / f"{p.stem}.svg", material=material, mass_kg=mass, title=title or None)
    return {"svg": str(svg), "note": "Tarayıcıda aç. Taslaktır; imalat resmi NX Drafting'de tamamlanmalı."}


@mcp.tool()
def datum_suggestion(file_name: str) -> dict:
    """Geometriden datum referans çerçevesi (A/B/C) önerisi ve gerekçesi."""
    from .geometry import datum_suggestion as ds, inspect
    return ds(inspect(_file(file_name)))


@mcp.tool()
def fit(nominal_mm: float, hole: str = "H7", shaft: str = "g6") -> dict:
    """ISO 286 geçme: sınırlar, min/maks boşluk, geçme tipi. Örn. fit(20, 'H7', 'p6')."""
    return T.fit(nominal_mm, hole, shaft)


@mcp.tool()
def tolerance_stackup(dims_json: str, target_json: str = "") -> dict:
    """1B tolerans zinciri: en kötü durum, RSS, Monte Carlo, katkı yüzdeleri.
    dims_json: [{"name":"A","nominal":20,"tol":0.1,"dir":1}, {"name":"B","nominal":19.6,"tol":0.05,"dir":-1}]
    target_json: {"min":0.1,"max":0.6}"""
    return T.stackup(json.loads(dims_json), json.loads(target_json) if target_json else None)


@mcp.tool()
def gdt_position(hole_d_mm: float, fastener_d_mm: float, fixed: bool = False, hole_tol_mm: float = 0.0) -> dict:
    """Cıvata/pim deliği pozisyon toleransı (floating/fixed fastener) ve kontrol çerçevesi."""
    return G.fastener_position(hole_d_mm, fastener_d_mm, fixed, hole_tol_mm)


@mcp.tool()
def gdt_recommend(feature: str) -> dict:
    """Tipik GD&T önerisi. feature: mating_plane | bolt_pattern | bearing_seat | shaft_journal |
    locating_pin_hole | sheet_profile"""
    return G.recommend(feature)


@mcp.tool()
def hand_calc(kind: str, params_json: str) -> dict:
    """FEA doğrulama el hesapları.
    kind=beam: {"case":"cantilever|simply_supported|fixed_fixed","F_n":500,"L_mm":200,"E_gpa":200,"shape":"round","d":20}
               (rect: "b","h"; tube: "d","t")
    kind=bolt: {"size":"M8","grade":"8.8","K":0.2,"F_ext_n":2000,"n_bolts":4}
    kind=vessel: {"p_mpa":2,"D_mm":100,"t_mm":3}
    kind=buckling: {"E_gpa":200,"L_mm":500,"shape":"round","d":10,"K":1.0}"""
    p = json.loads(params_json)
    fn = {"beam": HC.beam, "bolt": HC.bolt, "vessel": HC.thin_pressure_vessel,
          "buckling": HC.euler_buckling}.get(kind)
    if fn is None:
        return {"error": "kind: beam | bolt | vessel | buckling"}
    return fn(**p)


@mcp.tool()
def materials() -> list[dict]:
    """Malzeme veritabanı (E, ν, ρ, akma, çekme)."""
    return M.table()


def serve(cfg_path=None):
    STATE["cfg_path"] = cfg_path
    try:
        mcp.run()
    finally:
        if STATE["session"]:
            STATE["session"].close()
