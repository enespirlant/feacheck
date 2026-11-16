"""FEA sonuçlarını doğrulamak için el hesapları (sanity check).

Her FEA'dan önce/sonra bir el hesabı: büyüklük mertebesi tutmuyorsa sınır şartı/birim hatası vardır.
"""
from __future__ import annotations

import math

# ISO 898-1 metrik kaba diş gerilme alanı As [mm2]
BOLT_AS = {"M3": 5.03, "M4": 8.78, "M5": 14.2, "M6": 20.1, "M8": 36.6, "M10": 58.0,
           "M12": 84.3, "M14": 115, "M16": 157, "M20": 245, "M24": 353}
# Proof (yük deneyi) gerilmesi Sp [MPa]
PROOF = {"8.8": 580, "10.9": 830, "12.9": 970}


def _section(shape: str, d: float = 0, b: float = 0, h: float = 0, t: float = 0):
    if shape == "round":
        return math.pi * d ** 4 / 64, d / 2, math.pi * d ** 2 / 4
    if shape == "tube":
        di = d - 2 * t
        return math.pi * (d ** 4 - di ** 4) / 64, d / 2, math.pi * (d ** 2 - di ** 2) / 4
    if shape == "rect":
        return b * h ** 3 / 12, h / 2, b * h
    raise ValueError("shape: round | tube | rect")


def beam(case: str, F_n: float, L_mm: float, E_gpa: float, shape: str, **dims) -> dict:
    """case: cantilever (uçta yük) | simply_supported (ortada yük) | fixed_fixed (ortada yük)."""
    I, c, A = _section(shape, **dims)
    E = E_gpa * 1000
    if case == "cantilever":
        M, delta = F_n * L_mm, F_n * L_mm ** 3 / (3 * E * I)
    elif case == "simply_supported":
        M, delta = F_n * L_mm / 4, F_n * L_mm ** 3 / (48 * E * I)
    elif case == "fixed_fixed":
        M, delta = F_n * L_mm / 8, F_n * L_mm ** 3 / (192 * E * I)
    else:
        raise ValueError("case: cantilever | simply_supported | fixed_fixed")
    return {"I_mm4": round(I, 3), "M_max_Nmm": round(M, 2), "sigma_max_mpa": round(M * c / I, 3),
            "tau_avg_mpa": round(F_n / A, 3), "deflection_max_mm": round(delta, 5),
            "note": "Euler-Bernoulli; L/h < 10 ise kayma deformasyonu ihmal edilemez."}


def bolt(size: str, grade: str = "8.8", K: float = 0.2, preload_ratio: float = 0.75,
         F_ext_n: float = 0.0, n_bolts: int = 1, mu_joint: float = 0.15) -> dict:
    """Cıvata ön yükü, sıkma torku ve basit kayma (sürtünme) kontrolü. Shigley yaklaşımı."""
    As, Sp = BOLT_AS[size], PROOF[grade]
    d = float(size[1:])
    Fp = As * Sp
    Fi = preload_ratio * Fp
    T = K * Fi * d / 1000
    out = {"As_mm2": As, "proof_load_n": round(Fp), "preload_n": round(Fi),
           "torque_nm": round(T, 2),
           "note": f"K={K} (kuru çelik ~0.2, yağlı ~0.15). Ön yük %{preload_ratio * 100:.0f} proof (sökülebilir bağlantı)."}
    if F_ext_n:
        slip = mu_joint * Fi * n_bolts
        out["shear_slip_capacity_n"] = round(slip)
        out["slip_safety"] = round(slip / F_ext_n, 2)
    return out


def thin_pressure_vessel(p_mpa: float, D_mm: float, t_mm: float) -> dict:
    return {"hoop_mpa": round(p_mpa * D_mm / (2 * t_mm), 3), "axial_mpa": round(p_mpa * D_mm / (4 * t_mm), 3),
            "valid": D_mm / t_mm > 20}


def euler_buckling(E_gpa: float, L_mm: float, shape: str, K: float = 1.0, **dims) -> dict:
    """K: 2.0 ankastre-serbest, 1.0 mafsal-mafsal, 0.7 ankastre-mafsal, 0.5 ankastre-ankastre."""
    I, _, A = _section(shape, **dims)
    P = math.pi ** 2 * E_gpa * 1000 * I / (K * L_mm) ** 2
    return {"P_cr_n": round(P, 1), "sigma_cr_mpa": round(P / A, 2),
            "slenderness": round(K * L_mm / math.sqrt(I / A), 1),
            "note": "σ_cr akmaya yakın/üstünde ise Johnson eğrisi kullan."}
