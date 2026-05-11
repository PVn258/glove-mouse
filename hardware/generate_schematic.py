#!/usr/bin/env python3
"""
手套鼠标 PCB - KiCad 6 原理图生成器
输出 glove_mouse.kicad_sch，可直接导入立创EDA专业版

用法:
  python generate_schematic.py

导入步骤（立创EDA专业版）:
  1. 文件 → 导入 → KiCad 工程（选 hardware/ 目录）
  2. 导入后，选中所有元件 → 右键 → 更新封装（用LCSC编号重新绑定）
     各元件LCSC编号已写入 Footprint/LCSC 属性

设计概述：
  锂电池 → 裸焊盘(BT1) → 滑动开关(SW1) → MT3608 升压(4.6V) → XIAO VIN
  XIAO ESP32C6 内置 USB-C 充电 + LDO(3.3V)，无需外部充电电路
"""

import uuid, os, math

# ─────────────────────────────────────────────────────────────
# 辅助
# ─────────────────────────────────────────────────────────────
def uid():
    return str(uuid.uuid4())

OUT = []
def w(s=""):
    OUT.append(s)

def prop(name, val, x=0, y=0, size=1.27, hide=False):
    h = " hide" if hide else ""
    return (f'    (property "{name}" "{val}" (at {x:.4f} {y:.4f} 0)\n'
            f'      (effects (font (size {size} {size})){h})\n'
            f'    )')

def pin_s(name, num, ptype, px, py, angle, length=2.54):
    return (f'        (pin {ptype} line (at {px:.4f} {py:.4f} {angle}) (length {length:.4f})\n'
            f'          (name "{name}" (effects (font (size 1.016 1.016))))\n'
            f'          (number "{num}" (effects (font (size 1.016 1.016)))))')

def rect_s(x1, y1, x2, y2, lw=0.254):
    return (f'      (rectangle (start {x1:.4f} {y1:.4f}) (end {x2:.4f} {y2:.4f})\n'
            f'        (stroke (width {lw}) (type default)) (fill (type background)))')

def rotate_offset(dx, dy, deg):
    if deg == 0:
        return dx, dy
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return dx*c - dy*s, dx*s + dy*c

# ─────────────────────────────────────────────────────────────
# 自定义符号库
# pins: [(name, number, type, rel_x, rel_y, angle)]
# SYM_PINS 存 {pin_number: (rel_x, rel_y, pin_angle)}
# ─────────────────────────────────────────────────────────────
LIB_SYMS = {}
SYM_PINS = {}   # name → {pin_number: (rel_x, rel_y, pin_angle)}

def def_sym(name, body, pins, ref_pfx="U"):
    x1, y1, x2, y2 = body
    pin_lines = "\n".join(pin_s(*p) for p in pins)
    # 存储 (rel_x, rel_y, pin_angle) 以便生成导线存根
    SYM_PINS[name] = {p[1]: (p[3], p[4], p[5]) for p in pins}
    LIB_SYMS[name] = (
        f'  (symbol "{name}"\n'
        f'    (pin_numbers hide) (pin_names (offset 0.508)) (in_bom yes) (on_board yes)\n'
        + prop("Reference", ref_pfx, 0, y1 - 1.27, hide=True) + "\n"
        + prop("Value", name, 0, y2 + 1.27, hide=True) + "\n"
        + prop("Footprint", "", 0, 0, hide=True) + "\n"
        + prop("Datasheet", "~", 0, 0, hide=True) + "\n"
        + prop("LCSC", "", 0, 0, hide=True) + "\n"
        + f'    (symbol "{name}_0_1"\n'
        + rect_s(x1, y1, x2, y2) + "\n"
        + f'    )\n'
        + f'    (symbol "{name}_1_1"\n'
        + pin_lines + "\n"
        + f'    )\n'
        + f'  )'
    )

STUB = 2.54  # 导线存根长度 (mm)

