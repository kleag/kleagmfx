#!/usr/bin/env python3
import time
import math
from adafruit_ads1x15.analog_in import AnalogIn
import adafruit_ads1x15.ads1115 as ADS
from board import SCL, SDA
import busio
import board
from digitalio import Direction, Pull
from adafruit_mcp230xx.mcp23017 import MCP23017
import uinput

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

# Create I2C bus
i2c = busio.I2C(SCL, SDA)

# Create the ADS1115 ADC object
ads = ADS.ADS1115(i2c)
#ads.gain = 1  # +/-4.096V input range

# Create channels for X and Y
x_axis = AnalogIn(ads, ADS.P0)
y_axis = AnalogIn(ads, ADS.P1)

# --- Setup MCP23017 ---
mcp = MCP23017(i2c, address=0x20)
switch = mcp.get_pin(10)  # B2 is pin 10 in Adafruit MCP23017 library
switch.direction = Direction.INPUT
switch.pull = Pull.UP  # Assuming switch connects to GND when pressed

# Variable to track the previous state of the switch
last_switch_state = True # True = not pressed

def read_joystick():
    """Return normalized X, Y values in range -1.0 .. +1.0"""
    # Joystick gives ~0V to ~3.3V, midpoint around 1.65V
    # Read the full range of voltage: 0V to 3.3V
    # A center voltage of 1.65 is an estimate; you might need to calibrate this
    x_center = 1.65
    y_center = 1.65
    x = (x_axis.voltage - x_center) / x_center
    y = (y_axis.voltage - y_center) / y_center

    # Invert Y-axis movement: pushing forward (less voltage) should move the cursor UP (negative change in screen Y)
    # The ADS1115 P1 (Y-axis) increases voltage when pulling the stick *down*, which should be *positive* screen Y movement.
    # The calculation below for y returns a negative value when pulled down (V < V_center), so we invert it for screen movement.
    y = -y

    return max(-1, min(1, x)), max(-1, min(1, y))

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

try:
    print(f"Joystick Mouse Control Active. Sensitivity: {SENSITIVITY}, Dead Zone: {DEAD_ZONE}, Power Curve: {POWER_CURVE}")
    print("Joystick switch acts as Left Mouse Button. Press Ctrl+C to stop.")

    while True:
        # 1. Read Joystick Position
        x, y = read_joystick()

        # 2. Calculate Movement
        dx, dy = calculate_speed(x, y)

        switch_state = switch.value  # True = not pressed, False = pressed
        print(f"X: {x_axis.voltage:.3f} V ({x:+.2f}) dx={dx}, Y: {y_axis.voltage:.3f} V ({y:+.2f}) dy={dy}, Switch: {'Released' if switch_state else 'Pressed'}",
              end="\r")

        # 3. Move Mouse (Using UInput)
        if dx != 0 or dy != 0:
            # Emit relative X and Y movement events (uinput handles integer values)
            device.emit(uinput.REL_X, int(dx))
            device.emit(uinput.REL_Y, int(dy))

        # 4. Read Switch State
        current_switch_state = switch.value # True = not pressed, False = pressed

        # 5. Handle Mouse Button Click
        if current_switch_state != last_switch_state:
            # UInput button states: 1 for press, 0 for release
            uinput_state = 1 if current_switch_state == False else 0
            device.emit(uinput.BTN_LEFT, uinput_state)


        # Update last state
        last_switch_state = current_switch_state

        # 6. Optional: Print for Debugging (remove for production)
        # print(f"Joystick ({x:+.2f}, {y:+.2f}), Movement ({dx:+.1f}, {dy:+.1f}), Switch: {'Released' if current_switch_state else 'Pressed'}")

        time.sleep(LOOP_DELAY)

except KeyboardInterrupt:
    print("\nExiting cleanly.")
