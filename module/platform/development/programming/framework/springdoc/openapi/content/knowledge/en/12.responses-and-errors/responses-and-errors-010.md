# @ControllerAdvice, @ExceptionHandler, and Error Inference Limits

## 1. Why Is Error Handling Part of the API Contract?

An API does not describe only data when a request succeeds. Clients also need to know how the server responds when a resource does not exist, input data is invalid, the caller is unauthenticated, or a business rule is violated.

If every controller handles errors in its own way, responses can become inconsistent: one endpoint returns a plain string, another returns a JSON object, one uses status 400 while another uses 422 for the same kind of error. Clients end up writing many handling branches and struggling to distinguish business errors from system errors.

Spring Boot provides centralized exception handling via **@ControllerAdvice** and **@ExceptionHandler**. Springdoc OpenAPI can use metadata from these handlers to document error responses in the specification. However, source code can throw many exceptions from services, repositories, security filters, or data conversion layers; not every error branch can be inferred accurately from controller signatures alone.

Three pieces must work together:

- **Runtime exception handling** decides which exceptions are caught and what actual HTTP response is returned.
- **OpenAPI response description** documents status codes, headers, media types, and error schemas for clients.
- **Integration/contract testing** verifies that the documentation matches application behavior.

The goal is to advertise the errors clients can encounter, with a stable structure and meaningful status codes.

## 2. Exception Handling Flow in Spring MVC

A request can fail at multiple stages:

1. Spring receives the request and locates the matching handler.
2. HttpMessageConverter/Jackson reads the body and converts JSON into Java objects.
3. Bean Validation checks DTOs or parameters.
4. The controller invokes services and business components.
5. Exceptions may originate from controllers, services, repositories, or the security layer.
6. Spring looks for a matching exception handler.
7. The handler constructs a response containing status, headers, and body.
8. The client receives the response under the HTTP contract.

For example, malformed JSON can raise **HttpMessageNotReadableException** before the controller method is invoked. A request body that deserializes cleanly yet violates @NotBlank can raise **MethodArgumentNotValidException**. A service failing to find a product can throw **ProductNotFoundException**. These three cases come from different sources, yet all can be mapped into structured error responses.

Springdoc does not execute requests through these steps to discover every error. The library builds the OpenAPI document from observable application metadata, annotations, and configuration. Therefore, declaring exception handlers and response metadata explicitly is essential.

## 3. @ControllerAdvice and @RestControllerAdvice

**@ControllerAdvice** applies shared handling logic across multiple controllers. It is commonly used for centralized exception handling, data binding, or model attributes.

**@RestControllerAdvice** is a variant combining @ControllerAdvice and @ResponseBody. Return values from its handlers are written to the response body via message converters, fitting REST APIs that return JSON.

Example:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {
    // Shared @ExceptionHandler methods
}
~~~

If using @ControllerAdvice in a REST application, handlers can return ResponseEntity or add @ResponseBody so bodies are serialized. For REST APIs, @RestControllerAdvice usually makes intent clearer.

You can narrow an advice's scope by package, annotation, or controller type. For instance, an advice might apply only to controllers in package api.admin. This runtime scope must also be considered when documenting shared responses in OpenAPI.

## 4. @ExceptionHandler Maps Exceptions to Responses

The **@ExceptionHandler** annotation designates a method to handle one or more exception types. Spring resolves the matching handler when an exception occurs within its scope.

Example:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    public ResponseEntity<ApiError> handleProductNotFound(
        ProductNotFoundException exception
    ) {
        ApiError body = new ApiError(
            "PRODUCT_NOT_FOUND",
            "Product not found"
        );

        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(body);
    }
}
~~~

The method above turns ProductNotFoundException into HTTP 404 with an ApiError body. Handlers can accept the exception, WebRequest, HttpServletRequest, or other supported arguments depending on the scenario.

A single handler can cover multiple exception types:

