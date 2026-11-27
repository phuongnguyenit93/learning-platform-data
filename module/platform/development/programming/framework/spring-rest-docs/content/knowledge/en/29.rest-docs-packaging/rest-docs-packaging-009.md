# Verifying the JAR Contains All HTML, Markdown, and Assets

## Learning Objectives

After this lesson, you will be able to:

- Identify which HTML, Markdown, and static assets must be present in the documentation artifact.
- Understand how classpath resource locations correspond to entries inside an executable Spring Boot JAR.
- Use JDK tools to list, search, and extract JAR contents.
- Verify file presence, reasonable file sizes, non-empty contents, and preserved directory structures.
- Distinguish Markdown sources from HTML served to browsers and understand how consumers access each type.
- Detect missing assets, broken relative paths, filtered files, or omissions in copy tasks.
- Automate artifact completeness checks in Gradle, Maven, and CI.

## 1. Why Inspect JAR Contents?

A passing build does not guarantee the executable JAR contains complete documentation. A JAR can start normally while the docs page lacks CSS files, images, operation pages, or Markdown sources.

Common causes:

- Asciidoctor generates `index.html`, but the copy task fails to include subpages in the resource directory.
- The copy task grabs only HTML files in the root directory, skipping subdirectories.
- Include/exclude patterns in Gradle or Maven accidentally omit CSS, JS, images, or Markdown.
- Documentation is generated after resource processing or packaging has already run.
- Resource filtering alters the contents of static files.
- Relative links in HTML point to assets not present in the JAR.
- Markdown files reside outside the output directory read by the packaging task.

Therefore, inspect the artifact after packaging. Checking the build directory before packaging only confirms intermediate outputs; it does not prove the final JAR has every file.

## 2. Defining What Must Be Packaged

Before checking, list the expected files. A documentation bundle may include:

| Group | Example | Purpose |
| --- | --- | --- |
| Main HTML page | `index.html` | Landing page and navigation |
| Operation pages | `orders.html`, `authentication.html` | API content per resource |
| Markdown source | `index.md`, `orders.md` | Readable source, downloadable, or for downstream processing |
| CSS | `css/site.css`, `css/theme.css` | Styling |
| JavaScript | `js/navigation.js`, `js/search.js` | Navigation, search, or interactivity |
| Images | `images/logo.svg`, `images/flow.png` | Logos, diagrams, and illustrations |
| Fonts | `fonts/*.woff2` | Custom fonts |
| Metadata | `manifest.json`, `version.json` | Version, revision, or release info |
| Downloadable docs | `openapi.yaml`, `api-guide.pdf` | Supplemental artifacts if published by the project |

Not every project needs all groups above. The manifest must reflect the project's actual intended output rather than checking for files never designed for release.

### 2.1. Example Expected Structure

Suppose the application places documentation under `static/docs`:

```text
BOOT-INF/classes/static/docs/
├── index.html
├── index.md
├── manifest.json
├── orders/
│   ├── index.html
│   └── orders.md
├── css/
│   └── site.css
├── js/
│   └── navigation.js
└── images/
    ├── logo.svg
    └── request-flow.png
```

The JAR does not have to mirror the source directory layout identically. For instance, outputs may originate in `build/docs/asciidoc` and then be copied into classpath resources. What must be verified is that the final entries in the JAR carry the proper prefix and preserve directory relationships.

### 2.2. HTML and Markdown Serve Different Roles

HTML is typically the format browsers render directly. Markdown is source text that can be:

- Downloaded or read as plain text by consumers.
- Used as input for another renderer.
- Stored for review, diffing, or reuse.
- Served with an appropriate `Content-Type`, typically `text/markdown` if the resource handler and MIME config support it.

Browsers do not automatically turn a `.md` file into a styled website with navigation like HTML. If readers need web pages, package the rendered HTML. If Markdown sources are required, package `.md` files as well and document clearly how to access them.

## 3. From Classpath Resources to JAR Entries

