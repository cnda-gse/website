#!/usr/bin/env python3
"""
process_photos.py - Pre-push photo optimization and gallery generator for Zola.

Converts local photos in `photos_raw/` into 1200px wide, 50% compressed .AVIF images,
extracts title, date, and camera EXIF metadata, and generates `content/photos/index.md`
organized by category with markdown headings matching the blog page format.

Usage:
    python3 scripts/process_photos.py [options]

Options:
    -i, --input DIR       Source directory for raw photos (default: photos_raw)
    -o, --output DIR      Destination directory for AVIF images (default: static/assets/images/photos)
    -c, --content FILE    Markdown gallery page path (default: content/photos/index.md)
    -f, --force           Force re-processing and re-compression of all images
    --no-build            Skip running 'zola build' after processing
    --install-hook        Install this script into .git/hooks/pre-push
    -h, --help            Show this help message
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageOps

# Supported image extensions
IMAGE_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.webp', '.tiff', '.tif',
    '.heic', '.heif', '.avif', '.raw', '.cr2', '.cr3',
    '.nef', '.arw', '.dng'
}

CACHE_FILE_NAME = ".photo_cache.json"


def get_file_hash(path: Path) -> str:
    """Compute MD5 hash of a file for change detection."""
    hasher = hashlib.md5()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def slugify(text: str) -> str:
    """Convert text to URL-friendly lowercase string."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('-')


def extract_metadata_exiftool(file_path: Path) -> dict:
    """Extract metadata using exiftool if available."""
    try:
        res = subprocess.run(
            ['exiftool', '-json', str(file_path)],
            capture_output=True,
            text=True,
            check=True
        )
        data = json.loads(res.stdout)
        if data and isinstance(data, list):
            return data[0]
    except (subprocess.SubprocessError, json.JSONDecodeError, FileNotFoundError):
        pass
    return {}


def extract_metadata_pillow(file_path: Path) -> dict:
    """Fallback EXIF extraction using Pillow."""
    data = {}
    try:
        with Image.open(file_path) as img:
            exif = img.getexif()
            if not exif:
                return data
            for tag_id, value in exif.items():
                tag = Image.ExifTags.TAGS.get(tag_id, str(tag_id))
                data[tag] = value
            # Exif IFD
            if hasattr(Image.ExifTags, 'IFD'):
                try:
                    exif_ifd = exif.get_ifd(Image.ExifTags.IFD.Exif)
                    for tag_id, value in exif_ifd.items():
                        tag = Image.ExifTags.TAGS.get(tag_id, str(tag_id))
                        data[tag] = value
                except Exception:
                    pass
    except Exception:
        pass
    return data


