# Wonder SOPs — Staff Assistant

A command-line chat assistant that answers Wonder Group / Infinite Kitchen staff questions using only the 645 Standard Operating Procedures.

## Setup

```bash
cd sop-chat
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key_here
```

## Usage

```bash
python main.py
```

Type your question at the `You:` prompt. The assistant will search the SOPs and stream an answer.

### Commands

- `exit` or `quit` — end the session
- `clear` — reset conversation history
- `list` — show all SOP IDs and titles

## Important

This assistant answers **only** from the 645 Wonder Group SOPs. It will not speculate, guess, or answer questions outside of what the SOPs cover.
