"""
Gmail Client - Reads actual emails from your Gmail inbox
Integrates with Google Gmail API using OAuth2 credentials
"""

import os
import pickle
from pathlib import Path
from typing import List, Dict, Any, Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.api_core import retry
import google.auth
from googleapiclient.discovery import build
import base64
from email.mime.text import MIMEText
import json


# Gmail API scopes
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.modify'
]

# Path to OAuth credentials
HOME_DIR = Path.home()
CONFIG_DIR = HOME_DIR / '.gmail-mcp'
OAUTH_KEYS_PATH = CONFIG_DIR / 'gcp-oauth.keys.json'
CREDENTIALS_PATH = CONFIG_DIR / 'credentials.json'

# Also check for keys in the Gmail-MCP-Server folder
GMAIL_MCP_KEYS = Path(__file__).parent.parent / 'Gmail-MCP-Server' / 'gcp-oauth.keys.json'


class GmailClient:
    """
    Client for reading and interacting with Gmail.
    Uses the same credentials as the Gmail-MCP-Server.
    """
    
    def __init__(self):
        """Initialize Gmail API client with credentials."""
        self.service = None
        self.credentials = None
        self._authenticate()
    
    def _authenticate(self):
        """
        Authenticate with Gmail API.
        Uses existing credentials or prompts for OAuth flow.
        """
        # Try loading from Streamlit secrets (for cloud deployments)
        try:
            import streamlit as st
            if "GMAIL_CREDENTIALS" in st.secrets:
                try:
                    creds_info = json.loads(st.secrets["GMAIL_CREDENTIALS"])
                    self.credentials = Credentials.from_authorized_user_info(creds_info, SCOPES)
                    if self.credentials:
                        if self.credentials.expired and self.credentials.refresh_token:
                            self.credentials.refresh(Request())
                        self.service = build('gmail', 'v1', credentials=self.credentials)
                        return
                except Exception as e:
                    raise ValueError(f"Failed to initialize Gmail client using Streamlit secrets ['GMAIL_CREDENTIALS']: {e}")
        except ImportError:
            pass

        # Check for existing credentials first
        if CREDENTIALS_PATH.exists():
            try:
                self.credentials = Credentials.from_authorized_user_file(str(CREDENTIALS_PATH), SCOPES)
                if self.credentials and self.credentials.valid:
                    self.service = build('gmail', 'v1', credentials=self.credentials)
                    return
            except Exception as e:
                print(f"⚠️  Existing credentials invalid: {e}")
        
        # Find OAuth keys
        oauth_keys_file = None
        if GMAIL_MCP_KEYS.exists():
            oauth_keys_file = GMAIL_MCP_KEYS
        elif OAUTH_KEYS_PATH.exists():
            oauth_keys_file = OAUTH_KEYS_PATH
        
        if not oauth_keys_file:
            raise FileNotFoundError(
                f"OAuth keys file not found at:\n"
                f"  {GMAIL_MCP_KEYS}\n"
                f"  or {OAUTH_KEYS_PATH}\n\n"
                f"Please copy your gcp-oauth.keys.json from Gmail-MCP-Server folder\n"
                f"to ~/.gmail-mcp/ directory."
            )
        
        # Load and verify OAuth keys format
        try:
            with open(oauth_keys_file, 'r') as f:
                keys_data = json.load(f)
            
            keys = keys_data.get('installed') or keys_data.get('web')
            if not keys:
                raise ValueError("Invalid keys format")
        except Exception as e:
            raise ValueError(f"Failed to load OAuth keys: {e}")
        
        # Create OAuth flow
        try:
            # Use the redirect URI from the keys file
            redirect_uri = keys.get('redirect_uris', ['http://localhost'])[0]
            
            flow = InstalledAppFlow.from_client_secrets_file(
                str(oauth_keys_file), SCOPES, redirect_uri=redirect_uri)
            
            self.credentials = flow.run_local_server(port=0, open_browser=True)
            
            # Save credentials for future use
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(CREDENTIALS_PATH, 'w') as token:
                token.write(self.credentials.to_json())
            
            # Build service
            self.service = build('gmail', 'v1', credentials=self.credentials)
        
        except Exception as e:
            raise Exception(f"OAuth authentication failed: {e}")
    
    def get_inbox_threads(self, max_results: int = 10, query: str = "is:unread") -> List[Dict[str, Any]]:
        """
        Fetch email threads from inbox.
        
        Args:
            max_results: Maximum number of threads to fetch
            query: Gmail search query (default: unread emails)
            
        Returns:
            List of thread dicts with subject, sender, snippet, and message IDs
        """
        try:
            results = self.service.users().threads().list(
                userId='me',
                q=query,
                maxResults=max_results
            ).execute()
            
            threads = results.get('threads', [])
            formatted_threads = []
            
            for thread in threads:
                thread_data = self._format_thread(thread['id'])
                if thread_data:
                    formatted_threads.append(thread_data)
            
            return formatted_threads
        except Exception as e:
            print(f"❌ Error fetching inbox: {e}")
            return []
    
    def _format_thread(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """
        Format a Gmail thread into our standard thread format.
        
        Args:
            thread_id: Gmail thread ID
            
        Returns:
            Thread dict with subject, messages, etc.
        """
        try:
            thread = self.service.users().threads().get(
                userId='me',
                id=thread_id,
                format='full'
            ).execute()
            
            messages = thread.get('messages', [])
            if not messages:
                return None
            
            # Extract thread info from messages
            formatted_messages = []
            subject = "No subject"
            
            for msg in messages:
                headers = msg['payload'].get('headers', [])
                
                # Extract headers
                msg_dict = {"id": msg.get("id")}
                for header in headers:
                    header_name_lower = header['name'].lower()
                    if header_name_lower == 'subject':
                        subject = header['value']
                    elif header_name_lower == 'from':
                        msg_dict['from'] = header['value']
                    elif header_name_lower == 'date':
                        msg_dict['date'] = header['value']
                
                # Extract body
                body = self._get_message_body(msg['payload'])
                msg_dict['body'] = body
                
                if msg_dict.get('from') and msg_dict.get('body'):
                    formatted_messages.append(msg_dict)
            
            if not formatted_messages:
                return None
            
            return {
                "subject": subject,
                "thread_id": thread_id,
                "last_message_id": messages[-1].get('id') if messages else None,
                "messages": formatted_messages,
                "from": formatted_messages[-1].get('from', 'Unknown'),
                "snippet": messages[-1].get('snippet', '')
            }
        
        except Exception as e:
            print(f"⚠️  Error formatting thread {thread_id}: {e}")
            return None
    
    def _get_message_body(self, payload: Dict[str, Any]) -> str:
        """
        Extract plain text body from email payload.
        
        Args:
            payload: Gmail message payload
            
        Returns:
            Email body text
        """
        try:
            # Check if body is directly in payload
            if 'body' in payload and 'data' in payload['body']:
                data = payload['body']['data']
                if data:
                    return base64.urlsafe_b64decode(data).decode('utf-8')
            
            # Check parts if nested
            if 'parts' in payload:
                for part in payload['parts']:
                    if part.get('mimeType') == 'text/plain':
                        if 'data' in part.get('body', {}):
                            data = part['body']['data']
                            if data:
                                return base64.urlsafe_b64decode(data).decode('utf-8')
            
            return ""
        except Exception as e:
            print(f"⚠️  Error extracting body: {e}")
            return ""
    
    def search_emails(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """
        Search for emails matching a query.
        
        Args:
            query: Gmail search query
            max_results: Maximum results to return
            
        Returns:
            List of matching thread dicts
        """
        return self.get_inbox_threads(max_results=max_results, query=query)
    
    def mark_thread_as_read(self, thread_id: str) -> bool:
        """
        Mark a thread as read.
        
        Args:
            thread_id: Gmail thread ID
            
        Returns:
            True if successful
        """
        try:
            self.service.users().threads().modify(
                userId='me',
                id=thread_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
            return True
        except Exception as e:
            print(f"⚠️  Error marking thread as read: {e}")
            return False
    
    def add_label_to_thread(self, thread_id: str, label_name: str) -> bool:
        """
        Add a label to a thread.
        
        Args:
            thread_id: Gmail thread ID
            label_name: Label name (e.g., "Replied")
            
        Returns:
            True if successful
        """
        try:
            # Get label ID
            labels = self.service.users().labels().list(userId='me').execute()
            label_id = None
            
            for label in labels.get('labels', []):
                if label['name'] == label_name:
                    label_id = label['id']
                    break
            
            if not label_id:
                # Create label if it doesn't exist
                label_body = {
                    'name': label_name,
                    'labelListVisibility': 'labelShow',
                    'messageListVisibility': 'show'
                }
                label_obj = self.service.users().labels().create(
                    userId='me', body=label_body).execute()
                label_id = label_obj['id']
            
            # Add label to thread
            self.service.users().threads().modify(
                userId='me',
                id=thread_id,
                body={'addLabelIds': [label_id]}
            ).execute()
            return True
        except Exception as e:
            print(f"⚠️  Error adding label: {e}")
            return False
    
    def send_reply(self, thread_id: str, message_id: str, reply_text: str, subject_prefix: str = "Re: ") -> Optional[str]:
        """
        Send a reply to an email in a thread.
        
        Args:
            thread_id: Gmail thread ID
            message_id: Message ID to reply to
            reply_text: Reply body text
            subject_prefix: Prefix for reply subject
            
        Returns:
            Sent message ID or None on error
        """
        try:
            # If message_id is missing, fetch the thread to find the last message
            if not message_id:
                print(f"⚠️ Message ID not provided for thread {thread_id}. Fetching thread to get last message ID...")
                thread_detail = self.service.users().threads().get(
                    userId='me', id=thread_id, format='minimal'
                ).execute()
                messages = thread_detail.get('messages', [])
                if messages:
                    message_id = messages[-1].get('id')
                    print(f"✓ Found last message ID: {message_id}")
                else:
                    raise ValueError(f"No messages found in thread {thread_id}")

            # Get original message to extract headers
            message = self.service.users().messages().get(
                userId='me', id=message_id, format='full').execute()
            
            headers = message['payload'].get('headers', [])
            original_subject = ""
            from_email = ""
            to_email = ""
            msg_id_header = ""
            
            for header in headers:
                header_name_lower = header['name'].lower()
                if header_name_lower == 'subject':
                    original_subject = header['value']
                elif header_name_lower == 'from':
                    from_email = header['value']
                elif header_name_lower == 'to':
                    to_email = header['value']
                elif header_name_lower == 'message-id':
                    msg_id_header = header['value']
            
            # Fetch my profile to check if I sent the last message
            try:
                profile = self.service.users().getProfile(userId='me').execute()
                my_email = profile.get('emailAddress', '').lower()
            except Exception:
                my_email = ""

            # Decide who to send the reply to:
            # If the last message was from us, reply to the 'To' header (the other person)
            if my_email and my_email in from_email.lower():
                reply_to = to_email
            else:
                reply_to = from_email

            if not reply_to:
                reply_to = from_email or to_email

            # Clean and format the reply_to address using email.utils
            import email.utils
            parsed_addresses = email.utils.getaddresses([reply_to])
            valid_addresses = []
            for name, addr in parsed_addresses:
                if addr:
                    valid_addresses.append(email.utils.formataddr((name, addr)))
            if valid_addresses:
                reply_to = ", ".join(valid_addresses)

            # Create reply subject
            if not original_subject.lower().startswith('re:'):
                reply_subject = f"{subject_prefix}{original_subject}"
            else:
                reply_subject = original_subject
            
            # Create reply message
            reply_message = MIMEText(reply_text)
            reply_message['to'] = reply_to
            reply_message['subject'] = reply_subject
            if msg_id_header:
                reply_message['In-Reply-To'] = msg_id_header
                reply_message['References'] = msg_id_header
            
            raw = base64.urlsafe_b64encode(reply_message.as_bytes()).decode()
            
            # Send reply in same thread
            sent = self.service.users().messages().send(
                userId='me',
                body={'raw': raw, 'threadId': thread_id}
            ).execute()
            
            print(f"✓ Reply sent (ID: {sent['id']}) to {reply_to}")
            return sent['id']
        
        except Exception as e:
            print(f"❌ Error sending reply: {e}")
            return None


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("GMAIL CLIENT TEST")
    print("=" * 80)
    
    try:
        print("\n🔐 Authenticating with Gmail...")
        client = GmailClient()
        print("✓ Authentication successful")
        
        print("\n📥 Fetching unread emails...")
        threads = client.get_inbox_threads(max_results=5, query="is:unread")
        
        if threads:
            print(f"\n✓ Found {len(threads)} unread thread(s):\n")
            for i, thread in enumerate(threads, 1):
                print(f"[{i}] Subject: {thread['subject']}")
                print(f"    From: {thread['from']}")
                print(f"    Messages: {len(thread['messages'])}")
                print()
        else:
            print("\n📭 No unread emails found")
    
    except FileNotFoundError as e:
        print(f"\n❌ Configuration Error: {e}")
    except Exception as e:
        print(f"\n❌ Error: {e}")
