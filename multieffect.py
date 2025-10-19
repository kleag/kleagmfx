#!/usr/bin/env python3
import adafruit_ads1x15.ads1115 as ADS
import board
import busio
import math
import time
import uinput
import mido
import logging
import threading

from adafruit_ads1x15.analog_in import AnalogIn
from adafruit_mcp230xx.mcp23017 import MCP23017
from digitalio import Direction, Pull
from gpiozero import Button as GpioZeroButton, LED as GpioZeroLED
from signal import pause

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# --- CONFIGURATION ---
SENSITIVITY = 10.0 # Mouse movement sensitivity
DEAD_ZONE = 0.1    # Joystick dead zone
POWER_CURVE = 2.0  # Joystick speed scaling
LOOP_DELAY = 0.01  # General loop delay (seconds)
ENCODER_STEP = 5  # Value change per encoder tick (approx. 5% of 127)

SWITCH_CC = 64  # MIDI CC number for effect toggles
ENCODER_CC_NUMBERS = [20, 21, 22, 23]  # MIDI CC for encoders

# Keypad/Power LED (Keep original GPIO)
POWER_LED_PIN = 11
KEYPAD_ROW_PINS = [0, 1, 2, 3]
KEYPAD_COL_PINS = [4, 5, 6, 7]

# MCP23017 1 Button/LED Map
BUTTON_PINS_MAP = [(1, 14), (1, 15), (1, 6), (1, 7)] # B6, B7, A6, A7
LED_PINS_MAP = [(1, 13), (1, 12), (1, 4), (1, 5)] # B5, B4, A4, A5

# --- MIDI SETUP ---
midi_out = mido.open_output('KleagMFX', virtual=True)
midi_in = mido.open_input('KleagMFX', virtual=True)

def send_cc(cc, value):
    msg = mido.Message('control_change', control=cc, value=value)
    midi_out.send(msg)

# --- HARDWARE INITIALIZATION ---
i2c = busio.I2C(board.SCL, board.SDA)

# ADS1115 for Joystick (kept as requested)
ads = ADS.ADS1115(i2c)
# Use P0 and P1 for Joystick X and Y
joystick_x_axis = AnalogIn(ads, ADS.P0)
joystick_y_axis = AnalogIn(ads, ADS.P1)

# MCP23017
mcp1 = MCP23017(i2c, address=0x20)
mcp2 = MCP23017(i2c, address=0x21)
MCP_MAP = {1: mcp1, 2: mcp2}

# Power LED
power_led = mcp1.get_pin(POWER_LED_PIN)
power_led.direction = Direction.OUTPUT
power_led.value = True

# --- BUTTONS & LEDS (MCP23017) ---
class MCPButton:
    def __init__(self, mcp, pin):
        self.pin = mcp.get_pin(pin)
        self.pin.direction = Direction.INPUT
        self.pin.pull = Pull.UP
        self.last_state = not self.pin.value # Active Low
        self.when_pressed = None

    def check(self, idx):
        current_state = not self.pin.value
        if current_state and not self.last_state:
            if self.when_pressed:
                self.when_pressed(idx)
        self.last_state = current_state

class MCPLed:
    def __init__(self, mcp, pin):
        self.pin = mcp.get_pin(pin)
        self.pin.direction = Direction.OUTPUT
        self._value = False
        self.value = False

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, state):
        self._value = state
        self.pin.value = state

buttons = [MCPButton(MCP_MAP[mcp], pin) for mcp, pin in BUTTON_PINS_MAP]
leds = [MCPLed(MCP_MAP[mcp], pin) for mcp, pin in LED_PINS_MAP]

# --- JOYSTICK/MOUSE SETUP (retained ADS1115 usage) ---
events = (uinput.REL_X, uinput.REL_Y, uinput.BTN_LEFT)
try:
    device = uinput.Device(events)
except Exception as e:
    logger.error(f"UInput device creation failed. Check permissions (sudo or your user in the input group setup with udev). Error: {e}")
    exit(1)

joystick_sw = mcp1.get_pin(10)  # B2
joystick_sw.direction = Direction.INPUT
joystick_sw.pull = Pull.UP
joystick_last_switch_state = True # True = not pressed

