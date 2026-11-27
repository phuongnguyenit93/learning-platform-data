# Verifying Headers Are Sent and Returned Correctly

## 1. Lesson Objectives

In the **SPRING_REST_DOCS** module, REST API documentation is generated from HTTP tests using MockMvc, WebTestClient, or REST Assured. Tests send requests, verify responses, and Spring REST Docs generates snippets for requests, responses, payloads, parameters, and headers. The snippets are compiled using Asciidoctor/Markdown and integrated into the build and CI.

The **Headers** chapter does more than just document header names. Tests must prove that requests send the exact metadata the endpoint requires and that the server returns the exact headers in the contract. This lesson focuses on both directions:

- **Request headers**: checking that headers are included in requests and recorded in snippets.
- **Response headers**: using `expectHeader()` to verify that headers are present, absent, match a value, or match a pattern.

After this lesson, you will be able to use `requestHeaders(...)` to document request headers, distinguish presence checks from exact value checks, use `expectHeader()` to verify responses, combine assertions with REST Docs descriptors, and generate snippets in JUnit 5/WebTestClient.

## 2. Two Header Directions to Verify

An HTTP exchange has a request and a response:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json
Accept: application/json
X-Request-Id: req-test-001

{"productId":"BOOK-01","quantity":2}
~~~

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/orders/42
X-Request-Id: req-test-001
Cache-Control: no-store

{"id":42}
~~~

| Side | Testing Question | Primary Tool |
| --- | --- | --- |
| Request | Which headers did the client send? Are required headers present? | Request builder, `requestHeaders(...)`, server-side probe if value verification is needed |
| Response | Did the server return the header? Does the value match the contract? | `expectHeader()` |
| Documentation | Are headers documented in the snippet on the right side? | `requestHeaders(...)`, `responseHeaders(...)` |

~~~mermaid
flowchart TD
    A["WebTestClient request builder"] --> B["HTTP request"]
    B --> C["Endpoint receives headers"]
    C --> D["Endpoint builds response"]
    D --> E["expectHeader() assertions"]
    B --> F["REST Docs requestHeaders descriptors"]
    D --> G["REST Docs responseHeaders descriptors"]
    F --> H["request-headers.adoc"]
    G --> I["response-headers.adoc"]
~~~

Key point to remember: `requestHeaders(...)` is a REST Docs descriptor, not an assertion API for comparing a request header against an arbitrary expected string. Descriptors check that documented headers are present in the operation and generate the documentation table. If you need to prove a request header value actually reaches the endpoint, verify it on the receiving side—such as through a controller parameter, filter, or test probe.

## 3. Verifying Request Headers Are Sent

### 3.1. Setting Headers on WebTestClient

Headers can be set per request:

~~~java
client.post()
    .uri("/api/orders")
    .contentType(MediaType.APPLICATION_JSON)
    .accept(MediaType.APPLICATION_JSON)
    .header("X-Request-Id", "req-test-001")
    .bodyValue(Map.of("productId", "BOOK-01", "quantity", 2))
    .exchange();
~~~

`contentType(...)` sets `Content-Type`; `accept(...)` sets `Accept`; `header(name, value)` sets a custom header. If many tests share default headers, you can configure `defaultHeader(...)` when building WebTestClient. For operation-specific headers, setting them directly on the request makes the contract visible right where it is used.

### 3.2. Using requestHeaders(...) to Verify Header Presence and Document It

~~~java
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;

document("orders/create",
    requestHeaders(
        headerWithName("Content-Type")
            .description("Content type of the request body; endpoint requires application/json."),
        headerWithName("Accept")
            .description("Media type accepted by the client; endpoint returns application/json."),
        headerWithName("X-Request-Id")
            .description("Unique tracing ID of the request.")
    )
)
~~~

When the request is documented, REST Docs matches descriptors against headers in the operation. If a required descriptor cannot find its corresponding header, snippet generation can fail. This verifies that documented headers appear in the recorded request.

Optional headers can be marked with `.optional()`:

~~~java
headerWithName("If-Match")
    .description("ETag sent when the client conditionally updates the resource.")
    .optional()
~~~

Mark a header optional only when the contract permits its absence; do not use it to bypass a request that is missing a required header.

### 3.3. Checking Request Header Values on the Receiving Side

REST Docs descriptors do not compare a request header value against a constant you pass in. If a specific value is part of the behavior under test, verify it on the receiving side. For example, a controller receiving the header via `@RequestHeader`:

~~~java
@RestController
static class ProbeController {

    @GetMapping("/test/probe")
    Map<String, String> probe(
            @RequestHeader("X-Request-Id") String requestId) {
        return Map.of("receivedRequestId", requestId);
    }
}
~~~

The test sends and asserts the value received by the controller:

