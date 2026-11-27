# headerWithName and Header Descriptions

## 1. Lesson Objectives

In the **SPRING_REST_DOCS** module, REST API documentation is generated from runnable HTTP tests. A test sends a request, asserts the response, and Spring REST Docs generates snippets for the request, response, payload, parameters, and headers. The snippets are compiled using Asciidoctor/Markdown and then integrated into the build and CI so that documentation stays aligned with verified behavior.

In the **Headers** chapter, a useful header table needs to explain more than just header names. API consumers need to know what a header is used for, what format its value takes, when it must be sent, and what happens if it is missing or sent incorrectly.

This lesson focuses on `headerWithName(...)` and how to write header descriptions in Spring REST Docs. After this lesson, you will be able to create descriptors, write clear descriptions covering purpose/format/usage conditions, distinguish between request and response headers, express required/optional/ignored headers, and use those descriptors to generate verifiable snippets.

## 2. From Header Names to a Contract Clients Can Understand

An order creation request might contain:

~~~http
POST /api/orders HTTP/1.1
Accept: application/json
Content-Type: application/json
X-Request-Id: 5f23c4a8-1b62-4af0-9f75-2ad6c2b19a40
Idempotency-Key: checkout-2026-00042

{"productId":"BOOK-01","quantity":2}
~~~

Simply listing the names `X-Request-Id` and `Idempotency-Key` does not explain how callers should construct the values. The documentation table should answer:

| Question | Example Information to Describe |
| --- | --- |
| What is the header's purpose? | Tracing requests or preventing duplicate order creation when the client retries. |
| What format does the value take? | UUID, a conventional identifier string, or a media type. |
| When should it be sent? | Every request, only on conditional updates, or when retrying a creation operation. |
| Is it required? | If missing, does the server reject the request or generate a fallback value? |
| Are there any constraints? | Length, character set, uniqueness, and uniqueness scope. |

Spring REST Docs uses descriptors to define which headers need to be documented. When the test runs, the library checks the descriptors against the actual request and generates the header table. As a result, the documentation serves both as an API usage guide and as part of contract testing.

## 3. Syntax of headerWithName(...)

Static import:

~~~java
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
~~~

Create a descriptor for a header:

~~~java
headerWithName("X-Request-Id")
    .description("Identifier used to trace the request across services.");
~~~

`headerWithName(name)` creates a descriptor for the given header name. Call `.description(...)` to explain what purpose the header serves. The descriptor is then passed into `requestHeaders(...)` or `responseHeaders(...)` depending on the communication direction.

Example with a standard header:

~~~java
headerWithName("Content-Type")
    .description("Content type of the request body; this endpoint requires application/json.");
~~~

Example with a custom header:

~~~java
headerWithName("X-Tenant-Id")
    .description("Tenant ID determining the data scope the request is permitted to access.");
~~~

A good description does more than just restate the header name in prose. It provides the context an integrator needs to construct a valid request.

## 4. Rules for Writing High-Quality Descriptions

A description should be concise yet informative enough that readers can use the header without guessing.

### 4.1. State the Purpose First

~~~java
headerWithName("X-Request-Id")
    .description("Unique tracing ID for the request, logged by the services processing the request.");
~~~

Avoid generic descriptions like "Request header", "Custom header", or "Request value". Such phrases fail to tell clients why they need to send the header.

### 4.2. Describe the Format and Provide an Example

~~~java
headerWithName("X-Request-Id")
    .description("Tracing ID in UUID format; for example: 5f23c4a8-1b62-4af0-9f75-2ad6c2b19a40.");
~~~

For a header carrying media types:

~~~java
headerWithName("Accept")
    .description("List of media types the client can accept; this endpoint supports application/json.");
~~~

Examples must use dummy, valid data and must not contain real tokens, cookies, or credentials.

### 4.3. State Sending Conditions and Requiredness

~~~java
headerWithName("If-Match")
    .description("ETag of the resource version the client has read; send on conditional updates to avoid overwriting newer changes.")
    .optional();
~~~

The description explains the meaning; `.optional()` expresses that the header may be absent in the operation. If there are specific error rules when the header is missing or when the ETag does not match, you can describe them further in the operation or error handling section.

