"""Ansys Engineering Data (MatML) XML dosyasından akma dayanımı okur.

Mechanical'da Materials > Export ile alınan XML'de yapı:
  <Material><BulkDetails><Name>Structural Steel</Name>
     <PropertyData property="pr3"> <ParameterValue parameter="pa5"><Data>2.5E+08</Data> ...
  <Metadata> <ParameterDetails id="pa5"><Name>Tensile Yield Strength</Name><Units><Unit><Name>Pa</Name>...
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

TO_MPA = {"Pa": 1e-6, "kPa": 1e-3, "MPa": 1.0, "GPa": 1e3, "psi": 0.00689476, "ksi": 6.89476}
YIELD_NAMES = ("Tensile Yield Strength", "Yield Strength")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _text(el, name):
    for ch in el.iter():
        if _local(ch.tag) == name and ch.text:
            return ch.text.strip()
    return None


def read_yields(path: Path) -> dict[str, float]:
    """{malzeme adı: akma [MPa]} döndürür."""
    root = ET.parse(path).getroot()
    params = {}
    for el in root.iter():
        if _local(el.tag) == "ParameterDetails":
            name = _text(el, "Name")
            unit = None
            for u in el.iter():
                if _local(u.tag) == "Unit":
                    unit = _text(u, "Name")
                    break
            params[el.get("id")] = (name, unit)
    out = {}
    for mat in root.iter():
        if _local(mat.tag) != "Material":
            continue
        bulk = next((c for c in mat if _local(c.tag) == "BulkDetails"), None)
        if bulk is None:
            continue
        mname = next((c.text.strip() for c in bulk if _local(c.tag) == "Name" and c.text), None)
        for pv in bulk.iter():
            if _local(pv.tag) != "ParameterValue":
                continue
            pname, unit = params.get(pv.get("parameter"), (None, None))
            if pname not in YIELD_NAMES:
                continue
            data = _text(pv, "Data")
            if not data:
                continue
            try:
                val = float(data.split(",")[0])
            except ValueError:
                continue
            k = TO_MPA.get((unit or "").strip())
            if k is None:
                k = 1e-6 if val > 1e5 else 1.0     # birim yoksa: büyük sayı -> Pa
            out[mname] = val * k
            break
    return out
