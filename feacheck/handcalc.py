"""El hesabı: FEA sonucunu bağımsız bir referansla karşılaştırmak için kapalı form çözümler.

Birimler: N, mm, MPa (N/mm²), N·mm. Her fonksiyon {"value", "formula", "source", ...} döndürür ki raporda
hesabın nereden geldiği görünsün. Eğri uydurmaları geçerlilik aralığı dışında ValueError verir: aralık dışı
bir Kt sessizce kullanılırsa el hesabı FEA'yı "doğrulamaz", yanıltır.
"""
from __future__ import annotations

import math


def _res(value, formula, source, **kw):
    return {"value": value, "formula": formula, "source": source, **kw}


# ------------------------------------------------------------------ kesit ve kiriş
def bending_round(M_Nmm: float, d: float) -> dict:
    """Dolu dairesel kesit, eğilme: σ = 32M / (πd³)."""
    return _res(32 * M_Nmm / (math.pi * d ** 3), "σ = 32M/(πd³)", "kiriş teorisi")


def bending_rect(M_Nmm: float, b: float, t: float) -> dict:
    """Dikdörtgen kesit (genişlik b, eğilme yönündeki kalınlık t): σ = 6M / (b t²)."""
    return _res(6 * M_Nmm / (b * t ** 2), "σ = 6M/(bt²)", "kiriş teorisi")


def torsion_round(T_Nmm: float, d: float) -> dict:
    """Dolu dairesel kesit, burulma: τ = 16T / (πd³)."""
    return _res(16 * T_Nmm / (math.pi * d ** 3), "τ = 16T/(πd³)", "burulma teorisi")


def cantilever_tip_deflection(F: float, L: float, E: float, I: float) -> dict:
    """Konsol kiriş uç yükü: δ = FL³ / (3EI)."""
    return _res(F * L ** 3 / (3 * E * I), "δ = FL³/(3EI)", "Euler-Bernoulli kiriş")


def I_round(d: float) -> float:
    return math.pi * d ** 4 / 64


def von_mises(sigma: float, tau: float = 0.0) -> dict:
    """Tek eksenli normal gerilme + kayma: σ_vM = √(σ² + 3τ²)."""
    return _res(math.sqrt(sigma ** 2 + 3 * tau ** 2), "σ_vM = √(σ² + 3τ²)", "von Mises")


# ------------------------------------------------------------------ eğri kiriş
def winkler_rect_inner(M_Nmm: float, ri: float, ro: float, b: float) -> dict:
    """Dikdörtgen kesitli eğri kiriş (Winkler-Bach), iç lif gerilmesi.
    r_n = h / ln(ro/ri), e = R − r_n, σ_i = M (r_n − ri) / (A e ri)."""
    if not ro > ri > 0:
        raise ValueError("ro > ri > 0 olmalı")
    h = ro - ri
    rn = h / math.log(ro / ri)
    R = (ro + ri) / 2
    e = R - rn
    A = b * h
    s = M_Nmm * (rn - ri) / (A * e * ri)
    return _res(s, "σ_i = M(r_n − r_i)/(A·e·r_i), r_n = h/ln(r_o/r_i)", "Winkler-Bach eğri kiriş",
                r_n=rn, e=e)


# ------------------------------------------------------------------ gerilme yığılma katsayıları
def kt_plate_central_hole_tension(d: float, W: float) -> dict:
    """Sonlu genişlikte levhada merkezi delik, çekme; Kt net kesite göre.
    Kt = 3 − 3,14(d/W) + 3,667(d/W)² − 1,527(d/W)³  (Heywood; Pilkey, Peterson's SCF, Chart 4.1 uydurması)."""
    a = d / W
    if not 0 < a <= 0.65:
        raise ValueError(f"d/W = {a:.3f} geçerlilik aralığı dışında (0 < d/W ≤ 0,65)")
    kt = 3 - 3.14 * a + 3.667 * a ** 2 - 1.527 * a ** 3
    return _res(kt, "Kt = 3 − 3,14(d/W) + 3,667(d/W)² − 1,527(d/W)³ (net kesit)",
                "Heywood; Pilkey & Pilkey, Peterson's Stress Concentration Factors, Chart 4.1", d_W=a)


_SHOULDER = {   # Roark (Young & Budynas) Tablo 17.1 — Pilkey/Peterson eğri uydurmaları, kademeli dairesel mil
    "tension": [((0.1, 2.0), [(0.926, 1.157, -0.099), (0.012, -3.036, 0.961), (-0.302, 3.977, -1.744),
                              (0.365, -2.098, 0.878)]),
                ((2.0, 20.0), [(1.200, 0.860, -0.022), (-1.805, -0.346, -0.038), (2.198, -0.486, 0.165),
                               (-0.593, -0.028, -0.106)])],
    "bending": [((0.1, 2.0), [(0.947, 1.206, -0.131), (0.022, -3.405, 0.915), (0.869, 1.777, -0.555),
                              (-0.810, 0.422, -0.260)]),
                ((2.0, 20.0), [(1.232, 0.832, -0.008), (-3.813, 0.968, -0.260), (7.423, -4.868, 0.869),
                               (-3.839, 3.070, -0.600)])],
    "torsion": [((0.25, 4.0), [(0.905, 0.783, -0.075), (-0.437, -1.969, 0.553), (1.557, 1.073, -0.578),
                               (-1.061, 0.171, 0.086)])],
}


