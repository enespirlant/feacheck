"""L-braket üreticisi: R0/R5 mevcut STEP ölçüleriyle aynı, R serisi hacmi analitikle tutarlı."""
import math
import sys
from pathlib import Path

import pytest

pytest.importorskip("cadquery")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
from make_lbraket import W, lbraket  # noqa: E402


@pytest.mark.parametrize("r", [0, 1, 2, 5])
def test_hacim_analitik(r):
    # Dolgu hacmi: (R² − πR²/4)·W; R5 için 42160,95 = mevcut L_braket_R5.step
    beklenen = 42000.0 + r * r * (1 - math.pi / 4) * W
    assert lbraket(r).val().Volume() == pytest.approx(beklenen, abs=0.01)


def test_radyus_yuzu():
    s = lbraket(2).val()
    cyl = [f for f in s.Faces() if f.geomType() == "CYLINDER"]
    assert len(cyl) == 1 and cyl[0].Area() == pytest.approx(math.pi / 2 * 2 * W, rel=1e-6)
