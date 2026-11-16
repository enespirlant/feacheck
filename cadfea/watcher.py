"""inbox klasörünü izler; yeni STEP/Parasolid düştüğünde analiz başlatır."""
from __future__ import annotations

import time
from pathlib import Path

from .runner import MechanicalSession, analyze


def _stable(p: Path, wait: float = 1.5) -> bool:
    """CAD export'u bitene kadar bekle (dosya boyutu değişmeyi bırakınca)."""
    try:
        a = p.stat().st_size
        time.sleep(wait)
        return a > 0 and a == p.stat().st_size
    except FileNotFoundError:
        return False


def watch(cfg: dict, poll_s: float = 2.0):
    inbox = Path(cfg["paths"]["inbox"])
    inbox.mkdir(parents=True, exist_ok=True)
    done = inbox / "processed"
    done.mkdir(exist_ok=True)
    exts = {e.lower() for e in cfg["geometry"]["formats"]}
    session = None
    if cfg["ansys"]["mode"] != "script_only":
        session = MechanicalSession(int(cfg["ansys"]["version"]), bool(cfg["ansys"]["show_gui"]))
    print(f"İzleniyor: {inbox}  (çıkmak için Ctrl+C)")
    try:
        while True:
            for p in sorted(inbox.iterdir()):
                if not (p.is_file() and p.suffix.lower() in exts and _stable(p)):
                    continue
                print(f"\n>> {p.name} analiz ediliyor...")
                try:
                    s = analyze(p, cfg, session=session)
                    print(_line(s))
                except Exception as e:  # izleyici çökmesin
                    print(f"   HATA: {e}")
                for f in (p, p.with_suffix(".yaml")):
                    if f.exists():
                        target = done / f.name
                        if target.exists():
                            target = done / f"{f.stem}_{int(time.time())}{f.suffix}"
                        f.rename(target)
            time.sleep(poll_s)
    except KeyboardInterrupt:
        pass
    finally:
        if session:
            session.close()


def _line(s: dict) -> str:
    if s.get("status") == "script_ready":
        return f"   script hazır: {s['dir']}"
    if not s.get("ok"):
        return f"   HATA: {s.get('errors')}"
    out = (f"   σvM={s.get('max_von_mises_mpa'):.4g} MPa  δ={s.get('max_deformation_mm'):.4g} mm  "
           f"GK={s.get('safety_factor')}  -> {s['dir']}")
    for w in s.get("warnings", []):
        out += f"\n   ! {w}"
    return out
