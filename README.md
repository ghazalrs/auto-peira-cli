# auto-peira-cli

A small command-line tool to send one prompt to a list of OpenRouter
models, one at a time, and interactively follow up with a model in the same
conversation thread if its response is incomplete or malformed.

It does not save anything to disk — copy/paste any output you want to keep.

## Setup

1. Create a virtual environment and install dependencies (already done if you
   ran this during initial setup):

   ```bash
   python3 -m venv venv
   ./venv/bin/pip install -r requirements.txt
   ```

2. Add your OpenRouter API key. Copy `.env.example` to `.env` and fill it in:

   ```bash
   cp .env.example .env
   # then edit .env:
   # OPENROUTER_API_KEY=sk-or-...
   ```

3. Fill in `models.txt` with your model IDs, one per line (`#` for comments):

   ```
   anthropic/claude-sonnet-4.6
   openai/gpt-4o
   google/gemini-2.5-pro
   ```

4. Put your research prompt in `prompt.txt`.

5. (Optional) Put a standard follow-up prompt in `followup_prompt.txt` —
   e.g. a feedback-request prompt you want to send to every model after
   its main response. Send it verbatim at any time by typing `f`. Leave
   the file empty/unused if you don't need this.

## Running

```bash
./venv/bin/python3 query_models.py
```

Optional flags:

```bash
./venv/bin/python3 query_models.py --prompt my_prompt.txt --models my_models.txt \
    --followup my_followup.txt --judge-model anthropic/claude-sonnet-4.6
```

Pass `--judge-model ''` to disable the Claude analysis feature (see below).

## How it works

For each model in `models.txt`, in order:

1. The prompt from `prompt.txt` is sent and the response is printed.
2. You're then prompted to:
   - press **Enter** to accept the response and move to the next model,
   - type a **follow-up message** (e.g. "You missed exercise 3, please
     provide a response to it") which is sent in the same conversation
     thread — the model sees its own prior answer and can correct or
     complete it without the original prompt being resent,
   - type **`f`** to send the standard follow-up prompt loaded from
     `followup_prompt.txt` verbatim (only shown if that file has content),
   - type **`a`** to have Claude analyze the response (see below),
   - type **`skip`** to abandon the current model and move on, or
   - type **`quit`** to exit the tool entirely.
3. Step 2 repeats until you accept or skip, then the tool moves to the next
   model.

Copy any response you want to keep directly from the terminal.

## Claude-assisted analysis (`a`)

Typing `a` sends the original prompt and the model's latest response to
Claude (via OpenRouter, model set by `--judge-model`, default
`anthropic/claude-sonnet-4.6`) for review. Claude checks the response
against the prompt's requirements and recommends ONE of:

- **Direct clean-up** — for minor mechanical issues (e.g. a missing
  bracket, stray comma, truncated line). Claude prints a corrected version
  of the response for you to copy; nothing is sent to the model.
- **Suggested follow-up** — for substantive issues (e.g. missing content,
  wrong structure). Claude drafts a short follow-up message. You can then
  type that suggestion (verbatim or edited), or your own message, at the
  prompt to send it to the model.
- **No action** — if the response already looks complete and correct.

Claude only *suggests* — you always decide what (if anything) to send.

After Claude has analyzed a response, you can type **`s`** to save that
analysis (original prompt, the model's response, Claude's assessment, the
recommended action, and the corrected text/follow-up message) to a markdown
file in `analysis/` (created automatically), named like
`<model>_<timestamp>.md`. This directory is git-ignored — copy out anything
you want to keep as part of your research record.
