# Naming Tests and Operations to Trace Snippets Easily

## 1. Why Should Test Names and Operation Names Be Consistent?

In the **SPRING_REST_DOCS** module, HTTP tests using MockMvc, WebTestClient, or REST Assured both verify API behavior and produce generated snippets. Those snippets are assembled into Asciidoctor/Markdown documentation and are typically regenerated in build/CI.

When an API has many operations and each operation has multiple outcomes, unclear names make tracing the source of a snippet difficult. For example, a directory named `get-1` does not tell you whether it captures fetching an account successfully, a missing account, or listing accounts. If a test method has a generic name like `testApi()`, reviewers also struggle to identify the test's goal from CI reports.

Two kinds of names must be distinguished:

- **Test name:** the method/scenario identifier in JUnit, such as `getExistingOrder_returns200` or its display name.
- **Operation/snippet name:** the string passed to `document("...")`, which determines the generated snippets directory, such as `orders-get-success`.

JUnit does not automatically convert `@DisplayName` into a REST Docs snippet identifier. Both names can share the same semantic meaning, yet they must be connected through clear conventions and code.

This lesson covers:

1. Naming tests by operation, scenario, and outcome.
2. Choosing stable, meaningful, non-colliding snippet identifiers.
3. Linking test methods, HTTP operations, snippets, and Asciidoctor include blocks.
4. Handling parameterized/dynamic tests and multiple statuses for the same endpoint.
5. Designing names that are easy to find in CI reports, generated snippets, and code reviews.

## 2. Distinguishing Test Name, Display Name, and Snippet Identifier

| Concept | Example | Where It Appears | Purpose |
| --- | --- | --- | --- |
| Test method name | `getOrder_whenExists_returns200` | Java code, test reports | Identifies the technical scenario |
| JUnit display name | `GET order - existing - 200 OK` | IDE/test report | Helps human readers understand the test |
| REST Docs identifier | `orders-get-success` | Generated snippets path | Operation/scenario name in documentation |
| API path | `GET /api/orders/{id}` | HTTP request and docs | Actual endpoint |
| Asciidoctor section | `Get Existing Order` | Published documentation | Content navigation for readers |

A test can send an HTTP request to `GET /api/orders/42`, appear in JUnit as `GET order - existing - 200 OK`, and write snippets into `orders-get-success`. No automatic mechanism forces these three strings to be identical.

**Rule:** each name serves a distinct purpose, yet carries enough information for a reader to trace back between them.

## 3. Structuring Test Method Names

A readable pattern:

```text
<operation>_<condition>_<expectedOutcome>
```

Examples:

| Operation | Test method | Meaning |
| --- | --- | --- |
| GET order | `getOrder_whenExists_returns200` | Order exists |
| GET order | `getOrder_whenMissing_returns404` | Not found |
| POST order | `createOrder_withValidRequest_returns201` | Order created successfully |
| POST order | `createOrder_whenInvalid_returns400` | Invalid input data |
| DELETE order | `deleteOrder_whenExists_returns204` | Deleted successfully, no body |

Names should clearly state the condition and the expected outcome under test. Avoid generic names like `testGet()`, `testSuccess()`, `testError()`, or overly long names repeating the entire business narrative.

You do not need to cram the entire endpoint into the method name. When the enclosing class or nested class already establishes the resource, method names can stay shorter.

### 3.1. Using @DisplayName for Readable Reports

JUnit Jupiter lets you specify a separate display name:

```java
@Test
@DisplayName("GET order: existing order returns 200")
void getOrder_whenExists_returns200() throws Exception {
    // Arrange fixture, perform request, assert, and document(...)
}
```

A display name helps report readers understand the scenario without decoding naming conventions. It does not replace the method name; the method name remains useful for stack traces, repository search, and team conventions.

Do not derive identifiers from display names via reflection unless there is a strong reason. Display names may contain accents, spaces, or wording changed for presentation; snippet identifiers should be stable, path-safe strings controlled in source code.

### 3.2. Using @Nested to Group by Resource

```java
@Nested
@DisplayName("Orders API")
class OrdersApi {

    @Nested
    @DisplayName("GET /api/orders/{id}")
    class GetOrder {

        @Test
        @DisplayName("Existing order returns 200")
        void whenExists_returns200() throws Exception {
            // ...
        }

        @Test
        @DisplayName("Missing order returns 404")
        void whenMissing_returns404() throws Exception {
            // ...
        }
    }
}
```

Nested structures give test reports a resource/operation/scenario hierarchy. Inner methods do not need to repeat the full endpoint name when the enclosing class already supplies the context.

