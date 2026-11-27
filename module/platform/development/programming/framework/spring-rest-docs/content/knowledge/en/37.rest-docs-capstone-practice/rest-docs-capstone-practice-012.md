# Evaluating Solutions by Accuracy, Readability, and Reproducibility

## 1. Lesson Objectives

In the **SPRING_REST_DOCS** module, we create verifiable REST API documentation through HTTP tests using MockMvc, WebTestClient, or REST Assured. Tests send requests, verify responses, and Spring REST Docs generates snippets for requests, responses, payloads, parameters, and headers. Snippets are assembled with Asciidoctor/Markdown and integrated into the build and CI.

Complete API documentation needs more than a passing build. It must accurately reflect real behavior, help readers execute requests quickly, and be reproducible from a clean environment. The three criteria of this capstone:

- **Accuracy:** examples, statuses, headers, payloads, and field descriptions match the tested behavior.
- **Readability:** integrators understand how to call the endpoint, what data to send, what responses to expect, and how to handle errors.
- **Reproducibility:** others can check out the source, run tests, and regenerate the exact same snippets and documentation without manual edits.

After this lesson, you will be able to evaluate a Spring REST Docs solution using an evidence-based rubric, identify trade-offs, and plan improvements before publishing documentation.

## 2. Capstone Context

Suppose a team develops an order management API with the following endpoints:

| Method | Endpoint | Success | Typical errors |
| --- | --- | --- | --- |
| POST | `/api/orders` | 201 Created | 400 validation, 401 unauthorized |
| GET | `/api/orders/{id}` | 200 OK | 404 not found |
| GET | `/api/orders` | 200 OK with list and paging | 400 invalid query |
| POST | `/api/orders/{id}/cancel` | 204 No Content | 403 forbidden, 409 conflict |

The team uses MockMvc to document Spring MVC controllers, Spring REST Docs to generate snippets, Asciidoctor to assemble documentation, and Gradle/CI for automation.

The capstone does not grade page count or snippet count. The goal is to demonstrate that readers can understand and use the API from the documentation, and that the team can regenerate the documentation from tests.

## 3. Three Evaluation Axes

| Axis | Weight | Evaluation question |
| --- | ---: | --- |
| Accuracy | 40% | Does the documentation match the contract and is it verified by tests? |
| Readability | 30% | Can a developer understand and execute a request from the documentation? |
| Reproducibility | 30% | Can the documentation be regenerated from a clean checkout via an automated workflow? |

The weights are suggestions for the exercise. Teams can adjust them, but one criterion should never fully compensate for a severe deficiency in another. Pretty documentation with a wrong contract still cannot be published; accurate documentation that cannot be rebuilt is hard to maintain.

## 4. Evaluating Accuracy

Accuracy answers the question: "Is what the documentation states verified by tests and faithful to the contract clients observe?"

### 4.1. Requests Must Be Accurate

Check:

- Do HTTP method and path match the mapping?
- Are path variables, query parameters, and encoding accurate?
- Are request headers such as `Content-Type`, `Accept`, and `Authorization` documented accurately?
- Does the request body have the right fields, data types, required/optional flags, and nested structures?
- Do examples use valid values consistent with validation and business rules?

A request example can look plausible yet be wrong if `quantity` is documented as optional when the DTO requires a positive value. Cross-check snippets against test assertions and the actual schema.

### 4.2. Responses Must Be Accurate

Check:

- Are status codes right for each success and failure case?
- Do response headers reflect the media type, pagination, location, or correlation ID promised by the API?
- Does the body have the right structure, field paths, nullability, and formats?
- Are error codes stable and paired with the right HTTP status?
- Are empty responses, redirects, async, or streaming responses documented accurately?

In particular, never use a 200 response as a stand-in for error branches. Each major error category should have its own test and operation snippet.

### 4.3. Descriptors Must Match the Payload

Spring REST Docs catches differences between payloads and field descriptors:

~~~java
responseFields(
    fieldWithPath("id")
        .description("Order identifier."),
    fieldWithPath("status")
        .description("Current status of the order."),
    fieldWithPath("items[]")
        .description("List of items in the order.")
)
~~~

Descriptor review:

- Field paths match the real JSON, including nested paths and collections.
- Types/formats are explained clearly enough for client use.
- `optional` is marked only when the contract permits absence.
- `ignored` fields or relaxed descriptors must have an explicit justification.
- Do not use `relaxedResponseFields` to mask an undocumented important field.

### 4.4. Tests Are Evidence, Not Assertions in Name Only

Tests need assertions on contract-deciding points:

~~~java
mockMvc.perform(get("/api/orders/{id}", 42))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.id").value(42))
    .andExpect(jsonPath("$.status").value("CREATED"))
    .andDo(document("orders/get"));
~~~

