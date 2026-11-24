# Testing ProblemDetail or Custom Error Structures

In Spring MVC, an invalid request or one that cannot complete usually ends with an HTTP error response. Tests must verify both the status and how the API describes the error in the response body. An API may use `ProblemDetail` following the Problem Details for HTTP APIs format, or a custom structure like `{ code, message, errors }`. Either approach can work well; what matters is that the response forms a stable contract that clients can rely on.

`MockMvc` lets you send requests into the Spring MVC processing pipeline and read the response without opening an HTTP port. Through it, tests can verify that exceptions are mapped to the right status, content type, data fields, and extensions. For asynchronously processed requests, tests also need to perform the async dispatch step to observe the final response.

## 1. Exceptions and Error Responses Are Two Different Things

An exception describes what happened inside the application. An error response describes what the client needs to know over HTTP. Do not let internal exception details automatically become the API contract.

For example, a service may throw `OrderNotFoundException` when an order is not found. The API can convert that exception into:

```http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json
```

```json
{
  "type": "https://api.example.com/problems/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "The requested order does not exist.",
  "instance": "/orders/42",
  "code": "ORDER_NOT_FOUND"
}
```

The client needs to know the request failed because the resource does not exist and can handle the `ORDER_NOT_FOUND` code. The client does not need to know which class or method threw the exception or what the stack trace looked like.

An error response test typically answers four questions:

1. Does the HTTP status match the error type?
2. Does `Content-Type` match the format committed by the API?
3. Does the body contain the required fields and a stable error code?
4. Does the body accidentally leak internal details or sensitive data?

## 2. What Is ProblemDetail?

`ProblemDetail` is a data type provided by Spring Framework since Spring Framework 6 to represent Problem Details for HTTP APIs. This format originated in RFC 7807 and is now specified in RFC 9457. When returning a `ProblemDetail` from Spring MVC, the response typically uses the `application/problem+json` media type.

The standard properties include:

| Property | Meaning | Example |
|---|---|---|
| `type` | URI identifying the problem type | `https://api.example.com/problems/order-not-found` |
| `title` | Short summary of the problem type | `Order not found` |
| `status` | HTTP status appropriate for the problem | `404` |
| `detail` | Specific description of this request's failure | `The requested order does not exist.` |
| `instance` | URI referencing this occurrence of the problem | `/orders/42` |

`type` is typically a stable identifier for the error category. If omitted, it defaults to `about:blank`, meaning the problem has no specific type identifier beyond the HTTP status. `detail` is meant for information about the specific occurrence; do not use it as a code for clients to branch logic on.

Spring lets you add extension properties via `ProblemDetail.setProperty(...)`. For example, `code`, `errors`, `field`, or `traceId` can be added to the body alongside the standard properties. With Spring's Jackson integration, extension properties are serialized as top-level JSON properties on the Problem Detail.

## 3. Creating ProblemDetail in `@RestControllerAdvice`

`@RestControllerAdvice` applies exception handlers across controllers and writes the response body directly. A business exception can be mapped to a Problem Detail as follows:

```java
import java.net.URI;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiProblemAdvice {

    @ExceptionHandler(OrderNotFoundException.class)
    ProblemDetail handleOrderNotFound(
            OrderNotFoundException ex,
            HttpServletRequest request) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "The requested order does not exist.");

        problem.setType(URI.create(
                "https://api.example.com/problems/order-not-found"));
        problem.setTitle("Order not found");
        problem.setInstance(URI.create(request.getRequestURI()));
        problem.setProperty("code", "ORDER_NOT_FOUND");

        return problem;
    }
}

class OrderNotFoundException extends RuntimeException {
    OrderNotFoundException(long orderId) {
        super("Order " + orderId + " was not found");
    }
}
```

`ProblemDetail.forStatusAndDetail(...)` initializes the body with status and detail. The handler sets `type`, `title`, `instance`, and a custom error code. Spring MVC uses the status of `ProblemDetail` as the response status when returning this object directly.

In the example, the exception message includes the order ID, but the public `detail` does not need to repeat that data. If the API wants to expose the order ID, a controlled property like `orderId` can be added; consider access permissions and sensitive data before putting values in the response.

