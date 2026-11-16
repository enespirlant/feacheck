"""Bir geometri dosyasını uçtan uca analiz eder."""
from __future__ import annotations

import csv
import json
import shutil
import time
from datetime import datetime
from pathlib import Path

from .config import ConfigError, config_for_part
from .report import write_report
from .script_builder import build_script

MASS_TO_KG = {"t": 1000.0, "tonne": 1000.0, "kg": 1.0, "g": 0.001}


class MechanicalSession:
    """PyMechanical oturumu. İzleyici modunda tekrar tekrar açılmasın diye bir kez açılır."""

    def __init__(self, version: int, show_gui: bool):
        self.version, self.show_gui, self._m = version, show_gui, None

    def run(self, script: str, fresh: bool = False) -> str:
        """fresh=True: önceki modeli temizle (her yeni analizde). feacheck aynı oturumda ardışık komut yollar."""
        from ansys.mechanical.core import launch_mechanical  # Ansys sadece Windows PC'de

        if self._m is None:
            kw = {}
            if self.version < 242:  # 2024 R1 ve öncesi güvenli gRPC desteklemiyor (yerel bağlantı)
                kw["transport_mode"] = "insecure"
            self._m = launch_mechanical(batch=not self.show_gui, version=self.version,
                                        cleanup_on_exit=True, **kw)
        elif fresh:
            self._m.clear()
        return self._m.run_python_script(script)

    def close(self):
        if self._m is not None:
            try:
                self._m.exit()
            finally:
                self._m = None


def resolve_geometry(cfg: dict, geometry: Path) -> dict:
    """Kapsamları (delikler, düzlemler, yüz no...) geometrik tanımlara çevirir.

    cadquery yoksa veya dosya Parasolid ise eski yol kullanılır (eksen kuralı Mechanical'da).
    """
    try:
        from . import geometry as G
    except ImportError:
        return {"available": False, "note": "cadquery kurulu değil; sadece axis/named_selection kapsamları"}
    if geometry.suffix.lower() not in (".step", ".stp", ".igs", ".iges"):
        return {"available": False, "note": "Parasolid Ansys'siz okunamıyor; gelişmiş kapsam için STEP kullan"}
    part = G.inspect(geometry)
    loads = cfg["loads"]

    def res(spec, where):
        try:
            return G.resolve_scope(part, spec)
        except ValueError as e:
            raise ConfigError(f"{where}: {e}")

    loads["fixed"] = [res(s, f"fixed[{i}]") for i, s in enumerate(loads.get("fixed") or [])]
    for key in ("forces", "pressures"):
        for i, ld in enumerate(loads.get(key) or []):
            ld["scope"] = res(ld["scope"], f"{key}[{i}]")
    xs = [[f.centroid[k] for f in part.faces] for k in range(3)]
    cfg["_geo"] = {"ref_volume_mm3": part.volume_mm3,
                   "ref_span_mm": max(max(v) - min(v) for v in xs),
                   "match_tol_mm": max(0.02, 2e-4 * max(part.size_mm))}
    out = {"available": True, "volume_mm3": part.volume_mm3, "size_mm": part.size_mm}
    rho = cfg["material"].get("density_kg_m3")
    if rho:
        out["mass_kg"] = round(part.volume_mm3 * 1e-9 * rho, 5)
    return out


def summarize(raw: dict, cfg: dict) -> dict:
    s = {"ok": raw.get("ok", False), "errors": raw.get("errors", []),
         "warnings": list(raw.get("warnings", [])), "scopes": raw.get("scopes", [])}
    runs = raw.get("runs") or []
    if not runs:
        return s
    last = runs[-1]
    vm, dm = last.get("max_von_mises"), last.get("max_deformation")
    s.update({"element_size_mm": last["element_size_mm"], "nodes": last.get("nodes"),
              "elements": last.get("elements"), "max_von_mises_mpa": vm,
              "max_deformation_mm": dm, "solution_state": last.get("solution_state")})
    if last.get("max_von_mises_unit", "MPa") != "MPa":
        s["warnings"].append(f"Gerilme birimi beklenen MPa değil: {last.get('max_von_mises_unit')}")
    unit = raw.get("mass_unit")
    if raw.get("mass_value") is not None and unit in MASS_TO_KG:
        s["mass_kg"] = raw["mass_value"] * MASS_TO_KG[unit]

    mat = cfg["material"]
    if mat.get("mode") == "scaled" and dm is not None:
        from .materials import E_STRUCTURAL_STEEL
        k = E_STRUCTURAL_STEEL / float(mat["E_gpa"])
        s["max_deformation_mm"] = dm * k
        s["material_note"] = (f"{mat['db']}: çözüm Structural Steel ile yapıldı, deformasyon E oranıyla "
                              f"×{k:.3f} ölçeklendi, gerilme aynı. Kesin sonuç için Engineering Data xml ver.")
    sy = mat.get("yield_strength_mpa")
    if sy and vm:
        s["safety_factor"] = round(sy / vm, 3)
        if s["safety_factor"] < cfg.get("results", {}).get("sf_warning", 1.5):
            s["warnings"].append(f"Güvenlik katsayısı düşük: {s['safety_factor']}")

    if len(runs) >= 2 and runs[-2].get("max_von_mises"):
        prev = runs[-2]["max_von_mises"]
        change = abs(vm - prev) / abs(prev) * 100
        s["convergence"] = {"sizes_mm": [r["element_size_mm"] for r in runs],
                            "von_mises_mpa": [r.get("max_von_mises") for r in runs],
                            "last_change_pct": round(change, 2), "converged": change < 5.0}
        if change >= 5.0:
            s["warnings"].append(f"Mesh yakınsamadı (son değişim %{change:.1f}). Daha küçük eleman dene "
                                 "veya maksimum gerilme bir tekillik (keskin köşe/mesnet) olabilir.")
    else:
        s["warnings"].append("Mesh yakınsaması yapılmadı (mesh.convergence_sizes_mm boş).")
    return s


