from enum import Enum


class FaceState(str, Enum):
    """Face display states matching the faces/ directory structure."""
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    ERROR = "error"
    CAPTURING = "capturing"
    WARMUP = "warmup"


# Maps HomeAssistant voice assistant pipeline states to face states.
# Keys are HA entity state strings; values are FaceState values.
DEFAULT_STATE_MAP = {
    "idle": FaceState.IDLE,
    "listening": FaceState.LISTENING,
    "stt": FaceState.LISTENING,
    "processing": FaceState.THINKING,
    "intent": FaceState.THINKING,
    "tts": FaceState.SPEAKING,
    "responding": FaceState.SPEAKING,
    "error": FaceState.ERROR,
    "unavailable": FaceState.ERROR,
    "unknown": FaceState.WARMUP,
}
