#!/usr/bin/env python3
"""Generate anchor_board.kicad_sch — the anchor-board schematic netlist.

This script authored the schematic by placing components and connecting
them with same-named local labels / global power ports (no hand-tracked
UUIDs). It captures the full design: §4.1-4.9 from the anchor-board
README plus the §7 break-off dev rail. ERC-clean (0/0).

  Run from anywhere:  python3 hardware/anchor-board/tools/gen_schematic.py

IMPORTANT — this REGENERATES the whole sheet. Re-running it clobbers any
manual layout/tidying done in KiCad. Once the schematic has been
hand-tidied, treat `anchor_board.kicad_sch` as the source of truth and
retire this script — or, for a connectivity change, edit here and
re-run, then re-tidy. The netlist (which pins connect to which net) is
the part worth keeping here; the x/y placement is just a starting point.

Layout notes:
- Components sit on a 1.27 mm grid (on_grid() asserts this).
- Each label is pulled off its pin onto a short stub wire and oriented
  to read *away* from the component body, so text doesn't pile up on the
  component edge or overlap neighbours. Densely-packed pin columns get
  alternating stub lengths so adjacent labels stagger.
- Power ports and no-connects stay on the pin (ports are compact
  graphics; NC flags must sit on the pin to mark it).

KiCad symbol library path can be overridden with $KICAD_SYMBOL_DIR.
"""
import os
import re
import uuid
from collections import defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
_BOARD = os.path.normpath(os.path.join(_HERE, ".."))

KSYM = os.environ.get(
    "KICAD_SYMBOL_DIR",
    "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols")
PROJ_SYM = os.path.join(_BOARD, "anchor_board.kicad_sym")
OUT = os.path.join(_BOARD, "anchor_board.kicad_sch")
ROOT = "ccc23363-f05f-472d-883e-00c200b7d03a"
PROJECT = "anchor_board"
GRID = 1.27
STUB = 2.54  # base label stub length; dense columns alternate STUB / 2*STUB


def u():
    return str(uuid.uuid4())


def on_grid(x, y, what):
    for v in (x, y):
        if abs(round(v / GRID) * GRID - v) > 1e-6:
            raise AssertionError("OFF-GRID %s: (%s, %s)" % (what, x, y))


def extract_symbol(text, name):
    i = text.index('(symbol "%s"' % name)
    d = 0
    for k in range(i, len(text)):
        if text[k] == '(':
            d += 1
        elif text[k] == ')':
            d -= 1
            if d == 0:
                return text[i:k + 1]
    raise ValueError(name)


def embed(block, name, lib_id):
    block = block.replace('(symbol "%s"' % name, '(symbol "%s"' % lib_id, 1)
    out = []
    for n, line in enumerate(block.split("\n")):
        if line.lstrip().startswith("#"):
            continue
        out.append(("\t\t" if n == 0 else "\t") + line)
    return "\n".join(out)


def parse_pins(block):
    pins = {}
    for m in re.finditer(
        r'\(pin\s+\S+\s+\S+\s*\(at ([-\d.]+) ([-\d.]+) [-\d.]+\)\s*'
        r'\(length [\d.]+\)\s*\(name "[^"]*".*?\(number "([^"]+)"', block, re.S):
        x, y, num = m.groups()
        pins[num] = (float(x), float(y))
    return pins


dev = open(KSYM + "/Device.kicad_sym").read()
pwr = open(KSYM + "/power.kicad_sym").read()
sw = open(KSYM + "/Switch.kicad_sym").read()
conn = open(KSYM + "/Connector.kicad_sym").read()
cgen = open(KSYM + "/Connector_Generic.kicad_sym").read()
prj = open(PROJ_SYM).read()

raw = {
    "Device:C": extract_symbol(dev, "C"),
    "Device:R": extract_symbol(dev, "R"),
    "Device:L": extract_symbol(dev, "L"),
    "Device:D_TVS": extract_symbol(dev, "D_TVS"),
    "Device:Battery_Cell": extract_symbol(dev, "Battery_Cell"),
    "Device:LED_ARGB": extract_symbol(dev, "LED_ARGB"),
    "Switch:SW_Push": extract_symbol(sw, "SW_Push"),
    "Connector:TestPoint": extract_symbol(conn, "TestPoint"),
    "Connector_Generic:Conn_01x02": extract_symbol(cgen, "Conn_01x02"),
    "Connector_Generic:Conn_01x03": extract_symbol(cgen, "Conn_01x03"),
    "Connector_Generic:Conn_01x06": extract_symbol(cgen, "Conn_01x06"),
    "Connector_Generic:Conn_02x03_Odd_Even": extract_symbol(cgen, "Conn_02x03_Odd_Even"),
    "Connector_Generic:Conn_02x05_Odd_Even": extract_symbol(cgen, "Conn_02x05_Odd_Even"),
    "power:GND": extract_symbol(pwr, "GND"),
    "power:PWR_FLAG": extract_symbol(pwr, "PWR_FLAG"),
    "infinity-stumps:DWM3001C": extract_symbol(prj, "DWM3001C"),
    "infinity-stumps:3V0": extract_symbol(prj, "3V0"),
    "infinity-stumps:VSYS": extract_symbol(prj, "VSYS"),
    "infinity-stumps:VBAT": extract_symbol(prj, "VBAT"),
    "infinity-stumps:VBUS": extract_symbol(prj, "VBUS"),
    "infinity-stumps:TLV75530": extract_symbol(prj, "TLV75530"),
    "infinity-stumps:DW01A": extract_symbol(prj, "DW01A"),
    "infinity-stumps:FS8205A": extract_symbol(prj, "FS8205A"),
    "infinity-stumps:BQ24074": extract_symbol(prj, "BQ24074"),
    "infinity-stumps:TPD2E2U06": extract_symbol(prj, "TPD2E2U06"),
    "infinity-stumps:USB4105-GF-A": extract_symbol(prj, "USB4105-GF-A"),
    "infinity-stumps:W25Q128JV": extract_symbol(prj, "W25Q128JV"),
    "infinity-stumps:TPS22916C": extract_symbol(prj, "TPS22916C"),
}
bare = {k: k.split(":")[1] for k in raw}
PINS = {lib: parse_pins(blk) for lib, blk in raw.items()}
lib_syms = [embed(raw[lib], bare[lib], lib) for lib in raw]

