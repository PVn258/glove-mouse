#!/usr/bin/env python3
"""
手套鼠标 - KiCad 6 PCB（XIAO ESP32C6 + MT3608 升压）
输出 hardware/glove_mouse.kicad_pcb

电源方案：
  锂电池导线 → 裸焊盘(BT1) → 滑动开关(SW1) → MT3608 升压(→ 4.6V) → XIAO VIN(pin8)
  MT3608 从电池低至 2V 均可稳压输出 4.6V，XIAO 内部 LDO 再降至 3.3V
  充电：通过 XIAO 自带 USB-C 口进行，无需外部充电电路

板尺寸：50 × 40 mm
"""

import uuid, os, math, heapq

OUT = []
def w(s=""): OUT.append(s)
def uid(): return str(uuid.uuid4())

# ─────────────────────────────────────────────────────────────────────────────
# 网络列表
# ─────────────────────────────────────────────────────────────────────────────
NETS_LIST = [
    "GND", "BAT_RAW", "VBAT", "BOOST_SW", "BOOST_OUT", "BOOST_FB", "3V3",
    "SDA", "SCL",
    "FSR_L_DO", "FSR_R_DO", "FLEX_DO",
    "VMID_FLEX", "VREF_FLEX", "VREF_FLEX_PRE",
    "VMID_FSR_L", "VMID_FSR_R", "VREF_FSR", "VREF_FSR_PRE",
]
NET_IDX = {"": 0}
for _i, _n in enumerate(NETS_LIST, 1):
    NET_IDX[_n] = _i
def ni(name): return NET_IDX.get(name, 0), name

# ─────────────────────────────────────────────────────────────────────────────
# Footprint 焊盘模板
# ─────────────────────────────────────────────────────────────────────────────
FP = {}