## 4. Standardizing Validation Errors with ProblemDetail

When a DTO has `@Valid @RequestBody`, Bean Validation violations typically produce `MethodArgumentNotValidException`. An advice can convert the field errors into an `errors` extension property:

```java
import java.net.URI;
import java.util.List;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ValidationProblemAdvice {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ProblemDetail handleInvalidRequest(MethodArgumentNotValidException ex) {
        List<Map<String, String>> errors = ex.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> Map.of(
                        "field", error.getField(),
                        "code", error.getCode()))
                .toList();

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "One or more request fields are invalid.");

        problem.setType(URI.create(
                "https://api.example.com/problems/validation-error"));
        problem.setTitle("Request validation failed");
        problem.setProperty("code", "VALIDATION_FAILED");
        problem.setProperty("errors", errors);

        return problem;
    }
}
```

The code uses `URI`, so `java.net.URI` must be imported in the file containing the class. `error.getCode()` is the constraint code such as `NotBlank`, `Min`, or `Size`; clients can rely on this code instead of parsing natural-language messages that depend on locale.

If multiple errors are returned, do not assume the order of field errors is always fixed. You can sort by field/code before returning the response if ordering is part of the contract, or write tests that verify the error set in an order-independent way.

In Spring MVC applications, standard binding and validation errors are also supported via `ResponseEntityExceptionHandler` and `ErrorResponse` types. If you need to customize several standard MVC exceptions, you can extend `ResponseEntityExceptionHandler` and override the corresponding handler methods. This preserves the default headers and statuses computed by the framework. For a few custom business exceptions, `@ExceptionHandler` is usually more concise.

## 5. When to Choose a Custom Error Structure?

Some APIs already have an established error schema or need a format tailored to various clients. In that case, a custom DTO can be used instead of Problem Detail:

```java
import java.util.List;

record ApiError(
        String code,
        String message,
        int status,
        List<ApiFieldError> errors) {
}

record ApiFieldError(String field, String code) {
}
```

An advice can return that schema with `ResponseEntity`:

```java
import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class CustomApiErrorAdvice {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ApiError> handleOrderNotFound(OrderNotFoundException ex) {
        ApiError body = new ApiError(
                "ORDER_NOT_FOUND",
                "The requested order does not exist.",
                HttpStatus.NOT_FOUND.value(),
                List.of());

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .contentType(MediaType.APPLICATION_JSON)
                .body(body);
    }
}
```

When using a custom schema, the HTTP status and the `status` field in the body must be consistent. If the API returns errors with `application/json`, tests must check that exact content type. Do not require `application/problem+json` for a response that does not follow Problem Details.

| Criterion | ProblemDetail | Custom error schema |
|---|---|---|
| Standardization across APIs | Has standard properties per Problem Details | Defined by the application |
| Extending fields | Has `properties` serialized as extension members | Add fields to the DTO |
| Common media type | `application/problem+json` | Usually `application/json` |
| Spring MVC integration | Supported directly by Spring | Returned via `ResponseEntity` or regular objects |
| Legacy contract compatibility | May require client changes | Can preserve an already published schema |

Avoid mixing the two schemas arbitrarily across endpoints. If an API has already published an error structure, switching to Problem Detail is a contract change and should be treated as an intentional API change.

## 6. Testing ProblemDetail with MockMvc

Suppose a controller throws `OrderNotFoundException` when the service does not find an order:

```java
@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    OrderView find(@PathVariable long id) {
        return orderService.find(id);
    }
}
```

