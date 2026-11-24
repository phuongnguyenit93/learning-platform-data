# Verifying HTTP Contracts: Status, Headers, JSON, and Error Messages

A valuable HTTP integration test does more than verify that an endpoint returns `200 OK`. An API can return the right status code yet have the wrong `Content-Type`, omit `Cache-Control`, drop a correlation ID, rename a JSON field, miscalculate totals, or accidentally expose a stack trace in an error message. Conversely, a JSON body might look right in a unit test while a real request fails due to routing, HTTP message converters, servlet filters, server configuration, or exception handlers.

An **HTTP contract** is the set of behaviors a client is entitled to expect from an endpoint: **method + path + input**, status codes, headers, representation/body, error payloads, and operational rules (caching, authentication, idempotency, pagination, etc.). This lesson shows how to verify key aspects with clear assertions while highlighting the boundaries of each testing level.

The primary examples use **Java 17+, Spring Boot 3.5.x, Spring MVC, JUnit Jupiter 5, Jackson, and `TestRestTemplate`** with `@SpringBootTest(webEnvironment = RANDOM_PORT)` to call a real HTTP server on localhost. We keep real controllers and services without connecting to production databases or services. With Spring Boot 4.x / Spring Framework 7.x, several REST test client packages and auto-configurations have changed; follow the documentation for your exact version rather than copying imports mechanically from the 3.5 branch.

## 1. Learning objectives

After this lesson, you will be able to:

- Build an **HTTP contract matrix** covering method, path, status, headers, JSON shape, and error responses.
- Distinguish `@WebMvcTest`, full `@SpringBootTest` + `MockMvc`, and full `@SpringBootTest(RANDOM_PORT)`.
- Choose `TestRestTemplate`, `WebTestClient`, or `MockMvc` according to the testing goal without confusing mock transport with a real HTTP server.
- Properly verify `200`, `201`, `204`, `400`, `401`, `403`, `404`, `405`, `409`, `415`, and `5xx` when those branches belong to the contract.
- Verify `Content-Type`, `Accept`, `Location`, `Cache-Control`, correlation headers, security headers, and multi-value headers when needed.
- Parse JSON with Jackson `JsonNode` to check types, keys, nested objects, arrays, Unicode data, `null` values, and absent fields.
- Design a stable error contract that does not leak exception internals, stack traces, or sensitive data.
- Write both **positive tests** and **negative tests** for invalid parameters, malformed JSON, and unsupported media types.
- Keep tests independent and deterministic; inspect logs, status, headers, and bodies at the right layer when an assertion fails.

## 2. What does an HTTP response contain?

Consider an illustrative response when requesting a price quote:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
X-Request-Id: req-100

