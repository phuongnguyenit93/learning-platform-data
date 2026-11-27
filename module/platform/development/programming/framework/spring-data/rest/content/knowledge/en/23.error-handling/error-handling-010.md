# Client-Safe Messages, Correlation Identifiers, and Diagnostics for Logs

## 1. Why separate client messages and internal logs?

When a request fails, two distinct audiences need different information:

- **Clients** need to know why the request was rejected, whether they can fix the input or retry, and which identifier to provide when contacting support.
- **Engineering teams** need the actual exception, stack trace, associated request/trace, service, and failing step for investigation.

If you return raw exception messages, SQL, stack traces, or internal class names to clients, the API can leak system architecture, table names, file paths, connection details, or sensitive data. Conversely, if logs only record "request failed" without a tracking ID, engineers struggle to locate the exact request among millions of log lines.

A good design separates three kinds of information:

1. **Error code:** a stable identifier describing the error category, e.g., ORDER_STATE_CONFLICT.
2. **Request/correlation ID:** an identifier for a specific execution, e.g., 8f7d...; clients can give this ID to support.
3. **Technical diagnostics:** exception class, stack trace, root cause, trace/span, and technical context stored only in access-controlled logging/tracing systems.

An error code may repeat across many requests; a request ID must distinguish each individual occurrence. A trace ID links multiple spans across services within a single distributed trace. These three values are related but do not replace one another.

## 2. Error response design principles

Error responses need a stable, machine-readable structure that does not depend on internal exception wording.

Do:

- Keep HTTP statuses accurate to the semantics of the error.
- Use stable error codes so clients can branch programmatically.
- Write concise, safe messages that tell the client the next step.
- Return only the validation fields actually needed to fix the request.
- Provide a request ID or occurrence ID for lookup.
- Keep debug details, stack traces, and database causes in logs.
- Never require clients to parse the detail string to infer the error type.

Do not:

- Return exception.getMessage() directly for all exceptions.
- Return stack traces, SQL, table/column names, hostnames, file paths, or connection strings.
- Return access tokens, cookies, passwords, secrets, personal data, or sensitive request payloads.
- Return HTTP 200 for a failed request just to simplify the frontend.
- Let the body's status field differ from the actual HTTP status.

## 3. Using Problem Details per RFC 9457

RFC 9457 defines the Problem Details format for HTTP APIs. JSON responses use the media type:

~~~~http
Content-Type: application/problem+json
~~~~

Standard members:

| Member | Meaning |
|---|---|
| type | URI identifying the problem type; should be stable and under API control |
| title | Short summary of the problem type |
| status | HTTP status code of the response |
| detail | Explanation specific to this occurrence, focused on how the client can handle it |
| instance | URI reference identifying the specific problem occurrence |

You may add extension members such as code, requestId, or errors when the API clearly defines their semantics.

Example of an order that cannot be confirmed because it has already been shipped:

~~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
X-Request-Id: 8f7d8d5e-6e16-4bb0-9f3e-1a42dfe49c11
~~~~

~~~~json
{
  "type": "https://api.example.com/problems/order-state-conflict",
  "title": "Order cannot be confirmed",
  "status": 409,
  "detail": "This order has already been shipped. Refresh the order before continuing.",
  "instance": "urn:uuid:8f7d8d5e-6e16-4bb0-9f3e-1a42dfe49c11",
  "code": "ORDER_STATE_CONFLICT",
  "requestId": "8f7d8d5e-6e16-4bb0-9f3e-1a42dfe49c11"
}
~~~~

Clients can use status to understand the error class, code to pick specific behavior, and requestId to provide to support. detail is for human readers; do not treat it as a machine-readable protocol.

instance identifies a specific occurrence. You can use a URI or URN like urn:uuid:<id> if the API does not provide an occurrence lookup endpoint. Do not put stack traces or log file paths into instance.

## 4. Choosing consistent HTTP statuses and error codes