If a test only asserts status 200 and documents the entire response, the test does not prove key business values. Add deliberate assertions, especially for error codes, pagination metadata, headers, and required fields.

## 5. Evaluating Readability

Readability answers the question: "Can a developer unfamiliar with the system call the API successfully and understand how to process the response?"

### 5.1. Structuring Documentation Around Reader Tasks

An operation should be presented in this order:

1. Purpose and usage prerequisites.
2. HTTP method, endpoint, and required permissions.
3. Path/query parameters and request headers.
4. Request body with a realistic example.
5. Response status, headers, and body.
6. Common errors, error codes, and remediation.
7. Links to related schemas or operations.

Readers should find the information they need without tracing back through test source code.

### 5.2. Descriptions Must Answer "Why" and "How to Use"

Weak description:

~~~java
fieldWithPath("status").description("Status");
~~~

Better description:

~~~java
fieldWithPath("status")
    .description("Order status. CREATED means newly created, PAID means paid, and SHIPPED means handed over for delivery.");
~~~

Good descriptions state meaning, allowed values, and client implications. Do not repeat the field name with a synonym.

### 5.3. Examples Must Be Consistent

If the request uses `customerId = 1001`, the response should reference that same customer. If the response shows `status = PAID`, the explanation should state the conditions for the order to reach that state. Avoid copy/paste errors that cause IDs, dates, or statuses to contradict across snippets.

### 5.4. Keeping Documentation Scannable

- Use meaningful headings by endpoint or domain action.
- Use tables for parameters, headers, error codes, and enum values.
- Keep code blocks concise, runnable, or supplied with enough context to understand.
- Place explanations before or immediately after the relevant snippet.
- Do not dump all implementation details into client guides.
- Use consistent terminology for the same concept.

## 6. Evaluating Reproducibility

Reproducibility answers the question: "Can another developer regenerate this exact documentation set from the repository?"

### 6.1. Builds Must Have a Clear Order

~~~mermaid
flowchart TD
    A["Checkout source"] --> B["Resolve dependencies"]
    B --> C["Run HTTP documentation tests"]
    C --> D["Generate REST Docs snippets"]
    D --> E["Run Asciidoctor"]
    E --> F["Validate output"]
    F --> G["Publish CI artifact"]
~~~

Tests must run before Asciidoctor because snippets are inputs to the assembly step. Never rely on stale snippets left over from a previous build to make the current build appear successful.

### 6.2. Environments Must Be Stable

Verify:

- Java and Gradle wrapper versions are pinned.
- Spring Boot/Spring REST Docs dependencies are managed consistently.
- Tests do not depend on external APIs or personal credentials.
- Clocks, random IDs, and test data are controlled.
- Locale, timezone, and encoding do not unexpectedly alter snippets.
- Generated snippets are written into a clean build directory.

If trace IDs or timestamps change on every run, snippet diffs become noisy. Use stable test fixtures or deliberate preprocessors, while keeping assertions that verify real behavior.

### 6.3. Do Not Edit Auto-Generated Snippets

Snippets are test outputs. Do not manually edit files under `build/generated-snippets` to make documentation look prettier. Instead, update:

- Test fixtures if example data is unsuitable.
- Assertions if tests do not verify the contract yet.
- Field/header descriptors if descriptions are missing.
- Operation preprocessors if URIs need normalization or data needs masking.
- Asciidoctor sources if narrative explanation, summary tables, or structure needs additions.

After making changes, re-run tests so snippets are generated from the source of truth.

## 7. Detailed Evaluation Rubric

Score each criterion on a 0–4 scale:

| Score | Meaning |
| ---: | --- |
| 0 | Missing or critically incorrect. |
| 1 | Present but missing major parts; hard to trust. |
| 2 | Partially met; missing important examples/assertions. |
| 3 | Meets requirements; evidenced and easy to use. |
| 4 | Excellent; consistent, maintainable, and automatically verifiable. |

### 7.1. Accuracy — 40%

| Criterion | Evidence to evaluate |
| --- | --- |
| Request contract | Request snippets, path/query/header descriptors, and test assertions. |
| Response contract | Status, response header/body snippets, and assertions. |
| Payload descriptors | Field paths, types, optionality, nested objects, and arrays. |
| Error contract | Status, error codes, validation details, and examples per error group. |
| Example consistency | Request/response examples are consistent and executable. |

### 7.2. Readability — 30%

| Criterion | Evidence to evaluate |
| --- | --- |
| Information architecture | Table of contents and operation order fit reader tasks. |
| Description quality | Explains meaning, constraints, and usage rather than repeating field names. |
| Example clarity | Code blocks have context, clear data, and consistency. |
| Navigation | Readers can locate endpoints, error codes, and related schemas. |

### 7.3. Reproducibility — 30%