FP["R_0402"] = FP["C_0402"] = [
    ("1", -0.575, 0, 0.6, 0.55, "rect"),
    ("2",  0.575, 0, 0.6, 0.55, "rect"),
]
FP["C_0805"] = [
    ("1", -1.025, 0, 1.0, 1.4, "rect"),
    ("2",  1.025, 0, 1.0, 1.4, "rect"),
]
_sp = [3.81, 2.54, 1.27, 0.0, -1.27, -2.54, -3.81]
FP["SOP-14"] = (
    [(str(i+1), -2.9,  _sp[i], 1.6, 0.6, "rect") for i in range(7)] +
    [(str(i+8),  2.9, -_sp[i], 1.6, 0.6, "rect") for i in range(7)]
)
_qp = [-1.25, -0.75, -0.25, 0.25, 0.75, 1.25]
FP["QFN-24"] = (
    [(str(i+1),  _qp[i], -2.375, 0.25, 0.7,  "rect") for i in range(6)] +
    [(str(i+7),   2.375,  _qp[i], 0.7,  0.25, "rect") for i in range(6)] +
    [(str(i+13),-_qp[i],  2.375, 0.25, 0.7,  "rect") for i in range(6)] +
    [(str(i+19),-2.375, -_qp[i], 0.7,  0.25, "rect") for i in range(6)] +
    [("25", 0, 0, 2.7, 2.7, "rect")]
)
# XIAO ESP32C6 (Seeed 102010510): 21×17.5mm, 14 castellated pads, 2.54mm pitch
# Left (pin 1 靠 USB): GND(1) 3V3(2) GPIO2(3) GPIO3(4) GPIO4(5) GPIO5(6) GPIO6/SDA(7)
# Right(pin 8 靠 USB): VIN(8) GND(9) GPIO7/SCL(10) GPIO21~18 NC(11-14)
_xiao_y = [-7.62, -5.08, -2.54, 0.0, 2.54, 5.08, 7.62]
FP["XIAO-ESP32C6"] = (
    [(str(i+1), -8.89, _xiao_y[i], 2.5, 1.0, "rect") for i in range(7)] +
    [(str(i+8),  8.89, _xiao_y[i], 2.5, 1.0, "rect") for i in range(7)]
)
# SOT-23-6 (MT3608 升压芯片)
FP["SOT-23-6"] = [
    ("1", -1.425,  0.95, 0.6, 0.7, "rect"),
    ("2", -1.425,  0.00, 0.6, 0.7, "rect"),
    ("3", -1.425, -0.95, 0.6, 0.7, "rect"),
    ("4",  1.425, -0.95, 0.6, 0.7, "rect"),
    ("5",  1.425,  0.00, 0.6, 0.7, "rect"),
    ("6",  1.425,  0.95, 0.6, 0.7, "rect"),
]
# 0603 电感
FP["L_0603"] = [
    ("1", -1.0, 0, 1.4, 1.2, "rect"),
    ("2",  1.0, 0, 1.4, 1.2, "rect"),
]
# SOD-123 肖特基二极管 (SS14)
FP["SOD-123"] = [
    ("K", -1.65, 0, 1.0, 1.2, "rect"),
    ("A",  1.65, 0, 1.0, 1.2, "rect"),
]
# 电池裸焊盘：两块大 SMD 铜皮，直接焊电池导线
# 左焊盘=BAT+，右焊盘=BAT-，间距 6mm，每块 3.5×6mm
FP["BAT-SOLDER"] = [
    ("+", -3.0, 0, 3.5, 6.0, "rect"),
    ("-",  3.0, 0, 3.5, 6.0, "rect"),
]
# 滑动开关 SS-12D00G
FP["SLIDE-SW"] = [
    ("1", -2.0, 0, 1.0, 1.5, "rect"),
    ("2",  0.0, 0, 1.0, 1.5, "rect"),
    ("3",  2.0, 0, 1.0, 1.5, "rect"),
]
# 微调电位器 3224W
FP["TRIMPOT-3224W"] = [
    ("1", -1.5,  1.25, 1.0, 1.0, "rect"),
    ("W",  0.0, -1.75, 1.0, 1.0, "rect"),
    ("3",  1.5,  1.25, 1.0, 1.0, "rect"),
]
# JST PH2.0 2P
FP["JST-PH-2P"] = [
    ("1", -1.0, 0, 1.2, 2.0, "rect"),
    ("2",  1.0, 0, 1.2, 2.0, "rect"),
]

