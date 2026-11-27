# Testing Validation Errors and Error Responses

## 1. Why Test and Document Error Responses?

An API does not only return success responses. Clients also need to know how the server responds when a request is missing required fields, has invalid formats, violates constraints, or breaks business rules. If only HTTP 200/201 responses are documented, integrators are forced to guess the error structure and how to handle it.

In **SPRING_REST_DOCS**, REST API documentation is generated from HTTP tests using MockMvc, WebTestClient, or REST Assured. These tests verify request/response behavior and produce snippets for payloads, headers, parameters, and status codes. Snippets are then compiled in Asciidoctor/Markdown and integrated into build/CI.

The **Documentation Tests** chapter helps turn contract changes into verification signals. This lesson focuses on validation and error responses: enabling Bean Validation, distinguishing binding errors from business errors, standardizing responses via `@RestControllerAdvice`, writing negative tests, and using Spring REST Docs to describe the error contract.

After this lesson, you will be able to:

- Test invalid requests using MockMvc.
- Distinguish deserialization/binding errors, Bean Validation errors, and business errors.
- Design a stable error response with error codes and field details.
- Use `responseFields(...)` or `responseBody(...)` to document errors.
- Use `requestFields(...)` when input payloads need descriptions and `responseHeaders(...)` for error headers.
- Assert status, error code, field paths, and messages in tests.
- Integrate negative tests and error snippets into Asciidoctor/CI.

## 2. Classifying Input Errors

An invalid request can fail at multiple stages. Distinguishing them helps the API return consistent status codes and error codes.

| Error group | Examples | Where typically detected |
| --- | --- | --- |
| JSON parse/deserialization | Malformed JSON body or unconvertible data type | Jackson/HttpMessageConverter |
| Bean Validation | Blank `name`, negative `price`, malformed email | `@Valid` / Jakarta Validation |
| Request binding | Missing required query parameter, unconvertible path value | Spring MVC argument resolver |
| Multipart validation | Missing file, unsupported MIME type, empty file | Controller/service or multipart resolver |
| Domain/business validation | Product cannot transition state, quantity exceeds stock | Service/domain layer |
| Authorization | User lacks permission to perform the operation | Security filter/method security |

Not every error passes through the controller method. For instance, a JSON parse error occurs before the method is invoked; validation errors may be thrown after the body is deserialized; business errors typically arise in the service layer. Exception handlers must cover the exact exceptions the application intends to standardize.

## 3. Defining Request DTOs with Bean Validation

Suppose `POST /api/products` accepts:

```json
{
  "name": "Mechanical Keyboard",
  "price": 1290000,
  "email": "owner@example.com"
}
```

The DTO can declare constraints:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

public record CreateProductRequest(
        @NotBlank
        @Size(max = 120)
        String name,

        @Positive
        Integer price,

        @NotBlank
        @Email
        String email
) {}
```

The controller triggers validation with `@Valid`:

```java
@RestController
@RequestMapping("/api/products")
class ProductController {

    private final ProductService productService;

    ProductController(ProductService productService) {
        this.productService = productService;
    }