HTTP status describes the outcome at the protocol level; error code describes the cause at the application level.

| HTTP status | Common situation | Example error code |
|---|---|---|
| 400 Bad Request | Malformed JSON, binding failure, or invalid request | MALFORMED_REQUEST |
| 401 Unauthorized | Missing or invalid authentication credentials | AUTHENTICATION_REQUIRED |
| 403 Forbidden | Authenticated but not permitted to perform the operation | ACCESS_DENIED |
| 404 Not Found | Resource does not exist or is not exposed to the caller | RESOURCE_NOT_FOUND |
| 409 Conflict | Operation conflicts with current state | ORDER_STATE_CONFLICT |
| 412 Precondition Failed | Condition such as If-Match is not satisfied | PRECONDITION_FAILED |
| 422 Unprocessable Content | Request parsed, but data failed validation per API contract | VALIDATION_FAILED |
| 429 Too Many Requests | Request rate limit exceeded | RATE_LIMIT_EXCEEDED |
| 500 Internal Server Error | Unexpected server-side error | INTERNAL_ERROR |
| 503 Service Unavailable | Service temporarily unavailable | SERVICE_UNAVAILABLE |

This table is a guideline, not a rigid rule forcing every application to use the exact same status for every error. For example, validation may return 400 under an existing contract; choose one convention and stay consistent. When a response indicates a retry is possible, consider Retry-After with a reasonable interval.

Do not turn every error into 500. Errors caused by invalid client data, insufficient permissions, or state conflicts need appropriate statuses so clients and proxies can respond properly.

## 5. What is safe to return to the client

Safe return information depends on the error type and data policy:

- HTTP status and stable error code.
- Brief message explaining why the action cannot be completed.
- Failing field names and constraint codes, provided they do not disclose sensitive data.
- Allowed limits or formats, if helpful and safe.
- Request ID for support lookup.
- Next steps, such as reloading the resource or signing in again.

Information that should usually stay in internal logs only:

- Full stack traces and cause chains.
- SQL, schema/table names, and bound query statements.
- File paths, temp directories, hostnames, and internal configuration.
- Implementation class names or internal packages.
- Access tokens, refresh tokens, cookies, passwords, API keys, and secrets.
- Full request bodies if they contain PII, payment info, or confidential data.
- Information belonging to other users or tenants.

For example, instead of returning:

~~~~json
{
  "message": "org.postgresql.util.PSQLException: duplicate key value violates unique constraint users_email_key at UserRepository.save(UserRepository.java:87)"
}
~~~~

return a stable business error:

~~~~json
{
  "type": "https://api.example.com/problems/email-already-registered",
  "title": "Email is already registered",
  "status": 409,
  "detail": "Use another email address or sign in to the existing account.",
  "code": "EMAIL_ALREADY_REGISTERED",
  "requestId": "8f7d8d5e-6e16-4bb0-9f3e-1a42dfe49c11"
}
~~~~

Internal logs can record the unique constraint cause along with the request ID for engineering investigation. Clients do not need to know constraint names or repository names.

## 6. How request ID, correlation ID, and trace ID differ

| Value | Scope | Purpose |
|---|---|---|
| Error code | One error category | Client identifies error and chooses behavior |
| Request ID | One HTTP request or processing invocation | Look up a specific request in logs |
| Correlation ID | A workflow that may span multiple requests/services | Link log events belonging to the same activity |
| Trace ID | One distributed trace | Group spans across multiple services |
| Span ID | One unit of work within a trace | Identify a specific step inside a trace |

In a simple application, request ID and correlation ID are sometimes used interchangeably. In multi-service systems, trace ID is well suited to link spans; request ID remains useful for supporting a single request at the API boundary.

Do not use an error code as a request ID. For instance, VALIDATION_FAILED may occur thousands of times, whereas a request ID represents a single occurrence.

Do not treat a request ID or trace ID as a credential. Knowing this ID must not grant permission to read logs, access resources, or retrieve internal data.

