"""L-braket STEP üretici (radyus serisi için).

Ölçüler mevcut parts/L_braket_R5.step'ten ölçüldü: yatay kol 80×10, dikey kol 10×70 (XZ düzlemi),
genişlik 30 (Y), iç köşe (10, 10)'da. R = 0 keskin köşe verir.

Kullanım:  python examples/make_lbraket.py [R ...] [--out KLASOR]
Varsayılan: R1 ve R2, C:/Users/pirla/feacheck/parts altına (veya --out).
"""
from __future__ import annotations

import argparse
from pathlib import Path

L_YATAY, L_DIKEY, T, W = 80.0, 70.0, 10.0, 30.0


def lbraket(r: float):
    import cadquery as cq

    prof = (cq.Workplane("XZ")
            .polyline([(0, 0), (L_YATAY, 0), (L_YATAY, T), (T, T), (T, L_DIKEY), (0, L_DIKEY)])
            .close()
            .extrude(-W))  # XZ normali -Y; -W ile gövde y = 0..30 aralığına düşer
    if r > 0:
        prof = prof.edges("|Y").edges(cq.selectors.NearestToPointSelector((T, W / 2, T))).fillet(r)
    return prof


def ad(r: float) -> str:
    return "L_braket_keskin" if r == 0 else f"L_braket_R{r:g}"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("r", nargs="*", type=float, default=[1.0, 2.0])
    ap.add_argument("--out", type=Path, default=Path(r"C:/Users/pirla/feacheck/parts"))
    a = ap.parse_args(argv)
    import cadquery as cq

    a.out.mkdir(parents=True, exist_ok=True)
    for r in a.r:
        p = a.out / f"{ad(r)}.step"
        cq.exporters.export(lbraket(r), str(p))
        print(f"{p}  V = {lbraket(r).val().Volume():.2f} mm3")


if __name__ == "__main__":
    main()
