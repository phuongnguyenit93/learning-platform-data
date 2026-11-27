# Checking Paths and Encoding on Runners

Spring REST Docs documentation tests write snippets to the filesystem; the Asciidoctor/Markdown renderer reads those files to build documentation. A pipeline that works on a developer machine may fail on a CI runner because the runner can use a different operating system, working directory, case-sensitive filesystem, path separator, and locale/encoding. Issues typically show up as missing includes, wrong artifact paths, corrupted Vietnamese characters, or output differing across environments.

To keep the pipeline reliable, manage paths via the build tool and workspace, use a single configuration source for snippet output and the renderer, handle files consistently in UTF-8, and verify artifacts directly on the runner. This lesson focuses on path and encoding portability in CI without depending on a specific CI provider.

This lesson belongs to the **CI and Publishing** chapter of the `SPRING_REST_DOCS` module. The module creates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured, generates snippets for requests, responses, payloads, parameters, and headers, and then compiles Asciidoctor/Markdown and integrates the build and CI.

## 1. Learning Objectives

After this lesson, you can:

1. Identify path differences across Windows, Linux, and macOS runners.
2. Configure a consistent snippets directory between the test recorder and Asciidoctor.
3. Avoid relying on working directories or absolute paths on developer machines.
4. Handle case-sensitive filesystems and exact filenames.
5. Ensure Markdown, AsciiDoc, and snippets are read/written in UTF-8.
6. Verify newlines, locale, and encoding on runners.
7. Validate artifact paths before uploading or publishing.

## 2. Why Are Paths and Encoding Prone to Break in CI?

A project may be developed on Windows while CI runs on Linux. Common differences that cause failures:

- Windows uses backslashes in native paths; Linux/macOS use forward slashes.
- Linux filesystems typically distinguish `Orders-Get` from `orders-get`; local environments might not.
- A CI step's working directory may differ from the local execution directory.
- Absolute paths on a developer machine do not exist on the runner.
- Files saved using a machine's default encoding may be misread on the runner.
- Different locales/timezones can make output contain inconsistent characters or formatting.

### 2.1. Warning Signs

| Symptom | Possible cause |
| --- | --- |
| Asciidoctor reports include file does not exist | Wrong base directory, identifier, or separator |
| Works locally, fails on Linux CI | Case sensitivity difference |
| Snippets exist yet renderer misses them | Tests and renderer use two different output directories |
| Vietnamese text becomes garbled characters | File is not UTF-8 or reader uses a different encoding |
| Diff shows many unexplained changes | Inconsistent newlines, locale, or timezone |
| Artifact upload reports not found | Glob/path resolved from a different working directory |
| Tests write to an unexpected directory | Relative path resolved from an unexpected `user.dir` |

## 3. Using Relative Paths from the Build Directory

Avoid hard-coding absolute paths such as `C:\Users\developer\project` or `/home/runner/work`. Those paths work only on one specific machine or runner.

With Gradle, prefer the build directory API:

```groovy
def snippetsDir = layout.buildDirectory.dir("generated-snippets")

tasks.named("asciidoctor") {
    inputs.dir(snippetsDir)
}
```

With Maven, use the build directory property:

```xml
<snippets>${project.build.directory}/generated-snippets</snippets>
```

Both examples show how to construct paths from the build system. The test recorder and Asciidoctor must receive the exact same value. If tests write to `build/generated-snippets` while the renderer looks in `target/generated-snippets`, includes will break even though each path is valid on its own.

### 3.1. Single Configuration Source

Define the snippets directory in one shared property or build variable instead of repeating the string in multiple places. Conceptual example in Gradle:

```groovy
def restDocsSnippets = layout.buildDirectory.dir("generated-snippets")

tasks.named("test") {
    systemProperty(
        "org.springframework.restdocs.outputDir",
        restDocsSnippets.get().asFile.absolutePath
    )
}

tasks.named("asciidoctor") {
    inputs.dir(restDocsSnippets)
}
```

How you pass the output directory to the test recorder depends on your project's Spring REST Docs setup; check your current MockMvc/WebTestClient/REST Assured configuration. Do not assume this example system property automatically configures every test harness if the project does not read that property. The principle is having a single source of truth for both sides.

## 4. Separators and Path APIs

In AsciiDoc configuration files, include paths are normally written with `/`, even when builds run on Windows:

```asciidoc
include::{snippets}/orders-get/http-request.adoc[]
```

In Java code, use `Path`/`Paths` instead of concatenating separators manually:

```java
Path snippets = Paths.get(
    buildDirectory,
    "generated-snippets",
    "orders-get"
);

Path requestSnippet = snippets.resolve("http-request.adoc");
```

`Path.resolve(...)` picks the separator matching the current filesystem. When passing paths to plugins or tools outside the JVM, use build tool APIs to supply an absolute path resolved from the project/build directory.

