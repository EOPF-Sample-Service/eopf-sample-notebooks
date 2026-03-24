#!/usr/bin/env python3
"""
Auto-generate MyST gallery pages with categorized notebook cards
Supports both explicit tags in notebook metadata and automatic content analysis
"""

import json
import argparse
from pathlib import Path
from collections import Counter
import nbformat


def extract_notebook_metadata_and_content(notebook_path):
    """Extract explicit tags and metadata from Jupyter notebook frontmatter only"""
    try:
        with open(notebook_path, "r", encoding="utf-8") as f:
            nb = nbformat.read(f, as_version=4)

        content = []
        imports = []
        explicit_tags = []
        explicit_title = None
        explicit_description = None
        explicit_subtitle = None
        explicit_authors = []
        explicit_keywords = None

        # Process cells - only look for YAML frontmatter in first markdown cell
        for cell in nb.cells:
            if cell.cell_type == "markdown":
                source = cell.source
                content.append(source)

                # Check for YAML frontmatter in first markdown cell only
                if source.strip().startswith("---"):
                    try:
                        import yaml

                        # Extract YAML frontmatter
                        lines = source.split("\n")
                        yaml_end = -1
                        for i, line in enumerate(lines[1:], 1):
                            if line.strip() == "---":
                                yaml_end = i
                                break

                        if yaml_end > 0:
                            yaml_content = "\n".join(lines[1:yaml_end])
                            frontmatter = yaml.safe_load(yaml_content)

                            # Extract metadata from frontmatter
                            if "title" in frontmatter:
                                explicit_title = frontmatter["title"]
                            if "subtitle" in frontmatter:
                                explicit_subtitle = frontmatter["subtitle"]
                            if "keywords" in frontmatter:
                                if isinstance(frontmatter["keywords"], str):
                                    explicit_keywords = frontmatter["keywords"]
                                elif isinstance(frontmatter["keywords"], list):
                                    explicit_keywords = ", ".join(
                                        frontmatter["keywords"]
                                    )
                            if "authors" in frontmatter:
                                explicit_authors = frontmatter["authors"]

                            # Look for tags in frontmatter
                            if "tags" in frontmatter:
                                if isinstance(frontmatter["tags"], list):
                                    explicit_tags.extend(frontmatter["tags"])
                                elif isinstance(frontmatter["tags"], str):
                                    explicit_tags.extend(
                                        [
                                            tag.strip()
                                            for tag in frontmatter["tags"].split(",")
                                        ]
                                    )

                    except ImportError:
                        print("    ⚠️  PyYAML not available for frontmatter parsing")
                    except Exception as e:
                        print(f"    ⚠️  Error parsing frontmatter: {e}")

                # Break after first markdown cell (frontmatter should be first)
                break

            elif cell.cell_type == "code":
                source = cell.source
                content.append(source)

                # Extract imports
                for line in source.split("\n"):
                    line = line.strip()
                    if line.startswith(("import ", "from ")) and not line.startswith(
                        "#"
                    ):
                        imports.append(line)

        # Generate description from subtitle if not explicitly set
        if not explicit_description and explicit_subtitle:
            explicit_description = explicit_subtitle

        return {
            "content": " ".join(content),
            "imports": imports,
            "explicit_tags": list(set(explicit_tags)),  # Remove duplicates
            "explicit_title": explicit_title,
            "explicit_description": explicit_description,
            "explicit_subtitle": explicit_subtitle,
            "explicit_authors": explicit_authors,
            "explicit_keywords": explicit_keywords,
        }

    except Exception as e:
        print(f"Error reading {notebook_path}: {e}")
        return {
            "content": "",
            "imports": [],
            "explicit_tags": [],
            "explicit_title": None,
            "explicit_description": None,
            "explicit_subtitle": None,
            "explicit_authors": [],
            "explicit_keywords": None,
        }


def enhanced_tag_detection(notebook_data, filename):
    """Extract tags from frontmatter only"""

    # Only use frontmatter tags
    if notebook_data["explicit_tags"]:
        print(f"    ✅ Found frontmatter tags: {notebook_data['explicit_tags']}")
        return notebook_data["explicit_tags"]

    # No fallback - frontmatter only
    print("    ⚠️  No frontmatter tags found")
    return []