In `@WebMvcTest`, import the advice so it participates in the MVC slice:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
@Import(ApiProblemAdvice.class)
class OrderControllerProblemTests {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @Test
    void returnsProblemDetailWhenOrderDoesNotExist() throws Exception {
        when(orderService.find(42L))
                .thenThrow(new OrderNotFoundException(42L));

        mockMvc.perform(get("/orders/{id}", 42)
                        .accept(MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(status().isNotFound())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(jsonPath("$.type").value(
                        "https://api.example.com/problems/order-not-found"))
                .andExpect(jsonPath("$.title").value("Order not found"))
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.detail").value(
                        "The requested order does not exist."))
                .andExpect(jsonPath("$.instance").value("/orders/42"))
                .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"));
    }
}
```

The test verifies both the HTTP status and the `status` field in the body. Both values must be `404`. `contentTypeCompatibleWith(...)` is suitable when checking a compatible media type without locking into charset parameter details.

If the controller or advice returns `ProblemDetail` directly, Spring MVC selects `application/problem+json` for the response. Sending `Accept: application/problem+json` in the test makes the format requested by the client explicit. If the API supports multiple representations, test each content negotiation branch according to the published contract.

## 7. Testing Extension Properties and Validation Errors

For validation errors, tests should verify the problem type and the rejected fields. For example:

```java
@Test
void returnsProblemDetailWithFieldErrors() throws Exception {
    mockMvc.perform(post("/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_PROBLEM_JSON)
                    .content("""
                            {
                              "productCode": "BOOK-01",
                              "quantity": 0
                            }
                            """))
            .andExpect(status().isBadRequest())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.type").value(
                    "https://api.example.com/problems/validation-error"))
            .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
            .andExpect(jsonPath("$.errors[0].field").value("quantity"))
            .andExpect(jsonPath("$.errors[0].code").value("Min"));
}
```

This example assumes the DTO has `@Min(1)` on `quantity` and the validation advice from the previous section is imported into the test context. If a request produces multiple errors, use JSONPath filters or deserialize the list and compare as a set so the test does not depend on order.

The key assertions are typically:

- HTTP status is `400`.
- `type` identifies the validation error category.
- `code` is a stable API code.
- `errors` contains the exact violated fields and constraints.
- No stack trace, exception class, or internal information appears in the body.

## 8. Testing a Custom Error Structure

If the API uses `ApiError`, tests should verify the custom schema and content type:

```java
@Test
void returnsCustomErrorEnvelope() throws Exception {
    when(orderService.find(42L))
            .thenThrow(new OrderNotFoundException(42L));

    mockMvc.perform(get("/orders/{id}", 42)
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isNotFound())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"))
            .andExpect(jsonPath("$.message").value(
                    "The requested order does not exist."))
            .andExpect(jsonPath("$.status").value(404))
            .andExpect(jsonPath("$.errors").isArray());
}
```

Here, we do not check `$.type` or `$.title` because the custom envelope is not Problem Detail. The test verifies the exact contract the client actually receives.

If the custom schema has optional fields, distinguish between always-present fields and fields that only appear for certain error types. You can use `jsonPath(...).doesNotExist()` to ensure sensitive fields or non-contract fields are not returned.

## 9. Testing Standard Spring MVC Exceptions

Not all errors come from custom business exceptions. Spring MVC can raise exceptions such as:

| Exception | Common situation | Typical default status |
|---|---|---:|
| `MethodArgumentNotValidException` | `@Valid` DTO has invalid fields | `400` |
| `HttpMessageNotReadableException` | Missing body, malformed JSON, or deserialization failure | `400` |
| `MethodArgumentTypeMismatchException` | Query/path parameter cannot be converted | `400` |
| `MissingServletRequestParameterException` | Required query parameter is missing | `400` |
| `HttpRequestMethodNotSupportedException` | Calling an HTTP method not supported by the endpoint | `405` |
| `HttpMediaTypeNotSupportedException` | Unsupported `Content-Type` | `415` |
| `NoHandlerFoundException` or `NoResourceFoundException` | No matching handler/resource, depending on configuration and version | `404` |

Spring Framework provides `ResponseEntityExceptionHandler` to handle the set of standard MVC exceptions. When an application needs Problem Details for framework errors, it can extend this class or use Spring Boot's Problem Details configuration. Then use `MockMvc` to verify the response for each important case, because exception resolver configuration, advices, and framework versions all affect the final response.

In Spring Boot, auto-configured Problem Details handling for standard MVC errors can be enabled with:

```yaml
spring:
  mvc:
    problemdetails:
      enabled: true
