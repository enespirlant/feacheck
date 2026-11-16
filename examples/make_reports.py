"""Demo raporlarını gerçek ham sonuçlardan (tests/fixtures) yeniden üretir:  python examples/make_reports.py"""
import json, shutil, tempfile
from pathlib import Path
from feacheck.app import finalize
from feacheck.store import Store

ROOT = Path(__file__).resolve().parents[1]
CASES = {"lbraket_keskin_kose": ("lbraket_keskin_yuzbilgili.json", "L-braket, keskin iç köşe"),
         "lbraket_r5_radyus": ("lbraket_r5_buyume_12.json", "L-braket, R5 radyus"),
         "delikli_plaka": ("plaka_basinc.json", "Delikli plaka Ø10"),
         "konsol_aks": ("aks.json", "Konsol aks Ø20")}

def elhesap_yaml() -> str:
    """Demo vakalarının el hesapları; sayılar feacheck.handcalc ile hesaplanır."""
    from feacheck import handcalc as h
    aks = h.bending_round(500 * 178, 20)["value"]                       # probe kesiti, kol 178 mm
    kt = h.kt_plate_central_hole_tension(10, 50)["value"]
    plaka = kt * 10_000 / ((50 - 10) * 5)
    egilme = h.bending_rect(65_000, 30, 10)["value"] + 1000 / 300        # eğilme + eksenel (F/A)
    winkler = h.winkler_rect_inner(65_000, 5, 15, 30)["value"] + 1000 / 300
    return (f'Konsol aks:\n  deger: {aks:.1f}\n  aciklama: "σ = 32M/(πd³), M = 500 N × 178 mm (sabit nokta kesiti)"\n'
            f'Delikli plaka:\n  deger: {plaka:.1f}\n  aciklama: "Kt = {kt:.3f} (Heywood/Peterson), net kesit gerilmesi 50 MPa"\n'
            f'keskin iç köşe:\n  deger: {egilme:.1f}\n  aciklama: "Köşeden uzakta düz kesit: 6M/(bt²) + F/A, M = 65 N·m"\n'
            f'R5 radyus:\n  alt: 168\n  ust: {winkler:.0f}\n  aciklama: "Alt: kademeli düz çubuk omuz radyusu Kt ≈ 1,27 '
            f'(Peterson). Üst: Winkler eğri kiriş iç lifi {winkler:.0f} MPa (dış köşe gerçekte dolu, daha rijit)."\n')


if __name__ == "__main__":
    out = ROOT / "examples" / "reports"; out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp())
    for key in CASES:
        (tmp / key).mkdir(parents=True, exist_ok=True)
        (tmp / key / "elhesap.yaml").write_text(elhesap_yaml(), encoding="utf-8")
    for key, (fx, name) in CASES.items():
        raw = json.loads((ROOT / "tests" / "fixtures" / fx).read_text(encoding="utf-8"))
        _, html, res = finalize(raw, model_name=name, yield_mpa=250, yield_source="örnek değer",
                                store=Store(tmp / key), open_browser=False)
        shutil.copy(html, out / f"{key}.html")
        print(key, (res.get("design_stress") or {}).get("value_mpa"))