{
  "sku": "BOOK",
  "quantity": 2,
  "subtotalVnd": 240000,
  "discountVnd": 24000,
  "totalVnd": 216000
}
```

A test checking only `status == 200` misses these bugs:

- JSON omits `discountVnd` or renames the field to `discount`.
- `totalVnd` is wrong due to a broken discount calculation.
- The HTTP body is plain text `"OK"`, not JSON.
- `Cache-Control` was dropped, allowing sensitive data to be cached inappropriately.
- `X-Request-Id` is not returned, making it hard to correlate requests with logs.
- The API adds an `internalToken` or `passwordHash` field that must never be public.

Conversely, checking only the body while ignoring status is also wrong: an API could return JSON with plausible numbers yet carry status `500` or `206`. **A contract consists of independent data layers; assertions are needed on every required layer.**

Classification table:

| Contract layer | Question | Typical assertion tools |
|---|---|---|
| Request | Are method/path/query/headers/body right? | Test sends specific request, verifies domain effects when needed |
| Status | Did the outcome succeed or fail per rules? | `getStatusCode().value()` |
| Representation | Does it return JSON with the right media type and structure? | `Content-Type` + Jackson `JsonNode` |
| Header | Are cache, location, correlation, retry, cookie headers right? | `getHeaders()` |
| Error | Are public error code, message, path, and secret-hiding right? | Assert error JSON + status |
| State/side effect | Does it persist data, emit events, charge money, or roll back? | DB/repository/test double/adapter tests depending on scope |
| Transport/runtime | Do socket, embedded server, and real serialization work? | `RANDOM_PORT` and HTTP client |

## 3. Write the HTTP contract before writing tests

Do not start with an `andExpect(...)` chain and guess what to assert. Describe the observable outcome at the endpoint level first.

In this lesson, we have a quote API:

| Scenario | Request | Status | Key headers/body |
|---|---|---|---|
| Valid quote | `GET /api/quotes/BOOK?quantity=2&member=true` | 200 | JSON with exact amounts; `Cache-Control: no-store`; echoed `X-Request-Id` |
| Default values applied | `GET /api/quotes/BOOK` | 200 | `quantity=1`, `member=false`, total 120000 |
| Valid JSON input | `POST /api/quotes` + JSON body | 200 | Returns calculation for input; does not claim a resource was created |
| Unknown SKU | `GET /api/quotes/MISSING` | 404 | Error JSON `SKU_NOT_FOUND`, public message |
| Invalid quantity | `GET ...?quantity=0` | 400 | Error JSON `INVALID_ARGUMENT` |
| Wrong query type | `GET ...?quantity=abc` | 400 | Error JSON `INVALID_PARAMETER` |
| Malformed JSON syntax | `POST /api/quotes` + invalid body | 400 | Error JSON `MALFORMED_JSON` |
| Wrong Content-Type | `POST /api/quotes` with `text/plain` | 415 | Error JSON `UNSUPPORTED_MEDIA_TYPE` |

Convention in this example: because `POST /api/quotes` only **computes and returns a quote** without persisting a new resource, it returns `200 OK`. **Do not return `201 Created` solely because the HTTP method is POST.** If a real endpoint creates an order or resource, `201` and `Location` are usually appropriate.

A test matrix should cover **happy paths, validation failures, not found, and important infrastructure errors**. The number of cases depends on system risk; there is no need to fabricate every status code for an API that lacks those branches.

## 4. HTTP integration tests have multiple depths

In Spring Boot, web tests have distinct boundaries:

| Form | Context | Real TCP HTTP server? | Typically suited for |
|---|---|---|---|
| Plain JUnit controller unit test with mock collaborators | No Spring needed | No | Very thin controller coordination logic |
| `@WebMvcTest(Controller.class)` + `MockMvc` | MVC slice | No | Mappings, argument binding, JSON, advice/filters in slice |
| `@SpringBootTest` + `@AutoConfigureMockMvc` | Full Boot context | No | Wiring, real beans, MVC chain without a socket |
| `@SpringBootTest(RANDOM_PORT)` + `TestRestTemplate` | Full Boot context | **Yes** | HTTP request/response through embedded server and real beans |
| `@SpringBootTest(RANDOM_PORT)` + `WebTestClient` | Full Boot context | **Yes** | Fluent HTTP assertions, especially handy with webflux test dependency |
| Staging/system E2E | Server/infra outside test JVM | Yes, over the target network | Gateways, TLS, auth providers, real DBs/brokers per environment |

**`RANDOM_PORT` does not automatically become full-ecosystem E2E.** If a service uses a fake repository, mock payment gateway, or local cache, an HTTP integration test only protects the path executed across those collaborators. To prove real DB queries, migrations, retries, or brokers, write the corresponding adapter/integration tests.

### 4.1. Why choose `TestRestTemplate` for the example?

Spring Boot 3.5 provides `TestRestTemplate` when `@SpringBootTest` starts an embedded server; it is auto-configured to target the random port and has the property of **not throwing exceptions on HTTP 4xx/5xx** like a default `RestTemplate`. The test receives the full `ResponseEntity` to inspect status, headers, and error bodies.

`TestRestTemplate` is not a subclass of `RestTemplate`. In other tests, you can also use `WebTestClient` or your project's HTTP client, as long as **you know whether it calls a real server or a mock environment**.

### 4.2. Why not use `DEFINED_PORT`?

`DEFINED_PORT` binds the configured port, which easily collides with other apps on a developer machine or CI worker. `RANDOM_PORT` picks an available port for each application context and is usually the safer choice. If the app has a separate management port, test the management port too when Actuator is in scope; do not assume a test client calling the application port also tests management endpoints.

## 5. Status semantics: do not treat every error as 500

Meaningful status groups:

| Status | Typical meaning | Assertions to care about |
|---|---|---|
| 200 OK | Request succeeded and returned a representation | Accurate body, right `Content-Type` |
| 201 Created | New resource created | `Location` pointing to the new resource if specified by contract |
| 202 Accepted | Asynchronous work accepted, completion not yet guaranteed | Job ID / status URL or tracking metadata |
| 204 No Content | Success, **no response body** | Status and empty body |
| 304 Not Modified | Conditional request needs no representation returned | `ETag`/Last-Modified per conditional caching, no body |
| 400 Bad Request | Invalid input or unparseable request | Public error code/message |
| 401 Unauthorized | Not validly authenticated | Auth challenge/header per scheme |
| 403 Forbidden | Authenticated but unauthorized, or denied by policy | Do not leak sensitive resources/permissions |
| 404 Not Found | Resource does not exist or is masked by policy | Consistent error shape if a body is returned |
| 405 Method Not Allowed | Method unsupported on this resource | Appropriate `Allow` header |
| 409 Conflict | State or version conflict | Conflict code/ETag/version when applicable |
| 415 Unsupported Media Type | Request body `Content-Type` not supported | Client knows how to fix the request |
| 422 Unprocessable Content | Syntax valid but data unprocessable per chosen contract | Structured error details |
| 429 Too Many Requests | Rate-limited | `Retry-After` or rate-limit headers if contracted |
| 500 Internal Server Error | Unexpected server failure | Generic payload, no leaked internals |
| 503 Service Unavailable | System/dependency temporarily unavailable | `Retry-After` when meaningful, never disguised as 200 |

**Exact statuses belong to the API contract.** One domain may choose 400 for validation while another uses 422; what matters is consistency, documentation, and client handling. For `401`/`403`, actual behavior also depends on the security chain, authentication scheme, and resource-enumeration prevention policies.

### 5.1. 204, 304, and bodies

- `204 No Content`: successful response **carrying no body**; tests should not force JSONPath onto an empty body.
- `304 Not Modified`: conditional response **containing no representation body**, yet caching metadata is important.
- `HEAD`: semantically returns headers equivalent to the matching GET without returning response content; tests can check headers and an empty body.

If a test only asks for "any 2xx", it can miss an accidental API change from 200 with JSON to an empty 204. Assert the exact status when the client contract requires it.

## 6. HTTP headers are contract data, not decoration

Headers carry distinct semantics:

| Header | Request or response | What to check? |
|---|---|---|
| `Content-Type` | Both | Representation type; JSON responses use the right media type |
| `Accept` | Request | Representation the client wants; can lead to 406 |
| `Location` | Response | URI of new resource after 201/redirect when contracted |
| `Cache-Control` | Response | `no-store`/`private`/`max-age` matching data and policy |
| `ETag` / `If-None-Match` | Response / Request | Conditional caching or concurrency; 304/412 if used |
| `X-Request-Id` or `traceparent` | Both per convention | Correlation present, valid, and forwarded if contracted |
| `Authorization` | Request | Only verify in appropriate security tests; never log tokens |
| `WWW-Authenticate` | Response | Challenge on 401 matching the actual scheme |
| `Retry-After` | Response | Retry time/delay for 429/503 if provided |
| `Set-Cookie` / `Cookie` | Response / Request | `HttpOnly`, `Secure`, `SameSite`, domain/path attributes when relevant |
| `Vary` | Response | Cache variance by `Accept-Encoding`/`Origin` or relevant headers |
| `Allow` | Response | Supported methods on 405 |
| `Content-Disposition` | Response | Download filename/type when exporting files |

**HTTP header names are case-insensitive.** Avoid assertions requiring exact casing like `Content-Type` over `content-type` in raw bytes. Use Spring's `HttpHeaders` to read values.

For `Content-Type`, the question is usually **media type compatibility**: `application/json;charset=UTF-8` and `application/json` belong to the same JSON family. Exact string matching can be brittle. Use:

```java
// Snippet used inside a JUnit test that has ResponseEntity<String> response.
MediaType actual = response.getHeaders().getContentType();
assertNotNull(actual);
assertTrue(MediaType.APPLICATION_JSON.isCompatibleWith(actual));
```

If the contract mandates a versioned media type like `application/vnd.company.v1+json`, check the version and key parameters explicitly; avoid overly broad matchers.

### 6.1. Cache-Control: why is `no-store` different from `no-cache`?

`no-store` instructs caches not to store the response/request under caching semantics; `no-cache` **does not mean "do not store"** — it requires revalidation before reusing a stored response. For sensitive data, pick a policy based on your threat model and HTTP caching semantics; a test should assert the actual required directive, not merely that "a header exists".

Spring MVC example:

```java
ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(quote);
```

This is a snippet; `quote` is undeclared. The test can verify `response.getHeaders().getCacheControl().contains("no-store")`. Do not use `Thread.sleep` or guess cache expiration timings to prove policy; header contracts and cache integration are separate levels.

### 6.2. Does a correlation ID make tests safe?

A system may accept `X-Request-Id` and echo it back for correlation. However, **never treat a client-supplied header as a trusted identity**. In production, validate length/characters, optionally generate IDs server-side, and sanitize logs to prevent log injection or forged metadata. This example echoes a fixed ASCII ID purely to teach header assertions; it does not demonstrate a complete tracing system.

## 7. Checking JSON: shape, types, and semantics

Suppose the body is:

```json
{
  "sku": "BOOK",
  "quantity": 2,
  "subtotalVnd": 240000,
  "discountVnd": 24000,
  "totalVnd": 216000
}
```

Verification questions:

1. Is the body valid JSON rather than an HTML fallback?
2. Is the root an object or an array?
3. Do core fields exist with the right **types**?
4. Are the values correct, especially monetary amounts and statuses?
5. Are any sensitive fields, debug data, secrets, or stack traces leaked?
6. Does an array have the right elements and order per the contract?
7. If a field is optional, is it **absent, explicit null, or empty** per convention?

### 7.1. Jackson `JsonNode` for HTTP integration tests

A straightforward approach:

```java
JsonNode root = objectMapper.readTree(response.getBody());

assertTrue(root.isObject());
assertEquals("BOOK", root.required("sku").asText());
assertEquals(2, root.required("quantity").intValue());
assertEquals(216_000L, root.required("totalVnd").longValue());
assertFalse(root.has("internalToken"));
```

This is a snippet: `objectMapper`/`response` and JUnit imports are defined in the complete test in Section 16. `JsonNode.required("field")` fails when a field is missing; however, it does not always replace type checks. When the contract is strict, combine with `isTextual()`, `isIntegralNumber()`, or `isArray()`.

### 7.2. JSON numbers are not Java types

JSON has a single number type, whereas Jackson can represent values as `Integer`, `Long`, `BigDecimal`, or other types. For monetary amounts in this example, we use **integer VND (`long`)**, avoiding `double` to prevent binary floating-point rounding errors.

Do not assert a `json string` with fixed whitespace when only semantic equality is needed. Field order inside a JSON object is generally not part of the contract; array elements **are ordered** and should be checked when the API specifies ordering.

### 7.3. Missing, null, and empty are not the same

```json
{
  "note": null,
  "displayName": "",
  "items": []
}
```

- `note` is present with value `null`.
- `displayName` is present with an empty string.
- `items` is present with an empty array.
- `internalTrace` does not appear at all.

With Jackson:

```java
assertTrue(root.has("note"));
assertTrue(root.get("note").isNull());
assertEquals("", root.required("displayName").asText());
assertTrue(root.required("items").isArray());
assertEquals(0, root.required("items").size());
assertFalse(root.has("internalTrace"));
```

This is an illustrative snippet. Do not rely solely on `root.path("note").asText()` to distinguish null vs missing: `path` returns a missing-node placeholder, and converting to text can mask the difference.

### 7.4. JSONPath and JSONassert

In `MockMvc`, you can write:

```java
mockMvc.perform(get("/api/quotes/BOOK")
                .param("quantity", "2")
                .param("member", "true"))
        .andExpectAll(
                status().isOk(),
                header().string("Cache-Control", "no-store"),
                jsonPath("$.sku").value("BOOK"),
                jsonPath("$.totalVnd").value(216_000));
