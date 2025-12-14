#!/usr/bin/env python3
import adafruit_ads1x15.ads1115 as ADS
import board
import busio
import logging
import math
import threading
import time
import uinput

from adafruit_ads1x15.analog_in import AnalogIn
from adafruit_mcp230xx.mcp23017 import MCP23017
from digitalio import Direction, Pull
from signal import pause


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

# --- CONFIGURATION ---
SENSITIVITY = 50.0  # Maximum mouse speed in pixels/s
DEAD_ZONE   = 0.1    # Joystick dead zone
POWER_CURVE = math.log(1/SENSITIVITY) / math.log(0.02)  # Exponent to match 1px/s at 0.02, 100px/s at 1.0
LOOP_DELAY = 0.01  # General loop delay (seconds)

class Joystick:
    def __init__(self, i2c: busio.I2C, ads: ADS.ADS1115, mcp: MCP23017):
        # --- HARDWARE INITIALIZATION ---
        self.i2c = i2c
        self.ads = ads
        # Use P0 and P1 for Joystick X and Y
        self.joystick_x_axis = AnalogIn(ads, ADS.P0)
        self.joystick_y_axis = AnalogIn(ads, ADS.P1)


        # --- JOYSTICK/MOUSE SETUP (retained ADS1115 usage) ---
        events = (uinput.REL_X, uinput.REL_Y, uinput.BTN_LEFT, uinput.BTN_RIGHT, uinput.BTN_MIDDLE)
        try:
            self.device = uinput.Device(events)
        except Exception as e:
            logger.error(f"UInput device creation failed. Check permissions (sudo or your user in the input group setup with udev). Error: {e}")
            exit(1)

        self.joystick_sw = mcp.get_pin(10)  # B2
        self.joystick_sw.direction = Direction.INPUT
        self.joystick_sw.pull = Pull.UP
        self.last_switch_state = True # True = not pressed

    def read_joystick(self):
        """Return normalized X, Y values in range -1.0 .. +1.0 using ADS1115."""
        x_center = 1.65 # Approximate center voltage
        y_center = 1.65
        x = (self.joystick_x_axis.voltage - x_center) / x_center
        y = (self.joystick_y_axis.voltage - y_center) / y_center
        return max(-1, min(1, x)), max(-1, min(1, y))

    def calculate_speed(self, x, y):
        """Calculates mouse movement speed from joystick position."""
        def axis_speed(v):
            av = abs(v)
            if av < DEAD_ZONE:
                return 0.0

            # Normalize after dead zone to range 0–1
            nv = (av - DEAD_ZONE) / (1.0 - DEAD_ZONE)

            # Exponential curve
            speed = SENSITIVITY * (nv ** POWER_CURVE)

            return speed if v > 0 else -speed

        return axis_speed(x), axis_speed(y)

    def poll_joystick(self):
        while True:
            # 1. Joystick Analog Control (Reads from ADS1115)
            x, y = self.read_joystick()
            #logger.debug(f"joystick {x},{y}")
            dx, dy = self.calculate_speed(x, y)
            if dx != 0 or dy != 0:
                logger.debug(f"joystick {dx},{dy}")
                try:
                    self.device.emit(uinput.REL_X, int(-dx))
                    self.device.emit(uinput.REL_Y, int(-dy))
                except NameError as e: # Handle case where uinput device failed to initialize
                    logger.warn(f"Joystick.poll_joystick uinput failure: {e}")

            # 2. Joystick Button (Reads from MCP23017)
            switch_state = self.joystick_sw.value  # True = not pressed
            if switch_state != self.last_switch_state:
                uinput_state = 1 if switch_state == False else 0
                logger.debug(f"joystick button new state: {uinput_state}")
                try:
                    self.device.emit(uinput.BTN_MIDDLE, uinput_state)
                except NameError as e:
                    logger.error(f"Name error in joystick button: {e}")

            self.last_switch_state = switch_state

            time.sleep(LOOP_DELAY)


# === Main ===
if __name__ == "__main__":
        # --- HARDWARE INITIALIZATION ---
    i2c = busio.I2C(board.SCL, board.SDA)

    # ADS1115 for Joystick (kept as requested)
    ads = ADS.ADS1115(i2c)

    mcp = MCP23017(i2c, address=0x20)

    joystick = Joystick(i2c, ads, mcp)
    threading.Thread(target=joystick.poll_joystick, daemon=True).start()

    logger.info("Joystick daemon running.")
    pause()
