# Testing Empty Bodies, Validation Errors, and ProblemDetail in Spring WebFlux

> **Module:** Spring Framework – reactive  
> **Parent topic:** WebFlux Testing  
> **Primary goal:** accurately test the HTTP contract of reactive REST endpoints when a response has no content, when request data fails Bean Validation, and when the API returns RFC 9457 `ProblemDetail` errors. The lesson focuses on `WebTestClient`, JUnit 5, Spring WebFlux, `@Valid`, `WebExchangeBindException`, `HandlerMethodValidationException`, `ServerWebInputException`, `ResponseEntity<ProblemDetail>`, and assertions that are both accurate and resilient.

## 1. What will you be able to do after this lesson?

1. Distinguish **HTTP 204 No Content**, **HTTP 200 with a 0-byte body**, **HTTP 200 containing JSON `null`**, **HTTP 200 containing JSON `[]`**, and a `Mono.empty()` at the service layer.
2. Use `WebTestClient.expectBody().isEmpty()` to verify that a response truly has no payload.
3. Verify status, `Content-Type`, `Location`, JSON fields, raw bytes, and empty bodies according to the exact endpoint contract.
4. Recognize the difference between a **missing** body, a **syntactically invalid JSON** body, a **valid JSON body that violates constraints**, and a method parameter violating a constraint.
5. Understand that `@Valid @RequestBody` leads to `WebExchangeBindException`, whereas constraints directly on parameters can lead to `HandlerMethodValidationException`.
6. Understand why `ServerWebInputException` usually relates to decoding or missing request bodies and should not lump all errors into "validation failed."
7. Design `ProblemDetail` per RFC 9457: `type`, `title`, `status`, `detail`, `instance`, adding `code` or `errors` in a controlled way.
8. Write a `@RestControllerAdvice` returning consistent `application/problem+json` errors while avoiding leaking internal data.
9. Test success branches (201/204), validation branches (400), business not found (404), internal errors (500), and unsupported media types (415).
10. Distinguish unit/controller-slice tests from HTTP integration tests, knowing what is verified and what is not.
11. Use `StepVerifier` for service publishers and `WebTestClient` for HTTP contracts, without relying on `.block()` as the default testing method.
12. Run a Spring Boot 4.0.9 / Java 17+ project with validation, ProblemDetail, HTTP tests, and matching curl commands.

**Key rule:** REST testing does not just check "received 400." It must answer: where is the request wrong, does the response have the right media type, does the body have a stable structure, is any internal detail leaked, and when there is no content, are truly zero bytes sent.

## 2. Map of layers to test

A request passes through multiple steps before an HTTP response is received:

~~~text
HTTP Client / WebTestClient
       |
       v
WebFlux WebHandler / WebFilter
       |
       v
HandlerMapping / argument resolver
       |
       +-- Select method, read Content-Type
       +-- Decode JSON to DTO
       +-- Bean Validation / method validation
       |        |
       |        +-- error: exception -> error handler -> ProblemDetail
       |
       v
Controller method
       |
       v
Mono<T> / Flux<T> / ResponseEntity<T>
       |
       +-- complete empty -> body has no elements
       +-- success with value -> JSON codec
       +-- error -> exception mapping
       |
       v
HttpMessageWriter / HTTP status, headers, bytes
       |
       v
WebTestClient assertions
~~~

Different layers can all return HTTP 400 for different reasons: missing request body, codec unable to parse JSON, failed Bean Validation, or failed method parameter constraints. A test that only asserts 400 will not catch wrong message mapping or wrong body structure.

From the API consumer's perspective, you must test **the contract observable over HTTP**, not just mock a controller method and assert that the repository/service was called.

## 3. Five commonly confused "empty" states

### 3.1. HTTP 204 No Content

`204` signals that the operation succeeded yet **sends no message content**. Examples include DELETE, status updates, or requests needing no payload:

~~~java
@GetMapping("/no-content")
public Mono<ResponseEntity<Void>> noContent() {
    return Mono.just(
        ResponseEntity.noContent().<Void>build());
}
~~~

Expectations:
- HTTP status: 204.
- Response body: zero data bytes.
- Do not expect JSON `{}` or `null`.
- Do not parse the response body into a DTO.

### 3.2. HTTP 200 with an empty body

~~~java
@GetMapping("/empty-ok")
public Mono<ResponseEntity<Void>> emptyOk() {
    return Mono.just(ResponseEntity.ok().<Void>build());
}
~~~

The expectation is status 200 with no body content. This is a valid API contract if clearly designed, though for commands returning no result, 204 usually expresses intent more directly.

### 3.3. HTTP 200 containing an empty JSON list

~~~java
@GetMapping("/empty-list")
public Mono<List<ItemView>> emptyList() {
    return Mono.just(List.of());
}
~~~

With standard JSON codecs, the body is `[]`. **This is not an empty response body**: it has two JSON characters and represents an existing collection with 0 elements.

### 3.4. JSON `null`

The `null` payload consists of four characters (`n`, `u`, `l`, `l`). It is completely different from having no body. If the API contract allows `null` values, check the exact type and semantics. Do not assume `Mono.empty()` automatically serializes to JSON `null`.

### 3.5. `Mono.empty()` at the reactive layer

`Mono.empty()` is a publisher that **emits no `onNext`** and only `onComplete`. When WebFlux handles a response with no body value, the result can be a contentless response with the chosen/default status; `Mono.empty()` **does not automatically mean HTTP 204**.

Example:

~~~java
@GetMapping("/ambiguous")
public Mono<String> ambiguous() {
    return Mono.empty();
}
~~~

A clearer approach when the API must return 204 is `ResponseEntity.noContent().build()`; for a lookup that finds nothing, use `switchIfEmpty(Mono.error(new ResponseStatusException(HttpStatus.NOT_FOUND)))` or an explicitly mapped custom not-found exception.

### 3.6. Practical expectations table

| Case | HTTP status | Observable payload | Recommended test |
| --- | ---: | --- | --- |
| Operation returns no content | 204 | 0 bytes | `expectStatus().isNoContent()` and `expectBody().isEmpty()` |
| Success with no payload | 200 | 0 bytes | `expectStatus().isOk()` and `expectBody().isEmpty()` |
| Empty list | 200 | `[]` | `expectBody().json("[]")` |
| Explicit JSON null | 200 | `null` | Assert raw JSON/body if required by API contract |
| Empty JSON object | 200 | `{}` | JSON object exists with no fields |
| Resource does not exist | 404 | Possibly `ProblemDetail` | Assert status + problem fields |
| `Mono<Void>` completes, default status | Usually 200 depending on handler | No onNext | Test actual HTTP, do not guess status from Publisher |

Do not use `expectBody().isEmpty()` to test an empty list. For a collection endpoint returning `[]`, the `isEmpty()` assertion must fail: that is how the test protects the true contract.

## 4. How does WebTestClient test an empty response body?

`WebTestClient` is supported by Spring Framework for both real HTTP servers and direct controller/router bindings. You can verify status/headers/body:

~~~java
client.get()
    .uri("/api/demo/no-content")
    .exchange()
    .expectStatus().isNoContent()
    .expectBody().isEmpty();
~~~

Per Spring Framework documentation, `expectBody()` inspects the raw `byte[]` and provides `.isEmpty()` for responses with no content. Do not just write `.expectBody(Void.class)`: type `Void` is typically used when **ignoring content** or skipping the body; it does not directly prove the body is truly 0 bytes long the way `isEmpty()` does.

### 4.1. When checking raw bytes

