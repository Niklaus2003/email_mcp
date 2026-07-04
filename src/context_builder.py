"""
Email reply drafting agent - Context builder module.
Assembles full prompt context including tone profile, past replies, and thread history.
"""

import json
from typing import Dict, List, Any
from datetime import datetime


def load_tone_profile(path: str = "data/tone_profile.json") -> Dict[str, Any]:
    """
    Load and return the tone profile dictionary.
    
    Args:
        path: Path to the tone profile JSON file
        
    Returns:
        Dictionary containing persona details, tone, and writing quirks
    """
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_past_replies(path: str = "data/past_replies.json") -> List[Dict[str, str]]:
    """
    Load and return list of past reply examples.
    
    Args:
        path: Path to the past replies JSON file
        
    Returns:
        List of past email examples with subject, to, and body
    """
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def format_thread_history(thread: Dict[str, Any]) -> str:
    """
    Format email thread into readable string showing conversation history.
    
    Args:
        thread: Dict with "subject" (str) and "messages" (list of {from, date, body})
        
    Returns:
        Formatted string representation of the thread
    """
    formatted = f"Subject: {thread.get('subject', 'No subject')}\n"
    formatted += "=" * 60 + "\n\n"
    
    messages = thread.get('messages', [])
    for i, msg in enumerate(messages, 1):
        sender = msg.get('from', 'Unknown')
        date = msg.get('date', 'Unknown date')
        body = msg.get('body', '')
        
        formatted += f"[{i}] From: {sender} ({date})\n"
        formatted += "-" * 40 + "\n"
        formatted += f"{body}\n\n"
    
    return formatted


def build_system_prompt(tone_profile: Dict[str, Any], past_replies: List[Dict[str, str]]) -> str:
    """
    Build the system prompt that defines persona and writing rules.
    
    Args:
        tone_profile: Tone profile dictionary with persona and rules
        past_replies: List of past email examples
        
    Returns:
        System prompt string for the LLM
    """
    name = tone_profile.get('name', 'Unknown')
    role = tone_profile.get('role', 'Professional')
    tone = tone_profile.get('tone', 'Professional')
    formality = tone_profile.get('formality', 'Formal')
    quirks = tone_profile.get('quirks', [])
    sign_off = tone_profile.get('sign_off', 'Best regards')
    
    prompt = f"""You are drafting an email reply as {name}, a {role}.

PERSONA:
- Name: {name}
- Role: {role}
- Communication tone: {tone}
- Formality level: {formality}
- Sign-off: {sign_off}

WRITING RULES & QUIRKS:
"""
    
    for i, quirk in enumerate(quirks, 1):
        prompt += f"{i}. {quirk}\n"
    
    prompt += "\nEXAMPLES OF PAST REPLIES:\n"
    prompt += "=" * 60 + "\n"
    
    # Include 2-3 past reply examples
    for reply in past_replies[:3]:
        to = reply.get('to', 'Recipient')
        subject = reply.get('subject', 'Re: Subject')
        body = reply.get('body', '')
        
        prompt += f"\nHere's how {name} writes:\n"
        prompt += f"To: {to}\n"
        prompt += f"Subject: {subject}\n"
        prompt += "-" * 40 + "\n"
        prompt += f"{body}\n"
    
    prompt += "\n" + "=" * 60 + "\n"
    prompt += "Now draft a reply to the incoming email thread below, matching this writing style.\n"
    
    return prompt


def build_user_prompt(thread_formatted: str) -> str:
    """
    Build the user message asking for a reply draft.
    
    Args:
        thread_formatted: Formatted thread history string
        
    Returns:
        User prompt string
    """
    user_prompt = f"""Please draft a professional email reply to the following thread:

{thread_formatted}

Requirements:
- Keep the reply concise and direct
- Match the tone and style shown in the examples above
- Use proper email etiquette
- End with an appropriate sign-off
- Only provide the email body, not headers

Draft the reply now:"""
    
    return user_prompt


def assemble_context(
    thread: Dict[str, Any],
    tone_path: str = "data/tone_profile.json",
    replies_path: str = "data/past_replies.json",
    tone_profile: Dict[str, Any] = None
) -> Dict[str, str]:
    """
    Main function: Load all components and assemble the full prompt context.
    
    Args:
        thread: Email thread dict with subject and messages
        tone_path: Path to tone profile JSON
        replies_path: Path to past replies JSON
        tone_profile: Optional tone profile dictionary (overrides loading from file)
        
    Returns:
        Dictionary with "system" and "user" keys containing the full prompt context
    """
    # Load all components
    if tone_profile is None:
        tone_profile = load_tone_profile(tone_path)
    past_replies = load_past_replies(replies_path)
    
    # Format the thread
    thread_formatted = format_thread_history(thread)
    
    # Build both prompts
    system_prompt = build_system_prompt(tone_profile, past_replies)
    user_prompt = build_user_prompt(thread_formatted)
    
    return {
        "system": system_prompt,
        "user": user_prompt
    }


if __name__ == "__main__":
    # Example usage
    sample_thread = {
        "subject": "Model performance review \u2014 next steps",
        "messages": [

            {
                "from": "Sarah Chen (ML Lead)",
                "date": "2026-06-15 10:30",
                "body": "Hi Aaron,\n\nThanks for running those model comparisons. The results look solid. Before we proceed to production, I want to make sure we have a solid evaluation framework in place.\n\nA few questions:\n1. How confident are we in the validation set?\n2. Have you tested on any of the edge cases we identified last month?\n3. What's the inference time looking like on the target hardware?\n\nLooking forward to your thoughts."
            },
            {
                "from": "You (Aaron Francis)",
                "date": "2026-06-15 14:45",
                "body": "Hi Sarah,\n\nGreat questions. Quick summary:\n\n1. Validation set is solid — we used stratified sampling to ensure representation across all key segments\n2. Tested on edge cases — performance holds up well except for one scenario with non-English text that we flagged for later\n3. Inference time is 120ms per record on the target hardware — well within our budget\n\nI've documented all the findings in the evaluation report. Can we sync this week to go through the methodology?\n\nBest regards, Aaron Francis"
            },
            {
                "from": "Sarah Chen (ML Lead)",
                "date": "2026-06-16 09:15",
                "body": "Excellent. Let's schedule a 30-minute sync — Thursday afternoon works for me. I want to make sure the team understands the approach before we move forward. Also, can you prepare a brief summary of the non-English text edge case? We may want to handle that separately."
            }
        ]
    }
    
    # Assemble the context
    context = assemble_context(sample_thread)
    
    print("\n" + "=" * 80)
    print("ASSEMBLED PROMPT CONTEXT")
    print("=" * 80)
    print("\n--- SYSTEM PROMPT ---\n")
    print(context["system"])
    print("\n--- USER PROMPT ---\n")
    print(context["user"])
    print("\n" + "=" * 80)
