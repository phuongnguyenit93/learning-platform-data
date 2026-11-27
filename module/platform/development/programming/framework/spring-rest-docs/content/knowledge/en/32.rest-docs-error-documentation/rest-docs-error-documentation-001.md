# Documenting Error Structures and Error Codes

## 1. Lesson Objectives

In the **SPRING_REST_DOCS** module, we generate verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. Tests send requests, assert responses, and Spring REST Docs generates snippets for requests, responses, payloads, parameters, and headers. The snippets are compiled with Asciidoctor/Markdown and integrated into the build and CI.

An API needs to describe both success and failure cases. When a request is invalid, integrators need to know which HTTP status is returned, which fields make up the error body, what the error code means, and what information they can use to fix the request or contact support. If every endpoint returns errors in a different format or the documentation only states “400 Bad Request”, it is very difficult for clients to handle errors consistently.

This lesson focuses on documenting error structures and error codes with Spring REST Docs. After this lesson, you will be able to:

- Design an error response with a stable structure and error codes.
- Write tests that assert HTTP status, response headers, and error payloads.
- Use response field descriptors to describe top-level fields, nested fields, and lists of errors.
- Distinguish business error codes from HTTP status codes.
- Document multiple error categories without blurring differences in root causes.
- Include error snippets into Asciidoctor and run the build in CI.

## 2. Why Document Errors?

Suppose a client submits an order without a shipping address:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json

{
  "productId": "BOOK-01",
  "quantity": 2
}
~~~

The API returns an error:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "code": "ORDER_SHIPPING_ADDRESS_REQUIRED",
  "message": "Shipping address is required.",
  "details": [
    {
      "field": "shippingAddress",
      "reason": "must not be blank"
    }
  ],
  "traceId": "req-7f3a91"
}
~~~

The client needs to know:

- HTTP 400 indicates the request is invalid at the protocol/contract layer.
- `ORDER_SHIPPING_ADDRESS_REQUIRED` is a machine-readable error code for branching error-handling logic.
- `message` is a human-readable explanation and should not be the only string the client uses to identify the error.
- `details` describes the field that needs to be fixed.
- `traceId` helps look up logs when needed.

Good error documentation helps API consumers answer three questions: where the request went wrong, which rules to follow when handling it, and what information to provide when requesting support.

## 3. Distinguishing HTTP Status and Application Error Codes

HTTP status codes and application error codes serve different roles:

| Component | Example | Purpose |
| --- | --- | --- |
| HTTP status | 400, 401, 403, 404, 409, 500 | Classifies the HTTP outcome so clients, proxies, and middleware can understand it. |
| Error code | ORDER_SHIPPING_ADDRESS_REQUIRED | Uniquely identifies the specific error case in the application contract. |
| Message | Shipping address is required. | Explains the error for human readers or logs; may be localized. |
| Details | field, reason | Provides specific details about invalid input fields or business state. |
| Trace/correlation ID | req-7f3a91 | Correlates the request with logs and observability systems. |

Do not encode every root cause into the HTTP status alone. Many different validation errors can share HTTP 400 while having different error codes. Similarly, do not use status 200 for every response just because the body contains a success/error flag; the HTTP status must accurately reflect the semantics of the result.

An HTTP status does not replace an error code, and an error code does not replace an HTTP status. Clients typically check the status to determine the general handling category, then inspect the code to handle the specific case.

## 4. Designing a Stable Error Schema

A simple schema can be shared across many endpoints:

~~~json
{
  "code": "ORDER_SHIPPING_ADDRESS_REQUIRED",
  "message": "Shipping address is required.",
  "details": [
    {
      "field": "shippingAddress",
      "reason": "must not be blank"
    }
  ],
  "traceId": "req-7f3a91"
}
~~~

Meaning of each field:

| Field | Data Type | Convention |
| --- | --- | --- |
| code | string | A stable code, unique within the defined API or domain scope. |
| message | string | Explanatory message; wording or language may change. |
| details | array | List of additional details; may be empty if the error is not tied to an input field. |
| details[].field | string | Name or path of the field causing the error. |
| details[].reason | string | Reason or rule that was not satisfied. |
| traceId | string | Correlation ID for tracing, if provided by the API. |

Important conventions:

1. Error codes must remain stable across releases; do not use `message` as a machine identifier.
2. `message` should not contain stack traces, SQL, internal class names, or sensitive secrets.
3. Do not return sensitive data or unnecessary input values in `details`.
4. Optional fields must be documented as allowed to be absent.
5. `traceId` should be a safe reference ID for troubleshooting, containing no authentication tokens or personal data.

If the project uses the HTTP Problem Details standard format, properties such as `type`, `title`, `status`, `detail`, `instance`, and extension members can be used. Do not arbitrarily mix two schemas. Choose one format as the primary contract and document all fields the API actually returns.

## 5. Organizing Error Codes

Error codes should describe the situation without depending on message phrasing or internal implementation locations.

Example:

| Error code | HTTP status | When returned |
| --- | ---: | --- |
| REQUEST_VALIDATION_FAILED | 400 | Request body or query fails validation. |
| ORDER_SHIPPING_ADDRESS_REQUIRED | 400 | Required shipping address is missing. |
| AUTHENTICATION_REQUIRED | 401 | Request is not authenticated. |
| ACCESS_DENIED | 403 | Identity is authenticated but lacks sufficient permissions. |
| ORDER_NOT_FOUND | 404 | Requested order was not found. |
| ORDER_STATE_CONFLICT | 409 | Current state does not allow the operation. |
| INTERNAL_ERROR | 500 | Unexpected server-side error. |

This is an illustrative set of codes; the project must define the actual code list, uniqueness scope, and compatibility policy. Changing or removing a published error code should be treated as an API contract change.

Do not reuse the same error code for two different causes if clients need to handle them differently. Do not create a new code simply because the message wording was rephrased.

## 6. Generating Error Responses in a Spring Application

Exception-to-error-response conversion can be centralized using `@RestControllerAdvice`. The following example uses simple DTOs:

~~~java
import java.util.List;

public record ApiError(
    String code,
    String message,
    List<ErrorDetail> details,
    String traceId
) {
}

public record ErrorDetail(
    String field,
    String reason
) {
}
~~~

Exception and handler:

~~~java
public class MissingShippingAddressException extends RuntimeException {
}
~~~

~~~java
import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(MissingShippingAddressException.class)
    ResponseEntity<ApiError> handleMissingShippingAddress() {
        ApiError error = new ApiError(
            "ORDER_SHIPPING_ADDRESS_REQUIRED",
            "Shipping address is required.",
            List.of(new ErrorDetail(
                "shippingAddress",
                "must not be blank"
            )),
            "req-test-001"
        );

        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(error);
    }
}
~~~

In a real application, `traceId` should be obtained from the request's correlation ID mechanism, such as a request attribute or tracing context, instead of a hardcoded constant. The example uses a constant to keep snippets stable and easy to read.

Do not return stack traces through `ApiError`. Stack traces belong in internal logs; API documentation should only describe information clients are allowed to receive.

## 7. Testing HTTP Status and Error Body

REST Docs generates snippets from tested operations. Before documenting an error, tests must verify the status and key fields:

