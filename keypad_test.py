#!/usr/bin/env python3
import time
import board
import busio
from adafruit_mcp230xx.mcp23017 import MCP23017
from digitalio import Direction, Pull

# I2C setup
i2c = busio.I2C(board.SCL, board.SDA)

# MCP23017 at 0x21
mcp = MCP23017(i2c, address=0x21)

# MCP pins A0-A7 for keypad
pins = [mcp.get_pin(i) for i in range(8)]

# Set first 4 pins as outputs (rows), last 4 pins as inputs (columns)
rows = pins[:4]
cols = pins[4:]

for row in rows:
    row.direction = Direction.OUTPUT
    row.value = True  # default HIGH

for col in cols:
    col.direction = Direction.INPUT
    col.pull = Pull.UP  # enable pull-ups

# Key mapping for 4x4 keypad
KEYS = [
    ['1','2','3','A'],
    ['4','5','6','B'],
    ['7','8','9','C'],
    ['*','0','#','D']
]

print("Press keys on the keypad. Ctrl+C to exit.")
try:
    while True:
        for r_idx, row in enumerate(rows):
            row.value = False  # drive current row LOW
            for c_idx, col in enumerate(cols):
                if not col.value:  # pressed
                    print("Key pressed:", KEYS[r_idx][c_idx])
                    while not col.value:
                        time.sleep(0.01)  # wait for release
            row.value = True  # reset row HIGH
        time.sleep(0.05)
except KeyboardInterrupt:
    print("Exiting...")