def parse_photo_metadata(file_path: Path, manual_overrides: dict = None) -> dict:
    """
    Parse title, date, and camera metadata from image EXIF/IPTC with manual overrides.
    """
    manual = manual_overrides or {}
    raw_data = extract_metadata_exiftool(file_path)
    if not raw_data:
        raw_data = extract_metadata_pillow(file_path)

    # 1. Title
    title = (
        manual.get('title')
        or raw_data.get('Title')
        or raw_data.get('ObjectName')
        or raw_data.get('Headline')
        or raw_data.get('ImageDescription')
        or raw_data.get('XPTitle')
    )
    if not title or str(title).strip() in ('', 'None'):
        # Fallback to humanized filename
        base = file_path.stem
        # Strip date prefixes like 2026-10-24- or 20261024_
        base = re.sub(r'^\d{4}[-_]\d{2}[-_]\d{2}[-_]?', '', base)
        base = re.sub(r'[-_]+', ' ', base).strip()
        title = base.title() if base else file_path.stem

    # 2. Date (format: YYYY-MM-DD)
    date_str = manual.get('date')
    if not date_str:
        raw_date = (
            raw_data.get('DateTimeOriginal')
            or raw_data.get('CreateDate')
            or raw_data.get('DateTime')
            or raw_data.get('FileModifyDate')
        )
        if raw_date:
            m = re.search(r'(\d{4})[:\-](\d{2})[:\-](\d{2})', str(raw_date))
            if m:
                date_str = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        if not date_str:
            # Fallback to file modification time
            mtime = os.path.getmtime(file_path)
            date_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')

    # 3. Camera Make and Model
    make = (manual.get('make') or raw_data.get('Make') or '').strip()
    model = (manual.get('model') or manual.get('camera') or raw_data.get('Model') or '').strip()
    
    # Normalize known camera brands
    make_clean = make.title() if make.isupper() else make
    if make_clean and model:
        if model.lower().startswith(make_clean.lower()):
            camera = model
        else:
            camera = f"{make_clean} {model}"
    else:
        camera = model or make_clean

    # 4. Lens
    lens = (
        manual.get('lens')
        or raw_data.get('LensModel')
        or raw_data.get('Lens')
        or raw_data.get('LensID')
        or ''
    ).strip()

    # 5. Focal Length
    fl = manual.get('focal_length') or raw_data.get('FocalLength') or ''
    fl_str = ''
    if fl:
        m_fl = re.search(r'([\d.]+)', str(fl))
        if m_fl:
            fl_val = float(m_fl.group(1))
            fl_str = f"{int(fl_val) if fl_val.is_integer() else fl_val}mm"

    # 6. Aperture
    ap = manual.get('aperture') or raw_data.get('FNumber') or raw_data.get('Aperture')
    ap_str = ''
    if ap is not None and str(ap).strip():
        try:
            ap_val = float(ap)
            ap_str = f"f/{int(ap_val) if ap_val.is_integer() else ap_val}"
        except ValueError:
            s_ap = str(ap).strip()
            ap_str = s_ap if s_ap.startswith('f/') else f"f/{s_ap}"

    # 7. Shutter Speed
    ss = manual.get('shutter_speed') or raw_data.get('ExposureTime') or raw_data.get('ShutterSpeed') or ''
    ss_str = ''
    if ss:
        s_ss = str(ss).strip()
        if s_ss.endswith('s'):
            ss_str = s_ss
        elif '/' in s_ss:
            ss_str = f"{s_ss}s"
        else:
            try:
                val = float(s_ss)
                if 0 < val < 1:
                    ss_str = f"1/{round(1/val)}s"
                else:
                    ss_str = f"{int(val) if val.is_integer() else val}s"
            except ValueError:
                ss_str = s_ss

    # 8. ISO
    iso = manual.get('iso') or raw_data.get('ISO') or raw_data.get('PhotographicSensitivity')
    iso_str = ''
    if iso:
        s_iso = str(iso).strip()
        iso_str = s_iso if s_iso.upper().startswith('ISO') else f"ISO {s_iso}"

    # Assemble specs
    specs = [s for s in [camera, lens, fl_str, ap_str, ss_str, iso_str] if s]
    specs_str = " &middot; ".join(specs)

    return {
        'title': str(title).strip(),
        'date': date_str,
        'camera': camera,
        'lens': lens,
        'specs': specs,
        'specs_str': specs_str,
        'category': manual.get('category')
    }


