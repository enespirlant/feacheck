"""feacheck converge: mevcut bir Mechanical modelinde yakınsama + doğrulama."""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from cadfea.script_builder import pylit

from .analysis import evaluate
from .mech_converge import TEMPLATE

PROBE = r'''
Model = ExtAPI.DataModel.Project.Model
ExtAPI.Application.ActiveUnitSystem = MechanicalUnitSystem.StandardNMM
v = 0.0
n = 0
for b in Model.Geometry.GetChildren(DataModelObjectCategory.Body, True):
    if not b.Suppressed:
        v += float(b.Volume.Value)
        n += 1
names = [a.Name for a in Model.Analyses]
"%s|%s|%s" % (v, n, ";".join(names))
'''


def auto_sizes(volume_mm3: float, levels: int = 3, ratio: float = 1.5) -> tuple[list[float], float]:
    """Kaba tahmin (yalnızca bilgi için): Lc = V^(1/3), h0 = Lc/8, her seviyede /ratio, dışlama Lc/2.
    Gerçek koşuda boyutları Mechanical şablonu kalınlık sınırıyla, dışlamayı √A kuralıyla hesaplar."""
    lc = volume_mm3 ** (1 / 3)
    h0 = lc / 8
    return [round(h0 / ratio ** i, 3) for i in range(levels)], round(lc / 2, 2)


def run_converge(model: Path, *, version: int, analysis: str | None = None, sizes: list[float] | None = None,
                 exclusion_mm: float | None = None, max_nodes: int | None = None, yield_mpa: float | None = None,
                 gci_tol_pct: float | None = None, show_gui: bool = False, session=None,
                 settings: dict | None = None, log=print) -> dict:
    from .app import load_settings, template_cfg
    st = settings or load_settings()
    if gci_tol_pct is None:
        gci_tol_pct = st["gci_tol_pct"]
    model = Path(model).resolve()
    own = session is None
    if session is None:
                session = MechanicalSession(version, show_gui)
    t0 = time.time()
    try:
        log(f"Ansys açılıyor ve model yükleniyor: {model.name}")
        session.run(f'ExtAPI.DataModel.Project.Open(r"{model}")')
        vol, nb, names = session.run(PROBE).split("|")
        vol = float(vol)
        if vol <= 0 or not names:
            raise SystemExit(f"Model açılamadı veya boş (hacim={vol}, analizler='{names}'). "
                             "Dosyanın Mechanical'da File > Save Project As ile .mechdb kaydedildiğinden emin ol.")
        # Boyutlar/dışlama verilmezse şablon butondakiyle aynı kuralla hesaplar (kalınlık sınırı, √A).
        cfg = template_cfg(st, analysis=analysis, sizes=sizes, exclusion_mm=exclusion_mm, max_nodes=max_nodes)
        log(f"Analizler: {names} | mesh seviyeleri: {sizes or 'otomatik'} mm | "
            f"dışlama: {exclusion_mm if exclusion_mm is not None else 'otomatik (√A)'} mm")
        log("Çözülüyor (her seviye birkaç dakika sürebilir)...")
        raw = json.loads(session.run(TEMPLATE.replace("__CFG_LITERAL__", pylit(cfg))))
    finally:
        if own:
            session.close()
    used = raw.get("settings_used", {})
    for k in ("exclusion_mm", "exclusion_rule", "sizes_mm"):
        if used.get(k) is not None:
            cfg[k] = used[k]
    ev_cfg = {**cfg, "gci_tol_pct": gci_tol_pct, "yield_mpa": yield_mpa, "model_size_mm": vol ** (1 / 3)}
    result = evaluate(raw, ev_cfg)
    result.update({"model": str(model), "volume_mm3": vol, "settings": ev_cfg,
                   "duration_s": round(time.time() - t0, 1), "timestamp": datetime.now().isoformat(timespec="seconds")})
    return result
