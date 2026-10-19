# Display brightness schedule

Time-of-day backlight control for the **QDtech MPI5006** 5" 1024×600 HDMI display (USB ID `0484:5750`, shows up in `lsusb` as "Specialix MPI5001").

The panel doesn't support DDC/CI, so `ddcutil` can't reach it (`DDC communication failed`). Its controller does take brightness commands over the USB-C cable that carries touch, which is what this uses. That changes the real backlight, not just the image.

## Install

From the repo on the Pi:

```bash
sudo sh brightness/install.sh
```

This installs `/usr/local/bin/bmo-brightness` plus `bmo-brightness.service` and `bmo-brightness.timer`. The timer applies the schedule every 5 minutes and 30 seconds after boot.

## Usage

```bash
sudo bmo-brightness 40        # set 40%
sudo bmo-brightness auto      # apply the schedule for the current time
bmo-brightness now            # print the scheduled value, change nothing
sudo bmo-brightness --raw N   # raw controller level 0–90 (see below)
```

Writing needs root, or write access to the display's `/dev/hidraw*` node. The script finds the node itself by USB ID, so it doesn't matter which `hidrawN` the display lands on.

## Schedule

Edit `SCHEDULE` at the top of `brightness/bmo-brightness`, then re-run `sudo sh brightness/install.sh`.

```python
SCHEDULE = [
    ("06:30", 5),
    ("08:00", 100),
    ("19:00", 100),
    ("21:30", 30),
    ("23:00", 5),
]
```

Brightness ramps linearly between points and wraps around midnight, so two neighbouring points with the same value hold flat. With the defaults it holds 5% overnight, rises to 100% from 06:30 to 08:00, holds through the day, and fades back down from 19:00 to 23:00.

Times are the Pi's local time, so check `timedatectl` shows the right time zone.

## Protocol

Recovered from the vendor's Windows tool (`LCD-USB-BRIGHTNESS-Windows-V1.0`, a Go/Fyne app using hidapi):

- The display has one HID interface. Report 1 is the touchscreen; report 4 is a vendor-defined collection (usage page `0xFF00`) with a 63-byte input and a 63-byte output report.
- To set brightness, write **output report 4**: `04 aa 01 00 00 00 VV`, zero-padded to 64 bytes.
- `VV = int(percent / 100 * 90)`, with percent clamped to 5–100, so `VV` runs from `0x04` to `0x5a`.
- The vendor tool sends nothing else: no read-back and no separate power command.

`--raw` sends `VV` directly (0–90) so you can try levels below the vendor's 5% floor. Levels 0–3 haven't been tested; if one turns the backlight fully off, `sudo bmo-brightness 100` brings it back.

Quick test without installing anything (sets about 22%):

```bash
sudo python3 -c "import os;f=os.open('/dev/hidraw0',os.O_WRONLY);os.write(f,bytes([4,0xaa,1,0,0,0,20]).ljust(64,bytes(1)))"
```

## Troubleshooting

- **`display 0484:5750 not found`**: check `lsusb`. The display's USB-C cable must be plugged into the Pi and must carry data, not just power.
- **Timer status**: `systemctl list-timers bmo-brightness.timer`, and `journalctl -u bmo-brightness` for errors from each run.
- **Brightness looks wrong for the time**: run `bmo-brightness now` and compare with `date`.
