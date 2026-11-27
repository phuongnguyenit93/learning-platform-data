# Designing Documentation So Implementation Changes Have Minimal Impact

API documentation typically needs to outlive a single version of a controller, service, or database schema. If REST Docs pages depend too tightly on class names, internal method names, package layout, or test fixture details from a single run, implementation changes that leave the API contract untouched can still force unnecessary documentation edits.

A sound design goal is **having documentation describe the contract clients consume, while allowing the implementation to be refactored independently as long as the contract stays intact**. Spring REST Docs supports this goal by generating HTTP examples and description tables from tests; authors choose the identifiers, descriptors, page composition, and how much internal detail is exposed. That boundary must be designed intentionally.

This lesson belongs to the **Documentation Model** chapter of the `SPRING_REST_DOCS` module. The module practices generating verifiable REST API documentation from MockMvc, WebTestClient, or REST Assured, producing snippets for requests, responses, payloads, parameters, and headers, and compiling Asciidoctor/Markdown in build and CI. This lesson focuses on documentation structures that remain resilient to implementation changes, controlling dependencies, and distinguishing internal changes from contract changes.

## 1. Learning Objectives

After this lesson, you can:

1. Distinguish implementation details from the public elements of an HTTP contract.
2. Design documentation pages around resources, operations, and behaviors observable by clients.
3. Choose identifiers and snippet structures that remain stable when controllers, services, or packages are refactored.
4. Separate fixtures, assertions, descriptors, and business explanations so each layer has a clear responsibility.
5. Identify which implementation changes require no documentation edits and which contract changes require updating tests and snippets.
6. Use helpers, templates, and includes judiciously to reduce duplication without hiding differences between endpoints.
7. Manage versioning, backward compatibility, and CI to detect API changes that impact clients.

## 2. The Key Boundary: Public Contract vs. Internal Implementation

An API may be implemented with an MVC controller, layered services, JPA repositories, a message broker, and a cache. Clients communicate solely through the HTTP contract published by the server: method, URI, query/path parameters, headers, payload, status, and field semantics.

For example, a client calls:

```http
GET /api/orders/42
Accept: application/json
```

and receives:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": 42,
  "status": "CONFIRMED",
  "total": 189000,
  "currency": "VND"
}
```

Contract elements may include:

- `GET /api/orders/{orderId}` is the operation for reading an order.
- `orderId` identifies an order according to published public rules.
- A successful response contains fields `id`, `status`, `total`, and `currency` with the documented types and meanings.
- Error statuses and the conditions that trigger them are clearly defined.
- Access permissions, currency rules, and status semantics are described in business terms.

The following typically belong to the internal implementation:

- Whether the controller is named `OrderController` or `PurchaseController`.
- Whether the Java method is named `getOrder` or `findById`.
- How many layers the service is split into.
- Whether the repository uses JPA, JDBC, or calls another service.
- Internal packages, modules, variable names, and caching strategies.
- Whether data is fetched in one query or multiple queries.

When those internal details change while HTTP behavior and semantics are preserved, public documentation should generally not change just because of a refactor.

| Detail | Part of the API contract? | Should it appear in client docs? |
| --- | --- | --- |
| HTTP method and URI | Yes | Yes |
| Path/query parameter names and meanings | Yes | Yes |
| Published request/response headers | Yes | Yes |
| JSON fields, types, nullability, and semantics | Yes | Yes |
| HTTP statuses and trigger conditions | Yes | Yes |
| Permissions, limits, side effects, and retry semantics | Yes, if a commitment clients need to know | Yes |
| Controller/service/repository names | Usually not | No, except in separate internal architecture docs |
| Database table/column names | Usually not | No |
| Number of internal classes or cache algorithms | No | No |
| Fixture classes or test method names | No | No |

**Principle:** public REST API documentation should help clients use a stable interface, not force clients to understand how the server is organized internally.

## 3. Organizing Documentation Around Resources and Operations

A durable structure starts from how clients view the API, not the application's package diagram.

Example content hierarchy:

```text
API Reference
├── Overview
│   ├── Base URL
│   ├── Authentication
│   ├── Error conventions
│   └── Pagination
├── Orders
│   ├── Look up an order
│   ├── Create an order
│   ├── Update an order
│   └── Cancel an order
└── Products
    ├── Look up a product
    └── Search products
