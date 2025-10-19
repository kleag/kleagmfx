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

import adafruit_ads1x15.ads1115 as ADS
import board
import busio
import math
import time
import uinput

from adafruit_ads1x15.analog_in import AnalogIn
from adafruit_mcp230xx.mcp23017 import MCP23017
from digitalio import Direction, Pull
from signal import pause

# --- Configuration ---
SENSITIVITY = 10.0 # Mouse movement sensitivity (higher value = faster movement)
DEAD_ZONE = 0.1    # Ignore movements within this normalized radius of the center (0.0 to 1.0)
POWER_CURVE = 2.0  # Speed scaling: 1.0 is linear, >1.0 makes small movements slower (e.g., 2.0 for quadratic)
LOOP_DELAY = 0.01  # Delay between joystick readings (seconds)

# --- Hardware Setup ---

# 🚨 CRITICAL FIX: Define events before they are used in the try block
events = (
    uinput.REL_X,       # Relative X movement
    uinput.REL_Y,       # Relative Y movement
    uinput.BTN_LEFT,    # Left mouse button
)

try:
    # Create the virtual device
    device = uinput.Device(events)
    print("Virtual UInput Mouse Created. Running with 'sudo' is required.")
except Exception as e:
    # This error should now only occur if uinput is not installed or the kernel module is missing.
    print(f"Error creating UInput device. Check installation or permissions. Error: {e}")
    exit()

# Initialize I2C and MCP23017
i2c = busio.I2C(board.SCL, board.SDA)
# Create the ADS1115 ADC object
ads = ADS.ADS1115(i2c)
# --- Setup MCP23017 ---
mcp1 = MCP23017(i2c, address=0x20)
mcp2 = MCP23017(i2c, address=0x21)

# --- Rotary encoder definitions ---
# Each entry: (mcp, clk_pin, dt_pin, sw_pin, name)
encoder_configs = [
    (mcp1, 0, 8, 9,  "Encoder 0"),      # original one
    (mcp1, 3, 2, 1,  "Encoder 1"),      # first new: A2 (clk), A3 (dt), A1 (sw)
    (mcp2, 15, 14, 13,  "Encoder 2"),      # second: B6 (clk), B7 (dt), B5 (sw)
    (mcp2, 12, 11, 10,  "Encoder 3"),      # third: B3 (clk), B4 (dt), B2 (sw)
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

# Create channels for X and Y
x_axis = AnalogIn(ads, ADS.P0)
y_axis = AnalogIn(ads, ADS.P1)

def read_joystick():
    """Return normalized X, Y values in range -1.0 .. +1.0"""
    # Joystick gives ~0V to ~3.3V, midpoint around 1.65V
    x_center = 1.65
    y_center = 1.65
    x = (x_axis.voltage - x_center) / x_center
    y = (y_axis.voltage - y_center) / y_center
    return max(-1, min(1, x)), max(-1, min(1, y))

joystick_sw = mcp1.get_pin(10)  # B2 is pin 10 in Adafruit MCP23017 library
joystick_sw.direction = Direction.INPUT
joystick_sw.pull = Pull.UP  # Assuming joystick_sw connects to GND when pressed

# Variable to track the previous state of the switch
joystick_last_switch_state = True # True = not pressed

# Setup LEDs as outputs
pwr_led = mcp1.get_pin(11)  # B3 - blinking LED
pwr_led.direction = Direction.OUTPUT
# B4:12, B5:13, A4:4, A5:5
leds = [mcp1.get_pin(pin) for pin in [13, 12, 4, 5]]
for led in leds:
    led.direction = Direction.OUTPUT

# Setup buttons as inputs with pull-ups
# B6:14, B7:15, A6:6, A7:7
btns = [mcp1.get_pin(pin) for pin in [14, 15, 6, 7]]
for btn in btns:
    led.direction = Direction.OUTPUT
    btn.direction = Direction.INPUT
    btn.pull = Pull.UP


led_button_map = dict(zip(leds, btns))

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

def read_encoder_button(enc):
    sw_val = enc["sw"].value
    if sw_val != enc["last_sw"]:
        enc["last_sw"] = sw_val
        if not sw_val:
            print(f"{enc['name']}: Button pressed!")
        else:
            print(f"{enc['name']}: Button released!")
        time.sleep(0.2)

def calculate_speed(x, y):
    """
    Calculates movement speed based on joystick position.
    Applies dead zone and power curve scaling.
    """
    # Calculate distance from center (magnitude)
    magnitude = math.sqrt(x**2 + y**2)

    # Apply dead zone
    if magnitude < DEAD_ZONE:
        return 0, 0

    # Scale magnitude: (distance - dead_zone) / (1 - dead_zone)
    # This maps the range [DEAD_ZONE, 1.0] to [0.0, 1.0]
    scaled_magnitude = (magnitude - DEAD_ZONE) / (1.0 - DEAD_ZONE)

    # Apply power curve scaling for "logarithmic-like" behavior
    # For POWER_CURVE=2.0, speed is proportional to magnitude^2, making small movements very slow.
    speed_factor = math.pow(scaled_magnitude, POWER_CURVE) * SENSITIVITY

    # Recalculate movement vector based on new speed factor
    # We maintain the direction (x/magnitude, y/magnitude)
    if magnitude > 0:
        dx = (x / magnitude) * speed_factor
        dy = (y / magnitude) * speed_factor
        return dx, dy
    else:
        return 0, 0

print("B3 will blink, other LEDs follow button presses.")
print("Manipulate and press the joystick.")
print("Rotate or press any encoder.\n")
print("Press Ctrl+C to exit\n")

try:
    last_blink = time.time()
    blink_state = False
    
    while True:
        # Blink B3 every 0.5 seconds
        if time.time() - last_blink >= 0.5:
            blink_state = not blink_state
            pwr_led.value = blink_state
            last_blink = time.time()
        
        # Control LEDs based on button presses (buttons are active low)
        for led, btn in led_button_map.items():
            led.value = not btn.value
        
        # Read and print joystick values
        x, y = read_joystick()
        # 2. Calculate Movement
        dx, dy = calculate_speed(x, y)

        joystick_switch_state = joystick_sw.value  # True = not pressed, False = pressed
        print(f"X: {x_axis.voltage:.3f} V ({x:+.2f}) dx={dx}, Y: {y_axis.voltage:.3f} V ({y:+.2f}) dy={dy}, Switch: {'Released' if joystick_switch_state else 'Pressed'}",
              end="\r")

        # 3. Move Mouse (Using UInput)
        if dx != 0 or dy != 0:
            # Emit relative X and Y movement events (uinput handles integer values)
            device.emit(uinput.REL_X, int(dx))
            device.emit(uinput.REL_Y, int(dy))


        # 5. Handle Mouse Button Click
        if joystick_switch_state != joystick_last_switch_state:
            # UInput button states: 1 for press, 0 for release
            uinput_state = 1 if joystick_switch_state == False else 0
            device.emit(uinput.BTN_LEFT, uinput_state)

        # Update last state
        joystick_last_switch_state = joystick_switch_state


        # Read and print rotary encoders values
        for enc in encoders:
            read_encoder(enc)
            read_encoder_button(enc)

        # Polling interval
        time.sleep(0.01)

except KeyboardInterrupt:
    print("\nExiting...")
    # Turn off all LEDs
    for led in led_button_map.keys():
        led.value = False
    print("All LEDs off. Goodbye!")
