#!/usr/bin/env python3
"""Send one prompt to a list of OpenRouter models, one at a time, with
interactive follow-up support in the same conversation thread.

Usage:
    python3 query_models.py [--prompt prompt.txt] [--models models.txt]
                            [--followup followup_prompt.txt]
                            [--judge-model anthropic/claude-sonnet-4.6]

At each model:
  - The prompt is sent and the response is printed.
  - You can then either press Enter to move to the next model, type a
    follow-up message (sent in the same conversation thread) to ask the
    model to fix/complete its answer, type 'f' to send the standard
    follow-up prompt loaded from --followup verbatim, type 'a' to have
    Claude analyze the response and suggest a fix, type 'skip' to abandon
    the current model and move on, or 'quit' to exit.

Copy/paste any output you want to keep yourself - this tool does not save
anything to disk.
"""

import argparse
import datetime
import os
import re
import sys

import requests

API_URL = "https://openrouter.ai/api/v1/chat/completions"
ANALYSIS_DIR = "analysis"

JUDGE_INSTRUCTIONS = """\
You are helping a researcher review an AI model's response to a research \
prompt, and decide what (if anything) needs fixing.

ORIGINAL PROMPT SENT TO THE MODEL:
---
{prompt}
---

THE MODEL'S RESPONSE:
---
{response}
---

Assess whether the response fully and correctly satisfies the prompt's \
requirements (completeness, structure/format, etc), then choose ONE action:

- CLEANUP: the response is substantively fine but has a minor, mechanical \
issue (e.g. a missing bracket, stray comma, truncated last line, broken \
formatting) you can fix yourself by lightly editing the text without \
changing its substance. Provide the full corrected response.
- FOLLOWUP: the response has a substantive issue (e.g. missing content, \
ignored instructions, wrong structure) that the model itself needs to \
address. Draft a short, 1-2 sentence follow-up request to send back to the \
model. Do not repeat any part of the original prompt.
- NONE: the response already looks complete and correctly formatted.

Respond in EXACTLY this format (including the literal labels), with nothing \
before or after:

ACTION: <CLEANUP|FOLLOWUP|NONE>
ASSESSMENT: <one or two sentence explanation of your judgment>
RESULT:
<if ACTION is CLEANUP: the full corrected response text>
<if ACTION is FOLLOWUP: the follow-up message to send>
<if ACTION is NONE: leave this section empty>
"""


def parse_judge_output(text):
    action_match = re.search(r"ACTION:\s*(CLEANUP|FOLLOWUP|NONE)", text, re.IGNORECASE)
    assessment_match = re.search(r"ASSESSMENT:\s*(.+)", text)
    result_match = re.search(r"RESULT:\s*\n?(.*)", text, re.DOTALL)

    action = action_match.group(1).upper() if action_match else "NONE"
    assessment = assessment_match.group(1).strip() if assessment_match else ""
    result = result_match.group(1).strip() if result_match else ""
    return action, assessment, result


def load_api_key():
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key

    # Fall back to a local .env file with a line like OPENROUTER_API_KEY=sk-...
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("OPENROUTER_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")

    sys.exit(
        "No OpenRouter API key found. Set the OPENROUTER_API_KEY environment "
        "variable, or create a .env file in this directory containing:\n"
        "OPENROUTER_API_KEY=sk-..."
    )


def load_lines(path):
    with open(path) as f:
        lines = [line.strip() for line in f]
    return [line for line in lines if line and not line.startswith("#")]


def send_message(api_key, model, messages):
    response = requests.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={"model": model, "messages": messages},
        timeout=300,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


def analyze_response(api_key, judge_model, prompt, response_text):
    judge_messages = [
        {"role": "user", "content": JUDGE_INSTRUCTIONS.format(prompt=prompt, response=response_text)}
    ]
    judge_reply = send_message(api_key, judge_model, judge_messages)
    return parse_judge_output(judge_reply)


def save_analysis(model, prompt, response_text, action, assessment, result):
    os.makedirs(ANALYSIS_DIR, exist_ok=True)
    now = datetime.datetime.now()
    safe_model = model.replace("/", "_").replace(":", "_")
    filename = f"{safe_model}_{now.strftime('%Y%m%d_%H%M%S')}.md"
    path = os.path.join(ANALYSIS_DIR, filename)

    content = f"""# Claude's analysis for {model}

**Date:** {now.isoformat(timespec="seconds")}

## Original prompt

{prompt}

## Model's response

{response_text}

## Claude's assessment

{assessment}

## Recommended action: {action}

{result}
"""
    with open(path, "w") as f:
        f.write(content)
    return path