~~~java
client.get()
    .uri("/api/demo/no-content")
    .exchange()
    .expectStatus().isNoContent()
    .expectBody()
    .consumeWith(result -> {
        byte[] bytes = result.getResponseBody();
        org.junit.jupiter.api.Assertions.assertTrue(
            bytes == null || bytes.length == 0);
    });
~~~

This is a test fragment with an initialized `client` variable; `isEmpty()` is more concise for common contracts. With `consumeWith`, account for the framework representing an empty body as either `null` or an empty array.

### 4.2. Checking headers

~~~java
client.get()
    .uri("/api/demo/no-content")
    .exchange()
    .expectStatus().isNoContent()
    .expectHeader().doesNotExist("Content-Type")
    .expectBody().isEmpty();
~~~

If the endpoint is designed not to send `Content-Type` on 204, this assertion can be helpful. Do not write assertions on headers outside the contract or added automatically by a deployment gateway if the test only cares about status/body semantics. Choose the right level of strictness.

### 4.3. 200 empty body differs from 204

~~~java
client.get()
    .uri("/api/demo/empty-ok")
    .exchange()
    .expectStatus().isOk()
    .expectBody().isEmpty();
~~~

Both 200 and 204 can come with a 0-byte payload; **status does not replace the body assertion**. When a frontend checks only status and tries to parse JSON, `response.json()` can fail on a 204 response because there is no JSON content.

### 4.4. JSON empty list

~~~java
client.get()
    .uri("/api/demo/empty-list")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectHeader()
        .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBody()
    .json("[]");
~~~

`json("[]")` checks the JSON content. For complex schemas, use JSONPath and `expectBodyList(Dto.class)`; do not assume element order if the DB query has no `ORDER BY`.

## 5. Where does validation occur in Spring WebFlux?

Two validation levels are easily conflated:

1. **Argument-level validation** for `@Valid @RequestBody` DTOs or `@Validated` applied to an object, usually producing `WebExchangeBindException`.
2. **Method validation** when constraints like `@Min`, `@NotBlank`, or `@NotNull` are placed directly on method parameters/return values; Spring WebFlux can produce `HandlerMethodValidationException`.

In addition, decoding and required bodies commonly trigger `ServerWebInputException`; a missing or wrong Content-Type can lead to other error types like `UnsupportedMediaTypeStatusException`.

### 5.1. DTO validated with Bean Validation

~~~java
public record CreateItemRequest(
    @NotBlank @Size(max = 60) String name,
    @NotNull @Min(1) Integer quantity
) {}
~~~

Constraints:
- `name` cannot be null, empty, or whitespace-only; maximum 60 characters per Bean Validation size.
- `quantity` must be present and greater than or equal to 1.
- Annotations sit on record components; the validation provider reads those constraints.
- Do not assume `@Valid` works automatically if the classpath lacks a Jakarta Validation provider (add `spring-boot-starter-validation`).

Controller:

~~~java
@PostMapping("/items")
public Mono<ResponseEntity<ItemView>> create(
        @Valid @RequestBody CreateItemRequest request) {

    return service.create(request)
        .map(item ->
            ResponseEntity.created(
                URI.create("/api/demo/items/" + item.id()))
                .body(item));
}
~~~

This is an **illustrative fragment** with `service`, `ItemView`, and `URI` already defined. The runnable project in section 16 provides the full controller/service/DTOs. If the DTO is invalid, the argument resolver/validator can throw `WebExchangeBindException` before the method constructs a response.

### 5.2. Method-level constraints

~~~java
@GetMapping("/quantity/{amount}")
public Mono<Map<String, Integer>> quantity(
        @PathVariable @Min(1) int amount) {

    return Mono.just(Map.of("amount", amount));
}
~~~

`@Min(1)` is attached **directly** to the method parameter. Spring WebFlux built-in method validation can raise `HandlerMethodValidationException` when receiving `amount=0`.

If the controller also has `@Validated` at the class level, Spring may use AOP method validation instead of the built-in handler method validation mechanism; when testing `HandlerMethodValidationException`, **do not add `@Validated` to the class** just because you see validation annotations in the DTO.

### 5.3. `@Valid` is not a direct constraint

`@Valid` requests nested/bean validation. If you add `@NotNull` directly on a `@Valid @RequestBody` parameter, method validation may take precedence over object-only validation. Thus the same DTO can emit a different exception type if the method signature changes.

Spring Framework recommends handling both `WebExchangeBindException` and `HandlerMethodValidationException` when an API uses both argument-level and method-level constraints.

### 5.4. Note on reactive request body types

~~~java
public Mono<Void> create(
        @Valid @RequestBody Mono<CreateItemRequest> body) {

    return body.flatMap(service::save).then();
}
~~~

This is a fragment; validation for `Mono<CreateItemRequest>` occurs when the request body publisher is subscribed to, and errors can flow through the reactive chain. Do not call `subscribe()` manually to "make validation run." In the runnable lesson project, the controller uses the DTO directly to clearly show exception mapping before the handler body.

## 6. Classifying input request errors

| Scenario | Where does it occur? | Common exception | Recommended HTTP contract |
| --- | --- | --- | --- |
| POST without body when `required=true` | Argument resolver | `ServerWebInputException` | 400 `INVALID_BODY` |
| Malformed JSON | Decoder/codec | `ServerWebInputException` (wrapping decoding error) | 400 `INVALID_BODY` |
| Valid JSON, blank `name` field | Bean Validation | `WebExchangeBindException` | 400 `VALIDATION_FAILED` |
| Valid JSON, `quantity=0` | Bean Validation | `WebExchangeBindException` | 400 `VALIDATION_FAILED` |
| Path `amount=0` with `@Min(1)` | Method validation | `HandlerMethodValidationException` | 400 `METHOD_VALIDATION_FAILED` |
| Unsupported Content-Type | Message reader/content negotiation | `UnsupportedMediaTypeStatusException` | 415, optionally ProblemDetail |
| Resource ID does not exist | Service/lookup | Domain not-found exception | 404 `ITEM_NOT_FOUND` |
| DB/gateway unavailable | Service/infrastructure | Timeout, connection error, etc. | 5xx or 503 with safe detail |
| Unprocessable business state | Business rule | Domain validation | 409 or 422 per contract |

These are **common categories**; exact error mapping depends on Spring/Boot configuration and the application's exception handler. Do not write tests requiring a specific internal exception type when the goal is purely protecting HTTP semantics; however, separate exception-type tests at the service/controller layer can catch mapping regressions.

## 7. What is ProblemDetail?

`ProblemDetail` is Spring Framework's abstraction for representing HTTP errors per **RFC 9457 (Problem Details for HTTP APIs)**. When serialized in a REST API, the response typically has media type `application/problem+json`.

Example:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json

{
  "type": "https://example.org/problems/validation-failed",
  "title": "Validation failed",
  "status": 400,
  "detail": "Request validation failed",
  "instance": "/api/demo/items",
  "code": "VALIDATION_FAILED",
  "errors": [
    {"field": "name", "message": "must not be blank"},
    {"field": "quantity", "message": "must be greater than or equal to 1"}
  ]
}
~~~

`example.org` is a domain reserved for documentation examples; production must use the API's official namespace and error documentation.

### 7.1. Meaning of the five standard fields

| Field | Type | Role |
| --- | --- | --- |
| `type` | URI | Identifies the **problem type**; may point to documentation |
| `title` | string | Short, stable human-readable summary of the problem type |
| `status` | number | HTTP status of the error, e.g., 400/404/500 |
| `detail` | string | Specific explanation of the error, safe for clients |
| `instance` | URI-reference | Identifies the request occurrence/path or error incident ID |