    @PostMapping
    ResponseEntity<ProductResponse> create(
            @Valid @RequestBody CreateProductRequest request) {

        ProductResponse response = productService.create(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }
}
```

If `@Valid` (or an equivalent validation mechanism) is missing, constraints on the DTO may not be enforced when a request enters the controller. The project also needs a Jakarta Bean Validation implementation dependency compatible with its Spring Boot/Spring Framework version.

## 4. Designing a Stable Error Response

An error response should have a consistent structure so clients can handle it programmatically. Example:

```json
{
  "code": "VALIDATION_FAILED",
  "message": "Request contains invalid fields",
  "status": 400,
  "path": "/api/products",
  "fieldErrors": [
    {
      "field": "name",
      "code": "NotBlank",
      "message": "must not be blank"
    },
    {
      "field": "price",
      "code": "Positive",
      "message": "must be greater than 0"
    }
  ]
}
```

An illustrative DTO:

```java
public record FieldErrorDetail(
        String field,
        String code,
        String message
) {}

public record ApiError(
        String code,
        String message,
        int status,
        String path,
        List<FieldErrorDetail> fieldErrors
) {}
```

Design principles:

- `code` is stable and independent of display wording.
- `message` provides a concise explanation for integrators.
- `status` mirrors the HTTP status for convenient debugging, though the HTTP status line remains authoritative.
- `path` includes only the necessary path; avoid echoing query strings that might contain sensitive data.
- `fieldErrors` only applies when errors relate to fields; it can be an empty array or omitted per a consistent convention.
- Never return stack traces, SQL, internal class names, file paths, or secret data.

Standardize the ordering rule for `fieldErrors` if you want stable snippets and test outputs. Do not let tests depend on an ordering not guaranteed by the contract.

## 5. Mapping Bean Validation via `@RestControllerAdvice`

In Spring MVC, Bean Validation failures on `@Valid @RequestBody` are typically represented by `MethodArgumentNotValidException`. You can map the exception to the response contract:

```java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ApiError> handleValidation(
            MethodArgumentNotValidException exception,
            HttpServletRequest request) {

        List<FieldErrorDetail> details =
                exception.getBindingResult()
                        .getFieldErrors()
                        .stream()
                        .map(error -> new FieldErrorDetail(
                                error.getField(),
                                error.getCode(),
                                error.getDefaultMessage()
                        ))
                        .toList();

        ApiError body = new ApiError(
                "VALIDATION_FAILED",
                "Request contains invalid fields",
                HttpStatus.BAD_REQUEST.value(),
                request.getRequestURI(),
                details
        );

        return ResponseEntity.badRequest().body(body);
    }
}
```

This is an example for Spring MVC and modern Java; import `HttpServletRequest`, `MethodArgumentNotValidException`, `HttpStatus`, and collection types as appropriate for the project. In newer Spring versions, certain method-level validation modes may throw a different exception, such as `HandlerMethodValidationException`; if an endpoint uses that mechanism, handle and test it separately.

### 5.1. Handling Unparseable JSON Errors

Malformed or unconvertible JSON can raise `HttpMessageNotReadableException`. This is not a Bean Validation error because the DTO was never successfully constructed to run constraints.

```java
@ExceptionHandler(HttpMessageNotReadableException.class)
ResponseEntity<ApiError> handleUnreadableBody(
        HttpMessageNotReadableException exception,
        HttpServletRequest request) {

    ApiError body = new ApiError(
            "INVALID_REQUEST_BODY",
            "Request body is missing or malformed",
            HttpStatus.BAD_REQUEST.value(),
            request.getRequestURI(),
            List.of()
    );

    return ResponseEntity.badRequest().body(body);
}
```

Do not expose detailed parser messages directly to clients if they contain internal details or are overly cryptic. Log the full cause on the server with a correlation ID; keep the public response stable.

### 5.2. Handling Business Errors

Suppose a product name already exists:

```java
public class ProductAlreadyExistsException extends RuntimeException {
    public ProductAlreadyExistsException(String name) {
        super(name);
    }
}
```

Handler:

```java
@ExceptionHandler(ProductAlreadyExistsException.class)
ResponseEntity<ApiError> handleDuplicateProduct(
        ProductAlreadyExistsException exception,
        HttpServletRequest request) {

    ApiError body = new ApiError(
            "PRODUCT_ALREADY_EXISTS",
            "A product with this name already exists",
            HttpStatus.CONFLICT.value(),
            request.getRequestURI(),
            List.of()
    );

    return ResponseEntity.status(HttpStatus.CONFLICT).body(body);
}
```

Business errors often use status 409 when conflicting with a resource's current state, though status codes must follow the API contract. Do not lump all errors into `400` if clients need to distinguish validation, conflict, authorization, and server errors.

## 6. Writing Negative Tests with MockMvc

Tests must send invalid requests and verify both the status and the error payload. For example, blank `name`, negative `price`, and invalid email:

```java
@Test
void returnsValidationErrorForInvalidCreateProduct() throws Exception {
    mockMvc.perform(post("/api/products")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "name": "",
                  "price": -10,
                  "email": "not-an-email"
                }
                """))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.status").value(400))
        .andExpect(jsonPath("$.fieldErrors").isArray())
        .andExpect(jsonPath("$.fieldErrors[*].field",
                containsInAnyOrder("name", "price", "email")));
}
```

`containsInAnyOrder` avoids locking error order if the contract does not guarantee ordering. If the API enforces a fixed ordering rule, you can assert that exact order.

This test only verifies the application's response when validation is enabled. It must also run against a test configuration that includes the real `@RestControllerAdvice`. If a test uses standalone MockMvc, register the controller advice explicitly.

## 7. Using Spring REST Docs to Document Error Responses

A negative test can generate snippets for both the erroneous request and error response. Example:

```java
mockMvc.perform(post("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content("""
            {
              "name": "",
              "price": -10,
              "email": "not-an-email"
            }
            """))
    .andExpect(status().isBadRequest())
    .andDo(document("products-create-validation-error",
        requestFields(
            fieldWithPath("name").description("Product name"),
            fieldWithPath("price").description("Selling price"),
            fieldWithPath("email").description("Manager email")
        ),
        responseFields(
            fieldWithPath("code").description("Stable error code"),
            fieldWithPath("message").description("General error description"),
            fieldWithPath("status").description("HTTP status"),
            fieldWithPath("path").description("Request path"),
            fieldWithPath("fieldErrors").description("List of validation errors"),
            fieldWithPath("fieldErrors[].field").description("Invalid field name"),
            fieldWithPath("fieldErrors[].code").description("Constraint code"),
            fieldWithPath("fieldErrors[].message").description("Validation message")
        )
    ));
```

If the test only needs to document the error response, you can use `responseFields(...)` without repeating request fields. Conversely, when you want readers to see the shape of the request that triggered the error, keep `requestFields(...)` and describe the input payload.

Descriptors must match the actual response. If the response gains a new undocumented field, strict `responseFields(...)` can fail the test. This is useful behavior for catching error contract drift.

### 7.1. Separating Snippets for Each Error Type

Do not collapse every error into one operation ID when the response structure or cause differs. You can create separate ones:

```text
products-create-validation-error/
products-create-invalid-json/
products-create-conflict/
products-create-unauthorized/
```

Each operation ID can generate `http-response.adoc`, `response-fields.adoc`, and other snippets according to configuration. Documentation pages can include distinct error examples.

## 8. Documenting Error Responses with `responseBody(...)`

When an error response has a large JSON structure or follows a shared schema, you can use `responseBody(...)` to include a sample body instead of describing every field.

Example:

```java
.andDo(document("products-create-validation-error",
    responseBody()
));
```

Body snippets help readers see a complete error response. However, a body snippet does not replace field-structure verification. If you need a detailed contract and strict validation, use `responseFields(...)`; if you need both the schema and the example, you can use both.

You can add `responseHeaders(...)` if the error response exposes important public headers:

```java
responseHeaders(
    headerWithName("Content-Type")
        .description("Error response format"),
    headerWithName("X-Correlation-Id")
        .description("Identifier for looking up support logs")
);
```

Only document a correlation header if the application actually returns that header. Do not record tokens or cookies in snippets.

## 9. Distinguishing Validation Errors, Binding Errors, and Domain Errors

A good API page should help clients understand which error types can occur.

| Scenario | Typical exception/source | Example status | Example error code |
| --- | --- | --- | --- |
| Field violates `@NotBlank` | `MethodArgumentNotValidException` | 400 | `VALIDATION_FAILED` |
| Malformed JSON | `HttpMessageNotReadableException` | 400 | `INVALID_REQUEST_BODY` |
| Unconvertible query param | Type mismatch/binding exception | 400 | `INVALID_PARAMETER` |
| Resource already exists causing conflict | Domain exception | 409 | `PRODUCT_ALREADY_EXISTS` |
| Unauthorized / unauthenticated | Security exception/entry point | 401 or 403 | `UNAUTHORIZED` / `FORBIDDEN` |
| Unsupported media type | `HttpMediaTypeNotSupportedException` | 415 | `UNSUPPORTED_MEDIA_TYPE` |

This table is a guide; actual exceptions and status codes depend on controller argument types, Spring version, security configuration, and exception handlers. Tests must verify the application's actual behavior.

Avoid writing an overly broad handler catching `Exception` and returning `400` for everything. Programming or system failures must be handled as server errors rather than turned into client request errors.

## 10. Testing Field-Level Errors

With `fieldErrors`, tests can verify the path and code of each error:

```java
.andExpect(jsonPath("$.fieldErrors[?(@.field == 'name')].code")
        .value(hasItem("NotBlank")))
.andExpect(jsonPath("$.fieldErrors[?(@.field == 'price')].code")
        .value(hasItem("Positive")));
```

JSONPath filter syntax can depend on the implementation. If it becomes hard to read, use `jsonPath("$.fieldErrors").value(...)` with a suitable matcher or deserialize the body into `ApiError` in the test.

If messages are localized by `Accept-Language`, avoid locking tests to a single message string unless that is part of the contract. Assert the stable error code, field path, and status; write separate tests for localization when needed.

For nested DTO errors, paths may look like `address.postalCode` or `items[0].quantity` depending on the binding result. Documentation should explain the path format the API returns and keep examples consistent.

## 11. WebTestClient and REST Assured

### 11.1. WebTestClient

Example negative test with WebTestClient:

```java
webTestClient.post()
    .uri("/api/products")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(Map.of(
        "name", "",
        "price", -10,
        "email", "not-an-email"
    ))
    .exchange()
    .expectStatus().isBadRequest()
    .expectBody()
    .jsonPath("$.code").isEqualTo("VALIDATION_FAILED")
    .consumeWith(document("products-create-validation-error",
        responseFields(
            fieldWithPath("code").description("Error code"),
            fieldWithPath("message").description("Error description"),
            fieldWithPath("status").description("HTTP status"),
            fieldWithPath("path").description("Request path"),
            fieldWithPath("fieldErrors").description("List of errors"),
            fieldWithPath("fieldErrors[].field").description("Invalid field"),
            fieldWithPath("fieldErrors[].code").description("Constraint code"),
            fieldWithPath("fieldErrors[].message").description("Message")
        )
    ));
```

This is an example using WebTestClient integrated with Spring REST Docs; the body style and test configuration must match the application's MVC/WebFlux stack. With WebFlux, validation exceptions and controller signatures may differ from MVC; verify against the runtime in use.

### 11.2. REST Assured

```java
given(this.spec)
    .filter(document("products-create-validation-error",
        responseFields(
            fieldWithPath("code").description("Error code"),
            fieldWithPath("message").description("Error description"),
            fieldWithPath("status").description("HTTP status"),
            fieldWithPath("path").description("Request path"),
            fieldWithPath("fieldErrors").description("List of errors"),
            fieldWithPath("fieldErrors[].field").description("Invalid field"),
            fieldWithPath("fieldErrors[].code").description("Constraint code"),
            fieldWithPath("fieldErrors[].message").description("Message")
        )))
    .contentType("application/json")
    .body(Map.of(
        "name", "",
        "price", -10,
        "email", "not-an-email"
    ))
    .when()
    .post("/api/products")
    .then()
    .statusCode(400)
    .body("code", equalTo("VALIDATION_FAILED"));
```

How filters and bodies are attached depends on the REST Assured module and version. What matters is ensuring negative assertions and snippet descriptors reflect the actual error response.

## 12. Organizing Asciidoctor for an Error Catalog

After tests run, output may include:

```text
build/generated-snippets/
└── products-create-validation-error/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-fields.adoc
    ├── response-fields.adoc
    └── response-body.adoc
```

Only snippets requested in `document(...)` are generated. Example documentation page:

```adoc
= Product API
:toc: left

== Create Product

=== Valid Request
include::{snippets}/products-create/http-request.adoc[]

=== Validation Error

Request causing the error:
include::{snippets}/products-create-validation-error/http-request.adoc[]

Response:
include::{snippets}/products-create-validation-error/http-response.adoc[]

Fields in the error response:
include::{snippets}/products-create-validation-error/response-fields.adoc[]
```

You can create a dedicated "Error responses" section for clients to look up common errors. Do not include a body snippet unless `responseBody()` or the corresponding body snippet has been generated.

## 13. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Constraints do not run | Missing `@Valid` or validation provider | Enable validation and check controller signature |
| Malformed JSON skips validation handler | Deserialization fails before Bean Validation | Handle `HttpMessageNotReadableException` separately |
| Inconsistent error bodies | Each controller builds a different response | Standardize via `@RestControllerAdvice` |
| Test depends on fieldErrors ordering | Validator does not guarantee order | Use order-independent matchers |
| `responseFields(...)` reports extra field | Error DTO gained an undocumented field | Review and update descriptors |
| Error snippet misses nested fields | Descriptor paths do not cover nested error structure | Add paths like `fieldErrors[].field` |
| Using `responseBody()` expecting schema validation | Body snippet only renders a sample payload | Add `responseFields(...)` to verify contract |
| Handler catches all `Exception` as 400 | Conflates server errors with client errors | Handle exceptions by group and keep 5xx for server errors |
| Standalone test skips controller advice | Advice not registered with MockMvc | Use context tests or `.setControllerAdvice(...)` |
| Changing error message breaks tests | Assertions lock onto unstable message strings | Prefer checking code, status, and field paths |
| Asciidoctor include missing file | Test did not generate snippet or wrong operation ID | Check `document(...)` and task dependencies |

## 14. Build and CI

With Gradle and the Asciidoctor plugin configured, the docs task must run after snippet-generating tests:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
}
```

CI workflow:

```text
Negative HTTP tests
        |
        +--> Bean Validation errors
        |
        +--> JSON binding errors
        |
        +--> Domain/business errors
        |
        v
Assert status + error code + field paths
        |
        v
Spring REST Docs response snippets
        |
        v
Asciidoctor / Markdown export step
        |
        v
Verify includes and publish
```

CI should run at least one test for each published error category. If the error DTO or exception handler changes, strict `responseFields(...)` helps catch newly added undocumented fields. When only wording in a message changes, tests should avoid depending on strings outside the stable contract.

Spring REST Docs typically outputs AsciiDoc. If a project exports Markdown, a separate template or conversion step is required; `.md` snippet files are not produced by default.

## 15. Hands-On Exercise

For the `POST /api/products` endpoint:

1. Create a DTO with `@NotBlank`, `@Positive`, and `@Email`.
2. Enable validation and add `@Valid` to `@RequestBody`.
3. Create `ApiError` along with `FieldErrorDetail`.
4. Write a handler for `MethodArgumentNotValidException`.
5. Write separate handlers for JSON parse errors and domain conflicts.
6. Create MockMvc negative tests for blank name, negative price, and invalid email.
7. Assert HTTP status, error code, and the list of field errors.
8. Use `responseFields(...)` to document the error contract.
9. Add `responseBody()` if you want to include the raw error payload.
10. Create separate operation IDs for validation, invalid JSON, and conflict.
11. Include snippets in an Error responses section.
12. Run tests and Asciidoctor in CI; confirm that new undocumented error response fields fail the test.

### Self-Assessment Questions

- Which step in request processing does `@Valid` trigger?
- How does `MethodArgumentNotValidException` differ from `HttpMessageNotReadableException`?
- Why should error codes be more stable than messages?
- When should status 400 be used versus 409?
- What does `responseFields(...)` validate in an error payload?
- How does `responseBody()` differ in purpose from `responseFields(...)`?
- How can you test field errors without depending on ordering?
- Why should you avoid mapping every exception to 400?
- When an error DTO gains a new field, how does strict REST Docs help catch it?

**Remember:** Validation tests must check both status and error contract. Use `@Valid` for DTO constraints, `@RestControllerAdvice` to standardize responses, negative tests to confirm behavior, and `responseFields(...)` to verify error payloads are completely documented. Distinguish parse/binding errors, Bean Validation errors, and domain errors so clients can handle each properly.

## References

- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): integrating Jakarta Bean Validation.
- [Spring Framework — `@ExceptionHandler`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html): handling exceptions in Spring MVC.
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): `responseFields`, `responseBody`, and payload snippets.
- [Spring REST Docs — HTTP Headers](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/http-headers.html): documenting response headers.
