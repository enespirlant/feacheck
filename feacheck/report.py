"""Yakınsama raporu: tek dosya HTML, satır içi SVG grafikler (internet/eklenti gerekmez)."""
from __future__ import annotations

import html
from pathlib import Path

from . import __version__
from .report_viz import bars, convergence_chart, growth_gauge, location_map, tr, tr_text, xyz

PALETTE = {"ok": "#2E7D4F", "warn": "#A8650F", "bad": "#B42318", "ink": "#1E2B38", "mute": "#5F6B78",
           "line1": "#2D5B88", "line2": "#B42318", "line3": "#2E7D4F", "grid": "#D9E0E7", "paper": "#F6F8FA",
           "blue": "#2D5B88"}


def _chart(series: list[tuple[str, list[float], str]], xs: list[int], unit: str, title: str) -> str:
    """Basit çizgi grafik: x = düğüm sayısı (log), y = değer."""
    import math
    nser = sum(1 for _, vals, _ in series if any(v is not None for v in vals))
    W, R, B, L = 560, 20, 40, 60
    T = 30 + 15 * nser
    H = 230 + 15 * nser
    allv = [v for _, vals, _ in series for v in vals if v is not None]
    if not allv or len(xs) < 2:
        return ""
    lo, hi = min(allv), max(allv)
    pad = (hi - lo) * 0.15 or abs(hi) * 0.05 or 1
    lo, hi = lo - pad, hi + pad
    lx = [math.log10(x) for x in xs]
    x0, x1 = min(lx), max(lx)

    def X(v):
        return L + (math.log10(v) - x0) / ((x1 - x0) or 1) * (W - L - R)

    def Y(v):
        return T + (hi - v) / (hi - lo) * (H - T - B)

    g = [f'<text x="{L}" y="18" class="ct">{html.escape(title)}</text>']
    for i in range(5):
        v = lo + (hi - lo) * i / 4
        g.append(f'<line x1="{L}" x2="{W - R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="{PALETTE["grid"]}"/>'
                 f'<text x="{L - 6}" y="{Y(v) + 4:.1f}" text-anchor="end" class="ax">{v:.4g}</text>')
    for x in xs:
        g.append(f'<text x="{X(x):.1f}" y="{H - B + 16}" text-anchor="middle" class="ax">{x:,}</text>')
    g.append(f'<text x="{(L + W - R) / 2}" y="{H - 6}" text-anchor="middle" class="ax">düğüm sayısı (log)</text>'
             f'<text x="14" y="{(T + H - B) / 2}" class="ax" transform="rotate(-90 14 {(T + H - B) / 2})" '
             f'text-anchor="middle">{html.escape(unit)}</text>')
    leg = 0
    for k, (name, vals, color) in enumerate(series):
        pts = [(X(x), Y(v)) for x, v in zip(xs, vals) if v is not None]
        if not pts:
            continue
        g.append(f'<polyline fill="none" stroke="{color}" stroke-width="2" points="'
                 + " ".join(f"{a:.1f},{b:.1f}" for a, b in pts) + '"/>')
        g += [f'<circle cx="{a:.1f}" cy="{b:.1f}" r="3.5" fill="{color}"/>' for a, b in pts]
        ly = 26 + 15 * leg
        leg += 1
        g.append(f'<rect x="{L}" y="{ly}" width="10" height="10" fill="{color}"/>'
                 f'<text x="{L + 15}" y="{ly + 9}" class="ax">{html.escape(name)}</text>')
    return f'<svg viewBox="0 0 {W} {H}" width="100%" role="img">{"".join(g)}</svg>'


SRC = {"max_von_mises": "maksimum von Mises",
       "von_mises_outside_zone": "tekillik bölgesi dışındaki maksimum",
       "von_mises_probe": "tekillik bölgesi dışında sabit noktada okuma (probe)",
       "von_mises_away_from_peak": "tekil köşe hariç en yüksek gerilme",
       "radius_peak": "radyustaki tepe gerilme (radyus yüzüne yerel sıklaştırma ile)"}


def _fmt(v, nd=4):
    if v is None:
        return "–"
    if isinstance(v, float):
        return f"{v:.{nd}g}"
    return str(v)


def _verdict(result: dict) -> tuple[str, str, str]:
    """(durum, kısa hüküm, açıklama cümlesi)"""
    sing = result.get("singularity", {})
    ds = result.get("design_stress")
    v = f"{tr(ds['value_mpa'])} MPa" if ds else ""
    if result.get("errors"):
        return "bad", "Analiz tamamlanamadı", "Aşağıdaki hataları düzeltip tekrar çalıştır."
    if sing.get("resolved_radius") and ds and ds.get("confidence") == "düşük":
        return "warn", "Radyus çözüldü, belirsizlik geniş", (
            f"Radyustaki tepe gerçek bir gerilme yığılması ve yakınsıyor (ince mesh {tr(ds['fine_mesh_mpa'])} MPa), "
            f"ama yakınsama zayıf doğrulandı (belirsizlik %{tr(ds.get('gci_pct'), 2)}). Tasarımda ihtiyatlı {v} kullan.")
    if sing.get("resolved_radius") and ds and ds.get("verdict", "").startswith("güvenilir"):
        return "ok", "Güvenilir: radyus yerel sıklaştırmayla çözüldü", (
            f"Radyustaki tepe gerçek bir gerilme yığılması ve yakınsadı. Tasarımda {v} kullan.")
    if sing.get("kind") == "çözülmemiş radyus" and result.get("radius_series", {}).get("quantity"):
        ind = result.get("indicative_stress") or {}
        return "warn", "Radyus yerel sıklaştırmaya rağmen yakınsamadı", (
            f"Radyustaki tepe her incelmede artmaya devam ediyor; son değer {tr(ind.get('value_mpa'))} MPa bir alt "
            "sınırdır. Bu haliyle bir tasarım değeri verilemez; bulgulardaki öneriye bak ve el hesabıyla karşılaştır.")
    if sing.get("kind") == "çözülmemiş radyus":
        return "warn", "Çözünürlük yetersiz: radyusu sıklaştır", (
            "Kritik nokta bir radyusta ve mesh orayı henüz çözemedi. Bu haliyle bir tasarım değeri verilemez.")
    if sing.get("kind") == "geometrik" and ds:
        return "warn", "Keskin köşe: köşe hariç güvenilir", (
            f"Köşedeki tepe sahte; mesh inceldikçe sonsuza gider. Parçanın geri kalanı için {v} kullan; "
            "köşenin kendisini gerçek radyusuyla modelleyip ayrıca kontrol et.")
    if sing.get("detected") and ds:
        return "warn", "Tekillik ayrıldı", (
            f"Mesnet/yük kenarındaki tepe sahte ve analizden dışlandı. Tasarımda {v} kullan.")
    if sing.get("kind") == "geometrik":
        return "warn", "Geometrik tekillik", "Keskin köşedeki tepe sahte ve köşe dışında güvenilir bir değer bulunamadı."
    if ds and ds.get("verdict", "").startswith("güvenilir"):
        return "ok", "Güvenilir", f"Sonuç mesh inceldikçe yakınsadı. Tasarımda {v} kullan."
    return "warn", "Şüpheli", "Sonuç yakınsamadı; bu haliyle güvenme. Aşağıdaki yapılacaklara bak."


