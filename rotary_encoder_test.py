import board
import busio
import time

from adafruit_mcp230xx.mcp23017 import MCP23017
from digitalio import Direction, Pull
from signal import pause

# I2C setup
i2c = busio.I2C(board.SCL, board.SDA)

# MCP_ADDR=0x20
MCP_ADDR=0x21
# MCP23017 n°1 at address 0x20
# MCP23017 n°2 at address 0x21
mcp = MCP23017(i2c, address=MCP_ADDR)

# 1st from left to right above : mcp n°2 clk B4=12 dt B3=11 sw B2=10
# 2nd from left to right above : mcp n°2 clk B7=15 dt B6=14 sw B5=13
# 3rd from left to right above : mcp n°1 clk A1=1 dt A2=2 sw A3=3
# 4th from left to right above (center of the board): mcp n°1 clk B1=9, dt B0=8, sw A0=0
# Rotary encoder connections
clk = mcp.get_pin(15)
dt = mcp.get_pin(14)
sw = mcp.get_pin(13)   # (push button)

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

print(f"KY-040 Rotary Encoder Test via MCP23017 @ {MCP_ADDR}")
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