def wire_dir(pin_angle, comp_rot):
    """引脚向外延伸方向（与引脚stub方向相反，再经元件旋转）"""
    outward = (pin_angle + 180) % 360
    r = math.radians(outward)
    dx, dy = math.cos(r), math.sin(r)
    return rotate_offset(dx * STUB, dy * STUB, comp_rot)

# ── 通用电阻（使用 KiCad 标准 lib_id，嘉立创EDA可自动识别）────
def_sym("Device:R", (-1.27, 0.508, 1.27, -0.508), [
    ("1", "1", "passive", -2.54, 0,  0),
    ("2", "2", "passive",  2.54, 0, 180),
], ref_pfx="R")

# ── 通用电容 ──────────────────────────────────────────────────
def_sym("Device:C", (-0.508, 1.27, 0.508, -1.27), [
    ("1", "1", "passive", 0,  2.54, 270),
    ("2", "2", "passive", 0, -2.54,  90),
], ref_pfx="C")

# ── 电感 ─────────────────────────────────────────────────────
def_sym("Device:L", (-1.27, 0.508, 1.27, -0.508), [
    ("1", "1", "passive", -2.54, 0,  0),
    ("2", "2", "passive",  2.54, 0, 180),
], ref_pfx="L")

# ── 二极管（K=阴极 A=阳极）────────────────────────────────────
def_sym("Device:D", (-1.27, 1.27, 1.27, -1.27), [
    ("K", "K", "passive", -2.54, 0,  0),
    ("A", "A", "passive",  2.54, 0, 180),
], ref_pfx="D")

# ── MT3608 升压 IC (SOT-23-6) ────────────────────────────────
# 引脚: 1=GND 2=VIN 3=EN 4=FB 5=SW 6=NC
def_sym("MT3608", (-5.08, 5.08, 5.08, -5.08), [
    ("GND", "1", "power_in",   -7.62,  3.81,   0),
    ("VIN", "2", "power_in",   -7.62,  1.27,   0),
    ("EN",  "3", "input",      -7.62, -1.27,   0),
    ("FB",  "4", "input",       7.62, -1.27, 180),
    ("SW",  "5", "output",      7.62,  1.27, 180),
    ("NC",  "6", "no_connect",  7.62,  3.81, 180),
])

# ── XIAO ESP32C6 (Seeed 102010510) 14引脚模块 ────────────────
# 左侧 pin1-7: GND 3V3 GPIO2 GPIO3 GPIO4 GPIO5 GPIO6/SDA
# 右侧 pin8-14: VIN GND GPIO7/SCL GPIO21 GPIO18 GPIO20 GPIO19
def_sym("XIAO_ESP32C6", (-10.16, 10.16, 10.16, -10.16), [
    ("GND",       "1",  "power_in",     -12.70,  8.89,   0),
    ("3V3",       "2",  "power_out",    -12.70,  6.35,   0),
    ("GPIO2",     "3",  "bidirectional",-12.70,  3.81,   0),
    ("GPIO3",     "4",  "bidirectional",-12.70,  1.27,   0),
    ("GPIO4",     "5",  "bidirectional",-12.70, -1.27,   0),
    ("GPIO5",     "6",  "bidirectional",-12.70, -3.81,   0),
    ("GPIO6/SDA", "7",  "bidirectional",-12.70, -6.35,   0),
    ("VIN",       "8",  "power_in",      12.70,  8.89, 180),
    ("GND",       "9",  "power_in",      12.70,  6.35, 180),
    ("GPIO7/SCL", "10", "bidirectional", 12.70,  3.81, 180),
    ("GPIO21",    "11", "bidirectional", 12.70,  1.27, 180),
    ("GPIO18",    "12", "bidirectional", 12.70, -1.27, 180),
    ("GPIO20",    "13", "bidirectional", 12.70, -3.81, 180),
    ("GPIO19",    "14", "bidirectional", 12.70, -6.35, 180),
])

# ── 电池裸焊盘（引脚编号与 PCB 焊盘名一致：+ / -）─────────────
def_sym("BAT_PAD", (-3.81, 1.27, 3.81, -1.27), [
    ("+", "+", "passive", -6.35, 0,   0),
    ("-", "-", "passive",  6.35, 0, 180),
], ref_pfx="BT")

