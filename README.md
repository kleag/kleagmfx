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