def find_all_notebooks(root_dir):
    """Find all notebooks in directory structure, excluding templates"""
    notebook_files = []
    root_path = Path(root_dir)

    # Files to exclude from gallery
    exclude_patterns = [
        "*template*",  # Any file with "template" in the name
        "template.ipynb",  # Specific file
    ]

    for notebook_file in root_path.rglob("*.ipynb"):
        # Skip hidden files and checkpoint files
        if any(part.startswith(".") for part in notebook_file.parts):
            continue

        # Skip template files
        should_exclude = False
        for pattern in exclude_patterns:
            if notebook_file.match(pattern):
                print(f"    🚫 Excluding template: {notebook_file.name}")
                should_exclude = True
                break

        if not should_exclude:
            notebook_files.append(notebook_file)

    return notebook_files


def extract_notebook_title(notebook_path):
    """Extract title from notebook metadata or first heading"""
    try:
        with open(notebook_path, "r", encoding="utf-8") as f:
            nb = nbformat.read(f, as_version=4)

        # Check notebook metadata first
        if "title" in nb.metadata:
            return nb.metadata["title"]

        # Look for first markdown heading
        for cell in nb.cells:
            if cell.cell_type == "markdown":
                lines = cell.source.split("\n")
                for line in lines:
                    line = line.strip()
                    if line.startswith("# "):
                        return line[2:].strip()

        # Fallback to filename
        return notebook_path.stem.replace("-", " ").replace("_", " ").title()

    except Exception:
        return notebook_path.stem.replace("-", " ").replace("_", " ").title()


def enhanced_title_extraction(notebook_path, notebook_data):
    """Enhanced title extraction with frontmatter priority"""

    # Use frontmatter title if available
    if notebook_data["explicit_title"]:
        return notebook_data["explicit_title"]

    # Fall back to existing extraction logic
    return extract_notebook_title(notebook_path)


def render_tags_html(tags, has_explicit_tags=False, max_visible=3):
    """Render tags as styled HTML elements"""
    if not tags:
        return ""

    visible_tags = tags[:max_visible]
    remaining_count = len(tags) - max_visible

    tag_html = '<div class="gallery-tags">'

    # Render visible tags
    for tag in visible_tags:
        # Normalize tag name for CSS class
        css_class = tag.replace("-", "-").replace("_", "-")
        tag_html += f'<span class="tag {css_class}">{tag}</span>'

    # Add "more" indicator if there are additional tags
    if remaining_count > 0:
        tag_html += f'<span class="tag-more">+{remaining_count} more</span>'

    tag_html += "</div>"
    return tag_html


def render_simple_tags(tags, has_explicit_tags=False, max_visible=3):
    """Render tags as simple text (MyST-compatible)"""
    if not tags:
        return ""

    visible_tags = tags[:max_visible]
    remaining_count = len(tags) - max_visible

    # Create simple tag display
    tag_text = "**Tags:** " + ", ".join(visible_tags)

    if remaining_count > 0:
        tag_text += f", +{remaining_count} more"

    return tag_text