### 4.1. Do Not Concatenate Paths with Strings

Avoid string concatenation using Windows separators like `generated-snippets\orders-get`. This ties code to one OS and easily produces invalid paths on Linux. Use `Path.resolve`, `File`, or the corresponding Gradle/Maven API.

### 4.2. Relative Paths Depend on the Working Directory

A relative path such as `build/generated-snippets` is resolved from the process working directory. A CI provider may run steps from the repository root or a specified subdirectory. Define the working directory explicitly in the job and use the project/build directory as the base.

Do not assume the shell sits in the same folder as the build script or AsciiDoc file. The renderer may resolve includes relative to the document's base directory or according to a plugin-provided attribute; check the behavior of the plugin in use.

## 5. Case-Sensitive Filesystems

Linux runners typically treat filenames as case-sensitive. Example:

```text
orders-get/http-request.adoc
Orders-Get/http-request.adoc
```

The two paths can point to two distinct files on Linux. If a test uses the identifier `orders-get` while AsciiDoc includes `Orders-Get`, local runs might still work on some filesystems, whereas Linux CI reports a missing file.

Rules:

- Use consistent identifiers, ideally lowercase kebab-case.
- Snippet names must match exact casing.
- Verify the actual generated filenames after tests.
- Never rely on a local filesystem to validate case sensitivity.

### 5.1. Checking Include Paths

For each include, check both the directory and the filename:

```asciidoc
include::{snippets}/orders-get/http-request.adoc[]
include::{snippets}/orders-get/http-response.adoc[]
include::{snippets}/orders-get/response-fields.adoc[]
```

If a descriptor does not generate `response-fields.adoc`, do not add an include based on guesswork. Inspect the actual generated files and test descriptors.

## 6. UTF-8 Encoding for Vietnamese Content

Markdown, AsciiDoc, and generated snippets may contain Vietnamese text in headings, descriptions, and example payloads. To prevent encoding errors:

- Save `.md`, `.adoc`, `.java`, and `.yml` sources in UTF-8.
- Configure editors/repositories not to convert to legacy encodings.
- When scripts read/write files, specify UTF-8 explicitly.
- Avoid relying on the OS or shell's default encoding.
- Verify the final HTML/PDF renders Vietnamese diacritics accurately.

Java example reading a UTF-8 file:

```java
String content = Files.readString(
    Path.of("src/docs/asciidoc/index.adoc"),
    StandardCharsets.UTF_8
);
```

PowerShell example reading/writing UTF-8 in a verification script:

```powershell
$content = Get-Content -Raw -Encoding UTF8 -LiteralPath $path
Set-Content -LiteralPath $output -Value $content -Encoding UTF8
```

PowerShell 5.1 and newer versions differ in default encoding and BOM handling. Specify encoding explicitly in scripts to avoid depending on the runner version.

### 6.1. Source Encoding and Output Encoding

Do not check only Markdown sources. Snippets can be generated from Java tests, templates, or fixtures; the renderer then produces HTML/PDF. Check the entire chain:

```text
Java test / fixture
       │
       ▼
Generated snippets
       │
       ▼
AsciiDoc / Markdown
       │
       ▼
HTML / PDF
```

If one step reads with the wrong encoding, corruption can appear at a later step even though the original source was proper UTF-8.

## 7. Newlines, Locale, and Timezone

Windows typically uses CRLF; Linux typically uses LF. Git can normalize newlines according to repository settings. Declare explicit rules via `.gitattributes`, for example:

```gitattributes
*.md   text eol=lf
*.adoc text eol=lf
*.yml  text eol=lf
*.java text eol=lf
```

Do not force binary files to text. PDFs, images, and binary artifacts must retain their exact bytes.

Locale and timezone can also affect timestamps or date/time formatting in snippets. If time values are fixtures, use fixed values. If tests need time, pin `Clock` or timezone per the contract. Avoid relying on the runner's default locale.

## 8. Verifying Output on Runners

After documentation tests run, check:

1. The snippets directory exists at the expected path.
2. Each identifier has a corresponding folder.
3. Included files exist with exact casing.
4. Files are non-empty.
5. Text files are readable as UTF-8.
6. Asciidoctor runs from the configured working directory/path.
7. HTML/PDF output resides in the right artifact directory.
8. The upload step points to the actual artifact path.

You can write a validation task to fail early when an include file is missing. Error messages should print the path searched and the working/base directory used.

### 8.1. Do Not Check Only Directory Existence

The existence of the snippets directory does not prove every operation was generated. Check each identifier and required include file. Also confirm test reports show that documentation tests actually executed.

## 9. Portable Validation Script Example

Java example checking snippet files with `Path`:

```java
Path root = Paths.get(snippetsDirectory);

List<String> requiredFiles = List.of(
    "orders-get/http-request.adoc",
    "orders-get/http-response.adoc"
);

for (String relative : requiredFiles) {
    Path file = root.resolve(relative).normalize();

    if (!file.startsWith(root.normalize())) {
        throw new IllegalArgumentException("Invalid snippet path: " + relative);
    }

    if (!Files.isRegularFile(file) || Files.size(file) == 0) {
        throw new IllegalStateException(
            "Missing or empty REST Docs snippet: " + file
        );
    }

    String text = Files.readString(file, StandardCharsets.UTF_8);
}
```

This example illustrates verifying files and encoding. If using an older Java version without `Files.readString` or `List.of`, substitute compatible APIs. With many operations, you can derive the required files list from a manifest/include declarations to avoid maintaining two separate lists.

## 10. Artifact Paths in CI

Artifact uploads typically accept workspace-relative paths or globs. Paths must match actual outputs:

```text
Gradle:
build/docs/**

Maven:
target/generated-docs/**

Snippets:
build/generated-snippets/**
or
target/generated-snippets/**
```

Do not upload `build/docs` if the plugin actually writes to `build/asciidoc/html5`, or upload snippets from another module's directory. Check plugin output configuration and task logs before declaring artifact paths.

In multi-module builds, identify each module's output and the aggregated location. Do not assume every module writes to one shared root directory.

## 11. Common Errors and Fixes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Include works locally but fails on Linux | Wrong identifier/file casing | Normalize to lowercase and verify exact match |
| Snippet not found | Wrong output directory or working directory | Use shared build directory and resolve paths explicitly |
| Path has wrong separator | Windows-style string concatenation | Use `Path.resolve` or build tool APIs |
| Vietnamese diacritics corrupted | Default encoding other than UTF-8 | Save/read/write explicitly in UTF-8 |
| Whole-file diffs after CI | Inconsistent CRLF/LF | Declare `.gitattributes` |
| Timestamps differ across runners | Different locale/timezone/clock | Use fixed fixtures/`Clock` |
| Artifact upload empty | Wrong glob or different output path | Verify actual output on the runner |
| Module A grabs Module B snippets | Shared output path without module isolation | Scope output by module or identifier namespace |
| File exists yet rendering fails | Empty file or wrong encoding | Check file size and read UTF-8 before rendering |
| Passes locally yet CI lacks snippets | Test task filtered or skipped | Check test count and task execution |

## 12. Best Practices

1. Use Gradle/Maven build directories and path APIs instead of personal-machine absolute paths.
2. Use a single configuration source for snippets output and the Asciidoctor attribute.
3. Use `/` in AsciiDoc include paths and the `Path` API in Java.
4. Normalize identifiers and filenames to consistent casing.
5. Store sources and text outputs in UTF-8; scripts must specify encoding.
6. Declare newline policies via `.gitattributes` if the repository supports multiple OSes.
7. Pin locale/timezone or fixtures whenever they affect snippets.
8. Validate every included file, not just directory existence.
9. Verify artifact paths from actual runner logs/outputs.
10. Run CI on Linux if production builds use Linux, even when developers work on Windows.

## 13. Hands-On Exercise

A Spring REST Docs project is developed on Windows while CI runs on Linux. Tests write snippets to the build directory; Asciidoctor includes requests/responses and Markdown pages contain Vietnamese text. CI currently reports a missing file for one identifier and some Vietnamese diacritics appear corrupted.

**Tasks:**

1. Identify the actual working directory and snippets output directory.
2. Synchronize output configuration between the test recorder and Asciidoctor.
3. Check identifier and filename casing on Linux.
4. Replace string-concatenated paths with appropriate `Path`/Gradle/Maven APIs.
5. Verify `.md`, `.adoc`, snippet, and script sources use UTF-8.
6. Standardize newline policy if the repository must support Windows/Linux.
7. Pin timezone/locale or fixtures for time data.
8. Write validation for included snippet files.
9. Fix artifact upload paths to match actual outputs.
10. Run the pipeline on a clean runner and inspect the Vietnamese HTML/PDF.

**Completion criteria:** paths are portable; includes match casing; recorder and renderer share the same output; UTF-8 text displays accurately; artifacts upload from the right directory; pipeline is reproducible between local and runner.

## 14. Key Takeaways

- Runners can differ from developer machines in OS, working directory, filesystem case sensitivity, locale, and encoding.
- Use the Gradle/Maven build directory as the base instead of hard-coding absolute paths.
- Recorder and Asciidoctor must use the same snippets directory.
- Use `Path.resolve` in Java; avoid manual OS-specific separator concatenation.
- Include paths must match the exact casing of identifiers and filenames.
- Save/read/write Markdown, AsciiDoc, and snippets explicitly in UTF-8.
- Normalize newlines, locale, and timezone to reduce unnecessary diffs.
- Validate every included file and artifact path directly on the runner before publishing.
