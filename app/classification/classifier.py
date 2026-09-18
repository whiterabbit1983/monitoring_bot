import re
from dataclasses import dataclass, field

from app.classification.categories import CATEGORIES, GEO_PATTERNS


@dataclass
class CategoryMatch:
    category_id: str
    title: str
    emoji: str
    score: float
    matched_patterns: list[str] = field(default_factory=list)
    has_geo: bool = False


def normalize(text: str) -> str:
    return text.lower().strip().replace("\u0451", "\u0435")


def detect_geo(norm_text: str) -> bool:
    return any(re.search(p, norm_text) for p in GEO_PATTERNS)


def classify(
    text: str,
    *,
    min_score: float = 3.0,
    geo_required: bool = False,
    geo_bonus: float = 2.0,
) -> list[CategoryMatch]:
    norm = normalize(text)
    has_geo = detect_geo(norm)

    results: list[CategoryMatch] = []
    for cat in CATEGORIES:
        if any(re.search(np_, norm) for np_ in cat.negative_patterns):
            continue

        matched: list[str] = []
        score = 0.0
        for pattern, weight in cat.patterns:
            if re.search(pattern, norm):
                matched.append(pattern)
                score += weight

        if not matched:
            continue
        if geo_required and not has_geo:
            continue
        if has_geo:
            score += geo_bonus
        if score < min_score:
            continue

        results.append(
            CategoryMatch(
                category_id=cat.id,
                title=cat.title,
                emoji=cat.emoji,
                score=round(score, 2),
                matched_patterns=matched,
                has_geo=has_geo,
            )
        )

    results.sort(key=lambda m: m.score, reverse=True)
    return results