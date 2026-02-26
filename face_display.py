#!/usr/bin/env python3
"""
Face Display for HomeAssistant

Standalone face display client for a dedicated Raspberry Pi.
Connects to HomeAssistant via WebSocket and shows animated faces
based on the HA Voice Assistant pipeline state.

Usage:
    python face_display.py             # Normal mode (connects to HA)
    python face_display.py --debug     # Debug mode (keyboard state switching, no HA)
"""

import argparse
import json
import os
import sys
import threading
import tkinter as tk
from queue import Queue

from lib.states import FaceState, DEFAULT_STATE_MAP
from lib.face_renderer import FaceRenderer

CONFIG_FILE = "face_display_config.json"


def load_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        print(f"[CONFIG] No {CONFIG_FILE} found, using defaults.", flush=True)
        return {}
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)


def build_state_map(config: dict) -> dict[str, FaceState]:
    """Build state map from config, falling back to defaults."""
    custom = config.get("state_map", {})
    if not custom:
        return DEFAULT_STATE_MAP

    result = {}
    for ha_state, face_state_str in custom.items():
        try:
            result[ha_state] = FaceState(face_state_str)
        except ValueError:
            print(f"[CONFIG] Unknown face state '{face_state_str}' for HA state '{ha_state}', skipping", flush=True)
    return result


def bind_debug_keys(root: tk.Tk, state_queue: Queue):
    """Bind number keys 1-7 to cycle through face states for testing."""
    states = list(FaceState)
    print("[DEBUG] Keyboard controls:", flush=True)
    for i, state in enumerate(states):
        print(f"  {i + 1} = {state.value}", flush=True)

    def on_key(event):
        try:
            idx = int(event.char) - 1
            if 0 <= idx < len(states):
                state_queue.put(states[idx])
        except (ValueError, IndexError):
            pass

    root.bind("<Key>", on_key)


def main():
    parser = argparse.ArgumentParser(description="Face Display for HomeAssistant")
    parser.add_argument("--debug", action="store_true", help="Debug mode: keyboard state switching, no HA connection")
    args = parser.parse_args()

    config = load_config()
    display_cfg = config.get("display", {})
    faces_dir = display_cfg.get("faces_dir", "faces")
    fullscreen = display_cfg.get("fullscreen", True)

    state_queue = Queue()
    command_queue = Queue()

    # --- Tkinter setup ---
    root = tk.Tk()
    root.title("Face Display")
    root.configure(bg="black")

    if fullscreen:
        root.attributes("-fullscreen", True)
    else:
        root.geometry(f"{FaceRenderer.WIDTH}x{FaceRenderer.HEIGHT}")

    root.bind("<Escape>", lambda e: root.destroy())

    renderer = FaceRenderer(root, state_queue, faces_dir=faces_dir)

    if args.debug:
        bind_debug_keys(root, state_queue)
        state_queue.put(FaceState.IDLE)
        print("[MODE] Debug — use number keys to switch states", flush=True)
    else:
        ha_cfg = config.get("homeassistant", {})
        if not ha_cfg.get("token"):
            print(f"[ERROR] No HomeAssistant token configured in {CONFIG_FILE}", flush=True)
            print("  Run with --debug for standalone testing, or configure homeassistant.token", flush=True)
            state_queue.put(FaceState.ERROR)
        else:
            from lib.ha_client import HAClient

            state_map = build_state_map(config)
            client = HAClient(
                url=ha_cfg.get("url", "homeassistant.local:8123"),
                token=ha_cfg["token"],
                entity_id=ha_cfg.get("entity_id", ""),
                use_ssl=ha_cfg.get("use_ssl", False),
                state_queue=state_queue,
                state_map=state_map,
                command_queue=command_queue,
            )
            client_thread = threading.Thread(target=client.run, daemon=True)
            client_thread.start()

            # Start GPIO button poller (gracefully skips if hardware unavailable)
            from lib.gpio_buttons import create_button_poller
            button_poller = create_button_poller(config, command_queue)  # noqa: F841

    root.mainloop()


if __name__ == "__main__":
    main()