~~~java
@ExceptionHandler({
    InvalidOrderException.class,
    OrderStateConflictException.class
})
public ResponseEntity<ApiError> handleOrderErrors(RuntimeException exception) {
    ApiError body = new ApiError(
        "ORDER_INVALID",
        "Request is incompatible with the order state"
    );

    return ResponseEntity.unprocessableEntity().body(body);
}
~~~

When grouping multiple exceptions into one handler, ensure they truly share the same HTTP semantics and error structure. If an error category needs a different status or error code, split the handler so the contract stays unambiguous.

## 5. @ResponseStatus and ResponseEntity

Spring offers two common ways to determine an error response's status.

### 5.1. Using @ResponseStatus

You can place @ResponseStatus on an exception class:

~~~java
@ResponseStatus(HttpStatus.NOT_FOUND)
public class ProductNotFoundException extends RuntimeException {
    public ProductNotFoundException(Long id) {
        super("Product not found: " + id);
    }
}
~~~

When the exception is thrown and not overridden by another handler, Spring maps it to status 404. The reason attribute can provide a reason phrase, though for REST APIs avoid exposing internal details or sensitive data in reason.

You can also place @ResponseStatus on an @ExceptionHandler method:

~~~java
@ExceptionHandler(ProductNotFoundException.class)
@ResponseStatus(HttpStatus.NOT_FOUND)
public ApiError handle(ProductNotFoundException exception) {
    return new ApiError("PRODUCT_NOT_FOUND", "Product not found");
}
~~~

With @RestControllerAdvice, ApiError is serialized into the response body.

### 5.2. Using ResponseEntity

ResponseEntity fits when status or headers depend on runtime data and processing logic:

~~~java
@ExceptionHandler(ProductNotFoundException.class)
public ResponseEntity<ApiError> handle(ProductNotFoundException exception) {
    ApiError body = new ApiError(
        "PRODUCT_NOT_FOUND",
        "Product not found"
    );

    return ResponseEntity
        .status(HttpStatus.NOT_FOUND)
        .header("X-Error-Code", "PRODUCT_NOT_FOUND")
        .body(body);
}
~~~

ResponseEntity lets you control status, headers, and body in one return value. Regardless of which mechanism you choose, OpenAPI responses must describe the actual status and payload.

Do not assume @ResponseStatus or @ExceptionHandler automatically generates complete error schemas in every Springdoc version or configuration. Verify the generated document and add @ApiResponse where needed.

## 6. Designing a Standardized Error Response

An API can standardize errors with a shared DTO:

~~~java
public record ApiError(
    String code,
    String message,
    String path
) {}
~~~

JSON example:

~~~json
{
  "code": "PRODUCT_NOT_FOUND",
  "message": "Product not found",
  "path": "/api/products/42"
}
~~~

Commonly useful fields:

| Field | Purpose |
|---|---|
| code | Stable error code for programmatic client handling |
| message | Clear message for users or developers |
| path | Request path where the error occurred |
| timestamp | Time the error was recorded if needed for correlation |
| traceId | Correlation ID for tracing logs across services |
| violations | Field-level validation error list |

You do not have to include every field in every response. Choose a structure matching client needs and data policies. Error codes should remain more stable than messages, because messages may be reworded, localized, or adjusted over time.

Avoid returning stack traces, SQL, table names, internal file paths, tokens, or configuration details in public responses. Full technical details belong in access-controlled logs; responses should contain only what clients need to understand and handle the error.

## 7. Using ProblemDetail When Supported by the Application

Spring Framework 6 provides **ProblemDetail** to represent errors following Problem Details for HTTP APIs. Spring Boot 3 can use this type in REST exception handling.

Example:

~~~java
@ExceptionHandler(ProductNotFoundException.class)
public ResponseEntity<ProblemDetail> handleNotFound(
    ProductNotFoundException exception
) {
    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.NOT_FOUND,
        "Requested product was not found"
    );

    problem.setTitle("Product not found");
    problem.setProperty("code", "PRODUCT_NOT_FOUND");

    return ResponseEntity.status(HttpStatus.NOT_FOUND).body(problem);
}
~~~

