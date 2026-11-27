# Flow from Test to Snippet, Asciidoctor, or Markdown

Spring REST Docs organizes API documentation generation into a reproducible flow: **an HTTP test executes a request, verifies the response, records the operation, generates snippets, and then compiles those snippets with explanations into complete documentation**. Each step has its own inputs and outputs. When wired in the right order, HTTP examples and description tables trace back to a test; when a step is skipped or stale output is used, a page can look complete while failing to reflect current source code.

This lesson belongs to the **Documentation Model** chapter of the `SPRING_REST_DOCS` module. The module practices building verifiable REST API documentation with Spring REST Docs via **MockMvc**, **WebTestClient**, or **REST Assured**; generating snippets for requests, responses, payloads, parameters, and headers; and then compiling **Asciidoctor/Markdown** and integrating with build and CI. This lesson walks end-to-end through the full chain from test to documentation page, highlighting the role of each step, dependency configuration, and common integration errors.

## 1. Learning Objectives

After this lesson, you can:

1. Describe the inputs and outputs of each step: HTTP test, assertions, descriptors, snippets, source pages, and rendered documentation.
2. Write an operation test using Spring REST Docs to generate snippets from requests and responses.
3. Configure the output directory and identifier so source documentation locates the exact snippets.
4. Compile documentation with Asciidoctor using includes, or organize an appropriate Markdown generation pipeline.
5. Set up task dependencies so tests run before rendering and stale outputs never mask errors.
6. Diagnose errors from test requests through output files and includes in documentation pages.
7. Distinguish what is verified automatically from what still requires content review.

## 2. Big-Picture View of the Processing Flow

A Spring REST Docs workflow can be represented as follows:

```text
Source code + tests + descriptors + documentation sources
                     │
                     ▼
               Compile tests
                     │
                     ▼
              Run HTTP tests
                     │
          ┌──────────┴───────────┐
          ▼                      ▼
     Assertions            Request/response
 status, headers, JSON         recorded
          │                      │
          └──────────┬───────────┘
                     ▼
             document(identifier)
                     │
                     ▼
             generated-snippets/
                     │
             ┌───────┴────────┐
             ▼                ▼
       Asciidoctor       Markdown Pipeline
       include adoc      convert/inject snippets
             │                │
             └───────┬────────┘
                     ▼
             HTML / PDF / site
                     │
                     ▼
             Verify and publish
```

This chain can be divided into six steps:

| Step | Input | Output | Questions to verify |
| --- | --- | --- | --- |
| 1. Prepare test | Fixtures, app config, expected request | Deterministic test environment | Which components does the test run through? |
| 2. Send request and receive response | MockMvc, WebTestClient, or REST Assured | Actual HTTP interaction in test | Do request and response match the scenario? |
| 3. Assertions and descriptors | HTTP result and contract rules | Behavior checks and structure descriptions | What is protected by assertions? |
| 4. Generate snippets | Recorded operation and descriptors | Snippet directory by identifier | Which files were created and where? |
| 5. Compile documentation | Snippets, AsciiDoc/Markdown, hand-written prose | HTML/PDF/site or Markdown pages | Are includes valid and does prose provide enough context? |
| 6. Build and CI | Sources, tests, task config | Reproducible artifacts | Does a clean build run tests before rendering? |

**Not every step is performed automatically by Spring REST Docs.** The library integrates recording operations and generating snippets. Developers still must write tests, assertions, descriptors, documentation sources, and proper build configuration.

## 3. Step 1 — Prepare Repeatable HTTP Tests

To obtain reliable snippets, you first need a clear and repeatable HTTP call. The test must control input data, application state, configuration, and dependencies that affect the response.

Product-lookup API example:

- `GET /api/products/{productId}` returns details when the product exists.
- Product `7` is a prepared fixture named `Notebook` with price `45000`.
- If the ID does not exist, the endpoint returns `404` per the example contract.

A fixture can be set up inside the test or via a test repository. What matters is that the outcome does not depend on whether another test ran earlier or on random environment data.

### 3.1. Choosing Test Scope

Spring REST Docs supports different testing approaches:

| Tool | Typical scope | What to decide |
| --- | --- | --- |
| MockMvc standalone | Controller and MVC configuration constructed inside the test | Do filters, converters, controller advice, or security need to be added? |
| MockMvc with application context | Spring MVC stack backed by the test context | Does the context represent all relevant configurations sufficiently? |
| WebTestClient | WebFlux or MVC, bound in-memory or connected to a server | Is the test binding directly to the app or sending HTTP over a server? |
| REST Assured | Typically calls a running server; also supports mock MVC/WebTestClient via suitable modules | Does the test cover the right HTTP layer, fixtures, and server lifecycle? |