~~~java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {
              "productId": "BOOK-01",
              "quantity": 2
            }
            """))
    .andExpect(status().isBadRequest())
    .andExpect(jsonPath("$.code")
        .value("ORDER_SHIPPING_ADDRESS_REQUIRED"))
    .andExpect(jsonPath("$.details[0].field")
        .value("shippingAddress"));
~~~

The status assertion verifies the HTTP contract; the code assertion verifies the error case; the details assertion confirms the client receives information to fix the request. Only after these assertions pass should you attach REST Docs `document()` to generate snippets.

If the status is right but the code is wrong, the test must fail. If the code is right but the server returns status 200 instead of 400, the test must also fail.

## 8. Documenting Error Responses with `responseFields`

Spring REST Docs uses `responseFields(...)` to describe the response body. For the schema above:

~~~java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
~~~

Descriptors:

~~~java
responseFields(
    fieldWithPath("code")
        .description("Stable error code for clients to identify the error case."),
    fieldWithPath("message")
        .description("Human-readable message explaining the error."),
    fieldWithPath("details")
        .description("List of details about invalid fields or conditions."),
    fieldWithPath("details[].field")
        .description("Name of the field causing the error."),
    fieldWithPath("details[].reason")
        .description("Reason the field failed to meet the rule."),
    fieldWithPath("traceId")
        .description("Correlation ID used to look up support logs.")
)
~~~

The `details[]` path describes fields inside each element of the array. Descriptors must match the actual JSON structure. If the JSON returns an object instead of an array, the path must change accordingly.

### 8.1. Documenting Optional Fields

If `traceId` is not always present, mark it as optional:

~~~java
fieldWithPath("traceId")
    .description("Correlation ID for looking up logs, if provided.")
    .optional()
~~~

`optional()` informs REST Docs that the field may be absent in the response. Do not mark a field optional just to make a test pass when the API is missing a field required by the contract.

### 8.2. Documenting Nested Structures

If `details` contains multiple properties or complex objects, declare each field explicitly:

~~~java
responseFields(
    fieldWithPath("code").description("Error code."),
    fieldWithPath("message").description("Error message."),
    fieldWithPath("details").description("List of error details."),
    fieldWithPath("details[].field").description("Path of the invalid field."),
    fieldWithPath("details[].reason").description("Reason validation failed."),
    fieldWithPath("traceId").description("Trace ID.")
)
~~~

If you only need to document a nested object such as `details` as a whole without describing each of its fields in the same table, use `subsectionWithPath("details")` with an appropriate description. In that case, the documentation explains that there is a subsection without listing the child schema in the current table; a separate table can be created for the subsection if integrators need the details.

## 9. Complete Example: Documenting a Validation Error

The example below assumes the test application has the controller and `ApiExceptionHandler` from the previous sections, and MockMvc is configured with REST Docs:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
@Import(ApiExceptionHandler.class)
class OrderErrorDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void documentsMissingShippingAddress() throws Exception {
        this.mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "productId": "BOOK-01",
                      "quantity": 2
                    }
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("ORDER_SHIPPING_ADDRESS_REQUIRED"))
            .andExpect(jsonPath("$.details[0].field")
                .value("shippingAddress"))
            .andDo(document("orders/create-validation-error",
                responseFields(
                    fieldWithPath("code")
                        .description("Stable error code for clients to identify the cause."),
                    fieldWithPath("message")
                        .description("Message describing the error."),
                    fieldWithPath("details")
                        .description("List of validation details."),
                    fieldWithPath("details[].field")
                        .description("Name of the invalid field."),
                    fieldWithPath("details[].reason")
                        .description("Reason validation failed."),
                    fieldWithPath("traceId")
                        .description("Correlation ID for looking up logs.")
                )
            ));
    }
}
~~~

The operation identifier `create-validation-error` clearly indicates this is a validation error response for the order creation operation. Snippet names should be meaningful; avoid generic names like `error-1` or `failed`.

After the test runs, REST Docs generates the corresponding snippets, including:

~~~text
build/generated-snippets/
└── orders/
    └── create-validation-error/
        ├── http-request.adoc
        ├── http-response.adoc
        └── response-fields.adoc
~~~

The actual directory name is determined by the operation identifier; the example above illustrates the expected path structure if that identifier is used.

## 10. Documenting Multiple Error Categories

An endpoint can return multiple types of errors. You should write separate tests for each case that has a different status or error code:

| Operation ID | HTTP status | Error code | Scenario |
| --- | ---: | --- | --- |
| orders/create-validation-error | 400 | ORDER_SHIPPING_ADDRESS_REQUIRED | Missing required field. |
| orders/get-not-found | 404 | ORDER_NOT_FOUND | Order not found. |
| orders/cancel-conflict | 409 | ORDER_STATE_CONFLICT | Order state does not allow cancellation. |
| orders/admin-forbidden | 403 | ACCESS_DENIED | User lacks sufficient permissions. |

Each test should verify:

1. Expected HTTP status.
2. Specific error code.
3. Required fields in the error body.
4. Necessary error headers if specified by the API, such as `WWW-Authenticate` for certain authentication responses.
5. Response content does not leak internal information.

If a common error schema is shared, descriptors can be reused, but each operation should still assert its own error code. Do not combine all errors into one branching test and only document the first branch.

## 11. Business Errors, Validation Errors, and System Errors

Different error categories may share a common payload but need clear explanations of their differences:

| Category | Example | Documentation approach |
| --- | --- | --- |
| Validation | Missing field, invalid format, or out-of-range value | State the field, reason, and how to fix the request. |
| Authentication | Missing, expired, or invalid token | State status, error code, and how the client should re-authenticate. Do not include tokens in snippets. |
| Authorization | User lacks permission for the operation | Explain required permissions at the level clients are permitted to know. |
| Not found | Resource does not exist or is inaccessible | Explain the error code and relevant resource identifier. |
| Conflict | Current state does not allow the operation | State the business conditions that must be satisfied or the next action. |
| Server error | Unexpected error | Provide a reference/trace ID; do not expose stack traces or internal details. |

401 and 403 have different semantics; 404 and 409 cannot substitute for each other merely to unify handling. Status codes and error codes must reflect the actual API contract.

## 12. Using Problem Details When Chosen by the Project

Some APIs choose the Problem Details format instead of a custom schema. Example payload:

~~~json
{
  "type": "https://api.example.com/problems/validation-error",
  "title": "Request validation failed",
  "status": 400,
  "detail": "One or more fields are invalid.",
  "instance": "/api/orders",
  "code": "ORDER_SHIPPING_ADDRESS_REQUIRED",
  "errors": [
    {
      "field": "shippingAddress",
      "reason": "must not be blank"
    }
  ]
}
~~~

Core properties describe the problem type, title, HTTP status, detail, and related instance. Extension properties such as `code` and `errors` belong to the API's own contract. Document all fields the server actually returns, and explain API-defined extension fields.

The content type for Problem Details is typically `application/problem+json`. Tests should assert both status and content type if the API commits to this format:

~~~java
.andExpect(status().isBadRequest())
.andExpect(content().contentTypeCompatibleWith("application/problem+json"))
~~~

Do not document a custom payload as Problem Details if the response does not follow the corresponding structure and media type. The schema name does not substitute for verifying the actual response.

## 13. Including Response Headers in Error Documentation

Besides the body, error responses may include important headers:

- `Content-Type`: data type of the error body.
- `WWW-Authenticate`: challenge information in 401 responses according to the authentication scheme.
- `Retry-After`: timestamp or wait duration before retrying, when the API uses an appropriate mechanism.
- `X-Request-Id` or trace header: reference ID to assist troubleshooting.

These can be described with `responseHeaders(...)`:

~~~java
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;

responseHeaders(
    headerWithName("Content-Type")
        .description("Media type of the error response."),
    headerWithName("X-Request-Id")
        .description("Request ID for looking up support logs.")
)
~~~

Only describe headers actually returned by the response. If a header only appears in one error branch, use an `optional` descriptor when a shared snippet is used for operations that may omit that header; if each error has its own operation, describe the exact headers of the corresponding response.

## 14. Adding Error Snippets to Asciidoctor

After tests generate snippets, you can create a dedicated documentation section for errors:

~~~asciidoc
== Errors

=== Create order: missing shipping address

HTTP response:

include::{snippets}/orders/create-validation-error/http-response.adoc[]

Response fields:

include::{snippets}/orders/create-validation-error/response-fields.adoc[]
~~~

You can create an error code catalog table in the overview section:

~~~asciidoc
[cols="2,1,3", options="header"]
|===
| Error code | HTTP status | Meaning

| ORDER_SHIPPING_ADDRESS_REQUIRED
| 400
| Missing shipping address

| ORDER_NOT_FOUND
| 404
| Order not found

| ORDER_STATE_CONFLICT
| 409
| Order state does not allow the operation
|===
~~~

A summary table helps quick lookup; the `response-fields` snippet provides the exact schema verified by tests. Do not let a manual error code table contradict operation snippets.

## 15. Integrating Gradle and CI

Assuming the Asciidoctor plugin is configured, connect the documentation task to the snippet-generating test task:

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

Run:

~~~bash
./gradlew clean test asciidoctor
~~~

If tests asserting the error status or error code fail, the `test` task fails and the documentation build step should not produce an artifact considered valid. CI thus verifies both error behavior and generated documentation content simultaneously.

With plain Markdown, Asciidoctor's `include::` syntax is not processed automatically; a separate step is needed to embed snippets or link to snippet files.

## 16. Common Pitfalls and Troubleshooting

| Symptom | Cause and Solution |
| --- | --- |
| Only HTTP response snippet exists, no fields table | `responseFields(...)` was not passed to `document(...)`, or descriptors do not match the payload. |
| REST Docs reports undocumented payload field | JSON response contains an undocumented field; add a descriptor or handle the field intentionally according to the contract. |
| Test passes even when error code is wrong | No assertion on the `code` field; add `jsonPath`/`value` or an equivalent assertion. |
| Status is right but error body is inconsistent | Exception handlers return different schemas; standardize DTOs and exception mapping. |
| `details` is an array but descriptor uses an object path | Use paths matching the actual structure, e.g., `details[].field`. |
| Optional field causes documentation failure | Mark `optional()` when the contract allows the field to be absent. |
| Error response leaks stack trace | Adjust the exception handler/serializer; only return information the client needs. |
| Changing Trace ID makes snippets hard to read | Use a stable fixture or a preprocessor to normalize values when generating snippets; tests must still assert that the trace ID header/body is present if required by the contract. |
| Error code table drifts from payload | Treat test-generated snippets as the verification source and keep the summary table synchronized with the managed error code list. |

## 17. Practice Exercise

1. Create an `ApiError` DTO with `code`, `message`, `details`, and `traceId`.
2. Write a `@RestControllerAdvice` that maps `MissingShippingAddressException` to HTTP 400.
3. Write a MockMvc test asserting the status, error code, and `details[0].field`.
4. Add `responseFields(...)` to describe the entire error schema and generate `response-fields.adoc`.
5. Mark `traceId` as `optional` if the contract allows it to be absent; test both branches with and without the field.
6. Add 404 and 409 tests, using distinct operation identifiers and distinct error codes.
7. If the API uses Problem Details, write a test asserting content type, status, and extension fields.
8. Include error snippets into the Errors section of Asciidoctor and run Gradle/CI.

## 18. Key Takeaways

- HTTP status classifies outcomes at the HTTP layer; error codes identify specific API error cases.
- Error schemas should be stable, clearly distinguish required/optional fields, and never expose internal details.
- Verify status, error code, and key fields before calling `document(...)`.
- Use `responseFields(...)` and `fieldWithPath(...)` to document the body; use `subsectionWithPath(...)` when only describing a child object at a high level.
- Each error category needs the right status/code and separate operation examples when behavior differs.
- Document response headers if they are part of the error contract.
- Asciidoctor assembles HTTP response and `response-fields` snippets; CI runs tests before building documentation.

## 19. References

- [Spring REST Docs — Documenting HTTP Responses](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html): how to document responses and payloads using snippets.
- [Spring REST Docs — Payload Snippets](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/payloads.html): field descriptors, nested paths, optional fields, and subsection documentation.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): standard format for representing HTTP errors if the API chooses to adopt it.