```

This snippet is valid only inside a test with `mockMvc` and static imports. The same contract can be verified using `TestRestTemplate` + Jackson against a real server. `content().json(expected, JsonCompareMode.STRICT)` enforces tighter structural matching; `LENIENT` allows some differences such as extra fields. Pick strictness according to your contract and data-leak risk.

**Note:** do not mix `MockMvc` matchers into `TestRestTemplate`; `TestRestTemplate` returns `ResponseEntity` and has no `andExpect(...)`. The two clients use different assertion styles.

## 8. Error contract: error messages must be designed for clients

HTTP errors should not just be raw text produced by an exception's `toString()`. A stable error DTO lets clients understand the **error category**, provides a public message, and keeps internal details in protected server logs.

Example:

```json
{
  "code": "INVALID_ARGUMENT",
  "message": "quantity must be positive",
  "path": "/api/quotes/BOOK"
}
```

In this example:

- `code` is a stable **machine-readable code** for clients.
- `message` is a human-readable/loggable message at an appropriate level; no stack traces, SQL queries, or credentials.
- `path` identifies the failing endpoint; avoid echoing sensitive data from queries/bodies into the error.
- The HTTP status must match the error category; never return `200` with `success:false` if the contract follows standard HTTP semantics.
- `Content-Type` must match the JSON body.
- `Cache-Control` and correlation headers should still be checked on error responses when policy requires them.

**Why avoid asserting full framework exception messages?** Internal messages from Spring/Jackson may include class names, parse positions, and input values, and can change across framework upgrades. Public error messages should be application-defined; **never return `ex.getMessage()` from a parse exception directly** if it might expose internals.

### 8.1. Problem Details is another option

Spring Framework supports `ProblemDetail` following the Problem Details for HTTP APIs standard (RFC 9457). An API can return:

```json
{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "detail": "quantity must be positive"
}
```

`application/problem+json` is the media type for Problem Details. An API using `ProblemDetail` should not be mis-tested by forcing every error to return `application/json` or the custom example's `code` field. Choose **one clear error contract** that fits your project and test it consistently.

If localization is supported, the public `message` may vary by `Accept-Language`. In that case, assert the stable `code` and key localized messages per defined locale rather than arbitrarily asserting a single hardcoded default string.

## 9. Validation and three distinct error layers

Distinguish:

1. **Binding/format errors:** malformed JSON, query parameters that cannot convert to `int`, unsupported media types. Spring MVC can raise these exceptions **before entering the controller method**.
2. **Domain validation errors:** non-positive quantity, blank SKU, business rules rejecting an operation. Real controllers/services throw domain-specific errors.
3. **State/conflict/infrastructure errors:** resource version conflict, gateway temporarily unavailable, DB failure. These typically need distinct statuses like 409, 503, or generic 500; never disguise all of them as 400.

Consequently, a single `@ExceptionHandler(IllegalArgumentException.class)` **does not automatically cover** `HttpMessageNotReadableException` or `HttpMediaTypeNotSupportedException`. To guarantee uniform error JSON, write explicit handlers for the framework exceptions your API standardizes, or deliberately extend `ResponseEntityExceptionHandler`/`ProblemDetail`.

Avoid a global handler catching `Exception.class` and always returning `400`: it hides server bugs, skews metrics, can turn security exceptions into input errors, and misleads clients.

## 10. Status and error messages: what to assert without becoming brittle?

For a 404 case:

```http
HTTP/1.1 404 Not Found
Content-Type: application/json
Cache-Control: no-store
X-Request-Id: req-404

{
  "code": "SKU_NOT_FOUND",
  "message": "Unknown SKU: MISSING",
  "path": "/api/quotes/MISSING"
}
```

Appropriate assertions:

- Status is **exactly `404`**.
- `Content-Type` is compatible with `application/json`.
- `Cache-Control` contains `no-store` if that is the API policy.
- `X-Request-Id` matches the request ID per the demo design.
- JSON has `code` equal to `SKU_NOT_FOUND`.
- `message` matches the defined public message; critical tests may assert the exact string.
- `path` is the request path, containing no sensitive query values or secrets.
- Absence of `stackTrace`, `exception`, `sql`, or `debugToken`.
- No unintended side effects (if the endpoint touches real infrastructure, verify in the appropriate test).

Do not assert **JSON key order**, whitespace indentation, or header name casing unless the contract mandates it. If `message` copywriting is allowed to evolve, keep `code` as the machine contract and assert message properties (non-empty, no sensitive details) at an appropriate level.

## 11. Runnable example design: quote calculation without external resources

To keep focus on the HTTP contract, the application has:

- Product `BOOK` priced at 120,000 VND and `PEN` at 20,000 VND.
- Members get a 10% discount on the subtotal, using integer division rounded down.
- Quantity must be greater than 0.
- Unknown SKU returns 404; invalid quantity returns 400.
- `GET` uses query params; `POST` takes a JSON body; both only return a quote without persisting anything.
- 200 responses include `Cache-Control: no-store` and `X-Request-Id`.
- Stable error body via `@RestControllerAdvice` for domain errors, malformed JSON, wrong query type, and unsupported Content-Type.
- JUnit integration test calling the real server with `TestRestTemplate`.

All components run for real in this example: Spring MVC controller, calculation service, HTTP message converters, and global advice. **Do not mock `QuoteService`** because the lesson needs to prove both the HTTP contract and the sample calculation. There is no DB, payment gateway, broker, or external network, so tests cause no side effects outside localhost.

### 11.1. Directory tree

```text
src/main/java/com/example/httpcontract/
    HttpContractApplication.java
    QuoteCommand.java
    QuoteView.java
    ApiError.java
    QuoteNotFoundException.java
    QuoteService.java
    QuoteController.java
    QuoteExceptionAdvice.java

src/test/java/com/example/httpcontract/
    QuoteHttpContractIntegrationTest.java
    QuoteMockMvcIntegrationTest.java
```

All Java files declare `package com.example.httpcontract;`. The project uses Java 17+ and Spring Boot 3.5.x with `spring-boot-starter-web` / `spring-boot-starter-test`. Do not add `spring-boot-starter-webflux` just to run this example.

## 12. Application, DTOs, and exception

**`src/main/java/com/example/httpcontract/HttpContractApplication.java`**

```java
package com.example.httpcontract;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpContractApplication {

    public static void main(String[] args) {
        SpringApplication.run(HttpContractApplication.class, args);
    }
}
```

**`src/main/java/com/example/httpcontract/QuoteCommand.java`**

```java
package com.example.httpcontract;

public record QuoteCommand(
        String sku,
        int quantity,
        boolean member) {
}
```

**`src/main/java/com/example/httpcontract/QuoteView.java`**

```java
package com.example.httpcontract;

public record QuoteView(
        String sku,
        int quantity,
        long subtotalVnd,
        long discountVnd,
        long totalVnd) {
}
```

**`src/main/java/com/example/httpcontract/ApiError.java`**

```java
package com.example.httpcontract;

public record ApiError(
        String code,
        String message,
        String path) {
}
```

**`src/main/java/com/example/httpcontract/QuoteNotFoundException.java`**

```java
package com.example.httpcontract;

