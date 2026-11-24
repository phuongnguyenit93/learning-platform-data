# Meanings of HTTP Status Code Groups and Choosing the Right Response

When a client sends an HTTP request, the server returns a three-digit **status code** to communicate the processing outcome at the protocol level. Choosing the right status helps browsers, mobile apps, API clients, caches, proxies, and monitoring systems understand what happened, even without reading the JSON content.

For example, for the same message "order not found", a `404 Not Found` response expresses the result more accurately than `200 OK` with `{"success":false}`. The status reflects the outcome of the request; the body provides data or details for the caller to act on. The two parts must be consistent.

## 1. The Five HTTP Status Groups

| Group | Meaning | When commonly seen |
| --- | --- | --- |
| `1xx` — Informational | Provisional information; not yet the final outcome. | `100 Continue`, `101 Switching Protocols`, `103 Early Hints`. |
| `2xx` — Successful | The server processed or accepted the request according to the specific code's semantics. | Reading data, creating, updating, deleting, accepting async tasks. |
| `3xx` — Redirection | A different location/representation is needed or a conditional cache result applies. | URL moves, method change after POST, `304 Not Modified`. |
| `4xx` — Client Error | The request cannot be fulfilled due to syntax, authentication, permissions, resource state, or request-side conditions. | Malformed JSON, unauthenticated, unauthorized, resource absent, data conflict. |
| `5xx` — Server Error | The server/gateway failed to complete a valid request due to an error or service condition. | Internal error, overload, upstream error, gateway timeout. |

**Two points to remember:** `202 Accepted` only means *accepted*, not necessarily that the work has finished. `304 Not Modified` belongs to the 3xx group, yet it is a response to a cache check—not an error, and it does not instruct the client to navigate to a new URL.

## 2. Codes You Need to Understand and Use Properly

### 2.1. Success: 2xx

| Code | Meaning | Selection example |
| --- | --- | --- |
| `200 OK` | Request completed, usually returning a representation in the body. | `GET /api/orders/7` finds the order; `GET /api/orders` returns `[]` when the list is empty. |
| `201 Created` | Request created a resource. | `POST /api/orders` creates order 7; returns `Location: /api/orders/7` and optionally the new order body. |
| `202 Accepted` | Accepted for further processing, which may succeed or fail later. | Accepting a background report export request; provide a job status check URL if available. |
| `204 No Content` | Processed successfully with no response body. | `DELETE /api/orders/7` deleted; `PUT/PATCH` succeeded without returning a representation. |
| `206 Partial Content` | Returns part of a representation for a range request. | Downloading a file slice with appropriate `Range` and `Content-Range`. |

- **GET** normally returns `200` with data. A collection that exists with 0 items is still `200` with `[]`; use `404` only if the *requested resource itself* does not exist.
- **POST creating a resource** typically uses `201`; `Location` should point to the newly created resource. If the endpoint only enqueues a job, `202` is typically used.
- **PUT/PATCH** succeeding an update typically uses `200` if returning the updated data, or `204` if returning no body. `PUT` may use `201` when creating a new resource at the target URI.
- **DELETE** succeeding can use `204`, or `200` if returning a result; background deletion can use `202`. For a resource that is already absent, either `404` or `204` on repeated calls can be designed and documented consistently. *Idempotent* means the effect after multiple requests matches the effect after one request; it does **not** force every call to return the same status.

Do not send JSON such as `{}`, `null`, or a success message in the body of a `204`; if a body is needed, choose a code that allows a body, typically `200`.

### 2.2. Redirection and Caching: 3xx

| Code | Interpretation and notes |
| --- | --- |
| `301 Moved Permanently` | The URL has moved permanently; some clients may change `POST` to `GET` when following the redirect. |
| `302 Found` | Temporary redirect; with `POST`, traditional clients may also switch to `GET`. |
| `303 See Other` | After an action such as `POST`, directs the client to `GET` another resource, e.g., the newly created page/result. |
| `307 Temporary Redirect` | Temporary redirect while **preserving the method and body** when the client follows it. |
| `308 Permanent Redirect` | Permanent redirect while **preserving the method and body** when the client follows it. |
| `304 Not Modified` | Cache condition of `GET/HEAD` indicates the stored copy can be reused; no response body. |

An API changing the URL of an endpoint that receives `POST` and needs to keep the method should consider `307` or `308`. When directing a browser from a POST result to a GET page, `303` expresses intent more clearly than `302`. With `304`, a conditional request mechanism such as `If-None-Match`/`ETag` or `If-Modified-Since` must be present; do not use this code for "empty data".

### 2.3. Unfulfilled Client Requests: 4xx

