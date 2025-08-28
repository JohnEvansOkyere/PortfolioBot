from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request as GoogleRequest
from googleapiclient.discovery import build
from pydantic import BaseModel
from datetime import datetime, timedelta
import os

app = FastAPI()

# Google Calendar API settings
SCOPES = ["https://www.googleapis.com/auth/calendar"]
CLIENT_SECRETS_FILE = "/home/grejoy/Projects/portfolio_bot/PortfolioBot/credentials.json"
TOKEN_FILE = "token.json"


# Pydantic model for Dialogflow webhook request
class DialogflowRequest(BaseModel):
    queryResult: dict


# Authenticate with Google Calendar
def authenticate_google_calendar():
    try:
        creds = None
        if os.path.exists(TOKEN_FILE):
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(GoogleRequest())
            else:
                raise HTTPException(
                    status_code=401, detail="Google authentication required."
                )

            with open(TOKEN_FILE, "w") as token:
                token.write(creds.to_json())

        return creds
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Auth error: {str(e)}")


# Fetch available slots
@app.get("/slots")
async def get_slots():
    try:
        creds = authenticate_google_calendar()
        service = build("calendar", "v3", credentials=creds)
        events_result = service.events().list(
            calendarId="primary",
            timeMin=datetime.utcnow().isoformat() + "Z",
            maxResults=10,
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        events = events_result.get("items", [])
        slots = [event["start"].get("dateTime") for event in events]

        return {"status": "success", "slots": slots}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# Book a slot
@app.post("/book")
async def book_slot(slot: str):
    try:
        creds = authenticate_google_calendar()
        service = build("calendar", "v3", credentials=creds)

        start_time = datetime.fromisoformat(slot)
        end_time = start_time + timedelta(hours=1)

        event = {
            "summary": "Appointment Booking",
            "description": "Reserved via chatbot",
            "start": {"dateTime": start_time.isoformat(), "timeZone": "UTC"},
            "end": {"dateTime": end_time.isoformat(), "timeZone": "UTC"},
        }

        service.events().insert(calendarId="primary", body=event).execute()
        return {"status": "success", "message": f"✅ Slot booked for {slot}"}
    except Exception as e:
        return {"status": "error", "message": f"Booking failed: {str(e)}"}


# Handle Dialogflow webhook
@app.post("/webhook")
async def webhook(request: DialogflowRequest):
    intent_name = request.queryResult.get("intent", {}).get("displayName")
    params = request.queryResult.get("parameters", {})

    if intent_name == "Book Appointment":
        try:
            date = params.get("date")
            time = params.get("time")
            details = params.get("any")
            email = params.get("email")
            phone = params.get("phone-number")

            # Person may come as object { "name": "John" }
            person = params.get("person", {})
            name = person.get("name") if isinstance(person, dict) else person

            # Validate required params
            if not all([date, time, name, phone, email]):
                return {
                    "fulfillmentText": "❌ Some details are missing. Please provide all required information."
                }

            # Use time as full ISO datetime
            start_time = datetime.fromisoformat(time.replace("Z", "+00:00"))
            await book_slot(start_time.isoformat())

            return {
                "fulfillmentText": (
                    f"✅ Appointment booked successfully!\n\n"
                    f"📅 Date: {date}\n"
                    f"⏰ Time: {time}\n"
                    f"👤 Name: {name}\n"
                    f"📧 Email: {email}\n"
                    f"📞 Phone: {phone}\n"
                    f"📝 Details: {details if details else 'N/A'}"
                )
            }

        except Exception as e:
            return {"fulfillmentText": f"⚠️ An error occurred: {str(e)}"}

    return {"fulfillmentText": "I didn't understand that. Can you please rephrase?"}



# OAuth callback
@app.get("/auth/callback")
async def auth_callback(code: str):
    try:
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            SCOPES,
            redirect_uri="https://ba48e9502df7.ngrok-free.app/auth/callback",
        )
        flow.fetch_token(code=code)
        creds = flow.credentials
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
        return JSONResponse(
            {"status": "success", "message": "Google Calendar authorized successfully!"}
        )
    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": f"OAuth callback failed: {str(e)}"}
        )


@app.get("/authorize")
async def authorize():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        SCOPES,
        redirect_uri="https://ba48e9502df7.ngrok-free.app/auth/callback",
    )
    auth_url, _ = flow.authorization_url(prompt="consent")
    return RedirectResponse(auth_url)
