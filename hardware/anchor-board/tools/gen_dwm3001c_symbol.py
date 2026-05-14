#!/usr/bin/env python3
"""Generate the 48-pin DWM3001C schematic symbol in anchor_board.kicad_sym.

The DWM3001C is a 48-castellation module. This builds a symbol with all
48 pins, numbered per the Qorvo datasheet pin table (DWM3001C Data Sheet
Rev F, §3). The anchor board's function->GPIO assignment is baked into
the *used* pin names; pins the board does not use keep their datasheet
name and are typed `no_connect` (those pads are deliberately left
floating on this carrier — see hardware/anchor-board/README.md §5).

Re-run this if the pin assignment changes; it splices the new symbol
over the existing "DWM3001C" entry in anchor_board.kicad_sym, then run
gen_schematic.py to rebuild the sheet against the new pin numbers.

nRF52833 constraints honoured:
  - VBAT_SENSE is on P0.31 (pin 42) = SAADC AIN7 — must be an ADC pin
  - SWDCLK/SWDIO/RESET are the module's dedicated debug pins (2/3/47)
  - P0.24/P1.04 (pins 14/15) are the on-module accelerometer I2C — left
    NC so the carrier never drives them
  - P0.09/P0.10 (pins 4/5) default to NFC — left NC, no UICR change
"""
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
SYM = os.path.normpath(os.path.join(_HERE, "..", "anchor_board.kicad_sym"))

HALF_W = 25.4
PITCH = 2.54
PIN_LEN = 5.08

# (name, datasheet pin number, electrical type) — listed top -> bottom.
# Used pins carry their board function as the name; unused pins keep the
# datasheet GPIO name and are typed no_connect.
PINS_LEFT = [
    ("VDD",        "12", "power_in"),
    ("GND",        "1",  "power_in"),
    ("GND",        "11", "power_in"),
    ("GND",        "21", "power_in"),
    ("GND",        "38", "power_in"),
    ("GND",        "48", "power_in"),
    ("nRESET",     "47", "bidirectional"),   # RESET / P0.18
    ("SWDCLK",     "2",  "bidirectional"),   # SWD_CLK
    ("SWDIO",      "3",  "bidirectional"),   # SWD_DIO
    ("UART_TX",    "27", "bidirectional"),   # P1.09
    ("UART_RX",    "28", "bidirectional"),   # P1.00
    ("BTN",        "13", "bidirectional"),   # P0.12
    ("CHG_STAT",   "17", "bidirectional"),   # P0.20
    ("PGOOD",      "16", "bidirectional"),   # P0.21
    ("VBAT_SENSE", "42", "bidirectional"),   # P0.31 / AIN7
    ("P0.10/NFC2", "4",  "no_connect"),
    ("P0.09/NFC1", "5",  "no_connect"),
    ("P0.05",      "9",  "no_connect"),
    ("P0.04",      "10", "no_connect"),
    ("P0.24/SDA",  "14", "no_connect"),      # on-module accel I2C
    ("P1.04/SCL",  "15", "no_connect"),      # on-module accel I2C
    ("NC18",       "18", "no_connect"),      # undocumented in datasheet table
    ("USB_N",      "19", "no_connect"),
    ("USB_P",      "20", "no_connect"),
]
PINS_RIGHT = [
    ("SPI_SCK",    "22", "bidirectional"),   # P0.11
    ("SPI_MOSI",   "23", "bidirectional"),   # P1.08
    ("SPI_MISO",   "24", "bidirectional"),   # P0.06
    ("SPI_CS",     "25", "bidirectional"),   # P1.01
    ("FLASH_EN",   "26", "bidirectional"),   # P0.13
    ("LED_R",      "6",  "bidirectional"),   # P0.17
    ("LED_G",      "7",  "bidirectional"),   # P0.14
    ("LED_B",      "8",  "bidirectional"),   # P0.22
    ("GPIO1",      "29", "bidirectional"),   # P1.05
    ("GPIO2",      "32", "bidirectional"),   # P0.15
    ("GPIO3",      "33", "bidirectional"),   # P0.28
    ("GPIO4",      "34", "bidirectional"),   # P0.19
    ("DW_GP5",     "30", "no_connect"),
    ("DW_GP6",     "31", "no_connect"),
    ("DW_GP1",     "35", "no_connect"),
    ("DW_GP0",     "36", "no_connect"),
    ("P0.26",      "37", "no_connect"),
    ("P0.23",      "39", "no_connect"),
    ("P0.07",      "40", "no_connect"),
    ("P0.27",      "41", "no_connect"),
    ("P0.30",      "43", "no_connect"),
    ("DW_GPIO3",   "44", "no_connect"),
    ("DW_GPIO2",   "45", "no_connect"),
    ("P0.02",      "46", "no_connect"),
]