# (ref, lib_id, value, footprint, x, y, ref_at, val_at)
comps = [
    # ===== §4.1 DWM3001C module + decoupling =====
    ("U1", "infinity-stumps:DWM3001C", "DWM3001C", "infinity-stumps:DWM3001C",
     127.0, 101.6, (140.97, 79.375), (140.97, 123.825)),
    ("C1", "Device:C", "100nF", "Capacitor_SMD:C_0402_1005Metric", 152.4, 81.28, (154.94, 80.01), (154.94, 82.55)),
    ("C2", "Device:C", "100nF", "Capacitor_SMD:C_0402_1005Metric", 165.1, 81.28, (167.64, 80.01), (167.64, 82.55)),
    ("C3", "Device:C", "10uF", "Capacitor_SMD:C_0805_2012Metric", 177.8, 81.28, (180.34, 80.01), (180.34, 82.55)),
    ("R1", "Device:R", "10k", "Resistor_SMD:R_0402_1005Metric", 109.22, 67.31, (111.76, 66.04), (111.76, 68.58)),
    ("C4", "Device:C", "100nF", "Capacitor_SMD:C_0402_1005Metric", 96.52, 85.09, (99.06, 83.82), (99.06, 86.36)),
    # ===== §4.2 USB-C input + ESD =====
    ("J1", "infinity-stumps:USB4105-GF-A", "USB4105-GF-A",
     "Connector_USB:USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal",
     39.37, 95.25, (39.37, 80.0), (39.37, 116.0)),
    ("U2", "infinity-stumps:TPD2E2U06", "TPD2E2U06", "Package_TO_SOT_SMD:SOT-563",
     74.93, 100.33, (74.93, 91.0), (74.93, 114.0)),
    ("R2", "Device:R", "5.1k", "Resistor_SMD:R_0402_1005Metric", 62.23, 80.01, (65.23, 78.74), (65.23, 81.28)),
    ("R3", "Device:R", "5.1k", "Resistor_SMD:R_0402_1005Metric", 69.85, 80.01, (72.85, 78.74), (72.85, 81.28)),
    ("D2", "Device:D_TVS", "SMF5.0A", "Diode_SMD:D_SOD-123", 54.61, 114.3, (54.61, 109.0), (54.61, 119.5)),
    ("C5", "Device:C", "10uF", "Capacitor_SMD:C_0805_2012Metric", 62.23, 114.3, (65.23, 113.03), (65.23, 115.57)),
    ("C6", "Device:C", "100nF", "Capacitor_SMD:C_0402_1005Metric", 69.85, 114.3, (72.85, 113.03), (72.85, 115.57)),
    ("R4", "Device:R", "1M", "Resistor_SMD:R_0402_1005Metric", 62.23, 135.89, (65.23, 134.62), (65.23, 137.16)),
    ("C7", "Device:C", "4.7nF", "Capacitor_SMD:C_0402_1005Metric", 69.85, 135.89, (72.85, 134.62), (72.85, 137.16)),
    # ===== §4.3 BQ24074 charger =====
    ("U3", "infinity-stumps:BQ24074", "BQ24074", "Package_DFN_QFN:QFN-16-1EP_3x3mm_P0.5mm_EP1.7x1.7mm",
     259.08, 200.66, (259.08, 185.42), (259.08, 215.9)),
    ("C8", "Device:C", "1uF", "Capacitor_SMD:C_0603_1608Metric", 240.03, 173.99, (243.03, 172.72), (243.03, 175.26)),
    ("R6", "Device:R", "TBD (TMR ~10h)", "Resistor_SMD:R_0402_1005Metric", 250.19, 173.99, (253.19, 172.72), (253.19, 175.26)),
    ("R25", "Device:R", "TBD (ITERM)", "Resistor_SMD:R_0402_1005Metric", 260.35, 173.99, (263.35, 172.72), (263.35, 175.26)),
    ("R5", "Device:R", "909", "Resistor_SMD:R_0402_1005Metric", 270.51, 173.99, (273.51, 172.72), (273.51, 175.26)),
    ("R24", "Device:R", "TBD (ILIM)", "Resistor_SMD:R_0402_1005Metric", 280.67, 173.99, (283.67, 172.72), (283.67, 175.26)),
    ("R7", "Device:R", "10k", "Resistor_SMD:R_0402_1005Metric", 228.6, 187.96, (231.6, 186.69), (231.6, 189.23)),
    ("R8", "Device:R", "10k", "Resistor_SMD:R_0402_1005Metric", 228.6, 203.2, (231.6, 201.93), (231.6, 204.47)),
    ("C9", "Device:C", "1uF", "Capacitor_SMD:C_0603_1608Metric", 293.37, 196.85, (296.37, 195.58), (296.37, 198.12)),
    ("C10", "Device:C", "1uF", "Capacitor_SMD:C_0603_1608Metric", 215.9, 200.66, (218.9, 199.39), (218.9, 201.93)),
    ("R9", "Device:R", "10k", "Resistor_SMD:R_0402_1005Metric", 293.37, 209.55, (296.37, 208.28), (296.37, 210.82)),
    ("R10", "Device:R", "10k", "Resistor_SMD:R_0402_1005Metric", 293.37, 222.25, (296.37, 220.98), (296.37, 223.52)),
    ("R11", "Device:R", "0R", "Resistor_SMD:R_0402_1005Metric", 247.65, 229.87, (250.65, 228.6), (250.65, 231.14)),
    ("R12", "Device:R", "0R", "Resistor_SMD:R_0402_1005Metric", 260.35, 229.87, (263.35, 228.6), (263.35, 231.14)),
    # ===== §4.4 DW01A / FS8205A cell protection + 18650 =====
    ("BT1", "Device:Battery_Cell", "NCR18650B 3400mAh", "Battery:BatteryHolder_Keystone_1042_1x18650",
     60.96, 189.23, (66.04, 184.15), (66.04, 194.31)),
    ("U4", "infinity-stumps:DW01A", "DW01A", "Package_TO_SOT_SMD:SOT-23-6",
     109.22, 185.42, (109.22, 176.53), (109.22, 195.58)),
    ("U5", "infinity-stumps:FS8205A", "FS8205A", "Package_SO:TSSOP-8_4.4x3mm_P0.65mm",
     109.22, 219.71, (109.22, 207.01), (109.22, 232.41)),
    ("R13", "Device:R", "330", "Resistor_SMD:R_0402_1005Metric", 86.36, 173.99, (89.36, 172.72), (89.36, 175.26)),
    ("C11", "Device:C", "100nF", "Capacitor_SMD:C_0402_1005Metric", 86.36, 195.58, (89.36, 194.31), (89.36, 196.85)),
    ("R14", "Device:R", "2k", "Resistor_SMD:R_0402_1005Metric", 140.97, 198.12, (143.97, 196.85), (143.97, 199.39)),
    # ===== §4.5 TLV75530 LDO -> 3V0 rail =====
    ("U6", "infinity-stumps:TLV75530", "TLV75530", "infinity-stumps:X2SON-4_1x1mm_P0.5mm",
     228.6, 80.01, (228.6, 71.0), (228.6, 92.0)),
    ("C12", "Device:C", "1uF", "Capacitor_SMD:C_0603_1608Metric", 208.28, 86.36, (211.28, 85.09), (211.28, 87.63)),
    ("C13", "Device:C", "1uF", "Capacitor_SMD:C_0603_1608Metric", 254.0, 90.17, (257.0, 88.9), (257.0, 91.44)),
    ("C14", "Device:C", "10uF", "Capacitor_SMD:C_0805_2012Metric", 266.7, 90.17, (269.7, 88.9), (269.7, 91.44)),
    ("FB1", "Device:L", "Ferrite Bead", "Inductor_SMD:L_0603_1608Metric", 208.28, 71.12, (211.28, 69.85), (211.28, 72.39)),
    # ===== §4.6 SPI flash + load switch =====
    ("U7", "infinity-stumps:W25Q128JV", "W25Q128JVSIQ", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
     330.2, 109.22, (330.2, 99.0), (330.2, 119.5)),
    ("U8", "infinity-stumps:TPS22916C", "TPS22916C", "Package_BGA:WLP-4_0.83x0.83mm_P0.4mm",
     330.2, 130.81, (330.2, 124.0), (330.2, 138.0)),
    ("C15", "Device:C", "100nF", "Capacitor_SMD:C_0402_1005Metric", 358.14, 109.22, (361.14, 107.95), (361.14, 110.49)),
    ("C16", "Device:C", "1uF", "Capacitor_SMD:C_0603_1608Metric", 358.14, 130.81, (361.14, 129.54), (361.14, 132.08)),
    ("R15", "Device:R", "10k", "Resistor_SMD:R_0402_1005Metric", 303.53, 100.33, (306.53, 99.06), (306.53, 101.6)),
    ("R16", "Device:R", "10k", "Resistor_SMD:R_0402_1005Metric", 370.84, 105.41, (373.84, 104.14), (373.84, 106.68)),
    ("R17", "Device:R", "10k", "Resistor_SMD:R_0402_1005Metric", 370.84, 116.84, (373.84, 115.57), (373.84, 118.11)),
    # ===== §4.7 RGB LED + power button =====
    ("D1", "Device:LED_ARGB", "150141RV73100", "LED_SMD:LED_RGB_Wuerth-PLCC4_3.2x2.8mm_150141M173100",
     203.2, 254.0, (208.0, 246.0), (208.0, 263.0)),
    ("R18", "Device:R", "1k", "Resistor_SMD:R_0402_1005Metric", 177.8, 243.84, (180.8, 242.57), (180.8, 245.11)),
    ("R19", "Device:R", "680", "Resistor_SMD:R_0402_1005Metric", 177.8, 256.54, (180.8, 255.27), (180.8, 257.81)),
    ("R20", "Device:R", "680", "Resistor_SMD:R_0402_1005Metric", 177.8, 269.24, (180.8, 267.97), (180.8, 270.51)),
    ("SW1", "Switch:SW_Push", "SKHHALA010", "infinity-stumps:SW_Alps_SKHHAL",
     152.4, 254.0, (152.4, 247.0), (152.4, 261.0)),
    ("R21", "Device:R", "10k", "Resistor_SMD:R_0402_1005Metric", 139.7, 246.38, (142.7, 245.11), (142.7, 247.65)),
    ("C18", "Device:C", "100nF", "Capacitor_SMD:C_0402_1005Metric", 139.7, 261.62, (142.7, 260.35), (142.7, 262.89)),
    # ===== §4.8 VBAT voltage sense divider =====
    ("R22", "Device:R", "1M", "Resistor_SMD:R_0402_1005Metric", 50.8, 152.4, (53.8, 151.13), (53.8, 153.67)),
    ("R23", "Device:R", "1M", "Resistor_SMD:R_0402_1005Metric", 50.8, 165.1, (53.8, 163.83), (53.8, 166.37)),
    ("C19", "Device:C", "100nF", "Capacitor_SMD:C_0402_1005Metric", 63.5, 165.1, (66.5, 163.83), (66.5, 166.37)),
    # ===== §4.9 rail-level test points + bulk cap (right-side open area) =====
    ("TP1", "Connector:TestPoint", "VBUS", "TestPoint:TestPoint_Pad_D1.5mm", 304.8, 149.86, (304.8, 144.78), (304.8, 154.94)),
    ("TP2", "Connector:TestPoint", "VSYS", "TestPoint:TestPoint_Pad_D1.5mm", 314.96, 149.86, (314.96, 144.78), (314.96, 154.94)),
    ("TP3", "Connector:TestPoint", "VBAT", "TestPoint:TestPoint_Pad_D1.5mm", 325.12, 149.86, (325.12, 144.78), (325.12, 154.94)),
    ("TP4", "Connector:TestPoint", "3V0", "TestPoint:TestPoint_Pad_D1.5mm", 335.28, 149.86, (335.28, 144.78), (335.28, 154.94)),
    ("TP5", "Connector:TestPoint", "GND", "TestPoint:TestPoint_Pad_D1.5mm", 345.44, 149.86, (345.44, 144.78), (345.44, 154.94)),
    ("TP6", "Connector:TestPoint", "GND", "TestPoint:TestPoint_Pad_D1.5mm", 355.6, 149.86, (355.6, 144.78), (355.6, 154.94)),
    ("C20", "Device:C", "10uF", "Capacitor_SMD:C_0805_2012Metric", 374.65, 149.86, (377.65, 148.59), (377.65, 151.13)),
    # ===== §7 break-off dev rail (right-side open area) =====
    ("J2", "Connector_Generic:Conn_02x05_Odd_Even", "SWD 2x5 1.27mm",
     "Connector_PinHeader_1.27mm:PinHeader_2x05_P1.27mm_Vertical", 320.04, 177.8, (320.04, 169.0), (320.04, 186.0)),
    ("J8", "Connector_Generic:Conn_02x03_Odd_Even", "TC2030 SWD",
     "Connector:Tag-Connect_TC2030-IDC-NL_2x03_P1.27mm_Vertical", 358.14, 177.8, (358.14, 171.0), (358.14, 184.0)),
    ("J3", "Connector_Generic:Conn_01x03", "UART TX/RX/GND",
     "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical", 320.04, 198.12, (320.04, 191.0), (320.04, 205.0)),
    ("J4", "Connector_Generic:Conn_01x06", "GPIO breakout",
     "Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical", 358.14, 201.93, (358.14, 191.0), (358.14, 213.0)),
    ("J5", "Connector_Generic:Conn_01x02", "3V0 current shunt",
     "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical", 320.04, 220.98, (320.04, 215.0), (320.04, 226.0)),
    ("R26", "Device:R", "0R", "Resistor_SMD:R_0402_1005Metric", 332.74, 219.71, (335.74, 218.44), (335.74, 220.98)),
    ("J6", "Connector_Generic:Conn_01x02", "LED disable",
     "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical", 358.14, 220.98, (358.14, 215.0), (358.14, 226.0)),
    ("J7", "Connector_Generic:Conn_01x02", "Reset/boot strap",
     "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical", 320.04, 240.03, (320.04, 234.0), (320.04, 245.0)),
]

