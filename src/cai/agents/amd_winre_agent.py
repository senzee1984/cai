"""
AMD Windows Reverse Engineering Agent

Specialized agent for Windows binary analysis, vulnerability research,
and reverse engineering using Ghidra and supporting tools.
"""

import os
from dotenv import load_dotenv
from openai import AsyncOpenAI

from cai.sdk.agents import Agent, OpenAIChatCompletionsModel
from cai.util import load_prompt_template
from cai.agents.guardrails import get_security_guardrails

# Core tools
from cai.tools.reconnaissance.generic_linux_command import generic_linux_command
from cai.tools.reconnaissance.exec_code import execute_code

# Optional OSINT search (requires PERPLEXITY_API_KEY)
from cai.tools.web.search_web import make_web_search_with_explanation

load_dotenv()
model_name = os.getenv("CAI_MODEL", "alias1")

# Load prompt
amd_winre_system_prompt = load_prompt_template("prompts/amd_winre_agent.md")

# Assemble tools
tools = [
    generic_linux_command,  # Shell commands (ghidra_headless, r2, strings, file, etc.)
    execute_code,           # Python scripts for analysis automation
]

# Conditional: add web search helper when available
if os.getenv("PERPLEXITY_API_KEY"):
    tools.append(make_web_search_with_explanation)

# Security guardrails
input_guardrails, output_guardrails = get_security_guardrails()

# Instantiate agent
amd_winre_agent = Agent(
    name="AMD Windows RE Specialist",
    description=(
        "Agent specializing in Windows reverse engineering and vulnerability research. "
        "Analyzes PE binaries (.exe, .dll, .sys), kernel drivers, services, and .NET assemblies "
        "using Ghidra, radare2, and other RE tools. Focuses on security-relevant findings with "
        "evidence-based reporting."
    ),
    instructions=amd_winre_system_prompt,
    tools=tools,
    input_guardrails=input_guardrails,
    output_guardrails=output_guardrails,
    model=OpenAIChatCompletionsModel(
        model=model_name,
        openai_client=AsyncOpenAI(),
    ),
)


def transfer_to_amd_winre(**kwargs):
    """
    Handoff helper for swarm patterns.
    Accepts arbitrary kwargs for compatibility; returns the agent instance.
    """
    return amd_winre_agent
