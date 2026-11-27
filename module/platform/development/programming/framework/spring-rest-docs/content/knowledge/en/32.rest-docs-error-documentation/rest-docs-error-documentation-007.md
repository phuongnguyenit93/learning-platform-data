# Distinguishing Technical Errors and Business Errors

## 1. Why Distinguish Between the Two Error Categories?

In the **Spring REST Docs (SPRING_REST_DOCS)** module under the **Error Documentation** chapter, HTTP tests not only describe successful responses, but also need to record cases where the API rejects a request or cannot complete processing. Good error documentation tells clients whether they need to fix the request, adjust the business flow, or retry after a system incident.

Two common error categories:

- **Business/domain error:** the request is syntactically valid and may be authenticated, but violates domain rules. Examples: insufficient balance, an already shipped order cannot be cancelled, an account is suspended under policy, or a product is no longer available.
- **Technical/infrastructure error:** the system cannot process the request due to infrastructure, dependency, or implementation failures. Examples: database unreachable, external service timeout, message broker down, or an unexpected exception.

Clients handle these two categories differently. Business errors usually need to be displayed to users or prompt an action change; technical errors may require controlled retries, circuit breakers, fallbacks, or asking the user to try again later.

In Spring REST Docs, each error category should have its own tests and snippets. Tests assert the actual HTTP status, headers, and error payload; descriptors verify the response structure so documentation never describes an unimplemented error contract.

Examples use **Spring Boot 3.5, Spring REST Docs 3.x, JUnit Jupiter, and MockMvc**. With WebTestClient or REST Assured, the verification principles remain the same even though the request-sending API differs.

## 2. Classifying Errors by Origin and Recoverability

| Criterion | Business Error | Technical Error |
| --- | --- | --- |
| Origin | Domain rules or resource state | Infrastructure, dependency, configuration, or bug |
| Request | May be syntactically valid | May be valid, but processing is interrupted |
| Resolution | Change data/action or wait for business conditions | Controlled retry, fallback, or incident handling |
| Examples | INSUFFICIENT_BALANCE, ORDER_ALREADY_SHIPPED | DATABASE_UNAVAILABLE, UPSTREAM_TIMEOUT |
| Typical HTTP status | 400, 403, 404, 409, 422 depending on semantics | 500, 502, 503, 504 depending on cause and gateway role |
| Retry | Usually do not retry the exact same request if conditions have not changed | May retry if the operation is safe and the failure is transient |

Do not classify solely by exception class name. The same technical exception may map to different responses depending on the contract; the same business error may have multiple reasonable HTTP statuses depending on semantics. Choose statuses according to HTTP meaning and document them consistently.

Examples of business errors:

- ORDER_ALREADY_SHIPPED: the order has transitioned to a state that does not allow cancellation.
- INSUFFICIENT_STOCK: inventory quantity is insufficient.
- ACCOUNT_SUSPENDED: the account is temporarily suspended under policy.
- DUPLICATE_RESOURCE: a resource with a unique business key already exists.

Examples of technical errors:

- DATABASE_UNAVAILABLE: the application cannot connect to the database.
- PAYMENT_PROVIDER_TIMEOUT: the payment provider did not respond in time.
- MESSAGE_BROKER_UNAVAILABLE: unable to send message to the broker.
- UNEXPECTED_ERROR: unexpected error requiring investigation via internal logs/traces.

Error code names should be stable and independent of exception class names or internal implementation details. Clients rely on codes to decide control flow; humans read messages to understand the situation.

## 3. Choosing Appropriate HTTP Status Codes

| Status | When Appropriate |
| --- | --- |
| 400 Bad Request | Request is invalid or cannot be parsed |
| 401 Unauthorized | Authentication credentials are missing or invalid |
| 403 Forbidden | Authenticated, but not permitted to perform the action |
| 404 Not Found | Resource or endpoint not found |
| 409 Conflict | Conflicts with the current state of the resource |
| 422 Unprocessable Content | Content is understood but cannot be processed under applicable rules |
| 429 Too Many Requests | Client exceeded request rate limit |
| 500 Internal Server Error | Unexpected error in server processing |
| 502 Bad Gateway | Gateway/proxy received an invalid response from upstream |
| 503 Service Unavailable | Service is temporarily unable to serve requests |
| 504 Gateway Timeout | Gateway/proxy did not receive a timely upstream response |

