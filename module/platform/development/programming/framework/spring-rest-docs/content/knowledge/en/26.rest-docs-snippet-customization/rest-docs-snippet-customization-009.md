# Keeping templates compatible when upgrading Spring REST Docs

## 1. Why can upgrades break custom templates?

Spring REST Docs generates snippets by combining data from operations, descriptors, and Mustache templates. Custom templates are usually placed in test resources to override default templates, for example:

```text
src/test/resources/
└── org/springframework/restdocs/templates/
    └── asciidoctor/
        ├── request-fields.snippet
        └── response-fields.snippet
```

These files give documentation custom titles, column names, display labels, and presentation conventions. However, templates are not a presentation layer independent of the library. They depend on the data Spring REST Docs provides to each snippet, how templates are loaded, the selected format, and the versions of integration modules.

During an upgrade, you may encounter situations such as:

- A custom template is still loaded, but Mustache variables no longer match the model.
- A default snippet changed its content or rendering behavior.
- Java APIs used by a custom snippet were deprecated or removed.
- Versions of Spring Framework, JUnit, AsciidoctorJ, or REST Assured require synchronized upgrades.
- The build still generates snippets, yet tables lose columns, miss data, or fail when Asciidoctor includes them.
- Generated documentation changes too broadly, making it hard for reviewers to separate API changes from formatting changes.

In the **SPRING_REST_DOCS** module, REST API documentation is generated from HTTP tests using MockMvc, WebTestClient, or REST Assured. Therefore, after an upgrade you must verify both layers: tests still verify requests/responses, and templates still present the verified data accurately.

This lesson belongs to the **Snippet customization** chapter. The goal is to establish a repeatable upgrade workflow, know how to compare against the target version's templates, check custom attributes, verify generated snippets, and integrate those checks into build/CI.

After this lesson, you will be able to:

- Identify dependencies between templates and library versions.
- Compare custom templates with the default templates of the target version.
- Verify format IDs, snippet names, Mustache variables, and custom attributes.
- Upgrade custom snippets using `TemplatedSnippet` and operation APIs.
- Distinguish issues caused by REST Docs, test frameworks, Asciidoctor, and build configuration.
- Compare pre-/post-upgrade output and design regression checks in CI.

## 2. Components to check when upgrading

A Spring REST Docs setup typically involves multiple interrelated components. Never just bump the `spring-restdocs-*` version and assume everything else stays intact.

| Component | What to verify |
| --- | --- |
| Spring REST Docs core | Snippet APIs, operation model, descriptors, and template resolution |
| Integration module | `spring-restdocs-mockmvc`, `spring-restdocs-webtestclient`, or `spring-restdocs-restassured` |
| Spring Framework | MockMvc, WebTestClient, multipart, HTTP abstractions, and baseline compatibility |
| JUnit/Test framework | Extensions, lifecycle, and supported JUnit versions |
| AsciidoctorJ and plugins | Documentation build capability, macros, and plugin compatibility |
| REST Assured | Multipart/filter APIs and minimum supported version |
| Custom Mustache templates | Variable names, model structure, and fallbacks |
| Custom snippets | Constructors, `createModel`, Operation APIs, and output filenames |
| Build tool | Dependency configuration, test outputs, and Asciidoctor task ordering |

Components must be compatible as a combined set. For example, upgrading REST Docs to a new major version may simultaneously require a newer Spring Framework or AsciidoctorJ version. Exact conditions depend on the release; always read the system requirements and release notes of the target version.

### 2.1. Explicitly record source and target versions

In the upgrade pull request, clearly document:

- Current Spring REST Docs version.
- Target version you intend to move to.
- Integration modules in use.
- Spring Framework and test framework versions.
- Asciidoctor/REST Assured plugin versions.
- Which templates are currently overridden.

Example tracking table:

| Component | Before upgrade | After upgrade |
| --- | --- | --- |
| Spring REST Docs | `3.x.y` | `4.x.y` |
| Spring Framework | `6.x.y` | `7.x.y` if required by target release |
| AsciidoctorJ | `2.x.y` | `3.x.y` if required by target release |
| JUnit | `5.x.y` | Version compatible with the new baseline |
| Custom template format | `asciidoctor` | `asciidoctor` |

These values are illustrative only. Do not copy this table as an official compatibility matrix; fill in versions confirmed from release notes and your project's dependency management.

## 3. Understanding the contract between snippets and Mustache templates