# ─────────────────────────────────────────────────────────────────────────────
# 元件放置表
# 坐标原点 = 板子左下角，单位 mm
# ─────────────────────────────────────────────────────────────────────────────
PLACEMENTS = [

  # ══ 电源：电池焊盘 → 开关 → MT3608 升压 → XIAO ══════════════════

  # BT1: 电池裸焊盘，BAT+ / BAT-（直接焊导线）
  ("BT1", "LiPo Battery", "BAT-SOLDER",  6, 36, 0, "—",
   {"+":"BAT_RAW", "-":"GND"}),

  # SW1: 滑动开关，pin3=电池正极输入，pin2=升压输入，pin1=GND（固定脚）
  ("SW1", "Power SW", "SLIDE-SW", 15, 36, 0, "C431540",
   {"1":"GND", "2":"VBAT", "3":"BAT_RAW"}),

  # ── MT3608 升压电路（输出 ≈ 4.6V 给 XIAO VIN）────────────────────
  # 计算：Vout = 0.6 × (1 + R_boost1/R_boost2) = 0.6 × (1+100/15) ≈ 4.6V
  # MT3608 引脚: 1=GND 2=VIN 3=EN 4=FB 5=SW 6=NC
  ("U_BOOST","MT3608",  "SOT-23-6",  23, 36, 0, "C84817",
   {"1":"GND","2":"VBAT","3":"VBAT","4":"BOOST_FB","5":"BOOST_SW","6":""}),

  ("L1",  "4.7uH",  "L_0603",   30, 36, 0, "C1046",
   {"1":"VBAT","2":"BOOST_SW"}),

  ("D1",  "SS14",   "SOD-123",  37, 36, 0, "C2480",
   {"A":"BOOST_SW","K":"BOOST_OUT"}),

  ("C_bin", "10uF",  "C_0805",  23, 32, 0, "C17024",
   {"1":"VBAT","2":"GND"}),

  ("C_bout","22uF",  "C_0805",  37, 32, 0, "C45783",
   {"1":"BOOST_OUT","2":"GND"}),

  # 反馈分压：BOOST_OUT → R_boost1(100k) → BOOST_FB → R_boost2(15k) → GND
  ("R_boost1","100k","R_0402",  43, 36, 90, "C25741",
   {"1":"BOOST_OUT","2":"BOOST_FB"}),

  ("R_boost2","15k", "R_0402",  43, 32, 90, "C25856",
   {"1":"BOOST_FB","2":"GND"}),

  # ══ 主控：XIAO ESP32C6 ═══════════════════════════════════════════
  # pin1=GND pin2=3V3(out) pin3~7=GPIO2~6/SDA
  # pin8=BOOST_OUT(VIN) pin9=GND pin10=GPIO7/SCL pin11~14=NC
  ("U1", "XIAO ESP32C6", "XIAO-ESP32C6", 24, 22, 0, "Seeed-102010510",
   {"1":"GND",  "2":"3V3",       "3":"FSR_L_DO", "4":"FSR_R_DO",
    "5":"FLEX_DO","6":"",        "7":"SDA",
    "8":"BOOST_OUT","9":"GND",   "10":"SCL",
    "11":"",    "12":"",         "13":"",         "14":""}),

  # XIAO 3V3 去耦
  ("C8",  "100nF", "C_0402", 12, 22, 0, "C14663", {"1":"3V3","2":"GND"}),
  ("C9",  "22uF",  "C_0805", 12, 18, 0, "C45783", {"1":"3V3","2":"GND"}),

  # ══ MPU-6050 ════════════════════════════════════════════════════
  ("U2", "MPU-6050", "QFN-24", 41, 22, 0, "C24112",
   {"1":"3V3","2":"GND","3":"SCL","4":"SDA","5":"GND","6":"3V3","7":"GND",
    "8":"","9":"GND","10":"","11":"","12":"","13":"","14":"","15":"","16":"",
    "17":"","18":"","19":"","20":"","21":"","22":"","23":"","24":"","25":"GND"}),

  ("C10","100nF","C_0402", 37, 22, 0, "C14663", {"1":"3V3","2":"GND"}),
  ("C11","10uF", "C_0805", 37, 17, 0, "C17024",  {"1":"3V3","2":"GND"}),
  ("C_vlog","100nF","C_0402",45,17,0, "C14663", {"1":"3V3","2":"GND"}),

  # I2C 上拉
  ("R_sda","4.7k","R_0402", 39, 14, 90, "C23162", {"1":"3V3","2":"SDA"}),
  ("R_scl","4.7k","R_0402", 42, 14, 90, "C23162", {"1":"3V3","2":"SCL"}),

  # ══ LM339 三路比较器 ════════════════════════════════════════════
  # 物理管脚: 1=FLEX_DO 2=VMID_FLEX 3=VREF_FLEX 4=3V3
  #           5=VMID_FSR_L 6=VREF_FSR 7=FSR_L_DO 8=GND
  #           9=FSR_R_DO 10=VREF_FSR 11=VMID_FSR_R 12-14=NC
  ("U7", "LM339", "SOP-14", 16, 9, 0, "C7701",
   {"1":"FLEX_DO",    "2":"VMID_FLEX",  "3":"VREF_FLEX",
    "4":"3V3",        "5":"VMID_FSR_L", "6":"VREF_FSR",
    "7":"FSR_L_DO",   "8":"GND",
    "9":"FSR_R_DO",   "10":"VREF_FSR",  "11":"VMID_FSR_R",
    "12":"",          "13":"",          "14":""}),

  ("C14","100nF","C_0402",  8, 12, 0, "C14663", {"1":"3V3","2":"GND"}),
  ("C15","4.7uF","C_0805",  8,  8, 0, "C17658",  {"1":"3V3","2":"GND"}),

  # ══ Flex 传感器分压 ══════════════════════════════════════════════
  ("R1",    "47k",       "R_0402",        25, 11, 90, "C25819",
   {"1":"3V3","2":"VMID_FLEX"}),
  ("R_rf1", "10k",       "R_0402",        28, 11, 90, "C25905",
   {"1":"3V3","2":"VREF_FLEX_PRE"}),
  ("RV1",   "10k Trim",  "TRIMPOT-3224W", 31,  9,  0, "C128917",
   {"1":"GND","W":"VREF_FLEX","3":"VREF_FLEX_PRE"}),
  ("J3",    "Flex",      "JST-PH-2P",     40,  6,  0, "C131337",
   {"1":"VMID_FLEX","2":"GND"}),

  # ══ FSR 分压 ════════════════════════════════════════════════════
  ("R2",    "10k",       "R_0402",        25,  7, 90, "C25905",
   {"1":"3V3","2":"VMID_FSR_L"}),
  ("R3",    "10k",       "R_0402",        28,  7, 90, "C25905",
   {"1":"3V3","2":"VMID_FSR_R"}),
  ("R_rf2", "10k",       "R_0402",        31,  5, 90, "C25905",
   {"1":"3V3","2":"VREF_FSR_PRE"}),
  ("RV2",   "10k Trim",  "TRIMPOT-3224W", 34,  3,  0, "C128917",
   {"1":"GND","W":"VREF_FSR","3":"VREF_FSR_PRE"}),
  ("J4",    "FSR Left",  "JST-PH-2P",     44, 12,  0, "C131337",
   {"1":"VMID_FSR_L","2":"GND"}),
  ("J5",    "FSR Right", "JST-PH-2P",     44,  6,  0, "C131337",
   {"1":"VMID_FSR_R","2":"GND"}),
]

