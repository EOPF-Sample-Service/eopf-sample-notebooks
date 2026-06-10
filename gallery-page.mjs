/**
 * MyST Gallery Plugin
 * Creates enhanced gallery pages with styled tags and categorized notebooks
 */

import { readFileSync, existsSync } from "fs";
import { join } from "path";

const plugin = {
  name: "gallery-page",
  author: "EOPF Sample Service",
  license: "Apache-2.0",

  directives: [
    {
      name: "gallery-grid",
      options: {
        category: { type: String },
        columns: { type: String, default: "1 1 2 3" },
      },
      body: { type: String, required: false },
      run(data, vfile, ctx) {
        try {
          const { category = "all", columns = "1 1 2 3" } = data.options || {};

          // Load notebook metadata
          const notebookData = loadNotebookMetadata();

          if (!notebookData || Object.keys(notebookData).length === 0) {
            console.warn("No notebook metadata found");
            return [
              {
                type: "paragraph",
                children: [{ type: "text", value: "No notebooks found." }],
              },
            ];
          }

          // Filter notebooks by category if specified
          let notebooks = Object.entries(notebookData);

          if (category !== "all") {
            notebooks = notebooks.filter(([path, meta]) => {
              // Safe checking for tags
              if (!meta || !meta.tags) return false;
              if (!Array.isArray(meta.tags)) return false;
              return meta.tags.includes(category);
            });
          }

          if (notebooks.length === 0) {
            return [
              {
                type: "paragraph",
                children: [
                  {
                    type: "text",
                    value: `No notebooks found for category: ${category}`,
                  },
                ],
              },
            ];
          }

          // Generate gallery cards
          const cards = notebooks.map(([path, meta]) => {
            const title = meta && meta.title ? meta.title : formatTitle(path);
            const description =
              meta && meta.description ? meta.description : "";
            const tags = meta && meta.tags ? meta.tags : [];
            const hasExplicitTags =
              meta && meta.has_explicit_tags ? meta.has_explicit_tags : false;

            // Create the notebook URL (add .ipynb extension and notebooks/ prefix)
            const notebookUrl = `${path}.ipynb`;

            const children = [];

            // Add description if available
            if (description) {
              children.push({
                type: "paragraph",
                children: [{ type: "text", value: description }],
              });
            }

            // Add tags if available
            if (tags.length > 0) {
              const tagHTML = renderTags(tags, hasExplicitTags);
              if (tagHTML) {
                children.push({
                  type: "html",
                  value: tagHTML,
                });
              }
            }

            return {
              type: "card",
              data: {
                hName: "div",
                hProperties: { className: ["gallery-card"] },
              },
              children: [
                {
                  type: "cardTitle",
                  children: [
                    {
                      type: "link",
                      url: notebookUrl,
                      children: [{ type: "text", value: title }],
                    },
                  ],
                },
                ...children,
              ],
            };
          });

          return [
            {
              type: "grid",
              data: {
                hName: "div",
                hProperties: {
                  className: ["gallery-grid"],
                  "data-columns": columns,
                },
              },
              children: cards,
            },
          ];
        } catch (error) {
          console.error("Error in gallery-grid directive:", error);
          return [
            {
              type: "paragraph",
              children: [
                {
                  type: "text",
                  value: `Error loading gallery: ${error.message}`,
                },
              ],
            },
          ];
        }
      },
    },

    {
      name: "gallery-categories",
      options: {},
      run(data, vfile, ctx) {
        try {
          // Generate category overview cards
          const categories = [
            {
              title: "🛰️ Sentinel Data",
              link: "gallery-sentinel",
              description:
                "Notebooks for Sentinel-1, Sentinel-2, and Sentinel-3 missions",
            },
            {
              title: "🌍 Application Topics",
              link: "gallery-topics",
              description:
                "Notebooks by application domain: land, marine, climate, emergency",
            },
            {
              title: "🔧 Tools & Libraries",
              link: "gallery-tools",
              description:
                "Notebooks demonstrating XArray, GDAL, XCube, Zarr, and more",
            },
            {
              title: "🔧 Tutorials",
              link: "gallery-tutorials",
              description:
                "Notebooks demonstrating the main workflows for accessing and working with the data.",
            },
          ];

          const cards = categories.map((cat) => ({
            type: "card",
            data: {
              hName: "div",
              hProperties: { className: ["category-card"] },
            },
            children: [
              {
                type: "cardTitle",
                children: [
                  {
                    type: "link",
                    url: cat.link,
                    children: [{ type: "text", value: cat.title }],
                  },
                ],
              },
              {
                type: "paragraph",
                children: [{ type: "text", value: cat.description }],
              },
            ],
          }));

          return [
            {
              type: "grid",
              data: {
                hName: "div",
                hProperties: {
                  className: ["gallery-grid", "category-grid"],
                  "data-columns": "1 1 2 3",
                },
              },
              children: cards,
            },
          ];
        } catch (error) {
          console.error("Error in gallery-categories directive:", error);
          return [
            {
              type: "paragraph",
              children: [
                {
                  type: "text",
                  value: `Error loading categories: ${error.message}`,
                },
              ],
            },
          ];
        }
      },
    },
  ],

  transforms: [
    {
      stage: "document",
      plugin: enhanceGalleryPages,
    },
  ],
};

