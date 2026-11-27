# Verifying Templates and Snippets After an Upgrade

## 1. Objectives

Spring REST Docs produces verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. Tests generate snippets for requests, responses, payloads, headers, parameters, and multipart parts; Asciidoctor combines snippets with templates and AsciiDoc content to build documentation.

After upgrading Spring Boot, Spring Framework, Spring REST Docs, Spring Test, or Asciidoctor, the build may still succeed while documentation output changes. Causes include formatters, serialization, default headers, snippet paths, template extensions, or the Asciidoctor version.

This lesson walks through systematic verification:

- Do tests still generate all snippets and operation IDs as before?
- Has snippet content changed unexpectedly?
- Are templates and AsciiDoc includes still compatible?
- Does the resulting HTML contain all endpoints, fields, links, CSS, and images?
- Does CI detect unintended documentation changes?

## 2. Establishing a Baseline Before Upgrading

Before changing dependencies/plugins, save a comparable baseline:

1. Commit/source revision currently released.
2. Java, Spring Boot, Spring Framework, Spring REST Docs, and Asciidoctor versions.
3. Build commands that generate snippets and HTML.
4. List of operation IDs and generated snippet files.
5. Representative snippets for requests, responses, fields, headers, parameters, and payloads.
6. HTML output and required assets.

Example output structure:

```text
target/
├── generated-snippets/
│   ├── users-get/
│   │   ├── http-request.adoc
│   │   ├── http-response.adoc
│   │   ├── path-parameters.adoc
│   │   └── response-fields.adoc
│   └── users-create/
│       ├── http-request.adoc
│       ├── request-fields.adoc
│       └── http-response.adoc
└── generated-docs/
    ├── index.html
    ├── css/
    └── images/
```

Do not treat the entire generated output mechanically as a golden file. Select representative snippets and identify which parts must remain stable and which may legitimately vary, such as timestamps, multipart boundaries, or generated metadata.

## 3. Keeping Test Data and HTTP Requests Deterministic

Snippets reflect the actual requests and responses sent and received by tests. If fixtures are unstable, post-upgrade diffs become noisy and it is hard to separate dependency changes from test-data variance.

Example test using fixed data:

```java
mockMvc.perform(get("/users/{id}", "42")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("users-get",
        pathParameters(
            parameterWithName("id").description("User ID")
        ),
        responseFields(
            fieldWithPath("id").description("User ID"),
            fieldWithPath("name").description("User name")
        )
    ));
```

To keep snippets deterministic:

- Use fixed fixtures rather than relying on existing data in a shared database.
- Do not generate random IDs if those IDs appear in documentation.
- Fix the clock when responses include timestamps.
- Avoid depending on collection order if the contract does not guarantee ordering.
- Use deterministic locales/timezones when formatting dates and times.
- Do not place real tokens, passwords, or personal data into sample requests/responses.

With REST Assured or WebTestClient, the same principle applies: request bodies, headers, and responses must be reproducible across runs.

## 4. Verifying Operation IDs and Snippet Sets

The operation ID passed to the document method is the directory name holding the snippets. For example:

```java
.andDo(document("users-get", ...))
```

writes output into the directory §users-get§. AsciiDoc include files must use that exact name:

```asciidoc
include::{snippets}/users-get/http-request.adoc[]
include::{snippets}/users-get/http-response.adoc[]
include::{snippets}/users-get/response-fields.adoc[]
```

If an operation ID changes, old templates may report missing includes or accidentally reference another operation's snippets. After upgrading, verify:

- Number of operations executed by tests.
- Snippet directory names.
- List of files inside each directory.
- Include paths in AsciiDoc files.
- Snippet handlers actually configured in tests.

Do not only check that the directory exists; it may still contain stale files from a previous build. Use a clean build to separate current output from stale output.

## 5. Comparing Snippets Before and After Upgrading

Run clean builds on the pre-upgrade revision and the post-upgrade revision using the same JDK/toolchain, profile, and test data. Compare files by operation ID.

PowerShell example:

```powershell
Get-ChildItem target/generated-snippets -Recurse -File |
    ForEach-Object { $_.FullName.Substring((Resolve-Path target/generated-snippets).Path.Length) } |
    Sort-Object
```

To generate checksums for the files:

```powershell
Get-ChildItem target/generated-snippets -Recurse -File |
    Get-FileHash -Algorithm SHA256 |
    Sort-Object Path
```