| Code | Choose when | Avoid confusing with |
| --- | --- | --- |
| `400 Bad Request` | Malformed request structure/syntax, unparseable JSON, invalid parameters per API convention. | `422` for parseable content that violates semantic rules. |
| `401 Unauthorized` | Missing or invalid authentication credentials; the client needs valid authentication. | `403` when authenticated but denied permission. |
| `403 Forbidden` | The server understood the request but refuses it, usually due to insufficient permissions. | `401` if re-login/re-authentication is required. |
| `404 Not Found` | Resource not found at URI or existence intentionally hidden. | `200 []` for a valid but empty collection. |
| `405 Method Not Allowed` | The URI is handled, but not for the HTTP method being called. | `404`; a `405` response must include an `Allow` header listing supported methods. |
| `406 Not Acceptable` | No representation satisfies the client's `Accept` header conditions. | `415`, which concerns the request's `Content-Type`. |
| `408 Request Timeout` | The server did not receive the complete request within its wait time. | `504`, which is a gateway waiting too long for an upstream. |
| `409 Conflict` | The operation conflicts with the **current state of the resource**. | `422` for data violating state-independent rules; `412` for failed HTTP preconditions. |
| `410 Gone` | It is known that the resource previously existed but was deleted and its absence is permanent. | `404` if unknown or if you do not want to reveal it ever existed. |
| `412 Precondition Failed` | Conditions such as `If-Match`/`If-Unmodified-Since` did not match. | `409` for business conflicts not based on HTTP conditional headers. |
| `413 Content Too Large` | Request payload exceeds accepted limits. | `415` when the media type itself is unsupported. |
| `415 Unsupported Media Type` | The server cannot process the media type/format of the sent body. | `406` when the client does not accept the response type. |
| `422 Unprocessable Content` | Content type and syntax are understood, but the content has semantic errors and cannot be processed. | `400` when JSON syntax is broken; `409` on state conflict. |
| `428 Precondition Required` | The server requires the client to send a condition such as `If-Match` to prevent lost updates. | `412` when the client **did send** a condition and it failed. |
| `429 Too Many Requests` | The client exceeded the request/rate limit threshold. | `503` when the service is overloaded or temporarily down on the server side. |

Distinguish three easily confused situations:

1. Body `{"quantity":-2}` is valid JSON but violates the rule that quantity must be positive: you can return `422` (or `400` if the API standardizes on 400 for validation errors). Pick one convention and apply it consistently.
2. Two requests create a resource with an already-existing business key: `409 Conflict` can express a unique key / current-state conflict. If you choose to use `422` here, document the API contract clearly; do not vary arbitrarily across endpoints.
3. The client updates a resource with `If-Match: "v3"`, while the current ETag is `"v4"`: `412 Precondition Failed`. If the endpoint requires the condition and the client omitted it, consider `428 Precondition Required`.

**401 and 403:** `401` means the request lacks valid authentication, despite the English name "Unauthorized"; a `401` response uses an appropriate challenge via `WWW-Authenticate`. `403` means refusing to fulfill an understood request, typically due to missing permissions. For sensitive resources, a server may return `404` to avoid leaking existence, depending on security policy.

### 2.4. Server/Gateway Failures: 5xx

| Code | Choose when | Example |
| --- | --- | --- |
| `500 Internal Server Error` | An unexpected internal error prevents the server from completing the request. | Unhandled NullPointerException, unexpected internal state error. |
| `501 Not Implemented` | The server does not support the functionality required to fulfill the request, e.g., an unrecognized HTTP method. | Unlike `405`: the method is understood by the server but disallowed on a specific URI. |
| `502 Bad Gateway` | The gateway/proxy received an invalid response from an upstream server. | Reverse proxy encounters an upstream returning corrupt data. |
| `503 Service Unavailable` | The service is temporarily unavailable due to overload or maintenance. | Can include `Retry-After` to guide retries. |
| `504 Gateway Timeout` | The gateway/proxy did not receive a timely response from an upstream server. | API gateway timed out waiting for backend. |

Do not return `500` for an expected business condition such as "out of stock", "insufficient permissions", or "order already canceled". Those generally belong to appropriate `4xx` codes. For `5xx` errors, log a correlation ID for investigation, but do not expose stack traces, configuration secrets, or sensitive content in public response bodies. A network connection failure where the client receives no HTTP response has **no HTTP status code** to inspect, even though the client itself may report a network error.

## 3. Process for Selecting a Status for an Endpoint

Follow the actual outcome of the request instead of defaulting to `200`:

