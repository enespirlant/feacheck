"""Rapor için satır içi SVG görseller (dış kütüphane/internet gerekmez)."""
from __future__ import annotations

import html
import math
import re

C = {"ink": "#1E2B38", "mute": "#5F6B78", "rule": "#D9E0E7", "blue": "#2D5B88", "red": "#B42318",
     "green": "#2E7D4F", "amber": "#A8650F", "band": "#2D5B88", "paper": "#F6F8FA"}


def tr(v, nd: int = 4) -> str:
    """Türkçe sayı yazımı: ondalık virgül."""
    if v is None:
        return "–"
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, int):
        return f"{v:,}".replace(",", ".")
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return "–"
        if abs(v) >= 10 ** nd:
            return f"{round(v):,}".replace(",", ".")
        return f"{v:.{nd}g}".replace(".", ",")
    return html.escape(str(v))


_NUM = r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?"
_GROUP = re.compile(r"[\[(]\s*(" + _NUM + r"(?:\s*,\s*" + _NUM + r")+)\s*[\])]")


def _num_tr(m: str) -> str:
    v = float(m)
    if "e" in m.lower():
        return tr(v)
    if "." in m:
        dec = len(m.split(".")[1])
        return (f"{v:.{min(dec, 3)}f}".rstrip("0").rstrip(".")).replace(".", ",")
    return m


def tr_text(s: str) -> str:
    """Analiz metinlerindeki Python biçimli sayıları Türkçeye çevirir: [1.25, 0.8333] → (1,25; 0,833),
    3.351 → 3,351. Sayı grupları önce ';' ile ayrılır ki ondalık virgülle karışmasın."""
    s = _GROUP.sub(lambda m: "(" + "; ".join(_num_tr(x.strip()) for x in m.group(1).split(",")) + ")", s)
    return re.sub(r"(?<![\w.])" + _NUM + r"(?![\w.])", lambda m: _num_tr(m.group(0)), s)


def xyz(p) -> str:
    return "(" + "; ".join(tr(float(c), 4) for c in p) + ")" if p else "–"


def _nice_ticks(lo: float, hi: float, n: int = 5) -> list[float]:
    span = hi - lo
    if span <= 0:
        return [lo]
    raw = span / n
    mag = 10 ** math.floor(math.log10(raw))
    step = min((m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw), default=mag * 10)
    t = math.ceil(lo / step) * step
    out = []
    while t <= hi + 1e-9 * step:
        out.append(round(t, 10))
        t += step
    return out


def _svg(w, h, body, label):
    return (f'<svg viewBox="0 0 {w} {h}" width="{w}" role="img" aria-label="{html.escape(label)}" '
            f'class="viz">{"".join(body)}</svg>')


