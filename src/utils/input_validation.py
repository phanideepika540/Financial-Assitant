def validate_question(question: str, max_characters: int) -> str:
    cleaned = question.strip()
    if not cleaned:
        raise ValueError("Please enter a question.")
    if len(cleaned) > max_characters:
        raise ValueError(f"Please keep your question under {max_characters} characters.")
    return cleaned


def build_goal_planning_question(
    goal: str,
    time_horizon: str = "",
    target_amount: str = "",
    current_savings: str = "",
    monthly_contribution: str = "",
) -> str:
    cleaned_goal = goal.strip()
    if not cleaned_goal:
        raise ValueError("Enter a goal to start a planning conversation.")

    details = [f"Help me think through this financial goal for educational purposes: {cleaned_goal}."]
    if time_horizon.strip():
        details.append(f"My approximate time horizon is {time_horizon.strip()}.")
    if target_amount.strip():
        details.append(f"My approximate target amount is {target_amount.strip()}.")
    if current_savings.strip():
        details.append(f"I have already saved approximately {current_savings.strip()}.")
    if monthly_contribution.strip():
        details.append(
            f"I may be able to contribute approximately {monthly_contribution.strip()} per month."
        )
    details.append(
        "Explain relevant planning considerations and questions to think about. "
        "Keep this general education: do not recommend specific investments or "
        "promise outcomes."
    )
    return " ".join(details)
