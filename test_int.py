#!/usr/bin/env python3
import time
import sys
import lgpio
import smbus2

# =========================================================
# MCP23017 REGISTER MAP
# =========================================================
IODIRA   = 0x00
IODIRB   = 0x01
IPOLA    = 0x02
IPOLB    = 0x03
GPINTENA = 0x04
GPINTENB = 0x05
DEFVALA  = 0x06
DEFVALB  = 0x07
INTCONA  = 0x08
INTCONB  = 0x09
IOCON    = 0x0A
GPPUA    = 0x0C
GPPUB    = 0x0D
INTFA    = 0x0E
INTFB    = 0x0F
INTCAPA  = 0x10
INTCAPB  = 0x11
GPIOA    = 0x12
GPIOB    = 0x13
OLATA    = 0x14
OLATB    = 0x15


# =========================================================
# MCP23017 CLASS (direct SMBus control)
# =========================================================
class MCP23017:
    def __init__(self, bus: smbus2.SMBus, address=0x20):
        print(f"MCP23017 {bus}, {address}", file=sys.stderr)
        self.bus = bus
        self.addr = address
        self.init_device()

    def write(self, reg, val):
        print(f"MCP23017.write {reg}, {val}", file=sys.stderr)
        self.bus.write_byte_data(self.addr, reg, val)

    def read(self, reg):
        print(f"MCP23017.read {reg}", file=sys.stderr)
        return self.bus.read_byte_data(self.addr, reg)

    def init_device(self):
        print(f"MCP23017.init_device", file=sys.stderr)
        """Configure all pins as input with pull-ups, mirror interrupts."""
        # IOCON: Mirror INTA/B, open-drain, active-low
        # self.write(IOCON, 0b01001000)
        self.write(IOCON, 0b01000100)
        # self.write(IOCON, 0b01000000)

        # All inputs by default
        self.write(IODIRA, 0xFF)
        self.write(IODIRB, 0xFF)

        # Enable pull-ups
        self.write(GPPUA, 0xFF)
        self.write(GPPUB, 0xFF)

        # Disable interrupts by default
        self.write(GPINTENA, 0x00)
        self.write(GPINTENB, 0x00)

    def set_pin_mode(self, pin, is_output):
        print(f"MCP23017.set_pin_mode {pin}, {is_output}", file=sys.stderr)
        reg = IODIRA if pin < 8 else IODIRB
        bit = pin % 8
        val = self.read(reg)
        if is_output:
            val &= ~(1 << bit)
        else:
            val |= (1 << bit)
        self.write(reg, val)

    def digital_write(self, pin, state):
        print(f"MCP23017.digital_write {pin}, {state}", file=sys.stderr)
        reg = OLATA if pin < 8 else OLATB
        bit = pin % 8
        val = self.read(reg)
        if state:
            val |= (1 << bit)
        else:
            val &= ~(1 << bit)
        self.write(reg, val)

    def digital_read(self, pin):
        print(f"MCP23017.digital_read {pin}", file=sys.stderr)
        reg = GPIOA if pin < 8 else GPIOB
        bit = pin % 8
        val = self.read(reg)
        return bool(val & (1 << bit))

    def enable_interrupt(self, pin):
        print(f"MCP23017.enable_interrupt {pin}", file=sys.stderr)
        reg = GPINTENA if pin < 8 else GPINTENB
        bit = pin % 8
        val = self.read(reg)
        val |= (1 << bit)
        self.write(reg, val)

    def clear_interrupts(self):
        print(f"MCP23017.clear_interrupts", file=sys.stderr)
        # Reading INTCAP clears interrupts
        self.read(INTCAPA)
        self.read(INTCAPB)


def update_leds():
    """Read all buttons and set LEDs accordingly."""
    # Map: B5<-B6, B4<-B7, A4<-A6, A5<-A7
    print(f"update_leds", file=sys.stderr)
    pairs = [(13, 14), (12, 15), (4, 6), (5, 7)]
    for led, btn in pairs:
        val = not mcp.digital_read(btn)  # buttons are active-low
        mcp.digital_write(led, val)

def mcp_callback(chip, gpio, level, timestamp):
    print(f"mcp_callback {chip}, {gpio}, {level}, {timestamp}", file=sys.stderr)
    mcp.clear_interrupts()
    update_leds()

def setup_interrupts():
    print(f"setup_interrupts", file=sys.stderr)
    MCP1_ITA = 27 # Pisound 9
    MCP1_ITB = 22 # Pisound 7
    MCP2_ITA = 7  # Pisound 3
    MCP2_ITB = 5  # Pisound 5
    INT_PINS = [MCP1_ITA, MCP1_ITB, MCP2_ITA, MCP2_ITB]

    # Setup interrupt line from MCP to Raspberry Pi GPIO22
    CHIP = 0
    for INT_PIN in INT_PINS:
        h = lgpio.gpiochip_open(CHIP)
        if lgpio.gpio_claim_input(h, INT_PIN, 2) < 0:
            print(f"Failed to claim GPIO{INT_PIN} for interrupt")
            sys.exit(1)
        lgpio.callback(h, INT_PIN, lgpio.FALLING_EDGE, mcp_callback)

# =========================================================
# MAIN TEST PROGRAM
# =========================================================
def main():
    bus = smbus2.SMBus(1)
    mcp = MCP23017(bus, address=0x20)

    # Configure LEDs (outputs)
    LEDS = [11, 12, 13, 4, 5]  # B3, B4, B5, A4, A5
    for pin in LEDS:
        mcp.set_pin_mode(pin, is_output=True)

    # Configure buttons (inputs + interrupts)
    BUTTONS = [14, 15, 6, 7]  # B6, B7, A6, A7
    for pin in BUTTONS:
        mcp.set_pin_mode(pin, is_output=False)
        mcp.enable_interrupt(pin)
    # Clear any pending
    mcp.clear_interrupts()

    setup_interrupts()
    mcp.clear_interrupts()

    print("Interrupt-based MCP23017 LED/Button test running. Ctrl+C to stop.")
    # Blink LED B3
    blink_led = 11
    try:
        state = False
        while True:
            # state = not state
            # mcp.digital_write(blink_led, state)
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        for led in LEDS:
            mcp.digital_write(led, 0)
        lgpio.gpiochip_close(0)
        bus.close()
        print("All LEDs off. Goodbye!")


if __name__ == "__main__":
    main()

