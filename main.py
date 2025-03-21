from fastapi import FastAPI, HTTPException
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import os.path
import json
from pydantic import BaseModel

app = FastAPI()

# Google Calendar API settings
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
CLIENT_SECRETS_FILE = 'C:\\Users\\GREJOY\\bot\\portfolio_appointment\\credentials.json'
TOKEN_FILE = 'token.json'

# Pydantic model for Dialogflow webhook request
class DialogflowRequest(BaseModel):
    queryResult: dict

# Authenticate with Google Calendar
def authenticate_google_calendar():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = Flow.from_client_secrets_file(
                CLIENT_SECRETS_FILE, SCOPES,
                redirect_uri='https://1654-102-176-75-159.ngrok-free.app/auth/callback'
            )
            auth_url, _ = flow.authorization_url(prompt='consent')
            print('Please go to this URL and authorize access:', auth_url)
            code = input('Enter the authorization code: ')
            flow.fetch_token(code=code)
            creds = flow.credentials
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
    return creds

# Fetch available slots
@app.get("/slots")
async def get_slots():
    try:
        creds = authenticate_google_calendar()
        service = build('calendar', 'v3', credentials=creds)
        events_result = service.events().list(
            calendarId='primary',  # Use 'primary' for the user's main calendar
            timeMin='2023-10-01T00:00:00Z',
            maxResults=10,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])
        return {"slots": [event['start']['dateTime'] for event in events]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Handle bookings
@app.post("/book")
async def book_slot(slot: str):
    try:
        creds = authenticate_google_calendar()
        service = build('calendar', 'v3', credentials=creds)
        event = {
            'summary': 'Booked Slot',
            'start': {'dateTime': slot},
            'end': {'dateTime': slot}
        }
        service.events().insert(calendarId='primary', body=event).execute()
        return {"message": "Slot booked successfully!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Handle Dialogflow webhook
@app.post("/webhook")
async def webhook(request: DialogflowRequest):
    intent_name = request.queryResult.get('intent', {}).get('displayName')

    if intent_name == "booking.info":
        try:
            # Fetch available slots
            slots = await get_slots()
            return {
                "fulfillmentText": "Here are the available slots. Please choose one:",
                "payload": {
                    "richContent": [
                        [
                            {
                                "type": "chips",
                                "options": [
                                    {"text": slot} for slot in slots["slots"]
                                ]
                            }
                        ]
                    ]
                }
            }
        except Exception as e:
            return {"fulfillmentText": f"An error occurred: {str(e)}"}
    else:
        return {"fulfillmentText": "I didn't understand that. Can you please rephrase?"}