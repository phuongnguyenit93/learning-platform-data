# Standardizing Errors with Custom DTOs or ProblemDetail

A good API clearly describes both successful outcomes and situations where a request cannot be completed. When every controller returns errors in a different structure, clients must write many handling branches and struggle to distinguish business errors from technical failures. A unified error contract enables automated client handling, improves system observability, and makes OpenAPI documentation easier to use.

In Spring Boot, there are two common approaches to standardizing error responses:

- **Application-specific error DTO:** a custom-designed structure with fields such as error code, message, path, correlation ID, and validation error list.
- **ProblemDetail:** Spring Framework's standard model based on RFC 9457 for representing HTTP error details.

springdoc-openapi can document both approaches using schemas, examples, and `@ApiResponse` annotations. Which approach to choose depends on existing contracts, compatibility requirements, and how closely you want to follow HTTP standards. Either way, the JSON structure, HTTP status, and OpenAPI documentation must align with actual application behavior.

## 1. Why Do We Need a Standardized Error Format?

Suppose the same API has three endpoints returning errors in three different shapes:

~~~json
{
  "message": "Product not found"
}
~~~

~~~json
{
  "error": "PRODUCT_NOT_FOUND",
  "description": "Product does not exist"
}
~~~

~~~json
{
  "status": 400,
  "errors": [
    {
      "field": "price",
      "message": "Price must be greater than 0"
    }
  ]
}
~~~

Clients have to check multiple field names and structures. Logging, displaying messages to users, or automating retries also becomes complicated.

A consistent error contract brings several benefits:

- Clients can use a single shared handler for most errors.
- Machine-readable error codes let clients distinguish business errors without parsing prose messages.
- Validation errors can pinpoint the exact field and violated rule.
- Trace IDs or correlation IDs link responses to server logs and traces.
- OpenAPI can reuse one error schema across many operations.
- Development teams can test more easily and catch runtime drift from the contract.

A uniform format does not mean every error shares the same HTTP status. 400, 401, 403, 404, 409, and 500 still express different situations; only the body structure needs to remain consistent.

## 2. Two Options: Custom Error DTO and ProblemDetail

| Criterion | Custom error DTO | ProblemDetail |
|---|---|---|
| Structure | Designed by the application | Follows RFC 9457 |
| Field names | Chosen freely, e.g., code, message, violations | Standard members such as type, title, status, detail, instance |
| Extensibility | Add fields per application contract | Add extension members |
| Spring MVC integration | Uses @RestControllerAdvice and ResponseEntity | Directly supported by Spring Framework |
| Media type | Usually application/json | application/problem+json |
| Best suited for | APIs with an existing error format or specialized structure | New APIs or teams wanting a standard HTTP error format |

A custom DTO can be the right choice when a system already has an error contract consumed by many clients. ProblemDetail fits well when you want a standardized format whose members carry clear, interoperable semantics across systems.

Do not publish an arbitrary custom DTO under the application/problem+json media type and treat it as Problem Details. If you select that media type, the body must follow the structure and semantics of RFC 9457. If the body uses a custom shape such as {code, message, path}, use application/json or a designated custom media type.

## 3. ProblemDetail and RFC 9457

RFC 9457 defines the Problem Details for HTTP APIs format. It is the current standard superseding RFC 7807. Spring Framework 6 provides org.springframework.http.ProblemDetail to represent responses under this standard.

A Problem Detail can include these standard members:

| Member | Typical type | Meaning |
|---|---|---|
| type | URI reference | Identifies the problem type; defaults to about:blank if omitted |
| title | String | Short, stable summary of the problem type |
| status | Integer | HTTP status corresponding to the problem |
| detail | String | Specific explanation for this occurrence of the error |
| instance | URI reference | Identifies the specific occurrence of the problem |

Beyond the standard members, the server can add extension members such as code, traceId, or violations. Extensions should have consistent names and data types.

Example:

~~~json
{
  "type": "https://api.example.com/problems/product-not-found",
  "title": "Product not found",
  "status": 404,
  "detail": "Product with ID 42 was not found.",
  "instance": "/api/v1/products/42",
  "code": "PRODUCT_NOT_FOUND",
  "traceId": "8f3a1b7c2d"
}
~~~

type should be a stable URI so clients can identify the error category. That URI can point to documentation explaining causes and remedies. title should stay stable for the problem type; detail can vary per specific occurrence. status in the body must match the actual HTTP status on the response.

In this example, instance uses the request path to locate the failing request. If you need a unique identifier per occurrence, you can use a dedicated occurrence URI or include a stable request ID/trace ID; do not use instance as an error-type code.

