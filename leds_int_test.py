#!/usr/bin/env python3
import sys
import time
import threading
import board
import busio
import lgpio
from adafruit_mcp230xx.mcp23017 import MCP23017
from digitalio import Direction, Pull

# --------------------------
# I2C and MCP23017 setup
# --------------------------
i2c = busio.I2C(board.SCL, board.SDA)

# MCP23017 instances
mcp = MCP23017(i2c, address=0x20)  # first MCP
mcp.interrupt_enable = 0xFFFF  # Enable Interrupts in all pins
mcp.interrupt_configuration = 0x0000  # interrupt on any change
mcp.io_control = 0x44  # Interrupt as open drain and mirrored
mcp.clear_ints()  # Interrupts need to be cleared initially

# # Helper: compute bit mask for a given pin number 0..15
# def bitmask(pin):
#     return 1 << (pin & 0x0F)
#
# pins_to_enable_mask = 0
# pins_to_enable_mask |= bitmask(4)
# pins_to_enable_mask |= bitmask(5)
# pins_to_enable_mask |= bitmask(12)
# pins_to_enable_mask |= bitmask(13)
# mcp.interrupt_enable = pins_to_enable_mask
# --------------------------
# LEDs and buttons mapping
# --------------------------
# LED:Button
led_button_map = {
    mcp.get_pin(6): mcp.get_pin(5),  # A6 LED <- A5 button
    mcp.get_pin(7): mcp.get_pin(4),  # A7 LED <- A4 button
    mcp.get_pin(14): mcp.get_pin(12),  # B6 LED <- B7 button
    mcp.get_pin(15): mcp.get_pin(13),  # B7 LED <- B5 button
}

# Blink LED B3 on MCP1
blink_led = mcp.get_pin(11)  # B3
blink_led.direction = Direction.OUTPUT

# Set other LEDs as outputs
for led in led_button_map.keys():
    led.direction = Direction.OUTPUT

# Set buttons as inputs with pull-ups
for btn in led_button_map.values():
    btn.direction = Direction.INPUT
    btn.pull = Pull.UP
    # 4. Configure the MCP interrupt behavior for the pin
    # Enable the pin to generate an interrupt
    btn.interrupt_enabled = True
    # Set the interrupt configuration register (INTDEF) to HIGH (True).
    # This means an interrupt is triggered when the pin value differs from HIGH, i.e., when it goes LOW.
    btn.interruption_configuration = True

# --------------------------
# LGPIO setup for MCP interrupts
# --------------------------
CHIP = 0
h = lgpio.gpiochip_open(CHIP)

# --------------------------
# Interrupt handler thread
# --------------------------
def monitor_mcp_int(chip, pin, level, timestamp):
    print(f"Callback called {chip}, {pin}, {level}, {timestamp}")
    update_leds()

# GPIOs on RPi connected to MCP INTA/INTB pins
INT_PINS = [5, 7, 22, 27]  # replace with actual pins
for pin in INT_PINS:
    if lgpio.gpio_claim_input(h, pin) != 0:
        print(f"Error")
        sys.exit(1)
    # lgpio.callback(h, pin, lgpio.FALLING_EDGE, monitor_mcp_int)
    lgpio.callback(h, pin, lgpio.BOTH_EDGES, monitor_mcp_int)


def update_leds():
    """Read all buttons and update LEDs accordingly."""
    for led, btn in led_button_map.items():
        print(btn.value)
        led.value = not btn.value  # True if button pressed, False if released

# # Start threads for each MCP interrupt pin
# for pin in INT_PINS:
#     threading.Thread(target=monitor_mcp_int, args=(pin,), daemon=True).start()

# --------------------------
# Blink LED B3
# --------------------------
try:
    while True:
        blink_led.value = not blink_led.value
        time.sleep(0.5)
except KeyboardInterrupt:
    pass
finally:
    lgpio.gpiochip_close(h)
