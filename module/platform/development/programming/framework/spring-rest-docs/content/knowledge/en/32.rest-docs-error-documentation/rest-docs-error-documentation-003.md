# Status Codes and Headers in Error Responses

## 1. Lesson Objectives

In the **SPRING_REST_DOCS** module, we generate verifiable REST API documentation through HTTP tests using MockMvc, WebTestClient, or REST Assured. Tests send requests, assert responses, and Spring REST Docs generates snippets for requests, responses, payloads, parameters, and headers. The snippets are compiled with Asciidoctor/Markdown and integrated into the build and CI pipeline.

When an API returns an error, the HTTP status and response headers are part of the contract. The body may contain an error code and message, but clients still need the status to classify the result and need headers to know how to authenticate, retry, trace requests, or handle redirects. Documentation that describes only the body while omitting status codes and headers is insufficient for proper integration.

This lesson guides you through testing and documenting error status codes and response headers with Spring REST Docs. After this lesson, you will be able to:

- Choose HTTP status codes that match the semantics of the error.
- Distinguish status classes from business error codes in the body.
- Test status codes with MockMvc and let REST Docs record the status in HTTP response snippets.
- Document response headers using `responseHeaders(...)` and `headerWithName(...)`.
- Describe headers such as `WWW-Authenticate`, `Retry-After`, `Location`, `Allow`, `Content-Type`, and correlation IDs.
- Handle headers that only appear in specific error branches.
- Include error response snippets into Asciidoctor and CI.

## 2. Status Codes Are Part of the API Contract

The HTTP status describes the result of a request at the HTTP layer. Clients, proxies, caches, gateways, and middleware can rely on the status to decide how to handle a response before reading the error body.

Example:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/json
Retry-After: 5
X-Request-Id: req-91a7

{
  "code": "ORDER_STATE_CONFLICT",
  "message": "The order cannot be cancelled in its current state."
}
~~~

In this response:

- 409 Conflict indicates that the request conflicts with the current state of the resource.
- ORDER_STATE_CONFLICT identifies the specific scenario in the application contract.
- Retry-After indicates the time or wait interval if the API defines retry behavior for this case.
- X-Request-Id provides a reference ID for looking up logs.

A status code does not replace an error code, and an error code does not replace a status code. One status code can be used for multiple error codes; the body explains the more specific cause.

## 3. Choosing Status Codes by Semantics

The following table shows common API cases:

| Status | Name | Example Error | Client Guidance |
| ---: | --- | --- | --- |
| 400 | Bad Request | Invalid body or parameters | Fix the request according to validation details. |
| 401 | Unauthorized | Missing or invalid credentials | Re-authenticate according to the API's published mechanism. |
| 403 | Forbidden | Authenticated but lacking sufficient permissions | Check assigned permissions or roles. |
| 404 | Not Found | Resource does not exist | Check the resource ID or access state. |
| 405 | Method Not Allowed | HTTP method is not supported by the endpoint | Use a method allowed by the API; check the Allow header if present. |
| 409 | Conflict | Resource state conflicts with the operation | Read the current state and decide the next step. |
| 412 | Precondition Failed | Conditions such as If-Match are not met | Re-read the resource or update the validator. |
| 415 | Unsupported Media Type | Request Content-Type is not supported | Send a media type published by the endpoint. |
| 422 | Unprocessable Content | Syntactically valid content that cannot be processed per rules | Fix the content according to business/validation details. |
| 429 | Too Many Requests | Request rate limit exceeded | Respect the retry policy and Retry-After if returned. |
| 500 | Internal Server Error | Unexpected server-side error | Retry according to a safe policy and provide the trace ID when contacting support. |
| 503 | Service Unavailable | Service temporarily unavailable | Retry later; check Retry-After if present. |

These are general guidelines, not mandatory rules for every API. Choose status codes according to endpoint semantics and the HTTP standards your system commits to. Do not use 200 for errors simply because the body has success=false; likewise, do not use 500 for input errors that the client can fix.

### 3.1. Distinguishing 401 and 403