Never put stack traces, SQL statements, internal hostnames, tokens, credentials, or sensitive personal data in detail or extension members.

## 4. Designing a Custom Error DTO

If the application needs a custom structure, define a clear, stable DTO. Example:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.List;

@Schema(name = "ApiErrorResponse", description = "Unified API error structure.")
public record ApiErrorResponse(
    @Schema(description = "UTC timestamp when the error occurred.",
            example = "2026-11-20T10:30:00Z")
    Instant timestamp,

    @Schema(description = "Returned HTTP status.", example = "404")
    int status,

    @Schema(description = "Stable error code for client handling.",
            example = "PRODUCT_NOT_FOUND")
    String code,

    @Schema(description = "Safe message intended for clients.",
            example = "Requested product was not found.")
    String message,

    @Schema(description = "Request path that caused the error.",
            example = "/api/v1/products/42")
    String path,

    @Schema(description = "Correlation ID for log lookup.",
            example = "8f3a1b7c2d")
    String traceId,

    List<FieldViolation> violations
) {
    public record FieldViolation(
        @Schema(example = "price")
        String field,

        @Schema(example = "Price must be greater than 0.")
        String message
    ) {
    }
}
~~~

Each field has a distinct responsibility:

- status reports the HTTP code, while the HTTP status line remains the primary protocol status source.
- code is machine-readable and should remain stable across versions.
- message is safe text for display or logging on the client; do not use it as a branching key.
- path identifies the related endpoint.
- traceId helps operations locate corresponding logs.
- violations lists field-level errors when a request fails validation.

When a response has no field errors, you can return an empty list instead of null to simplify client handling. Keep this convention consistent across the entire API.

## 5. Building Centralized Error Responses with @RestControllerAdvice

@RestControllerAdvice gathers exception-handling methods into one place. This annotation combines @ControllerAdvice and @ResponseBody, so returned objects are written directly to the response body.

Example handling product-not-found and validation errors:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.slf4j.MDC;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.time.Instant;
import java.util.List;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    public ResponseEntity<ApiErrorResponse> handleProductNotFound(
            ProductNotFoundException ex,
            HttpServletRequest request) {

        var body = new ApiErrorResponse(
            Instant.now(),
            HttpStatus.NOT_FOUND.value(),
            "PRODUCT_NOT_FOUND",
            "Requested product was not found.",
            request.getRequestURI(),
            MDC.get("traceId"),
            List.of()
        );

        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(body);
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiErrorResponse> handleValidation(
            MethodArgumentNotValidException ex,
            HttpServletRequest request) {

        List<ApiErrorResponse.FieldViolation> violations =
            ex.getBindingResult().getFieldErrors().stream()
                .map(error -> new ApiErrorResponse.FieldViolation(
                    error.getField(),
                    error.getDefaultMessage()
                ))
                .toList();

        var body = new ApiErrorResponse(
            Instant.now(),
            HttpStatus.BAD_REQUEST.value(),
            "VALIDATION_FAILED",
            "Invalid request data.",
            request.getRequestURI(),
            MDC.get("traceId"),
            violations
        );

        return ResponseEntity.badRequest().body(body);
    }
}
~~~

The example assumes the application defines ProductNotFoundException, ApiErrorResponse, and an MDC configuration populating traceId in the logging context. If no trace ID is present, you can return null, omit the field, or generate a correlation ID according to your shared convention.

MethodArgumentNotValidException typically occurs when a @RequestBody parameter annotated with @Valid violates Bean Validation constraints. If the application uses @Validated for method validation, some errors may pass through a different exception type; handle them according to your Spring version and method-validation configuration.

Do not return error.getDefaultMessage() verbatim if a message could contain internal details or unvalidated text. For public APIs, use standardized messages that can be localized.

## 6. Mapping Business Errors to HTTP Statuses and Error Codes

Each error category should have an appropriate HTTP status and machine-readable error code. Example:

| HTTP status | Example error code | Scenario |
|---|---|---|
| 400 Bad Request | VALIDATION_FAILED | Malformed body or validation violation |
| 401 Unauthorized | AUTHENTICATION_REQUIRED | Missing or invalid credentials |
| 403 Forbidden | ACCESS_DENIED | Authenticated but lacking permission |
| 404 Not Found | PRODUCT_NOT_FOUND | Resource not found |
| 409 Conflict | ORDER_STATE_CONFLICT | Current state prevents the operation |
| 415 Unsupported Media Type | UNSUPPORTED_MEDIA_TYPE | Content-Type not supported by the endpoint |
| 429 Too Many Requests | RATE_LIMIT_EXCEEDED | Request rate limit exceeded |
| 500 Internal Server Error | INTERNAL_ERROR | Unexpected server failure |

