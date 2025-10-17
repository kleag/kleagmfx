#!/usr/bin/env python3
"""
Interrupt-driven KY-040 rotary encoder test using MCP23017 expanders
and lgpio (Raspberry Pi 5 compatible).

This version handles both INTA and INTB pins separately, so all pins
on both banks are monitored.

Dependencies:
  pip install adafruit-circuitpython-mcp230xx lgpio
"""

import time
import threading
import board
import busio
import lgpio
from adafruit_mcp230xx.mcp23017 import MCP23017
from digitalio import Direction, Pull

# ------------------ CONFIGURATION ------------------
# MCP I2C addresses
I2C_ADDR_MCP1 = 0x20
I2C_ADDR_MCP2 = 0x21

# BCM GPIO pins for MCP23017 interrupt outputs
INTA_MCP1 = 17  # port A interrupt
INTB_MCP1 = 18  # port B interrupt
INTA_MCP2 = None  # Not used, only B bank is active
INTB_MCP2 = 27

# Rotary encoder layout: (mcp_name, clk_pin, dt_pin, sw_pin, label)
ENCODERS_DEF = [
    ("mcp1", 0, 8, 9, "Encoder 0"),  # A0 clk, B0 dt, B1 sw
    ("mcp1", 2, 3, 1, "Encoder 1"),  # A2 clk, A3 dt, A1 sw
    ("mcp2", 6, 7, 5, "Encoder 2"),  # B6 clk, B7 dt, B5 sw
    ("mcp2", 3, 4, 2, "Encoder 3"),  # B3 clk, B4 dt, B2 sw
]

BUTTON_DEBOUNCE = 0.15  # seconds
# ---------------------------------------------------

# I2C + MCP setup
i2c = busio.I2C(board.SCL, board.SDA)
mcp1 = MCP23017(i2c, address=I2C_ADDR_MCP1)
mcp2 = MCP23017(i2c, address=I2C_ADDR_MCP2)
mcps = {"mcp1": mcp1, "mcp2": mcp2}

# Thread-safe lock for I2C access
mcp_lock = threading.Lock()

# --- Build encoders table and enable interrupts on MCPs ---
encoders = []
mcp_masks = {"mcp1": {"A": 0, "B": 0}, "mcp2": {"A": 0, "B": 0}}

for mname, clk_p, dt_p, sw_p, label in ENCODERS_DEF:
    mcp = mcps[mname]
    for p in (clk_p, dt_p, sw_p):
        pin = mcp.get_pin(p)
        pin.direction = Direction.INPUT
        pin.pull = Pull.UP
        # Update mask for interrupt enable
        if p < 8:
            mcp_masks[mname]["A"] |= 1 << p
        else:
            mcp_masks[mname]["B"] |= 1 << (p - 8)
    encoders.append(
        {
            "label": label,
            "mname": mname,
            "clk_p": clk_p,
            "dt_p": dt_p,
            "sw_p": sw_p,
            "last_clk": mcp.get_pin(clk_p).value,
            "last_sw": mcp.get_pin(sw_p).value,
            "last_btn_time": 0.0,
        }
    )

# Enable interrupt-on-change for all pins used
for name, mcp in mcps.items():
    # Combine masks into 16-bit value
    mask = (mcp_masks[name]["B"] << 8) | mcp_masks[name]["A"]
    mcp.interrupt_enable = mask
    mcp.interrupt_configuration = 0  # compare to previous value

# Snapshot of last GPIO states
last_gpio = {name: mcp.gpio for name, mcp in mcps.items()}


# --- Encoder processing ---
def handle_encoder(enc, gpio_snapshot):
    clk = bool(gpio_snapshot & (1 << enc["clk_p"]))
    dt = bool(gpio_snapshot & (1 << enc["dt_p"]))
    sw = bool(gpio_snapshot & (1 << enc["sw_p"]))

    # Rotary rotation detection
    if clk != enc["last_clk"]:
        direction = "→" if dt != clk else "←"
        print(f"{enc['label']}: Rotated {direction}")
        enc["last_clk"] = clk

    # Button press/release (active-low)
    if sw != enc["last_sw"]:
        now = time.monotonic()
        if now - enc["last_btn_time"] > BUTTON_DEBOUNCE:
            enc["last_btn_time"] = now
            enc["last_sw"] = sw
            print(f"{enc['label']}: {'Pressed' if not sw else 'Released'}")


# --- MCP callbacks ---
def make_mcp_callback(mname, mcp):
    def callback(chip, gpio, level, tick):
        with mcp_lock:
            current = mcp.gpio  # read clears interrupt
            changed = current ^ last_gpio[mname]
            last_gpio[mname] = current
        for enc in encoders:
            if enc["mname"] != mname:
                continue
            mask = (1 << enc["clk_p"]) | (1 << enc["dt_p"]) | (1 << enc["sw_p"])
            if changed & mask:
                handle_encoder(enc, current)

    return callback


# --- lgpio setup ---
chip = lgpio.gpiochip_open(0)
int_pins = []
callbacks = []

# MCP1 INTA
if INTA_MCP1 is not None:
    lgpio.gpio_claim_input(chip, INTA_MCP1)
    lgpio.gpio_set_pull_up(chip, INTA_MCP1)
    cb = lgpio.callback(
        chip, INTA_MCP1, lgpio.FALLING_EDGE, make_mcp_callback("mcp1", mcp1)
    )
    int_pins.append(INTA_MCP1)
    callbacks.append(cb)

# MCP1 INTB
if INTB_MCP1 is not None:
    lgpio.gpio_claim_input(chip, INTB_MCP1)
    lgpio.gpio_set_pull_up(chip, INTB_MCP1)
    cb = lgpio.callback(
        chip, INTB_MCP1, lgpio.FALLING_EDGE, make_mcp_callback("mcp1", mcp1)
    )
    int_pins.append(INTB_MCP1)
    callbacks.append(cb)

# MCP2 INTA (not used)
if INTA_MCP2 is not None:
    lgpio.gpio_claim_input(chip, INTA_MCP2)
    lgpio.gpio_set_pull_up(chip, INTA_MCP2)
    cb = lgpio.callback(
        chip, INTA_MCP2, lgpio.FALLING_EDGE, make_mcp_callback("mcp2", mcp2)
    )
    int_pins.append(INTA_MCP2)
    callbacks.append(cb)

# MCP2 INTB
if INTB_MCP2 is not None:
    lgpio.gpio_claim_input(chip, INTB_MCP2)
    lgpio.gpio_set_pull_up(chip, INTB_MCP2)
    cb = lgpio.callback(
        chip, INTB_MCP2, lgpio.FALLING_EDGE, make_mcp_callback("mcp2", mcp2)
    )
    int_pins.append(INTB_MCP2)
    callbacks.append(cb)

print("KY-040 Rotary Encoder Test (interrupt-driven, lgpio, correct INTA/INTB)")
print("Rotate or press buttons (Ctrl+C to exit)\n")

# --- Main loop ---
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    for cb in callbacks:
        cb.cancel()
    lgpio.gpiochip_close(chip)
    print("Clean exit.")