- 401 indicates that the request has not been validly authenticated; the response typically includes WWW-Authenticate when the endpoint uses an HTTP authentication scheme.
- 403 indicates that the server understood the request but refuses to fulfill it due to access permissions or policy.

Do not return 401 and 403 interchangeably. Clients may require different handling flows: updating credentials versus requesting permission grants.

### 3.2. Distinguishing 404 and 409

- 404 is appropriate when the requested resource is not found or the API chooses not to disclose the resource's existence.
- 409 is appropriate when the request conflicts with the current state of the resource.

For example, a nonexistent order ID can return 404; an order that exists but has already been shipped and therefore cannot be cancelled can return 409.

## 4. HTTP Response Snippets Record Status and Headers

Spring REST Docs generates http-response.adoc from the response received by the test. This snippet contains the status line, response headers, and body:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/json
Retry-After: 5
X-Request-Id: req-91a7

{
  "code": "ORDER_STATE_CONFLICT",
  "message": "The order cannot be cancelled in its current state."
}
~~~

REST Docs does not require a separate descriptor to record the status line. Tests verify the status with assertions, while http-response.adoc shows the actual status of the documented response. responseHeaders(...) adds a table describing the meaning of headers that clients need to understand.

The two parts complement each other:

1. The HTTP response snippet shows the concrete response that occurred.
2. The response headers snippet explains which headers are part of the contract and what they mean.

## 5. Testing Status Codes with MockMvc

Use status matchers to assert the expected status before generating snippets:

~~~java
mockMvc.perform(delete("/api/orders/{id}", 42))
    .andExpect(status().isConflict())
    .andExpect(jsonPath("$.code").value("ORDER_STATE_CONFLICT"))
    .andDo(document("orders/cancel-conflict"));
~~~

Commonly used matchers:

~~~java
status().isBadRequest();          // 400
status().isUnauthorized();       // 401
status().isForbidden();          // 403
status().isNotFound();            // 404
status().isMethodNotAllowed();    // 405
status().isConflict();            // 409
status().isTooManyRequests();     // 429
status().isInternalServerError(); // 500
status().isServiceUnavailable();  // 503
~~~

If a convenience matcher is not available in your project's Spring Test version, you can use status().is(409) or status().isEqualTo(HttpStatus.CONFLICT.value()). Choose APIs available in your actual dependency version.

Do not stop after asserting only the status. You should also assert the error code and key fields in the body to confirm the status corresponds to the right cause.

## 6. Documenting Response Headers

Spring REST Docs uses responseHeaders(...) and headerWithName(...) to describe response headers:

~~~java
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
~~~

Example:

~~~java
responseHeaders(
    headerWithName("Content-Type")
        .description("Media type of the error response."),
    headerWithName("X-Request-Id")
        .description("Request ID for looking up support logs.")
)
~~~

When descriptors are passed to document(...), REST Docs checks that the documented headers exist in the actual response. If the response contains an undocumented header, REST Docs may report an undocumented header depending on snippet configuration and version.

Do not add a header to descriptors just because you want it to appear in the documentation. The test must actually return that header. If a header is optional, mark it optional according to the contract.

## 7. Common Response Headers in Errors

### 7.1. Content-Type

Tells the client the format of the error body:

~~~http
Content-Type: application/json
~~~

If the API uses Problem Details, the media type is typically:

~~~http
Content-Type: application/problem+json
~~~

Documenting Content-Type helps clients choose the appropriate parser. Tests should verify the media type matches the body.

### 7.2. WWW-Authenticate

A 401 response may indicate the authentication scheme:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="api"
Content-Type: application/json
~~~

Document the header:

~~~java
headerWithName("WWW-Authenticate")
    .description("Authentication challenge the client must satisfy.")
~~~

Do not include access tokens or credentials in examples. The challenge header describes the scheme/realm; clients obtain and send valid credentials using the published mechanism.

### 7.3. Retry-After

Some 429 or 503 responses may return:

~~~http
Retry-After: 30
~~~

The value can represent the number of seconds to wait or an HTTP date per HTTP syntax. Documentation should explain how the API uses the header and how clients must respect it.