## 7. Generating and returning a request ID

If the system does not yet use tracing, you can generate a request ID in a servlet filter and place it in a response header. Example:

~~~~java
import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class RequestIdFilter extends OncePerRequestFilter {

    public static final String ATTRIBUTE = "requestId";
    public static final String HEADER = "X-Request-Id";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String requestId = UUID.randomUUID().toString();

        request.setAttribute(ATTRIBUTE, requestId);
        response.setHeader(HEADER, requestId);
        MDC.put(ATTRIBUTE, requestId);

        try {
            chain.doFilter(request, response);
        } finally {
            MDC.remove(ATTRIBUTE);
        }
    }
}
~~~~

The example above always generates the ID on the server. If the system needs to accept an ID from an API gateway, accept only headers overwritten by a trusted gateway; validate length and allowed characters, disallowing newlines or control characters. Never trust an arbitrary value from the Internet and write it straight into logs.

Ensure the filter runs for all requests needing tracking and is ordered appropriately relative to security/error handling. If the application uses async servlets or executors, MDC does not automatically propagate across threads; proper context propagation or a tracer is needed.

If Micrometer Tracing is already enabled, prefer using the trace context managed by the tracing system instead of generating a competing trace ID. You can still keep a dedicated request ID for API support and use traceId/spanId for distributed tracing.

## 8. Adding request ID to ProblemDetail

Spring Framework supports ProblemDetail for RFC 9457. You can create a response with an error code and request ID:

~~~~java
import java.net.URI;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiProblemHandler {

    @ExceptionHandler(OrderStateConflictException.class)
    public ResponseEntity<ProblemDetail> handleOrderConflict(
            OrderStateConflictException exception,
            HttpServletRequest request) {

        String requestId = (String) request.getAttribute(
                RequestIdFilter.ATTRIBUTE
        );

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT,
                "This order cannot be changed in its current state."
        );

        problem.setType(URI.create(
                "https://api.example.com/problems/order-state-conflict"
        ));
        problem.setTitle("Order state conflict");
        problem.setInstance(URI.create("urn:uuid:" + requestId));
        problem.setProperty("code", "ORDER_STATE_CONFLICT");
        problem.setProperty("requestId", requestId);

        return ResponseEntity.status(problem.getStatus())
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(problem);
    }
}
~~~~

In the example, the exception is only used to identify the error type. The exception's content is not returned directly. If the exception carries internal details, log them according to the policy in the later section.

ProblemDetail can carry extension properties such as code and requestId. With Jackson configured per Spring Framework defaults, extension properties are serialized at the top level of the JSON object.

Ensure requestId always has a value before constructing ProblemDetail. If the filter did not run on a special dispatch path, generate a new occurrence ID as a fallback and ensure that ID also appears in logs.

## 9. Standard Spring MVC error handling

With Spring MVC, you can return ProblemDetail or ErrorResponse from @ExceptionHandler or controller methods.

In Spring Boot, you can enable Problem Details for built-in web exceptions with:

~~~~properties
spring.mvc.problemdetails.enabled=true
~~~~

Spring MVC provides ResponseEntityExceptionHandler to handle standard web exceptions. Applications can extend this class and add handlers for custom business exceptions, or use @ControllerAdvice structured to fit the application.

Handlers for business exceptions can return ProblemDetail as shown earlier. For binding/validation errors, keep useful field paths and constraint codes without putting sensitive raw values into the response.

Do not assume enabling the Problem Details property automatically standardizes every exception from every library. Test exceptions from Spring MVC, Spring Security, Spring Data REST, the persistence layer, and custom services using integration tests.

## 10. Special considerations for Spring Data REST

Spring Data REST has its own exception handling for the repository exporter. The current API provides RepositoryRestExceptionHandler, a @ControllerAdvice dedicated to Spring Data REST controllers.

This has two consequences:

1. A custom @RestControllerAdvice used for regular MVC controllers should not be assumed to replace all error handling of the repository exporter.
2. If a unified error contract is needed for repository resources, you must inspect Spring Data REST's actual exception resolver and handlers in the version in use.

RepositoryRestConfigurer provides the extension point configureExceptionHandlerExceptionResolver(ExceptionHandlerExceptionResolver). You can use this configuration hook to customize the exception resolver per the release train's API. Skeleton example:

~~~~java
@Configuration
public class RepositoryRestErrorConfiguration
        implements RepositoryRestConfigurer {

    @Override
    public void configureExceptionHandlerExceptionResolver(
            ExceptionHandlerExceptionResolver resolver) {

        // Register or configure a resolver/handler suitable
        // for the Spring Data REST version in use.
    }
}
~~~~

The method above receives Spring Data REST's default resolver; how specific handlers are registered depends on the resolver and version. Do not copy Spring MVC configuration here without checking handler precedence and scope.

If you need a custom endpoint that still uses Spring Data REST's configuration, message converters, and exception handling, consider @RepositoryRestController instead of a completely separate MVC controller. Consult the overriding response handlers documentation for your application's version.

For repository event validators, validation exceptions, and persistence errors, test the actual responses. Do not assume everything returns application/problem+json just because spring.mvc.problemdetails.enabled is enabled.

## 11. Returning validation errors without leaking data

Clients need to know which fields to fix. You can define an errors extension:

~~~~json
{
  "type": "https://api.example.com/problems/validation",
  "title": "Request validation failed",
  "status": 400,
  "detail": "One or more fields need correction.",
  "code": "VALIDATION_FAILED",
  "requestId": "8f7d8d5e-6e16-4bb0-9f3e-1a42dfe49c11",
  "errors": [
    {
      "field": "email",
      "code": "Email",
      "message": "Enter a valid email address."
    },
    {
      "field": "quantity",
      "code": "Positive",
      "message": "Quantity must be greater than zero."
    }
  ]
}
~~~~

Error items should contain:

- Field name or JSON pointer.
- Stable error code, such as NotBlank, Size, or a custom domain code.
- Safe, localizable message.

You do not necessarily have to return the value sent by the client. For example, never return passwords, tokens, card numbers, or the entire rejected object. If the API needs to display the rejected value, explicitly restrict which field types are allowed and consider masking.

Do not force the frontend to parse English/Vietnamese sentences to figure out which field failed. Use field and code for logic, and message for human display.

## 12. Logging technical diagnostics

Server logs need enough context to investigate without recording sensitive data.

A structured log event might include:

| Field | Example | Purpose |
|---|---|---|
| timestamp | UTC timestamp | Order events |
| service | people-api | Identify service |
| environment | production | Identify environment |
| requestId | UUID | Find request from client-supplied ID |
| traceId / spanId | Tracing IDs | Correlate services and spans |
| method | PATCH | HTTP method |
| route | /people/{id} | Route template, avoiding logging sensitive query strings |
| status | 409 | HTTP status |
| errorCode | ORDER_STATE_CONFLICT | Error category |
| exceptionType | exception class | Internal diagnosis |
| durationMs | 38 | Processing duration |
| actorId | Policy-permitted ID | Caller context if needed |

Example with SLF4J:

~~~~java
log.warn(
    "API request rejected requestId={} errorCode={} route={} status={}",
    requestId,
    "ORDER_STATE_CONFLICT",
    "/orders/{id}/confirm",
    409,
    exception
);
~~~~

For unexpected 5xx errors, log the exception with its stack trace in internal logs:

~~~~java
log.error(
    "Unexpected API failure requestId={} traceId={} route={}",
    requestId,
    traceId,
    routeTemplate,
    exception
);
~~~~

Choose log levels by nature:

- Expected validation or client errors: usually INFO or WARN depending on volume and policy.
- Repeated business conflicts: WARN or metrics/counters; avoid generating huge volumes of stack traces.
- Unexpected server-side errors: ERROR with exception.
- Detailed debug: enable only under strict control, never exposing secrets.

Log errors once at the appropriate boundary. If service, repository, filter, and exception handler all log the same stack trace, one request can produce duplicate log events and complicate investigation.

## 13. Spring Boot and correlation IDs in logs

Spring Boot with Micrometer Tracing can add correlation IDs to default logs. The correlation ID is built from traceId and spanId in MDC.

Example Logback configuration:

~~~~properties
logging.pattern.correlation=[%X{traceId:-},%X{spanId:-}]
~~~~

Logs may display as:

~~~~text
[803B448A0489F84084905D3093480352,3425F23BB2432450] ERROR ...
~~~~

Spring Boot also supports customizing the correlation format via logging.pattern.correlation. When using Micrometer Tracing, do not generate UUID trace IDs to replace the trace context.

For traces to propagate across HTTP clients, use Spring Boot auto-configured builders such as RestClient.Builder, WebClient.Builder, or RestTemplateBuilder. Manually instantiating clients can lose automatic trace propagation unless instrumented accordingly.

When using async executors, message queues, or schedulers, verify context propagation so trace IDs are neither lost nor leaked to other tasks. MDC is thread-local context; do not copy it arbitrarily without cleaning up after processing.

## 14. Log redaction and log injection prevention

Logs are a sensitive data store. Both content and how data enters logs must be controlled.

- Never log Authorization, Cookie, Set-Cookie, passwords, API keys, refresh tokens, or secrets.
- Never log raw request bodies containing PII or payment data.
- Mask or omit emails, phone numbers, addresses, and personal identifiers when unnecessary.
- Avoid logging query strings that may carry tokens or private data.
- Never log unfiltered client-controlled headers verbatim.
- Sanitize newlines/control characters so input cannot forge extra log lines.
- Bound the length of logged values.
- Restrict log access permissions and set appropriate retention policies.
- Never expose stack traces on public support endpoints.

Dangerous example:

~~~~java
log.error("Request failed: " + request.getHeader("X-Request-Id"));
~~~~

If the header contains newlines, the input can corrupt log structure under unsafe formatters. Use structured logging or placeholders, validate/sanitize values, and prefer server-generated request IDs.

A request ID is not a secret, yet its format still must be constrained to prevent log injection and log flooding.

## 15. Using tracking IDs when working with support

A client may receive a response:

~~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: application/problem+json
X-Request-Id: 8f7d8d5e-6e16-4bb0-9f3e-1a42dfe49c11
~~~~

~~~~json
{
  "type": "https://api.example.com/problems/internal-error",
  "title": "Unexpected server error",
  "status": 500,
  "detail": "The request could not be completed. Contact support and provide the request ID.",
  "code": "INTERNAL_ERROR",
  "requestId": "8f7d8d5e-6e16-4bb0-9f3e-1a42dfe49c11"
}
~~~~

When customers contact support, they provide:

- Request ID.
- Timestamp and timezone.
- Endpoint or action being performed.
- HTTP status and error code.
- Short description of reproduction steps, if applicable.

Support staff use the request ID to look up log events and traces. Never ask customers to send access tokens, cookies, passwords, or full personal data for debugging.

If the system uses trace ID as the support identifier, standardize display formatting and sharing policies. A dedicated request ID is often easier for API support; trace ID can remain inside the observability platform.

## 16. Testing error contracts and logging

Tests should verify more than status codes. Confirm that the body is safe and linkable to logs.

### Testing ProblemDetail

~~~~java
mockMvc.perform(post("/orders/42/confirm")
        .accept("application/problem+json"))
    .andExpect(status().isConflict())
    .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_PROBLEM_JSON
    ))
    .andExpect(jsonPath("$.type").value(
            "https://api.example.com/problems/order-state-conflict"
    ))
    .andExpect(jsonPath("$.status").value(409))
    .andExpect(jsonPath("$.code").value(
            "ORDER_STATE_CONFLICT"
    ))
    .andExpect(jsonPath("$.requestId").isNotEmpty());
