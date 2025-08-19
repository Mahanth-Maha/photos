"""
Generate or update a Hugo-style index.md front matter for a photo directory.

- Reads image files in a directory.
- Extracts per-image date (EXIF DateTimeOriginal) and GPS (as "lat,lon" string) when available.
- Applies common tags (comma-separated argument) to every image.
- Applies default location if no GPS/location metadata.
- Creates index.md if missing with a simple template; preserves non-resource fields if present.
- Updates *only* the `resources` list: adds new images, removes missing ones, and re-sorts by filename.
- Sets `title` (per-image) to the filename (without extension).
- Sets `params.weight` incrementally based on sorted order (1..N).
- Marks the first image as `params: {cover: true}` if no cover is already present.
"""
import argparse
import os
import sys
import re
import datetime as dt
from pathlib import Path
from typing import Dict, Any, List, Tuple

try:
    from PIL import Image, ExifTags
except Exception as e:
    Image = None
    ExifTags = None
try:
    import yaml
except Exception as e:
    yaml = None

FRONT_MATTER_DELIM = '---'
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG'}

def die(msg: str, code: int = 1):
    print(f"[Error] {msg}", file=sys.stderr)
    sys.exit(code)

def parse_args():
    p = argparse.ArgumentParser(description="Build or update index.md for a photo directory.")
    p.add_argument("directory", help="Path to the directory containing images and/or index.md")
    p.add_argument("--common-tags", default="", help="Comma-separated list of tags to apply to all images")
    p.add_argument("--default-location", default="", help="Fallback location (string) when location metadata is absent")
    p.add_argument("--page-title", default=None, help="Title to use when creating a new index.md (defaults to directory name)")
    p.add_argument("--page-date", default=None, help="Date (YYYY-MM-DD) for new index.md front matter (defaults to today)")
    p.add_argument("--description", default="Photos.", help="Description for new index.md if created")
    p.add_argument("--categories", default="", help='Comma-separated categories for new index.md (e.g. "travel,india,kerala")')
    p.add_argument("--featured", action="store_true", help="If set, add params.featured: true in new index.md")
    p.add_argument("--dry-run", action="store_true", help="Print what would change without writing")
    return p.parse_args()

def split_front_matter(text: str) -> Tuple[str, Dict[str, Any], str]:
    """
    Returns (leading_text, front_matter_dict, trailing_text_after_front_matter).
    If no front matter, returns ("", {}, original_text)
    """
    lines = text.splitlines()
    if len(lines) >= 1 and lines[0].strip() == FRONT_MATTER_DELIM:
        # find closing delim
        try:
            end_idx = next(i for i in range(1, len(lines)) if lines[i].strip() == FRONT_MATTER_DELIM)
        except StopIteration:
            # malformed; treat as no front matter
            return "", {}, text
        fm_text = "\n".join(lines[1:end_idx])
        rest = "\n".join(lines[end_idx+1:])
        data = yaml.safe_load(fm_text) if fm_text.strip() else {}
        if data is None:
            data = {}
        return "", data, rest
    else:
        return "", {}, text

# def join_front_matter(front: Dict[str, Any]) -> str:
#     return FRONT_MATTER_DELIM + "\n" + yaml.safe_dump(front, sort_keys=False, allow_unicode=True).strip() + "\n" + FRONT_MATTER_DELIM + "\n"

def join_front_matter(front: Dict[str, Any]) -> str:
    class NoAliasDumper(yaml.SafeDumper):
        def ignore_aliases(self, data):
            return True
    dumped = yaml.dump(front, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=True)
    return FRONT_MATTER_DELIM + "\n" + dumped.strip() + "\n" + FRONT_MATTER_DELIM + "\n"

def list_images(dir_path: Path) -> List[Path]:
    return sorted([p for p in dir_path.iterdir() if p.is_file() and p.suffix in IMAGE_EXTS], key=lambda p: p.name)

def exif_to_dict(img) -> Dict[int, Any]:
    try:
        exif = img._getexif()  # type: ignore[attr-defined]
        return exif or {}
    except Exception:
        return {}