```

This setting supports MVC exceptions that the default mechanism knows how to handle. It does not automatically define semantics for business exceptions like `OrderNotFoundException`; the application still needs its own handlers or mapping mechanisms for those types. If you already have a custom `@ControllerAdvice`, you must understand the precedence order between advices to know which handler actually handles the exception.

## 10. Testing Errors in Asynchronous Flows

In Spring MVC, a controller can return `Callable`, `DeferredResult`, `WebAsyncTask`, or `CompletableFuture`. During asynchronous processing, the initial request may finish in an async state before the final response is ready.

If the async task completes with an exception, Spring performs an async dispatch to continue processing through the MVC pipeline. Exception resolvers and `@ExceptionHandler` can produce the same Problem Detail or custom envelope as in synchronous flows.

Example controller returning `Callable`:

```java
import java.util.concurrent.Callable;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ReportController {

    @GetMapping("/reports/async")
    Callable<String> generateReport() {
        return () -> {
            throw new ReportUnavailableException();
        };
    }
}

class ReportUnavailableException extends RuntimeException {
}
```

Advice mapping that exception:

```java
@ExceptionHandler(ReportUnavailableException.class)
ProblemDetail handleReportUnavailable() {
    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.SERVICE_UNAVAILABLE,
            "The report service is temporarily unavailable.");
    problem.setType(URI.create(
            "https://api.example.com/problems/report-unavailable"));
    problem.setTitle("Report unavailable");
    problem.setProperty("code", "REPORT_UNAVAILABLE");
    return problem;
}
```

The test needs two steps: assert that the request entered async processing, then dispatch the result to obtain the final response:

```java
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;

@Test
void mapsAsyncFailureToProblemDetail() throws Exception {
    MvcResult asyncResult = mockMvc.perform(get("/reports/async")
                    .accept(MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(request().asyncStarted())
            .andReturn();

    mockMvc.perform(asyncDispatch(asyncResult))
            .andExpect(status().isServiceUnavailable())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.type").value(
                    "https://api.example.com/problems/report-unavailable"))
            .andExpect(jsonPath("$.status").value(503))
            .andExpect(jsonPath("$.code").value("REPORT_UNAVAILABLE"));
}
```

`asyncDispatch(...)` uses the async result attached to `MvcResult` to continue processing the response. If the async task depends on a latch, mock service, or test-controlled callback, satisfy that condition before dispatching. Do not inspect the body immediately on the first `perform` call because the final response may not have been created yet.

With `DeferredResult`, similar logic applies when the producer calls `setErrorResult(exception)`. With `CompletableFuture`, an exception completes the future exceptionally; `MockMvc` still requires async dispatch to observe the response. Tests should also distinguish async request timeouts from business exceptions: timeouts can be handled via a timeout callback or a dedicated exception resolver.

## 11. Errors That Do Not Pass Through `@RestControllerAdvice`

`@RestControllerAdvice` handles exceptions within the Spring MVC processing flow. Some errors occur before a request reaches `DispatcherServlet` or are handled in the filter chain, such as:

- Authentication failing before the controller.
- An authenticated user lacking sufficient permissions.
- A rate limiter or filter rejecting the request.
- A reverse proxy or servlet container rejecting the request before MVC reads the body.

These errors are typically handled by the corresponding component, such as `AuthenticationEntryPoint`, `AccessDeniedHandler`, a filter, gateway, or container. Do not expect `@ExceptionHandler` in a controller advice to automatically format all of those errors.

If the API requires the same error schema for both MVC and Spring Security, configure the schema at both boundaries and write tests for each path. `MockMvc` can test the security filter chain when the test is configured with Spring Security; such tests must send requests through the test's real filter chain rather than calling the controller directly.

## 12. Verifying Safety and Stability of the Error Body

A good error response gives clients enough information to handle the error without leaking internals. The following details should generally not appear in public responses:

- Full stack traces or internal exception class names.
- SQL, query statements, or database connection details.
- Internal file paths, deployment directories, or environment variables.
- Tokens, cookies, authorization headers, or unnecessary personal data.
- Raw exception messages that may contain user-supplied input.

Tests can verify that sensitive fields do not appear:

```java
mockMvc.perform(get("/orders/{id}", 42)
                .accept(MediaType.APPLICATION_PROBLEM_JSON))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.stackTrace").doesNotExist())
        .andExpect(jsonPath("$.exception").doesNotExist())
        .andExpect(jsonPath("$.sql").doesNotExist());