```

Each operation page should answer: what does the client call, what must it send, what outcomes can the server return, what do the fields mean, and what business conditions apply? This structure remains meaningful even if a controller is renamed or an endpoint moves to a different internal module.

### 3.1. Separating Shared Content from Operation-Specific Content

Content that can be shared:

- Authentication rules and token transmission.
- Common error format.
- Timestamp, currency, and identifier conventions.
- Pagination, sorting, and filtering.
- Retry or idempotency policies if applied broadly.
- Request correlation headers.

Operation-specific content:

- Meaning of path/query parameters.
- Request payloads and response fields.
- Specific statuses of the operation.
- Business conditions, permissions, and side effects of that action.

An overview page can explain the standard error format. The `POST /api/orders` page only needs to specify which error codes apply to that request and link back to the error conventions section. Avoid copying the same generic rule paragraph onto every page; when policy changes, copies in many places easily drift out of sync.

### 3.2. Do Not Couple Documentation Structure to Package Structure

Example initial implementation:

```text
com.example.orders
├── web/OrderController.java
├── service/OrderService.java
└── persistence/OrderRepository.java
```

After refactoring to:

```text
com.example.sales
├── api/OrderResource.java
├── application/QueryOrder.java
└── adapter/OrderStore.java
```

If the HTTP contract has not changed, the `orders-get-success` pages, `orderId` description, and response fields table can stay untouched. Only test setup, imports, or fixtures might need updates to keep executing the same operation. Documentation should never include internal source paths like `com.example.orders.web.OrderController` as part of an endpoint definition.

## 4. Designing Stable, Reader-Friendly Identifiers

The identifier in `document("orders-get-success", ...)` is the link key from a test to a snippet directory. Name it after the public resource, action, and scenario:

```text
<resource>-<method-or-action>-<scenario>
```

Examples:

| Identifier | Purpose |
| --- | --- |
| `orders-get-success` | Read order successfully |
| `orders-get-not-found` | Order not found |
| `orders-create-success` | Create order successfully |
| `orders-create-invalid` | Invalid order creation data |
| `orders-cancel-conflict` | Order cancellation hit a state conflict |

Avoid tying identifiers to test class/method names or internal controller names, such as `order-controller-getOrder-test`. If the test moves to another suite or the controller is renamed, the snippet name would change even though the public operation remains the same.

Stable identifiers also do not mean forcing the same name when the contract fundamentally changes. If a public operation is changed or split into different behaviors, re-evaluate its name and all related includes.

### 4.1. Distinguishing Identifier Names from Fixtures

A test currently uses ID 42, and later the fixture changes to 1001 to avoid data collisions. As long as the operation is still “read order successfully”, the identifier `orders-get-success` remains appropriate. Do not name it `orders-get-42` merely because of a specific fixture value.

Values inside snippets may change between runs when sample data changes. If you want stable examples, control fixtures or normalize presentation data; do not turn operation names into copies of test data.

## 5. Designing Tests and Descriptors Around the Contract

Tests should produce HTTP behavior and check what matters to clients. Descriptors describe elements appearing in requests/responses and generate snippet tables. Implementation setup should be isolated from the operation definition.

### 5.1. MockMvc Test Example

Suppose the API publishes an order response:

```json
{
  "id": 42,
  "status": "CONFIRMED",
  "total": 189000,
  "currency": "VND"
}
```

The documentation test could look like:

```java
@Test
void getOrder_success() throws Exception {
    mockMvc.perform(
            get("/api/orders/{orderId}", 42L)
                .accept(MediaType.APPLICATION_JSON)
        )
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value(42))
        .andExpect(jsonPath("$.status").value("CONFIRMED"))
        .andExpect(jsonPath("$.currency").value("VND"))
        .andDo(document("orders-get-success",
            pathParameters(
                parameterWithName("orderId")
                    .description("Order identifier")
            ),
            responseFields(
                fieldWithPath("id")
                    .type(JsonFieldType.NUMBER)
                    .description("Order ID"),
                fieldWithPath("status")
                    .type(JsonFieldType.STRING)
                    .description("Business status"),
                fieldWithPath("total")
                    .type(JsonFieldType.NUMBER)
                    .description("Total amount per the API's financial rules"),
                fieldWithPath("currency")
                    .type(JsonFieldType.STRING)
                    .description("Currency code")
            )
        ));
}
```

For `pathParameters(...)` to read `{orderId}` in the URI template, use Spring REST Docs' `RestDocumentationRequestBuilders.get`. The test must be configured with `RestDocumentationExtension` or the appropriate setup for the test client in use.

Details such as whether `mockMvc` is initialized with standalone setup or an application context, or whether services are mocked or real, belong to **test configuration**. You can change them during refactoring to expand test scope without changing the API description if the HTTP contract stays the same.

### 5.2. Keep Descriptors Focused on Public Semantics

Avoid describing a field in internal terms:

```java
fieldWithPath("total")
    .description("Value fetched from column ORD_TOT in table ORDERS")