Regardless of class organization, the snippet identifier must still be explicitly passed to `document(...)`.

## 4. Conventions for REST Docs Identifiers

An extensible format:

```text
<resource>-<operation>-<scenario>
```

Examples:

```text
orders-get-success
orders-get-not-found
orders-create-success
orders-create-validation-error
orders-cancel-no-content
accounts-get-success
accounts-update-conflict
```

If you need to distinguish API versions or representations, add a standardized segment:

```text
v1-orders-get-success
v2-orders-get-success
orders-get-success-json
orders-get-success-xml
```

Only add a segment when it resolves a real distinction. Overly long names that repeat the full path and every request parameter make identifiers hard to maintain.

A good identifier has these traits:

- Lowercase, using hyphens and path-safe characters.
- Stable across runs, without timestamps or random UUIDs.
- Clearly distinguishes the resource, operation, and scenario/outcome.
- Never collides with another test whose output differs.
- Placed right next to the `document(...)` call so reviewers can inspect it easily.
- Used consistently in Asciidoctor include directives.

### 4.1. Never Use One Identifier for Different Content

Wrong:

```java
@Test
void getOrderSuccess() throws Exception {
    // ...
    mockMvc.perform(get("/api/orders/42"))
            .andDo(document("orders-get"));
}

@Test
void getOrderNotFound() throws Exception {
    // ...
    mockMvc.perform(get("/api/orders/404"))
            .andDo(document("orders-get"));
}
```

Both tests write to the same `orders-get` directory. Snippet contents can be overwritten or become execution-order dependent. This is especially hard to spot when suites run in parallel or builds retain old outputs.

Right:

```java
.andDo(document("orders-get-success"))
```

```java
.andDo(document("orders-get-not-found"))
```

Each scenario gets its own output, and Asciidoctor can include the exact matching scenario.

### 4.2. Avoid Identifiers Generated from Random Values

Avoid:

```java
.andDo(document("orders-" + UUID.randomUUID()))
```

The directory name changes on every run, making diffs hard to review and breaking stable documentation includes. Only use parameters from a controlled value set when you genuinely need separated outputs. For representative scenarios, fixed identifiers are better.

## 5. Linking Test Methods to Snippet Identifiers

A well-structured documentation test shows all three elements clearly:

```java
@Test
@DisplayName("GET order: existing order returns 200")
void getOrder_whenExists_returns200() throws Exception {
    given(orderService.findById("42"))
            .willReturn(new OrderResponse("ORD-42", "CONFIRMED"));

    mockMvc.perform(get("/api/orders/{id}", "42")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.orderId").value("ORD-42"))
            .andDo(document("orders-get-success",
                    responseFields(
                            fieldWithPath("orderId")
                                    .description("Order ID"),
                            fieldWithPath("status")
                                    .description("Order status")
                    )));
}
```

The method name states the condition and status; the display name is report-friendly; the snippet identifier serves as the output path. Reviewers can find the method by identifier or read the identifier right inside `document(...)`.

If one test contains multiple `document(...)` calls for different HTTP exchanges, assign distinct identifiers and name variables/blocks to reflect the corresponding operation. Better yet, split into separate tests if the exchanges represent independent outcomes that should be documented individually.

## 6. Organizing by Resource and Operation in JUnit

For APIs with multiple resources, you can use one class per resource or nested classes:

```java
@ExtendWith(RestDocumentationExtension.class)
class OrderDocumentationTests {

    @Nested
    class GetOrder {

        @Test
        void whenExists_returns200() throws Exception {
            // document("orders-get-success")
        }

        @Test
        void whenMissing_returns404() throws Exception {
            // document("orders-get-not-found")
        }
    }

    @Nested
    class CreateOrder {

        @Test
        void withValidRequest_returns201() throws Exception {
            // document("orders-create-success")
        }

        @Test
        void withInvalidRequest_returns400() throws Exception {
            // document("orders-create-validation-error")
        }
    }
}
```

Class, nested class, and method names form a navigation tree for the test suite. Snippet identifiers following the resource-operation-outcome convention form a matching output tree:

```text
OrderDocumentationTests
├── GetOrder
│   ├── whenExists_returns200
│   └── whenMissing_returns404
└── CreateOrder
    ├── withValidRequest_returns201
    └── withInvalidRequest_returns400

generated-snippets/
├── orders-get-success/
├── orders-get-not-found/
├── orders-create-success/
└── orders-create-validation-error/
```

Test structure and snippet directory names do not have to match character-for-character. What must be preserved is a clear relationship, easy traceability, and zero duplicate identifiers.

## 7. Parameterized Tests and Snippet Names

