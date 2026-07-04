import os
import re
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# Global client
client = None
if os.getenv("GROQ_API_KEY"):
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def triage_thread(sender: str, subject: str, snippet: str, api_key: str = None) -> dict:
    prompt = f"""
    You are an intelligent email assistant helping triage an inbox.

    Given this email thread metadata, classify it:

    sender: {sender}
    subject: {subject}
    preview: {snippet}

    Respond in this exact format:
    Priority: <urgent | needs-reply | fyi | ignore>
    category: <one short tag like: meeting request, follow-up, newsletter, billing, job-app, social, admin, other>
    Reason: <one sentence explaining why>
    """
    
    local_client = None
    if api_key:
        local_client = Groq(api_key=api_key)
    else:
        local_client = client or (Groq(api_key=os.getenv("GROQ_API_KEY")) if os.getenv("GROQ_API_KEY") else None)
        
    if not local_client:
        raise ValueError("Groq API key not found. Please provide it or set GROQ_API_KEY env variable.")
        
    model_name = os.getenv('MODEL_NAME', 'llama-3.3-70b-versatile')
    
    response = local_client.chat.completions.create(
        messages=[
            {"role": "user", "content": prompt}
        ],
        model=model_name
    )
    
    return parse_triage_response(response.choices[0].message.content)

def parse_triage_response(text: str) -> dict:
    import re
    result = {
        'priority': 'unknown',
        'category': 'other',
        'reason': ''
    }
    
    if not text:
        return result
        
    # Check if format matches the bracket format (from disassembly regex)
    match = re.match(r'^\[([A-Za-z0-9-]+)\] \[([A-Za-z0-9-]+)\] .*? - (.*)$', text.strip())
    if match:
        result['priority'] = match.group(1).lower()
        result['category'] = match.group(2).lower()
        result['reason'] = match.group(3).strip().lower()
        return result
    
    for line in text.strip().split('\n'):
        if line.startswith('Priority:'):
            result['priority'] = line.replace('Priority:', '').strip().lower()
        elif line.startswith('category:'):
            result['category'] = line.replace('category:', '').strip().lower()
        elif line.startswith('Category:'):
            result['category'] = line.replace('Category:', '').strip().lower()
        elif line.startswith('Reason:'):
            result['reason'] = line.replace('Reason:', '').strip().lower()
        elif line.startswith('reason:'):
            result['reason'] = line.replace('reason:', '').strip().lower()
            
    return result

def triage_inbox(threads: list, api_key: str = None) -> list:
    triaged = []
    for thread in threads:
        sender_val = thread.get('from') or thread.get('sender') or 'Unknown'
        subject_val = thread.get('subject') or 'No Subject'
        snippet_val = thread.get('snippet') or (thread.get('messages', [{}])[-1].get('body', '')[:100] if thread.get('messages') else '')
        
        try:
            label = triage_thread(sender=sender_val, subject=subject_val, snippet=snippet_val, api_key=api_key)
        except Exception as e:
            print(f"⚠️ Error triaging thread '{subject_val}': {e}")
            label = {
                'priority': 'unknown',
                'category': 'other',
                'reason': f"Classification failed: {str(e)}"
            }
        
        combined = {**thread, **label}
        triaged.append(combined)
        
    priority_order = {'urgent': 0, 'needs-reply': 1, 'fyi': 2, 'ignore': 3, 'unknown': 4}
    triaged.sort(key=lambda x: priority_order.get(x.get('priority', 'unknown'), 4))
    return triaged

# Sample threads for test/main
sample_threads = [
    {'sender': 'john.doe@example.com', 'subject': 'Urgent: Server Down', 'snippet': 'The production server is down. Please respond immediately.'},
    {'sender': 'jane.smith@example.com', 'subject': 'Meeting Reminder', 'snippet': 'Just a reminder for our meeting tomorrow at 10 AM.'},
    {'sender': 'bob.jones@example.com', 'subject': 'Your Weekly Newsletter', 'snippet': 'Check out the latest news from our company.'},
    {'sender': 'marketing@example.com', 'subject': 'Promotional Offer', 'snippet': 'Exclusive discount just for you!'},
    {'sender': 'support@example.com', 'subject': 'Ticket #1234: Your recent inquiry', 'snippet': 'We have received your support request and will get back to you soon.'},
    {'sender': 'hr@example.com', 'subject': 'Action Required: Complete your annual review', 'snippet': 'Please complete your annual performance review by Friday.'},
    {'sender': 'github@example.com', 'subject': 'New pull request on your repository', 'snippet': 'A new pull request has been opened on your project.'}
]

if __name__ == '__main__':
    # Ensure GROQ_API_KEY is available when running directly
    if not os.getenv("GROQ_API_KEY"):
        print("⚠️ Warning: GROQ_API_KEY environment variable not set.")
    results = triage_inbox(sample_threads)
    for r in results:
        print(f"[{r['priority'].upper()}] [{r['category'].upper()}] {r['subject']} - {r['reason']}")