Spring REST Docs uses the template format to look up templates on the classpath. The default format is Asciidoctor with ID `asciidoctor`; Markdown is also supported with its corresponding format ID.

Override example:

```text
src/test/resources/org/springframework/restdocs/templates/asciidoctor/
└── request-fields.snippet
```

Template names map to snippet names:
- `request-fields.snippet` generates `request-fields.adoc`.
- `response-fields.snippet` generates `response-fields.adoc`.
- `http-request.snippet` generates `http-request.adoc`.

A request fields template may use variables such as:

```adoc
{{#title}}
.{{title}}
{{/title}}
|===
|Path|Type|Description|Constraints

{{#fields}}
|{{path}}
|{{type}}
|{{description}}
|{{constraints}}

{{/fields}}
|===
```

Templates rely on the model supplied by the corresponding snippet. `title` can be a snippet attribute; `constraints` can be a descriptor attribute; `fields` is the field dataset. When upgrading, do not assume every snippet uses the same model or exposes the same variables.

Principles:

1. The snippet name determines which template is looked up.
2. The format ID determines the template package on the classpath.
3. Mustache variables must match keys present in the model.
4. Custom attributes must be attached at the right level: descriptor or snippet.
5. Fallbacks should exist for optional attributes.
6. Templates must use syntax compatible with the output format.

Renaming a variable in a template without checking the model can leave a column blank without necessarily failing HTTP tests. Therefore, inspecting generated snippets is a mandatory separate step.

## 4. Comparing against the target version's default templates

When upgrading versions, the best reference is the default template packaged inside the exact target Spring REST Docs artifact. Online docs explain customization concepts, but to know the exact variables and model structure of the target release, inspect the templates inside the corresponding JAR.

Workflow:

1. Download the target dependency version via the build or inspect the artifact from the Maven repository.
2. Open the JAR as a ZIP file.
3. Locate the template package by format ID, e.g., `org/springframework/restdocs/templates/asciidoctor/`.
4. Copy the default template of the exact snippet you are overriding into a temporary folder for comparison.
5. Use diff to identify changes in content, Mustache sections, and variables.
6. Bring only the necessary changes into your custom template.

You can use the `jar` command to list artifact contents:

```bash
jar tf spring-restdocs-core-<target-version>.jar
```

After finding the template file inside the JAR, read it with a ZIP tool or extract it into a temporary working directory. Do not extract over `src/test/resources`; the goal is comparison, not replacing your active templates.

### 4.1. Creating a reviewable diff

Example:

```bash
git diff --no-index \
  baseline/request-fields.snippet \
  target/request-fields.snippet
```

Where:
- `baseline` is the template packaged in the version currently in use.
- `target` is the default template in the target version.

Then compare your custom template against the target to see which override parts are still needed:

```bash
git diff --no-index \
  target/request-fields.snippet \
  src/test/resources/org/springframework/restdocs/templates/asciidoctor/request-fields.snippet
```

Read the diff semantically:
- Did the new template add or remove any variables?
- Did `{{#...}}` sections or `{{^...}}` inverted sections change?
- Were new lambdas or helpers added for escaping?
- Did the table structure change?
- Do project-added columns still keep their fallbacks?

Do not copy the entire new template into the project and wipe out existing customizations. First understand the upstream changes, then merge intentionally.

## 5. Keeping custom attributes working after an upgrade

Suppose a template uses `constraints` and `title` columns:

```java
requestFields(
    attributes(key("title").value("Order creation information")),
    fieldWithPath("email")
        .description("Notification email")
        .attributes(key("constraints").value("Valid email format"))
);
```

Template:

```adoc
{{#title}}
.{{title}}
{{/title}}
|===
|Path|Type|Description|Constraints

{{#fields}}
|{{path}}
|{{type}}
|{{description}}
|{{constraints}}

{{/fields}}
|===
```

After upgrading, verify each layer:

| Question | How to check |
| --- | --- |
| Are snippet attributes still passed? | Check `requestFields(...)` calls and title output |
| Are descriptor attributes still passed? | Check that each field has the right key |
| Does the template still read the right keys? | Compare Mustache variables |
| Does a field missing an attribute break the template? | Run a test with a descriptor lacking custom attributes |
| Do optional/ignored fields still behave properly? | Run tests with and without optional fields |
| Does the table show complete data? | Inspect generated snippets or assert on output |