On Git Bash/Linux/macOS you can use:

```bash
find target/generated-snippets -type f | sort
find target/generated-snippets -type f -print0 | sort -z | xargs -0 sha256sum
```

Hashes detect changed files, but they do not explain what changed inside. For differing files, use text diffs to identify:

- Added or removed headers.
- Changed JSON formatting or field order.
- Changed request/response bodies.
- Missing field descriptors or descriptions.
- Different paths, query parameters, or content types.

Classify each diff as a contract change, a valid formatting change, a fixture change, or a regression. Do not update golden files just to make CI green without understanding the root cause.

## 6. Verifying AsciiDoc Templates and Extensions

The Spring REST Docs Asciidoctor extension provides the snippets attribute and related macros. For example:

```asciidoc
= User API
:toc: left

== GET /users/{id}

=== Request
include::{snippets}/users-get/http-request.adoc[]

=== Response
include::{snippets}/users-get/http-response.adoc[]

=== Response fields
include::{snippets}/users-get/response-fields.adoc[]
```

After upgrading, check:

1. The Asciidoctor plugin still loads the Spring REST Docs extension.
2. The snippets attribute points to the right generated-snippets directory.
3. Base directory and source directory have not changed unintentionally.
4. All include paths point to existing files.
5. Attributes, macros, and syntax are supported by the new plugin version.
6. Any project-custom templates are still included properly.

If logs report a missing attribute or include file, verify the plugin dependencies and extension classpath before editing templates. Do not change include paths to local machine paths.

## 7. Verifying Custom Templates

Projects may customize snippet templates to change how requests/responses are presented. When upgrading Spring REST Docs, custom templates may no longer match the context or model provided by the new version.

Verification workflow:

- List custom templates currently being overridden.
- Identify which snippets use each template.
- Compare default snippet output against custom output.
- Inspect placeholders/context referenced by the template.
- Render samples with requests containing headers, bodies, query parameters, and error responses.
- Confirm the template does not drop important data.

Do not copy internal templates from an old version into a new version without checking the new release's implementation/documentation. If no layout customization is needed, prefer default templates to reduce maintenance cost.

### 7.1. Example Template Verification Matrix

| Snippet | Required Test Case | What to Verify |
| --- | --- | --- |
| http-request | GET with path/query/headers | Method, URI, headers |
| http-response | 200 and 4xx error | Status, headers, body |
| request-fields | JSON nested object | Path, type, description, optionality |
| response-fields | Arrays and nested objects | Field path, type, description |
| path-parameters | Endpoint with path variables | Parameter name and description |
| request-parameters | Query/form parameters | Name, required/optional, description |
| request-parts | Multipart upload | Part name, content type, description |

## 8. Checking Snippet Content by Group

### 8.1. Request and Response

Verify method, URL, status code, Content-Type, Accept, and important headers. If a header disappears after upgrading, verify that the test sends that header and that the handler captures it.

### 8.2. Payload and Field Descriptors

Verify field paths, types, descriptions, optionality, ignored fields, and relaxed mode. For nested JSON/arrays, confirm descriptor paths still reflect the payload structure accurately.

Do not use relaxed descriptors to hide regressions. If a new field appears outside the contract, decide explicitly whether it should be documented, intentionally ignored, or cause the test to fail.

### 8.3. Parameters and Headers

Verify path parameters, query parameters, form parameters, and request headers. Some handlers generate separate snippets; passing tests do not guarantee every snippet was requested to be generated.

### 8.4. Multipart and Binary

Multipart boundaries can vary between runs. Do not compare boundaries byte-for-byte if they are not part of the contract. Focus on checking part names, content types, filenames, and documented payloads.

## 9. Verifying HTML After Asciidoctor

Correct snippets are not enough; the final HTML documentation must also be verified. Run the documentation pipeline:

```bash
./mvnw clean test
./mvnw prepare-package
```

Or Gradle:

```bash
./gradlew clean test asciidoctor
```

Check:

- The HTML entry point is generated.
- Expected sections/operations appear.
- No unresolved placeholders such as the snippets attribute remain.
- No include warnings/errors occur.
- Inter-page links work.
- CSS, JavaScript, images, and fonts exist.
- Anchors, table of contents, and code blocks render properly.

HTML can still be produced while missing content if includes are skipped or templates are no longer invoked. Therefore inspect text content and headings, not just the build exit code.

## 10. Automating Checks in CI

