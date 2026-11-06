# Raw Photos Input Directory

Place your local photos here before running `./process_photos.sh`.

### Directory & Category Structure

You can organize photos using 1 or 2 levels of categories:

#### 1. Two Levels: `category -> subcategory (latin name or species)`
```
photos_raw/
├── other birds/
│   ├── branta canadensis/
│   │   └── goose.jpg
│   └── junco hyemalis/
│       └── junco.cr2
└── plants/
    └── hydrangea quercifolia/
        └── oakleaf.jpg
```
On the photos page, this renders as:
- `### other birds (2)`
  - `#### branta canadensis (1)`
  - `#### junco hyemalis (1)`
- `### plants (1)`
  - `#### hydrangea quercifolia (1)`

#### 2. Single Level: `category` only
```
photos_raw/
└── infrastructure/
    └── insulators_and_taps.cr2
```
Renders directly as:
- `### infrastructure (1)`

#### 3. Root Level: `photos_raw/<image>`
Photos placed directly in `photos_raw/` fall under the `general` category heading.

---

### How to Run

Before pushing to GitHub, run:
```bash
./process_photos.sh
```

Supported formats: JPG, PNG, WEBP, TIFF, HEIC, AVIF, and Camera RAW (CR2, NEF, ARW, DNG, etc.).
Photos are converted to 1200px wide, 50% compressed .AVIF images, metadata is extracted, and `zola build` is executed.
