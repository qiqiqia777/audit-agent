"""THE LOOP — observe → reason → act → repeat. This file is the whole trick.

Every agent framework is ultimately this while-loop with more indirection:

    while not done:
        response = llm(messages, tools)          # reason
        if response asks for tools:
            results = run(tool_calls)            # act
            messages += results                  # observe
        else:
            done                                 # reply to the human

End-loop guardrails (the orange box's exit conditions):
  1. the model stops asking for tools  → natural end of turn
  2. max_iterations reached            → hard stop, never spin forever
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Callable

import anthropic

from minihermes.tools.registry import ToolRegistry

# Observers let the gateway show tool calls live and let ops/tracing record
# them — without either being wired into the loop's logic.
LoopEvent = dict[str, Any]
Observer = Callable[[str, LoopEvent], None]


@dataclass
class LoopResult:
    reply: str
    tool_calls: list[LoopEvent] = field(default_factory=list)
    iterations: int = 0


class ToolArgumentsExhausted(ValueError):
    """Only local tool traces are safe to retain when JSON correction runs out."""

    def __init__(self, trace, iterations):
        super().__init__("Tool argument JSON correction or iteration budget exhausted")
        self.diagnostics = {"trace": trace, "iterations": iterations}
        self.failure_class = type(self).__name__


def _validate_wire_arguments(response):
    for block in response.content:
        if getattr(block, "argument_error", None):
            json.loads(block.raw_arguments)


def run_loop(
    client: anthropic.Anthropic,
    model: str,
    system: str,
    messages: list[dict],
    tools: ToolRegistry,
    max_iterations: int = 10,
    max_tokens: int = 2048,
    observer: Observer | None = None,
    stream: bool = False,
    max_json_corrections: int | None = None,
    stop_after_tool: str | None = None,
) -> LoopResult:
    """Run one agent turn. `messages` is mutated in place — after the call it
    contains the full working memory of the turn (assistant thoughts, tool
    calls, tool results), which is exactly what gets traced.

    stream=True emits the assistant's text as it's generated (notify("text",
    {"delta": ...})) so a gateway can show it appear token by token — used by
    the dashboard. Falls back to a single call for clients without streaming."""
    notify = observer or (lambda kind, ev: None)
    result = LoopResult(reply="")
    can_stream = stream and hasattr(client.messages, "stream")
    json_errors = 0

    for iteration in range(1, max_iterations + 1):
        result.iterations = iteration

        # ---- reason: one LLM call with the current working memory
        response = None
        if can_stream:
            try:
                with client.messages.stream(
                    model=model, system=system, messages=messages,
                    tools=tools.schemas(), max_tokens=max_tokens,
                ) as s:
                    for delta in s.text_stream:
                        notify("text", {"delta": delta})
                    response = s.get_final_message()
                    if max_json_corrections is None:
                        _validate_wire_arguments(response)
            except Exception:
                response = None  # any streaming hiccup → fall back to one call
        if response is None:
            response = client.messages.create(
                model=model,
                system=system,
                messages=messages,
                tools=tools.schemas(),
                max_tokens=max_tokens,
            )
        notify("llm", {"iteration": iteration, "stop_reason": response.stop_reason,
                       "usage": {"in": response.usage.input_tokens, "out": response.usage.output_tokens}})

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if max_json_corrections is None:
            # The original adapter rejected a whole malformed batch before any
            # side effects. Preserve that boundary for callers without recovery.
            _validate_wire_arguments(response)

        # the assistant's turn (text and/or tool requests) joins working memory
        messages.append({"role": "assistant", "content": response.content})

        # ---- guardrail 1: no tool calls → the model is talking to the human
        if not tool_uses:
            result.reply = "".join(b.text for b in response.content if b.type == "text")
            return result

        # ---- act: execute each requested tool; observe: feed results back
        tool_results = []
        for call in tool_uses:
            argument_error = getattr(call, "argument_error", None)
            if argument_error:
                json_errors += 1
                output = (
                    f"Error: {call.name} arguments are invalid JSON: {argument_error}. "
                    "This call was not executed. Regenerate the complete arguments as a JSON object; "
                    "do not repeat tools that already succeeded. "
                    f"Correction {json_errors}/{max_json_corrections}; original iteration budget applies."
                )
            else:
                output = tools.execute(call.name, call.input)
            event = {"tool": call.name, "args": call.input, "output": output}
            if argument_error:
                event.update(raw_arguments=call.raw_arguments, argument_error=argument_error)
            result.tool_calls.append(event)
            notify("tool", event)
            if argument_error and json_errors > max_json_corrections:
                raise ToolArgumentsExhausted(result.tool_calls, iteration)
            if call.name == stop_after_tool and not output.startswith("Error"):
                # This caller has a terminal tool: do not ask for, or execute,
                # additional calls after its accepted result.
                return result
            tool_results.append(
                {"type": "tool_result", "tool_use_id": call.id, "content": output}
            )
        messages.append({"role": "user", "content": tool_results})

    # ---- guardrail 2: ran out of iterations
    result.reply = "(I hit my iteration limit before finishing — try breaking the request into smaller steps.)"
    return result
