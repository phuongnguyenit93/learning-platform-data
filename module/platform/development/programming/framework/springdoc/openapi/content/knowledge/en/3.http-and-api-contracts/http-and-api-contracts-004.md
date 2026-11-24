# Status Codes and the Meaning of Success or Failure Responses

When a client calls an API, the HTTP status code is the first signal indicating how the server processed the request. This code helps the client decide whether it can use the returned data, needs to fix the request, must re-authenticate, should retry later, or needs to report an error to the user. A good API contract must therefore clearly describe status codes, response payloads, and the conditions under which each case occurs.

In a Spring Boot application, controllers and the exception-handling layer determine the actual HTTP responses. **springdoc-openapi** brings those responses into the OpenAPI specification so integrators can see them immediately in Swagger UI or use them in client generation, testing, and contract management tools. This lesson focuses on choosing the right status codes, designing consistent responses, and documenting them with OpenAPI.

## Objectives

After this lesson, you will be able to:

- Distinguish HTTP status code classes and understand the meaning of codes commonly used in REST APIs.
- Choose appropriate status codes for read, create, update, delete, and asynchronous processing operations.
- Design consistent error responses with enough information for clients to handle without exposing internal details.
- Return status codes and headers properly from Spring MVC.
- Document success responses, error responses, schemas, and headers in OpenAPI using springdoc-openapi.
- Verify whether the documented contract matches the application's actual HTTP responses.

## 1. Where Does the Status Code Live in an HTTP Response?

An HTTP response consists of a status line, headers, and an optional body depending on the case:

~~~http
HTTP/1.1 201 Created
Location: https://api.example.com/products/42
Content-Type: application/json

{
  "id": 42,
  "name": "Mechanical keyboard",
  "price": 1250000
}
~~~

In this example:

- `201 Created` indicates that the request created a new resource.
- `Location` points to the URI of the newly created resource.
- `Content-Type` indicates the format of the body.
- JSON is the resource representation that the client can consume.

The status code belongs to the HTTP protocol, not an arbitrary field inside JSON. For example, a `200 OK` response with body `{ "success": false }` is still interpreted by clients and proxies as a successful HTTP request. That style of representation makes it harder for clients to handle errors properly, because they must read and interpret custom conventions inside the body instead of relying on the protocol.

Use the status code to express the outcome at the HTTP level; use the body to provide data or detailed explanations. The body may contain a business error code such as `PRODUCT_NOT_FOUND`, which complements the status code rather than replacing it.

## 2. Five Classes of Status Codes

Status codes have three digits. The first digit indicates the outcome class:

| Class | Name | General meaning | Common scenarios |
|---|---|---|---|
| 1xx | Informational | The request is continuing to be processed | Protocol-level exchanges |
| 2xx | Success | The request was received and processed successfully according to the code's semantics | Reading, creating, updating, or accepting work |
| 3xx | Redirection | The client needs to take further action to complete the request | Redirection or using caches |
| 4xx | Client Error | The request has an issue or cannot be fulfilled in the current context | Invalid data, missing authentication, insufficient permissions |
| 5xx | Server Error | The server encountered an error while fulfilling an apparently valid request | Unexpected errors, dependent services unavailable |

REST APIs most commonly encounter the 2xx, 4xx, and 5xx classes. The 3xx class remains important when APIs use caching, proxies, or redirects. The 1xx class is usually handled at the protocol level by HTTP servers and clients and rarely needs to be declared as a business response on an endpoint.

Do not assume that all codes in the same class are interchangeable. `200`, `201`, `202`, and `204` are all 2xx yet convey different states; clients may rely on those differences to fetch a resource, track a job, or skip reading a body.

## 3. Common Success Codes

### 200 OK — Request Processed Successfully

`200 OK` is the standard code for reading data. The server returns the representation of a resource or query result:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": 42,
  "name": "Mechanical keyboard"
}
~~~

Common scenarios:

- `GET` returns a resource or a list of results.
- `PUT` or `PATCH` returns the updated representation after modification.
- `POST` performs an action and returns the completed result, when no new resource is created in a way requiring `201`.

If the client needs data after the operation, `200` is usually accompanied by a body with a clear schema. For empty query results, returning `200` with an empty list is appropriate if the endpoint means querying a collection; do not automatically turn every empty list into `404`.

### 201 Created — Resource Created