def run_conversation(api_key, model, prompt, standard_followup=None, judge_model=None):
    messages = [{"role": "user", "content": prompt}]

    print(f"\n{'=' * 70}\nMODEL: {model}\n{'=' * 70}")
    print("\n--- Sending prompt ---")

    try:
        reply = send_message(api_key, model, messages)
    except requests.exceptions.RequestException as exc:
        print(f"\n[ERROR] Request to {model} failed: {exc}")
        return

    messages.append({"role": "assistant", "content": reply})
    print(f"\n--- Response from {model} ---\n{reply}\n")

    last_analysis = None

    while True:
        prompt_text = (
            "Press Enter to move to the next model, type a follow-up "
            "message, 'skip' to abandon this model, or 'quit' to exit"
        )
        if standard_followup:
            prompt_text += ", or 'f' to send the standard follow-up prompt"
        if judge_model:
            prompt_text += ", or 'a' to have Claude analyze this response"
        if last_analysis:
            prompt_text += ", or 's' to save Claude's last analysis to a markdown file"
        user_input = input(prompt_text + ": ").strip()

        if user_input == "":
            return
        if user_input.lower() == "skip":
            return
        if user_input.lower() == "quit":
            print("Exiting.")
            sys.exit(0)

        if user_input.lower() == "a" and judge_model:
            print("\n--- Asking Claude to analyze the response ---")
            try:
                action, assessment, result = analyze_response(api_key, judge_model, prompt, reply)
            except requests.exceptions.RequestException as exc:
                print(f"\n[ERROR] Analysis request failed: {exc}")
                continue

            last_analysis = {
                "model": model,
                "prompt": prompt,
                "response_text": reply,
                "action": action,
                "assessment": assessment,
                "result": result,
            }

            print(f"\nClaude's assessment: {assessment}")
            if action == "CLEANUP":
                print(
                    "\nRecommended action: direct clean-up. Corrected response "
                    f"(copy this yourself if you want to use it):\n\n{result}\n"
                )
            elif action == "FOLLOWUP":
                print(
                    "\nRecommended action: send a follow-up so the model fixes "
                    f"its own answer. Suggested message:\n\n{result}\n"
                    "\n(Type this, an edited version, or your own message at the "
                    "prompt below to send it as a follow-up.)"
                )
            else:
                print("\nRecommended action: none — the response already looks complete and correctly formatted.")
            continue

        if user_input.lower() == "s" and last_analysis:
            path = save_analysis(**last_analysis)
            print(f"\nSaved Claude's analysis to {path}\n")
            continue

        if user_input.lower() == "f" and standard_followup:
            followup_message = standard_followup
            print("\n--- Sending standard follow-up prompt ---")
        else:
            followup_message = user_input
            print("\n--- Sending follow-up ---")

        messages.append({"role": "user", "content": followup_message})
        try:
            reply = send_message(api_key, model, messages)
        except requests.exceptions.RequestException as exc:
            print(f"\n[ERROR] Follow-up request to {model} failed: {exc}")
            continue

        messages.append({"role": "assistant", "content": reply})
        print(f"\n--- Response from {model} ---\n{reply}\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", default="prompt.txt", help="Path to the prompt text file")
    parser.add_argument("--models", default="models.txt", help="Path to the model list file")
    parser.add_argument(
        "--followup",
        default="followup_prompt.txt",
        help="Path to an optional standard follow-up prompt file (sent via 'f')",
    )
    parser.add_argument(
        "--judge-model",
        default="anthropic/claude-sonnet-4.6",
        help="OpenRouter model ID Claude analysis runs on (sent via 'a'); pass '' to disable",
    )
    args = parser.parse_args()

    api_key = load_api_key()

    with open(args.prompt) as f:
        prompt = f.read().strip()
    if not prompt:
        sys.exit(f"Prompt file '{args.prompt}' is empty.")

    models = load_lines(args.models)
    if not models:
        sys.exit(f"Model list '{args.models}' contains no model IDs.")

    standard_followup = None
    if os.path.exists(args.followup):
        with open(args.followup) as f:
            text = f.read().strip()
        if text:
            standard_followup = text

    judge_model = args.judge_model.strip() or None

    print(f"Loaded {len(models)} models from {args.models}")
    print(f"Prompt loaded from {args.prompt} ({len(prompt)} characters)")
    if standard_followup:
        print(f"Standard follow-up loaded from {args.followup} (send with 'f')")
    if judge_model:
        print(f"Response analysis enabled via {judge_model} (trigger with 'a')")

    for model in models:
        run_conversation(api_key, model, prompt, standard_followup, judge_model)

    print("\nAll models done.")


if __name__ == "__main__":
    main()
