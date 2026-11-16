"""Ayarlardan Mechanical scriptini üretir."""
from __future__ import annotations

import json
from pathlib import Path

from .mechanical_template import TEMPLATE


def build_script(cfg: dict, geometry_path: Path, out_dir: Path, save_mechdb: bool = False) -> str:
    mesh = cfg["mesh"]
    sizes = [float(s) for s in (mesh.get("convergence_sizes_mm") or [])] or [float(mesh["element_size_mm"])]
    payload = {
        "geometry_path": str(Path(geometry_path).resolve()),
        "out_dir": str(Path(out_dir).resolve()),
        "named_selection_prefix": cfg["geometry"].get("named_selection_prefix", "NS_"),
        "material_name": cfg["material"]["name"],
        "material_xml": cfg["material"].get("xml"),
        "mesh_sizes": sizes,
        "loads": cfg["loads"],
        "export_images": bool(cfg.get("results", {}).get("export_images", True)),
        "save_mechdb": save_mechdb,
        **cfg.get("_geo", {}),
    }
    return TEMPLATE.replace("__CFG_LITERAL__", pylit(payload))


def pylit(o) -> str:
    """IronPython 2.7 ve Python 3'te aynı okunan, sadece ASCII Python literal'i."""
    if o is None:
        return "None"
    if isinstance(o, bool):
        return "True" if o else "False"
    if isinstance(o, (int, float)):
        return repr(o)
    if isinstance(o, str):
        return "u" + json.dumps(o, ensure_ascii=True)
    if isinstance(o, dict):
        return "{" + ", ".join(f"{pylit(str(k))}: {pylit(v)}" for k, v in o.items()) + "}"
    if isinstance(o, (list, tuple)):
        return "[" + ", ".join(pylit(v) for v in o) + "]"
    raise TypeError(f"Desteklenmeyen tip: {type(o)}")


def read_cfg(script: str) -> dict:
    """Üretilmiş scriptteki CFG literal'ini geri okur (test/hata ayıklama)."""
    import ast
    blob = script.split("CFG = ", 1)[1].split("\n# CFG_END", 1)[0]
    return ast.literal_eval(blob)