1. **Is the request understood and valid at the HTTP/API layer?** Malformed JSON → `400`; unsupported `Content-Type` → `415`; failed `Accept` negotiation → `406`.
2. **Is the caller authenticated and authorized?** Missing/invalid credentials → `401`; denied by permissions/policy → `403` (may be masked with `404` per policy).
3. **What are the resource state and execution conditions?** Not found → `404`; method unsupported at URI → `405`; state conflict → `409`; `If-Match` mismatch → `412`; validation of parsed content failed → `422` or `400` per API contract.
4. **Did the server/gateway encounter a failure?** Unexpected error → `500`; temporarily unavailable → `503`; gateway/upstream error → `502` or `504`.
5. **If successful, what is the outcome?** Representation returned → usually `200`; resource created → `201`; accepted for background processing → `202`; success without body → `204`; byte range returned → `206`.
6. **If handling caching/redirects**, pick the semantically right 3xx code (`304`, `303`, `307`, `308`, etc.) and set the corresponding headers.

### Decision Table by API Scenario

| Request / scenario | Suggested status | Reason |
| --- | --- | --- |
| `GET /products/8` found | `200` | Returns the product representation. |
| `GET /products?category=x` has zero items | `200` + `[]` | The collection is valid; the filter result is empty. |
| `GET /products/999` does not exist | `404` | Single resource not found. |
| `POST /products` creates a new product immediately | `201` + `Location` | A new resource exists with its own URI. |
| `POST /exports` enqueues a job | `202` | Work is not finished yet; return a tracking link. |
| `PUT /products/8` updates and returns object | `200` | Has a response body. |
| `PATCH /products/8` updates without returning object | `204` | No response body. |
| `DELETE /products/8` succeeds without returning object | `204` | Deleted, no body needed. |
| Malformed JSON request | `400` | Cannot parse request. |
| Valid JSON request with negative quantity | `422` or `400` per API standard | Semantic/validation error. |
| Unauthenticated call to an endpoint requiring login | `401` | Lacks valid authentication. |
| Authenticated but lacking admin permission | `403` | Authorization denied. |
| Placing an order with an already existing unique code | `409` | Conflicts with current state. |
| Updating with a stale ETag in `If-Match` | `412` | HTTP precondition failed. |
| Sending `Content-Type: text/plain` to a JSON-only endpoint | `415` | Request media type unsupported. |
| Rate limit exceeded | `429` | Caller must slow down or wait per policy. |
| Service temporarily paused for maintenance | `503` | Temporary server-side outage. |

No table can replace the endpoint contract: the same business operation may return different codes depending on whether the work actually completed or was merely accepted. Document possible statuses in your API documentation and test them.

## 4. Status, Headers, and Body Must Stay in Sync

An HTTP response consists of a status and headers; a body is optional depending on status semantics. Important combinations:

| Status | Headers / body to watch |
| --- | --- |
| `201` | `Location` typically indicates the URI of the new resource; body may return the new object. |
| `202` | Body/link should indicate how to check task status; do not promise the task will definitely succeed. |
| `204` | **No body**. |
| `206` | Range headers, especially `Content-Range`, must match the actual slice content. |
| `301/302/303/307/308` | `Location` indicates redirect target; the code choice governs method behavior. |
| `304` | **No body**; used with cache conditions and appropriate representation metadata. |
| `401` | `WWW-Authenticate` conveys the authentication challenge per protocol. |
| `405` | `Allow` header lists the methods supported on that resource. |
| `429/503` | May send `Retry-After` indicating when or how many seconds to wait. |