Do not mechanically map every business error to 400 or every technical error to 500:

- Cancelling a shipped order can be 409 Conflict because the current state conflicts with the action.
- Insufficient permissions can be 403 Forbidden.
- Order not found can be 404 Not Found.
- A temporarily unavailable dependency can be 503 Service Unavailable.
- A timeout when the application acts as a gateway can be 504 Gateway Timeout.

HTTP status and error code complement each other: status indicates the protocol-level outcome class; error code identifies the specific scenario in the API contract.

## 4. Designing a Stable Error Response

With Spring Framework 6+, you can use Problem Details per RFC 9457. The standard media type is application/problem+json. Example:

```http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/order-state-conflict",
  "title": "Cannot cancel order",
  "status": 409,
  "detail": "The order has already been shipped.",
  "instance": "/api/orders/9001",
  "code": "ORDER_ALREADY_SHIPPED"
}
```

| Field | Meaning |
| --- | --- |
| type | URI identifying the problem type; should be stable |
| title | Short summary of the problem type |
| status | Corresponding HTTP status |
| detail | Explanation of the specific occurrence for this response |
| instance | URI referencing this occurrence of the problem |
| code | API-defined extension field for stable client handling |

code is an API extension, not a required field in RFC 9457. Use a stable code like ORDER_ALREADY_SHIPPED; do not use class names like OrderAlreadyShippedException as a public contract.

### Separating Client Information and Internal Information

Public responses should contain enough information for clients to understand and act: a stable error code, a message that does not expose sensitive data, failing validation fields where appropriate, and a request/trace identifier for contacting support.

Do not include in public responses:

- Stack traces or exception class names.
- SQL queries, table names, schemas, or connection strings.
- Internal hosts, private IPs, pod/container names, or topology.
- Tokens, cookies, secrets, or authentication credentials.
- Unsanitized exception messages from dependencies.

Technical details should be written to access-controlled logs/traces. The response can provide a requestId so operations teams can locate the corresponding logs.

## 5. Building Business Errors in Spring

### 5.1. Domain Exceptions

```java
public class OrderAlreadyShippedException extends RuntimeException {
    public OrderAlreadyShippedException() {
        super("Order has already been shipped");
    }
}

public void cancelOrder(Order order) {
    if (order.isShipped()) {
        throw new OrderAlreadyShippedException();
    }
    order.cancel();
}
```

Exceptions represent domain rules; controller advice is responsible for converting them into HTTP responses. Do not let services depend on MockMvc or Spring REST Docs.

### 5.2. Converting to ProblemDetail

```java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderAlreadyShippedException.class)
    ResponseEntity<ProblemDetail> handleOrderAlreadyShipped(
            OrderAlreadyShippedException exception,
            HttpServletRequest request) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.CONFLICT,
            "The order has already been shipped and cannot be cancelled."
        );
        problem.setType(URI.create(
            "https://api.example.test/problems/order-state-conflict"
        ));
        problem.setTitle("Cannot cancel order");
        problem.setInstance(URI.create(request.getRequestURI()));
        problem.setProperty("code", "ORDER_ALREADY_SHIPPED");

        return ResponseEntity.status(HttpStatus.CONFLICT)
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(problem);
    }
}
```

This example illustrates mapping an exception to a response. In a real application, you can centralize mappings in an advice and use a message source if localization is needed. Never return raw exception messages directly if they might contain internal data.

## 6. Handling Technical Errors

Technical errors generally should not expose detailed root causes to clients. Example dependency timeout:

```java
@ExceptionHandler(UpstreamTimeoutException.class)
ResponseEntity<ProblemDetail> handleUpstreamTimeout(
        UpstreamTimeoutException exception,
        HttpServletRequest request) {

    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.SERVICE_UNAVAILABLE,
        "Service is temporarily unavailable. Please try again later."
    );
    problem.setType(URI.create(
        "https://api.example.test/problems/dependency-unavailable"
    ));
    problem.setTitle("Service temporarily unavailable");
    problem.setInstance(URI.create(request.getRequestURI()));
    problem.setProperty("code", "UPSTREAM_UNAVAILABLE");
    problem.setProperty("requestId", requestIdFromContext());

    log.error("Upstream dependency timed out, requestId={}",
        requestIdFromContext(), exception);

    return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
        .contentType(MediaType.APPLICATION_PROBLEM_JSON)
        .body(problem);
}
```