public final class QuoteNotFoundException
        extends RuntimeException {

    public QuoteNotFoundException(String sku) {
        super("Unknown SKU: " + sku);
    }
}
```

These `record` types are simple immutable data carriers serialized by Jackson using component names. If a real app uses `@JsonProperty`, a naming strategy, custom serializers, or API versioning, field names in tests must follow the **public contract**, not assumptions from Java class names.

### 12.1. Do not return JPA entities directly in responses

In systems with a DB, separate response DTOs from entities/persistence models to avoid exposing internal identifiers/fields, lazy-loading exceptions, and implementation-coupled schemas. Using dedicated records for the API keeps what may appear in JSON transparent.

## 13. Real service: calculating and reporting domain errors

**`src/main/java/com/example/httpcontract/QuoteService.java`**

```java
package com.example.httpcontract;

import org.springframework.stereotype.Service;

@Service
public class QuoteService {

    public QuoteView quote(
            String sku, int quantity, boolean member) {

        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException(
                    "sku must not be blank");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }

        long unitPrice = switch (sku) {
            case "BOOK" -> 120_000L;
            case "PEN" -> 20_000L;
            default -> throw new QuoteNotFoundException(sku);
        };

        long subtotal = Math.multiplyExact(unitPrice, quantity);
        long discount = member ? subtotal / 10L : 0L;
        long total = Math.subtractExact(subtotal, discount);

        return new QuoteView(
                sku, quantity, subtotal, discount, total);
    }
}
```

Explanation:

- The service validates inputs before calculating amounts.
- An unknown SKU throws a **dedicated exception** so it maps to 404 instead of turning into a generic 500.
- `quantity <= 0` becomes 400 via the error advice.
- `Math.multiplyExact` catches overflow rather than silently wrapping around; the demo does not define a separate public error code for overflow yet. In production, enforce sensible quantity limits and money types, and map overflow to an appropriate error.
- Never use `double` for money. Numbers in this lesson use **integer VND** with a simple floor-rounding discount rule for learning purposes.

Because `QuoteService` runs for real in the HTTP integration test, a discount bug will turn the JSON total test red. Mocking the service to return a canned `QuoteView` would lose that guarantee.

## 14. Controller: status 200 and stable headers

**`src/main/java/com/example/httpcontract/QuoteController.java`**

```java
package com.example.httpcontract;

import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/quotes")
public class QuoteController {

    private final QuoteService service;

    public QuoteController(QuoteService service) {
        this.service = service;
    }

    @GetMapping("/{sku}")
    public ResponseEntity<QuoteView> get(
            @PathVariable String sku,
            @RequestParam(defaultValue = "1") int quantity,
            @RequestParam(defaultValue = "false") boolean member,
            @RequestHeader(
                    name = "X-Request-Id",
                    defaultValue = "unknown") String requestId) {

        return success(
                service.quote(sku, quantity, member), requestId);
    }

    @PostMapping
    public ResponseEntity<QuoteView> post(
            @RequestBody QuoteCommand command,
            @RequestHeader(
                    name = "X-Request-Id",
                    defaultValue = "unknown") String requestId) {

        return success(service.quote(
                command.sku(),
                command.quantity(),
                command.member()), requestId);
    }

    private static ResponseEntity<QuoteView> success(
            QuoteView view, String requestId) {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .header("X-Request-Id", requestId)
                .body(view);
    }
}
```

**Intentional design choices:**

- `GET /api/quotes/BOOK` defaults to `quantity=1`, `member=false`.
- `POST /api/quotes` accepts JSON via `@RequestBody`; it does not create/persist a resource, so **200** matches the demo design.
- Both return `Cache-Control: no-store` and an illustrative correlation header.
- `ResponseEntity<QuoteView>` lets Spring MVC pick the HTTP message converter (Jackson) to produce JSON.
- Avoid setting `Content-Type` manually as a raw string when the converter already produces JSON; the error handler sets the media type explicitly.
- The demo does not validate client-sent `X-Request-Id`; production needs proper trust rules for tracing IDs.

**Do not mix business logic into the controller:** the discount calculation lives in the service. The controller handles HTTP binding, delegation, and response construction.

## 15. Error advice: 400, 404, 415, and public JSON

**`src/main/java/com/example/httpcontract/QuoteExceptionAdvice.java`**

```java
package com.example.httpcontract;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.HttpMediaTypeNotSupportedException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@RestControllerAdvice
public class QuoteExceptionAdvice {

