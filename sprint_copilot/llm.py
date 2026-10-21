"""
llm.py — the single place Sprint Copilot talks to a language model.

Uses Azure OpenAI. Unlike plain OpenAI, Azure needs an endpoint, an api
version, and — importantly — you pass your *deployment name* where you'd
normally pass a model name. All of that comes from .env:

    AZURE_OPENAI_ENDPOINT      https://<your-resource>.openai.azure.com
    AZURE_OPENAI_API_KEY       the key from the Azure resource
    AZURE_OPENAI_DEPLOYMENT    the deployment you created (e.g. "gpt-5" or "gpt-4o-mini")
    AZURE_OPENAI_API_VERSION   e.g. 2025-04-01-preview

Everything else in Sprint Copilot calls llm(system, user) and doesn't care
which provider is behind it — so swapping providers later touches only this
file.
"""

import os

# Reasoning models (gpt-5, o1, o3, o4 ...) "think" before they answer.
# They use different settings than classic chat models like gpt-4o.
_REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")


def _is_reasoning_model(deployment: str) -> bool:
    return deployment.lower().startswith(_REASONING_PREFIXES)


# Connect to Azure OpenAI with settings from .env
def _client():
    from openai import AzureOpenAI
    return AzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"),
    )


# The ONE place that talks to the AI. Switch provider = change only this file
def llm(system: str, user: str, max_tokens: int = 800, temperature: float = 0.3) -> str:
    """Send one system+user prompt, return the model's text reply."""
    client = _client()
    # On Azure you pass your deployment name, not the model name
    deployment = os.environ["AZURE_OPENAI_DEPLOYMENT"]

    # system = the AI's job description and rules, user = the actual task and data
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    if _is_reasoning_model(deployment):
        # Reasoning models: no custom temperature, and the token limit is called
        # max_completion_tokens. It also covers the hidden "thinking", so give extra room.
        response = client.chat.completions.create(
            model=deployment,
            messages=messages,
            max_completion_tokens=max(max_tokens * 4, 2000),
        )
    else:
        # Classic chat models: low temperature (0.3) = factual, not creative
        response = client.chat.completions.create(
            model=deployment,
            messages=messages,
            max_tokens=max_tokens,  # maximum length of the answer
            temperature=temperature,
        )
    return (response.choices[0].message.content or "").strip()


if __name__ == "__main__":
    from pathlib import Path
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
    print(llm("You are a test.", "Reply with exactly: ok"))