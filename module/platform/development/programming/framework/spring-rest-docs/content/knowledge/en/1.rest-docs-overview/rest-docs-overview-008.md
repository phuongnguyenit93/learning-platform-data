# HTTP, REST, JSON, Testing, and Build Prerequisites

## Learning Objectives

Before practicing Spring REST Docs, learners need enough background to read an HTTP exchange, understand REST resource structure, recognize JSON requests/responses, write tests with assertions, and run a build process. After this lesson, you will be able to:

- Analyze the method, URI, status code, headers, and body of an HTTP request/response.
- Understand common REST principles: resources, representations, statelessness, idempotency, caching, and content negotiation.
- Read and describe JSON, including objects, arrays, data types, nested fields, optional values, and `null`.
- Write basic HTTP tests with JUnit and an appropriate tool such as MockMvc, WebTestClient, or REST Assured.
- Understand the role of assertions, fixtures, test isolation, test data, and success/failure scenarios.
- Identify required build inputs: dependencies, plugins, tasks, output directories, and running tests before generating documentation.

## 1. Prerequisite Knowledge Map

Spring REST Docs sits at the intersection of HTTP testing and technical documentation. You do not need to be a computer networking expert, but you do need to understand requests and responses to know what snippets capture and which assertions are meaningful.

| Foundation | What to Know | Where It Is Used in REST Docs |
| --- | --- | --- |
| HTTP | Method, URI, status, headers, body, media type | Reading and recording request/response snippets |
| REST | Resources, URIs, method semantics, statelessness, idempotency | Understanding API contracts and examples |
| JSON | Objects, arrays, field paths, data types, null, nested data | Writing request/response field descriptors |
| Java and Spring | Controllers, DTOs, serialization, exception handling | Understanding how the tested app processes requests |
| Testing | JUnit, assertions, fixtures, test isolation | Writing repeatable documentation tests |
| Build | Dependencies, plugins, tasks, output directories, CI | Automating snippet generation and doc rendering |
| Technical writing | Headings, tables, code blocks, AsciiDoc/Markdown | Combining snippets with explanations for API users |

You do not need to learn every bit of theory before starting a small hands-on exercise. Understand requests and responses first, write a passing HTTP test, generate one snippet, and then expand to parameters, headers, payloads, and error scenarios.

## 2. HTTP Foundations

HTTP is a request/response protocol between client and server. When reading REST API documentation, first identify four parts: **request line, request headers, request body**, and the corresponding parts of the response.

### 2.1. What Makes Up an HTTP Request?

Example of a client requesting order details:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Accept: application/json
Authorization: Bearer <access-token>
```

- `GET` is the method.
- `/api/orders/42` is the request target/path.
- `Host` identifies the target host in HTTP/1.1.
- `Accept` tells the server which representation type the client prefers.
- `Authorization` carries credentials according to the mechanism defined by the API.
- The request has no body in this example; other methods may include a body.

An order creation request might look like:

```http
POST /api/orders HTTP/1.1
Content-Type: application/json
Accept: application/json

{"customerId":7,"quantity":2}
```

`Content-Type` describes the format of the body being sent; `Accept` describes the response format the client can receive. Do not confuse these two headers.

### 2.2. What Makes Up an HTTP Response?

```http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/orders/43

{"id":43,"status":"CREATED"}
```

- `201 Created` is the status line, indicating a new resource was created per HTTP semantics.
- `Content-Type` describes the media type of the response body.
- `Location` typically points to the URI associated with the newly created resource in this scenario.
- A blank line separates headers from the body.
- The JSON below is the representation the client reads.

In Spring REST Docs, these elements can be represented through snippets such as `http-request`, `http-response`, `request-headers`, and `response-headers`.

### 2.3. Methods and Properties to Understand

| Method | Common Meaning | Characteristics to Watch |
| --- | --- | --- |
| `GET` | Retrieve a representation of a resource | Safe; should not be used to request business state changes |
| `POST` | Submit data for processing or create a resource under a collection | Not idempotent by default |
| `PUT` | Create/replace the representation at the target URI per contract | Defined as idempotent |
| `PATCH` | Apply a partial update | Idempotency depends on semantics and design |
| `DELETE` | Request deletion of a resource | Defined as idempotent per HTTP semantics, even if responses across calls differ |

**Safe** means the method is defined not to request state changes on the resource; **idempotent** means repeating the same request has the intended effect of executing it once. These are method semantics, not a guarantee that every implemented endpoint has no unintended side effects.

When documenting, describe the actual method and behavior committed by the API. Do not conclude that `POST` always creates new data or that every `PUT` operation replaces the entire object unless the specific contract defines it that way.

### 2.4. Status Codes and Groupings

| Group | General Meaning | Examples |
| --- | --- | --- |
| `1xx` | Informational/provisional | `100 Continue` |
| `2xx` | Request accepted or processed successfully | `200 OK`, `201 Created`, `202 Accepted`, `204 No Content` |
| `3xx` | Redirection or cache handling | `301 Moved Permanently`, `304 Not Modified` |
| `4xx` | Client/request cannot be processed as sent | `400 Bad Request`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`, `409 Conflict`, `429 Too Many Requests` |
| `5xx` | Server or intermediary failure | `500 Internal Server Error`, `502 Bad Gateway`, `503 Service Unavailable` |

