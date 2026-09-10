# Burns Depression Checklist — 25 items, grouped into 4 categories.
# Wording and order are preserved exactly as specified.

CATEGORIES = [
    {
        "key": "thoughts",
        "name": "Thoughts & Feelings",
        "range": (1, 10),
    },
    {
        "key": "activities",
        "name": "Activities & Relationships",
        "range": (11, 17),
    },
    {
        "key": "physical",
        "name": "Physical Symptoms",
        "range": (18, 22),
    },
    {
        "key": "urges",
        "name": "Suicidal Urges",
        "range": (23, 25),
    },
]

QUESTIONS = [
    {"id": 1, "category": "thoughts", "text": "Feeling sad or down in the dumps"},
    {"id": 2, "category": "thoughts", "text": "Feeling unhappy or blue"},
    {"id": 3, "category": "thoughts", "text": "Crying spells or tearfulness"},
    {"id": 4, "category": "thoughts", "text": "Feeling discouraged"},
    {"id": 5, "category": "thoughts", "text": "Feeling hopeless"},
    {"id": 6, "category": "thoughts", "text": "Low self-esteem"},
    {"id": 7, "category": "thoughts", "text": "Feeling worthless or inadequate"},
    {"id": 8, "category": "thoughts", "text": "Guilt or shame"},
    {"id": 9, "category": "thoughts", "text": "Criticizing yourself or blaming yourself"},
    {"id": 10, "category": "thoughts", "text": "Difficulty making decisions"},

    {"id": 11, "category": "activities", "text": "Loss of interest in family, friends, or colleagues"},
    {"id": 12, "category": "activities", "text": "Loneliness"},
    {"id": 13, "category": "activities", "text": "Spending less time with family or friends"},
    {"id": 14, "category": "activities", "text": "Loss of motivation"},
    {"id": 15, "category": "activities", "text": "Loss of interest in work or other activities"},
    {"id": 16, "category": "activities", "text": "Avoiding work or other activities"},
    {"id": 17, "category": "activities", "text": "Loss of pleasure or satisfaction in life"},

    {"id": 18, "category": "physical", "text": "Feeling tired"},
    {"id": 19, "category": "physical", "text": "Difficulty sleeping or sleeping too much"},
    {"id": 20, "category": "physical", "text": "Decreased or increased appetite"},
    {"id": 21, "category": "physical", "text": "Loss of interest in sex"},
    {"id": 22, "category": "physical", "text": "Worrying about your health"},

    {"id": 23, "category": "urges", "text": "Do you have any suicidal thoughts?"},
    {"id": 24, "category": "urges", "text": "Would you like to end your life?"},
    {"id": 25, "category": "urges", "text": "Do you have a plan for harming yourself?"},
]

ANSWER_SCALE = [
    {"value": 0, "label": "Not at all"},
    {"value": 1, "label": "Somewhat"},
    {"value": 2, "label": "Moderately"},
    {"value": 3, "label": "A Lot"},
    {"value": 4, "label": "Extremely"},
]


def category_for(question_id: int) -> str:
    for q in QUESTIONS:
        if q["id"] == question_id:
            return q["category"]
    return ""


def category_name(key: str) -> str:
    for c in CATEGORIES:
        if c["key"] == key:
            return c["name"]
    return ""


SEVERITY_RANGES = [
    {"min": 0, "max": 5, "label": "No depression"},
    {"min": 6, "max": 10, "label": "Normal but unhappy"},
    {"min": 11, "max": 25, "label": "Mild depression"},
    {"min": 26, "max": 50, "label": "Moderate depression"},
    {"min": 51, "max": 75, "label": "Severe depression"},
    {"min": 76, "max": 100, "label": "Extreme depression"},
]


def severity_for(score: int) -> str:
    for r in SEVERITY_RANGES:
        if r["min"] <= score <= r["max"]:
            return r["label"]
    return "Unknown"


SEVERITY_TONE = {
    "No depression": {"text": "text-moss-600", "bg": "bg-moss-50", "border": "border-moss-100"},
    "Normal but unhappy": {"text": "text-moss-600", "bg": "bg-moss-50", "border": "border-moss-100"},
    "Mild depression": {"text": "text-amber", "bg": "bg-[#FBF3E3]", "border": "border-[#F0E0BC]"},
    "Moderate depression": {"text": "text-clay", "bg": "bg-[#FBEEE3]", "border": "border-[#F0D7BE]"},
    "Severe depression": {"text": "text-brick", "bg": "bg-[#FAEBE7]", "border": "border-[#EFCFC5]"},
    "Extreme depression": {"text": "text-maroon", "bg": "bg-[#F7E9E9]", "border": "border-[#E9C9C9]"},
}


def severity_tone(severity: str) -> dict:
    return SEVERITY_TONE.get(severity, {"text": "text-ink-soft", "bg": "bg-paper", "border": "border-line"})


def has_urgent_flags(answers: dict) -> bool:
    """True if any suicidal-urges question (23-25) has a non-zero answer."""
    return any(answers.get(i, 0) > 0 for i in (23, 24, 25))
