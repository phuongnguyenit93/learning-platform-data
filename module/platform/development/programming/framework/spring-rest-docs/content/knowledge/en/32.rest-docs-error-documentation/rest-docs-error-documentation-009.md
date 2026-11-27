# Synchronizing the Error Contract with Exception Handlers

## 1. Why Must Exception Handlers and Documentation Stay Synchronized?

In the **SPRING_REST_DOCS** module, Spring REST Docs generates REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. Error responses typically pass through multiple layers: the domain/service throws an exception, controller advice maps the exception to an HTTP response, and REST Docs documents the status, headers, and payload.

If these layers are out of sync, documentation easily becomes wrong:
- A service throws OrderNotFoundException, but the advice returns 500 instead of 404.
- The error body uses code ORDER_MISSING while the documentation says ORDER_NOT_FOUND.
- The handler adds timestamp or correlationId, but descriptors are not updated.
- Multiple handlers can catch the exception and precedence is unclear.
- Validation errors and domain errors accidentally share the same status/code.
- Tests check only the body, ignoring the status line and Content-Type.

The goal is a stable error contract enforced by exception handlers and verified via HTTP documentation tests. REST Docs does not design the error model itself; it detects mismatches between actual responses and descriptors.

## 2. Defining the Error Contract Before Writing Handlers

An error contract needs to define:

| Component | Question |
| --- | --- |
| HTTP status | Does the client receive 400, 404, 409, or 5xx? |
| Media type | application/problem+json or a custom schema? |
| Error type/code | Which stable code should clients branch on? |
| Title/message | What general message is published? |
| Detail | Are occurrence-specific details included? |
| Field violations | What path format represents validation errors? |
| Correlation ID | Which ID do clients use to contact support? |
| Retry semantics | Is there a Retry-After header or retry guidance? |
| Sensitive data | Which fields must never be returned? |

Example contract for an order not found:

```http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json
X-Request-Id: req-demo-42
```

```json
{
  "type": "https://api.example.com/problems/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "Order ORD-42 was not found.",
  "code": "ORDER_NOT_FOUND",
  "correlationId": "req-demo-42"
}
```

The HTTP status and the status field in Problem Details should match if the API includes that field in the body. The code should be stable for programmatic client handling; detail can be specific to each error occurrence. Never use exception class names as public error codes because they are implementation details.

## 3. Layering Exceptions: Domain Errors vs. HTTP Errors

Do not make the domain/service layer depend on HTTP status codes or Spring MVC response types. The domain layer can throw exceptions with business meaning:

```java
public class OrderNotFoundException extends RuntimeException {
    private final String orderId;

    public OrderNotFoundException(String orderId) {
        super("Order not found: " + orderId);
        this.orderId = orderId;
    }

    public String getOrderId() {
        return orderId;
    }
}
```

Service using the exception:

```java
@Service
class OrderService {
    private final OrderRepository repository;

    OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    Order getRequired(String id) {
        return repository.findById(id)
                .orElseThrow(() -> new OrderNotFoundException(id));
    }
}
```

The exception expresses a domain error. Controller advice maps it to an HTTP status, error code, and response representation. The same domain exception can be handled according to the HTTP contract without forcing the service to know about ResponseEntity or ProblemDetail.

For recoverable errors or normal business outcomes, consider a result type instead of exceptions. Do not use exceptions as control flow for every ordinary branch.

## 4. Using ProblemDetail in @RestControllerAdvice

Spring Framework supports ProblemDetail to represent Problem Details. Controller advice can map domain exceptions:

```java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ProblemDetail> handleOrderNotFound(
            OrderNotFoundException exception) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "Order " + exception.getOrderId() + " was not found.");

        problem.setType(URI.create(
                "https://api.example.com/problems/order-not-found"));
        problem.setTitle("Order not found");
        problem.setProperty("code", "ORDER_NOT_FOUND");

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(problem);
    }
}
```

Standard members include type, title, status, detail, and instance. Extension members such as code can be added with setProperty. How extensions are serialized depends on Spring/Jackson configuration; verify the actual JSON in tests.

If correlationId is needed, obtain it from the request-scoped context or a request attribute created by a filter. Do not generate an independent ID in the advice if response headers and logs use a different source.

