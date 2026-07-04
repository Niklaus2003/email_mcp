# Implementation Plan - Human-in-the-Loop Approval Gate with Gmail MCP

This plan outlines the design and implementation details for building `approval_gate.py`, a Streamlit application that acts as a human-in-the-loop review and approval gate for an AI email ghostwriter. The app will fetch actual email threads from your Gmail inbox using your Gmail API credentials, generate replies using the Groq API, and let you approve, edit, or discard drafts before they are sent.

We will build a highly creative, professional, and visually stunning user interface that leverages custom CSS, premium typography, modern glassmorphism layouts, and smooth transition animations to deliver an outstanding experience.

## User Review Required

> [!IMPORTANT]
> 1. **Direct Send Action:** We plan to add a toggle "Send email via Gmail upon approval" in the Streamlit app. If checked, clicking "Approve" will send the email reply using the Gmail API (via `gmail_client.py`). If unchecked, it will only write to `approved_drafts.json` as "ready to send".
> 2. **Gmail API Update:** To reply to a specific message, we need to know its `message_id`. We will modify `gmail_client.py`'s thread formatting to include `last_message_id` in the thread dictionary.

## Open Questions

> [!NOTE]
> 1. Since we are connecting directly to your live Gmail account, what should the default search query be? We plan to default to `is:unread` so you can review incoming unread emails, but we will provide a text field in the sidebar to change this query (e.g. `is:inbox`, `from:boss`, etc.).
> 2. For `approved_drafts.json`, we will format it as a list of JSON objects containing the thread ID, subject, final draft, timestamp, and whether it was successfully sent. Let us know if you want any additional fields saved.

## Proposed Changes

---

### [Component Name] Gmail Client Integration

We will modify the Gmail client helper to return message IDs so the app can reply to the correct message in a thread.

#### [MODIFY] [gmail_client.py](file:///c:/Users/AaronFrancis/Desktop/vscode/research/AI_agent_workshop/June_cohort_MCP/Chief_of_staff/gmail_client.py)
- Update `_format_thread(self, thread_id: str)` to:
  - Store the Gmail message `id` in each message's formatted dictionary.
  - Return the `last_message_id` as part of the thread dictionary:
    ```python
    return {
        "subject": subject,
        "thread_id": thread_id,
        "last_message_id": messages[-1]['id'] if messages else None,
        "messages": formatted_messages,
        "from": formatted_messages[-1].get('from', 'Unknown'),
        "snippet": messages[-1].get('snippet', '')
    }
    ```

---

### [Component Name] Groq-Based Drafting Logic

We will modify the drafting logic to run with the Groq API and support passing the API key dynamically from Streamlit.

#### [MODIFY] [draft_machine.py](file:///c:/Users/AaronFrancis/Desktop/vscode/research/AI_agent_workshop/June_cohort_MCP/Chief_of_staff/draft_machine.py)
- Import `groq.Groq` instead of `google.genai`.
- Refactor `draft_reply` to:
  - Initialize the `Groq` client using the provided `api_key` parameter (or fall back to `os.environ` / `st.secrets`).
  - Read `MODEL_NAME` from environment (defaulting to `llama-3.3-70b-versatile`).
  - Send the system prompt and user prompt to Groq's chat completions API:
    ```python
    client = Groq(api_key=api_key)
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt + "\n" + rules},
            {"role": "user", "content": user_prompt}
        ]
    )
    draft = response.choices[0].message.content.strip()
    ```
- Update `draft_reply_with_metadata` to accept `api_key` and pass it to `draft_reply`.

---

### [Component Name] Streamlit Approval Gate Application

We will build the Streamlit frontend with a premium dark-themed layout and integration with Gmail and Groq.

