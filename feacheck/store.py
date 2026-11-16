"""Git'teki .git gibi: proje klasöründe .feacheck/ altında her kontrolün kaydı."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path


class Store:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.dir = self.root / ".feacheck"

    @classmethod
    def default(cls) -> "Store":
        """Proje klasörü dışındaki kontroller: %USERPROFILE%\\feacheck"""
        return cls(Path.home() / "feacheck")

    @classmethod
    def find_or_default(cls) -> "Store":
        p = Path.cwd()
        for q in [p, *p.parents]:
            if (q / ".feacheck").is_dir():
                return cls(q)
        return cls.default()

    find_or_here = find_or_default

    def init(self) -> str:
        new = not self.dir.exists()
        (self.dir / "runs").mkdir(parents=True, exist_ok=True)
        return f"{'Oluşturuldu' if new else 'Zaten var'}: {self.dir}"

    def save(self, res: dict) -> tuple[str, Path]:
        (self.dir / "runs").mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        rid = hashlib.sha1((stamp + res.get("model", "")).encode()).hexdigest()[:7]
        folder = self.dir / "runs" / rid
        k = 1
        while folder.exists():                      # aynı saniyede aynı model: çakışmayı önle
            folder = self.dir / "runs" / f"{rid}-{k}"
            k += 1
        rid = folder.name
        folder.mkdir()
        (folder / "result.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
        ds = res.get("design_stress") or {}
        summary = ("HATA" if res.get("errors") else
                   f"{ds.get('value_mpa', '–')} MPa"
                   + (" (tekillik ayrıldı)" if res.get("singularity", {}).get("detected") else "")
                   + (f" GK {ds['safety_factor']}" if ds.get("safety_factor") else ""))
        entry = {"id": rid, "timestamp": res.get("timestamp", stamp), "model": Path(res.get("model", "?")).name,
                 "summary": summary}
        with open(self.dir / "log.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return rid, folder

    def log(self, n: int = 15) -> list[dict]:
        f = self.dir / "log.jsonl"
        if not f.exists():
            return []
        lines = f.read_text(encoding="utf-8").splitlines()
        return [json.loads(x) for x in reversed(lines[-n:])]

    def get(self, rid: str) -> tuple[dict, Path]:
        matches = [p for p in (self.dir / "runs").glob(f"{rid}*") if p.is_dir()]
        if not matches:
            raise SystemExit(f"Bulunamadı: {rid}")
        folder = matches[0]
        return json.loads((folder / "result.json").read_text(encoding="utf-8")), folder