ProblemDetail provides standard properties such as type, title, status, detail, and instance; applications can add extension properties such as code. Springdoc can document this type depending on version and configuration. If you need a stable client contract, inspect the actual serialized JSON and generated schema, especially when adding custom properties.

Do not mix ProblemDetail at runtime with a different ApiError schema in documentation if runtime only returns one of them. Pick a consistent structure or explicitly document each media type/response variant if multiple formats genuinely exist.

## 8. Declaring Error Responses Explicitly with @ApiResponse

The **@ApiResponse** annotation belongs to OpenAPI annotations and describes one response of an operation. Key attributes include:

- **responseCode**: HTTP status code or default.
- **description**: meaning of the response.
- **content**: media type and body schema.
- **headers**: response headers clients need to know about.
- **links**: links to related operations if required by the contract.

Example:

~~~java
@GetMapping("/api/products/{id}")
@Operation(summary = "Get product by ID")
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Product found",
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = ProductResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "404",
        description = "Product not found",
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = ApiError.class)
        )
    )
})
public ProductResponse findById(@PathVariable Long id) {
    return productService.getByIdOrThrow(id);
}
~~~

This declaration documents the 200 success response and the 404 error. Controllers and services must still return those actual outcomes. Annotations do not alter exception-handling logic.

If a response has no body, declare description without content:

~~~java
@ApiResponse(
    responseCode = "204",
    description = "Resource deleted successfully"
)
~~~

Do not attach a body schema to 204 No Content if runtime sends no body.

## 9. Limits of Error Inference from @ControllerAdvice

Springdoc supports collecting response metadata from methods in @ControllerAdvice/@RestControllerAdvice. In supported versions, these responses can be added to multiple operations as **generic responses**. The springdoc.override-with-generic-response setting controls applying these generic responses; it is typically enabled by default in versions that support it, though you should verify the configuration and docs for your project's exact version.

This mechanism is helpful for errors that can genuinely occur across almost every endpoint, such as a common authentication error or a standardized system error. However, it has significant limitations:

- Springdoc does not analyze the entire call graph to know which endpoints can throw a given exception.
- A handler may apply only to a subset of controllers, while auto-inferred responses may appear more broadly than business scope intends depending on configuration.
- Exceptions can be thrown by services, repositories, filters, or external libraries without appearing in controller signatures.
- An exception may be handled across layers, where handler precedence and advice scope determine which handler runs.
- Status codes and bodies may depend on runtime conditions that cannot be deduced solely from exception types.
- A single handler may return different responses depending on the exception instance or request data.

For example, ProductNotFoundException can only occur on product lookup endpoints. If a 404 response from advice is added as a generic response to every operation, the documentation can mislead clients into thinking order creation, login, or report download can return that same 404. That produces redundant or misleading documentation.

Therefore, use generic responses only when an error truly applies broadly and fits the operation scope. For business-specific or endpoint-specific errors, declare responses on the relevant operations.

## 10. Controlling Generic Responses with springdoc.override-with-generic-response

In Springdoc versions supporting this property, you can disable overriding/adding generic responses from @ControllerAdvice:

~~~yaml
springdoc:
  override-with-generic-response: false
~~~

When disabled, the team declares needed responses directly on operations or through a clearly scoped OpenAPI customization mechanism. This is useful when an advice handles many distinct exceptions that do not apply to every endpoint.

If generic responses are enabled, inspect the OpenAPI JSON to see which responses are being added to operations. Never assume every response in an advice fits the entire API.

Property names, defaults, and exact behavior can vary across Springdoc releases. When upgrading, check the configuration reference for your dependency version. Changing this property affects documentation generation only; it does not alter how Spring handles exceptions at runtime.