### 4.4. Do Not Repeat What Readers Already Know

`Content-Type` is already inherently a header indicating content type. Its description should specify the endpoint's requirement, such as JSON, rather than simply writing "Content type". Similarly, `Authorization` should not merely be described as "Authentication information"; direct readers to the authentication mechanism or scheme supported by the API, if that content is within the documentation's scope.

## 5. Documenting Request Headers with requestHeaders(...)

`headerWithName(...)` creates a descriptor; `requestHeaders(...)` attaches descriptors to the operation:

~~~java
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

document("orders/create",
    requestHeaders(
        headerWithName("Content-Type")
            .description("Content type of the request body; endpoint requires application/json."),
        headerWithName("Accept")
            .description("Media type accepted by the client; endpoint returns application/json."),
        headerWithName("X-Request-Id")
            .description("Unique tracing ID of the request, used to correlate logs.")
    )
)
~~~

This is an illustrative callback passed into `consumeWith(document(...))` after the request has been sent and the necessary assertions have run. When the test passes, Spring REST Docs creates the `request-headers.adoc` file in the operation's snippet directory.

~~~mermaid
flowchart LR
    A["headerWithName(name)"] --> B["description(...)"]
    B --> C["requestHeaders(...)"]
    C --> D["document(operation-id, ...)"]
    D --> E["consumeWith(...)"]
    E --> F["request-headers.adoc"]
~~~

`requestHeaders(...)` describes headers sent by the client to the server. Do not place headers that only appear in the response into this table.

## 6. Documenting Response Headers with responseHeaders(...)

For headers returned by the server, use `responseHeaders(...)`:

~~~java
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;

responseHeaders(
    headerWithName("Location")
        .description("Relative URI of the newly created order; clients can use this URI to query the resource."),
    headerWithName("ETag")
        .description("Validator representing the current version of the resource.")
)
~~~

Some common response headers:

| Header | What the Description Should Explain |
| --- | --- |
| `Location` | URI of the created resource or redirect destination. |
| `ETag` | Representation version validator and how to use it with conditional requests. |
| `Cache-Control` | Caching policy that clients or proxies must follow. |
| `Retry-After` | Wait duration or timestamp when the client should retry, in the format returned by the server. |
| `Content-Type` | Representation type in the response. |

Example resource creation test:

~~~java
client.post()
    .uri("/api/orders")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(Map.of("productId", "BOOK-01", "quantity", 2))
    .exchange()
    .expectStatus().isCreated()
    .expectHeader().valueEquals("Location", "/api/orders/42")
    .expectBody()
    .consumeWith(document("orders/create",
        responseHeaders(
            headerWithName("Location")
                .description("Relative URI of the newly created order; can be used to query the order.")
        )
    ));
~~~

The example assumes the endpoint returns status 201 and `Location` matching the assertion. The description clearly states the meaning of the URI so the client knows what to do next.

## 7. Required, Optional, and Ignored Headers

### 7.1. Required Headers

A descriptor without `.optional()` expresses that the header is a required part of the documented request:

~~~java
requestHeaders(
    headerWithName("X-Tenant-Id")
        .description("Tenant ID that the client has been granted access to.")
)
~~~

If the request does not contain a header documented as required, snippet generation may fail. When that happens, inspect the request builder and the API contract.

### 7.2. Optional Headers

Use `.optional()` if the header can legitimately be absent:

~~~java
headerWithName("If-Match")
    .description("ETag used for conditional resource updates.")
    .optional()
~~~

Do not mark a header optional just to make a test pass when the endpoint actually requires the header. If the header is sent, the descriptor still defines how that header is documented.

### 7.3. Headers Excluded from the Table

Use `.ignored()` for headers that need to be recognized but should not appear as a documented row:

~~~java
headerWithName("Host").ignored()
~~~

`.ignored()` does not remove the header from the actual HTTP request. If you need to remove sensitive headers from the request record in snippets as well, evaluate a request preprocessor. The two options serve different purposes: ignored adjusts the descriptor table; a preprocessor adjusts the documented data.

## 8. Documenting Custom Headers According to the API Contract

