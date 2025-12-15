/**
 * MyST Plugin for JupyterHub launch button
 */

const plugin = {
  name: "jupyterhub-button",
  author: "EOPF Sample Service",
  license: "Apache-2.0",

  directives: [
    {
      name: "jupyterhub-button",
      alias: ["launch-button"],
      doc: "Create a JupyterHub launch button",
      arg: { type: String, required: false },
      options: {
        notebook: { type: String },
        style: { type: String, default: "large" },
        color: { type: String, default: "#00c6fd" },
        image: { type: String, default: "default-notebooks-image" },
        profile: { type: String, default: "choose-your-environment" },
      },
      run(data, vfile) {
        // Get notebook path from option or current file
        let notebookPath = data.options?.notebook || "";

        if (!notebookPath && vfile && vfile.path) {
          const fullPath = vfile.path;

          // Find the last occurrence of 'notebooks/' and take everything after it
          const lastNotebooksIndex = fullPath.lastIndexOf("notebooks/");
          if (lastNotebooksIndex !== -1) {
            notebookPath = fullPath.substring(
              lastNotebooksIndex + "notebooks/".length,
            );
          } else {
            // Fallback: just get the filename and immediate parent directory
            const pathParts = fullPath.split("/");
            if (pathParts.length >= 2) {
              notebookPath = pathParts.slice(-2).join("/");
            } else {
              notebookPath = pathParts[pathParts.length - 1];
            }
          }
        }

        if (!notebookPath) {
          return [
            {
              type: "paragraph",
              children: [
                {
                  type: "text",
                  value: "Error: Could not determine notebook path",
                },
              ],
            },
          ];
        }

        // Create JupyterHub URL
        const gitpull_next =
          "/hub/user-redirect/git-pull?repo=https://github.com/EOPF-Sample-Service/eopf-sample-notebooks&branch=main&urlpath=lab/tree/eopf-sample-notebooks/notebooks/" +
          notebookPath;
        const encoded = encodeURIComponent(gitpull_next);
        const spawn_next = "/hub/spawn?next=" + encoded;
        var jupyterHubUrl = "";
        // All the notebooks including GDAL in their name will use a different image containing the GDAL EOPF ZARR DRIVER
        if (notebookPath.includes("GDAL")) {
          jupyterHubUrl =
            "https://jupyterhub.user.eopf.eodc.eu/hub/login?next=" +
            encodeURIComponent(spawn_next) +
            "%23fancy-forms-config=%7B%22profile%22%3A%22choose-your-environment%22%2C%22image%22%3A%22unlisted_choice%22%2C%22image%3Aunlisted_choice%22%3A%22yuvraj1989%2Feopf-zarr-driver%3Alatest%22%2C%20%22autoStart%22%3A%22true%22%7D";
        } else {
          jupyterHubUrl =
            "https://jupyterhub.user.eopf.eodc.eu/hub/login?next=" +
            encodeURIComponent(spawn_next) +
            "%23fancy-forms-config%3D%7B%22default_url%22%3A%22lab%22%2C%22default_url%3Aunlisted_choice%22%3A%22%22%2C%22image%22%3A%22base%22%2C%22image%3Aunlisted_choice%22%3A%22%22%2C%20%22autoStart%22%3A%22true%22%7D";
        }

        // Get style options
        const isLarge = data.options?.style === "large";

        // Create a centered container using classes
        return [
          {
            type: "div",
            data: {
              hName: "div",
              hProperties: {
                className: [
                  `jupyterhub-button-container`,
                  isLarge ? "large" : "small",
                ],
              },
            },
            children: [
              {
                type: "paragraph",
                data: {
                  hName: "p",
                  hProperties: {
                    className: ["jupyterhub-button-wrapper"],
                  },
                },
                children: [
                  {
                    type: "link",
                    url: jupyterHubUrl,
                    data: {
                      hName: "a",
                      hProperties: {
                        target: "_blank",
                        className: ["jupyterhub-launch-button"],
                      },
                    },
                    children: [
                      { type: "text", value: "🚀 Launch in JupyterHub" },
                    ],
                  },
                ],
              },
              {
                type: "paragraph",
                data: {
                  hName: "p",
                  hProperties: {
                    className: ["jupyterhub-button-description"],
                  },
                },
                children: [
                  {
                    type: "emphasis",
                    children: [
                      {
                        type: "text",
                        value:
                          "Run this notebook interactively with all dependencies pre-installed",
                      },
                    ],
                  },
                ],
              },
            ],
          },
        ];
      },
    },
  ],
};

export default plugin;
