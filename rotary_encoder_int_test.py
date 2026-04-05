import board
import busio
import digitalio
import time
from adafruit_mcp230xx.mcp23017 import MCP23017

# --- Configuration I2C ---
i2c = busio.I2C(board.SCL, board.SDA)
mcp = MCP23017(i2c, address=0x20)

# --- Configuration des Pins de l'encodeur ---
clk = mcp.get_pin(0) # A0
dt = mcp.get_pin(8)  # B0
sw = mcp.get_pin(9)  # B1

for pin in [clk, dt, sw]:
    pin.direction = digitalio.Direction.INPUT
    pin.pull = digitalio.Pull.UP

# --- Configuration des Interruptions du MCP23017 ---
mcp.interrupt_configuration = 0x40 # Mirror mode
mcp._write_u8(0x04, 0x01)          # GPINTENA (A0)
mcp._write_u8(0x05, 0x03)          # GPINTENB (B0, B1)

# --- Configuration de la Pin d'interruption sur le Pi (BCM 22) ---
# On remplace RPi.GPIO par digitalio pour éviter l'erreur de base address
int_pi = digitalio.DigitalInOut(board.D22)
int_pi.direction = digitalio.Direction.INPUT
int_pi.pull = digitalio.Pull.UP

# Variables d'état
last_clk_state = clk.value
counter = 0

print("Système prêt sur BCM 22 (Pin 7 Pisound)...")

try:
    while True:
        # On vérifie si la pin d'interruption est passée à LOW
        if not int_pi.value:
            # Lecture globale pour vider l'interruption
            all_states = mcp.gpio

            # Parsing des bits
            current_clk = all_states & 0x0001
            current_dt = (all_states >> 8) & 0x0001
            current_sw = (all_states >> 9) & 0x0001

            # Logique encodeur
            if current_clk != last_clk_state and current_clk == 0:
                if current_dt != current_clk:
                    counter += 1
                else:
                    counter -= 1
                print(f"MIDI Control: {counter}")

            if current_sw == 0:
                print("Switch actif")

            last_clk_state = current_clk

        # Petite pause pour ne pas saturer le CPU dans la boucle de polling
        # mais assez courte pour ne pas rater de rotation
        time.sleep(0.002)

except KeyboardInterrupt:
    print("Arrêt...")
