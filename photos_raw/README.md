# Raw photos input directory
# Place local photos here before running `./process_photos.sh`

You can organize photos by category into subfolders:
- `photos_raw/wildlife/my_goose.jpg` -> appears under `### wildlife` heading
- `photos_raw/travel/paris.jpg`      -> appears under `### travel` heading
- `photos_raw/photo.jpg`             -> appears under `### general` heading

Supported formats: JPG, PNG, WEBP, TIFF, HEIC, AVIF, RAW (CR2, NEF, ARW, DNG, etc.)

When you run `./process_photos.sh` before pushing to GitHub:
1. Photos are resized to 1200px wide and compressed into 50% quality .AVIF files.
2. Saved to `static/assets/images/photos/<category>/`.
3. EXIF metadata (title, date, camera, lens, focal length, aperture, shutter speed, ISO) is extracted.
4. `content/photos/index.md` is updated with categories matching the blog page structure.
5. `zola build` compiles the site and updates `public/`.

### Optional Manual Metadata
If you have photos that don't have EXIF metadata or you want custom titles/dates, you can create a `metadata.json` in this folder:
```json
{
  "my_photo.jpg": {
    "title": "Canada Goose at Sunset",
    "date": "2026-10-24",
    "category": "wildlife",
    "camera": "Sony A7 IV",
    "lens": "FE 24-70mm F2.8 GM",
    "focal_length": "50mm",
    "aperture": "f/2.8",
    "shutter_speed": "1/500s",
    "iso": "ISO 100"
  }
}
```
