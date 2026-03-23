"""Wonder SOPs — Staff Assistant CLI."""

import os
import sys

import anthropic

from loader import load_sops
from search import SOPIndex
from chat import build_context_block
from prompts import CLI_SYSTEM_PROMPT, MODEL

BANNER = """
╔══════════════════════════════════════════╗
║     Wonder SOPs — Staff Assistant        ║
║     Powered by Claude Haiku              ║
║     Type 'exit' or Ctrl+C to quit        ║
╚══════════════════════════════════════════╝
"""


def send_message(
    client: anthropic.Anthropic,
    history: list[dict],
    user_message: str,
    retrieved_sops: list,
) -> str:
    """Send a message to Claude with SOP context and stream the response."""
    context = build_context_block(retrieved_sops)
    augmented = f"{context}\n\nUser question: {user_message}"

    history.append({"role": "user", "content": augmented})
    trimmed = history[-100:] if len(history) > 100 else history

    full_response = ""
    with client.messages.stream(
        model=MODEL,
        system=CLI_SYSTEM_PROMPT,
        messages=trimmed,
        max_tokens=1024,
    ) as stream:
        for text in stream.text_stream:
            print(text, end="", flush=True)
            full_response += text

    history.append({"role": "assistant", "content": full_response})
    return full_response


def main():
    if not os.environ.get('ANTHROPIC_API_KEY'):
        print("Error: ANTHROPIC_API_KEY environment variable not set.")
        print("Set it with: export ANTHROPIC_API_KEY=your_key_here")
        sys.exit(1)

    print(BANNER)

    sops = load_sops()
    index = SOPIndex(sops)
    client = anthropic.Anthropic()
    history = []

    print()

    try:
        while True:
            try:
                user_input = input("You: ").strip()
            except EOFError:
                print("\nGoodbye!")
                break

            if not user_input:
                continue

            command = user_input.lower()

            if command in ('exit', 'quit'):
                print("Goodbye!")
                break

            if command == 'clear':
                history.clear()
                print("Conversation cleared.")
                continue

            if command == 'list':
                for sop in sops:
                    print(f"  {sop.id} — {sop.title}")
                continue

            retrieved = index.search(user_input)

            print("\nAssistant: ", end="", flush=True)
            try:
                send_message(client, history, user_input, retrieved)
            except Exception as e:
                print(f"\nError communicating with Claude: {e}")
                if history and history[-1]["role"] == "user":
                    history.pop()
                continue

            source_ids = ", ".join(sop.id for sop in retrieved)
            print(f"\n[Sources: {source_ids}]\n")

    except KeyboardInterrupt:
        print("\nGoodbye!")


if __name__ == '__main__':
    main()