With Spring Boot, files placed under `src/main/resources/static/docs` are typically copied onto the classpath at paths:

```text
static/docs/index.html
static/docs/index.md
static/docs/css/site.css
```

Inside an executable JAR, these entries typically appear under:

```text
BOOT-INF/classes/static/docs/index.html
BOOT-INF/classes/static/docs/index.md
BOOT-INF/classes/static/docs/css/site.css
```

Spring Boot's loader uses the contents under `BOOT-INF/classes` as the application classpath. Therefore, entry paths inside the JAR must match the resource paths the application expects to serve.

Common default mapping examples:

| JAR Entry | Runtime Application URL |
| --- | --- |
| `BOOT-INF/classes/static/docs/index.html` | `/docs/` or `/docs/index.html` |
| `BOOT-INF/classes/static/docs/index.md` | `/docs/index.md` |
| `BOOT-INF/classes/static/docs/css/site.css` | `/docs/css/site.css` |
| `BOOT-INF/classes/static/docs/images/logo.svg` | `/docs/images/logo.svg` |

Actual URLs may vary depending on context path, resource handlers, security, and reverse proxies. An entry existing in the JAR does not prove the URL works; a runtime smoke test is still required.

## 4. Listing JAR Contents with jar tf

The JDK provides the `jar` command to view the entry list:

```bash
jar tf build/libs/orders-service.jar
```

With Maven:

```bash
jar tf target/orders-service.jar
```

Find key entries:

```bash
jar tf build/libs/orders-service.jar | grep 'BOOT-INF/classes/static/docs/'
```

On Windows PowerShell, you can filter the output:

```powershell
jar tf build/libs/orders-service.jar | Select-String 'BOOT-INF/classes/static/docs/'
```

Check at minimum:

- The main HTML page is present.
- Operation pages linked from the index are present.
- Markdown sources are present if required by the release contract.
- All referenced CSS, JavaScript, images, and fonts are present.
- Metadata/version files are present if published by the pipeline.

Do not merely count entries. A JAR with hundreds of files can still be missing the exact file the landing page needs.

## 5. Checking Each Required File

You can use a list of expected paths to verify:

```text
BOOT-INF/classes/static/docs/index.html
BOOT-INF/classes/static/docs/index.md
BOOT-INF/classes/static/docs/orders/index.html
BOOT-INF/classes/static/docs/orders/orders.md
BOOT-INF/classes/static/docs/css/site.css
BOOT-INF/classes/static/docs/js/navigation.js
BOOT-INF/classes/static/docs/images/logo.svg
```

This list is illustrative. Replace it with your project's actual manifest. Optional files may be checked conditionally, while core files like `index.html` should fail the build if missing.

### 5.1. Checking with PowerShell

You can retrieve the entry list and check required paths:

```powershell
$jarPath = "build/libs/orders-service.jar"
$entries = jar tf $jarPath

$required = @(
    "BOOT-INF/classes/static/docs/index.html",
    "BOOT-INF/classes/static/docs/index.md",
    "BOOT-INF/classes/static/docs/css/site.css",
    "BOOT-INF/classes/static/docs/images/logo.svg"
)

$missing = $required | Where-Object { $_ -notin $entries }
if ($missing.Count -gt 0) {
    $missing | ForEach-Object { Write-Error "Missing JAR entry: $_" }
    exit 1
}

Write-Host "Documentation entries are present."
```

This script demonstrates existence checking. For real projects, store the manifest in the build script or CI configuration and adjust required files according to the published documentation.

### 5.2. Pattern-Based Checks

You can verify at least one file in each category:

- At least one `.html` file.
- `.md` files present if Markdown sources are published.
- CSS present if HTML references stylesheets.
- JS present if pages use scripts.
- Image/font files present if HTML or CSS references them.

Pattern-based checks are useful when the page count grows with the number of operations. However, patterns do not replace a manifest of mandatory core files.

## 6. Extracting the JAR to Verify Contents

The entry list only confirms filenames. To verify files actually have content, extract the JAR into a temporary directory:

```bash
mkdir -p build/jar-inspection
cd build/jar-inspection
jar xf ../libs/orders-service.jar BOOT-INF/classes/static/docs
```

Then inspect:

```bash
find BOOT-INF/classes/static/docs -type f
```

With PowerShell:

```powershell
$inspectionDir = "build/jar-inspection"
New-Item -ItemType Directory -Force -Path $inspectionDir | Out-Null
Push-Location $inspectionDir
jar xf ../libs/orders-service.jar BOOT-INF/classes/static/docs
Get-ChildItem -Recurse BOOT-INF/classes/static/docs
Pop-Location
```

Extraction helps verify:

- File sizes are greater than 0.
- HTML contains the expected title and body content.
- Markdown contains headings and source text.
- CSS/JS are not empty or altered by resource filtering.
- Images/SVGs/fonts are readable.
- Relative asset paths have corresponding target files.

Do not edit extracted files to patch the artifact. If you find a defect, go back to the AsciiDoc sources, assets, or build tasks and rebuild the JAR.

## 7. Checking Asset References in HTML

An HTML page can return 200 while CSS or images are missing. Example:

```html
<link rel="stylesheet" href="css/site.css">
<script src="js/navigation.js"></script>
<img src="images/logo.svg" alt="Orders API">
```

Relative paths are resolved against the HTML page URL. For a page at `/docs/index.html`, the browser requests:

```text
/docs/css/site.css
/docs/js/navigation.js
/docs/images/logo.svg
```

If a subpage at `/docs/orders/index.html` uses `../css/site.css`, the target URL differs. Inspect each subpage and the assets it references.

### 7.1. Common Path Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| HTML 200, CSS 404 | CSS was not copied or `href` is wrong | Check JAR entry and asset URL |
| Main page works, subpage loses logo | Relative path resolved from subpage folder | Fix relative URL or configure base path |
| CSS loads but fonts return 404 | CSS references fonts at an unpackaged path | Check `url(...)` in CSS and font entries |
| JS returns 404 | Wrong script path or include/exclude dropped the file | Check `script src` and resource task |
| SVG fails to render | Missing file, MIME type, or corrupted SVG | Check entry, content, and response `Content-Type` |

Do not replace every URL with a `/docs/`-rooted path if the website may be deployed under a different context path. Use relative paths or a consistently configured base path.

## 8. Checking Markdown Sources

If publishing both HTML and Markdown is required, verify `.md` files are copied into the JAR:

```text
BOOT-INF/classes/static/docs/index.md
BOOT-INF/classes/static/docs/orders/orders.md
```

Check Markdown files for:

- Non-empty content.
- Main heading present.
- Balanced opening/closing code fences.
- Links to images or downloadable files point to assets present in the artifact.
- No secrets, tokens, cookies, or production data.
- Version/source revision included if required by release policy.

If Markdown uses a relative image path:

```markdown
![Request flow](images/request-flow.png)
```

then `images/request-flow.png` must sit at the right relative location to the Markdown file, or the link must be adjusted to match the release layout.

### 8.1. Accessing Markdown via URL

If resources are placed under `static/docs`, you can request:

```text
GET /docs/index.md
```

The server may return Markdown as `text/plain` or `text/markdown` depending on MIME mappings. Do not assume browsers will render Markdown. If formatted rendering is needed, provide corresponding HTML or a dedicated Markdown viewer.

## 9. Checking File Sizes and Empty Files

An entry existing with a size of 0 bytes usually indicates a failed copy or rendering task. Check minimum sizes for core files:

| File Type | Check |
| --- | --- |
| `index.html` | Greater than 0 and contains page content |
| Markdown | Greater than 0 and contains headings |
| CSS/JS | Greater than 0 if used by the page |
| SVG/images | Reasonable size, readable file |
| `manifest`/`version` | Valid JSON containing required metadata |

Do not set arbitrarily high byte thresholds. A small CSS file can be completely valid; an unusually large image may need optimization. Focus on non-empty files, valid format, and presence whenever referenced.

