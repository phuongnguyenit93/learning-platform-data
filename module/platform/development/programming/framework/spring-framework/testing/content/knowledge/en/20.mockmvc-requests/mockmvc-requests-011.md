# Testing Missing, Wrong-Type, and Out-of-Range Data

When sending requests with `MockMvc`, an API test needs to verify that the application responds properly to invalid data. Common scenarios include a missing body or missing required fields, passing values that cannot be converted to the Java type declared by the controller, and passing values outside business limits such as negative quantities, overly long strings, or excessively large page requests.

These cases happen at different stages of request processing. Spring may reject a request when it fails to read the body, when parameter conversion fails, or after binding succeeds when Bean Validation detects a constraint violation. Therefore, tests should build the exact request form being verified and assert the HTTP contract published by the API.

## 1. Input Validation Layers in Spring MVC

A request passes through several stages before the controller executes business logic:

```text
HTTP request
    |
    v
Mapping and request condition checks
    |
    v
Read body / convert path variable / query parameter
    |
    v
Bind data into parameters or DTO
    |
    v
Bean Validation (if @Valid / @Validated declared)
    |
    v
Controller and business logic
    |
    v
HTTP response
```

Typical scenarios:

| Input | Example | Stage typically catching it | Common HTTP outcome |
|---|---|---|---|
| Missing required request body | Sending `POST` without a body for a `@RequestBody` parameter | Body reading | `400 Bad Request` |
| Missing required field in JSON | Omitting `quantity` from a JSON DTO annotated with `@NotNull` | Bean Validation after binding | `400 Bad Request` |
| Invalid JSON syntax or wrong JSON type | Sending `"quantity": "many"` when Java expects `Integer` | HTTP message converter/Jackson | `400 Bad Request` |
| Missing required query parameter | Omitting `pageSize` with `@RequestParam` default `required=true` | Controller argument resolution | `400 Bad Request` |
| Wrong query/path parameter type | Sending `pageSize=large` for `int` or non-numeric id for `Long` | Conversion | `400 Bad Request` |
| Range violation | `quantity=0`, `quantity=101` when range is 1 to 100 | Bean Validation | `400 Bad Request` |
| Wrong media type | Sending a non-JSON body to an endpoint consuming only JSON | Content negotiation/message converter | `415 Unsupported Media Type` |

These are Spring MVC's common default outcomes. An API may define its own error response body via `@RestControllerAdvice`; tests should assert the status and error structure defined by that contract rather than relying on internal framework messages.

## 2. Declaring the Input Contract for a Request Body

Suppose an order-creation API accepts a product code and quantity. The DTO uses the `Integer` wrapper so a missing field (`null`) can be distinguished from a numeric value of 0:

```java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record CreateOrderRequest(
        @NotBlank
        @Size(max = 20)
        String productCode,

        @NotNull
        @Min(1)
        @Max(100)
        Integer quantity
) {
}
```

The constraints express distinct conditions:

- `@NotNull` requires the value to be present and non-`null`.
- `@NotBlank` requires the string to be non-null, non-empty, and contain at least one non-whitespace character.
- `@Size(max = 20)` caps string length at 20 characters.
- `@Min(1)` and `@Max(100)` define the valid numeric range for quantity, inclusive of both bounds 1 and 100.

If `int` were used instead of `Integer`, a missing JSON field could receive the default value `0` during binding. Then `@NotNull` could not detect the missing field. For required numeric inputs that must distinguish "not sent" from "sent 0", a wrapper type expresses the contract more accurately.

The controller instructs Spring to validate the DTO after reading the body:

```java
import jakarta.validation.Valid;
import java.util.List;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    OrderView create(@Valid @RequestBody CreateOrderRequest request) {
        return orderService.create(request);
    }

    @GetMapping("/search")
    List<OrderView> search(@RequestParam int pageSize) {
        return orderService.search(pageSize);
    }

    @GetMapping("/by-id/{id}")
    OrderView findById(@PathVariable Long id) {
        return orderService.findById(id);
    }
}

interface OrderService {
    OrderView create(CreateOrderRequest request);
    List<OrderView> search(int pageSize);
    OrderView findById(Long id);
}

record OrderView(Long id, String productCode, Integer quantity) {
}
```

`@RequestBody` requests that the body be read into `CreateOrderRequest`. `@Valid` instructs Spring to run Bean Validation on the DTO once conversion succeeds. If a field is missing or violates a constraint, execution does not enter the controller's business logic.