These are example conventions, not a mandatory list for every API. Choose statuses based on error semantics and keep them consistent across endpoints. 401 and 403 are not interchangeable; 409 fits conflicts with resource state; 500 should never mask known validation or business errors.

code should remain stable and language-independent. message can be translated or reworded without breaking client logic. Avoid forcing clients to compare exact message strings to decide control flow.

## 7. Using ProblemDetail in Spring Framework

Spring Framework 6 provides ProblemDetail in package org.springframework.http. You can instantiate it with forStatus or forStatusAndDetail, then attach standard fields and extension members.

Example:

~~~java
import org.slf4j.MDC;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import jakarta.servlet.http.HttpServletRequest;
import java.net.URI;

@RestControllerAdvice
public class ProblemExceptionHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    public ProblemDetail handleProductNotFound(
            ProductNotFoundException ex,
            HttpServletRequest request) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND,
            "Requested product was not found."
        );

        problem.setType(URI.create(
            "https://api.example.com/problems/product-not-found"
        ));
        problem.setTitle("Product not found");
        problem.setInstance(URI.create(request.getRequestURI()));
        problem.setProperty("code", "PRODUCT_NOT_FOUND");
        problem.setProperty("traceId", MDC.get("traceId"));

        return problem;
    }
}
~~~

When Spring MVC writes a ProblemDetail, the framework supports media type application/problem+json and uses the status set on the object for the HTTP response. Inspect the actual response in your running Spring version.

ProblemDetail supports extensions via setProperty. Spring/Jackson supports serializing extension properties as top-level JSON members rather than nesting them under a properties object. For example, code and traceId appear at the same level as type, title, status, detail, and instance.

## 8. Enabling Problem Details Support in Spring Boot

Spring Boot 3 with Spring MVC can enable Problem Details support for HTTP errors handled by the framework via configuration:

~~~yaml
spring:
  mvc:
    problemdetails:
      enabled: true
~~~

When enabled, Spring Boot registers Problem Details handling for certain standard Spring MVC exceptions. This setting does not automatically convert all custom application exceptions into ProblemDetail. For domain exceptions such as ProductNotFoundException, you still need an @ExceptionHandler or equivalent handling.

To customize how standard MVC exceptions are handled, extend ResponseEntityExceptionHandler in a @ControllerAdvice class and override the relevant methods, such as unreadable-body or validation handling. Check method signatures for your Spring Framework version, as some signatures may vary across releases.

Authentication and authorization errors can occur in the Spring Security filter chain before requests reach a controller. Consequently, @RestControllerAdvice will not necessarily catch all 401 and 403 errors. Configure AuthenticationEntryPoint and AccessDeniedHandler to return the same error format as the rest of the API.

## 9. Comparing the Two Response Examples

### 9.1. Custom DTO

~~~json
{
  "timestamp": "2026-11-20T10:30:00Z",
  "status": 404,
  "code": "PRODUCT_NOT_FOUND",
  "message": "Requested product was not found.",
  "path": "/api/v1/products/42",
  "traceId": "8f3a1b7c2d",
  "violations": []
}
~~~

This is an application-defined structure. Clients can rely on code, status, and violations. When using this structure, the media type is usually application/json.

### 9.2. ProblemDetail

~~~json
{
  "type": "https://api.example.com/problems/product-not-found",
  "title": "Product not found",
  "status": 404,
  "detail": "Product with ID 42 was not found.",
  "instance": "/api/v1/products/42",
  "code": "PRODUCT_NOT_FOUND",
  "traceId": "8f3a1b7c2d"
}
~~~

This is Problem Details with two extension members, code and traceId. The response should use application/problem+json. Standard members follow RFC 9457 semantics; extensions add application-specific data.

## 10. Describing Error DTOs with OpenAPI and springdoc

If a controller returns errors using a custom DTO, declare responses via @ApiResponse:

~~~java
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

@PostMapping
@Operation(summary = "Create product")
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Product created."
    ),
    @ApiResponse(
        responseCode = "400",
        description = "Invalid request.",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ApiErrorResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "409",
        description = "Product code already exists.",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ApiErrorResponse.class)
        )
    )
})
public ResponseEntity<ProductResponse> create(
        @Valid @RequestBody CreateProductRequest request) {
    // ...
}
~~~

For errors with JSON examples, add @ExampleObject inside @Content so integrators can see concrete payloads. You can reuse the same schema across multiple statuses, provided each description explains the condition triggering that error.

