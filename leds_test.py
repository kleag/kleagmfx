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
led_b3.direction = Direction.OUTPUT
# B4:12, B5:13, A4:4, A5:5
leds = [mcp.get_pin(pin) for pin in [13, 12, 4, 5]]
for led in leds:
    led.direction = Direction.OUTPUT

# Setup buttons as inputs with pull-ups
# B6:14, B7:15, A6:6, A7:7
btns = [mcp.get_pin(pin) for pin in [14, 15, 6, 7]]
for btn in btns:
    led.direction = Direction.OUTPUT
    btn.direction = Direction.INPUT
    btn.pull = Pull.UP


led_button_map = dict(zip(leds, btns))

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
        for led, btn in led_button_map.items():
            led.value = not btn.value
        
        time.sleep(0.01)

except KeyboardInterrupt:
    print("\nExiting...")
    # Turn off all LEDs
    for led in led_button_map.keys():
        led.value = False
    print("All LEDs off. Goodbye!")
