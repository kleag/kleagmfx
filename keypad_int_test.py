#!/usr/bin/env python3
import time
import board
import busio
import RPi.GPIO as GPIO
from adafruit_mcp230xx.mcp23017 import MCP23017

# I2C setup
i2c = busio.I2C(board.SCL, board.SDA)

# MCP23017 at 0x21
mcp = MCP23017(i2c, address=0x21)

# MCP pins A0-A7 for keypad
pins = [mcp.get_pin(i) for i in range(8)]
rows = pins[:4]
cols = pins[4:]

# Configure rows as outputs
for row in rows:
    row.direction = row.Direction.OUTPUT
    row.value = True  # default HIGH

# Configure columns as inputs with pull-ups
for col in cols:
    col.direction = col.Direction.INPUT
    col.pull = col.Pull.UP

# Key mapping
KEYS = [
    ['1','2','3','A'],
    ['4','5','6','B'],
    ['7','8','9','C'],
    ['*','0','#','D']
]

# Raspberry Pi GPIO connected to MCP INTA
INT_PIN = 17  # change to your wiring
GPIO.setmode(GPIO.BCM)
GPIO.setup(INT_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

def scan_keypad():
    for r_idx, row in enumerate(rows):
        row.value = False  # drive current row LOW
        for c_idx, col in enumerate(cols):
            if not col.value:
                print("Key pressed:", KEYS[r_idx][c_idx])
                while not col.value:
                    time.sleep(0.01)  # wait for release
        row.value = True

# Interrupt callback
def keypad_interrupt(channel):
    # small delay to let signals settle
    time.sleep(0.01)
    scan_keypad()

# Setup GPIO interrupt
GPIO.add_event_detect(INT_PIN, GPIO.FALLING, callback=keypad_interrupt, bouncetime=50)

print("Press keys on the keypad. Ctrl+C to exit.")
try:
    while True:
        time.sleep(1)  # main loop does nothing, all handled by interrupt
except KeyboardInterrupt:
    print("Exiting...")
finally:
    GPIO.cleanup()
