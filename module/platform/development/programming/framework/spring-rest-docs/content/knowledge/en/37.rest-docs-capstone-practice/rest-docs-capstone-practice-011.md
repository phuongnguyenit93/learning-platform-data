# Integrating Documentation Checks into CI

## Lesson Objectives

REST API documentation is trustworthy only when it can be reproduced from HTTP tests and verified on every code change. If CI runs unit tests without generating snippets, rendering documentation, and verifying the output, the API pages can become outdated even while the build stays green.

This lesson belongs to the **Capstone Practice** chapter of the **SPRING_REST_DOCS** module: creating verifiable REST API documentation with Spring REST Docs from HTTP tests using **MockMvc**, **WebTestClient**, or **REST Assured**; generating snippets for requests, responses, payloads, parameters, and headers; assembling Asciidoctor/Markdown documentation; and integrating into the build and CI pipeline.

After this lesson, you will be able to:

- Design a complete CI pipeline for Spring REST Docs.
- Wire the proper order of tests, snippet generation, rendering, and documentation checks.
- Set up quality gates so the build fails when snippets are missing or documentation is broken.
- Verify links, includes, JSON, field descriptors, and sensitive data.
- Archive documentation artifacts for review or publishing.
- Keep build results consistent between local machines and CI.
- Separate documentation checks from application deployment when needed.

## 1. Why Verify Documentation in CI?

Spring REST Docs derives documentation content from HTTP operations executed by tests. When the API changes, tests and descriptors can catch new fields, removed fields, or responses that diverge from the contract. However, for readers to receive complete documentation, the pipeline must also assemble snippets and render the documentation.

CI should catch these failures:

- Tests did not run or did not generate snippets.
- Document identifiers changed while AsciiDoc/Markdown files still include the old names.
- Request/response field descriptors no longer match the payload.
- Asciidoctor cannot find an include or extension.
- Markdown assembly drops a fragment.
- Internal links or assets are broken.
- Snippets contain tokens, cookies, or personal data.
- Final artifacts are not produced or are uploaded from the wrong directory.

A complete pipeline turns documentation into a verifiable deliverable rather than a manual post-release chore.

## 2. Pipeline Architecture

Basic flow:

~~~mermaid
flowchart TD
    A["Checkout source"] --> B["Resolve pinned toolchain"]
    B --> C["Run HTTP documentation tests"]
    C --> D["Generate REST Docs snippets"]
    D --> E["Validate required snippets"]
    E --> F["Assemble / render documentation"]
    F --> G["Check links, includes and content"]
    G --> H["Scan for secrets"]
    H --> I["Upload documentation artifact"]
    I --> J["Optional publish / deploy"]
~~~

Each step needs clear pass criteria:

| Step | Pass condition |
| --- | --- |
| Toolchain | Uses the pinned JDK and build wrapper |
| HTTP tests | All documentation tests pass |
| Snippet generation | All operations requiring docs produce output |
| Snippet validation | Required files exist and are non-empty |
| Render | Asciidoctor/Markdown renderer completes successfully |
| Content checks | Links, includes, JSON, and document structure are valid |
| Secret checks | No blocked sensitive data is detected |
| Artifact | Output directory is created and archived successfully |

Do not collapse every step into a single opaque command. Steps may run in the same job, but logs should clearly show which step failed.

## 3. Preparing the Project for CI Reproducibility

Before writing the workflow, lock down:

| Component | Decision to finalize |
| --- | --- |
| JDK | Version and distribution used by CI |
| Build tool | Gradle Wrapper or Maven Wrapper |
| Test integration | MockMvc, WebTestClient, or REST Assured |
| Snippet output | A fixed output directory under `build`/`target` |
| Document identifiers | List of IDs included by documentation |
| Renderer | Asciidoctor task or Markdown generator/assembly |
| Artifact directory | Final HTML/PDF/Markdown directory |
| Validation | Script checking snippets, links, and content |

