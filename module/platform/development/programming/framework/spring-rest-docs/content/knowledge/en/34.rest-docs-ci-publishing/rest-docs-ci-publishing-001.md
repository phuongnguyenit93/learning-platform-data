# Running Snippet-Generating Tests in CI

Spring REST Docs generates documentation from requests and responses recorded when documentation tests run. Therefore, the CI pipeline must execute these tests before the Asciidoctor/Markdown rendering step. If tests do not run, snippets may be missing or left over from a previous build; the documentation will then fail to reflect the current code version.

A reliable pipeline needs to execute in order: clean old output, run snippet-generating tests, verify tests and snippets, render documentation, and then store artifacts or publish according to the project workflow. Tests must be a mandatory condition of the documentation build. When an operation changes and its corresponding test fails, CI must stop before publishing documentation that no longer matches the API.

This lesson belongs to the **CI and Publishing** chapter of the `SPRING_REST_DOCS` module. The module creates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured, generates snippets for requests, responses, payloads, parameters, and headers, and then compiles Asciidoctor/Markdown and integrates it into the build and CI.

## 1. Learning Objectives

After this lesson, you can:

1. Explain the role of documentation tests in a CI pipeline.
2. Order clean, test, snippet generation, and rendering in the right sequence.
3. Configure Gradle or Maven so snippet-generating tests run before Asciidoctor executes.
4. Distinguish the snippet-generating test task from the documentation rendering task.
5. Save generated snippets and rendered documentation as build artifacts.
6. Make the pipeline reproducible and detect stale or missing snippets.
7. Set up failure gates and control sensitive data before publishing.

## 2. Why Must Snippet-Generating Tests Run in CI?

Spring REST Docs does not generate content from controller annotations or standalone API specification files. Snippets are created when tests execute requests, verify responses, and call the document API. Therefore, documentation is directly tied to test fixtures, endpoint behavior, status/header/body assertions, descriptors for fields/parameters/headers, and preprocessors applied before writing snippets.

If the pipeline only renders Asciidoctor without running tests, includes may reference nonexistent files or use stale snippets. Documentation can sometimes still build successfully if old files remain, but the content is no longer verified by the current code.

### 2.1. Standard Pipeline Flow

```text
Checkout source
      │
      ▼
Resolve dependencies
      │
      ▼
Clean generated snippets
      │
      ▼
Run documentation tests
      │
      ├── Test failed ──► Fail CI
      │
      ▼
Verify generated snippets
      │
      ▼
Render Asciidoctor / Markdown
      │
      ▼
Verify rendered documentation
      │
      ▼
Upload build artifacts
      │
      ▼
Publish (if permitted by pipeline)
```

Snippet generation takes place during test execution. Asciidoctor runs after the relevant tests complete and produce all required snippets.

## 3. Organizing Source and Output

A common structure:

```text
project/
├── src/
│   ├── main/
│   └── test/
│       └── java/
│           └── .../
│               └── OrdersDocumentationTests.java
├── src/docs/
│   └── asciidoc/
│       └── index.adoc
├── build/
│   └── generated-snippets/
└── build.gradle
```

With Maven, output is usually in `target/generated-snippets`; with Gradle, many projects use `build/generated-snippets`. These are common conventions, not mandatory paths. Choose a consistent output directory and configure both the test recorder and the Asciidoctor plugin to use that same directory.

Example in a test:

```java
.andDo(document("orders-get",
    requestHeaders(
        headerWithName("Accept")
            .description("Media type accepted by the client")
    ),
    responseFields(
        fieldWithPath("id")
            .description("Order ID"),
        fieldWithPath("status")
            .description("Order status")
    )
));
```

The identifier `orders-get` determines the subdirectory containing the operation's snippets. The identifier name must be stable and used consistently in the AsciiDoc files.

### 3.1. Do Not Commit Generated Snippets as Default Source

Normally, snippets are outputs regenerated from tests, so they should reside in the build directory and be generated on every CI run. This avoids confusing stale generated files with source content.