~~~java
client.get()
    .uri("/test/probe")
    .header("X-Request-Id", "req-test-001")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.receivedRequestId").isEqualTo("req-test-001");
~~~

This is an illustrative probe test. In a real system, you can verify headers inside a filter, interceptor, or mock collaborator invoked by the controller. This is useful when header values are transformed or validated before use.

## 4. Verifying Response Headers with expectHeader()

After `exchange()`, `expectHeader()` lets you assert headers returned by the server:

~~~java
client.get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().exists("ETag")
    .expectHeader().valueEquals("Cache-Control", "private, max-age=60");
~~~

Commonly used checks:

| Assertion | Verified Condition |
| --- | --- |
| `exists(name)` | The header must be present. |
| `doesNotExist(name)` | The header must not appear. |
| `valueEquals(name, value)` | The header value must equal the expected value. |
| `valueMatches(name, regex)` | The value must match the regular expression. |
| `values(name, consumer)` | Inspects the list of header values using an assertion callback. |
| `contentTypeCompatibleWith(mediaType)` | `Content-Type` is compatible with the expected media type. |

Choose specific assertions according to the contract. Checking only `exists("Location")` does not prove the URI is correct. If the endpoint requires `Location: /api/orders/42`, use `valueEquals(...)`.

### 4.1. Checking Exact Values

~~~java
.expectHeader().valueEquals(HttpHeaders.LOCATION, "/api/orders/42")
~~~

Suitable for headers with contractually fixed values, such as a relative URI defined by the endpoint.

### 4.2. Checking with Regular Expressions

~~~java
.expectHeader().valueMatches("X-Request-Id", "req-[a-z0-9-]+")
~~~

Use regex when values have a valid structure yet vary across runs. Regexes should be tight enough to catch invalid values; `.*` is usually too broad.

### 4.3. Checking Multiple Values

The example below uses AssertJ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

.expectHeader().values("Vary", values ->
    assertThat(values).contains("Accept")
)
~~~

The example uses AssertJ to verify that the value list contains `Accept`. If the full value set or ordering is specified, assert that exact rule.

## 5. Combining Assertions and REST Docs Descriptors

Assertions prove the server returns the right values. Descriptors generate documentation tables and catch undocumented headers. A single operation usually needs both:

~~~java
client.post()
    .uri("/api/orders")
    .contentType(MediaType.APPLICATION_JSON)
    .accept(MediaType.APPLICATION_JSON)
    .header("X-Request-Id", "req-test-001")
    .bodyValue(Map.of("productId", "BOOK-01", "quantity", 2))
    .exchange()
    .expectStatus().isCreated()
    .expectHeader().valueEquals(HttpHeaders.LOCATION, "/api/orders/42")
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectHeader().valueEquals("X-Request-Id", "req-test-001")
    .expectBody()
    .jsonPath("$.id").isEqualTo(42)
    .consumeWith(document("orders/create",
        requestHeaders(
            headerWithName(HttpHeaders.CONTENT_TYPE)
                .description("Content type of the request body; endpoint requires application/json."),
            headerWithName(HttpHeaders.ACCEPT)
                .description("Media type accepted by the client; endpoint returns application/json."),
            headerWithName("X-Request-Id")
                .description("Unique tracing ID of the request.")
        ),
        responseHeaders(
            headerWithName(HttpHeaders.LOCATION)
                .description("Relative URI of the newly created order."),
            headerWithName(HttpHeaders.CONTENT_TYPE)
                .description("Response representation type; endpoint returns application/json."),
            headerWithName("X-Request-Id")
                .description("Tracing ID echoed back by the server to the client.")
        )
    ));
~~~

In the example, the request builder sets three request headers; `expectHeader()` verifies that the response has `Location`, `Content-Type`, and `X-Request-Id` with the right values; `requestHeaders(...)` documents sent headers; `responseHeaders(...)` documents returned headers; finally `consumeWith(document(...))` generates snippets after key assertions pass.

Note: `expectHeader()` after `exchange()` only checks the response. It does not inspect the request the client sent. If you want to verify the value of `X-Request-Id` on the request, use a probe/controller/filter as in section 3.3; do not infer it from response assertions unless the endpoint is explicitly designed to echo back the received header.

## 6. Distinguishing Request and Response Descriptors

| Descriptor | Documented Headers | Snippet |
| --- | --- | --- |
| `requestHeaders(...)` | Sent by client to server | `request-headers.adoc` |
| `responseHeaders(...)` | Returned by server to client | `response-headers.adoc` |

~~~java
document("books/create",
    requestHeaders(
        headerWithName("Content-Type")
            .description("Content type of the request body.")
    ),
    responseHeaders(
        headerWithName("Location")
            .description("URI of the newly created resource."),
        headerWithName("ETag")
            .description("Validator of the returned representation.")
    )
)
~~~