Use the repository's wrapper rather than installing an arbitrary Gradle/Maven version on the runner. Pin plugin and dependency versions; avoid using `latest` in builds because results can change between CI runs.

Place generated outputs inside the build directory (`build/` with Gradle or `target/` with Maven). Do not commit generated snippets as the source of truth if the project's workflow specifies regenerating them from tests.

## 4. Running Tests to Generate Snippets

With Gradle, REST Docs tests typically run in `test` or a dedicated task. Example:

~~~powershell
./gradlew clean test
~~~

If the project separates documentation tests:

~~~groovy
tasks.register('documentationTest', Test) {
    useJUnitPlatform()
    include '**/*DocumentationTest.class'
}
~~~

Only create a separate task when the project has a matching naming convention and test suite. If the `test` task already runs all REST Docs tests, do not run them twice unnecessarily.

With Maven:

~~~bash
./mvnw clean test
~~~

If tests are split by profiles or Maven Failsafe, activate the right profile/phase to ensure integration tests generating snippets also run. Check the test report to confirm the expected tests actually executed.

### 4.1. Keeping Output Clean

CI usually starts with a fresh workspace, but in jobs with caching or multiple tasks, stale snippet files can still persist. Use a clean build or clean the specific output directory before running snippet-generating tests.

Do not delete the entire workspace or dependency cache indiscriminately. Clean only the output directories owned by documentation tasks.

## 5. Validating Required Snippets

A test suite can pass even when an operation is no longer invoked or no longer records documentation. Therefore, add a step confirming required snippets exist.

PowerShell example:

~~~powershell
$required = @(
    'build/generated-snippets/orders-get/http-request.adoc',
    'build/generated-snippets/orders-get/http-response.adoc',
    'build/generated-snippets/orders-create/request-fields.adoc',
    'build/generated-snippets/orders-create/response-fields.adoc'
)

$missing = $required | Where-Object {
    -not (Test-Path -LiteralPath $_ -PathType Leaf)
}

if ($missing.Count -gt 0) {
    throw "Missing REST Docs snippets: $($missing -join ', ')"
}

$empty = $required | Where-Object {
    (Test-Path -LiteralPath $_ -PathType Leaf) -and
    ((Get-Item -LiteralPath $_).Length -eq 0)
}

if ($empty.Count -gt 0) {
    throw "Empty REST Docs snippets: $($empty -join ', ')"
}
~~~

The paths and extensions above are illustrative. Replace them with your project's actual output directory, document identifiers, and template format. If the project uses Markdown templates, filenames may end in `.md`.

Do not require every snippet type for every operation. For instance, a `GET` with no request body does not need `request-fields.adoc`. The manifest should match the exact fragments that the documentation pages actually include.

## 6. Rendering Asciidoctor Documentation

With the Gradle Asciidoctor plugin, the render task must depend on the snippet-generating task:

~~~groovy
tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir layout.buildDirectory.dir('generated-snippets')
    attributes 'snippets': layout.buildDirectory
        .dir('generated-snippets')
        .get()
        .asFile
}
~~~

Run:

~~~powershell
./gradlew clean test asciidoctor
~~~

Verify the task's output directory. Example:

~~~powershell
Get-ChildItem -Path build/docs/asciidoc -Recurse -File
~~~

Do not assume every plugin configuration writes to `build/docs/asciidoc`; check `outputDir` in the build script.

With Maven, the Asciidoctor plugin must be bound to an appropriate lifecycle phase. Run the configured phase, such as `verify`, and confirm HTML is generated. `mvn test` alone does not guarantee documentation is rendered if the execution runs in a later phase.

### 6.1. Checking Includes

An Asciidoctor include can point to a missing file if:

- The `snippets` attribute points to the wrong output directory.
- `document(...)` changed its identifier.
- The snippet name or extension differs from the active template.
- The render task ran before tests.

Asciidoctor typically reports an error when a required include cannot be found. Do not suppress missing-include errors just to make the pipeline pass; fix the path or update the documentation source.

