"""ISO 286 geçme hesabı ve tolerans zinciri (stack-up).

Kapsam: delik tabanlı sistem (H delik) + yaygın mil sapmaları, 0-500 mm, IT5-IT11.
Değerler ISO 286-2 tablolarındandır (µm). Kritik işte tabloyla teyit et.
"""
from __future__ import annotations

import math
import random
import re

RANGES = [3, 6, 10, 18, 30, 50, 80, 120, 180, 250, 315, 400, 500]  # üst sınırlar (mm)

IT = {  # µm
    5: [4, 5, 6, 8, 9, 11, 13, 15, 18, 20, 23, 25, 27],
    6: [6, 8, 9, 11, 13, 16, 19, 22, 25, 29, 32, 36, 40],
    7: [10, 12, 15, 18, 21, 25, 30, 35, 40, 46, 52, 57, 63],
    8: [14, 18, 22, 27, 33, 39, 46, 54, 63, 72, 81, 89, 97],
    9: [25, 30, 36, 43, 52, 62, 74, 87, 100, 115, 130, 140, 155],
    10: [40, 48, 58, 70, 84, 100, 120, 140, 160, 185, 210, 230, 250],
    11: [60, 75, 90, 110, 130, 160, 190, 220, 250, 290, 320, 360, 400],
}

# Mil temel sapmaları (µm). Üst sapma es: d e f g h ; alt sapma ei: k m n p
SHAFT_ES = {
    "d": [-20, -30, -40, -50, -65, -80, -100, -120, -145, -170, -190, -210, -230],
    "e": [-14, -20, -25, -32, -40, -50, -60, -72, -85, -100, -110, -125, -135],
    "f": [-6, -10, -13, -16, -20, -25, -30, -36, -43, -50, -56, -62, -68],
    "g": [-2, -4, -5, -6, -7, -9, -10, -12, -14, -15, -17, -18, -20],
    "h": [0] * 13,
}
SHAFT_EI = {
    "k": [0, 1, 1, 1, 2, 2, 2, 3, 3, 4, 4, 4, 5],     # IT4..IT7 için; diğer kalitelerde 0
    "m": [2, 4, 6, 7, 8, 9, 11, 13, 15, 17, 20, 21, 23],
    "n": [4, 8, 10, 12, 15, 17, 20, 23, 27, 31, 34, 37, 40],
    "p": [6, 12, 15, 18, 22, 26, 32, 37, 43, 50, 56, 62, 68],
}


def _idx(d: float) -> int:
    if not 0 < d <= 500:
        raise ValueError("Nominal ölçü 0-500 mm arasında olmalı")
    return next(i for i, up in enumerate(RANGES) if d <= up)


def _parse(code: str):
    m = re.fullmatch(r"([A-Za-z]{1,2})(\d{1,2})", code.strip())
    if not m:
        raise ValueError(f"Tolerans kodu anlaşılamadı: {code} (örn. H7, g6)")
    return m.group(1), int(m.group(2))


def limits(d: float, code: str) -> dict:
    """Tek özellik sınırları. Büyük harf = delik, küçük harf = mil."""
    letter, grade = _parse(code)
    if grade not in IT:
        raise ValueError(f"IT{grade} desteklenmiyor (IT5-IT11)")
    i, it = _idx(d), IT[grade][_idx(d)]
    if letter == "H":
        lo, hi = 0, it
    elif letter == "JS" or letter == "js":
        lo, hi = -it / 2, it / 2
    elif letter in SHAFT_ES:
        hi = SHAFT_ES[letter][i]
        lo = hi - it
    elif letter in SHAFT_EI:
        lo = SHAFT_EI[letter][i] if (letter != "k" or 4 <= grade <= 7) else 0
        hi = lo + it
    else:
        raise ValueError(f"'{letter}' desteklenmiyor. Delik: H, JS; mil: d e f g h js k m n p")
    return {"code": code, "nominal_mm": d, "lower_um": lo, "upper_um": hi, "IT_um": it,
            "min_mm": round(d + lo / 1000, 4), "max_mm": round(d + hi / 1000, 4)}


def fit(d: float, hole: str = "H7", shaft: str = "g6") -> dict:
    h, s = limits(d, hole), limits(d, shaft)
    cmax = h["upper_um"] - s["lower_um"]
    cmin = h["lower_um"] - s["upper_um"]
    kind = "boşluklu" if cmin >= 0 else ("sıkı" if cmax <= 0 else "geçiş")
    use = {"boşluklu": "dönen/kayan parçalar, kolay montaj",
           "geçiş": "konumlama; hafif presle veya tokmakla montaj",
           "sıkı": "pres geçme; tork/kuvvet iletimi, sökülmez"}[kind]
    return {"fit": f"Ø{d:g} {hole}/{shaft}", "hole": h, "shaft": s, "type": kind,
            "clearance_max_um": cmax, "clearance_min_um": cmin,
            "note": "Negatif boşluk = sıkılık. " + use}


# ---------------------------------------------------------------- stack-up

def stackup(dims: list[dict], target: dict | None = None, mc_samples: int = 100_000, seed: int = 1) -> dict:
    """1B tolerans zinciri.

    dims: [{"name": "A", "nominal": 20, "tol": 0.1, "dir": +1}, ...]  tol = ± simetrik
          veya {"upper": 0.05, "lower": -0.02} asimetrik. dir: +1 artıran, -1 azaltan halka.
    target: {"min": 0.1, "max": 0.5} kapanış ölçüsü (boşluk) sınırları.
    Yöntemler: en kötü durum (WC), RSS (istatistiksel, ±3σ), Monte Carlo (normal dağılım, ±tol = 3σ).
    """
    nom = wc = 0.0
    var = 0.0
    rows = []
    for d in dims:
        up = d.get("upper", d.get("tol"))
        lo = d.get("lower", -d.get("tol", 0))
        mid = d["nominal"] + (up + lo) / 2
        half = (up - lo) / 2
        s = d.get("dir", 1)
        nom += s * mid
        wc += half
        var += (half / 3) ** 2
        rows.append({"name": d.get("name", "?"), "mean": mid, "half_tol": half, "dir": s})
    rss = 3 * math.sqrt(var)
    rnd = random.Random(seed)
    samples = [sum(r["dir"] * rnd.gauss(r["mean"], r["half_tol"] / 3) for r in rows) for _ in range(mc_samples)]
    samples.sort()
    out = {"nominal_mean": round(nom, 5),
           "worst_case": [round(nom - wc, 5), round(nom + wc, 5)],
           "rss_3sigma": [round(nom - rss, 5), round(nom + rss, 5)],
           "monte_carlo_0.135_99.865pct": [round(samples[int(0.00135 * mc_samples)], 5),
                                           round(samples[int(0.99865 * mc_samples)], 5)],
           "contributors_pct": {r["name"]: round(100 * (r["half_tol"] / 3) ** 2 / var, 1) if var else 0 for r in rows}}
    if target:
        bad = sum(1 for x in samples if x < target.get("min", -1e18) or x > target.get("max", 1e18))
        out["mc_out_of_spec_ppm"] = round(1e6 * bad / mc_samples, 1)
        out["worst_case_ok"] = target.get("min", -1e18) <= nom - wc and nom + wc <= target.get("max", 1e18)
    return out