_SETUP_KEYS = ("Fixed Support", "Mesnetler", "LINEAR", "kalınlık", "Eleman derecesi", "aşırı kısıtlanmış",
               "Bağlantı:")


def _scale(result: dict) -> str:
    """Gerilme cetveli: reddedilen ham tepe, tasarım (ya da gösterge) değeri, el hesabı ve akma aynı eksende."""
    ds = result.get("design_stress")
    ind = result.get("indicative_stress")
    hc = result.get("hand_calc")
    q = result.get("quantities", {})
    raw = (q.get("max_von_mises", {}).get("values") or [None])[-1]
    y = result.get("settings", {}).get("yield_mpa")
    if ds:
        val, fine, col, lab = ds["value_mpa"], ds["fine_mesh_mpa"], PALETTE["blue"], "tasarım"
    elif ind:
        val, fine, col, lab = ind["value_mpa"], ind["value_mpa"], PALETTE["mute"], "gösterge (alt sınır)"
    else:
        return ""
    src = (ds or ind).get("source")
    rejected = raw is not None and raw > val * 1.03 and src != "max_von_mises" and bool(ds)
    cands = [val, raw if rejected else None, y]
    if hc:
        cands += [hc.get("high"), hc.get("ref")]
    top = max(x for x in cands if x) * 1.12
    W, L, R = 860, 8, 8

    def X(v):
        return L + v / top * (W - L - R)

    g = []
    if hc and hc["kind"] == "range":
        g.append(f'<rect x="{X(hc["low"]):.1f}" y="44" width="{X(hc["high"]) - X(hc["low"]):.1f}" height="32" '
                 f'fill="{PALETTE["ok"]}" opacity=".14"/><text x="{X((hc["low"] + hc["high"]) / 2):.1f}" y="104" '
                 f'text-anchor="middle" class="tick">el hesabı aralığı {tr(hc["low"])}–{tr(hc["high"])}</text>')
    elif hc:
        g.append(f'<line x1="{X(hc["ref"]):.1f}" x2="{X(hc["ref"]):.1f}" y1="44" y2="76" stroke="{PALETTE["ok"]}" '
                 f'stroke-width="2"/><text x="{X(hc["ref"]):.1f}" y="104" text-anchor="middle" class="tick">'
                 f'el hesabı {tr(hc["ref"])}</text>')
    g.append(f'<line x1="{L}" x2="{W - R}" y1="60" y2="60" stroke="{PALETTE["ink"]}" stroke-width="1.5"/>')
    step = 10 ** max(0, len(str(int(top))) - 1)
    step = step if top / step >= 4 else step / 2
    k = 0.0
    while k <= top:
        g.append(f'<line x1="{X(k):.1f}" x2="{X(k):.1f}" y1="60" y2="66" stroke="{PALETTE["ink"]}"/>'
                 f'<text x="{X(k):.1f}" y="82" text-anchor="middle" class="tick">{tr(float(k))}</text>')
        k += step
    g.append(f'<text x="{W - R}" y="82" text-anchor="end" class="tick">MPa</text>')
    if ds:   # GCI bandı
        g.append(f'<rect x="{X(min(fine, val)):.1f}" y="48" width="{max(2.0, X(max(fine, val)) - X(min(fine, val))):.1f}" '
                 f'height="24" fill="{PALETTE["blue"]}" opacity=".18"/>')
    dash = '' if ds else ' stroke-dasharray="5 3"'
    g.append(f'<line x1="{X(val):.1f}" x2="{X(val):.1f}" y1="30" y2="72" stroke="{col}" stroke-width="3"{dash}/>'
             f'<text x="{X(val):.1f}" y="22" text-anchor="middle" class="mk" fill="{col}">{lab} {tr(val)}</text>')
    if y:
        g.append(f'<line x1="{X(y):.1f}" x2="{X(y):.1f}" y1="30" y2="72" stroke="{PALETTE["ink"]}" stroke-width="2" '
                 f'stroke-dasharray="4 3"/><text x="{X(y):.1f}" y="22" text-anchor="middle" class="mk">akma {tr(float(y))}</text>')
    if rejected:
        g.append(f'<line x1="{X(raw):.1f}" x2="{X(raw):.1f}" y1="40" y2="72" stroke="{PALETTE["bad"]}" stroke-width="2"/>'
                 f'<text x="{X(raw):.1f}" y="{122 if hc else 104}" text-anchor="middle" class="mk rej" fill="{PALETTE["bad"]}">'
                 f'ham tepe {tr(raw)}</text><text x="{X(raw):.1f}" y="{138 if hc else 120}" text-anchor="middle" class="tick">'
                 'sahte, dışlandı</text>')
    h = (146 if hc else 128) if rejected else (112 if hc else 92)
    return f'<svg viewBox="0 0 {W} {h}" width="100%" role="img" aria-label="Gerilme cetveli">{"".join(g)}</svg>'


_LEVEL_OF = {"max_von_mises": lambda lv: lv.get("max_vm"),
             "von_mises_outside_zone": lambda lv: (lv.get("max_outside_zone") or {}).get("value"),
             "von_mises_probe": lambda lv: (lv.get("probe") or {}).get("value"),
             "von_mises_away_from_peak": lambda lv: (lv.get("max_away_from_peak") or {}).get("value")}