Use `201 Created` when the request has created one or more new resources. The response should provide a way to identify the newly created resource, usually via the `Location` header, and may return a body containing the resource representation:

~~~http
HTTP/1.1 201 Created
Location: /api/products/42
Content-Type: application/json

{
  "id": 42,
  "name": "Mechanical keyboard"
}
~~~

`201` is especially suited for `POST /api/products`. If an API returns `201` without telling the client where the new resource lives or what identifier it has, integration becomes harder. The `Location` header is a clear choice; the body can contain the same URI or data representing the resource.

### 202 Accepted — Request Accepted, Work Not Yet Completed

Use `202 Accepted` when the server has accepted the request for later processing, but has not finished the work at the time of responding. For example, a client requests a large report export and the server queues the job.

~~~http
HTTP/1.1 202 Accepted
Location: /api/jobs/8f31
Content-Type: application/json

{
  "jobId": "8f31",
  "status": "QUEUED",
  "statusUrl": "/api/jobs/8f31"
}
~~~

`202` does not mean the operation is guaranteed to succeed. The contract should tell clients where to track status, whether callbacks are supported, how long results are retained, and how failures are handled. If the work already finishes within the request itself, choose a code reflecting the final outcome instead of using `202` for every asynchronous-sounding operation.

### 204 No Content — Success, No Body

Use `204 No Content` when the request succeeds and the client does not need a response body. Common examples are deleting a resource or updating without returning a new representation:

~~~http
HTTP/1.1 204 No Content
~~~

A `204` response must not contain a body. If the client needs to receive the object after an update or a result message, use `200` with a body. Do not declare a JSON schema for a `204` response in OpenAPI.

### Other 2xx Codes

- `203 Non-Authoritative Information`: response information has been transformed by a proxy or intermediary; rarely used in ordinary REST contracts.
- `205 Reset Content`: signals the client to reset displayed content or form input state; rare in service APIs.
- `206 Partial Content`: returns part of the content via range requests, commonly used when downloading large files.

Only include these codes in the contract when the endpoint genuinely supports their corresponding semantics.

## 4. Redirection and Caching Codes

The 3xx class instructs the client to perform a follow-up action or use cached information:

| Code | Meaning | Usage notes |
|---|---|---|
| 301 Moved Permanently | Resource has permanently moved to a new address | Clients may update the URI; method preservation can vary by client |
| 302 Found | Temporarily redirected to another URI | Some clients may switch POST to GET when following the redirect |
| 303 See Other | View the result at another URI using GET | Useful when redirecting from a data submission to a result page |
| 304 Not Modified | Representation has not changed compared to the cached version | Returns no body; client uses its stored copy |
| 307 Temporary Redirect | Temporarily redirects while preserving method and body | Suitable when request semantics must be preserved |
| 308 Permanent Redirect | Permanently redirects while preserving method and body | Similar to 301 while preserving the method |

For public APIs, redirects require care because clients, proxies, and HTTP libraries have different redirect-following policies. When moving an endpoint, publish the new URI and the deprecation period for the old URI. For caching, also document related headers such as `ETag`, `Last-Modified`, `Cache-Control`, and `If-None-Match` when they affect how clients call the API.

## 5. Client Error Codes (4xx)

The 4xx class indicates that the request cannot be fulfilled in its current state. The error body should explain the issue in an actionable way for the client: which field to fix, how to authenticate, which resource does not exist, or when to retry.

### 400 Bad Request — Invalid Request

Use `400` for malformed requests, missing required structure, or unparseable parameters. Examples:

- Invalid JSON or wrong data types.
- Query parameter cannot be converted to the expected type.
- Missing required fields per the contract.
- Request fails validation rules for which the API specifies returning `400`.

Return errors that pinpoint the offending field or location. Do not include full stack traces or sensitive request data in the response.

### 401 Unauthorized — Not Validly Authenticated

Use `401` when a request lacks credentials, has an expired token, or has invalid credentials. The standard name includes the word “Unauthorized”, though the actual meaning is that the client has not been authenticated. According to HTTP, a `401` response must include at least one challenge in the `WWW-Authenticate` header indicating supported authentication schemes.

The client may need to log in or refresh its token and resend the request. Do not use `401` simply because an authenticated user lacks permission to perform an action; that case is typically `403`.

