"""Her analiz için tek sayfalık HTML rapor."""
from __future__ import annotations

import html
from pathlib import Path


def _fmt(v, nd=3):
    if v is None:
        return "-"
    return f"{v:.{nd}g}" if isinstance(v, float) else str(v)


def write_report(out: Path, s: dict, cfg: dict) -> Path:
    rows = [
        ("Durum", "BAŞARILI" if s.get("ok") else "HATA"),
        ("Malzeme", cfg["material"]["name"]),
        ("Eleman boyutu [mm]", _fmt(s.get("element_size_mm"))),
        ("Düğüm / Eleman", f"{_fmt(s.get('nodes'))} / {_fmt(s.get('elements'))}"),
        ("Maks. von Mises [MPa]", _fmt(s.get("max_von_mises_mpa"), 4)),
        ("Maks. deformasyon [mm]", _fmt(s.get("max_deformation_mm"), 4)),
        ("Güvenlik katsayısı", _fmt(s.get("safety_factor"))),
        ("Kütle [kg]", _fmt(s.get("mass_kg"), 4)),
        ("Süre [s]", _fmt(s.get("duration_s"))),
    ]
    conv = s.get("convergence")
    if conv:
        pairs = ", ".join(f"{a} mm → {_fmt(b, 4)} MPa" for a, b in zip(conv["sizes_mm"], conv["von_mises_mpa"]))
        rows.append(("Yakınsama", f"{pairs} (son değişim %{conv['last_change_pct']})"))

    table = "".join(f"<tr><th>{html.escape(k)}</th><td>{html.escape(str(v))}</td></tr>" for k, v in rows)
    scopes = "".join(
        f"<li><b>{html.escape(x['name'])}</b> ({x['tag']}): "
        + ("CAD named selection" if x.get("source") == "named_selection"
           else f"{x.get('face_count')} yüz, kural: {html.escape(str(x.get('rule', '')))}") + "</li>"
        for x in s.get("scopes", []))
    msgs = "".join(f"<li class=w>{html.escape(m)}</li>" for m in s.get("warnings", [])) + \
           "".join(f"<li class=e>{html.escape(m)}</li>" for m in s.get("errors", []))
    imgs = "".join(f'<figure><img src="{n}"><figcaption>{n}</figcaption></figure>'
                   for n in ("von_mises.png", "deformation.png") if (out / n).exists())

    doc = f"""<!DOCTYPE html><html lang="tr"><meta charset="utf-8">
<title>{html.escape(s.get('run_id', 'rapor'))}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#222}}
table{{border-collapse:collapse;width:100%}}th,td{{border-bottom:1px solid #ddd;padding:.45rem;text-align:left}}
th{{width:40%;color:#555;font-weight:500}}.w{{color:#a06000}}.e{{color:#b00020}}
img{{max-width:100%;border:1px solid #ddd}}figure{{margin:1rem 0}}</style>
<h1>{html.escape(s.get('file', ''))}</h1><p>{html.escape(s.get('run_id', ''))}</p>
<table>{table}</table>
<h2>Kontrol et: sınır şartları</h2>
<p>Mechanical'da <code>model.mechdb</code>'yi aç, Named Selections altında AUTO_ seçimlerine tıkla ve doğru yüzler mi bak.</p>
<ul>{scopes}</ul>
<h2>Uyarılar</h2><ul>{msgs or '<li>Yok</li>'}</ul>{imgs}</html>"""
    p = out / "report.html"
    p.write_text(doc, encoding="utf-8")
    return p
