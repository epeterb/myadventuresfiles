"""
Adventures Of — Image Generation Pipeline
==========================================
Generates storybook illustrations from parent-uploaded photos using Flux Kontext via Replicate.

Requirements:
    pip install replicate anthropic boto3 Pillow requests

Environment variables:
    REPLICATE_API_TOKEN — Your Replicate API token
    ANTHROPIC_API_KEY — Your Anthropic API key (for story generation)
    AWS_ACCESS_KEY_ID — (Optional) For S3 photo storage
    AWS_SECRET_ACCESS_KEY — (Optional) For S3 photo storage

Usage:
    # Test single illustration
    python adventures_pipeline.py test --photo path/to/child_photo.jpg --scene "riding a friendly dinosaur through a jungle"

    # Generate full storybook
    python adventures_pipeline.py generate --photos photo1.jpg photo2.jpg --profile child_profile.json

    # Generate full storybook with story generation included
    python adventures_pipeline.py full --photos photo1.jpg photo2.jpg --profile child_profile.json
"""

import replicate
import anthropic
import json
import os
import sys
import time
import base64
import requests
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Flux Kontext model on Replicate — fast, identity-preserving, no fine-tuning
FLUX_MODEL = "black-forest-labs/flux-kontext-pro"

# Fallback if Kontext Pro is too expensive for POC testing
FLUX_MODEL_FAST = "black-forest-labs/flux-kontext-fast"

# Art style directive appended to every illustration prompt
ART_STYLE = (
    "Children's storybook illustration style. Warm, inviting colors. "
    "Whimsical and magical atmosphere. Soft lighting. "
    "Hand-painted watercolor texture. Safe, joyful mood. "
    "The child should be clearly recognizable from the reference photo "
    "but rendered in an illustrated storybook art style."
)

