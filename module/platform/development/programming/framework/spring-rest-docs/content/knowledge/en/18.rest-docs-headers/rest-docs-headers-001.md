# Documenting Request Headers with requestHeaders

## 1. Lesson Objectives

In the **SPRING_REST_DOCS** module, REST API documentation is generated from runnable and verifiable HTTP tests. A test sends a request, asserts the response, and then Spring REST Docs generates snippets for the request, response, payload, parameters, and headers. Asciidoctor/Markdown assembles the snippets into documentation, and then the build and CI verify the documentation alongside the source code.

The **Headers** chapter focuses on metadata passed in HTTP. Request headers indicate what content types the client wants to receive, what format it sends data in, how it authenticates, or what tracing information it provides. If the documentation does not clearly explain the headers that belong to the API contract, users may call the right URI and still get errors due to missing headers or sending the wrong format.

This lesson shows how to use `requestHeaders(...)` from Spring REST Docs to describe request-side headers. After this lesson, you will be able to:

- Declare headers to be documented using `headerWithName(...)`.
- Use `requestHeaders(...)` inside `document(...)` to generate `request-headers.adoc`.
- Understand how descriptors validate actual headers against the documented contract.
- Document required headers, optional headers, and headers excluded from the documentation table.
- Combine WebTestClient, JUnit 5, and Spring REST Docs in a complete test.
- Include header snippets in an Asciidoctor page and ensure CI regenerates documentation from tests.

## 2. What Are Request Headers and Why Document Them?

An HTTP request consists of a method, a URI, headers, and optionally a body. Headers carry metadata that affects how the server receives or processes the request. For example:

~~~http
POST /api/orders HTTP/1.1
Host: api.example.test
Accept: application/json
Content-Type: application/json
X-Request-Id: req-001

{"productId":"BOOK-01","quantity":2}
~~~

In the example:

| Header | Meaning |
| --- | --- |
| `Accept` | The response types the client can accept. |
| `Content-Type` | The data type of the request body. |
| `X-Request-Id` | A custom header used for request tracing. |
| `Authorization` | Authentication credentials if required by the API. |
| `If-Match` | An ETag-based condition, commonly used in version-controlled updates. |

Not every endpoint needs every header. Documentation should only describe headers that belong to the operation's contract: required headers, optional headers, and headers that are meaningful to the client.

Spring REST Docs uses descriptors to define which headers should be documented. When a test runs, the library checks the descriptors against the actual request and generates the header table. As a result, the documentation serves both as an API usage guide and as part of contract testing.

## 3. `headerWithName(...)` and `requestHeaders(...)`

The two main APIs come from `HeaderDocumentation`:

~~~java
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
~~~

`headerWithName(name)` creates a descriptor for a header. Call `.description(...)` to explain what purpose the header serves:

~~~java
headerWithName("X-Request-Id")
    .description("Unique ID used to trace the request");
~~~

`requestHeaders(...)` accepts one or more descriptors and passes them into `document(...)`:

~~~java
document("orders/create",
    requestHeaders(
        headerWithName("X-Request-Id")
            .description("Request tracing ID"),
        headerWithName("Content-Type")
            .description("JSON format of the request body")
    )
)
~~~

When the test generates snippets successfully, Spring REST Docs creates the `request-headers.adoc` file in the operation's directory. The table in the file typically has columns for the header name and description.

~~~mermaid
flowchart LR
    A["WebTestClient sends request"] --> B["REST Docs captures HTTP operation"]
    B --> C["requestHeaders descriptors"]
    C --> D["Verify against actual headers"]
    D --> E["request-headers.adoc"]
    E --> F["Asciidoctor / API guide"]
~~~

`requestHeaders(...)` must be passed to the `document(...)` callback of the request being documented. Simply importing or declaring descriptors without invoking the callback will not generate a snippet.

## 4. Complete Example with WebTestClient and JUnit 5

Suppose the `POST /api/orders` endpoint accepts JSON, requires the `X-Request-Id` header, and returns status 201. The test below sends real headers, verifies the response, and generates the request headers table.

Gradle Groovy DSL dependencies in a Spring Boot WebFlux project:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-webtestclient'
}
~~~

