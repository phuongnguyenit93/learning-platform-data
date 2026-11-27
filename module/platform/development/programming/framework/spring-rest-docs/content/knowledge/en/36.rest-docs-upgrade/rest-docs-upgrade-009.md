# Handling Snippet Format Changes

## 1. Why Can Snippet Formats Change After an Upgrade?

Spring REST Docs generates snippets from HTTP tests. Content is produced from operations, field descriptors, attributes, and Mustache templates. When upgrading Spring REST Docs, Spring Framework, AsciidoctorJ, or custom templates, output can differ even when the HTTP contract has not changed.

Common differences include:
- Snippet file names or extensions change because a different format is configured.
- Field tables have different columns, ordering, or headers.
- Special character escaping in AsciiDoc/Markdown changes.
- HTTP request/response snippets display headers, URIs, or bodies differently.
- Custom templates use Mustache variables no longer supplied in the same way.
- Snippet files are unchanged, yet Asciidoctor or the Markdown renderer produces different HTML.

In **SPRING_REST_DOCS**, HTTP tests using MockMvc, WebTestClient, or REST Assured establish evidence for requests, responses, payloads, parameters, and headers. Snippets are compiled using Asciidoctor/Markdown and integrated into the build/CI. This lesson belongs to the **Upgrade** chapter and explains how to diagnose and handle formatting changes so library upgrades do not accidentally mask API changes or corrupt documentation.

After this lesson, you will be able to distinguish contract drift from rendering changes, establish a baseline, compare snippets per operation, inspect default templates in the target version, update Mustache variables, and verify output in CI.

## 2. The Three Layers Producing Output

| Layer | Components | What It Determines |
| --- | --- | --- |
| HTTP exchange | Request/response captured by tests | Method, URI, status, headers, payload, bytes |
| Snippet generation | REST Docs descriptors, operation model, Mustache templates | Which snippets are generated, data, and structure |
| Document rendering | Asciidoctor, Markdown builder, CSS/theme | Final HTML/PDF and visual presentation |

If `response-fields.adoc` keeps the same paths while column headers change, the cause typically lies in templates/snippet generation. If `.adoc` files are unchanged while HTML changes, check AsciidoctorJ, extensions, themes, or CSS. If the actual JSON response changes, that may be a contract change.

Do not start by updating snapshots before identifying which layer produced the difference.

## 3. Distinguishing Format Changes from Contract Changes

| Symptom | Possible Change Type | How to Verify |
| --- | --- | --- |
| Different whitespace or line wrapping | Rendering | Compare meaningful content |
| Different table headers/columns | Template | Diff template and generated snippet |
| Added or missing field path | Contract or descriptor | Check actual JSON and strict descriptors |
| Different HTTP status | Application behavior/contract | Check status assertions and response |
| Header appeared/disappeared | HTTP exchange or preprocessor | Inspect operation and preprocessors |
| File extension changed | Format configuration | Check format ID and output naming |
| AsciiDoc include not found | Build path/task dependency | Check snippets directory and include paths |
| HTML differs while snippets match | Renderer/theme | Check Asciidoctor and CSS |

Do not assume every diff is formatting. A disappearing response field can be a breaking change; a new undocumented field can be payload drift. Inspect the operation data before classifying.

## 4. Establishing a Baseline Before Upgrading

Before changing dependencies or templates, establish a reproducible baseline:

1. Check out the exact currently released commit.
2. Use the exact current JDK, dependencies, and build tool.
3. Run the same documentation tests and fixtures.
4. Save the entire `build/generated-snippets` folder as a baseline artifact.
5. Build Asciidoctor/Markdown and save the final output if rendering checks are needed.
6. Record the commit SHA, Spring REST Docs version, format ID, and renderer version.

The artifact structure might look like this:

```text
docs-baseline/
├── metadata.txt
├── generated-snippets/
│   ├── products-get/
│   └── products-create/
└── rendered-site/
```

You do not necessarily need to commit generated snippets into the source repository if the project lacks that policy. You can store retrievable CI artifacts or release artifacts. The baseline must use the same fixtures; if fixtures change alongside the library, diffs become hard to diagnose.

## 5. Comparing Output Layer by Layer

### 5.1. Comparing the HTTP Exchange

Confirm tests still send the same requests and receive the same responses:
- HTTP method and URI.
- Request/response status.
- Content-Type and meaningful headers.
- Request/response JSON fields.
- Query/path parameters and multipart parts.

Assertions such as `status().isOk()`, `jsonPath(...)`, `requestFields(...)`, and `responseFields(...)` keep contracts explicit. If fixtures or endpoints changed, note them separately before evaluating formatting.

### 5.2. Comparing Generated Snippets

After running tests on the target version, compare each operation directory:

```text
products-get/
  http-request.adoc
  http-response.adoc
  response-fields.adoc
```

Use diff to inspect changes:

```bash
git diff --no-index baseline/products-get target/products-get
```

Read the diff semantically:
- Did any field or header disappear?
- Did paths and types stay the same?
- Are differences limited to titles, table borders, or whitespace?
- Do placeholders/redactions still work?
- Are custom attributes rendered?

### 5.3. Comparing Rendered Documents

If snippets are identical while HTML pages differ, check:
- AsciidoctorJ and plugin versions.
- Asciidoctor extensions and attributes.
- Themes, stylesheets, fonts, and assets.
- Include structure and toc configuration.
- Markdown processor version.

Do not alter REST Docs templates to compensate for CSS or renderer changes if the source snippets have no issues.

## 6. Inspecting Default Templates of the Target Version

Custom templates are the most fragile area during an upgrade. The authoritative reference is the default template inside the target Spring REST Docs artifact.

Workflow:
1. Identify the target REST Docs version and format ID, e.g. `asciidoctor`.
2. Download the exact-version `spring-restdocs-core` artifact through your build.
3. List the JAR contents and locate package `org/springframework/restdocs/templates/<format-id>/`.
4. Extract the default template for the snippet you override into a temp directory.
5. Diff the old default template against the target default template.
6. Diff your custom template against the new default template.
7. Merge necessary updates while preserving intentional customizations.

Example listing a JAR:

```bash
jar tf spring-restdocs-core-<target-version>.jar
```

Comparing templates:

```bash
git diff --no-index baseline/request-fields.snippet target/request-fields.snippet
```

Do not copy the entire new template into your source and delete customizations. First identify which Mustache variables, lambdas, sections, or model structures changed upstream.

## 7. Checking Mustache Variables and Attributes

Suppose a custom template contains:

```adoc
{{#title}}
.{{title}}
{{/title}}
|===
|Field Name|Path|Type|Description|Constraints

{{#fields}}
|{{#label}}{{label}}{{/label}}{{^label}}{{path}}{{/label}}
|{{path}}
|{{type}}
|{{description}}
|{{constraints}}

{{/fields}}
|===
```

Variables can come from multiple sources:
- `fields`, `path`, `type`, `description`: the fields snippet model.
- `title`: snippet attribute passed into the `requestFields(...)` call.
- `label`, `constraints`: attributes attached to each `FieldDescriptor`.

When upgrading:
- Cross-check default templates to confirm model variable names.
- Verify custom keys are still attached in tests.
- Keep fallbacks when `label` or `constraints` are absent.
- Check both request and response templates; they are independent snippets.
- Verify escaping lambdas are only used in formats that support them.

A template can render without throwing errors while printing blank cells if a variable is no longer provided. Add assertions on generated output content rather than relying solely on tests not throwing exceptions.

## 8. Verifying Format ID and File Extensions

Spring REST Docs selects templates by format ID. For example:

```text
src/test/resources/org/springframework/restdocs/templates/
├── asciidoctor/
│   ├── request-fields.snippet
│   └── response-fields.snippet
└── markdown/
    ├── request-fields.snippet
    └── response-fields.snippet
```

If tests switch from Asciidoctor to Markdown while templates remain under the `asciidoctor` package, custom templates may not be picked up. Output file extensions also reflect the configured format.

Check format configuration wherever MockMvc/WebTestClient/REST Assured documentation is configured. MockMvc example:

```java
.apply(documentationConfiguration(restDocumentation)
    .snippets()
    .withTemplateFormat(TemplateFormats.markdown()))
```

The exact API must match your dependency version. Do not simply rename output files via script to simulate Markdown; select the corresponding template format and use a proper renderer.

## 9. Checking Escaping and Table Content

Mustache or renderer changes can affect:
- Pipe `|` characters inside AsciiDoc/Markdown tables.
- Curly braces, backticks, and inline code.
- Multiline line breaks inside descriptions.
- Unicode and Vietnamese characters.
- HTML or characters requiring escaping.

Default Asciidoctor templates may use helpers such as `tableCellContent` to handle pipes in cells. If overriding templates, inspect helpers in the target version and apply them to custom attributes that may contain similar content.

Descriptor example:

```java
fieldWithPath("description")
    .description("Label A | label B; supports Vietnamese");
```

After generating snippets, confirm tables retain the right column count and content is not split incorrectly. For Markdown, verify with the project's processor; table and escaping syntax can differ from AsciiDoc.

## 10. Keeping Output Deterministic and Avoiding Noisy Diffs

Generated snippets are often reviewed in pull requests. To keep diffs readable:
- Use deterministic fixtures; avoid random timestamps or UUIDs in primary examples.
- Do not embed build times in individual snippets unnecessarily.
- Standardize test locale/timezone.
- Use stable data ordering when output depends on collections.
- Keep operation IDs consistent.
- Separate template changes from API contract changes in pull requests whenever possible.

You do not have to lock every single byte with snapshot tests. You can assert critical contract values; reserve golden files for artifacts needing strict stability and review every update.

