import board
import busio
import time

from adafruit_mcp230xx.mcp23017 import MCP23017
from digitalio import Direction, Pull
from signal import pause

# I2C setup
i2c = busio.I2C(board.SCL, board.SDA)

# MCP23017 at address 0x20
mcp = MCP23017(i2c, address=0x20)

# Rotary encoder connections
clk = mcp.get_pin(0)  # A0
dt = mcp.get_pin(8)   # B0
sw = mcp.get_pin(9)   # B1 (push button)

# Configure inputs with pull-ups
for pin in (clk, dt, sw):
    pin.direction = Direction.INPUT
    pin.pull = Pull.UP

# Track rotary state
last_clk = clk.value

last_sw = sw.value

def read_encoder():
    global last_clk
    clk_value = clk.value
    dt_value = dt.value

    if clk_value != last_clk:  # Edge detected
        if dt_value != clk_value:
            print("Rotated → (clockwise)")
        else:
            print("Rotated ← (counterclockwise)")
    last_clk = clk_value

print("KY-040 Rotary Encoder Test via MCP23017 @ 0x20")
print("Rotate or press button (Ctrl+C to exit)\n")

try:
    while True:
        read_encoder()
        current_sw = sw.value

        if current_sw != last_sw:  # Active low
            last_sw = current_sw
            if not current_sw:
                print("Button pressed!")
            else:
                print("Button released!")
            time.sleep(0.2)
        time.sleep(0.001)
except KeyboardInterrupt:
    print("\nExiting.")
