import os
import sys
import socket
import json
import requests
from datetime import datetime, timedelta

# Force IPv4 monkeypatch to avoid slow IPv6 resolution
orig_getaddrinfo = socket.getaddrinfo
def patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = patched_getaddrinfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar"
]

def _build_calendar_service():
    creds = None
    
    # Try loading from Streamlit secrets (for cloud deployments)
    try:
        import streamlit as st
        if "CALENDAR_CREDENTIALS" in st.secrets:
            creds_info = json.loads(st.secrets["CALENDAR_CREDENTIALS"])
            creds = Credentials.from_authorized_user_info(creds_info, SCOPES)
            if creds:
                if creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                return build("calendar", "v3", credentials=creds, cache_discovery=False)
    except Exception:
        pass

    if os.path.exists("data/token.json"):
        creds = Credentials.from_authorized_user_file("data/token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("data/credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("data/token.json", "w") as token:
            token.write(creds.to_json())
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _parse_naive_datetime(time_str):
    """
    Parse an ISO-8601 time string and strip any timezone offset/indicator (e.g. Z, +00:00, -05:00)
    so the year, month, day, hour, and minute are interpreted strictly as local time in the calendar timezone.
    """
    naive_str = time_str
    if "Z" in naive_str:
        naive_str = naive_str.replace("Z", "")
    if "+" in naive_str:
        naive_str = naive_str.split("+")[0]
    if "-" in naive_str:
        parts = naive_str.split("T")
        if len(parts) > 1 and "-" in parts[1]:
            parts[1] = parts[1].split("-")[0]
            naive_str = "T".join(parts)
    return datetime.fromisoformat(naive_str)

def parse_meeting_request(thread, draft_text=None):
    api_key = os.environ.get("GEMINI_API_KEY")
    
    messages = thread.get("messages", [])
    thread_text = ""
    for msg in messages:
        sender = msg.get("from") or msg.get("sender") or "Unknown"
        body = msg.get("body") or ""
        date = msg.get("date") or ""
        thread_text += f"Date: {date}\nFrom: {sender}\nBody:\n{body}\n\n"
        
    if not thread_text:
        thread_text = thread.get("snippet", "")
        
    if draft_text:
        thread_text += f"\nDraft Reply:\n{draft_text}\n\n"
        
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    prompt = f"""
    Here is an email thread. Please extract meeting details.
    
    Today's date is: {today_str}. Use this to resolve relative dates/times like "tomorrow", "next Monday at 3 PM", or "June 25th".
    If multiple times are proposed, return all of them in proposed_times.
    
    Email Thread:
    {thread_text}
    """
    
    system_instruction = (
        "You are an AI assistant that extracts meeting details from email threads and draft replies. "
        "Return ONLY a valid JSON object. Do not include markdown formatting or code blocks. "
        "The JSON object must contain these fields:\n"
        "1. proposed_times: a list of ISO-8601 datetime strings (YYYY-MM-DDTHH:MM:SS) representing the proposed times for the meeting. "
        "If times are relative, resolve them using today's date and the context. "
        "Make sure to represent them in the timezone/local time of the thread/context.\n"
        "CRITICAL: If a 'Draft Reply' is present at the end of the context, prioritize and extract ONLY the specific meeting times or slots proposed or confirmed in that 'Draft Reply' (e.g. counter-proposals or specific selections), as they represent the final choices. Do not extract the broader availability ranges proposed in earlier incoming emails if the Draft Reply makes a specific selection.\n"
        "2. attendees: a list of email addresses of the attendees mentioned in the thread.\n"
        "3. topic: a one-line summary of the meeting topic.\n"
        "4. duration_minutes: the meeting duration in minutes (integer). Default to 30 if not specified."
    )
    
    res_text = None
    
    # Try Gemini API first
    if api_key:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "generationConfig": {"responseMimeType": "application/json"}
        }
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=20)
            if response.status_code == 200:
                res_data = response.json()
                res_text = res_data["candidates"][0]["content"]["parts"][0]["text"]
            else:
                print(f"Gemini API returned status code {response.status_code}, falling back to Groq.")
        except Exception as e:
            print(f"Gemini API error ({e}), falling back to Groq.")
            
    # Fallback to Groq if Gemini fails or key not found
    if not res_text:
        groq_api_key = os.environ.get("GROQ_API_KEY")
        if not groq_api_key:
            return {"parsing_error": "Neither GEMINI_API_KEY nor GROQ_API_KEY is available"}
        try:
            from groq import Groq
            client = Groq(api_key=groq_api_key)
            model_name = os.environ.get("MODEL_NAME", "llama-3.3-70b-versatile")
            combined_prompt = f"{system_instruction}\n\n{prompt}"
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "user", "content": combined_prompt}
                ]
            )
            res_text = response.choices[0].message.content.strip()
        except Exception as e:
            return {"parsing_error": f"Groq fallback failed: {str(e)}"}
            
    # Strip markdown code fences if present
    text_clean = res_text.strip()
    if text_clean.startswith("```"):
        lines = text_clean.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text_clean = "\n".join(lines).strip()
        
    try:
        data = json.loads(text_clean)
        return {
            "proposed_times": data.get("proposed_times", []),
            "attendees": data.get("attendees", []),
            "topic": data.get("topic", "Meeting"),
            "duration_minutes": int(data.get("duration_minutes", 30))
        }
    except Exception as e:
        return {"parsing_error": f"JSON parsing failed: {str(e)}", "raw": res_text}

