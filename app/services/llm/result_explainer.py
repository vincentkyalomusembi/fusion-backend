"""Generate a plain-language explanation of portfolio risk results."""
from app.services.llm.client import chat


def explain_results(portfolio_name: str, results: dict) -> str:
    system = (
        "You are a catastrophe risk analyst. Explain flood risk results clearly "
        "for a non-technical insurance professional. Be concise (3–5 paragraphs). "
        "Use KES amounts as provided. Do not invent data."
    )
    user = (
        f"Portfolio: {portfolio_name}\n"
        f"Total Insured Value: KES {results['total_tiv_kes']:,.0f}\n"
        f"Total locations: {results['total_rows']}\n"
        f"Expected Annual Loss (EAL): KES {results['eal_total_kes']:,.0f}\n"
        f"EAL breakdown:\n"
        f"  Common (1-in-5yr):     KES {results['eal_common_kes']:,.0f}\n"
        f"  Occasional (1-in-20yr): KES {results['eal_occasional_kes']:,.0f}\n"
        f"  Moderate (1-in-50yr):  KES {results['eal_moderate_kes']:,.0f}\n"
        f"  Severe (1-in-100yr):   KES {results['eal_severe_kes']:,.0f}\n"
        f"  Extreme (1-in-250yr):  KES {results['eal_extreme_kes']:,.0f}\n"
        f"Exceedance curve: {results['exceedance_curve']}\n"
        f"Top exposed locations: {results['top_locations']}\n\n"
        "Explain what these results mean, highlight the key risk drivers, "
        "and note any locations that warrant attention."
    )
    return chat([{"role": "system", "content": system}, {"role": "user", "content": user}])
