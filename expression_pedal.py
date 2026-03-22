#!/usr/bin/env python3
import adafruit_ads1x15.ads1115 as ADS
import board
import busio
import logging
import threading
import time

from adafruit_ads1x15.analog_in import AnalogIn
from signal import pause


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)


class ExpressionPedal:
    def __init__(self, i2c: busio.I2C, ads: ADS.ADS1115, channel=ADS.P2, gain=1, v_ref=3.3):
        # --- HARDWARE INITIALIZATION ---
        self.i2c = i2c
        self.ads = ads
        self.chan = AnalogIn(self.ads, channel)

        # 2. Configuration
        self.v_ref = v_ref
        self.ads.gain = gain  # Gain 1 = +/- 4.096V

        # 3. Data Storage
        self._current_value = 0.0  # Percentage 0.0 - 100.0
        self._running = False
        self._thread = None

        # Smoothing settings
        self.window_size = 5
        self.readings = [0] * self.window_size

    def poll(self):
        """Internal method to be run in a separate thread."""
        while self._running:
            # Calculate voltage and map to percentage
            voltage = self.chan.voltage
            raw_percent = (voltage / self.v_ref) * 100

            # Clamp and smooth
            clamped = max(0, min(100, raw_percent))

            # Simple Moving Average (SMA) logic
            self.readings.pop(0)
            self.readings.append(clamped)
            self._current_value = sum(self.readings) / self.window_size
            logger.debug(f"Pedal: {self._current_value}")
            # Polling rate (100Hz is usually plenty for expression pedals)
            time.sleep(0.01)

# === Main ===
if __name__ == "__main__":
        # --- HARDWARE INITIALIZATION ---
    i2c = busio.I2C(board.SCL, board.SDA)

    # ADS1115 for ExpressionPedal (kept as requested)
    ads = ADS.ADS1115(i2c)

    pedal = ExpressionPedal(i2c, ads)
    threading.Thread(target=pedal.poll, daemon=True).start()

    logger.info("ExpressionPedal daemon running.")
    pause()
