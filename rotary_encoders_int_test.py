import board
import busio
import digitalio
import time
from adafruit_mcp230xx.mcp23017 import MCP23017

# --- Configuration I2C ---
i2c = busio.I2C(board.SCL, board.SDA)
mcp1 = MCP23017(i2c, address=0x20)
mcp2 = MCP23017(i2c, address=0x21)

# --- Configuration des Pins d'Interruption Pi (Pisound) ---
int_mcp1 = digitalio.DigitalInOut(board.D22) # Pin 7 Pisound
int_mcp2 = digitalio.DigitalInOut(board.D5)  # Autre pin libre
for pin in [int_mcp1, int_mcp2]:
    pin.direction = digitalio.Direction.INPUT
    pin.pull = digitalio.Pull.UP

# --- Classe de gestion des Encodeurs ---
class RotaryEncoder:
    def __init__(self, mcp, clk_pin, dt_pin, sw_pin, name, cc_number):
        self.mcp = mcp
        self.clk_num = clk_pin
        self.dt_num = dt_pin
        self.sw_num = sw_pin
        self.name = name
        self.cc = cc_number

        self.counter = 0
        self.last_clk_state = 1

        # Initialisation des pins physiques sur le MCP
        self.pin_clk = mcp.get_pin(clk_pin)
        self.pin_dt = mcp.get_pin(dt_pin)
        self.pin_sw = mcp.get_pin(sw_pin)

        for p in [self.pin_clk, self.pin_dt, self.pin_sw]:
            p.direction = digitalio.Direction.INPUT
            p.pull = digitalio.Pull.UP

    def update(self, gpio_state):
        # gpio_state est un entier de 16 bits représentant tout le MCP
        # Extraction des états via bitmask
        current_clk = (gpio_state >> self.clk_num) & 0x01
        current_dt = (gpio_state >> self.dt_num) & 0x01
        current_sw = (gpio_state >> self.sw_num) & 0x01

        changed = False
        # Détection de rotation (Falling edge sur CLK)
        if current_clk != self.last_clk_state and current_clk == 0:
            if current_dt != current_clk:
                self.counter = min(127, self.counter + 1)
            else:
                self.counter = max(0, self.counter - 1)
            print(f"{self.name} [CC{self.cc}]: {self.counter}")
            changed = True

        if current_sw == 0:
            # Note : à filtrer avec un timer si vous voulez éviter les répétitions
            pass

        self.last_clk_state = current_clk
        return changed

# --- Initialisation des instances ---
ENCODER_CC_NUMBERS = [20, 21, 22, 23]

encoders_mcp1 = [
    RotaryEncoder(mcp1, 0, 8, 9, "Rotary 1", ENCODER_CC_NUMBERS[0]),
    RotaryEncoder(mcp1, 3, 2, 1, "Rotary 2", ENCODER_CC_NUMBERS[1])
]

encoders_mcp2 = [
    RotaryEncoder(mcp2, 15, 14, 13, "Rotary 3", ENCODER_CC_NUMBERS[2]),
    RotaryEncoder(mcp2, 12, 11, 10, "Rotary 4", ENCODER_CC_NUMBERS[3])
]

# --- Configuration Hardware des MCP (Registers) ---
for m in [mcp1, mcp2]:
    m.interrupt_configuration = 0x40 # Mode Mirror : INTA/B liés
    # On active les interruptions sur les pins utilisées
    # Pour MCP1 : A0, A1, A2, A3 (0x0F) et B0, B1 (0x03)
    # Pour MCP2 : B2-B7 (0xFC)
    if m == mcp1:
        m._write_u8(0x04, 0x0F) # GPINTENA
        m._write_u8(0x05, 0x03) # GPINTENB
    else:
        m._write_u8(0x04, 0x00) # GPINTENA (rien sur port A)
        m._write_u8(0x05, 0xFC) # GPINTENB (B2 à B7)

# --- Boucle principale ---
print("Multi-Encoder MIDI Controller actif...")

try:
    while True:
        # Check MCP1
        if not int_mcp1.value:
            state1 = mcp1.gpio
            for enc in encoders_mcp1:
                enc.update(state1)

        # Check MCP2
        if not int_mcp2.value:
            state2 = mcp2.gpio
            for enc in encoders_mcp2:
                enc.update(state2)

        # Très légère pause pour le scheduler Linux
        time.sleep(0.001)

except KeyboardInterrupt:
    print("\nArrêt du contrôleur.")