Test scope determines what can be claimed. MockMvc standalone can prove that the constructed controller returned a response in that setup; it does not automatically test the database, production security, or networking. When you need to prove those components, choose the appropriate test type and describe the scope accurately.

### 3.2. Test Data Must Be Safe and Stable

Use dummy fixtures, fixed IDs when appropriate, controllable timestamps, and isolated data per test. Never put real tokens, passwords, session cookies, or personal data in requests/responses that will be emitted to snippets. If a response contains dynamic values, explicitly decide whether to normalize them with a preprocessor before publishing.

## 4. Step 2 — Send Requests and Receive Responses with a Test Client

Test clients differ in how they issue requests, yet the overall flow is the same:

```text
Test setup
   │
   ▼
HTTP request
   │
   ▼
Application under test
   │
   ▼
HTTP response
   │
   ├── status
   ├── headers
   └── body
```

### 4.1. MockMvc

MockMvc tests Spring MVC without starting a real HTTP server. Example product-lookup request:

```java
mockMvc.perform(
        get("/api/products/{productId}", 7L)
            .accept(MediaType.APPLICATION_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").value(7));
```

For Spring REST Docs to extract path parameters from the URI template, use Spring REST Docs' corresponding request builder:

```java
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
```

When the request is `GET /api/products/{productId}`, the URI template lets `pathParameters(...)` identify the `productId` variable. Using a builder that does not preserve templates may keep path parameter documentation from working as intended.

### 4.2. WebTestClient

WebTestClient can bind to a WebFlux/MVC app in tests or connect to a running server, depending on setup. Spring REST Docs integrates via the corresponding WebTestClient configuration, for example:

```java
client
    .get()
    .uri("/api/products/{id}", 7L)
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("products-get-success"));
```

This snippet illustrates where to invoke snippet generation after verifying the response; to use it in a project, configure WebTestClient with Spring REST Docs' filter/documentation configuration and import the matching extension/API. Exact syntax depends on the Spring REST Docs version and how the test client is bound. Always verify the test client is configured with the documentation recorder, rather than calling `consumeWith(document(...))` in isolation.

### 4.3. REST Assured

With REST Assured, tests typically describe requests and responses fluently:

```java
given()
    .accept("application/json")
.when()
    .get("/api/products/{id}", 7)
.then()
    .statusCode(200);
```

To generate snippets, use the Spring REST Docs integration for REST Assured (such as the REST Docs filter) and attach the filter to the request specification. The specific integration differs from MockMvc; you cannot simply swap the request builder name while keeping MockMvc configuration.

**Principle:** the test client sends the request, receives the response, and is configured to record the operation; assertions verify the result; only then does Spring REST Docs have the data needed to generate snippets.

## 5. Step 3 — Combine Assertions and Descriptors

A well-written documentation test has at least two responsibilities: verifying important behavior and describing the elements that will appear in documentation.

Example assertions:

```java
.andExpect(status().isOk())
.andExpect(jsonPath("$.id").value(7))
.andExpect(jsonPath("$.name").value("Notebook"))
.andExpect(jsonPath("$.price").value(45000))
```

Descriptor section:

```java
.andDo(document("products-get-success",
    pathParameters(
        parameterWithName("productId")
            .description("ID of the product to look up")
    ),
    responseFields(
        fieldWithPath("id")
            .type(JsonFieldType.NUMBER)
            .description("Product ID"),
        fieldWithPath("name")
            .type(JsonFieldType.STRING)
            .description("Display name"),
        fieldWithPath("price")
            .type(JsonFieldType.NUMBER)
            .description("Product price")
    )
));
```

The two parts verify different things:

| Mechanism | Checks | Does not automatically check |
| --- | --- | --- |
| `status().isOk()` | HTTP status of this run | All possible statuses |
| `jsonPath("$.price").value(45000)` | Fixture's price value | Pricing formula across all products |
| `responseFields(...)` | Documented field structure and payload match per documentation mode | All business rules of each field |
| `pathParameters(...)` | Descriptions of path variables sent | Full business semantics of product IDs |

In strict documentation mode, payload descriptors typically catch undocumented fields or missing required fields. `optional()` is for fields that can genuinely be absent; `relaxedResponseFields(...)` allows partial documentation. Do not use either just to silence a failing test.

### 5.1. Create Separate Operations for Different Scenarios

