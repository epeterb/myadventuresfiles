"""
Regenerate specific storybook pages with corrected prompts.

Fixes:
  - Page 1: Evan should be on living room floor with dinosaur figures (not outside)
  - Page 2: Evan should wear black outfit with orange gloves (not green shirt)
  - Page 6: Fix Evan's eyes — natural, not crossed
  - Page 8: Black outfit consistency (not teal/green shirt)

Usage:
    export REPLICATE_API_TOKEN=your_token_here
    python regenerate_pages.py --photo path/to/evan_reference.jpg [--fast]
"""

import replicate
import requests
import os
import sys
import base64
import json
from pathlib import Path
from PIL import Image

# Consistent outfit description used across all corrected prompts
OUTFIT_DESC = (
    "wearing a dark navy/black zip-up hoodie with a small red logo on the chest, "
    "dark navy track pants with white triple stripes down the sides, "
    "bright orange work gloves, dark sneakers, and a grey climbing harness/belt"
)

ART_STYLE = (
    "Children's storybook illustration style. Warm, inviting colors. "
    "Whimsical and magical atmosphere. Soft lighting. "
    "Hand-painted watercolor texture. Safe, joyful mood. "
    "The child should be clearly recognizable from the reference photo "
    "but rendered in an illustrated storybook art style."
)

# Model
FLUX_MODEL = "black-forest-labs/flux-kontext-pro"
FLUX_MODEL_FAST = "black-forest-labs/flux-kontext-fast"

# Updated prompts for the 4 pages that need fixes
CORRECTED_PROMPTS = {
    1: (
        f"Evan is an 8-year-old boy {OUTFIT_DESC}, lying on his stomach on a colorful rug "
        f"on a cozy living room floor. He is surrounded by several plastic dinosaur figures, "
        f"including a green Brachiosaurus that stands tallest. Morning sunlight streams through "
        f"nearby windows. The room has a warm, lived-in feeling with a couch and bookshelf visible "
        f"in the background. Evan's face shows happy concentration as he plays with the dinosaurs. "
        f"Indoor scene — living room floor, NOT outside."
    ),
    2: (
        f"Evan, an 8-year-old boy {OUTFIT_DESC}, is looking out a large window from inside "
        f"a cozy living room. His hand is pressed against the glass. Through the window, a large "
        f"oak tree is visible in the backyard, with a mysterious green shimmer glowing between "
        f"its branches. Evan's expression shows curious excitement. The room behind him is slightly "
        f"dim while the outdoor scene is bright and inviting. A few dinosaur figures are stuffed "
        f"in his pockets. The green glow is magical and beckoning."
    ),
    6: (
        f"Evan, an 8-year-old boy {OUTFIT_DESC}, walks along a dirt path beside Jade the young "
        f"Stegosaurus through the prehistoric valley. Jade has bright green plates along her back. "
        f"In the background, friendly Triceratops and Parasaurolophus dinosaurs go about peaceful "
        f"activities. In the far distance, an enormous ancient tree stands alone with its leaves "
        f"visibly brown and wilting while everything else is lush green. Jade looks worried, her "
        f"head lowered. Evan follows her gaze with concern on his face. His eyes are naturally "
        f"focused and looking in the same direction as Jade — toward the dying tree. "
        f"IMPORTANT: Evan's eyes must look natural, both eyes looking in the same direction, "
        f"not crossed or misaligned."
    ),
    8: (
        f"Evan, an 8-year-old boy {OUTFIT_DESC}, is perched carefully on a pile of rocks near "
        f"the base of an enormous ancient tree. He is pulling at a key stone while Jade the green "
        f"Stegosaurus uses her powerful tail to push another rock away. Both are working together "
        f"with focused determination. Some rocks are already cleared and a small trickle of water "
        f"is beginning to reach the tree roots. Evan's outfit is a bit dusty from the work. "
        f"Jade looks proud to be helping. The scene shows teamwork and progress."
    ),
}