def generate_gallery_pages(notebook_tags, output_dir="notebooks"):
    """Generate MyST gallery pages with enhanced styling"""

    categories = {
        "sentinel": {
            "title": "Sentinel Data",
            "description": (
                "Notebooks showcasing Sentinel mission data processing and analysis"
            ),
            "file": f"{output_dir}/gallery-sentinel.md",
        },
        "topics": {
            "title": "Application Topics",
            "description": (
                "Notebooks organized by Earth observation application domains"
            ),
            "file": f"{output_dir}/gallery-topics.md",
        },
        "tools": {
            "title": "Tools & Libraries",
            "description": (
                "Notebooks demonstrating different software tools and libraries"
            ),
            "file": f"{output_dir}/gallery-tools.md",
        },
        "tutorials": {
            "title": "Tutorials",
            "description": (
                "Notebooks demonstrating the main workflows for accessing and processing data"
            ),
            "file": f"{output_dir}/gallery-tutorials.md",
        },
    }

    # Create output directory if it doesn't exist
    Path(output_dir).mkdir(exist_ok=True)

    # Generate main gallery index
    with open(f"{output_dir}/gallery.md", "w") as f:
        f.write("""---
title: Gallery
---

## How to run the notebooks

The notebooks can be run on the **EOPF Sentinel Zarr Samples JupyterHub**. Each notebook integrates a Launch in JupyterHub button.

![Screenshot: Launch Notebook button](static/launch_notebook.jpg)

---

Click **Sign in with CDSE IdP** to proceed.

You will be redirected to the CDSE login page:

![Screenshot: CDSE Login Page](static/CDSE_login.png)

---

Please log in using your **CDSE user account**.  
If you do not have one, create one now, it's free!

Once logged in, you will be able to run your notebook in JupyterLab!

---

If you encounter any problem or have suggestions, please let us know on GitHub, opening a new issue [here](https://github.com/EOPF-Sample-Service/eopf-sample-notebooks/issues).


## Notebooks Gallery

Click on the category to explore the corresponding notebooks!

### Sentinel Data
<a class="link" href="gallery-sentinel#sentinel-1" ><p style="background-color:white;"><span class="gallery-tag tag-sentinel-1">🛰️ sentinel-1</span></p></a>
<a class="link" href="gallery-sentinel#sentinel-2" ><p style="background-color:white;"><span class="gallery-tag tag-sentinel-2">🛰️ sentinel-2</span></p></a>
<a class="link" href="gallery-sentinel#sentinel-3" ><p style="background-color:white;"><span class="gallery-tag tag-sentinel-3">🛰️ sentinel-3</span></p></a>
                
### Application Topics
<a class="link" href="gallery-topics#land-applications" ><p style="background-color:white;"><span class="gallery-tag tag-land">🌱 land</span></p></a>
<a class="link" href="gallery-topics#climate-monitoring" ><p style="background-color:white;"><span class="gallery-tag tag-climate-change">🌡️ climate-change</span></p></a>
<a class="link" href="gallery-topics#marine-applications" ><p style="background-color:white;"><span class="gallery-tag tag-marine">🌊 marine</span></p></a>
<a class="link" href="gallery-topics#emergency-and-security-applications" ><p style="background-color:white;"><span class="gallery-tag tag-security">🔒 security</span></p></a>

### Tools & Libraries
<a class="link" href="gallery-tools/#xarray" ><p style="background-color:white;"><span class="gallery-tag tag-xarray">📊 xarray</span></p></a>
<a class="link" href="gallery-tools/#xarray-eopf-plugin" ><p style="background-color:white;"><span class="gallery-tag tag-xarray-eopf">🔌 xarray-eopf</span></p></a>
<a class="link" href="gallery-tools/#xcube-eopf-plugin" ><p style="background-color:white;"><span class="gallery-tag tag-xcube">🏷️ xcube</span></p></a>
<a class="link" href="gallery-tools/#gdal" ><p style="background-color:white;"><span class="gallery-tag tag-gdal">🗺️ gdal</span></p></a>

### Basic Tutorials
<a class="link" href="gallery-tutorials/#dask" ><p style="background-color:white;"><span class="gallery-tag tag-dask">🧮 dask</span></p></a>
<a class="link" href="gallery-tutorials/#basic-data-access" ><p style="background-color:white;"><span class="gallery-tag tag-basic">👶 basic</span></p></a>

""")

    # Generate Sentinel category page
    with open(categories["sentinel"]["file"], "w") as f:
        f.write(f"""---
title: {categories["sentinel"]["title"]}
---

# {categories["sentinel"]["title"]}

<a class="link" href="gallery-sentinel#sentinel-1" ><p style="background-color:white;"><span class="gallery-tag tag-sentinel-1">🛰️ sentinel-1</span></p></a>
<a class="link" href="gallery-sentinel#sentinel-2" ><p style="background-color:white;"><span class="gallery-tag tag-sentinel-2">🛰️ sentinel-2</span></p></a>
<a class="link" href="gallery-sentinel#sentinel-3" ><p style="background-color:white;"><span class="gallery-tag tag-sentinel-3">🛰️ sentinel-3</span></p></a>

{categories["sentinel"]["description"]}

## Sentinel-1

```{{gallery-grid}}
:category: sentinel-1
:columns: 1 1 2 3
```

## Sentinel-2

```{{gallery-grid}}
:category: sentinel-2
:columns: 1 1 2 3
```

## Sentinel-3

```{{gallery-grid}}
:category: sentinel-3
:columns: 1 1 2 3
```

""")

    # Generate Topics category page
    with open(categories["topics"]["file"], "w") as f:
        f.write(f"""---
title: {categories["topics"]["title"]}
---

# {categories["topics"]["title"]}

<a class="link" href="gallery-topics#land-applications" ><p style="background-color:white;"><span class="gallery-tag tag-land">🌱 land</span></p></a>
<a class="link" href="gallery-topics#climate-monitoring" ><p style="background-color:white;"><span class="gallery-tag tag-climate-change">🌡️ climate-change</span></p></a>
<a class="link" href="gallery-topics#marine-applications" ><p style="background-color:white;"><span class="gallery-tag tag-marine">🌊 marine</span></p></a>
<a class="link" href="gallery-topics#emergency-and-security-applications" ><p style="background-color:white;"><span class="gallery-tag tag-security">🔒 security</span></p></a>


{categories["topics"]["description"]}

## Land Applications

```{{gallery-grid}}
:category: land
:columns: 1 1 2 3
```

## Climate Monitoring

```{{gallery-grid}}
:category: climate-change
:columns: 1 1 2 3
```

## Marine Applications

```{{gallery-grid}}
:category: marine
:columns: 1 1 2 3
```

## Emergency and Security Applications

```{{gallery-grid}}
:category: security
:columns: 1 1 2 3
```

""")

    # Generate Tools category page
    with open(categories["tools"]["file"], "w") as f:
        f.write(f"""---
title: {categories["tools"]["title"]}
---

# {categories["tools"]["title"]}

<a class="link" href="gallery-tools/#xarray" ><p style="background-color:white;"><span class="gallery-tag tag-xarray">📊 xarray</span></p></a>
<a class="link" href="gallery-tools/#xarray-eopf-plugin" ><p style="background-color:white;"><span class="gallery-tag tag-xarray-eopf">🔌 xarray-eopf</span></p></a>
<a class="link" href="gallery-tools/#xcube-eopf-plugin" ><p style="background-color:white;"><span class="gallery-tag tag-xcube">🏷️ xcube</span></p></a>
<a class="link" href="gallery-tools/#gdal" ><p style="background-color:white;"><span class="gallery-tag tag-gdal">🗺️ gdal</span></p></a>

{categories["tools"]["description"]}

## Xarray

```{{gallery-grid}}
:category: xarray
:columns: 1 1 2 3
```

## xarray-eopf plugin

```{{gallery-grid}}
:category: xarray-eopf
:columns: 1 1 2 3
```

## xcube-eopf plugin

```{{gallery-grid}}
:category: xcube
:columns: 1 1 2 3
```

## GDAL

```{{gallery-grid}}
:category: gdal
:columns: 1 1 2 3
```

## STAC

```{{gallery-grid}}
:category: stac
:columns: 1 1 2 3
```

""")

    # Generate Tutorials category page
    with open(categories["tutorials"]["file"], "w") as f:
        f.write(f"""---
title: {categories["tutorials"]["title"]}
---

# {categories["tutorials"]["title"]}

<a class="link" href="gallery-tutorials/#dask" ><p style="background-color:white;"><span class="gallery-tag tag-dask">🧮 dask</span></p></a>
<a class="link" href="gallery-tutorials/#basic-data-access" ><p style="background-color:white;"><span class="gallery-tag tag-basic">👶 basic</span></p></a>

{categories["tutorials"]["description"]}

## Dask

```{{gallery-grid}}
:category: dask
:columns: 1 1 2 3
```

## Basic Data Access

```{{gallery-grid}}
:category: basic
:columns: 1 1 2 3
```

        """)


