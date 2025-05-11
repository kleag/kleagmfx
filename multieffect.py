import adafruit_ads1x15.ads1115 as ADS
import board
import busio
import logging
import mido
import sys
import time
import threading
import traceback

from adafruit_ads1x15.analog_in import AnalogIn
from gpiozero import (Button, LED)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
logging.root.setLevel(logging.INFO)


# Initialize the I2C interface
i2c = busio.I2C(board.SCL, board.SDA)

# Create an ADS1115 object
ads = ADS.ADS1115(i2c)

# Define the analog input channel
channels = [AnalogIn(ads, ADS.P0),
            AnalogIn(ads, ADS.P1),
            AnalogIn(ads, ADS.P2),
            AnalogIn(ads, ADS.P3),]


# MIDI base controller input id
SWITCH_CC = 64  # Control Change number used in Guitarix

# === NEW GPIO ASSIGNMENTS ===
POWER_LED_PIN = 18


# BUTTON_PINS = [14]
# LED_PINS = [23]
BUTTON_PINS = [14, 4, 17, 27]
LED_PINS    = [23, 10, 9, 11]

# GPIO pins for keypad rows and columns
KEYPAD_ROW_PINS = [5, 6, 13, 19]
KEYPAD_COL_PINS = [12, 16, 20, 21]


# === Setup ===
power_led = LED(POWER_LED_PIN)
power_led.on()

buttons = [Button(gpio, bounce_time=0.2) for gpio in BUTTON_PINS]
button_pressed = [False for gpio in BUTTON_PINS]
leds = [LED(pin) for pin in LED_PINS]


def map_adc_to_midi(value):
    # Flip the value: 0 becomes 65535, 65535 becomes 0
    # flipped = 65535 - value  # or 65535 - value if it ever reaches 65535
    # Scale to 0–127
    midi_value = int((value / 26363)*127)
    midi_value =  max(0, min(127, midi_value))  # Ensure value is clamped
    return midi_value


def read_pot(channel):
    pot_value = channels[channel].value
    midi_value = map_adc_to_midi(pot_value)
    logger.debug(f"read_pot {channel}: {pot_value}, midi: {midi_value}")
    return midi_value


# === MIDI SETUP ===
midi_out = mido.open_output('Guitarix Footswitch', virtual=True)


def toggle_action(i: int):
    logger.info(f"toggle_action {i} (GPIO {BUTTON_PINS[i]})")
    leds[i].toggle()
    # send_control_change(30 + i, 127)
    # send_control_change(30 + i, 0)
    time.sleep(0.1)  # debounce


keypad_map = [
    ['1', '2', '3', 'A'],
    ['4', '5', '6', 'B'],
    ['7', '8', '9', 'C'],
    ['*', '0', '#', 'D']
]

cols = [LED(pin) for pin in KEYPAD_COL_PINS]
for col in cols:
    col.on()
rows = [Button(pin, pull_up=True) for pin in KEYPAD_ROW_PINS]

def send_cc(cc, value):
    msg = mido.Message('control_change', control=cc, value=value)
    midi_out.send(msg)


def scan_keypad():
    for col_idx, col in enumerate(cols):
        col.off()
        for row_idx, row in enumerate(rows):
            if row.is_pressed:
                char = keypad_map[row_idx][col_idx]
                logger.debug(f"Char pressed [{row_idx}, {col_idx}]: '{char}'")
                while row.is_pressed:
                    time.sleep(0.01)
                col.on()
                return char
        col.on()
    return None


def set_bank(value: int):
    midi_out.send(mido.Message('control_change', control=0, value=2))   # Bank MSB
    midi_out.send(mido.Message('control_change', control=32, value=value))  # Bank LSB
    midi_out.send(mido.Message('program_change', program=0))


def set_preset(value: int):
    midi_out.send(mido.Message('program_change', program=value))


def keypad_thread():
    last_key = None
    while True:
        key = scan_keypad()
        if key and key != last_key:
            logger.info(f"Key pressed: {key}")
            if key in 'ABCD':
                set_bank(ord(key) - ord('A'))  # bank select
            elif key in '0123456789':
                set_preset(int(key))  # preset select
            last_key = key
        elif key is None:
            last_key = None
        time.sleep(0.1)


# === MAIN LOOP ===
def main():
    potentiometers = True
    threading.Thread(target=keypad_thread, daemon=True).start()
    last_pot_values = [0] * 4
    while True:
        # Potentiometers
        pot_values = [0, 0, 0, 0]
        pot_changed = False
        for i in range(4 if potentiometers else 0):
            try:
                pot_value = read_pot(i)
                pot_values[i] = pot_value
                if abs(pot_value - last_pot_values[i]) > 2:
                    pot_changed = True
                    midi_out.send(mido.Message('control_change',
                                               control=20+i,
                                               value=pot_value))
                    last_pot_values[i] = pot_value
            except OSError as e:
                logger.error(f"Error reading potentiometer value: {e}. Stopping reading potentiometers")
                potentiometers = False
                # sys.exit(1)
        if pot_changed:
            logger.info(f"pots = {pot_values}")
        # Buttons
        for i, pin in enumerate(BUTTON_PINS):
            if buttons[i].is_pressed and not button_pressed[i]:
                midi_out.send(mido.Message('control_change',
                                           control=SWITCH_CC+i,
                                           value=127))
                button_pressed[i] = True
                leds[i].toggle()
                logger.info(f"Button {i} pressed")
            elif not buttons[i].is_pressed and button_pressed[i]:
                midi_out.send(mido.Message('control_change',
                                           control=SWITCH_CC+i,
                                           value=0))
                button_pressed[i] = False
                logger.info(f"Button {i} released")

        time.sleep(0.05)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Exception {e}:\n{traceback.format_exc()}")
