"""
Email reply drafting machine using Groq API.
Generates authentic email replies based on context, tone profile, and past replies.
"""

import os
import sys
import json
from typing import Dict, Any
from dotenv import load_dotenv
from groq import Groq

# Force UTF-8 encoding for standard output on Windows to support emojis/unicode
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from context_builder import assemble_context


# Load environment variables
load_dotenv()


def get_drafting_rules() -> str:
    """
    Return the drafting rules that constrain the email generation.
    
    Returns:
        String with drafting constraints for the LLM
    """
    rules = """
DRAFTING RULES (CRITICAL - FOLLOW EXACTLY):

1. ONE-ASK RULE: Every email has exactly ONE clear question OR ONE clear response/decision.
   - Do not include multiple unrelated asks or requests.
   - If there are multiple topics, prioritize the most important one.
   - Example of ONE ASK: "Can we move the deadline to Friday?" OR "I recommend we proceed with option A."

2. LENGTH CONTROL: Match the energy of the thread, maximum 5 sentences.
   - Use numbered points (1, 2, 3) if you need to list items.
   - Each point should be one sentence max.
   - Keep sentences punchy and direct.

3. NO AI FILLER: Never use these phrases:
   - "I hope this email finds you well"
   - "Thank you for reaching out"
   - "I appreciate your message"
   - "Looking forward to hearing from you"
   - Any other generic corporate fluff

4. STRUCTURE: Follow this pattern exactly:
   - ACKNOWLEDGE: Brief one-line acknowledgment of their point
   - RESPONSE: Your main response/answer
   - ONE NEXT STEP: A single, clear next step or question
   
   Example structure:
   "Acknowledge point. [Details/analysis]. [Clear next step]."

5. SIGN-OFF: Always end with "Best regards, Aaron Francis" or match the tone profile's sign-off.

6. NO EXPLANATIONS: Return ONLY the email draft body. No meta-commentary, no "Subject:" line, no preamble.
"""
    return rules


def draft_reply(
    thread: Dict[str, Any],
    api_key: str = None,
    tone_profile: Dict[str, Any] = None,
    guidance: str = None
) -> str:
    """
    Generate an email reply draft for the given thread.
    
    Args:
        thread: Email thread dict with subject and messages
        api_key: Optional Groq API key (defaults to environment variable GROQ_API_KEY)
        tone_profile: Optional tone profile dictionary override
        guidance: Optional specific guidance/instructions for the draft
        
    Returns:
        Draft email text (body only, no headers)
        
    Raises:
        ValueError: If GROQ_API_KEY is not configured
        Exception: If Groq API call fails
    """
    key = api_key or os.getenv("GROQ_API_KEY")
    if not key:
        raise ValueError(
            "GROQ_API_KEY not found. Please set it in your .env file or enter it in the app.\n"
            "Example: GROQ_API_KEY=gsk_your-api-key-here"
        )
    
    model_name = os.getenv("MODEL_NAME", "llama-3.3-70b-versatile")
    
    # Assemble the context from thread
    context = assemble_context(thread, tone_profile=tone_profile)
    system_prompt = context["system"]
    user_prompt = context["user"]
    
    # If custom guidance is provided, append it to user prompt to steer reply
    if guidance and guidance.strip():
        user_prompt += f"\n\nAdditional Guidance for this specific reply:\n- {guidance.strip()}"
    
    # Get drafting rules
    rules = get_drafting_rules()
    
    # Initialize Groq Client
    try:
        client = Groq(api_key=key)
        
        # Combine system prompt with rules
        combined_system = f"{system_prompt}\n\n{rules}"
        
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": combined_system},
                {"role": "user", "content": user_prompt}
            ]
        )
        draft = response.choices[0].message.content.strip()
        return draft
    except Exception as e:
        raise Exception(f"Failed to generate reply with Groq ({model_name}): {str(e)}")


