ADS1115
MCP23017
https://github.com/adafruit/Adafruit-MCP23017-Arduino-Library#pin-addressing

KY-040
n°4 on MCP@0x20
    - sw pin B1 (9)
    - but on A0, B0 (0, 8)

Pisound
Raspberry Pi 5 (4 should be OK)

Joystick: ADS.P0, ADS.P1
sudo apt install python3-uinput
sudo nano /etc/modules
uinput

sudo nano /etc/udev/rules.d/99-uinput.rules
KERNEL=="uinput", SUBSYSTEM=="misc", MODE="0660", GROUP="input"
sudo usermod -a -G input $USER


```
sudo raspi-config
```

Then go to:
`Interface Options → I2C → Enable → Reboot the Pi.`

```bash
sudo apt install -y i2c-tools
```

```bash
sudo i2cdetect -y 1
```

`/home/gael/.config/systemd/user/multieffect.service`
`/home/gael/.config/systemd/user/default.target.wants/multieffect.service -> /home/gael/.config/systemd/user/multieffect.service`

```ini
[Unit]
Description=Start Guitar Multi-Effect Python Script
After=graphical-session.target

[Service]
ExecStart=python /home/gael/multieffects/multieffect.py
WorkingDirectory=/home/gael
Restart=on-failure


[Install]
WantedBy=default.target
```

```bash
journalctl --user-unit multieffect.service
systemctl --user disable multieffect.service
systemctl --user enable multieffect.service
systemctl --user stop multieffect.service
systemctl --user start multieffect.service
```
