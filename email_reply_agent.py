"""
Email Reply Agent - Main Orchestration Script
Reads emails from Gmail, triages them, and generates AI-powered replies.
"""

import os
import sys
import json
from datetime import datetime
from typing import List, Dict, Any
from pathlib import Path
from dotenv import load_dotenv

# Force UTF-8 encoding for standard output on Windows to support emojis/unicode
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Add src folder to sys.path
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from context_builder import assemble_context
from draft_machine import draft_reply_with_metadata
from gmail_client import GmailClient


# Load environment variables
load_dotenv()


class EmailReplyAgent:
    """
    Main orchestrator that reads emails, triages them, and generates replies.
    """
    
    def __init__(self, output_dir: str = "output"):
        """
        Initialize the email reply agent.
        
        Args:
            output_dir: Directory where generated replies will be saved
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.results = []
        
    def load_sample_thread(self) -> Dict[str, Any]:
        """
        Load a sample email thread for demonstration.
        
        Returns:
            Sample thread dict
        """
        return {
            "subject": "Q3 Budget Review — Model Training Infrastructure",
            "messages": [
                {
                    "from": "Director of ML (James Wu)",
                    "date": "2026-06-16 08:00",
                    "body": "Aaron,\n\nWe're reviewing Q3 budgets and need to finalize the ML infrastructure spend. The team is considering two options:\n\n1. Upgrade our current setup (cheaper, less flexible)\n2. Migrate to cloud-based training (higher cost but scales better)\n\nWhat's your technical take? Which direction do you recommend for our model development roadmap?"
                },
                {
                    "from": "You (Aaron Francis)",
                    "date": "2026-06-16 14:30",
                    "body": "Hi James,\n\nGreat question. Both have trade-offs. Let me break down what I'm seeing:\n\n1. On-prem upgrade: Good for predictable workloads, lower ongoing costs, but we'd hit scaling limits by Q4 when we add new datasets\n2. Cloud migration: Higher initial setup, but gives us elasticity and reduces our ops burden significantly\n\nGiven our roadmap (sentiment analysis expansion + multi-language support), I'd lean toward cloud for the flexibility. I've drafted a technical comparison doc — want to review it together?\n\nBest regards, Aaron Francis"
                },
                {
                    "from": "Director of ML (James Wu)",
                    "date": "2026-06-17 09:00",
                    "body": "Makes sense. The flexibility angle is compelling. Before I take this to the finance committee, can you put together a quick cost projection for both scenarios? I need hard numbers — ideally a 6-month and 12-month breakdown.\n\nHow much time do you need?"
                }
            ]
        }
    
    def load_threads_from_json(self, json_file: str) -> List[Dict[str, Any]]:
        """
        Load email threads from a JSON file.
        
        Expected format:
        [
            {
                "subject": "...",
                "messages": [
                    {"from": "...", "date": "...", "body": "..."},
                    ...
                ]
            },
            ...
        ]
        
        Args:
            json_file: Path to JSON file containing threads
            
        Returns:
            List of thread dicts
        """
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"[WARN] File not found: {json_file}")
            return []
        except json.JSONDecodeError:
            print(f"[WARN] Invalid JSON in: {json_file}")
            return []
    
    def load_threads_from_txt(self, txt_file: str) -> List[Dict[str, Any]]:
        """
        Load email threads from a text file (empty or simple format).
        Returns sample threads if file is empty.
        
        Args:
            txt_file: Path to text file
            
        Returns:
            List of thread dicts
        """
        try:
            with open(txt_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    print(f"[INFO] {txt_file} is empty. Using sample thread for demo.")
                    return [self.load_sample_thread()]
        except FileNotFoundError:
            pass
        
        return [self.load_sample_thread()]
    
    def generate_reply_for_thread(self, thread: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate an AI reply for a single email thread.
        
        Args:
            thread: Email thread dict
            
        Returns:
            Dict with thread info and generated reply
        """
        try:
            print(f"\n  Processing: {thread['subject']}")
            if 'priority' in thread:
                print(f"  Triage: [{thread['priority'].upper()}] [{thread['category'].upper()}] - {thread['reason']}")
            result = draft_reply_with_metadata(thread)
            
            res_dict = {
                "success": True,
                "subject": thread['subject'],
                "replying_to": result['replying_to'],
                "draft": result['draft'],
                "model": result['model'],
                "timestamp": datetime.now().isoformat()
            }
            if 'priority' in thread:
                res_dict.update({
                    "priority": thread['priority'],
                    "category": thread['category'],
                    "reason": thread['reason']
                })
            return res_dict
        except ValueError as e:
            return {
                "success": False,
                "subject": thread['subject'],
                "error": str(e)
            }
        except Exception as e:
            return {
                "success": False,
                "subject": thread['subject'],
                "error": f"Failed to generate reply: {str(e)}"
            }
    
    def process_threads(self, threads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Process multiple email threads and generate replies.
        
        Args:
            threads: List of email threads
            
        Returns:
            List of results with generated replies
        """
        print(f"\nProcessing {len(threads)} thread(s)...")
        
        self.results = []
        for i, thread in enumerate(threads, 1):
            print(f"\n[{i}/{len(threads)}]", end="")
            result = self.generate_reply_for_thread(thread)
            self.results.append(result)
        
        return self.results
    
    def save_results(self, format_type: str = "json") -> str:
        """
        Save generated replies to a file.
        
        Args:
            format_type: 'json' or 'txt'
            
        Returns:
            Path to saved file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if format_type == "json":
            filename = f"email_replies_{timestamp}.json"
            filepath = self.output_dir / filename
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.results, f, indent=2, ensure_ascii=False)
            
            print(f"\nResults saved to: {filepath}")
            return str(filepath)
        
        elif format_type == "txt":
            filename = f"email_replies_{timestamp}.txt"
            filepath = self.output_dir / filename
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("=" * 80 + "\n")
                f.write("EMAIL REPLY GENERATION RESULTS\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 80 + "\n\n")
                
                for i, result in enumerate(self.results, 1):
                    f.write(f"\n[{i}] Subject: {result['subject']}\n")
                    f.write("-" * 80 + "\n")
                    
                    if result['success']:
                        f.write(f"Replying to: {result['replying_to']}\n")
                        f.write(f"Model: {result['model']}\n")
                        f.write(f"\nDraft:\n{result['draft']}\n")
                    else:
                        f.write(f"[ERROR] Error: {result['error']}\n")
                    
                    f.write("\n")
            
            print(f"\nResults saved to: {filepath}")
            return str(filepath)
    
    def display_results(self):
        """
        Display generated replies in the console.
        """
        print("\n" + "=" * 80)
        print("GENERATED EMAIL REPLIES")
        print("=" * 80)
        
        for i, result in enumerate(self.results, 1):
            print(f"\n[{i}] Subject: {result['subject']}")
            print("-" * 80)
            
            if result['success']:
                print(f"Replying to: {result['replying_to']}")
                print(f"Model: {result['model']}")
                print(f"\n{result['draft']}")
            else:
                print(f"[ERROR] Error: {result['error']}")
            
            print()
        
        print("=" * 80)
        print(f"[OK] Processed {len(self.results)} thread(s)")
        print("=" * 80)


def main():
    """Main entry point for the email reply agent."""
    
    print("\n" + "=" * 80)
    print("AARON FRANCIS - EMAIL REPLY AGENT")
    print("AI-Powered Gmail Reply Generation")
    print("=" * 80)
    
    # Check for API key
    if not os.getenv("GROQ_API_KEY"):
        print("\n[ERROR] GROQ_API_KEY not found in .env file")
        print("\nTo use this agent, add your Groq API key to .env:")
        print("  GROQ_API_KEY=your-api-key-here")
        return
    
    print("[OK] Groq API Key loaded")
    
    # Initialize agent
    agent = EmailReplyAgent(output_dir="output")
    
    # Try to load threads from Gmail first
    print("\nLoading email threads...")
    threads = []
    source = None
    
    # Try Gmail
    try:
        print("   Connecting to Gmail...")
        gmail_client = GmailClient()
        print("   [OK] Gmail authenticated")
        
        threads = gmail_client.get_inbox_threads(max_results=5, query="is:unread")
        
        if threads:
            source = "Gmail (unread)"
            print(f"   [OK] Loaded {len(threads)} unread thread(s) from Gmail")
        else:
            print("   No unread emails in Gmail")
            # Try all emails
            threads = gmail_client.get_inbox_threads(max_results=5, query="is:inbox")
            if threads:
                source = "Gmail (all inbox)"
                print(f"   [OK] Loaded {len(threads)} thread(s) from Gmail inbox")
    
    except FileNotFoundError as e:
        print(f"   [WARN] Gmail not configured: {e}")
    except Exception as e:
        print(f"   [WARN] Gmail error: {e}")
    
    # Fallback to JSON if Gmail not available
    if not threads:
        if os.path.exists("data/threads.json"):
            threads = agent.load_threads_from_json("data/threads.json")
            source = "data/threads.json"
            print(f"   [OK] Loaded {len(threads)} thread(s) from data/threads.json")
        elif os.path.exists("email.txt"):
            threads = agent.load_threads_from_txt("email.txt")
            source = "email.txt"
            print(f"   [OK] Loaded {len(threads)} thread(s) from email.txt")
        else:
            threads = [agent.load_sample_thread()]
            source = "Sample"
            print("   Using sample thread for demonstration")
    
    if not threads:
        print("\n[ERROR] No email threads available")
        return
    
    print(f"\nSource: {source}")
    
    # Triage email threads
    if os.getenv("GROQ_API_KEY"):
        try:
            from triage import triage_inbox
            print("\nTriaging email threads...")
            threads = triage_inbox(threads)
            print("✓ Triage completed and sorted by priority")
        except Exception as e:
            print(f"\n[WARN] Triage failed: {e}")
            
    # Process threads
    agent.process_threads(threads)
    
    # Display results
    agent.display_results()
    
    # Save results
    agent.save_results(format_type="json")
    agent.save_results(format_type="txt")
    
    print("\n" + "=" * 80)
    print("[OK] Email reply generation complete!")
    print(f"   Results saved to: {agent.output_dir}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