BOARD_W = 50.0
BOARD_H = 40.0

# ─────────────────────────────────────────────────────────────────────────────
# 布线引擎
# ─────────────────────────────────────────────────────────────────────────────
POWER_NETS_SET = {"BAT_RAW", "VBAT", "BOOST_OUT", "3V3"}

def rotate_xy(dx, dy, deg):
    if deg == 0: return dx, dy
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return dx*c - dy*s, dx*s + dy*c

def build_net_pad_map():
    nm = {}
    for ref, value, fp_key, cx, cy, rot, lcsc, pad_nets in PLACEMENTS:
        for pd in FP.get(fp_key, []):
            pnum = str(pd[0])
            net = pad_nets.get(pnum, "")
            if not net: continue
            rdx, rdy = rotate_xy(pd[1], pd[2], rot)
            nm.setdefault(net, []).append((cx+rdx, cy+rdy))
    return nm

def prim_mst(pts):
    n = len(pts)
    if n <= 1: return []
    visited = [False]*n
    min_d = [1e18]*n
    parent = [-1]*n
    min_d[0] = 0.0
    heap = [(0.0, 0)]
    edges = []
    while heap:
        d, u = heapq.heappop(heap)
        if visited[u]: continue
        visited[u] = True
        if parent[u] >= 0: edges.append((parent[u], u))
        for v in range(n):
            if not visited[v]:
                dd = math.hypot(pts[u][0]-pts[v][0], pts[u][1]-pts[v][1])
                if dd < min_d[v]:
                    min_d[v] = dd; parent[v] = u
                    heapq.heappush(heap, (dd, v))
    return edges

SEGMENTS = []
VIAS = []

