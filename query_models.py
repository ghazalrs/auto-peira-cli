#!/usr/bin/env python3
"""Send one prompt to a list of OpenRouter models, one at a time, with
interactive follow-up support in the same conversation thread.

Usage:
    python3 query_models.py [--prompt prompt.txt] [--models models.txt]

At each model:
  - The prompt is sent and the response is printed.
  - You can then either press Enter to move to the next model, or type a
    follow-up message (sent in the same conversation thread) to ask the
    model to fix/complete its answer.
  - Type 'skip' to abandon the current model and move on, or 'quit' to exit.

Copy/paste any output you want to keep yourself - this tool does not save
anything to disk.
"""

import argparse
import os
import sys

import requests

API_URL = "https://openrouter.ai/api/v1/chat/completions"


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


def run_conversation(api_key, model, prompt):
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

    while True:
        user_input = input(
            "Press Enter to move to the next model, type a follow-up "
            "message, 'skip' to abandon this model, or 'quit' to exit: "
        ).strip()

        if user_input == "":
            return
        if user_input.lower() == "skip":
            return
        if user_input.lower() == "quit":
            print("Exiting.")
            sys.exit(0)

        messages.append({"role": "user", "content": user_input})
        print("\n--- Sending follow-up ---")
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
    args = parser.parse_args()

    api_key = load_api_key()

    with open(args.prompt) as f:
        prompt = f.read().strip()
    if not prompt:
        sys.exit(f"Prompt file '{args.prompt}' is empty.")

    models = load_lines(args.models)
    if not models:
        sys.exit(f"Model list '{args.models}' contains no model IDs.")

    print(f"Loaded {len(models)} models from {args.models}")
    print(f"Prompt loaded from {args.prompt} ({len(prompt)} characters)")

    for model in models:
        run_conversation(api_key, model, prompt)

    print("\nAll models done.")


if __name__ == "__main__":
    main()