The application needs a Jakarta Bean Validation implementation on the classpath, typically via `spring-boot-starter-validation` in Spring Boot. Declaring annotations without a provider on the classpath may prevent validation from executing.

## 3. Standardizing Error Responses for the API

Spring MVC can generate default error responses, yet real APIs usually need a stable structure for clients to handle. You can define an error code and a list of violations:

```java
import java.util.List;

record ApiError(String code, List<FieldViolation> violations) {
}

record FieldViolation(String field, String constraint) {
}
```

A `@RestControllerAdvice` can translate common input errors into a unified response:

```java
import java.util.List;

import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ApiError> handleValidation(MethodArgumentNotValidException ex) {
        List<FieldViolation> violations = ex.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> new FieldViolation(error.getField(), error.getCode()))
                .toList();

        return ResponseEntity.badRequest()
                .body(new ApiError("VALIDATION_FAILED", violations));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ResponseEntity<ApiError> handleUnreadableBody(HttpMessageNotReadableException ex) {
        return ResponseEntity.badRequest()
                .body(new ApiError("INVALID_REQUEST_BODY", List.of()));
    }

    @ExceptionHandler({
            MethodArgumentTypeMismatchException.class,
            MissingServletRequestParameterException.class
    })
    ResponseEntity<ApiError> handleInvalidParameter(Exception ex) {
        return ResponseEntity.badRequest()
                .body(new ApiError("INVALID_PARAMETER", List.of()));
    }
}
```

This example keeps responses independent of verbose Jackson or Bean Validation error strings. `constraint` is taken from constraint codes such as `NotNull`, `NotBlank`, `Min`, `Max`, or `Size`; clients do not need to parse text messages that can vary by locale or provider version.

In production applications, you can add case-specific error codes, parameter locations (`query`, `path`, `body`), rejected values, or correlation IDs. Include only safe data in the response; never expose stack traces, internal class names, or raw exception text to clients.

## 4. Setting Up MockMvc for Controller Tests

With Spring Boot, `@WebMvcTest` creates an MVC slice and provides `MockMvc` to send requests without opening an HTTP port. The controller can use a mocked service so tests focus on binding, validation, and response construction.

```java
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.beans.factory.annotation.Autowired;

@WebMvcTest(OrderController.class)
@Import(ApiExceptionHandler.class)
class OrderControllerRequestTests {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;
}
```

`@WebMvcTest` focuses on web components. If the controller requires a service, repository, or other business bean, provide mocks or import the corresponding test configuration. In invalid-data tests, the service is usually not called because the request is rejected before entering the controller.