CI should run clean builds so old snippets cannot hide tests failing to generate output. Maven example:

```bash
./mvnw clean package
```

Gradle:

```bash
./gradlew clean bootJar
```

You can add an output structure check step:

```bash
test -f target/generated-snippets/users-get/http-request.adoc
test -f target/generated-snippets/users-get/http-response.adoc
test -f target/generated-docs/index.html
```

Adjust paths according to your project's build tool and actual output directory. With Gradle, checks usually target build/generated-snippets and build/docs/asciidoc or the configured outputDir.

To catch unintended changes, CI can:

1. Generate snippets from a clean checkout.
2. Compare the operation/file list against an expected manifest.
3. Run Asciidoctor and fail if include/attribute warnings are treated as errors.
4. Check the HTML entry point and essential assets.
5. Save snippet diffs or docs artifacts as build artifacts for reviewers to inspect.

You do not necessarily need to commit all generated snippets into Git. If a repository chooses to store golden outputs, define clear update rules and require diff content review.

## 11. Diagnosing Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Missing snippet folder after clean build | Test did not run, was skipped, or operation not called | Check test discovery and build flags |
| Include file does not exist | Operation ID changed or handler did not generate that snippet | Match document ID, handler, and include path |
| Snippets differ significantly after upgrade | Formatter/serializer/default header or fixture changed | Diff contents and classify each change |
| Custom template fails | Context/placeholders or extension behavior changed | Compare template against the new release |
| Asciidoctor fails to resolve snippets | Extension failed to load or wrong attribute path | Check plugin dependencies and configuration |
| HTML missing sections | Include skipped, different source file, or missing operation | Inspect logs, source tree, and snippet list |
| HTML has broken links | Asset paths changed or not all output was copied | Check relative links and archive contents |
| CI passes but docs are stale | Non-clean build or missing task input/output declarations | Clean build and inspect task graph |
| Multipart diff keeps changing | Dynamically generated boundary | Ignore non-contract varying parts; verify part semantics |

## 12. Hands-On Exercise

Perform a simulated upgrade for the User API:

1. Run a baseline on the current revision and save generated-snippets.
2. Record the list of operation IDs along with expected snippet files.
3. Run tests covering GET user, POST user, query parameters, and response fields.
4. Upgrade one dependency/plugin on a test branch.
5. Run a clean test build and generate new snippets.
6. Compare file lists, hashes, and snippet contents before/after.
7. Check custom templates and AsciiDoc includes.
8. Run Asciidoctor; inspect HTML, headings, links, and assets.
9. Build the JAR and verify docs are packaged if the application serves docs itself.
10. Document each diff as expected or regression and request reviewer verification.

**Completion criteria:** baseline exists; tests generate all snippets; operation IDs/includes are consistent; templates work; HTML is complete; CI catches missing or unexpected output changes.

## 13. Self-Check Questions

**1. Why run a clean build before checking snippets?**

So leftover files from an earlier build do not mislead you into thinking current tests generated all output.

**2. How does the operation ID affect snippet paths?**

The operation ID creates the output directory; AsciiDoc includes must use that exact same name.

**3. Why do passing tests not prove templates are right?**

Tests only verify requests/responses and write snippets for invoked handlers. Asciidoctor/templates can still fail or drop content during rendering.

**4. How should snippet diffs after an upgrade be handled?**

Classify them into contract changes, valid formatting, fixture variance, and regressions; never update baselines mechanically.

**5. Why inspect both HTML and assets?**

Pages may be generated yet miss sections, CSS, images, or links due to broken includes or paths.

**6. Must multipart boundaries always remain identical?**

No. Boundaries are typically varying transport data; verify part semantics instead of requiring a fixed boundary if it is not part of the contract.

## References

- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html): test configuration, generated snippets, and Asciidoctor.
- [Spring REST Docs — Reference Documentation](https://docs.spring.io/spring-restdocs/docs/current/reference/htmlsingle/): snippet generation, descriptors, and template customization.
- [Asciidoctor Maven Plugin](https://docs.asciidoctor.org/maven-tools/latest/): processing AsciiDoc in Maven builds.
- [Asciidoctor Gradle Plugin](https://docs.asciidoctor.org/gradle-plugin/latest/): Asciidoctor tasks and output configuration.
- [Gradle — Incremental Builds](https://docs.gradle.org/current/userguide/incremental_build.html): declaring task inputs/outputs for reproducible builds.
