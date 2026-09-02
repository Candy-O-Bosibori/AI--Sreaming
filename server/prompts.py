# ============================================================
# prompts.py — System prompts for every Claude call in the app
# ============================================================
# Centralized here so main.py stays focused on routing/orchestration,
# not prompt text. Each constant is used in exactly one place — see
# the call sites in main.py for how context gets appended to these.
# ============================================================

SYSTEM_PROMPT_DEFAULT = (
    "Answer the user's question directly using only the information below. "
    "Do not say 'based on the context' or similar phrases — just answer. "
    "If the answer is not present, say so in one sentence."
)

SYSTEM_PROMPT_DEBATE = (
    "You will be given a document and a question. "
    "For any argument, claim, or position in the document relevant to the question, "
    "steelman BOTH the supporting and opposing positions with equal rigour. "
    "Present each side fairly before giving your own conclusion. "
    "Use only the information below — do not introduce outside knowledge."
)

SYSTEM_PROMPT_SUMMARY = (
    "Summarize the document below in 4-6 concise bullet points covering its main "
    "argument, key findings, and conclusions. Use only the information given."
)

SYSTEM_PROMPT_DISCUSSION_QUESTIONS = (
    "Generate 5 discussion questions a student could bring to a seminar/class "
    "discussion about the document below. Questions should probe assumptions, "
    "implications, and points of debate — not simple recall. "
    "Return ONLY a numbered list, one question per line."
)