### 4.1. Using a Custom Schema When a Contract Already Exists

Not every API uses Problem Details. With a custom schema:

```java
record ApiError(String code, String message, String correlationId) {}

@RestControllerAdvice
class LegacyApiExceptionHandler {
    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ApiError> handle(OrderNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError(
                        "ORDER_NOT_FOUND",
                        "Order not found.",
                        RequestIds.current()));
    }
}
```

If an API has already published this envelope, preserve the public schema or plan intentional migration/versioning. Do not change a schema just to make examples match a standard.

## 5. Mapping Multiple Exceptions Using a Unified Table

| Exception/domain condition | HTTP status | Error code |
| --- | --- | --- |
| InvalidRequestException | 400 | INVALID_REQUEST |
| OrderNotFoundException | 404 | ORDER_NOT_FOUND |
| DuplicateOrderException | 409 | ORDER_ALREADY_EXISTS |
| InsufficientStockException | 409 | INSUFFICIENT_STOCK |
| UnauthenticatedException | 401 | UNAUTHENTICATED |
| AccessDeniedException | 403 | FORBIDDEN |
| RateLimitExceededException | 429 | RATE_LIMITED |
| Unexpected exception | 500 | INTERNAL_ERROR |

This is an example mapping; the exact status depends on API semantics. An inventory error may use 409 or another status per contract. What matters is consistent mapping backed by tests.

Do not return internal exception messages for every exception to clients. For 500 errors, return a generic message and correlation ID; stack traces, SQL, filesystem paths, and dependency details belong only in access-controlled logs.

## 6. Handler Precedence and Exception Hierarchy

Spring MVC selects a matching handler by exception type and advice configuration. When multiple handlers can process the same exception hierarchy, advice ordering and mapping specificity affect the outcome.

- Use specific handlers for domain exceptions.
- Provide a fallback handler for unexpected errors.
- Explicitly define advice ordering when multiple classes participate.
- Ensure framework, security, and validation handlers are not shadowed by custom advice.
- Do not turn every exception into 400; programming/dependency bugs are usually not client errors.

Illustrative fallback:

```java
@ExceptionHandler(Exception.class)
ResponseEntity<ProblemDetail> handleUnexpected(Exception exception) {
    String correlationId = RequestIds.current();

    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.INTERNAL_SERVER_ERROR,
            "An internal system error occurred. Please contact support.");

    problem.setTitle("System error");
    problem.setType(URI.create(
            "https://api.example.com/problems/internal-error"));
    problem.setProperty("code", "INTERNAL_ERROR");
    problem.setProperty("correlationId", correlationId);

    // Record exception and correlationId in access-controlled internal logs.
    return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
            .header("X-Request-Id", correlationId)
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(problem);
}
```

Never write stack traces into detail. The fallback must avoid swallowing exceptions that the framework needs to handle through its own mechanisms. Check the security filter chain, async errors, and errors occurring before DispatcherServlet.

## 7. Validation Exceptions vs. Domain Exceptions

Validation errors usually come from request binding or Bean Validation. Domain exceptions come from business rules after the request passes validation.

| Scenario | Error Category | Example |
| --- | --- | --- |
| Invalid email format | Validation | 400 or 422 per contract |
| Order does not exist | Domain | 404 |
| Paid order cannot be cancelled | Domain/state conflict | 409 |
| Not logged in | Authentication | 401 |
| Insufficient permissions | Authorization | 403 |

Do not reuse the VALIDATION_ERROR code for business errors. Clients need to distinguish which field is invalid from which resource state disallows an operation.

Example validation payload:

```json
{
  "type": "https://api.example.com/problems/validation-error",
  "title": "Invalid request",
  "status": 400,
  "code": "VALIDATION_ERROR",
  "violations": [
    {
      "field": "email",
      "code": "INVALID_FORMAT",
      "message": "Email format is invalid."
    }
  ]
}
```

A not-found response does not need violations. Because payload shapes differ, use separate descriptors/snippets per error type.

## 8. Controlled Descriptor Reuse

If error responses share a Problem Details schema, you can create a descriptor helper for standard fields:

```java
static FieldDescriptor[] problemDetailFields() {
    return new FieldDescriptor[] {
        fieldWithPath("type").description("Problem type URI"),
        fieldWithPath("title").description("Error title"),
        fieldWithPath("status").description("HTTP status"),
        fieldWithPath("detail").description("Error details"),
        fieldWithPath("instance").optional()
                .description("URI of the problem occurrence, if available")
    };
}
```

Then append extension fields per error type. You must define your own array-concatenation helper or use an appropriate Java concatenation approach:

```java
responseFields(
    concat(
        problemDetailFields(),
        new FieldDescriptor[] {
            fieldWithPath("code").description("Stable error code"),
            fieldWithPath("correlationId")
                    .description("Request trace ID")
        }
    )
)
```

This illustrates the idea; concat is not a built-in Spring REST Docs helper. Avoid overly generic abstractions that obscure each error type's schema. If optional fields differ, separate descriptors are easier to read and safer.

## 9. MockMvc Tests Must Go Through Real Exception Handlers

To verify the mapping, tests should use the real controller advice. Do not simply mock the response body and call document, because that does not test exception mapping.

```java
@ExtendWith(RestDocumentationExtension.class)
class OrderErrorDocumentationTest {
    private MockMvc mockMvc;

    @BeforeEach
    void setUp(WebApplicationContext context,
               RestDocumentationContextProvider documentation) {
        mockMvc = MockMvcBuilders.webAppContextSetup(context)
                .apply(documentationConfiguration(documentation))
                .build();
    }

    @Test
    void documentsOrderNotFound() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", "ORD-42")
                        .accept(MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(status().isNotFound())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"))
                .andExpect(jsonPath("$.status").value(404))
                .andDo(document("orders-get-not-found",
                        responseFields(
                                fieldWithPath("type").description("Problem type URI"),
                                fieldWithPath("title").description("Error title"),
                                fieldWithPath("status").description("HTTP status"),
                                fieldWithPath("detail").description("Error details"),
                                fieldWithPath("code").description("Error code"),
                                fieldWithPath("correlationId").optional()
                                        .description("Trace ID if present")
                        )));
    }
}
```

This example assumes the application context contains the controller, service, advice, and a fixture for a nonexistent order. With standalone setup, you must register the advice and required converters/validators. The goal is for a real exception to pass through the real handler before REST Docs records the response.

## 10. Verifying Status, Headers, and Body

An error contract is not just a JSON body. Tests must verify status, media type, headers, and fields:

```java
mockMvc.perform(get("/api/orders/{id}", "ORD-42"))
    .andExpect(status().isNotFound())
    .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_PROBLEM_JSON))
    .andExpect(header().exists("X-Request-Id"))
    .andExpect(jsonPath("$.status").value(404))
    .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"));
```

Then document the components to be published:

```java
.andDo(document("orders-get-not-found",
    responseHeaders(
        headerWithName("Content-Type")
            .description("Media type of the error response"),
        headerWithName("X-Request-Id")
            .description("ID used to look up the request")
    ),
    responseFields(
        fieldWithPath("type").description("Problem type URI"),
        fieldWithPath("title").description("Error title"),
        fieldWithPath("status").description("HTTP status"),
        fieldWithPath("detail").description("Error details"),
        fieldWithPath("code").description("Stable error code"),
        fieldWithPath("correlationId").optional()
            .description("Trace ID in the error body, if present")
    )
))
```

Do not document a header as optional if the implementation guarantees it is always present; likewise, do not declare it required when the contract permits absence. Descriptors must match actual behavior.

## 11. Synchronizing Error Codes and Messages

An error code is an identifier for client logic; message/detail is explanatory text. Do not require clients to parse messages because messages may be localized or revised.

| Code | Stable Meaning | Can Message Change? |
| --- | --- | --- |
| ORDER_NOT_FOUND | No order exists with the requested ID | Yes |
| ORDER_ALREADY_EXISTS | Order violates unique business key | Yes |
| INSUFFICIENT_STOCK | Insufficient inventory | Yes |
| VALIDATION_ERROR | Request is invalid | Yes |
| INTERNAL_ERROR | Unexpected system error | Yes |

In documentation, describe code as a stable value and detail as human-readable information. Do not put class names, SQL messages, or stack traces into public error bodies.

If a code changes, that is a contract change requiring review/versioning. Tests should assert exact codes to catch unintended changes.

