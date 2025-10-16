import board
import busio
import time

from adafruit_mcp230xx.mcp23017 import MCP23017
from digitalio import Direction, Pull
from signal import pause
import lgpio

# I2C setup
i2c = busio.I2C(board.SCL, board.SDA)

# MCP23017 at address 0x20
mcp = MCP23017(i2c, address=0x20)

# Rotary encoder connections
clk = mcp.get_pin(0)  # A0
dt = mcp.get_pin(8)   # B0
sw = mcp.get_pin(9)   # B1 (push button)

# Configure inputs with pull-ups
for pin in (clk, dt, sw):
    pin.direction = Direction.INPUT
    pin.pull = Pull.UP

# Track rotary state
last_clk = clk.value

# Callback for switch interrupt
def switch_changed(pin):
    if not pin.value:
        print("Button pressed!")
    else:
        print("Button released!")

# Enable interrupt on both edges (change)
# Set up to check all the port B pins (pins 8-15) w/interrupts!

mcp.interrupt_enable = 0x100 # Enable Interrupts in all pins
# If intcon is set to 0's we will get interrupts on
# both button presses and button releases
mcp.interrupt_configuration = 0x0000  # interrupt on any change
mcp.io_control = 0x44  # Interrupt as open drain and mirrored
mcp.clear_ints()  # Interrupts need to be cleared initially

def print_interrupt(port):
    """Callback function to be called when an Interrupt occurs."""
    for pin_flag in mcp.int_flag:
        print(f"Interrupt connected to Pin: {port}")
        print(f"Pin number: {pin_flag} changed to: {pins[pin_flag].value}")
    mcp.clear_ints()

# --- Raspberry Pi side interrupt setup using lgpio ---
INT_PIN = 6  # BCM GPIO17, connected to MCP23017 INT output

# Open GPIO chip (RP1 controller)
chip = lgpio.gpiochip_open(0)

# Claim the interrupt pin as input with pull-up
lgpio.gpio_claim_input(chip, INT_PIN)
lgpio.gpio_set_debounce_micros(chip, INT_PIN, 10000)  # 10 ms debounce

# Configure the Pi pin as input with pull-up and alert on falling edge
# lgpio.gpio_claim_alert(chip, INT_PIN, lgpio.FALLING_EDGE, lgpio.SET_PULL_UP)
# lgpio.gpio_claim_alert(chip, INT_PIN, lgpio.FALLING_EDGE)

def handle_interrupt():
    """Read MCP23017 interrupt flags and print changed pins."""
    for pin_flag in mcp.int_flag:
        print(f"Interrupt detected on MCP23017 pin {pin_flag}: value={pins[pin_flag].value}")
    mcp.clear_ints()

# Register the interrupt callback
cb_id = lgpio.callback(chip, INT_PIN, lgpio.FALLING_EDGE, handle_interrupt)


def read_encoder():
    global last_clk
    clk_value = clk.value
    dt_value = dt.value

    if clk_value != last_clk:  # Edge detected
        if dt_value != clk_value:
            print("Rotated → (clockwise)")
        else:
            print("Rotated ← (counterclockwise)")
    last_clk = clk_value

print("KY-040 Rotary Encoder Test via MCP23017 @ 0x20")
print("Rotate or press button (Ctrl+C to exit)\n")

try:
    while True:
        read_encoder()
        # if not sw.value:  # Active low
        #     print("Button pressed!")
        #     time.sleep(0.2)
        time.sleep(0.001)
except KeyboardInterrupt:
    print("\nExiting.")
finally:
    print("Cleaning up.")
    cb_id.cancel()               # Remove callback
    lgpio.gpiochip_close(chip)