~~~java
headerWithName("Retry-After")
    .description("Duration or timestamp the client should wait before retrying.")
~~~

Do not assume every 429/503 must have Retry-After. Only document the header when the API actually emits it and commits to that behavior.

### 7.4. Location

Location can appear in redirect responses or some resource creation responses:

~~~http
HTTP/1.1 201 Created
Location: /api/orders/42
~~~

If the API returns Location in a specific error response, document the exact meaning specific to that endpoint. Do not assume Location is always an error header.

~~~java
headerWithName("Location")
    .description("URI referencing the related resource per the endpoint contract.")
~~~

### 7.5. Allow

405 Method Not Allowed can return the list of supported methods:

~~~http
HTTP/1.1 405 Method Not Allowed
Allow: GET, HEAD
~~~

Document the header:

~~~java
headerWithName("Allow")
    .description("HTTP methods supported by the endpoint.")
~~~

This header helps clients pick a valid method rather than guessing randomly.

### 7.6. Correlation ID

An API may return a header such as X-Request-Id or Traceparent to link the request to observability systems:

~~~http
X-Request-Id: req-91a7
~~~

Document the system's exact header name:

~~~java
headerWithName("X-Request-Id")
    .description("Correlation ID for support teams to look up the request.")
~~~

Example values should be stable so snippets remain readable. Do not put tokens, session IDs, or sensitive identifying data in sample headers.

## 8. Required and Optional Headers

Some headers appear only in specific error branches. For example:

| Header | 401 | 403 | 409 | 429 | 503 |
| --- | --- | --- | --- | --- | --- |
| Content-Type | Usually present if body exists | Usually present if body exists | Usually present if body exists | Usually present if body exists | Usually present if body exists |
| WWW-Authenticate | May be present per auth scheme | Usually not used as a challenge | Not commonly used | Not commonly used | Not commonly used |
| Retry-After | Per specific policy | Per specific policy | May be present if specified by API | May be present | May be present |
| X-Request-Id | Per tracing configuration | Per tracing configuration | Per tracing configuration | Per tracing configuration | Per tracing configuration |

This table only illustrates likelihood; the API's specific contract is the final authority.

If a descriptor is used for responses where a header may be absent, mark it optional:

~~~java
headerWithName("Retry-After")
    .description("Wait time before retrying, if provided.")
    .optional()
~~~

Optional means the header may not appear in the documented response. Do not use optional to hide failures when a header required by the contract is missing; let tests or REST Docs catch the violation.

If each error category has its own operation, it is usually better to describe the exact headers actually present on that operation instead of creating one overly broad header table with almost everything marked optional.

## 9. Complete Example: Documenting 409 Conflict

Suppose cancelling a shipped order returns 409 along with an error code and two response headers:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/json
Retry-After: 5
X-Request-Id: req-test-409

{
  "code": "ORDER_STATE_CONFLICT",
  "message": "The order cannot be cancelled in its current state."
}
~~~

MockMvc test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
@Import(ApiExceptionHandler.class)
class OrderConflictDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void documentsCancelConflict() throws Exception {
        this.mockMvc.perform(delete("/api/orders/{id}", 42))
            .andExpect(status().isConflict())
            .andExpect(jsonPath("$.code").value("ORDER_STATE_CONFLICT"))
            .andDo(document("orders/cancel-conflict",
                responseHeaders(
                    headerWithName("Content-Type")
                        .description("Media type of the error response."),
                    headerWithName("Retry-After")
                        .description("Number of seconds the client should wait before retrying."),
                    headerWithName("X-Request-Id")
                        .description("Request ID for looking up support logs.")
                ),
                responseFields(
                    fieldWithPath("code")
                        .description("Stable error code for the order state conflict."),
                    fieldWithPath("message")
                        .description("Explanation of why the order cannot be cancelled.")
                )
            ));
    }
}
~~~

The example assumes MockMvc has been configured with the REST Docs filter and the endpoint returns the status/headers/body described. If the application does not return Retry-After for 409, remove that descriptor or mark it optional if the header can genuinely appear conditionally.

REST Docs generates the snippets:

