#!/usr/bin/env python3
"""
手套鼠标 PCB - EasyEDA Standard JSON 原理图生成器
输出 glove_mouse_sch.json，可直接导入嘉立创EDA专业版

导入步骤（嘉立创EDA专业版 v2.x）:
  文件 → 导入 → EasyEDA Standard → 选择 glove_mouse_sch.json
  导入后所有元件已含 BOM_Supplier_Part (LCSC编号)
  → 选中全部 → 右键 → 更换器件 → 用LCSC编号一键绑定封装+原理图符号

关键说明：
  EasyEDA Standard LIB 子形状使用 **绝对坐标**（center + local，不含旋转）
  引脚出线方向由 P~ 的 rotation 字段决定，本脚本统一 LIB rot=0 以简化处理
"""

import json, math, os

# ─────────────────────────────────────────────────────────────
# 坐标：1mm → SCALE EasyEDA units
# ─────────────────────────────────────────────────────────────
SCALE   = 4      # 1mm → 4 units  (1 unit ≈ 6.25 mil)
STUB_MM = 3.0    # 引脚出线 stub 长度 (mm)

_gid = [0]
def gid():
    _gid[0] += 1
    return f"gge{_gid[0]}"

def u(mm):
    return round(mm * SCALE)

shapes = []

def add_shape(s):
    shapes.append(s)

# ─────────────────────────────────────────────────────────────
# 外部形状（绝对坐标，mm 输入）
# ─────────────────────────────────────────────────────────────

def add_wire(x1_mm, y1_mm, x2_mm, y2_mm):
    add_shape(f"W~{u(x1_mm)} {u(y1_mm)} {u(x2_mm)} {u(y2_mm)}~#000000~1~0~none~{gid()}~0")

def add_label(net, x_mm, y_mm, rot=0):
    x, y = u(x_mm), u(y_mm)
    add_shape(f"N~{x}~{y}~{rot}~#FF0000~{net}~{gid()}~start~{x+3}~{y-3}~Times New Roman~9pt~0~0")

def add_gnd(x_mm, y_mm):
    # 用网络标签连接 GND，比 POWER~ 更通用
    add_label("GND", x_mm, y_mm)

def add_noconnect(x_mm, y_mm):
    add_shape(f"X~{u(x_mm)}~{u(y_mm)}~{gid()}~0")

# ─────────────────────────────────────────────────────────────
# 元件子形状（绝对坐标 in EasyEDA units）
# ─────────────────────────────────────────────────────────────

def child_rect(ax_u, ay_u, bw_u, bh_u, fill="#eeeeee"):
    """矩形：top-left=(ax-bw, ay-bh), width=2bw, height=2bh"""
    x = ax_u - bw_u
    y = ay_u - bh_u
    w = 2 * bw_u
    h = 2 * bh_u
    return f"R~{x}~{y}~0~0~{w}~{h}~{fill}~#000000~1~{gid()}"

def child_text(x_u, y_u, text, size=7, bold=False, anchor="start"):
    style = "bold" if bold else "normal"
    return f"T~L~{x_u}~{y_u}~0~{size}~#000000~{style}~normal~{gid()}~{text}~1~{anchor}~0~"

def child_pin(dot_x_u, dot_y_u, out_rot, pin_name, pin_num):
    """
    EasyEDA P~ 引脚形状（绝对坐标）
    out_rot: 引脚导线向外伸出方向
      0   = 向右(+x)，dot 在右侧，SVG 向左进体
      90  = 向下(+y)，dot 在下侧，SVG 向上进体
      180 = 向左(-x)，dot 在左侧，SVG 向右进体
      270 = 向上(-y)，dot 在上侧，SVG 向下进体
    """
    stub_u = round(STUB_MM * SCALE)
    if out_rot == 0:
        svg  = f"h -{stub_u}"
        nx, ny = dot_x_u + 2, dot_y_u - 4
        px, py = dot_x_u + 2, dot_y_u + 3
        na, pa = "start", "start"
    elif out_rot == 180:
        svg  = f"h {stub_u}"
        nx, ny = dot_x_u - 2, dot_y_u - 4
        px, py = dot_x_u - 2, dot_y_u + 3
        na, pa = "end", "end"
    elif out_rot == 90:
        svg  = f"v -{stub_u}"
        nx, ny = dot_x_u + 3, dot_y_u + 4
        px, py = dot_x_u - 3, dot_y_u + 4
        na, pa = "start", "end"
    else:  # 270
        svg  = f"v {stub_u}"
        nx, ny = dot_x_u + 3, dot_y_u - 5
        px, py = dot_x_u - 3, dot_y_u - 5
        na, pa = "start", "end"

    g = gid()
    return (
        f"P~show~1~1~{dot_x_u}~{dot_y_u}~{out_rot}~{g}~0"
        f"^^{dot_x_u}~{dot_y_u}"
        f"^^M {dot_x_u} {dot_y_u} {svg}~#000000"
        f"^^1~{nx}~{ny}~0~{pin_name}~{na}~~~#000000"
        f"^^1~{px}~{py}~0~{pin_num}~{pa}~~~#000000^^"
    )