## 11. Writing Regression Tests for Snippet Formats

| Case | Assertion |
| --- | --- |
| Request fields | Critical paths, types, and descriptions still appear |
| Response fields | Public fields do not disappear |
| Custom title | Title is rendered |
| Custom attributes | Label/constraints/example are not lost |
| Absent attribute | Fallback displays properly |
| Nested/array fields | Nested paths and array elements are accurate |
| Special characters | Tables do not break |
| Redaction | Tokens and cookies do not appear |
| Asciidoctor format | Extensions and syntax are valid |
| Markdown format | Templates in right package and output renders |

Assertion example:

```java
String generated = Files.readString(
    snippetsDir.resolve("products-get/response-fields.adoc")
);

assertThat(generated)
    .contains("Product ID")
    .contains("name")
    .contains("Product name");
```

Assert meaningful content rather than locking all whitespace when formats may evolve. For golden files, every update must be reviewed and explained.

## 12. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Snippet missing column after upgrade | Mustache variable removed from model or attribute not passed | Compare against default template and descriptor attributes |
| Custom template not loaded | Wrong format ID or snippet file name | Check classpath and `TemplateFormats` |
| Table breaks on pipe character | Escape/helper no longer invoked | Check `tableCellContent` and renderer |
| Output extension changed | Format configuration changed | Explicitly choose format and update include paths |
| Snippets identical, HTML differs | Asciidoctor/theme/CSS changed | Inspect renderer separately |
| Field disappeared | Contract or descriptor changed | Check actual payload and strict descriptors |
| Whole-file diff is huge | Formatting change mixed with contract change | Classify diffs and split pull requests |
| Request template right, response wrong | Updated only one template | Check both sides |
| Markdown renders poorly | Used Asciidoctor-specific helpers/syntax | Use Markdown templates and processor |
| Build passes with empty table cells | No assertions on generated content | Add snippet regression tests |

## 13. Asciidoctor and Build/CI

AsciiDoc files include generated snippets:

```adoc
= Product API
:toc: left

== Get Product

=== Request
include::{snippets}/products-get/http-request.adoc[]

=== Response
include::{snippets}/products-get/http-response.adoc[]

=== Response fields
include::{snippets}/products-get/response-fields.adoc[]
```

With Gradle and the Asciidoctor plugin configured:

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

Upgrade pipeline:

```text
Checkout source + lock dependency versions
                |
                v
Run documentation tests
                |
                v
Generate snippets
                |
                v
Compare contract assertions and snippet output
                |
                v
Build Asciidoctor / Markdown
                |
                v
Review diff + publish artifact
```

Store baseline and new outputs as artifacts for reviewers to compare. When diffs appear, classify them as contract, template, or renderer before accepting. Never automatically update golden files just because a new build produced different output.

## 14. Hands-On Exercise

Assume a project is upgrading Spring REST Docs and uses custom templates:

1. Run tests on the current version and save baseline snippets.
2. Upgrade dependencies on a separate branch and re-run the same tests/fixtures.
3. Compare HTTP status, headers, and payload assertions to verify contracts.
4. Diff generated snippets per operation.
5. Extract default templates from the target artifact and compare against overrides.
6. Check Mustache variables, `title`, `label`, `constraints`, and fallbacks.
7. Check format ID, file extensions, and include paths.
8. Add a description containing pipes and Unicode; confirm tables do not break.
9. Build HTML with the exact-version Asciidoctor/Markdown processor.
10. Classify diffs, update regression assertions, and review artifacts in CI.

### Self-Evaluation Questions

- Which three layers participate in producing documentation from HTTP tests to HTML?
- How do you distinguish contract drift from a rendering change?
- Why must the baseline be generated from the exact same fixtures?
- Which source confirms Mustache variables for the target version?
- How does the format ID affect template lookup and file extensions?
- Why can a snippet render without errors while a column remains blank?
- When should you inspect Asciidoctor instead of editing REST Docs templates?
- Should you lock the entire output or only critical contract values?
- Which artifacts should CI store and verify for a safe upgrade?

**Key Takeaway:** When snippets change after an upgrade, determine whether the difference lies in the HTTP exchange, snippet generation, or document renderer. Establish a baseline, compare output per operation, inspect default templates in the target version, and verify both requests and responses. Only accept diffs after classifying them and confirming contracts were not altered unintentionally.

## References

- [Spring REST Docs — Customizing the Output](https://docs.spring.io/spring-restdocs/how-to/customizing-the-output.html): Mustache templates and custom attributes.
- [Spring REST Docs — Snippet Template Format](https://docs.spring.io/spring-restdocs/reference/configuration/snippet-template-format.html): format IDs and template resolution.
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): field descriptors and payload snippets.
- [Spring REST Docs — Working with Asciidoctor](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/working-with-asciidoctor.html): includes and documentation rendering.