def process_image(src_path: Path, dest_path: Path, target_width: int = 1200, quality: int = 50):
    """
    Open image, handle EXIF orientation, resize to target_width, and save as 50% compressed AVIF.
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src_path) as img:
        # Correct rotation based on EXIF orientation tag
        img = ImageOps.exif_transpose(img)

        # Calculate height proportional to target_width
        w, h = img.size
        target_height = max(1, int(round(h * (target_width / float(w)))))

        # Resize image using high quality Lanczos antialiasing
        resized_img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)

        # Convert palette or CMYK modes to RGB
        if resized_img.mode not in ('RGB', 'RGBA'):
            resized_img = resized_img.convert('RGB')

        # Save as AVIF with specified quality
        resized_img.save(dest_path, format="AVIF", quality=quality)


def load_manual_metadata(input_dir: Path) -> dict:
    """Load optional metadata.json from input directory if present."""
    meta_file = input_dir / "metadata.json"
    if meta_file.is_file():
        try:
            with open(meta_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[!] Warning: Failed to parse {meta_file}: {e}")
    return {}


def load_cache(cache_file: Path) -> dict:
    if cache_file.is_file():
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_cache(cache_file: Path, cache: dict):
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        print(f"[!] Warning: Could not save cache: {e}")


def generate_markdown(categories_data: dict, output_file: Path):
    """
    Generate the Zola content/photos/index.md page replicating the blog format:
    Headings: `### category (count)`
    Items: Image + `<p><strong>Title</strong> - Date</p>` + metadata caption.
    """
    lines = [
        "+++",
        'title = "photos"',
        'description = "Where my photos are located."',
        'template = "page.html"',
        "",
        "[extra]",
        "display_toc = false",
        "+++",
        ""
    ]

    total_photos = sum(len(photos) for photos in categories_data.values())

    if total_photos == 0:
        lines.append("No photos have been added yet.")
        lines.append("")
        lines.append(
            "To add photos, place images into `photos_raw/` (or subdirectories like `photos_raw/wildlife/`) "
            "and run `./process_photos.sh` before pushing."
        )
    else:
        # Sort categories alphabetically
        sorted_categories = sorted(categories_data.keys())
        for category in sorted_categories:
            photos = categories_data[category]
            if not photos:
                continue

            # Sort photos by date descending (newest first)
            photos.sort(key=lambda p: (p['date'], p['title']), reverse=True)

            # Category heading replicating blog page format: ### category_name (count)
            lines.append(f"### {category} ({len(photos)})")
            lines.append("")

            for p in photos:
                img_url = p['web_path']
                title = p['title']
                date = p['date']
                specs_str = p['specs_str']

                lines.append('<div class="photo-entry">')
                lines.append('  <div class="photo-frame">')
                lines.append(f'    <a href="{img_url}" target="_blank" rel="noopener">')
                lines.append(f'      <img src="{img_url}" alt="{title}" width="1200" loading="lazy">')
                lines.append('    </a>')
                lines.append('  </div>')
                lines.append('  <div class="photo-info">')
                lines.append(f'    <p><strong>{title}</strong> - {date}</p>')
                if specs_str:
                    lines.append(f'    <p class="photo-meta">{specs_str}</p>')
                lines.append('  </div>')
                lines.append('</div>')
                lines.append("<br>")
                lines.append("")

    content = "\n".join(lines).strip() + "\n"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(content)


def install_git_hook(repo_root: Path):
    """Install pre-push hook in .git/hooks/pre-push."""
    hook_path = repo_root / ".git" / "hooks" / "pre-push"
    hook_content = """#!/usr/bin/env bash
# Git pre-push hook to optimize photos and build site before push
set -e

echo "[pre-push] Running photo processor..."
python3 scripts/process_photos.py

