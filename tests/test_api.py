import datetime as dt
import io
import os

import pytest

os.environ["DATABASE_URL"] = "sqlite:///./test_ruralcare.db"
os.environ["UPLOAD_DIR"] = "./test_uploads"

from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import User
from app.security import hash_password

PW = "Passw0rd!x"


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.add(User(role="authority", name="Authority", phone="9000000001", password_hash=hash_password(PW)))
        db.commit()
    with TestClient(app) as c:
        yield c


def login(c, phone, pw=PW):
    r = c.post("/auth/login", data={"username": phone, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, r.json()["user"]


def make_user(c, auth, role, name, phone, **extra):
    r = c.post("/admin/users", headers=auth, json={"role": role, "name": name, "phone": phone, "password": PW, **extra})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture()
def world(client):
    c = client
    auth, _ = login(c, "9000000001")
    asha = make_user(c, auth, "asha", "Meena", "9000000010", village="Melur")
    doc = make_user(c, auth, "doctor", "Dr. Rao", "9000000020")
    ph = make_user(c, auth, "pharmacy", "Murugan Medicals", "9000000030", lat=12.9, lng=79.1)
    assert c.post("/auth/register", json={"name": "Lakshmi", "phone": "9000000040", "password": PW,
                                          "village": "Melur"}).status_code == 201
    return {"c": c, "auth": auth, "asha": asha, "doc": doc, "ph": ph,
            "pat": login(c, "9000000040"), "pharm": login(c, "9000000030"),
            "doctor": login(c, "9000000020"), "ashal": login(c, "9000000010")}


def batch(code, expiry=None, **kw):
    return {"code": code, "medicine_name": "Metformin", "strength": "500 mg", "manufacturer": "SunRise Labs",
            "batch_no": "B07", "expiry": str(expiry or dt.date.today() + dt.timedelta(days=400)), "quantity": 40, **kw}


def test_auth_and_roles(world):
    c = world["c"]
    assert world["pat"][1]["role"] == "patient"
    assert world["pat"][1]["asha_id"] == world["asha"]["id"]          # auto-assigned by village
    assert c.post("/auth/login", data={"username": "9000000040", "password": "wrong"}).status_code == 401
    assert c.get("/auth/me").status_code == 401
    # a patient cannot register medicines or open the authority dashboard
    assert c.post("/pharmacy/batches", headers=world["pat"][0], json=batch("ABC-1")).status_code == 403
    assert c.get("/authority/dashboard", headers=world["pat"][0]).status_code == 403


def test_verify_flow(world):
    c, pat, pharm = world["c"], world["pat"][0], world["pharm"][0]
    assert c.post("/pharmacy/batches", headers=pharm, json=batch("MTF-1")).status_code == 201
    assert c.post("/pharmacy/batches", headers=pharm, json=batch("mtf-1")).status_code == 409   # duplicate code
    c.post("/pharmacy/batches", headers=pharm, json=batch("OLD-1", expiry=dt.date.today() - dt.timedelta(days=5)))

    r = c.post("/scan/verify", headers=pat, json={"code": "mtf-1"}).json()
    assert r["status"] == "genuine" and r["batch"]["registered_by"] == "Murugan Medicals"
    assert c.post("/scan/verify", headers=pat, json={"code": "OLD-1"}).json()["status"] == "expired"
    r = c.post("/scan/verify", headers=pat, json={"code": "NOPE-9"}).json()
    assert (r["status"], r["reason"]) == ("suspicious", "not_registered")

    for _ in range(2):                                                  # scans 2 and 3 still genuine
        assert c.post("/scan/verify", headers=pat, json={"code": "MTF-1"}).json()["status"] == "genuine"
    r = c.post("/scan/verify", headers=pat, json={"code": "MTF-1"}).json()   # 4th scan: duplicate
    assert (r["status"], r["reason"]) == ("suspicious", "duplicate_scans")


def test_image_scan(world):
    c, pat, pharm = world["c"], world["pat"][0], world["pharm"][0]
    b = c.post("/pharmacy/batches", headers=pharm, json=batch("IMG-2231-B07")).json()
    png = c.get(f"/pharmacy/batches/{b['id']}/qr.png", headers=pharm)
    assert png.status_code == 200 and png.headers["content-type"] == "image/png"
    r = c.post("/scan/image", headers=pat, files={"file": ("qr.png", png.content, "image/png")})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "genuine" and r.json()["code"] == "IMG-2231-B07"

    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (200, 200), "white").save(buf, "PNG")
    assert c.post("/scan/image", headers=pat, files={"file": ("w.png", buf.getvalue(), "image/png")}).status_code == 422
    assert c.post("/scan/image", headers=pat, files={"file": ("t.txt", b"hello", "text/plain")}).status_code == 415


def test_patient_symptoms_and_asha(world):
    c, pat, ashal = world["c"], world["pat"][0], world["ashal"][0]
    r = c.post("/patient/symptoms", headers=pat, json={"symptoms": ["fever"]}).json()
    assert r["urgent"] is False
    r = c.post("/patient/symptoms", headers=pat, json={"symptoms": ["blood", "cough"]}).json()
    assert r["urgent"] is True and r["message_key"] == "symUrgent"
    assert c.post("/patient/symptoms", headers=pat, json={"symptoms": ["bogus"]}).status_code == 422

    alerts = c.get("/asha/alerts", headers=ashal).json()
    assert alerts[0]["level"] == "bad" and alerts[0]["patient"] == "Lakshmi"
    assert c.post(f"/asha/alerts/{alerts[0]['id']}/visit", headers=ashal).status_code == 200
    assert all(a["id"] != alerts[0]["id"] for a in c.get("/asha/alerts", headers=ashal).json() if a["kind"] == "symptoms")


def test_my_medicines_and_report_and_dashboard(world):
    c, pat, pharm, auth = world["c"], world["pat"][0], world["pharm"][0], world["auth"]
    soon = dt.date.today() + dt.timedelta(days=10)
    c.post("/pharmacy/batches", headers=pharm, json=batch("SOON-1", expiry=soon))
    assert c.post("/patient/medicines", headers=pat, json={"code": "SOON-1"}).status_code == 201
    assert c.post("/patient/medicines", headers=pat, json={"code": "UNKNOWN"}).status_code == 404
    assert c.get("/patient/alerts", headers=pat).json()[0]["kind"] == "expiring"

    r = c.post("/reports", headers=pat, json={"code": "SOON-1", "reason": "expired_sold"})
    assert r.status_code == 201 and r.json()["pharmacy_id"] == world["ph"]["id"]
    dash = c.get("/authority/dashboard", headers=auth).json()
    assert dash["public_reports"] == 1 and dash["pharmacies"][0]["score"] == 90


def test_consultation_photo_and_prescription(world):
    c, pat, doc = world["c"], world["pat"][0], world["doctor"][0]
    cid = c.post("/consultations", headers=pat, json={"doctor_id": world["doc"]["id"]}).json()["id"]
    assert c.post(f"/consultations/{cid}/messages", headers=pat, json={"body": "I have a fever"}).status_code == 201
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (2000, 1500), (180, 90, 60)).save(buf, "PNG")
    p = c.post(f"/consultations/{cid}/photo", headers=pat, files={"file": ("a.png", buf.getvalue(), "image/png")})
    assert p.status_code == 201 and p.json()["has_photo"]
    got = c.get(f"/messages/{p.json()['id']}/photo", headers=doc)
    assert got.status_code == 200 and len(got.content) <= 40 * 1024

    assert len(c.get("/doctor/queue", headers=doc).json()) == 1
    rx = c.post("/prescriptions", headers=doc, json={"patient_id": world["pat"][1]["id"], "consultation_id": cid,
                                                     "items": ["Paracetamol 500 mg", "Rest"]})
    assert rx.status_code == 201
    assert c.get("/doctor/queue", headers=doc).json() == []
    assert c.get("/patient/prescriptions", headers=pat).json()[0]["items"][0] == "Paracetamol 500 mg"
    # another doctor-less user cannot read the chat
    assert c.get(f"/consultations/{cid}/messages", headers=world["pharm"][0]).status_code == 404