### 403 Forbidden — Authenticated but Not Permitted

Use `403` when the server understands the request and the identity has been authenticated, yet authorization policy forbids the operation. For example, a user has a valid token but lacks the `product:write` permission.

The message may mention the required permission or how to contact an administrator, without exposing internal authorization structures if doing so creates risk. Some systems intentionally return `404` instead of `403` to avoid disclosing the existence of a resource; if adopting that policy, apply it consistently and document the public behavior.

### 404 Not Found — Resource Not Found

Use `404` when the URI does not point to an existing resource or the API chooses not to reveal that the resource exists. For example, `GET /api/products/9999` when that product ID does not exist.

For list endpoints, finding no matching items is usually represented by `200` with an empty list. `404` is reserved for nonexistent resources or paths according to endpoint semantics.

### 405 Method Not Allowed — Method Not Supported

Use `405` when the path exists but does not support the HTTP method sent by the client. According to HTTP, the response must include an `Allow` header listing supported methods, such as `Allow: GET, HEAD`.

In Spring MVC, request routing typically handles unmapped methods automatically. When testing, confirm the actual status code and headers across application configuration, proxies, and exception handlers.

### 406 Not Acceptable — No Matching Representation

Use `406` when the server cannot produce a response matching the formats requested by the client in the `Accept` header. For example, the client only accepts XML while the API only provides JSON. Document supported media types so clients send an appropriate `Accept` header.

### 409 Conflict — Conflict with Current State

Use `409` when the request is structurally valid but cannot complete due to a conflict with resource or data state. Examples:

- Creating a user with an already existing email.
- Transitioning an order to a status disallowed by the business workflow.
- An update colliding with a concurrent modification.

The response should explain the conflict and possible resolution steps. For concurrent updates using ETag or HTTP preconditions, `412 Precondition Failed` may express the situation more accurately when an `If-Match` condition no longer holds.

### 410 Gone — Resource Removed

Use `410` when the server knows the resource used to exist but has been permanently removed. `404` fits when the server cannot confirm whether the resource ever existed; `410` gives a clearer signal that the client should stop looking for the resource at the old URI.

### 412 Precondition Failed — Request Precondition Not Met

Use `412` when a condition sent via request headers is not satisfied. A common case is conditional updates with `If-Match` and ETag: a client reads an old ETag version, another client updates first, so the server rejects the update to prevent overwriting newer data.

### 415 Unsupported Media Type — Content Format Not Supported

Use `415` when the body format is not supported by the endpoint, usually due to an incompatible `Content-Type`. For example, the endpoint only accepts `application/json` while the client sends `text/plain`. Distinguish `415` from `406`: one relates to the submitted request format, while the other relates to the response format the client accepts.

### 422 Unprocessable Content — Understood Content That Cannot Be Processed

Use `422` when the request syntax and format are valid, yet the content cannot be processed semantically. For example, valid JSON where a combination of values violates complex business rules.

An API can choose `400` for all validation errors, or separate `400` for unparseable requests and `422` for content violating business rules. Both approaches work if clearly defined, consistent, and reflected in documentation. Avoid mixing `400` and `422` inconsistently for the same error category.

### 429 Too Many Requests — Rate Limit Exceeded

Use `429` when a client sends too many requests within a time window. The response should guide when to retry, typically via `Retry-After`, and may include remaining quota details if policy permits.

Clients should not immediately keep retrying in a tight loop after `429`. Wait as instructed, apply exponential backoff and jitter when needed, and respect shared rate limits across requests.

## 6. Server Error Codes (5xx)

The 5xx class indicates that the server could not complete an apparently valid request due to processing failures or system dependencies.

| Code | Meaning | When to use |
|---|---|---|
| 500 Internal Server Error | Unexpected internal error | Unhandled exceptions or errors without a more specific classification |
| 501 Not Implemented | Server does not support the required functionality | Feature or method not yet implemented |
| 502 Bad Gateway | Gateway received an invalid response from upstream | Reverse proxy or gateway calling a backend service |
| 503 Service Unavailable | Service is temporarily unavailable | Maintenance, overload, or temporarily unavailable dependency |
| 504 Gateway Timeout | Gateway did not receive a timely response from upstream | Downstream service timed out |

