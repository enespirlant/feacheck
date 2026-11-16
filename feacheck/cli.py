"""feacheck komut satırı.

  feacheck setup                        Mechanical butonu + masaüstü kısayolu kur (bir kez)
  feacheck init                         bu klasörü feacheck projesi yap
  feacheck converge model.mechdb        yakınsama + tekillik + GCI + denge + rapor
  feacheck log                          geçmiş kontroller
  feacheck show <id>                    bir kontrolün özeti / raporu aç
"""
from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

from . import __version__
from .store import Store


def _sizes(s):
    return [float(x) for x in s.split(",")] if s else None


def _num(text: str) -> float:
    """Ondalık virgülü de kabul eden sayı ('250,5' -> 250.5)."""
    return float(str(text).strip().replace(",", "."))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="feacheck", description="Ansys Mechanical sonuç doğrulama aracı")
    ap.add_argument("--version", action="version", version=f"feacheck {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("setup", help="Mechanical butonu ve masaüstü kısayolunu kur (bir kez)")
    sub.add_parser("init", help="bu klasörü feacheck projesi yap")
    sub.add_parser("build-button", help="(buton kullanır) güncel buton scriptini üret")
    sub.add_parser("build-selftest", help="(öz test butonu kullanır) güncel öz test scriptini üret")
    kt = sub.add_parser("katalog", help="(öz test butonu kullanır) öz test sonuçlarını değerlendir")
    kt.add_argument("folder", help="katalog_<tarih> klasörü")
    kt.add_argument("--no-open", action="store_true", help="tarayıcıda açma")
    fz = sub.add_parser("finalize", help="(Mechanical butonu kullanır) ham sonucu raporla")
    fz.add_argument("raw")
    fz.add_argument("--yield", dest="yield_mpa", type=_num)
    fz.add_argument("--tol", type=float, default=None)
    fz.add_argument("--materials-xml", default=None)
    fz.add_argument("--yield-source", default=None)
    fz.add_argument("--no-open", action="store_true")

    c = sub.add_parser("converge", help="mesh yakınsaması ve doğrulama")
    c.add_argument("model", help=".mechdb dosyası (Mechanical'da File > Save Project As > .mechdb)")
    c.add_argument("--analysis", help="analiz adı (varsayılan: ilk analiz)")
    c.add_argument("--sizes", help="eleman boyutları mm, kabadan inceye: 6,4,2.67 (varsayılan: otomatik)")
    c.add_argument("--exclude", type=float, help="tekillik dışlama mesafesi mm (varsayılan: otomatik)")
    c.add_argument("--max-nodes", type=int, help="düğüm limiti (varsayılan: ayarlar.yaml, öğrenci lisansı 128000)")
    c.add_argument("--yield", dest="yield_mpa", type=_num, help="akma dayanımı MPa (GK hesabı için)")
    c.add_argument("--tol", type=float, help="GCI eşiği %% (varsayılan: ayarlar.yaml, 5)")
    c.add_argument("--version-ansys", type=int, default=241, help="Ansys sürümü: 241, 242, 251...")
    c.add_argument("--gui", action="store_true", help="Mechanical penceresini göster")
    c.add_argument("--no-open", action="store_true", help="raporu tarayıcıda açma")

    lg = sub.add_parser("log", help="geçmiş kontroller")
    lg.add_argument("-n", type=int, default=15)
    sh = sub.add_parser("show", help="bir kontrolü göster")
    sh.add_argument("id")
    a = ap.parse_args(argv)

    if a.cmd == "setup":
        from .app import setup
        r = setup()
        print(f"""
feacheck kuruldu.

1) Mechanical butonu (önerilen):
   Mechanical > Automation > Scripting penceresine şu satırı yapıştırıp Run'a bas
   (önce ağaçta kontrol etmek istediğin analizi seç):

   {r['one_liner']}

   Kalıcı buton yapmak için aynı satırı Automation > Manage (User Buttons) ile bir butona kaydedebilirsin.

   Öz test (hata kataloğu; modeli bilerek bozar, her vakayı koşar, geri alır; ~6 koşu sürer):

   {r['oztest_one_liner']}

2) Sürükle-bırak: bir .mechdb dosyasını şu dosyanın üzerine bırak:
   {r['bat']}

Raporlar ve geçmiş: {r['home']}   (feacheck log ile listele)
""")
        return
    if a.cmd == "build-button":
        from .app import build_button
        build_button()
        return 0
    if a.cmd == "build-selftest":
        from .app import build_selftest
        build_selftest()
        return 0
    if a.cmd == "katalog":
        from .selftest import run_catalog
        out = run_catalog(Path(a.folder), open_browser=not a.no_open)
        print(out)
        return
    if a.cmd == "init":
        print(Store(Path.cwd()).init())
        return
    if a.cmd == "finalize":
        from .app import finalize_file
        rid, html, res = finalize_file(Path(a.raw), yield_mpa=a.yield_mpa, tol=a.tol, open_browser=not a.no_open,
                                       materials_xml=Path(a.materials_xml) if a.materials_xml else None,
                                       yield_source=a.yield_source)
        _print_summary(rid, res, html)
        return
    store = Store.find_or_default()
    if a.cmd == "converge":
        from .converge import run_converge
        from .report import write
        res = run_converge(Path(a.model), version=a.version_ansys, analysis=a.analysis, sizes=_sizes(a.sizes),
                           exclusion_mm=a.exclude, max_nodes=a.max_nodes, yield_mpa=a.yield_mpa,
                           gci_tol_pct=a.tol, show_gui=a.gui)
        rid, folder = store.save(res)
        html = write(res, folder / "report.html")
        _print_summary(rid, res, html)
        if not a.no_open:
            webbrowser.open(html.as_uri())
        return
    if a.cmd == "log":
        for e in store.log(a.n):
            print(f"{e['id']}  {e['timestamp']}  {e['model']:<28} {e['summary']}")
        return
    if a.cmd == "show":
        res, folder = store.get(a.id)
        _print_summary(a.id, res, folder / "report.html")
        webbrowser.open((folder / "report.html").as_uri())


def _print_summary(rid, res, html):
    ds = res.get("design_stress")
    print(f"\nfeacheck {rid}")
    if res.get("errors"):
        print("  HATA:", "; ".join(res["errors"]))
    if res.get("singularity", {}).get("detected"):
        print("  ! Maksimum gerilme TEKİLLİK (mesnet/yük yüzeyinde), tasarım değeri değil")
    if ds:
        print(f"  Tasarım gerilmesi: {ds['value_mpa']:.4g} MPa ({ds['verdict']}, GCI %{ds.get('gci_pct')})"
              + (f", GK {ds['safety_factor']}" if ds.get("safety_factor") else ""))
    d = res.get("quantities", {}).get("max_deformation", {})
    if d.get("values"):
        print(f"  Maks. deformasyon: {d['values'][-1]:.4g} mm ({d.get('verdict')})")
    if res.get("equilibrium"):
        print(f"  Denge hatası: %{res['equilibrium']['error_pct']}")
    for f in res.get("findings", []):
        print("  -", f)
    print(f"  Rapor: {html}")


if __name__ == "__main__":
    main()
