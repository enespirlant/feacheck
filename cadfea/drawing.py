"""STEP'ten teknik resim TASLAĞI (A3, ISO birinci açı / E metodu).

Üretir: ön, sol yan ve üst görünüş (gizli çizgiler kesikli), izometrik, ana ölçüler,
delik tablosu, datum önerisi, genel tolerans notu ve antet.
Bu bir taslaktır: imalata gidecek resim NX Drafting'de ölçülendirilip kontrol edilmelidir.
"""
from __future__ import annotations

import html
import re
from datetime import date
from pathlib import Path

import cadquery as cq
from cadquery.occ_impl.exporters.svg import getSVG

from .geometry import datum_suggestion, hole_groups, inspect

W, H = 420, 297  # A3 yatay, mm
# Görünüş matrisleri: satırlar = ekran sağ (X'), ekran yukarı (Y'), bakan kişiye doğru (Z')
VIEWS = {
    "front": [[1, 0, 0], [0, 0, 1], [0, -1, 0]],    # -Y'den bakış
    "left": [[0, -1, 0], [0, 0, 1], [-1, 0, 0]],    # -X'ten bakış (birinci açıda sağa yerleşir)
    "top": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],       # +Z'den bakış (birinci açıda alta yerleşir)
}


ROTATIONS = {  # VIEWS matrislerini üreten eksen döndürmeleri (sağ el kuralı, derece)
    "front": [((1, 0, 0), -90)],
    "left": [((1, 0, 0), -90), ((0, 1, 0), 90)],
    "top": [],
}


def _rot(shape: cq.Shape, name: str) -> cq.Shape:
    o = cq.Vector(0, 0, 0)
    for axis, ang in ROTATIONS[name]:
        shape = shape.rotate(o, cq.Vector(*axis), ang)
    return shape


def _extent(rows, size):
    """Görünüşteki genişlik/yükseklik (mm)."""
    w = sum(abs(rows[0][k]) * size[k] for k in range(3))
    h = sum(abs(rows[1][k]) * size[k] for k in range(3))
    return w, h


def _view_svg(shape, proj, w_px, x, y, stroke_mm=0.35, model_w=None):
    """width verilip height=None bırakılınca getSVG tam ölçekli çizer (0.75 dolgu yok)."""
    unit = w_px / model_w if model_w else 1.0
    s = getSVG(shape, {"width": w_px, "height": None, "marginLeft": 0, "marginTop": 0,
                       "projectionDir": proj, "showAxes": False, "showHidden": True,
                       "strokeWidth": stroke_mm / unit,
                       "strokeColor": (20, 20, 20), "hiddenColor": (120, 120, 120)})
    s = re.sub(r"<\?xml[^>]*\?>", "", s)
    h = float(re.search(r'height="([0-9.]+)"', s).group(1))
    return re.sub(r"<svg\b", f'<svg x="{x:.2f}" y="{y:.2f}" overflow="visible"', s, count=1), h


def _scale_for(size, area_w, area_h):
    std = [5, 2, 1, 0.5, 0.2, 0.1, 0.05, 0.02, 0.01]
    fw, fh = size[0] + size[1], size[2] + size[1]   # ön+sol yan genişlik, ön+üst yükseklik
    for s in std:
        if fw * s <= area_w and fh * s <= area_h:
            return s
    return std[-1]


