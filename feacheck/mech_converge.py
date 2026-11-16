"""Mechanical içinde (IronPython 2.7) çalışan yakınsama scripti.

Kullanıcının kurduğu analize DOKUNMAZ: sadece global eleman boyutunu değiştirir, çözer,
sonuçları okur. Eksik sonuç nesnesi (Equivalent Stress, Total Deformation, Force Reaction)
varsa "FEACHECK_" önekiyle ekler ve sonunda siler.
Sadece ASCII, f-string yok, json modülü yok.
"""

TEMPLATE = r'''
Model = ExtAPI.DataModel.Project.Model   # Project.Open sonrasi global Model eski projeyi gosterir
DataModel = ExtAPI.DataModel
CFG = __CFG_LITERAL__
# CFG_END

try:
    _STR = basestring
except NameError:
    _STR = str


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


def tojson(o):
    if o is None:
        return "null"
    if o is True:
        return "true"
    if o is False:
        return "false"
    if isinstance(o, _STR):
        return _jstr(o)
    if isinstance(o, dict):
        return "{" + ", ".join([_jstr(str(k)) + ": " + tojson(v) for k, v in o.items()]) + "}"
    if isinstance(o, (list, tuple)):
        return "[" + ", ".join([tojson(v) for v in o]) + "]"
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


R = {"ok": False, "errors": [], "warnings": [], "levels": []}


def warn(m):
    R["warnings"].append(m)


SUPPORT_TYPES = ("FixedSupport", "Displacement", "CylindricalSupport", "FrictionlessSupport",
                 "CompressionOnlySupport", "RemoteDisplacement", "ElasticSupport")
LOAD_TYPES = ("Force", "Pressure", "Moment", "BoltPretension", "RemoteForce", "Bearing")
# Kutle/atalet ve termal yukler: denge kontrolunu atlatir, "yuk yok" uyarisini susturur.
BODY_LOAD_TYPES = ("EarthGravity", "Acceleration", "RotationalVelocity", "ThermalCondition",
                   "HydrostaticPressure", "LineForce")
# Not: Mechanical editoru yakalanan hatalarda bile duruyor; bu yuzden try/except yerine
# once kontrol (getattr, tip adi) kullaniliyor.


def num(x):
    return float(getattr(x, "Value", x))


def q_mm(qv):
    """Quantity -> sayi (aktif birim sistemi NMM)."""
    return float(qv.Value)


def active_analysis():
    """Agacta secili nesnenin ait oldugu analiz NESNESI (ayni isimli analizler karismasin)."""
    o = ExtAPI.DataModel.Tree.FirstActiveObject
    k = 0
    while o is not None and k < 20:
        if type(o).__name__ == "Analysis":
            return o
        o = getattr(o, "Parent", None)
        k += 1
    return None


def _first_number(o, depth=0):
    """Ic ice liste/sozluk icindeki ilk sayiyi ve varsa birim metnini bulur."""
    if depth > 4 or o is None:
        return None, None
    if isinstance(o, (int, float)) and not isinstance(o, bool):
        return float(o), None
    if isinstance(o, _STR):
        return None, o
    items = list(o.values()) if hasattr(o, "values") and hasattr(o, "keys") else (list(o) if hasattr(o, "__iter__") else [])
    unit = None
    for it in items:
        v, u = _first_number(it, depth + 1)
        if u and unit is None:
            unit = u
        if v is not None:
            return v, unit
    return None, unit


# Ansys Engineering Data varsayilan kutuphanesi, Tensile Yield Strength [MPa]
YIELD_LIB = {"Structural Steel": 250.0, "Aluminum Alloy": 280.0, "Titanium Alloy": 930.0,
             "Stainless Steel": 207.0, "Copper Alloy": 280.0}


def read_yield_mpa():
    """Engineering Data'dan 'Tensile Yield Strength' okur (2024R1 Material API). Bulamazsa None."""
    names = []
    for b in Model.Geometry.GetChildren(DataModelObjectCategory.Body, True):
        if not b.Suppressed:
            nm = str(b.Material)
            if nm not in names:
                names.append(nm)
    R["materials"] = names
    getter = getattr(Model.Materials, "GetEngineeringDataMaterial", None)
    matmod = getattr(getattr(Ansys, "Mechanical", None), "Material", None)
    byname = getattr(matmod, "GetMaterialPropertyByName", None) if matmod is not None else None
    if getter is None or byname is None:
        return None
    vals = []
    for nm in names:
        ed = getter(nm)
        if ed is None:
            continue
        prop = byname(ed, "Tensile Yield Strength")
        v, unit = _first_number(prop)
        if v is None:
            continue
        u = (unit or "").strip()
        if u == "Pa" or (not u and v > 1e5):
            v = v * 1e-6
        elif u in ("kPa",):
            v = v * 1e-3
        elif u in ("psi",):
            v = v * 0.00689476
        vals.append(v)
    return min(vals) if vals else None


def pick_analysis():
    name = CFG.get("analysis")
    for a in Model.Analyses:
        if name is None or a.Name == name:
            return a
    return None


def children_of(obj, typename):
    out = []
    for c in obj.Children:
        if type(c).__name__ == typename:
            out.append(c)
    return out


def bc_face_ids(analysis):
    """Mesnet/yuk nesnelerinin geometri yuz kimlikleri (tekillik bolgesi icin)."""
    ids = {}
    for c in analysis.Children:
        t = type(c).__name__
        if t not in SUPPORT_TYPES and t not in LOAD_TYPES:
            continue
        if getattr(c, "Suppressed", False):
            continue
        loc = getattr(c, "Location", None)
        if loc is not None and type(loc).__name__ == "NamedSelection":
            loc = getattr(loc, "Location", None)
        sel_ids = list(getattr(loc, "Ids", None) or []) if loc is not None else []
        for i in sel_ids:
            ids.setdefault(t, []).append(i)
    return ids


def faces_of(loc, sc, geo, limit=20):
    """Bir konum (Location/NamedSelection) icindeki yuzlerin merkezi (mm), alani, yuzey tipi ve kenar yaricaplari."""
    if loc is not None and type(loc).__name__ == "NamedSelection":
        loc = getattr(loc, "Location", None)
    ids = list(getattr(loc, "Ids", None) or []) if loc is not None else []
    faces = []
    for i in ids[:limit]:
        ent = geo.GeoEntityById(i)
        cen = getattr(ent, "Centroid", None) if ent is not None else None
        if cen is None:
            continue
        cl = [float(v) * sc for v in cen]
        if len(cl) != 3:
            continue
        area = getattr(ent, "Area", None)
        rec = {"id": i, "c": [round(v, 2) for v in cl],
               "area_mm2": round(float(area) * sc * sc, 1) if area is not None else None,
               "surface": str(getattr(ent, "SurfaceType", ""))}
        rr = []
        for ed in list(getattr(ent, "Edges", None) or []):
            r = getattr(ed, "Radius", None)
            if r is not None and float(r) > 0:
                rr.append(round(float(r) * sc, 3))
        if rr:
            rec["edge_radii_mm"] = sorted(set(rr))[:4]
        faces.append(rec)
    return faces


def bc_locations(analysis):
    """Her mesnet/yuk icin secili yuzlerin merkezleri (mm) ve alanlari."""
    sc = length_scale(None)
    geo = DataModel.GeoData
    out = {}
    for c in analysis.Children:
        t = type(c).__name__
        if t not in SUPPORT_TYPES and t not in LOAD_TYPES:
            continue
        out[c.Name] = faces_of(getattr(c, "Location", None), sc, geo)
    return out


def connections_info(n_bodies):
    """Montaj baglantilari: temas bolgeleri (tip, kaynak/hedef yuzler), mafsallar, kiris baglantilari."""
    sc = length_scale(None)
    geo = DataModel.GeoData
    out = {"bodies": n_bodies, "contacts": [], "joints": [], "beams": []}
    conn = getattr(Model, "Connections", None)
    if conn is None:
        return out
    cats = [("contacts", "ContactRegion"), ("joints", "Joint"), ("beams", "Beam")]
    for key, catname in cats:
        cat = getattr(DataModelObjectCategory, catname, None)
        if cat is None:
            continue
        try:
            objs = list(conn.GetChildren(cat, True))
        except Exception:
            continue
        for o in objs[:60]:
            rec = {"name": o.Name, "suppressed": bool(getattr(o, "Suppressed", False))}
            for prop, k in (("ContactType", "contact_type"), ("Type", "joint_type"),
                            ("ConnectionType", "connection_type"), ("Behavior", "behavior")):
                try:
                    v = getattr(o, prop, None)
                    if v is not None:
                        rec[k] = str(v)
                except Exception:
                    pass
            for side, attr in (("source", "SourceLocation"), ("target", "TargetLocation"),
                               ("source", "ReferenceLocation"), ("target", "MobileLocation")):
                if side in rec:
                    continue
                try:
                    loc = getattr(o, attr, None)
                except Exception:
                    loc = None
                if loc is not None:
                    rec[side] = faces_of(loc, sc, geo, 6)
            out[key].append(rec)
    return out


def nodes_of_faces(meshdata, face_ids, limit):
    pts = []
    for fid in face_ids:
        try:
            reg = meshdata.MeshRegionById(fid)
            nids = list(reg.NodeIds)
        except Exception:
            continue
        step = max(1, len(nids) // max(1, limit // max(1, len(face_ids))))
        for k in range(0, len(nids), step):
            n = meshdata.NodeById(nids[k])
            pts.append((n.X, n.Y, n.Z))
    return pts


def min_dist(p, pts):
    best = 1e30
    for q in pts:
        d = (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2
        if d < best:
            best = d
    return best ** 0.5


def length_scale(meshdata):
    """Mesh dugum koordinatlarini mm'ye ceviren carpan (govde hacmi karsilastirmasi)."""
    v_mm3 = 0.0
    for b in Model.Geometry.GetChildren(DataModelObjectCategory.Body, True):
        v_mm3 += q_mm(b.Volume)
    v_geo = 0.0
    for asm in DataModel.GeoData.Assemblies:
        for part in asm.Parts:
            for body in part.Bodies:
                v_geo += body.Volume
    if v_geo <= 0 or v_mm3 <= 0:
        return 1.0
    s = (v_mm3 / v_geo) ** (1.0 / 3.0)
    for c in (1000.0, 1.0, 25.4, 10.0, 0.001):
        if abs(s / c - 1.0) < 0.02:
            return c
    return s


def effective_thickness(v_mm3):
    """Etkin et kalinligi t = 2V/A (ince plakada kalinliga yakin, kompakt parcada buyuk)."""
    sc = length_scale(None)
    a = 0.0
    for asm in DataModel.GeoData.Assemblies:
        for part in asm.Parts:
            for body in part.Bodies:
                for f in body.Faces:
                    a += float(getattr(f, "Area", 0.0) or 0.0)
    a_mm2 = a * sc * sc
    if a_mm2 <= 0 or v_mm3 <= 0:
        return None
    return round(2.0 * v_mm3 / a_mm2, 3)


def material_names():
    names = []
    for b in Model.Geometry.GetChildren(DataModelObjectCategory.Body, True):
        if not b.Suppressed:
            nm = str(b.Material)
            if nm not in names:
                names.append(nm)
    return names


def all_face_ids():
    out = []
    for asm in DataModel.GeoData.Assemblies:
        for part in asm.Parts:
            for body in part.Bodies:
                for f in body.Faces:
                    out.append(f.Id)
    return out


def faces_containing_node(md, node_id):
    out = []
    for fid in all_face_ids():
        try:
            reg = md.MeshRegionById(fid)
            nids = list(reg.NodeIds)
        except Exception:
            continue
        if node_id in nids:
            out.append(fid)
    return out


def face_info(fids):
    """Maksimum dugumun bulundugu yuzlerin tipi ve (varsa) dairesel kenar yaricaplari [mm].
    Keskin kosede duzlemsel yuzler, radyusta silindirik yuz beklenir."""
    sc = length_scale(None)
    geo = DataModel.GeoData
    out = []
    for fid in fids[:6]:
        ent = geo.GeoEntityById(fid)
        if ent is None:
            continue
        rec = {"id": fid, "type": str(getattr(ent, "SurfaceType", "")), "radii_mm": []}
        for e in list(getattr(ent, "Edges", None) or []):
            r = getattr(e, "Radius", None)
            if r is not None and float(r) > 0:
                rec["radii_mm"].append(round(float(r) * sc, 4))
        out.append(rec)
    return out


def user_sizings(mesh):
    """Kullanicinin kendi lokal eleman boyutlari (feacheck bunlari global ile orantili olcekler)."""
    out = []
    for c in mesh.Children:
        if type(c).__name__ != "Sizing" or c.Name.startswith("FEACHECK_"):
            continue
        if getattr(c, "Suppressed", False):
            continue
        es = getattr(c, "ElementSize", None)
        v = q_mm(es) if es is not None else 0.0
        if v > 0:
            out.append((c, v))
        else:
            warn("Lokal mesh kontrolu '%s' eleman boyutu ile tanimli degil; olceklenemedi, yakinsamayi bozabilir." % c.Name)
    return out


CURVED = ("Cylind", "Torus", "Cone")


def radius_target(levels):
    """Son cozulmus seviyede maksimum egri bir yuzdeyse ve radyus uzerinde < 8 eleman varsa
    (yuz kimlikleri, yaricap mm, en ince global boyut) dondurur; yoksa None."""
    solved = [lv for lv in levels if "max_vm" in lv]
    if not solved:
        return None
    last = solved[-1]
    fids, radii = [], []
    for f in (last.get("max_faces") or []):
        t = f.get("type", "")
        if [c for c in CURVED if c in t] and f.get("radii_mm"):
            fids.append(f["id"])
            radii.append(min(f["radii_mm"]))
    if not fids:
        return None
    rad = min(radii)
    hf = float(last["element_size_mm"])
    n_arc = rad * 1.5708 / hf
    if n_arc >= 8:
        return None
    return fids, rad, hf, n_arc


def peak_node(eqv, md, S, vmax_q):
    """PlotData'dan en yuksek gerilmeli dugum: (deger, xyz_mm, node_id)."""
    pdata = eqv.PlotData
    nodes = list(pdata["Node"])
    vals = [float(x) for x in pdata["Values"]]
    vmax = max(vals)
    k = vmax_q / vmax if vmax > 0 else 1.0
    i = vals.index(vmax)
    n = md.NodeById(int(nodes[i]))
    return vmax * k, [n.X * S, n.Y * S, n.Z * S], int(nodes[i])


def radius_needs_more(vals, tol_pct):
    """Son uc seviyede degisimler gurultu duzeyinde (her adim <= esik/2) ama yon belirsizse
    (salinim ya da son adim bir oncekinden buyuk) bir seviye daha cozmeye deger."""
    if len(vals) < 3:
        return False
    a, b, c = vals[-3], vals[-2], vals[-1]
    d1, d2 = b - a, c - b
    rel = max(abs(d1) / max(abs(b), 1e-30), abs(d2) / max(abs(c), 1e-30)) * 100.0
    if rel > tol_pct / 2.0:
        return False
    if abs(d2) <= 1e-9 * max(abs(c), 1e-30):
        return False   # degisim yok: tam yakinsamis
    return d1 * d2 < 0 or abs(d2) > abs(d1)


def global_needs_more(levels, tol_pct, max_nodes):
    """Global seri bittiginde: tasarim degeri adaylarindan biri gurultu duzeyinde ama yonu belirsiz
    degisiyorsa ve bir sonraki seviye dugum limitine sigacak gibiyse True. Tekil tepe her adimda
    esik/2'den fazla buyudugu icin bu kurali tetiklemez."""
    sv = [lv for lv in levels if "max_vm" in lv]
    if len(sv) < 3:
        return False
    n2, n3 = float(sv[-2]["nodes"]), float(sv[-1]["nodes"])
    if n2 <= 0 or n3 * (n3 / n2) > max_nodes:
        return False
    for key in ("max_outside_zone", "max_away_from_peak", "probe"):
        vals = [(lv.get(key) or {}).get("value") for lv in sv]
        if None not in vals and radius_needs_more(vals, tol_pct):
            return True
    for key in ("max_vm", "max_def"):
        if radius_needs_more([lv[key] for lv in sv if key in lv], tol_pct):
            return True
    return False


def run_radius_series(mesh, sol, eqv, dfm, fids, rad, hf):
    """Global boyut en ince seviyede sabit; yalnizca radyus yuzune R/4, R/6, R/9 ... yerel boyut.
    Ayni fiziksel noktanin (radyustaki tepe) yerel incelmeyle yakinsamasini olcer."""
    ratio = float(CFG.get("ratio", 1.5))
    nlev = int(CFG.get("levels", 3))
    s0 = rad / 4.0
    if s0 > hf / ratio:
        s0 = hf / ratio
    sizes = [round(s0 / ratio ** i, 4) for i in range(nlev)]
    RS = {"face_ids": fids, "radius_mm": rad, "global_size_mm": hf, "sizes_mm": sizes, "levels": []}
    R["radius_series"] = RS
    adder = getattr(mesh, "AddSizing", None)
    if adder is None:
        RS["skipped"] = "Mesh.AddSizing yok"
        return
    sel = ExtAPI.SelectionManager.CreateSelectionInfo(SelectionTypeEnum.GeometryEntities)
    sel.Ids = fids
    sz = adder()
    sz.Name = "FEACHECK_RadiusSizing"
    sz.Location = sel
    ST["added"].append(sz)
    mesh.ElementSize = Quantity("%s [mm]" % hf)
    # Yalniz yuzey incelirse radyusun altindaki hacim kaba kalir ve gerilme gradyani iceri dogru
    # cozulemez (gercek R5 kosusu: tepe 178->180->182->186, hizlanan artis). Buyume oranini dusurmek
    # ince yuzey elemanlarinin hacme yavas buyuyerek gecmesini saglar.
    # Not: "Use Adaptive Sizing = Yes" (Mechanical varsayilani) iken Growth Rate yok sayilir; 15.11 kosusunda
    # ayar hatasiz atandi ama mesh hic degismedi. Bu yuzden once adaptive sizing kapatilir, sonra geri okunur.
    gr = CFG.get("radius_growth_rate", 1.2)
    if gr:
        try:
            if ST.get("orig_adaptive") is None and hasattr(mesh, "UseAdaptiveSizing"):
                ST["orig_adaptive"] = mesh.UseAdaptiveSizing
            if hasattr(mesh, "UseAdaptiveSizing"):
                mesh.UseAdaptiveSizing = False
            if ST.get("orig_growth") is None:
                ST["orig_growth"] = mesh.GrowthRate
            mesh.GrowthRate = float(gr)
            RS["growth_rate_requested"] = float(gr)
            RS["growth_rate"] = float(mesh.GrowthRate)
            RS["adaptive_sizing"] = str(getattr(mesh, "UseAdaptiveSizing", "?"))
        except Exception as e:
            warn("radyus serisinde buyume orani ayarlanamadi: %s" % e)
    for size in sizes:
        if not radius_level(mesh, sol, eqv, dfm, fids, rad, sz, size, RS):
            return
    vals = [x["max_vm"] for x in RS["levels"] if "max_vm" in x]
    if CFG.get("radius_extra_level", True) and len(vals) == len(sizes) and \
            radius_needs_more(vals, float(CFG.get("gci_tol_pct", 5.0))):
        extra = round(sizes[-1] / ratio, 4)
        RS["sizes_mm"] = sizes + [extra]
        RS["extra_level"] = "degisim gurultu duzeyinde ama yonu belirsiz; bir seviye daha cozuldu"
        radius_level(mesh, sol, eqv, dfm, fids, rad, sz, extra, RS)


def radius_level(mesh, sol, eqv, dfm, fids, rad, sz, size, RS):
    """Radyus serisinin tek seviyesi. Devam edilebilirse True."""
    sz.ElementSize = Quantity("%s [mm]" % size)
    mesh.GenerateMesh()
    lv = {"element_size_mm": size, "h_eff_mm": size, "nodes": mesh.Nodes, "elements": mesh.Elements,
          "elements_on_arc": round(rad * 1.5708 / size, 1)}
    if mesh.Nodes > CFG["max_nodes"]:
        lv["skipped"] = "dugum limiti (%d > %d)" % (mesh.Nodes, CFG["max_nodes"])
        RS["levels"].append(lv)
        return False
    sol.Solve(True)
    lv["state"] = str(sol.ObjectState)
    if "Solved" not in lv["state"] or "Not" in lv["state"]:
        RS["levels"].append(lv)
        warn("radyus serisi %s mm ile cozulemedi (%s)" % (size, lv["state"]))
        return False
    lv["max_vm"] = q_mm(eqv.Maximum)
    lv["max_def"] = q_mm(dfm.Maximum)
    try:
        md = DataModel.MeshDataByName("Global")
        S = length_scale(md)
        v, xyz, nid = peak_node(eqv, md, S, lv["max_vm"])
        lv["max_location"] = {"value": v, "xyz_mm": xyz, "node_id": nid}
        on = faces_containing_node(md, nid)
        lv["on_target"] = len([f for f in on if f in fids]) > 0
    except Exception as e:
        warn("radyus serisinde tepe konumu okunamadi: %s" % e)
    RS["levels"].append(lv)
    return True


ST = {"mesh": None, "orig_size": None, "usz": [], "added": [], "orig_growth": None, "orig_adaptive": None}


def restore_model():
    """Kullanicinin modelini eski haline getirir; run() ortada hata verse bile cagrilir."""
    mesh = ST["mesh"]
    if mesh is not None and ST["orig_size"] is not None:
        mesh.ElementSize = Quantity("%s [mm]" % ST["orig_size"])
    if mesh is not None and ST.get("orig_growth") is not None:
        try:
            mesh.GrowthRate = ST["orig_growth"]
        except Exception:
            pass
    if mesh is not None and ST.get("orig_adaptive") is not None:
        try:
            mesh.UseAdaptiveSizing = ST["orig_adaptive"]
        except Exception:
            pass
    for c, sz0 in ST["usz"]:
        c.ElementSize = Quantity("%s [mm]" % sz0)
    if CFG.get("cleanup", True):
        for o in ST["added"]:
            o.Delete()
    ST["added"] = []


def main():
    app = ExtAPI.Application
    old_units = app.ActiveUnitSystem
    app.ActiveUnitSystem = MechanicalUnitSystem.StandardNMM
    try:
        return run()
    finally:
        try:
            restore_model()
        finally:
            app.ActiveUnitSystem = old_units
            R["unit_system_restored"] = str(old_units)


def run():
    if CFG.get("analysis") == "__ACTIVE__":
        analysis = active_analysis()
        if analysis is None:
            R["errors"].append("Agacta bir analiz secili degil. Kontrol edilecek analize (veya altindaki bir nesneye) tikla.")
            return False
    else:
        analysis = pick_analysis()
    if analysis is None:
        R["errors"].append("Analiz bulunamadi: %s" % CFG.get("analysis"))
        return False
    R["analysis"] = analysis.Name
    atype = str(getattr(analysis, "AnalysisType", ""))
    R["analysis_type"] = atype
    ptype = str(getattr(analysis, "PhysicsType", ""))
    R["physics_type"] = ptype
    # Ansys enum: PhysicsType.Mechanical (yapisal), Thermal, Electric, ...
    if ptype and "Mechanical" not in ptype and "Structural" not in ptype:
        R["errors"].append("feacheck yalnizca yapisal (Static Structural) analizi destekler (secilen: %s)." % ptype)
        return False
    if atype and "Static" not in atype:
        R["errors"].append("feacheck yalnizca Static Structural analizini destekler (secilen: %s)." % atype)
        return False
    aset = getattr(analysis, "AnalysisSettings", None)
    nsteps = getattr(aset, "NumberOfSteps", 1) if aset is not None else 1
    if nsteps and int(nsteps) > 1:
        warn("Analiz %d adimli; sonuclar son adimdan okunuyor." % int(nsteps))
    sysc = getattr(analysis, "SystemCaption", None)
    if sysc and sysc != analysis.Name:
        R["analysis"] = "%s (%s)" % (analysis.Name, sysc)
    bodies = [b for b in Model.Geometry.GetChildren(DataModelObjectCategory.Body, True) if not b.Suppressed]
    if bodies:
        R["model_name"] = bodies[0].Name + ("" if len(bodies) == 1 else " +%d govde" % (len(bodies) - 1))
    sol = analysis.Solution
    mesh = Model.Mesh
    for o in list(sol.Children) + list(mesh.Children):
        if o.Name.startswith("FEACHECK_"):
            o.Delete()

    # ---- teshis dokumu
    R["tree"] = []
    for c in analysis.Children:
        R["tree"].append({"type": type(c).__name__, "name": c.Name, "state": str(c.ObjectState),
                          "suppressed": bool(getattr(c, "Suppressed", False))})
    try:
        R["bc_locations"] = bc_locations(analysis)
    except Exception as _e:
        R["bc_locations"] = {}
        R["warnings"].append("BC yuz konumlari okunamadi: " + str(_e))
    for e in R["tree"]:
        if e["name"] in R["bc_locations"]:
            e["faces"] = R["bc_locations"][e["name"]]
    try:
        R["connections"] = connections_info(len(bodies))
    except Exception as _e:
        R["warnings"].append("baglantilar okunamadi: " + str(_e))

    # ---- on kontrol
    bad = []
    n_sup, n_load = 0, 0
    for c in analysis.Children:
        t = type(c).__name__
        if t not in SUPPORT_TYPES and t not in LOAD_TYPES and t not in BODY_LOAD_TYPES:
            continue
        if getattr(c, "Suppressed", False):
            continue
        st = str(c.ObjectState)
        if "UnderDefined" in st or "Error" in st:
            bad.append("%s (%s)" % (c.Name, st))
        if t in SUPPORT_TYPES:
            n_sup += 1
        else:
            n_load += 1
    if bad:
        R["errors"].append("Tanimsiz/hatali sinir sarti: %s. Kapsamini (geometri/named selection) duzelt." % ", ".join(bad))
        return False
    if n_sup == 0:
        R["errors"].append("'%s' analizinde mesnet yok (Fixed Support vb.); model serbest." % R["analysis"])
        return False
    if n_load == 0:
        warn("Analizde yuk yok; sadece zorlanmis deplasman yuklemesi olabilir.")

    # ---- otomatik mesh seviyeleri ve dislama bolgesi (karakteristik boy Lc = V^(1/3))
    v = 0.0
    for b in bodies:
        v += q_mm(b.Volume)
    R["volume_mm3"] = v
    lc = v ** (1.0 / 3.0) if v > 0 else 10.0
    nlev = int(CFG.get("levels", 3))
    ratio = float(CFG.get("ratio", 1.5))
    t_eff = effective_thickness(v)
    R["t_eff_mm"] = t_eff
    if not CFG.get("sizes_mm"):
        # Ince cidarda Lc/8 et kalinligindan buyuk cikar; ilk mesh en az ~1 kuadratik
        # eleman kalinlikta olsun diye etkin kalinlik (2V/A) ile sinirlanir.
        h0 = lc / 8.0
        if t_eff and t_eff < h0:
            h0 = t_eff
            R["h0_limited_by_thickness"] = True
        CFG["sizes_mm"] = [round(h0 / ratio ** i, 3) for i in range(nlev)]
    if CFG.get("exclusion_mm") is None:
        # Saint-Venant: karakteristik boy yukun uygulandigi bolgenin boyu -> sqrt(yuz alani).
        # Alt sinir 2*h0, ust sinir Lc/2. analysis.exclusion_distance ile ayni kural.
        h0x = float(CFG["sizes_mm"][0])
        areas = []
        for nm in R.get("bc_locations", {}):
            a = 0.0
            for f in R["bc_locations"][nm]:
                if f.get("area_mm2"):
                    a += float(f["area_mm2"])
            if a > 0:
                areas.append(a)
        if areas:
            ex = max([a ** 0.5 for a in areas])
            rule = "sqrt(A)"
            if ex < 2.0 * h0x:
                ex, rule = 2.0 * h0x, "2*h0"
            if ex > lc / 2.0:
                ex, rule = lc / 2.0, "Lc/2"
        else:
            ex, rule = lc / 2.0, "Lc/2 (alan yok)"
        CFG["exclusion_mm"] = round(ex, 2)
        R["exclusion_rule"] = rule
    R["materials"] = material_names()
    R["yield_mpa"] = read_yield_mpa()
    lib = [YIELD_LIB.get(m) for m in R["materials"]]
    if lib and None not in lib:
        R["yield_lib_mpa"] = min(lib)
    local = bool(CFG.get("local_refine"))
    R["mode"] = "local" if local else "global"
    R["settings_used"] = {"sizes_mm": CFG["sizes_mm"], "exclusion_mm": CFG["exclusion_mm"],
                          "exclusion_rule": R.get("exclusion_rule"),
                          "max_nodes": CFG["max_nodes"], "mode": R["mode"], "lc_mm": round(lc, 3),
                          "t_eff_mm": t_eff}

    added = ST["added"]
    # Kullanicinin sonuc nesneleri tek govdeye/yuze scope'lanmis olabilir: daima kendi nesnemiz
    # (varsayilan scope = tum govdeler, son zaman) eklenir ve sonda silinir.
    eqv = sol.AddEquivalentStress()
    eqv.Name = "FEACHECK_EquivalentStress"
    added.append(eqv)
    dfm = sol.AddTotalDeformation()
    dfm.Name = "FEACHECK_TotalDeformation"
    added.append(dfm)

    bcs = bc_face_ids(analysis)
    R["bc_types"] = dict([(k, len(vv)) for k, vv in bcs.items()])
    singular_faces = []
    for k, vv in bcs.items():
        singular_faces += vv

    # ---- denge icin: tepkiler ve uygulanan kuvvet
    reactions = []
    R["reaction_supports"] = []
    for c in analysis.Children:
        if type(c).__name__ in SUPPORT_TYPES and not c.Suppressed:
            fr = sol.AddForceReaction()
            fr.Name = "FEACHECK_Reaction"
            added.append(fr)
            try:
                fr.BoundaryConditionSelection = c
            except Exception as _e:
                warn("'%s' icin tepki okunamiyor (%s); denge kontrolu eksik kalabilir." % (c.Name, type(c).__name__))
                R["reaction_incomplete"] = True
                continue
            reactions.append(fr)
            R["reaction_supports"].append(c.Name)
    applied = [0.0, 0.0, 0.0]
    vec_mag = 0.0
    n_vec = 0
    for c in analysis.Children:
        if type(c).__name__ == "Force" and not c.Suppressed:
            if "Component" in str(c.DefineBy):
                applied[0] += q_mm(list(c.XComponent.Output.DiscreteValues)[-1])
                applied[1] += q_mm(list(c.YComponent.Output.DiscreteValues)[-1])
                applied[2] += q_mm(list(c.ZComponent.Output.DiscreteValues)[-1])
            else:
                mag = getattr(c, "Magnitude", None)
                if mag is not None:
                    vec_mag += q_mm(list(mag.Output.DiscreteValues)[-1])
                    n_vec += 1
    R["applied_force_n"] = applied
    if n_vec:
        R["applied_force_vector_mag_n"] = vec_mag
        R["applied_force_vector_count"] = n_vec
    others = [type(c).__name__ for c in analysis.Children if not getattr(c, "Suppressed", False)
              and (type(c).__name__ in ("Pressure", "Moment", "RemoteForce", "BoltPretension", "Bearing")
                   or type(c).__name__ in BODY_LOAD_TYPES)]
    if others:
        R["other_loads"] = True
        R["other_load_types"] = sorted(set(others))

    # ---- kullanici mesh kontrolleri
    R["original_element_size_mm"] = q_mm(mesh.ElementSize)
    R["element_order"] = str(getattr(mesh, "ElementOrder", ""))
    ST["mesh"] = mesh
    ST["orig_size"] = R["original_element_size_mm"]
    usz = user_sizings(mesh)
    ST["usz"] = usz
    R["user_sizings"] = [{"name": c.Name, "size_mm": sz} for c, sz in usz]

    excl = float(CFG["exclusion_mm"])
    sizes = CFG["sizes_mm"]
    h0 = sizes[0]
    loc_sz = None
    li = -1
    while li + 1 < len(sizes):
        li += 1
        size = sizes[li]
        if local and li > 0 and loc_sz is None:
            fids = R.get("hot_faces") or []
            adder = getattr(mesh, "AddSizing", None)
            if not fids or adder is None:
                warn("Yerel siklastirma yapilamadi (sicak bolge yuzu bulunamadi); global incelmeye gecildi.")
                local = False
                R["mode"] = "global"
                R["settings_used"]["mode"] = "global"
            else:
                sel = ExtAPI.SelectionManager.CreateSelectionInfo(SelectionTypeEnum.GeometryEntities)
                sel.Ids = fids
                loc_sz = adder()
                loc_sz.Name = "FEACHECK_LocalSizing"
                loc_sz.Location = sel
                added.append(loc_sz)
        if local and li > 0:
            mesh.ElementSize = Quantity("%s [mm]" % h0)
            loc_sz.ElementSize = Quantity("%s [mm]" % size)
        else:
            mesh.ElementSize = Quantity("%s [mm]" % size)
            for c, sz0 in usz:
                c.ElementSize = Quantity("%s [mm]" % (sz0 * size / h0))
        mesh.GenerateMesh()
        lv = {"element_size_mm": size, "h_eff_mm": size, "nodes": mesh.Nodes, "elements": mesh.Elements}
        try:
            mesh.MeshMetric = MeshMetricType.ElementQuality
            lv["quality_min"] = num(mesh.Minimum)
            lv["quality_avg"] = num(mesh.Average)
            mesh.MeshMetric = MeshMetricType.Skewness
            lv["skewness_max"] = num(mesh.Maximum)
            lv["skewness_avg"] = num(mesh.Average)
            mesh.MeshMetric = MeshMetricType.AspectRatio
            lv["aspect_max"] = num(mesh.Maximum)
            mesh.MeshMetric = getattr(MeshMetricType, "None")
        except Exception as e:
            warn("mesh metrigi okunamadi: %s" % e)
        if mesh.Nodes > CFG["max_nodes"]:
            lv["skipped"] = "dugum limiti (%d > %d)" % (mesh.Nodes, CFG["max_nodes"])
            R["levels"].append(lv)
            break
        sol.Solve(True)
        lv["state"] = str(sol.ObjectState)
        if "Solved" not in lv["state"] or "Not" in lv["state"]:
            R["levels"].append(lv)
            R["errors"].append("%s mm mesh ile cozum basarisiz (%s). Mechanical mesajlarina bak." % (size, lv["state"]))
            break
        lv["max_vm"] = q_mm(eqv.Maximum)
        lv["max_def"] = q_mm(dfm.Maximum)

        md = DataModel.MeshDataByName("Global")
        S = length_scale(md)
        try:
            pdata = eqv.PlotData
            nodes = list(pdata["Node"])
            vals = [float(x) for x in pdata["Values"]]
            vmax = max(vals)
            k = lv["max_vm"] / vmax if vmax > 0 else 1.0   # PlotData birimini Maximum'a esitle
            vals = [x * k for x in vals]
            order = sorted(range(len(vals)), key=lambda i: -float(vals[i]))
            top = order[:CFG["top_k"]]
            bc_pts = nodes_of_faces(md, singular_faces, 600)
            first = None
            outside = None
            away = None
            # tepe kumesi: maksimumun %90'i ustundeki dugumler (tekil kenar boyunca, simetrik ikizler dahil)
            peak_pts = []
            for i in top:
                n = md.NodeById(int(nodes[i]))
                p = (n.X * S, n.Y * S, n.Z * S)
                d = (min_dist((n.X, n.Y, n.Z), bc_pts) if bc_pts else 1e30) * S
                rec = {"value": float(vals[i]), "xyz_mm": [p[0], p[1], p[2]], "dist_to_bc_mm": d,
                       "node_id": int(nodes[i])}
                if first is None:
                    first = rec
                if rec["value"] >= 0.9 * first["value"] and len(peak_pts) < 200:
                    peak_pts.append(p)
                if outside is None and d > excl:
                    outside = rec
                # tepe disi: hem tepe kumesinden hem mesnet/yuk bolgesinden uzak olmali
                if away is None and rec["value"] < 0.9 * first["value"] and d > excl:
                    if min_dist(p, peak_pts) > excl:
                        away = rec
                if outside is not None and away is not None:
                    break
            lv["max_location"] = first
            if first is not None:
                try:
                    lv["max_faces"] = face_info(faces_containing_node(md, first["node_id"]))
                except Exception as _fe:
                    warn("maksimumun yuz bilgisi okunamadi: %s" % _fe)
            lv["max_outside_zone"] = outside
            lv["max_away_from_peak"] = away
            # ---- sabit nokta (probe): ilk seviyede bolge disi maksimumun yeri, sonra hep orasi
            probe = CFG.get("probe_xyz_mm") or R.get("probe_xyz_mm")
            if probe is None and outside is not None:
                probe = outside["xyz_mm"]
                R["probe_xyz_mm"] = probe
                if local:
                    R["hot_faces"] = faces_containing_node(md, outside["node_id"])
            if probe is not None:
                rad2 = float(size) ** 2
                bi, bd = None, 1e30
                best_in, nin = None, 0
                for i in range(len(nodes)):
                    n = md.NodeById(int(nodes[i]))
                    d = (n.X * S - probe[0]) ** 2 + (n.Y * S - probe[1]) ** 2 + (n.Z * S - probe[2]) ** 2
                    if d < bd:
                        bi, bd = i, d
                    if d <= rad2:
                        nin += 1
                        if best_in is None or vals[i] > vals[best_in]:
                            best_in = i
                kk = best_in if best_in is not None else bi
                if kk is not None:
                    lv["probe"] = {"value": vals[kk], "nearest_mm": bd ** 0.5, "radius_mm": float(size),
                                   "nodes_in_radius": nin}
            if outside is None:
                warn("ilk %d dugumun hepsi dislama bolgesinde; top_k'yi artir" % CFG["top_k"])
        except Exception as e:
            warn("PlotData okunamadi, sadece maksimum degerler var: %s" % e)

        if reactions:
            try:
                tot = [0.0, 0.0, 0.0]
                per = []
                for k in range(len(reactions)):
                    fr = reactions[k]
                    rx, ry, rz = q_mm(fr.XAxis), q_mm(fr.YAxis), q_mm(fr.ZAxis)
                    tot[0] += rx
                    tot[1] += ry
                    tot[2] += rz
                    per.append({"name": R["reaction_supports"][k], "r_n": [rx, ry, rz]})
                lv["reaction_n"] = tot
                lv["reactions_by_support"] = per
            except Exception as e:
                warn("mesnet tepkisi okunamadi: %s" % e)
        R["levels"].append(lv)
        if li == len(sizes) - 1 and not R.get("extra_level") and not local and \
                CFG.get("global_extra_level", True) and \
                global_needs_more(R["levels"], float(CFG.get("gci_tol_pct", 5.0)), CFG["max_nodes"]):
            sizes.append(round(size / float(CFG.get("ratio", 1.5)), 3))
            R["extra_level"] = "degisim gurultu duzeyinde ama yonu belirsiz; bir global seviye daha cozuldu"

    # ---- radyus serisi: tepe bir radyusta ve global mesh onu cozemiyorsa o yuze yerel siklastirma
    tgt = radius_target(R["levels"]) if CFG.get("radius_refine", True) and not R["errors"] else None
    if tgt and not local:
        fids, rad, hf, n_arc = tgt
        R["radius_trigger"] = {"face_ids": fids, "radius_mm": rad, "elements_on_arc": round(n_arc, 1)}
        run_radius_series(mesh, sol, eqv, dfm, fids, rad, hf)

    return True


R["ok"] = bool(main())
tojson(R)
'''