Some projects may intentionally store snapshots or publish separate artifacts; in that case, clear rules for updating and reviewing them must be defined. Do not allow the pipeline to accidentally use snippets from the working tree or an old cache without verifying their origin.

## 4. Running Documentation Tests with Gradle

With Gradle, documentation tests are typically part of the test source set or a separate test task. If using the shared `test` task, CI can run:

```bash
./gradlew clean test
```

If the project separates documentation tests into a dedicated task, such as `docsTest`:

```bash
./gradlew clean test docsTest
```

The name `docsTest` is only an example; the actual task depends on the build script. Ensure the snippet-generating task is executed before the Asciidoctor task.

### 4.1. Wiring Task Ordering

When using the Asciidoctor Gradle plugin, configure the render task to depend on the snippet-generating test task. General structural example:

```groovy
tasks.named("asciidoctor") {
    dependsOn(tasks.named("test"))
    inputs.dir(layout.buildDirectory.dir("generated-snippets"))
}
```

Task names and paths must match the project. If the snippet-generating test task is `docsTest`, use that task instead of `test`. Declaring the input directory helps Gradle understand the snippet source of the render task.

Do not rely solely on tasks running in the right order in a manual CI command; dependencies between tasks ensure the build remains correct even when a developer invokes the Asciidoctor task directly.

### 4.2. When Tests Do Not Generate Snippets

If tests are filtered, disabled, or excluded from the task, the output directory may lack operations. Verify the number of tests executed in the CI logs and check that required identifiers have corresponding directories/files.

## 5. Running Documentation Tests with Maven

With Maven, documentation tests can run in the test/verify lifecycle depending on how the project is structured. A common command:

```bash
./mvnw clean verify
```

`clean` deletes old output; `verify` runs preceding phases and plugins bound to the lifecycle. The command only generates snippets and renders documentation if tests/plugins are properly configured in `pom.xml`.

### 5.1. Ensuring Asciidoctor Runs After Tests

If using the Asciidoctor Maven plugin, bind the execution to a phase after documentation tests have completed successfully. General example:

```xml
<plugin>
  <groupId>org.asciidoctor</groupId>
  <artifactId>asciidoctor-maven-plugin</artifactId>
  <executions>
    <execution>
      <id>render-rest-docs</id>
      <phase>prepare-package</phase>
      <goals>
        <goal>process-asciidoc</goal>
      </goals>
      <configuration>
        <attributes>
          <snippets>${project.build.directory}/generated-snippets</snippets>
        </attributes>
      </configuration>
    </execution>
  </executions>
</plugin>
```

This is an illustrative structure; plugin version, goal, phase, and output need to match the project. If documentation tests are configured to run later than `prepare-package`, adjust the lifecycle so tests complete before rendering.

### 5.2. Watch Out for Skipped Tests

Some CI configurations use properties that skip tests. Do not publish documentation based on stale snippets when tests are skipped. The publish pipeline must ensure documentation tests actually run; checking only the exit code of the render step is insufficient.

## 6. Linking Tests with Asciidoctor

In AsciiDoc, snippets are included using their corresponding identifier:

```asciidoc
= Orders API

== Get order information

=== Request

include::{snippets}/orders-get/http-request.adoc[]

=== Request headers

include::{snippets}/orders-get/request-headers.adoc[]

=== Response

include::{snippets}/orders-get/http-response.adoc[]

=== Response fields

include::{snippets}/orders-get/response-fields.adoc[]
```

The `snippets` attribute must point to the exact output directory where tests wrote files. You can declare the attribute in the AsciiDoc file or pass it from the build plugin. Avoid hard-coding two different paths between local and CI.

### 6.1. Markdown and Snippets

Markdown does not support Asciidoctor include syntax by default. If the target documentation is Markdown, an explicit snippet insertion or conversion step is needed in the build. The pipeline must run tests before the Markdown assembly step and verify that inserted segments come from the current output.

Do not assume manually copying snippets into Markdown will stay synchronized with tests in subsequent builds.

## 7. Cleaning Output and Reproducibility

