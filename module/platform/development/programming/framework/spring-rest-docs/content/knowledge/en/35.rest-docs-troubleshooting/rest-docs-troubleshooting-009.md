# Markdown Include Wrong Path in Spring REST Docs

## 1. Why Does the Include Fail to Find Snippets?

Spring REST Docs writes snippets into an output directory, with each operation placed in a directory determined by its document identifier. For example:

```text
build/
  generated-snippets/
    orders/
      get-by-id/
        http-request.adoc
        http-response.adoc
        curl-request.adoc
```

Asciidoctor documents normally include snippets via paths relative to an attribute such as `{snippets}`. If the attribute points to the wrong output root, the identifier in the include does not match, tests have not generated snippets yet, or the build runs out of order, Asciidoctor reports that the file cannot be found.

With Markdown, include syntax is not a standard feature. Spring REST Docs can generate Markdown-formatted snippets, but how those snippets are embedded into an aggregated page depends on the project's generator, templates, or static-site tool. Do not assume Asciidoctor's `include::...[]` syntax works in `.md` files.

The **SPRING_REST_DOCS** module creates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. Tests generate snippets for requests, responses, payloads, parameters, and headers; these are then assembled into Asciidoctor/Markdown and integrated into build/CI. This lesson belongs to the **Troubleshooting** chapter and focuses on diagnosing wrong include paths in Markdown/Asciidoctor and wiring snippet outputs properly into documentation.

After this lesson, you will be able to:

1. Distinguish the output directory, document identifier, and snippet filename.
2. Inspect the `snippets` attribute value and actual include paths.
3. Fix includes when changing identifiers or output directories.
4. Configure Gradle/Maven so tests generate snippets before rendering.
5. Distinguish Asciidoctor includes from snippet embedding approaches in Markdown.

## 2. Three Components That Form an Include Path

| Component | Example | Role |
| --- | --- | --- |
| Output directory | build/generated-snippets | Root where tests write snippets |
| Document identifier | orders/get-by-id | Operation subdirectory |
| Snippet filename | http-request.adoc | File to include |

Full path:

```text
build/generated-snippets/orders/get-by-id/http-request.adoc
```

If Asciidoctor declares:

```asciidoc
include::{snippets}/orders/get-by-id/http-request.adoc[]
```

then `{snippets}` must point directly to `build/generated-snippets`, not `build/generated-snippets/orders` or the `get-by-id` directory itself.

### 2.1. Inspecting the Directory Tree Before Editing Includes

Do not guess paths based on test names or endpoints. Open the output directory after tests run and verify:

- The actual identifier directory.
- The actual snippet filenames.
- The uppercase/lowercase casing of each segment.
- Whether the file exists in the right module being built.

If the file does not exist in the output, the error lies in snippet generation or output configuration; changing the include cannot create a missing file.

## 3. Configuring the `snippets` Attribute in Asciidoctor

An Asciidoctor document typically declares an attribute pointing to the output root:

```asciidoc
:snippets: build/generated-snippets

= Order API

== Get Order

include::{snippets}/orders/get-by-id/http-request.adoc[]
include::{snippets}/orders/get-by-id/http-response.adoc[]
```

During rendering, Asciidoctor substitutes `{snippets}` with the attribute value. If the attribute is undeclared or the build fails to pass it in, the include may be left verbatim or raise an error depending on configuration.

### 3.1. Passing the Attribute from Gradle

Gradle Groovy DSL example:

```groovy
def snippetsDir = file('build/generated-snippets')

test {
    outputs.dir snippetsDir
    useJUnitPlatform()
}

asciidoctor {
    inputs.dir snippetsDir
    dependsOn test
    attributes 'snippets': snippetsDir
}
```

Kotlin DSL example:

```kotlin
val snippetsDir = layout.buildDirectory.dir("generated-snippets")

tasks.test {
    outputs.dir(snippetsDir)
    useJUnitPlatform()
}

tasks.named("asciidoctor") {
    inputs.dir(snippetsDir)
    dependsOn(tasks.test)
    attributes(mapOf("snippets" to snippetsDir.get().asFile))
}
```

This is an illustrative configuration; Asciidoctor plugins and task names may vary by project. What matters is that the output directory matches where Spring REST Docs writes snippets, and Asciidoctor runs after tests.

### 3.2. Passing the Attribute from the Command Line

You can pass the attribute when invoking the Asciidoctor CLI:

```bash
asciidoctor -a snippets=build/generated-snippets src/docs/asciidoc/index.adoc
```

Relative paths are resolved from the rendering process's working directory. If the build runs inside a subproject, check the working directory and maintain a consistent project layout.

## 4. Relative vs. Absolute Paths