# ─────────────────────────────────────────────────────────────
# 符号定义
# pins: [(name, num, rel_x_mm, rel_y_mm, out_rot)]
#   rel_x/y: 相对于元件中心的局部坐标 (mm)
#   out_rot: 导线伸出方向 (0/90/180/270)
# ─────────────────────────────────────────────────────────────
SYMBOLS = {}

def defsym(name, bw, bh, pins, fill="#eeeeee"):
    SYMBOLS[name] = dict(bw=bw, bh=bh, pins=pins, fill=fill)

defsym("RES",   2.0, 0.8,  [("~","1",-4.0,0,180),("~","2", 4.0,0,  0)])
defsym("CAP",   1.0, 2.0,  [("~","1", 0,-4.0,270),("~","2", 0, 4.0,90)])
defsym("IND",   2.0, 0.8,  [("~","1",-4.0,0,180),("~","2", 4.0,0,  0)], "#eeeeff")
defsym("DIODE", 2.0, 1.0,  [("K","K",-4.0,0,180),("A","A", 4.0,0,  0)], "#eeffee")

defsym("BAT_PAD", 3.81, 1.27, [
    ("+","+", -6.35,0,180),("-","-",  6.35,0,  0)], "#ffffcc")

defsym("SLIDE_SW", 3.81, 2.54, [
    ("1","1",-6.35, 1.27,180),("2","2",6.35,0.00,0),("3","3",-6.35,-1.27,180)], "#ffeedd")

defsym("MT3608", 5.08, 5.08, [
    ("GND","1",-7.62, 3.81,180),("VIN","2",-7.62, 1.27,180),
    ("EN", "3",-7.62,-1.27,180),("FB", "4", 7.62,-1.27,  0),
    ("SW", "5", 7.62, 1.27,  0),("NC", "6", 7.62, 3.81,  0)], "#ddeeff")

defsym("XIAO_ESP32C6", 10.16, 10.16, [
    ("GND",       "1" ,-12.70, 8.89,180),("3V3",       "2" ,-12.70, 6.35,180),
    ("GPIO2",     "3" ,-12.70, 3.81,180),("GPIO3",     "4" ,-12.70, 1.27,180),
    ("GPIO4",     "5" ,-12.70,-1.27,180),("GPIO5",     "6" ,-12.70,-3.81,180),
    ("GPIO6/SDA", "7" ,-12.70,-6.35,180),("VIN",       "8" , 12.70, 8.89,  0),
    ("GND",       "9" , 12.70, 6.35,  0),("GPIO7/SCL", "10", 12.70, 3.81,  0),
    ("GPIO21",    "11", 12.70, 1.27,  0),("GPIO18",    "12", 12.70,-1.27,  0),
    ("GPIO20",    "13", 12.70,-3.81,  0),("GPIO19",    "14", 12.70,-6.35,  0)], "#ffeedd")

defsym("MPU6050", 7.62, 8.89, [
    ("VCC",   "1" ,-10.16, 7.62,180),("GND",   "2" ,-10.16, 5.08,180),
    ("SCL",   "3" ,-10.16, 2.54,180),("SDA",   "4" ,-10.16, 0.00,180),
    ("AD0",   "5" ,-10.16,-2.54,180),("VLOGIC","6" ,-10.16,-5.08,180),
    ("CLKIN", "7" ,-10.16,-7.62,180),("INT",   "8" , 10.16, 7.62,  0),
    ("FSYNC", "9" , 10.16, 5.08,  0),("XDA",   "10", 10.16, 2.54,  0),
    ("XCL",   "11", 10.16, 0.00,  0)], "#ddeeff")