def draft_reply_with_metadata(
    thread: Dict[str, Any],
    api_key: str = None,
    tone_profile: Dict[str, Any] = None,
    guidance: str = None
) -> Dict[str, Any]:
    """
    Generate an email reply draft with metadata about the generation.
    
    Args:
        thread: Email thread dict with subject and messages
        api_key: Optional Groq API key
        tone_profile: Optional tone profile dictionary override
        guidance: Optional specific guidance/instructions for the draft
        
    Returns:
        Dictionary containing:
        - draft: The generated email reply text
        - model: Model name used (e.g. llama-3.3-70b-versatile)
        - subject: Original thread subject
        - replying_to: The most recent sender in the thread
    """
    # Get the draft
    draft = draft_reply(thread, api_key=api_key, tone_profile=tone_profile, guidance=guidance)
    
    # Extract metadata
    subject = thread.get("subject", "Unknown")
    messages = thread.get("messages", [])
    replying_to = messages[-1].get("from", "Unknown") if messages else "Unknown"
    
    model_name = os.getenv("MODEL_NAME", "llama-3.3-70b-versatile")
    
    return {
        "draft": draft,
        "model": model_name,
        "subject": subject,
        "replying_to": replying_to
    }



if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("EMAIL REPLY DRAFT MACHINE (GROQ)")
    print("=" * 80)
    
    # Check for API key
    test_key = os.getenv("GROQ_API_KEY")
    if not test_key:
        print("\n[ERROR] GROQ_API_KEY not found!")
        print("\nPlease create a .env file in this directory with:")
        print("  GROQ_API_KEY=your-groq-key-here")
        exit(1)
    
    print("\n[OK] API Key loaded successfully")
    
    # Sample thread (AI/ML focused, matching Aaron Francis's role)
    sample_thread = {
        "subject": "Q3 Budget Review \u2014 Model Training Infrastructure",
        "messages": [
            {
                "from": "Director of ML (James Wu)",
                "date": "2026-06-16 08:00",
                "body": "Aaron,\n\nWe're reviewing Q3 budgets and need to finalize the ML infrastructure spend. The team is considering two options:\n\n1. Upgrade our current setup (cheaper, less flexible)\n2. Migrate to cloud-based training (higher cost but scales better)\n\nWhat's your technical take? Which direction do you recommend for our model development roadmap?"
            },
            {
                "from": "You (Aaron Francis)",
                "date": "2026-06-16 14:30",
                "body": "Hi James,\n\nGreat question. Both have trade-offs. Let me break down what I'm seeing:\n\n1. On-prem upgrade: Good for predictable workloads, lower ongoing costs, but we'd hit scaling limits by Q4 when we add new datasets\n2. Cloud migration: Higher initial setup, but gives us elasticity and reduces our ops burden significantly\n\nGiven our roadmap (sentiment analysis expansion + multi-language support), I'd lean toward cloud for the flexibility. I've drafted a technical comparison doc \u2014 want to review it together?\n\nBest regards, Aaron Francis"
            },
            {
                "from": "Director of ML (James Wu)",
                "date": "2026-06-17 09:00",
                "body": "Makes sense. The flexibility angle is compelling. Before I take this to the finance committee, can you put together a quick cost projection for both scenarios? I need hard numbers \u2014 ideally a 6-month and 12-month breakdown.\n\nHow much time do you need?"
            }
        ]
    }
    
    print("\n" + "-" * 80)
    print("GENERATING REPLY...")
    print("-" * 80)
    
    try:
        # Generate reply with metadata
        result = draft_reply_with_metadata(sample_thread)
        
        print(f"\nThread Subject: {result['subject']}")
        print(f"Replying to: {result['replying_to']}")
        print(f"Model: {result['model']}")
        print("\n" + "=" * 80)
        print("GENERATED DRAFT")
        print("=" * 80)
        print(f"\n{result['draft']}")
        print("\n" + "=" * 80)
        
    except ValueError as e:
        print(f"\n[ERROR] Configuration Error: {e}")
        exit(1)
    except Exception as e:
        print(f"\n[ERROR] Error generating reply: {e}")
        exit(1)
