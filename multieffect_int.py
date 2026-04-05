#!/usr/bin/env python3
import adafruit_ads1x15.ads1115 as ADS
import board
import busio
import digitalio
import math
import queue
import time
import uinput
import mido
import logging
import subprocess
import threading

from adafruit_ads1x15.analog_in import AnalogIn
from adafruit_mcp230xx.mcp23017 import MCP23017
from digitalio import Direction, Pull
from gpiozero import Button as GpioZeroButton, LED as GpioZeroLED
from signal import pause

from expression_pedal import ExpressionPedal
from joystick import Joystick
from keypad import KeyPad
from mcp_button import MCPButton
from mcp_led import MCPLed
from rotary_encoder import RotaryEncoder

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG, force=True)

# --- CONFIGURATION ---
SWITCH_CC = 64  # MIDI CC number for effect toggles
ENCODER_CC_NUMBERS = [20, 21, 22, 23]  # MIDI CC for encoders

# Keypad/Power LED (Keep original GPIO)
POWER_LED_PIN = 11

# MCP23017 1 Button/LED Map
BUTTON_PINS_MAP = [(1, 14), (1, 15), (1, 6), (1, 7)] # B6, B7, A6, A7
LED_PINS_MAP = [(1, 13), (1, 12), (1, 4), (1, 5)] # B5, B4, A4, A5

# --- MIDI/ENCODER LOGIC ---
effect_states = [False] * 4 # Global state for MIDI toggles

def send_cc(cc, value):
    msg = mido.Message('control_change', control=cc, value=value)
    midi_out.send(msg)

# --- BUTTON HANDLERS ---
def handle_effect_toggle(idx):
    # logger.info(f"handle_effect_toggle {idx}")
    effect_states[idx] = not effect_states[idx]
    if leds[idx] is not None:
        leds[idx].value = effect_states[idx]
    send_cc(SWITCH_CC + idx, 127 if effect_states[idx] else 0)
    # logger.info(f"Button {idx} pressed. State: {effect_states[idx]}")


def reset():
    logger.info("reset")
    for i in range(len(effect_states)):
        effect_states[i] = False
        if leds[i] is not None:
            leds[i].value = False

# --- THREADS ---

def midi_input_thread():
    # logger.info("Listening for incoming MIDI messages...")
    for msg in midi_in:
        if msg.type == 'control_change':
            # logger.info(f"midi_input_thread received: {msg}")
            # Update Effect States (SWITCH_CC)
            if SWITCH_CC <= msg.control <= SWITCH_CC + 3:
                idx = msg.control - SWITCH_CC
                new_state = msg.value > 0

                # Only update if the state actually changed to avoid flickering
                if effect_states[idx] != new_state:
                    effect_states[idx] = new_state
                    if leds[idx] is not None:
                        leds[idx].value = new_state
                # logger.debug(f"Sync: LED {idx} set to {new_state} via MIDI")
            # Update Encoder CC Value if received externally
            if msg.control in ENCODER_CC_NUMBERS:
                for encoders in [encoders_mcp1, encoders_mcp2]:
                    for enc in encoders:
                        if enc.cc == msg.control:
                            enc.update_from_midi(msg.value)
                            break

def buttons_thread():
    while True:
        # MCP Button Scan
        for i, btn in enumerate(buttons):
            btn.check(i)
        time.sleep(0.01)

# --- Main Thread Logic ---
def main_thread_loop():
    # logger.info("\n[Main Thread] Starting queue processor...")

    while True:
        while not task_queue.empty():
            try:
                func, args = task_queue.get(timeout=0.1)
                if func == "reset":
                    reset(*args)

                task_queue.task_done()
            except queue.Empty:
                # This happens if the queue is temporarily empty
                pass
        time.sleep(0.001)

def link_pipewire_ports():
    try:
        # Link Script -> Guitarix
        subprocess.run(['pw-link', 'Midi-Bridge:RtMidiOut Client:(capture_0) KleagMFX', 'gx_head_amp:midi_in_1'], check=False)
        # Link Guitarix -> Script
        subprocess.run(['pw-link', 'gx_head_amp:midi_out_1', 'Midi-Bridge:RtMidiIn Client:(playback_0) KleagMFX'], check=False)
        logger.info("PipeWire MIDI ports linked successfully.")
    except Exception as e:
        logger.error(f"Failed to link PipeWire ports: {e}")


# --- MIDI SETUP ---
midi_out = mido.open_output('KleagMFX', virtual=True)
midi_in = mido.open_input('KleagMFX', virtual=True)

# --- HARDWARE INITIALIZATION ---
i2c = busio.I2C(board.SCL, board.SDA)
i2c_lock = threading.Lock()

# ADS1115 for Joystick (kept as requested)
ads = ADS.ADS1115(i2c)

