import os
from PIL import Image, ImageDraw, ImageFont

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
ICONS_DIR = os.path.join(STATIC_DIR, 'icons')
os.makedirs(ICONS_DIR, exist_ok=True)

def create_app_icon(size: int, filename: str):
    # Create image with dark gradient or solid stylish background
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw rounded rectangle background with gradient effect
    radius = int(size * 0.22)
    # Background base
    draw.rounded_rectangle([0, 0, size, size], radius=radius, fill=(15, 23, 42, 255))
    
    # Inner glowing border
    margin = int(size * 0.04)
    draw.rounded_rectangle([margin, margin, size - margin, size - margin], radius=int(radius * 0.9), fill=(24, 32, 56, 255), outline=(99, 102, 241, 200), width=max(2, int(size * 0.02)))

    # YouTube red badge in center
    badge_w = int(size * 0.55)
    badge_h = int(size * 0.38)
    bx0 = (size - badge_w) // 2
    by0 = int(size * 0.22)
    bx1 = bx0 + badge_w
    by1 = by0 + badge_h
    draw.rounded_rectangle([bx0, by0, bx1, by1], radius=int(badge_h * 0.28), fill=(239, 68, 68, 255))

    # White play triangle
    tri_size = int(badge_h * 0.45)
    tx0 = bx0 + int(badge_w * 0.42)
    ty0 = by0 + (badge_h - tri_size) // 2
    draw.polygon([
        (tx0, ty0),
        (tx0 + tri_size, ty0 + tri_size // 2),
        (tx0, ty0 + tri_size)
    ], fill=(255, 255, 255, 255))

    # Wave / Studio symbol below badge
    wave_y = int(size * 0.72)
    bar_count = 7
    bar_width = int(size * 0.045)
    gap = int(size * 0.025)
    total_w = bar_count * bar_width + (bar_count - 1) * gap
    start_x = (size - total_w) // 2

    heights = [0.35, 0.65, 1.0, 0.8, 1.0, 0.65, 0.35]
    max_h = int(size * 0.16)

    for i in range(bar_count):
        h = int(max_h * heights[i])
        bx = start_x + i * (bar_width + gap)
        by = wave_y - h // 2
        # Violet/cyan gradient color
        col = (99, 102, 241, 255) if i % 2 == 0 else (236, 72, 153, 255)
        draw.rounded_rectangle([bx, by, bx + bar_width, by + h], radius=int(bar_width * 0.4), fill=col)

    out_path = os.path.join(ICONS_DIR, filename)
    img.save(out_path, 'PNG')
    print(f"Generated icon: {out_path} ({size}x{size})")

if __name__ == '__main__':
    create_app_icon(192, 'icon-192.png')
    create_app_icon(512, 'icon-512.png')
    create_app_icon(180, 'apple-touch-icon.png')
    create_app_icon(64, 'favicon.png')