`500` should be a fallback for unexpected failures, not a catch-all answer for every scenario. If the client sent bad data, use 4xx; if a dependent service is temporarily unavailable, `503` or `502` may describe the situation more accurately depending on the server's role.

For `503`, `Retry-After` can be sent if the server knows an appropriate time for the client to retry. Do not return stack traces, internal class names, SQL queries, file paths, secrets, or connection details in error bodies. Log technical details to controlled internal logs and return a reference ID so support teams can look them up.

## 7. Choosing Consistent Status Codes for Each REST Operation

The following table is a starting point for a product management API. Actual codes depend on business requirements, yet should stay consistent across the entire service:

| Operation | Common success | Common errors |
|---|---|---|
| `GET /api/products/{id}` | `200` | `400`, `401`, `403`, `404`, `500` |
| `GET /api/products` | `200`, including an empty list | `400`, `401`, `403`, `500` |
| `POST /api/products` | `201` and `Location` | `400` or `422`, `401`, `403`, `409`, `500` |
| `PUT /api/products/{id}` | `201` if creating a new resource; `200` if returning the updated representation; `204` if no body | `400`, `401`, `403`, `404`, `409`, `412`, `500` |
| `PATCH /api/products/{id}` | `200` or `204` depending on response | `400`, `401`, `403`, `404`, `409`, `412`, `422`, `500` |
| `DELETE /api/products/{id}` | `204` when deleted with no body; `200` may be used if returning a result | `401`, `403`, `404`, `409`, `500` |
| `POST /api/reports` creating a long-running task | `202` and tracking details | `400`, `401`, `403`, `429`, `500`, `503` |

Selection principles:

- Use `201` when a new resource has been created, not merely because the HTTP method is `POST`.
- Use `202` when work has been accepted but the outcome is not yet complete.
- Use `204` when succeeding with no body.
- Use `404` for nonexistent resources; an empty list usually remains `200`.
- Use `409` for business-state conflicts; use `412` when an HTTP precondition such as ETag fails.
- Pick a clear convention for validation, such as `400` or `422`, and apply it uniformly.

No single status code table fits every domain. What matters is choosing by HTTP semantics, explaining special cases, and keeping the same conventions across endpoints.

## 8. Designing Error Response Structure

A good error response should have a stable structure. Clients can read the error code to decide what action to take and read the message to display or log. Example:

~~~json
{
  "code": "VALIDATION_FAILED",
  "message": "Submitted data is invalid",
  "details": {
    "name": "Product name must not be blank",
    "price": "Price must be greater than 0"
  },
  "timestamp": "2026-11-20T10:30:00Z",
  "path": "/api/products",
  "traceId": "01J..."
}
~~~

Field meanings:

| Field | Purpose |
|---|---|
| `code` | Stable error code for programmatic client handling |
| `message` | Brief explanation for users or integrating developers |
| `details` | Field-level details or causes, if available |
| `timestamp` | Time when the server recorded the error |
| `path` | Related request path |
| `traceId` | Correlation ID for finding internal logs, if supported by the system |

Do not force clients to parse wording inside `message` to drive logic, because messages may be edited or translated. Use `code` as the stable identifier. For validation errors, returning a list or map of field-level details helps UIs highlight the exact fields to fix.

Error bodies should avoid:

- Stack traces, package names, SQL queries, table names, or internal file paths.
- Tokens, passwords, credentials, or unnecessary personal data.
- Echoing raw request payloads verbatim if requests may contain secrets.
- Inconsistent structures across endpoints that force clients to write multiple parsing branches.

### Using Problem Details

HTTP has a standardized Problem Details format defined in RFC 9457. Common fields include `type`, `title`, `status`, `detail`, and `instance`; APIs may add extension members for error codes or validation details. Example:

~~~json
{
  "type": "https://api.example.com/problems/validation-failed",
  "title": "Invalid request",
  "status": 400,
  "detail": "One or more fields failed validation rules.",
  "instance": "/api/products",
  "code": "VALIDATION_FAILED",
  "errors": {
    "name": "Product name must not be blank"
  }
}
~~~

Problem Details is typically sent with media type `application/problem+json`. Using a standard error format enables generic clients and tools to understand the base fields; extensions like `code` and `errors` supply API-specific semantics. If choosing Problem Details, use it consistently and document the exact media type and schema in OpenAPI.

## 9. Returning Status Codes from Spring Boot