## 11. When to Use Shared vs. Operation-Specific Responses?

Errors can be divided into categories to decide how to publish them:

| Error category | Examples | Appropriate documentation approach |
|---|---|---|
| Infrastructure or protocol errors occurring broadly | 401, 403, common auth errors, 500 | Shared responses if they genuinely apply to the relevant operations |
| Operation-specific business errors | 404 product, 409 duplicate order code, 422 invalid order state | Declare on operations that can raise the error |
| Validation errors for a specific request payload | 400 with DTO violations | Declare on operations accepting that DTO or sharing the same rules |
| Upload errors | 413 payload too large, 415 unsupported media type | Declare on upload endpoints or corresponding endpoint groups |
| Resource-permission-dependent errors | 403 or 404 depending on resource-hiding policy | Describe according to actual security policy and endpoints |

A shared response does not have to appear on every endpoint. If Spring Security protects specific paths, 401/403 responses apply only to those operations. If certain endpoints are public, do not include authentication responses as if login were required.

Good documentation reflects what clients can encounter within a given scope, not a dump of every exception class in the codebase.

## 12. Common Exceptions and How They Map

Common exceptions in Spring MVC:

| Exception/scenario | Cause | Typical response |
|---|---|---|
| MethodArgumentNotValidException | Request DTO violates Bean Validation | 400 Bad Request |
| HttpMessageNotReadableException | Malformed JSON, type mismatch, or unreadable body | 400 Bad Request |
| HandlerMethodValidationException | Handler method validation in supported Spring Framework versions | Usually 400 Bad Request |
| ConstraintViolationException | Constraint validation at method/service or other layers | Depends on origin and exception mapping |
| ProductNotFoundException | Resource not found | 404 Not Found |
| DuplicateResourceException | Data or identifier conflict | 409 Conflict |
| AccessDeniedException | Authenticated user lacks required permission | 403 Forbidden |
| AuthenticationException | Authentication failed or credentials missing | 401 Unauthorized per security entry point |
| ResponseStatusException | Application explicitly requests a specific status | Matches specified status |
| Unexpected Exception | Unhandled system error | Usually 500 Internal Server Error |

This table is only a guide. Actual statuses depend on exception handlers, Spring Security entry points, framework configuration, and API policy. For instance, ConstraintViolationException may map to 400, 422, or another response depending on where it arises and project conventions.

With Spring Framework 6.1+, controller method validation can raise HandlerMethodValidationException in some cases. Applications upgrading from older versions should verify the actual exception raised and update handlers accordingly.

## 13. Describing Validation Errors and JSON Parse Errors

Validation errors and parse errors often both return 400, yet they have different causes.

**Validation errors** occur after JSON is converted into a DTO—for example, blank name, negative price, or an oversized items list. The response can list errors by field:

~~~json
{
  "code": "VALIDATION_FAILED",
  "message": "Request contains invalid data",
  "violations": [
    {
      "field": "name",
      "message": "Product name must not be blank"
    },
    {
      "field": "price",
      "message": "Price must be greater than 0"
    }
  ]
}
~~~

**Parse/binding errors** occur when Jackson cannot read the body, such as invalid JSON syntax or a string that cannot be parsed as a number. The response can share the same ApiError schema with a different code:

~~~json
{
  "code": "INVALID_REQUEST_BODY",
  "message": "Invalid JSON content"
}
~~~

If both cases share the same response structure, you can reuse one schema with distinct error codes. If violations appears only on validation errors, mark that field optional or use dedicated schemas for each error category.

Never expose raw Jackson messages if they reveal parser internals, class names, or sensitive fragments. Standardize client-facing messages and log technical details internally.

## 14. Declaring Shared Responses via OpenAPI Configuration

When multiple operations genuinely share a response, you can configure OpenAPI metadata centrally. One way is declaring responses via annotations on operations; another is using a customizer to add responses under well-scoped rules.

Operation annotation example:

