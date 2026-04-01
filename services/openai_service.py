from __future__ import annotations

import os

from openai import OpenAI


SYSTEM_PROMPT = (
    "You are an internal operations assistant. Convert work requests into practical, "
    "clear execution guides for operations teams. Write concise but useful instructions."
)


def build_prompt(ticket: dict[str, str]) -> str:
    return f"""
Create a structured response for this internal ticket.

Ticket ID: {ticket['ticket_code']}
Title: {ticket['title']}
Requester: {ticket['requester']}
Department: {ticket['department']}
Urgency: {ticket['urgency']}
Category: {ticket['category']}
Request Description: {ticket['request_description']}
Desired Outcome: {ticket['desired_outcome']}

Return markdown with these headings exactly:
## Request Summary
## Task Type
## Step-by-Step Instructions
## Tools Needed
## Formula or Process Suggestions
## Things to Watch Out For
## Expected Output

Requirements:
- Use numbered steps under Step-by-Step Instructions.
- Keep it execution-focused and practical.
- Mention validation checks where relevant.
- If Excel/data task, include concrete formula patterns.
""".strip()


def generate_instructions(ticket: dict[str, str], model: str = "gpt-4.1-mini") -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return (
            "## Request Summary\nOpenAI API key is not configured.\n\n"
            "## Task Type\nConfiguration issue\n\n"
            "## Step-by-Step Instructions\n"
            "1. Set `OPENAI_API_KEY` in your environment.\n"
            "2. Restart Streamlit and click **Generate Instructions** again.\n\n"
            "## Tools Needed\nOpenAI API key\n\n"
            "## Formula or Process Suggestions\nN/A\n\n"
            "## Things to Watch Out For\nDo not expose API keys in source code.\n\n"
            "## Expected Output\nAI-generated work instructions for this ticket."
        )

    client = OpenAI(api_key=api_key)
    completion = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_prompt(ticket)},
        ],
        temperature=0.2,
    )
    return completion.output_text