Example test:

~~~java
import java.net.URI;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.documentationConfiguration;

@ExtendWith(RestDocumentationExtension.class)
class OrderRequestHeadersDocumentationTest {

    private WebTestClient client;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.client = WebTestClient.bindToController(new OrderController())
            .configureClient()
            .filter(documentationConfiguration(restDocumentation))
            .build();
    }

    @Test
    void documentsCreateOrderRequestHeaders() {
        client.post()
            .uri("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .header("X-Request-Id", "doc-test-001")
            .bodyValue(Map.of(
                "productId", "BOOK-01",
                "quantity", 2
            ))
            .exchange()
            .expectStatus().isCreated()
            .expectBody()
            .jsonPath("$.id").isEqualTo(42)
            .consumeWith(document("orders/create",
                requestHeaders(
                    headerWithName("X-Request-Id")
                        .description("ID used to trace the request"),
                    headerWithName("Content-Type")
                        .description("Format of the request body"),
                    headerWithName("Accept")
                        .description("Response type accepted by the client")
                ),
                requestFields(
                    fieldWithPath("productId").description("Product ID"),
                    fieldWithPath("quantity").description("Quantity")
                )
            ));
    }

    @RestController
    static class OrderController {

        @PostMapping(
            path = "/api/orders",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
        )
        public Mono<ResponseEntity<Map<String, Object>>> create(
                @RequestBody Map<String, Object> request) {
            Map<String, Object> result = Map.of(
                "id", 42,
                "productId", request.get("productId"),
                "quantity", request.get("quantity")
            );
            return Mono.just(
                ResponseEntity.created(URI.create("/api/orders/42"))
                    .body(result)
            );
        }
    }
}
~~~

Steps in the test:

1. `@ExtendWith(RestDocumentationExtension.class)` integrates Spring REST Docs into JUnit 5.
2. `documentationConfiguration(restDocumentation)` adds the REST Docs filter to WebTestClient.
3. `contentType(...)`, `accept(...)`, and `header(...)` build the headers of the request sent to the endpoint.
4. `exchange()` executes the request; `expectStatus()` and JSONPath verify the result.
5. `consumeWith(document("orders/create", ...))` invokes the documentation callback. `requestHeaders(...)` documents three headers; `requestFields(...)` documents the JSON body.

The example uses deterministic header values so that snippets are reproducible. `X-Request-Id` in a real system may have a different value for each request; documentation describes the header's role and format rather than depending on a random tracing ID.

## 5. Required and Optional Headers

By default, a descriptor documents a header as part of the contract. If a header only appears in certain valid scenarios, use `.optional()`:

~~~java
requestHeaders(
    headerWithName("X-Request-Id")
        .description("Request tracing ID"),
    headerWithName("If-Match")
        .description("ETag of the resource version the client has read")
        .optional()
)
~~~

This example fits a resource update endpoint: the client may send `If-Match` to request a conditional update, but not every call flow is required to use this header.

`.optional()` states that the header is allowed to be absent in the operation. If the header appears in the request, the descriptor still documents its meaning. Do not mark a header optional just to make a test pass when the API actually requires that header.

When a header is marked as required but the request does not send it, snippet generation will fail. This is a signal to check one of two things: either the test is missing a necessary header or the API contract is documented inaccurately.

## 6. Excluding Headers from the Documentation Table with `.ignored()`

A request may contain infrastructure headers that the API documentation does not need to present, such as internal headers from the test environment. Descriptors support `.ignored()`:

~~~java
requestHeaders(
    headerWithName("X-Request-Id")
        .description("Request tracing ID"),
    headerWithName("Host")
        .ignored()
)
~~~

`.ignored()` indicates that the header is recognized during documentation processing but does not need to appear as a documented entry in the table. This is not a way to remove the header from the actual HTTP request.

Distinction:

| Declaration | Meaning |
| --- | --- |
| No descriptor declared | The header is not in the documented contract; for strict snippets, an undocumented header can cause the test to fail. |
| `.optional()` | The header is allowed to be absent, but is still documented if present. |
| `.ignored()` | The header is processed but excluded from the documentation table. |