def generate_routes():
    pad_map = build_net_pad_map()
    for idx, (net, pts) in enumerate(sorted(pad_map.items())):
        if net == "GND":
            for px, py in pts: VIAS.append((px, py, "GND"))
            continue
        is_power = net in POWER_NETS_SET
        width = 0.5 if is_power else 0.2
        layer = "B.Cu" if is_power else "F.Cu"
        for ei, (i, j) in enumerate(prim_mst(pts)):
            x1, y1 = pts[i]; x2, y2 = pts[j]
            if abs(x1-x2) < 0.01:
                SEGMENTS.append((x1,y1,x2,y2,layer,width,net))
            elif abs(y1-y2) < 0.01:
                SEGMENTS.append((x1,y1,x2,y2,layer,width,net))
            elif (idx+ei) % 2 == 0:
                SEGMENTS.append((x1,y1,x2,y1,layer,width,net))
                SEGMENTS.append((x2,y1,x2,y2,layer,width,net))
            else:
                SEGMENTS.append((x1,y1,x1,y2,layer,width,net))
                SEGMENTS.append((x1,y2,x2,y2,layer,width,net))

# ─────────────────────────────────────────────────────────────────────────────
# KiCad PCB 生成
# ─────────────────────────────────────────────────────────────────────────────
def pad_sexpr(pad_num, dx, dy, pw, ph, shape, net_name):
    net_i, net_n = ni(net_name)
    net_clause = f'\n      (net {net_i} "{net_n}")' if net_name else ""
    return (
        f'    (pad "{pad_num}" smd {shape} (at {dx:.4f} {dy:.4f}) '
        f'(size {pw:.4f} {ph:.4f}) (layers "F.Cu" "F.Paste" "F.Mask"){net_clause}'
        f'\n      (uuid "{uid()}"))'
    )