## 10. Verifying Gradle Includes All Resources in the JAR

If using a generated resource directory, ensure the copy task grabs the entire Asciidoctor output tree:

```groovy
tasks.register('copyApiDocs', Copy) {
    dependsOn tasks.named('asciidoctor')
    from(layout.buildDirectory.dir('docs/asciidoc'))
    into(layout.buildDirectory.dir('generated-resources/api-docs/static/docs'))
}

sourceSets {
    main {
        resources {
            srcDir(layout.buildDirectory.dir('generated-resources/api-docs'))
        }
    }
}

tasks.named('processResources') {
    dependsOn tasks.named('copyApiDocs')
}
```

Do not restrict `include` to only `index.html` if pages need CSS, JS, images, or Markdown. If temporary files must be omitted, use explicit `exclude` rules and verify the manifest after packaging.

### 10.1. Verifying Task Outputs

Gradle may run tasks incrementally or from cache. When input files change, declare appropriate inputs/outputs so the copy and Asciidoctor tasks re-run when needed. When investigating an artifact missing files:

```bash
./gradlew clean test asciidoctor copyApiDocs bootJar
```

Then inspect the newly built JAR with `jar tf`. A clean build eliminates stale files left over from prior runs.

## 11. Verifying Maven Includes All Resources in the JAR

With Maven, HTML/Markdown outputs must be copied into `target/classes` before `package`:

```xml
<configuration>
  <outputDirectory>target/classes/static/docs</outputDirectory>
  <resources>
    <resource>
      <directory>target/generated-docs</directory>
      <filtering>false</filtering>
    </resource>
  </resources>
</configuration>
```

The `generated-docs` directory should contain the full documentation tree, not just `index.html`. If using `includes`/`excludes`, review them against the expected manifest.

Disable filtering for HTML, Markdown, CSS, JS, SVG, and binary assets. Unwanted filtering can substitute placeholders or special strings in sources, leaving contents corrupted.

After packaging:

```bash
mvn clean verify
jar tf target/orders-service.jar
```

Verify entries under `BOOT-INF/classes/static/docs`. Do not stop at seeing files in `target/classes`; the final JAR is the artifact that will be deployed.

## 12. Automating Completeness Checks in CI

A CI step can verify the manifest:

1. Clean build and run documentation tests.
2. Render Asciidoctor.
3. Package the executable JAR.
4. List entries in the JAR.
5. Compare against the list of required files.
6. Extract documentation into a temporary directory.
7. Check for empty files, HTML/Markdown missing content, and missing assets.
8. Run a runtime smoke test against documentation URLs.

Example shell entry check:

```bash
set -eu

JAR_FILE="build/libs/orders-service.jar"
ENTRIES_FILE="build/jar-entries.txt"

jar tf "$JAR_FILE" > "$ENTRIES_FILE"

grep -Fxq "BOOT-INF/classes/static/docs/index.html" "$ENTRIES_FILE"
grep -Fxq "BOOT-INF/classes/static/docs/index.md" "$ENTRIES_FILE"
grep -Fxq "BOOT-INF/classes/static/docs/css/site.css" "$ENTRIES_FILE"
```

If a file is missing, `grep` returns a non-zero exit code and `set -e` fails the CI step. Add required entries according to your project's manifest.

### 12.1. Runtime Verification

After starting the JAR in a smoke-test environment, check the URLs:

```bash
curl --fail --silent --show-error http://localhost:8080/docs/
curl --fail --silent --show-error http://localhost:8080/docs/index.md
curl --fail --silent --show-error http://localhost:8080/docs/css/site.css
curl --fail --silent --show-error http://localhost:8080/docs/images/logo.svg
```

These URLs are examples. Replace host, context path, and filenames according to your runtime configuration. Check response bodies or `Content-Type` if needed; checking status codes alone can miss empty bodies or wrong content types.

## 13. Protecting Artifact Integrity