#### [NEW] [approval_gate.py](file:///c:/Users/AaronFrancis/Desktop/vscode/research/AI_agent_workshop/June_cohort_MCP/Chief_of_staff/approval_gate.py)
- **Imports:** Import from `gmail_client.py`, `context_builder.py`, and `draft_machine.py`.
- **API Key Handling:**
  - Check `st.secrets` for `GROQ_API_KEY`, then check `os.environ`.
  - If not found, show a password input field in the sidebar.
- **Gmail Integration in Sidebar:**
  - Initialize `GmailClient`. If OAuth keys/credentials are missing, show a clear setup card.
  - Query Input field (default: `is:unread`) and Max Results slider (default: 5).
  - "Fetch Emails" button.
  - Dropdown menu containing fetched threads, showing `Subject (From: Sender)`.
  - Fallback option: A text area to paste custom thread JSON if the user wants to test offline.
- **Visual Design & Aesthetics (Premium CSS Inject):**
  - **Typography:** Load `Outfit` or `Inter` Google fonts.
  - **Background & Theme:** Theme base is dark with `#0f0f1b` background, utilizing smooth radial gradients (`radial-gradient(circle, #1a1a36 0%, #0c0c16 100%)`).
  - **Glassmorphism:** Render cards with semi-transparent backgrounds (`rgba(255,255,255,0.03)`), blurred backdrops, and thin border glows (`1px solid rgba(255,255,255,0.08)`).
  - **Thread Message Cards:** Alternating side bubbles. Messages from other users show up on the left with a subtle blue/violet glow. Messages from "You" show up on the right with a subtle slate/teal glow.
  - **Status Badges:** Animated pulse lights for statuses (Green pulse for `"Approved"`, Red pulsing border for `"Rejected"`, Yellow/Amber pulsing glow for `"Editing"`).
  - **Hover Micro-Animations:** Standard buttons will have a smooth hover zoom and background transition.
- **Main Layout (layout="wide"):**
  - **Left Column (Thread History):** Beautiful conversational thread displaying headers, dates, and bodies inside custom glass cards.
  - **Right Column (Drafting Area):**
    - Large glass card with glowing borders showing the AI-generated draft.
    - If no draft is loaded, prompts user to click "Generate Draft".
    - "Generate Draft" button.
- **Action Buttons & State Management:**
  - Track `st.session_state` for:
    - `current_draft`: holds the text of the generated reply.
    - `status`: one of `"none"`, `"approved"`, `"editing"`, `"rejected"`.
    - `selected_thread_dict`: the current thread data.
    - `generation_count`: tracker to force update.
    - `edited_draft`: temporary buffer for manual edits.
  - Action buttons below the draft:
    - **APPROVE:**
      - Saves the draft to `approved_drafts.json` with timestamp.
      - If "Send to Gmail on approval" toggle is checked, calls `gmail_client.send_reply` using `thread_id` and `last_message_id`.
      - Displays a green success banner and sets status to `"approved"`.
    - **EDIT:** Sets status to `"editing"`, displays a `st.text_area` pre-populated with the draft text, and displays a "Save and Approve Edited Draft" button. Also displays a "Cancel Edit" button.
    - **REJECT / DISCARD:** Discards the current draft, sets status to `"rejected"`, shows a red status confirmation, and allows regenerating a new draft.

---

## Verification Plan

### Automated Tests
- Run `.\venv\Scripts\python.exe -m streamlit run approval_gate.py` to test the application.

### Manual Verification
- **Visual Check:** Verify the typography, colors, animations, glassmorphism containers, and pulsing badges look beautiful and professional.
- **Gmail Connectivity:** Confirm the app successfully fetches your inbox threads using `GmailClient`.
- **Draft Generation:** Verify Groq API is called with the compiled thread history and tone rules.
- **Approve and Send:**
  - Verify writing to `approved_drafts.json`.
  - Check the toggle behavior: verify email is actually sent to Gmail when checked.
- **Edit & Approve:** Edit draft, save, verify the edited version is saved/sent.
- **Reject & Regenerate:** Discard a draft, verify red status, regenerate, and verify a new draft is generated.