Do not document only success statuses. API consumers need to know meaningful error cases, error response bodies, retryability, and corrective actions if specified by the API. For instance, `401` and `403` are not synonymous: `401` relates to missing/required authentication, whereas `403` indicates the request is denied due to permissions in HTTP terms.

### 2.5. Headers, Media Types, and Content Negotiation

Headers carry metadata about requests and responses. Common headers include:

| Header | Direction | Purpose |
| --- | --- | --- |
| `Accept` | Request | Representation type the client wants to receive |
| `Content-Type` | Request/Response | Media type of the body being sent/received |
| `Authorization` | Request | Credentials according to the auth scheme |
| `Location` | Response | URI associated with a resource or redirect target |
| `Cache-Control` | Request/Response | Caching directives |
| `ETag` | Response | Validator for a representation |
| `If-Match` | Request | Conditional update based on a validator |

For example, `Accept: application/json` indicates the client wants JSON. If the server supports multiple formats, content negotiation can affect the response; tests must send the appropriate headers to record the right scenario. Never place real tokens or sensitive cookies in published snippets.

## 3. REST Foundations

REST is a set of architectural constraints for distributed systems. An API is not RESTful simply because it uses JSON or URLs with slashes.

Useful concepts when reading API docs:

- **Resource:** a concept or object managed by the system, such as an order or customer.
- **URI:** resource identifier, e.g., `/api/orders/42`.
- **Representation:** data representing a resource at a point in time, e.g., JSON containing `id` and `status`.
- **Statelessness:** each request carries enough context for the server to process it; the server does not implicitly depend on client session state between requests as an application-protocol condition.
- **Cacheability:** responses can indicate whether a representation may be cached and under what conditions.
- **Uniform interface:** clients interact through a consistent interface grounded in resources, representations, methods, and semantics.
- **Layered system:** clients do not necessarily know all intermediary layers handling a request.

### 3.1. Resources and URIs

URIs typically name resources, while methods express actions:

| URI | Method | Illustrative Meaning |
| --- | --- | --- |
| `/api/orders` | `GET` | List/search orders per API rules |
| `/api/orders` | `POST` | Create a new order |
| `/api/orders/42` | `GET` | Retrieve order with ID 42 |
| `/api/orders/42` | `PUT` | Replace the representation at the resource per contract |
| `/api/orders/42` | `DELETE` | Request deletion of the order |

Path parameters and query parameters play different roles:

- Path `/api/orders/42` identifies a specific order.
- Query `/api/orders?page=0&size=20` expresses query/pagination criteria per API design.

REST Docs can generate `path-parameters` and `query-parameters` snippets when tests declare descriptors for those parameters.

### 3.2. Statelessness, Authentication, and Retries

Statelessness does not mean an API needs no authentication. A request can carry a bearer token in `Authorization`; the server verifies each request independently based on the credentials and current policy.

Retries must be designed carefully. Having idempotent method semantics does not eliminate every risk from timeouts, async processing, or network failures. If an API supports `Idempotency-Key`, documentation must state how to send it, its scope of validity, and what happens when the same key is sent repeatedly. Never assume every `POST` endpoint is safe to retry.

### 3.3. Caching and Validators

Some APIs use `Cache-Control`, `ETag`, `Last-Modified`, `If-None-Match`, or `If-Modified-Since` to support caching and conditional requests. When these behaviors are part of the contract, include corresponding tests and snippets for headers/statuses rather than only showing JSON examples.

## 4. JSON Foundations

JSON is a text format for representing structured data. In REST APIs, it commonly appears in request and response bodies with media type `application/json`.

### 4.1. Basic Data Types

