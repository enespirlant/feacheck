"""STEP/IGES geometrisini Ansys'siz okur: yüzler, delik grupları, datum adayları, kütle.

Burada üretilen yüz numaraları (face id) sadece bu modüle aittir. Mechanical'a
gönderilirken geometrik tanıma (düzlem / silindir / nokta) çevrilir, böylece
Ansys yüzleri farklı bölse bile doğru yüzler seçilir.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

import cadquery as cq
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cone, GeomAbs_Cylinder, GeomAbs_Plane, GeomAbs_Sphere, GeomAbs_Torus

SURF = {GeomAbs_Plane: "plane", GeomAbs_Cylinder: "cylinder", GeomAbs_Cone: "cone",
        GeomAbs_Sphere: "sphere", GeomAbs_Torus: "torus"}


def _r(v, n=3):
    return [round(float(x), n) + 0.0 for x in v]


@dataclass
class Face:
    id: int
    type: str
    area_mm2: float
    centroid: list
    bbox_min: list
    bbox_max: list
    normal: list | None = None          # düzlem: dışa bakan normal
    radius_mm: float | None = None      # silindir
    axis_point: list | None = None
    axis_dir: list | None = None
    axial_range: list | None = None     # eksen boyunca [min, max]
    internal: bool | None = None        # silindir: True = delik, False = mil/boss


@dataclass
class Part:
    file: str
    bbox_min: list
    bbox_max: list
    size_mm: list
    volume_mm3: float
    area_mm2: float
    faces: list = field(default_factory=list)


def _unit(v):
    n = math.sqrt(sum(c * c for c in v)) or 1.0
    return [c / n for c in v]


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _load(path: Path) -> cq.Shape:
    suf = path.suffix.lower()
    if suf in (".step", ".stp"):
        return cq.importers.importStep(str(path)).val()
    if suf in (".igs", ".iges"):
        from OCP.IGESControl import IGESControl_Reader
        rd = IGESControl_Reader()
        rd.ReadFile(str(path))
        rd.TransferRoots()
        return cq.Shape.cast(rd.OneShape())
    raise ValueError(f"{suf} okunamıyor. Parasolid (.x_t) için NX'ten STEP de export et.")


def _face_info(i: int, f: cq.Face) -> Face:
    ad = BRepAdaptor_Surface(f.wrapped)
    kind = SURF.get(ad.GetType(), "other")
    bb = f.BoundingBox()
    c = f.Center()
    info = Face(id=i, type=kind, area_mm2=round(f.Area(), 3), centroid=_r(c.toTuple()),
                bbox_min=_r((bb.xmin, bb.ymin, bb.zmin)), bbox_max=_r((bb.xmax, bb.ymax, bb.zmax)))
    if kind == "plane":
        info.normal = _r(f.normalAt().toTuple(), 4)
    elif kind == "cylinder":
        cyl = ad.Cylinder()
        ax = cyl.Axis()
        p0 = ax.Location()
        d = _unit((ax.Direction().X(), ax.Direction().Y(), ax.Direction().Z()))
        # yüz üzerinde bir nokta ve oradaki normal -> delik mi mil mi?
        u = (ad.FirstUParameter() + ad.LastUParameter()) / 2
        v = (ad.FirstVParameter() + ad.LastVParameter()) / 2
        pt = ad.Value(u, v)
        pv = cq.Vector(pt.X(), pt.Y(), pt.Z())
        n = f.normalAt(pv).toTuple()
        rel = [pv.x - p0.X(), pv.y - p0.Y(), pv.z - p0.Z()]
        radial = [rel[k] - _dot(rel, d) * d[k] for k in range(3)]
        info.internal = _dot(radial, n) < 0
        info.radius_mm = round(cyl.Radius(), 4)
        info.axis_dir = _r(d, 5)
        # eksen boyunca uzanım: bbox köşelerini eksene izdüşür
        corners = [(x, y, z) for x in (bb.xmin, bb.xmax) for y in (bb.ymin, bb.ymax) for z in (bb.zmin, bb.zmax)]
        base = (p0.X(), p0.Y(), p0.Z())
        ts = [_dot([cc[k] - base[k] for k in range(3)], d) for cc in corners]
        # eksen noktasını yüzün merkez yüksekliğine taşı (okunabilirlik için)
        tc = _dot([c.x - base[0], c.y - base[1], c.z - base[2]], d)
        info.axis_point = _r([base[k] + tc * d[k] for k in range(3)])
        lo, hi = min(ts) - tc, max(ts) - tc
        # bbox izdüşümü yarıçap kadar şişer; eksen boyunca gerçek uzunluk için düzelt
        info.axial_range = [round(lo, 3), round(hi, 3)]
    return info


@lru_cache(maxsize=16)
def _inspect_cached(path: str, mtime: float) -> Part:
    shape = _load(Path(path))
    bb = shape.BoundingBox()
    faces = [_face_info(i, f) for i, f in enumerate(shape.Faces())]
    return Part(file=Path(path).name, bbox_min=_r((bb.xmin, bb.ymin, bb.zmin)),
                bbox_max=_r((bb.xmax, bb.ymax, bb.zmax)),
                size_mm=_r((bb.xlen, bb.ylen, bb.zlen)), volume_mm3=round(shape.Volume(), 3),
                area_mm2=round(shape.Area(), 3), faces=faces)


def inspect(path: Path) -> Part:
    p = Path(path).resolve()
    return _inspect_cached(str(p), p.stat().st_mtime)


# ---------------------------------------------------------------- özellik tanıma

def hole_groups(part: Part, tol=0.01) -> list[dict]:
    """Aynı yarıçaplı iç silindirleri (delikleri) eksenlerine göre gruplar."""
    holes = {}
    for f in part.faces:
        if f.type != "cylinder" or not f.internal:
            continue
        key = round(f.radius_mm / tol) * tol
        axis_key = tuple(round(abs(c), 2) for c in f.axis_dir)
        # Aynı deliğin iki yarısı aynı eksende: eksen noktası ile birleştir
        holes.setdefault((key, axis_key), {})
        pos_key = tuple(round(c, 1) for c in _project_out(f.axis_point, f.axis_dir))
        holes[(key, axis_key)].setdefault(pos_key, []).append(f.id)
    out = []
    for (r, ax), positions in sorted(holes.items()):
        out.append({"diameter_mm": round(2 * r, 3), "axis": list(ax), "count": len(positions),
                    "positions": [list(p) for p in positions], "face_ids": sum(positions.values(), [])})
    return out


def _project_out(p, d):
    """Noktayı eksen doğrultusundaki bileşeninden arındır (aynı deliğin parçalarını eşlemek için)."""
    t = _dot(p, d)
    return [p[k] - t * d[k] for k in range(3)]


def planar_groups(part: Part) -> list[dict]:
    """Aynı normal + aynı düzlemdeki yüzleri birleştirir, alana göre sıralar."""
    groups = {}
    for f in part.faces:
        if f.type != "plane":
            continue
        n = tuple(round(c, 3) for c in f.normal)
        off = round(_dot(f.centroid, n), 2)
        g = groups.setdefault((n, off), {"normal": list(n), "offset_mm": off, "area_mm2": 0.0, "face_ids": []})
        g["area_mm2"] += f.area_mm2
        g["face_ids"].append(f.id)
    out = sorted(groups.values(), key=lambda g: -g["area_mm2"])
    for g in out:
        g["area_mm2"] = round(g["area_mm2"], 2)
    return out


def datum_suggestion(part: Part) -> dict:
    """ASME Y14.5 / ISO 5459 mantığıyla datum referans çerçevesi önerisi."""
    planes = planar_groups(part)
    holes = hole_groups(part)
    if not planes:
        return {"note": "Düzlemsel yüz yok; datumu silindirik bir yüzden kur (örn. mil ekseni A)."}
    A = planes[0]
    B = next((p for p in planes[1:] if abs(_dot(p["normal"], A["normal"])) < 0.05), None)
    C = None
    hole_parallel_to_A = [h for h in holes if abs(_dot(h["axis"], [abs(c) for c in A["normal"]])) > 0.95]
    if hole_parallel_to_A:
        h = max(hole_parallel_to_A, key=lambda h: h["diameter_mm"])
        C = {"type": "hole", "diameter_mm": h["diameter_mm"], "count": h["count"],
             "why": "A'ya dik delik(ler): montajda konumu belirleyen özellik, B/C için ideal."}
    elif B:
        C = next((p for p in planes[1:] if p is not B and abs(_dot(p["normal"], A["normal"])) < 0.05
                  and abs(_dot(p["normal"], B["normal"])) < 0.05), None)
    return {
        "A": {**A, "why": "En büyük düzlem: parçanın oturduğu birincil yüz (3 serbestlik)."},
        "B": ({**B, "why": "A'ya dik en büyük düzlem (2 serbestlik)."} if B else None),
        "C": C,
        "note": "Öneri geometriden türetildi. Datumlar parçanın montajdaki gerçek oturma "
                "yüzlerine göre seçilir; fonksiyonu sen biliyorsun, son kararı sen ver.",
    }


def summary(part: Part, density_kg_m3: float | None = None) -> dict:
    """Claude için kısa özet (token tasarrufu): tüm yüz listesi yerine gruplar."""
    planes = planar_groups(part)
    s = {"file": part.file, "size_mm": part.size_mm, "bbox_min": part.bbox_min, "bbox_max": part.bbox_max,
         "volume_mm3": part.volume_mm3, "face_count": len(part.faces),
         "face_types": {t: sum(1 for f in part.faces if f.type == t) for t in {f.type for f in part.faces}},
         "holes": hole_groups(part),
         "bosses": [{"diameter_mm": round(2 * f.radius_mm, 3), "axis": f.axis_dir, "face_id": f.id}
                    for f in part.faces if f.type == "cylinder" and f.internal is False][:10],
         "largest_planes": planes[:6]}
    if density_kg_m3:
        s["mass_kg"] = round(part.volume_mm3 * 1e-9 * density_kg_m3, 5)
    return s


def face_details(part: Part, ids: list[int]) -> list[dict]:
    return [asdict(f) for f in part.faces if f.id in set(ids)]


# ---------------------------------------------------------------- kapsam çözümleme

def _primitive(f: Face) -> dict:
    """Bir yüzü Mechanical'ın tanıyabileceği geometrik tanıma çevirir."""
    if f.type == "plane":
        return {"kind": "plane", "point": f.centroid, "normal": f.normal,
                "bbox_min": f.bbox_min, "bbox_max": f.bbox_max}
    if f.type == "cylinder":
        return {"kind": "cylinder", "axis_point": f.axis_point, "axis_dir": f.axis_dir,
                "radius": f.radius_mm, "axial_range": f.axial_range}
    return {"kind": "point", "point": f.centroid, "bbox_min": f.bbox_min, "bbox_max": f.bbox_max}