def kt_shaft_shoulder(D: float, d: float, r: float, load: str = "bending") -> dict:
    """Kademeli dairesel mil, omuz radyusu. h = (D − d)/2, x = 2h/D,
    Kt = C1 + C2·x + C3·x² + C4·x³, Cᵢ = a + b√(h/r) + c(h/r). Nominal gerilme küçük çap d ile."""
    if not D > d > 0 or r <= 0:
        raise ValueError("D > d > 0 ve r > 0 olmalı")
    h = (D - d) / 2
    hr = h / r
    for (lo, hi), coeffs in _SHOULDER[load]:
        if lo <= hr <= hi:
            C = [a + b * math.sqrt(hr) + c * hr for a, b, c in coeffs]
            x = 2 * h / D
            kt = C[0] + C[1] * x + C[2] * x ** 2 + C[3] * x ** 3
            return _res(kt, "Kt = C1 + C2(2h/D) + C3(2h/D)² + C4(2h/D)³, h = (D−d)/2",
                        f"Roark (Young & Budynas) Tablo 17.1, kademeli mil, {load}; Pilkey/Peterson uydurması",
                        h_r=hr, two_h_D=x)
    rng = ", ".join(f"[{lo:g}; {hi:g}]" for (lo, hi), _ in _SHOULDER[load])
    raise ValueError(f"h/r = {hr:.3f} geçerlilik aralığı dışında ({load}: {rng})")


# ------------------------------------------------------------------ rover teker yükleri
G = 9.81


def rover_wheel_loads(m_kg: float, n_wheels: int, D_wheel_mm: float, T_motor_Nm: float,
                      gear_ratio: float = 1.0, eta: float = 1.0, k_dyn: float = 2.5,
                      mu: float = 0.8, mu_lat: float = 0.5) -> dict:
    """Tek tekerin tasarım yükleri (N). Eşit yük paylaşımı varsayılır.

    k_dyn, mu, mu_lat VARSAYIMDIR (engel/çukur darbesi, toprak-teker sürtünmesi); rover_girdi.yaml'da
    kullanıcı onaylar. Çekiş kuvveti motorun verebileceği ile zeminin taşıyabileceğinin küçüğüdür.
    """
    if min(m_kg, n_wheels, D_wheel_mm, gear_ratio, eta, k_dyn) <= 0 or T_motor_Nm < 0:
        raise ValueError("kütle, teker sayısı, çap, oran, verim ve k_dyn pozitif olmalı")
    r = D_wheel_mm / 2
    Fz = m_kg * G / n_wheels
    Fx_motor = T_motor_Nm * 1000 * gear_ratio * eta / r
    Fx_zemin = mu * Fz
    Fx = min(Fx_motor, Fx_zemin)
    return _res(
        {"Fz_statik": Fz, "Fz_tasarim": k_dyn * Fz, "Fx_cekis": Fx, "Fy_yanal": mu_lat * Fz,
         "M_aks_Nmm": Fx * r},
        "Fz = mg/n; Fz,t = k·Fz; Fx = min(T·i·η/r, μ·Fz); Fy = μy·Fz; M = Fx·r",
        "statik denge + Coulomb sürtünmesi; k_dyn, μ, μy varsayım",
        cekis_siniri="motor" if Fx_motor <= Fx_zemin else "zemin",
        varsayimlar={"k_dyn": k_dyn, "mu": mu, "mu_lat": mu_lat})


# ------------------------------------------------------------------ karşılaştırma
def _n(v: float) -> str:
    return f"{v:.4g}".replace(".", ",")


def compare(fea: float, low: float | None = None, high: float | None = None, value: float | None = None,
            tol_pct: float = 10.0) -> dict:
    """FEA değerini el hesabıyla karşılaştırır. Ya tek değer (± tol) ya da [alt, üst] aralığı."""
    if value is not None:
        diff = 100 * (fea - value) / value
        ok = abs(diff) <= tol_pct
        return {"kind": "value", "ref": value, "diff_pct": round(diff, 2), "ok": ok,
                "text": f"FEA {_n(fea)}, el hesabı {_n(value)} MPa, fark %{diff:+.1f}".replace(".", ",")
                        + ("" if ok else f" (tolerans ±%{tol_pct:g} aşıldı)")}
    if low is None or high is None or not high > low:
        raise ValueError("ya value ya da alt < üst verilmeli")
    pos = (fea - low) / (high - low)
    ok = 0 <= pos <= 1
    return {"kind": "range", "low": low, "high": high, "pos": round(pos, 3), "ok": ok,
            "text": f"FEA {_n(fea)} MPa, el hesabı aralığı {_n(low)}–{_n(high)} MPa"
                    + (" içinde" if ok else (" altında" if pos < 0 else " üstünde"))}