```

This style leaks database details and locks documentation to internal schemas. Describe it in concepts clients need to understand:

```java
fieldWithPath("total")
    .type(JsonFieldType.NUMBER)
    .description("Total order amount in the specified currency unit")
```

If clients need to know whether `total` includes taxes/fees or how rounding works, state it clearly in contract prose and back it with appropriate business tests. Never substitute database column names for semantics.

### 5.3. Extract Reusable Test Setup

You can use base configurations, fixture builders, or helpers to reduce repetition when multiple operations share an environment. However, helpers must never obscure important differences between requests or responses.

Good candidates for reuse:

- Initializing the Spring REST Docs extension.
- Configuring MockMvc/WebTestClient.
- Fixture builders for resources with valid data.
- Truly identical shared descriptors, such as trace headers or fields in a standard error envelope.

Do not lump every operation into an opaque helper taking multiple boolean flags like `isSuccess`, `isAdmin`, `useLegacyPayload` if that makes it unclear which behavior a test documents. Keep tests concrete; helpers should only remove repetitive setup.

## 6. Writing Documentation Sources Without Exposing Implementation Details

An AsciiDoc page can maintain a stable structure:

```asciidoc
[[orders-get]]
=== Look up an order

Retrieve the current representation of an order that the caller is authorized to access.

==== Request
include::{snippets}/orders-get-success/http-request.adoc[]

==== Path parameters
include::{snippets}/orders-get-success/path-parameters.adoc[]

==== Successful response
include::{snippets}/orders-get-success/http-response.adoc[]

==== Response fields
include::{snippets}/orders-get-success/response-fields.adoc[]