After confirming file presence, you can verify integrity:

- Compute the SHA-256 checksum of the JAR before publishing.
- Compare the checksum after downloading the artifact from the repository.
- Store the entry manifest and build metadata alongside the artifact.
- Verify HTML/Markdown files do not contain secrets.
- Ensure the artifact was built from an approved source revision.

Example:

```bash
sha256sum build/libs/orders-service.jar
```

A checksum confirms the artifact's bytes did not change between two checks. It does not prove the contents are technically accurate or free of secrets; combine checksums with content checks and review.

## 14. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| JAR has HTML but lacks Markdown | Markdown outside copy source or excluded | Include `.md` files in output/manifest and copy tree |
| JAR has only the index page | Copy task selected only one file | Recursively copy the entire docs output |
| CSS/images missing from JAR | Include pattern missing asset extensions or folders | Review `include`/`exclude` rules and inspect entries |
| Entry exists but is 0 bytes | Render/copy task created an empty file | Check task output before packaging |
| JAR has assets yet browser gets 404 | Relative/base path mismatch | Check links in HTML/CSS and runtime mapping |
| Markdown downloads but does not render as a page | Browser receives raw Markdown source | Provide HTML or a dedicated viewer |
| JAR has old files removed from source | Output directory was not cleaned | Clean build or wipe destination before copying |
| HTML/CSS contains strange placeholders | Resource filtering altered content | Disable filtering for static docs |
| CI passes despite missing operation pages | Checked only index or only build success | Compare required manifest and verify target links |

## 15. JAR Verification Checklist

- [ ] A manifest of expected HTML, Markdown, and asset files exists.
- [ ] JAR contains `index.html` under the proper classpath path.
- [ ] Linked operation pages are all present in the JAR.
- [ ] Markdown sources are present in the JAR if required by the release.
- [ ] CSS, JavaScript, images, and fonts are completely packaged.
- [ ] Relative paths between HTML and assets are preserved.
- [ ] No required files are empty or truncated.
- [ ] No resource filtering alters content.
- [ ] Key files have been extracted and inspected.
- [ ] Runtime URLs for HTML, Markdown, and assets return expected contents.
- [ ] CI compares JAR entries against the manifest.
- [ ] Checksum and source revision are stored per release policy.

## 16. Hands-On Exercise

An Orders service packages documentation under `static/docs`. The documentation set requires:

- `index.html` and `index.md`.
- `orders/index.html` and `orders/orders.md`.
- `css/site.css`.
- `js/navigation.js`.
- `images/logo.svg`.

Perform the following:

1. Write a manifest listing the required classpath entries.
2. Build the executable JAR from a clean state.
3. Use `jar tf` to list and verify every entry in the manifest.
4. Extract `static/docs` to a temporary directory and verify files are non-empty.
5. Verify HTML references CSS, JS, and logo using proper relative paths.
6. Verify Markdown has headings, balanced code fences, and valid image links.
7. Run the JAR and request `/docs/`, `/docs/index.md`, `/docs/css/site.css`, and `/docs/images/logo.svg`.
8. Intentionally omit an asset in the copy task to confirm CI catches the failure.
9. Restore the copy rule, rebuild, and record the JAR's checksum.

**Self-check question:** If `jar tf` shows `index.html`, can you conclude the entire documentation set was completely packaged? No. You must verify subpages, Markdown if required, CSS/JS/images/fonts referenced by HTML, extracted file contents, and runtime URLs. A single entry does not represent the entire website.

## Summary

Verifying the JAR requires checking entry names, file contents, and runtime accessibility. Create a manifest of HTML, Markdown, and assets to release; use `jar tf` to compare entries, extract to check for non-empty files, and verify relative paths between pages and assets. Markdown is a source format for downloading or downstream processing, while HTML is the format browsers typically render directly. Gradle/Maven must copy the entire output tree and avoid filtering that alters contents. Finally, CI should check the manifest, key file contents, runtime URLs, and checksums to catch missing pages or assets early before release.