def generate():
    generate_routes()
    w('(kicad_pcb (version 20240108) (generator "pcbnew") (generator_version "8.0")')
    w('  (general (thickness 1.6))')
    w('  (paper "A4")')
    w('  (layers')
    for ldef in [
        '(0 "F.Cu" signal)', '(31 "B.Cu" signal)',
        '(34 "B.Paste" user)', '(35 "F.Paste" user)',
        '(36 "B.SilkS" user "B.Silkscreen")', '(37 "F.SilkS" user "F.Silkscreen")',
        '(38 "B.Mask" user)', '(39 "F.Mask" user)',
        '(44 "Edge.Cuts" user)', '(49 "F.Fab" user "F.Fabrication")',
    ]:
        w(f'    {ldef}')
    w('  )')
    w('  (setup (pad_to_mask_clearance 0.05) (solder_mask_min_width 0)'
      ' (pcbplotparams (layerselection 0x00010fc_ffffffff)))')
    w()
    w('  (net 0 "")')
    for i, name in enumerate(NETS_LIST, 1):
        w(f'  (net {i} "{name}")')
    w()

    for ref, value, fp_key, cx, cy, rot, lcsc, pad_nets in PLACEMENTS:
        w(f'  (footprint "{fp_key}" (layer "F.Cu") (at {cx:.4f} {cy:.4f} {rot})')
        w(f'    (property "Reference" "{ref}" (at 0 -2.5 0)'
          f' (layer "F.SilkS") (effects (font (size 1 1))))')
        w(f'    (property "Value" "{value}" (at 0 2.5 0)'
          f' (layer "F.Fab") (effects (font (size 1 1))))')
        w(f'    (property "LCSC" "{lcsc}" (at 0 0 0)'
          f' (layer "F.Fab") (hide yes) (effects (font (size 1 1))))')
        w(f'    (uuid "{uid()}")')
        for pd in FP.get(fp_key, []):
            pnum = str(pd[0])
            w(pad_sexpr(pnum, pd[1], pd[2], pd[3], pd[4], pd[5],
                        pad_nets.get(pnum, "")))
        w('  )')
        w()

    # 走线
    for x1,y1,x2,y2,layer,width,net_name in SEGMENTS:
        net_i, _ = ni(net_name)
        w(f'  (segment (start {x1:.4f} {y1:.4f}) (end {x2:.4f} {y2:.4f})'
          f' (width {width}) (layer "{layer}") (net {net_i}) (uuid "{uid()}"))')
    w()

    # 过孔（GND）
    seen = set()
    for vx, vy, vnet in VIAS:
        k = (round(vx,3), round(vy,3))
        if k in seen: continue
        seen.add(k)
        net_i, _ = ni(vnet)
        w(f'  (via (at {vx:.4f} {vy:.4f}) (size 0.8) (drill 0.4)'
          f' (layers "F.Cu" "B.Cu") (net {net_i}) (uuid "{uid()}"))')
    w()

    # B.Cu GND 铺铜
    gnd_i = NET_IDX["GND"]
    w(f'  (zone (net {gnd_i}) (net_name "GND") (layer "B.Cu") (uuid "{uid()}")')
    w('    (hatch full 0.508) (connect_pads (clearance 0.2)) (min_thickness 0.25)')
    w('    (fill yes (arc_segments 16) (thermal_gap 0.3) (thermal_bridge_width 0.3))')
    w(f'    (polygon (pts (xy 0.5 0.5) (xy {BOARD_W-0.5:.1f} 0.5)'
      f' (xy {BOARD_W-0.5:.1f} {BOARD_H-0.5:.1f}) (xy 0.5 {BOARD_H-0.5:.1f}))))')
    w()

    # 板框
    for x0,y0,x1,y1 in [(0,0,BOARD_W,0),(BOARD_W,0,BOARD_W,BOARD_H),
                         (BOARD_W,BOARD_H,0,BOARD_H),(0,BOARD_H,0,0)]:
        w(f'  (gr_line (start {x0} {y0}) (end {x1} {y1})'
          f' (stroke (width 0.05) (type default)) (layer "Edge.Cuts") (uuid "{uid()}"))')

    # 电池焊盘标注丝印
    w(f'  (gr_text "BAT+" (at 3.5 39.5 0) (layer "F.SilkS")'
      f' (effects (font (size 1.2 1.2) (bold yes))) (uuid "{uid()}"))')
    w(f'  (gr_text "BAT-" (at 8.5 39.5 0) (layer "F.SilkS")'
      f' (effects (font (size 1.2 1.2) (bold yes))) (uuid "{uid()}"))')
    w(f'  (gr_text "Glove Mouse v1.2  {BOARD_W:.0f}x{BOARD_H:.0f}mm"'
      f' (at {BOARD_W/2:.1f} 1.5 0) (layer "F.SilkS")'
      f' (effects (font (size 1.0 1.0))) (uuid "{uid()}"))')
    w()
    w(')')

def write_file():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    generate()
    path = os.path.join(script_dir, "glove_mouse.kicad_pcb")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(OUT))
    seg_n = len(SEGMENTS)
    via_n = len(set((round(v[0],3),round(v[1],3)) for v in VIAS))
    print(f"[OK] {os.path.abspath(path)}")
    print(f"     {len(PLACEMENTS)} components  {len(NETS_LIST)} nets")
    print(f"     {seg_n} segments  {via_n} vias  {BOARD_W:.0f}x{BOARD_H:.0f}mm")
    print()
    print("电源路径:")
    print("  锂电池导线 → BT1 裸焊盘 → SW1(开关) → MT3608 升压(4.6V) → XIAO VIN")
    print("  MT3608 输出电压: Vout = 0.6*(1+R_boost1/R_boost2)")
    print("         = 0.6*(1+100k/15k) = 4.60V")
    print("  充电: 通过 XIAO 自带 USB-C 口，无需外部充电电路")
    print()
    print("BT1 焊接说明:")
    print("  左焊盘(BAT+): 焊接锂电池红线（正极）")
    print("  右焊盘(BAT-): 焊接锂电池黑线（负极）")

if __name__ == "__main__":
    write_file()