Stale snippets can remain in the build directory. For example, a test previously generated `orders-delete`, and then the test was renamed or deleted; without cleaning, the old snippet directory may persist and Asciidoctor will continue including it.

Use a clean build for the documentation pipeline:

```bash
./gradlew clean test asciidoctor
```

Or with Maven:

```bash
./mvnw clean verify
```

These commands are only appropriate when tasks/lifecycles are configured properly. Clean deletes generated output; tests regenerate snippets; rendering uses the fresh output.

### 7.1. Controlling Cache

If CI caches Gradle/Maven dependencies, that is dependency caching; generated snippets should not be cached as authoritative source. If build output caching is necessary, ensure cache keys include relevant source/test/build configurations and tasks declare inputs/outputs accurately.

For public documentation pipelines, clean generation is usually simpler and more reliable than restoring snippets from a cache of uncertain origin.

### 7.2. Verifying the Output Directory

After tests run, verify the output directory exists; each operation has its corresponding identifier; every file included in AsciiDoc is present; files are non-empty and created in the current build; and no deleted or renamed identifiers remain.

A file-checking script or a dedicated validation task can be used. The script should fail with a clear message when snippets are missing, rather than letting the error surface only at the render step.

## 8. Failure Gates: When Must CI Fail?

CI must stop if:

1. A documentation test fails.
2. A test expected to run is skipped.
3. An operation requiring documentation does not generate snippets.
4. An included snippet does not exist or is empty.
5. Asciidoctor/Markdown rendering fails.
6. Secret scanning detects credentials or forbidden values.
7. Artifacts are not produced or required output documentation files are missing.

Do not use options that let the build continue when tests fail in a documentation publishing pipeline. If an unrelated test is allowed to be skipped, configure test groups explicitly; do not accidentally skip all documentation tests.

### 8.1. Distinguishing Test Errors and Render Errors

| Error | Example | Check step |
| --- | --- | --- |
| Test failure | Status/body fails assertion | Test report, application logs |
| No snippets generated | Test did not run or missing document(...) | Test count and generated-snippets |
| Wrong include path | Identifier differs from folder name | AsciiDoc include and output tree |
| Render failure | Invalid attribute or AsciiDoc syntax | Asciidoctor logs |
| Stale content | Build not cleaned | Clean output and rerun tests |
| Secret exposed | Unsafe fixture/preprocessor | Scan snippets and artifacts |

## 9. CI Artifacts

After tests and rendering succeed, store the necessary artifacts for review or deployment:

```text
build/
├── generated-snippets/
│   └── orders-get/
│       ├── http-request.adoc
│       └── http-response.adoc
└── docs/
    └── index.html
```

You can save generated snippets for debugging/review; rendered HTML/PDF for preview; test reports for traceability; and build metadata such as commit SHA, build number, and documentation version.

Artifacts should be tied to a specific commit/build. Do not mix snippets from one commit with HTML from another commit. When publishing, take artifacts from the same pipeline run where tests and rendering succeeded.

### 9.1. Artifacts Do Not Replace Source

Generated snippets and HTML/PDF are build outputs. The authoritative sources remain tests, descriptors, AsciiDoc/Markdown content, and build configuration. When a snippet is wrong, fix the test/preprocessor/descriptor and rerun the pipeline; do not edit output artifacts manually.

## 10. Security When Generating Snippets in CI

CI may run in an environment with many environment variables and credentials. Documentation tests should not read production tokens or real secrets just to produce examples.

- Use fixtures, test principals, or dummy tokens valid only in tests.
- Do not pass CI secrets into tests unless required for the behavior being tested.
- Use preprocessors to replace or remove sensitive values from snippets.
- Scan Authorization, Cookie, Set-Cookie, API keys, URL tokens, and personal data.
- Inspect raw snippets, cURL/HTTPie, HTML/PDF, and uploaded artifacts.
- Do not print secrets into test logs or failure messages.

Secret scanning is an additional layer; safe fixtures from the start remain more important. If a real credential has already been published, halt publishing, assess the scope, and revoke/rotate the credential according to organizational procedures.