In particular, custom attributes are not validation APIs. `constraints` is project-supplied content; Spring REST Docs does not run Bean Validation automatically just because a template renders that column.

### 5.1. Provide fallbacks to avoid unintended blank cells

If a field lacks `label`, the template can fall back to `path`:

```adoc
{{#fields}}
|{{#label}}{{label}}{{/label}}{{^label}}{{path}}{{/label}}
|{{path}}
|{{type}}
|{{description}}
|{{constraints}}

{{/fields}}
```

If `constraints` may be absent, you can display `—` by supplying a default value when building the model/descriptor or using a tested template convention. Do not rely on how Mustache renders `null` without verifying the actual renderer's output.

## 6. Upgrading custom snippets that use `TemplatedSnippet`

Custom snippets usually depend on the `TemplatedSnippet` API and the operation model. Areas to review:

- Snippet constructors and how `snippetName`, `templateName`, and attributes are passed.
- Return type and visibility of `createModel(Operation)`.
- Methods on `Operation`, `OperationRequest`, `OperationResponse`, and `OperationRequestPart` called by the snippet.
- Data types of status, URI, headers, content, and parts.
- Template loading and output writing mechanisms.
- Exceptions thrown when the model lacks required data.

Example custom snippet:

```java
public class OperationSummarySnippet extends TemplatedSnippet {

    public OperationSummarySnippet() {
        super("operation-summary", "operation-summary", Map.of());
    }

    @Override
    protected Map<String, Object> createModel(Operation operation) {
        Map<String, Object> model = new LinkedHashMap<>();
        model.put("operationName", operation.getName());
        model.put("method", operation.getRequest().getMethod().name());
        model.put("uri", operation.getRequest().getUri().toString());
        model.put("status", operation.getResponse().getStatus().value());
        return model;
    }
}
```

When upgrading versions:
1. Compile the custom snippet against the target API.
2. Check imports and method signatures against the target version's Javadoc/artifact.
3. Handle missing headers or empty parts collections.
4. Verify the template is still resolved under the right format.
5. Run tests to verify output files and contents.

If an API was deprecated in the source version, do not merely suppress warnings. Check the replacement and removal timeline in the release notes. If an API was removed in a major version, update code to the replacement API before upgrading the full build.

## 7. Major changes to check when crossing major versions

A major version can change Java, Spring Framework, test framework, and rendering tool baselines. For example, the official Spring REST Docs 4.0.0 release announcement notes foundational changes such as removing deprecated APIs, dropping JUnit 4 support, and raising minimum baseline dependency requirements. This is why reading release notes is essential instead of assuming upgrades only affect templates.

Checklist for a major upgrade:

- Read release notes for every intermediate major/minor release, not just the final target.
- Check minimum Java and Spring Framework versions.
- Check JUnit version and extension configuration.
- Check AsciidoctorJ, Gradle plugin, and template formats.
- Check REST Assured version if using that module.
- Search for deprecated/removed APIs in custom snippets and test utilities.
- Build a representative test for each integration module in use.
- Inspect the output of every overridden snippet.
- Verify Asciidoctor documentation after including snippets.

Do not upgrade multiple major libraries simultaneously without a clear verification matrix. Whenever possible, upgrade dependency groups incrementally and record results so regressions are easy to isolate.

## 8. Regression testing for templates

A passing build only proves Java/templates processed at a basic level; it does not guarantee output preserves expected content. Maintain representative documentation tests covering these cases:

| Case | What to verify |
| --- | --- |
| Standard request fields | Path, type, and description |
| Standard response fields | Response fields and column order |
| Custom title | Title renders properly |
| Custom label | Label displays while technical path is preserved |
| Constraint/example | Extra columns receive the right values |
| Descriptor without custom attributes | Fallback does not break the table |
| Optional field | Snippet generates when field is absent |
| Ignored field | Field is checked without producing a row |
| Nested fields/arrays | Paths `a.b` and `items[]` display accurately |
| Special characters | `|`, brackets, and line breaks do not break the table |
| HTTP request/response | Method, URI, status, and headers are not lost |
| Markdown format | Template uses right format ID and renderer understands table |

### 8.1. Checking generated snippet contents

You can write tests that read output files after documenting an operation:

```java
Path snippet = snippetsDir
        .resolve("orders-create")
        .resolve("request-fields.adoc");

String generated = Files.readString(snippet);

assertThat(generated)
        .contains("Order creation fields")
        .contains("customerId")
        .contains("Positive integer");
```