Custom headers may use organization-specific prefixes by convention. Regardless of the name, the description needs to explain the semantics clients must follow.

~~~java
requestHeaders(
    headerWithName("X-Tenant-Id")
        .description("Tenant ID determining data scope; value must belong to a tenant the client is authorized to access."),
    headerWithName("X-Request-Id")
        .description("Tracing ID for an API call; this ID should be preserved when forwarding requests across services."),
    headerWithName("Idempotency-Key")
        .description("Deduplication key for the order creation operation; the client resends the same key when retrying the same operation.")
)
~~~

These are examples of hypothetical API conventions. When applying this in a real system, describe the actual mechanism accurately, especially the uniqueness scope, key retention duration, how the server handles duplicate keys, and the response when reusing a key with a different payload.

Do not guess behavior solely from the header name. The name `X-Tenant-Id` does not prove the server uses that value as an authorization mechanism; descriptions must be grounded in the actual API contract.

## 9. Documenting List-Valued Headers

Some headers can carry multiple values or a list of media types:

~~~java
client.get()
    .uri("/api/reports")
    .accept(
        MediaType.APPLICATION_JSON,
        MediaType.APPLICATION_XML
    )
    .exchange()
    .expectStatus().isOk();
~~~

The `Accept` descriptor should clearly state which representations the endpoint supports, matching the actual server configuration:

~~~java
headerWithName("Accept")
    .description("List of media types the client can accept; endpoint supports application/json and application/xml.")
~~~

Do not list a set of media types in the description if the server does not actually support them. Tests should verify content negotiation choices that matter to the API contract.

A multi-valued header does not necessarily need one descriptor per value. `headerWithName(...)` describes the header name; the description explains how to interpret that header's value.

## 10. Complete Example: Writing Useful Descriptions and Generating Snippets

The example below illustrates an order creation endpoint. The `X-Request-Id` header is sent by the client; the server returns `Location`. The descriptions clearly state each role instead of merely repeating the names.

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
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.documentationConfiguration;

@ExtendWith(RestDocumentationExtension.class)
class OrderHeaderDescriptionDocumentationTest {