Clients receive an actionable message without a stack trace. Internal logs retain the exception and context needed for investigation. Retries are only appropriate when operations are safe, bounded, and do not cause duplicate execution. Retry-After may be returned if the API has a clear retry policy.

Do not map every exception to 503. Programming bugs or unexpected states usually warrant 500; 503 is appropriate when a service is temporarily unable to serve requests.

## 7. Testing and Documenting Business Errors with MockMvc

Suppose the DELETE order endpoint returns Problem Details when the order is already shipped:

```json
{
  "type": "https://api.example.test/problems/order-state-conflict",
  "title": "Cannot cancel order",
  "status": 409,
  "detail": "The order has already been shipped and cannot be cancelled.",
  "instance": "/api/orders/9001",
  "code": "ORDER_ALREADY_SHIPPED"
}
```

The test verifies status, content type, error code, and fields:

```java
@WebMvcTest(OrderController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class OrderErrorDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @Test
    void documentsOrderAlreadyShipped() throws Exception {
        doThrow(new OrderAlreadyShippedException())
            .when(orderService).cancel(9001L);

        mockMvc.perform(delete("/api/orders/{id}", 9001)
                .accept(MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(status().isConflict())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON
            ))
            .andExpect(jsonPath("$.code").value("ORDER_ALREADY_SHIPPED"))
            .andDo(document("orders-cancel-already-shipped",
                responseFields(
                    fieldWithPath("type").description("URI identifying the problem type"),
                    fieldWithPath("title").description("Error title"),
                    fieldWithPath("status").description("HTTP status"),
                    fieldWithPath("detail").description("Error explanation"),
                    fieldWithPath("instance").description("URI of the failing request"),
                    fieldWithPath("code").description("Stable business error code")
                )
            ));
    }
}
```

responseFields(...) creates response-fields.adoc. You can add responseHeaders(...) to describe important headers such as Content-Type or Retry-After if the response actually returns them.

With Spring Boot 3.4+, @MockitoBean can be used; in older versions, @MockBean is the common approach. Choose the annotation matching your project's Spring Boot version.

## 8. Documenting Technical Errors

Technical errors should have their own operation IDs and a stable public payload:

```java
@Test
void documentsDependencyUnavailable() throws Exception {
    doThrow(new UpstreamTimeoutException())
        .when(paymentService).charge(any());

    mockMvc.perform(post("/api/payments")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {"orderId": 9001, "amount": 89.5}
                """)
            .accept(MediaType.APPLICATION_PROBLEM_JSON))
        .andExpect(status().isServiceUnavailable())
        .andExpect(jsonPath("$.code").value("UPSTREAM_UNAVAILABLE"))
        .andDo(document("payments-upstream-unavailable",
            responseFields(
                fieldWithPath("type").description("URI identifying the problem type"),
                fieldWithPath("title").description("Error title"),
                fieldWithPath("status").description("HTTP status"),
                fieldWithPath("detail").description("Message for the client"),
                fieldWithPath("instance").description("Request URI"),
                fieldWithPath("code").description("Stable technical error code"),
                fieldWithPath("requestId").description("ID for looking up support logs")
            )
        ));
}
```

Tests must not expect the payload to contain exception names, stack traces, or internal endpoint details. Additional assertions can be included:

```java
andExpect(jsonPath("$.stackTrace").doesNotExist())
andExpect(jsonPath("$.sql").doesNotExist())
```

In a real project, choose sensitive fields matching your application's error schema. Assertions help prevent accidental changes from leaking information in responses.

## 9. Validation Errors Are a Separate Contract

Validation errors are typically request errors and should not be conflated with technical errors. Example payload:

```json
{
  "type": "https://api.example.test/problems/validation",
  "title": "Invalid data",
  "status": 400,
  "detail": "One or more fields are invalid.",
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "field": "email",
      "code": "INVALID_FORMAT",
      "message": "Email format is invalid"
    }
  ]
}
```

Descriptors:

```java
responseFields(
    fieldWithPath("type").description("Problem type URI"),
    fieldWithPath("title").description("Error title"),
    fieldWithPath("status").description("HTTP status"),
    fieldWithPath("detail").description("Summary of validation errors"),
    fieldWithPath("code").description("Validation error code"),
    fieldWithPath("errors[]").description("List of per-field errors"),
    fieldWithPath("errors[].field").description("Name of the invalid field"),
    fieldWithPath("errors[].code").description("Field error code"),
    fieldWithPath("errors[].message").description("Field error message")
)
```