This is an AssertJ example; your project's test configuration must resolve `snippetsDir` accurately and ensure assertions execute after Spring REST Docs writes the file.

Prefer asserting on contract-meaningful content. If you assert on exact whitespace, spacing, or line wrapping, minor formatting tweaks can trigger noisy, low-value test failures. If output is a public artifact requiring strict stability, you can use golden files, provided golden files and templates are reviewed and updated together intentionally.

### 8.2. Comparing output before and after upgrade

Generate two output sets from the same commit and same fixtures:
- `snippets-before`: generated with the source version.
- `snippets-after`: generated with the target version and updated templates.

Compare by operation and snippet name. Classify diffs:
1. **Intentional changes:** new template adds a column or updates a title.
2. **Upstream changes:** default formatting or model changed.
3. **Regressions:** missing fields, blank values, wrong titles, lost paths.
4. **HTTP contract changes:** request/response actually changed due to application code.

Do not bundle all four categories into a single golden-file update without explanation. Reviewers need to see what changed because of the API versus what changed because of the renderer.

## 9. Testing each template format separately

If the project supports both Asciidoctor and Markdown, each format has its own template package:

```text
src/test/resources/org/springframework/restdocs/templates/
├── asciidoctor/
│   ├── request-fields.snippet
│   └── response-fields.snippet
└── markdown/
    ├── request-fields.snippet
    └── response-fields.snippet
```

Markdown configuration on MockMvc looks like:

```java
this.mockMvc = MockMvcBuilders.webAppContextSetup(this.context)
    .apply(documentationConfiguration(this.restDocumentation)
        .snippets()
        .withTemplateFormat(TemplateFormats.markdown()))
    .build();
```

Verify:
- Which format the tests are actually using.
- Templates are loaded from the right package.
- Output extensions are right, e.g., `.adoc` or `.md`.
- Table syntax matches the target renderer.
- Asciidoctor-specific helper lambdas are not mistakenly used in Markdown.
- The Markdown include pipeline has its own include processor, because Markdown lacks a standard include directive like Asciidoctor.

A working Asciidoctor template set does not prove the Markdown set is also compatible.

## 10. Dependencies and build configuration

Upgrading the Spring REST Docs version usually requires updating test modules and documentation plugins together.

Gradle declaration example:

```groovy
dependencies {
    testImplementation "org.springframework.restdocs:spring-restdocs-mockmvc:${restdocsVersion}"
    // Or use spring-restdocs-webtestclient when the project uses WebTestClient.
    // Only add spring-restdocs-restassured if the project actually uses REST Assured.
}
```

If the project uses a version catalog or Spring dependency management, update versions at the central version source instead of hard-coding each dependency.

Inspect the dependency graph to detect:
- Two versions of Spring REST Docs being pulled simultaneously.
- An integration module at a different version from core.
- Spring Framework being overridden by an incompatible version.
- Old JUnit or REST Assured versions still pulled in from test utilities.
- AsciidoctorJ/plugins not meeting the target release's baseline.

Do not bump dependencies to the latest version arbitrarily. Pick a target version verified alongside your application's Spring Boot/Spring Framework and build tool versions.

## 11. Common errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Custom template is not used | Wrong format ID package, wrong template name, or resource missing from test classpath | Check the path and snippet name |
| Build passes but custom column is blank | Mustache variable missing from model | Compare target default template and attributes |
| Title disappeared after upgrade | Snippet attribute not passed or template does not read `title` | Check overloads and model output |
| Custom snippet fails to compile | API or method signature changed | Read Javadoc/release notes and update code |
| Table is misaligned | Header/row cell counts mismatch or escaping changed | Render snippet and check with target renderer |
| `request-fields` is right but `response-fields` is wrong | Only one of the two templates was upgraded | Update and test both templates |
| Markdown does not use new template | Format ID is not `markdown` or tests did not configure format | Check `TemplateFormats.markdown()` |
| Asciidoctor cannot include snippet | Build task ran before tests or wrong output path | Declare task dependency and snippets input |
| Snippet diff is too large | Formatting changes mixed with API changes | Classify diffs by template, operation, and contract |
| Test assertions break on whitespace | Assertions lock down brittle presentation details | Assert meaningful fields/values or use reviewed golden files |
| Major build upgrade missing JUnit/API | Baseline changed | Check version requirements and update test framework |