echo "[pre-push] Photo processing complete!"
"""
    try:
        hook_path.parent.mkdir(parents=True, exist_ok=True)
        with open(hook_path, 'w', encoding='utf-8') as f:
            f.write(hook_content)
        hook_path.chmod(0o755)
        print(f"[✓] Git pre-push hook successfully installed at: {hook_path}")
    except Exception as e:
        print(f"[!] Error installing git hook: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Process local photos into 1200px 50% AVIF images and build photo gallery page."
    )
    parser.add_argument(
        '-i', '--input',
        default="photos_raw",
        help="Source directory for raw photos (default: photos_raw)"
    )
    parser.add_argument(
        '-o', '--output',
        default="static/assets/images/photos",
        help="Destination directory for AVIF images (default: static/assets/images/photos)"
    )
    parser.add_argument(
        '-c', '--content',
        default="content/photos/index.md",
        help="Output path for gallery markdown file (default: content/photos/index.md)"
    )
    parser.add_argument(
        '-f', '--force',
        action="store_true",
        help="Force re-converting all photos even if cached"
    )
    parser.add_argument(
        '--no-build',
        action="store_true",
        help="Skip running 'zola build' after processing"
    )
    parser.add_argument(
        '--install-hook',
        action="store_true",
        help="Install git pre-push hook and exit"
    )
    args = parser.parse_args()

    # Determine repo root (directory where zola.toml lives)
    current_dir = Path.cwd().resolve()
    repo_root = current_dir
    while repo_root != repo_root.parent and not (repo_root / "zola.toml").is_file():
        repo_root = repo_root.parent
    if not (repo_root / "zola.toml").is_file():
        repo_root = current_dir

    if args.install_hook:
        install_git_hook(repo_root)
        return

    input_dir = (repo_root / args.input).resolve()
    output_dir = (repo_root / args.output).resolve()
    content_file = (repo_root / args.content).resolve()
    cache_file = repo_root / CACHE_FILE_NAME

    print(f"=== Photo Processor ===")
    print(f"Input Directory:  {input_dir}")
    print(f"Output Directory: {output_dir}")
    print(f"Content File:     {content_file}")

    if not input_dir.is_dir():
        print(f"Creating input directory: {input_dir}")
        input_dir.mkdir(parents=True, exist_ok=True)
        readme = input_dir / "README.md"
        if not readme.is_file():
            readme.write_text(
                "# photos_raw\n\n"
                "Place your high-resolution photos here.\n"
                "You can organize them into category subfolders, for example:\n"
                "- `photos_raw/wildlife/my_photo.jpg`\n"
                "- `photos_raw/travel/scenery.png`\n\n"
                "Photos placed directly in `photos_raw/` will be placed under the 'general' category.\n"
            )

    manual_meta = load_manual_metadata(input_dir)
    cache = load_cache(cache_file) if not args.force else {}
    new_cache = {}

    # Scan for photos
    found_files = []
    for root, _, files in os.walk(input_dir):
        for f in files:
            p = Path(root) / f
            if p.suffix.lower() in IMAGE_EXTENSIONS and not f.startswith('.'):
                found_files.append(p)

    categories_data = {}
    converted_count = 0
    cached_count = 0

    for file_path in sorted(found_files):
        rel_to_input = file_path.relative_to(input_dir)
        # Determine category: subfolder name or 'general'
        parts = rel_to_input.parts
        if len(parts) > 1:
            category_name = slugify(parts[0])
        else:
            category_name = "general"

        # Check manual metadata overrides
        file_key = str(rel_to_input)
        override = manual_meta.get(file_key) or manual_meta.get(file_path.name) or {}
        if override.get('category'):
            category_name = slugify(override['category'])

        meta = parse_photo_metadata(file_path, override)
        if override.get('category'):
            category_name = slugify(override['category'])

        # Destination filename & path
        dest_filename = f"{slugify(file_path.stem)}.avif"
        dest_path = output_dir / category_name / dest_filename
        web_path = f"/assets/images/photos/{category_name}/{dest_filename}"

        # Change detection with hash and mtime
        file_hash = get_file_hash(file_path)
        cache_entry = cache.get(str(file_path))
        needs_convert = (
            args.force
            or not dest_path.is_file()
            or not cache_entry
            or cache_entry.get('hash') != file_hash
        )

        if needs_convert:
            print(f"  [+] Converting: {rel_to_input} -> {dest_path.relative_to(repo_root)}")
            try:
                process_image(file_path, dest_path, target_width=1200, quality=50)
                converted_count += 1
            except Exception as e:
                print(f"  [!] Error processing {file_path}: {e}")
                continue
        else:
            cached_count += 1

        new_cache[str(file_path)] = {
            'hash': file_hash,
            'dest': str(dest_path),
            'mtime': os.path.getmtime(file_path)
        }

        # Add to category collection
        photo_info = {
            'title': meta['title'],
            'date': meta['date'],
            'specs_str': meta['specs_str'],
            'web_path': web_path,
            'dest_path': dest_path
        }
        categories_data.setdefault(category_name, []).append(photo_info)

    save_cache(cache_file, new_cache)

    print(f"\nProcessing Summary:")
    print(f"  Converted: {converted_count}")
    print(f"  Cached/Unchanged: {cached_count}")
    print(f"  Total Categories: {len(categories_data)}")

    # Generate content/photos/index.md
    print(f"\nWriting gallery page to: {content_file.relative_to(repo_root)}")
    generate_markdown(categories_data, content_file)

    # Run zola build if requested
    if not args.no_build:
        print("\nRunning 'zola build' to update public/ directory...")
        try:
            res = subprocess.run(['zola', 'build'], cwd=repo_root, check=True)
            print("[✓] 'zola build' completed successfully!")
        except Exception as e:
            print(f"[!] Warning: 'zola build' encountered an issue: {e}")

    print("\n[✓] Done! You're ready to push to GitHub.")


if __name__ == '__main__':
    main()