```json
{
  "id": 42,
  "name": "Notebook",
  "active": true,
  "discount": null,
  "tags": ["office", "stationery"],
  "price": {
    "amount": 59000,
    "currency": "VND"
  }
}
```

| Syntax | JSON Type | Notes |
| --- | --- | --- |
| `42` | Number | JSON does not distinguish int/long/decimal; exact rules depend on schema and client |
| `"Notebook"` | String | Strings enclosed in double quotes |
| `true`, `false` | Boolean | Not enclosed in quotes |
| `null` | Null | Explicit empty value, distinct from omitting a field |
| `[]` | Array | List of values, may be empty |
| `{}` | Object | Collection of key/value fields |

Common syntax errors: using single quotes, missing commas/braces, writing `NaN`, putting comments directly in JSON, or trailing commas after the last element. The example below is not valid JSON:

```text
{'id': 42,}
```

### 4.2. Nested Fields and Paths in REST Docs

Given JSON:

```json
{
  "orderId": "ord-42",
  "total": {
    "amount": 199000,
    "currency": "VND"
  },
  "items": [
    {"sku": "BOOK-01", "quantity": 2}
  ]
}
```

Commonly used descriptors:

| JSON Path | Description |
| --- | --- |
| `orderId` | Order ID |
| `total` | Total amount details |
| `total.amount` | Monetary value |
| `total.currency` | Currency code |
| `items` | List of order line items |
| `items[].sku` | Product SKU in a line item |
| `items[].quantity` | Quantity in a line item |

For nested objects, declare parent objects when the descriptor mode requires documenting the full structure; for arrays of objects, `[]` denotes array elements. Exact declarations must match the actual payload and the REST Docs API version in use.

### 4.3. Distinguishing Missing Fields, Null, and Default Values

The three cases below are different:

```json
{"name": "Lan"}
```

```json
{"name": "Lan", "nickname": null}
```

```json
{"name": "Lan", "nickname": ""}
```

- **Missing field:** the client does not receive the `nickname` key.
- **Null field:** the key is present with no value.
- **Empty string field:** the key is present and its value is `""`.

The contract must state clearly which fields are required, may be omitted, are nullable, have defaults, or may be empty strings. Do not equate `optional()` in REST Docs with nullable in a schema: `optional()` relates to whether a field may be absent from the tested payload being documented, whereas `null` is a value that must be considered per the contract.

## 5. Required Java and Spring Knowledge

To read documentation tests, learners should recognize:

- **Controller:** receives requests and routes them to application handlers.
- **DTO/record:** data types used to accept or return API information; not necessarily database entities.
- **Binding:** how Spring converts path/query parameters or request bodies into Java arguments.
- **Serialization/deserialization:** converting Java objects to HTTP representations and back, typically via Jackson in Spring Boot applications.
- **Validation:** validating inputs, e.g., `@Valid`, constraint annotations, and corresponding error handling.
- **Exception handling:** how exceptions are translated into status codes and error bodies, typically via `@ExceptionHandler` or `@ControllerAdvice`.
- **Filters/security:** layers that may reject requests before a controller executes.

Example DTOs:

```java
public record CreateOrderRequest(
        @NotNull Long customerId,
        @NotEmpty List<OrderItemRequest> items
) {}

public record OrderItemRequest(
        @NotBlank String sku,
        @Positive int quantity
) {}
```

DTOs and annotations help reveal the expected schema, yet HTTP tests confirm how the application actually responds to valid and invalid data at the tested layer. For example, the status and JSON structure of a validation error response depend on exception handler configuration.

## 6. Automated Testing Foundations

Spring REST Docs does not discover and run every request on its own. You need an active HTTP test simulating a scenario.

### 6.1. Unit Tests, MVC Tests, and Integration Tests

| Test Type | Typical Scope | When Used |
| --- | --- | --- |
| Unit test | A class/logic with dependencies replaced by mocks/fakes | Verifying small rules, calculations, and business validations |
| MVC/WebFlux test | Web infrastructure and controllers in a test environment | Verifying mapping, binding, HTTP responses, and generating snippets |
| Integration test | Multiple application components working together | Verifying wiring, serialization, database/security, or needed integrations |
| End-to-end test | Broad path through the app/server and potentially external dependencies | Verifying behavior closer to client experience, though usually slower |

No single test layer covers every commitment. If documentation describes a security error produced by a filter, the test must bring security filters into scope. A minimal MockMvc `standaloneSetup` may exclude those configurations.

### 6.2. Assertions and Repeatable Tests