For API errors, you can use **Problem Details for HTTP APIs** with media type `application/problem+json`. Example of a validation error (illustrative, not Spring's default message strings):

```http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Invalid order data",
  "status": 422,
  "detail": "sku must have a value"
}
```

The `status` in the JSON is only supplementary information and must match the actual response status. Clients should check the HTTP status first before reading the body. For production APIs, you can add an application error code, `instance`, and a consistent correlation ID while avoiding sensitive data leaks.

## 5. Spring Boot 3.x (Java 17+) Example: Choosing Status with `ResponseEntity`

The example below uses **Spring MVC** and the `spring-boot-starter-web` dependency. Data is kept in RAM to focus on HTTP semantics; restarting the app loses created orders. Both files are in package `demo.web` inside a standard Gradle/Maven Spring Boot project.

File `src/main/java/demo/web/WebRuntimeApplication.java`:

```java
package demo.web;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebRuntimeApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebRuntimeApplication.class, args);
    }
}
```

File `src/main/java/demo/web/OrderController.java`:

```java
package demo.web;

import java.net.URI;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@RestController
@RequestMapping("/api/orders")
public class OrderController {
    private final Map<Long, Order> orders = new ConcurrentHashMap<>();
    private final AtomicLong nextId = new AtomicLong(1);

    public record NewOrder(String sku) {}
    public record Order(long id, String sku) {}

    @GetMapping("/{id}")
    public ResponseEntity<Order> get(@PathVariable long id) {
        Order order = orders.get(id);
        return order == null
                ? ResponseEntity.notFound().build()
                : ResponseEntity.ok(order);
    }

    @PostMapping
    public ResponseEntity<?> create(@RequestBody NewOrder request) {
        if (request == null || request.sku() == null || request.sku().isBlank()) {
            ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                    HttpStatus.UNPROCESSABLE_ENTITY, "sku must have a value");
            problem.setTitle("Invalid order data");
            return ResponseEntity.unprocessableEntity().body(problem);
        }

        long id = nextId.getAndIncrement();
        Order order = new Order(id, request.sku());
        orders.put(id, order);
        URI location = ServletUriComponentsBuilder.fromCurrentRequest()
                .path("/{id}").buildAndExpand(id).toUri();
        return ResponseEntity.created(location).body(order);
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable long id) {
        return orders.remove(id) == null
                ? ResponseEntity.notFound().build()
                : ResponseEntity.noContent().build();
    }
}
```

Start from the Spring Boot project root: `./gradlew bootRun` on Linux/macOS or `gradlew.bat bootRun` on Windows (using the project's Gradle wrapper). Test in a terminal with `curl`; the commands below use Bash syntax:

```bash
# First creation after starting the application
curl -i -X POST http://localhost:8080/api/orders \
  -H 'Content-Type: application/json' \
  -d '{"sku":"BOOK-1"}'

# Find the newly created order
curl -i http://localhost:8080/api/orders/1

# Syntactically valid data with a semantic error
curl -i -X POST http://localhost:8080/api/orders \
  -H 'Content-Type: application/json' \
  -d '{"sku":"  "}'

# Delete the order; a subsequent GET to the same URI will no longer find it
curl -i -X DELETE http://localhost:8080/api/orders/1
curl -i http://localhost:8080/api/orders/1
```

**Expected statuses**, assuming a freshly started app and the first order creation request: `201` with `Location` for the valid POST; `200` with the order JSON for GET; `422` with Problem Details for the POST with a whitespace-only `sku`; `204` without a body for the successful DELETE; `404` for GET after deletion. Extra headers, reason-phrase text, and error formatting are determined by the server/framework and do not need to match byte-for-byte. Syntactically broken JSON will be rejected by the Spring MVC layer before reaching validation logic and will typically return `400`.

In WebFlux, the **same HTTP status semantics** apply; code can use `ResponseEntity` in annotated controllers or `ServerResponse` with functional endpoints. Status selection does not depend on whether you use Servlet or reactive runtime.

## 6. Common Status Selection Mistakes

- **Always returning `200`**, even when the body says `"error"`: clients, proxies, and monitoring can misinterpret the outcome. Use codes reflecting the true outcome.
- **Returning `201` before the resource is created**: if only enqueued for processing, use `202`; do not claim creation is finished.
- **Using `204` and sending JSON**: contradicts no-content semantics; choose `200` if a body is needed.
- **Using `401` for every permission error**: distinguish authentication (`401`) from authorization/forbidden (`403`).
- **Using `404` for an empty list**: a successful filter returning zero items is normally `200 []`.
- **Using `409` for every input error**: distinguish state conflicts (`409`), failed HTTP preconditions (`412`), and semantically invalid data (`422/400`).
- **Using `500` for user-correctable errors**: map validation, authentication, permission, and business conflicts to appropriate `4xx` codes.
- **Using `302` when a POST/PUT method must be preserved across a redirect**: choose `307`/`308` if method and body must be preserved.
- **Equating idempotency with an unchanging status**: PUT/DELETE can change status across calls while still being idempotent in effect.
- **Forgetting required or helpful headers**: especially `Allow` for `405`, `WWW-Authenticate` challenge for `401`, `Location` for `201`/redirects, and retry hints when appropriate.

## 7. Self-Check Checklist for an API Endpoint

1. Did the request actually succeed, get accepted, or get rejected? Does the status state this **timing and outcome** accurately?
2. Are a newly created resource, an absent resource, an empty collection, a business conflict, and validation errors clearly distinguished?
3. Are authentication separated from authorization, and client errors separated from server errors?
4. Do cases with/without a response body align with `200/201/202/204/304`?
5. Are required headers (`Location`, `Allow`, `WWW-Authenticate`, `ETag`/`Retry-After` when applicable) sent?
6. Do the API documentation and automated tests verify both happy paths and expected `4xx/5xx` cases, error bodies, and related headers?

**Rule of thumb:** Choose an HTTP status based on the **semantics of the request outcome**, then design the body and headers to explain that outcome consistently. The `2xx` group records success/acceptance, `3xx` handles navigation/caching, `4xx` expresses requests that cannot be fulfilled under client conditions, and `5xx` indicates the service/gateway could not complete processing.
