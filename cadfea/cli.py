"""Komut satırı.

python -m cadfea run inbox/aks.step [--gui] [--script-only]
python -m cadfea watch
python -m cadfea mcp
"""
from __future__ import annotations

import argparse
import json
import sys

from .config import ConfigError, load_config


def main(argv=None):
    ap = argparse.ArgumentParser(prog="cadfea")
    ap.add_argument("--config", default=None, help="config.yaml yolu")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="tek dosyayı analiz et")
    r.add_argument("file")
    r.add_argument("--gui", action="store_true", help="Mechanical penceresini göster")
    r.add_argument("--script-only", action="store_true", help="sadece Mechanical scripti üret")
    sub.add_parser("watch", help="inbox klasörünü izle")
    sub.add_parser("mcp", help="Claude için MCP sunucusunu başlat")
    a = ap.parse_args(argv)

    cfg = load_config(a.config)
    try:
        if a.cmd == "run":
            from .runner import analyze
            if a.gui:
                cfg["ansys"]["show_gui"] = True
            s = analyze(a.file, cfg, script_only=a.script_only or None)
            print(json.dumps(s, indent=2, ensure_ascii=False))
        elif a.cmd == "watch":
            from .watcher import watch
            watch(cfg)
        elif a.cmd == "mcp":
            from .mcp_server import serve
            serve(a.config)
    except ConfigError as e:
        print(f"Ayar hatası: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