def _get_calendar_timezone(service=None):
    try:
        if not service:
            service = _build_calendar_service()
        primary_cal = service.calendars().get(calendarId="primary").execute()
        return primary_cal.get("timeZone", "UTC")
    except Exception:
        return "UTC"

def check_availability(time_min, time_max):
    try:
        service = _build_calendar_service()
        calendar_timezone = _get_calendar_timezone(service)
        
        # Parse and localize
        dt_min = _parse_naive_datetime(time_min)
        from zoneinfo import ZoneInfo
        dt_min = dt_min.replace(tzinfo=ZoneInfo(calendar_timezone))
            
        dt_max = _parse_naive_datetime(time_max)
        dt_max = dt_max.replace(tzinfo=ZoneInfo(calendar_timezone))
            
        body = {
            "timeMin": dt_min.isoformat(),
            "timeMax": dt_max.isoformat(),
            "items": [{"id": "primary"}]
        }
        response = service.freebusy().query(body=body).execute()
        busy_intervals = response.get("calendars", {}).get("primary", {}).get("busy", [])
        return len(busy_intervals) == 0
    except Exception as e:
        print(f"Error checking availability: {e}")
        return False

def find_free_slot(proposed_times, duration_minutes):
    service = _build_calendar_service()
    calendar_timezone = _get_calendar_timezone(service)
    
    for time_str in proposed_times:
        try:
            # Parse and localize
            start_dt = _parse_naive_datetime(time_str)
            from zoneinfo import ZoneInfo
            start_dt = start_dt.replace(tzinfo=ZoneInfo(calendar_timezone))
                
            end_dt = start_dt + timedelta(minutes=duration_minutes)
            
            if check_availability(start_dt.isoformat(), end_dt.isoformat()):
                return start_dt.isoformat()
        except Exception as e:
            print(f"Skipping malformed proposed time '{time_str}': {e}")
            continue
    return None

def create_event(summary, start_time, duration_minutes, attendees, description=""):
    try:
        service = _build_calendar_service()
        calendar_timezone = _get_calendar_timezone(service)
        
        # Parse and localize
        start_dt = _parse_naive_datetime(start_time)
        from zoneinfo import ZoneInfo
        start_dt = start_dt.replace(tzinfo=ZoneInfo(calendar_timezone))
            
        end_dt = start_dt + timedelta(minutes=duration_minutes)
        
        mock_domains = {"company.com", "example.com", "cloudhost.com", "aiweekly.io", "officedeals.com"}
        valid_attendees = []
        for email in attendees:
            email_clean = email.strip()
            if "@" not in email_clean:
                continue
            domain = email_clean.split("@")[-1].lower()
            if domain in mock_domains:
                continue
            valid_attendees.append({"email": email_clean})
        
        event_body = {
            "summary": summary,
            "description": description,
            "start": {
                "dateTime": start_dt.isoformat(),
                "timeZone": calendar_timezone
            },
            "end": {
                "dateTime": end_dt.isoformat(),
                "timeZone": calendar_timezone
            }
        }
        if valid_attendees:
            event_body["attendees"] = valid_attendees
            
        created_event = service.events().insert(
            calendarId="primary",
            sendUpdates="all",
            body=event_body
        ).execute()
        
        return created_event
    except Exception as e:
        print(f"Error creating event: {e}")
        raise e