# ---- section grouping & placement -------------------------------------
# Each functional block gets its own framed area on the sheet. The comps
# above keep their *relative* layout within a block; here the whole block
# is translated so its parts cluster together, instead of being scattered.
SECTION_REFS = {
    "4.1": ["U1", "C1", "C2", "C3", "R1", "C4"],
    "4.2": ["J1", "U2", "R2", "R3", "D2", "C5", "C6", "R4", "C7"],
    "4.3": ["U3", "C8", "R6", "R25", "R5", "R24", "R7", "R8",
            "C9", "C10", "R9", "R10", "R11", "R12"],
    "4.4": ["BT1", "U4", "U5", "R13", "C11", "R14"],
    "4.5": ["U6", "C12", "C13", "C14", "FB1"],
    "4.6": ["U7", "U8", "C15", "C16", "R15", "R16", "R17"],
    "4.7": ["D1", "R18", "R19", "R20", "SW1", "R21", "C18"],
    "4.8": ["R22", "R23", "C19"],
    "4.9": ["TP1", "TP2", "TP3", "TP4", "TP5", "TP6", "C20"],
    "7": ["J2", "J8", "J3", "J4", "J5", "R26", "J6", "J7"],
}
SECTION_TITLE = {
    "4.1": "4.1  DWM3001C module + decoupling",
    "4.2": "4.2  USB-C input + ESD",
    "4.3": "4.3  BQ24074 Li-ion charger",
    "4.4": "4.4  Cell protection + 18650",
    "4.5": "4.5  TLV75530 3.0 V LDO",
    "4.6": "4.6  SPI flash + load switch",
    "4.7": "4.7  RGB LED + power button",
    "4.8": "4.8  VBAT sense divider",
    "4.9": "4.9  Rail test points",
    "7": "7  Break-off dev rail",
}
# target (min component-x, min component-y) for each block — on the 1.27
# grid. Roughly follows power flow: input top-left, rails across the top,
# the module centre, peripherals down the right, dev aids along the bottom.
SECTION_TARGET = {
    "4.2": (50.8, 27.94),    # USB-C input        — top left
    "4.3": (140.97, 27.94),  # charger            — top middle
    "4.5": (256.54, 27.94),  # LDO                — top right
    "4.6": (256.54, 78.74),  # flash              — right, below LDO
    "4.4": (25.4, 119.38),   # cell protection    — middle left
    "4.1": (140.97, 119.38), # DWM3001C module    — centre
    "4.7": (256.54, 142.24), # RGB LED + button   — right, below flash
    "7": (38.1, 203.2),      # break-off dev rail — bottom left
    "4.8": (140.97, 205.74), # VBAT sense divider — bottom middle
    "4.9": (140.97, 252.73), # rail test points   — bottom middle, lower
}
comp_section = {ref: sec for sec, refs in SECTION_REFS.items() for ref in refs}
assert set(comp_section) == {c[0] for c in comps}, "SECTION_REFS / comps mismatch"