def select_faces(part: Part, scope: dict) -> list[Face]:
    tol = float(scope.get("tol", 0.01))
    if "face_ids" in scope:
        ids = set(scope["face_ids"])
        return [f for f in part.faces if f.id in ids]
    if "holes" in scope:
        d = float(scope["holes"]["diameter_mm"])
        t = float(scope["holes"].get("tol_mm", 0.02))
        return [f for f in part.faces if f.type == "cylinder" and f.internal and abs(2 * f.radius_mm - d) <= t]
    if "cylinders" in scope:
        d = float(scope["cylinders"]["diameter_mm"])
        t = float(scope["cylinders"].get("tol_mm", 0.02))
        return [f for f in part.faces if f.type == "cylinder" and abs(2 * f.radius_mm - d) <= t]
    if "planes" in scope:
        n = _unit(scope["planes"]["normal"])
        out = [f for f in part.faces if f.type == "plane" and _dot(f.normal, n) > 0.999]
        if "offset_mm" in scope["planes"]:
            o = float(scope["planes"]["offset_mm"])
            out = [f for f in out if abs(_dot(f.centroid, n) - o) <= scope["planes"].get("tol_mm", 0.05)]
        return out
    if "axis" in scope:
        k = "xyz".index(scope["axis"])
        span = (part.bbox_max[k] - part.bbox_min[k]) or 1.0
        target = part.bbox_min[k] if scope["side"] == "min" else part.bbox_max[k]
        return [f for f in part.faces if f.type == "plane"
                and abs(f.bbox_min[k] - target) <= tol * span and abs(f.bbox_max[k] - target) <= tol * span]
    raise ValueError(f"Tanınmayan kapsam: {scope}")


def resolve_scope(part: Part, scope: dict) -> dict:
    """Kullanıcı/Claude kapsamını Mechanical'a gidecek geometrik tanıma çevirir."""
    if "named_selection" in scope:
        return scope
    faces = select_faces(part, scope)
    if not faces:
        raise ValueError(f"Kapsam hiçbir yüzle eşleşmedi: {scope}")
    return {"geo": [_primitive(f) for f in faces], "face_ids": [f.id for f in faces],
            "area_mm2": round(sum(f.area_mm2 for f in faces), 3), "source": scope}