def read_joystick():
    """Return normalized X, Y values in range -1.0 .. +1.0 using ADS1115."""
    x_center = 1.65 # Approximate center voltage
    y_center = 1.65
    x = (joystick_x_axis.voltage - x_center) / x_center
    y = (joystick_y_axis.voltage - y_center) / y_center
    return max(-1, min(1, x)), max(-1, min(1, y))

def calculate_speed(x, y):
    """Calculates movement speed based on joystick position."""
    magnitude = math.sqrt(x**2 + y**2)
    if magnitude < DEAD_ZONE: return 0, 0
    scaled_magnitude = (magnitude - DEAD_ZONE) / (1.0 - DEAD_ZONE)
    speed_factor = math.pow(scaled_magnitude, POWER_CURVE) * SENSITIVITY
    if magnitude > 0:
        dx = (x / magnitude) * speed_factor
        dy = (y / magnitude) * speed_factor
        return dx, dy
    return 0, 0

# --- ROTARY ENCODERS ---
encoder_configs = [
    (mcp1, 0, 8, 9,  "Encoder 0", ENCODER_CC_NUMBERS[0]), # CC 20
    (mcp1, 3, 2, 1,  "Encoder 1", ENCODER_CC_NUMBERS[1]), # CC 21
    (mcp2, 15, 14, 13, "Encoder 2", ENCODER_CC_NUMBERS[2]), # CC 22
    (mcp2, 12, 11, 10, "Encoder 3", ENCODER_CC_NUMBERS[3]), # CC 23
]
encoders = []
for mcp, clk_pin, dt_pin, sw_pin, name, cc in encoder_configs:
    clk = mcp.get_pin(clk_pin)
    dt = mcp.get_pin(dt_pin)
    sw = mcp.get_pin(sw_pin)
    for pin in (clk, dt, sw):
        pin.direction = Direction.INPUT
        pin.pull = Pull.UP
    encoders.append({
        "name": name,
        "cc": cc,
        "clk": clk,
        "dt": dt,
        "sw": sw,
        "last_clk": clk.value,
        "last_sw": sw.value,
        "midi_value": 64
    })

# --- MIDI/ENCODER LOGIC ---
effect_states = [False] * 4 # Global state for MIDI toggles

def increment_cc_value(cc_num, direction):
    """Adjusts the MIDI CC value for an encoder incrementally."""
    for enc in encoders:
        if enc["cc"] == cc_num:
            current_value = enc["midi_value"]
            # Adjust by ENCODER_STEP, then clamp
            new_value = max(0, min(127, current_value + direction * ENCODER_STEP))
            if new_value != current_value:
                enc["midi_value"] = new_value
                send_cc(cc_num, new_value)
                logger.info(f"{enc['name']} CC {cc_num} adjusted to {new_value}")
            return

# Initialize all encoder MIDI values to 64 and send initial CC message
for enc in encoders:
    send_cc(enc["cc"], enc["midi_value"])

# --- KEYPAD LOGIC (retained) ---
# MCP pins A0-A7 for keypad
kp_pins = [mcp2.get_pin(i) for i in range(8)]

keypad_map = [
    ['1', '2', '3', 'A'],
    ['4', '5', '6', 'B'],
    ['7', '8', '9', 'C'],
    ['*', '0', '#', 'D']
]
kp_rows = kp_pins[:4]
kp_cols = kp_pins[4:]
for row in kp_rows:
    row.direction = Direction.OUTPUT
    row.value = True  # default HIGH

for col in kp_cols:
    col.direction = Direction.INPUT
    col.pull = Pull.UP  # enable pull-ups

def scan_keypad():
    for row_idx, row in enumerate(kp_rows):
        row.value = False
        for col_idx, col in enumerate(kp_cols):
            if not col.value:
                char = keypad_map[row_idx][col_idx]
                while not col.value:
                    time.sleep(0.01)
                return char
        row.value = True
    return None

