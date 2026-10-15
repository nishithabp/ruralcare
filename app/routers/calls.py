"""Doctor-patient audio/video calls: ringing + WebRTC signalling over one WebSocket.

Connect:  ws://host/ws?token=<JWT>            (doctors keep this open to receive calls)

Client -> server                                  Server -> client
  {"type":"ring","doctor_id":2,"mode":"video"}      {"type":"ringing","call_id":9}            (to the caller)
  {"type":"accept"} / {"type":"decline"}            {"type":"ring","call_id":9,"from":{...},"mode":"video"}   (to the doctor)
  {"type":"cancel"} / {"type":"end"}                {"type":"accept"|"decline"|"cancel"|"end"|"missed"|"busy"|"unavailable"}
  {"type":"offer"|"answer"|"ice","data":{...}}      the same offer/answer/ice, relayed to the other person
The media itself flows peer-to-peer (WebRTC); get STUN/TURN servers from GET /calls/ice-servers.
"""
import asyncio
from dataclasses import dataclass, field

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from ..config import get_settings
from ..database import SessionLocal
from ..deps import current_user
from ..models import Consultation, User, utcnow
from ..security import decode_token

router = APIRouter(tags=["calls"])
RELAY = {"offer", "answer", "ice"}


@dataclass
class Call:
    id: int
    patient_id: int
    doctor_id: int
    mode: str
    state: str = "ringing"          # ringing | connected
    timer: asyncio.Task | None = field(default=None, repr=False)

    def peer_of(self, uid: int) -> int:
        return self.doctor_id if uid == self.patient_id else self.patient_id


class CallHub:
    def __init__(self) -> None:
        self.sockets: dict[int, WebSocket] = {}
        self.calls: dict[int, Call] = {}       # call id -> call
        self.active: dict[int, int] = {}       # user id -> call id

    async def send(self, uid: int, msg: dict) -> None:
        ws = self.sockets.get(uid)
        if ws:
            try:
                await ws.send_json(msg)
            except Exception:
                pass

    def _set_status(self, call_id: int, status: str, started: bool = False, ended: bool = False) -> None:
        with SessionLocal() as db:
            c = db.get(Consultation, call_id)
            if c:
                c.status = status
                if started:
                    c.started_at = utcnow()
                if ended:
                    c.ended_at = utcnow()
                db.commit()

    async def ring(self, user: dict, msg: dict) -> None:
        if user["role"] != "patient":
            return await self.send(user["id"], {"type": "error", "error": "only_patients_can_call"})
        doctor_id, mode = msg.get("doctor_id"), msg.get("mode", "audio")
        if mode not in ("audio", "video") or not isinstance(doctor_id, int):
            return await self.send(user["id"], {"type": "error", "error": "bad_request"})
        with SessionLocal() as db:
            doc = db.get(User, doctor_id)
            if not doc or doc.role != "doctor":
                return await self.send(user["id"], {"type": "error", "error": "doctor_not_found"})
            if doctor_id not in self.sockets:
                return await self.send(user["id"], {"type": "unavailable"})
            if user["id"] in self.active or doctor_id in self.active:
                return await self.send(user["id"], {"type": "busy"})
            c = Consultation(patient_id=user["id"], doctor_id=doctor_id, mode=mode, status="ringing")
            db.add(c)
            db.commit()
            call = Call(c.id, user["id"], doctor_id, mode)
        self.calls[call.id] = call
        self.active[call.patient_id] = self.active[call.doctor_id] = call.id
        call.timer = asyncio.get_running_loop().create_task(self._ring_timeout(call))
        await self.send(user["id"], {"type": "ringing", "call_id": call.id})
        await self.send(doctor_id, {"type": "ring", "call_id": call.id, "mode": mode,
                                    "from": {"id": user["id"], "name": user["name"]}})

    async def _ring_timeout(self, call: Call) -> None:
        await asyncio.sleep(get_settings().ring_timeout_seconds)
        if call.state == "ringing":
            await self.finish(call, "missed", notify=(call.patient_id, call.doctor_id))

    async def finish(self, call: Call, status: str, notify: tuple[int, ...]) -> None:
        if call.id not in self.calls:
            return
        if call.timer and call.timer is not asyncio.current_task():
            call.timer.cancel()
        self.calls.pop(call.id, None)
        self.active.pop(call.patient_id, None)
        self.active.pop(call.doctor_id, None)
        self._set_status(call.id, status, ended=True)
        kind = {"declined": "decline", "cancelled": "cancel", "ended": "end", "missed": "missed"}[status]
        for uid in notify:
            await self.send(uid, {"type": kind, "call_id": call.id})

    async def handle(self, user: dict, msg: dict) -> None:
        kind, uid = msg.get("type"), user["id"]
        if kind == "ring":
            return await self.ring(user, msg)
        call = self.calls.get(self.active.get(uid, -1))
        if not call:
            return
        peer = call.peer_of(uid)
        if kind == "accept" and uid == call.doctor_id and call.state == "ringing":
            call.state = "connected"
            if call.timer:
                call.timer.cancel()
            self._set_status(call.id, "connected", started=True)
            await self.send(call.patient_id, {"type": "accept", "call_id": call.id})
        elif kind == "decline" and uid == call.doctor_id and call.state == "ringing":
            await self.finish(call, "declined", notify=(call.patient_id,))
        elif kind == "cancel" and uid == call.patient_id and call.state == "ringing":
            await self.finish(call, "cancelled", notify=(call.doctor_id,))
        elif kind == "end" and call.state == "connected":
            await self.finish(call, "ended", notify=(peer,))
        elif kind in RELAY and call.state == "connected":
            await self.send(peer, {"type": kind, "data": msg.get("data")})

    async def disconnect(self, uid: int, ws: WebSocket) -> None:
        if self.sockets.get(uid) is ws:
            self.sockets.pop(uid, None)
        call = self.calls.get(self.active.get(uid, -1))
        if call:
            peer = call.peer_of(uid)
            if call.state == "ringing":
                status = "cancelled" if uid == call.patient_id else "declined"
            else:
                status = "ended"
            await self.finish(call, status, notify=(peer,))


hub = CallHub()


@router.get("/calls/ice-servers")
def ice_servers(_: User = Depends(current_user)):
    s = get_settings()
    servers: list[dict] = [{"urls": s.stun_urls}]
    if s.turn_url:
        servers.append({"urls": [s.turn_url], "username": s.turn_username, "credential": s.turn_credential})
    return {"iceServers": servers}


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket, token: str):
    payload = decode_token(token)
    user = None
    if payload:
        with SessionLocal() as db:
            u = db.get(User, int(payload["sub"]))
            if u and u.is_active:
                user = {"id": u.id, "role": u.role, "name": u.name}
    if not user:
        await ws.close(code=4401)
        return
    await ws.accept()
    hub.sockets[user["id"]] = ws
    try:
        while True:
            msg = await ws.receive_json()
            if isinstance(msg, dict):
                await hub.handle(user, msg)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        await hub.disconnect(user["id"], ws)