def analyze_notebook_content(notebook_tags):
    """Provide analysis of what was found"""
    tag_counts = Counter()

    for path, meta in notebook_tags.items():
        for tag in meta["tags"]:
            tag_counts[tag] += 1

    print("\n📊 Content Analysis Summary:")
    print("=" * 50)

    print(f"\n📓 Total notebooks with frontmatter tags: {len(notebook_tags)}")

    print("\n🏷️  Most common tags:")
    for tag, count in tag_counts.most_common(10):
        print(f"  {tag}: {count} notebooks")

    print("\n📂 Notebooks by folder:")
    folder_counts = Counter(meta["folder"] for meta in notebook_tags.values())
    for folder, count in folder_counts.items():
        print(f"  {folder}: {count} notebooks")


def analyze_notebooks(root_dir="notebooks"):
    """Analyze all notebooks and extract tags from frontmatter"""
    print(f"🔍 Analyzing notebooks in {root_dir} for frontmatter tags...")

    notebook_files = find_all_notebooks(root_dir)

    print(f"📓 Found {len(notebook_files)} Jupyter notebooks")

    notebook_tags = {}
    skipped_count = 0

    for file_path in notebook_files:
        print(f"  🔎 Analyzing: {file_path.name}")

        # Extract notebook metadata and content
        notebook_data = extract_notebook_metadata_and_content(file_path)

        relative_path = str(file_path.relative_to(root_dir)).replace("\\", "/")
        if relative_path.endswith(".ipynb"):
            relative_path = relative_path[:-6]  # Remove .ipynb extension

        # Get tags from frontmatter only
        tags = enhanced_tag_detection(notebook_data, file_path.name)

        # Get title (frontmatter first, then automatic)
        title = enhanced_title_extraction(file_path, notebook_data)

        if tags:  # Only include if we found tags
            notebook_tags[relative_path] = {
                "title": title,
                "description": notebook_data["explicit_description"] or "",
                "tags": tags,
                "full_path": str(file_path),
                "folder": (
                    str(file_path.parent.relative_to(root_dir))
                    if file_path.parent != Path(root_dir)
                    else "root"
                ),
                "imports": notebook_data["imports"][:5],
                "has_explicit_tags": bool(notebook_data["explicit_tags"]),
            }
        else:
            print(f"    ❌ Skipped: No frontmatter tags found for {file_path.name}")
            skipped_count += 1

    if skipped_count > 0:
        print(f"\n⚠️  Skipped {skipped_count} notebooks without frontmatter tags")
        print("💡 Add YAML frontmatter with tags to include these notebooks")

    return notebook_tags


