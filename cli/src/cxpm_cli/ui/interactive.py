from __future__ import annotations

from rich.prompt import Prompt


def ask_action(valid_actions: set[str]) -> str:
    while True:
        choice = Prompt.ask(f"Choose action [{'/'.join(sorted(valid_actions))}]").strip().lower()
        if choice in valid_actions:
            return choice
        print(f"Invalid action: {choice}")


def ask_multiline(prompt: str) -> str:
    print(prompt)
    print("Finish with a single line containing only 'END'.")
    lines: list[str] = []
    while True:
        line = input()
        if line.strip() == "END":
            break
        lines.append(line)
    return "\n".join(lines)