def _token(headers):
    return headers["Authorization"].split()[1]


def test_call_flow(world):
    c = world["c"]
    pat_t, doc_t = _token(world["pat"][0]), _token(world["doctor"][0])
    did = world["doc"]["id"]
    with c.websocket_connect(f"/ws?token={doc_t}") as docws, c.websocket_connect(f"/ws?token={pat_t}") as patws:
        patws.send_json({"type": "ring", "doctor_id": did, "mode": "video"})
        assert patws.receive_json()["type"] == "ringing"
        ring = docws.receive_json()
        assert ring["type"] == "ring" and ring["mode"] == "video" and ring["from"]["name"] == "Lakshmi"

        docws.send_json({"type": "accept"})
        assert patws.receive_json()["type"] == "accept"
        patws.send_json({"type": "offer", "data": {"sdp": "x"}})
        assert docws.receive_json() == {"type": "offer", "data": {"sdp": "x"}}
        docws.send_json({"type": "answer", "data": {"sdp": "y"}})
        assert patws.receive_json()["type"] == "answer"
        docws.send_json({"type": "end"})
        assert patws.receive_json()["type"] == "end"

        patws.send_json({"type": "ring", "doctor_id": did, "mode": "audio"})   # decline path
        patws.receive_json(); docws.receive_json()
        docws.send_json({"type": "decline"})
        assert patws.receive_json()["type"] == "decline"

    cons = c.get("/consultations", headers=world["pat"][0]).json()
    assert sorted(x["status"] for x in cons) == ["declined", "ended"]


def test_call_unavailable_and_bad_token(world):
    c = world["c"]
    with c.websocket_connect(f"/ws?token={_token(world['pat'][0])}") as ws:
        ws.send_json({"type": "ring", "doctor_id": world["doc"]["id"], "mode": "audio"})
        assert ws.receive_json()["type"] == "unavailable"            # the doctor is not online
    with pytest.raises(Exception):
        with c.websocket_connect("/ws?token=bad"):
            pass


def test_frontend_support_endpoints(world):
    c, pat, pharm = world["c"], world["pat"][0], world["pharm"][0]
    assert c.get("/health").json()["status"] == "ok"
    assert "RuralCare" in c.get("/").text                                  # the web app is served by the API
    assert c.get("/app.js").status_code == 200

    assert c.get("/patient/asha", headers=pat).json()["name"] == "Meena"
    c.post("/pharmacy/batches", headers=pharm, json=batch("HIST-1"))
    c.post("/scan/verify", headers=pat, json={"code": "HIST-1"})
    c.post("/scan/verify", headers=pat, json={"code": "NOPE"})
    hist = c.get("/scan/history", headers=pat).json()
    assert hist[0]["medicine_name"] is None and hist[1]["medicine_name"] == "Metformin"

    assert c.get("/doctors", headers=pat).json()[0]["online"] is False
    with c.websocket_connect(f"/ws?token={_token(world['doctor'][0])}"):
        assert c.get("/doctors", headers=pat).json()[0]["online"] is True
