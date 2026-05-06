#!/usr/bin/env python3
import io
import json
import subprocess
import sys
from collections import defaultdict

from PIL import Image, ImageEnhance, ImageFilter

try:
    import ddddocr
except Exception as error:  # pragma: no cover - surfaced to caller as JSON
    ddddocr = None
    IMPORT_ERROR = str(error)
else:
    IMPORT_ERROR = ""

EXPECTED_LENGTH = 4
FILTER_SETS = [
    None,
    ["purple", "blue"],
    ["purple"],
    ["red", "purple"],
    ["green"],
    ["green", "purple"],
]


def normalize_text(text):
    return "".join(
        character
        for character in (text or "").strip()
        if character.isascii() and character.isalnum()
    )


def make_variants(image):
    base_2x = image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)
    base_4x = image.resize((image.width * 4, image.height * 4), Image.Resampling.LANCZOS)
    width = image.width
    return {
        "orig": image,
        "sharp2x": ImageEnhance.Sharpness(base_2x).enhance(2.0),
        "contrast2x": ImageEnhance.Contrast(base_2x).enhance(1.5),
        "cropL4": image.crop((4, 0, width, image.height)),
        "cropL6": image.crop((6, 0, width, image.height)),
        "cropR4": image.crop((0, 0, max(1, width - 4), image.height)),
        "detail4x": base_4x.filter(ImageFilter.DETAIL),
    }


def length_bucket(text):
    length = len(text)
    if length == EXPECTED_LENGTH:
        return 3
    if length in {EXPECTED_LENGTH - 1, EXPECTED_LENGTH + 1}:
        return 2
    if length:
        return 1
    return 0


def candidate_weight(text, confidence, variant_name, filters):
    weight = float(confidence or 0.0)
    bucket = length_bucket(text)
    if bucket == 3:
        weight += 0.35
    elif bucket == 2:
        weight += 0.08
    if variant_name in {"sharp2x", "contrast2x", "detail4x"}:
        weight += 0.02
    if filters:
        weight += 0.01 * len(filters)
    return weight


def is_subsequence(shorter, longer):
    if len(shorter) >= len(longer):
        return False

    index = 0
    for character in longer:
        if index < len(shorter) and shorter[index] == character:
            index += 1
    return index == len(shorter)