# ------------------------------------------------------------------ yakınsama grafiği
def convergence_chart(levels: list[dict], series: list[dict], extrap: float | None, gci_pct: float | None,
                      unit: str = "MPa", xlabel: str = "eleman boyu h [mm] (sağa doğru incelir)") -> str:
    """x = eleman boyu (log, ters: ince mesh sağda), y = değer.
    series: {"name","values"(seviye sırasıyla, None olabilir),"color","dash"?,"role"?}
    extrap: tasarım serisinin Richardson ekstrapolasyonu (yatay kesik çizgi, h→0 değeri)
    gci_pct: tasarım serisinin en ince değerine bant."""
    hs = [float(lv.get("h_eff_mm") or lv.get("element_size_mm")) for lv in levels]
    if len(hs) < 2:
        return ""
    allv = [v for s in series for v in s["values"] if v is not None]
    if extrap:
        allv.append(extrap)
    if not allv:
        return ""
    lo, hi = min(allv), max(allv)
    pad = (hi - lo) * 0.12 or abs(hi) * 0.05 or 1
    lo, hi = lo - pad, hi + pad
    # Küçük değişimleri büyütüp dramatik göstermemek için eksen en az değerin ±%4'ü kadar geniş
    mid, need = (lo + hi) / 2, 0.08 * max(abs(v) for v in allv)
    if hi - lo < need:
        lo, hi = mid - need / 2, mid + need / 2
    W, H, L, R, T, B = 760, 300, 58, 170, 16, 46
    lx = [math.log(h) for h in hs]
    xa, xb = max(lx), min(lx)                       # kaba solda, ince sağda
    span = (xa - xb) or 1
    xb_ext = xb - span * 0.18                       # h→0 tarafına yer: ekstrapolasyon etiketi

    def X(h):
        return L + (xa - math.log(h)) / (xa - xb_ext) * (W - L - R)

    def Y(v):
        return T + (hi - v) / (hi - lo) * (H - T - B)

    g = []
    for t in _nice_ticks(lo, hi):
        g.append(f'<line x1="{L}" x2="{W - R}" y1="{Y(t):.1f}" y2="{Y(t):.1f}" stroke="{C["rule"]}"/>'
                 f'<text x="{L - 6}" y="{Y(t) + 4:.1f}" text-anchor="end" class="ax">{tr(t)}</text>')
    for h in hs:
        g.append(f'<line x1="{X(h):.1f}" x2="{X(h):.1f}" y1="{H - B}" y2="{H - B + 5}" stroke="{C["mute"]}"/>'
                 f'<text x="{X(h):.1f}" y="{H - B + 18}" text-anchor="middle" class="ax">{tr(h, 3)}</text>')
    g.append(f'<text x="{(L + W - R) / 2:.0f}" y="{H - 8}" text-anchor="middle" class="ax">{html.escape(xlabel)}</text>'
             f'<text x="14" y="{(T + H - B) / 2:.0f}" class="ax" transform="rotate(-90 14 {(T + H - B) / 2:.0f})" '
             f'text-anchor="middle">{html.escape(unit)}</text>')
    design = next((s for s in series if s.get("role") == "design"), None)
    if design and extrap is not None:
        fine = next((v for v in reversed(design["values"]) if v is not None), None)
        g.append(f'<line x1="{X(hs[0]):.1f}" x2="{W - R:.1f}" y1="{Y(extrap):.1f}" y2="{Y(extrap):.1f}" '
                 f'stroke="{design["color"]}" stroke-dasharray="5 4" opacity=".8"/>'
                 f'<text x="{X(hs[0]) + 4:.1f}" y="{Y(extrap) - 6:.1f}" class="ax">'
                 f'h→0 ekstrapolasyonu {tr(extrap)}</text>')
        if fine is not None and gci_pct:
            d = abs(fine) * gci_pct / 100
            y1, y2 = Y(fine + d), Y(fine - d)
            g.append(f'<rect x="{X(hs[-1]) - 7:.1f}" y="{y1:.1f}" width="14" height="{max(2, y2 - y1):.1f}" '
                     f'fill="{C["band"]}" opacity=".22"/>')
    for s in series:
        pts = [(X(h), Y(v)) for h, v in zip(hs, s["values"]) if v is not None]
        if not pts:
            continue
        dash = ' stroke-dasharray="6 4"' if s.get("dash") else ""
        g.append(f'<polyline fill="none" stroke="{s["color"]}" stroke-width="2.4"{dash} points="'
                 + " ".join(f"{a:.1f},{b:.1f}" for a, b in pts) + '"/>')
        g += [f'<circle cx="{a:.1f}" cy="{b:.1f}" r="4" fill="{s["color"]}"/>' for a, b in pts]
        lx_, ly_ = pts[-1]
        g.append(f'<text x="{lx_ + 10:.1f}" y="{ly_ + 4:.1f}" class="lab" fill="{s["color"]}">'
                 f'{html.escape(s["name"])} {tr([v for v in s["values"] if v is not None][-1])}</text>')
    return _svg(W, H, g, "Mesh inceldikçe değerler")


