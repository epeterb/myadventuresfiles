"""
Regenerate ALL storybook pages for consistent character appearance.

Uses page 5 (and optionally page 12) as the reference image so Flux Kontext
maintains the same face, outfit, and art style across every page.

Pages 5 and 12 are the "gold standard" — they won't be regenerated.

Usage:
    export REPLICATE_API_TOKEN=your_token_here
    python regenerate_consistent.py [--fast] [--pages 3,6,7,8,9] [--all]
"""

import replicate
import requests
import os
import sys
import base64
import json
import time
from pathlib import Path
from PIL import Image


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output" / "evan_illustrations"
STORY_JSON = BASE_DIR / "output" / "evan_story.json"

# Reference images — page 5 for outdoor scenes, page 12 for home scenes
REF_OUTDOOR = OUTPUT_DIR / "page_05.png"
REF_HOME = OUTPUT_DIR / "page_12.png"

# Models
FLUX_MODEL_PRO = "black-forest-labs/flux-kontext-pro"
FLUX_MODEL_FAST = "black-forest-labs/flux-kontext-fast"

# Consistent outfit — matches pages 5 and 12 exactly
OUTFIT = (
    "wearing a dark navy/black zip-up hoodie with a small red logo on the chest, "
    "dark navy track pants with white triple stripes down the sides, "
    "and dark sneakers"
)

ART_STYLE = (
    "Children's storybook illustration style. Warm, inviting colors. "
    "Whimsical and magical atmosphere. Soft lighting. "
    "Hand-painted watercolor texture. Safe, joyful mood."
)

# Pages to skip (these are the reference pages)
REFERENCE_PAGES = {5, 12}

# Which reference image to use for each page
# Home scenes use page 12, outdoor/adventure scenes use page 5
HOME_PAGES = {1, 2}  # Indoor scenes


# ---------------------------------------------------------------------------
# Updated prompts — every single one includes outfit + character consistency
# ---------------------------------------------------------------------------

