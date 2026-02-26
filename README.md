# Be More Agent

**An animated face display & button controller for HomeAssistant voice satellites, built for Raspberry Pi.**

[![Watch the Demo](https://img.youtube.com/vi/l5ggH-YhuAw/maxresdefault.jpg)](https://youtu.be/l5ggH-YhuAw)

![Python](https://img.shields.io/badge/Python-3.9%2B-blue) ![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi-red) ![License](https://img.shields.io/badge/License-MIT-green)

A dedicated Raspberry Pi shows reactive face animations driven by your HomeAssistant voice assistant pipeline — listening, thinking, speaking, idle — over a WebSocket connection. Physical buttons via an MCP23017 I2C GPIO expander let you control volume, mute, and trigger the voice pipeline without touching a screen.

**It is designed as a blank canvas:** swap the face images to create your own character.

## Features

- **Reactive face animations** — PNG frame sequences that change with the HA voice pipeline state
- **HomeAssistant WebSocket** — auto-reconnecting, bidirectional connection for state events and service calls
- **Physical buttons** — volume up/down/mute, pipeline start/stop via MCP23017 GPIO expander over I2C
- **Hold-repeat** — hold the volume buttons for continuous adjustment (configurable timing)
- **Graceful degradation** — runs without GPIO hardware, without HA, or in debug mode with keyboard controls
- **Systemd service** — starts on boot, auto-restarts on failure
- **Fully configurable** — JSON config for HA connection, button mappings, display settings, and state mapping

## Hardware

### Required

- **Raspberry Pi** (any model with 40-pin header) — Pi 4 or 5 recommended
- **LCD screen** — DSI or HDMI, 800x480 recommended (designed for the [Pimoroni HyperPixel 4.0](https://shop.pimoroni.com/products/hyperpixel-4))
- **Network connection** — to reach your HomeAssistant instance

### Optional (for physical buttons)

The HyperPixel 4.0 consumes all 28 GPIO pins, so buttons connect through an I2C GPIO expander on the HyperPixel's breakout header.

| Qty | Component | Notes |
|-----|-----------|-------|
| 1 | MCP23017 (DIP-28) | I2C GPIO expander, or use a breakout board |
| 10 | 6mm tactile push buttons | 4 for d-pad, 6 standalone (or use a 5-way nav switch for the d-pad) |
| 1 | Half-size breadboard | For prototyping; swap for perfboard once validated |
| ~15 | Jumper wires | For breadboard wiring |
| 1 | 5-pin female Dupont cable (2.54mm) | Connects to the HyperPixel I2C header |

No pull-up resistors needed — the MCP23017's internal pull-ups are enabled in software. No level shifter needed — both the Pi and MCP23017 run at 3.3V.

### Wiring

```
HyperPixel I2C header (back of board)        MCP23017
  3V3  ────────────────────────────────────>  VDD (pin 9)
  GND  ────────────────────────────────────>  VSS (pin 10)
  SDA (BCM 10) ───────────────────────────>  SDA (pin 13)
  SCL (BCM 11) ───────────────────────────>  SCL (pin 12)
  GND  ────────────────────────────────────>  A0, A1, A2 (pins 15-17)  → address 0x20

MCP23017 button pins                          Function
  GPA0 (pin 21) ── button ── GND              D-Pad Up    (volume up, hold-repeat)
  GPA1 (pin 22) ── button ── GND              D-Pad Down  (volume down, hold-repeat)
  GPA2 (pin 23) ── button ── GND              D-Pad Left  (mute)
  GPA3 (pin 24) ── button ── GND              D-Pad Right (unassigned)
  GPA4 (pin 25) ── button ── GND              Btn 1       (pipeline start)
  GPA5 (pin 26) ── button ── GND              Btn 2       (pipeline stop)
  GPA6 (pin 27) ── button ── GND              Btn 3       (unassigned)
  GPA7 (pin 28) ── button ── GND              Btn 4       (unassigned)
  GPB0 (pin 1)  ── button ── GND              Btn 5       (unassigned)
  GPB1 (pin 2)  ── button ── GND              Btn 6       (unassigned)
```

Verify the MCP23017 is detected: `i2cdetect -y 3` — should show `20`.

## Installation

### 1. Clone the repo

```bash
git clone https://github.com/brenpoly/be-more-agent.git
cd be-more-agent
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

`smbus2` is only needed if you're using physical buttons. It will be skipped gracefully on machines without I2C hardware.

### 3. Configure

Copy or edit `face_display_config.json`:

```json
{
    "homeassistant": {
        "url": "homeassistant.local:8123",
        "token": "YOUR_LONG_LIVED_ACCESS_TOKEN",
        "entity_id": "assist_satellite.your_satellite",
        "use_ssl": false
    },
    "display": {
        "faces_dir": "faces",
        "fullscreen": true
    },
    "gpio": {
        "enabled": true,
        "i2c_bus": 3,
        "i2c_address": 32,
        "media_player_entity": "media_player.your_speaker",
        "hold_repeat": {
            "initial_delay_ms": 400,
            "interval_ms": 150
        },
        "buttons": {
            "dpad_up":    {"pin": 0, "action": "volume_up",      "hold_repeat": true},
            "dpad_down":  {"pin": 1, "action": "volume_down",    "hold_repeat": true},
            "dpad_left":  {"pin": 2, "action": "volume_mute"},
            "dpad_right": {"pin": 3, "action": null},
            "btn_1":      {"pin": 4, "action": "pipeline_start"},
            "btn_2":      {"pin": 5, "action": "pipeline_stop"},
            "btn_3":      {"pin": 6, "action": null},
            "btn_4":      {"pin": 7, "action": null},
            "btn_5":      {"pin": 8, "action": null},
            "btn_6":      {"pin": 9, "action": null}
        }
    }
}
```

**Key settings:**
- `homeassistant.token` — generate a long-lived access token in HA under your user profile
- `homeassistant.entity_id` — the `assist_satellite.*` entity for your voice pipeline
- `gpio.media_player_entity` — the media player entity for volume control
- `gpio.enabled` — set to `false` to disable button polling entirely

**Available button actions:** `volume_up`, `volume_down`, `volume_mute`, `pipeline_start`, `pipeline_stop`, or `null` for unassigned.

### 4. Run

```bash
python face_display.py           # Normal mode (connects to HA)
python face_display.py --debug   # Debug mode (keyboard controls, no HA)
```

In debug mode, press number keys 1-7 to cycle through face states.

### 5. Install as a service (optional)

```bash
sudo cp face-display.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now face-display
```

Check status: `sudo systemctl status face-display`

## Project Structure

```
be-more-agent/
├── face_display.py              # Main entry point — Tkinter GUI + orchestration
├── face_display_config.json     # Configuration (HA connection, buttons, display)
├── face-display.service         # systemd unit file
├── requirements.txt             # Python dependencies
├── lib/
│   ├── states.py                # FaceState enum + HA state mapping
│   ├── face_renderer.py         # PNG frame animation engine
│   ├── ha_client.py             # HA WebSocket client (listen + send)
│   └── gpio_buttons.py          # MCP23017 button poller
└── faces/                       # Face animation frames
    ├── idle/                    # PNG sequence for idle state
    ├── listening/               # PNG sequence for listening
    ├── thinking/                # PNG sequence for thinking
    ├── speaking/                # PNG sequence for speaking
    ├── error/                   # PNG sequence for errors
    ├── capturing/               # PNG sequence for camera capture
    └── warmup/                  # PNG sequence for startup
```

### Architecture

Three threads work together:

1. **Main thread** — Tkinter event loop + FaceRenderer animation
2. **HA WebSocket thread** — asyncio loop that listens for state events and sends button commands concurrently
3. **Button poller thread** — reads MCP23017 every 20ms, pushes commands to a shared queue

```
Physical Buttons (10)
        |
  MCP23017 (I2C 0x20, bus 3)
        |
  ButtonPoller            command_queue          HAClient
    polls 20ms        ──────────────────>    _process_commands()
    detects press/release                    ws.send(call_service)
    hold-repeat for vol                            |
                         state_queue               v
  FaceRenderer        <──────────────────    _listen_events()
    animates faces                           ws state_changed
```

## Customizing Your Character

Swap the PNG files in `faces/[state]/` to create your own character. The renderer loops through all `.png` files in each state directory alphabetically:

- **Single frame** — just one PNG, held indefinitely
- **Multiple frames** — cycled at 500ms intervals (speaking uses a bouncing pattern at 100-150ms)

Images are resized to 800x480 to fill the display.

## Troubleshooting

- **No face appears** — check that the `faces/` directory contains PNG files in state subdirectories
- **HA connection fails** — verify your token, URL, and that the entity exists in HA Developer Tools
- **Buttons not working** — run `i2cdetect -y 3` to confirm the MCP23017 is visible at address 0x20
- **"smbus2 not installed"** — expected on dev machines; GPIO buttons are simply skipped
- **Service won't start** — check `journalctl -u face-display -f` for errors; ensure `DISPLAY=:0` is correct

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

## Legal Disclaimer

**"BMO"** and **"Adventure Time"** are trademarks of **Cartoon Network** (Warner Bros. Discovery). This project is a fan creation built for educational and hobbyist purposes only. It is not affiliated with, endorsed by, or connected to Cartoon Network or the official Adventure Time brand. The software is a generic framework; users are responsible for the assets they load into it.