Relative include paths are typically resolved relative to the current Asciidoctor file's location or an include base directory configured by the toolchain. Do not assume every relative path is resolved from the repository root.

Example:

```text
project/
  src/docs/asciidoc/
    index.adoc
  build/generated-snippets/
    orders/get-by-id/http-request.adoc
```

If `index.adoc` declares directly:

```asciidoc
include::../../build/generated-snippets/orders/get-by-id/http-request.adoc[]
```

the relative path is resolved according to Asciidoctor's include rules. If `index.adoc` is moved to another folder, that path may no longer be valid.

Using the `{snippets}` attribute decouples the output location from the documentation source location. When building across environments, you only need to pass the right root path.

### 4.1. Avoiding Hard-Coded Developer Machine Paths

Do not include using paths like:

```asciidoc
include::C:/Users/dev/project/build/generated-snippets/orders/get-by-id/http-request.adoc[]
```

This path exists only on a single machine. Use project-relative paths or build-injected attributes so local environments, CI, and teammates share the same configuration.

## 5. The Identifier in the Include Must Match `document(...)`

Test:

```java
mockMvc.perform(get("/api/orders/42"))
        .andDo(document("orders/get-by-id"));
```

Correct include:

```asciidoc
include::{snippets}/orders/get-by-id/http-request.adoc[]
```

Wrong include:

```asciidoc
include::{snippets}/order/get-order/http-request.adoc[]
```

The URL `/api/orders/42` does not automatically create the `orders/get-by-id` directory; the directory is determined by the identifier passed to `document(...)`. When refactoring identifiers, update includes and any scripts checking required snippets.

### 5.1. Class/Method/Step Placeholders

If a test uses:

```java
document("{class-name}/{method-name}/{step}")
```

then the actual path depends on the class, method, and exchange sequence number:

```text
build/generated-snippets/
  order-documentation-tests/
    create-and-read-order/
      1/
      2/
```

Do not include `{class-name}` as a literal string unless Asciidoctor is passed a corresponding attribute value. Documentation normally writes includes with resolved directory names or lets a build script define dedicated attributes for class/method.

## 6. Snippets Not Yet Generated When Asciidoctor Runs

A common cause is that the render task runs before tests. In Gradle, declare the dependency:

```groovy
tasks.named('asciidoctor') {
    dependsOn tasks.test
    inputs.dir file('build/generated-snippets')
}
```

Then run:

```bash
./gradlew clean test asciidoctor
```

With Maven, bind the Asciidoctor goal to a lifecycle phase after test or verify depending on the plugin in use:

```bash
mvn clean verify
```

If tests fail or do not run, the snippets needed by includes will not be generated. Check the test report and output directory before concluding the error lies in Asciidoctor.

### 6.1. Stale Snippets Hiding Broken Includes

Without cleaning the output, files from a prior run may remain on disk. Old includes continue to succeed even if current tests changed identifiers or stopped documenting that operation.

In CI/release builds, use a clean build:

```bash
./gradlew clean test asciidoctor
```

A clean build exposes stale includes pointing to files that are no longer generated.

## 7. Markdown Has No Standard Include Syntax

Standard Markdown does not define a file-inclusion directive like Asciidoctor. The line:

```markdown
include::{snippets}/orders/get-by-id/http-request.adoc[]
```

is not standard Markdown syntax. A standard Markdown renderer will display that line as literal text or process it only via a custom extension.

If your primary documentation uses Markdown, you have several options:

1. Use Spring REST Docs Markdown templates to generate `.md` snippets, then link or assemble content via your site generator's mechanism.
2. Use an include plugin/extension provided by the static-site generator chosen by the project.
3. Use a controlled build script to inject snippets into Markdown before rendering.
4. Use Asciidoctor as the primary documentation source when direct snippet includes and many operations are needed.

Do not use Asciidoctor syntax inside Markdown unless your Markdown pipeline explicitly supports an extension for it. Inspect the rendered HTML to confirm snippets are actually embedded rather than displayed as raw directives.

### 7.1. Assembling Markdown Snippets with a Script

A build script can read snippet files and insert them at markers inside Markdown. Example marker:

```markdown
## Get Order

<!-- snippet: orders/get-by-id/http-request.md -->
```

The script must resolve source paths strictly beneath the configured output root, fail clearly if a snippet is missing, avoid reading arbitrary paths outside the output root, write output to a separate generated directory, and run after snippet-generating tests but before the Markdown renderer.

If using a custom script, add tests for missing-file and wrong-identifier cases.

## 8. Checking Snippet Filenames

Snippet filenames depend on the operation and snippet templates:

| Target | Common file |
| --- | --- |
| HTTP request | http-request.adoc |
| HTTP response | http-response.adoc |
| cURL request | curl-request.adoc |
| Request body | request-body.adoc |
| Response body | response-body.adoc |
| Request fields | request-fields.adoc |
| Path parameters | path-parameters.adoc |
| Request headers | request-headers.adoc |

Do not guess filenames if the project customizes snippet templates or uses Markdown format. Open the output directory to inspect actual files.

A frequent mistake is including `request-fields.adoc` when the test only documents `requestParameters(...)` or has not called `requestFields(...)`. When a snippet is not created, check the descriptors and test before editing the include.

## 9. Windows and Linux Differences

Windows is typically case-insensitive in paths by default, whereas Linux is case-sensitive. The include:

```asciidoc
include::{snippets}/Orders/Get-By-Id/http-request.adoc[]
```

may work on a Windows workstation even when the actual directory is `orders/get-by-id`, yet fail on Linux CI.

Keep identifiers and includes in identical casing, use forward slashes `/` in Asciidoctor include paths, avoid special characters or spaces in identifiers, never construct paths using Windows backslashes inside Asciidoctor files, and test on Linux CI or a container matching the release environment.

## 10. Diagnosing from Error Messages

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Include file not found | Wrong output root or identifier | List the `generated-snippets` tree |
| Attribute `snippets` not defined | Attribute not declared or not passed | Check Asciidoctor headers and Gradle attributes |
| Include works locally but fails in CI | Case-sensitive path or different working directory | Check exact names on Linux |
| File missing after clean | Tests do not generate snippet or identifier changed | Run tests and inspect the report |
| Markdown renders literal include directive | Using Asciidoctor syntax in plain Markdown | Use Markdown integration/templates or a script |
| Only `request-fields` snippet is missing | Test does not invoke matching descriptor | Check `requestFields(...)` and output |
| Include path duplicates `build/generated-snippets` | `{snippets}` already contains the identifier | Reset attribute to the output root |
| Include still pulls stale content | Stale snippets were not cleaned | Run a clean build |

## 11. Verifying Includes Before Publishing

Recommended workflow:

1. Confirm the output directory in the test configuration.
2. Confirm identifiers in `document(...)`.
3. Run clean and tests to generate fresh snippets.
4. List snippet files and compare against the include list.
5. Pass `{snippets}` pointing to the right output root into Asciidoctor.
6. Render documentation and inspect HTML/PDF output.
7. If using Markdown, verify the extension/script actually embeds snippets.
8. Run the same pipeline on Linux CI to catch casing and path-separator issues.

Example check for required files:

```bash
test -f build/generated-snippets/orders/get-by-id/http-request.adoc
test -f build/generated-snippets/orders/get-by-id/http-response.adoc
```

Audit include directives in Asciidoctor sources:

```bash
rg -n 'include::' src/docs/asciidoc
```

CI should fail whenever a required file is missing or Asciidoctor cannot resolve an include. Do not ignore include errors just to let the build continue publishing incomplete documentation.

## 12. Hands-On Exercise

A test generates snippets:

```java
mockMvc.perform(get("/api/orders/42"))
        .andDo(document("orders/get-by-id"));
```

Steps:

1. Configure the output root as `build/generated-snippets`.
2. Create an Asciidoctor source with the `snippets` attribute.
3. Include `http-request.adoc` and `http-response.adoc` from the `orders/get-by-id` identifier.
4. Intentionally mistype the identifier to observe the include error.
5. Run `clean test asciidoctor` and verify the error is caught.
6. If using Markdown docs, try an Asciidoctor directive in plain Markdown; then choose a suitable template/extension or assembly script.
7. Run the pipeline on Linux CI to verify casing and path separators.

**Completion criteria:** Includes point to the right output root, identifier, and filename; tests generate snippets before rendering; Markdown uses a supported embedding mechanism; clean builds and CI catch missing files, stale snippets, and casing mismatches.

## 13. Key Takeaways

A snippet path consists of the output directory, document identifier, and snippet filename. Asciidoctor uses include directives together with an attribute such as `{snippets}`; the attribute must point to the output root and includes must match actual identifiers and filenames. Tests must run before the rendering step. Plain Markdown has no standard file-include syntax, so it requires templates, extensions, or a dedicated assembly script. Cleaning output, checking filenames, preserving exact casing, and running on Linux CI catch broken includes before publishing.

### References

- [Spring REST Docs — Getting Started and Snippets](https://docs.spring.io/spring-restdocs/docs/current/reference/htmlsingle/)
- [Asciidoctor — Include Directive](https://docs.asciidoctor.org/asciidoc/latest/directives/include/)
- [Asciidoctor Gradle Plugin — Attributes](https://docs.asciidoctor.org/gradle-plugin/latest/common-task-configuration/)
