#!/usr/bin/env python3
import board
import busio
import time
from adafruit_mcp230xx.mcp23017 import MCP23017
from digitalio import Direction, Pull

# --- Setup I2C bus ---
i2c = busio.I2C(board.SCL, board.SDA)

# --- Initialize MCP23017 chips ---
mcp1 = MCP23017(i2c, address=0x20)
mcp2 = MCP23017(i2c, address=0x21)  

# --- Rotary encoder definitions ---
# Each entry: (mcp, clk_pin, dt_pin, sw_pin, name)
encoder_configs = [
    (mcp1, 0, 8, 9,  "Encoder 0"),      # original one
    (mcp1, 2, 3, 1,  "Encoder 1"),      # first new: A2 (clk), A3 (dt), A1 (sw)
    (mcp2, 6, 7, 5,  "Encoder 2"),      # second: B6 (clk), B7 (dt), B5 (sw)
    (mcp2, 3, 4, 2,  "Encoder 3"),      # third: B3 (clk), B4 (dt), B2 (sw)
]

# --- Initialize encoders ---
encoders = []
for mcp, clk_pin, dt_pin, sw_pin, name in encoder_configs:
    clk = mcp.get_pin(clk_pin)
    dt = mcp.get_pin(dt_pin)
    sw = mcp.get_pin(sw_pin)

    for pin in (clk, dt, sw):
        pin.direction = Direction.INPUT
        pin.pull = Pull.UP

    encoders.append({
        "name": name,
        "clk": clk,
        "dt": dt,
        "sw": sw,
        "last_clk": clk.value,
        "last_sw": sw.value
    })

print("KY-040 Rotary Encoder Test via MCP23017")
print("Rotate or press any encoder (Ctrl+C to exit)\n")

# --- Helper function to process one encoder ---
def read_encoder(enc):
    clk_val = enc["clk"].value
    dt_val = enc["dt"].value

    if clk_val != enc["last_clk"]:
        if dt_val != clk_val:
            print(f"{enc['name']}: Rotated → (clockwise)")
        else:
            print(f"{enc['name']}: Rotated ← (counterclockwise)")
        enc["last_clk"] = clk_val

def read_button(enc):
    sw_val = enc["sw"].value
    if sw_val != enc["last_sw"]:
        enc["last_sw"] = sw_val
        if not sw_val:
            print(f"{enc['name']}: Button pressed!")
        else:
            print(f"{enc['name']}: Button released!")
        time.sleep(0.2)

# --- Main loop ---
try:
    while True:
        for enc in encoders:
            read_encoder(enc)
            read_button(enc)
        time.sleep(0.001)

except KeyboardInterrupt:
    print("\nExiting.")