defsym("LM339_CMP", 5.08, 3.81, [
    ("IN+","1",-7.62, 2.54,180),("IN-","2",-7.62,-2.54,180),
    ("OUT","3", 7.62, 0.00,  0),("VCC","4",-7.62, 0.00,180),
    ("GND","5", 7.62, 2.54,  0)], "#eeffee")

defsym("TRIMPOT", 3.81, 2.54, [
    ("1","1",-6.35, 1.27,180),("W","W",6.35,0.00,0),("3","3",-6.35,-1.27,180)])

defsym("JST2P", 2.54, 2.54, [
    ("1","1",-5.08, 1.27,180),("2","2",-5.08,-1.27,180)], "#ffffcc")


# ─────────────────────────────────────────────────────────────
# 放置元件
# ─────────────────────────────────────────────────────────────
def place(ref, value, sym_name, cx_mm, cy_mm, _rot, lcsc, footprint, pin_nets):
    """
    注：EasyEDA Standard LIB 子形状使用绝对坐标 = center + local（不含旋转变换）
    为简化处理，所有 LIB 元件统一设 rotation=0；
    pin_nets 中以 NC 开头的网络添加不连接标记。
    """
    sym = SYMBOLS.get(sym_name)
    if not sym:
        print(f"  [!] 未知符号 {sym_name}，跳过 {ref}")
        return

    bw = sym["bw"]; bh = sym["bh"]; fill = sym["fill"]

    # 属性字符串（反引号分隔键值对）
    pkg = footprint.split(":")[-1] if ":" in footprint else footprint
    attrs = (
        f"package`{pkg}`"
        f"pre`{ref[0]}`"
        f"nameAlias`Value`"
        f"Value`{value}`"
        f"Designator`{ref}`"
        f"BOM_Supplier_Part`{lcsc}`"
        f"BOM_Supplier`LCSC`"
    )

    # ── 子形状 ────────────────────────────────────────────────
    cx_u = u(cx_mm); cy_u = u(cy_mm)
    bw_u = u(bw);    bh_u = u(bh)

    children = []
    children.append(child_rect(cx_u, cy_u, bw_u, bh_u, fill))
    children.append(child_text(cx_u - bw_u, cy_u - bh_u - 10, ref,   size=7, bold=True))
    children.append(child_text(cx_u - bw_u, cy_u + bh_u +  3, value, size=6))

    # 引脚（绝对坐标 = center + local，rot=0，即直接相加）
    pin_abs = {}   # pin_num → (dot_x_mm, dot_y_mm)
    for pname, pnum, rx_mm, ry_mm, out_rot in sym["pins"]:
        # 绝对位置（不旋转）
        abs_x_mm = cx_mm + rx_mm
        abs_y_mm = cy_mm + ry_mm
        abs_x_u  = u(abs_x_mm)
        abs_y_u  = u(abs_y_mm)
        children.append(child_pin(abs_x_u, abs_y_u, out_rot, pname, pnum))
        pin_abs[pnum] = (abs_x_mm, abs_y_mm, out_rot)

    # ── LIB 主形状 ────────────────────────────────────────────
    child_str = "#@$".join(children)
    add_shape(f"LIB~{cx_u}~{cy_u}~{attrs}~0~0~{gid()}#@${child_str}")

    # ── 引脚导线 + 网络标签 ───────────────────────────────────
    for pnum, net in pin_nets.items():
        if pnum not in pin_abs:
            print(f"  [!] 引脚 {pnum} 不在符号 {sym_name} ({ref})")
            continue
        dot_x, dot_y, out_rot = pin_abs[pnum]
        sr = math.radians(out_rot)
        stub_x = dot_x + STUB_MM * math.cos(sr)
        stub_y = dot_y + STUB_MM * math.sin(sr)

        add_wire(dot_x, dot_y, stub_x, stub_y)

        if net.startswith("NC"):
            add_noconnect(stub_x, stub_y)
        elif net == "GND":
            add_gnd(stub_x, stub_y)
        else:
            add_label(net, stub_x, stub_y)