Per the RFC, some fields may be omitted depending on the producer; do not assume every ProblemDetail in every framework includes all five fields unless the API contract specifies it. In this lesson's project example, we **deliberately set all five** for stable tests.

### 7.2. Extension fields

Spring `ProblemDetail` provides `setProperty(String, Object)` to attach extension properties. With the Jackson mixin registered by Spring, these properties can appear at the JSON top level:

~~~java
ProblemDetail problem =
    ProblemDetail.forStatusAndDetail(
        HttpStatus.BAD_REQUEST, "Request validation failed");

problem.setProperty("code", "VALIDATION_FAILED");
problem.setProperty("errors", List.of(
    Map.of("field", "name", "message", "must not be blank")
));
~~~

This example is a fragment needing imports for `ProblemDetail`, `HttpStatus`, `List`, and `Map`. Never stuff the raw `BindingResult` or exception object into `properties`; they contain complex structures, rejected values, and potentially sensitive data.

### 7.3. `type` is not an HTTP status

Many APIs mistakenly set `type="400"` or `"VALIDATION_FAILED"` without a meaningful URI. A stable design uses categorizing URIs:

~~~text
https://example.org/problems/validation-failed
https://example.org/problems/invalid-body
https://example.org/problems/method-validation-failed
https://example.org/problems/item-not-found
https://example.org/problems/internal-error
~~~

The `code` is a dedicated field for frontend branching logic. `title` is for readers, `detail` is localized/tailored to the specific occurrence, and `type` identifies the problem category.

### 7.4. HTTP status and status field must be consistent

A dangerous response is HTTP 200 with body `{"status":400,...}`. Clients, proxies, tracing, and retries generally rely on the actual HTTP status, not just the JSON body.

Tests must verify **both** `.expectStatus().isBadRequest()` and `.jsonPath("$.status").isEqualTo(400)`, while also checking Content-Type. Never assert only `$.status=400`.

## 8. Default and custom ProblemDetail mechanisms

Spring Framework supports `ErrorResponse`, `ErrorResponseException`, `ProblemDetail`, and `ResponseEntityExceptionHandler`. Spring Boot WebFlux can enable ProblemDetail error handling via:

~~~properties
spring.webflux.problemdetails.enabled=true
~~~

Spring Boot 4.0 documentation describes this property to auto-configure built-in error handling in problem format. When a custom business schema is needed, a `@RestControllerAdvice` can be added for specific exceptions.

If Boot already provides advice from `ResponseEntityExceptionHandler` with default ordering, custom advice for the same exceptions should take precedence, for example:

~~~java
@RestControllerAdvice
@Order(Ordered.HIGHEST_PRECEDENCE)
public class ApiProblemHandler {
    // @ExceptionHandler for error types that the API wants to customize.
}
~~~

This is a fragment; the runnable project provides the full handler. Never register a high-priority catch-all `@ExceptionHandler(Exception.class)` that turns every error into status 400; doing so hides 404/415/500 and corrupts monitoring.

Another option is extending `ResponseEntityExceptionHandler` and overriding methods for built-in errors. Choose **one consistent strategy**, understand advice ordering, and test real HTTP outputs before deploying.

## 9. Designing safe field error responses

When Bean Validation fails, `WebExchangeBindException` contains a `BindingResult` with lists of `FieldError` and `ObjectError`. Never serialize the exception or rejected object directly to clients.

Mapping example:

~~~java
List<Map<String, String>> errors =
    exception.getFieldErrors().stream()
        .map(error -> Map.of(
            "field", error.getField(),
            "message",
            error.getDefaultMessage() == null
                ? "invalid"
                : error.getDefaultMessage()))
        .toList();
~~~

This is a fragment needing `exception` of type `WebExchangeBindException` and imports for `List`/`Map`. For inputs containing PII such as passwords, secrets, or tokens:
- Return only **the field name and a safe validation message**.
- Never return `rejectedValue`, raw JSON, SQL exceptions, or stack traces.
- Avoid returning messages containing user-entered content unless necessary.
- Stable codes like `NOT_BLANK` or `MIN_VALUE` can be used so frontends do not parse natural language.
- Validation messages may be localized; tests should not assert verbatim message text unless localization is part of the contract.

For the `errors` field, pick a uniform schema: a list of `{field, code, message}` or a field-to-errors map. Do not change the schema across endpoints. If one field has multiple errors, the list must support multiple entries for the same field.

### 9.1. Checking important content without brittle tests

Assert:
- HTTP status `400`.
- Content-Type compatible with `application/problem+json`.
- Fixed `type`.
- `status=400`.
- `code="VALIDATION_FAILED"`.
- `errors` is an array containing the relevant fields.
- `instance` matches the route when required by the contract.

Avoid asserting:
- Order of `errors` if the API does not guarantee one.
- Exact localized message text across all locales.
- Random timestamps or request IDs as fixed values.
- Stack traces or implementation class names.

In the demo project, we intentionally sort `errors` by field name for stable output, yet integration tests still prioritize schema and semantics.

## 10. Writing ProblemDetail assertions with WebTestClient

Complete API contract example:

~~~java
client.post()
    .uri("/api/demo/items")
    .contentType(MediaType.APPLICATION_JSON)
    .accept(MediaType.APPLICATION_PROBLEM_JSON)
    .bodyValue(new CreateItemRequest(" ", 0))
    .exchange()
    .expectStatus().isBadRequest()
    .expectHeader()
        .contentTypeCompatibleWith(
            MediaType.APPLICATION_PROBLEM_JSON)
    .expectBody()
    .jsonPath("$.type").isEqualTo(
        "https://example.org/problems/validation-failed")
    .jsonPath("$.title").isEqualTo("Validation failed")
    .jsonPath("$.status").isEqualTo(400)
    .jsonPath("$.detail").isEqualTo("Request validation failed")
    .jsonPath("$.instance").isEqualTo("/api/demo/items")
    .jsonPath("$.code").isEqualTo("VALIDATION_FAILED")
    .jsonPath("$.errors").isArray();
~~~

The snippet above requires an initialized `client` and the project's DTOs. Calling `.accept(MediaType.APPLICATION_PROBLEM_JSON)` is optional if the server always returns the problem content-type from the handler, yet it helps the test state the expected format clearly.

### 10.1. Checking that `$.errors` contains the needed fields

You can extract the raw body and parse it with `ObjectMapper`/Jackson or `JsonPath`, then assert against the set of field names rather than array indices. Fragment example:

~~~java
.expectBody()
.consumeWith(result -> {
    String json = new String(
        result.getResponseBody(), StandardCharsets.UTF_8);

    assertTrue(json.contains("\"field\":\"name\""));
    assertTrue(json.contains("\"field\":\"quantity\""));
});
~~~

The `contains` approach only fits small demos, since JSON can include whitespace or reorder fields. Production tests should parse JSON via `ObjectMapper` or JsonPath to inspect structure, e.g., using `JsonPath.read(json, "$.errors[*].field")` and asserting a `Set`. In the runnable project, the test simply asserts `errors` is an array to stay concise and avoid depending on field order.

### 10.2. Checking `application/problem+json`

`application/problem+json` is a distinct media type; do not assert only `application/json`. With `WebTestClient`:

~~~java
.expectHeader()
    .contentTypeCompatibleWith(
        MediaType.APPLICATION_PROBLEM_JSON)
~~~

