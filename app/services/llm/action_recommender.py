"""Recommend risk mitigation actions based on portfolio results."""
from app.services.llm.client import chat


def recommend_actions(portfolio_name: str, results: dict) -> list[dict]:
    """Return a list of {priority, action, rationale} dicts."""
    system = (
        "You are a catastrophe risk consultant. Given flood risk results, "
        "return a JSON array of up to 6 recommended actions. "
        "Each item must have: priority (High/Medium/Low), action (short title), "
        "rationale (one sentence). Return only valid JSON, no markdown."
    )
    user = (
        f"Portfolio: {portfolio_name}\n"
        f"EAL total: KES {results['eal_total_kes']:,.0f}\n"
        f"TIV: KES {results['total_tiv_kes']:,.0f}\n"
        f"Top locations: {results['top_locations']}\n"
        "Suggest practical risk mitigation actions."
    )
    import json
    raw = chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.4,
    )
    try:
        actions = json.loads(raw)
        if isinstance(actions, list):
            return actions
    except (json.JSONDecodeError, ValueError):
        pass
    return [{"priority": "High", "action": "Manual review required", "rationale": raw[:200]}]
