"""Geometriye bakıp analiz kurulumu ÖNERİR. Öneri onaylanmadan çözüme geçilmez.

Mantık bir mühendisin ilk bakışını taklit eder:
  * Aynı çaplı delik grubu varsa -> büyük ihtimalle cıvatalı bağlantı -> mesnet adayı
  * Delik yoksa ve parça uzunsa -> konsol kiriş kabulü (bir uç sabit, diğer uç yük)
  * Yük yüzü: mesnetten en uzaktaki büyük düzlem veya boss
  * Mesh: en küçük özelliğe göre (delik yarıçapı, et kalınlığı tahmini)
Yük BÜYÜKLÜĞÜ asla tahmin edilmez: kullanıcıdan istenir.
"""
from __future__ import annotations

import math

import yaml

from .geometry import Part, _dot, hole_groups, planar_groups


def _mesh_suggestion(part: Part) -> dict:
    holes = hole_groups(part)
    smallest = min(part.size_mm)
    cands = [smallest / 4]
    reason = [f"en ince boyut {smallest:g} mm / 4"]
    if holes:
        dmin = min(h["diameter_mm"] for h in holes)
        cands.append(dmin * math.pi / 8)  # delik çevresinde ~8 eleman
        reason.append(f"en küçük delik Ø{dmin:g} çevresinde ~8 eleman")
    s = max(0.2, round(min(cands), 2))
    return {"element_size_mm": s, "convergence_sizes_mm": [round(2 * s, 2), s, round(s / 2, 2)],
            "why": "; ".join(reason) + ". Delik/köşe çevresine lokal sıklaştırma daha verimli olur."}


def propose(part: Part, material: str = "Structural Steel") -> dict:
    holes = hole_groups(part)
    planes = planar_groups(part)
    notes, fixed, forces = [], [], []
    bolt = [h for h in holes if h["count"] >= 2]

    if bolt:
        g = max(bolt, key=lambda h: (h["count"], h["diameter_mm"]))
        fixed.append({"holes": {"diameter_mm": g["diameter_mm"]}})
        notes.append(f"{g['count']}× Ø{g['diameter_mm']:g} delik grubu cıvatalı bağlantı kabul edildi ve sabitlendi. "
                     "Delik yüzeyini tamamen sabitlemek RİJİT bir kabuldür; gerilmeler delik çevresinde "
                     "olduğundan yüksek çıkar. Daha gerçekçisi: oturma yüzeyine 'compression only' "
                     "mesnet + deliklere silindirik mesnet (v0.4).")
        axis = [abs(c) for c in g["axis"]]
        # yük: delik eksenine dik olmayan, en uzak/en büyük karşı yüz veya boss
        boss = [f for f in part.faces if f.type == "cylinder" and f.internal is False]
        if boss:
            b = max(boss, key=lambda f: f.area_mm2)
            forces.append({"scope": {"cylinders": {"diameter_mm": round(2 * b.radius_mm, 4)}},
                           "components_n": None})
            notes.append(f"Yük Ø{2 * b.radius_mm:g} mm boss yüzeyine konuldu (montaj/yük noktası varsayımı).")
        else:
            top = next((p for p in planes if abs(_dot(p["normal"], axis)) > 0.99), planes[0])
            forces.append({"scope": {"planes": {"normal": top["normal"], "offset_mm": top["offset_mm"]}},
                           "components_n": None})
            notes.append("Yük, delik eksenine dik en büyük düzleme konuldu.")
    else:
        k = max(range(3), key=lambda i: part.size_mm[i])
        ax = "xyz"[k]
        slender = part.size_mm[k] / max(1e-9, sorted(part.size_mm)[1])
        fixed.append({"axis": ax, "side": "min"})
        forces.append({"scope": {"axis": ax, "side": "max"}, "components_n": None})
        notes.append(f"Delik grubu yok. En uzun eksen {ax} (narinlik ≈ {slender:.1f}): "
                     "konsol kiriş kabulü, min uç sabit, max uca yük.")

    notes.append("YÜK DEĞERİ GİRİLMEDİ: components_n [Fx, Fy, Fz] (N) alanını doldur. Yükü ben tahmin etmem.")
    mesh = _mesh_suggestion(part)
    setup = {"material": {"db": material},
             "mesh": {"element_size_mm": mesh["element_size_mm"],
                      "convergence_sizes_mm": mesh["convergence_sizes_mm"]},
             "loads": {"fixed": fixed, "forces": forces, "pressures": []}}
    return {"setup": setup, "notes": notes + [f"Mesh: {mesh['why']}"],
            "yaml": "# ÖNERİ - onaylamadan çözülmez\n" + "".join(f"# - {n}\n" for n in notes)
                    + yaml.safe_dump(setup, allow_unicode=True, sort_keys=False)}
