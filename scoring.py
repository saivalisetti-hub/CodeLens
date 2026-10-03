"""CodeLens scoring. The original 3-argument call still works."""


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def score_breakdown(maintainability, average_complexity, lines,
                    issues=None, docstring_coverage=100.0):
    """Return per-dimension scores (0-100) used by the radar chart."""
    issues = issues or []
    errors = sum(i["severity"] == "error" for i in issues)
    warnings = sum(i["severity"] == "warning" for i in issues)

    complexity = _clamp(100 - max(0, average_complexity - 3) * 9)
    size = _clamp(100 - max(0, lines - 200) * 0.15)
    cleanliness = _clamp(100 - errors * 15 - warnings * 6)

    return {
        "Maintainability": _clamp(maintainability),
        "Complexity": complexity,
        "Cleanliness": cleanliness,
        "Documentation": _clamp(docstring_coverage),
        "Size": size,
    }


def calculate_score(maintainability, average_complexity, lines,
                    issues=None, docstring_coverage=100.0):
    b = score_breakdown(maintainability, average_complexity, lines,
                        issues, docstring_coverage)
    weights = {"Maintainability": .35, "Complexity": .25, "Cleanliness": .25,
               "Documentation": .10, "Size": .05}
    return round(sum(b[k] * w for k, w in weights.items()))


def grade(score):
    for cutoff, letter in ((90, "A"), (80, "B"), (70, "C"), (60, "D")):
        if score >= cutoff:
            return letter
    return "F"