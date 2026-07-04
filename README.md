# 📧 AI Email Ghostwriter & Approval Gate

A highly professional, human-in-the-loop email drafting and review system. This application reads incoming email threads from your **live Gmail inbox**, generates authentic replies matching your writing style using the **Groq API** (`llama-3.3-70b-versatile`), and lets you review, edit, or reject the drafts before they are sent.

The core principle of this project is **never auto-send without human approval**. This forms a safe and reliable guardrail for AI assistants in real-world professional contexts.

---

## 🚀 Key Features

* **Live Gmail Integration:** Connects securely to your Gmail inbox via OAuth2 to fetch unread threads.
* **Authentic Tone Mimicry:** Combines your customized tone guidelines (`tone_profile.json`) with historical examples of your emails (`past_replies.json`) to draft natural-sounding responses.
* **Premium Web UI:** A high-end Streamlit application featuring a modern glassmorphism dark-theme layout, custom fonts, and responsive layout columns.
* **Human-in-the-Loop Review:**
  * **Approve:** Writes the draft to `approved_drafts.json` and optionally sends the reply immediately via Gmail.
  * **Edit:** Provides inline draft editing with options to **Save & Approve** (commit changes & send) or **Save Draft Only** (revert to preview/review state without sending).
  * **Discard/Reject:** Rejects the draft and prompts a status reset to regenerate a new one.
* **Dual Execution Modes:** Support for both a graphic web dashboard and a fast terminal CLI agent.
* **Dynamic API Key Entry:** Automatically reads keys from `.env` or Streamlit secrets, with an interactive password input field fallback.

---

## 📂 Repository Structure

The project has been organized into a clean folder structure:

```
Chief_of_staff/
├── app.py                 ← Web app entry point (Streamlit)
├── email_reply_agent.py   ← CLI agent entry point (Terminal)
├── src/                   ← Core functional modules
│   ├── gmail_client.py    ← Connects to Google Gmail API
│   ├── calendar_engine.py ← Connects to Google Calendar API
│   ├── context_builder.py ← Assembles tone + history prompts
│   ├── draft_machine.py   ← Handles Groq LLM generations
│   └── task_logger.py     ← Logs task execution
├── data/                  ← Configuration and local secrets/data
│   ├── tone_profile.json  ← Persona, role, and writing quirks (tracked)
│   ├── past_replies.json  ← Examples of how you reply to emails (tracked)
│   ├── credentials.json   ← Google OAuth client secrets (ignored)
│   ├── token.json         ← Google Calendar authorized token (ignored)
│   ├── approved_drafts.json ← Local database of approved drafts (ignored)
│   └── action_log.json    ← Event action log (ignored)
├── docs/                  ← Project documentation
│   ├── SETUP_SUMMARY.md   ← Full details of previous setup
│   ├── walkthrough.md     ← Walkthrough of implementation
│   ├── task.md            ← Checklist of completed tasks
│   └── implementation_plan.md  ← Original technical design plan
├── requirements.txt       ← Python dependencies
├── .gitignore             ← Files excluded from Git tracking
└── .env                   ← Environment keys (ignored)
```

---

## 🛠️ Setup Instructions

### 1. Pre-requisites
Make sure you have Python 3.10+ installed.

### 2. Set Up Virtual Environment
Clone this repository, then create and activate a virtual environment:
```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
Install all required packages from `requirements.txt`:
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Keys
Create a `.env` file in the root directory:
```env
GROQ_API_KEY=your_groq_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
MODEL_NAME=llama-3.3-70b-versatile
```

### 5. Obtain & Configure Google API OAuth Credentials
This project integrates with the **Gmail API** (via `gmail_client.py`) and the **Google Calendar API** (via `calendar_engine.py`). They both require Google OAuth 2.0 Desktop Application client secrets.

#### Step A: Download OAuth Secrets from Google Cloud
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a project (or select an existing one).
3. Enable the **Gmail API** and **Google Calendar API** in the API Library.
4. Set up the **OAuth Consent Screen**:
   - Choose User Type **External**.
   - Under **Scopes**, add `/auth/gmail.readonly`, `/auth/gmail.send`, `/auth/gmail.modify`, and `/auth/calendar`.
   - Add your email as a **Test User** (required while the app is in Testing mode).
5. Create Credentials:
   - Click **Create Credentials** -> **OAuth client ID**.
   - Select Application Type: **Desktop app**.
   - Name it, click **Create**, and download the JSON file.

#### Step B: Place Credentials for Gmail Integration
1. Save the downloaded JSON file as `gcp-oauth.keys.json`.
2. Place it in the `Gmail-MCP-Server/` directory at the project root:
   - File path: `Gmail-MCP-Server/gcp-oauth.keys.json`
3. *(Alternatively, you can place it in your user home directory at `~/.gmail-mcp/gcp-oauth.keys.json`)*

#### Step C: Place Credentials for Calendar Integration
1. Save the same downloaded JSON file as `credentials.json`.
2. Place it in the `data/` directory at the project root:
   - File path: `data/credentials.json`

#### Step D: Perform First-Time Authorization
The application will handle authorizing and caching your OAuth access/refresh tokens on first run.

1. Run the CLI agent to prompt the initial Gmail OAuth consent flow:
   ```bash
   python email_reply_agent.py
   ```
   A browser window will open asking you to sign in with your test Google account. Grant permissions. This will generate and save the Gmail user token to `~/.gmail-mcp/credentials.json`.
2. Start the Streamlit web dashboard to trigger the Google Calendar OAuth consent flow:
   ```bash
   streamlit run app.py
   ```
   When you use a calendar scheduling action, it will prompt an OAuth flow in the browser. Authorize it, and the calendar token will be automatically created and saved to `data/token.json`.

---

## 💻 Running the Applications

### Option A: The Streamlit Web Interface (Recommended)
Launch the beautiful review dashboard by running:
```bash
streamlit run app.py
```
This opens the app in your default browser at `http://localhost:8501`.

