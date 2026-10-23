import math
from typing import Literal

from fastmcp import FastMCP

# Initialize the server with a descriptive name
mcp = FastMCP("Pizza-Ops 🍕")


@mcp.tool()
def calculate_pizza_payload(
    attendees: int, duration_hours: float, hunger_index: Literal["snackish", "standard", "hackathon_mode"] = "standard"
) -> str:
    """
    Computes the total number of pizza slices and boxes required for a meeting.

    Args:
        attendees: Number of people attending the meeting.
        duration_hours: Length of the meeting in hours.
        hunger_index: Appetite level ('snackish', 'standard', 'hackathon_mode').
    """
    # Base slices per person mapped to appetite
    base_slices = {"snackish": 2, "standard": 3, "hackathon_mode": 5}[hunger_index]

    # Apply a 10% duration buffer per hour of meeting length
    duration_multiplier = 1.0 + (duration_hours * 0.1)
    total_slices = attendees * base_slices * duration_multiplier

    # Standard large pizza has 8 slices
    pizzas_needed = math.ceil(total_slices / 8)

    # Witty contextual commentary for the agent
    commentary = ""
    if hunger_index == "hackathon_mode":
        commentary = "\n⚠️ Warning: Impending food coma detected. Ensure afternoon code reviews are canceled."
    elif hunger_index == "snackish":
        commentary = "\nNote: This is a light snack order. Beware of grazing managers stealing slices."

    return (
        f"📊 Pizza Allocation Report:\n"
        f"- Total Slices Required: {total_slices:.1f}\n"
        f"- Total Pizza Boxes to Order: {pizzas_needed}\n"
        f"{commentary}"
    )


@mcp.tool()
def optimize_topping_distribution(team_preferences: list[str], dietary_restrictions: list[str]) -> str:
    """
    Resolves office ordering conflicts by mapping dietary needs and preferences.

    Args:
        team_preferences: List of favorite toppings (e.g., ['pepperoni', 'margherita'])
        dietary_restrictions: List of restrictions (e.g., ['vegan', 'gluten-free'])
    """
    veg_count = sum(1 for r in dietary_restrictions if r.lower() in ["vegan", "vegetarian"])
    gf_count = sum(1 for r in dietary_restrictions if r.lower() in ["gluten-free", "gf"])

    report = ["🎯 Optimized Topping Matrix:"]

    if gf_count > 0:
        report.append(f"- {gf_count}x Dedicated Gluten-Free Base (Keep isolated to prevent cross-contamination)")
    if veg_count > 0:
        report.append(f"- {veg_count + 1}x Vegetarian/Vegan Options (e.g., Margherita or Veggie Supreme)")

    # Tally up standard favorites
    pref_counts = {}
    for pref in team_preferences:
        pref_counts[pref] = pref_counts.get(pref, 0) + 1

    sorted_prefs = sorted(pref_counts.items(), key=lambda x: x[1], reverse=True)
    if sorted_prefs:
        top_pref = sorted_prefs[0][0]
        report.append(f"- Remainder allocated to top request: {top_pref.capitalize()}")
    else:
        report.append("- Remainder allocated to standard crowd-pleasers (Pepperoni / BBQ Chicken).")

    return "\n".join(report)


@mcp.resource("pizza-ops://config/cheatsheet")
def get_cheatsheet() -> str:
    """The unwritten universal truths of corporate pizza distribution."""
    return (
        "1. Always round UP. A leftover slice is cold breakfast; a missing slice is a riot.\n"
        "2. The Introvert Variable: Assume introverts eat 1.5x what they claim out loud.\n"
        "3. The Free Pizza Effect: People who claim they aren't hungry will eat 2 slices if it's free."
    )


if __name__ == "__main__":
    mcp.run()
