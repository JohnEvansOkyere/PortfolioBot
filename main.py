from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request as GoogleRequest
from googleapiclient.discovery import build
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
import os
import requests
from typing import Optional, Dict, Any

app = FastAPI()

# --- CORS (allow your frontend/ngrok) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten later: ["https://<your-ngrok>.ngrok-free.app", "http://localhost:****"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Google Calendar OAuth settings ---
SCOPES = ["https://www.googleapis.com/auth/calendar"]
CLIENT_SECRETS_FILE = "/home/grejoy/Projects/portfolio_bot/PortfolioBot/credentials.json"
TOKEN_FILE = "token.json"
REDIRECT_URI = "https://portfoliobot-1.onrender.com/auth/google/callback"

# --- EmailJS settings (from your portfolio config) ---
EMAILJS_SERVICE_ID = "service_wpa4e28"
EMAILJS_TEMPLATE_ID = "template_yja8nnz"
EMAILJS_PUBLIC_KEY = "qfm15fP7kAwGRCLID"   # EmailJS calls this "public key" (user_id in v1 API)

# ---------- Models ----------
class DialogflowRequest(BaseModel):
    queryResult: Dict[str, Any]

class BookRequest(BaseModel):
    slot: str                       # ISO string from frontend
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    details: Optional[str] = None

# ---------- Auth ----------
def authenticate_google_calendar():
    try:
        creds = None
        if os.path.exists(TOKEN_FILE):
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(GoogleRequest())
            else:
                # Not authorized yet
                raise HTTPException(status_code=401, detail="Google authentication required. Visit /authorize")

            with open(TOKEN_FILE, "w") as token:
                token.write(creds.to_json())

        return creds
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Auth error: {str(e)}")

def get_calendar_service():
    creds = authenticate_google_calendar()
    return build("calendar", "v3", credentials=creds)

# ---------- EmailJS ----------
def send_email_via_emailjs(name: str, email: str, phone: str, date: str, time: str, details: str):
    payload = {
        "service_id": EMAILJS_SERVICE_ID,
        "template_id": EMAILJS_TEMPLATE_ID,
        "user_id": EMAILJS_PUBLIC_KEY,   # v1 endpoint expects 'user_id'
        "template_params": {
            "name": name,
            "email": email,
            "phone": phone,
            "date": date,
            "time": time,
            "details": details,
        },
    }
    r = requests.post("https://api.emailjs.com/api/v1.0/email/send", json=payload, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"EmailJS failed: {r.status_code} {r.text}")