## 12. Recommended upgrade workflow

You can apply this step-by-step sequence:

```text
Record source and target versions
              |
              v
Read release notes + system requirements
              |
              v
Check dependency/module compatibility
              |
              v
Extract default templates of target version
              |
              v
Diff against current override templates
              |
              v
Update custom templates and custom snippets
              |
              v
Run documentation tests + output assertions
              |
              v
Compare before/after snippets
              |
              v
Compile Asciidoctor/Markdown
              |
              v
Review diff and merge upgrade
```

At each step, record verification results so the pull request can explain:
- Which versions changed.
- Which templates were edited.
- Which custom attributes or APIs were updated.
- Which snippets produced diffs.
- Why those diffs are acceptable.

## 13. Build and CI

A basic Gradle pipeline must ensure snippet-generating tests run before Asciidoctor:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
}
```

If the pipeline saves pre-/post-upgrade snapshots, you can store snippet outputs as CI artifacts for reviewers to download and compare. Do not leave stale snapshot files inside the generated directory that tests overwrite.

Stages should include:
1. Compile tests and custom snippets.
2. Run documentation tests for each integration module.
3. Assert that critical snippets are generated with expected content.
4. Build Asciidoctor or Markdown output.
5. Verify no includes are missing.
6. Archive snippet diffs/artifacts if this is a version-upgrade pull request.

Example upgrade acceptance criteria:
- No remaining compile errors from removed/old APIs.
- All critical operations generate snippets.
- No loss of path/type/description or custom attributes.
- All supported formats render cleanly.
- Output changes are reviewed and categorized.
- Documentation build runs independently and reproducibly.

## 14. Hands-on exercises

Suppose a project has custom `request-fields.snippet` and `response-fields.snippet` templates:

1. Record the current Spring REST Docs version and choose a target version from release notes.
2. Identify active integration modules and current Spring Framework, JUnit, and AsciidoctorJ versions.
3. Extract the default `request-fields.snippet` template from both source and target artifacts.
4. Use diff to find changes in Mustache variables and table structure.
5. Update the request template while preserving custom `label`, `constraints`, and `title`.
6. Repeat for `response-fields.snippet`; confirm the example column is not lost.
7. Compile your custom `TemplatedSnippet` and update any deprecated/removed APIs.
8. Run representative tests with labels, without labels, with optional fields, and with nested fields.
9. Generate snippets in both Asciidoctor and Markdown if the project supports both formats.
10. Compare before/after output; categorize diffs into formatting, upstream, and API contract changes.
11. Build documentation in CI and review the artifact.
12. Document notable changes to watch for during the next upgrade.

### Self-check questions

- Why do custom templates depend on the Spring REST Docs version?
- Which factors determine how a template is resolved?
- What is the most reliable source for checking Mustache variables of a target version?
- Why is a passing build alone not enough to conclude templates are compatible?
- Where should descriptor attributes and snippet attributes be checked?
- Which API areas should a custom `TemplatedSnippet` review?
- Why must Asciidoctor and Markdown be tested separately?
- How do you separate formatting diffs from API contract diffs?
- When upload limits or error snippets change, how do you confirm the change is intentional?
- Which conditions should CI verify before accepting an upgrade?

**Key takeaway:** Keep templates compatible by treating them as a version-dependent interface. Compare against default templates in the target artifact, review Mustache variables and custom attributes, update custom snippets to newer APIs, then run tests and compare output per format. A passing build is only part of the check; reviewers need to see that snippets remain complete, accurate, and preserve custom content.

## References

- [Spring REST Docs — Customizing the Output](https://docs.spring.io/spring-restdocs/how-to/customizing-the-output.html): Mustache templates, classpath, and attributes.
- [Spring REST Docs — Snippet Template Format](https://docs.spring.io/spring-restdocs/reference/configuration/snippet-template-format.html): Asciidoctor/Markdown and selecting template format.
- [Spring REST Docs — System Requirements](https://docs.spring.io/spring-restdocs/reference/index.html): baseline version requirements of Spring REST Docs.
- [Spring REST Docs 4.0.0 Release](https://spring.io/blog/2025/11/18/spring-restdocs-4-0-0): major version changes and dependency baselines.
- [Spring REST Docs 4.0.1 Release](https://spring.io/blog/2026/06/09/spring-restdocs-4/): bug fixes and dependency upgrades in 4.0.1.
