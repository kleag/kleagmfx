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
from rich.console import Console
from signal import pause


logger = logging.getLogger(__name__)


class Joystick:
    # --- CONFIGURATION ---
    SENSITIVITY = 30.0  # Maximum mouse speed in pixels/s
    DEAD_ZONE   = 0.02    # Joystick dead zone
    POWER_CURVE = math.log(1/SENSITIVITY) / math.log(0.02)  # Exponent to match 1px/s at 0.02, 100px/s at 1.0
    LOOP_DELAY = 0.01  # General loop delay (seconds)

    def __init__(self, ads: ADS.ADS1115, mcp: MCP23017, lock: threading.Lock, debug: bool = False):
        self.debug = debug
        # --- HARDWARE INITIALIZATION ---
        self.ads = ads
        self.lock = lock
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
        self.last_x = 0
        self.last_y = 0
        self.spike_count_x = 0
        self.spike_count_y = 0
        self.console = Console()


    def read_joystick(self):
        """Return normalized X, Y values in range -1.0 .. +1.0 using ADS1115."""
        x_center = 1.62 # Approximate center voltage
        y_center = 1.65
        with self.lock:
            x = (self.joystick_x_axis.voltage - x_center) / x_center
            y = (self.joystick_y_axis.voltage - y_center) / y_center
        return max(-1, min(1, x)), max(-1, min(1, y))

    def calculate_speed(self, x, y):
        # --- 1. Glitch Guard Logic ---
        # If the reading is exactly 1.0 (or -1.0) and we were just at 0
        if abs(x) > 0.99 and abs(self.last_x) < 0.1:
            self.spike_count_x += 1
            if self.spike_count_x < 2: # Ignore the first frame of a max-value spike
                x = 0
        else:
            self.spike_count_x = 0

        if abs(y) > 0.99 and abs(self.last_y) < 0.1:
            self.spike_count_y += 1
            if self.spike_count_y < 2:
                y = 0
        else:
            self.spike_count_y = 0

        self.last_x, self.last_y = x, y

        # --- 2. Axial Dead Zone Logic ---
        # X Axis
        if abs(x) < Joystick.DEAD_ZONE:
            dx = 0
        else:
            norm_x = (abs(x) - Joystick.DEAD_ZONE) / (1.0 - Joystick.DEAD_ZONE)
            dx = math.pow(norm_x, Joystick.POWER_CURVE) * math.copysign(Joystick.SENSITIVITY, x)

        # Y Axis
        if abs(y) < Joystick.DEAD_ZONE:
            dy = 0
        else:
            norm_y = (abs(y) - Joystick.DEAD_ZONE) / (1.0 - Joystick.DEAD_ZONE)
            dy = math.pow(norm_y, Joystick.POWER_CURVE) * math.copysign(Joystick.SENSITIVITY, y)

        return dx, dy

    def poll_joystick(self):
        while True:
            # 1. Joystick Analog Control (Reads from ADS1115)
            x, y = self.read_joystick()
            # logger.debug(f"joystick {x},{y}")
            dx, dy = self.calculate_speed(x, y)
            if dx != 0 or dy != 0:
                # logger.debug(f"joystick move: {dx},{dy}")
                try:
                    self.device.emit(uinput.REL_X, int(-dx))
                    self.device.emit(uinput.REL_Y, int(-dy))
                except NameError as e: # Handle case where uinput device failed to initialize
                    logger.warn(f"Joystick.poll_joystick uinput failure: {e}")

            # 2. Joystick Button (Reads from MCP23017)
            switch_state = self.joystick_sw.value  # True = not pressed
            if switch_state != self.last_switch_state:
                uinput_state = 1 if switch_state == False else 0
                # logger.debug(f"joystick button new state: {uinput_state}")
                try:
                    self.device.emit(uinput.BTN_MIDDLE, uinput_state)
                except NameError as e:
                    logger.error(f"Name error in joystick button: {e}")

            self.last_switch_state = switch_state
            if self.debug:
                status_text = (
                    f"[bold blue]X:[/bold blue] {self.joystick_x_axis.voltage:+5.2f}V ({x:+5.2f}) [dim]dx={dx:+6.2f}[/dim] | "
                    f"[bold magenta]Y:[/bold magenta] {self.joystick_y_axis.voltage:+5.2f}V ({y:+5.2f}) [dim]dy={dy:+6.2f}[/dim] | "
                    f"[bold yellow]Switch:[/bold yellow] {'Released' if switch_state else 'Pressed'}"
                )
                self.console.print(status_text, end="\r")
            time.sleep(Joystick.LOOP_DELAY)


# === Main ===
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
        # --- HARDWARE INITIALIZATION ---
    i2c = busio.I2C(board.SCL, board.SDA)
    i2c_lock = threading.Lock()

    # ADS1115 for Joystick (kept as requested)
    ads = ADS.ADS1115(i2c)

    mcp = MCP23017(i2c, address=0x20)

    joystick = Joystick(ads, mcp, lock=i2c_lock, debug=True)
    threading.Thread(target=joystick.poll_joystick, daemon=True).start()

    logger.info("Joystick daemon running.")
    pause()
