"""MCP23017 I2C GPIO expander button poller.

Reads physical buttons via an MCP23017 on the HyperPixel's I2C bus 3
and pushes HA call_service commands to a thread-safe Queue.

Graceful degradation: returns None if smbus2 is unavailable or the
MCP23017 is not detected, allowing the rest of the app to run normally.
"""

import threading
import time
from queue import Queue

# MCP23017 registers
_IODIRA = 0x00   # I/O direction register A
_IODIRB = 0x01   # I/O direction register B
_GPPUA = 0x0C    # Pull-up resistor register A
_GPPUB = 0x0D    # Pull-up resistor register B
_GPIOA = 0x12    # Port register A
_GPIOB = 0x13    # Port register B

POLL_INTERVAL = 0.02  # 20ms

# Predefined action strings -> (domain, service) tuples.
# Target is resolved at runtime from config.
_ACTION_TABLE = {
    "volume_up":      ("media_player", "volume_up"),
    "volume_down":    ("media_player", "volume_down"),
    "volume_mute":    ("media_player", "volume_mute"),
    "pipeline_start": ("assist_satellite", "start_listening"),
    "pipeline_stop":  ("homeassistant", "turn_off"),
}


def _build_command(action: str, gpio_cfg: dict) -> dict | None:
    """Resolve an action string to an HA call_service command dict."""
    if action not in _ACTION_TABLE:
        return None
    domain, service = _ACTION_TABLE[action]

    if domain == "media_player":
        entity = gpio_cfg.get("media_player_entity", "")
    else:
        # pipeline actions target the main HA entity
        entity = gpio_cfg.get("ha_entity_id", "")

    if not entity:
        return None

    return {"domain": domain, "service": service, "target": {"entity_id": entity}}


class ButtonPoller:
    """Polls an MCP23017 for button presses and pushes commands to a queue."""

    def __init__(self, bus, address: int, gpio_cfg: dict, command_queue: Queue):
        self._bus = bus
        self._address = address
        self._command_queue = command_queue
        self._gpio_cfg = gpio_cfg

        hold = gpio_cfg.get("hold_repeat", {})
        self._initial_delay = hold.get("initial_delay_ms", 400) / 1000.0
        self._repeat_interval = hold.get("interval_ms", 150) / 1000.0

        # Parse button config: pin -> (action_string, hold_repeat_bool, command_dict)
        self._buttons: dict[int, tuple[str, bool, dict | None]] = {}
        for _name, btn_cfg in gpio_cfg.get("buttons", {}).items():
            pin = btn_cfg.get("pin")
            action = btn_cfg.get("action")
            if pin is None or action is None:
                continue
            cmd = _build_command(action, gpio_cfg)
            hold_repeat = btn_cfg.get("hold_repeat", False)
            self._buttons[pin] = (action, hold_repeat, cmd)

        # Track previous pin states (16-bit, 1=released, 0=pressed)
        self._prev_state = 0xFFFF
        # Active hold-repeat timers keyed by pin
        self._repeat_timers: dict[int, threading.Timer] = {}

        # Configure MCP23017: all pins as inputs with pull-ups
        self._bus.write_byte_data(self._address, _IODIRA, 0xFF)
        self._bus.write_byte_data(self._address, _IODIRB, 0xFF)
        self._bus.write_byte_data(self._address, _GPPUA, 0xFF)
        self._bus.write_byte_data(self._address, _GPPUB, 0xFF)

        print(f"[GPIO] MCP23017 initialized at 0x{address:02X}, {len(self._buttons)} buttons configured", flush=True)

    def _read_pins(self) -> int:
        """Read 16-bit pin state from GPIOA and GPIOB."""
        a = self._bus.read_byte_data(self._address, _GPIOA)
        b = self._bus.read_byte_data(self._address, _GPIOB)
        return (b << 8) | a

    def _send_command(self, pin: int):
        """Push the command for a pin to the queue."""
        _, _, cmd = self._buttons[pin]
        if cmd:
            self._command_queue.put(dict(cmd))  # copy to avoid mutation

    def _start_repeat(self, pin: int):
        """Start hold-repeat: initial delay, then periodic repeats."""
        def repeat():
            self._send_command(pin)
            # Schedule next repeat
            t = threading.Timer(self._repeat_interval, repeat)
            t.daemon = True
            self._repeat_timers[pin] = t
            t.start()

        t = threading.Timer(self._initial_delay, repeat)
        t.daemon = True
        self._repeat_timers[pin] = t
        t.start()

    def _stop_repeat(self, pin: int):
        """Cancel any active hold-repeat timer for a pin."""
        timer = self._repeat_timers.pop(pin, None)
        if timer:
            timer.cancel()

    def _poll_once(self):
        """Read pins, detect transitions, fire actions."""
        current = self._read_pins()
        changed = current ^ self._prev_state

        for pin, (action, hold_repeat, cmd) in self._buttons.items():
            bit = 1 << pin
            if not (changed & bit):
                continue

            pressed = not (current & bit)  # active-low
            if pressed:
                print(f"[GPIO] Button press: pin {pin} ({action})", flush=True)
                self._send_command(pin)
                if hold_repeat:
                    self._start_repeat(pin)
            else:
                print(f"[GPIO] Button release: pin {pin} ({action})", flush=True)
                self._stop_repeat(pin)

        self._prev_state = current

    def run(self):
        """Polling loop — intended to run in a daemon thread."""
        print("[GPIO] Button poller started", flush=True)
        while True:
            try:
                self._poll_once()
            except OSError as e:
                print(f"[GPIO] I2C read error: {e}", flush=True)
                time.sleep(1)  # back off on I2C errors
                continue
            time.sleep(POLL_INTERVAL)


def create_button_poller(config: dict, command_queue: Queue) -> ButtonPoller | None:
    """Factory: create and start a ButtonPoller if hardware is available.

    Returns the poller instance (to prevent GC) or None if unavailable.
    """
    gpio_cfg = config.get("gpio", {})
    if not gpio_cfg.get("enabled", False):
        print("[GPIO] Buttons disabled in config", flush=True)
        return None

    try:
        import smbus2
    except ImportError:
        print("[GPIO] smbus2 not installed — GPIO buttons unavailable", flush=True)
        return None

    bus_num = gpio_cfg.get("i2c_bus", 3)
    address = gpio_cfg.get("i2c_address", 0x20)

    try:
        bus = smbus2.SMBus(bus_num)
    except FileNotFoundError:
        print(f"[GPIO] I2C bus {bus_num} not found — GPIO buttons unavailable", flush=True)
        return None

    # Probe the MCP23017
    try:
        bus.read_byte_data(address, _IODIRA)
    except OSError:
        print(f"[GPIO] No MCP23017 at 0x{address:02X} on bus {bus_num}", flush=True)
        bus.close()
        return None

    # Resolve ha_entity_id from main config for pipeline actions
    ha_entity = config.get("homeassistant", {}).get("entity_id", "")
    gpio_cfg_with_entity = {**gpio_cfg, "ha_entity_id": ha_entity}

    poller = ButtonPoller(bus, address, gpio_cfg_with_entity, command_queue)

    thread = threading.Thread(target=poller.run, daemon=True)
    thread.start()

    return poller