| Criterion | Evidence to evaluate |
| --- | --- |
| Clean build | Runs from a clean checkout without relying on stale snippets. |
| Deterministic output | Fixtures/clock/locale/IDs are controlled; diffs are clean. |
| CI integration | Tests run before Asciidoctor; build fails on test or snippet contract failure. |
| Maintenance | No manual edits to generated snippets; sources and versions are managed. |

## 8. Example Scorecard for a Documentation Set

Suppose a team reviews a documentation set with these results:

| Axis | Average score (0–4) | Weight | Weighted score |
| --- | ---: | ---: | ---: |
| Accuracy | 3.5 | 40% | 35.0/40 |
| Readability | 2.5 | 30% | 18.75/30 |
| Reproducibility | 4.0 | 30% | 30.0/30 |
| **Total** | | | **83.75/100** |

Formula per axis:

\[
\text{Axis score} =
\frac{\text{Average score}}{4}
\times \text{Weight}
\]

A score of 83.75 does not mean the documentation is automatically cleared for release. Reviewers must still check for blocking defects such as leaked secrets, wrong statuses, or missing examples on critical endpoints. A single severe defect can fail the documentation despite a high total score.

## 9. Quality Gates Before Release

Separate scoring criteria from mandatory gates:

| Gate | Pass condition |
| --- | --- |
| Contract | Test assertions and REST Docs descriptors accurately reflect published endpoints. |
| Coverage | Examples exist for happy paths and major errors within API scope. |
| Security | No unintended tokens, secrets, personal data, or debug details. |
| Build | Clean test and Asciidoctor build succeed. |
| Output | Snippets and final documentation are completely generated without stale output. |
| Review | Content and contract changes have been reviewed by a peer. |

Do not publish based solely on the rubric total if any mandatory gate fails.

## 10. Workflow for Reviewing an Operation

For each endpoint, a reviewer can follow these steps:

1. Read the endpoint description and identify what the API consumer needs to do.
2. Read the test to see which request is sent and which assertions protect the contract.
3. Read `http-request.adoc` and verify method, URI, headers, and body.
4. Read `http-response.adoc` and verify status, headers, and body.
5. Read request/response field snippets to inspect the schema.
6. Compare Asciidoctor prose against snippets and error behavior.
7. Check for sensitive data and internal details.
8. Re-run the build from a clean state to verify reproducibility.

If a reviewer cannot explain how to call the endpoint from the documentation alone, readability fails. If snippets must be edited by hand for the build to pass, reproducibility fails.

## 11. Example of High-Quality Test and Documentation

Order creation test example:

~~~java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content("""
            {
              "customerId": 1001,
              "items": [
                {
                  "productId": "BOOK-01",
                  "quantity": 2
                }
              ]
            }
            """))
    .andExpect(status().isCreated())
    .andExpect(header().exists("Location"))
    .andExpect(jsonPath("$.id").isNumber())
    .andExpect(jsonPath("$.status").value("CREATED"))
    .andDo(document("orders/create",
        requestFields(
            fieldWithPath("customerId")
                .description("Authenticated customer ID authorized to place orders."),
            fieldWithPath("items")
                .description("List of items to order."),
            fieldWithPath("items[].productId")
                .description("Product ID in the catalog."),
            fieldWithPath("items[].quantity")
                .description("Quantity; must be greater than or equal to 1.")
        ),
        responseHeaders(
            headerWithName("Location")
                .description("URI of the newly created order.")
        ),
        responseFields(
            fieldWithPath("id")
                .description("New order identifier."),
            fieldWithPath("status")
                .description("Initial status of the order.")
        )
    ));
~~~

Evaluating the example:

- **Accuracy:** test verifies 201, `Location`, `id`, and `status`; descriptors document request/response fields.
- **Readability:** descriptions explain meaning and constraints; operation ID is clear.
- **Reproducibility:** test uses explicit fixture data; snippets are generated via `document(...)`.

This code illustrates a test with MockMvc and REST Docs already configured; the project needs the appropriate static imports and setup.

## 12. Evaluating Error Documentation

Good documentation does not cover only 2xx responses. Validation error example:

~~~java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {
              "customerId": 1001,
              "items": []
            }
            """))
    .andExpect(status().isBadRequest())
    .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
    .andExpect(jsonPath("$.errors").isArray())
    .andDo(document("orders/create-validation-error",
        responseFields(
            fieldWithPath("code")
                .description("Overall error code."),
            fieldWithPath("message")
                .description("Error explanation message."),
            fieldWithPath("errors")
                .description("List of validation errors."),
            fieldWithPath("errors[].path")
                .description("Path to the invalid field."),
            fieldWithPath("errors[].code")
                .description("Field-specific error code."),
            fieldWithPath("errors[].message")
                .description("Explanation of the validation constraint.")
        )
    ));
~~~

Reviewers must verify whether the actual error payload matches this structure, especially if object-level errors have a nullable `path` or the response has extra fields. Never copy descriptors from an example without checking against the real response.

## 13. Verifying Output Stability

Run the build twice from a clean state and compare:

~~~bash
./gradlew clean test asciidoctor
~~~

~~~bash
./gradlew clean test asciidoctor
~~~

Expected result:

- Identical test sources and fixtures generate identical snippet content.
- Independent of test execution order.
- Independent of current time, timezone, or unintended locale.
- Does not require snippet files from a previous run.
- Does not require manual editing after the build.

If output contains timestamps or dynamic IDs, determine whether they are part of the contract to document or just noise. Use test fixtures or operation preprocessors to normalize snippets without altering the behavior verified by assertions.

## 14. Gradle and CI Integration

Task configuration example:

~~~groovy
def snippetsDir = layout.buildDirectory.dir("generated-snippets")

tasks.named("test") {
    outputs.dir(snippetsDir)
}

tasks.named("asciidoctor") {
    dependsOn(tasks.named("test"))
    inputs.dir(snippetsDir)
    attributes "snippets": snippetsDir.get().asFile
}
~~~

Pipeline may include:

~~~yaml
steps:
  - name: Run documentation tests and build API docs
    run: ./gradlew clean test asciidoctor
  - name: Archive generated API documentation
    uses: actions/upload-artifact@v4
    with:
      name: spring-rest-docs
      path: build/docs/asciidoc
~~~

This is a general workflow example; task names, output paths, and artifact actions must match repository configuration. Do not copy paths verbatim if your project's plugin outputs documentation elsewhere.

## 15. Common Evaluation Pitfalls

| Misconception | Why it falls short | Proper evaluation |
| --- | --- | --- |
| "Build succeeded so docs are accurate" | Build only proves steps ran, not that test assertions cover the contract | Inspect assertions and snippets per endpoint. |
| "All snippets are present so it is readable" | Snippets may lack context, descriptions, and structure | Try completing a task using only the documentation. |
| "CI is green so it is reproducible" | CI may be using caches or stale outputs | Run a clean build, verify generated outputs, and check dependency pinning. |
| "Relaxed descriptors keep tests stable" | Can hide new or important undocumented fields | Use strict descriptors for key contracts; justify exceptions clearly. |
| "Masking tokens in snippets is safe enough" | Secrets may still appear in test logs, reports, or other artifacts | Scan all outputs and never use real secrets in fixtures. |
| "Two clients must produce byte-for-byte identical output" | Host/port/runtime headers can vary by binding mode | Compare meaningful contract details and normalize intentional differences. |

## 16. Capstone Exercise

Complete the order management API documentation with these requirements:

1. Document `POST /api/orders` with request fields, response fields, 201, and `Location`.
2. Document `GET /api/orders/{id}` with path parameter and 404 error.
3. Document `GET /api/orders` with query parameters, paging metadata, and response list.
4. Document field-level and object-level validation errors.
5. Document 401/403/409 errors according to the actual contract.
6. Mask credentials, cookies, and personal data from snippets.
7. Organize Asciidoctor into Overview, Authentication, Orders, Errors, and Troubleshooting sections.
8. Wire Gradle `test` and `asciidoctor` into CI.
9. Run two clean builds and compare outputs.
10. Use the rubric in section 7 to score, record evidence, and create an improvement action list.

## 17. Evaluation Report Template

When reviewing, record results using this template:

~~~text
Project:
Commit:
Build command:

Accuracy: __ / 4
Evidence:
- Request contract:
- Response contract:
- Field descriptors:
- Error contract:

Readability: __ / 4
Evidence:
- Navigation:
- Descriptions:
- Examples:

Reproducibility: __ / 4
Evidence:
- Clean build:
- Deterministic output:
- CI integration:

Blocking issues:
1.

Improvements:
1.

Decision: PASS / NEEDS WORK
~~~

Evidence must point to specific tests, snippets, documentation sections, or CI results. Avoid vague remarks like "docs look good" or "clean code" without citing proof.

## 18. Remember

- Accuracy is proven by test assertions and snippets matching the contract.
- Readability is measured by whether developers can understand and call the API from the documentation.
- Reproducibility requires clean builds, stable fixtures, managed dependencies, and CI running in the right order.
- Snippets are test outputs; never manually edit generated snippets.
- Strict descriptors help detect unexpected payload changes.
- Security, contract correctness, and clean builds are quality gates, not mere bonus points in a rubric.
- Scorecards need concrete evidence and an actionable improvement list.

## 19. References

- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/reference/getting-started.html): configuring tests and generating documentation from snippets.
- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html): snippet types for requests, responses, headers, and payloads.
- [Spring REST Docs — Gradle Plugin](https://docs.spring.io/spring-restdocs/reference/gradle.html): integrating Asciidoctor and Gradle.
