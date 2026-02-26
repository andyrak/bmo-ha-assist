"""HomeAssistant WebSocket client with auto-reconnect and command sending."""

import asyncio
import json
from queue import Queue

import websockets

from lib.states import FaceState, DEFAULT_STATE_MAP

RECONNECT_DELAY = 5  # seconds


class HAClient:
    """Connects to HA via WebSocket, subscribes to entity state changes,
    pushes FaceState updates to a thread-safe Queue, and sends commands
    from an optional command_queue."""

    def __init__(
        self,
        url: str,
        token: str,
        entity_id: str,
        use_ssl: bool,
        state_queue: Queue,
        state_map: dict[str, FaceState] | None = None,
        command_queue: Queue | None = None,
    ):
        scheme = "wss" if use_ssl else "ws"
        # Strip any existing scheme from the url
        clean_url = url.replace("ws://", "").replace("wss://", "").replace("http://", "").replace("https://", "")
        self.ws_url = f"{scheme}://{clean_url}/api/websocket"
        self.token = token
        self.entity_id = entity_id
        self.state_queue = state_queue
        self.state_map = state_map or DEFAULT_STATE_MAP
        self.command_queue = command_queue
        self._msg_id = 0

    def _next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    def _map_state(self, ha_state: str) -> FaceState:
        """Convert an HA state string to a FaceState."""
        return self.state_map.get(ha_state, FaceState.IDLE)

    def run(self):
        """Entry point for the daemon thread — runs the asyncio event loop."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._connect_loop())

    async def _connect_loop(self):
        """Reconnect loop — retries on any failure."""
        while True:
            try:
                await self._connect()
            except Exception as e:
                print(f"[HA] Connection lost: {e}", flush=True)
                self.state_queue.put(FaceState.ERROR)
            print(f"[HA] Reconnecting in {RECONNECT_DELAY}s...", flush=True)
            await asyncio.sleep(RECONNECT_DELAY)
            self._msg_id = 0

    async def _connect(self):
        """Single connection lifecycle: auth -> fetch state -> subscribe -> listen + send."""
        print(f"[HA] Connecting to {self.ws_url}", flush=True)

        async with websockets.connect(self.ws_url) as ws:
            await self._authenticate(ws)

            if self.entity_id:
                await self._fetch_current_state(ws)

            await self._subscribe_events(ws)

            # Run listen and (optionally) command sender concurrently
            tasks = [asyncio.ensure_future(self._listen_events(ws))]
            if self.command_queue is not None:
                tasks.append(asyncio.ensure_future(self._process_commands(ws)))

            # If either task exits (e.g. connection drops), cancel the other
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
            for t in pending:
                t.cancel()
            # Re-raise any exception so _connect_loop handles reconnection
            for t in done:
                t.result()

    async def _authenticate(self, ws):
        """Handle auth_required -> auth -> auth_ok handshake."""
        msg = json.loads(await ws.recv())
        if msg.get("type") != "auth_required":
            raise ConnectionError(f"Expected auth_required, got: {msg.get('type')}")

        await ws.send(json.dumps({"type": "auth", "access_token": self.token}))
        msg = json.loads(await ws.recv())
        if msg.get("type") != "auth_ok":
            raise PermissionError(f"Authentication failed: {msg.get('message', 'unknown')}")
        print("[HA] Authenticated", flush=True)

    async def _subscribe_events(self, ws):
        """Subscribe to state_changed events."""
        sub_id = self._next_id()
        await ws.send(json.dumps({
            "id": sub_id,
            "type": "subscribe_events",
            "event_type": "state_changed",
        }))
        msg = json.loads(await ws.recv())
        if not msg.get("success"):
            print(f"[HA] Subscribe failed: {msg}", flush=True)
        else:
            print("[HA] Subscribed to state_changed events", flush=True)

    async def _listen_events(self, ws):
        """Listen for state_changed events and push FaceState updates."""
        async for raw in ws:
            msg = json.loads(raw)
            if msg.get("type") != "event":
                continue
            event_data = msg.get("event", {}).get("data", {})
            entity = event_data.get("entity_id", "")
            if entity != self.entity_id:
                continue

            new_state_str = event_data.get("new_state", {}).get("state", "")
            face_state = self._map_state(new_state_str)
            print(f"[HA] {entity}: {new_state_str} -> {face_state.value}", flush=True)
            self.state_queue.put(face_state)

    async def _process_commands(self, ws):
        """Read commands from command_queue and send as call_service messages."""
        loop = asyncio.get_event_loop()
        while True:
            # Block in executor so we don't stall the event loop
            cmd = await loop.run_in_executor(None, self.command_queue.get)
            msg_id = self._next_id()
            payload = {
                "id": msg_id,
                "type": "call_service",
                "domain": cmd["domain"],
                "service": cmd["service"],
                "target": cmd.get("target", {}),
            }
            if "service_data" in cmd:
                payload["service_data"] = cmd["service_data"]
            try:
                await ws.send(json.dumps(payload))
                print(f"[HA] Sent: {cmd['domain']}.{cmd['service']} (id={msg_id})", flush=True)
            except Exception as e:
                print(f"[HA] Failed to send command: {e}", flush=True)
                raise

    async def _fetch_current_state(self, ws):
        """Get the current state of the entity on connect."""
        get_id = self._next_id()
        await ws.send(json.dumps({"id": get_id, "type": "get_states"}))
        msg = json.loads(await ws.recv())

        if msg.get("success") and msg.get("result"):
            for entity in msg["result"]:
                if entity.get("entity_id") == self.entity_id:
                    state_str = entity.get("state", "")
                    face_state = self._map_state(state_str)
                    print(f"[HA] Initial state: {state_str} -> {face_state.value}", flush=True)
                    self.state_queue.put(face_state)
                    return
            print(f"[HA] Entity '{self.entity_id}' not found in HA states", flush=True)
            self.state_queue.put(FaceState.IDLE)
