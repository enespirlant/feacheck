"""Grid Convergence Index (Roache 1994; Celik et al., J. Fluids Eng. 130, 2008).

Üç mesh (1 = en ince, 3 = en kaba) sonucundan:
  * görünen yakınsama mertebesi p
  * Richardson ekstrapolasyonu (sonsuz ince mesh tahmini)
  * GCI_fine: ince mesh sonucunun sayısal belirsizliği (% olarak, Fs = 1.25)
Yapısal FEA'da tet10 için teorik p ≈ 2 (yer değiştirme), gerilmede ≈ 1-2.
"""
from __future__ import annotations

import math

FS = 1.25          # mertebesi doğrulanmış 3+ mesh (Roache 1998)
FS_WEAK = 3.0      # görünen mertebe beklenen aralığın dışında
P_MIN, P_MAX = 0.5, 4.0
P_LOW = 1.0        # kuadratik elemanda gerilmenin beklenen mertebesi ≈ 2; p < 1 doğrulanmamış mertebe sayılır


def rep_h(nodes: int) -> float:
    """3B temsilî eleman boyutu: h = (1/N)^(1/3) (Celik 2008, Eq. 1 sadeleşmiş)."""
    return (1.0 / nodes) ** (1.0 / 3.0)


def gci3(phi: list[float], h: list[float]) -> dict:
    """phi, h: [ince, orta, kaba]. Dönüş: p, ekstrapolasyon, GCI, durum."""
    f1, f2, f3 = phi
    h1, h2, h3 = h
    if min(h1, h2, h3) <= 0:
        return {"status": "invalid", "p": None, "extrapolated": None, "gci_fine_pct": None,
                "note": "Geçersiz eleman boyu."}
    r21, r32 = h2 / h1, h3 / h2
    e21, e32 = f2 - f1, f3 - f2
    out = {"r21": round(r21, 3), "r32": round(r32, 3)}
    if r21 <= 1.0 + 1e-6 or r32 <= 1.0 + 1e-6:
        return {**out, "status": "invalid", "p": None, "extrapolated": None, "gci_fine_pct": None,
                "note": "Mesh seviyeleri incelmiyor (r ≤ 1); GCI hesaplanamaz."}
    if abs(e21) < 1e-12 * max(1.0, abs(f1)):
        return {**out, "status": "exact", "p": None, "extrapolated": f1, "gci_fine_pct": 0.0}
    ratio = e32 / e21
    if ratio < 0:
        return {**out, "status": "oscillatory", "p": None, "extrapolated": None,
                "gci_fine_pct": None, "note": "Sonuç mesh ile salınıyor; yakınsama belirsiz."}
    s = 1.0  # monotonik
    p = abs(math.log(abs(ratio))) / math.log(r21)
    for _ in range(100):  # Celik 2008 sabit nokta iterasyonu (r21 != r32 için)
        q = math.log((r21 ** p - s) / (r32 ** p - s)) if r21 ** p != s and r32 ** p != s else 0.0
        p_new = abs(math.log(abs(ratio)) + q) / math.log(r21)
        if abs(p_new - p) < 1e-8:
            break
        p = p_new
    diverging = abs(e21) > abs(e32)  # ince tarafta değişim büyüyor
    if diverging:
        return {**out, "status": "diverging", "p": round(-p, 3), "extrapolated": None, "gci_fine_pct": None,
                "note": "Mesh inceldikçe değişim BÜYÜYOR: tekillik belirtisi."}
    # Görünen mertebe beklenen aralığın dışındaysa seri asimptotik bölgede değildir:
    # p kırpılır ve güvenlik katsayısı 3 alınır (Roache 1998).
    p_raw = p
    non_asym = not (P_MIN <= p <= P_MAX)
    p = min(max(p, P_MIN), P_MAX)
    low_order = (not non_asym) and p < P_LOW
    fs = FS_WEAK if (non_asym or low_order) else FS
    ea21 = abs((f1 - f2) / f1) if abs(f1) > 1e-30 else 0.0
    ext = (r21 ** p * f1 - f2) / (r21 ** p - 1)
    gci = fs * ea21 / (r21 ** p - 1)
    eext = abs((ext - f1) / ext) if abs(ext) > 1e-30 else 0.0
    res = {**out, "status": "converging", "p": round(p, 3), "extrapolated": ext, "fs": fs,
           "gci_fine_pct": round(100 * gci, 3), "rel_change_pct": round(100 * ea21, 3),
           "ext_rel_error_pct": round(100 * eext, 3)}
    if low_order:
        res["low_order"] = True
        res["note"] = (f"Görünen mertebe p = {p:.2f}, beklenen mertebenin (kuadratik elemanda gerilme için ≈ 2) çok "
                       f"altında: yakınsama zayıf doğrulanmış, Fs = {FS_WEAK:g} alındı (Roache 1998).")
    if non_asym:
        res["non_asymptotic"] = True
        res["p_raw"] = round(p_raw, 3)
        res["note"] = (f"Görünen mertebe p = {p_raw:.2f}, beklenen aralık [{P_MIN}, {P_MAX}] dışında: "
                       f"seri asimptotik bölgede değil, p kırpıldı ve Fs = {FS_WEAK:g} alındı.")
    return res