_sec_min = {}
for _c in comps:
    _m = _sec_min.setdefault(comp_section[_c[0]], [_c[4], _c[5]])
    _m[0] = min(_m[0], _c[4])
    _m[1] = min(_m[1], _c[5])
_sec_delta = {_s: (round(SECTION_TARGET[_s][0] - _m[0], 4),
                   round(SECTION_TARGET[_s][1] - _m[1], 4))
              for _s, _m in _sec_min.items()}


def _shift(sec, x, y):
    dx, dy = _sec_delta[sec]
    return (round(x + dx, 4), round(y + dy, 4))


comps = [(ref, lib, val, fp,
          *_shift(comp_section[ref], x, y),
          _shift(comp_section[ref], *rat), _shift(comp_section[ref], *vat))
         for (ref, lib, val, fp, x, y, rat, vat) in comps]
comp_xy = {c[0]: (c[4], c[5]) for c in comps}
comp_lib = {c[0]: c[1] for c in comps}

# Every pin coordinate of every component — a label's stub must never
# touch one of these (other than its own), or it would short two nets.
# `sec_pts` collects, per section, every point used to size its frame.
ALL_PIN_COORDS = set()
sec_pts = defaultdict(list)
for _ref in comp_xy:
    _cx, _cy = comp_xy[_ref]
    for _lx, _ly in PINS[comp_lib[_ref]].values():
        _p = (round(_cx + _lx, 4), round(_cy - _ly, 4))
        ALL_PIN_COORDS.add(_p)
        sec_pts[comp_section[_ref]].append(_p)

# coord -> direction the pin faces, outward from its component ('L'/'R'/'U'/'D')
_pin_dir = {}
# coord -> the section the pin's component belongs to
_pin_section = {}


def pin_xy(ref, num):
    cx, cy = comp_xy[ref]
    lx, ly = PINS[comp_lib[ref]][str(num)]
    p = (round(cx + lx, 4), round(cy - ly, 4))
    on_grid(p[0], p[1], "%s.%s" % (ref, num))
    dx, dy = p[0] - cx, p[1] - cy
    if abs(dx) >= abs(dy):
        _pin_dir[p] = "L" if dx < 0 else "R"
    else:
        _pin_dir[p] = "U" if dy < 0 else "D"  # KiCad y grows downward
    _pin_section[p] = comp_section[ref]
    return p