PROMPTS = {
    1: (
        f"Keep this exact same boy with the same face, hair, and features. "
        f"The boy is {OUTFIT}. "
        f"He is an 8-year-old boy, NOT a toddler or baby — he looks school-age and confident. "
        f"He is lying on his stomach on a colorful rug on a cozy living room floor, propped up "
        f"on his elbows. He is surrounded by several plastic dinosaur figures, including a green "
        f"Brachiosaurus that stands tallest. Morning sunlight streams through nearby "
        f"windows. The room has a warm, lived-in feeling with a couch and bookshelf "
        f"visible in the background. The boy's face shows happy concentration as he "
        f"plays with the dinosaurs. Indoor scene — living room floor."
    ),
    2: (
        f"Keep this exact same boy with the same face, hair, and features. "
        f"The boy is {OUTFIT}. "
        f"He is standing inside a cozy living room, looking out through a large window "
        f"with both hands pressed against the glass. The scene is shot from INSIDE the room "
        f"showing the boy from behind/side angle. Through the window, a large oak tree is "
        f"visible in a green backyard, with a mysterious bright green magical shimmer glowing "
        f"between its branches. The living room is slightly dim with warm lamplight. "
        f"A few dinosaur figures are stuffed in his hoodie pockets. "
        f"This is an INTERIOR scene — very different from an outdoor dusk scene."
    ),
    3: (
        f"Keep this exact same boy with the same face, hair, and features. "
        f"The boy is {OUTFIT}. "
        f"The boy is SMALL compared to the tree — the oak tree is VERY LARGE and towers above him. "
        f"He is climbing high up in the massive oak tree's thick branches. "
        f"Near the top of the tree, a magical glowing green archway is carved into the wide trunk. "
        f"The archway has ancient-looking patterns around its edges and pulses with green light. "
        f"The boy is climbing toward it, one hand gripping a branch, looking up in amazement. "
        f"The tree trunk is at least 3 feet wide. Dappled sunlight filters through leaves. "
        f"The ground is visible far below, showing how high he has climbed."
    ),
    4: (
        f"Keep this exact same boy with the same face, hair, and features. "
        f"The boy is {OUTFIT}. "
        f"He stands on a rocky ledge with his arms outstretched in wonder, overlooking "
        f"a vast prehistoric valley. Giant ferns tower below, a majestic waterfall "
        f"cascades in the background with rainbows in the mist. Several dinosaurs are "
        f"visible in the valley: a Triceratops family grazing, Pteranodons flying "
        f"overhead, and long-necked sauropods in the distance. Everything is lush and "
        f"green. The boy's face shows pure joy and amazement."
    ),
    6: (
        f"Keep this exact same boy with the same face, hair, and features. "
        f"The boy is {OUTFIT}. "
        f"He walks along a dirt path beside a young friendly Stegosaurus with bright "
        f"green plates along its back. In the background, friendly Triceratops and "
        f"Parasaurolophus dinosaurs go about peaceful activities. In the far distance, "
        f"an enormous ancient tree stands alone with its leaves visibly brown and "
        f"wilting while everything else is lush green. The Stegosaurus looks worried "
        f"with her head lowered. The boy follows her gaze with concern on his face, "
        f"looking toward the dying tree. Both eyes looking naturally in the same direction. "
        f"The boy MUST be clearly visible and prominent in the scene."
    ),
    7: (
        f"Keep this exact same boy with the same face, hair, and features. "
        f"The boy is {OUTFIT}. "
        f"He stands at the base of an enormous ancient tree with brown, wilting leaves. "
        f"The tree's thick roots are trapped under a pile of medium-sized rocks and "
        f"boulders. A small stream flows nearby but is blocked from reaching the roots. "
        f"A young friendly green-plated Stegosaurus stands beside the boy, looking at "
        f"him hopefully. The boy has his hands on his hips, studying the problem with "
        f"a determined expression. Afternoon sunlight filters through the canopy. "
        f"The boy MUST be clearly visible wearing the dark navy/black hoodie and "
        f"dark track pants with white stripes."
    ),
    8: (
        f"Keep this exact same boy with the same face, hair, and features. "
        f"The boy is {OUTFIT}. "
        f"He is perched on a pile of natural rocks and boulders near the base of an enormous "
        f"ancient tree. He is pulling a large rock with both hands to move it aside, while a young "
        f"green-plated Stegosaurus uses her powerful tail to push another boulder away. "
        f"A natural forest stream is visible nearby — the rocks had been blocking it from "
        f"reaching the tree roots. NO pipes, NO spigots, NO man-made objects — only natural "
        f"rocks, stream water, moss, and prehistoric forest. Some rocks are already cleared "
        f"and water is beginning to trickle through to the roots. The boy is slightly dusty. "
        f"The boy MUST be clearly visible wearing the dark navy/black hoodie."
    ),
    9: (
        f"Keep this exact same boy with the same face, hair, and features. "
        f"The boy is {OUTFIT}. "
        f"He stands before a massive ancient tree whose leaves are transforming from "
        f"brown to brilliant glowing green. The boy raises both arms high in triumph "
        f"with a huge joyful smile. Beside him, a friendly green-plated Stegosaurus "
        f"rears up in celebration. Sparkling water flows around the tree roots. In the "
        f"background, Pteranodons soar and other dinosaurs gather to celebrate. The "
        f"valley is lush and bright with golden sunlight. "
        f"The boy MUST be clearly visible in the center of the scene, "
        f"wearing the dark navy/black hoodie and dark track pants with white stripes."
    ),
    10: (
        f"Keep this exact same boy with the same face, hair, and features. "
        f"The boy is {OUTFIT}. "
        f"A touching scene: the boy stands between a giant gentle Brachiosaurus "
        f"whose long neck curves down to his level, and a young green-plated "
        f"Stegosaurus. The ancient Brachiosaurus has wise, kind eyes and is gently "
        f"touching the boy's outstretched hand with her nose. The boy is hugging the "
        f"Stegosaurus's neck with his other arm, eyes closed in a moment of "
        f"connection. The Great Tree stands tall and healthy behind them, its leaves "
        f"brilliantly green. Golden afternoon light makes the scene glow with warmth."
    ),
    11: (
        f"Keep this exact same boy with the same face, hair, and features. "
        f"The boy is {OUTFIT}. "
        f"He stands at a glowing green archway on a rocky ledge, waving goodbye to "
        f"a valley below. A young green-plated Stegosaurus and many other dinosaurs "
        f"are gathered, waving back or calling out. The valley behind them is lush, "
        f"green, and healthy, with a Great Tree standing tall in the distance. The "
        f"boy has a bittersweet smile, happy but sad to leave. The sun is beginning "
        f"to set, casting golden light across the prehistoric scene."
    ),
}


# ---------------------------------------------------------------------------
# Image utilities
# ---------------------------------------------------------------------------

