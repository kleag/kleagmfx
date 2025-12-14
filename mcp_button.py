#!/usr/bin/env python3
from adafruit_mcp230xx.mcp23017 import MCP23017
from digitalio import Direction, Pull

class MCPButton:
    """ MCP23017 Button """
    def __init__(self, mcp: MCP23017, pin: int):
        self.pin = mcp.get_pin(pin)
        self.pin.direction = Direction.INPUT
        self.pin.pull = Pull.UP
        self.last_state = not self.pin.value # Active Low
        self.when_pressed = None

    def check(self, idx: int):
        current_state = not self.pin.value
        if current_state and not self.last_state:
            if self.when_pressed:
                self.when_pressed(idx)
        self.last_state = current_state