### Option B: The CLI Agent
Run a batch job in your terminal to process unread emails:
```bash
python email_reply_agent.py
```
Replies will be output in the console and saved to `output/email_replies_*.json` and `output/email_replies_*.txt` files.

---

You can easily adjust the ghostwriter to match your style by editing the JSON configuration files inside the `data/` directory:
1. **`data/tone_profile.json`**: Update your `name`, `role`, `company`, `formality`, and add specific writing habits or structure rules in `quirks` (e.g. *"Uses dashes — like this — for clarifications"*).
2. **`data/past_replies.json`**: Add 3-5 real examples of emails you have written. The LLM studies these to mimic your spacing, formatting, vocabulary, and length.

---

## 🔒 Security & Git Best Practices (Critical)

> [!WARNING]
> **Do NOT push credentials, tokens, or environment files to GitHub!**
> 
> The project uses a robust `.gitignore` file to ensure sensitive keys and tokens never leave your local machine.
> 
> Here are the sensitive resources that are **automatically ignored** and must NOT be committed to public repositories:
> 1. **`.env`**: Holds your raw API keys (`GROQ_API_KEY`, `GEMINI_API_KEY`).
> 2. **`Gmail-MCP-Server/`**: Contains the nested MCP codebase and your local `gcp-oauth.keys.json` client secrets.
> 3. **`data/credentials.json`**: Holds your Google Cloud OAuth client secrets for the calendar integration.
> 4. **`data/token.json`**: Holds your active Google Calendar user OAuth token.
> 5. **`data/approved_drafts.json`**: Holds local copies of draft responses, which might contain personal or business email content.
> 6. **`data/action_log.json`**: Holds logs of your actions which may contain personal info.
> 7. **`output/`**: Local email reply output logs.
> 8. **`venv/`**: Virtual environment directories.
> 
> **How credentials are managed securely:**
> * All active user Gmail OAuth session credentials (`credentials.json`) are stored outside this project directory in your user home folder (`~/.gmail-mcp/`).
> * The Google Calendar token (`token.json`) and client secrets (`credentials.json`) are kept under `data/`, which is ignored by Git.
> * The core code dynamically reads secrets from these paths or from secure environment variables, keeping secrets safely isolated from the code repository.

---

## 🌐 Deploying to Streamlit Cloud

To host your review dashboard on Streamlit Community Cloud (or any remote server), follow this secure authentication protocol:

### Step 1: Authenticate Locally First
Streamlit Cloud cannot prompt the interactive Google login screen. You must run the application locally first to generate the active tokens at:
- **Gmail Token**: `C:\Users\<Username>\.gmail-mcp\credentials.json` (Windows) or `~/.gmail-mcp/credentials.json` (Mac/Linux).
- **Calendar Token**: `data/token.json` in the project root.

### Step 2: Configure Streamlit Secrets
Copy the entire raw text content of these generated JSON files.
When setting up your app on Streamlit Cloud, go to **Settings** -> **Secrets**, and paste the secrets in TOML format:

```toml
GROQ_API_KEY = "gsk_your_actual_groq_api_key_here"
GEMINI_API_KEY = "AIzaSy_your_actual_gemini_api_key_here"
MODEL_NAME = "llama-3.3-70b-versatile"

# Paste the raw contents of ~/.gmail-mcp/credentials.json as a string
GMAIL_CREDENTIALS = '''
{
  "token": "...",
  "refresh_token": "...",
  "token_uri": "https://oauth2.googleapis.com/token",
  "client_id": "...",
  "client_secret": "...",
  "scopes": [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify"
  ],
  "expiry": "..."
}
'''

# Paste the raw contents of data/token.json as a string
CALENDAR_CREDENTIALS = '''
{
  "token": "...",
  "refresh_token": "...",
  "token_uri": "https://oauth2.googleapis.com/token",
  "client_id": "...",
  "client_secret": "...",
  "scopes": [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar"
  ],
  "expiry": "..."
}
'''
```

### Step 3: Deployment
Once these secrets are saved:
1. Deployed instances of `GmailClient` and `calendar_engine` automatically read the credential dictionaries from `st.secrets["GMAIL_CREDENTIALS"]` and `st.secrets["CALENDAR_CREDENTIALS"]` respectively.
2. They use the `refresh_token` to seamlessly fetch new access tokens from Google when they expire, requiring no manual login screens.
3. The app is fully operational and safe to share!