## 11. Describing ProblemDetail in OpenAPI

When using ProblemDetail, declare the application/problem+json media type along with a schema and example:

~~~java
@ApiResponse(
    responseCode = "404",
    description = "Product not found.",
    content = @Content(
        mediaType = "application/problem+json",
        schema = @Schema(implementation = ProblemDetail.class),
        examples = @ExampleObject(
            name = "product-not-found",
            value = """
                {
                  "type": "https://api.example.com/problems/product-not-found",
                  "title": "Product not found",
                  "status": 404,
                  "detail": "Product with ID 42 was not found.",
                  "instance": "/api/v1/products/42",
                  "code": "PRODUCT_NOT_FOUND",
                  "traceId": "8f3a1b7c2d"
                }
                """
        )
    )
)
~~~

The ProblemDetail schema reflects standard members. Extensions added dynamically via setProperty may not appear fully in the auto-generated schema. If clients need to know extensions such as code, traceId, or violations, describe them in a dedicated component schema, use that schema in @ApiResponse, and keep examples aligned with runtime JSON.

Example documentation schema for a Problem Detail with extensions:

~~~yaml
ApiProblem:
  type: object
  properties:
    type:
      type: string
      format: uri
    title:
      type: string
    status:
      type: integer
      format: int32
    detail:
      type: string
    instance:
      type: string
      format: uri-reference
    code:
      type: string
    traceId:
      type: string
~~~

Not all standard members have to appear in every Problem Detail; mark fields required only when the API genuinely guarantees their presence. Extensions should also have stable types and semantics.

## 12. Reusing Error Responses Across Operations

If all endpoints share the same error structure, avoid repeating long annotations on every controller without a convention. Responses can be reused by:

- Creating composite annotations containing common @ApiResponse declarations.
- Declaring reusable responses in OpenAPI components and referencing them with $ref.
- Using OpenApiCustomizer to add shared responses according to project rules.

Reusable response example in YAML:

~~~yaml
components:
  responses:
    ValidationError:
      description: Request failed data validation.
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ApiProblem'
    InternalError:
      description: Server encountered an unexpected error.
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ApiProblem'
paths:
  /api/v1/products:
    post:
      responses:
        '400':
          $ref: '#/components/responses/ValidationError'
        '500':
          $ref: '#/components/responses/InternalError'
~~~

Having a @RestControllerAdvice that handles exceptions at runtime does not guarantee every operation in the OpenAPI docs automatically lists all corresponding responses. Inspect /v3/api-docs; if global responses are missing, add them via annotations, reusable responses, or customizers.

## 13. Describing Field-Level Validation Errors

Validation errors typically require more detail than a generic message. Clients need to know which field failed and which constraint was violated.

Error DTO example:

~~~java
public record ValidationViolation(
    String field,
    String code,
    String message,
    Object rejectedValue
) {
}
~~~

Sample response:

~~~json
{
  "code": "VALIDATION_FAILED",
  "message": "Invalid request data.",
  "violations": [
    {
      "field": "email",
      "code": "Email",
      "message": "Invalid email format."
    },
    {
      "field": "quantity",
      "code": "Positive",
      "message": "Quantity must be greater than 0."
    }
  ]
}
~~~

rejectedValue can be helpful in internal systems, but think carefully before exposing it externally. Rejected values may contain passwords, tokens, personal data, or sensitive information. For public APIs, field name, rule code, and a safe message are usually sufficient.

For nested DTOs or collections, field names can include paths such as items[0].quantity. Standardize path formatting so clients can map errors back to input fields.

## 14. Handling Unexpected Errors and Protecting Internal Details

A catch-all exception handler can intercept unexpected exceptions and return 500 Internal Server Error with a generic error code:

~~~java
@ExceptionHandler(Exception.class)
public ResponseEntity<ApiErrorResponse> handleUnexpected(
        Exception ex,
        HttpServletRequest request) {

    log.error("Unexpected API error at {}", request.getRequestURI(), ex);

    var body = new ApiErrorResponse(
        Instant.now(),
        HttpStatus.INTERNAL_SERVER_ERROR.value(),
        "INTERNAL_ERROR",
        "An error occurred while processing the request.",
        request.getRequestURI(),
        MDC.get("traceId"),
        List.of()
    );

    return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(body);
}
~~~

Internal logs can capture stack traces for investigation. Responses sent to clients should only contain enough detail to recognize the error and contact support. Never return ex.getMessage() by default, as exception messages can expose SQL queries, file paths, class names, or sensitive data.

