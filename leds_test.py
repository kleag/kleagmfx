#!/usr/bin/env python3
"""
MCP23017 LED and Button Test Program
Simple version using Adafruit libraries

LED/Button Mapping:
- B3: Blinking LED
- B4 (LED) : B6 (Button)
- B5 (LED) : B7 (Button)
- A4 (LED) : A6 (Button)
- A5 (LED) : A7 (Button)
"""

import time
import board
import busio
from adafruit_mcp230xx.mcp23017 import MCP23017
from digitalio import Direction, Pull

# Initialize I2C and MCP23017
i2c = busio.I2C(board.SCL, board.SDA)
mcp = MCP23017(i2c)

# Setup LEDs as outputs
led_b3 = mcp.get_pin(11)  # B3 - blinking LED
led_b4 = mcp.get_pin(13)  # B4
led_b5 = mcp.get_pin(12)  # B5
led_a4 = mcp.get_pin(4)   # A4
led_a5 = mcp.get_pin(5)   # A5

led_b3.direction = Direction.OUTPUT
led_b4.direction = Direction.OUTPUT
led_b5.direction = Direction.OUTPUT
led_a4.direction = Direction.OUTPUT
led_a5.direction = Direction.OUTPUT

# Setup buttons as inputs with pull-ups
btn_b6 = mcp.get_pin(14)  # B6
btn_b7 = mcp.get_pin(15)  # B7
btn_a6 = mcp.get_pin(6)   # A6
btn_a7 = mcp.get_pin(7)   # A7

btn_b6.direction = Direction.INPUT
btn_b7.direction = Direction.INPUT
btn_a6.direction = Direction.INPUT
btn_a7.direction = Direction.INPUT

btn_b6.pull = Pull.UP
btn_b7.pull = Pull.UP
btn_a6.pull = Pull.UP
btn_a7.pull = Pull.UP

print("MCP23017 Test Program")
print("B3 will blink, other LEDs follow button presses")
print("Press Ctrl+C to exit\n")

try:
    last_blink = time.time()
    blink_state = False
    
    while True:
        # Blink B3 every 0.5 seconds
        if time.time() - last_blink >= 0.5:
            blink_state = not blink_state
            led_b3.value = blink_state
            last_blink = time.time()
        
        # Control LEDs based on button presses (buttons are active low)
        led_b4.value = not btn_b6.value
        led_b5.value = not btn_b7.value
        led_a4.value = not btn_a6.value
        led_a5.value = not btn_a7.value
        
        time.sleep(0.01)

except KeyboardInterrupt:
    print("\nExiting...")
    # Turn off all LEDs
    led_b3.value = False
    led_b4.value = False
    led_b5.value = False
    led_a4.value = False
    led_a5.value = False
    print("All LEDs off. Goodbye!")