def encode_png_bytes(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def run_ddddocr(image):
    if ddddocr is None:
        return []

    ocr = ddddocr.DdddOcr(show_ad=False)
    candidates = []
    for variant_name, variant in make_variants(image).items():
        for filters in FILTER_SETS:
            try:
                result = ocr.classification(
                    variant,
                    probability=True,
                    color_filter_colors=filters,
                )
            except Exception:
                continue

            text = normalize_text(result.get("text", ""))
            if not text:
                continue

            confidence = float(result.get("confidence") or 0.0)
            candidates.append(
                {
                    "text": text,
                    "confidence": confidence,
                    "variant": variant_name,
                    "filters": filters or [],
                    "engine": "ddddocr",
                    "weight": candidate_weight(text, confidence, variant_name, filters),
                }
            )

    return candidates


def run_tesseract(image):
    candidates = []
    whitelist = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    variants = {
        "tess-4x": image.resize((image.width * 4, image.height * 4), Image.Resampling.LANCZOS),
        "tess-sharp2x": ImageEnhance.Sharpness(
            image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)
        ).enhance(2.0),
    }

    for variant_name, variant in variants.items():
        payload = encode_png_bytes(variant)
        process = subprocess.run(
            [
                "tesseract",
                "stdin",
                "stdout",
                "--psm",
                "8",
                "-c",
                f"tessedit_char_whitelist={whitelist}",
            ],
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        text = normalize_text(process.stdout.decode("utf-8", errors="ignore"))
        if not text:
            continue

        candidates.append(
            {
                "text": text,
                "confidence": 0.0,
                "variant": variant_name,
                "filters": [],
                "engine": "tesseract",
                "weight": candidate_weight(text, 0.0, variant_name, []),
            }
        )

    return candidates


def group_candidates(candidates):
    exact_grouped = defaultdict(
        lambda: {
            "text": "",
            "score": 0.0,
            "confidence": 0.0,
            "count": 0,
            "engines": set(),
            "sources": [],
        }
    )

    for candidate in candidates:
        key = candidate["text"]
        entry = exact_grouped[key]
        entry["text"] = candidate["text"]
        entry["score"] += candidate["weight"]
        entry["confidence"] = max(entry["confidence"], candidate["confidence"])
        entry["count"] += 1
        entry["engines"].add(candidate["engine"])
        entry["sources"].append(
            {
                "engine": candidate["engine"],
                "variant": candidate["variant"],
                "filters": candidate["filters"],
                "confidence": candidate["confidence"],
            }
        )

    exact_ranked = []
    for entry in exact_grouped.values():
        exact_ranked.append(
            {
                "text": entry["text"],
                "score": round(entry["score"], 6),
                "confidence": round(entry["confidence"], 6),
                "count": entry["count"],
                "engines": sorted(entry["engines"]),
                "sources": entry["sources"],
            }
        )

    canonical_grouped = defaultdict(
        lambda: {
            "canonical": "",
            "score": 0.0,
            "confidence": 0.0,
            "count": 0,
            "engines": set(),
            "sources": [],
            "variants": [],
        }
    )

    for item in exact_ranked:
        canonical = item["text"].upper()
        entry = canonical_grouped[canonical]
        entry["canonical"] = canonical
        entry["score"] += item["score"]
        entry["confidence"] = max(entry["confidence"], item["confidence"])
        entry["count"] += item["count"]
        entry["engines"].update(item["engines"])
        entry["sources"].extend(item["sources"])
        entry["variants"].append(
            {
                "text": item["text"],
                "score": item["score"],
                "confidence": item["confidence"],
                "count": item["count"],
            }
        )

    ranked = []
    for entry in canonical_grouped.values():
        variants = sorted(
            entry["variants"],
            key=lambda item: (
                length_bucket(item["text"]),
                item["score"],
                item["confidence"],
                item["count"],
            ),
            reverse=True,
        )
        best_variant = variants[0]
        ranked.append(
            {
                "canonical": entry["canonical"],
                "text": best_variant["text"],
                "score": round(entry["score"], 6),
                "support": 0.0,
                "confidence": round(entry["confidence"], 6),
                "count": entry["count"],
                "engines": sorted(entry["engines"]),
                "sources": entry["sources"],
                "variants": variants[:6],
            }
        )

    expected_entries = [item for item in ranked if len(item["canonical"]) == EXPECTED_LENGTH]
    shorter_entries = [item for item in ranked if 0 < len(item["canonical"]) < EXPECTED_LENGTH]
    for expected in expected_entries:
        support = 0.0
        for shorter in shorter_entries:
            if not is_subsequence(shorter["canonical"], expected["canonical"]):
                continue

            factor = 0.35 if len(shorter["canonical"]) == EXPECTED_LENGTH - 1 else 0.18
            support += shorter["score"] * factor

        expected["support"] = round(support, 6)
        expected["score"] = round(expected["score"] + support, 6)

    ranked.sort(
        key=lambda item: (
            length_bucket(item["canonical"]),
            item["score"],
            item["confidence"],
            item["count"],
        ),
        reverse=True,
    )
    return ranked


def main():
    payload = sys.stdin.buffer.read()
    if not payload:
        raise SystemExit("no image payload received from stdin")

    image = Image.open(io.BytesIO(payload)).convert("RGB")
    raw_candidates = []

    if ddddocr is not None:
        raw_candidates.extend(run_ddddocr(image))

    raw_candidates.extend(run_tesseract(image))
    ranked = group_candidates(raw_candidates)

    best = ranked[0] if ranked else None
    result = {
        "ok": bool(best),
        "guess": best["text"] if best else "",
        "expectedLength": EXPECTED_LENGTH,
        "usedDdddocr": ddddocr is not None,
        "importError": IMPORT_ERROR,
        "candidates": ranked[:8],
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
