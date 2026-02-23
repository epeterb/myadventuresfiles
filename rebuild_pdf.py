"""
Rebuild the storybook PDF with enriched page backgrounds and smaller file size.
Uses JPG images and warm cream backgrounds on every page.
"""

import json
import os
from pathlib import Path

try:
    from fpdf import FPDF
except ImportError:
    print("Install fpdf2: pip install fpdf2")
    exit(1)

BASE_DIR = Path(__file__).parent
STORY_JSON = BASE_DIR / "output" / "evan_story.json"
ILLUST_DIR = BASE_DIR / "output" / "evan_illustrations"
OUTPUT_PDF = BASE_DIR / "output" / "evan_storybook.pdf"

# Colors
WARM_BG = (255, 248, 235)       # Warm cream
TEXT_COLOR = (60, 40, 20)        # Dark brown for readability
TITLE_COLOR = (34, 100, 34)     # Forest green for title
PAGE_NUM_COLOR = (140, 120, 100) # Muted brown for page numbers
BORDER_COLOR = (200, 180, 150)  # Soft border around illustrations


def sanitize(text):
    return (text
        .replace("\u2014", "--")
        .replace("\u2013", "-")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
    )


def build_pdf():
    with open(STORY_JSON) as f:
        story = json.load(f)

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=False)

    # A4 Landscape: 297mm x 210mm

    # --- Title Page ---
    pdf.add_page()
    pdf.set_fill_color(*WARM_BG)
    pdf.rect(0, 0, 297, 210, "F")

    # Decorative border
    pdf.set_draw_color(*BORDER_COLOR)
    pdf.set_line_width(1.5)
    pdf.rect(15, 15, 267, 180, "D")
    pdf.set_line_width(0.5)
    pdf.rect(18, 18, 261, 174, "D")

    # Title
    pdf.set_text_color(*TITLE_COLOR)
    pdf.set_font("Helvetica", "B", 32)
    pdf.set_xy(30, 55)
    title = sanitize(story["title"])
    pdf.multi_cell(237, 16, title, align="C")

    # Subtitle
    pdf.set_text_color(*TEXT_COLOR)
    pdf.set_font("Helvetica", "I", 18)
    pdf.ln(8)
    theme = story.get("theme", "courage")
    pdf.cell(0, 12, f"A {theme} adventure", align="C")

    # Decorative line
    pdf.set_draw_color(*TITLE_COLOR)
    pdf.set_line_width(0.8)
    pdf.line(100, pdf.get_y() + 15, 197, pdf.get_y() + 15)

    # --- Story Pages ---
    for page_data in story["pages"]:
        pdf.add_page()

        # Warm background on EVERY page
        pdf.set_fill_color(*WARM_BG)
        pdf.rect(0, 0, 297, 210, "F")

        page_num = page_data["page_number"]
        text = sanitize(page_data["text"])

        # Find illustration (prefer JPG)
        jpg_path = ILLUST_DIR / f"page_{page_num:02d}.jpg"
        png_path = ILLUST_DIR / f"page_{page_num:02d}.png"
        illust_path = None
        if jpg_path.exists():
            illust_path = str(jpg_path)
        elif png_path.exists():
            illust_path = str(png_path)

        if illust_path:
            # Illustration border/shadow effect
            pdf.set_fill_color(220, 210, 195)
            pdf.rect(8, 8, 156, 120, "F")  # shadow
            pdf.set_draw_color(*BORDER_COLOR)
            pdf.set_line_width(0.5)
            pdf.rect(7, 7, 155, 119, "D")

            # Illustration — larger, taking up left ~55% of page
            pdf.image(illust_path, x=8, y=8, w=154, h=118)

            # Text on right side with warm panel
            pdf.set_fill_color(255, 252, 245)  # Slightly lighter cream for text area
            pdf.rect(168, 8, 122, 190, "F")
            pdf.set_draw_color(*BORDER_COLOR)
            pdf.rect(168, 8, 122, 190, "D")

            # Story text
            pdf.set_text_color(*TEXT_COLOR)
            pdf.set_font("Helvetica", "", 12)
            pdf.set_xy(173, 14)
            pdf.multi_cell(112, 7, text)

            # Text below illustration if needed (for longer text)
            if pdf.get_y() > 190:
                pass  # text fit in the panel

            # Also add text below the illustration for visual balance
            bottom_y = 132
            if pdf.get_y() < 180:
                # Text fit in the right panel, optionally add chapter marker
                pass
        else:
            # Text-only page (shouldn't happen but handle gracefully)
            pdf.set_draw_color(*BORDER_COLOR)
            pdf.set_line_width(0.5)
            pdf.rect(20, 20, 257, 170, "D")

            pdf.set_text_color(*TEXT_COLOR)
            pdf.set_font("Helvetica", "", 16)
            pdf.set_xy(35, 35)
            pdf.multi_cell(227, 10, text)

        # Page number
        pdf.set_text_color(*PAGE_NUM_COLOR)
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_xy(140, 198)
        pdf.cell(17, 5, str(page_num), align="C")

    # --- Back Cover ---
    pdf.add_page()
    pdf.set_fill_color(*WARM_BG)
    pdf.rect(0, 0, 297, 210, "F")

    pdf.set_draw_color(*BORDER_COLOR)
    pdf.set_line_width(1.5)
    pdf.rect(15, 15, 267, 180, "D")

    pdf.set_text_color(*TITLE_COLOR)
    pdf.set_font("Helvetica", "I", 16)
    pdf.set_xy(30, 85)
    pdf.multi_cell(237, 10, "The End", align="C")
    pdf.set_font("Helvetica", "", 12)
    pdf.set_text_color(*TEXT_COLOR)
    pdf.ln(10)
    pdf.multi_cell(237, 8, "...but the adventure continues!", align="C")

    pdf.output(str(OUTPUT_PDF))
    pdf_size = os.path.getsize(OUTPUT_PDF) / 1024
    print(f"PDF saved: {OUTPUT_PDF} ({pdf_size:.0f}KB)")


if __name__ == "__main__":
    build_pdf()
