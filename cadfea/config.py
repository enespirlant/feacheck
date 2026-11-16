"""Ayar yükleme, parça bazlı override ve doğrulama."""
from __future__ import annotations

import copy
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config.yaml"
AXES = {"x", "y", "z"}


class ConfigError(ValueError):
    pass


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_config(path: Path | None = None) -> dict:
    path = Path(path or DEFAULT_CONFIG)
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    base = path.parent
    for key in ("inbox", "runs"):
        p = Path(cfg["paths"][key])
        cfg["paths"][key] = str((base / p).resolve() if not p.is_absolute() else p)
    return cfg


def _merge_part(cfg: dict, over: dict) -> dict:
    """Parça ayarı: yükler BİRLEŞTİRİLMEZ, tamamen değiştirilir (varsayılan yük sızmasın)."""
    out = deep_merge(cfg, {k: v for k, v in over.items() if k != "loads"})
    if "loads" in over:
        out["loads"] = {"fixed": [], "forces": [], "pressures": [], **copy.deepcopy(over["loads"])}
    return out


def config_for_part(cfg: dict, geometry: Path, extra: dict | None = None) -> dict:
    """Geometrinin yanındaki <isim>.yaml ve ek override'ları uygular."""
    cfg = copy.deepcopy(cfg)
    side = Path(geometry).with_suffix(".yaml")
    if side.exists():
        with open(side, encoding="utf-8") as f:
            cfg = _merge_part(cfg, yaml.safe_load(f) or {})
    if extra:
        cfg = _merge_part(cfg, extra)
    apply_material(cfg)
    validate(cfg)
    return cfg


def apply_material(cfg: dict):
    """material.db verilmişse veritabanından doldurur.

    Mechanical'da sadece 'Structural Steel' hazır olduğundan, başka malzeme için xml
    yoksa çözüm çelikle yapılır ve doğrusal statikte geçerli olan ölçekleme uygulanır:
    gerilme aynı kalır (tek malzeme, kuvvet/mesnet sınır şartı), deformasyon E oranıyla
    ölçeklenir. Poisson farkı küçük bir hata getirir, raporda belirtilir.
    """
    from .materials import get
    m = cfg.get("material", {})
    if not m.get("db"):
        return
    try:
        d = get(m["db"])
    except KeyError as e:
        raise ConfigError(str(e))
    m["yield_strength_mpa"] = d["sy"]
    m["density_kg_m3"] = d["rho"]
    m["E_gpa"] = d["E"]
    if m.get("xml"):
        m.setdefault("name", d["name"])
        m["mode"] = "xml"
    elif d.get("ansys"):
        m["name"] = d["ansys"]
        m["mode"] = "native"
    else:
        m["name"] = "Structural Steel"
        m["mode"] = "scaled"


SCOPE_KEYS = ("named_selection", "face_ids", "holes", "cylinders", "planes", "axis", "geo")


def _check_scope(scope: dict, where: str):
    if not isinstance(scope, dict):
        raise ConfigError(f"{where}: scope bir sözlük olmalı")
    if not any(k in scope for k in SCOPE_KEYS):
        raise ConfigError(f"{where}: kapsam türü yok. Seçenekler: {', '.join(SCOPE_KEYS[:-1])}")
    if "axis" not in scope:
        return
    if scope.get("axis") not in AXES:
        raise ConfigError(f"{where}: axis x/y/z olmalı (verilen: {scope.get('axis')})")
    if scope.get("side") not in ("min", "max"):
        raise ConfigError(f"{where}: side min veya max olmalı")


def validate(cfg: dict):
    loads = cfg.get("loads", {})
    fixed = loads.get("fixed") or []
    if not fixed:
        raise ConfigError("En az bir sabit mesnet (loads.fixed) gerekli, yoksa model serbest kalır.")
    for i, s in enumerate(fixed):
        _check_scope(s, f"fixed[{i}]")
    if not (loads.get("forces") or loads.get("pressures")):
        raise ConfigError("En az bir kuvvet veya basınç gerekli.")
    for i, f in enumerate(loads.get("forces") or []):
        _check_scope(f.get("scope"), f"forces[{i}]")
        c = f.get("components_n")
        if c is None:
            raise ConfigError(f"forces[{i}]: yük değeri girilmemiş. components_n: [Fx, Fy, Fz] (N) yaz.")
        if not (isinstance(c, list) and len(c) == 3 and all(isinstance(x, (int, float)) for x in c)):
            raise ConfigError(f"forces[{i}]: components_n [Fx, Fy, Fz] sayı listesi olmalı")
    for i, p in enumerate(loads.get("pressures") or []):
        _check_scope(p.get("scope"), f"pressures[{i}]")
        if "mpa" not in p:
            raise ConfigError(f"pressures[{i}]: mpa değeri eksik")
    if float(cfg["mesh"]["element_size_mm"]) <= 0:
        raise ConfigError("mesh.element_size_mm pozitif olmalı")
