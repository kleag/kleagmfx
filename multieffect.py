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
from keypad import KeyPad
from mcp_button import MCPButton
from mcp_led import MCPLed
from rotary_encoder import RotaryEncoder

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

# --- CONFIGURATION ---

SWITCH_CC = 64  # MIDI CC number for effect toggles
ENCODER_CC_NUMBERS = [20, 21, 22, 23]  # MIDI CC for encoders

# Keypad/Power LED (Keep original GPIO)
POWER_LED_PIN = 11

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
    encoder = RotaryEncoder(midi_out, mcp, name, clk_pin, dt_pin, sw_pin, cc)
    encoders.append(encoder)
    buttons.append(encoder.button)


# --- MIDI/ENCODER LOGIC ---
effect_states = [False] * 4 # Global state for MIDI toggles


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

def buttons_thread():
        # MCP Button Scan
        for i, btn in enumerate(buttons):
            btn.check(i)

        time.sleep(0.01)

# === Main ===
if __name__ == "__main__":
    joystick = Joystick(i2c, ads, mcp1)
    keypad = KeyPad(midi_out, mcp2)

    threading.Thread(target=joystick.poll_joystick, daemon=True).start()
    threading.Thread(target=keypad.keypad_thread, daemon=True).start()
    threading.Thread(target=buttons_thread, daemon=True).start()
    threading.Thread(target=midi_input_thread, daemon=True).start()
    for encoder in encoders:
        threading.Thread(target=encoder.poll_thread, daemon=True).start()

    logger.info("Kleag's Multi-effect daemon running.")
    pause()