# Safety: negative prompt to keep outputs child-safe
SAFETY_NEGATIVE = (
    "scary, dark, violent, blood, weapons, sexual, nude, realistic photo, "
    "horror, creepy, disturbing, sad, crying, injured, frightening, "
    "photorealistic, hyperrealistic"
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ChildProfile:
    name: str
    age: int
    interests: list[str]
    favorite_things: dict
    fears_to_avoid: list[str]
    reading_level: str  # "emerging", "developing", "confident"
    special_considerations: str = ""
    previous_adventures: list[str] = field(default_factory=list)

    @classmethod
    def from_json(cls, path: str) -> "ChildProfile":
        with open(path) as f:
            data = json.load(f)
        return cls(**data)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StoryPage:
    page_number: int
    text: str
    illustration_prompt: str
    illustration_path: Optional[str] = None


@dataclass
class Storybook:
    title: str
    framework_used: str
    theme: str
    pages: list[StoryPage]
    character_bible_update: dict

    @classmethod
    def from_api_response(cls, data: dict) -> "Storybook":
        pages = [
            StoryPage(
                page_number=p["page_number"],
                text=p["text"],
                illustration_prompt=p["illustration_prompt"],
            )
            for p in data["pages"]
        ]
        return cls(
            title=data["title"],
            framework_used=data["framework_used"],
            theme=data["theme"],
            pages=pages,
            character_bible_update=data.get("character_bible_update", {}),
        )


# ---------------------------------------------------------------------------
# Image Generation
# ---------------------------------------------------------------------------

def encode_image_to_data_uri(image_path: str) -> str:
    """Convert a local image file to a data URI for Replicate input."""
    path = Path(image_path)
    suffix = path.suffix.lower()
    mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
    mime_type = mime_map.get(suffix, "image/jpeg")

    with open(path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def generate_illustration(
    reference_photo_path: str,
    scene_prompt: str,
    output_path: str,
    use_fast_model: bool = False,
) -> str:
    """
    Generate a single storybook illustration using Flux Kontext.

    Args:
        reference_photo_path: Path to the child's photo
        scene_prompt: Description of the scene (from story generation)
        output_path: Where to save the generated illustration
        use_fast_model: Use the faster/cheaper model for testing

    Returns:
        Path to the saved illustration
    """
    model = FLUX_MODEL_FAST if use_fast_model else FLUX_MODEL
    image_uri = encode_image_to_data_uri(reference_photo_path)

    # Build the full prompt with art style
    full_prompt = (
        f"Transform the child in this photo into a children's storybook illustration. "
        f"Keep the child's face, hair, and features exactly the same. "
        f"The child is {scene_prompt}\n\n"
        f"Style: {ART_STYLE}"
    )

    print(f"  Generating illustration with {model}...")
    print(f"  Prompt: {scene_prompt[:100]}...")

    output = replicate.run(
        model,
        input={
            "prompt": full_prompt,
            "input_image": image_uri,
            "aspect_ratio": "4:3",       # Landscape storybook format
            "safety_tolerance": 2,        # Strict safety filtering
            "output_format": "png",
            "output_quality": 90,
        },
    )

    # Replicate returns a URL or FileOutput — download the image
    if hasattr(output, "url"):
        image_url = output.url
    elif isinstance(output, str):
        image_url = output
    else:
        # Some models return a list
        image_url = str(output[0]) if isinstance(output, list) else str(output)

    response = requests.get(image_url)
    response.raise_for_status()

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(response.content)

    print(f"  Saved: {output_path}")
    return output_path


def generate_all_illustrations(
    reference_photo_path: str,
    storybook: Storybook,
    output_dir: str,
    use_fast_model: bool = False,
    pages_to_illustrate: Optional[list[int]] = None,
) -> Storybook:
    """
    Generate illustrations for all (or selected) pages of a storybook.

    Args:
        reference_photo_path: Best photo of the child
        storybook: The generated storybook with illustration prompts
        output_dir: Directory to save illustrations
        use_fast_model: Use faster/cheaper model
        pages_to_illustrate: Which pages to illustrate (default: all)

    Returns:
        Updated storybook with illustration paths filled in
    """
    os.makedirs(output_dir, exist_ok=True)

    # Default: illustrate pages 1,3,5,7,9,11 (every other page) for POC
    # Full version: all 12 pages
    if pages_to_illustrate is None:
        pages_to_illustrate = list(range(1, 13))  # All 12 pages

    for page in storybook.pages:
        if page.page_number not in pages_to_illustrate:
            continue

        output_path = os.path.join(
            output_dir,
            f"page_{page.page_number:02d}.png",
        )

        try:
            page.illustration_path = generate_illustration(
                reference_photo_path=reference_photo_path,
                scene_prompt=page.illustration_prompt,
                output_path=output_path,
                use_fast_model=use_fast_model,
            )
        except Exception as e:
            print(f"  ERROR on page {page.page_number}: {e}")
            page.illustration_path = None

        # Rate limiting — be nice to the API
        time.sleep(1)

    return storybook


# ---------------------------------------------------------------------------
# Story Generation (calls Claude API)
# ---------------------------------------------------------------------------

def generate_story(profile: ChildProfile, system_prompt_path: str = "story_system_prompt.md") -> Storybook:
    """
    Generate a complete story using Claude API.

    Args:
        profile: The child's profile
        system_prompt_path: Path to the system prompt markdown file

    Returns:
        A Storybook object with text and illustration prompts
    """
    client = anthropic.Anthropic()

    # Load system prompt — strip the markdown wrapper, extract just the prompt
    with open(system_prompt_path) as f:
        content = f.read()

    # Extract the prompt between the ``` blocks
    parts = content.split("```")
    if len(parts) >= 3:
        system_prompt = parts[1]
        # Remove the language identifier if present
        if system_prompt.startswith("\n"):
            system_prompt = system_prompt[1:]
    else:
        system_prompt = content

    print(f"Generating story for {profile.name}...")

    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=8192,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Generate a personalized adventure story for this child:\n\n"
                    f"{json.dumps(profile.to_dict(), indent=2)}\n\n"
                    f"Return ONLY the JSON object, no markdown formatting."
                ),
            }
        ],
    )

    # Parse the response
    response_text = message.content[0].text

    # Clean up common JSON issues
    response_text = response_text.strip()
    if response_text.startswith("```json"):
        response_text = response_text[7:]
    if response_text.startswith("```"):
        response_text = response_text[3:]
    if response_text.endswith("```"):
        response_text = response_text[:-3]
    response_text = response_text.strip()

    data = json.loads(response_text)
    storybook = Storybook.from_api_response(data)

    print(f"Generated: {storybook.title}")
    print(f"Framework: {storybook.framework_used}")
    print(f"Theme: {storybook.theme}")
    print(f"Pages: {len(storybook.pages)}")

    return storybook


# ---------------------------------------------------------------------------
# PDF Assembly (simple POC version)
# ---------------------------------------------------------------------------

