"""
deanonymizer.py
---------------
Replaces synthetic values in LLM responses with the original real values.

Uses longest-match-first ordering to prevent partial replacement bugs.
Example: if "Daniel Park" and "Daniel" are both in the map, we must
replace "Daniel Park" before "Daniel" or we'd corrupt the longer match.
"""

from .mapper import mapper


def deanonymize(session_id: str, text: str) -> str:
    """
    Swap all synthetic values back to their real counterparts.
    Safe against partial matches via longest-first replacement order.
    """
    synthetic_to_real = mapper.get_all_synthetic_to_real(session_id)

    if not synthetic_to_real:
        return text

    # Longest synthetic values first to avoid partial-match corruption
    ordered = sorted(synthetic_to_real.items(), key=lambda x: len(x[0]), reverse=True)

    for synthetic, real in ordered:
        text = text.replace(synthetic, real)

    return text


def deanonymize_content_blocks(session_id: str, content: list) -> list:
    """
    Deanonymize Anthropic-format content block list.
    Only touches text blocks; passes tool_use and other blocks through untouched.
    """
    result = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            block = dict(block)
            block["text"] = deanonymize(session_id, block["text"])
        result.append(block)
    return result