def analyze(geometry: Path, cfg: dict, overrides: dict | None = None,
            session: MechanicalSession | None = None, script_only: bool | None = None) -> dict:
    geometry = Path(geometry).resolve()
    if not geometry.exists():
        raise FileNotFoundError(geometry)
    cfg = config_for_part(cfg, geometry, overrides)
    geo = resolve_geometry(cfg, geometry)

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "_" + geometry.stem
    out = Path(cfg["paths"]["runs"]) / run_id
    out.mkdir(parents=True, exist_ok=True)
    geo_copy = out / geometry.name
    shutil.copy2(geometry, geo_copy)

    is_script_only = script_only if script_only is not None else cfg["ansys"]["mode"] == "script_only"
    script = build_script(cfg, geo_copy, out, save_mechdb=not is_script_only)
    (out / "mechanical_script.py").write_text(script, encoding="utf-8")
    (out / "config_used.json").write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")

    if is_script_only:
        return {"run_id": run_id, "status": "script_ready", "dir": str(out),
                "note": "Mechanical > Automation > Scripting içine mechanical_script.py'yi yapıştır."}

    own = session is None
    session = session or MechanicalSession(int(cfg["ansys"]["version"]), bool(cfg["ansys"]["show_gui"]))
    t0 = time.time()
    returned, run_error = "{}", None
    try:
        returned = session.run(script, fresh=True)
    except Exception as e:  # script yarıda kalsa bile o ana kadarki sonuçlar dosyada
        run_error = str(e).strip().splitlines()[-1][:500] if str(e).strip() else repr(e)
    finally:
        if own:
            session.close()

    raw_file = out / "result_raw.json"
    txt = raw_file.read_text(encoding="utf-8") if raw_file.exists() else ""
    raw = json.loads(txt) if txt.strip() else {"ok": False, "errors": ["sonuç dosyası boş"]}
    summary = summarize(raw, cfg)
    if run_error:
        summary["errors"] = summary.get("errors", []) + [f"Mechanical: {run_error}"]
    summary["geometry"] = geo
    if geo.get("mass_kg") is not None:
        summary["mass_kg"] = geo["mass_kg"]  # CAD hacmi x gerçek yoğunluk
    summary.update({"run_id": run_id, "file": geometry.name, "dir": str(out),
                    "duration_s": round(time.time() - t0, 1)})
    (out / "result.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_report(out, summary, cfg)
    _append_index(Path(cfg["paths"]["runs"]), summary)
    return summary


def _append_index(runs_dir: Path, s: dict):
    f = runs_dir / "summary.csv"
    cols = ["run_id", "file", "ok", "element_size_mm", "nodes", "max_von_mises_mpa",
            "max_deformation_mm", "safety_factor", "mass_kg", "duration_s"]
    new = not f.exists()
    with open(f, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerow(s)


def list_runs(runs_dir: Path, limit: int = 10) -> list[dict]:
    runs_dir = Path(runs_dir)
    if not runs_dir.exists():
        return []
    out = []
    for d in sorted((p for p in runs_dir.iterdir() if p.is_dir()), reverse=True)[:limit]:
        r = d / "result.json"
        if r.exists():
            s = json.loads(r.read_text(encoding="utf-8"))
            out.append({k: s.get(k) for k in ("run_id", "ok", "max_von_mises_mpa",
                                              "max_deformation_mm", "safety_factor", "mass_kg")})
        else:
            out.append({"run_id": d.name, "status": "script_only_or_failed"})
    return out