# MCP23017
mcp1 = MCP23017(i2c, address=0x20)
mcp2 = MCP23017(i2c, address=0x21)
MCP_MAP = {1: mcp1, 2: mcp2}

# --- Configuration of Interruption pins ---
int_mcp1 = digitalio.DigitalInOut(board.D22) # Pin pisound 7
int_mcp2 = digitalio.DigitalInOut(board.D5)  # Pin pisound 5
for pin in [int_mcp1, int_mcp2]:
    pin.direction = digitalio.Direction.INPUT
    pin.pull = digitalio.Pull.UP

for m in [mcp1, mcp2]:
    m.interrupt_configuration = 0x40 # Mode Mirror : INTA/B linked
    # Activate interruptions on pins used
    # MCP1 : A0, A1, A2, A3 (0x0F) et B0, B1 (0x03)
    # MCP2 : B2-B7 (0xFC)
    if m == mcp1:
        m._write_u8(0x04, 0x0F) # GPINTENA
        m._write_u8(0x05, 0x03) # GPINTENB
    else:
        m._write_u8(0x04, 0x00) # GPINTENA (rien sur port A)
        m._write_u8(0x05, 0xFC) # GPINTENB (B2 à B7)


# Power LED
power_led = mcp1.get_pin(POWER_LED_PIN)
power_led.direction = Direction.OUTPUT
power_led.value = True

# Foot switches and their associated LED
buttons = [MCPButton(MCP_MAP[mcp], pin) for mcp, pin in BUTTON_PINS_MAP]
leds = [MCPLed(MCP_MAP[mcp], pin) for mcp, pin in LED_PINS_MAP]

# Board label: as visible on physical pedalboard: mcp number and mcp pins map
# RotaryEncoder4: 1st from left to right above : mcp n°2 clk B4=12 dt B3=11 sw B2=10
# RotaryEncoder3: 2nd from left to right above : mcp n°2 clk B7=15 dt B6=14 sw B5=13
# RotaryEncoder2: 3rd from left to right above : mcp n°1 clk A3=3  dt A2=2  sw A1=1
# RotaryEncoder1: 4th from left to right above : mcp n°1 clk A0=0, dt B0=8, sw B1=9
# --- ROTARY ENCODERS ---
encoder_configs = [
    (mcp1, 0,   8,  9, "Encoder 0", ENCODER_CC_NUMBERS[0]), # CC 20
    (mcp1, 3,   2,  1, "Encoder 1", ENCODER_CC_NUMBERS[1]), # CC 21
    (mcp2, 15, 14, 13, "Encoder 2", ENCODER_CC_NUMBERS[2]), # CC 22
    (mcp2, 12, 11, 10, "Encoder 3", ENCODER_CC_NUMBERS[3]), # CC 23
]
encoders_mcp1 = []
encoders_mcp2 = []
for mcp, clk_pin, dt_pin, sw_pin, name, cc in encoder_configs:
    encoder = RotaryEncoder(midi_out, mcp, name, clk_pin, dt_pin, sw_pin, cc)
    if mcp == mcp1:
        encoders_mcp1.append(encoder)
    else:
        encoders_mcp2.append(encoder)
    buttons.append(encoder.button)
    effect_states.append(False)
    leds.append(None)

def watchdog_thread():
    while True:
        if not int_mcp1.value:
            data = mcp1.gpio
            for enc in encoders_mcp1:
                enc.update(data)

        if not int_mcp2.value:
            data = mcp2.gpio
            for enc in encoders_mcp2:
                enc.update(data)

        time.sleep(0.001)

for i, btn in enumerate(buttons):
    btn.when_pressed = handle_effect_toggle


# === Main ===
if __name__ == "__main__":
    link_pipewire_ports()
    task_queue = queue.Queue()
    joystick = Joystick(ads, mcp1, lock=i2c_lock)
    keypad = KeyPad(task_queue, midi_out, mcp2)
    pedal = ExpressionPedal(midi_out, ads, lock=i2c_lock, channel=ADS.P2)

    threading.Thread(target=midi_input_thread, daemon=True).start()
    threading.Thread(target=buttons_thread, daemon=True).start()
    threading.Thread(target=joystick.poll_joystick, daemon=True).start()
    threading.Thread(target=keypad.keypad_thread, daemon=True).start()
    threading.Thread(target=pedal.poll, daemon=True).start()
    threading.Thread(target=watchdog_thread, daemon=True).start()

    # for encoder in encoders:
    #     threading.Thread(target=encoder.poll_thread, daemon=True).start()
    threading.Thread(target=main_thread_loop, daemon=True).start()

    logger.info("Kleag's Multi-effect daemon running.")
    try:
        pause()
    except KeyboardInterrupt:
        logger.info("Kleag's Multi-effect daemon terminating through keyboard interrupt.")