# ------------------------------------------------------------------ büyüme üssü göstergesi
def growth_gauge(q: float | None, steps: list | None) -> str:
    """σ ∝ h^-q. q ≈ 0: değer sabitleniyor; q ≈ 0,45: 90° keskin iç köşe (Williams); q azalıyorsa çözünürlük."""
    if q is None:
        return ""
    W, H, L, R = 760, 96, 20, 20
    qmax = max(1.0, (q or 0) * 1.15, max(steps or [0]) * 1.15)

    def X(v):
        return L + max(0.0, min(v, qmax)) / qmax * (W - L - R)

    # Bölgeler karar mantığıyla aynı: q ≤ 0,1 değer sabitleniyor; q > 0,1 artıyor. Artışın tekillik mi çözülmemiş
    # radyus mu olduğuna q değil, tepenin bulunduğu yüzün tipi karar verir (düz kenar / silindirik radyus).
    g = [f'<rect x="{X(0):.1f}" y="40" width="{X(0.1) - X(0):.1f}" height="14" fill="{C["green"]}" opacity=".25"/>',
         f'<rect x="{X(0.1):.1f}" y="40" width="{X(qmax) - X(0.1):.1f}" height="14" fill="{C["red"]}" opacity=".14"/>',
         f'<text x="{X(0.05):.1f}" y="72" text-anchor="middle" class="ax">sabitleniyor</text>',
         f'<text x="{X((0.1 + 0.455) / 2):.1f}" y="72" text-anchor="middle" class="ax">artıyor: tekillik ya da çözülmemiş radyus</text>',
         f'<line x1="{X(0.455):.1f}" x2="{X(0.455):.1f}" y1="36" y2="58" stroke="{C["ink"]}" stroke-dasharray="3 2"/>',
         f'<text x="{X(0.455):.1f}" y="90" text-anchor="middle" class="ax">0,455: 90° keskin köşe</text>']
    for s in steps or []:
        g.append(f'<circle cx="{X(s):.1f}" cy="47" r="3.5" fill="none" stroke="{C["ink"]}"/>')
    g.append(f'<path d="M{X(q):.1f},36 l-6,-10 h12 z" fill="{C["ink"]}"/>'
             f'<text x="{X(q):.1f}" y="20" text-anchor="middle" class="lab">q = {tr(q, 3)}</text>')
    return _svg(W, H, g, "Gerilme büyüme üssü")


# ------------------------------------------------------------------ konum haritası
def location_map(bcs: list[dict], points: list[dict], excl_mm: float | None) -> str:
    """İki izdüşüm. bcs: sonuç bcs listesi; points: {"name","xyz","color","shape"}."""
    faces = [(b, f) for b in bcs if not b.get("suppressed") for f in b.get("faces", []) if f.get("c")]
    pts = [p for p in points if p.get("xyz")]
    allp = [f["c"] for _, f in faces] + [p["xyz"] for p in pts]
    if len(allp) < 2:
        return ""
    spread = [max(p[i] for p in allp) - min(p[i] for p in allp) for i in range(3)]
    ax = sorted(range(3), key=lambda i: -spread[i])
    views = [(ax[0], ax[1]), (ax[0], ax[2])]
    names = "XYZ"
    out = []
    for a, b in views:
        out.append(_map_view(faces, pts, excl_mm, a, b, names[a], names[b]))
    legend = "".join(f'<span class="lg"><svg width="14" height="14">{_mark(p)}</svg>{html.escape(p["name"])}</span>'
                     for p in pts)
    legend = (f'<span class="lg"><svg width="14" height="14"><rect x="2" y="2" width="10" height="10" fill="none" '
              f'stroke="{C["ink"]}" stroke-width="2"/></svg>mesnet</span>'
              f'<span class="lg"><svg width="14" height="14"><rect x="2" y="2" width="10" height="10" fill="{C["amber"]}"/>'
              f'</svg>yük</span>'
              + (f'<span class="lg"><svg width="14" height="14"><circle cx="7" cy="7" r="5" fill="none" stroke="{C["mute"]}" '
                 f'stroke-dasharray="2 2"/></svg>dışlama bölgesi ({tr(excl_mm, 3)} mm)</span>' if excl_mm else "")
              + legend)
    return f'<div class="maps">{"".join(out)}</div><p class="legend">{legend}</p>'


def _mark(p) -> str:
    if p["shape"] == "sq":
        return f'<rect x="2" y="2" width="10" height="10" fill="{p["color"]}"/>'
    if p["shape"] == "x":
        return f'<path d="M2,2 l10,10 M12,2 l-10,10" stroke="{p["color"]}" stroke-width="2.5"/>'
    return f'<circle cx="7" cy="7" r="5" fill="{p["color"]}"/>'