An assertion is a condition a test requires to be true. For example:

```java
mockMvc.perform(get("/api/orders/{id}", 42))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value(42))
        .andExpect(jsonPath("$.status").value("PAID"));
```

This test checks three things: status, order ID, and order status. Calling an endpoint without assertions proves no contract. Checking only status `200` is also insufficient when clients depend on JSON fields.

Tests should be **repeatable** (producing deterministic results on re-runs) and **isolated** (not implicitly depending on test order or data created by another test). To achieve that:

- Create explicit fixtures with non-sensitive dummy data.
- Fix clocks or timestamped data where needed.
- Avoid depending on unstable external APIs in snippet-generating tests.
- Clean up or roll back data after tests according to test design.
- Test both empty-data results and invalid-input cases.

### 6.3. Documentation Tests Add Descriptors

Beyond assertions, a REST Docs test specifies the structure to publish:

```java
document("orders-get",
    pathParameters(
        parameterWithName("id").description("Order ID")
    ),
    responseFields(
        fieldWithPath("id").description("Order ID"),
        fieldWithPath("status").description("Order status")
    )
)
```

The snippet name `orders-get` becomes part of the output path. Descriptors do not replace assertions on business values: describing `status` as "Order status" does not prove the value `PAID` was applied correctly.

## 7. Test Clients You Will Encounter in Spring REST Docs

| Tool | Typical Fit | What to Prepare |
| --- | --- | --- |
| **MockMvc** | Spring MVC/Servlet | Spring MVC Test, JUnit, REST Docs MockMvc integration |
| **WebTestClient** | Spring WebFlux/reactive or supported test setups | WebTestClient, matching context/handler/server, REST Docs WebTestClient integration |
| **REST Assured** | HTTP integration tests targeting a running server | Server/port/fixtures, REST Assured, REST Docs REST Assured integration |

Choose the tool based on your stack and required scope of evidence:

- MVC controller tests can start with MockMvc.
- WebFlux reactive handlers commonly use WebTestClient.
- When you need to test requests over a real HTTP server in integration tests, REST Assured can fit; WebTestClient can also connect to a server in the appropriate mode.

You do not need all three in the same project. Test configuration determines whether requests flow through converters, security filters, exception handlers, or a real server.

## 8. Build Knowledge to Prepare

A build is the process of compiling, testing, and producing artifacts. With Spring REST Docs, the key rule is **tests generate snippets first, and documentation composition reads snippets afterward**.

### 8.1. Basic Build Concepts

| Concept | Meaning |
| --- | --- |
| Dependency | Library needed by source/test code, e.g., `spring-restdocs-mockmvc` |
| Plugin | Extends build tool tasks/capabilities, e.g., the Asciidoctor plugin |
| Task/phase | A unit of work or lifecycle stage in the build |
| Output directory | Folder storing intermediate outputs/artifacts, e.g., `build/generated-snippets` |
| Task dependency | Relationship requiring one task to run after another |
| CI | System automating build/test/render on commits or pull requests |

### 8.2. Why Does Test-Then-Render Order Matter?

```text
HTTP documentation tests
        |
        v
build/generated-snippets/
        |
        v
Asciidoctor / Markdown renderer
        |
        v
API documentation HTML
```

If Asciidoctor runs before snippets are created, include directives fail to find the files. If the renderer uses old snippets from a previous build, pages can become stale even though the current code has changed.

An illustrative Gradle configuration:

```groovy
configurations {
    asciidoctorExt
}

dependencies {
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
    asciidoctorExt 'org.springframework.restdocs:spring-restdocs-asciidoctor'
}

def snippetsDir = file("$buildDir/generated-snippets")

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    configurations 'asciidoctorExt'
    inputs.dir snippetsDir
    dependsOn tasks.named('test')
}
```

This is task-wiring illustration, not a complete `build.gradle`. The project still needs plugins, compatible dependency versions, JUnit/Spring Test, and the `snippets` attribute configured on the Asciidoctor task. If using WebTestClient or REST Assured, the REST Docs integration dependency corresponds to that test client.

With Gradle, once fully configured you can run:

```bash
./gradlew clean test asciidoctor
```

On Windows:

```bat
gradlew.bat clean test asciidoctor
```

With Maven, you must likewise coordinate snippet-generating tests and the Asciidoctor rendering plugin in the proper order. Do not assume Maven output paths or configuration match Gradle; inspect the actual project configuration.

### 8.3. CI and Artifact Quality

CI can run:

1. Compile source and test code.
2. Run HTTP documentation tests.
3. Verify snippets for required scenarios were generated.
4. Render documentation.
5. Check for include/output errors and archive the HTML artifact.
6. Publish documentation alongside the API version/commit.

Clean builds prevent stale outputs; dummy test data prevents leaking sensitive info; include checks prevent publishing pages with missing snippets. Not every renderer configuration treats missing includes as errors by default, so verify it with an actual build.

## 9. AsciiDoc, Markdown, and Composition Knowledge

Auto-generated snippets are documentation fragments. Authors must know how to organize headings, tables, explanatory paragraphs, and code blocks to assemble a readable page.

AsciiDoc commonly uses directives like:

```asciidoc
== HTTP response
include::{snippets}/orders-get/http-response.adoc[]
```

The `{snippets}` attribute must point to the right output directory. Asciidoctor processes `include::...[]` and renders the page; it does not run HTTP tests.

Markdown can be used if compatible snippet templates are configured and the composition system supports merging content. Standard Markdown lacks Asciidoctor's include syntax. Do not rename `.adoc` files to `.md` without changing how files are generated and combined.

In human-written prose, describe:

- Endpoint purpose and when to call it.
- Authentication and authorization prerequisites.
- Field semantics, enums, units, and default values.
- Error handling, retries, pagination, or idempotency if committed by the API.
- API version and compatibility notes.

## 10. Suggested Learning Path

Learners can track progress through these steps:

| Step | Practice Task | Expected Outcome |
| --- | --- | --- |
| 1 | Read an HTTP request/response | Identify method, URI, headers, status, body |
| 2 | Read nested JSON objects/arrays | Write JSON paths for fields to document |
| 3 | Write a test with JUnit and MockMvc | Send request, assert status and response |
| 4 | Add Spring REST Docs descriptors | Generate request/response/field snippets |
| 5 | Write an AsciiDoc page with includes | Render HTML containing explanations and snippets |
| 6 | Add a test for an error scenario | Documentation includes examples for key failure paths |
| 7 | Run build from a clean workspace | Tests and rendering run in the proper order |
| 8 | Integrate into CI | Every relevant change is checked automatically |

### Foundational Gaps to Fix Before Moving Forward

| Symptom | Topic to Review |
| --- | --- |
| Confusing `Accept` with `Content-Type` | HTTP headers and content negotiation |
| Not distinguishing `201` from `202` | HTTP semantics and status codes |
| Unsure how to document `items[].sku` | JSON arrays, objects, and field paths |
| Asserting only status while ignoring body | Contract-driven test and assertion design |
| Unsure why snippets were not generated | JUnit lifecycle, REST Docs config, and test output |
| Asciidoctor cannot find include files | Build task ordering and output directories |
| Docs contain real tokens or real data | Test fixtures, security, and artifact management |

## 11. Self-Check Exercise

Suppose an application has the `POST /api/orders` endpoint, request:

```http
POST /api/orders HTTP/1.1
Content-Type: application/json
Accept: application/json

{"customerId":7,"items":[{"sku":"BOOK-01","quantity":2}]}
```

Response:

```http
HTTP/1.1 201 Created
Location: /api/orders/43
Content-Type: application/json

{"id":43,"status":"CREATED"}
```

Answer the following:

1. What are the method, path, media types, request fields, and success status?
2. Which headers need descriptors if you want to document both request and response headers?
3. Write the assertions needed to verify status, `Location`, `id`, and `status`.
4. Choose `requestFields(...)` and `responseFields(...)` to describe the JSON fields.
5. Propose at least two error scenarios clients need to know; do not guess status codes without a defined contract.
6. State which task must run before Asciidoctor and why.

**Extension question:** The current test returns status `201` and the right body. Does that prove a request cannot create duplicate orders when a client retries? No. Making that guarantee requires defining idempotency semantics and writing tests covering repeated requests.

## Conclusion

To learn Spring REST Docs effectively, you need **HTTP and REST** to read contracts, **JSON** to describe payloads, **Java/Spring** to understand how requests flow through the app, **JUnit and assertions** to write repeatable tests, and **build/Asciidoctor/CI** to generate and publish documentation. These foundations help separate executed requests/responses from business explanations. Spring REST Docs links HTTP tests using MockMvc, WebTestClient, or REST Assured with descriptors and snippets; Asciidoctor/Markdown completes the page. Trustworthy documentation requires not just syntactically valid examples, but testing at the right scope, covering important scenarios, and building from the exact API version.