A parameterized test has multiple invocations of a single method. If every invocation calls `document(...)` with the same identifier, they will write to the same snippet directory.

Example with overwrite risk:

```java
@ParameterizedTest
@ValueSource(strings = {"42", "43"})
void getOrder(String id) throws Exception {
    mockMvc.perform(get("/api/orders/{id}", id))
            .andExpect(status().isOk())
            .andDo(document("orders-get-success"));
}
```

Decide the test's purpose:

**Case A — only one representative snippet is needed:** keep the parameterized test to verify multiple IDs, without generating snippets from every invocation. Create a separate documentation test with a stable fixture and fixed identifier.

**Case B — each invocation is a distinct documented scenario:** supply a static scenario key instead of using arbitrary values as directory names.

```java
@ParameterizedTest
@CsvSource({
    "42, ORD-42, order-42",
    "43, ORD-43, order-43"
})
void getOrder(String id, String expectedId, String scenario)
        throws Exception {

    mockMvc.perform(get("/api/orders/{id}", id))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.orderId").value(expectedId))
            .andDo(document("orders-get-" + scenario));
}
```

The scenario keys here are controlled by the test author and each key is unique. If input data contains accents, slashes, spaces, or unstable values, never concatenate it directly into the identifier.

## 8. Dynamic Tests and Stable Names

Dynamic tests create test nodes at runtime. You can assign readable display names and use stable scenario keys:

```java
@TestFactory
Stream<DynamicTest> orderScenarios() {
    return Stream.of(
            new OrderScenario(
                    "existing-order", "42", 200),
            new OrderScenario(
                    "missing-order", "404", 404))
        .map(scenario -> dynamicTest(
                "GET order - " + scenario.name(),
                () -> {
                    // Arrange, request, assertions
                    // document("orders-get-" + scenario.name())
                }));
}

record OrderScenario(String name, String id, int status) {}
```

Display names aid reporting; the scenario name serves as the identifier suffix. Because dynamic tests do not automatically get separate per-node lifecycle callbacks like standard test methods, if each node requires an independent documentation context, manage the lifecycle inside the executable or prefer parameterized tests with the Jupiter extension.

Never construct names from exception messages or dynamic responses. Those strings vary across environments and make output hard to trace.

## 9. Synchronizing Identifiers with Asciidoctor

Once identifiers are known, include snippets from the exact paths:

```adoc
= Order API
:snippets: build/generated-snippets

== Get Order

=== Existing Order
include::{snippets}/orders-get-success/http-request.adoc[]
include::{snippets}/orders-get-success/http-response.adoc[]
include::{snippets}/orders-get-success/response-fields.adoc[]

=== Order Not Found
include::{snippets}/orders-get-not-found/http-request.adoc[]
include::{snippets}/orders-get-not-found/http-response.adoc[]
```

If a test renames its identifier from `orders-get-success` to `orders-read-success` while Asciidoctor still includes the old path, the documentation build step will report missing snippets. When renaming an identifier, update references and check all related includes in the delivered documentation.

Follow these rules:

- Each identifier appears in a single `document(...)` declaration for a given scenario.
- Asciidoctor includes reference the exact same identifier.
- Documentation headings express the outcome in the API consumer's language.
- CI runs snippet-generating tests before the Asciidoctor task.
- Snippets are never hand-edited to "match" includes.

## 10. Tracing Back from a Snippet File to Its Test

When a reviewer sees the file:

```text
build/generated-snippets/orders-create-validation-error/http-response.adoc
```

They can trace it using this workflow:

1. Search for `orders-create-validation-error` in source code using an IDE or code search.
2. Locate the class and method containing `document("orders-create-validation-error")`.
3. Read the arrange/fixture section to see which request produced the response.
4. Read the assertions to verify status/body/headers.
5. Find the include in Asciidoctor to see which section presents the snippet.
6. Compare the snippet output against code changes and the API contract in the pull request.

This helps whenever CI flags a snippet diff: reviewers know which test produced the output, what input was sent, and why the documentation changed.

You can search the repository using source search tools:

```text
rg -n 'document\("orders-create-validation-error"\)' src/test
rg -n 'orders-create-validation-error' src/docs
```

Specific paths depend on module structure. The first command locates where the identifier is declared; the second locates where it is included or referenced in documentation.

## 11. Naming Conventions at Team Scale

A convention you can record in your project's test support/documentation guide:

| Element | Convention | Example |
| --- | --- | --- |
| Test class | Resource + DocumentationTests | `OrderDocumentationTests` |
| Nested class | HTTP operation | `GetOrder` |
| Test method | condition + expected outcome | `whenMissing_returns404` |
| Display name | HTTP verb/resource + scenario + status | `GET order - missing - 404` |
| Snippet identifier | resource-operation-outcome | `orders-get-not-found` |
| Asciidoctor heading | Client-facing descriptive phrase | `Order Not Found` |

Teams may choose different conventions as long as they apply them consistently. Avoid overly complex rules that force developers to guess multiple segments. For nested resources or long operations, keep names short yet distinguishable.

### 11.1. When Should You Rename?

Rename a test method when it no longer describes the scenario after a contract change. Rename a snippet identifier when the resource, operation, or outcome is reclassified, or when the old name is misleading. Rename a documentation heading when what readers see is no longer accurate.

Do not rename an identifier just to match a method name character-for-character if there is no real benefit. The identifier is an internal contract between tests and documentation: all referencing includes must be updated at the same time.

## 12. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Cannot find the test that generated a snippet | Generic identifier like `get-1` | Search by identifier; rename to resource-operation-outcome |
| Two tests write to the same directory | Reusing one document identifier for different output | Split identifiers by scenario |
| Readable JUnit report, confusing snippets | Only `@DisplayName` was set while identifier stayed generic | Give `document(...)` a distinct name |
| Assuming `@DisplayName` auto-generates snippet names | Confusing the two naming systems | Pass an explicit identifier to `document` |
| Parameterized invocations overwrite output | Same identifier across all invocations | Use one representative snippet or unique scenario keys |
| Dynamic test has changing names each run | Using runtime/random data for display/identifier | Use stable scenario keys |
| Asciidoctor reports missing snippet | Identifier renamed without updating include | Synchronize test identifier and include path |
| Test method name is too long | Stuffing full path and payload into the method name | Use class/nested context and condition/outcome naming |
| Hard-to-review snippet diffs | Identifier/fixture contains timestamps or random data | Standardize naming and fixtures |
| Multiple operations on one resource hard to tell apart | Only using the resource name | Add operation and outcome segments |

## 13. Checklist Before Completing a Documentation Test

- [ ] Test class/nested class indicates the resource or operation.
- [ ] Test method expresses the condition and outcome.
- [ ] Display name is readable in IDE/CI.
- [ ] REST Docs identifier is passed explicitly.
- [ ] Identifier reflects resource, operation, and scenario.
- [ ] No two tests with different contents write to the same identifier.
- [ ] Parameterized/dynamic tests use stable scenario keys.
- [ ] Identifier contains no timestamps, random UUIDs, or arbitrary data.
- [ ] Asciidoctor includes the exact declared identifier.
- [ ] HTTP request and assertions are sufficient to explain why the snippet is generated.
- [ ] CI generates snippets before compiling documentation.
- [ ] When renaming an identifier, tests and docs are updated together.

## 14. Practice

Using the Order API operations:

1. Create nested test classes `OrdersApi` and `GetOrder`.
2. Write two methods `whenExists_returns200` and `whenMissing_returns404`; add readable `@DisplayName` annotations.
3. Assign snippet identifiers `orders-get-success` and `orders-get-not-found` respectively.
4. Intentionally have both tests share `orders-get`; observe the overwrite risk and then fix them to use separate identifiers.
5. Write a parameterized test for IDs 42 and 43. Choose either a single representative snippet or fixed scenario keys.
6. Create dynamic tests with readable display names and identifiers that do not depend on random data.
7. Include both GET snippets in Asciidoctor and verify each heading points to the right outcome.
8. Search for an identifier in source and docs to trace back from a generated snippet to its test method.
9. Rename an identifier and verify the build catches the stale include; update all references.
10. Inspect CI test reports and generated snippet diffs to assess whether reviewers can locate the source of changes.

**Completion criteria:** you distinguish test method names, JUnit display names, and REST Docs identifiers; apply a concise resource/operation/scenario convention; avoid snippet collisions; organize stable parameterized/dynamic scenarios; and trace back from generated snippets to tests and Asciidoctor sections.

## References

- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/index.html): using `document(...)` and generating snippets by identifier.
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/reference/getting-started/index.html): configuring the output directory and test framework integration.
- [JUnit 5 User Guide — Display Names](https://junit.org/junit5/docs/current/user-guide/#writing-tests-display-names): setting test display names.
- [JUnit 5 User Guide — Nested Tests](https://junit.org/junit5/docs/current/user-guide/#writing-tests-nested): organizing tests with nested groups/classes.
- [JUnit 5 User Guide — Parameterized Tests](https://junit.org/junit5/docs/current/user-guide/#writing-tests-parameterized-tests): multiple invocations with parameterized data.
