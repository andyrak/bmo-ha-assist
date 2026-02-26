import os
import random
import tkinter as tk
from queue import Queue, Empty

from PIL import Image, ImageTk

from lib.states import FaceState

# Animation timing constants
SPEAKING_INTERVAL_MIN = 100   # ms
SPEAKING_INTERVAL_MAX = 150   # ms
CYCLE_INTERVAL = 500          # ms for multi-frame non-speaking states
TICK_INTERVAL = 50            # ms for queue drain polling


class FaceRenderer:
    """Loads face PNGs and animates them based on state changes from a queue."""

    WIDTH, HEIGHT = 800, 480

    def __init__(self, master: tk.Tk, state_queue: Queue, faces_dir: str = "faces"):
        self.master = master
        self.state_queue = state_queue
        self.faces_dir = faces_dir

        self.current_state = FaceState.WARMUP
        self.animations: dict[str, list[ImageTk.PhotoImage]] = {}
        self.frame_index = 0
        self.bounce_direction = 1  # 1 = forward, -1 = backward (for speaking)

        self.label = tk.Label(master, bg="black")
        self.label.place(x=0, y=0, width=self.WIDTH, height=self.HEIGHT)

        self._load_animations()
        self._show_frame()
        self._tick()
        self._schedule_animation()

    def _load_animations(self):
        """Load PNG sequences from faces/ subdirectories."""
        for state in FaceState:
            folder = os.path.join(self.faces_dir, state.value)
            self.animations[state.value] = []
            if os.path.isdir(folder):
                files = sorted(f for f in os.listdir(folder) if f.lower().endswith(".png"))
                for f in files:
                    img = Image.open(os.path.join(folder, f)).resize(
                        (self.WIDTH, self.HEIGHT), Image.LANCZOS
                    )
                    self.animations[state.value].append(ImageTk.PhotoImage(img))

            # Blue fallback if no frames found
            if not self.animations[state.value]:
                blank = Image.new("RGB", (self.WIDTH, self.HEIGHT), color="#0000FF")
                self.animations[state.value].append(ImageTk.PhotoImage(blank))

        count = sum(len(v) for v in self.animations.values())
        print(f"[FACE] Loaded {count} frames across {len(self.animations)} states", flush=True)

    def _show_frame(self):
        """Display the current frame."""
        frames = self.animations.get(self.current_state.value, [])
        if frames:
            idx = self.frame_index % len(frames)
            self.label.config(image=frames[idx])

    def _tick(self):
        """Drain the state queue and apply any new state."""
        new_state = None
        try:
            while True:
                new_state = self.state_queue.get_nowait()
        except Empty:
            pass

        if new_state is not None and new_state != self.current_state:
            print(f"[FACE] State: {self.current_state.value} -> {new_state.value}", flush=True)
            self.current_state = new_state
            self.frame_index = 0
            self.bounce_direction = 1
            self._show_frame()

        self.master.after(TICK_INTERVAL, self._tick)

    def _schedule_animation(self):
        """Advance the animation frame and schedule the next one."""
        frames = self.animations.get(self.current_state.value, [])
        num_frames = len(frames)

        if num_frames <= 1:
            # Single-frame state — just check back later
            self.master.after(CYCLE_INTERVAL, self._schedule_animation)
            return

        if self.current_state == FaceState.SPEAKING:
            # Bounce pattern: 0->1->2->1->0->1->2...
            self.frame_index += self.bounce_direction
            if self.frame_index >= num_frames - 1:
                self.bounce_direction = -1
            elif self.frame_index <= 0:
                self.bounce_direction = 1
            interval = random.randint(SPEAKING_INTERVAL_MIN, SPEAKING_INTERVAL_MAX)
        else:
            # Sequential cycle for listening, thinking
            self.frame_index = (self.frame_index + 1) % num_frames
            interval = CYCLE_INTERVAL

        self._show_frame()
        self.master.after(interval, self._schedule_animation)

    def set_state(self, state: FaceState):
        """Thread-safe state change via the queue."""
        self.state_queue.put(state)