Do not claim every default exception in every Boot application automatically gets the problem content-type unless support or a matching custom handler is enabled. The demo enables support and provides advice for a stable contract.

### 10.3. When to use typed `ProblemDetail`?

You can decode directly:

~~~java
client.post()
    .uri("/api/demo/items")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(new CreateItemRequest(" ", 0))
    .exchange()
    .expectStatus().isBadRequest()
    .expectBody(ProblemDetail.class)
    .value(problem -> {
        assertEquals(400, problem.getStatus());
        assertEquals("Validation failed", problem.getTitle());
    });
~~~

Note: deserialization and extension-field handling depend on the ObjectMapper/codecs configured on WebTestClient. If you only want to test the public JSON contract without coupling to Java types, JSONPath is usually clearer.

## 11. Testing missing body, malformed JSON, and Bean Validation failure

All three cases may return 400, yet `code` should differ:

~~~text
POST /api/demo/items
Content-Type: application/json

(no bytes)
    -> 400 INVALID_BODY
~~~

~~~text
POST /api/demo/items
Content-Type: application/json

{not-valid-json
    -> 400 INVALID_BODY
~~~

~~~text
POST /api/demo/items
Content-Type: application/json

{"name":" ","quantity":0}
    -> 400 VALIDATION_FAILED
~~~

How to distinguish them:
- No body: the argument resolver has no required data.
- Invalid JSON: the decoder cannot construct the DTO.
- Valid JSON, invalid constraints: the DTO was built, but Bean Validation failed.

If the frontend needs to display per-field errors, only `VALIDATION_FAILED` has per-field `errors`. For `INVALID_BODY`, accurate field errors do not exist because the DTO may not have been parsed; return an error code and a safe explanation.

### 11.1. Do not lump every error into 422

HTTP 400 suits malformed JSON and Bean Validation in many Spring APIs. 422 Unprocessable Content can be an agreed API policy for semantic validation, yet do not unilaterally change Spring's status assuming the frontend understands it.

The goal of testing is protecting a **specific contract**, not arguing that all validation errors must be 422. If your organization chooses 422, design exception mapping and status/body tests consistently.

## 12. Request-side and response-side "empty body" scenarios differ

| Perspective | What is being tested | Related API |
| --- | --- | --- |
| Request | Client sends no required body | `@RequestBody(required = true)` default |
| Request | Client sends JSON body with blank fields | `@NotBlank`, `@NotNull`, `@Min` |
| Request | Client sends JSON `{}` | Validation of required fields may fail |
| Response | Server returns 204 zero body | `ResponseEntity.noContent()` |
| Response | Server returns 200 zero body | `ResponseEntity.ok().build()` |
| Response | Server returns JSON `[]` | `Mono.just(List.of())` |
| Response | Server returns ProblemDetail | `ProblemDetail` + `application/problem+json` |

Do not use one "empty" test for both directions. `expectBody().isEmpty()` checks the **response body**, not whether the request body was sent properly.

## 13. Testing 404 and 500 errors without leaking information

An API typically needs two error categories beyond validation:
- `404`: resource absent; clients can adjust the ID or update UI state.
- `500`: internal error; clients should never receive SQL/connection details, stack traces, or operational data.

Both can use `ProblemDetail`:
- 404 `type=https://example.org/problems/item-not-found`, `code=ITEM_NOT_FOUND`, `status=404`.
- 500 `type=https://example.org/problems/internal-error`, `code=INTERNAL_ERROR`, `status=500`, generic safe `detail`.

Tests for 500 should verify:
1. HTTP status 5xx.
2. `Content-Type: application/problem+json`.
3. `$.status=500` and `$.code=INTERNAL_ERROR`.
4. Response **does not contain** the raw internal exception message.
5. Server-side correlation/trace exists for investigation without exposing raw errors to clients.

Do not use `.expectStatus().isOk()` for a failing method just because the controller used `onErrorResume(error -> Mono.empty())`: that turns errors into empty success responses and hides failures.

## 14. Types of tests to write

### 14.1. Service-level unit tests with StepVerifier

If a reactive service returns `Mono<Item>` or `Mono.empty()`, test the signals:

~~~java
StepVerifier.create(service.find("missing"))
    .verifyComplete();
~~~

Or on error:

~~~java
StepVerifier.create(service.create(invalid))
    .expectError(InvalidItemException.class)
    .verify();
~~~

These are fragments using illustrative service/exception types, not the complete API of the demo below. StepVerifier tests **publisher signals**; it does not yet confirm they are mapped by WebFlux to HTTP 400/404.

### 14.2. WebTestClient bound directly to a controller

~~~java
WebTestClient client = WebTestClient
    .bindToController(controller)
    .build();
~~~

Suitable for testing routes, handler mapping, serialization, and body semantics, though when testing validation/advice/dependencies you must register the corresponding config (`controllerAdvice`, validator, etc.). If you use `bindToController` and forget advice, ProblemDetail may differ from the application's contract.

### 14.3. Real HTTP server

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ApiContractTest {
    // WebTestClient.bindToServer() + baseUrl(local.server.port)
}
~~~

This starts a real Spring Boot context, runs configured codecs/validation/advice, and verifies requests/responses over HTTP. It requires no database or external service if the controller uses a deterministic demo service.

### 14.4. Testing through a production-like proxy

A local test does not guarantee headers/caching/compression/CORS/proxy error responses in production match identically. For real applications, add staging smoke tests through the ingress/API gateway to confirm:
- 204 is not given a fake JSON body by the proxy.
- ProblemDetail preserves its Content-Type.
- The reverse proxy does not rewrite 400/404 into generic HTML error pages.
- Correlation IDs remain present and do not leak secrets.
- Method validation and size limits remain intact.

## 15. Designing a test matrix before coding

| Test name | Request | Expected status | Body assertion |
| --- | --- | ---: | --- |
| `noContentHasEmptyPayload` | GET `/no-content` | 204 | `isEmpty()` |
| `okCanHaveEmptyPayload` | GET `/empty-ok` | 200 | `isEmpty()` |
| `emptyListIsJsonArrayNotEmptyBody` | GET `/empty-list` | 200 | JSON `[]` |
| `validItemReturnsCreatedJson` | POST valid JSON | 201 | `id`, `name`, `quantity`, Location |
| `invalidFieldsReturnProblemDetail` | POST blank name, 0 quantity | 400 | ProblemDetail `VALIDATION_FAILED`, errors array |
| `missingRequestBodyReturnsInvalidBody` | POST no body | 400 | ProblemDetail `INVALID_BODY` |
| `malformedJsonReturnsInvalidBody` | POST invalid JSON | 400 | ProblemDetail `INVALID_BODY` |
| `methodParameterConstraintReturnsProblemDetail` | GET `/quantity/0` | 400 | ProblemDetail `METHOD_VALIDATION_FAILED` |
| `missingResourceReturnsProblemDetail404` | GET `/missing` | 404 | ProblemDetail `ITEM_NOT_FOUND` |
| `internalErrorIsSanitized` | GET `/fault` | 500 | ProblemDetail `INTERNAL_ERROR`, no raw exception |
| `unsupportedMediaTypeReturns415` | POST `text/plain` | 415 | Do not assert custom body if undefined |

This is an intentionally minimal matrix. Production APIs using pagination, authentication, multipart, or streaming need dedicated scenarios; do not cram everything into a single "400 error" test.

## 16. Runnable project: Spring Boot 4.0.9 + Java 17 + WebFlux

The following demo runs without a database or cloud service. It focuses on testing **the HTTP contract** rather than persistence. The service generates IDs using `AtomicLong` so tests do not depend on fixed IDs, without persisting items: this is a simulated API for testing, not a production CRUD implementation.

### 16.1. Project structure

~~~text
webflux-problem-contract/
├── pom.xml
├── src/main/resources/application.properties
├── src/main/java/com/example/problem/
│   ├── ProblemContractApplication.java
│   ├── CreateItemRequest.java
│   ├── ItemView.java
│   ├── ItemNotFoundException.java
│   ├── DemoItemService.java
│   ├── DemoController.java
│   └── ApiProblemHandler.java
└── src/test/java/com/example/problem/
    └── ApiContractIntegrationTest.java
~~~

### 16.2. `pom.xml`

Uses Spring Boot 4.0.9 and Java 17+; the validation starter provides the Jakarta Validation provider. The WebFlux test starter and JUnit 5 are in `test` scope.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.9</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>webflux-problem-contract</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Do not add `spring-boot-starter-webmvc` because this lesson tests Spring WebFlux. Having both MVC and WebFlux starters can cause Boot auto-configuration to choose a servlet web application; include only the needed stack.

### 16.3. `application.properties`

~~~properties
spring.application.name=webflux-problem-contract
spring.webflux.problemdetails.enabled=true
~~~

The property enables Boot WebFlux ProblemDetail handling for built-in framework-supported errors. Custom `ApiProblemHandler` takes precedence for API errors requiring a stable schema. Never enable config that exposes stack traces and exception messages in production responses.

### 16.4. `ProblemContractApplication.java`

~~~java
package com.example.problem;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProblemContractApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProblemContractApplication.class, args);
    }
}
~~~

