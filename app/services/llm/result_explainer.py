"""Generate a plain-language explanation of portfolio risk results."""
from app.services.llm.client import chat


def explain_results(portfolio_name: str, results: dict) -> str:
    top_building_losses = sorted(
        results.get("building_losses", []),
        key=lambda item: item.get("gross_loss_kes", 0),
        reverse=True,
    )[:10]
    system = (
        "You are a catastrophe risk analyst. Explain flood risk results clearly "
        "for a non-technical insurance professional as a short, evidence-based story. "
        "Use KES amounts as provided. Do not invent data or describe a loss layer as "
        "covered unless the supplied insurance program says so."
    )
    user = (
        f"Portfolio: {portfolio_name}\n"
        f"Total Insured Value: KES {results['total_tiv_kes']:,.0f}\n"
        f"Total locations: {results['total_rows']}\n"
        f"Expected Annual Loss (EAL): KES {results['eal_total_kes']:,.0f}\n"
        f"EAL breakdown:\n"
        f"  Common (1-in-250yr):     KES {results['eal_common_kes']:,.0f}\n"
        f"  Occasional (1-in-100yr): KES {results['eal_occasional_kes']:,.0f}\n"
        f"  Moderate (1-in-50yr):  KES {results['eal_moderate_kes']:,.0f}\n"
        f"  Severe (1-in-20yr):   KES {results['eal_severe_kes']:,.0f}\n"
        f"  Extreme (1-in-10yr):  KES {results['eal_extreme_kes']:,.0f}\n"
        f"Exceedance curve: {results['exceedance_curve']}\n"
        f"Insurance program: {results['insurance_program']}\n"
        f"Ground-up and insured loss curve: {results['insurance_curve']}\n"
        f"Highest building losses: {top_building_losses}\n"
        f"Top exposed locations: {results['top_locations']}\n\n"
        "Tell the story in 4–6 short paragraphs: start with the portfolio's overall exposure, "
        "explain how damage ratio turns hazard into building loss, compare frequent and rare "
        "events using the EP curve, then explain deductible, limit, quota share, and catastrophe "
        "excess effects. Name the highest-loss buildings and finish with practical actions. "
        "Clearly distinguish ground-up loss, gross insured loss, quota-share net loss, and "
        "catastrophe excess loss."
    )
    return chat([{"role": "system", "content": system}, {"role": "user", "content": user}])
