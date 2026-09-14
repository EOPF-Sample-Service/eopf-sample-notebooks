#!/usr/bin/env python3
"""
Inject JupyterHub button directive into notebooks
"""

import argparse
from pathlib import Path

import nbformat


def create_button_directive(notebook_path=None, style="large"):
    """Create the MyST directive for the button"""
    directive = f"""```{{jupyterhub-button}}
:style: {style}
:color: #00c6fd
```"""

    return directive


def add_directive_to_notebook(notebook_file, style="large"):
    """Add JupyterHub directive to a single notebook"""
    try:
        # Read the notebook
        with open(notebook_file, "r", encoding="utf-8") as f:
            nb = nbformat.read(f, as_version=4)

        # Check if directive already exists
        directive_markers = [
            "jupyterhub-button",
            "launch-button",
            "{jupyterhub-button}",
        ]
        for cell in nb.cells:
            if cell.cell_type == "markdown" and any(
                marker in cell.source for marker in directive_markers
            ):
                print(f"  ⏭️  Button directive already exists in {notebook_file.name}")
                return False

        # Find where to insert the directive
        insert_index = 0

        # Look for the first markdown cell with a title (after frontmatter)
        for i, cell in enumerate(nb.cells):
            if cell.cell_type == "markdown":
                # Skip frontmatter
                if cell.source.strip().startswith("---") and i == 0:
                    continue

                # Look for a heading
                if cell.source.strip().startswith("#"):
                    insert_index = i + 1
                    break

        # Create directive
        directive_content = create_button_directive(style=style)
        directive_cell = nbformat.v4.new_markdown_cell(directive_content)

        # Insert the directive
        nb.cells.insert(insert_index, directive_cell)

        # Save the notebook
        with open(notebook_file, "w", encoding="utf-8") as f:
            nbformat.write(nb, f)

        print(f"  ✅ Added button directive to {notebook_file.name}")
        return True

    except Exception as e:
        print(f"  ❌ Error processing {notebook_file}: {e}")
        return False


def find_notebooks(directory):
    """Find all Jupyter notebooks in directory"""
    path = Path(directory)
    notebooks = list(path.rglob("*.ipynb"))
    # Filter out checkpoint files
    notebooks = [nb for nb in notebooks if ".ipynb_checkpoints" not in str(nb)]
    return notebooks


def remove_existing_directives(notebook_file):
    """Remove existing button directives from a notebook"""
    try:
        with open(notebook_file, "r", encoding="utf-8") as f:
            nb = nbformat.read(f, as_version=4)

        # Remove cells containing button directives
        directive_markers = [
            "jupyterhub-button",
            "launch-button",
            "Launch in JupyterHub",
        ]
        cells_to_remove = []

        for i, cell in enumerate(nb.cells):
            if cell.cell_type == "markdown" and any(
                marker in cell.source for marker in directive_markers
            ):
                cells_to_remove.append(i)

        # Remove cells in reverse order to maintain indices
        for i in reversed(cells_to_remove):
            nb.cells.pop(i)

        if cells_to_remove:
            with open(notebook_file, "w", encoding="utf-8") as f:
                nbformat.write(nb, f)
            print(
                f"  🗑️  Removed {len(cells_to_remove)} existing directive(s) from {notebook_file.name}"
            )
            return True

        return False

    except Exception as e:
        print(f"  ❌ Error removing directives from {notebook_file}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Inject JupyterHub button directive into notebooks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python inject_directive.py                    # Add to all notebooks
  python inject_directive.py --style small      # Use small button style
  python inject_directive.py --remove           # Remove old directives first
  python inject_directive.py --notebook path/to/notebook.ipynb
        """,
    )
    parser.add_argument(
        "--dir", default="notebooks", help="Directory containing notebooks"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument("--notebook", help="Process only a specific notebook")
    parser.add_argument(
        "--style",
        choices=["large", "small"],
        default="large",
        help="Button style: large (default) or small",
    )
    parser.add_argument(
        "--remove",
        action="store_true",
        help="Remove existing directives before adding new ones",
    )

    args = parser.parse_args()

    print("💫 JupyterHub Button Directive Injector")
    print(f"Style: {args.style}")
    print()

    if args.notebook:
        # Process single notebook
        notebook_file = Path(args.notebook)
        if notebook_file.exists():
            print(f"Processing {notebook_file}...")
            if not args.dry_run:
                if args.remove:
                    remove_existing_directives(notebook_file)
                add_directive_to_notebook(notebook_file, args.style)
            else:
                print(f"  Would add {args.style} directive to {notebook_file}")
        else:
            print(f"Error: {notebook_file} not found")
    else:
        # Process all notebooks
        notebooks = find_notebooks(args.dir)
        print(f"Found {len(notebooks)} notebooks in {args.dir}")

        added_count = 0
        for notebook in notebooks:
            print(f"\nProcessing {notebook.name}...")
            if args.dry_run:
                print(f"  Would check and potentially add {args.style} directive")
            else:
                if args.remove:
                    remove_existing_directives(notebook)
                if add_directive_to_notebook(notebook, args.style):
                    added_count += 1

        if not args.dry_run:
            print(f"\n✅ Added directives to {added_count} notebooks")
            print("\n📝 Next steps:")
            print("1. Make sure jupyterhub-button.mjs is in your root directory")
            print("2. Add it to myst.yml under project.plugins:")
            print("   plugins:")
            print("     - gallery-page.mjs")
            print("     - jupyterhub-button.mjs")
            print("3. Run: myst build")


if __name__ == "__main__":
    main()