The same route can return `200` and `404`. Create separate tests and identifiers:

```java
document("products-get-success", ...);
document("products-get-not-found", ...);
```

Never share one identifier if request/response content differs. Otherwise, tests can overwrite the same snippet files and the documentation page can no longer identify which scenario an example belongs to.

## 6. Step 4 — Generate Snippets into the Output Directory

Each `document("identifier", ...)` call writes snippets to a directory named after the identifier under the configured output directory.

Example:

```text
build/generated-snippets/
├── products-get-success/
│   ├── http-request.adoc
│   ├── http-response.adoc
│   ├── curl-request.adoc
│   ├── httpie-request.adoc
│   ├── path-parameters.adoc
│   └── response-fields.adoc
└── products-get-not-found/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── curl-request.adoc
    └── path-parameters.adoc
```

The list above illustrates commonly generated snippets; exact files depend on configuration and requested descriptors. A `GET` without a body does not need a request fields table. If the test does not declare response field descriptors, do not assume `response-fields.adoc` was created.

### 6.1. What Does Each Snippet Represent?

| Snippet | Source | Purpose |
| --- | --- | --- |
| `http-request.adoc` | Recorded request | Displays method, URI, headers, and body |
| `http-response.adoc` | Recorded response | Displays status, headers, and body |
| `curl-request.adoc` | Recorded request | Provides a sample cURL command |
| `path-parameters.adoc` | `pathParameters(...)` | Documents path variables |
| `query-parameters.adoc` | `queryParameters(...)` | Documents query string parameters |
| `request-headers.adoc` | `requestHeaders(...)` | Documents incoming headers |
| `response-headers.adoc` | `responseHeaders(...)` | Documents outgoing headers |
| `request-fields.adoc` | `requestFields(...)` | Documents incoming payload |
| `response-fields.adoc` | `responseFields(...)` | Documents outgoing payload |

A snippet is a **documentation fragment**, not a complete API page. It does not explain by itself why clients should call the endpoint or how to handle errors.

### 6.2. Formatting and Normalizing Snippets

Spring REST Docs supports preprocessors like `preprocessRequest(prettyPrint())` and `preprocessResponse(prettyPrint())` to make examples readable. You can normalize hostnames or replace dynamic values when needed. Still:

- Assertions must check the real response according to the test's goal.
- Preprocessors only change the presentation written to snippets.
- Never mask statuses, fields, or data types that need verification.
- Verify final outputs contain no tokens, cookies, personal data, or internal addresses.

## 7. Step 5A — Compile Asciidoctor Using Includes

Asciidoctor has an `include::...[]` directive to insert snippets into documentation at compile time. Example `products.adoc` file:

```asciidoc
[[products-get]]
=== Look up a product

Use this endpoint to read information about a product
by its identifier. If the ID does not exist, the API returns HTTP 404.

==== Request

include::{snippets}/products-get-success/http-request.adoc[]

==== Path parameters

include::{snippets}/products-get-success/path-parameters.adoc[]

==== Successful response

include::{snippets}/products-get-success/http-response.adoc[]

==== Response fields

include::{snippets}/products-get-success/response-fields.adoc[]

==== Not found

include::{snippets}/products-get-not-found/http-response.adoc[]
```

In this example:

- `{snippets}` is an attribute pointing to the output directory.
- `products-get-success` is the identifier used in the test.
- `http-request.adoc` is the name of the snippet to insert.

Asciidoctor reads these files when rendering the page. If an identifier or file does not exist, the include cannot be resolved; the build configuration should ensure this failure is caught in CI.

### 7.1. Assembling Large Documentation Pages

An entry-point file can organize multiple sections:

```asciidoc
= API Reference
:toc: left
:toclevels: 3

include::introduction.adoc[]

include::products.adoc[]

include::orders.adoc[]

include::errors.adoc[]
```

Within that structure, `products.adoc` includes snippets of product operations. There are two levels of composition:

1. Composing resource pages into the overall document.
2. Composing test snippets into each resource page.

This two-tier structure lets business explanations be managed as documentation sources while HTTP examples and field tables are generated from tests.

## 8. Step 5B — Organizing a Markdown Generation Pipeline

The `include::{snippets}/...[]` syntax is an Asciidoctor directive, **not a built-in Markdown feature**. If you choose Markdown as the target format, you need an explicit mechanism to bring snippets into Markdown content.

Common approaches:

| Approach | How it works | What to control |
| --- | --- | --- |
| AsciiDoc as canonical source | Write pages in AsciiDoc, include snippets, and render to HTML/PDF | Ensure output format and styling fit your needs |
| Generate Markdown from snippets | After tests, a build step reads snippet outputs and injects them into Markdown templates | Define file mappings, ordering, and code/table escaping |
| Custom snippet templates | Use templates matching the project's desired output format | Templates must be configured and tested with the REST Docs version |
| Markdown include tool | Use a project-chosen plugin/preprocessor to insert files | Verify the tool runs in CI and fails on missing files |

A Markdown pipeline can be illustrated as:

```text
HTTP tests
    │
    ▼
generated-snippets/*.adoc or snippet data
    │
    ▼
Project-configured conversion/injection step
    │
    ├── Convert field tables to Markdown tables
    ├── Convert HTTP request/response to fenced code blocks
    └── Preserve paths/identifiers to trace sources
    │
    ▼
Complete Markdown
    │
    ▼
Markdown renderer / site generator
```

Do not simply rename `.adoc` extensions to `.md` and assume the syntax is compatible. Tables, source blocks, attributes, and includes may follow different rules. Define a concrete pipeline, verify its output, and test an end-to-end example in CI.

## 9. Step 6 — Wiring Steps into Build and CI

The goal is to ensure **snippet-generating tests run before documentation**, and pages are rendered from that exact build's output.

### 9.1. Gradle Example

The following Groovy DSL example illustrates basic task dependencies when a project already configures a `test` task, the Asciidoctor plugin, and the matching Spring REST Docs dependencies:

```groovy
plugins {
    id 'org.asciidoctor.jvm.convert' version '4.0.2'
}

def snippetsDir = file("$buildDir/generated-snippets")

tasks.named("test") {
    outputs.dir snippetsDir
}

tasks.named("asciidoctor") {
    dependsOn tasks.named("test")
    inputs.dir snippetsDir
    attributes "snippets": snippetsDir
}
```

This is a skeleton example; full configuration depends on plugins, dependency setup, and the project's test engine. Many projects declare a dedicated configuration for the Spring REST Docs Asciidoctor extension. What must be ensured is:

- Tests actually run.
- Snippets are written to the declared `snippetsDir`.
- The Asciidoctor task depends on tests.
- The `snippets` attribute points to the right directory.
- When tests fail or snippets are missing, the build stops instead of publishing broken pages.

If documentation tests run via another task, such as `integrationTest`, depend on that task instead of always assuming `test`.

### 9.2. With Maven

Maven typically places snippets in `target/generated-snippets` under common configurations. Wire the test plugin and Asciidoctor plugin into the lifecycle so tests run and generate snippets before documentation compilation.

Do not copy Gradle configuration verbatim into Maven. Check three points: which phase runs tests, which output directory is used, and where the compilation plugin receives the `snippets` attribute. The build must succeed from a clean state without manually pre-generated snippets.

### 9.3. CI Pipeline Pattern

```text
Checkout source
      │
      ▼
Clean generated outputs
      │
      ▼
Compile + run documentation tests
      │
      ├── Assertion/descriptor failure ──► Fail
      │
      ▼
Verify generated snippets
      │
      ▼
Render Asciidoctor or generate Markdown
      │
      ├── Missing include/render failure ──► Fail
      │
      ▼
Review output and public data
      │
      ▼
Publish artifact / documentation site
```

CI should run from a clean checkout or clean the auto-generated output directories properly. If tests are skipped while snippets from a previous run remain, rendering might succeed and create the false impression that docs were built from current code.

### 9.4. What Does CI Verify?

CI can verify that tests ran, assertions passed, descriptors matched, snippets were created, includes resolved, and pages rendered cleanly. CI does not automatically verify that every written business rule is accurate. Content such as status meanings, monetary limits, access permissions, and retry policies still needs review by someone who understands the contract, plus automated tests wherever verifiable.

## 10. Tracing and Diagnosing Errors Step by Step

A multi-step chain helps isolate failures faster. Do not look solely at the final message from the rendering task.

