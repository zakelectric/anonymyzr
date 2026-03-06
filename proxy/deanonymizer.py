"""
deanonymizer.py
---------------
Replaces synthetic values in LLM responses with the original real values.

Uses longest-match-first ordering to prevent partial replacement bugs.
Example: if "Daniel Park" and "Daniel" are both in the map, we must
replace "Daniel Park" before "Daniel" or we'd corrupt the longer match.
"""

from .mapper import mapper


def deanonymize(session_id: str, text: str) -> tuple[str, int]:
    """
    Swap all synthetic values back to their real counterparts.
    Safe against partial matches via longest-first replacement order.

    Returns:
        (deanonymized_text, count_of_replacements_made)
    """
    synthetic_to_real = mapper.get_all_synthetic_to_real(session_id)

    if not synthetic_to_real:
        return text, 0

    # Longest synthetic values first to avoid partial-match corruption
    ordered = sorted(synthetic_to_real.items(), key=lambda x: len(x[0]), reverse=True)

    swaps = 0
    for synthetic, real in ordered:
        if synthetic in text:
            text = text.replace(synthetic, real)
            swaps += 1

    return text, swaps


def deanonymize_content_blocks(session_id: str, content: list) -> tuple[list, int]:
    """
    Deanonymize Anthropic-format content block list.
    Only touches text blocks; passes tool_use and other blocks through untouched.

    Returns:
        (deanonymized_content_blocks, total_count_of_replacements_made)
    """
    result = []
    total_swaps = 0
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            block = dict(block)
            block["text"], swaps = deanonymize(session_id, block["text"])
            total_swaps += swaps
        result.append(block)
    return result, total_swaps