def dms_to_deg(value, ref):
    try:
        d = float(value[0][0]) / float(value[0][1])
        m = float(value[1][0]) / float(value[1][1])
        s = float(value[2][0]) / float(value[2][1])
        deg = d + (m / 60.0) + (s / 3600.0)
        if ref in ['S', 'W']:
            deg = -deg
        return deg
    except Exception:
        return None

def extract_metadata(img_path: Path) -> Tuple[str, str]:
    """
    Returns (date_str, location_str). If missing, returns ("", "").
    date_str format: YYYY-MM-DD
    location_str format: "lat,lon" with up to 6 decimals, if GPS found; else "".
    """
    date_str = ""
    loc_str = ""
    if Image is None:
        return date_str, loc_str
    try:
        with Image.open(img_path) as im:
            exif = exif_to_dict(im)
            if exif and ExifTags is not None:
                tag_map = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}
                # DateTimeOriginal
                for k in ("DateTimeOriginal", "DateTime", "CreateDate"):
                    if k in tag_map and isinstance(tag_map[k], str):
                        # EXIF datetime format: "YYYY:MM:DD HH:MM:SS"
                        m = re.match(r"(\d{4}):(\d{2}):(\d{2})", tag_map[k])
                        if m:
                            date_str = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
                            break
                # GPS
                if "GPSInfo" in tag_map:
                    gps = tag_map["GPSInfo"]
                    gps_tag_map = {}
                    if isinstance(gps, dict):
                        gps_tag_map = {ExifTags.GPSTAGS.get(k, k): v for k, v in gps.items()}
                    lat = lon = None
                    if "GPSLatitude" in gps_tag_map and "GPSLatitudeRef" in gps_tag_map:
                        lat = dms_to_deg(gps_tag_map["GPSLatitude"], gps_tag_map["GPSLatitudeRef"])
                    if "GPSLongitude" in gps_tag_map and "GPSLongitudeRef" in gps_tag_map:
                        lon = dms_to_deg(gps_tag_map["GPSLongitude"], gps_tag_map["GPSLongitudeRef"])
                    if lat is not None and lon is not None:
                        loc_str = f"{lat:.6f},{lon:.6f}"
            # Fall back to file modified time for date
            if not date_str:
                ts = img_path.stat().st_mtime
                date_str = dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    except Exception:
        # ignore failures, keep empty loc/date if not set
        try:
            ts = img_path.stat().st_mtime
            date_str = dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        except Exception:
            pass
    return date_str, loc_str

def build_resource_for_image(img_path: Path, common_tags: List[str], default_location: str) -> Dict[str, Any]:
    date_str, loc_str = extract_metadata(img_path)
    location_val = loc_str if loc_str else default_location
    title = img_path.stem
    params = {"date": date_str}
    if location_val:
        params["location"] = location_val
    if common_tags:
        # params["tags"] = common_tags
        params["tags"] = list(common_tags)
    resource = {
        "src": img_path.name,
        "title": title,
        "params": params
    }
    return resource

def ensure_cover(resources: List[Dict[str, Any]]):
    # If none has cover true, set the first to have cover: true (but don't overwrite existing params)
    any_cover = False
    for r in resources:
        if isinstance(r.get("params"), dict) and r["params"].get("cover") is True:
            any_cover = True
            break
    if not any_cover and resources:
        resources[0].setdefault("params", {})
        resources[0]["params"]["cover"] = True