function loadNotebookMetadata() {
  try {
    const metadataPath = join(
      process.cwd(),
      "notebooks",
      ".gallery-metadata.json",
    );
    if (existsSync(metadataPath)) {
      const content = readFileSync(metadataPath, "utf8");
      return JSON.parse(content);
    }
    console.warn(`Metadata file not found: ${metadataPath}`);
    return {};
  } catch (error) {
    console.error("Error loading gallery metadata:", error);
    return {};
  }
}

function renderTags(tags, hasExplicitTags = false) {
  try {
    if (!tags || !Array.isArray(tags) || tags.length === 0) {
      return "";
    }

    const visibleTags = tags.slice(0, 3);
    const remainingCount = Math.max(0, tags.length - 3);

    const tagElements = visibleTags
      .map((tag) => {
        if (typeof tag !== "string") return "";
        const cssClass = tag.replace(/[^a-zA-Z0-9-]/g, "-").toLowerCase();
        const icon = getTagIcon(tag);
        return `<span class="gallery-tag tag-${cssClass}">${icon} ${tag}</span>`;
      })
      .filter(Boolean)
      .join(" ");

    const moreElement =
      remainingCount > 0
        ? ` <span class="gallery-tag-more">+${remainingCount} more</span>`
        : "";

    return `<div class="gallery-tags">${tagElements}${moreElement}</div>`;
  } catch (error) {
    console.error("Error rendering tags:", error);
    return '<div class="gallery-tags">Tags unavailable</div>';
  }
}

function getTagIcon(tag) {
  if (typeof tag !== "string") return "🏷️";

  const icons = {
    "sentinel-1": "🛰️",
    "sentinel-2": "🛰️",
    "sentinel-3": "🛰️",
    land: "🌱",
    emergency: "🚨",
    "climate-change": "🌡️",
    marine: "🌊",
    security: "🔒",
    xarray: "📊",
    "xarray-eopf": "🔌",
    gdal: "🗺️",
    stac: "📋",
    zarr: "📦",
    dask: "🧮",
    basic: "👶",
  };
  return icons[tag] || "🏷️";
}

function formatTitle(path) {
  try {
    if (typeof path !== "string") return "Unknown";
    return path
      .split("/")
      .pop()
      .replace(/[-_]/g, " ")
      .replace(/\b\w/g, (l) => l.toUpperCase());
  } catch (error) {
    return "Unknown";
  }
}

function enhanceGalleryPages(mdast, vfile) {
  try {
    if (!mdast || !mdast.children) return mdast;

    // Since CSS is loaded via myst.yml style option, we don't need to inject it
    // Just return the mdast as-is
    return mdast;
  } catch (error) {
    console.error("Error in enhanceGalleryPages:", error);
    return mdast;
  }
}

export default plugin;