## 11. General CI Pipeline Example

A pipeline can be organized into steps:

```yaml
steps:
  - name: Checkout
    run: checkout source

  - name: Clean and test
    run: ./gradlew clean test

  - name: Render REST documentation
    run: ./gradlew asciidoctor

  - name: Validate documentation
    run: ./gradlew verifyDocs

  - name: Upload artifacts
    uses: upload-artifact
    with:
      path: build/docs
```

This is pseudoconfiguration describing order, not runnable workflow YAML as-is: checkout/upload syntax depends on the CI provider and `verifyDocs` is a project task you need to define yourself. If `asciidoctor` already depends on `test`, a composite task can be invoked; you still need to ensure tests actually run and output is cleaned.

### 11.1. Separating Test Jobs and Publish Jobs

For large pipelines, you can separate:

- **Test job:** runs unit/integration/documentation tests and generates snippets.
- **Render job:** receives snippet artifacts from the same commit and renders documentation.
- **Publish job:** runs only when tests, validation, and rendering all succeed.

If jobs are separated, artifacts passed between jobs must have clear commit/build identity. The render job should not fetch snippets from a cache or an artifact from another run.

## 12. Common Errors and Fixes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Asciidoctor reports missing snippet | Tests did not run or wrong identifier | Run docs tests before render; check identifier |
| Docs still build but with stale content | Generated directory not cleaned | Clean before test and render |
| CI generates no snippets while local does | Documentation tests excluded/skipped in CI | Check test filters and profiles |
| Render task runs before tests | Missing dependency between tasks | Declare dependsOn or lifecycle phase |
| Tests pass but snippet files missing | Test does not call document or operation uncovered | Check test body and output tree |
| Snippet path differs between local and CI | Output directory configured inconsistently | Use a single shared property/attribute |
| Secret appears in artifact | Real fixture or preprocessor not applied | Use fake data, scan all outputs |
| Publish runs despite test failure | Pipeline allows continue-on-error/skip | Set up failure gates |
| Render job uses snippets from another commit | Artifact/cache not tied to commit | Pass artifacts within the same pipeline run |
| Markdown does not include snippets | Using Asciidoctor syntax as default Markdown | Add explicit insertion/conversion step |

## 13. Hands-On Exercise

Integrate documentation tests for the orders API into CI. Tests generate snippets for `GET /api/orders/{id}` and `POST /api/orders`. AsciiDoc documentation includes request, response, header, and field snippets.

**Tasks:**

1. Identify the Gradle or Maven task that runs documentation tests.
2. Choose a single consistent `generated-snippets` directory.
3. Configure cleaning before running tests.
4. Ensure snippet-generating tests run before Asciidoctor.
5. Add a check for snippet files of each included identifier.
6. Configure rendering documentation to HTML or PDF.
7. Configure CI to fail when tests, validation, or rendering fail.
8. Save test reports, generated snippets, and rendered docs as artifacts of the same commit.
9. Add secret scanning for raw snippets and rendered output.
10. Run the pipeline from a clean state and confirm documentation does not use stale output.

**Completion criteria:** documentation tests actually run in CI; snippets are freshly generated; rendering runs after tests; missing snippets or failing tests stop the pipeline; artifacts match the right commit; no secrets exist in the output.

## 14. Key Takeaways

- Spring REST Docs generates snippets when documentation tests run; documentation rendering must occur after this step.
- Clean output before tests to prevent stale snippets from hiding untested operations.
- Gradle needs proper task dependencies; Maven needs lifecycle phases ensuring tests run before Asciidoctor.
- Testing, snippet generation, validation, and rendering must be mandatory steps before publishing.
- Use one consistent output directory for both the recorder and Asciidoctor.
- Save snippets, HTML/PDF, and test reports as artifacts of the same commit/build.
- Use dummy fixtures, secret scanning, and artifact review to avoid exposing sensitive data.
- CI should publish documentation only when tests, snippet validation, and rendering all succeed.