Do not put `Location` in `requestHeaders(...)` when the endpoint produces it in the response. Similarly, `If-Match` is a request header; `ETag` is typically a response header. When a header name can appear in both directions, such as `Cache-Control` or `Content-Type`, clearly identify which side the operation is verifying.

## 7. Checking Absent and Optional Headers

An API may commit to not emitting an internal header or not emitting caching headers on a certain type of response:

~~~java
client.get()
    .uri("/api/private/export")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().doesNotExist("X-Debug-Only");
~~~

For response headers that may be omitted in one branch, only place `expectHeader().exists("ETag")` in tests where the contract guarantees ETag is present. In other branches, check `doesNotExist(...)` if absence is specified by the API.

Distinguish assertions from descriptors:

- `expectHeader().doesNotExist(...)` verifies that the actual response does not contain the header.
- `headerWithName(...).optional()` tells REST Docs that the header may be absent in the documented operation.
- `headerWithName(...).ignored()` intentionally excludes the header from the description table; it does not assert that the header is absent.

Do not use `.optional()` or `.ignored()` in place of assertions on presence/absence when that is behavior that needs verification.

## 8. Complete Example with Controller and WebTestClient

The following example has a POST endpoint that receives `X-Request-Id`, echoes that value back, and returns `Location`. Echoing the request ID is only to illustrate checking that the value reached the controller; real APIs may not need to echo this header.

~~~java
import java.net.URI;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
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
class VerifyHeadersDocumentationTest {