def export_metadata_for_plugin(notebook_tags, output_dir="notebooks"):
    """Export notebook metadata for MyST plugin"""
    metadata_file = Path(output_dir) / ".gallery-metadata.json"

    # Convert metadata to plugin-friendly format
    plugin_metadata = {}
    for path, meta in notebook_tags.items():
        plugin_metadata[path] = {
            "title": meta["title"],
            "description": meta.get("description", ""),
            "tags": meta["tags"],
            "has_explicit_tags": meta.get("has_explicit_tags", False),
            "folder": meta["folder"],
        }

    with open(metadata_file, "w") as f:
        json.dump(plugin_metadata, f, indent=2)

    print(f"✅ Exported metadata: {metadata_file}")


def generate_toc_entries(notebook_tags):
    """Generate MyST TOC entries for all notebooks - SINGLE FUNCTION ONLY"""
    print("\n📋 MyST TOC entries for myst.yml:")
    print("Add these to your 'toc:' section:")
    print("\n```yaml")

    for notebook_path in sorted(notebook_tags.keys()):
        print(f"        - file: notebooks/{notebook_path}")

    print("```")


def print_tag_examples():
    """Print examples of how to add frontmatter tags to notebooks"""
    print("\n📝 How to add frontmatter tags to your notebooks:")
    print("=" * 60)

    print("\n🟢 YAML Frontmatter (Recommended)")
    print("Add this to the FIRST markdown cell of your notebook:")
    print("""
---
title: Your Notebook Title
subtitle: Descriptive subtitle for gallery
tags: ["sentinel-2", "land", "xarray", "deforestation"]
keywords: ["earth observation", "remote sensing", "forest monitoring"]
authors:
  - name: Your Name
    orcid: 0000-0000-0000-0000
    github: yourusername
    affiliations:
      - id: Your Institution
        institution: Your Institution Name
        ror: your-ror-id
date: 2025-03-04
---

# Your Notebook Content Starts Here
...
""")

    print("\n📝 Available tag categories:")
    print("  Sentinel: sentinel-1, sentinel-2, sentinel-3")
    print("  Topics: land, climate-change, marine, security")
    print("  Tools: xarray, xarray-eopf, xcube, gdal, snap, stac, zarr, dask")
    print("  Levels: level-1, level-2")
    print("\n💡 Tags from frontmatter take priority over automatic detection")
    print("💡 If no tags are found, keywords will be converted to tags automatically")
    print("\n🚫 To disable auto-tagging: python generate_gallery.py --no-auto-tag")


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Generate MyST gallery pages from Jupyter notebooks with frontmatter tags",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python generate_gallery.py                    # Generate gallery from notebooks/
  python generate_gallery.py --dir my_notebooks # Custom directory
  python generate_gallery.py --verbose          # Verbose output
        """,
    )

    parser.add_argument(
        "--dir",
        "--directory",
        default="notebooks",
        help="Directory containing notebooks (default: notebooks)",
    )

    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )

    return parser.parse_args()


if __name__ == "__main__":
    # Parse command line arguments
    args = parse_arguments()

    ROOT_DIR = args.dir

    # Clean up existing gallery files first
    gallery_files = [
        f"{ROOT_DIR}/gallery.md",
        f"{ROOT_DIR}/gallery-sentinel.md",
        f"{ROOT_DIR}/gallery-topics.md",
        f"{ROOT_DIR}/gallery-tools.md",
        f"{ROOT_DIR}/gallery-tutorials.md",
    ]
    for file_path in gallery_files:
        if Path(file_path).exists():
            Path(file_path).unlink()
            if args.verbose:
                print(f"🗑️  Removed old {file_path}")

    # Display configuration
    print("🧠 Notebook Gallery Generator")
    print("=" * 40)
    print(f"📁 Directory: {ROOT_DIR}")
    print("🏷️  Only notebooks with YAML frontmatter tags will be included")
    print()

    print("🔍 Starting notebook analysis...")
    notebook_tags = analyze_notebooks(ROOT_DIR)

    if notebook_tags:
        analyze_notebook_content(notebook_tags)

        if args.verbose:
            print("\n📋 Tagged notebooks:")
            for path, meta in sorted(notebook_tags.items()):
                frontmatter_indicator = (
                    " 🏷️" if meta.get("has_explicit_tags") else " 🤖"
                )
                print(f"  📓 {path}{frontmatter_indicator}")
                print(f"     📂 {meta['folder']}")
                print(f"     🏷️  {', '.join(meta['tags'])}")
                if meta.get("description"):
                    print(f"     📝 {meta['description'][:50]}...")
                if meta["imports"]:
                    print(f"     📦 Imports: {', '.join(meta['imports'][:3])}")
                print()

        # Generate gallery pages
        print("\n📝 Generating gallery pages...")
        generate_gallery_pages(notebook_tags, ROOT_DIR)

        # Export metadata for MyST plugin
        print("📄 Exporting metadata for MyST plugin...")
        export_metadata_for_plugin(notebook_tags, ROOT_DIR)

        # Generate TOC entries - CALLED ONLY ONCE HERE
        generate_toc_entries(notebook_tags)

        # Show tagging examples if few notebooks found
        if len(notebook_tags) < 3:
            print_tag_examples()

        print("\n✅ Gallery generation complete!")
        print("✅ Generated gallery files:")
        print(f"  - {ROOT_DIR}/gallery.md (main gallery)")
        print(f"  - {ROOT_DIR}/gallery-sentinel.md")
        print(f"  - {ROOT_DIR}/gallery-topics.md")
        print(f"  - {ROOT_DIR}/gallery-tools.md")
        print(f"  - {ROOT_DIR}/gallery-tutorials.md")

        print("\n💡 All notebooks use YAML frontmatter tags")
    else:
        print("❌ No notebooks found with tags.")
        print(
            "💡 Add frontmatter tags to your notebooks or check your notebook directory"
        )
        print_tag_examples()