If the API allows an empty errors list or has different structures for object errors versus field errors, describe the actual schema accurately. You can use subsectionWithPath(...) when you only want to describe errors as a group; if clients need to read each field error, describe them in detail.

## 10. Distinguishing Errors in API Documentation

| Operation ID | HTTP status | Category | Meaning |
| --- | --- | --- | --- |
| orders-cancel-already-shipped | 409 | Business | Order state does not allow cancellation |
| orders-find-not-found | 404 | Business/resource | Order not found |
| products-create-validation-failed | 400 or 422 per contract | Validation | Payload fails validation |
| payments-upstream-unavailable | 503 | Technical | Dependency temporarily unavailable |
| orders-unexpected-error | 500 | Technical | Unexpected server error |

Do not merge all errors into a single error-response operation. Each response variant can differ in status, headers, and fields. Separating operation IDs enables Asciidoctor to include the right example and helps clients understand when each error occurs.

## 11. Including Error Snippets in Asciidoctor

Example src/docs/asciidoc/errors.adoc file:

```asciidoc
= API Errors
:toc: left

== Cancel Shipped Order

=== HTTP response
include::{snippets}/orders-cancel-already-shipped/http-response.adoc[]

=== Response fields
include::{snippets}/orders-cancel-already-shipped/response-fields.adoc[]

== Payment Dependency Unavailable

=== HTTP response
include::{snippets}/payments-upstream-unavailable/http-response.adoc[]

=== Response fields
include::{snippets}/payments-upstream-unavailable/response-fields.adoc[]
```

The snippets attribute must point to the root generated snippets directory. Operation IDs in includes must match the IDs passed to document(...). Tests must run before the Asciidoctor task so the snippets exist.

## 12. Common Pitfalls

| Symptom | Cause | Solution |
| --- | --- | --- |
| Business error returns 500 | Domain exception is not mapped in controller advice. | Map the exception to the appropriate status and Problem Details. |
| Technical error returns 400 | Same handler used for all exceptions. | Classify errors by origin and HTTP semantics. |
| Client cannot distinguish errors | Only free-form messages exist, no stable error code. | Add a contracted extension code. |
| Response leaks stack trace or SQL | Returning raw exception details. | Redact responses; keep details in internal logs. |
| Test does not create response-fields snippet | responseFields(...) not called or response body mismatches schema. | Check the operation and actual payload. |
| Test fails due to missing field | Required descriptor is absent in a response variant. | Split descriptors by variant or mark optional if permitted by contract. |
| Test misses new errors | relaxedResponseFields used too broadly. | Keep strict mode for the core error schema and narrow relaxed scope. |
| Asciidoctor cannot find snippet | Wrong operation ID or outputDir. | Check generated-snippets and include paths. |

## 13. Practice Exercise

Create an Orders and Payments API with these scenarios:

1. Cancelling a shipped order returns 409 and code ORDER_ALREADY_SHIPPED.
2. Order not found returns 404 and code ORDER_NOT_FOUND.
3. Payload validation failure returns 400 or 422 per contract, with a list of field errors.
4. Payment provider timeout returns 503 and code UPSTREAM_UNAVAILABLE.

Implementation steps:

1. Create a domain exception for the order cancellation error and an exception simulating timeout.
2. Use @RestControllerAdvice to convert errors to Problem Details.
3. Write MockMvc tests verifying status, Content-Type, error code, and response fields.
4. Verify technical error responses contain no stack traces, SQL, or secrets.
5. Assign a separate operation ID for each error variant.
6. Include HTTP response and response-fields snippets into Asciidoctor.
7. Run clean test and build the documentation; verify error examples reflect the current contract.

**Completion criteria:** You can distinguish business/domain errors, technical errors, and validation errors; choose HTTP status codes by semantics; design stable error codes; avoid leaking internal information; generate error snippets via tests; and include them in documentation.

## 14. References

- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)
- [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring REST Docs — Request and Response Fields](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [Spring REST Docs — HTTP Headers](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/http-headers.html)
- [HTTP Semantics — RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html)
