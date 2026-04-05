#!/usr/bin/env python3
import board
import busio
import mido
import logging
import threading

from adafruit_mcp230xx.mcp23017 import MCP23017
from signal import pause

from rotary_encoder import RotaryEncoder

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, force=True)

# --- CONFIGURATION ---
ENCODER_CC_NUMBERS = [20, 21, 22, 23]  # MIDI CC for encoders

# --- MIDI SETUP ---
midi_out = mido.open_output('KleagMFX', virtual=True)

# --- HARDWARE INITIALIZATION ---
i2c = busio.I2C(board.SCL, board.SDA)

# MCP23017
mcp1 = MCP23017(i2c, address=0x20)
mcp2 = MCP23017(i2c, address=0x21)

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
encoders = []
for mcp, clk_pin, dt_pin, sw_pin, name, cc in encoder_configs:
    encoder = RotaryEncoder(midi_out, mcp, name, clk_pin, dt_pin, sw_pin, cc)
    encoders.append(encoder)


# === Main ===
if __name__ == "__main__":

    for encoder in encoders:
        threading.Thread(target=encoder.poll_thread, daemon=True).start()

    logger.info("Encoders test script running.")
    try:
        pause()
    except KeyboardInterrupt:
        logger.info("Encoders test script terminating through keyboard interrupt.")