def assemble_pdf(storybook: Storybook, output_path: str):
    """
    Assemble storybook into a simple PDF.
    Uses fpdf2 for simplicity — upgrade to reportlab for production.

    Requires: pip install fpdf2
    """
    try:
        from fpdf import FPDF
    except ImportError:
        print("Install fpdf2 for PDF generation: pip install fpdf2")
        print("Skipping PDF assembly — story text saved as JSON instead.")
        json_path = output_path.replace(".pdf", ".json")
        with open(json_path, "w") as f:
            json.dump(
                {
                    "title": storybook.title,
                    "pages": [
                        {"page": p.page_number, "text": p.text, "illustration": p.illustration_path}
                        for p in storybook.pages
                    ],
                },
                f,
                indent=2,
            )
        print(f"Saved story JSON: {json_path}")
        return

    pdf = FPDF(orientation="L", unit="mm", format="A4")  # Landscape for storybook feel
    pdf.set_auto_page_break(auto=False)

    # Warm background color for text-only pages (cream/warm tone)
    WARM_BG = (255, 248, 235)  # Warm cream to match illustration style

    # Title page — warm background
    pdf.add_page()
    pdf.set_fill_color(*WARM_BG)
    pdf.rect(0, 0, 297, 210, "F")
    pdf.set_font("Helvetica", "B", 30)
    pdf.set_xy(20, 65)
    pdf.multi_cell(257, 16, storybook.title, align="C")
    pdf.set_font("Helvetica", "", 16)
    pdf.ln(10)
    pdf.cell(0, 10, f"A {storybook.theme} adventure", align="C")

    # Story pages
    for page in storybook.pages:
        pdf.add_page()

        # Sanitize Unicode characters not supported by Helvetica
        text = page.text.replace("\u2014", "--").replace("\u2013", "-").replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')

        # Prefer JPG if available (smaller file size)
        illust_path = page.illustration_path
        if illust_path and illust_path.endswith(".png"):
            jpg_alt = illust_path.replace(".png", ".jpg")
            if os.path.exists(jpg_alt):
                illust_path = jpg_alt

        if illust_path and os.path.exists(illust_path):
            # Left half: illustration
            pdf.image(illust_path, x=10, y=10, w=130, h=100)
            # Right half: text
            pdf.set_xy(150, 20)
            pdf.set_font("Helvetica", "", 14)
            pdf.multi_cell(130, 8, text)
        else:
            # Warm cream background for text-only pages
            pdf.set_fill_color(*WARM_BG)
            pdf.rect(0, 0, 297, 210, "F")
            # Full page text if no illustration
            pdf.set_xy(30, 30)
            pdf.set_font("Helvetica", "", 16)
            pdf.multi_cell(237, 10, text)

        # Page number
        pdf.set_xy(260, 190)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 5, str(page.page_number))

    pdf.output(output_path)
    print(f"PDF saved: {output_path}")


# ---------------------------------------------------------------------------
# Photo Safety Utilities
# ---------------------------------------------------------------------------

def validate_photo(photo_path: str) -> bool:
    """
    Basic photo validation before processing.
    In production, add: NSFW detection, face detection, file size limits.
    """
    path = Path(photo_path)

    # Check file exists
    if not path.exists():
        print(f"ERROR: Photo not found: {photo_path}")
        return False

    # Check file type
    allowed = {".jpg", ".jpeg", ".png", ".webp"}
    if path.suffix.lower() not in allowed:
        print(f"ERROR: Unsupported file type: {path.suffix}")
        return False

    # Check file size (max 10MB)
    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb > 10:
        print(f"ERROR: Photo too large: {size_mb:.1f}MB (max 10MB)")
        return False

    # Check it's actually an image
    try:
        from PIL import Image
        img = Image.open(path)
        img.verify()
        # Reopen after verify
        img = Image.open(path)
        width, height = img.size
        if width < 200 or height < 200:
            print(f"WARNING: Photo is very small ({width}x{height}). Quality may be low.")
        print(f"  Photo valid: {path.name} ({width}x{height}, {size_mb:.1f}MB)")
        return True
    except Exception as e:
        print(f"ERROR: Invalid image file: {e}")
        return False


def select_best_photo(photo_paths: list[str]) -> str:
    """
    Select the best photo for character reference.
    Prefers: clear face, good lighting, simple background.
    For POC: just picks the first valid one. In production, use face detection scoring.
    """
    for path in photo_paths:
        if validate_photo(path):
            return path
    raise ValueError("No valid photos provided")


# ---------------------------------------------------------------------------
# CLI Interface
# ---------------------------------------------------------------------------

def cmd_test(args):
    """Test single illustration generation."""
    photo = args[args.index("--photo") + 1]
    scene = args[args.index("--scene") + 1]
    fast = "--fast" in args
    output = "test_illustration.png"

    if not validate_photo(photo):
        sys.exit(1)

    generate_illustration(
        reference_photo_path=photo,
        scene_prompt=scene,
        output_path=output,
        use_fast_model=fast,
    )
    print(f"\nDone! Check: {output}")