# ── 滑动电源开关 ──────────────────────────────────────────────
def_sym("SLIDE_SW", (-3.81, 2.54, 3.81, -2.54), [
    ("1", "1", "passive", -6.35,  1.27,   0),
    ("2", "2", "passive",  6.35,  0.00, 180),
    ("3", "3", "passive", -6.35, -1.27,   0),
], ref_pfx="SW")

# ── MPU-6050 六轴IMU (QFN-24，常用引脚) ──────────────────────
def_sym("MPU6050", (-7.62, 8.89, 7.62, -8.89), [
    ("VCC",    "1",  "power_in",      -10.16,  7.62,   0),
    ("GND",    "2",  "power_in",      -10.16,  5.08,   0),
    ("SCL",    "3",  "input",         -10.16,  2.54,   0),
    ("SDA",    "4",  "bidirectional", -10.16,  0.00,   0),
    ("AD0",    "5",  "input",         -10.16, -2.54,   0),
    ("VLOGIC", "6",  "power_in",      -10.16, -5.08,   0),
    ("CLKIN",  "7",  "input",         -10.16, -7.62,   0),
    ("INT",    "8",  "output",         10.16,  7.62, 180),
    ("FSYNC",  "9",  "input",          10.16,  5.08, 180),
    ("XDA",    "10", "bidirectional",  10.16,  2.54, 180),
    ("XCL",    "11", "input",          10.16,  0.00, 180),
])

# ── LM339 单比较器单元 ─────────────────────────────────────────
def_sym("LM339_CMP", (-5.08, 3.81, 5.08, -3.81), [
    ("IN+", "1", "input",      -7.62,  2.54,   0),
    ("IN-", "2", "input",      -7.62, -2.54,   0),
    ("OUT", "3", "open_drain",  7.62,  0.00, 180),
    ("VCC", "4", "power_in",   -7.62,  0.00,   0),
    ("GND", "5", "power_in",    7.62,  2.54, 180),
])

# ── 微调电位器 3224W（引脚编号 1/W/3，W用字符串以便查找）────────
def_sym("TRIMPOT", (-3.81, 2.54, 3.81, -2.54), [
    ("1", "1", "passive", -6.35,  1.27,   0),
    ("W", "W", "passive",  6.35,  0.00, 180),   # 编号"W"与COMPONENTS键匹配
    ("3", "3", "passive", -6.35, -1.27,   0),
], ref_pfx="RV")

# ── JST PH2.0 2P ─────────────────────────────────────────────
def_sym("JST2P", (-2.54, 2.54, 2.54, -2.54), [
    ("1", "1", "passive", -5.08,  1.27,   0),
    ("2", "2", "passive", -5.08, -1.27,   0),
], ref_pfx="J")