    private WebTestClient client;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.client = WebTestClient.bindToController(new OrderController())
            .configureClient()
            .filter(documentationConfiguration(restDocumentation))
            .build();
    }

    @Test
    void verifiesRequestAndResponseHeaders() {
        client.post()
            .uri("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .header("X-Request-Id", "req-test-001")
            .bodyValue(Map.of("productId", "BOOK-01", "quantity", 2))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().valueEquals(HttpHeaders.LOCATION, "/api/orders/42")
            .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectHeader().valueEquals("X-Request-Id", "req-test-001")
            .expectBody()
            .jsonPath("$.id").isEqualTo(42)
            .consumeWith(document("orders/create",
                requestHeaders(
                    headerWithName(HttpHeaders.CONTENT_TYPE)
                        .description("Content type of the request body; endpoint requires application/json."),
                    headerWithName(HttpHeaders.ACCEPT)
                        .description("Media type accepted by the client; endpoint returns application/json."),
                    headerWithName("X-Request-Id")
                        .description("Unique tracing ID of the request.")
                ),
                responseHeaders(
                    headerWithName(HttpHeaders.LOCATION)
                        .description("Relative URI of the newly created order."),
                    headerWithName(HttpHeaders.CONTENT_TYPE)
                        .description("Response representation type; endpoint returns application/json."),
                    headerWithName("X-Request-Id")
                        .description("Tracing ID echoed back by the server after receiving the request.")
                ),
                requestFields(
                    fieldWithPath("productId").description("Product ID"),
                    fieldWithPath("quantity").description("Quantity")
                ),
                responseFields(
                    fieldWithPath("id").description("ID of the created order")
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
                @RequestHeader("X-Request-Id") String requestId,
                @RequestBody Map<String, Object> request) {
            Map<String, Object> body = Map.of(
                "id", 42,
                "productId", request.get("productId"),
                "quantity", request.get("quantity")
            );
            return Mono.just(
                ResponseEntity.created(URI.create("/api/orders/42"))
                    .header("X-Request-Id", requestId)
                    .body(Map.of("id", body.get("id")))
            );
        }
    }
}
~~~

The controller receives `X-Request-Id` via `@RequestHeader` and returns it. The test uses `expectHeader().valueEquals(...)` to assert the response value; because the controller echoes the exact value it received, the example also proves the controller received the header as expected.

In a real project, if you do not want the endpoint to echo the header, use a filter or mock collaborator that records the received value so assertions do not alter the public API contract.

## 9. Documenting and Checking Multi-Valued Headers

A header like `Vary` can contain multiple values; `Accept` in a request can also contain multiple media types. Use the `values(...)` assertion if you need to verify list contents:

~~~java
.expectHeader().values("Vary", values ->
    assertThat(values).contains("Accept")
)
~~~

For request headers, WebTestClient can send multiple media types:

~~~java
client.get()
    .uri("/api/reports")
    .accept(MediaType.APPLICATION_JSON, MediaType.APPLICATION_XML)
    .exchange()
    .expectStatus().isOk();
~~~

The `headerWithName("Accept")` descriptor documents the header by name. The HTTP request snippet provides the values sent by the client; the descriptor provides meaning to readers. If the API requires a specific set of media types, test content negotiation and test each supported representation.

## 10. Handling Variable or Dynamically Generated Headers

Some response headers do not have fixed values:

- `Date` changes over time.
- `X-Request-Id` may be newly generated per request.
- `ETag` may depend on the version or representation content.
- `Set-Cookie` may contain security attributes and sessions that vary by run.

Do not assert these headers with fixed values unless the contract requires it. You can use `exists(...)`, `valueMatches(...)`, `values(...)`, or check individual required attributes. For dynamic values, descriptors can still describe stable meaning while snippets contain examples from test fixtures.

If snippets should not store dynamic or sensitive values, normalize the record using REST Docs preprocessors such as `modifyHeaders()` or replace values according to clear rules. Preprocessors affect the documented record; assertions must still check the actual response before snippets are written.

## 11. Header Snippets and Asciidoctor

For the `orders/create` operation identifier, REST Docs generates typical snippets:

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

Asciidoctor can place request and response headers in separate documentation sections:

~~~asciidoc
= Orders API
:snippets: build/generated-snippets

== Create order

=== Request headers
include::{snippets}/orders/create/request-headers.adoc[]

=== HTTP request
include::{snippets}/orders/create/http-request.adoc[]

=== Response headers
include::{snippets}/orders/create/response-headers.adoc[]

=== HTTP response
include::{snippets}/orders/create/http-response.adoc[]
~~~

`request-headers.adoc` tells clients what to send; `response-headers.adoc` tells clients what the server returns. Both tables must match the assertions and descriptors in the tests.

## 12. Integrating Gradle and CI

Once the Asciidoctor plugin and `asciidoctor` task are configured, wire the documentation task to the snippet-generating test task:

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

In CI:

~~~bash
./gradlew clean test asciidoctor
~~~

Tests verify request/response headers and validate descriptors; REST Docs generates snippets; Asciidoctor builds the documentation. When a required header is missing or a response returns an incorrect value, the test task fails and prevents the build/publish step from proceeding as if the contract were still valid. With plain Markdown, a separate step is required to embed or link snippets; `include::` syntax belongs to Asciidoctor.

## 13. Common Errors and How to Fix Them

| Symptom | Cause and Resolution |
| --- | --- |
| Request header descriptor cannot find header | Check whether the request builder sends the header, whether the header name is spelled correctly, and whether the operation is documented properly. |
| Assuming `requestHeaders(...)` validates exact values | Descriptors verify that headers are documented and generate snippets; verify values on the receiving side with a probe/filter/controller. |
| `expectHeader().exists(...)` passes but value is wrong | Use `valueEquals(...)` or `valueMatches(...)` when the contract specifies content. |
| Using response assertions to infer request headers | `expectHeader()` checks the response; verify the request at the endpoint or receiving collaborator. |
| Confusing request headers with response headers | Use `requestHeaders(...)` for client → server and `responseHeaders(...)` for server → client. |
| Optional header breaks tests | Use the `.optional()` descriptor if the header is allowed to be absent; do not ignore required headers. |
| Dynamic headers make tests flaky | Assert structure or presence instead of fixed values; use stable fixtures when recording snippets. |
| Snippet leaks cookies/tokens | Use dummy data and preprocessors to normalize the record; inspect snippets before sharing. |
| Header snippets are missing | Check the REST Docs filter, operation identifier, and descriptors inside `document(...)`. |

## 14. Practice Exercises

1. Run the integration test and open `request-headers.adoc` and `response-headers.adoc`.
2. Remove the `X-Request-Id` header from the request while keeping the required descriptor; observe how REST Docs detects the missing header in the recorded request.
3. Return the wrong `Location` and confirm `valueEquals(...)` fails the test.
4. Change the `exists("ETag")` assertion to `valueMatches(...)` with the ETag format defined by the API.
5. Use `@RequestHeader` in a probe to confirm the specific request header value reached the controller.
6. Add an optional response header, test both the branch with the header and the branch without it; use `.optional()` accurately per the contract.
7. Include the snippets in Asciidoctor and configure CI to run tests before building documentation.

## 15. Key Takeaways

- The request builder sets headers sent by the client; `requestHeaders(...)` documents headers in the operation and checks presence against descriptors.
- To confirm a request header value was received by the endpoint, verify it on the receiving side; never use `expectHeader()` to infer request values.
- `expectHeader()` verifies response headers: presence, absence, exact value, regex match, or list of values.
- `requestHeaders(...)` and `responseHeaders(...)` describe two different communication directions; place descriptors on the correct side.
- Combine assertions with descriptors so tests both verify behavior and generate clear snippets.
- Use stable test data, preprocess sensitive headers when needed, and run tests before Asciidoctor/CI so documentation reflects verified HTTP exchanges.