```

Only check fields that the application might realistically emit or that the schema forbids. There is no need to list every imaginable field name in every test. More importantly, never pass raw exceptions or internal objects directly into the body.

Error codes such as `ORDER_NOT_FOUND` or `VALIDATION_FAILED` should remain stable across versions. `detail` may be refined for clarity, so clients should not use natural-language sentences as logic keys. If a correlation ID is needed, add a clearly named property and ensure its value is not a secret.

## 13. Assertions to Prioritize

| Target | MockMvc assertion | Purpose |
|---|---|---|
| HTTP status | `status().isNotFound()` | Verify the actual status |
| Problem Details media type | `contentTypeCompatibleWith(APPLICATION_PROBLEM_JSON)` | Verify the response format |
| Problem type | `jsonPath("$.type").value(...)` | Identify a stable problem category |
| Title | `jsonPath("$.title").value(...)` | Verify the error title |
| Status in body | `jsonPath("$.status").value(404)` | Ensure consistency with HTTP status |
| Custom error code | `jsonPath("$.code").value(...)` | Let clients branch on the code |
| Validation fields | `jsonPath("$.errors...")` | Verify specific input errors |
| Disallowed fields | `jsonPath("$.stackTrace").doesNotExist()` | Prevent leaking internal data |

Avoid comparing the entire JSON body against one long string if property ordering or error list ordering is not part of the contract. Use JSONPath to assert meaningful fields, or deserialize into a DTO and compare the required values.

## 14. Common Mistakes When Testing Error Responses

| Practice | Problem | Better practice |
|---|---|---|
| Only asserting status `400` or `500` | Does not verify the body clients rely on | Assert content type, type/code, and key fields |
| Asserting `detail` against the verbatim exception message | Couples tests to internal messages, locale, or library versions | Use stable error codes and intentional public detail |
| Asserting `$.type` on a custom envelope | Custom schemas may not have Problem Details fields | Assert against the endpoint's actual schema |
| Asserting `application/json` for `ProblemDetail` | Misses the Problem Details media type | Assert `application/problem+json` |
| Assuming `@RestControllerAdvice` catches all errors | Filters, security, and containers have separate boundaries | Test the responsible filter/entry point/gateway |
| Reading body right after the first async `perform` | The request may not have finished yet | Use `asyncStarted()` then `asyncDispatch(...)` |
| Comparing validation error lists by fixed index | Error order may change | Compare by field/code or normalize ordering |
| Returning exception messages or stack traces to clients | Can expose implementation details | Map to public messages and stable error codes |

## 15. Workflow for Testing an Error Contract

1. Determine whether the error originates from controller/service code, MVC binding/validation, async processing, or filters/security.
2. Identify the schema published by the endpoint: Problem Detail or a custom error envelope.
3. Verify the exception is mapped at the right advice, resolver, or filter handler.
4. Use `MockMvc` to send a request that triggers the error along the real processing path.
5. Assert the HTTP status and content type.
6. Assert required fields, error code, extension properties, and that sensitive fields do not appear.
7. For validation, verify fields/constraints; for async, verify async start and perform async dispatch.
8. If the error arises in security/filters/container, test at that boundary rather than only testing controller advice.
9. Keep tests independent of stack traces, uncommitted error ordering, and internal exception messages.

## 16. References

- [Spring Framework Reference — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): ProblemDetail, ErrorResponse, and exception handling in Spring MVC.
- [Spring Framework Javadoc — `ProblemDetail`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ProblemDetail.html): standard properties and extension properties.
- [Spring Framework Reference — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): sending requests and asserting responses.
- [Spring Framework Reference — Testing Asynchronous Requests](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/async-requests.html): testing asynchronous MVC requests.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): the standard Problem Details format.
- [Spring Boot Application Properties — `spring.mvc.problemdetails.enabled`](https://docs.spring.io/spring-boot/appendix/application-properties/index.html): enabling Spring Boot auto-configured Problem Details handling.

Testing error responses must prove that the client receives a clear contract when a request fails. Use `ProblemDetail` when following the Problem Details standard, use a custom DTO when the API already has an appropriate schema, and always verify the status, media type, and public codes/fields. With asynchronous processing, complete the async dispatch before asserting the final body.