Only ignore a header when there is a clear reason. If clients need to know they must send `Content-Type`, `Accept`, `If-Match`, or a custom header, document it instead of marking it ignored.

## 7. Header Descriptors and Request Contract Verification

`requestHeaders(...)` does more than simply generate a text table. Descriptors help REST Docs detect discrepancies between the actual request and the declared headers.

Example descriptor:

~~~java
requestHeaders(
    headerWithName("X-Request-Id")
        .description("Request tracing ID"),
    headerWithName("Content-Type")
        .description("Content type of the request body")
)
~~~

If the request introduces a new header that a strict snippet has not yet documented, snippet generation may fail. In that case:

1. Check whether the new header belongs to the public contract.
2. If clients need to know about that header, add `headerWithName(...).description(...)`.
3. If the header is optional, add `.optional()` according to the API rules.
4. If the header is only an internal detail, consider `.ignored()` and explain the reason in code review.

Conversely, if the test declares a required header but the request does not send it, REST Docs also detects the descriptor mismatch. Therefore, descriptors clarify the exact headers that the test proves.

## 8. Distinguishing Request Headers from Response Headers

`requestHeaders(...)` documents headers sent by the client to the server. Headers returned by the server are documented using `responseHeaders(...)`.

~~~java
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;

document("orders/create",
    requestHeaders(
        headerWithName("X-Request-Id")
            .description("Request tracing ID")
    ),
    responseHeaders(
        headerWithName("Location")
            .description("URI of the newly created resource")
    )
)
~~~

| HTTP Direction | REST Docs API | Snippet File |
| --- | --- | --- |
| Client → Server | `requestHeaders(...)` | `request-headers.adoc` |
| Server → Client | `responseHeaders(...)` | `response-headers.adoc` |

Do not use `requestHeaders(...)` to document `Location`, `ETag`, or `Cache-Control` returned by the server. Choosing the right direction ensures the documentation accurately shows who must send or who produces each header.

## 9. Multiple Headers, Custom Headers, and Name Normalization

### 9.1. Multi-Valued Headers

Some headers can carry multiple values or a list of values. For example, `Accept` can contain multiple media types:

~~~java
client.get()
    .uri("/api/orders")
    .accept(
        MediaType.APPLICATION_JSON,
        MediaType.APPLICATION_XML
    )
    .exchange()
    .expectStatus().isOk();
~~~

The descriptor should explain the meaning of the header, while the request snippet shows the actual values sent. When the contract requires a specific value, test how the server handles the corresponding media type selection.

### 9.2. Custom Headers

Custom header names should have a meaningful prefix following your organization's API conventions:

~~~java
requestHeaders(
    headerWithName("X-Tenant-Id")
        .description("Tenant ID used to determine the data scope"),
    headerWithName("X-Request-Id")
        .description("Tracing ID across services")
)
~~~

Documentation needs to explain the format, when to send it, and the meaning of the value. Avoid vague descriptions such as "custom header" when clients need to understand how to construct the value.

### 9.3. Case-Insensitive Header Names