def make_drawing(step: Path, out_svg: Path, material: str = "-", mass_kg: float | None = None,
                 drawn_by: str = "Enes", title: str | None = None) -> Path:
    step = Path(step)
    part = inspect(step)
    shape = cq.importers.importStep(str(step)).val()
    shape = shape.translate(cq.Vector(*[-(a + b) / 2 for a, b in zip(part.bbox_min, part.bbox_max)]))
    sx, sy, sz = part.size_mm

    area_w, area_h = 250, 190
    scale = _scale_for(part.size_mm, area_w - 30, area_h - 30)
    gap = 18
    fw, fh = _extent(VIEWS["front"], part.size_mm)
    lw, _ = _extent(VIEWS["left"], part.size_mm)
    _, th = _extent(VIEWS["top"], part.size_mm)
    x0, y0 = 20, 20
    pos = {"front": (x0, y0), "left": (x0 + fw * scale + gap, y0), "top": (x0, y0 + fh * scale + gap)}
    sizes = {"front": (fw, fh), "left": (lw, fh), "top": (fw, th)}

    parts_svg = []
    for name, rows in VIEWS.items():
        w, h = sizes[name]
        px, py = pos[name]
        rotated = _rot(shape, name)
        parts_svg.append(_view_svg(rotated, (0, 0, 1), w * scale, px, py, model_w=w)[0])
        parts_svg.append(f'<text x="{px}" y="{py + h * scale + 7}" class="lbl">{ {"front": "ÖN", "left": "SOL YAN", "top": "ÜST"}[name]}</text>')

    # ana ölçüler (ön görünüşe) - basit ölçü çizgileri
    fx, fy = pos["front"]
    dim = []
    dim.append(_hdim(fx, fx + fw * scale, fy - 6, f"{sx:g}"))
    dim.append(_vdim(fx - 6, fy, fy + fh * scale, f"{sz:g}"))
    lx, _ = pos["left"]
    dim.append(_hdim(lx, lx + lw * scale, fy - 6, f"{sy:g}"))

    # izometrik
    iso, iso_h = _view_svg(shape, (1, -1, 1), 80, 305, 20, stroke_mm=0.3,
                           model_w=max(part.size_mm) * 1.3)
    if iso_h > 80:  # çok uzun parçalarda yüksekliği sınırla
        k = 80 / iso_h
        iso, iso_h = _view_svg(shape, (1, -1, 1), 80 * k, 305, 20, stroke_mm=0.3,
                               model_w=max(part.size_mm) * 1.3)
    ny = 20 + iso_h + 10  # sağ sütun notlarının başladığı y

    holes = hole_groups(part)
    ds = datum_suggestion(part)
    lines = [("h2", "Delik tablosu")]
    for i, h in enumerate(holes[:8]):
        ax = "XYZ"[h["axis"].index(max(h["axis"]))]
        lines.append(("t", f"{chr(65 + i)}  {h['count']}× Ø{h['diameter_mm']:g}  (eksen {ax})"))
    if not holes:
        lines.append(("t", "-"))
    bosses = sorted({round(2 * f.radius_mm, 3) for f in part.faces if f.type == "cylinder" and f.internal is False})
    if bosses:
        lines += [("gap", ""), ("h2", "Dış silindirik yüzler"), ("t", ", ".join(f"Ø{d:g}" for d in bosses[:8]))]
    lines += [("gap", ""), ("h2", "Datum önerisi")]
    for k in ("A", "B", "C"):
        v = ds.get(k)
        if v:
            lines.append(("t", f"{k}: " + (f"Ø{v['diameter_mm']:g} delik(ler)" if v.get("type") == "hole"
                                           else _face_name(v["normal"]))))
    lines += [("gap", ""), ("h2", "Ana ölçüler"), ("t", f"{sx:g} × {sy:g} × {sz:g} mm (X×Y×Z)")]
    out, y = [], ny
    for cls, txt in lines:
        y += 4 if cls == "gap" else 6
        if cls != "gap":
            out.append(f'<text x="290" y="{y:.1f}" class="{cls}">{html.escape(txt)}</text>')
    notes = "".join(out)

    title = title or step.stem
    mass = f"{mass_kg:.4g} kg" if mass_kg else "-"
    tb = f'''
<g class="tb">
 <rect x="250" y="235" width="160" height="52" class="frame"/>
 <line x1="250" y1="248" x2="410" y2="248"/><line x1="250" y1="261" x2="410" y2="261"/>
 <line x1="250" y1="274" x2="410" y2="274"/><line x1="330" y1="235" x2="330" y2="287"/>
 <text x="253" y="244" class="h">{html.escape(title)}</text>
 <text x="333" y="244" class="t">Ölçek {_scale_txt(scale)} · A3 · mm</text>
 <text x="253" y="257" class="t">Malzeme: {html.escape(str(material))}</text>
 <text x="333" y="257" class="t">Kütle: {mass}</text>
 <text x="253" y="270" class="t">Genel tol.: ISO 2768-mK</text>
 <text x="333" y="270" class="t">İzdüşüm: ISO E (birinci açı)</text>
 <text x="253" y="283" class="t">Çizen: {html.escape(drawn_by)} · {date.today():%d.%m.%Y}</text>
 <text x="333" y="283" class="t">TASLAK - imalata uygun değil</text>
</g>'''
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}">
<style>
 text{{font-family:"Segoe UI",Arial,sans-serif;fill:#111}}
 .t{{font-size:3.4px}} .h{{font-size:5px;font-weight:600}} .h2{{font-size:4px;font-weight:600}}
 .lbl{{font-size:3.6px;font-weight:600}} .frame{{fill:none;stroke:#111;stroke-width:0.5}}
 .tb line{{stroke:#111;stroke-width:0.3}} .dim{{stroke:#0a4fa0;stroke-width:0.18;fill:none}}
 .dimt{{font-size:3.2px;fill:#0a4fa0}}
</style>
<rect x="0" y="0" width="{W}" height="{H}" fill="#fff"/>
<rect x="10" y="10" width="{W - 20}" height="{H - 20}" class="frame"/>
{"".join(parts_svg)}
{"".join(dim)}
{iso}<text x="305" y="{20 + iso_h + 5}" class="lbl">İZOMETRİK (ölçeksiz)</text>
{notes}
{tb}
</svg>'''
    out_svg = Path(out_svg)
    out_svg.write_text(svg, encoding="utf-8")
    return out_svg


def _face_name(n):
    names = {(0, 0, -1): "alt yüz (−Z)", (0, 0, 1): "üst yüz (+Z)", (0, -1, 0): "ön yüz (−Y)",
             (0, 1, 0): "arka yüz (+Y)", (-1, 0, 0): "sol yüz (−X)", (1, 0, 0): "sağ yüz (+X)"}
    return names.get(tuple(round(c) for c in n), f"düzlem n={n}")


def _scale_txt(s):
    return f"{int(s)}:1" if s >= 1 else f"1:{round(1 / s):g}"


def _hdim(x1, x2, y, txt):
    return (f'<path class="dim" d="M{x1},{y} L{x2},{y} M{x1},{y - 2} L{x1},{y + 4} M{x2},{y - 2} L{x2},{y + 4}"/>'
            f'<text x="{(x1 + x2) / 2}" y="{y - 1}" class="dimt" text-anchor="middle">{txt}</text>')


def _vdim(x, y1, y2, txt):
    ym = (y1 + y2) / 2
    return (f'<path class="dim" d="M{x},{y1} L{x},{y2} M{x - 2},{y1} L{x + 4},{y1} M{x - 2},{y2} L{x + 4},{y2}"/>'
            f'<text x="{x - 1}" y="{ym}" class="dimt" text-anchor="middle" transform="rotate(-90 {x - 1} {ym})">{txt}</text>')