# ─────────────────────────────────────────────────────────────
# 元件放置表
# (ref, value, sym_name, x_mm, y_mm, rot_deg, lcsc, footprint,
#  {pin_number: net_name})
# 注意：pin_number 必须与 SYM_PINS 的 key 一致
# ─────────────────────────────────────────────────────────────
COMPONENTS = [

  # ══ 电源：电池焊盘 → 开关 → MT3608 升压 → XIAO VIN ══════════

  ("BT1", "LiPo Battery", "BAT_PAD", 30, 30, 0,
   "—", "BAT-SOLDER",
   {"+":"BAT_RAW", "-":"GND"}),

  ("SW1", "Power SW", "SLIDE_SW", 60, 30, 0,
   "C431540", "SS-12D00-G",
   {"1":"GND", "2":"VBAT", "3":"BAT_RAW"}),

  # MT3608: Vout=0.6×(1+100k/15k)≈4.6V
  ("U_BOOST", "MT3608", "MT3608", 90, 30, 0,
   "C84817", "Package_TO_SOT_SMD:SOT-23-6",
   {"1":"GND", "2":"VBAT", "3":"VBAT", "4":"BOOST_FB", "5":"BOOST_SW", "6":"NC_B"}),

  ("L1", "4.7uH", "Device:L", 115, 30, 0,
   "C1046", "Inductor_SMD:L_0603_1608Metric",
   {"1":"VBAT", "2":"BOOST_SW"}),

  ("D1", "SS14", "Device:D", 135, 30, 0,
   "C2480", "Diode_SMD:D_SOD-123",
   {"K":"BOOST_SW", "A":"BOOST_OUT"}),

  ("C_bin",  "10uF",  "Device:C", 90,  15, 0,
   "C17024", "Capacitor_SMD:C_0805_2012Metric",
   {"1":"VBAT", "2":"GND"}),

  ("C_bout", "22uF",  "Device:C", 135, 15, 0,
   "C45783", "Capacitor_SMD:C_0805_2012Metric",
   {"1":"BOOST_OUT", "2":"GND"}),

  ("R_boost1", "100k", "Device:R", 150, 30, 90,
   "C25741", "Resistor_SMD:R_0402_1005Metric",
   {"1":"BOOST_OUT", "2":"BOOST_FB"}),

  ("R_boost2", "15k",  "Device:R", 150, 15, 90,
   "C25856", "Resistor_SMD:R_0402_1005Metric",
   {"1":"BOOST_FB", "2":"GND"}),

  # ══ 主控：XIAO ESP32C6 ════════════════════════════════════════
  ("U1", "XIAO ESP32C6", "XIAO_ESP32C6", 195, 80, 0,
   "Seeed-102010510", "XIAO-ESP32C6_21x17.5mm",
   {"1":"GND",       "2":"3V3",       "3":"FSR_L_DO",
    "4":"FSR_R_DO",  "5":"FLEX_DO",   "6":"NC1",
    "7":"SDA",       "8":"BOOST_OUT", "9":"GND",
    "10":"SCL",      "11":"NC2",      "12":"NC3",
    "13":"NC4",      "14":"NC5"}),

  ("C8",  "100nF", "Device:C", 178, 68, 0,
   "C14663", "Capacitor_SMD:C_0402_1005Metric",
   {"1":"3V3", "2":"GND"}),
  ("C9",  "22uF",  "Device:C", 172, 68, 0,
   "C45783", "Capacitor_SMD:C_0805_2012Metric",
   {"1":"3V3", "2":"GND"}),

  # ══ MPU-6050 ═════════════════════════════════════════════════
  ("U2", "MPU-6050", "MPU6050", 240, 80, 0,
   "C24112", "Package_DFN_QFN:QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm",
   {"1":"3V3",  "2":"GND",  "3":"SCL", "4":"SDA",
    "5":"GND",  "6":"3V3",  "7":"GND",
    "8":"NC6",  "9":"GND",  "10":"NC7", "11":"NC8"}),

  ("C10",   "100nF", "Device:C", 228, 68, 0,
   "C14663", "Capacitor_SMD:C_0402_1005Metric",
   {"1":"3V3", "2":"GND"}),
  ("C11",   "10uF",  "Device:C", 222, 68, 0,
   "C17024",  "Capacitor_SMD:C_0805_2012Metric",
   {"1":"3V3", "2":"GND"}),
  ("C_vlog","100nF", "Device:C", 252, 68, 0,
   "C14663", "Capacitor_SMD:C_0402_1005Metric",
   {"1":"3V3", "2":"GND"}),

  ("R_sda", "4.7k", "Device:R", 228, 96, 90,
   "C23162", "Resistor_SMD:R_0402_1005Metric",
   {"1":"3V3", "2":"SDA"}),
  ("R_scl", "4.7k", "Device:R", 236, 96, 90,
   "C23162", "Resistor_SMD:R_0402_1005Metric",
   {"1":"3V3", "2":"SCL"}),

  # ══ LM339 比较器（3路复用同一颗 SOP-14）══════════════════════
  ("U7A", "LM339 CMP1", "LM339_CMP", 60, 140, 0,
   "C7701", "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm",
   {"1":"VREF_FLEX", "2":"VMID_FLEX", "3":"FLEX_DO",
    "4":"3V3",       "5":"GND"}),
  ("U7B", "LM339 CMP2", "LM339_CMP", 60, 155, 0,
   "C7701", "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm",
   {"1":"VMID_FSR_L", "2":"VREF_FSR", "3":"FSR_L_DO",
    "4":"3V3",        "5":"GND"}),
  ("U7C", "LM339 CMP3", "LM339_CMP", 60, 170, 0,
   "C7701", "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm",
   {"1":"VMID_FSR_R", "2":"VREF_FSR", "3":"FSR_R_DO",
    "4":"3V3",        "5":"GND"}),

  ("C14", "100nF", "Device:C", 45, 140, 0,
   "C14663", "Capacitor_SMD:C_0402_1005Metric",
   {"1":"3V3", "2":"GND"}),
  ("C15", "4.7uF", "Device:C", 39, 140, 0,
   "C17658",  "Capacitor_SMD:C_0805_2012Metric",
   {"1":"3V3", "2":"GND"}),

  # ── Flex 分压 ────────────────────────────────────────────────
  ("R1",    "47k",      "Device:R", 95, 140, 90,
   "C25819", "Resistor_SMD:R_0402_1005Metric",
   {"1":"3V3", "2":"VMID_FLEX"}),
  ("R_rf1", "10k",      "Device:R", 95, 150, 90,
   "C25905", "Resistor_SMD:R_0402_1005Metric",
   {"1":"3V3", "2":"VREF_FLEX_PRE"}),
  ("RV1",   "10k Trim", "TRIMPOT", 108, 150, 0,
   "C128917", "Potentiometer_Bourns:Potentiometer_Bourns_3224W_Vertical",
   {"1":"GND", "W":"VREF_FLEX", "3":"VREF_FLEX_PRE"}),
  ("J3",    "Flex Sensor", "JST2P", 130, 140, 0,
   "C131337", "Connector_JST:JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical",
   {"1":"VMID_FLEX", "2":"GND"}),

  # ── FSR 分压 ─────────────────────────────────────────────────
  ("R2",    "10k",      "Device:R", 95, 162, 90,
   "C25905", "Resistor_SMD:R_0402_1005Metric",
   {"1":"3V3", "2":"VMID_FSR_L"}),
  ("R3",    "10k",      "Device:R", 95, 170, 90,
   "C25905", "Resistor_SMD:R_0402_1005Metric",
   {"1":"3V3", "2":"VMID_FSR_R"}),
  ("R_rf2", "10k",      "Device:R", 95, 178, 90,
   "C25905", "Resistor_SMD:R_0402_1005Metric",
   {"1":"3V3", "2":"VREF_FSR_PRE"}),
  ("RV2",   "10k Trim", "TRIMPOT", 108, 178, 0,
   "C128917", "Potentiometer_Bourns:Potentiometer_Bourns_3224W_Vertical",
   {"1":"GND", "W":"VREF_FSR", "3":"VREF_FSR_PRE"}),
  ("J4",    "FSR Left",  "JST2P", 130, 157, 0,
   "C131337", "Connector_JST:JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical",
   {"1":"VMID_FSR_L", "2":"GND"}),
  ("J5",    "FSR Right", "JST2P", 130, 167, 0,
   "C131337", "Connector_JST:JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical",
   {"1":"VMID_FSR_R", "2":"GND"}),
]