_SHORT = {"max_von_mises": "ham tepe", "von_mises_outside_zone": "bölge dışı maks.",
          "von_mises_probe": "sabit nokta", "von_mises_away_from_peak": "tepe dışı maks.",
          "radius_peak": "radyus tepesi"}
_QLABEL = [("max_deformation", "Maks. deformasyon [mm]"), ("max_von_mises", "Maks. von Mises (ham tepe) [MPa]"),
           ("von_mises_outside_zone", "Dışlama bölgesi dışındaki maks. [MPa]"),
           ("von_mises_probe", "Sabit noktada (probe) [MPa]"), ("von_mises_away_from_peak", "Tepe dışı maks. [MPa]"),
           ("radius_peak", "Radyus tepesi, yerel seri [MPa]")]
_STATUS = {"converging": "monoton yakınsıyor", "oscillatory": "salınarak yakınsıyor", "diverging": "ıraksıyor",
           "exact": "değişmiyor", "invalid": "hesaplanamadı"}


def _gci_steps(qd: dict, hs: list[float]) -> str:
    """Tasarım büyüklüğü için GCI hesabını gerçek sayılarla adım adım gösterir."""
    vals = qd.get("values") or []
    g = qd.get("gci") or {}
    if len(vals) < 3 or not g:
        return ""
    f1, f2, f3 = vals[-1], vals[-2], vals[-3]
    h1, h2, h3 = hs[-1], hs[-2], hs[-3]
    rows = [("Üç çözüm (ince → kaba)", f"f₁ = {tr(f1)}, f₂ = {tr(f2)}, f₃ = {tr(f3)}"),
            ("Eleman boyları", f"h₁ = {tr(h1, 3)}, h₂ = {tr(h2, 3)}, h₃ = {tr(h3, 3)} mm"),
            ("İncelme oranları", f"r₂₁ = {tr(g.get('r21'), 3)}, r₃₂ = {tr(g.get('r32'), 3)}"),
            ("Değişimler", f"ε₂₁ = f₂ − f₁ = {tr(f2 - f1)}, ε₃₂ = f₃ − f₂ = {tr(f3 - f2)}"),
            ("Durum", _STATUS.get(g.get("status"), g.get("status") or "–")
             + (f" (adımlar gürültü düzeyinde)" if g.get("small_change") else "")),
            ("Görünen mertebe p", f"{tr(g.get('p'), 3)}"
             + (f" (ham {tr(g.get('p_raw'), 3)}, [0,5; 4] aralığına kırpıldı)" if g.get("p_raw") not in (None, g.get("p")) else "")),
            ("Richardson ekstrapolasyonu", f"f(h→0) ≈ {tr(g.get('extrapolated'))}"),
            ("Güvenlik çarpanı Fs", f"{tr(g.get('fs'), 3)}"),
            ("Ekstrapolasyona göre bağıl hata e_ext", f"%{tr(g.get('ext_rel_error_pct'), 3)}"),
            ("GCI = Fs·|ε/f₁| / (rᵖ − 1)", f"%{tr(g.get('gci_fine_pct'), 3)}")]
    note = f"<p class='sub'>{html.escape(tr_text(g['note']))}</p>" if g.get("note") else ""
    return ("<table class='steps'>" + "".join(f"<tr><td>{a}</td><td>{b}</td></tr>" for a, b in rows)
            + "</table>" + note)


def _handcalc_section(hc: dict | None) -> str:
    if not hc:
        return ""
    ref = (f"{tr(hc['low'])}–{tr(hc['high'])} MPa aralığı" if hc["kind"] == "range" else
           f"{tr(hc['ref'])} MPa (fark %{tr(hc['diff_pct'], 3)})")
    verdict = ("tutarlı" if hc["ok"] else "UYUŞMUYOR")
    why = ("Aralık iki bağımsız el hesabıyla çizilir: biri gerçek durumdan daha yumuşak, diğeri daha rijit "
           "bir idealleştirme. Doğru çözüm ikisinin arasında olmalı. " if hc["kind"] == "range" else "")
    return (f"<h2 id='elhesap'>El hesabıyla karşılaştırma</h2>"
            f"<p>FEA ({html.escape(hc['fea_kind'])}) <b>{tr(hc['fea_mpa'])} MPa</b>, el hesabı {ref}: <b>{verdict}</b>.</p>"
            + (f"<p class='sub'>{html.escape(str(hc['note']))}</p>" if hc.get("note") else "")
            + f"<p class='sub'>{why}Karşılaştırma girişi: elhesap.yaml › {html.escape(hc['key'])}. Hesap formülleri "
            "ve kaynakları feacheck/handcalc.py içinde.</p>")