## 12. Errors That Bypass ControllerAdvice

Not all errors pass through RestControllerAdvice. Some occur before reaching controllers:

- Authentication/authorization filters.
- Gateways or reverse proxies.
- Request parsing and message converters.
- Servlet container or network layer.
- Rate limiters or API management layers.

Testing controller advice alone is not enough to prove all error responses share the same schema. Identify API boundaries and write integration tests for errors clients actually observe. If a gateway generates 429, the gateway contract documentation needs its own verification.

With Spring Security, the authentication entry point and access denied handler are typically responsible for generating 401/403 responses. Synchronize their schemas with controller advice or clearly document any differences. Never let the same API return two different envelopes without a reason.

## 13. Asciidoctor and CI Integration

Organize snippets by operation and error outcome:

```adoc
= Order API

== Get Order

=== Success
include::{snippets}/orders-get-success/http-response.adoc[]

=== Not found
include::{snippets}/orders-get-not-found/http-response.adoc[]
include::{snippets}/orders-get-not-found/response-fields.adoc[]

=== Conflict on cancel
include::{snippets}/orders-cancel-conflict/http-response.adoc[]
include::{snippets}/orders-cancel-conflict/response-fields.adoc[]
```

The build must run documentation tests before Asciidoctor. CI should fail if an exception handler returns the wrong status/media type, an error code mismatches the contract, a payload has undocumented fields, correlation ID/header/body are inconsistent, snippet identifiers collide, or an Asciidoctor include file does not exist.

Include a 500 fallback test to verify responses do not contain internal exception messages, while internal logs retain investigation details.

## 14. Common Pitfalls

| Symptom | Cause | Solution |
| --- | --- | --- |
| Domain exception returns 500 | No specific handler exists | Add mapping and assert status |
| Error code mismatches documentation | Scattered mappings | Centralize codes and assert them |
| Body status differs from HTTP status | Handler sets status/body independently | Use the same mapping and assert both |
| Validation and domain errors share code | Schema lacks classification | Separate error types/codes |
| Advice not invoked in MockMvc | Setup did not register advice/context | Use application context or setControllerAdvice |
| Broad handler shadows specific handler | Unclear hierarchy/ordering | Map specifically and test precedence |
| 401/403 use a different schema | Security filter runs before MVC | Align entry point/access denied handler |
| responseFields reports missing field | Descriptors out of sync with response | Synchronize DTO/advice/descriptors |
| New fields go undetected | Relaxed descriptors too broad | Use strict mode for stable contracts |
| Stack trace leaks in body | Fallback returns exception message | Return generic message, log internally |
| Body is right but headers are wrong | Only JSON asserted | Check status, Content-Type, headers |
| Gateway errors lack ID | Error occurred before application | Put contract into gateway and test boundary |

## 15. Practice Exercise

Use an Order API with not-found, conflict, and validation errors:

1. Create domain exceptions OrderNotFoundException and OrderAlreadyCancelledException.
2. Define a mapping table: exception → HTTP status → error code.
3. Write a RestControllerAdvice returning Problem Details or your chosen error schema.
4. Ensure status in the body matches the HTTP status and error codes are stable.
5. Create MockMvc tests using the real application context so exceptions go through the advice.
6. Assert status, Content-Type, correlation ID response header, and error body.
7. Use responseFields(...) to document each error type; keep strict mode for public contracts.
8. Add a 500 fallback test confirming no stack trace or exception message is leaked.
9. If using Spring Security, separately test 401/403 from the entry point and access denied handler.
10. Include error snippets into Asciidoctor; run documentation tests before rendering.
11. Intentionally alter an error code in the handler to confirm contract tests fail.
12. Review generated diffs as API contract changes, not merely documentation text changes.

**Completion criteria:** You separate domain exceptions from HTTP error mapping; synchronize controller advice, status, media type, error code, and payload; verify via MockMvc through real handlers; document response headers/fields; and integrate contract verification into Asciidoctor/CI.

## References

- [Spring Framework — @ExceptionHandler](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html): mapping exceptions in Spring MVC.
- [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): ProblemDetail, ErrorResponse, and REST error handling.
- [Spring REST Docs — Response Fields](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/response-fields.html): documenting and validating response payload fields.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): standard error representation for HTTP APIs.