# ─────────────────────────────────────────────────────────────
# 生成 KiCad 6 (.kicad_sch)
# ─────────────────────────────────────────────────────────────
def generate():
    main_uuid = uid()

    w(f'(kicad_sch (version 20231120) (generator "eeschema") (generator_version "8.0")')
    w(f'  (uuid "{main_uuid}")')
    w(f'  (paper "A2")')
    w()

    w("  (lib_symbols")
    for sym_str in LIB_SYMS.values():
        w(sym_str)
    w("  )")
    w()

    pwr_cnt = [0]

    def add_wire(x1, y1, x2, y2):
        w(f'  (wire (pts (xy {x1:.4f} {y1:.4f}) (xy {x2:.4f} {y2:.4f}))')
        w(f'    (stroke (width 0) (type default))')
        w(f'    (uuid "{uid()}")')
        w(f'  )')

    def add_power_gnd(x, y):
        pwr_cnt[0] += 1
        ref = f"#PWR{pwr_cnt[0]:03d}"
        w(f'  (symbol (lib_id "power:GND") (at {x:.4f} {y:.4f} 0) (unit 1)')
        w(f'    (uuid "{uid()}")')
        w(f'    {prop("Reference", ref, x, y-2, hide=True)}')
        w(f'    {prop("Value", "GND", x, y+2)}')
        w(f'    (pin "1" (uuid "{uid()}"))')
        w(f'  )')

    def add_label(net, x, y):
        w(f'  (label "{net}" (at {x:.4f} {y:.4f} 0)')
        w(f'    (effects (font (size 1.27 1.27)))')
        w(f'    (uuid "{uid()}")')
        w(f'  )')

    def add_no_connect(x, y):
        w(f'  (no_connect (at {x:.4f} {y:.4f}) (uuid "{uid()}"))')

    for comp in COMPONENTS:
        ref, value, sym_name, cx, cy, rot, lcsc, footprint, pin_nets = comp
        pin_offsets = SYM_PINS.get(sym_name, {})

        w(f'  (symbol (lib_id "{sym_name}") (at {cx:.4f} {cy:.4f} {rot}) (unit 1)')
        w(f'    (uuid "{uid()}")')
        w(f'    {prop("Reference", ref,       cx+2, cy-3, size=1.27)}')
        w(f'    {prop("Value",     value,     cx+2, cy+3, size=1.27)}')
        w(f'    {prop("Footprint", footprint, cx,   cy,   hide=True)}')
        w(f'    {prop("Datasheet", "~",       cx,   cy,   hide=True)}')
        w(f'    {prop("LCSC",      lcsc,      cx,   cy,   hide=True)}')
        for pnum in pin_nets:
            w(f'    (pin "{pnum}" (uuid "{uid()}"))')
        w(f'    (instances (project "glove_mouse"')
        w(f'      (path "/{main_uuid}" (reference "{ref}") (unit 1))')
        w(f'    ))')
        w(f'  )')

        # 每个引脚：画导线存根 + 放置网络标签（或GND符号 / NC标记）
        for pnum, net in pin_nets.items():
            pinfo = pin_offsets.get(pnum, (0, 0, 0))
            rdx, rdy = rotate_offset(pinfo[0], pinfo[1], rot)
            pin_x = cx + rdx
            pin_y = cy + rdy
            wdx, wdy = wire_dir(pinfo[2], rot)
            lx = pin_x + wdx
            ly = pin_y + wdy

            if net == "GND":
                add_wire(pin_x, pin_y, lx, ly)
                add_power_gnd(lx, ly)
            elif net.startswith("NC"):
                add_no_connect(pin_x, pin_y)
            else:
                add_wire(pin_x, pin_y, lx, ly)
                add_label(net, lx, ly)

    # 全局 GND 标志
    add_power_gnd(20, 200)
    w()

    # KiCad 8 必须包含 sheet_instances 节
    w('  (sheet_instances')
    w(f'    (path "/" (page "1"))')
    w('  )')
    w()
    w(")")

def write_file():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    generate()
    path = os.path.join(script_dir, "glove_mouse.kicad_sch")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(OUT))
    print(f"[OK] {os.path.abspath(path)}")
    print(f"     {len(COMPONENTS)} components, wire stubs enabled")
    print()
    print("导入后仍需手动操作（缺少封装问题）:")
    print("  JLC EDA 导入自定义KiCad符号时无法自动匹配其封装库")
    print("  请在导入后：选中元件 → 右键 → 更改器件 → 用LCSC编号搜索重新绑定")
    print()
    for comp in COMPONENTS:
        ref, value, _, _, _, _, lcsc, _, _ = comp
        if lcsc != "—":
            print(f"  {ref:12s} {value:20s}  LCSC: {lcsc}")

if __name__ == "__main__":
    write_file()