In Spring MVC, status codes can be determined via `@ResponseStatus`, `ResponseEntity`, or exception handlers. Choose the mechanism suited to the required flexibility.

### Using @ResponseStatus for Fixed Outcomes

When an endpoint always returns the same status code, it can be declared directly:

~~~java
@PostMapping
@ResponseStatus(HttpStatus.CREATED)
public ProductResponse create(@Valid @RequestBody CreateProductRequest request) {
    return productService.create(request);
}
~~~

Spring returns `201 Created` for the method's result. This is concise when custom response headers are not needed. If you need `Location`, cache headers, or a status that depends on processing outcomes, use `ResponseEntity`.

### Using ResponseEntity When Full Response Control Is Needed

`ResponseEntity<T>` lets you specify status, headers, and body:

~~~java
@PostMapping
public ResponseEntity<ProductResponse> create(
        @Valid @RequestBody CreateProductRequest request) {

    ProductResponse created = productService.create(request);
    URI location = URI.create("/api/products/" + created.id());

    return ResponseEntity.created(location).body(created);
}

@DeleteMapping("/{id}")
public ResponseEntity<Void> delete(@PathVariable long id) {
    productService.delete(id);
    return ResponseEntity.noContent().build();
}

@PostMapping("/reports")
public ResponseEntity<JobResponse> createReport(@RequestBody ReportRequest request) {
    JobResponse job = reportService.submit(request);
    URI statusUri = URI.create("/api/jobs/" + job.id());

    return ResponseEntity.accepted()
        .location(statusUri)
        .body(job);
}
~~~

The snippet requires appropriate DTO types, services, and imports in the project. The builders have clear semantics: `created(...)` builds a 201 response with Location, `noContent()` builds a 204 without body, and `accepted()` builds a 202.

### Centralized Error Handling with @RestControllerAdvice

Do not repeat exception-to-response conversion logic in every controller. You can create a `@RestControllerAdvice` to map exceptions to consistent status codes and error schemas:

~~~java
public record ApiError(
    String code,
    String message,
    Map<String, String> details,
    Instant timestamp
) {}

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    public ResponseEntity<ApiError> handleNotFound(ProductNotFoundException ex) {
        ApiError body = new ApiError(
            "PRODUCT_NOT_FOUND",
            "Product not found",
            Map.of(),
            Instant.now()
        );
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(body);
    }

    @ExceptionHandler(DuplicateProductException.class)
    public ResponseEntity<ApiError> handleConflict(DuplicateProductException ex) {
        ApiError body = new ApiError(
            "PRODUCT_ALREADY_EXISTS",
            "Product already exists",
            Map.of(),
            Instant.now()
        );
        return ResponseEntity.status(HttpStatus.CONFLICT).body(body);
    }
}
~~~

The example omits imports and exception definitions to focus on mapping. In real applications, validation handlers also need to transform field errors into an appropriate `details` structure. Do not return `ex.getMessage()` directly for every exception because its content may expose technical details or sensitive data.

With Spring Framework 6+, consider `ProblemDetail` to return standardized Problem Details. Example:

~~~java
@ExceptionHandler(ProductNotFoundException.class)
public ProblemDetail handleNotFound(ProductNotFoundException ex) {
    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.NOT_FOUND,
        "The requested product was not found."
    );
    problem.setTitle("Resource not found");
    problem.setProperty("code", "PRODUCT_NOT_FOUND");
    return problem;
}
~~~

`ProblemDetail` can be used directly in Spring MVC; verify framework configuration and version to ensure the media type and extension members are serialized properly. If the project uses Spring Boot 2 or an older Spring Framework, this type may not be available and a custom error DTO is needed.

## 10. Documenting Status Codes in OpenAPI with springdoc-openapi

OpenAPI describes responses per operation inside the `responses` property. Each response has a status code or the `default` key, a required `description`, and may include:

- `content`: media types and schemas for the body.
- `headers`: returned headers, such as `Location`, `Retry-After`, or `ETag`.
- `links`: relationships to other operations in the document.

In Spring, OpenAPI annotations commonly used to document responses:

| Annotation | Role |
|---|---|
| `@ApiResponse` | Describes one status code and its corresponding response |
| `@ApiResponses` | Groups multiple `@ApiResponse` annotations on an operation |
| `@Content` | Declares media types and response content |
| `@Schema` | Specifies the body schema |
| `@ExampleObject` | Provides payload examples |
| `@Header` | Describes a response header |