def _map_view(faces, pts, excl, a, b, na, nb) -> str:
    allp = [f["c"] for _, f in faces] + [p["xyz"] for p in pts]
    xs = [p[a] for p in allp]
    ys = [p[b] for p in allp]
    pad = max(max(xs) - min(xs), max(ys) - min(ys), 1.0) * 0.15 + (excl or 0) * 0.6
    x0, x1 = min(xs) - pad, max(xs) + pad
    y0, y1 = min(ys) - pad, max(ys) + pad
    W, H, M = 300, 260, 28
    s = min((W - 2 * M) / (x1 - x0), (H - 2 * M) / (y1 - y0))
    ox = M + ((W - 2 * M) - (x1 - x0) * s) / 2
    oy = M + ((H - 2 * M) - (y1 - y0) * s) / 2

    def P(p):
        return ox + (p[a] - x0) * s, H - (oy + (p[b] - y0) * s)

    g = [f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" fill="#fff" stroke="{C["rule"]}"/>',
         f'<text x="10" y="18" class="lab">{na}–{nb} görünüşü</text>',
         f'<text x="{W - 10}" y="{H - 8}" text-anchor="end" class="ax">{na} →</text>',
         f'<text x="10" y="{H - 8}" class="ax">↑ {nb}</text>']
    for bc, f in faces:
        cx, cy = P(f["c"])
        side = max(8.0, min(40.0, math.sqrt(f.get("area_mm2") or 0) * s * 0.6))
        is_sup = bc["type"] in ("FixedSupport", "Displacement", "CylindricalSupport", "FrictionlessSupport",
                                "CompressionOnlySupport", "RemoteDisplacement", "ElasticSupport", "SimplySupported",
                                "FixedRotation")
        if excl:
            g.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{excl * s:.1f}" fill="none" stroke="{C["mute"]}" '
                     f'stroke-dasharray="3 3"/>')
        if is_sup:
            g.append(f'<rect x="{cx - side / 2:.1f}" y="{cy - side / 2:.1f}" width="{side:.1f}" height="{side:.1f}" '
                     f'fill="none" stroke="{C["ink"]}" stroke-width="2"/>')
        else:
            g.append(f'<rect x="{cx - side / 2:.1f}" y="{cy - side / 2:.1f}" width="{side:.1f}" height="{side:.1f}" '
                     f'fill="{C["amber"]}" opacity=".85"/>')
        g.append(f'<text x="{cx:.1f}" y="{cy - side / 2 - 4:.1f}" text-anchor="middle" class="ax">'
                 f'{html.escape(bc["name"])}</text>')
    for p in pts:
        cx, cy = P(p["xyz"])
        if p["shape"] == "x":
            g.append(f'<path d="M{cx - 6:.1f},{cy - 6:.1f} l12,12 M{cx + 6:.1f},{cy - 6:.1f} l-12,12" '
                     f'stroke="{p["color"]}" stroke-width="3"/>')
        elif p["shape"] == "sq":
            g.append(f'<rect x="{cx - 5:.1f}" y="{cy - 5:.1f}" width="10" height="10" fill="{p["color"]}"/>')
        else:
            g.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="6" fill="{p["color"]}" stroke="#fff" stroke-width="1.5"/>')
    return _svg(W, H, g, f"{na}-{nb} izdüşümü")


# ------------------------------------------------------------------ çubuk grafikler
def bars(groups: list[tuple[str, list[tuple[str, float, str]]]], unit: str, title: str,
         limit: float | None = None, limit_label: str = "") -> str:
    """Gruplu yatay çubuklar. groups: [(grup adı, [(çubuk adı, değer, renk), ...]), ...]"""
    vals = [abs(v) for _, bs in groups for _, v, _ in bs if v is not None]
    if not vals:
        return ""
    vmax = max(vals + ([limit] if limit else [])) * 1.1 or 1
    nb = sum(len(bs) for _, bs in groups)
    W, L, R, bh = 440, 110, 120, 14
    H = 30 + nb * (bh + 6) + len(groups) * 10 + 24
    g = [f'<text x="0" y="14" class="lab">{html.escape(title)}</text>']
    y = 28

    def X(v):
        return L + abs(v) / vmax * (W - L - R)

    for name, bs in groups:
        g.append(f'<text x="0" y="{y + bh - 3}" class="ax">{html.escape(name)}</text>')
        for bn, v, col in bs:
            if v is None:
                continue
            g.append(f'<rect x="{L}" y="{y}" width="{max(1.0, X(v) - L):.1f}" height="{bh}" fill="{col}"/>'
                     f'<text x="{X(v) + 6:.1f}" y="{y + bh - 3}" class="ax">{html.escape(bn)} {tr(float(v))}</text>')
            y += bh + 6
        y += 10
    if limit:
        g.append(f'<line x1="{X(limit):.1f}" x2="{X(limit):.1f}" y1="24" y2="{y - 6}" stroke="{C["red"]}" '
                 f'stroke-dasharray="4 3"/><text x="{X(limit):.1f}" y="{y + 8}" text-anchor="middle" class="ax">'
                 f'{html.escape(limit_label)}</text>')
    g.append(f'<text x="{W}" y="{y + 8}" text-anchor="end" class="ax">{html.escape(unit)}</text>')
    return _svg(W, y + 14, g, title)