~~~java
@Operation(
    summary = "List products",
    responses = {
        @ApiResponse(
            responseCode = "400",
            description = "Invalid query parameters",
            content = @Content(
                schema = @Schema(implementation = ApiError.class)
            )
        ),
        @ApiResponse(
            responseCode = "500",
            description = "System error",
            content = @Content(
                schema = @Schema(implementation = ApiError.class)
            )
        )
    }
)
@GetMapping("/api/products")
public List<ProductResponse> findAll() {
    return productService.findAll();
}
~~~

When using OpenApiCustomizer, control which operations receive the added responses. Do not attach business-specific responses unconditionally to every operation merely to avoid repeating annotations. A customizer can filter by path, tag, or API group, provided that logic is reviewed whenever paths or tags change.

For shared response schemas, reuse a component schema:

~~~yaml
components:
  schemas:
    ApiError:
      type: object
      required:
        - code
        - message
      properties:
        code:
          type: string
          example: PRODUCT_NOT_FOUND
        message:
          type: string
          example: Product not found
        path:
          type: string
          example: /api/products/42
~~~

If response objects share the same structure and differ only by error code, one shared schema may fit well. If validation responses include violations or authentication responses include challenge headers, document those differences explicitly.

## 15. Response Headers and Media Types in Errors

An error response can include headers clients must process. For example, 401 may require WWW-Authenticate; 429 may include Retry-After; error responses may include a trace ID.

You can document headers in @ApiResponse:

~~~java
@ApiResponse(
    responseCode = "429",
    description = "Rate limit exceeded",
    headers = {
        @Header(
            name = "Retry-After",
            description = "Number of seconds to wait before retrying",
            schema = @Schema(type = "integer", format = "int32")
        ),
        @Header(
            name = "X-Trace-Id",
            description = "Correlation ID for log lookup",
            schema = @Schema(type = "string")
        )
    },
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = ApiError.class)
    )
)
~~~

The response body can be application/json or application/problem+json if the API uses Problem Details. The media type must match the actual response. Merely declaring a media type in OpenAPI does not make Spring serialize that format; configure the matching converter and handler.

For 401, authentication schemes may also require the WWW-Authenticate header. Check the security entry point and actual runtime responses, because that header may be produced by Spring Security rather than a controller advice @ExceptionHandler.

## 16. Security and Scope of Error Information

Error responses should help clients fix requests without leaking internal details. Follow these practices:

- Return stable error codes and messages suited for the audience.
- Never return stack traces or exception class names in public APIs.
- Never put SQL, internal paths, tokens, session IDs, or personal data in messages.
- Use traceId/correlationId for operations teams to look up logs.
- Avoid revealing whether a resource exists when security policy requires hiding it.
- Align response details with the system's 401/403/404 policies.

Some systems intentionally return 404 instead of 403 to avoid disclosing resource existence. This is a security and business decision; OpenAPI must reflect the public behavior clients actually observe.

Do not document detailed internal errors if the server intentionally hides them. For example, a schema can expose generic code and message fields without enumerating table names or internal conditions.

## 17. Testing Exception Handlers and OpenAPI Contracts

To verify error responses, test both runtime behavior and the generated documentation.

**Runtime testing:**

- Send malformed JSON.
- Send a DTO missing required fields or violating constraints.
- Call an endpoint with a nonexistent ID.
- Send a request triggering a business conflict.
- Call an endpoint without a token or without sufficient permissions.
- Trigger a controlled system failure.
- Verify status, Content-Type, headers, and body.

**OpenAPI inspection:**

1. Download /v3/api-docs or the corresponding group document.
2. Verify each operation lists the expected response codes.
3. Verify error body schemas match runtime JSON.
4. Verify bodyless responses do not declare invalid content.
5. Check response headers such as Retry-After, Location, or WWW-Authenticate when applicable.
6. Confirm generic responses from @ControllerAdvice are scoped properly.
7. Confirm error responses do not appear superfluously on unrelated endpoints.
8. Diff docs across versions to catch client-breaking changes.