DATASHEET = "${KIPRJMOD}/../../docs/datasheets/DWM3001C Data Sheet.pdf"
DESCR = ("Qorvo DWM3001C UWB module: nRF52833 MCU + DW3110 UWB radio + "
         "on-module antennas + 32.768 kHz LFXO + low-g accel. 48-pin "
         "symbol, numbered per the datasheet castellation map; used-pin "
         "names carry the anchor-board function assignment.")
KEYWORDS = "UWB module Qorvo DWM3001C nRF52833 DW3110"

n = max(len(PINS_LEFT), len(PINS_RIGHT))
HALF_H = round((n - 1) * PITCH / 2 + PITCH, 4)   # box half-height
Y0 = (n - 1) / 2 * PITCH                          # topmost pin y


def pin(et, x, y, ang, name, num):
    return "\n".join([
        '\t\t\t(pin %s line' % et,
        '\t\t\t\t(at %s %s %s)' % (round(x, 4), round(y, 4), ang),
        '\t\t\t\t(length %s)' % PIN_LEN,
        '\t\t\t\t(name "%s"' % name,
        '\t\t\t\t\t(effects (font (size 1.27 1.27)))',
        '\t\t\t\t)',
        '\t\t\t\t(number "%s"' % num,
        '\t\t\t\t\t(effects (font (size 1.27 1.27)))',
        '\t\t\t\t)',
        '\t\t\t)',
    ])


def prop(name, value, x, y, hide=False):
    out = ['\t\t(property "%s" "%s"' % (name, value),
           '\t\t\t(at %s %s 0)' % (x, y)]
    if hide:
        out.append('\t\t\t(hide yes)')
    out += ['\t\t\t(effects (font (size 1.27 1.27)))', '\t\t)']
    return out


L = ['\t(symbol "DWM3001C"',
     '\t\t(pin_names (offset 1.016))',
     '\t\t(exclude_from_sim no)', '\t\t(in_bom yes)', '\t\t(on_board yes)']
L += prop("Reference", "U", 0, round(HALF_H + 2.54, 2))
L += prop("Value", "DWM3001C", 0, round(-HALF_H - 2.54, 2))
L += prop("Footprint", "infinity-stumps:DWM3001C", 0, 0, hide=True)
L += prop("Datasheet", DATASHEET, 0, 0, hide=True)
L += prop("Description", DESCR, 0, 0, hide=True)
L += prop("ki_keywords", KEYWORDS, 0, 0, hide=True)
L += ['\t\t(symbol "DWM3001C_0_1"',
      '\t\t\t(rectangle',
      '\t\t\t\t(start %s %s)' % (-HALF_W, HALF_H),
      '\t\t\t\t(end %s %s)' % (HALF_W, -HALF_H),
      '\t\t\t\t(stroke (width 0.254) (type default))',
      '\t\t\t\t(fill (type background))',
      '\t\t\t)', '\t\t)',
      '\t\t(symbol "DWM3001C_1_1"']
for i, (nm, num, et) in enumerate(PINS_LEFT):
    L.append(pin(et, -(HALF_W + PIN_LEN), Y0 - i * PITCH, 0, nm, num))
for i, (nm, num, et) in enumerate(PINS_RIGHT):
    L.append(pin(et, HALF_W + PIN_LEN, Y0 - i * PITCH, 180, nm, num))
L += ['\t\t)', '\t\t(embedded_fonts no)', '\t)']
new_sym = "\n".join(L)

txt = open(SYM).read()
i = txt.index('\t(symbol "DWM3001C"')
depth = 0
for k in range(i, len(txt)):
    if txt[k] == '(':
        depth += 1
    elif txt[k] == ')':
        depth -= 1
        if depth == 0:
            break
old_sym = txt[i:k + 1]
open(SYM, "w").write(txt.replace(old_sym, new_sym, 1))

nums = [p[1] for p in PINS_LEFT + PINS_RIGHT]
assert sorted(int(x) for x in nums) == list(range(1, 49)), "pin numbers != 1..48"
print("replaced DWM3001C symbol: %d pins (%d used, %d no_connect)" % (
    len(nums),
    sum(1 for p in PINS_LEFT + PINS_RIGHT if p[2] != "no_connect"),
    sum(1 for p in PINS_LEFT + PINS_RIGHT if p[2] == "no_connect")))