### 16.5. `CreateItemRequest.java`

~~~java
package com.example.problem;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record CreateItemRequest(
    @NotBlank @Size(max = 60) String name,
    @NotNull @Min(1) Integer quantity
) {}
~~~

Field `Integer` instead of `int` allows `@NotNull` to detect missing JSON fields. `quantity=0` is caught by `@Min(1)`. If `name=null`, `@NotBlank` also fails.

### 16.6. `ItemView.java`

~~~java
package com.example.problem;

public record ItemView(
    String id,
    String name,
    int quantity
) {}
~~~

The output DTO is separate from the request DTO so persistence can evolve later without forcing response schema changes.

### 16.7. `ItemNotFoundException.java`

~~~java
package com.example.problem;

public class ItemNotFoundException extends RuntimeException {

    public ItemNotFoundException(String id) {
        super("Item not found: " + id);
    }
}
~~~

An exception representing business not-found. In the API handler, do not return the raw exception message to the client: the message may contain IDs or internal data; replace it with a standardized message.

### 16.8. `DemoItemService.java`

~~~java
package com.example.problem;

import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class DemoItemService {

    private final AtomicLong sequence = new AtomicLong();

    public Mono<ItemView> create(CreateItemRequest request) {
        return Mono.fromSupplier(() ->
            new ItemView(
                Long.toString(sequence.incrementAndGet()),
                request.name().trim(),
                request.quantity()));
    }

    public Mono<ItemView> missing() {
        return Mono.error(new ItemNotFoundException("unknown"));
    }

    public Mono<ItemView> fail() {
        return Mono.error(new IllegalStateException(
            "internal connection endpoint: secret-location"));
    }
}
~~~

`Mono.fromSupplier` creates the item when the Publisher is subscribed to; this code manipulates memory only, with no blocking I/O. Endpoints `/missing` and `/fault` intentionally simulate errors to test error contracts. Do not use the simulated internal error string as an API response.

### 16.9. `DemoController.java`

~~~java
package com.example.problem;

import java.net.URI;
import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/demo")
public class DemoController {

    private final DemoItemService service;

    public DemoController(DemoItemService service) {
        this.service = service;
    }

    @GetMapping("/no-content")
    public Mono<ResponseEntity<Void>> noContent() {
        return Mono.just(
            ResponseEntity.noContent().<Void>build());
    }

    @GetMapping("/empty-ok")
    public Mono<ResponseEntity<Void>> emptyOk() {
        return Mono.just(ResponseEntity.ok().<Void>build());
    }

