"""Küçük malzeme veritabanı (oda sıcaklığı, tipik/minimum değerler).

Kaynak: MMPDS / üretici veri sayfaları / EN standartlarındaki tipik değerler.
Tasarım onayı için firmanın kendi malzeme kartını ve A/B-basis değerlerini kullan.
"""
from __future__ import annotations

# E [GPa], nu, rho [kg/m3], sy [MPa] akma, su [MPa] çekme
MATERIALS = {
    "Structural Steel": dict(E=200, nu=0.30, rho=7850, sy=250, su=460, ansys="Structural Steel",
                             note="Ansys varsayılanı"),
    "S235":        dict(E=210, nu=0.30, rho=7850, sy=235, su=360, note="EN 10025, t<=16 mm"),
    "S355":        dict(E=210, nu=0.30, rho=7850, sy=355, su=470, note="EN 10025, t<=16 mm"),
    "C45":         dict(E=210, nu=0.30, rho=7850, sy=340, su=620, note="normalize"),
    "42CrMo4-QT":  dict(E=210, nu=0.30, rho=7850, sy=650, su=900, note="ıslah, çapa göre değişir"),
    "AISI304":     dict(E=193, nu=0.29, rho=8000, sy=215, su=505, note="tavlı"),
    "Al6061-T6":   dict(E=68.9, nu=0.33, rho=2700, sy=276, su=310),
    "Al7075-T6":   dict(E=71.7, nu=0.33, rho=2810, sy=503, su=572),
    "Al2024-T3":   dict(E=73.1, nu=0.33, rho=2780, sy=345, su=483),
    "AlSi10Mg-AM": dict(E=70, nu=0.33, rho=2670, sy=230, su=350,
                        note="LPBF, gerilim giderilmiş, yöne bağlı; üretici verisini kullan"),
    "Ti6Al4V":     dict(E=113.8, nu=0.34, rho=4430, sy=880, su=950),
    "Ti6Al4V-AM":  dict(E=110, nu=0.34, rho=4430, sy=900, su=1000,
                        note="LPBF + HIP tipik; yorulma dövme malzemeden düşük"),
    "PA12-SLS":    dict(E=1.7, nu=0.40, rho=1010, sy=45, su=48, note="izotrop değil, yaklaşık"),
    "PLA":         dict(E=3.5, nu=0.36, rho=1240, sy=50, su=55, note="FDM, baskı yönüne çok bağlı"),
}

E_STRUCTURAL_STEEL = 200.0


def get(name: str) -> dict:
    key = next((k for k in MATERIALS if k.lower() == str(name).lower()), None)
    if key is None:
        raise KeyError(f"'{name}' yok. Mevcut: {', '.join(MATERIALS)}")
    return {"name": key, **MATERIALS[key]}


def table() -> list[dict]:
    return [{"name": k, **v} for k, v in MATERIALS.items()]