def encode_image_to_data_uri(image_path: str) -> str:
    path = Path(image_path)
    suffix = path.suffix.lower()
    mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
    mime_type = mime_map.get(suffix, "image/jpeg")
    with open(path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def regenerate_page(reference_photo: str, page_num: int, prompt: str, use_fast: bool = False):
    model = FLUX_MODEL_FAST if use_fast else FLUX_MODEL
    image_uri = encode_image_to_data_uri(reference_photo)

    full_prompt = (
        f"Transform the child in this photo into a children's storybook illustration. "
        f"Keep the child's face, hair, and features exactly the same. "
        f"The child is {prompt}\n\n"
        f"Style: {ART_STYLE}"
    )

    print(f"\n{'='*60}")
    print(f"Regenerating page {page_num} with {model}...")
    print(f"Prompt preview: {prompt[:120]}...")

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

    if hasattr(output, "url"):
        image_url = output.url
    elif isinstance(output, str):
        image_url = output
    else:
        image_url = str(output[0]) if isinstance(output, list) else str(output)

    response = requests.get(image_url)
    response.raise_for_status()

    # Save as PNG first (original format)
    output_dir = "output/evan_illustrations"
    png_path = os.path.join(output_dir, f"page_{page_num:02d}.png")
    with open(png_path, "wb") as f:
        f.write(response.content)
    print(f"  Saved PNG: {png_path}")

    # Also save as optimized JPEG
    img = Image.open(png_path)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    jpg_path = os.path.join(output_dir, f"page_{page_num:02d}.jpg")
    img.save(jpg_path, "JPEG", quality=85)
    jpg_size = os.path.getsize(jpg_path) / 1024
    print(f"  Saved JPG: {jpg_path} ({jpg_size:.0f}KB)")

    return png_path, jpg_path


def update_story_json(pages_regenerated: list[int]):
    """Update evan_story.json with corrected prompts."""
    story_path = "output/evan_story.json"
    with open(story_path) as f:
        story = json.load(f)

    for page in story["pages"]:
        pn = page["page_number"]
        if pn in CORRECTED_PROMPTS:
            page["illustration_prompt"] = CORRECTED_PROMPTS[pn]
            print(f"  Updated prompt for page {pn} in {story_path}")

    with open(story_path, "w") as f:
        json.dump(story, f, indent=2)
    print(f"Saved updated story: {story_path}")


def main():
    if "--photo" not in sys.argv:
        print("Usage: python regenerate_pages.py --photo <path/to/evan_photo.jpg> [--fast]")
        print()
        print("Requires: REPLICATE_API_TOKEN environment variable")
        sys.exit(1)

    photo_path = sys.argv[sys.argv.index("--photo") + 1]
    use_fast = "--fast" in sys.argv

    if not os.path.exists(photo_path):
        print(f"ERROR: Photo not found: {photo_path}")
        sys.exit(1)

    token = os.environ.get("REPLICATE_API_TOKEN", "")
    if not token:
        print("ERROR: REPLICATE_API_TOKEN not set")
        print("  export REPLICATE_API_TOKEN=your_token_here")
        sys.exit(1)

    pages_to_fix = [1, 2, 6, 8]
    print(f"Regenerating pages: {pages_to_fix}")
    print(f"Reference photo: {photo_path}")
    print(f"Model: {'FAST' if use_fast else 'PRO'}")

    # Update prompts in story JSON
    update_story_json(pages_to_fix)

    # Regenerate each page
    for page_num in pages_to_fix:
        try:
            regenerate_page(photo_path, page_num, CORRECTED_PROMPTS[page_num], use_fast)
        except Exception as e:
            print(f"  ERROR on page {page_num}: {e}")
            continue

        import time
        time.sleep(1)  # Rate limiting

    print(f"\n{'='*60}")
    print("DONE! Regenerated pages: " + ", ".join(str(p) for p in pages_to_fix))
    print("Review the new illustrations, then run PDF assembly when ready.")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