# ---------- Calendar helper ----------
def create_calendar_event(start_time_utc: datetime, name: str, email: str, phone: str, details: str):
    """
    Creates a 1-hour event starting at start_time_utc (timezone-aware datetime in UTC).
    """
    if start_time_utc.tzinfo is None:
        start_time_utc = start_time_utc.replace(tzinfo=timezone.utc)

    end_time_utc = start_time_utc + timedelta(hours=1)

    service = get_calendar_service()
    event = {
        "summary": f"Appointment with {name}",
        "description": f"Details: {details}\nPhone: {phone}\nEmail: {email}",
        "start": {"dateTime": start_time_utc.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": end_time_utc.isoformat(), "timeZone": "UTC"},
        "attendees": [{"email": email}] if email else [],
    }
    created = service.events().insert(calendarId="primary", body=event).execute()
    return created.get("id")

# ---------- Slots (demo: lists upcoming event starts; adjust per your logic) ----------
@app.get("/slots")
async def get_slots():
    try:
        service = get_calendar_service()
        events_result = service.events().list(
            calendarId="primary",
            timeMin=datetime.utcnow().isoformat() + "Z",
            maxResults=10,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        events = events_result.get("items", [])
        slots = []
        for e in events:
            start = e.get("start", {})
            dt = start.get("dateTime") or start.get("date")  # handle all-day
            if dt:
                slots.append(dt)
        return {"status": "success", "slots": slots}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ---------- Book (from frontend) ----------
@app.post("/book")
async def book_slot(body: BookRequest):
    """
    Expects JSON body { slot: ISOString, name?, email?, phone?, details? }
    """
    try:
        # parse time
        # accept Z or offset; ensure timezone aware
        iso = body.slot.replace("Z", "+00:00")
        start_dt = datetime.fromisoformat(iso)
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        else:
            start_dt = start_dt.astimezone(timezone.utc)

        # Create calendar event
        event_id = create_calendar_event(
            start_time_utc=start_dt,
            name=body.name or "Client",
            email=body.email or "",
            phone=body.phone or "",
            details=body.details or "Reserved via website",
        )

        # Optionally send EmailJS if we have at least an email or phone
        try:
            send_email_via_emailjs(
                name=body.name or "Client",
                email=body.email or "no-email@local",
                phone=body.phone or "N/A",
                date=start_dt.date().isoformat(),
                time=start_dt.time().strftime("%H:%M"),
                details=body.details or "Reserved via website",
            )
        except Exception as em_err:
            # don't fail booking if email fails
            print(f"EmailJS warning: {em_err}")

        return {"status": "success", "message": f"✅ Slot booked for {body.slot}", "eventId": event_id}
    except Exception as e:
        return {"status": "error", "message": f"Booking failed: {str(e)}"}

# ---------- Dialogflow Webhook ----------
@app.post("/webhook")
async def webhook(req: DialogflowRequest):
    intent_name = req.queryResult.get("intent", {}).get("displayName")
    params = req.queryResult.get("parameters", {}) or {}

    if intent_name == "Book Appointment":
        try:
            # Extract parameters safely
            date = params.get("date")                    # often ISO (e.g., 2025-09-01T12:00:00Z)
            time = params.get("time")                    # often ISO (e.g., 2025-08-28T11:30:00Z)
            details = params.get("any") or ""
            email = params.get("email") or ""
            phone = params.get("phone-number") or ""

            person = params.get("person", {})
            name = person.get("name") if isinstance(person, dict) else (person or "")

            # Validate required params (choose your strictness)
            if not all([time, name]):   # time is full ISO; date is optional because time usually carries date
                return {"fulfillmentText": "❌ Some details are missing. Please provide all required information."}

            # Use 'time' as the full ISO datetime
            start_iso = time.replace("Z", "+00:00")
            start_dt = datetime.fromisoformat(start_iso)
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)
            else:
                start_dt = start_dt.astimezone(timezone.utc)

            # Create Calendar event
            event_id = create_calendar_event(
                start_time_utc=start_dt,
                name=name,
                email=email,
                phone=phone,
                details=details or "N/A",
            )

            # Send EmailJS (notify you)
            try:
                send_email_via_emailjs(
                    name=name,
                    email=email or "no-email@local",
                    phone=phone or "N/A",
                    date=(date or start_dt.date().isoformat()),
                    time=start_dt.time().strftime("%H:%M"),
                    details=details or "N/A",
                )
            except Exception as em_err:
                print(f"EmailJS warning: {em_err}")

            # Clean, fixed order confirmation
            return {
                "fulfillmentText": (
                    "✅ Appointment booked successfully!\n\n"
                    f"📅 Date: {(date or start_dt.date().isoformat())}\n"
                    f"⏰ Time: {start_dt.time().strftime('%H:%M')} (UTC)\n"
                    f"👤 Name: {name}\n"
                    f"📧 Email: {email or 'N/A'}\n"
                    f"📞 Phone: {phone or 'N/A'}\n"
                    f"📝 Details: {details or 'N/A'}\n"
                    f"🆔 Event ID: {event_id}"
                )
            }
        except Exception as e:
            return {"fulfillmentText": f"⚠️ An error occurred: {str(e)}"}

    # default
    return {"fulfillmentText": "I didn't understand that. Can you please rephrase?"}

# ---------- OAuth endpoints ----------
@app.get("/auth/callback")
async def auth_callback(code: str):
    try:
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE, SCOPES, redirect_uri=REDIRECT_URI
        )
        flow.fetch_token(code=code)
        creds = flow.credentials
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
        return JSONResponse({"status": "success", "message": "Google Calendar authorized successfully!"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"OAuth callback failed: {str(e)}"})

@app.get("/authorize")
async def authorize():
    flow = Flow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES, redirect_uri=REDIRECT_URI)
    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline", include_granted_scopes="true")
    return RedirectResponse(auth_url)


@app.get("/")
async def root():
    return {"status": "ok", "message": "API is working on Render 🚀"}

