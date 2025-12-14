#!/usr/bin/env python3
import board
import busio
import time
import mido
import queue
import logging
import threading

from adafruit_mcp230xx.mcp23017 import MCP23017
from digitalio import Direction, Pull
from signal import pause
from typing import List

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

# --- CONFIGURATION ---

KEYPAD_ROW_PINS = [0, 1, 2, 3]
KEYPAD_COL_PINS = [4, 5, 6, 7]

class KeyPad:
    keypad_map = [
        ['1', '2', '3', 'A'],
        ['4', '5', '6', 'B'],
        ['7', '8', '9', 'C'],
        ['*', '0', '#', 'D']
    ]
    def __init__(self, task_queue: queue.Queue, midi_out, mcp: MCP23017, row_pins: List[int] = KEYPAD_ROW_PINS, col_pins: List[int] = KEYPAD_COL_PINS):
        self.task_queue = task_queue
        self.last_key = None
        self.midi_out = midi_out
        self.mcp = mcp
        kp_pins = row_pins + col_pins

        self.kp_rows = [self.mcp.get_pin(i) for i in row_pins]
        self.kp_cols = [self.mcp.get_pin(i) for i in col_pins]

        for row in self.kp_rows:
            row.direction = Direction.OUTPUT
            row.value = True  # default HIGH

        for col in self.kp_cols:
            col.direction = Direction.INPUT
            col.pull = Pull.UP  # enable pull-ups

    def scan_keypad(self):
        for row_idx, row in enumerate(self.kp_rows):
            row.value = False
            for col_idx, col in enumerate(self.kp_cols):
                if not col.value:
                    char = KeyPad.keypad_map[row_idx][col_idx]
                    while not col.value:
                        time.sleep(0.01)
                    return char
            row.value = True
        return None

    def set_bank(self, value: int):
        # logger.info(f"KeyPad.set_bank {value}")
        self.task_queue.put(("reset", []))
        self.midi_out.send(mido.Message('control_change', control=0, value=2))
        self.midi_out.send(mido.Message('control_change', control=32, value=value))
        self.midi_out.send(mido.Message('program_change', program=0))

    def set_preset(self, value: int):
        # logger.info(f"KeyPad.set_preset {value}")
        self.task_queue.put(("reset", []))
        self.midi_out.send(mido.Message('program_change', program=value))

    def keypad_thread(self):
        while True:
            # Keypad Scan
            key = self.scan_keypad()
            if key and key != self.last_key:
                # logger.info(f"Key pressed: {key}")
                if key in 'ABCD': self.set_bank(ord(key) - ord('A'))
                elif key in '0123456789': self.set_preset(int(key))
                self.last_key = key
            elif key is None:
                self.last_key = None
            time.sleep(0.01)


# === Main ===
if __name__ == "__main__":
    i2c = busio.I2C(board.SCL, board.SDA)
    mcp = MCP23017(i2c, address=0x21)
    # --- MIDI SETUP ---
    midi_out = mido.open_output('KleagMFX', virtual=True)
    task_queue = queue.Queue()
    keypad = KeyPad(task_queue, midi_out, mcp)
    threading.Thread(target=keypad.keypad_thread, daemon=True).start()

    logger.info("KeyPad daemon running.")
    pause()
