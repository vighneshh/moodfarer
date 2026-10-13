REWIREMENTS = [
    {
        "key": "signature_strengths",
        "title": "Use Your Signature Strengths",
        "description": "Once you've identified your top strengths, try to use them in new ways every day for a week.",
        "type": "week",
        "notes_prompt": None,
        "has_strengths_list": True,
    },
    {
        "key": "savoring",
        "title": "Savoring",
        "description": "Pick one experience to truly savor each day — a nice shower, a good meal, a walk outside. Stay present, share it, and appreciate it fully.",
        "type": "week",
        "notes_prompt": "What did you savor today?",
    },
    {
        "key": "gratitude_journal",
        "title": "Daily Gratitude Journal",
        "description": "Each night, take 5-10 minutes to write down five things you're grateful for — big or small.",
        "type": "week",
        "notes_prompt": "Five things you're grateful for",
    },
    {
        "key": "kindness",
        "title": "Random Acts of Kindness",
        "description": "Perform at least one act of kindness beyond what you'd normally do — help a colleague, say something kind to a stranger, write a thank-you note.",
        "type": "week",
        "notes_prompt": "What kind act did you do?",
    },
    {
        "key": "social_connection",
        "title": "Social Connection",
        "description": "Make one new social connection per day — a quick chat with a stranger, checking in with a coworker, or a longer conversation with someone you care about.",
        "type": "week",
        "notes_prompt": "Who did you connect with?",
    },
    {
        "key": "exercise",
        "title": "Exercise",
        "description": "Get your body moving for at least 30 minutes a day — walk, dance, yoga, the gym, whatever works.",
        "type": "week",
        "notes_prompt": None,
    },
    {
        "key": "sleep",
        "title": "Sleep",
        "description": "Aim for at least 7 hours of sleep on at least 4 nights this week. Good sleep hygiene: no devices before bed, less caffeine and alcohol.",
        "type": "week",
        "notes_prompt": None,
        "target_days": 4,
    },
    {
        "key": "gratitude_letter",
        "title": "Gratitude Letter / Visit",
        "description": "Write a heartfelt letter (300+ words) to someone who made a big difference in your life but was never properly thanked. Then read it to them, ideally in person.",
        "type": "binary",
        "options": [
            {"key": "letter", "label": "Letter"},
            {"key": "visit", "label": "Visit"},
        ],
        "notes_prompt": None,
    },
]

WEEKDAY_KEYS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]
WEEKDAY_LABELS = {"sun": "Sun", "mon": "Mon", "tue": "Tue", "wed": "Wed", "thu": "Thu", "fri": "Fri", "sat": "Sat"}


def rewirement_for(key: str):
    for r in REWIREMENTS:
        if r["key"] == key:
            return r
    return None