Controller example:

~~~java
@RestController
@RequestMapping("/api/products")
@Tag(name = "Products")
public class ProductController {

    @GetMapping("/{id}")
    @Operation(summary = "Get product by ID")
    @ApiResponses({
        @ApiResponse(
            responseCode = "200",
            description = "Product found",
            content = @Content(
                mediaType = "application/json",
                schema = @Schema(implementation = ProductResponse.class)
            )
        ),
        @ApiResponse(
            responseCode = "404",
            description = "Product not found",
            content = @Content(
                mediaType = "application/json",
                schema = @Schema(implementation = ApiError.class)
            )
        ),
        @ApiResponse(
            responseCode = "401",
            description = "Missing or invalid authentication credentials"
        )
    })
    public ProductResponse getById(@PathVariable long id) {
        return productService.getById(id);
    }

    @PostMapping
    @Operation(summary = "Create a product")
    @ApiResponses({
        @ApiResponse(
            responseCode = "201",
            description = "Product created",
            content = @Content(
                mediaType = "application/json",
                schema = @Schema(implementation = ProductResponse.class)
            )
        ),
        @ApiResponse(
            responseCode = "400",
            description = "Invalid request data",
            content = @Content(
                schema = @Schema(implementation = ApiError.class)
            )
        ),
        @ApiResponse(
            responseCode = "409",
            description = "Product already exists",
            content = @Content(
                schema = @Schema(implementation = ApiError.class)
            )
        )
    })
    public ResponseEntity<ProductResponse> create(
            @Valid @RequestBody CreateProductRequest request) {
        ProductResponse created = productService.create(request);
        URI location = URI.create("/api/products/" + created.id());
        return ResponseEntity.created(location).body(created);
    }
}
~~~

This is an illustrative example; replace `ProductResponse`, `ApiError`, DTOs, and services with your application's types. The `@ApiResponse` annotation documents the contract, while `ResponseEntity` and exception handlers determine the actual HTTP response. Declaring `404` in OpenAPI does not make a controller return `404`; conversely, having a handler return `404` without a matching description leaves the documentation incomplete.

### Documenting Responses Without a Body

For a delete endpoint returning `204`, declare the response and omit `content`:

~~~java
@DeleteMapping("/{id}")
@ApiResponse(responseCode = "204", description = "Product deleted")
@ApiResponse(
    responseCode = "404",
    description = "Product not found",
    content = @Content(
        schema = @Schema(implementation = ApiError.class)
    )
)
public ResponseEntity<Void> delete(@PathVariable long id) {
    productService.delete(id);
    return ResponseEntity.noContent().build();
}
~~~

A `204` response declares no body schema. Swagger UI indicates that the operation succeeds with no returned content.

### Documenting Response Headers

For `201 Created`, you can declare the `Location` header so contract consumers know where the newly created resource URI is returned. The `@Header` annotation resides in the `io.swagger.v3.oas.annotations.headers` package:

~~~java
@ApiResponse(
    responseCode = "201",
    description = "Resource created",
    headers = @Header(
        name = "Location",
        description = "URI of the newly created resource",
        schema = @Schema(type = "string", format = "uri")
    ),
    content = @Content(
        schema = @Schema(implementation = ProductResponse.class)
    )
)
~~~

Similarly, for `429` or `503`, document `Retry-After` if the API actually returns that header. Do not declare a header just because you wish clients would use it; the code must emit the corresponding header.

### Documenting Problem Details

If the API uses Problem Details, explicitly specify the media type and response schema:

~~~java
@ApiResponse(
    responseCode = "400",
    description = "Invalid request",
    content = @Content(
        mediaType = "application/problem+json",
        schema = @Schema(implementation = ProblemDetail.class)
    )
)
~~~

If the API includes extensions such as `code` or `errors`, use a dedicated schema or an OpenAPI customization mechanism to represent the additional fields. Do not assume the default `ProblemDetail` class schema already documents every extension added by your application.

### Reusing Error Descriptions

Many endpoints share `400`, `401`, `403`, or `500` responses. Reusable responses can be defined under `components.responses` and referenced from operations. With annotations, you can use `@ApiResponse(ref = "...")` following the appropriate OpenAPI reference syntax, or use an `OpenApiCustomizer` bean to add shared responses to operations.

