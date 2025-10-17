#!/usr/bin/env python3
"""
MCP23017 LED and Button Test Program
Interrupt-driven version with compact array-based code

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
import lgpio
from adafruit_mcp230xx.mcp23017 import MCP23017
from digitalio import Direction, Pull

# GPIO pins for interrupts (connect MCP23017 INTA and INTB to these pins)
INTERRUPT_PIN_A = 17  # GPIO17 for INTA (Port A buttons)
INTERRUPT_PIN_B = 27  # GPIO27 for INTB (Port B buttons)

# Initialize I2C and MCP23017
i2c = busio.I2C(board.SCL, board.SDA)
mcp = MCP23017(i2c, address=0x20)

# Setup LED/Button pairs
led_btn_pairs = [
    (12, 14),  # B4:B6
    (13, 15),  # B5:B7
    (4, 6),    # A4:A6
    (5, 7),    # A5:A7
]

leds = []
btns = []

# Configure LED and button pins
for led_pin, btn_pin in led_btn_pairs:
    # Setup LED
    led = mcp.get_pin(led_pin)
    led.direction = Direction.OUTPUT
    led.value = False
    leds.append(led)
    
    # Setup button with pull-up and interrupt
    btn = mcp.get_pin(btn_pin)
    btn.direction = Direction.INPUT
    btn.pull = Pull.UP
    btns.append(btn)

# Setup blinking LED (B3)
led_blink = mcp.get_pin(11)
led_blink.direction = Direction.OUTPUT

# Enable interrupts on button pins
mcp.interrupt_enable = 0b11000000 | 0b11000000 << 8  # A6,A7,B6,B7
mcp.interrupt_configuration = 0xFFFF  # Interrupt on any change
mcp.default_value = 0xFFFF  # Compare against high (for pull-ups)

# Setup interrupt handlers with lgpio for both banks
h = lgpio.gpiochip_open(0)
lgpio.gpio_claim_input(h, INTERRUPT_PIN_A, lgpio.SET_PULL_UP)
lgpio.gpio_claim_alert(h, INTERRUPT_PIN_A, lgpio.FALLING_EDGE)
lgpio.gpio_claim_input(h, INTERRUPT_PIN_B, lgpio.SET_PULL_UP)
lgpio.gpio_claim_alert(h, INTERRUPT_PIN_B, lgpio.FALLING_EDGE)

print("MCP23017 Test Program (Interrupt-driven)")
print("Connect INTA to GPIO17 and INTB to GPIO27")
print("B3 will blink, other LEDs follow button presses")
print("Press Ctrl+C to exit\n")

def update_leds():
    """Update all LEDs based on button states"""
    for led, btn in zip(leds, btns):
        led.value = not btn.value  # Active low buttons

try:
    last_blink = time.time()
    blink_state = False
    
    while True:
        # Blink B3 every 0.5 seconds
        if time.time() - last_blink >= 0.5:
            blink_state = not blink_state
            led_blink.value = blink_state
            last_blink = time.time()
        
        # Check for interrupts
        e, gpio, level, tick = lgpio.gpio_read_alert(h)
        if e == lgpio.TIMEOUT:
            # No interrupt, just wait
            time.sleep(0.01)
        else:
            # Interrupt occurred, clear it and update LEDs
            _ = mcp.int_flag  # Read to clear interrupt
            update_leds()

except KeyboardInterrupt:
    print("\nExiting...")
    # Turn off all LEDs
    led_blink.value = False
    for led in leds:
        led.value = False
    lgpio.gpiochip_close(h)
    print("All LEDs off. Goodbye!")