# ─────────────────────────────────────────────────────────────
# 元件列表
# ─────────────────────────────────────────────────────────────
COMPONENTS = [

  # ══ 电源：电池 → 开关 → MT3608 → XIAO ═══════════════════════

  ("BT1","LiPo Battery","BAT_PAD",  30,  30, 0,"—","BAT-SOLDER",
   {"+":"BAT_RAW","-":"GND"}),

  ("SW1","Power SW","SLIDE_SW",     60,  30, 0,"C431540","SS-12D00-G",
   {"1":"GND","2":"VBAT","3":"BAT_RAW"}),

  ("U_BOOST","MT3608","MT3608",     95,  30, 0,"C84817","SOT-23-6",
   {"1":"GND","2":"VBAT","3":"VBAT","4":"BOOST_FB","5":"BOOST_SW","6":"NC_B"}),

  ("L1","4.7uH","IND",            120,  30, 0,"C1046","L_0603",
   {"1":"VBAT","2":"BOOST_SW"}),

  ("D1","SS14","DIODE",           140,  30, 0,"C2480","D_SOD-123",
   {"K":"BOOST_SW","A":"BOOST_OUT"}),

  ("C_bin","10uF","CAP",           95,  15, 0,"C17024","C_0805",
   {"1":"VBAT","2":"GND"}),

  ("C_bout","22uF","CAP",         140,  15, 0,"C45783","C_0805",
   {"1":"BOOST_OUT","2":"GND"}),

  ("R_boost1","100k","RES",       158,  30, 0,"C25741","R_0402",
   {"1":"BOOST_OUT","2":"BOOST_FB"}),

  ("R_boost2","15k","RES",        158,  15, 0,"C25856","R_0402",
   {"1":"BOOST_FB","2":"GND"}),

  # ══ XIAO ESP32C6 ═════════════════════════════════════════════

  ("U1","XIAO ESP32C6","XIAO_ESP32C6", 205, 80, 0,"Seeed-102010510","XIAO-ESP32C6",
   {"1":"GND","2":"3V3","3":"FSR_L_DO","4":"FSR_R_DO","5":"FLEX_DO",
    "6":"NC1","7":"SDA","8":"BOOST_OUT","9":"GND",
    "10":"SCL","11":"NC2","12":"NC3","13":"NC4","14":"NC5"}),

  ("C8","100nF","CAP",            185, 68, 0,"C14663","C_0402",{"1":"3V3","2":"GND"}),
  ("C9","22uF", "CAP",            179, 68, 0,"C45783","C_0805", {"1":"3V3","2":"GND"}),

  # ══ MPU-6050 ═════════════════════════════════════════════════

  ("U2","MPU-6050","MPU6050",     255, 80, 0,"C24112","QFN-24_4x4mm",
   {"1":"3V3","2":"GND","3":"SCL","4":"SDA","5":"GND","6":"3V3","7":"GND",
    "8":"NC6","9":"GND","10":"NC7","11":"NC8"}),

  ("C10","100nF","CAP",           240, 68, 0,"C14663","C_0402",{"1":"3V3","2":"GND"}),
  ("C11","10uF", "CAP",           234, 68, 0,"C17024","C_0805", {"1":"3V3","2":"GND"}),
  ("C_vlog","100nF","CAP",        268, 68, 0,"C14663","C_0402",{"1":"3V3","2":"GND"}),

  ("R_sda","4.7k","RES",          240, 96, 0,"C23162","R_0402",{"1":"3V3","2":"SDA"}),
  ("R_scl","4.7k","RES",          250, 96, 0,"C23162","R_0402",{"1":"3V3","2":"SCL"}),

  # ══ LM339 比较器 ═════════════════════════════════════════════

  ("U7A","LM339 CMP1","LM339_CMP", 60, 140, 0,"C7701","SOIC-14",
   {"1":"VREF_FLEX","2":"VMID_FLEX","3":"FLEX_DO","4":"3V3","5":"GND"}),

  ("U7B","LM339 CMP2","LM339_CMP", 60, 155, 0,"C7701","SOIC-14",
   {"1":"VMID_FSR_L","2":"VREF_FSR","3":"FSR_L_DO","4":"3V3","5":"GND"}),

  ("U7C","LM339 CMP3","LM339_CMP", 60, 170, 0,"C7701","SOIC-14",
   {"1":"VMID_FSR_R","2":"VREF_FSR","3":"FSR_R_DO","4":"3V3","5":"GND"}),

  ("C14","100nF","CAP", 42, 140, 0,"C14663","C_0402",{"1":"3V3","2":"GND"}),
  ("C15","4.7uF","CAP", 36, 140, 0,"C17658","C_0805", {"1":"3V3","2":"GND"}),

  # ══ Flex 传感器分压 ═══════════════════════════════════════════

  ("R1",   "47k",      "RES",    95, 140, 0,"C25819","R_0402",{"1":"3V3","2":"VMID_FLEX"}),
  ("R_rf1","10k",      "RES",    95, 150, 0,"C25905","R_0402",{"1":"3V3","2":"VREF_FLEX_PRE"}),

  ("RV1","10k Trim","TRIMPOT", 110, 150, 0,"C128917","Potentiometer_Bourns_3224W",
   {"1":"GND","W":"VREF_FLEX","3":"VREF_FLEX_PRE"}),

  ("J3","Flex Sensor","JST2P",  130, 140, 0,"C131337","JST_PH_B2B-PH-K_2P",
   {"1":"VMID_FLEX","2":"GND"}),

  # ══ FSR 分压 ═════════════════════════════════════════════════

  ("R2",   "10k","RES",         95, 162, 0,"C25905","R_0402",{"1":"3V3","2":"VMID_FSR_L"}),
  ("R3",   "10k","RES",         95, 170, 0,"C25905","R_0402",{"1":"3V3","2":"VMID_FSR_R"}),
  ("R_rf2","10k","RES",         95, 178, 0,"C25905","R_0402",{"1":"3V3","2":"VREF_FSR_PRE"}),

  ("RV2","10k Trim","TRIMPOT", 110, 178, 0,"C128917","Potentiometer_Bourns_3224W",
   {"1":"GND","W":"VREF_FSR","3":"VREF_FSR_PRE"}),

  ("J4","FSR Left", "JST2P",   130, 157, 0,"C131337","JST_PH_B2B-PH-K_2P",
   {"1":"VMID_FSR_L","2":"GND"}),

  ("J5","FSR Right","JST2P",   130, 167, 0,"C131337","JST_PH_B2B-PH-K_2P",
   {"1":"VMID_FSR_R","2":"GND"}),
]