==== Not found
include::{snippets}/orders-get-not-found/http-response.adoc[]
```

The page describes public concepts. Do not write “the controller calls OrderService and then OrderRepository queries table ORDERS” inside an API Reference. If the engineering team needs that information, it belongs in internal architecture docs or developer guides with a different audience.

### 6.1. Structure Sections Around Client Questions

A maintainable layout:

1. **Purpose:** What is the resource/operation for?
2. **Conditions:** Who can call it, input constraints, and preconditions?
3. **Request:** HTTP example, path/query parameters, headers, body.
4. **Response:** Status, headers, body, and fields.
5. **Errors:** Meaningful error responses and how to handle them.
6. **Business rules:** States, units, idempotency, side effects.
7. **Links:** General conventions or related operations.

Do not repeat every section if inapplicable; for instance, a `GET` with no request body should not include an empty request fields table.

### 6.2. Use Attributes and Includes Instead of Absolute Paths

Using `{snippets}` allows changing the output directory via build configuration without editing every page. Never hardcode personal machine paths or absolute paths such as `C:/workspace/project/build/generated-snippets`.

Also centralize attribute declarations in the compilation task so pages only reference `{snippets}/<identifier>/<file>`. If outputs move from Gradle to Maven or a module build folder changes, the edit stays in build configuration instead of touching dozens of source pages.

## 7. Distinguishing Internal Refactors from Contract Changes

Not every code change has the same documentation impact. The matrix below helps determine what to do:

| Change | Can the HTTP contract stay intact? | Typical documentation impact |
| --- | --- | --- |
| Rename a controller or Java method | Yes | No page/identifier edits needed if tests still describe the same operation |
| Move packages or modules | Yes | Update imports/test setup; snippets and pages can remain unchanged |
| Swap JPA for JDBC or another HTTP client | Yes | No documentation edits needed if observable behavior does not change |
| Split a service into multiple components | Yes | No client documentation edits needed |
| Change caching implementation | Yes | No documentation edits needed if semantics stay intact |
| Change URI or HTTP method | No, usually a breaking/contract change | Update pages, tests, identifiers if appropriate, and migration notes |
| Rename or change JSON field type | Impacts the contract | Update descriptors, tests, snippets, and pages; assess compatibility |
| Change error status or error conditions | Impacts the contract | Update test cases and prose explanations |
| Change meaning of `total` while keeping numeric type | Impacts semantics | Update prose explanations and business tests |
| Change access permissions | Impacts public behavior | Update security tests, error cases, and permission docs |
| Add a required request header for clients | Impacts request contract | Update request tests, descriptors, examples, and guides |

### 7.1. The “Would a Client Notice?” Test

Before deciding whether documentation must change, ask:

- Must the client change the method, URL, headers, payload, or response parsing?
- Is there a new status or error condition the client must handle?
- Did a field's meaning change even though its name and type stayed the same?
- Did auth, retry, idempotency, or side-effect rules change?
- Is a behavior clients rely on no longer guaranteed?

If any answer is yes, it is likely a contract change that must be documented. If the change lies solely in how the server organizes classes without altering what clients observe or are promised, the API Reference normally does not need changes.

### 7.2. Example of Changing Implementation While Keeping Documentation Unchanged

Before refactor:

```java
@GetMapping("/api/orders/{id}")
OrderDto find(@PathVariable long id) {
    return orderService.find(id);
}
```

After refactor:

```java
@GetMapping("/api/orders/{orderId}")
OrderRepresentation query(@PathVariable long orderId) {
    return queryOrder.execute(orderId);
}
```

If the URI mapping, response, status, headers, and public semantics truly stay identical, the documentation content can stay the same. However, variable names in the URI template or how a builder preserves templates can affect path parameter descriptors. Ensure tests still record the same path contract `{orderId}` or update descriptors to match the real template. Never ignore a test failure simply because you consider the change an internal refactor.

## 8. Keeping Snippets Resilient When Implementation Changes

Snippets are test outputs, so output can change if fixture setup or test environments shift. To reduce meaningless churn:

- Use deterministic and independent fixtures.
- Normalize timestamps, hostnames, ports, or request IDs when they are not what is being illustrated.
- Avoid leaking class names, stack traces, or internal error messages in public responses.
- Name identifiers after public operations, not test class names.
- Document only headers and fields belonging to the contract.
- Keep assertions checking important business values rather than recording responses without verification.

Spring REST Docs supports preprocessors like `preprocessRequest(prettyPrint())` and `preprocessResponse(prettyPrint())`. You can use preprocessors to format JSON, replace dynamic data, or strip sensitive headers from snippets. Preprocessing must never turn a broken response into a healthy-looking example; assertions must run against the actual result before documenting.

### 8.1. Do Not Leak Internal Details into Output Accidentally

For example, an error response should not expose stack traces:

```json
{
  "code": "ORDER_NOT_FOUND",
  "message": "Order not found"
}
```

Avoid returning responses like:

```json
{
  "exception": "com.example.orders.persistence.OrderNotFoundException",
  "sql": "select * from orders where id = ?",
  "message": "..."
}
```

If the real application is leaking internal details, fix the implementation and error contract before generating public docs. Scrubbing data inside snippets prevents publishing secrets, yet it does not replace fixing the real response if that leak is a vulnerability or contract violation.

## 9. Reusing Helpers and Templates Without Losing Specificity

When there are many operations, helpers can build common descriptors:

```java
static RequestHeadersSnippet commonRequestHeaders() {
    return requestHeaders(
        headerWithName("Accept")
            .description("Media type accepted by the client"),
        headerWithName("X-Request-Id")
            .description("Correlation ID if provided by the client")
            .optional()
    );
}
```

Then reuse them across multiple tests:

```java
.andDo(document("orders-get-success",
    commonRequestHeaders(),
    pathParameters(/* specific descriptors */),
    responseFields(/* specific descriptors */)
));
```

This is an example of a test helper; adjust imports and snippet types for your REST Docs version. Share helpers only when headers and semantics are genuinely identical across those endpoints. A header that is required on `POST` but optional on `GET` should not be forced into a shared helper that makes documentation inaccurate.

Asciidoctor templates can also be reused to keep layouts consistent. Yet a template should not force every endpoint to display the same response/error sections if an endpoint does not support them. Reuse reduces duplication, while specifics must remain clear in tests and pages.

## 10. Versioning and Backward Compatibility

When the contract must change, decide whether the change is backward-compatible and how clients transition.

Examples:

| Change | Typical compatibility risk | Documentation action |
| --- | --- | --- |
| Add an optional response field | Usually low for clients ignoring unknown fields, though not all clients do | Update schema/examples and explicitly note the new field |
| Remove a required field | High | Requires migration/versioning and change documentation |
| Change a field's type | High | Publish a new version or clear migration guidance |
| Change field semantics without changing type/name | Very high because clients see no shape change | Clearly explain new semantics and how clients adapt |
| Add an optional query parameter | Usually low | Document the default and behavior when provided |
| Add a required request header | High for older clients | Publish applicability conditions and upgrade steps |
| Add a new error status | Clients may not handle it yet | Add error scenario and retry/display rules |

If multiple API versions exist, organize documentation by version or separate output directories accordingly. Never include a v2 snippet into a v1 page just because two operations have similar names. Version structures and attributes must stay explicit so schemas never mix.

### 10.1. Migration Guides Are Part of Contract Change Documentation

For breaking changes, documenting the new endpoint alone is not enough. Clients on older versions need to know:

- What changed?
- When or in which version does the change take effect?
- How must clients update request/response handling?
- Is there a parallel-run window or deprecation deadline for the old version?
- Are there before/after examples for key operations?

This information usually lives in release notes or a separate migration guide linked from the API Reference.

## 11. CI Helps Guard Documentation Boundaries

The pipeline should run snippet-generating tests before rendering:

```text
Checkout source
      │
      ▼