An integration test can use MockMvc:

~~~java
mockMvc.perform(get("/api/products/{id}", 9999))
    .andExpect(status().isNotFound())
    .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.code").value("PRODUCT_NOT_FOUND"));
~~~

This test verifies HTTP behavior. Add tests reading the OpenAPI document or checking the generated JSON file to confirm the 404 response is documented with the ApiError schema.

## 18. Common Pitfalls When Using @ControllerAdvice with Springdoc

| Symptom | Cause to check |
|---|---|
| Error response missing from Swagger UI | Handler not recognized by Springdoc, missing @ApiResponse, or generic responses disabled |
| One error response appears on every endpoint | Generic responses from @ControllerAdvice applied more broadly than business scope |
| Docs list 404 while runtime returns 200 | Annotation metadata mismatches controller/service logic |
| Response body shows an empty schema | Handler return type too broad, generic type erased, or missing schema implementation |
| Response code exists without content | Media type/schema not documented or actual response has no body |
| Validation errors missing from docs | 400 response not declared or automatic inference misses the actual exception |
| JSON parse error confused with validation | Not distinguishing HttpMessageNotReadableException from MethodArgumentNotValidException |
| 401 response missing header | Header generated in Spring Security entry point but not documented |
| Handler returns ProblemDetail while docs show another DTO | Schema override or model resolver does not reflect runtime serializer |
| Duplicate or conflicting response descriptions | Generic response and operation-level @ApiResponse declare conflicting metadata |

When troubleshooting, inspect the OpenAPI JSON first to see whether a response came from operation annotations, controller advice, or a customizer. Then call the endpoint to verify the actual status and body. Never fix docs solely by eyeballing the Swagger UI interface.

## 19. Workflow for Building a Consistent Error Contract

A practical workflow for a Spring Boot application includes:

1. Identify the error groups clients must handle: validation, not found, conflict, authentication, authorization, and server errors.
2. Choose a stable error response structure or ProblemDetail per application policy.
3. Create exception classes and @RestControllerAdvice to map exceptions to status, headers, and body.
4. Add handlers for Jackson, Bean Validation, and method validation matching your Spring version.
5. Declare @ApiResponse for errors per operation; use generic responses only for truly global errors.
6. Decide whether to enable springdoc.override-with-generic-response based on advice scope and generated docs.
7. Inspect /v3/api-docs to remove redundant responses or broken schemas.
8. Write integration tests for key error scenarios.
9. Include OpenAPI inspection and contract diffs in the review/release process.

There is no need to list every internal exception that clients cannot or should not handle. Focus on HTTP outcomes that are meaningful in the public contract.

## 20. Guidelines for Using @ControllerAdvice and @ExceptionHandler

When combining exception handling with Springdoc OpenAPI, follow these principles:

1. Use @RestControllerAdvice to standardize error responses for REST APIs.
2. Use @ExceptionHandler to map each exception group to the appropriate status and body.
3. Use @ResponseStatus or ResponseEntity to drive the actual HTTP response.
4. Use @ApiResponse/@ApiResponses to publish status, content, schema, and headers to clients.
5. Distinguish shared responses from responses raised only by specific operations.
6. Understand the limits of generic responses from @ControllerAdvice and the springdoc.override-with-generic-response setting.
7. Never assume Springdoc can analyze every exception thrown from services, repositories, or filters.
8. Standardize error codes and avoid leaking internal information.
9. Verify the OpenAPI document alongside runtime responses and integration tests.

@ControllerAdvice and @ExceptionHandler decide how the application handles exceptions; Springdoc uses observable metadata to describe responses in the contract. Because an exception handler alone cannot tell which endpoints can raise an error, teams must explicitly decide which errors are global versus operation-specific and verify the generated documentation. Doing so ensures clients understand status codes, error structures, and how to recover from failed requests.