def resources_to_dict(resources: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {r.get("src"): r for r in resources if isinstance(r, dict) and r.get("src")}

def update_weights(sorted_resources: List[Dict[str, Any]]):
    for idx, r in enumerate(sorted_resources, start=1):
        r.setdefault("params", {})
        r["params"]["weight"] = idx

def update_weights_preserve_existing(sorted_resources: list, previous_by_src: dict):
    """
    Keep existing weights exactly as they are.
    For resources without a weight (i.e., new images), assign weights
    starting from (max existing weight + 1) in filename order.
    """
    # Collect existing weights
    existing_weights = {}
    for src, r in previous_by_src.items():
        try:
            w = int(r.get("params", {}).get("weight"))
            existing_weights[src] = w
        except (TypeError, ValueError):
            pass

    max_w = max(existing_weights.values(), default=0)

    # First pass: ensure params dict exists
    for r in sorted_resources:
        r.setdefault("params", {})

    # Second pass: assign only to ones missing weight
    next_w = max_w + 1
    for r in sorted_resources:
        if "weight" not in r["params"] or r["params"]["weight"] in (None, ""):
            r["params"]["weight"] = next_w
            next_w += 1

def main():
    args = parse_args()
    if yaml is None:
        die("PyYAML is required. Install with: pip install pyyaml")
    dir_path = Path(args.directory).resolve()
    if not dir_path.exists() or not dir_path.is_dir():
        die(f"Directory not found: {dir_path}")

    index_path = dir_path / "index.md"
    images = list_images(dir_path)
    common_tags = [t.strip() for t in args.common_tags.split(",") if t.strip()]

    if not images:
        print("[INFO] No images found. Supported extensions:", ", ".join(sorted(IMAGE_EXTS)))
    
    front: Dict[str, Any] = {}
    trailing_body = ""

    if index_path.exists():
        text = index_path.read_text(encoding="utf-8")
        _, front, trailing_body = split_front_matter(text)
        if not isinstance(front, dict):
            front = {}
    else:
        # Create a minimal template
        page_title = args.page_title or dir_path.name
        page_date = args.page_date or dt.date.today().strftime("%Y-%m-%d")
        categories = [c.strip() for c in args.categories.split(",") if c.strip()]
        front = {
            "title": page_title,
            "date": page_date,
            "description": args.description,
        }
        if categories:
            front["categories"] = categories
        if args.featured:
            front.setdefault("params", {})
            front["params"]["featured"] = True

    # Preserve any existing non-resource keys; rebuild only resources
    existing_resources = front.get("resources", [])
    existing_by_src = resources_to_dict(existing_resources) if isinstance(existing_resources, list) else {}

    # Build desired set from filesystem
    desired_by_src: Dict[str, Dict[str, Any]] = {}
    for img in images:
        desired_by_src[img.name] = build_resource_for_image(img, common_tags, args.default_location)

    # Merge strategy:
    # - Add new images from desired_by_src that are not in existing_by_src
    # - For images present in both, we keep existing entries BUT we update date/location/tags if missing there
    #   and always ensure title = filename stem.
    # - Remove entries whose src no longer exists on disk.
    merged: List[Dict[str, Any]] = []
    for src in sorted(desired_by_src.keys()):
        if src in existing_by_src:
            r = existing_by_src[src]
            r["title"] = Path(src).stem
            r.setdefault("params", {})
            # only fill if absent
            for key in ("date", "location", "tags"):
                if key not in r["params"] or r["params"].get(key) in (None, "", []):
                    val = desired_by_src[src]["params"].get(key)
                    if val not in (None, "", []):
                        r["params"][key] = val
            merged.append(r)
        else:
            merged.append(desired_by_src[src])

    # Remove any resources not present on disk (implicitly by rebuilding merged only from desired keys)

    # Update weights based on sorted order by filename
    # update_weights(merged)
    update_weights_preserve_existing(merged, existing_by_src)

    # Ensure a cover image is set if none exists
    ensure_cover(merged)

    # Write back
    front["resources"] = merged

    output_text = join_front_matter(front)
    if trailing_body.strip():
        output_text += trailing_body if output_text.endswith("\n") else "\n" + trailing_body

    if args.dry_run:
        print("----- DRY RUN: index.md would be -----")
        print(output_text)
        return

    index_path.write_text(output_text, encoding="utf-8")
    print(f"[INFO] Updated: {index_path}")
    print(f"[INFO] Images found: {len(images)}")
    if not images:
        print("[Tip] Add images (jpg/jpeg/png) to the directory and run again.")
    print("[INFO] Done.")

if __name__ == "__main__":
    main()
    
    