    @GetMapping(
        value = "/empty-list",
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<List<ItemView>> emptyList() {
        return Mono.just(List.of());
    }

    @PostMapping(
        value = "/items",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<ItemView>> create(
            @Valid @RequestBody CreateItemRequest request) {

        return service.create(request)
            .map(item ->
                ResponseEntity
                    .created(URI.create(
                        "/api/demo/items/" + item.id()))
                    .body(item));
    }

    @GetMapping(
        value = "/quantity/{amount}",
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Map<String, Integer>> quantity(
            @PathVariable @Min(1) int amount) {

        return Mono.just(Map.of("amount", amount));
    }

    @GetMapping("/missing")
    public Mono<ItemView> missing() {
        return service.missing();
    }

    @GetMapping("/fault")
    public Mono<ItemView> fault() {
        return service.fail();
    }
}
~~~

There is no `@Validated` at the class level; `@Min(1)` on the path variable uses built-in method validation. `@Valid @RequestBody` on the record uses object validation. Do not call `.block()` or `.subscribe()` in the controller; WebFlux manages subscription and response lifecycle.

### 16.10. `ApiProblemHandler.java`

~~~java
package com.example.problem;

import java.net.URI;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.bind.support.WebExchangeBindException;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.ServerWebInputException;

@RestControllerAdvice
@Order(Ordered.HIGHEST_PRECEDENCE)
public class ApiProblemHandler {

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<ProblemDetail> beanValidation(
            WebExchangeBindException exception,
            ServerWebExchange exchange) {

        List<Map<String, String>> errors =
            exception.getFieldErrors().stream()
                .map(error -> Map.of(
                    "field", error.getField(),
                    "message",
                    error.getDefaultMessage() == null
                        ? "invalid"
                        : error.getDefaultMessage()))
                .sorted(Comparator.comparing(
                    error -> error.get("field")))
                .toList();

        ResponseEntity<ProblemDetail> response =
            problem(
                exchange,
                HttpStatus.BAD_REQUEST,
                "VALIDATION_FAILED",
                "Validation failed",
                "Request validation failed");

        response.getBody().setProperty("errors", errors);
        return response;
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<ProblemDetail> methodValidation(
            HandlerMethodValidationException exception,
            ServerWebExchange exchange) {

        return problem(
            exchange,
            HttpStatus.BAD_REQUEST,
            "METHOD_VALIDATION_FAILED",
            "Method validation failed",
            "A request parameter violates a constraint");
    }

    @ExceptionHandler(ServerWebInputException.class)
    public ResponseEntity<ProblemDetail> invalidBody(
            ServerWebInputException exception,
            ServerWebExchange exchange) {

        return problem(
            exchange,
            HttpStatus.BAD_REQUEST,
            "INVALID_BODY",
            "Invalid request body",
            "The JSON request body is missing or unreadable");
    }

    @ExceptionHandler(ItemNotFoundException.class)
    public ResponseEntity<ProblemDetail> notFound(
            ItemNotFoundException exception,
            ServerWebExchange exchange) {

        return problem(
            exchange,
            HttpStatus.NOT_FOUND,
            "ITEM_NOT_FOUND",
            "Item not found",
            "The requested item does not exist");
    }

    @ExceptionHandler(IllegalStateException.class)
    public ResponseEntity<ProblemDetail> internalError(
            IllegalStateException exception,
            ServerWebExchange exchange) {

        // In production, log safely with a request/trace ID on the server.
        // Do not return exception.getMessage() to the browser.
        return problem(
            exchange,
            HttpStatus.INTERNAL_SERVER_ERROR,
            "INTERNAL_ERROR",
            "Internal server error",
            "Unexpected server failure");
    }

    private static ResponseEntity<ProblemDetail> problem(
            ServerWebExchange exchange,
            HttpStatus status,
            String code,
            String title,
            String detail) {

        ProblemDetail pd =
            ProblemDetail.forStatusAndDetail(status, detail);

        pd.setType(URI.create(
            "https://example.org/problems/"
                + code.toLowerCase(Locale.ROOT)
                    .replace('_', '-')));
        pd.setTitle(title);
        pd.setInstance(URI.create(
            exchange.getRequest().getPath().value()));
        pd.setProperty("code", code);

        return ResponseEntity.status(status)
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(pd);
    }
}
~~~

Explanation:
1. The advice handles `WebExchangeBindException` before the more general handler for `ServerWebInputException` because the two types share an inheritance relationship; Spring chooses the handler by the most specific exception type.
2. `HandlerMethodValidationException` is handled separately to avoid conflating it with body errors.
3. `ProblemDetail.forStatusAndDetail` sets `status` and `detail`; the code then sets type/title/instance.
4. `response.getBody().setProperty("errors", ...)` is safe here because the `problem` method always creates a fresh `ProblemDetail` body; in production architectures you can extract a helper returning `ProblemDetail` first and then build the ResponseEntity.
5. `@Order(Ordered.HIGHEST_PRECEDENCE)` gives the custom handler priority over Boot's auto-configured default advice for overlapping exception types.
6. Uncustomized errors, such as unsupported Content-Type 415, can still be handled by Spring Boot's default error handling per config.
7. Server 500 returns only a generic message, never the raw exception message containing endpoint/secret information.
8. `instance` uses the request path, suitable for a demo; in real APIs, consider a dedicated trace ID and avoid putting PII/secrets from the URL into the error payload.

## 17. HTTP integration tests with WebTestClient

The test starts Spring Boot on a random port to exercise all validation, codecs, advice, and REST routes; it does not mock the controller alone.

### 17.1. `ApiContractIntegrationTest.java`

~~~java
package com.example.problem;

import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ApiContractIntegrationTest {

    @Value("${local.server.port}")
    int port;

    private WebTestClient http() {
        return WebTestClient.bindToServer()
            .baseUrl("http://localhost:" + port)
            .responseTimeout(Duration.ofSeconds(5))
            .build();
    }

    @Test
    void noContentHasEmptyPayload() {
        http().get()
            .uri("/api/demo/no-content")
            .exchange()
            .expectStatus().isNoContent()
            .expectBody().isEmpty();
    }

    @Test
    void okCanHaveEmptyPayload() {
        http().get()
            .uri("/api/demo/empty-ok")
            .exchange()
            .expectStatus().isOk()
            .expectBody().isEmpty();
    }

    @Test
    void emptyListIsJsonArrayNotEmptyBody() {
        http().get()
            .uri("/api/demo/empty-list")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON)
            .expectBody().json("[]");
    }

    @Test
    void validItemReturnsCreatedJson() {
        http().post()
            .uri("/api/demo/items")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(
                new CreateItemRequest("Notebook", 3))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader()
                .valueMatches("Location",
                    "/api/demo/items/[0-9]+")
            .expectBody()
                .jsonPath("$.id").isNotEmpty()
                .jsonPath("$.name").isEqualTo("Notebook")
                .jsonPath("$.quantity").isEqualTo(3);
    }

    @Test
    void invalidFieldsReturnProblemDetail() {
        http().post()
            .uri("/api/demo/items")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_PROBLEM_JSON)
            .bodyValue(new CreateItemRequest(" ", 0))
            .exchange()
            .expectStatus().isBadRequest()
            .expectHeader()
                .contentTypeCompatibleWith(
                    MediaType.APPLICATION_PROBLEM_JSON)
            .expectBody()
                .jsonPath("$.type").isEqualTo(
                    "https://example.org/problems/validation-failed")
                .jsonPath("$.title").isEqualTo("Validation failed")
                .jsonPath("$.status").isEqualTo(400)
                .jsonPath("$.detail").isEqualTo(
                    "Request validation failed")
                .jsonPath("$.instance").isEqualTo(
                    "/api/demo/items")
                .jsonPath("$.code").isEqualTo(
                    "VALIDATION_FAILED")
                .jsonPath("$.errors").isArray();
    }

    @Test
    void missingRequestBodyReturnsInvalidBody() {
        http().post()
            .uri("/api/demo/items")
            .contentType(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isBadRequest()
            .expectHeader()
                .contentTypeCompatibleWith(
                    MediaType.APPLICATION_PROBLEM_JSON)
            .expectBody()
                .jsonPath("$.status").isEqualTo(400)
                .jsonPath("$.code").isEqualTo(
                    "INVALID_BODY");
    }

    @Test
    void malformedJsonReturnsInvalidBody() {
        http().post()
            .uri("/api/demo/items")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{not-valid-json")
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
                .jsonPath("$.code").isEqualTo(
                    "INVALID_BODY");
    }

    @Test
    void methodParameterConstraintReturnsProblemDetail() {
        http().get()
            .uri("/api/demo/quantity/0")
            .exchange()
            .expectStatus().isBadRequest()
            .expectHeader()
                .contentTypeCompatibleWith(
                    MediaType.APPLICATION_PROBLEM_JSON)
            .expectBody()
                .jsonPath("$.status").isEqualTo(400)
                .jsonPath("$.code").isEqualTo(
                    "METHOD_VALIDATION_FAILED");
    }

    @Test
    void missingResourceReturnsProblemDetail404() {
        http().get()
            .uri("/api/demo/missing")
            .exchange()
            .expectStatus().isNotFound()
            .expectHeader()
                .contentTypeCompatibleWith(
                    MediaType.APPLICATION_PROBLEM_JSON)
            .expectBody()
                .jsonPath("$.status").isEqualTo(404)
                .jsonPath("$.code").isEqualTo(
                    "ITEM_NOT_FOUND")
                .jsonPath("$.instance").isEqualTo(
                    "/api/demo/missing");
    }

    @Test
    void internalErrorIsSanitized() {
        http().get()
            .uri("/api/demo/fault")
            .exchange()
            .expectStatus().is5xxServerError()
            .expectHeader()
                .contentTypeCompatibleWith(
                    MediaType.APPLICATION_PROBLEM_JSON)
            .expectBody()
            .consumeWith(result -> {
                byte[] bytes = result.getResponseBody();

                assertNotNull(bytes);

                String body = new String(
                    bytes, StandardCharsets.UTF_8);

                assertFalse(body.contains("secret-location"));
                assertFalse(body.contains("connection endpoint"));
            });
    }

    @Test
    void unsupportedMediaTypeReturns415() {
        http().post()
            .uri("/api/demo/items")
            .contentType(MediaType.TEXT_PLAIN)
            .bodyValue("hello")
            .exchange()
            .expectStatus().isEqualTo(415);
    }
}
~~~

**Notes when reviewing tests:**
- Random port avoids port 8080 conflicts in CI.
- `expectBody().isEmpty()` verifies the body has no content.
- `emptyList` uses `.json("[]")`, not `.isEmpty()`.
- Error body tests verify status + schema + problem content-type.
- 201 checks `Location` with a pattern because IDs increment dynamically, rather than asserting a hardcoded ID.
- Checks that server 500 **does not leak** internal error details.
- The 415 test asserts only status because the default error structure is not the focus of the custom handler.
- No real DB is used, so tests guard the HTTP contract without proving transactional correctness or connection pool performance.

### 17.2. Testing an empty body with the typed API

If no custom error object is needed:

~~~java
client.delete()
    .uri("/api/items/123")
    .exchange()
    .expectStatus().isNoContent()
    .expectBody().isEmpty();
~~~

This is a fragment for an API with a matching DELETE endpoint, **not a route in the section 16 demo**. Unlike `expectBody(Void.class)`, `isEmpty()` explicitly states the 0-byte requirement.

### 17.3. Testing a service exception without starting HTTP

~~~java
Mono<ItemView> failing = Mono.error(
    new IllegalArgumentException("invalid quantity"));

StepVerifier.create(failing)
    .expectError(IllegalArgumentException.class)
    .verify();
~~~

This is a JUnit fragment with Reactor Test. Use `StepVerifier` to verify signals in the service; use `WebTestClient` to verify `IllegalArgumentException` is translated by the HTTP mapper into the proper status/ProblemDetail. The two test layers do not replace each other.

## 18. Run commands and curl checks

Requirements:
- JDK 17+ and Maven.
- Network access to download Maven dependencies the first time.
- Port 8080 available if running with default settings.

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

### 18.1. 204 with no body

~~~bash
curl -i http://localhost:8080/api/demo/no-content
~~~

Expect status `204 No Content`, with no JSON body. With `curl -i`, you still see headers (those are not the body).

### 18.2. 200 zero-byte body

~~~bash
curl -i http://localhost:8080/api/demo/empty-ok
~~~

Expect status `200 OK`, 0-byte body. Do not infer `null` or `[]`.

### 18.3. 200 empty JSON list

~~~bash
curl -i http://localhost:8080/api/demo/empty-list
~~~

Body:

~~~json
[]
~~~

### 18.4. Creating a valid item

Linux/macOS shell:

~~~bash
curl -i -X POST http://localhost:8080/api/demo/items \
  -H "Content-Type: application/json" \
  -d '{"name":"Notebook","quantity":3}'
~~~

Windows CMD:

~~~bat
curl -i -X POST http://localhost:8080/api/demo/items ^
  -H "Content-Type: application/json" ^
  -d "{\"name\":\"Notebook\",\"quantity\":3}"
~~~

Illustrative response; the ID is generated when the request is subscribed to:

~~~http
HTTP/1.1 201 Created
Location: /api/demo/items/1
Content-Type: application/json

{"id":"1","name":"Notebook","quantity":3}
~~~

### 18.5. Validation 400 ProblemDetail

~~~bash
curl -i -X POST http://localhost:8080/api/demo/items \
  -H "Content-Type: application/json" \
  -H "Accept: application/problem+json" \
  -d '{"name":" ","quantity":0}'
~~~

Expect `application/problem+json`, `status:400`, `code:VALIDATION_FAILED`, with `errors` for `name` and `quantity`. Field error order may be sorted by name by the demo handler.

### 18.6. Missing body

~~~bash
curl -i -X POST http://localhost:8080/api/demo/items \
  -H "Content-Type: application/json"
~~~

Expect 400 `INVALID_BODY`.

### 18.7. Method validation

~~~bash
curl -i http://localhost:8080/api/demo/quantity/0
~~~

Expect 400 `METHOD_VALIDATION_FAILED`. For `/quantity/2`, the request is valid and returns JSON `{"amount":2}`.

### 18.8. Domain 404 and 500 errors

~~~bash
curl -i http://localhost:8080/api/demo/missing
curl -i http://localhost:8080/api/demo/fault
~~~

404 returns `ITEM_NOT_FOUND`; 500 returns `INTERNAL_ERROR` and a safe `detail`. Never returns the string `internal connection endpoint: secret-location`.

## 19. Alternative approach: Test-first before writing handlers

A practical way to learn is writing contract tests first:

1. Define standard error codes: `INVALID_BODY`, `VALIDATION_FAILED`, `METHOD_VALIDATION_FAILED`, `ITEM_NOT_FOUND`, `INTERNAL_ERROR`.
2. Define the corresponding HTTP statuses.
3. Choose `application/problem+json`.
4. Specify standard fields always present in the response.
5. Specify stable extension `code`, with `errors` appearing only for field validation.
6. Create status/header/JSONPath tests.
7. Implement controller, service, and advice to make tests pass.
8. Add security tests ensuring raw exceptions are not leaked.
9. Separate tests at the business service and HTTP layers so bugs surface at the right place.

Avoid writing advice first and snapshotting the entire JSON into one big test. Snapshots break easily when Jackson changes field ordering or messages are localized; field-by-field assertions clarify the contract.

## 20. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Asserting only 204 without checking body | Erroneous body can slip through | `expectBody().isEmpty()` |
| Treating `[]` as a 0-byte body | Test does not distinguish collection from no-content | Assert JSON `[]` |
| Assuming `Mono.empty()` always means HTTP 204 | Ambiguous contract | Return `ResponseEntity.noContent()` explicitly |
| Calling `expectBody(Void.class)` thinking it asserts 0 bytes | May simply ignore content | Use raw-body `isEmpty()` |
| Asserting only 400 for all invalid requests | Fails to detect mis-mapped error types | Assert ProblemDetail `type/code` |
| Forgetting `spring-boot-starter-validation` | Constraints may not execute | Add validation provider and integration tests |
| Forgetting `@Valid` on body DTO | Bean Validation is not triggered as intended | Use `@Valid @RequestBody` |
| Adding `@Validated` to controller without understanding AOP | Different exception type than expected | Choose built-in method validation and test it |
| Handling only `WebExchangeBindException` | Misses method-level constraints | Also handle `HandlerMethodValidationException` |
| Returning field errors with rejectedValue | Leaks passwords/tokens/PII | Return only safe code/field/message |
| Returning `exception.getMessage()` on 500 | Leaks stack/endpoints/DB details | Return generic detail, log safely on server |
| HTTP 200 with ProblemDetail status 400 | Breaks monitoring/retries/frontends | Synchronize HTTP status and body status |
| Not setting `Content-Type` on custom problems | Clients misinterpret JSON schema | `MediaType.APPLICATION_PROBLEM_JSON` |
| Not distinguishing missing body from validation | Frontend renders field errors incorrectly | Dedicated `INVALID_BODY` |
| Asserting exact localized field error messages | Tests break on internationalization | Assert code/field; assert messages only when contracted |
| Asserting uncontracted error ordering | Flaky CI | Compare sets of field errors |
| `onErrorResume(error -> Mono.empty())` | Masks validation/DB failures as empty success | Map each error type properly |
| Using `MockMvc` for WebFlux without checking stack | Tests wrong runtime/framework | Use `WebTestClient` |
| Using only `bindToController` and forgetting advice | Problem response differs from production | Register advice or run Boot integration tests |
| Asserting only JSON body, omitting HTTP status/headers | Contract is not fully protected | Assert status, media type, and body |
| Using HTTP 204 yet sending JSON `{}` | Violates no-content semantics | Send no response body with 204 |
| Mocking codecs/validators in unit tests | Never tests real request parsing | Add HTTP integration tests |

## 21. Debugging failed validation/ProblemDetail tests

### 21.1. Test expects 400 but receives 201

Check:
- Is `spring-boot-starter-validation` on the classpath?
- Does the request DTO have `jakarta.validation.Valid` on the controller parameter?
- Are constraints imported from `jakarta.validation.constraints` or an inactive package?
- Is the test data actually invalid? `@Min(1)` still permits `quantity=1`.
- Is any code using `onErrorResume` to turn errors into a success fallback?
- Is the controller using a different DTO than the one annotated?

### 21.2. Test expects `VALIDATION_FAILED` but receives `INVALID_BODY`

The JSON may not have decoded into the DTO: syntax error, wrong JSON type, or missing required body. In those cases `ServerWebInputException` is more accurate than `WebExchangeBindException`.

Use WebTestClient's raw request/response to verify the JSON sent by the client. Do not change advice to turn every `ServerWebInputException` into `VALIDATION_FAILED`, as that erases the distinction in error origin.

### 21.3. Test expects `HandlerMethodValidationException` but receives a different error

Check:
- Is the constraint placed directly on the method parameter?
- Is `@Validated` at the class level causing Spring to choose AOP method validation?
- Is Spring Boot's validation starter present?
- Can the path variable parse into `int`, or does type conversion fail before validation?
- Which Spring Framework version is in use?

Method validation can also be affected by exception handling configuration and controller proxying. The best approach is testing **the HTTP contract** after the Boot context starts, alongside unit/integration tests for exception types when classification is a requirement.

### 21.4. `Content-Type` is not `application/problem+json`

Check:
- Is a custom handler returning a `Map` or plain DTO and leaving `application/json`?
- Is `spring.webflux.problemdetails.enabled=true` enabled?
- Is the high-precedence advice registered?
- Was the exception caught by another handler?
- Did the request send an incompatible restrictive Accept header?
- Did a gateway/ingress alter the response content-type?

If the API advertises ProblemDetail, test the actual media type rather than looking only at JSON fields.

### 21.5. 204 response is not empty as expected

Check:
- Does the controller return `ResponseEntity.noContent().build()`?
- Is a filter/global error handler appending a JSON response body?
- Did the test actually hit the intended route?
- Is a gateway/error page injecting a body outside WebFlux?
- Are header lines from `curl -i` output being mistaken for a response body?

In HTTP tests, `.expectBody().isEmpty()` is clearer proof than checking status 204 alone.

## 22. Production API checklist

- [ ] Each endpoint clearly specifies 200, 201, 202, 204, 400, 404, 409, 415, 422, and 5xx where meaningful.
- [ ] No-content endpoints return an explicit status and a truly 0-byte body.
- [ ] Empty collections return `[]` per contract, never accidentally turning into 204.
- [ ] Required JSON bodies are tested when missing and when malformed.
- [ ] `@Valid` and a Jakarta Validation provider are configured.
- [ ] Argument validation and method validation are handled distinctly.
- [ ] Error codes are stable and independent of message text.
- [ ] Error HTTP status equals `ProblemDetail.status`.
- [ ] ProblemDetail responses have `application/problem+json`.
- [ ] `type` uses a suitably versioned/documented URI namespace.
- [ ] `instance` does not leak secrets from query/path.
- [ ] Rejected values, raw exceptions, stack traces, and internal URLs are never returned.
- [ ] Field `errors` has a clear schema supporting multiple errors per field.
- [ ] A localization policy exists if clients display messages.
- [ ] Custom `@RestControllerAdvice` does not swallow all 404/415/500 responses.
- [ ] 400 tests exist for invalid DTOs, missing body, malformed JSON, and method-level constraints.
- [ ] Tests exist for 201 + Location header, 204 no-body, and 200 empty-list.
- [ ] Tests exist for business 404 and sanitized 500.
- [ ] HTTP integration tests start an actual WebFlux context.
- [ ] Service-level Publisher signal tests exist when reactive logic is complex.
- [ ] Server-side trace/correlation IDs exist for debugging without leaking PII.
- [ ] Staging smoke tests run through ingress/API gateway.
- [ ] Test scenarios avoid depending on field order and message localization unless contracted.

## 23. Practice exercises

**Exercise 1 – 204 vs 200.** Create two endpoints returning no payload, one 204 and one 200. Use `expectBody().isEmpty()` for both and verify the differing statuses.

**Exercise 2 – JSON list.** Return `Mono.just(List.of())` and verify body `[]`; demonstrate why `isEmpty()` is inappropriate.

**Exercise 3 – DTO validation.** Add `@Email` to `contact` and `@Size` to `name`; send invalid data and verify field errors without exposing rejectedValue.

**Exercise 4 – Missing body.** Send a POST without a body and verify `INVALID_BODY`.

**Exercise 5 – Malformed JSON.** Send syntactically invalid JSON and verify the API does not conflate it with Bean Validation.

**Exercise 6 – Method validation.** Put `@Min(1)` on a path variable and test `/quantity/0` vs `/quantity/1` with different statuses.

**Exercise 7 – Standard ProblemDetail.** Verify `type/title/status/detail/instance` and extension `code` using JSONPath.

**Exercise 8 – Media type.** Omit Content-Type or send `text/plain` to a JSON-only endpoint; verify 415 or behavior per the chosen contract.

**Exercise 9 – Domain 404.** Create a dedicated domain exception for missing items; assert 404 + `ITEM_NOT_FOUND`.

**Exercise 10 – Security.** Make the service throw an exception containing simulated SQL credentials; test that the response does not contain that string.

**Exercise 11 – Localization.** Run requests with different `Accept-Language` headers; test stable error codes and messages per the supported policy.

**Exercise 12 – Functional endpoints.** Write a RouterFunction returning `ServerResponse.noContent()` and a ProblemDetail error handler; use WebTestClient bound to the router to verify parity with the annotated controller.

**Exercise 13 – StepVerifier.** In the service, write empty Mono and Mono.error; verify individual signals before testing HTTP mapping.

**Exercise 14 – Contract regression.** Change 204 to 200 in the controller and observe the test fail; change code `VALIDATION_FAILED` to `INVALID_BODY` and observe the JSONPath failure.

**Exercise 15 – Staging.** Run HTTP tests through a real gateway, confirming 204 stays 0 bytes and ProblemDetail retains its Content-Type.

## 24. Official references

1. Spring Framework – WebTestClient, No Content, JSON body, and streaming responses: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
2. Spring Framework – WebFlux controller validation: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html
3. Spring Framework – `@RequestBody` and Bean Validation: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html
4. Spring Framework – Error Responses/ProblemDetail in WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html
5. Spring Framework – `ProblemDetail` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ProblemDetail.html
6. Spring Boot 4.0 – WebFlux Problem Details configuration: https://docs.spring.io/spring-boot/4.0/reference/web/reactive.html
7. Spring Boot 4.0.9 – Managed dependency coordinates (WebFlux, Validation, Test): https://docs.spring.io/spring-boot/4.0/appendix/dependency-versions/coordinates.html
8. RFC 9457 – Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457
9. HTTP Semantics – RFC 9110 (204/400/404/415/500): https://www.rfc-editor.org/rfc/rfc9110
10. Jakarta Bean Validation: https://jakarta.ee/specifications/bean-validation/
11. Reactor Test/StepVerifier: https://projectreactor.io/docs/core/release/reference/testing.html

**Final self-assessment:** How does HTTP 204 differ from HTTP 200 with a 0-byte body? Is `[]` considered an empty body? Why can `@Valid @RequestBody` throw `WebExchangeBindException` while `@Min` on a path variable uses `HandlerMethodValidationException`? When a request lacks a body, is there a field validation result yet? Must ProblemDetail `status` and HTTP status match? Which test protects internal data from being leaked? If you can answer these and run the tests in the project, you can accurately test empty bodies, validation, and ProblemDetail in WebFlux.
