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

from joystick import Joystick
from mcp_button import MCPButton
from mcp_led import MCPLed

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

# --- CONFIGURATION ---

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

buttons = [MCPButton(MCP_MAP[mcp], pin) for mcp, pin in BUTTON_PINS_MAP]
leds = [MCPLed(MCP_MAP[mcp], pin) for mcp, pin in LED_PINS_MAP]

# --- JOYSTICK/MOUSE SETUP (retained ADS1115 usage) ---
events = (uinput.REL_X, uinput.REL_Y, uinput.BTN_LEFT, uinput.BTN_RIGHT, uinput.BTN_MIDDLE)
try:
    device = uinput.Device(events)
except Exception as e:
    logger.error(f"UInput device creation failed. Check permissions (sudo or your user in the input group setup with udev). Error: {e}")
    exit(1)

# 1st from left to right above : mcp n°2 clk B4=12 dt B3=11 sw B2=10
# 2nd from left to right above : mcp n°2 clk B7=15 dt B6=14 sw B5=13
# 3rd from left to right above : mcp n°1 clk A1=1 dt A2=2 sw A3=3
# 4th from left to right above (center of the board): mcp n°1 clk B1=9, dt B0=8, sw A0=0
# --- ROTARY ENCODERS ---
encoder_configs = [
    (mcp1, 9, 8, 0,  "Encoder 0", ENCODER_CC_NUMBERS[0]), # CC 20
    (mcp1, 1, 2, 3,  "Encoder 1", ENCODER_CC_NUMBERS[1]), # CC 21
    (mcp2, 15, 14, 13, "Encoder 2", ENCODER_CC_NUMBERS[2]), # CC 22
    (mcp2, 12, 11, 10, "Encoder 3", ENCODER_CC_NUMBERS[3]), # CC 23
]
encoders = []
for mcp, clk_pin, dt_pin, sw_pin, name, cc in encoder_configs:
    clk = mcp.get_pin(clk_pin)
    dt = mcp.get_pin(dt_pin)
    # sw = mcp.get_pin(sw_pin)
    initial_clk = clk.value
    initial_dt = dt.value
    for pin in (clk, dt):
        pin.direction = Direction.INPUT
        pin.pull = Pull.UP
    encoders.append({
        "name": name,
        "cc": cc,
        "clk": clk,
        "dt": dt,
        # "sw": sw,
        # "last_clk": clk.value,
        "last_state": (initial_clk << 1) | initial_dt,
        # "last_sw": sw.value,
        "midi_value": 64
    })
    buttons.append(MCPButton(mcp, sw_pin))

def read_encoder_state_machine(encoder):

    # 1. Read Current State (2-bit value: (clk << 1) | dt)
    current_clk = int(encoder["clk"].value)
    # print(type(current_clk), current_clk)
    current_dt = int(encoder["dt"].value)
    current_state = (current_clk << 1) | current_dt # e.g., 00, 01, 10, or 11

    last_state = encoder["last_state"]

    # 2. Check if the state has changed
    if current_state != last_state:

        # 3. Create a 4-bit transition key: (last_state << 2) | current_state
        # This key defines the exact transition, e.g., 00 -> 10, or 10 -> 11
        transition = (last_state << 2) | current_state

        # 4. Define Valid Transitions (Standard Quadrature Sequence)
        # Clockwise (CW) steps:
        # 00 -> 10 (0x2)
        # 10 -> 11 (0xB)
        # 11 -> 01 (0x7)
        # 01 -> 00 (0x4)
        CW_transitions = {0b0010, 0b1011, 0b1101, 0b0100} # Set of 4-bit transition keys

        # Counter-Clockwise (CCW) steps (Reversed Sequence):
        # 00 -> 01 (0x1)
        # 01 -> 11 (0x7) -> NOTE: 0x7 (1101) is CCW, 0x7 (0111) is CW
        # Let's list the CCW sequences explicitly:
        # 00 -> 01 (0x1)
        # 01 -> 11 (0x7)
        # 11 -> 10 (0xE)
        # 10 -> 00 (0x8)
        CCW_transitions = {0b0001, 0b0111, 0b1110, 0b1000}

        # 5. Check if the transition is valid and update
        if transition in CW_transitions:
            # logger.debug(f"Encoder {encoder['name']} Rotated → (clockwise)")
            encoder["last_state"] = current_state # Update state after a valid step
            direction = 1
            # logger.info(f"{encoder['name']} turned {direction}, send to {encoder['cc']}")
            increment_cc_value(encoder, direction)

        elif transition in CCW_transitions:
            # logger.debug(f"Encoder {encoder['name']} Rotated → (counterclockwise)")
            encoder["last_state"] = current_state # Update state after a valid step
            direction = -1
            # logger.debug(f"{encoder['name']} turned {direction}, send to {encoder['cc']}")
            increment_cc_value(encoder, direction)

        # 6. Optional: If the transition is invalid (i.e., due to bounce/noise),
        #    we generally ignore it and wait for a valid state.
        #    However, if we are in a state not part of the sequence,
        #    we might reset the state to catch up. For simplicity, we only
        #    update the state on a valid transition.
        else:
            # 5. CATCH-UP LOGIC: If the transition is INVALID (due to bounce or skipped steps),
            #    we force the last_state to the current_state.
            #    This ignores the current invalid movement but prepares the encoder
            #    to detect the next valid step from the new physical position.
            # logger.debug(f"Encoder {encoder['name']} state corrected (Invalid transition: {bin(transition)})")
            encoder["last_state"] = current_state
        # The key is to only update last_state *after* a valid transition has completed.


# --- MIDI/ENCODER LOGIC ---
effect_states = [False] * 4 # Global state for MIDI toggles

def increment_cc_value(encoder, direction):
    """Adjusts the MIDI CC value for an encoder incrementally."""
    current_value = encoder["midi_value"]
    # Adjust by ENCODER_STEP, then clamp
    new_value = max(0, min(127, current_value + direction * ENCODER_STEP))
    if new_value != current_value:
        encoder["midi_value"] = new_value
        send_cc(encoder["cc"], new_value)
        logger.debug(f"{encoder['name']} CC {encoder['cc']} adjusted to {new_value}")

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

def poll_encoders_thread():
    while True:
        for enc in encoders:
            read_encoder_state_machine(enc)
            # read_encoder_fixed(enc)
            # read_encoder(enc)
        time.sleep(0.001)

# === Main ===
if __name__ == "__main__":
    joystick = Joystick(i2c, ads, mcp)
    threading.Thread(target=joystick.poll_joystick, daemon=True).start()
    threading.Thread(target=keypad_and_buttons_thread, daemon=True).start()
    threading.Thread(target=midi_input_thread, daemon=True).start()
    threading.Thread(target=poll_encoders_thread, daemon=True).start()

    logger.info("Kleag's Multi-effect daemon running.")
    pause()