def cmd_generate(args):
    """Generate illustrations for an existing story."""
    photos = []
    i = args.index("--photos") + 1
    while i < len(args) and not args[i].startswith("--"):
        photos.append(args[i])
        i += 1

    profile_path = args[args.index("--profile") + 1]
    fast = "--fast" in args

    profile = ChildProfile.from_json(profile_path)
    best_photo = select_best_photo(photos)

    # Load or generate story
    story_path = f"output/{profile.name.lower()}_story.json"
    if os.path.exists(story_path):
        with open(story_path) as f:
            storybook = Storybook.from_api_response(json.load(f))
        print(f"Loaded existing story: {storybook.title}")
    else:
        print("No existing story found. Run with 'full' command to generate story + illustrations.")
        sys.exit(1)

    output_dir = f"output/{profile.name.lower()}_illustrations"
    storybook = generate_all_illustrations(best_photo, storybook, output_dir, use_fast_model=fast)
    print(f"\nIllustrations saved to: {output_dir}")


def cmd_full(args):
    """Generate complete storybook: story + illustrations + PDF."""
    photos = []
    i = args.index("--photos") + 1
    while i < len(args) and not args[i].startswith("--"):
        photos.append(args[i])
        i += 1

    profile_path = args[args.index("--profile") + 1]
    fast = "--fast" in args

    profile = ChildProfile.from_json(profile_path)
    best_photo = select_best_photo(photos)

    # Step 1: Generate story
    storybook = generate_story(profile)

    # Save story JSON
    os.makedirs("output", exist_ok=True)
    story_path = f"output/{profile.name.lower()}_story.json"
    with open(story_path, "w") as f:
        json.dump(
            {
                "title": storybook.title,
                "framework_used": storybook.framework_used,
                "theme": storybook.theme,
                "pages": [
                    {
                        "page_number": p.page_number,
                        "text": p.text,
                        "illustration_prompt": p.illustration_prompt,
                    }
                    for p in storybook.pages
                ],
                "character_bible_update": storybook.character_bible_update,
            },
            f,
            indent=2,
        )
    print(f"Story saved: {story_path}")

    # Step 2: Generate illustrations
    output_dir = f"output/{profile.name.lower()}_illustrations"
    storybook = generate_all_illustrations(best_photo, storybook, output_dir, use_fast_model=fast)

    # Step 3: Assemble PDF
    pdf_path = f"output/{profile.name.lower()}_storybook.pdf"
    assemble_pdf(storybook, pdf_path)

    print(f"\n{'='*50}")
    print(f"COMPLETE: {storybook.title}")
    print(f"Story JSON: {story_path}")
    print(f"Illustrations: {output_dir}/")
    print(f"PDF: {pdf_path}")
    print(f"{'='*50}")


def cmd_demo_profile(args):
    """Create a sample child profile JSON for testing."""
    profile = {
        "name": "Leo",
        "age": 5,
        "interests": ["dinosaurs", "trucks", "building things", "mud"],
        "favorite_things": {
            "color": "green",
            "pet": "a cat named Biscuit",
            "food": "mac and cheese",
            "toy": "T-Rex action figure"
        },
        "fears_to_avoid": ["loud thunder", "being alone in the dark", "spiders"],
        "reading_level": "emerging",
        "special_considerations": "",
        "previous_adventures": []
    }

    path = "sample_profile.json"
    with open(path, "w") as f:
        json.dump(profile, f, indent=2)
    print(f"Sample profile saved: {path}")
    print(json.dumps(profile, indent=2))


def main():
    if len(sys.argv) < 2:
        print("""
Adventures Of — Image & Story Pipeline
=======================================

Commands:
  test          Test single illustration generation
                  --photo <path> --scene "description" [--fast]

  full          Generate complete storybook (story + illustrations + PDF)
                  --photos <path1> <path2> --profile <json_path> [--fast]

  generate      Generate illustrations for existing story
                  --photos <path1> <path2> --profile <json_path> [--fast]

  demo-profile  Create a sample child profile JSON for testing

Flags:
  --fast        Use faster/cheaper model (lower quality, good for testing)

Examples:
  python adventures_pipeline.py demo-profile
  python adventures_pipeline.py test --photo kid.jpg --scene "riding a dinosaur through a jungle"
  python adventures_pipeline.py full --photos kid1.jpg kid2.jpg --profile sample_profile.json --fast
        """)
        sys.exit(0)

    command = sys.argv[1]
    args = sys.argv[1:]

    commands = {
        "test": cmd_test,
        "full": cmd_full,
        "generate": cmd_generate,
        "demo-profile": cmd_demo_profile,
    }

    if command in commands:
        commands[command](args)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