def encode_image_to_data_uri(image_path: str) -> str:
    path = Path(image_path)
    suffix = path.suffix.lower()
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    mime_type = mime_map.get(suffix, "image/jpeg")
    with open(path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


# ---------------------------------------------------------------------------
# Regeneration
# ---------------------------------------------------------------------------

def regenerate_page(page_num: int, prompt: str, use_fast: bool = False):
    """Regenerate a single page using the appropriate reference image."""
    model = FLUX_MODEL_FAST if use_fast else FLUX_MODEL_PRO

    # Choose reference image based on scene type
    if page_num in HOME_PAGES:
        ref_image = REF_HOME
        print(f"  Using home reference (page 12)")
    else:
        ref_image = REF_OUTDOOR
        print(f"  Using outdoor reference (page 5)")

    image_uri = encode_image_to_data_uri(str(ref_image))

    full_prompt = f"{prompt}\n\nStyle: {ART_STYLE}"

    print(f"\n{'='*60}")
    print(f"Regenerating page {page_num} with {model.split('/')[-1]}...")
    print(f"  Prompt preview: {prompt[:120]}...")

    output = replicate.run(
        model,
        input={
            "prompt": full_prompt,
            "input_image": image_uri,
            "aspect_ratio": "4:3",
            "safety_tolerance": 2,
            "output_format": "png",
            "output_quality": 90,
        },
    )

    # Extract URL from output
    if hasattr(output, "url"):
        image_url = output.url
    elif isinstance(output, str):
        image_url = output
    else:
        image_url = str(output[0]) if isinstance(output, list) else str(output)

    response = requests.get(image_url)
    response.raise_for_status()

    # Save PNG
    png_path = OUTPUT_DIR / f"page_{page_num:02d}.png"
    with open(png_path, "wb") as f:
        f.write(response.content)
    png_size = os.path.getsize(png_path) / 1024
    print(f"  Saved PNG: {png_path} ({png_size:.0f}KB)")

    # Save optimized JPG
    img = Image.open(png_path)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    jpg_path = OUTPUT_DIR / f"page_{page_num:02d}.jpg"
    img.save(str(jpg_path), "JPEG", quality=85)
    jpg_size = os.path.getsize(jpg_path) / 1024
    print(f"  Saved JPG: {jpg_path} ({jpg_size:.0f}KB)")

    return str(png_path)


def update_story_json(pages_to_update: list[int]):
    """Update evan_story.json with the new consistent prompts."""
    with open(STORY_JSON) as f:
        story = json.load(f)

    updated = []
    for page in story["pages"]:
        pn = page["page_number"]
        if pn in PROMPTS:
            page["illustration_prompt"] = PROMPTS[pn]
            updated.append(pn)

    with open(STORY_JSON, "w") as f:
        json.dump(story, f, indent=2)

    print(f"Updated prompts in {STORY_JSON} for pages: {updated}")


def backup_originals(pages: list[int]):
    """Back up current images before overwriting."""
    backup_dir = OUTPUT_DIR / "pre_consistency_backup"
    backup_dir.mkdir(exist_ok=True)

    for page_num in pages:
        for ext in ["png", "jpg"]:
            src = OUTPUT_DIR / f"page_{page_num:02d}.{ext}"
            if src.exists():
                dst = backup_dir / f"page_{page_num:02d}.{ext}"
                if not dst.exists():
                    import shutil
                    shutil.copy2(src, dst)

    print(f"Backed up originals to: {backup_dir}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    use_fast = "--fast" in sys.argv

    # Determine which pages to regenerate
    if "--pages" in sys.argv:
        idx = sys.argv.index("--pages") + 1
        pages_to_fix = [int(p) for p in sys.argv[idx].split(",")]
    elif "--all" in sys.argv:
        pages_to_fix = sorted(PROMPTS.keys())
    else:
        # Default: fix the worst offenders
        pages_to_fix = [3, 6, 7, 8, 9]
        print("Default: regenerating broken pages (3, 6, 7, 8, 9)")
        print("Use --all to regenerate all 10 non-reference pages")
        print("Use --pages 1,2,3 to pick specific pages")

    # Validate
    for p in pages_to_fix:
        if p in REFERENCE_PAGES:
            print(f"WARNING: Skipping page {p} (it's a reference page)")
    pages_to_fix = [p for p in pages_to_fix if p not in REFERENCE_PAGES]

    if not pages_to_fix:
        print("No pages to regenerate!")
        sys.exit(0)

    # Check API token
    token = os.environ.get("REPLICATE_API_TOKEN", "")
    if not token:
        print("ERROR: REPLICATE_API_TOKEN not set")
        print("  export REPLICATE_API_TOKEN=your_token_here")
        sys.exit(1)

    # Check reference images exist
    for ref in [REF_OUTDOOR, REF_HOME]:
        if not ref.exists():
            print(f"ERROR: Reference image not found: {ref}")
            sys.exit(1)

    print(f"\n{'='*60}")
    print(f"CONSISTENT CHARACTER REGENERATION")
    print(f"{'='*60}")
    print(f"Pages to regenerate: {pages_to_fix}")
    print(f"Model: {'FAST' if use_fast else 'PRO'}")
    print(f"Reference (outdoor): {REF_OUTDOOR}")
    print(f"Reference (home): {REF_HOME}")
    print(f"Estimated cost: ~${len(pages_to_fix) * 0.05:.2f} (Pro)")
    print(f"{'='*60}")

    # Back up current images
    backup_originals(pages_to_fix)

    # Update story JSON with consistent prompts
    update_story_json(pages_to_fix)

    # Regenerate each page
    successes = []
    failures = []

    for page_num in pages_to_fix:
        try:
            regenerate_page(page_num, PROMPTS[page_num], use_fast)
            successes.append(page_num)
        except Exception as e:
            print(f"  ERROR on page {page_num}: {e}")
            failures.append(page_num)

        # Rate limiting
        time.sleep(2)

    # Summary
    print(f"\n{'='*60}")
    print(f"DONE!")
    print(f"  Successful: {successes}")
    if failures:
        print(f"  Failed: {failures}")
        print(f"  Re-run with: --pages {','.join(str(p) for p in failures)}")
    print(f"  Backups in: {OUTPUT_DIR}/pre_consistency_backup/")
    print(f"\nReview the new illustrations, then rebuild PDF when ready.")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