# §4.1 is captured with explicit wires/junctions/power-ports (not labels);
# its hand-drawn connectivity is translated by the §4.1 block delta too.
_d41x, _d41y = _sec_delta["4.1"]
wires = [(round(x1 + _d41x, 4), round(y1 + _d41y, 4),
          round(x2 + _d41x, 4), round(y2 + _d41y, 4)) for (x1, y1, x2, y2) in [
    (127.0, 77.47, 177.8, 77.47), (152.4, 85.09, 177.8, 85.09),
    (177.8, 85.09, 177.8, 90.17), (127.0, 125.73, 127.0, 130.81),
    (109.22, 71.12, 109.22, 85.09), (96.52, 81.28, 109.22, 81.28),
    (109.22, 63.5, 109.22, 57.15), (96.52, 88.9, 96.52, 93.98),
]]
junctions = [(round(x + _d41x, 4), round(y + _d41y, 4)) for (x, y) in [
    (152.4, 77.47), (165.1, 77.47), (139.7, 77.47),
    (165.1, 85.09), (177.8, 85.09), (109.22, 81.28), (160.02, 85.09),
]]
ports = [(rf, lb, vl, round(x + _d41x, 4), round(y + _d41y, 4),
          (round(vx + _d41x, 4), round(vy + _d41y, 4)))
         for (rf, lb, vl, x, y, (vx, vy)) in [
    ("#PWR01", "infinity-stumps:3V0", "3V0", 139.7, 77.47, (142.24, 76.2)),
    ("#PWR02", "infinity-stumps:3V0", "3V0", 109.22, 57.15, (111.76, 55.88)),
    ("#PWR03", "power:GND", "GND", 127.0, 130.81, (127.0, 134.62)),
    ("#PWR04", "power:GND", "GND", 177.8, 90.17, (177.8, 93.98)),
    ("#PWR05", "power:GND", "GND", 96.52, 93.98, (96.52, 97.79)),
    ("#FLG02", "power:PWR_FLAG", "PWR_FLAG", 160.02, 85.09, (160.02, 80.62)),
]]
# label tuples: (name, x, y, angle, justify)
labels = [(nm, round(x + _d41x, 4), round(y + _d41y, 4), a, j)
          for (nm, x, y, a, j) in [("nRESET", 109.22, 78.74, 0, "left")]]
# §4.1's hand-placed ports/labels also count toward its frame
for _p in ports:
    sec_pts["4.1"].append((_p[3], _p[4]))
for _p in labels:
    sec_pts["4.1"].append((_p[1], _p[2]))
stub_wires = []
_stub_pts = set()  # every grid point covered by a placed stub wire
no_connects = []
_pn = [6]
_flg = [3]
# text reads away from the component body, by which way the pin faces
_JUST = {"L": "right", "R": "left", "U": "left", "D": "left"}


# a pin that already carries one stubbed item — the next item routes off
# it perpendicularly so the two don't pile up (e.g. a label + a PWR_FLAG)
_stubbed_pins = set()
_PERP = {"L": ["U", "D"], "R": ["U", "D"], "U": ["L", "R"], "D": ["L", "R"]}


def _stub_path(px, py, d, length):
    """Grid points from just past the pin out to the stub end (inclusive)."""
    step = {"L": (-GRID, 0), "R": (GRID, 0), "U": (0, -GRID), "D": (0, GRID)}[d]
    return [(round(px + step[0] * i, 4), round(py + step[1] * i, 4))
            for i in range(1, int(round(length / GRID)) + 1)]