Clean generated output
      │
      ▼
Run HTTP documentation tests
      │
      ├── Assertion/descriptor failure → Fail
      │
      ▼
Generate snippets
      │
      ▼
Render Asciidoctor/Markdown
      │
      ├── Missing include/link → Fail
      │
      ▼
Review public content and compatibility
      │
      ▼
Publish API docs
```

Items to verify in CI:

1. Did documentation tests actually run without being accidentally skipped?
2. Does the output directory match configuration?
3. Do identifiers and includes point to freshly generated snippets?
4. Do tests fail when public responses drift from assertions or descriptors?
5. Do pages render from sources and snippets of the same build?
6. Does output contain internal hostnames, tokens, or implementation details?
7. Did contract changes update release/migration notes when needed?

CI catches many technical linking errors, yet cannot evaluate the full meaning of every change automatically. Code and contract reviews are still necessary to verify whether a refactor accidentally altered behavior and what clients need to be told.

## 12. Common Mistakes and How to Fix Them

| Symptom | Cause | How to fix |
| --- | --- | --- |
| Renaming a controller forces edits across many pages | Identifiers/includes depend on internal class names | Switch identifiers to public resource/method/scenario |
| Database refactoring changes API descriptions | Descriptors explain things by column/table | Write descriptions using client-facing semantics |
| Test renames identifier, page cannot find snippet | Includes still hold the old path | Update identifier and includes in the same change |
| New test overwrites an old snippet | Two operations share an identifier | Split by scenario; check parallel test execution |
| Snippets change on every build | Unstable fixtures or dynamic values | Control fixtures and preprocessors |
| Shared helper gives endpoints inaccurate descriptions | Forced endpoint specifics into a shared template | Only reuse parts with genuinely identical contracts |
| Documentation contains stack traces or class names | Error responses or snippets expose internals | Fix public responses, scrub outputs, and add checks |
| Semantic change does not fail any test | Tests only check types/statuses | Add business assertions and update prose |
| Version 1 page uses version 2 response | Overlapping attributes/output directories | Separate outputs and includes by version |
| Refactor leaves tests unrepresentative of the system | Test setup is too isolated | Add appropriate integration tests and state scope clearly |
| CI renders from stale snippets | Output not cleaned or wrong task dependency | Clean outputs, run tests, then render |

## 13. Hands-On Exercise: Refactor Implementation While Preserving the Contract

Suppose an API publishes the `GET /api/orders/{orderId}` operation with:

- A `200` response having `id`, `status`, `total`, and `currency`.
- A `404` response following a common error schema.
- Clear business documentation for path parameter `orderId`.
- Snippets stored under `orders-get-success` and `orders-get-not-found`.

The team plans to restructure internals from controller/service/repository to resource/application/adapter, replace JPA with JDBC, and rename fixture classes. The HTTP contract is intended to remain unchanged.

### Tasks

1. List the internal details that can change without affecting the contract.
2. Rerun documentation tests and confirm statuses, headers, payloads, and fields still satisfy assertions and descriptors.
3. Keep identifiers unchanged if the public operation has not changed.
4. Inspect new snippet outputs; distinguish diffs caused solely by request IDs/timestamps from contract diffs.
5. Update fixtures/preprocessors only if sample data became unstable; leave public descriptions unchanged if semantics stayed intact.
6. Next, try changing the type of `total` from number to string. Identify which tests/descriptors must fail and which documentation must be updated.
7. Write a migration note describing client impact if that type change were approved.

### Completion Criteria

- Internal refactors do not force unnecessary edits to the API Reference.
- Tests still protect requests and responses per the contract.
- Identifiers and includes remain stable without pointing to stale outputs.
- Changes that genuinely impact clients are detected and documented.
- Unnecessary implementation details never leak into public documentation.

## 14. Takeaways

- Design documentation around **the HTTP contract and the client's perspective**, not internal class names, packages, services, or database schemas.
- Tie identifiers to **resource, method/action, and scenario** so tests can move without breaking documentation pages as long as the operation stays the same.
- Keep clear boundaries between test setup, fixtures, descriptors, and business explanations; reuse helpers only for parts whose contract is genuinely identical.
- Distinguish implementation refactors from changes to methods, URIs, statuses, headers, schemas, semantics, permissions, or side effects.
- When the contract changes, update tests, descriptors, snippets, pages, and migration guidance; when only the implementation changes, still run tests to confirm public behavior is preserved.
- CI regenerates documentation and verifies links; contract reviews remain necessary to evaluate compatibility and client impact.