~~~text
build/generated-snippets/orders/cancel-conflict/
├── http-request.adoc
├── http-response.adoc
├── response-headers.adoc
└── response-fields.adoc
~~~

http-response.adoc displays the actual status line and headers; response-headers.adoc explains the meaning of the headers; response-fields.adoc describes the body.

## 10. Documenting 401 Unauthorized and WWW-Authenticate

Example test verifying the challenge header:

~~~java
mockMvc.perform(get("/api/profile"))
    .andExpect(status().isUnauthorized())
    .andExpect(header().exists("WWW-Authenticate"))
    .andDo(document("profile/unauthorized",
        responseHeaders(
            headerWithName("WWW-Authenticate")
                .description("Authentication scheme the client needs to use."),
            headerWithName("Content-Type")
                .description("Media type of the error response.")
        )
    ));
~~~

The header matcher confirms the challenge is actually present. The response headers descriptor explains its meaning to readers. You should add body/error code assertions if the API specifies an error payload.

If the system uses Bearer tokens, do not include sample tokens that look valid in documentation. Describe how to obtain credentials in the authentication section of the API documentation.

## 11. Documenting 429 Too Many Requests and Retry-After

429 is commonly used when a client exceeds rate limits. If the API returns Retry-After, documentation should clearly state that the client needs to wait before resending.

~~~java
mockMvc.perform(get("/api/reports"))
    .andExpect(status().isTooManyRequests())
    .andExpect(header().string("Retry-After", "30"))
    .andDo(document("reports/rate-limited",
        responseHeaders(
            headerWithName("Retry-After")
                .description("Number of seconds the client must wait before the next attempt."),
            headerWithName("X-Request-Id")
                .description("Request ID for looking up rate-limit events.")
        )
    ));
~~~

If the Retry-After value varies over time, use a test fixture or a fixed clock to keep snippets deterministic. Do not fake values in assertions: tests must still verify the response complies with the actual policy.

## 12. Documenting 405 Method Not Allowed and Allow

405 indicates the HTTP method used is not supported for the resource. The Allow header lists permitted methods:

~~~java
mockMvc.perform(post("/api/orders/42"))
    .andExpect(status().isMethodNotAllowed())
    .andExpect(header().string("Allow", "GET, HEAD"))
    .andDo(document("orders/method-not-allowed",
        responseHeaders(
            headerWithName("Allow")
                .description("List of HTTP methods supported by the resource.")
        )
    ));
~~~

The exact Allow value depends on mappings and the framework/application. Assert according to the actual contract, and avoid hardcoding the method list if endpoint configuration changes intentionally.

## 13. Documenting Location and Related Routing Headers

Some responses related to resources or redirects include Location. For 201 Created, this header typically points to the newly created resource:

~~~http
HTTP/1.1 201 Created
Location: /api/orders/42
~~~

Test and document:

~~~java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content(validOrderJson))
    .andExpect(status().isCreated())
    .andExpect(header().string("Location", "/api/orders/42"))
    .andDo(document("orders/create",
        responseHeaders(
            headerWithName("Location")
                .description("URI of the newly created order.")
        )
    ));
~~~

This is a success response example illustrating Location. If an error response includes Location under a specific contract, document it in the corresponding error operation and clearly explain its meaning.

## 14. Combining Response Headers and Response Fields

An error response often needs both groups of descriptors:

~~~java
document("orders/cancel-conflict",
    responseHeaders(
        headerWithName("Content-Type")
            .description("Media type of the response."),
        headerWithName("X-Request-Id")
            .description("Reference ID for looking up logs.")
    ),
    responseFields(
        fieldWithPath("code")
            .description("Business error code."),
        fieldWithPath("message")
            .description("Message explaining the error.")
    )
)
~~~

Do not confuse them:

- responseHeaders(...) describes HTTP response metadata.
- responseFields(...) describes fields in the response body.
- status() assertions verify the status code.
- http-response.adoc records the status line, headers, and body of the actual response.

Separating these responsibilities keeps documentation showing both a concrete response and an explanation of its contract.

## 15. Organizing Documentation by Status Group

You can organize the error chapter by status class or by business domain:

| Organization Approach | Example Sections | When Appropriate |
| --- | --- | --- |
| By status | 4xx Client Errors, 5xx Server Errors | APIs with many endpoints needing general status lookup. |
| By business domain | Order errors, Authentication errors, Rate limits | Clients typically integrate by domain/business flow. |
| Combined | Status overview linking to operation snippets | Large documentation needing both quick lookup and concrete examples. |

You should have a summary table of important statuses/error codes/headers, then include snippets from each test. Summary tables do not replace test-verified response snippets.

## 16. Asciidoctor and CI Integration

Asciidoctor can include HTTP response and header snippets:

~~~asciidoc
== Cancel Order: State Conflict

=== HTTP response
include::{snippets}/orders/cancel-conflict/http-response.adoc[]

=== Response headers
include::{snippets}/orders/cancel-conflict/response-headers.adoc[]

=== Response fields
include::{snippets}/orders/cancel-conflict/response-fields.adoc[]
~~~

Assuming the Asciidoctor plugin is configured, connect the documentation task to tests:

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

Run in CI:

~~~bash
./gradlew clean test asciidoctor
~~~

Tests assert status/headers/body; REST Docs generates snippets; Asciidoctor builds documentation from the fresh output. If a status or header violates the contract, tests fail and CI should not publish new documentation.

With plain Markdown, Asciidoctor's include:: syntax is not processed automatically. Use a separate build step to embed snippets or link to generated files.

## 17. Common Pitfalls and Troubleshooting

| Symptom | Cause and Solution |
| --- | --- |
| HTTP response snippet has wrong status | Test did not assert status or endpoint mapping returns the wrong status; add a specific status matcher. |
| Response headers snippet is not generated | responseHeaders(...) was not passed to document(...). |
| REST Docs reports missing header | Descriptor documents a header absent from the response; check actual response or mark optional per contract. |
| Header appears but meaning is unclear | Description is too generic; explain what the client must do with the header. |
| 401 lacks WWW-Authenticate | Check authentication mechanism and the API's challenge contract. |
| 429 lacks Retry-After | API may not guarantee this header; do not document as required if the response does not return it. |
| 405 misses Allow | Check method mappings and the response produced by the framework/application. |
| Snippet contains random trace ID | Use a deterministic fixture/clock or appropriate preprocessor; still assert header presence. |
| Status table and response snippet contradict | Use test-generated snippets as the source of truth and sync the summary table with the current contract. |

## 18. Practice Exercise

1. Create an order cancellation endpoint that returns 409 when the state does not allow cancellation.
2. Write a MockMvc test asserting status 409 and error code ORDER_STATE_CONFLICT.
3. Document Content-Type and X-Request-Id using responseHeaders(...).
4. Create an endpoint requiring authentication; test 401 and WWW-Authenticate.
5. Create a rate-limited endpoint; test 429 and Retry-After.
6. Test an endpoint with an unsupported method; verify 405 and Allow.
7. Create a 503 response with Retry-After if specified by the service contract.
8. Include http-response, response-headers, and response-fields snippets into Asciidoctor.
9. Run Gradle/CI and verify the status and headers in the generated artifact.

## 19. Key Takeaways

- HTTP status is an essential part of the error contract; choose status codes by semantics rather than convenience.
- Error codes in the body supplement specific causes that status codes alone cannot express.
- http-response.adoc records the status line, response headers, and body of the actual response.
- Use responseHeaders(...) and headerWithName(...) to document headers; use optional() when the contract allows a header to be absent.
- WWW-Authenticate, Retry-After, Allow, Location, Content-Type, and correlation IDs have distinct meanings; only document headers the API actually returns.
- Combine status assertions, response header descriptors, and response field descriptors to verify the entire error response.
- Run tests before Asciidoctor in CI so documentation reflects verified status codes and headers.

## 20. References

- [Spring REST Docs — HTTP Headers](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/headers.html): documenting request/response headers with snippets.
- [Spring REST Docs — Documenting HTTP Responses](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html): how to generate HTTP response snippets.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): definitions of status codes and semantics of HTTP headers.