Adding shared responses must reflect the actual scope of each endpoint. Do not attach `401` to public endpoints that do not require authentication, and do not attach `404` to every endpoint if that operation cannot produce that situation. The more irrelevant responses a document contains, the harder it is for clients to understand the real contract.

## 11. Distinguishing Status Codes, Schemas, and Security in Documentation

These three layers of information complement one another:

| Component | Question it answers |
|---|---|
| Status code | Did the request succeed, get rejected, or fail somewhere? |
| Response schema | What structure and data types does the body have? |
| Security requirement | How must the client authenticate to invoke the operation? |

For example, an endpoint requiring JWT can declare a `security` requirement, document `401` for missing or invalid tokens, `403` for insufficient permissions, and `200` for success. The schema for `200` is `ProductResponse`, while the error schema can be `ApiError` or `ProblemDetail`.

Do not confuse `401` and `403` in documentation. Do not describe authentication errors merely as plain text without a status code. At the same time, OpenAPI security schemes only describe client requirements; Spring Security must still enforce authentication and authorization in the application.

## 12. How Should Clients Handle and Retry Responses?

Status codes drive client action selection. Some practical rules:

- For `2xx`, read the body according to the published schema; specifically for `204`, do not attempt to parse JSON.
- For `400` or `422`, display validation errors and allow the user to fix the input.
- For `401`, trigger login or token refresh if supported; avoid infinite loops when credentials are no longer valid.
- For `403`, report insufficient permissions or direct the user to an administrator; do not repeatedly resend the same request.
- For `404`, check the URI or update UI state if the resource was deleted.
- For `409` or `412`, reload the latest state and ask the user to resolve the conflict when needed.
- For `429` or `503`, obey `Retry-After`; if no header is present, apply bounded backoff.
- For `500`, retry only when the operation can be safely repeated or has an appropriate idempotency mechanism.

HTTP distinguishes safe and idempotent methods. `GET`, `HEAD`, `OPTIONS`, and `TRACE` are defined as safe (TRACE is usually disabled on application APIs); `PUT` and `DELETE` are idempotent per HTTP semantics; `POST` is generally not idempotent. An idempotent request can be resent without changing the intended outcome beyond the first call, though that does not mean every retry is free or devoid of side effects outside the contract.

For resource creation via `POST`, if the client might lose connection after the server succeeded but before receiving the response, retrying can create duplicate records. If the business requires safe retries, design an idempotency key or a result lookup mechanism before retrying. State this behavior clearly in the contract.

## 13. Verifying Actual Responses and the OpenAPI Document

An endpoint may return the right status code locally while the documentation still describes it inaccurately. Conversely, Swagger UI may list all responses while the code fails to produce them. Verify both sides.

### Testing with an HTTP Client

Example creating a resource:

~~~bash
curl -i -X POST http://localhost:8080/api/products \
  -H "Content-Type: application/json" \
  -d '{"name":"Mechanical keyboard","price":1250000}'
~~~

Verify status `201`, the `Location` header, `Content-Type`, and the body. Then test requests with a missing name, invalid price, invalid token, and nonexistent product ID to confirm error responses. `curl -i` displays both the status line and headers, making it suitable for verifying HTTP contracts.

### Testing with Spring MockMvc

For Spring MVC applications, MockMvc can verify status codes, headers, and bodies:

~~~java
@WebMvcTest(ProductController.class)
class ProductControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    ProductService productService;

    @Test
    void createReturns201AndLocation() throws Exception {
        given(productService.create(any()))
            .willReturn(new ProductResponse(42L, "Mechanical keyboard", 1250000));

        mockMvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"name":"Mechanical keyboard","price":1250000}
                    """))
            .andExpect(status().isCreated())
            .andExpect(header().string("Location", endsWith("/api/products/42")))
            .andExpect(jsonPath("$.id").value(42));
    }
}
~~~

The example uses Java text block syntax along with Spring Test and Mockito matchers; add imports and test setup appropriate for your project's Spring Boot version. Additional tests can verify `204` without body, `404` with error schema, `409` for conflicts, and `400` for validation.

### Inspecting the Generated Specification

Open `/v3/api-docs` or the corresponding group endpoint and inspect `paths`. An operation should include the necessary responses:

~~~yaml
paths:
  /api/products/{id}:
    get:
      responses:
        '200':
          description: Product found
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ProductResponse'
        '404':
          description: Product not found
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ApiError'
        '401':
          description: Missing or invalid authentication credentials
~~~

This is an abbreviated YAML snippet illustrating response structure; real documents also include `operationId`, parameters, security, and components. Use an OpenAPI validator or linter to catch structural errors, then verify important contents through automated tests or reviews.

A helpful reconciliation matrix:

| Check | In source code | In OpenAPI | On live call |
|---|---|---|---|
| Create succeeded | `ResponseEntity.created(...)` | `201` and success schema | `201`, Location, and expected body |
| Not found | Exception handler returns `404` | `404` and error schema | `404` with error payload |
| Delete succeeded | `noContent()` | `204`, no content | `204`, no body |
| Rate limited | Limiter returns `429` | `429` and Retry-After if present | `429` with published header |

If any cell mismatches, fix the implementation or the contract to match the agreed behavior, then re-run checks. Never let documentation promise a status code the application never returns, or let the application return an error type clients have no guidance on handling.

## 14. Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Always returning `200` and embedding errors in the body | Clients, gateways, and monitoring mistake failed requests for successes | Use semantically correct status codes and a stable error schema |
| Returning `201` with no way to identify the new resource | Clients struggle to fetch or link the resource | Return `Location` and/or a representation with an identifier |
| Returning `204` with JSON | Violates no-content response semantics | Use `200` if a body is needed; if `204`, omit the body |
| Using `404` for an empty list | Clients assume the endpoint or resource does not exist | Return `200` with an empty list when the collection exists |
| Using `401` for every permission error | Clients do not know whether to log in or request more permissions | Distinguish authentication `401` from authorization `403` |
| Using `500` for bad input data | Clients struggle to fix requests and monitoring logs the wrong error class | Return `400` or `422` according to convention |
| Documenting a response the code never produces | Clients integrate against a false contract | Test actual statuses, headers, and bodies |
| Code returns an error omitted from OpenAPI | Swagger UI and client generators lack information | Add `@ApiResponse` or an appropriate customizer |
| Returning stack traces in the body | Leaks internal structure and details | Use error codes, safe messages, and trace IDs |
| Retrying every error immediately | Increases load and may create duplicate data | Handle by status, idempotency, and backoff |

## 15. Practice Exercise

Build or choose a product management API with read, create, update, and delete endpoints. Complete these steps in order:

1. Create a status code table for each endpoint, covering successes and expected errors.
2. Decide on a validation convention using `400`, `422`, or both; document the conditions clearly.
3. Create a common error schema with `code`, `message`, `details`, and timestamp.
4. Use `ResponseEntity` to return `201` with `Location`, `204` without a body, and `202` for a background task.
5. Create a `@RestControllerAdvice` mapping not-found errors to `404`, duplicate data errors to `409`, and validation errors per your convention.
6. Use springdoc-openapi to declare responses for key status codes with schemas and headers.
7. Open Swagger UI to confirm responses display accurately; download `/v3/api-docs` and run a validator.
8. Write tests verifying status, headers, and body for both success and failure cases.
9. Send real requests using an HTTP client to verify results against the specification.
10. Test a `429` or `503` scenario and document how clients should wait before retrying.

### Completion Criteria

- [ ] Every endpoint has a success status code reflecting its actual outcome.
- [ ] `201`, `202`, and `204` are used with proper semantics; `204` responses have no body.
- [ ] Common errors are sensibly distinguished among `400`, `401`, `403`, `404`, `409`, `422`, and `5xx`.
- [ ] Error bodies have a stable schema and do not leak internal details.
- [ ] Important headers such as `Location`, `WWW-Authenticate`, or `Retry-After` are documented when used by the API.
- [ ] OpenAPI accurately lists responses, media types, and schemas for each endpoint.
- [ ] Tests verify status codes, headers, and bodies; results match the documentation.
- [ ] Clients have clear guidance for retries, re-authentication, and conflict resolution.

## Next Steps

After this lesson, combine status codes with request/response schema descriptions, standardize errors with Problem Details, declare security requirements, and run contract tests in CI. Whenever an endpoint changes behavior, update the controller or exception handler, the OpenAPI specification, and the tests together so API consumers always receive the same message from all three places.
