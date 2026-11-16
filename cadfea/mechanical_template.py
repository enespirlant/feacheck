"""Ansys Mechanical içinde çalışan script şablonu.

DİKKAT: Bu metin Mechanical'ın kendi Python'unda (IronPython 2.7 / CPython) çalışır.
f-string, type hint, pathlib KULLANMA. Sadece % formatlama.
Aynı script'i Mechanical > Automation > Scripting penceresine yapıştırıp elle de çalıştırabilirsin.
"""

TEMPLATE = r'''
# ===== CAD-FEA Bridge - otomatik uretilmis Mechanical scripti =====
# Not: os modulu bilerek kullanilmiyor (IronPython'da types.py hatasi verebiliyor).
def pj(a, b):
    return a.rstrip("\\/") + "\\" + b


# Not: IronPython'da json modulu (_json) bazen yok; bu yuzden ayarlar Python
# literal'i olarak gomulur ve sonuc kendi yazdigimiz tojson ile yazilir.
CFG = __CFG_LITERAL__
# CFG_END
OUT = CFG["out_dir"]


def _jstr(s):
    out = []
    for ch in s:
        o = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == '\\':
            out.append('\\\\')
        elif o < 32 or o > 126:
            out.append('\\u%04x' % o)
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


try:
    _STR = basestring  # IronPython 2.7
except NameError:
    _STR = str


def tojson(o, ind=""):
    """Hata firlatmayan JSON yazici (editor yakalanan hatalarda bile duruyor)."""
    if o is None:
        return "null"
    if o is True:
        return "true"
    if o is False:
        return "false"
    if isinstance(o, _STR):
        return _jstr(o)
    if isinstance(o, dict):
        n = ind + "  "
        items = [n + _jstr(str(k)) + ": " + tojson(v, n) for k, v in o.items()]
        return "{\n" + ",\n".join(items) + "\n" + ind + "}" if items else "{}"
    if isinstance(o, (list, tuple)):
        return "[" + ", ".join([tojson(v, ind) for v in o]) + "]"
    if isinstance(o, float):
        if o != o or o in (float("inf"), float("-inf")):
            return "null"
        return repr(o)
    if isinstance(o, int):
        return str(o)
    t = type(o).__name__
    if t in ("Int16", "Int64", "UInt16", "UInt32", "UInt64", "long", "Decimal"):
        return str(o)
    if t in ("Single", "Double"):
        return repr(float(str(o).replace(",", ".")))
    return _jstr(str(o))


R = {"ok": False, "errors": [], "warnings": [], "scopes": [], "steps": []}


def step(msg):
    R["steps"].append(msg)
    print("[cadfea] " + msg)


def warn(msg):
    R["warnings"].append(msg)
    print("[cadfea] UYARI: " + msg)


def fail(msg):
    """Hata firlatmadan durur (Mechanical editoru yakalanan hatalarda bile duruyor)."""
    R["errors"].append(msg)
    print("[cadfea] HATA: " + msg)
    return False


def dump():
    f = open(pj(OUT, "result_raw.json"), "w")
    f.write(tojson(R))
    f.close()


AX = {"x": 0, "y": 1, "z": 2}
STD_SCALES = (1000.0, 1.0, 25.4, 10.0, 0.001, 304.8)


def all_faces():
    out = []
    for asm in DataModel.GeoData.Assemblies:
        for part in asm.Parts:
            for body in part.Bodies:
                for f in body.Faces:
                    out.append(f)
    return out


def surf_type(f):
    t = str(f.SurfaceType)
    if "Plane" in t:
        return "plane"
    if "Cylinder" in t:
        return "cylinder"
    return "other"


def model_scale(faces):
    """Model birimini mm'ye ceviren carpan; standart degere yakinsa ona yapistirilir."""
    s = None
    ref_v = CFG.get("ref_volume_mm3")
    if ref_v:
        v = 0.0
        for asm in DataModel.GeoData.Assemblies:
            for part in asm.Parts:
                for body in part.Bodies:
                    v += body.Volume
        if v > 0:
            s = (ref_v / v) ** (1.0 / 3.0)
    if s is None and CFG.get("ref_span_mm"):
        sp = 0.0
        for i in range(3):
            vals = [f.Centroid[i] for f in faces]
            sp = max(sp, max(vals) - min(vals))
        s = CFG["ref_span_mm"] / (sp or 1.0)
    if s is None:
        return 1.0
    for cand in STD_SCALES:
        if abs(s / cand - 1.0) < 0.02:
            return cand
    warn("model birimi standart degil: %s" % s)
    return s


def cleanup_previous():
    """Onceki cadfea kosusundan kalan AUTO_ secimleri ve CADFEA analizlerini siler."""
    n = 0
    if Model.NamedSelections is not None:
        for ns in list(Model.NamedSelections.Children):
            if ns.Name.startswith("AUTO_"):
                ns.Delete()
                n += 1
    for a in list(Model.Analyses):
        if a.Name.startswith("CADFEA"):
            a.Delete()
            n += 1
    if n:
        step("onceki kosudan %d nesne silindi" % n)


def main():
    ExtAPI.Application.ActiveUnitSystem = MechanicalUnitSystem.StandardNMM
    cleanup_previous()

    # ---- Geometri
    if len(Model.Geometry.GetChildren(DataModelObjectCategory.Body, True)) > 0:
        step("modeldeki mevcut geometri kullanildi")
    else:
        gi = Model.GeometryImportGroup.AddGeometryImport()
        fmt = Ansys.Mechanical.DataModel.Enums.GeometryImportPreference.Format.Automatic
        prefs = Ansys.ACT.Mechanical.Utilities.GeometryImportPreferences()
        prefs.ProcessNamedSelections = True
        prefs.NamedSelectionKey = CFG["named_selection_prefix"]
        gi.Import(CFG["geometry_path"], fmt, prefs)
        step("geometri alindi")
    bodies = Model.Geometry.GetChildren(DataModelObjectCategory.Body, True)
    R["body_count"] = len(bodies)
    if len(bodies) == 0:
        return fail("Geometride govde yok. STEP export'unu kontrol et.")
    if len(bodies) > 1:
        warn("%d govde var. Tek parca bekleniyordu; ust uste binmis kopya olabilir." % len(bodies))

    # ---- Malzeme ve kutle
    if CFG.get("material_xml"):
        Model.Materials.Import(CFG["material_xml"])
    for b in bodies:
        b.Material = CFG["material_name"]
    m = 0.0
    for b in bodies:
        m += b.Mass.Value
    R["mass_value"] = m
    R["mass_unit"] = str(bodies[0].Mass.Unit)
    step("malzeme: %s" % CFG["material_name"])

    # ---- Yuz eslestirme
    faces = all_faces()
    scale = model_scale(faces)
    R["model_to_mm"] = scale
    span = CFG.get("ref_span_mm") or 100.0
    mtol = max(float(CFG.get("match_tol_mm", 0.05)), 1e-3 * span)
    R["match_tol_mm"] = mtol

    def cmm(f):
        c = f.Centroid
        return [c[0] * scale, c[1] * scale, c[2] * scale]

    def inside(c, p):
        if "bbox_min" not in p:
            return True
        for i in range(3):
            if c[i] < p["bbox_min"][i] - mtol or c[i] > p["bbox_max"][i] + mtol:
                return False
        return True

    def matches(f, p):
        st = surf_type(f)
        c = cmm(f)
        if p["kind"] == "plane":
            if st != "plane":
                return False
            n = p["normal"]
            d = sum([(c[i] - p["point"][i]) * n[i] for i in range(3)])
            return abs(d) <= mtol and inside(c, p)
        if p["kind"] == "cylinder":
            if st != "cylinder":
                return False
            a = p["axis_dir"]
            rel = [c[i] - p["axis_point"][i] for i in range(3)]
            t = sum([rel[i] * a[i] for i in range(3)])
            rad2 = sum([r * r for r in rel]) - t * t
            rad = rad2 ** 0.5 if rad2 > 0 else 0.0
            lo, hi = p["axial_range"]
            return rad <= p["radius"] + mtol and lo - mtol <= t <= hi + mtol
        return inside(c, p)

    def extreme_faces(axis, side, tol):
        i = AX[axis]
        vals = [cmm(f)[i] for f in faces]
        lo, hi = min(vals), max(vals)
        target = lo if side == "min" else hi
        return [f.Id for f, v in zip(faces, vals)
                if abs(v - target) <= tol * ((hi - lo) or 1.0) and surf_type(f) == "plane"]

    counter = {"n": 0}

    def make_scope(spec, tag):
        if "named_selection" in spec:
            for ns in (Model.NamedSelections.Children if Model.NamedSelections else []):
                if ns.Name == spec["named_selection"]:
                    R["scopes"].append({"tag": tag, "source": "named_selection", "name": ns.Name})
                    return ns
            fail("Named selection bulunamadi: %s" % spec["named_selection"])
            return None
        if "geo" in spec:
            ids = []
            for f in faces:
                for p in spec["geo"]:
                    if matches(f, p):
                        ids.append(f.Id)
                        break
            expected = len(spec["geo"])
        else:
            ids = extreme_faces(spec["axis"], spec["side"], float(spec.get("tol", 0.01)))
            expected = None
        if len(ids) == 0:
            fail("%s icin yuz bulunamadi (%s). Birim carpani=%s, tol=%s mm"
                 % (tag, spec.get("source", spec), scale, mtol))
            return None
        if expected and len(ids) < expected:
            warn("%s: %d yuz beklendi, %d eslesti" % (tag, expected, len(ids)))
        sel = ExtAPI.SelectionManager.CreateSelectionInfo(SelectionTypeEnum.GeometryEntities)
        sel.Ids = ids
        counter["n"] += 1
        ns = Model.AddNamedSelection()
        ns.Location = sel
        ns.Name = "AUTO_%s_%d" % (tag, counter["n"])
        R["scopes"].append({"tag": tag, "name": ns.Name, "face_count": len(ids), "expected": expected,
                            "rule": spec.get("source", spec)})
        step("%s -> %d yuz" % (ns.Name, len(ids)))
        return ns

    # Once tum kapsamlari coz; biri bile bulunamazsa analiz kurmadan dur
    loads = CFG["loads"]
    fix_locs = [make_scope(sp, "FIX") for sp in (loads.get("fixed") or [])]
    force_locs = [make_scope(ld["scope"], "FORCE") for ld in (loads.get("forces") or [])]
    press_locs = [make_scope(ld["scope"], "PRESS") for ld in (loads.get("pressures") or [])]
    if None in fix_locs + force_locs + press_locs:
        return False

    # ---- Analiz
    analysis = Model.AddStaticStructuralAnalysis()
    analysis.Name = "CADFEA Static"
    for loc in fix_locs:
        analysis.AddFixedSupport().Location = loc
    for ld, loc in zip(loads.get("forces") or [], force_locs):
        fc = analysis.AddForce()
        fc.Location = loc
        fc.DefineBy = LoadDefineBy.Components
        c = ld["components_n"]
        fc.XComponent.Output.DiscreteValues = [Quantity("%s [N]" % c[0])]
        fc.YComponent.Output.DiscreteValues = [Quantity("%s [N]" % c[1])]
        fc.ZComponent.Output.DiscreteValues = [Quantity("%s [N]" % c[2])]
    for ld, loc in zip(loads.get("pressures") or [], press_locs):
        pr = analysis.AddPressure()
        pr.Location = loc
        pr.Magnitude.Output.DiscreteValues = [Quantity("%s [MPa]" % ld["mpa"])]
    step("sinir sartlari kuruldu")

    sol = analysis.Solution
    eqv = sol.AddEquivalentStress()
    dfm = sol.AddTotalDeformation()
    R["runs"] = []
    for size in CFG["mesh_sizes"]:
        mesh = Model.Mesh
        mesh.ElementSize = Quantity("%s [mm]" % size)
        mesh.GenerateMesh()
        sol.Solve(True)
        r = {"element_size_mm": size, "nodes": mesh.Nodes, "elements": mesh.Elements,
             "solution_state": str(sol.ObjectState),
             "max_von_mises": eqv.Maximum.Value, "max_von_mises_unit": str(eqv.Maximum.Unit),
             "max_deformation": dfm.Maximum.Value, "max_deformation_unit": str(dfm.Maximum.Unit)}
        R["runs"].append(r)
        dump()
        step("cozuldu %s mm: vM=%.4g %s, def=%.4g %s, dugum=%s" % (
            size, r["max_von_mises"], r["max_von_mises_unit"],
            r["max_deformation"], r["max_deformation_unit"], r["nodes"]))

    if CFG.get("export_images"):
        st = Ansys.Mechanical.Graphics.GraphicsImageExportSettings()
        st.Width = 1280
        st.Height = 720
        for obj, name in ((eqv, "von_mises.png"), (dfm, "deformation.png")):
            obj.Activate()
            Graphics.Camera.SetFit()
            Graphics.ExportImage(pj(OUT, name), GraphicsImageExportFormat.PNG, st)
        R["images"] = ["von_mises.png", "deformation.png"]
    if CFG.get("save_mechdb"):
        ExtAPI.DataModel.Project.Save(pj(OUT, "model.mechdb"))
        R["mechdb"] = "model.mechdb"
    return True


R["ok"] = bool(main())
dump()
print("[cadfea] BITTI" if R["ok"] else "[cadfea] DURDU - hatalar: %s" % R["errors"])
'''