HTTP header names are case-insensitive. Even so, you should keep the casing consistent across descriptors and documentation (usually following the API's standard casing) so readers can look them up easily. Do not rely on casing differences to create two headers with distinct meanings.

## 10. Preprocessing Header Data Before Snippet Generation

A request may carry headers used for authentication or internal purposes. Never store real secrets in fixtures. When a test must send dummy credentials, you can remove sensitive headers from the request snippet using a preprocessor:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

consumeWith(document("orders/get",
    preprocessRequest(
        modifyHeaders()
            .remove("Authorization")
            .remove("Cookie")
    ),
    requestHeaders(
        headerWithName("X-Request-Id")
            .description("Request tracing ID")
    )
))
~~~

The preprocessor modifies the recorded operation used to generate snippets; it does not remove headers from the request sent to the endpoint. The example above does not document `Authorization` in the header table. If a public API requires users to send Authorization, explain the authentication mechanism in the appropriate security documentation section and show a safe placeholder value according to the project's documentation strategy. Never include real tokens, session cookies, or secret keys in snippets.

Check the resulting `request-headers.adoc` and `http-request.adoc` after preprocessing. If a descriptor requires a header that the preprocessor removes from the operation before snippet generation, adjust the design so the header is handled consistently; do not assume descriptors and preprocessors are always independent.

## 11. Including `request-headers.adoc` in Asciidoctor

After the `orders/create` test runs successfully, Spring REST Docs creates snippets under the operation directory, typically:

~~~text
build/generated-snippets/
└── orders/
    └── create/
        ├── http-request.adoc
        ├── request-headers.adoc
        ├── request-fields.adoc
        ├── http-response.adoc
        └── response-body.adoc
~~~

The list above shows typical files; the actual files depend on the request, response, and descriptors used.

In the Asciidoctor document:

~~~asciidoc
= Orders API
:snippets: build/generated-snippets

== Create order

=== Request headers
include::{snippets}/orders/create/request-headers.adoc[]

=== Request payload
include::{snippets}/orders/create/request-fields.adoc[]

=== HTTP request
include::{snippets}/orders/create/http-request.adoc[]

=== HTTP response
include::{snippets}/orders/create/http-response.adoc[]
~~~

`:snippets:` must point to the correct directory according to the build configuration and the location of the Asciidoctor file. You can pass this attribute from Gradle to avoid hardcoding scattered paths.

## 12. Integrating into Gradle and CI

When using a configured Asciidoctor plugin with an `asciidoctor` task, wire the documentation task to the test task:

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

In CI, run:

~~~bash
./gradlew clean test asciidoctor
~~~

`test` generates snippets and verifies descriptors; `asciidoctor` assembles the snippets into documentation. If a required header is missing or a new undocumented header is present, the documentation test fails and CI should not continue publishing stale documentation as new output.

With plain Markdown, Asciidoctor's `include::` syntax is not processed automatically. A separate build step is needed to inline snippet contents or link to the generated files.

## 13. Common Errors and How to Handle Them

| Symptom | Cause and Resolution |
| --- | --- |
| `request-headers.adoc` not found | Check that the test calls `consumeWith(document(..., requestHeaders(...)))` and the REST Docs filter is added to the right client. |
| Test fails due to missing header | A header is documented as required but the request did not send it; check the request builder or mark it optional if the contract allows. |
| A new header causes snippet failure | Add a descriptor for the public header or mark it ignored with a clear reason. |
| Unnecessary header appears in table | Consider `.ignored()` or design a preprocessor if the header should be removed from the entire record. |
| Mistakenly used `requestHeaders` for `Location` | `Location` is a response header; switch to `responseHeaders(...)`. |
| Authentication header appears in snippet | Use dummy credentials and preprocess the request record before writing; check the output file before sharing. |
| Header description is not clear enough | Explain the purpose, format, whether it is required, and conditions for sending the header. |
| Asciidoctor cannot find snippet | Check the operation identifier, the `generated-snippets` path, and ensure the test task runs first. |

## 14. Practice Exercises

1. Run the `OrderRequestHeadersDocumentationTest` test and open `orders/create/request-headers.adoc`.
2. Remove `.header("X-Request-Id", "doc-test-001")` while keeping the required descriptor; observe how the test and REST Docs detect that the request does not match the contract.
3. Restore the header and add `If-Match` with an `.optional()` descriptor. Run the test once with the header sent and once without it to verify both cases.
4. Add an internal header, describe it with `.ignored()`, and verify that the header does not appear in the documentation table.
5. Add a `responseHeaders(...)` descriptor for `Location`, distinguishing request header content from response header content.
6. Include the snippets in Asciidoctor and configure CI to run tests before building the documentation.

## 15. Key Takeaways

- `headerWithName(...)` creates a descriptor; `requestHeaders(...)` passes request header descriptors into `document(...)`.
- Each descriptor needs a specific description so clients understand when and why to send the header.
- Required, optional, and ignored headers have different meanings; use `.optional()` and `.ignored()` accurately according to the API contract.
- `requestHeaders(...)` documents the client → server direction; `responseHeaders(...)` documents the server → client direction.
- Descriptors help detect requests missing headers or introducing undocumented headers; update documentation and tests together when the contract changes.
- Inspect snippets after preprocessing to ensure no secrets are leaked and CI always builds documentation from tests that just passed.