## 7. Rendering Markdown Documentation

Pure Markdown has no standard file include mechanism. A Markdown pipeline needs one of the mechanisms chosen by the project:

1. A static site generator's include plugin.
2. REST Docs Markdown templates combined with build-time assembly.
3. Converting AsciiDoc snippets to Markdown with a verified tool.

Example flow:

~~~text
HTTP tests
   |
   v
build/generated-snippets/
   |
   v
Markdown assembly
   |
   v
build/docs-markdown/
   |
   v
Markdown site generator
   |
   v
build/site/
~~~

Chain the assembly task after tests and the renderer after assembly. Add a required-fragment check before rendering. If the generator has strict link-checking mode, enable it in CI.

Do not put Asciidoctor include directives inside Markdown files and expect every renderer to process them. Check the exact plugin/generator and version in use.

## 8. Quality Gates for Documentation

A solid pipeline checks multiple layers rather than relying solely on the renderer's exit code:

### 8.1. Tests and Descriptors

- HTTP tests pass.
- Field descriptors cover payloads according to the contract.
- Path/query parameters and headers are documented.
- Response statuses and error cases have appropriate tests.

### 8.2. Snippets

- Every included file exists.
- Snippets are non-empty.
- Operation identifiers were not unintentionally changed.
- Preprocessors masked tokens/cookies/sessions.
- Request/response contents belong to the right test operation.

### 8.3. Rendered Output

- Asciidoctor or the Markdown generator completes successfully.
- No unresolved include directives remain.
- Internal links and assets exist.
- Code fences and tables render properly.
- JSON snippets are valid when a fragment is raw JSON.
- Navigation/TOC is generated according to configuration.

### 8.4. Artifacts

- The output directory exists.
- At least one expected documentation file is present (for example `index.html`).
- Artifacts are saved with recognizable names/versions.
- Publishing runs only after all quality gates pass.

## 9. Checking Sensitive Data

Snippets can contain values captured from test requests/responses. Before publishing, check for:

- `Authorization` and bearer tokens.
- Cookie/session IDs.
- API keys or secret headers.
- Real emails, phone numbers, addresses, and personal data.
- Internal hosts, IPs, or identifiers that should not be exposed.

Use fake fixtures directly in tests and preprocessors to remove/replace sensitive values. Do not rely on a secret scanner as the sole safeguard; test data must be safe at the source.

If CI detects sample tokens such as `test-token`, it can fail to warn that preprocessing is not active. Tune patterns per project policy to avoid false positives on approved illustrative strings.

## 10. GitHub Actions Example

Illustrative Gradle workflow:

~~~yaml
name: REST Docs

on:
  pull_request:
  push:
    branches: [ main ]

jobs:
  documentation:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - name: Generate snippets and render docs
        run: ./gradlew --no-daemon clean test asciidoctor

      - name: Validate required snippets
        shell: bash
        run: |
          required=(
            build/generated-snippets/orders-get/http-request.adoc
            build/generated-snippets/orders-get/http-response.adoc
          )
          for file in "${required[@]}"; do
            test -s "$file" || {
              echo "Missing or empty snippet: $file"
              exit 1
            }
          done

      - name: Verify rendered documentation
        run: test -s build/docs/asciidoc/index.html

      - name: Upload documentation artifact
        uses: actions/upload-artifact@v4
        with:
          name: rest-api-docs
          path: build/docs/asciidoc/
          if-no-files-found: error
~~~

This example assumes JDK 21, branch `main`, task name `asciidoctor`, and the declared snippet and HTML output paths. Adjust to your repository's actual wrapper, JDK support matrix, test IDs, and `outputDir`. For Markdown, replace the Asciidoctor task with the corresponding assembly and generator tasks.

In real repositories, pin actions according to organizational security policy (for example to an approved commit SHA) and grant minimal required permissions.

## 11. Artifacts and Publishing

Separate two decisions:

- **Build artifact:** archive the rendered HTML/Markdown so reviewers can download and inspect it on pull requests.
- **Publish:** deploy documentation to the official website or hosting location after merge/release.

There is no need to publish the live website on every pull request. Upload artifacts for review, then publish from the main branch or release tags.

If documentation is versioned by API release, include version/commit metadata in the artifact path. Avoid overwriting released documentation with output from an unreleased branch.

## 12. Running Pipelines Efficiently and Reproducibly

To keep local and CI results equivalent:

- Use Gradle Wrapper/Maven Wrapper.
- Pin JDK and plugin versions.
- Manage REST Docs artifacts consistently.
- Use stable fixtures for timestamps, UUIDs, and dynamic data.
- Set a clear output directory and clean it before generating snippets.
- Do not depend on files generated from a previous build.
- Do not allow parallel tests to write to the same document identifier if outputs collide.
- Preserve logs and artifacts when the pipeline fails for investigation.

Dependency caching can speed up builds, but never cache generated snippets as a trusted input source. Snippets should be produced from the current commit's source and tests.

## 13. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Tests pass but no documentation is produced | Render task did not run or lacks dependency | Wire `test` → renderer in the task graph |
| Snippet missing in CI | Operation was not executed or ID changed | Check test report, document ID, and manifest |
| Passes locally, fails in CI | Stale output remained on local machine | Run a clean build and verify paths |
| Asciidoctor reports missing include | Wrong attribute or filename | Cross-check generated snippets against includes |
| Markdown retains include directive | Plugin/assembly did not run | Check generator and task dependencies |
| Empty artifact | Uploaded wrong output directory | Check `outputDir` and existing files |
| Pipeline misses tokens | Secret scan does not cover snippet format | Use fake fixtures, preprocessors, and content checks |
| Slow build from repeated test runs | Test task invoked multiple times in workflow | Design one task graph and reuse output in the same job |
| Two tests overwrite snippets | Duplicate document identifier | Assign unique IDs or serialize operations |
| Documentation stale after merge | Publish not tied to latest commit/release | Bind publishing to the exact revision's artifact |

## 14. Comprehensive Practice Exercise

Integrate CI for an order management API:

~~~text
GET  /api/orders/{id}
POST /api/orders
~~~

Requirements:

1. Write HTTP tests using MockMvc, WebTestClient, or REST Assured.
2. Generate request, response, path parameter, and request/response field snippets.
3. Use preprocessors to format JSON and mask sensitive headers.
4. Author an AsciiDoc or Markdown page to include/assemble snippets.
5. Configure the test task to run before the rendering step.
6. Create a required-snippets manifest and fail CI if any file is missing or empty.
7. Check includes, links, JSON, code fences, field tables, and sensitive data.
8. Upload the HTML/Markdown artifact on pull requests.
9. Publish official documentation only after quality gates pass.
10. Intentionally change a document identifier or delete a required snippet to verify CI catches the error.

**Completion criteria:** a fresh commit can generate snippets and documentation from a clean workspace; test failures, missing snippets, render errors, or sensitive data all fail the pipeline; the final artifact can be downloaded and traced back to the commit.

## Remember

CI needs to verify the entire chain: **HTTP tests → REST Docs snippets → Asciidoctor/Markdown → content validation → artifact**. Running tests alone is not enough. Confirm that required snippets exist, include/assembly works, the renderer produces output, links and JSON are valid, sensitive data is sanitized, and artifacts are saved in the proper directory. Pin the toolchain, use a clean workspace, and publish only after quality gates pass so API documentation always remains reproducible from the current commit.

**References:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs Getting Started](https://docs.spring.io/spring-restdocs/reference/getting-started/documentation.html), [Asciidoctor Gradle Plugin](https://docs.asciidoctor.org/gradle-plugin/latest/), [Asciidoctor Maven Plugin](https://docs.asciidoctor.org/maven-tools/latest/), [GitHub Actions Documentation](https://docs.github.com/actions), and [GitHub Actions upload-artifact](https://github.com/actions/upload-artifact).
