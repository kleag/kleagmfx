import adafruit_ads1x15.ads1115 as ADS
import board
import busio
import logging
import mido
import time
import threading

from adafruit_ads1x15.analog_in import AnalogIn
from gpiozero import (Button, LED)
from signal import pause

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
LED_PINS = [23, 10, 9, 11]

# GPIO pins for keypad rows and columns
KEYPAD_ROW_PINS = [5, 6, 13, 19]
KEYPAD_COL_PINS = [12, 16, 20, 21]

POT_CC_NUMBERS = [20, 21, 22, 23]  # MIDI CC for pots

# === Setup ===
power_led = LED(POWER_LED_PIN)
power_led.on()

buttons = [Button(gpio, bounce_time=0.01) for gpio in BUTTON_PINS]
# button_pressed = [False for gpio in BUTTON_PINS]
leds = [LED(pin) for pin in LED_PINS]


def map_adc_to_midi(value):
    # Flip the value: 0 becomes 65535, 65535 becomes 0
    # flipped = 65535 - value  # or 65535 - value if it ever reaches 65535
    # Scale to 0–127
    midi_value = int((value / 26363)*127)
    midi_value = max(0, min(127, midi_value))  # Ensure value is clamped
    return midi_value


def read_pot(channel):
    pot_value = channels[channel].value
    midi_value = map_adc_to_midi(pot_value)
    logger.debug(f"read_pot {channel}: {pot_value}, midi: {midi_value}")
    return midi_value


# === MIDI SETUP ===
midi_out = mido.open_output('Guitarix Footswitch', virtual=True)
midi_in = mido.open_input('Guitarix Footswitch', virtual=True)


# def toggle_action(i: int):
#     logger.info(f"toggle_action {i} (GPIO {BUTTON_PINS[i]})")
#     leds[i].toggle()
#     # send_control_change(30 + i, 127)
#     # send_control_change(30 + i, 0)
#     time.sleep(0.1)  # debounce


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

# === State ===
effect_states = [False] * 4
last_pot_values = [0] * len(POT_CC_NUMBERS)
pot_values = [0] * len(POT_CC_NUMBERS)


def send_cc(cc, value):
    logger.info(f"send_cc {cc}, {value}")
    msg = mido.Message('control_change', control=cc, value=value)
    midi_out.send(msg)


def scan_keypad():
    for col_idx, col in enumerate(cols):
        col.off()
        for row_idx, row in enumerate(rows):
            if row.is_pressed:
                char = keypad_map[row_idx][col_idx]
                logger.info(f"Char pressed [{row_idx}, {col_idx}]: '{char}'")
                while row.is_pressed:
                    time.sleep(0.01)
                col.on()
                return char
        col.on()
    return None


def set_bank(value: int):
    logger.info(f"set_bank {value}")
    effect_states = [False] * 4
    for i, btn in enumerate(buttons):
        toggle_effect(btn)
    midi_out.send(mido.Message('control_change', control=0, value=2))   # Bank MSB
    midi_out.send(mido.Message('control_change', control=32, value=value))  # Bank LSB
    midi_out.send(mido.Message('program_change', program=0))


def set_preset(value: int):
    logger.info(f"set_preset {value}")
    effect_states = [False] * 4
    for i, btn in enumerate(buttons):
        toggle_effect(btn)
    midi_out.send(mido.Message('program_change', program=value))


# === Threads ===

# Potentiometers
def poll_pots():
    while True:
        pot_changed = False
        for i in range(len(POT_CC_NUMBERS)):
            pot_value = read_pot(i)
            pot_values[i] = pot_value
            if abs(pot_value - last_pot_values[i]) > 2:
                pot_changed = True
                midi_out.send(mido.Message('control_change',
                                           control=POT_CC_NUMBERS[i],
                                           value=pot_value))
                last_pot_values[i] = pot_value
        if pot_changed:
            logger.info(f"pots = {pot_values}")
        time.sleep(0.05)


def midi_input_thread():
    logger.info("Listening for incoming MIDI messages...")
    for msg in midi_in:
        logger.info(f"midi_input_thread received: {msg}")
        if msg.type == 'control_change':
            if SWITCH_CC <= msg.control <= SWITCH_CC + 3:
                idx = msg.control - SWITCH_CC
                effect_states[idx] = msg.value > 0
                leds[idx].value = effect_states[idx]


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
        time.sleep(0.01)
        # # Buttons
        # for i, pin in enumerate(BUTTON_PINS):
        #     if buttons[i].is_pressed and not button_pressed[i]:
        #         midi_out.send(mido.Message('control_change',
        #                                    control=SWITCH_CC+i,
        #                                    value=127))
        #         button_pressed[i] = True
        #         leds[i].toggle()
        #         logger.info(f"Button {i} pressed")
        #     elif not buttons[i].is_pressed and button_pressed[i]:
        #         midi_out.send(mido.Message('control_change',
        #                                    control=SWITCH_CC+i,
        #                                    value=0))
        #         button_pressed[i] = False
        #         logger.info(f"Button {i} released")
        #
        # time.sleep(0.05)


# === Button Handlers ===
def toggle_effect(button):
    logger.info(f"toggle_effect {button}")
    for idx, btn in enumerate(buttons):
        if btn is button:
            break
    logger.info(f"toggle_effect idx={idx}")

    def handler():
        logger.info(f"toggle_effect handler idx={idx}, {effect_states[idx]}, {leds[idx].value}")
        # effect_states[idx] = not effect_states[idx]
        # leds[idx].value = effect_states[idx]
        # send_cc(SWITCH_CC + idx, 127 if effect_states[idx] else 0)
        send_cc(SWITCH_CC + idx, 127 if effect_states[idx] else 0)
    return handler()

logger.info(f"Activating toggling on buttons")
for i, btn in enumerate(buttons):
    btn.when_pressed = toggle_effect

# === Main ===
if __name__ == "__main__":
    threading.Thread(target=poll_pots, daemon=True).start()
    threading.Thread(target=keypad_thread, daemon=True).start()
    threading.Thread(target=midi_input_thread, daemon=True).start()

    logger.info("Multi-effect controller running.")
    pause()