    @ExceptionHandler(QuoteNotFoundException.class)
    public ResponseEntity<ApiError> notFound(
            QuoteNotFoundException failure,
            HttpServletRequest request) {

        return error(HttpStatus.NOT_FOUND,
                "SKU_NOT_FOUND", failure.getMessage(), request);
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ApiError> invalidArgument(
            IllegalArgumentException failure,
            HttpServletRequest request) {

        return error(HttpStatus.BAD_REQUEST,
                "INVALID_ARGUMENT", failure.getMessage(), request);
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<ApiError> invalidParameter(
            MethodArgumentTypeMismatchException failure,
            HttpServletRequest request) {

        return error(HttpStatus.BAD_REQUEST,
                "INVALID_PARAMETER",
                "Query parameter has invalid type", request);
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiError> malformedJson(
            HttpMessageNotReadableException failure,
            HttpServletRequest request) {

        return error(HttpStatus.BAD_REQUEST,
                "MALFORMED_JSON",
                "Request body is not valid JSON", request);
    }

    @ExceptionHandler(HttpMediaTypeNotSupportedException.class)
    public ResponseEntity<ApiError> unsupportedType(
            HttpMediaTypeNotSupportedException failure,
            HttpServletRequest request) {

        return error(HttpStatus.UNSUPPORTED_MEDIA_TYPE,
                "UNSUPPORTED_MEDIA_TYPE",
                "Request Content-Type is not supported", request);
    }

    private static ResponseEntity<ApiError> error(
            HttpStatus status,
            String code,
            String message,
            HttpServletRequest request) {

        String requestId = request.getHeader("X-Request-Id");
        if (requestId == null || requestId.isBlank()) {
            requestId = "unknown";
        }

        return ResponseEntity.status(status)
                .contentType(MediaType.APPLICATION_JSON)
                .cacheControl(CacheControl.noStore())
                .header("X-Request-Id", requestId)
                .body(new ApiError(
                        code, message, request.getRequestURI()));
    }
}
```

### 15.1. Why are there multiple handlers?

- `QuoteNotFoundException` comes from business logic when the SKU does not exist → 404.
- `IllegalArgumentException` comes from simple validation in the service → 400.
- `MethodArgumentTypeMismatchException` can occur **before the service is called** when query `quantity=abc` fails to parse as `int` → 400.
- `HttpMessageNotReadableException` can occur when the JSON body is syntactically invalid or cannot be read into the record → 400.
- `HttpMediaTypeNotSupportedException` occurs when POST carries a body with an unsupported media type, e.g., `text/plain` instead of JSON → 415.

**Do not expose the parsing exception's message**; we return the stable string `"Request body is not valid JSON"`. A malformed payload might contain sensitive data, so public logs/errors should not echo the raw payload.

### 15.2. Limitations of the advice

This is a minimal example and does not cover every framework error branch. For example:

- Security 401/403 can be produced **before the controller** by the Spring Security filter chain.
- JSON returned for 406, 405, or certain validation exceptions may come from default framework handling.
- Unexpected server 500s should generally return a generic error response, rather than blindly catching `Exception.class` and converting it into 400.
- Production runtimes need standardized logging/trace IDs, localization, internal-detail hiding policies, and sensitive-data scrubbing in logs.
- With Spring Framework 6.x, you can standardize on `ProblemDetail` or `ResponseEntityExceptionHandler`; pick one consistent API-wide schema.

This example **intentionally omits failing backends or security dependencies**; do not pretend those scenarios have been verified.

## 16. Real HTTP integration test with `TestRestTemplate`

This is the centerpiece test. It calls a **real embedded server** on a random port without mocking the service. Assertions verify status, headers, JSON, and stable error messages.

**`src/test/java/com/example/httpcontract/QuoteHttpContractIntegrationTest.java`**

```java
package com.example.httpcontract;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = HttpContractApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class QuoteHttpContractIntegrationTest {

    @LocalServerPort
    int serverPort;

    @Autowired
    TestRestTemplate rest;

    @Autowired
    ObjectMapper mapper;

    private ResponseEntity<String> get(
            String url, String requestId) {

        HttpHeaders headers = new HttpHeaders();
        headers.set("X-Request-Id", requestId);
        headers.setAccept(List.of(MediaType.APPLICATION_JSON));

        return rest.exchange(url, HttpMethod.GET,
                new HttpEntity<Void>(headers), String.class);
    }

    private JsonNode body(ResponseEntity<String> response)
            throws Exception {
        assertNotNull(response.getBody());
        return mapper.readTree(response.getBody());
    }

    private void assertJsonHeaders(
            ResponseEntity<String> response, String requestId) {

        MediaType type = response.getHeaders().getContentType();

        assertAll("HTTP representation headers",
                () -> assertNotNull(type),
                () -> assertTrue(type != null
                        && MediaType.APPLICATION_JSON.isCompatibleWith(type)),
                () -> assertTrue(response.getHeaders()
                        .getCacheControl().contains("no-store")),
                () -> assertEquals(requestId,
                        response.getHeaders()
                                .getFirst("X-Request-Id")));
    }

    @Test
    void getReturns200HeadersAndCorrectJson() throws Exception {
        ResponseEntity<String> response = get(
                "/api/quotes/BOOK?quantity=2&member=true",
                "req-get-1");
        JsonNode json = body(response);

        assertAll("GET quote contract",
                () -> assertTrue(serverPort > 0),
                () -> assertEquals(200,
                        response.getStatusCode().value()),
                () -> assertEquals("BOOK",
                        json.required("sku").asText()),
                () -> assertEquals(2,
                        json.required("quantity").intValue()),
                () -> assertEquals(240_000L,
                        json.required("subtotalVnd").longValue()),
                () -> assertEquals(24_000L,
                        json.required("discountVnd").longValue()),
                () -> assertEquals(216_000L,
                        json.required("totalVnd").longValue()),
                () -> assertTrue(
                        json.required("totalVnd").isIntegralNumber()),
                () -> assertFalse(json.has("internalToken")));

        assertJsonHeaders(response, "req-get-1");
    }

    @Test
    void defaultQueryParametersAreApplied() throws Exception {
        ResponseEntity<String> response =
                get("/api/quotes/BOOK", "req-default-1");

        assertEquals(200, response.getStatusCode().value());
        JsonNode json = body(response);
        assertEquals(1, json.required("quantity").intValue());
        assertEquals(120_000L,
                json.required("subtotalVnd").longValue());
        assertEquals(0L,
                json.required("discountVnd").longValue());
        assertEquals(120_000L,
                json.required("totalVnd").longValue());
        assertJsonHeaders(response, "req-default-1");
    }

    @Test
    void postParsesJsonRequestAndReturns200() throws Exception {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.setAccept(List.of(MediaType.APPLICATION_JSON));
        headers.set("X-Request-Id", "req-post-1");

        QuoteCommand command =
                new QuoteCommand("PEN", 3, true);
        HttpEntity<QuoteCommand> request =
                new HttpEntity<>(command, headers);

        ResponseEntity<String> response =
                rest.exchange("/api/quotes",
                        HttpMethod.POST, request, String.class);

        assertEquals(200, response.getStatusCode().value());
        JsonNode json = body(response);

        assertAll("POST body binding and quote",
                () -> assertEquals("PEN",
                        json.required("sku").asText()),
                () -> assertEquals(3,
                        json.required("quantity").intValue()),
                () -> assertEquals(60_000L,
                        json.required("subtotalVnd").longValue()),
                () -> assertEquals(6_000L,
                        json.required("discountVnd").longValue()),
                () -> assertEquals(54_000L,
                        json.required("totalVnd").longValue()));

        assertJsonHeaders(response, "req-post-1");
    }

    @Test
    void unknownSkuReturns404WithSafePublicError()
            throws Exception {

        ResponseEntity<String> response =
                get("/api/quotes/MISSING", "req-not-found");
        JsonNode json = body(response);

        assertEquals(404, response.getStatusCode().value());
        assertEquals("SKU_NOT_FOUND",
                json.required("code").asText());
        assertEquals("Unknown SKU: MISSING",
                json.required("message").asText());
        assertEquals("/api/quotes/MISSING",
                json.required("path").asText());
        assertFalse(json.has("stackTrace"));
        assertFalse(json.has("exception"));
        assertFalse(json.has("sql"));

        assertJsonHeaders(response, "req-not-found");
    }

    @Test
    void invalidQuantityReturns400Not500() throws Exception {
        ResponseEntity<String> response =
                get("/api/quotes/BOOK?quantity=0",
                        "req-invalid-quantity");

        assertEquals(400, response.getStatusCode().value());
        JsonNode json = body(response);

        assertEquals("INVALID_ARGUMENT",
                json.required("code").asText());
        assertEquals("quantity must be positive",
                json.required("message").asText());

        assertJsonHeaders(response, "req-invalid-quantity");
    }

    @Test
    void wrongQueryTypeReturnsStable400() throws Exception {
        ResponseEntity<String> response =
                get("/api/quotes/BOOK?quantity=abc",
                        "req-invalid-type");

        assertEquals(400, response.getStatusCode().value());
        JsonNode json = body(response);

        assertEquals("INVALID_PARAMETER",
                json.required("code").asText());
        assertEquals("Query parameter has invalid type",
                json.required("message").asText());
        assertFalse(json.has("stackTrace"));

        assertJsonHeaders(response, "req-invalid-type");
    }

    @Test
    void malformedJsonBodyReturnsSafe400() throws Exception {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.set("X-Request-Id", "req-bad-json");

        HttpEntity<String> request =
                new HttpEntity<>("{not-json}", headers);

        ResponseEntity<String> response =
                rest.exchange("/api/quotes", HttpMethod.POST,
                        request, String.class);

        assertEquals(400, response.getStatusCode().value());
        JsonNode json = body(response);

        assertEquals("MALFORMED_JSON",
                json.required("code").asText());
        assertEquals("Request body is not valid JSON",
                json.required("message").asText());
        assertFalse(json.has("exception"));
        assertFalse(json.has("stackTrace"));

        assertJsonHeaders(response, "req-bad-json");
    }

    @Test
    void unsupportedContentTypeReturns415() throws Exception {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.TEXT_PLAIN);
        headers.set("X-Request-Id", "req-bad-media");

        HttpEntity<String> request =
                new HttpEntity<>("sku=BOOK", headers);

        ResponseEntity<String> response =
                rest.exchange("/api/quotes", HttpMethod.POST,
                        request, String.class);

        assertEquals(415, response.getStatusCode().value());
        JsonNode json = body(response);

        assertEquals("UNSUPPORTED_MEDIA_TYPE",
                json.required("code").asText());
        assertEquals("Request Content-Type is not supported",
                json.required("message").asText());

        assertJsonHeaders(response, "req-bad-media");
    }
}
```

### 16.1. Why are `HttpEntity` and `ResponseEntity` important?

`HttpEntity` carries **request body and request headers**. `ResponseEntity` provides status, headers, and body together. Tests can verify:

- Method/path/query/request body traveled through the real HTTP server.
- Jackson deserialized the JSON into `QuoteCommand`.
- The service calculated the right amounts and Spring MVC serialized `QuoteView`.
- The exception advice produced the defined status and error body.
- Response headers have the expected values.

`TestRestTemplate` does not treat 4xx/5xx as client exceptions by default: it lets you read `response.getStatusCode()` and `response.getBody()` to accurately check negative contracts.

### 16.2. Why parse JSON with Jackson instead of comparing the whole string?

Responses can change whitespace or field order without changing semantics. `JsonNode` checks values by key. Use `required` for mandatory fields and `has`/`hasNonNull` to distinguish presence types.

For example, the test asserts `totalVnd=216000` as an integer without requiring JSON indentation to match the docs. That is a **less brittle** assertion that still catches business bugs.

### 16.3. Note on `assertJsonHeaders`

This helper is only for responses with a **JSON body** whose contract requires `no-store` + a correlation ID. Do not call it for `204 No Content` or file-download endpoints; each representation has its own header policy.

### 16.4. Do not let HTTP tests depend on test order

These methods do not mutate a database, use no singleton counters, and do not depend on one another. When real resource creation is involved, avoid having one test create resource `41` while another assumes it already exists simply due to test ordering. Create independent fixtures or proper setup/teardown.

## 17. Full Boot context with `MockMvc`: cheaper than real networking

If you want to run the real controller, service, and advice without opening a TCP port, use `@SpringBootTest` with the mock web environment and `@AutoConfigureMockMvc`.

**`src/test/java/com/example/httpcontract/QuoteMockMvcIntegrationTest.java`**

```java
package com.example.httpcontract;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
        classes = HttpContractApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class QuoteMockMvcIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void testsFullSpringContextWithoutSocket() throws Exception {
        mvc.perform(get("/api/quotes/BOOK")
                        .param("quantity", "2")
                        .param("member", "true")
                        .header("X-Request-Id", "req-mock"))
                .andExpectAll(
                        status().isOk(),
                        header().string("X-Request-Id", "req-mock"),
                        header().string("Cache-Control", "no-store"),
                        content().contentTypeCompatibleWith(
                                "application/json"),
                        jsonPath("$.sku").value("BOOK"),
                        jsonPath("$.totalVnd").value(216_000));
    }
}
```

In this test, **the real service still runs** because we load the full Boot context without mocking `QuoteService`. `MockMvc` traverses the MVC pipeline without **testing the socket/server runtime**. This is a good balance when a suite has many small HTTP contract cases and real transport is not the risk that needs verifying every time.

**Unlike `@WebMvcTest`:** `@WebMvcTest` does not scan `@Service` by default, so it usually needs `@MockitoBean` at the controller boundary; a green slice test does not protect the real service. Clearly separate **slice vs full context** and **mock transport vs real server** — those are two independent axes.

## 18. Branches to add when a real application has state

The example does not persist data to keep the lesson focused. For real CRUD APIs, add contracts for create/update/delete.

### 18.1. POST creating a resource: `201` + `Location`

Illustrative response:

```http
HTTP/1.1 201 Created
Location: /api/orders/41
Content-Type: application/json

{"id":41,"status":"NEW"}
```

When creation succeeds, a controller might typically use:

```java
// Snippet: order is an object that has actually been persisted.
URI location = URI.create("/api/orders/" + order.id());

return ResponseEntity.created(location).body(order);
```

This is a **non-standalone illustration**, different from the quote POST in Section 14. Tests should assert status 201, `Location`, and **GET the newly created resource back** if read-after-write is part of the contract, rather than only asserting a URI string the test itself predicted.

### 18.2. PUT/PATCH and optimistic locking

If an API supports `ETag` / `If-Match`, tests should cover:

- Updating with a valid version succeeds and returns a new ETag per convention.
- A stale version is rejected with `412 Precondition Failed` or `409 Conflict` depending on contract.
- Missing `If-Match` when the endpoint requires a precondition can result in `428 Precondition Required`.

Do not add meaningless `ETag` headers just to increase header assertions. They relate to **conditional updates, caching, and concurrency semantics**.

### 18.3. Successful DELETE with `204`

`204` has no body; proper test:

```java
// Snippet with MockMvc in a configured DELETE test.
mvc.perform(delete("/api/orders/{id}", 41L))
        .andExpect(status().isNoContent())
        .andExpect(content().string(""));
```

The snippet needs static imports and a real DELETE controller. Do not force a JSON body into 204 just to "make all responses uniform".

### 18.4. Pagination and sorting

An endpoint `GET /api/orders?page=1&size=5` may need to return JSON `items`, `total`, `page`, and `size` along with ordering. If the backend uses a DB yet tests mock out a hardcoded list, they do not protect `ORDER BY`, count queries, or page boundaries; test against a real service/repository when required.

## 19. Authorization, authentication, and error privacy

For APIs with Spring Security, the status contract should cover:

- **401** when authentication is missing or the token is invalid; may require a `WWW-Authenticate` header per scheme.
- **403** when the principal lacks permission; do not leak internal roles/permissions outside the contract.
- **404** may be used instead of 403 to avoid confirming resource existence in certain threat models.
- **429** when rate-limited if policy applies, with defined limit/retry headers.
- Session/cookie attributes or CORS response headers when browser clients need them.

A controller test using `@WithMockUser` can check authorization in a mock environment, yet **does not prove JWT signatures, issuers, audiences, or deployment security filters**. Write integration tests with real Spring Security config and appropriate token fixtures.

**Never disable security globally just to make tests return 200.** Because this example does not include `spring-boot-starter-security`, 401/403 statuses are not part of the runnable program; they are required extensions once authentication is added.

### 19.1. Checking error messages do not leak data

Error JSON must never contain:

- Raw SQL queries or connection strings with credentials.
- JVM stack traces or internal implementation class names unless explicitly part of a public contract.
- Full access tokens, refresh tokens, private keys, or passwords.
- Raw request bodies containing private information or unnecessary sensitive identifiers.
- Unsanitized exception messages coming from third-party libraries.

Assertions like `assertFalse(json.has("stackTrace"))` are one layer of defense; they **do not replace** threat modeling, security reviews, and verifying responses across every error handler. Error messages can also leak via other fields or headers; restrict the response schema tightly.

## 20. Content negotiation, charset, and localization

Clients send `Accept` to say which representation they want; clients send `Content-Type` to say what type the request body has.

| Situation | HTTP meaning | Expected status |
|---|---|---|
| `Accept: application/json` | Client accepts JSON | 200 with JSON when endpoint supports it |
| `Accept: application/xml` when endpoint only supports JSON | No matching representation | 406 |
| `Content-Type: application/json` and valid JSON body | JSON can be deserialized | 200/201 per contract |
| `Content-Type: text/plain` for endpoint expecting JSON DTO | Unsupported media type | 415 |
| `Content-Type: application/json` yet syntactically invalid body | JSON cannot be parsed | 400 |
| `Content-Type: application/problem+json` response | Problem Details response | Media type per error contract |

The runnable example intentionally tests **415** when POSTing to a JSON DTO endpoint with `text/plain` content type, and **400** when the content type is valid yet JSON is malformed. These two errors are **not synonymous**.

### 20.1. Content-Type is not always present

204, 304, or certain empty-body responses may not need `Content-Type`. Do not enforce a suite-wide helper asserting "every response must be application/json". Only assert the header when the response body actually carries that representation or the contract specifically requires it.

### 20.2. Charset and Unicode

UTF-8 is the usual choice for JSON. Jackson can represent the same Unicode string via literal characters or escaped sequences per JSON rules. If the API only requires **semantic string equality**, parse the JSON and assert the decoded value rather than comparing raw JSON bytes. If an endpoint uses digital signatures over payloads, tests must examine exact **byte serialization and canonicalization**, which is a different requirement.

### 20.3. Localization of error messages

If an API returns errors based on `Accept-Language: vi` or `en`, write tests selecting the locale and asserting the stable public code alongside the localized message defined for that language. Do not rely on the dev/CI machine's default locale; configure the test locale explicitly if required.

## 21. ETag, caching, and conditional requests

Cache headers and conditional responses need HTTP-level tests when the API actually supports them.

Example:

```http
GET /api/products/41
If-None-Match: "v7"
```

If the resource still has ETag `"v7"`, the server can return:

```http
HTTP/1.1 304 Not Modified
ETag: "v7"
```

with no representation body. If it changed to `"v8"`, the server returns `200` with the new body and new ETag. Tests should not merely assert that "an ETag exists"; verify **the state transition driven by conditional headers**.

For updates using `If-Match`, the semantics differ from `If-None-Match`. Do not put ETag names in tests unless the implementation genuinely emits and compares versions.

**Note:** the quote example sets `Cache-Control: no-store` to illustrate cache policy; it **does not implement ETag**. Do not add a 304 test to the runnable example and expect it to pass.

## 22. Error contracts when downstream services or DB are unavailable

For real applications with external APIs or DBs, design test cases for:

1. Downstream timeout → public error or fallback response per contract; client sees no stack trace.
2. Remote 429/503 → retry/backoff per policy, with idempotency and bounds.
3. Circuit breaker open → response clearly indicating service status, usually 503 or a defined fallback.
4. Database constraint/conflict → 409 or an appropriate business error, never raw SQL over HTTP.
5. Unexpected exception → generic 500 with a correlation ID for investigation.
6. Partial failure → clear rules on data consistency and retryability; never return 200 if the operation did not succeed unless the contract permits it.

These tests **do not have to call real external services**. You can mock the exact **outbound port** to force timeouts/exceptions and verify error mapping at the application boundary. However, to prove the HTTP client actually maps statuses, deserializes bodies, or retries properly over a socket, write an adapter integration test against a mock HTTP server.

Choose test doubles by boundary: **never mock the controller/service under test**, only mock/fake components outside its scope. If a test returns error JSON fabricated by a mocked controller, it does not protect the real global exception handler.

## 23. Transactions and external resources in real HTTP tests

A key pitfall of `@SpringBootTest(RANDOM_PORT)` is that **the test client and server request run on different threads/transactions**. `@Transactional` on a JUnit test method **does not guarantee** rolling back writes made by server HTTP requests. This differs from single-thread/same-context repository tests.

For real APIs with databases:

- Use a dedicated test database/schema with restricted permissions.
- Have each test create fixtures with unique IDs, independent of execution order.
- Clean up after tests or reset the DB with appropriate tools; consider Testcontainers.
- Never use production accounts or endpoints.
- Verify side effects after the HTTP request, not just the 201 body.
- When async jobs, messages, or outboxes are involved, wait conditionally with a timeout and assert the final outcome instead of arbitrary `Thread.sleep`.
- A random-port test does not by itself prove atomicity between a DB commit and a payment gateway; test failure modes separately.

**Never trade away isolation for a fleeting green run** by fixing test order or wiping shared data on a non-test database.

## 24. Maintaining tests: strong yet non-brittle assertions

### 24.1. Assertions that are too weak

```java
// Anti-pattern: checks status only.
assertEquals(200, response.getStatusCode().value());
```

It ignores `Content-Type`, headers, JSON shape, and values. If the endpoint returns 200 with body `{"error":"failed"}`, the test still passes.

### 24.2. Assertions too tightly coupled to non-contract details

```java
// Anti-pattern: depends on whitespace and JSON field order.
assertEquals(
        "{\"sku\":\"BOOK\",\"quantity\":2,\"totalVnd\":216000}",
        response.getBody());
```

This is an illustrative Java snippet; do not copy it when only JSON semantics matter. A serializer changing key order or adding an allowed public field can break the test.

### 24.3. Lock down the right contract

Protect at least:

- Exact status code, not just `is2xxSuccessful` when clients distinguish codes.
- Compatible content type, without demanding an exact string when valid charsets differ.
- Meaningful headers: cache, location, correlation, retry.
- Important JSON fields with their types and values; absence of sensitive fields.
- Public error code, convention-compliant message, no leaked internals.
- Side effects when the API genuinely mutates state.

### 24.4. Avoid excessive unreviewed snapshots

Full-response snapshots help guard rigid schemas when changes are carefully reviewed. However, oversized snapshots can tempt reviewers to just "approve update" and miss bugs. For evolving APIs, focused assertions paired with schema/contract tests are usually easier to maintain.

## 25. Diagnosing failures when an HTTP integration test turns red

A layered debugging workflow:

**Step 1 — Was the request actually sent?** Check HTTP method, path, port, query, headers, body, and encoding. With `RANDOM_PORT`, verify the injected port; never hardcode 8080.

**Step 2 — Did the server start?** On `Failed to load ApplicationContext`, inspect the root cause across beans, properties, profiles, or auto-config. On socket connection refused, distinguish bootstrap failures from wrong URL/port.

**Step 3 — Which status was actually returned?** 400 vs 404 vs 415 have distinct causes; 500 needs server logs and trace IDs — never change expectations to match a broken contract.

**Step 4 — Is `Content-Type` right?** An HTML error page body will make Jackson parsing fail, though the root cause is the status or an unstandardized error pipeline.

**Step 5 — Is the body valid JSON with the right shape?** Parse `JsonNode`; print non-sensitive fields in controlled debug output. Never dump raw tokens or customer payloads into CI logs.

**Step 6 — Which headers are missing?** Inspect `response.getHeaders()`; distinguish headers added by controllers, advice, filters, gateways, and the server.

**Step 7 — Which beans are mock/fake/real?** If totals are wrong, confirm the real service ran. If the test mocked the service, do not use that run to draw conclusions about domain policy.

**Step 8 — Is there shared state?** Tests that pass alone but fail in the suite typically involve DB/bean state, context caching, time, or test ordering.

**Step 9 — Did a framework version change?** Security defaults, error response shapes, Jackson serializers, and client auto-config can change; update tests against the decided contract rather than blindly accepting every shift.

### 25.1. Symptom and action table

| Symptom | Likely cause | Inspection action |
|---|---|---|
| GET returns 404 instead of 200 | Wrong route, path param, or missing resource | Check mapping and URI |
| POST returns 415 | Wrong request `Content-Type` | Set `application/json` when sending a DTO |
| POST returns 400 even though JSON "looks right" | JSON syntax/type/conversion/validation | Inspect response error code and server root cause |
| GET returns 406 | Unsupported `Accept` | Check media type / content negotiation |
| Unexpected 401/403 | Security filter or auth fixture | Check principal/token/CSRF per policy |
| Server returns HTML instead of JSON error | Unstandardized error pipeline / default handler | Check `Content-Type` and exception advice |
| Correlation ID header missing on errors | Advice/filter only added it on success | Add it on the error response path and test negative cases |
| Unexpected `Cache-Control` | Overwritten by controller/filter/gateway | Trace every layer setting headers |
| JSON shows wrong total | Service/policy or serialization mapping | Run domain unit tests and full integration tests |
| `TestRestTemplate` throws client/network error | Server not started, wrong URL/port, connect timeout | Read startup logs; do not confuse with 4xx responses |
| Slow test suite | Too many full contexts/ports/server startups | Keep a few critical real HTTP tests; move cheap cases to slice/unit |
| Subsequent test fails due to prior test's data | Shared DB/clock/singleton | Separate fixtures, clean up, avoid ordering assumptions |

## 26. Going further: contract testing with Spring Cloud Contract or OpenAPI

When many clients/servers evolve APIs concurrently, manual endpoint tests alone may not suffice. You can combine:

- **OpenAPI/schema validation:** verifies response JSON shapes, required fields, and statuses against the public spec. An OpenAPI file is only documentation without tests enforcing the implementation.
- **Consumer-driven contract tests:** verify the provider satisfies specific consumer expectations, useful when services communicate independently.
- **Spring Cloud Contract:** builds contracts from DSL/fixtures and verifies the provider in an appropriate workflow.
- **Real integration tests:** still necessary to catch bean wiring, security/filters, serialization, and business logic that contract stubs do not prove.
- **Small, meaningful E2E tests:** choose a few high-value flows crossing key boundaries.

Do not replace all HTTP tests with schema validation. A schema can validate while amounts or authorization are wrong. Conversely, a few HTTP happy paths do not protect compatibility for every consumer. **Match test depth to risk.**

## 27. Gradle and how to run the example

The project requires Java 17+, Spring Boot **3.5.x**, Spring MVC, Jackson, and JUnit Jupiter 5. In a Gradle project already configured with the **Spring Boot plugin/BOM, repositories, and matching toolchain/versions**, add dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is an **addition** to an existing `build.gradle`, not a standalone build file since it omits plugins and repositories. With Boot 3.5, `spring-boot-starter-test` provides JUnit Jupiter, Spring Test, and standard Jackson/test utilities.

Run from the directory with the Gradle wrapper:

```bash
./gradlew test --tests com.example.httpcontract.QuoteHttpContractIntegrationTest --tests com.example.httpcontract.QuoteMockMvcIntegrationTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests com.example.httpcontract.QuoteHttpContractIntegrationTest --tests com.example.httpcontract.QuoteMockMvcIntegrationTest
```

In a multi-project build, replace `test` with the actual module task such as `:your-module:test` when the module has that name. Copy the exact 10 Java files from the Section 11 tree with matching packages and dependencies. **Blocks labeled snippet/anti-pattern in other sections are not standalone compilable classes.**

### 27.1. Expected results

- `QuoteHttpContractIntegrationTest` has **8 test methods**: GET success, GET defaults, POST JSON success, 404, 400 quantity, 400 query conversion, 400 malformed JSON, 415 unsupported media type.
- `QuoteMockMvcIntegrationTest` has **1 test method**: full Boot context with mock web transport verifying 200, headers, and JSON.
- Total of **9 JUnit test methods**. With the right project and dependencies, the tests are expected to pass and Gradle reports `BUILD SUCCESSFUL`.
- Random HTTP ports and startup logs can vary between runs; **there is no fixed business stdout** to compare against. `@LocalServerPort` only needs to be greater than 0.
- This is the **expected outcome from reviewing the sample code**, not a claim of having run a build in a specific workspace/repository.

Gradle test reports are normally at `build/reports/tests/test/index.html` and XML results at `build/test-results/test/`, relative to the module's build directory.

### 27.2. If your project uses Spring Boot 4.x

Client packages and auto-configurations were reorganized in Boot 4, so check the specific version before copying `TestRestTemplate`, `@AutoConfigureMockMvc`, or test starters. HTTP contract goals (status, headers, JSON, public errors) stay the same; **imports and auto-configuration** must match the version.

## 28. Practice exercises

### Exercise A — designing assertions for 201 Created

An endpoint `POST /api/orders` actually creates an order and returns `201` with `Location: /api/orders/41` and body `{"id":41,"status":"NEW"}`. Write an assertion checklist covering status, `Location`, content type, JSON, and reading the resource back via GET. If `Location` points to a non-existent resource, which test catches it?

**Hint:** do not just check the header; perform a GET on the created resource with isolated fixtures/DB if the contract supports read-after-write.

### Exercise B — distinguishing 400 and 415

For `POST /api/quotes`:

1. Header `Content-Type: application/json`, body `{not-json}`.
2. Header `Content-Type: text/plain`, body `sku=BOOK`.

Which case is 400 and which is 415? Why not merge both into `INVALID_ARGUMENT`?

**Guided answer:** (1) unparseable JSON → 400, code `MALFORMED_JSON`; (2) unsupported media type → 415, code `UNSUPPORTED_MEDIA_TYPE`. They have different causes and require different client fixes.

### Exercise C — header missing on the error path

A valid GET returns `X-Request-Id`, while a GET for a missing SKU returns 404 without the correlation header. Would a happy-path-only test catch this?

**Answer:** No. You must assert headers on **negative responses**. The runnable test does this via `assertJsonHeaders(...)` for 404/400/415.

### Exercise D — right JSON but wrong status

An endpoint returns 200 instead of 201 along with the newly created JSON. Would a test doing only `assertEquals(body)` catch it? Add status, `Location`, and post-create GET assertions if needed.

### Exercise E — hiding internal messages

Jackson's `HttpMessageNotReadableException` contains parse offsets and class names. Why shouldn't `ex.getMessage()` be sent straight in the HTTP response? Design a public error code/message and verify `stackTrace` is absent.

### Exercise F — JSON null or missing?

Response A:

```json
{"note": null}
```

Response B:

```json
{}
```

In Jackson `JsonNode`, how do you verify `note` is present yet null in A, and completely absent in B?

**Answer:** `root.has("note")` + `root.get("note").isNull()` for A; `!root.has("note")` for B. Do not rely on `asText()` alone to distinguish both.

### Exercise G — comparing MockMvc and real HTTP

`@SpringBootTest` + `@AutoConfigureMockMvc` verifies status/headers/JSON properly. From that alone, can you claim the embedded server opened a port and TCP routing works?

**Answer:** No. `MockMvc` uses in-process mock requests/responses. When real transport is needed, add `RANDOM_PORT` + an HTTP client.

### Exercise H — transaction rollback

`@SpringBootTest(RANDOM_PORT)` sends a POST creating an order in the DB; the test method has `@Transactional` and expects the server write to roll back automatically when the JUnit method ends. Explain the mistake and propose a test data isolation strategy.

**Answer:** The HTTP client and server execute in different transactions/threads. Use an isolated DB/schema/fixture, clean up explicitly, test real transaction boundaries, and never use the production DB.

### Exercise I — contract-based security testing

An endpoint requires a token. Design test cases for no token, invalid token, insufficient privileges, and valid token. What status, headers, and public body should each case return? Note that 401 may include `WWW-Authenticate` and 403 must not leak internal resources; test the Spring Security filter chain in the right scope.

## 29. Checklist before signing off an HTTP integration test

- [ ] I have defined the **API contract** covering method, path, input, status, headers, JSON, and error responses.
- [ ] I chose the right test depth: slice, full MockMvc, real HTTP server, or E2E.
- [ ] If claiming "real HTTP", the test actually calls `RANDOM_PORT` through an HTTP client.
- [ ] I did not mock the very controller/service the test claims to verify.
- [ ] I assert **exact statuses**, not merely "no exception thrown".
- [ ] `Content-Type` matches the media type; avoid brittle exact raw string checks when valid charsets vary.
- [ ] `Cache-Control`, `Location`, `X-Request-Id`, and other headers are verified when part of the contract.
- [ ] JSON is parsed to assert values/types/field presence without depending on object key order or whitespace.
- [ ] Arrays, nested data, monetary amounts, Unicode, and date-times have meaningful assertions when relevant.
- [ ] 400, 404, and 415 errors have accurate **public codes/messages** and leak no stack traces, SQL, or secrets.
- [ ] Type-mismatch inputs and malformed JSON are tested separately from domain validation.
- [ ] I distinguish 201/202/204/304 from 200 and never force a JSON body onto empty responses.
- [ ] Security 401/403 and rate-limit 429 are tested with proper fixtures when the app has those branches.
- [ ] CORS, cookies, ETag, caching, and error localization are tested per the actual contract rather than out of habit.
- [ ] Transactions, DB fixtures, external APIs, and async side effects have dedicated testing/cleanup strategies.
- [ ] Tests run independently without relying on execution order, non-deterministic clocks, or hardcoded port 8080.
- [ ] A green test is meaningful: if business values or the HTTP response contract break, at least one assertion turns red.
- [ ] Test failures are diagnosed across **status, headers, and body**, never "fixed" by updating expectations to match a bug before confirming the contract.

**Conclusion:** HTTP integration contract testing verifies **client-observable behavior** through status, headers, JSON, and error messages. `@SpringBootTest(RANDOM_PORT)` verifies the path through a real server; `TestRestTemplate` retrieves full `ResponseEntity` objects including 4xx/5xx responses; Jackson or JSON assertions check content semantically. A durable test catches important regressions without depending on whitespace, JSON key order, internal exception details, or test order. When databases, security, external APIs, or transactions also need guarantees, add tests at those respective boundaries instead of claiming a single HTTP happy path tests the entire system.

### Official references

- Spring Boot 3.5 — Testing Spring Boot Applications, `RANDOM_PORT`, `TestRestTemplate`, transactions: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 — TestRestTemplate API and 4xx/5xx behavior: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/web/client/TestRestTemplate.html
- Spring Framework — MockMvc HTTP status/header/JSON testing: https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html
- Spring Framework — ResponseEntity: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html
- Spring Framework — Error Responses / ProblemDetail: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
- RFC 9110 — HTTP Semantics (status and headers): https://www.rfc-editor.org/rfc/rfc9110
- RFC 9457 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457
