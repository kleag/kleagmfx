#!/usr/bin/env python3
import time
from adafruit_ads1x15.analog_in import AnalogIn
import adafruit_ads1x15.ads1115 as ADS
from board import SCL, SDA
import busio

# Create I2C bus
i2c = busio.I2C(SCL, SDA)

# Create the ADS1115 ADC object
ads = ADS.ADS1115(i2c)
#ads.gain = 1  # +/-4.096V input range

# Create channels for X and Y
x_axis = AnalogIn(ads, ADS.P0)
y_axis = AnalogIn(ads, ADS.P1)

def read_joystick():
    """Return normalized X, Y values in range -1.0 .. +1.0"""
    # Joystick gives ~0V to ~3.3V, midpoint around 1.65V
    x_center = 1.65
    y_center = 1.65
    x = (x_axis.voltage - x_center) / x_center
    y = (y_axis.voltage - y_center) / y_center
    return max(-1, min(1, x)), max(-1, min(1, y))

try:
    print("Reading joystick values. Press Ctrl+C to stop.")
    while True:
        x, y = read_joystick()
        print(f"X: {x_axis.voltage:.3f} V ({x:+.2f}), Y: {y_axis.voltage:.3f} V ({y:+.2f})")
        time.sleep(0.1)
except KeyboardInterrupt:
    print("\nExiting cleanly.")

