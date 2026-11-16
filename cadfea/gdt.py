"""GD&T yardımcıları (ASME Y14.5-2018 / ISO 1101 mantığı)."""
from __future__ import annotations

SYMBOLS = {
    "flatness": ("⏥", "Düzlemsellik", "form", False),
    "straightness": ("⏤", "Doğrusallık", "form", False),
    "circularity": ("○", "Dairesellik", "form", False),
    "cylindricity": ("⌭", "Silindiriklik", "form", False),
    "perpendicularity": ("⟂", "Diklik", "yönelim", True),
    "parallelism": ("∥", "Paralellik", "yönelim", True),
    "angularity": ("∠", "Açısallık", "yönelim", True),
    "position": ("⌖", "Pozisyon", "konum", True),
    "profile_surface": ("⌓", "Yüzey profili", "profil", None),
    "circular_runout": ("↗", "Dairesel salgı", "salgı", True),
    "total_runout": ("⌰", "Toplam salgı", "salgı", True),
}


def symbols() -> list[dict]:
    return [{"key": k, "symbol": s, "tr": tr, "family": fam,
             "datum": {True: "gerekli", False: "kullanılmaz", None: "opsiyonel"}[dr]}
            for k, (s, tr, fam, dr) in SYMBOLS.items()]


def fastener_position(hole_d_mm: float, fastener_d_mm: float, fixed: bool = False,
                      hole_tol_mm: float = 0.0) -> dict:
    """Cıvata deliği pozisyon toleransı.

    Floating fastener (her iki parçada da açık delik): T = H - F
    Fixed fastener (bir parçada dişli/pimli):          T = (H - F) / 2  (her parçaya)
    MMC değiştiricisiyle, delik büyüdükçe bonus tolerans eklenir.
    """
    T = hole_d_mm - fastener_d_mm
    if fixed:
        T /= 2
    if T <= 0:
        raise ValueError("Delik çapı cıvata çapından büyük olmalı")
    fcf = f"|⌖|Ø{T:.3f} Ⓜ|A|B|C|"
    out = {"position_tol_at_mmc_mm": round(T, 4), "feature_control_frame": fcf,
           "case": "fixed fastener" if fixed else "floating fastener",
           "note": "Delik MMC'de (en küçük çapta) tolerans T; delik büyüdükçe bonus tolerans eklenir."}
    if hole_tol_mm:
        out["max_with_bonus_mm"] = round(T + hole_tol_mm, 4)
    return out


def recommend(feature: str) -> dict:
    """Özellik tipine göre tipik GD&T çağrısı (başlangıç önerisi)."""
    rec = {
        "mating_plane": ["Datum A olarak tanımla", "flatness 0.02-0.05 (işlenmiş yüz)"],
        "bolt_pattern": ["position Ø(H-F) Ⓜ |A|B|C|", "MMC ile fonksiyonel mastar mümkün"],
        "bearing_seat": ["cylindricity 0.005-0.01", "circular_runout A-B ortak eksene göre",
                         "geçme: H7/k6 (iç bilezik dönen yük) veya H7/g6 (kayar)"],
        "shaft_journal": ["circular_runout 0.01-0.02 |A-B|", "Ra 0.4-0.8"],
        "locating_pin_hole": ["position Ø0.02-0.05 |A|B|", "geçme H7/m6 (pim)"],
        "sheet_profile": ["profile_surface 0.5 |A|B|C|"],
    }
    if feature not in rec:
        raise ValueError(f"Seçenekler: {', '.join(rec)}")
    return {"feature": feature, "suggestions": rec[feature],
            "note": "Tipik başlangıç değerleri; tolerans fonksiyon ve imalat kabiliyetine göre seçilir."}