    private WebTestClient client;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        client = WebTestClient.bindToController(new OrderController())
            .configureClient()
            .filter(documentationConfiguration(restDocumentation))
            .build();
    }

    @Test
    void documentsOrderHeaders() {
        client.post()
            .uri("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .header("X-Request-Id", "doc-test-001")
            .bodyValue(Map.of("productId", "BOOK-01", "quantity", 2))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().valueEquals("Location", "/api/orders/42")
            .expectBody()
            .jsonPath("$.id").isEqualTo(42)
            .consumeWith(document("orders/create",
                requestHeaders(
                    headerWithName("Content-Type")
                        .description("Content type of the request body; endpoint requires application/json."),
                    headerWithName("Accept")
                        .description("Media type accepted by the client; endpoint returns application/json."),
                    headerWithName("X-Request-Id")
                        .description("Unique tracing ID of the request, used to correlate logs.")
                ),
                responseHeaders(
                    headerWithName("Location")
                        .description("Relative URI of the newly created order; can be used to query the order.")
                ),
                requestFields(
                    fieldWithPath("productId").description("Product ID"),
                    fieldWithPath("quantity").description("Quantity")
                ),
                responseFields(
                    fieldWithPath("id").description("ID of the newly created order"),
                    fieldWithPath("productId").description("Product ID in the order"),
                    fieldWithPath("quantity").description("Product quantity")
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
                @RequestBody Map<String, Object> input) {
            Map<String, Object> body = Map.of(
                "id", 42,
                "productId", input.get("productId"),
                "quantity", input.get("quantity")
            );
            return Mono.just(
                ResponseEntity.created(URI.create("/api/orders/42"))
                    .body(body)
            );
        }
    }
}
~~~

Execution flow:

1. WebTestClient sends `Content-Type`, `Accept`, and `X-Request-Id` along with the JSON body.
2. `exchange()` routes the request to the controller; the test verifies status 201, `Location`, and the `id` field.
3. `document("orders/create", ...)` attaches the request header and response header descriptors to the operation.
4. Spring REST Docs checks the actual headers and generates `request-headers.adoc` and `response-headers.adoc` snippets.

The controller returns `ResponseEntity.created(...)`, so the status and `Location` are consistent with the assertion. Fixed values make the example repeatable; real applications need fixtures/test doubles matching their own contracts.

## 11. Common Mistakes When Writing Descriptions

| Description or Usage | Problem | How to Improve |
| --- | --- | --- |
| "Request header" | Does not state what the header does. | State the purpose and how systems use the value. |
| "Custom value" | Client does not know what value to create. | State the format and provide a valid dummy example. |
| Describing `If-Match` without mentioning conditions | Unclear when to send and what happens on ETag mismatch. | Explain conditional updates and versioning rules. |
| Marking a required header `.optional()` | Weakens contract verification. | Keep the descriptor required or fix the test/API to match the true contract. |
| Using `requestHeaders(...)` for `Location` | Confuses request and response directions. | Use `responseHeaders(...)`. |
| Putting real tokens in examples | Risks exposing credentials. | Use placeholders/dummy credentials and preprocess snippets when needed. |
| Descriptor name does not match actual sent header | REST Docs cannot find the matching header or the test fails. | Check spelling; note HTTP headers are case-insensitive. |

## 12. Generating and Compiling Snippets

For the `orders/create` operation, REST Docs typically generates standard files in:

~~~text
build/generated-snippets/
└── orders/
    └── create/
        ├── http-request.adoc
        ├── request-headers.adoc
        ├── request-fields.adoc
        ├── http-response.adoc
        ├── response-headers.adoc
        └── response-fields.adoc
~~~

An Asciidoctor page can include the header tables in the operation description section:

~~~asciidoc
= Orders API
:snippets: build/generated-snippets

== Create order

=== Request headers
include::{snippets}/orders/create/request-headers.adoc[]

=== Request fields
include::{snippets}/orders/create/request-fields.adoc[]

=== HTTP request
include::{snippets}/orders/create/http-request.adoc[]

=== Response headers
include::{snippets}/orders/create/response-headers.adoc[]

=== Response fields
include::{snippets}/orders/create/response-fields.adoc[]
~~~

The `:snippets:` path must match where the build generates snippets and how Asciidoctor resolves files. The operation name in `document("orders/create", ...)` must be consistent with the path in `include::`.

## 13. Integrating Gradle and CI

After configuring the Asciidoctor plugin and the `asciidoctor` task, declare the dependency on tests:

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

Tests verify whether actual headers match the descriptors and generate snippets. Asciidoctor assembles the header tables into the final documentation. When a required header is missing or a new undocumented header appears, the documentation test fails; CI should stop before the publish step. With plain Markdown, a separate build step is needed to embed or link the snippets; `include::` syntax belongs to Asciidoctor.

## 14. Practice Exercises

1. Run `OrderHeaderDescriptionDocumentationTest` and open `orders/create/request-headers.adoc` and `response-headers.adoc`.
2. Rewrite the description of `X-Request-Id` to state its purpose, format, and how it is used for log correlation.
3. Try changing the `Content-Type` description to a generic sentence, then improve it to specify that the endpoint requires `application/json`.
4. Add `If-Match` to an update operation, mark it `.optional()` if the contract allows, and clearly state the sending condition.
5. Add the `ETag` response header to a resource retrieval endpoint; describe how clients use it in conditional update requests.
6. Build Asciidoctor and verify that the header tables in the documentation reflect the latest descriptors.

## 15. Key Takeaways

- `headerWithName(...)` creates a descriptor for a header; `.description(...)` explains its meaning to clients or response consumers.
- Useful descriptions need to state purpose, format, sending conditions, and requiredness when that information belongs to the contract.
- Use `requestHeaders(...)` for headers sent by the client and `responseHeaders(...)` for headers returned by the server.
- `.optional()` indicates the header may be absent; `.ignored()` intentionally excludes the header from the description table.
- Descriptors allow Spring REST Docs to verify actual headers against the declared contract and generate verifiable snippets.
- Use dummy examples, avoid real credentials, and run tests before Asciidoctor/CI so documentation is updated from verified HTTP exchanges.