def _find_stub(x, y):
    """Pull a pin out onto a short stub wire into clear space.

    Returns (end_x, end_y, dir). If (x, y) isn't a pin -> None. The first
    item on a pin stubs straight out; a second item (e.g. a PWR_FLAG that
    shares a labelled pin) routes perpendicular instead. If nothing is
    clear -> (x, y, dir) with no wire, so the caller sits it on the pin.
    """
    d0 = _pin_dir.get((x, y))
    if d0 is None:
        return None
    dirs = _PERP[d0] + [d0] if (x, y) in _stubbed_pins else [d0]
    _stubbed_pins.add((x, y))
    for d in dirs:
        # prefer STUB or 2*STUB by parity along the column so adjacent
        # items stagger; fall back to the other length, then the next dir
        axis = y if d in ("L", "R") else x
        lvl = (int(round(axis / GRID)) // 2) % 2
        for length in ([2 * STUB, STUB] if lvl else [STUB, 2 * STUB]):
            path = _stub_path(x, y, d, length)
            if any(pt in ALL_PIN_COORDS or pt in _stub_pts for pt in path):
                continue  # stub would touch another pin/stub → short risk
            ex, ey = path[-1]
            stub_wires.append((x, y, ex, ey))
            _stub_pts.update(path)
            _stub_pts.add((x, y))
            return (ex, ey, d)
    return (x, y, d0)


def add_port(lib, val, x, y):
    """Place a power port / PWR_FLAG on the pin at (x, y), on a stub."""
    on_grid(x, y, "port %s" % val)
    if lib == "power:PWR_FLAG":
        ref = "#FLG%02d" % _flg[0]; _flg[0] += 1
    else:
        ref = "#PWR%02d" % _pn[0]; _pn[0] += 1
    sec = _pin_section.get((x, y))
    s = _find_stub(x, y)
    if s is not None:
        x, y = s[0], s[1]
    if sec:
        sec_pts[sec].append((x, y))
    ports.append((ref, lib, val, x, y, (x + 2.5, y - 1.27)))


def add_label(name, x, y):
    """Place a local label for the net `name` on the pin at (x, y), on a stub.

    The label is pulled onto a short stub wire and oriented to read away
    from the component, so text clears the body and its neighbours.
    """
    on_grid(x, y, "label %s" % name)
    sec = _pin_section.get((x, y))
    s = _find_stub(x, y)
    if s is None:  # not a pin coord (e.g. a label dropped onto a drawn wire)
        labels.append((name, x, y, 0, "left"))
        return
    ex, ey, d = s
    labels.append((name, ex, ey, 0, _JUST[d]))
    if sec:  # include the far end of the text so the frame encloses it
        w = len(name) * 1.0
        sec_pts[sec].append((ex - w, ey) if _JUST[d] == "right" else (ex + w, ey))
        sec_pts[sec].append((ex, ey))


def add_nc(x, y):
    on_grid(x, y, "no_connect")
    no_connects.append((x, y))
    sec = _pin_section.get((x, y))
    if sec:
        sec_pts[sec].append((x, y))


# ----- §4.2 USB-C input + ESD -----
for p in [pin_xy("J1", "A4"), pin_xy("J1", "A9"), pin_xy("J1", "B4"), pin_xy("J1", "B9"),
          pin_xy("C5", 1), pin_xy("C6", 1), pin_xy("D2", 1),
          pin_xy("U3", 13), pin_xy("C8", 1)]:
    add_port("infinity-stumps:VBUS", "VBUS", *p)
add_port("power:PWR_FLAG", "PWR_FLAG", *pin_xy("J1", "A4"))
for p in [pin_xy("J1", "A5"), pin_xy("R2", 1), pin_xy("U2", 3)]:
    add_label("CC1", *p)
for p in [pin_xy("J1", "B5"), pin_xy("R3", 1), pin_xy("U2", 5)]:
    add_label("CC2", *p)
for p in [pin_xy("J1", "SH"), pin_xy("R4", 1), pin_xy("C7", 1)]:
    add_label("SHIELD", *p)
for p in [pin_xy("J1", "A1"), pin_xy("J1", "A12"), pin_xy("J1", "B1"), pin_xy("J1", "B12"),
          pin_xy("R2", 2), pin_xy("R3", 2), pin_xy("C5", 2), pin_xy("C6", 2),
          pin_xy("D2", 2), pin_xy("U2", 4), pin_xy("R4", 2), pin_xy("C7", 2)]:
    add_port("power:GND", "GND", *p)
for p in [pin_xy("J1", "A6"), pin_xy("J1", "A7"), pin_xy("J1", "A8"),
          pin_xy("J1", "B6"), pin_xy("J1", "B7"), pin_xy("J1", "B8")]:
    add_nc(*p)

# ----- §4.3 BQ24074 charger -----
for p in [pin_xy("U3", 11), pin_xy("U3", 10), pin_xy("C9", 1)]:
    add_port("infinity-stumps:VSYS", "VSYS", *p)
for p in [pin_xy("U3", 2), pin_xy("U3", 3), pin_xy("C10", 1), pin_xy("R7", 1)]:
    add_port("infinity-stumps:VBAT", "VBAT", *p)
for p in [pin_xy("U3", 8), pin_xy("U3", 17), pin_xy("U3", 4), pin_xy("C8", 2),
          pin_xy("C9", 2), pin_xy("C10", 2), pin_xy("R5", 2), pin_xy("R6", 2),
          pin_xy("R8", 2), pin_xy("R11", 2), pin_xy("R12", 2),
          pin_xy("R24", 2), pin_xy("R25", 2)]:
    add_port("power:GND", "GND", *p)
for p in [pin_xy("R9", 1), pin_xy("R10", 1)]:
    add_port("infinity-stumps:3V0", "3V0", *p)
for p in [pin_xy("U3", 1), pin_xy("R7", 2), pin_xy("R8", 1)]:
    add_label("TS", *p)
for p in [pin_xy("U3", 16), pin_xy("R5", 1)]:
    add_label("ISET", *p)
for p in [pin_xy("U3", 14), pin_xy("R6", 1)]:
    add_label("TMR", *p)
for p in [pin_xy("U3", 15), pin_xy("R25", 1)]:
    add_label("ITERM", *p)
for p in [pin_xy("U3", 12), pin_xy("R24", 1)]:
    add_label("ILIM", *p)
for p in [pin_xy("U3", 6), pin_xy("R11", 1)]:
    add_label("EN1_STRAP", *p)
for p in [pin_xy("U3", 5), pin_xy("R12", 1)]:
    add_label("EN2_STRAP", *p)
for p in [pin_xy("U3", 9), pin_xy("R9", 2), pin_xy("U1", 7)]:
    add_label("CHG", *p)
for p in [pin_xy("U3", 7), pin_xy("R10", 2), pin_xy("U1", 8)]:
    add_label("PGOOD", *p)

# ----- §4.4 cell protection -----
for p in [pin_xy("BT1", 1), pin_xy("R13", 1)]:
    add_port("infinity-stumps:VBAT", "VBAT", *p)
add_port("power:PWR_FLAG", "PWR_FLAG", *pin_xy("BT1", 1))
for p in [pin_xy("BT1", 2), pin_xy("U4", 6), pin_xy("C11", 2),
          pin_xy("U5", 2), pin_xy("U5", 3)]:
    add_label("BMINUS", *p)
add_port("power:PWR_FLAG", "PWR_FLAG", *pin_xy("U4", 6))
for p in [pin_xy("R13", 2), pin_xy("U4", 5), pin_xy("C11", 1)]:
    add_label("DW_VCC", *p)
add_port("power:PWR_FLAG", "PWR_FLAG", *pin_xy("U4", 5))
for p in [pin_xy("U5", 6), pin_xy("U5", 7), pin_xy("R14", 2)]:
    add_port("power:GND", "GND", *p)
for p in [pin_xy("U5", 1), pin_xy("U5", 8)]:
    add_label("DRAIN_MID", *p)
for p in [pin_xy("U4", 1), pin_xy("U5", 4)]:
    add_label("OD_G", *p)
for p in [pin_xy("U4", 3), pin_xy("U5", 5)]:
    add_label("OC_G", *p)
for p in [pin_xy("U4", 2), pin_xy("R14", 1)]:
    add_label("CS", *p)
add_nc(*pin_xy("U4", 4))

# ----- §4.5 LDO -----
for p in [pin_xy("U6", 4), pin_xy("U6", 3), pin_xy("FB1", 2), pin_xy("C12", 1)]:
    add_label("VSYS_LDO", *p)
# LDO output is "3V0_LDO" up to the dev-rail current-shunt jumper (§7);
# downstream of the jumper / 0R it becomes the system 3V0 rail.
for rn in [("U6", 1), ("C13", 1), ("C14", 1)]:
    add_label("3V0_LDO", *pin_xy(*rn))
for rn in [("U6", 2), ("C12", 2), ("C13", 2), ("C14", 2)]:
    add_port("power:GND", "GND", *pin_xy(*rn))
add_port("infinity-stumps:VSYS", "VSYS", *pin_xy("FB1", 1))
add_port("power:PWR_FLAG", "PWR_FLAG", *pin_xy("C12", 1))

# ----- §4.6 SPI flash + load switch -----
add_port("infinity-stumps:3V0", "3V0", *pin_xy("U8", "A2"))
for p in [pin_xy("U8", "A1"), pin_xy("U7", "8"), pin_xy("C15", 1), pin_xy("C16", 1),
          pin_xy("R15", 1), pin_xy("R16", 1), pin_xy("R17", 1)]:
    add_label("3V0_FLASH", *p)
for p in [pin_xy("U8", "B1"), pin_xy("U7", "4"), pin_xy("C15", 2), pin_xy("C16", 2)]:
    add_port("power:GND", "GND", *p)
for p in [pin_xy("U8", "B2"), pin_xy("U1", 16)]:
    add_label("FLASH_EN", *p)
for p in [pin_xy("U7", "6"), pin_xy("U1", 12)]:
    add_label("SPI_SCK", *p)
for p in [pin_xy("U7", "5"), pin_xy("U1", 13)]:
    add_label("SPI_MOSI", *p)
for p in [pin_xy("U7", "2"), pin_xy("U1", 14)]:
    add_label("SPI_MISO", *p)
for p in [pin_xy("U7", "1"), pin_xy("U1", 15), pin_xy("R15", 2)]:
    add_label("SPI_CS", *p)
for p in [pin_xy("U7", "3"), pin_xy("R16", 2)]:
    add_label("FLASH_WP", *p)
for p in [pin_xy("U7", "7"), pin_xy("R17", 2)]:
    add_label("FLASH_HOLD", *p)

# ----- §4.7 RGB LED + power button -----
# common-anode RGB: anode -> LED_VCC (via §7 LED-disable jumper from 3V0),
# each cathode -> current-limit R -> MCU GPIO
add_label("LED_VCC", *pin_xy("D1", 1))
add_port("infinity-stumps:3V0", "3V0", *pin_xy("R21", 1))
for p in [pin_xy("D1", 2), pin_xy("R18", 1)]:
    add_label("RED_K", *p)
for p in [pin_xy("R18", 2), pin_xy("U1", 17)]:
    add_label("LED_R", *p)
for p in [pin_xy("D1", 3), pin_xy("R19", 1)]:
    add_label("GRN_K", *p)
for p in [pin_xy("R19", 2), pin_xy("U1", 18)]:
    add_label("LED_G", *p)
for p in [pin_xy("D1", 4), pin_xy("R20", 1)]:
    add_label("BLU_K", *p)
for p in [pin_xy("R20", 2), pin_xy("U1", 19)]:
    add_label("LED_B", *p)
# power/mode button: BTN -> GND on press, R21 pull-up to 3V0, C18 debounce
for p in [pin_xy("SW1", 1), pin_xy("R21", 2), pin_xy("C18", 1), pin_xy("U1", 6)]:
    add_label("BTN", *p)
for p in [pin_xy("SW1", 2), pin_xy("C18", 2)]:
    add_port("power:GND", "GND", *p)
# EN1/EN2 are intentionally free - the BQ24074 mode is hard-strapped (R11/R12)
add_nc(*pin_xy("U1", 10))
add_nc(*pin_xy("U1", 11))

# ----- §4.8 VBAT voltage sense divider -----
# VBAT -> R22 -> tap -> R23 -> GND; C19 filters the tap; tap -> U1 VBAT_SENSE
add_port("infinity-stumps:VBAT", "VBAT", *pin_xy("R22", 1))
for p in [pin_xy("R22", 2), pin_xy("R23", 1), pin_xy("C19", 1), pin_xy("U1", 9)]:
    add_label("VBAT_SENSE", *p)
for p in [pin_xy("R23", 2), pin_xy("C19", 2)]:
    add_port("power:GND", "GND", *p)

# ----- §4.9 rail-level test points + 3V0 bulk cap -----
add_port("infinity-stumps:VBUS", "VBUS", *pin_xy("TP1", 1))
add_port("infinity-stumps:VSYS", "VSYS", *pin_xy("TP2", 1))
add_port("infinity-stumps:VBAT", "VBAT", *pin_xy("TP3", 1))
add_port("infinity-stumps:3V0", "3V0", *pin_xy("TP4", 1))
add_port("power:GND", "GND", *pin_xy("TP5", 1))
add_port("power:GND", "GND", *pin_xy("TP6", 1))
add_port("infinity-stumps:3V0", "3V0", *pin_xy("C20", 1))
add_port("power:GND", "GND", *pin_xy("C20", 2))
# 3V0 is a passive (power_in) net once split from 3V0_LDO by the shunt -
# flag it driven for ERC
add_port("power:PWR_FLAG", "PWR_FLAG", *pin_xy("C20", 1))

# ----- §7 break-off dev rail -----
# U1 debug / console / GPIO pins surface here
add_label("SWDIO", *pin_xy("U1", 2))
add_label("SWDCLK", *pin_xy("U1", 3))
add_label("UART_TX", *pin_xy("U1", 4))
add_label("UART_RX", *pin_xy("U1", 5))
for i, p in enumerate([pin_xy("U1", 20), pin_xy("U1", 21), pin_xy("U1", 22), pin_xy("U1", 23)]):
    add_label("GPIO%d" % (i + 1), *p)

# J2 - 2x5 1.27mm SWD/JTAG header (Cortex Debug pinout)
add_port("infinity-stumps:3V0", "3V0", *pin_xy("J2", 1))   # 1 VTref
add_label("SWDIO", *pin_xy("J2", 2))                       # 2 SWDIO
add_port("power:GND", "GND", *pin_xy("J2", 3))             # 3 GND
add_label("SWDCLK", *pin_xy("J2", 4))                      # 4 SWCLK
add_port("power:GND", "GND", *pin_xy("J2", 5))             # 5 GND
add_nc(*pin_xy("J2", 6))                                   # 6 SWO - unused
add_nc(*pin_xy("J2", 7))                                   # 7 KEY
add_nc(*pin_xy("J2", 8))                                   # 8 NC
add_port("power:GND", "GND", *pin_xy("J2", 9))             # 9 GNDDetect
add_label("nRESET", *pin_xy("J2", 10))                     # 10 nRESET

# J8 - Tag-Connect TC2030 SWD pads (stay on the core board, not the rail)
add_port("infinity-stumps:3V0", "3V0", *pin_xy("J8", 1))
add_label("SWDIO", *pin_xy("J8", 2))
add_label("nRESET", *pin_xy("J8", 3))
add_label("SWDCLK", *pin_xy("J8", 4))
add_port("power:GND", "GND", *pin_xy("J8", 5))
add_nc(*pin_xy("J8", 6))

# J3 - UART console header
add_label("UART_TX", *pin_xy("J3", 1))
add_label("UART_RX", *pin_xy("J3", 2))
add_port("power:GND", "GND", *pin_xy("J3", 3))

# J4 - spare GPIO breakout
add_port("infinity-stumps:3V0", "3V0", *pin_xy("J4", 1))
for i in range(4):
    add_label("GPIO%d" % (i + 1), *pin_xy("J4", i + 2))
add_port("power:GND", "GND", *pin_xy("J4", 6))

# J5 - 3V0 current-shunt jumper; R26 0R is its production replacement.
# Both bridge 3V0_LDO -> 3V0 (parallel - dev populates J5, production R26)
add_label("3V0_LDO", *pin_xy("J5", 1))
add_port("infinity-stumps:3V0", "3V0", *pin_xy("J5", 2))
add_label("3V0_LDO", *pin_xy("R26", 1))
add_port("infinity-stumps:3V0", "3V0", *pin_xy("R26", 2))

# J6 - LED-disable jumper: bridges 3V0 -> LED_VCC (pull to kill LEDs for
# sleep-current profiling)
add_port("infinity-stumps:3V0", "3V0", *pin_xy("J6", 1))
add_label("LED_VCC", *pin_xy("J6", 2))

# J7 - reset / boot-strap pads
add_label("nRESET", *pin_xy("J7", 1))
add_port("power:GND", "GND", *pin_xy("J7", 2))

# ============================ emit ============================
P = ['(kicad_sch', '\t(version 20250114)', '\t(generator "eeschema")',
     '\t(generator_version "9.0")', '\t(uuid "%s")' % ROOT, '\t(paper "A3")',
     '\t(title_block', '\t\t(title "Infinity Stumps — Anchor Board")',
     '\t\t(date "2026-05-14")', '\t\t(rev "A")', '\t\t(company "Infinity Stumps")',
     '\t\t(comment 1 "Carrier PCB for the DWM3001C UWB module — one design serves all 8 anchor positions")',
     '\t\t(comment 2 "Licence: CERN-OHL-S v2")',
     '\t\t(comment 3 "Design spec: hardware/anchor-board/README.md")',
     '\t\t(comment 4 "Sheet 1 — complete: §4.1-4.9 (module, USB-C, charger, protection, LDO, flash, LED/button, VBAT sense, test points) + §7 break-off dev rail")',
     '\t)', '\t(lib_symbols']
P += lib_syms
P.append('\t)')

# ---- section frames + titles ----
# A dashed box + heading around each functional block, sized to the
# block's components, stubs and labels (collected in sec_pts).
FRAME_PAD = 5.08
for _sec in SECTION_REFS:
    _pts = sec_pts.get(_sec)
    if not _pts:
        continue
    _x1 = round(min(p[0] for p in _pts) - FRAME_PAD, 2)
    _y1 = round(min(p[1] for p in _pts) - FRAME_PAD, 2)
    _x2 = round(max(p[0] for p in _pts) + FRAME_PAD, 2)
    _y2 = round(max(p[1] for p in _pts) + FRAME_PAD, 2)
    P += ['\t(polyline', '\t\t(pts',
          '\t\t\t(xy %s %s) (xy %s %s) (xy %s %s) (xy %s %s) (xy %s %s)'
          % (_x1, _y1, _x2, _y1, _x2, _y2, _x1, _y2, _x1, _y1),
          '\t\t)', '\t\t(stroke (width 0.2) (type dash))',
          '\t\t(uuid "%s")' % u(), '\t)']
    P += ['\t(text "%s"' % SECTION_TITLE[_sec],
          '\t\t(exclude_from_sim no)',
          '\t\t(at %s %s 0)' % (round(_x1 + 1.0, 2), round(_y1 - 1.5, 2)),
          '\t\t(effects', '\t\t\t(font (size 2.5 2.5))',
          '\t\t\t(justify left bottom)', '\t\t)',
          '\t\t(uuid "%s")' % u(), '\t)']

for (x1, y1, x2, y2) in wires + stub_wires:
    P += ['\t(wire', '\t\t(pts', '\t\t\t(xy %s %s) (xy %s %s)' % (x1, y1, x2, y2),
          '\t\t)', '\t\t(stroke', '\t\t\t(width 0)', '\t\t\t(type default)', '\t\t)',
          '\t\t(uuid "%s")' % u(), '\t)']
for (x, y) in junctions:
    P += ['\t(junction', '\t\t(at %s %s)' % (x, y), '\t\t(diameter 0)',
          '\t\t(color 0 0 0 0)', '\t\t(uuid "%s")' % u(), '\t)']
for (x, y) in no_connects:
    P += ['\t(no_connect', '\t\t(at %s %s)' % (x, y), '\t\t(uuid "%s")' % u(), '\t)']
for (name, x, y, angle, just) in labels:
    P += ['\t(label "%s"' % name, '\t\t(at %s %s %s)' % (x, y, angle), '\t\t(effects',
          '\t\t\t(font', '\t\t\t\t(size 1.27 1.27)', '\t\t\t)',
          '\t\t\t(justify %s bottom)' % just, '\t\t)', '\t\t(uuid "%s")' % u(), '\t)']


def prop(name, value, x, y, hide):
    r = ['\t\t(property "%s" "%s"' % (name, value), '\t\t\t(at %s %s 0)' % (x, y),
         '\t\t\t(effects', '\t\t\t\t(font', '\t\t\t\t\t(size 1.27 1.27)', '\t\t\t\t)']
    if hide:
        r.append('\t\t\t\t(hide yes)')
    r += ['\t\t\t)', '\t\t)']
    return r


def emit(ref, lib_id, value, fp, x, y, npins, ref_at, val_at):
    s = ['\t(symbol', '\t\t(lib_id "%s")' % lib_id, '\t\t(at %s %s 0)' % (x, y),
         '\t\t(unit 1)', '\t\t(exclude_from_sim no)', '\t\t(in_bom yes)',
         '\t\t(on_board yes)', '\t\t(dnp no)', '\t\t(uuid "%s")' % u()]
    s += prop("Reference", ref, ref_at[0], ref_at[1], False)
    s += prop("Value", value, val_at[0], val_at[1], False)
    s += prop("Footprint", fp, x, y, True)
    s += prop("Datasheet", "", x, y, True)
    for n in npins:
        s += ['\t\t(pin "%s"' % n, '\t\t\t(uuid "%s")' % u(), '\t\t)']
    s += ['\t\t(instances', '\t\t\t(project "%s"' % PROJECT,
          '\t\t\t\t(path "/%s"' % ROOT, '\t\t\t\t\t(reference "%s")' % ref,
          '\t\t\t\t\t(unit 1)', '\t\t\t\t)', '\t\t\t)', '\t\t)', '\t)']
    return s


for (ref, lib_id, value, fp, x, y, ref_at, val_at) in comps:
    P += emit(ref, lib_id, value, fp, x, y, list(PINS[lib_id].keys()), ref_at, val_at)

for (ref, lib_id, value, x, y, val_at) in ports:
    s = ['\t(symbol', '\t\t(lib_id "%s")' % lib_id, '\t\t(at %s %s 0)' % (x, y),
         '\t\t(unit 1)', '\t\t(exclude_from_sim no)', '\t\t(in_bom yes)',
         '\t\t(on_board yes)', '\t\t(dnp no)', '\t\t(uuid "%s")' % u()]
    s += prop("Reference", ref, x, y - 3.81, True)
    s += prop("Value", value, val_at[0], val_at[1], False)
    s += prop("Footprint", "", x, y, True)
    s += prop("Datasheet", "", x, y, True)
    s += ['\t\t(pin "1"', '\t\t\t(uuid "%s")' % u(), '\t\t)']
    s += ['\t\t(instances', '\t\t\t(project "%s"' % PROJECT,
          '\t\t\t\t(path "/%s"' % ROOT, '\t\t\t\t\t(reference "%s")' % ref,
          '\t\t\t\t\t(unit 1)', '\t\t\t\t)', '\t\t\t)', '\t\t)', '\t)']
    P += s

P += ['\t(sheet_instances', '\t\t(path "/"', '\t\t\t(page "1")', '\t\t)', '\t)',
      '\t(embedded_fonts no)', ')']
open(OUT, "w").write("\n".join(P) + "\n")
print("wrote", OUT, "(%d lines)" % len(P))
print("components:", len(comps), " ports:", len(ports),
      " labels:", len(labels), " stub wires:", len(stub_wires),
      " no_connects:", len(no_connects))