| Symptom | Step to inspect | Common cause | Action |
| --- | --- | --- | --- |
| Snippet directory not created | Tests / REST Docs config | Tests did not run or filter/extension not installed | Verify test discovery and test client setup |
| Missing `http-response.adoc` | Operation recording | `document(...)` not called or request failed earlier | Check test flow and logs |
| Path parameter table not generated | Builder / descriptors | Request builder did not retain URI template | Use the right REST Docs builder |
| `response-fields.adoc` fails | Descriptor validation | Undocumented field, missing required field, or different payload | Cross-check contract and response |
| Include reports missing file | Documentation source | Wrong identifier/filename or test task did not generate snippet | Match `document(...)` against include |
| Page renders, yet content is stale | Build output | Leftover old snippets | Clean outputs and rerun tests |
| Markdown displays raw include directive | Markdown pipeline | Renderer does not support Asciidoctor syntax | Use an appropriate conversion/injection step |
| Asciidoctor task runs before tests | Build dependency | Missing `dependsOn` or wrong task dependency | Wire snippet-generating test task before compilation |
| Snippets leak sensitive host/token | Preprocessor / fixture | Test request uses environment data | Use safe fixtures and normalize outputs |
| Build passes, yet business rule is wrong | Review / test coverage | Assertions miss the rule or hand-written text is inaccurate | Add tests and review contract |

### 10.1. Example of Diagnosing a Missing Snippet

Suppose a page has:

```asciidoc
include::{snippets}/products-get-success/response-fields.adoc[]
```

yet the build reports the file cannot be found. Check in order:

1. Does the test call `document("products-get-success", ...)`?
2. Is `responseFields(...)` declared for that operation?
3. Did the test pass and reach the documentation step?
4. Is the actual output directory `build/generated-snippets` or a different path?
5. Does the `snippets` attribute point to the right output directory?
6. Is the filename spelled exactly `response-fields.adoc`?

If the test omitted `responseFields(...)`, the field table file may not be generated. Changing the include to another file just to make the build pass hides the fact that the documentation no longer meets requirements.

## 11. Contract Changes and Documentation Regeneration

Suppose the product response changes from:

```json
{
  "id": 7,
  "name": "Notebook",
  "price": 45000
}
```

to:

```json
{
  "id": 7,
  "name": "Notebook",
  "unitPrice": 45000,
  "currency": "VND"
}
```

A proper update sequence consists of:

1. Confirm the new schema is an accepted contract change.
2. Update the controller/DTO or response logic.
3. Update assertions to verify key fields and values.
4. Update `responseFields(...)` descriptors for the new schema.
5. Run tests to regenerate snippets.
6. Update hand-written prose explaining `unitPrice` and `currency`.
7. Render documentation pages and check all includes.
8. Evaluate compatibility with clients using the old schema.

If you update only descriptors without updating assertions, tests may validate structure while missing business values. If you edit only JSON inside documentation sources, snippets will still be generated from test responses, leaving the two out of sync.

## 12. End-to-End Hands-On Exercise

Build documentation for two operations of a product API:

- `GET /api/products/{id}`: success returns `200` with product data; not found returns `404`.
- `POST /api/products`: successful creation returns `201`, a `Location` header, and JSON; invalid request returns `400` with an error schema.

### Tasks

1. Prepare fixtures with fixed IDs and deterministic data.
2. Write HTTP tests using MockMvc, WebTestClient, or REST Assured. Pick the tool matching your stack and verification scope.
3. In each test, assert the status and key business values.
4. Call `document(...)` with a distinct identifier for each scenario.
5. Declare descriptors for path/query parameters, request/response headers, and request/response fields whenever present in the contract.
6. Run tests, inspect the output directory, and verify expected snippets exist.
7. Create an AsciiDoc page with includes for request/response examples, field tables, and error cases.
8. If choosing Markdown, build an explicit snippet conversion or injection step and test the renderer.
9. Wire the compilation task to snippet-generating tests; run the entire workflow from a clean output directory.
10. Temporarily change an identifier in a test without updating the page, confirm the include fails; then update both and rerun.

### Completion Criteria

- Tests run from reproducible data.
- Assertions protect statuses and key values.
- Each scenario has an appropriate identifier without colliding outputs.
- Snippets are generated from the right tests and placed in the configured output directory.
- Documentation pages include the right files, contain business explanations, and distinguish success/error responses.
- A clean build runs tests before rendering and does not depend on stale outputs.
- Published content contains no sensitive data.

## 13. Takeaways

- The core flow of Spring REST Docs is **HTTP tests → assertions/descriptors → operations → snippets → Asciidoctor or Markdown pipeline → build/CI**.
- The test client sends requests and receives responses; assertions verify behavior; descriptors describe structure; `document(identifier, ...)` links the operation to snippet outputs.
- Asciidoctor can include snippets directly; Markdown requires a conversion/injection mechanism compatible with the renderer in use.
- The compilation task must depend on snippet-generating tests, outputs must be reproducible from a clean state, and identifiers/includes must match.
- A passing build proves the automated steps within the executed scope; contract reliability still depends on the quality of assertions, descriptors, test scope, and business review.