def write(result: dict, out_html: Path) -> Path:
    q = result.get("quantities", {})
    all_levels = result.get("levels", [])
    levels = [lv for lv in all_levels if "max_vm" in lv]
    sing = result.get("singularity", {})
    ds = result.get("design_stress")
    st = result.get("settings", {})
    state, headline, sentence = _verdict(result)
    color = PALETTE[state]
    src = ds["source"] if ds else None

    # ---------------- kontrol listesi (her satırda ne anlama geldiği)
    checks = []
    if ds:
        checks.append(("ok" if ds.get("verdict", "").startswith("güvenilir") else "warn", "Mesh yakınsaması",
                       f"İnce mesh {tr(ds['fine_mesh_mpa'])} MPa, sayısal belirsizlik %{tr(ds.get('gci_pct'), 2)} (GCI), "
                       f"güven {ds.get('confidence', '–')}.",
                       "Mesh inceldikçe değer sabitlendi mi? GCI, sonucun mesh'e bağlı hata payıdır."))
    else:
        checks.append(("bad", "Mesh yakınsaması", "Güvenilir bir değer yakınsamadı.",
                       "Mesh inceldikçe hiçbir aday değer sabitlenmedi."))
    kind = sing.get("kind")
    if sing.get("resolved_radius"):
        checks.append(("ok", "Tekillik", "Yok. Radyustaki tepe gerçek bir gerilme yığılması.",
                       "Sonsuza giden sahte bir tepe var mı?"))
    elif kind == "çözülmemiş radyus":
        checks.append(("warn", "Tekillik", "Yok, ama radyus henüz çözülmedi.", "Sonsuza giden sahte bir tepe var mı?"))
    elif sing.get("detected") or kind == "geometrik":
        checks.append(("warn", "Tekillik", f"Var ({kind or 'tespit edildi'}). Tepe değer tasarımdan dışlandı.",
                       "Sonsuza giden sahte bir tepe var mı?"))
    else:
        checks.append(("ok", "Tekillik", "Yok.", "Sonsuza giden sahte bir tepe var mı?"))
    eq = result.get("equilibrium")
    if eq and not eq.get("skipped") and eq.get("error_pct") is not None:
        checks.append(("ok" if eq.get("ok") else "bad", "Kuvvet dengesi", f"Tepki ile yük farkı %{tr(eq['error_pct'], 3)}.",
                       "Mesnetler uygulanan yükü karşılıyor mu?"))
    lv = levels[-1] if levels else {}
    if lv.get("quality_min") is not None:
        good = (lv.get("quality_min", 1) > 0.1 and (lv.get("quality_avg") or 1) > 0.7
                and (lv.get("skewness_max") or 0) < 0.9 and (lv.get("aspect_max") or 0) < 20)
        checks.append(("ok" if good else "warn", "Mesh kalitesi",
                       f"Kalite min {tr(lv.get('quality_min'), 2)}, skewness maks {tr(lv.get('skewness_max'), 2)}, "
                       f"aspect maks {tr(lv.get('aspect_max'), 3)}.", "Bozuk eleman var mı? (Ansys kabul sınırları)"))
    setup = [f for f in result.get("findings", []) if any(k in f for k in _SETUP_KEYS)]
    checks.append(("warn" if setup else "ok", "Model kurulumu",
                   f"{len(setup)} uyarı (bulgulara bak)." if setup else "Uyarı yok.",
                   "Mesnet tipi, aşırı kısıtlama, eleman derecesi, kalınlık boyunca eleman sayısı."))
    if ds and ds.get("safety_factor"):
        sf = ds["safety_factor"]
        checks.append(("ok" if sf >= 1.5 else "warn" if sf >= 1 else "bad", "Emniyet katsayısı",
                       f"{tr(float(sf), 3)} (akma {tr(st.get('yield_mpa'))} MPa, "
                       f"{html.escape(result.get('yield_source', '') or '–')}).",
                       "Akma / tasarım gerilmesi. 1,5 altı sarı, 1 altı kırmızı."))
    hc = result.get("hand_calc")
    if hc:
        checks.append(("ok" if hc["ok"] else "bad", "El hesabı", html.escape(hc["text"]) + ".",
                       "FEA, bağımsız bir kapalı form çözümle tutarlı mı? (elhesap.yaml)"))
    vl = result.get("vehicle_load")
    if vl:
        checks.append(("bad" if not vl["ok"] else "warn" if vl["durum"] != "uygun" else "ok", "Araç yükü",
                       html.escape(vl["text"]) + ".",
                       "Modeldeki kuvvet, arac.yaml'dan hesaplanan teker yüküyle tutarlı mı? "
                       + vl["formula"] + f" (k_dyn {tr(vl['varsayimlar']['k_dyn'])}, "
                       f"μ {tr(vl['varsayimlar']['mu'])}, μy {tr(vl['varsayimlar']['mu_lat'])} varsayım)."))
    icon = {"ok": "✓", "warn": "!", "bad": "✕"}
    checks_html = "".join(f'<li class="c {s_}"><span class="ic" aria-hidden="true">{icon[s_]}</span>'
                          f'<span class="cn">{html.escape(n)}</span><span class="cv">{v}'
                          f'<span class="why">{html.escape(w)}</span></span></li>'
                          for s_, n, v, w in checks)

    # ---------------- bulgular
    other = [f for f in result.get("findings", []) if f not in setup]
    todo = "".join(f"<li>{html.escape(tr_text(f))}</li>" for f in setup + other)
    if sing.get("why") and (sing.get("resolved_radius") or sing.get("unresolved") or sing.get("detected")):
        todo = f"<li>{html.escape(tr_text(sing['why']))}</li>" + todo
    errs = "".join(f"<li class='e'>{html.escape(tr_text(e))}</li>" for e in result.get("errors", []))
    warns = "".join(f"<li>{html.escape(tr_text(w))}</li>" for w in result.get("warnings", []))

    # ---------------- ana sayı
    ind = result.get("indicative_stress")
    if ds:
        number = (f'<p class="num">{tr(ds["value_mpa"])}<span>MPa</span></p>'
                  f'<p class="cap">İhtiyatlı tasarım gerilmesi; emniyet katsayısı bununla hesaplanır. '
                  f'Kaynak: {SRC.get(src, src)}' + (f', konum {xyz(ds["location_mm"])} mm' if ds.get("location_mm") else "")
                  + ".</p>")
    elif ind:
        number = (f'<p class="num muted">{tr(ind["value_mpa"])}<span>MPa</span></p>'
                  f'<p class="cap">Yalnızca gösterge değer, tasarımda kullanma. {html.escape(tr_text(ind["note"]))}</p>')
    else:
        number = ""
    raw_peak = (q.get("max_von_mises", {}).get("values") or [None])[-1]
    facts = [("Ham tepe gerilme", f"{tr(raw_peak)} MPa" if raw_peak is not None else "–"),
             ("Tasarım gerilmesi", f"{tr(ds['value_mpa'])} MPa" if ds else "–"),
             ("Sayısal belirsizlik", f"%{tr(ds.get('gci_pct'), 2)}" if ds else "–"),
             ("Maks. deformasyon", f"{tr((q.get('max_deformation', {}).get('values') or [None])[-1])} mm"),
             ("En ince mesh", f"{tr(int(lv.get('nodes', 0)))} düğüm, h = {tr(lv.get('element_size_mm'), 3)} mm" if lv else "–"),
             ("Toplam süre", f"{tr(float(result.get('duration_s', 0) or 0), 3)} s")]
    facts_html = "<dl class='facts'>" + "".join(f"<div><dt>{a}</dt><dd>{b}</dd></div>" for a, b in facts) + "</dl>"

    # ---------------- sahte mi gerçek mi: yakınsama grafiği
    series = [{"name": "ham tepe", "values": [lv_.get("max_vm") for lv_ in levels], "color": PALETTE["bad"],
               "role": "peak"}]
    if src in _LEVEL_OF and src != "max_von_mises":
        series.append({"name": _SHORT[src], "values": [_LEVEL_OF[src](lv_) for lv_ in levels],
                       "color": PALETTE["blue"], "role": "design"})
    elif src == "max_von_mises":
        series[0].update({"role": "design", "color": PALETTE["blue"]})
    dq = q.get(src, {}) if src else {}
    conv = convergence_chart(levels, series, (dq.get("gci") or {}).get("extrapolated") if src != "radius_peak" else None,
                             (dq.get("gci") or {}).get("gci_fine_pct") if src != "radius_peak" else None) if levels else ""
    gauge = growth_gauge(result.get("vm_growth_exponent"), result.get("vm_growth_steps"))
    conv_text = ("Kırmızı çizgi modelin en yüksek gerilmesi (ham tepe), mavi çizgi tasarım değerinin alındığı büyüklük. "
                 "Gerçek bir gerilme mesh inceldikçe yataylaşır ve kesik çizgiyle gösterilen h→0 değerine yaklaşır; "
                 "tekil (sahte) bir tepe her incelmede yükselmeye devam eder.")
    gauge_text = ("Gerilmenin mesh ile büyüme hızı: σ ∝ h^−q. q ≤ 0,1 ise değer sabitleniyor. Daha büyükse tepe artıyor; "
                  "bunun sonsuza giden bir tekillik mi yoksa henüz çözülmemiş bir radyus mu olduğuna tepenin bulunduğu yüz "
                  "karar verir: keskin düz kenar tekilliktir (90° iç köşede q ≈ 0,455), silindirik radyus ise yerel "
                  "sıklaştırmayla çözülür. Halkalar adım adım ölçülen q değerleri; tekillikte sabit kalır, radyusta azalır.")

    # ---------------- konum haritası
    pts = []
    mloc = (lv.get("max_location") or {}).get("xyz_mm") if lv else None
    if mloc:
        pts.append({"name": "ham tepe" + (" (sahte)" if sing.get("detected") else ""), "xyz": mloc,
                    "color": PALETTE["bad"], "shape": "x"})
    if ds and ds.get("location_mm") and ds.get("location_mm") != mloc:
        pts.append({"name": "tasarım noktası", "xyz": ds["location_mm"], "color": PALETTE["blue"], "shape": "o"})
    elif ds and ds.get("location_mm"):
        pts[-1]["name"] = "tepe = tasarım noktası"
        pts[-1]["color"] = PALETTE["blue"]
        pts[-1]["shape"] = "o"
    if result.get("probe_xyz_mm") and src == "von_mises_probe":
        pts.append({"name": "sabit nokta (probe)", "xyz": result["probe_xyz_mm"], "color": PALETTE["ok"], "shape": "sq"})
    lmap = location_map(result.get("bcs", []), pts, st.get("exclusion_mm"))

    # ---------------- GCI tablosu
    hs = [float(x.get("h_eff_mm") or x.get("element_size_mm")) for x in levels]
    qrows = ""
    for key, label in _QLABEL:
        d = q.get(key)
        if not d:
            continue
        g = d.get("gci", {})
        mark = " class='hl'" if key == src else ""
        qrows += (f"<tr{mark}><td>{label}</td><td>{' → '.join(tr(v) for v in d.get('values', []))}</td>"
                  f"<td>{tr(g.get('extrapolated'))}</td><td>{tr(g.get('p'), 3)}</td>"
                  f"<td>{tr(g.get('gci_fine_pct'), 3)}</td><td>{html.escape(d.get('verdict', '–'))}</td></tr>")
    rs = result.get("radius_series")
    steps_html = _gci_steps(dq, [float(x["element_size_mm"]) for x in (rs or {}).get("levels", []) if "max_vm" in x]
                            if src == "radius_peak" else hs) if dq else ""

    # ---------------- radyus serisi
    rs_html = ""
    if rs:
        rl = [x for x in rs.get("levels", []) if "max_vm" in x]
        rq = rs.get("quantity") or {}
        g = rq.get("gci", {})
        rchart = convergence_chart(rl, [{"name": "radyus tepesi", "values": [x["max_vm"] for x in rl],
                                         "color": PALETTE["blue"], "role": "design"}],
                                   None, g.get("gci_fine_pct"),
                                   xlabel="radyus yüzündeki yerel eleman boyu [mm] (sağa doğru incelir)") if len(rl) >= 2 else ""
        rrows = "".join(
            f"<tr><td>{tr(x.get('element_size_mm'), 3)}</td><td>{tr(x.get('elements_on_arc'), 3)}</td>"
            f"<td>{tr(int(x.get('nodes', 0)))}</td><td>{tr(x.get('max_vm'))}</td>"
            f"<td>{'evet' if x.get('on_target', True) else 'HAYIR'}</td>"
            f"<td>{html.escape(x.get('skipped', x.get('state', '')))}</td></tr>" for x in rs.get("levels", []))
        rs_html = (f"<h2>Radyus yerel sıklaştırma</h2><p class='sub'>Global mesh radyusu çözemediği için yalnızca "
                   f"{tr(rs.get('radius_mm'), 3)} mm yarıçaplı yüz inceltildi (global eleman boyu {tr(rs.get('global_size_mm'), 3)} mm "
                   f"sabit{(', hacim büyüme oranı ' + tr(rs['growth_rate'], 3) + ' (adaptive sizing kapalı)') if rs.get('growth_rate') and rs.get('adaptive_sizing') == 'False' else (', hacim büyüme oranı etkin değil: adaptive sizing açık' if rs.get('growth_rate') else '')}). Radyus boyunca eleman sayısı arttıkça tepe değerin yataylaşması beklenir. Karar: "
                   f"{html.escape(rq.get('verdict', '–'))}, GCI %{tr(g.get('gci_fine_pct'), 3)}. Yalnız bir bölge inceldiği için "
                   "GCI burada tahminidir."
                   + (" Değişim gürültü düzeyinde ama yönü belirsiz olduğu için bir seviye daha çözüldü; "
                      "GCI son üç seviyeden." if rs.get("extra_level") else "") + "</p>" + rchart +
                   "<div class='scroll'><table><tr><th>Yerel h [mm]</th><th>Radyusta eleman</th><th>Düğüm</th>"
                   f"<th>vM maks [MPa]</th><th>Tepe radyusta</th><th>Durum</th></tr>{rrows}</table></div>")

    # ---------------- denge
    eq_vis, eq_txt = "", ""
    if not eq:
        eq_txt = "<p class='sub'>Kuvvet tanımlı değil veya okunamadı.</p>"
    elif eq.get("skipped"):
        eq_txt = f"<p class='sub'>{html.escape(eq['note'])} Toplam tepki {xyz(eq['reaction_n'])} N.</p>"
    elif eq.get("applied_n") is None:
        eq_vis = bars([("Büyüklük", [("uygulanan", eq["applied_mag_n"], PALETTE["warn"]),
                                     ("tepki", eq["reaction_mag_n"], PALETTE["ink"])])], "N", "Kuvvet dengesi")
        eq_txt = f"<p class='sub'>Fark %{tr(eq['error_pct'], 3)}. {html.escape(eq['note'])}</p>"
    else:
        big = max([abs(v) for v in list(eq["applied_n"]) + list(eq["reaction_n"])] + [1e-30])
        eq_vis = bars([(ax, [("uygulanan", a, PALETTE["warn"]), ("tepki", r, PALETTE["ink"])])
                       for ax, a, r in zip("XYZ", eq["applied_n"], eq["reaction_n"])
                       if max(abs(a), abs(r)) > 1e-3 * big],
                      "N", "Uygulanan kuvvet ve toplam tepki")
        eq_txt = (f"<p class='sub'>Çubuk uzunluğu büyüklüğü gösterir; dengede tepki, yükle aynı büyüklükte ve ters "
                  f"işaretli olmalı. Sıfır olan eksenler gösterilmedi. Fark %{tr(eq['error_pct'], 3)}.</p>")
    sr = result.get("support_reactions")
    if sr and len(sr["supports"]) >= 2:
        eq_vis += bars([(x["name"], [("|R|", x["mag_n"], PALETTE["ink"])]) for x in sr["supports"]], "N",
                       "Mesnet başına tepki")
        eq_txt += (f"<p class='sub'>İç kuvvet oranı Σ|R|/|ΣR| = {tr(sr.get('internal_force_ratio'), 3)}. 1 ise mesnetler "
                   "birbirini zorlamıyor; 3'ün üstünde aşırı kısıtlama uyarısı verilir.</p>")

    # ---------------- mesh
    mesh_vis = bars([(f"h = {tr(x.get('element_size_mm'), 3)} mm", [("düğüm", float(x.get("nodes", 0)), PALETTE["blue"])])
                     for x in all_levels], "düğüm", "Mesh seviyeleri ve düğüm sayısı",
                    limit=float(st.get("max_nodes") or 0) or None, limit_label="düğüm limiti")
    rows = "".join(
        f"<tr><td>{tr(x.get('element_size_mm'), 3)}</td><td>{tr(int(x.get('nodes', 0)))}</td>"
        f"<td>{tr(x.get('quality_min'), 3)} / {tr(x.get('quality_avg'), 3)}</td>"
        f"<td>{tr(x.get('skewness_max'), 3)}</td><td>{tr(x.get('aspect_max'), 3)}</td>"
        f"<td>{tr(x.get('max_vm'))}</td><td>{tr((x.get('max_outside_zone') or {}).get('value'))}</td>"
        f"<td>{tr((x.get('probe') or {}).get('value'))}</td>"
        f"<td>{tr(x.get('max_def'))}</td><td>{html.escape(x.get('skipped', x.get('state', '')))}</td></tr>"
        for x in all_levels)
    defo = q.get("max_deformation", {})
    dchart = convergence_chart(levels, [{"name": "maks. deformasyon", "values": [x.get("max_def") for x in levels],
                                         "color": PALETTE["ok"], "role": "design"}],
                               (defo.get("gci") or {}).get("extrapolated"), (defo.get("gci") or {}).get("gci_fine_pct"),
                               unit="mm") if levels else ""

    # ---------------- sınır şartları, karar izi, ayarlar
    bc_rows = ""
    for b in result.get("bcs", []):
        if b.get("suppressed"):
            continue
        locs = "<br>".join(xyz(fc["c"]) + (f", {tr(float(fc['area_mm2']), 4)} mm²" if fc.get('area_mm2') else "")
                           for fc in b["faces"]) or "–"
        bc_rows += f"<tr><td>{html.escape(b['name'])}</td><td>{html.escape(b['type'])}</td><td>{len(b['faces'])}</td><td>{locs}</td></tr>"
    bc_html = ("<div class='scroll'><table><tr><th>Nesne</th><th>Tür</th><th>Yüz</th><th>Yüz merkezi [mm], alan</th></tr>"
               + bc_rows + "</table></div>") if bc_rows else "<p class='sub'>Yüz konumları okunamadı.</p>"
    con = result.get("connections")
    con_html = ""
    if con and (con.get("contacts") or con.get("joints") or con.get("beams") or (con.get("bodies") or 1) > 1):
        rows_c = ""
        for kind, lab in (("contacts", "Temas"), ("joints", "Mafsal"), ("beams", "Kiriş bağlantısı")):
            for c in con.get(kind, []):
                typ = c.get("contact_type") or c.get("joint_type") or c.get("connection_type") or "–"
                fs = (c.get("source") or []) + (c.get("target") or [])
                rows_c += (f"<tr><td>{html.escape(c['name'])}</td><td>{lab}</td>"
                           f"<td>{html.escape(str(typ).split('.')[-1])}</td><td>{len(c.get('source') or [])} / "
                           f"{len(c.get('target') or [])}</td><td>{'<br>'.join(xyz(f['c']) for f in fs[:4]) or '–'}</td></tr>")
        near = con.get("peak_near_contact")
        con_html = (f"<h3>Montaj bağlantıları</h3><p class='sub'>{con.get('bodies') or 1} gövde. "
                    + (f"En yüksek gerilme '{html.escape(near['name'])}' temasının yakınında. " if near else "")
                    + "Bonded temas kaymaz ve ayrılmaz; gerçek cıvatalı bağlantıdan daha rijittir.</p>"
                    + (f"<div class='scroll'><table><tr><th>Nesne</th><th>Tür</th><th>Tip</th><th>Yüz (kaynak / hedef)</th>"
                       f"<th>Yüz merkezleri [mm]</th></tr>{rows_c}</table></div>" if rows_c else ""))
    tr_ = result.get("decision_trace", [])
    trace_html = ("<ol class='trace'>" + "".join(
        f"<li class='{'acc' if t['accepted'] else 'rej'}'><b>{html.escape(t['name'])}</b>: "
        f"{'kabul edildi' if t['accepted'] else 'reddedildi'}. {html.escape(tr_text(t['reason']))}</li>" for t in tr_)
        + "</ol>") if tr_ else "<p>–</p>"
    meta = [f"Gerçek incelme oranları: {', '.join(tr(float(x), 3) for x in result['refinement_ratios'])}"
            if result.get("refinement_ratios") else "",
            f"Maksimumun konumu seviyeler arasında en çok {tr(result['max_location_shift_mm'], 3)} mm kaydı"
            if result.get("max_location_shift_mm") is not None else "",
            f"Kalınlık boyunca ~{tr(result['elements_through_thickness'], 3)} eleman (en ince mesh)"
            if result.get("elements_through_thickness") is not None else ""]
    meta_html = "".join(f"<p class='sub'>{m}.</p>" for m in meta if m)
    settings_html = (
        "<dl class='kv'>"
        f"<dt>Mod</dt><dd>{'yerel sıklaştırma (sıcak bölge yüzleri)' if result.get('mode') == 'local' else 'global incelme'}</dd>"
        f"<dt>Malzeme</dt><dd>{html.escape(', '.join(result.get('materials', [])) or '–')}</dd>"
        f"<dt>Dışlama bölgesi</dt><dd>{tr(st.get('exclusion_mm'), 4)} mm, mesnet/yük yüzeylerinden"
        f"{' (' + html.escape(str(st['exclusion_rule'])) + ')' if st.get('exclusion_rule') else ''}</dd>"
        f"<dt>Düğüm limiti</dt><dd>{tr(int(st.get('max_nodes') or 0))}</dd>"
        f"<dt>GCI eşiği</dt><dd>%{tr(st.get('gci_tol_pct'))}</dd></dl>")

    name = html.escape(Path(result.get("model", "")).name)
    P = PALETTE
    doc = f"""<!DOCTYPE html><html lang="tr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>feacheck: {name}</title>
<style>
:root{{--ink:{P['ink']};--mute:{P['mute']};--rule:{P['grid']};--paper:{P['paper']};--blue:{P['blue']};--st:{color}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.6 "Segoe UI",system-ui,-apple-system,sans-serif}}
.num,.cn,h1,h2,h3,.tick,.mk,th,summary,.facts dd,nav{{font-family:Bahnschrift,"DIN Alternate","Segoe UI",system-ui,sans-serif}}
main{{max-width:940px;margin:0 auto;padding:40px 24px 72px}}
header{{border-left:6px solid var(--st);padding:2px 0 2px 20px;margin-bottom:24px}}
.model{{color:var(--mute);margin:0 0 6px;font-size:14px}}
h1{{font-size:30px;line-height:1.15;font-weight:600;margin:0 0 8px;color:var(--st)}}
.lead{{font-size:17px;max-width:64ch;margin:0}}
nav{{display:flex;flex-wrap:wrap;gap:4px 18px;font-size:14px;margin:0 0 8px}} nav a{{color:var(--blue);text-decoration:none}}
nav a:hover,nav a:focus-visible{{text-decoration:underline}}
.num{{font-size:64px;font-weight:600;line-height:1;margin:24px 0 6px;font-variant-numeric:tabular-nums}}
.num span{{font-size:22px;font-weight:400;margin-left:8px;color:var(--mute)}} .num.muted{{color:var(--mute)}}
.cap{{color:var(--mute);margin:0 0 8px;max-width:72ch}}
.facts{{display:grid;grid-template-columns:repeat(3,1fr);gap:0;margin:20px 0 0;border-top:1px solid var(--rule)}}
.facts div{{padding:10px 12px 10px 0;border-bottom:1px solid var(--rule)}} .facts dt{{color:var(--mute);font-size:13px}}
.facts dd{{margin:2px 0 0;font-size:18px;font-weight:600;font-variant-numeric:tabular-nums}}
.tick{{font-size:12px;fill:var(--mute)}} .mk{{font-size:14px;font-weight:600;fill:var(--ink)}} .rej{{text-decoration:line-through}}
h2{{font-size:20px;font-weight:600;margin:48px 0 10px;padding-bottom:6px;border-bottom:1.5px solid var(--ink);scroll-margin-top:12px}}
h3{{font-size:15px;margin:24px 0 8px}}
.sub{{color:var(--mute);font-size:14px;max-width:78ch}}
ul.checks{{list-style:none;padding:0;margin:0}}
.c{{display:grid;grid-template-columns:30px 180px 1fr;align-items:baseline;padding:10px 0;border-bottom:1px solid var(--rule)}}
.ic{{font-weight:700;width:20px;height:20px;border-radius:50%;display:inline-grid;place-items:center;font-size:12px;color:#fff;transform:translateY(-1px)}}
.c.ok .ic{{background:{P['ok']}}} .c.warn .ic{{background:{P['warn']}}} .c.bad .ic{{background:{P['bad']}}}
.cn{{font-weight:600}} .why{{display:block;color:var(--mute);font-size:13px}}
ul.todo{{padding-left:20px;margin:0}} ul.todo li{{margin:0 0 10px;max-width:78ch}}
.e{{color:{P['bad']}}}
svg.viz{{display:block;margin:12px 0;max-width:100%;height:auto}}
.lab{{font-weight:600;font-size:14px;margin:12px 0 0}}
.viz .ax{{font-size:11px;fill:var(--mute)}} .viz .lab{{font-size:12.5px;font-weight:600;fill:var(--ink)}}
.pair{{display:grid;grid-template-columns:1fr 1fr;gap:28px}}
.maps{{display:grid;grid-template-columns:1fr 1fr;gap:16px}} .legend{{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:13px;color:var(--mute)}}
.lg{{display:inline-flex;align-items:center;gap:6px}}
table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:14px;background:#fff}}
th,td{{border-bottom:1px solid var(--rule);padding:6px 8px;text-align:right;vertical-align:top}} th:first-child,td:first-child{{text-align:left}}
th{{color:var(--mute);font-weight:500;font-size:13px;background:var(--paper)}}
tr.hl td{{background:#EAF0F6;font-weight:600}}
table.steps td{{text-align:left}} table.steps td:first-child{{color:var(--mute);width:38%}}
ol.trace li{{margin-bottom:6px}} ol.trace li.acc b{{color:{P['ok']}}} ol.trace li.rej{{color:var(--mute)}}
dl.kv{{display:grid;grid-template-columns:160px 1fr;gap:4px 16px;margin:0}} dl.kv dt{{color:var(--mute)}} dl.kv dd{{margin:0}}
.scroll{{overflow-x:auto}}
details{{border-top:1.5px solid var(--ink);margin-top:48px;padding-top:4px}}
summary{{cursor:pointer;font-weight:600;font-size:20px;padding:8px 0}}
summary:focus-visible,nav a:focus-visible{{outline:2px solid var(--blue);outline-offset:3px}}
footer{{margin-top:40px;color:var(--mute);font-size:13px}}
@media(max-width:720px){{.pair,.maps{{grid-template-columns:1fr}} .facts{{grid-template-columns:1fr 1fr}}
 .c{{grid-template-columns:30px 1fr}} .cv{{grid-column:2}} .num{{font-size:48px}}}}
@media print{{body{{background:#fff}} nav{{display:none}} details>*{{display:block}} h2{{break-after:avoid}} svg{{break-inside:avoid}}}}
</style>
<main>
<header><p class="model">{name}, {html.escape(str(result.get("analysis")))}, {html.escape(str(result.get('timestamp', '')))}</p>
<h1>{html.escape(headline)}</h1><p class="lead">{html.escape(sentence)}</p></header>
<nav aria-label="Bölümler"><a href="#kontroller">Kontroller</a>{'<a href="#elhesap">El hesabı</a>' if hc else ''}<a href="#yakinsama">Sahte mi, gerçek mi?</a>
<a href="#konum">Konum</a><a href="#gci">Belirsizlik</a>{'<a href="#radyus">Radyus</a>' if rs_html else ''}
<a href="#denge">Denge</a><a href="#mesh">Mesh</a><a href="#karar">Karar izi</a></nav>
{number}
{_scale(result)}
{facts_html}
<h2 id="kontroller">Kontroller</h2><ul class="checks">{checks_html}</ul>
{('<h2>Hatalar</h2><ul>' + errs + '</ul>') if errs else ''}
<h2>Bulgular ve yapılacaklar</h2><ul class="todo">{todo or '<li>Yapılacak bir şey yok.</li>'}</ul>
{_handcalc_section(hc)}
<h2 id="yakinsama">Sahte tepe mi, gerçek gerilme mi?</h2>
<p class="sub">{conv_text}</p>
{conv}
<h3>Büyüme üssü</h3><p class="sub">{gauge_text}</p>{gauge}
<h2 id="konum">Nerede?</h2>
<p class="sub">Mesnet ve yük yüzlerinin merkezleri, etraflarındaki dışlama bölgesi (Saint-Venant: bu bölgedeki gerilme
sınır şartının modellenme biçimine bağlıdır), ham tepe ve tasarım değerinin okunduğu nokta. Parçanın kendisi
çizilmez; koordinatlar global eksende.</p>
{lmap or "<p class='sub'>Bu koşuda yüz konumları kaydedilmemiş.</p>"}
<h3>Sınır şartları</h3>{bc_html}{con_html}
<h2 id="gci">Sayısal belirsizlik (GCI)</h2>
<p class="sub">Grid Convergence Index (Roache 1994; Celik vd. 2008): üç mesh'in sonucundan değerin mesh
sonsuz ince olsaydı ne olacağını (Richardson ekstrapolasyonu) ve en ince mesh'teki değerin hata payını yüzde
olarak verir. Tasarım değerinin hesabı:</p>
{steps_html or "<p class='sub'>Tasarım değeri için üç seviyeli hesap yok.</p>"}
<h3>Tüm büyüklükler</h3><div class="scroll"><table><tr><th>Büyüklük</th><th>Seviyeler (kaba → ince)</th>
<th>h→0</th><th>p</th><th>GCI %</th><th>Karar</th></tr>{qrows}</table></div>
<p class="sub">Vurgulu satır tasarım değerinin alındığı büyüklük.</p>
{('<div id="radyus"></div>' + rs_html) if rs_html else ''}
<h2 id="denge">Denge ve mesnet tepkileri</h2>
{eq_vis}{eq_txt}
<p class="sub">Doğrusal statik çözümde toplam denge neredeyse her zaman tutar. Tutması sınır şartlarının doğru
yüzlerde olduğunu göstermez; bunun için konum haritasına bak.</p>
<h2 id="mesh">Mesh</h2>
{mesh_vis}
<h3>Deformasyon, mesh inceldikçe</h3><p class="sub">Deformasyon gerilmeden çok daha hızlı yakınsar ve tekillikten etkilenmez;
yakınsamıyorsa model kurulumunda sorun vardır.</p>{dchart}
{"<p class='sub'>Bir tasarım değeri adayı gürültü düzeyinde ama yönü belirsiz değiştiği için düğüm limiti içinde bir global seviye daha çözüldü; GCI son üç seviyeden.</p>" if result.get("extra_level") else ""}
<div class="scroll"><table><tr><th>h [mm]</th><th>Düğüm</th><th>Kalite min/ort</th><th>Skewness maks</th><th>Aspect maks</th>
<th>vM maks</th><th>vM bölge dışı</th><th>vM probe</th><th>Def. maks</th><th>Durum</th></tr>{rows}</table></div>
<p class="sub">Kabul sınırları (Ansys önerileri): element quality ortalama 0,7'nin, minimum 0,1'in üstünde;
skewness maks 0,9'un, aspect ratio maks 20'nin altında.</p>{meta_html}
<h2 id="karar">Karar izi</h2>
<p class="sub">feacheck'in tasarım değerini seçerken sırayla denediği adaylar ve her birini neden kabul ya da
reddettiği.</p>{trace_html}
<details><summary>Ayarlar ve uyarılar</summary>
<h3>Ayarlar</h3>{settings_html}
<h3>Uyarılar</h3><ul>{warns or '<li>Yok</li>'}</ul>
</details>
<footer>feacheck {__version__}, doğrulama (verification) raporu: sonucun sayısal doğruluğunu ölçer; modelin gerçek parçayı
doğru temsil edip etmediğini (validation) göstermez. Süre {tr(float(result.get('duration_s', 0) or 0), 3)} s.</footer>
</main>
</html>"""
    out_html = Path(out_html)
    out_html.write_text(doc, encoding="utf-8")
    return out_html