# ─────────────────────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────────────────────
def generate():
    print("生成 EasyEDA Standard JSON 原理图...")
    for comp in COMPONENTS:
        ref, value, sym_name, cx, cy, rot, lcsc, fp, pin_nets = comp
        place(ref, value, sym_name, cx, cy, rot, lcsc, fp, pin_nets)
    print(f"  {len(COMPONENTS)} 个元件，{len(shapes)} 个形状")

    xs = [u(c[3]) for c in COMPONENTS]
    ys = [u(c[4]) for c in COMPONENTS]
    mg = u(30)
    bx  = min(xs) - mg;  by  = min(ys) - mg
    bw  = max(xs) - min(xs) + 2*mg
    bh  = max(ys) - min(ys) + 2*mg
    gs  = u(2.54)   # 网格间距 (≈ 100 mil)

    doc = {
        "head": {
            "docType":      "1",
            "editorVersion":"6.5.5",
            "c_para":       {"Contributor": "generate_easyeda.py"},
            "hasIdFlag":    True,
        },
        "canvas": (
            f"CA~{bw+mg}~{bh+mg}~#ffffff~yes~#cccccc~{gs}~"
            f"{bw+mg}~{bh+mg}~line~{gs}~pixel~5~"
        ),
        "shape":  shapes,
        "BBox":   {"x": bx, "y": by, "width": bw, "height": bh},
        "symbolNames": {},
    }
    return doc


def write_file():
    doc = generate()
    out_dir = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(out_dir, "glove_mouse_sch.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print(f"[OK] {out_path}")
    print()
    print("嘉立创EDA专业版导入后 LCSC 编号对照表：")
    print(f"  {'位号':12s} {'值':20s}  LCSC编号")
    print(f"  {'-'*12} {'-'*20}  {'-'*10}")
    for comp in COMPONENTS:
        ref, value, _, _, _, _, lcsc, fp, _ = comp
        if lcsc != "—":
            print(f"  {ref:12s} {value:20s}  {lcsc}")


if __name__ == "__main__":
    write_file()