def set_bank(value: int):
    logger.info(f"set_bank {value}")
    for i in range(len(effect_states)):
        effect_states[i] = False
        leds[i].value = False
    midi_out.send(mido.Message('control_change', control=0, value=2))
    midi_out.send(mido.Message('control_change', control=32, value=value))
    midi_out.send(mido.Message('program_change', program=0))

def set_preset(value: int):
    logger.info(f"set_preset {value}")
    for i in range(len(effect_states)):
        effect_states[i] = False
        leds[i].value = False
    midi_out.send(mido.Message('program_change', program=value))

# --- BUTTON HANDLERS ---
def handle_effect_toggle(idx):
    effect_states[idx] = not effect_states[idx]
    leds[idx].value = effect_states[idx]
    send_cc(SWITCH_CC + idx, 127 if effect_states[idx] else 0)
    logger.info(f"Button {idx} pressed. State: {effect_states[idx]}")

for i, btn in enumerate(buttons):
    btn.when_pressed = handle_effect_toggle

# --- THREADS ---

def poll_joystick():
    global joystick_last_switch_state
    while True:
        # 1. Joystick Analog Control (Reads from ADS1115)
        x, y = read_joystick()
        dx, dy = calculate_speed(x, y)
        if dx != 0 or dy != 0:
            try:
                device.emit(uinput.REL_X, int(dx))
                device.emit(uinput.REL_Y, int(dy))
            except NameError: # Handle case where uinput device failed to initialize
                pass

        # 2. Joystick Button (Reads from MCP23017)
        joystick_switch_state = joystick_sw.value  # True = not pressed
        if joystick_switch_state != joystick_last_switch_state:
            uinput_state = 1 if joystick_switch_state == False else 0
            try:
                device.emit(uinput.BTN_LEFT, uinput_state)
            except NameError:
                pass

        joystick_last_switch_state = joystick_switch_state

        time.sleep(LOOP_DELAY)


def midi_input_thread():
    logger.info("Listening for incoming MIDI messages...")
    for msg in midi_in:
        logger.info(f"midi_input_thread received: {msg}")
        if msg.type == 'control_change':
            # Update Effect States (SWITCH_CC)
            if SWITCH_CC <= msg.control <= SWITCH_CC + 3:
                idx = msg.control - SWITCH_CC
                effect_states[idx] = msg.value > 0
                leds[idx].value = effect_states[idx]
            # Update Encoder CC Value if received externally
            if msg.control in ENCODER_CC_NUMBERS:
                for enc in encoders:
                    if enc["cc"] == msg.control:
                        enc["midi_value"] = msg.value
                        break

def keypad_and_buttons_thread():
    last_key = None
    while True:
        # Keypad Scan
        key = scan_keypad()
        if key and key != last_key:
            logger.info(f"Key pressed: {key}")
            if key in 'ABCD': set_bank(ord(key) - ord('A'))
            elif key in '0123456789': set_preset(int(key))
            last_key = key
        elif key is None:
            last_key = None

        # MCP Button Scan
        for i, btn in enumerate(buttons):
            btn.check(i)

        time.sleep(0.01)

def poll_encoders():
    while True:
        for enc in encoders:
            # Rotary Action
            clk_val = enc["clk"].value
            dt_val = enc["dt"].value

            if clk_val != enc["last_clk"]:
                direction = 1 if dt_val != clk_val else -1
                logger.info(f"{enc['name']} turned {direction}, send to {enc['cc']}")
                increment_cc_value(enc["cc"], direction)
                enc["last_clk"] = clk_val

            # Button Action (optional)
            sw_val = enc["sw"].value
            if sw_val != enc["last_sw"]:
                enc["last_sw"] = sw_val
                if not sw_val:
                    logger.info(f"{enc['name']}: Button pressed!")
        time.sleep(0.005)

# === Main ===
if __name__ == "__main__":
    threading.Thread(target=poll_joystick, daemon=True).start()
    threading.Thread(target=keypad_and_buttons_thread, daemon=True).start()
    threading.Thread(target=midi_input_thread, daemon=True).start()
    threading.Thread(target=poll_encoders, daemon=True).start()

    logger.info("Integrated Multi-effect controller running.")
    pause()