Common static imports:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
```

A JSON request is sent using `.contentType(MediaType.APPLICATION_JSON)` and `.content(...)`. Setting the right `Content-Type` matters because it determines which converter is chosen to read the body.

## 5. Testing Missing Body and Missing JSON Fields

These two cases are distinct and usually trigger different exceptions.

### Missing the Entire Request Body

With `@RequestBody` defaulting to `required=true`, a request without a body cannot supply the input object. Spring typically throws `HttpMessageNotReadableException` and returns `400 Bad Request`.

```java
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void rejectsMissingRequestBody() throws Exception {
    mockMvc.perform(post("/orders")
                    .contentType(MediaType.APPLICATION_JSON))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_REQUEST_BODY"));
}
```

Sending `.content("")` is also an empty-body case. If the API allows an optional body via `@RequestBody(required = false)`, the contract differs and the controller must intentionally handle a `null` value.

### Missing a Required Field in JSON

When the body is syntactically valid yet omits `quantity`, Jackson can still instantiate the DTO with `quantity == null`. Bean Validation then detects the `@NotNull` violation:

```java
@Test
void rejectsMissingRequiredField() throws Exception {
    mockMvc.perform(post("/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "productCode": "BOOK-01"
                            }
                            """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
            .andExpect(jsonPath("$.violations[0].field").value("quantity"))
            .andExpect(jsonPath("$.violations[0].constraint").value("NotNull"));
}
```

The order of errors in the list can depend on how the provider reports results. When a request produces a single error as in this example, checking the first element suffices. If a request produces multiple errors, verify by field/constraint membership or use JSONPath filters to avoid order sensitivity.

### Empty, Whitespace-Only, and Null Strings

`@NotNull`, `@NotEmpty`, and `@NotBlank` have different semantics:

| Value | `@NotNull` | `@NotEmpty` | `@NotBlank` |
|---|---:|---:|---:|
| `null` | Invalid | Invalid | Invalid |
| `""` | Valid | Invalid | Invalid |
| `"   "` | Valid | Valid | Invalid |
| `"BOOK"` | Valid | Valid | Valid |

If the contract requires a name or code with actual characters, `@NotBlank` expresses this better than `@NotNull`. Send each value in tests to verify the policy the API intends to enforce.

## 6. Testing Malformed JSON or Wrong Data Types

Syntactically valid JSON does not guarantee types compatible with the DTO. When `quantity` is `Integer`, the following value has the wrong type:

```json
{
  "productCode": "BOOK-01",
  "quantity": "many"
}
```

Jackson cannot convert the string `"many"` into an integer. The error occurs while reading the body, before Bean Validation, so the handler receives `HttpMessageNotReadableException` instead of `MethodArgumentNotValidException`.

```java
@Test
void rejectsWrongJsonValueType() throws Exception {
    mockMvc.perform(post("/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "productCode": "BOOK-01",
                              "quantity": "many"
                            }
                            """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_REQUEST_BODY"));
}
```

Syntactically malformed JSON is rejected at the same stage:

```java
@Test
void rejectsMalformedJson() throws Exception {
    mockMvc.perform(post("/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"productCode\": \"BOOK-01\", \"quantity\": }"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_REQUEST_BODY"));
}
```

Avoid asserting against Jackson messages such as "Cannot deserialize value..." because those messages can change across versions, configurations, and locales. Assert the status and the API's published error code instead.

## 7. Testing Wrong-Type or Missing Query Parameters and Path Variables

Unlike JSON bodies, query parameters and path variables are typically converted from URL strings into the Java types of controller parameters.

Example of an endpoint accepting page size:

```java
@GetMapping("/search")
List<OrderView> search(@RequestParam int pageSize) {
    return orderService.search(pageSize);
}
```

`pageSize=large` cannot be converted to `int`:

```java
@Test
void rejectsNonNumericQueryParameter() throws Exception {
    mockMvc.perform(get("/orders/search")
                    .param("pageSize", "large"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_PARAMETER"));
}
```

If `pageSize` is required and omitted, Spring typically throws `MissingServletRequestParameterException`:

```java
@Test
void rejectsMissingRequiredQueryParameter() throws Exception {
    mockMvc.perform(get("/orders/search"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_PARAMETER"));
}
```

For path variables, such as `@PathVariable Long id`, `/orders/by-id/abc` cannot be converted to `Long` and usually results in `MethodArgumentTypeMismatchException`, also returning `400` under default handling or the advice above. If the `/id` segment is missing completely, the URL may fail to match the route and return `404 Not Found`; that is a routing error, not a parameter type-conversion error.

A parameter declared as `String` accepts arbitrary text, so `pageSize=large` is only a type error when the controller declares a target type such as `int`, `Integer`, `Long`, an enum, or a type with an associated converter. Check the exact controller signature when designing tests.

## 8. Testing Lower Bounds, Upper Bounds, and Lengths

Boundary tests should cover both sides of every limit. For `quantity` from 1 to 100:

| Value | Expectation | Relevant constraint |
|---:|---|---|
| `0` | Reject | `@Min(1)` |
| `1` | Accept | Valid lower boundary value |
| `100` | Accept | Valid upper boundary value |
| `101` | Reject | `@Max(100)` |

Test for a value below the lower bound:

```java
@Test
void rejectsQuantityBelowMinimum() throws Exception {
    mockMvc.perform(post("/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "productCode": "BOOK-01",
                              "quantity": 0
                            }
                            """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
            .andExpect(jsonPath("$.violations[0].field").value("quantity"))
            .andExpect(jsonPath("$.violations[0].constraint").value("Min"));
}
```

Test for a value above the upper bound:

```java
@Test
void rejectsQuantityAboveMaximum() throws Exception {
    mockMvc.perform(post("/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "productCode": "BOOK-01",
                              "quantity": 101
                            }
                            """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
            .andExpect(jsonPath("$.violations[0].field").value("quantity"))
            .andExpect(jsonPath("$.violations[0].constraint").value("Max"));
}
```

For an overly long string, send a value exceeding `@Size(max = 20)`:

```java
@Test
void rejectsProductCodeLongerThanAllowed() throws Exception {
    mockMvc.perform(post("/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "productCode": "123456789012345678901",
                              "quantity": 1
                            }
                            """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
            .andExpect(jsonPath("$.violations[0].field").value("productCode"))
            .andExpect(jsonPath("$.violations[0].constraint").value("Size"));
}
```

A complete test suite must also confirm that exact boundary values are accepted. Mock the service to return a result and verify that requests with `quantity=1` or `quantity=100` pass through the controller. Testing only invalid values does not prove whether bounds were configured as inclusive or exclusive.

### Digit and Decimal Limits

For monetary amounts or rates, choose constraints suited to the data type and business semantics:

- `@DecimalMin` and `@DecimalMax` constrain bounds for `BigDecimal` or compatible numeric types.
- `inclusive = false` applies when a value equal to the bound is also invalid.
- `@Digits(integer = ..., fraction = ...)` limits the number of integer and fractional digits.
- `@Positive`, `@PositiveOrZero`, `@Negative`, and `@NegativeOrZero` express sign rules.

Do not use `double` for money merely for the convenience of decimal limit checks. `BigDecimal` is generally more suitable because it represents decimal numbers accurately and supports the corresponding constraints.

## 9. Distinguishing Data Limits from HTTP Size Limits

`@Size`, `@Min`, `@Max`, and Bean Validation constraints inspect data after the request has been read and bound. They do not themselves limit the byte size of an HTTP body.

For example, `@Size(max = 20)` on `productCode` only checks the length of the string already deserialized into the DTO. If a client sends a massive JSON body, the application may still have to read or parse the body before that constraint ever runs.

Other limits belong to the HTTP or infrastructure layer:

| Limit kind | Where typically configured | Suitable test approach |
|---|---|---|
| String length, quantity, date range | Bean Validation or business logic | `MockMvc` with values below, at, and above the boundary |
| Number of elements in a JSON list | `@Size` on collection or validator | `MockMvc` with empty, at-limit, and over-limit lists |
| Uploaded file size | Multipart configuration and multipart resolver/container | `MockMvc` multipart for app logic; embedded server tests for container limits |
| Total HTTP request body size | Servlet container, proxy, gateway, or body-limiting filter | Integration tests through a real server/infrastructure with configured limits |
| Request rate or per-client quota | Gateway, filter, or rate limiter | Unit/component tests for that component and integration tests along the real request path |

`MockMvc` simulates Spring MVC processing in the test process, without opening sockets or passing through a full servlet container connector or reverse proxy. Thus, a `MockMvc` test can prove the application's validator rejects an overly long string, yet it cannot prove Nginx, an API Gateway, or embedded Tomcat caps request bodies at an exact byte count.

If the application includes a filter that explicitly checks `Content-Length` or enforces a byte-reading limit, that filter can be tested inside the MockMvc filter chain. Still, connector behavior for chunked requests, real bodies, and multipart requires tests against a really started server.

## 10. Mismatched Media Type and Request Format

Testing invalid data also requires distinguishing body errors from media type errors. If an endpoint declares:

```java
@PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
OrderView create(@Valid @RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
```

a request sending `Content-Type: text/plain` does not match `consumes`. Spring typically returns `415 Unsupported Media Type` before Bean Validation runs.

```java
@Test
void rejectsUnsupportedContentType() throws Exception {
    mockMvc.perform(post("/orders")
                    .contentType(MediaType.TEXT_PLAIN)
                    .content("productCode=BOOK-01&quantity=1"))
            .andExpect(status().isUnsupportedMediaType());
}
```

This test verifies the media type contract, not a type mismatch on the `quantity` field. Likewise, `Accept` describes the response format the client can receive; it differs from `Content-Type`, which describes the body format the client is sending.

## 11. Preventing Business Logic from Running When a Request Is Rejected

When an invalid request is blocked during binding or validation, the service must not be invoked. This can be verified using Mockito:

```java
import static org.mockito.Mockito.verifyNoInteractions;

@Test
void doesNotCallServiceWhenRequiredFieldIsMissing() throws Exception {
    mockMvc.perform(post("/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "productCode": "BOOK-01"
                            }
                            """))
            .andExpect(status().isBadRequest());

    verifyNoInteractions(orderService);
}
```

This assertion is helpful when the boundary to protect is that the controller never invokes business logic with invalid data. If the controller calls another dependency before validation or executes logic in a filter/interceptor, verify only the dependencies belonging to the contract under test.

## 12. Method Parameter Validation vs. DTO Validation

The examples in this article use `@Valid @RequestBody` to validate DTO fields. When placing constraints directly on controller parameters, such as `@Min(1) @RequestParam int pageSize`, Spring Framework 6.1 and later include built-in method validation that can raise `HandlerMethodValidationException`.

If the controller class uses `@Validated` to trigger proxy-based method validation, the execution path and exception type can differ, often involving `ConstraintViolationException`. When writing `@RestControllerAdvice`, base exception handlers on how validation is actually enabled in the application and handle the corresponding exceptions. Do not assume every violation raises `MethodArgumentNotValidException`.

In tests, send requests via `MockMvc` just like a real client and assert the final response contract. Assert exception classes directly only in unit tests dedicated to a validator or advice when that exception type itself is what needs verification.

## 13. Recommended Input Test Matrix

For an endpoint accepting JSON, a baseline matrix can include:

| Category | Request to send | Expectation |
|---|---|---|
| Body | No body | `400`, missing/unreadable body error code |
| Structure | Malformed JSON syntax | `400`, invalid body error code |
| Type | Numeric field receives non-convertible string | `400`, invalid body error code |
| Required | Missing `quantity` field | `400`, `NotNull` violation |
| String | `productCode` is `null`, empty, or whitespace-only | `400`, matching constraint violation |
| Length | `productCode` longer than 20 characters | `400`, `Size` violation |
| Below min | `quantity=0` | `400`, `Min` violation |
| Lower bound | `quantity=1` | Request accepted |
| Upper bound | `quantity=100` | Request accepted |
| Above max | `quantity=101` | `400`, `Max` violation |
| Query | Missing required `pageSize` | `400`, parameter error code |
| Query | `pageSize=large` | `400`, parameter error code |
| Media type | Sending `text/plain` to a JSON-only endpoint | `415` |

It is unnecessary to cram every case into one large test. Give each test a name describing one rejection reason and one primary expectation. Use parameterized tests when multiple values verify the same rule, such as `0` and `101` for quantity bounds.

## 14. Common Mistakes When Writing Tests

| Approach | Why it is poor | Clearer approach |
|---|---|---|
| Checking only status `400` for every invalid input | Fails to distinguish missing fields, wrong types, and out-of-range values | Also assert the error code and field/constraint in the response |
| Asserting on full exception message strings | Couples tests to Jackson, Bean Validation provider, locale, and version | Assert stable API error codes |
| Using `int` for a required field and expecting `@NotNull` | Primitives cannot represent `null` | Use wrappers like `Integer` when missing fields must be detected |
| Using `@NotNull` for strings where whitespace-only is invalid | `@NotNull` still accepts `"   "` | Use `@NotBlank` when meaningful content is required |
| Testing only out-of-bounds values | Does not prove valid boundary values are accepted | Test both exact boundary values and values just outside each boundary |
| Assuming `@Size` caps HTTP body byte size | `@Size` runs on already-bound values | Test body size limits at the appropriate filter/container/gateway layer |
| Sending `pageSize=large` when controller takes `String` | Spring has no reason to convert the string to a number | Declare the parameter type matching the contract, e.g., `int` |
| Expecting service calls in failed validation tests | Requests should be blocked before business logic | Use `verifyNoInteractions` or appropriate verification |

## 15. Workflow for Writing an Invalid-Data Test

1. Inspect the endpoint signature: `@RequestBody`, `@RequestParam`, `@PathVariable`, `consumes`, and the Java type of each parameter.
2. Identify at which stage the invalid request fails: missing data, unparseable input, unconvertible type, or post-binding constraint violation.
3. Use `MockMvc` to construct the exact request a client sends, including URL, `Content-Type`, body, and parameters.
4. Assert the HTTP status according to the contract, such as `400` for invalid data or `415` for unsupported media type.
5. If the API has an error schema, assert stable error codes, fields, and constraints.
6. Confirm the service is not called when the request is rejected before business logic.
7. For bounds, test both valid boundary values and values just outside each bound.
8. For byte limits or container/proxy-dependent behavior, add integration tests through a real server/infrastructure.

## 16. References

- [Spring Framework Reference — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): Jakarta Bean Validation integration in Spring.
- [Spring Framework Reference — `@RequestBody`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html): reading request bodies, message converters, and validation.
- [Spring Framework Reference — `@RequestParam`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html): binding query parameters to controller arguments.
- [Spring Framework Reference — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): performing requests and asserting responses in Spring MVC Test.
- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/): constraint semantics and validation mechanisms.

Testing missing, wrong-type, and out-of-range data is most valuable when each request faithfully simulates errors a real client can send. Distinguish body-reading errors, parameter-conversion errors, and Bean Validation errors; then assert the response contract at the exact boundary. This proves the API rejects invalid input before business logic executes.