~~~~

### Checking response content security

Confirm the response does not contain:

- java.lang.* or internal exception names.
- stackTrace, cause, SQL, or connection strings.
- Authorization headers, cookies, passwords, or secrets.
- Raw request bodies with sensitive data.

Do not test with just a single fixed string; include tests for representative exceptions such as database errors, timeouts, and downstream service failures.

### Checking request-to-log correlation

- Request ID in the response header matches request ID in ProblemDetail.
- The same request ID appears in the related log event.
- Trace ID/span ID are logged when tracing context is present.
- One error does not generate unwanted duplicate stack traces.
- MDC is cleared after the request and does not leak IDs into the next request.
- Invalid incoming request IDs are not written directly into logs.
- For Spring Data REST, test repository endpoints and custom RepositoryRestController endpoints separately to verify the actual exception handlers.

## 17. Common mistakes

| Symptom | Possible cause | Resolution |
|---|---|---|
| Client sees stack trace | Returning raw exceptions or overly broad error details | Use ProblemDetail/safe messages and log exceptions separately |
| Support cannot find request | Response lacks request ID or ID is not logged | Generate ID in filter, return header, and log same ID |
| Error code changes with exception message | Using message as error code | Define stable error codes |
| HTTP status differs from JSON status | Handler constructs body without syncing response status | Use a single status source and test both |
| MVC responses follow RFC 9457 but repository REST does not | Spring Data REST has its own exception handler | Inspect RepositoryRestExceptionHandler and resolver |
| Trace ID lost in downstream service | HTTP client is not instrumented or context does not propagate | Use auto-configured builders and verify tracing |
| MDC holds previous request's ID | Missing MDC removal in finally or broken context propagation | Clean up MDC and test thread reuse |
| Logs contain tokens/PII | Logging entire request/headers/body or unfiltered exception messages | Redact using allowlists and limit logged data |
| One error emits too many stack traces | Multiple layers log the same exception | Choose one primary logging boundary |
| Client sends forged request ID | Trusting arbitrary headers from the Internet | Generate ID server-side or trust only verified gateways |
| Cannot find log by ID | Log aggregator does not index the requestId field | Use structured logging and index lookup fields |
| 500 returns overly generic message | Missing tracking ID or support instructions | Add safe code and requestId |

## 18. Conclusion

Client-facing error responses should be stable, with accurate HTTP statuses, clear error codes, and messages guiding next steps. RFC 9457 Problem Details provides type, title, status, detail, and instance members, and can be extended with code, requestId, and field error lists. The detail member should guide the client to fix the request or contact support, never containing stack traces or debug details.

Request IDs help look up a specific execution; traceId/spanId correlate work across services; error codes identify error categories. In Spring Boot, Micrometer Tracing can populate correlation IDs from MDC into logs. Spring MVC supports ProblemDetail via exception handlers; Spring Data REST has dedicated exception handling, so verify the resolver and response contract on real repository endpoints.

Internal logs must capture exceptions, stack traces, and sanitized context, while public responses expose only safe information. Never log tokens, secrets, sensitive raw bodies, or unnecessary data. Test HTTP statuses, ProblemDetail, request IDs in responses, log searchability, and the absence of internal data leaks.

## References

- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)
- [Spring Framework — Error Responses and ProblemDetail](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring Boot — Tracing and Logging Correlation IDs](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Data REST — RepositoryRestExceptionHandler API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/RepositoryRestExceptionHandler.html)
- [Spring Data REST — RepositoryRestConfigurer API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/config/RepositoryRestConfigurer.html)
- [Spring Data REST — Overriding Response Handlers](https://docs.spring.io/spring-data/rest/reference/5.2/customizing/overriding-sdr-response-handlers.html)