Order the catch-all handler after specific handlers by design and avoid catching overly broad exceptions and turning everything into 500. Known HTTP errors must preserve their proper status and error codes.

## 15. Localizing Error Messages

Error codes should be stable and language-independent. Messages can be localized according to the client's locale:

~~~json
{
  "code": "VALIDATION_FAILED",
  "message": "Invalid request data.",
  "violations": [
    {
      "field": "email",
      "code": "Email",
      "message": "Invalid email format."
    }
  ]
}
~~~

Spring supports MessageSource and LocaleResolver for resolving messages by locale. With Bean Validation, message keys can be placed in annotations and resolved from resource bundles. If the API supports Accept-Language, define the default language and how unsupported locales are handled.

Clients should rely on code for programmatic logic and use message for display. Never use translated text as an identifier.

## 16. Testing the Error Contract

Tests should verify HTTP status, media type, and JSON content. Example with a custom DTO:

~~~java
mockMvc.perform(post("/api/v1/products")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {
              "name": "",
              "price": -1
            }
            """))
    .andExpect(status().isBadRequest())
    .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
    .andExpect(jsonPath("$.violations").isArray());
~~~

With ProblemDetail:

~~~java
mockMvc.perform(get("/api/v1/products/42"))
    .andExpect(status().isNotFound())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.valueOf("application/problem+json")
    ))
    .andExpect(jsonPath("$.type").value(
        "https://api.example.com/problems/product-not-found"
    ))
    .andExpect(jsonPath("$.status").value(404))
    .andExpect(jsonPath("$.code").value("PRODUCT_NOT_FOUND"));
~~~

These are illustrative test snippets; replace endpoints, payloads, and error codes to match your application. Beyond runtime tests, inspect OpenAPI JSON to verify:

1. Operations declare the error responses the API can actually return.
2. Each response has the right media type.
3. Schemas and examples match runtime bodies.
4. The HTTP status in the response body matches the status line.
5. Important extension members are documented in the schema.
6. Authentication/authorization errors from Spring Security follow the same contract.

## 17. Evolving Error Contracts Without Breaking Clients

The error format is part of the API contract. Once clients rely on it, changing field names, data types, or error code semantics can introduce breaking changes.

Safe evolution practices:

- Keep published error codes unchanged; add new codes for new error categories.
- Optional fields can be added if clients are built to ignore unknown fields.
- Never change status from a number to a string.
- Never change the media type without assessing client impact.
- Never turn detail or message prose into logic keys.
- When making major structural changes, consider API versioning or a well-documented transition period.

ProblemDetail has the advantage that standard members carry shared semantics. Extension members remain part of your API's custom contract and must be managed just like DTOs.

## 18. Choosing the Right Approach

| Scenario | Recommendation |
|---|---|
| New API wanting to follow a common HTTP standard | Prefer ProblemDetail per RFC 9457 |
| Existing API with an error DTO already used by many clients | Keep the DTO and standardize incrementally if needed |
| Need field-level validation error lists | Custom DTO or a violations extension on ProblemDetail |
| Need integration with standard Spring MVC errors | Use ProblemDetail and Spring Framework's built-in support |
| Need a product-specific error structure | Use a DTO with a clear schema |
| Errors originate in the Spring Security filter chain | Standardize both AuthenticationEntryPoint and AccessDeniedHandler |

Do not mix two error formats within the same endpoint without a clear reason. If a system is migrating from a custom DTO to ProblemDetail, specify which endpoints use which format, publish the corresponding media types, and avoid forcing clients to guess the structure per exception type.

## 19. Takeaways

- Standardizing errors enables consistent client handling and lets OpenAPI reuse schemas.
- Custom DTOs suit specialized contracts; ProblemDetail is the standardized choice under RFC 9457.
- ProblemDetail includes type, title, status, detail, and instance members and permits extension members.
- application/problem+json is for Problem Details responses; custom DTOs typically use application/json.
- Use @RestControllerAdvice for centralized exception handling; handle Spring Security errors separately in the filter chain.
- Error codes should be stable and machine-readable; messages should be safe and localizable.
- Never return stack traces or internal details to clients.
- Springdoc needs response status, media type, schema, and examples documented; do not assume advice adds every response to every operation.
- Test both runtime responses and /v3/api-docs documentation.

When standardizing errors in Spring Boot, pick a contract clients can rely on long-term. Use a DTO if the application needs a custom shape, or ProblemDetail to follow RFC 9457. Then implement centralized handling, document responses clearly with springdoc, and test to guarantee statuses, media types, schemas, and payloads always match.
