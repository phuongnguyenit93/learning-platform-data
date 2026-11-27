# Forwarding GET, POST, and Other HTTP Methods With ProxyExchange in Spring Cloud Gateway

In microservices architectures, an application sometimes needs to **forward an HTTP request to another service directly from inside a controller**, rather than building a standalone Gateway Server with separate route definitions and a GatewayFilter chain. For example, a BFF (Backend for Frontend) application may receive `GET /bff/catalog/42` and call `catalog-service`; or an intermediary controller may forward `POST /bff/orders` to an order service after applying business validation.

**Spring Cloud Gateway Proxy Exchange** provides the `ProxyExchange<T>` object so controllers in **Spring MVC** or **Spring WebFlux** can perform simple downstream HTTP exchanges via methods matching **GET, POST, PUT, PATCH, DELETE**, and, on supported APIs, **HEAD, OPTIONS**. This lesson belongs to the **Proxy Exchange** chapter of the **SPRING_CLOUD_GATEWAY** module, focusing on **forwarding GET, POST, and other HTTP methods** with explicitly managed paths, queries, request bodies, headers, response statuses, and security boundaries.

The broader Spring Cloud Gateway context includes route predicates, filter chains, path/header transformations, service discovery, authentication, rate limiting, circuit breakers, retries, TLS, and request observability. However, remember one crucial point: **Proxy Exchange is a distinct architectural variant, not the Gateway Server WebFlux/Server MVC route engine shrunk into a controller**. Subsequent sections specify which components must be integrated separately so you do not assume Gateway Server filters or configurations apply automatically.

> **Version scope:** Examples are based on the Spring Cloud Gateway lines featuring the `spring-cloud-gateway-proxyexchange-webmvc` and `spring-cloud-gateway-proxyexchange-webflux` artifacts, documented in 4.3/5.0. In older releases, artifacts may be named `spring-cloud-gateway-mvc` or `spring-cloud-gateway-webflux`. Choose a compatible **Spring Boot + Spring Cloud release train** pair. API methods and body/header customization mechanisms should be checked against the Javadoc for your exact version before release. URIs in the examples point to localhost in a **lab environment**, not an Internet-facing open proxy.

## 1. How Does Proxy Exchange Differ From Gateway Server?

Spring Cloud Gateway has two main usage styles:

| Criterion | **Proxy Exchange** | **Gateway Server WebFlux / Server MVC** |
|---|---|---|
| Declaration style | `@RestController` / `@RequestMapping` + `ProxyExchange<T>` parameter | Route definitions or Java route DSL |
| Request matching | Spring MVC/WebFlux handler mapping, annotations | Gateway route predicates |
| Downstream dispatch | Call `proxy.uri(...).get()/post()/...` in controller | Routing handler/filter orchestrated by Gateway Server |
| Request transformation | Controller code and `ProxyExchange` API | GatewayFilter/HandlerFilterFunctions |
| Security | Web stack's Spring Security and controller logic | Corresponding Security plus Gateway route/filter policies |
| Rate limiting, Retry, CircuitBreaker | Must be designed/integrated at controller, client, or middleware | Built-in factories/integrations depending on Server stack |
| Best suited for | BFFs, selective proxy endpoints, controller-coupled logic | Multi-route API Gateways, consistent policies, large-scale routing |
| Pitfalls to avoid | Accidentally creating an open proxy or body buffering | Misconfiguring route filter order and gateway settings |

The official **Proxy Exchange** documentation states clearly that it is **an alternative gateway style**; Gateway Server guides do not automatically apply verbatim.

### Basic Processing Flow

~~~mermaid
sequenceDiagram
    participant C as Client
    participant W as Spring MVC/WebFlux + Security
    participant P as Controller with ProxyExchange
    participant B as Backend microservice
    C->>W: GET /bff/catalog/42
    W->>W: Handler mapping + authentication
    W->>P: Inject ProxyExchange
    P->>P: Pick backend URI from allowlist
    P->>B: proxy.uri(target).get()
    B-->>P: 200 + JSON + headers
    P-->>W: ResponseEntity
    W-->>C: 200 + JSON
~~~

**ProxyExchange does not decide which paths are public.** That responsibility lies with annotations such as `@GetMapping`, `@PostMapping`, `@RequestMapping(method=...)`, together with Spring Security and business validation.

## 2. Choosing the Right Dependency and Web Stack

Dedicated artifacts for Proxy Exchange in modern lines:

~~~groovy
// Choose ONLY ONE of the two runtime types below.
// Versions are managed by the compatible Spring Cloud BOM.

// Spring MVC / Servlet application:
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.cloud:spring-cloud-gateway-proxyexchange-webmvc'
}

// OR Spring WebFlux / reactive application:
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.cloud:spring-cloud-gateway-proxyexchange-webflux'
}
~~~

These are **two independent build options**, not a Gradle file from which to copy both `dependencies` blocks into one application. If the project uses an older release, check the artifact renaming table across release trains before copying coordinates.

| Case | Class Import | Common Controller Return Type |
|---|---|---|
| **MVC** | `org.springframework.cloud.gateway.mvc.ProxyExchange` | `ResponseEntity<?>` |
| **WebFlux** | `org.springframework.cloud.gateway.webflux.ProxyExchange` | `Mono<ResponseEntity<?>>` |

With MVC, requests run on the servlet stack; with WebFlux, handlers return a reactive publisher. **Never call `block()` to turn a `Mono` into a synchronous value on the event loop**, and never import `ProxyExchange` from one stack into the other.

### Do Not Confuse Dependencies

- `spring-cloud-starter-gateway-server-webflux` is for **Gateway Server WebFlux**, not a drop-in alias for `proxyexchange-webflux`.
- `spring-cloud-starter-gateway-server-webmvc` is for **Gateway Server Web MVC**, and does not mean a `ProxyExchange` controller is configured with the same behavior.
- Legacy artifact names `spring-cloud-gateway-mvc` / `spring-cloud-gateway-webflux` may appear in older code; do not mix two release lines just because the package imports look similar.
- Do not force Spring Framework/HTTP client versions differing from the BOM merely to make a Java method “compile”.

## 3. How Is the ProxyExchange Object Created and Used?

Inside a controller, Spring creates/provides `ProxyExchange<T>` as a **handler method parameter**, via the argument resolver registered by the corresponding module.

Minimal MVC example per documentation:

~~~java
import org.springframework.cloud.gateway.mvc.ProxyExchange;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class PingProxyController {

    @GetMapping("/bff/ping")
    ResponseEntity<?> ping(ProxyExchange<byte[]> proxy) throws Exception {
        return proxy.uri("http://localhost:9090/ping").get();
    }
}
~~~

Flow:

1. `@GetMapping("/bff/ping")` matches an incoming **GET**.
2. Spring injects a `ProxyExchange<byte[]>` into the controller method.
3. `uri(...)` selects the **downstream** URI.
4. `get()` executes an HTTP GET downstream.
5. `ResponseEntity<?>` wraps the returned status, headers, and body.

**`ProxyExchange<T>` uses the generic type `T` of the representation/response body**, not as a way to declare the HTTP method or guarantee body streaming. `byte[]` is used to illustrate raw response bytes, but response size and concurrency must be bounded in production.

### Configurable Call Chain Before Sending

~~~text
Incoming request
    -> Spring handler + method mapping
    -> ProxyExchange argument
    -> uri(trustedTarget)
    -> (optional) body(requestBody)
    -> (optional) header(name, value)
    -> get() / post() / put() / patch() / delete() / head() / options()
    -> Downstream ResponseEntity
    -> Client ResponseEntity
~~~

These steps illustrate the **API semantics**. Any header filtering or response mapping depends on the versioned API and is covered in later sections.

## 4. GET: Forwarding Requests Without a Body

Scenario: the client calls `GET /bff/catalog/42`; the controller forwards to `GET http://localhost:9090/catalog/items/42`.

~~~java
package example.bff;

import java.net.URI;

import org.springframework.cloud.gateway.mvc.ProxyExchange;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CatalogProxyController {

    private static final URI CATALOG_ORIGIN =
        URI.create("http://localhost:9090");

    @GetMapping("/bff/catalog/{id}")
    public ResponseEntity<?> getItem(
            @PathVariable long id,
            ProxyExchange<byte[]> proxy) throws Exception {

        String target = CATALOG_ORIGIN.resolve(
            "/catalog/items/" + id).toString();

        return proxy.uri(target).get();
    }
}
~~~

**Why use `long id`?** `@PathVariable long` restricts the path variable to a finite numeric type, reducing the risk of injecting slashes, queries, or URI schemes through a path parameter. For string identifiers, enforce charset/length rules and encode **each path segment** rather than concatenating raw user input into a URI.

### Testing Both Hops

~~~bash
# Call backend directly (baseline):
curl -i "http://localhost:9090/catalog/items/42"

# Call through the Proxy Exchange controller:
curl -i "http://localhost:8080/bff/catalog/42"
~~~

Check **method, path, status, body, and content type** on both the backend and client. Do not stop at seeing HTTP 200; a controller can still return 200 from a different handler if mappings collide.

### GET With Query Parameters

ProxyExchange has a `path(...)` utility to extract the suffix from an incoming request, but **do not assume path concatenation automatically preserves, normalizes, and encodes every query parameter**. When forwarding queries is required, construct the target URI from validated data using `UriComponentsBuilder`.

~~~java
import java.net.URI;
import org.springframework.web.util.UriComponentsBuilder;
import org.springframework.web.bind.annotation.RequestParam;

@GetMapping("/bff/search")
public ResponseEntity<?> search(
        @RequestParam(defaultValue = "vi") String lang,
        @RequestParam(defaultValue = "1") int page,
        ProxyExchange<byte[]> proxy) throws Exception {

    if (!lang.equals("vi") && !lang.equals("en")) {
        throw new IllegalArgumentException("Unsupported language");
    }
    if (page < 1 || page > 100) {
        throw new IllegalArgumentException("Invalid page");
    }

    String target = UriComponentsBuilder
        .fromUri(URI.create("http://localhost:9090"))
        .path("/catalog/search")
        .queryParam("lang", lang)
        .queryParam("page", page)
        .build()
        .encode()
        .toUriString();

    return proxy.uri(target).get();
}
~~~

This snippet shows the **controller method** portion. For out-of-range inputs, the application should have a `@ControllerAdvice` converting validation errors into HTTP 400 instead of exposing exception details by default. If the backend requires repeated query values or order preservation, define an explicit contract rather than collapsing parameters into a `Map` that loses information.

## 5. POST: Forwarding Requests With a Body to the Backend

`POST` typically carries JSON to create a resource. With ProxyExchange MVC, you can read the body in the handler and attach it to the downstream request with `proxy.body(...)`.

~~~java
import org.springframework.cloud.gateway.mvc.ProxyExchange;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

@PostMapping(
    path = "/bff/orders",
    consumes = MediaType.APPLICATION_JSON_VALUE)
public ResponseEntity<?> createOrder(
        @RequestBody byte[] body,
        ProxyExchange<byte[]> proxy) throws Exception {

    if (body.length > 64 * 1024) {
        return ResponseEntity.status(413).build();
    }

    return proxy
        .uri("http://localhost:9091/orders")
        .body(body)
        .post();
}
~~~

**Snippet note:** This is a **handler method** inside a `@RestController`; imports and the controller class were shown in Section 4. `@RequestBody byte[]` represents raw bytes to avoid unintended JSON transformation. However, **it still materializes the entire request body in controller memory**; checking `body.length` after reading **does not prevent memory/DoS costs while reading**. Enforce request size limits at ingress/web server and codec/body resolvers before reading.

### Not Every POST Should Be Proxied Verbatim

| POST Type | Goal | Notes |
|---|---|---|
| Create small JSON order | BFF forwards to orders backend | Idempotency key, validation, and authorization |
| Large multipart upload | Forward files/parts | Do not assume `byte[]` handles streaming/multipart efficiently |
| Payment | Sensitive side effect | Never retry indiscriminately; prevent duplicate charges |
| Callback/webhook | Signature computed on raw body | Do not alter bytes/headers before signature verification |
| POST creating long job | Async job | Consider `202 Accepted` + polling rather than blocking long |

**`proxy.body(body).post()` does not validate JSON schemas, ownership, or rate limits.** Those remain the responsibility of the Spring web layer and the backend.

### When the Body Is Decoded Into a DTO

You can pass an object as the body via the `body(Object)` API, but serialization may **alter bytes** relative to the original payload. This matters for HMAC/webhook signatures, canonical JSON, content length, and charsets. Use a DTO when you intentionally want **content transformation**, and test Content-Type/encoding/status rather than treating it as a byte-transparent proxy.

## 6. PUT and PATCH: Differences in Update Contracts

Under HTTP semantics, **PUT** typically represents creating or replacing the target resource state with the submitted representation, and is *idempotent* if implemented properly by the backend. **PATCH** represents a set of modifications and is **not idempotent by default**.

### PUT a Resource

~~~java
import org.springframework.web.bind.annotation.PutMapping;

@PutMapping(
    path = "/bff/items/{id}",
    consumes = MediaType.APPLICATION_JSON_VALUE)
public ResponseEntity<?> replaceItem(
        @PathVariable long id,
        @RequestBody byte[] body,
        ProxyExchange<byte[]> proxy) throws Exception {

    return proxy
        .uri("http://localhost:9091/items/" + id)
        .body(body)
        .put();
}
~~~

### PATCH a Resource

~~~java
import org.springframework.web.bind.annotation.PatchMapping;

@PatchMapping(
    path = "/bff/items/{id}",
    consumes = "application/merge-patch+json")
public ResponseEntity<?> patchItem(
        @PathVariable long id,
        @RequestBody byte[] patch,
        ProxyExchange<byte[]> proxy) throws Exception {

    return proxy
        .uri("http://localhost:9091/items/" + id)
        .body(patch)
        .patch();
}
~~~

These are two illustrative **handler methods** to place inside a `@RestController`. The sample URIs are fixed via an allowlist; never accept the target host from the client.

| Criterion | PUT | PATCH |
|---|---|---|
| Purpose | Set the desired representation/state | Apply partial modifications |
| Body | Resource representation | Patch document per media type |
| Example Content-Type | `application/json` | `application/merge-patch+json` or `application/json-patch+json` |
| Idempotency | By HTTP semantics: idempotent | Depends on patch type and operations |
| Retry in Gateway/BFF | Only when backend truly preserves semantics | Often needs idempotency key or deduplication logic |
| Concurrent updates | Needs ETag/versioning when appropriate | Even more critical for increment/decrement/append operations |

**Do not turn PATCH into PUT just to work around a missing API in one version.** If the actual runtime does not support `patch()` or the HTTP client does not handle that method properly, choose an appropriate version/transport and write an integration test for the real method.

## 7. DELETE: Having No Body Does Not Mean Having No Risk

A controller can forward DELETE via `delete()`:

~~~java
import org.springframework.web.bind.annotation.DeleteMapping;

@DeleteMapping("/bff/items/{id}")
public ResponseEntity<?> deleteItem(
        @PathVariable long id,
        ProxyExchange<byte[]> proxy) throws Exception {

    return proxy
        .uri("http://localhost:9091/items/" + id)
        .delete();
}
~~~

**Critical controls:**

- Must authenticate and authorize the user on the **specific resource ID**; `@DeleteMapping` only selects the HTTP method, not deletion permissions.
- A `204 No Content` response must be returned **without a body**; prevent serializers from injecting unwanted JSON.
- An already-deleted resource may return 404 or 204 depending on the backend contract; do not force every response to 200.
- DELETE semantics are idempotent regarding **target state**, though response statuses between the first and subsequent calls may differ.
- Require auditing and idempotency/concurrency policies if deletion triggers external side effects (emails, billing, workflows).

In common ProxyExchange APIs, `delete()` takes no body parameter. **Do not assume a DELETE with a body will be forwarded intact**, because HTTP clients, servers, and proxies treat DELETE bodies differently. If a body is strictly required, verify the specific API and downstream contract.

## 8. HEAD and OPTIONS: Supported Methods With Special Semantics

Documented MVC ProxyExchange APIs include `head()` and `options()`. Check the Javadoc for your **exact module and version**, especially when using the WebFlux API on another line.

### HEAD

HEAD mirrors GET for metadata, but the response **must not contain a response body**.

~~~java
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;

@RequestMapping(path = "/bff/items/{id}", method = RequestMethod.HEAD)
public ResponseEntity<?> headItem(
        @PathVariable long id,
        ProxyExchange<byte[]> proxy) throws Exception {

    return proxy
        .uri("http://localhost:9091/items/" + id)
        .head();
}
~~~

Verify `Content-Length`, `ETag`, `Last-Modified`, and other response headers **against the backend contract**. Do not call `get()` and strip/keep the body to emulate HEAD when the framework/proxy provides a dedicated HEAD method.

### OPTIONS

OPTIONS communicates the capabilities/communication options of the target resource, often returning an `Allow` header in some responses. However, **browser CORS preflight** also uses OPTIONS, carrying `Origin` and `Access-Control-Request-*` headers; having `proxy.options()` **does not automatically give you a valid CORS policy**.

~~~java
@RequestMapping(path = "/bff/items/{id}", method = RequestMethod.OPTIONS)
public ResponseEntity<?> optionsItem(
        @PathVariable long id,
        ProxyExchange<byte[]> proxy) throws Exception {

    return proxy
        .uri("http://localhost:9091/items/" + id)
        .options();
}
~~~

**Practical warning:** Servlet/Spring Security/CORS filters may handle OPTIONS *before* the request reaches the controller. Thus in production, you do not necessarily want a controller proxying OPTIONS. If you plan to forward OPTIONS, clearly assign responsibility across BFF, ingress, and backend, then test browser preflight rather than running a single `curl -X OPTIONS` without `Origin`.

### Methods Without Helpers or Extension Methods

`TRACE`, `CONNECT`, HTTP extension methods, or WebSocket upgrades **must not be assumed to have `proxy.trace()` or `proxy.connect()` methods**. If you need specialized proxying for those protocols, use a protocol-capable component/client/gateway, or return 405/501 per policy. Never try converting them into GET/POST, as that breaks HTTP semantics or introduces vulnerabilities.

## 9. Method Comparison Reference Table

| Incoming Method | Controller Annotation | ProxyExchange Call | Body to Check | Common Statuses to Preserve |
|---|---|---|---|---|
| GET | `@GetMapping` | `.get()` | Usually none | 200, 304, 404, 5xx |
| POST | `@PostMapping` | `.body(body).post()` | Can be large/sensitive | 200, 201, 202, 400, 409 |
| PUT | `@PutMapping` | `.body(body).put()` | Resource representation | 200, 201, 204, 409, 412 |
| PATCH | `@PatchMapping` | `.body(body).patch()` | Patch document | 200, 204, 409, 412, 422 |
| DELETE | `@DeleteMapping` | `.delete()` | Usually none; do not assume replay | 200, 202, 204, 404 |
| HEAD | `@RequestMapping(HEAD)` | `.head()` when supported | No response body | 200, 304, 404, 5xx |
| OPTIONS | `@RequestMapping(OPTIONS)` | `.options()` when supported | Usually none | 200, 204, 405 |
| TRACE/CONNECT | Do not expose arbitrarily | Do not assume helper exists | Protocol-specific | Usually restricted |

**This table is a guide to HTTP contracts**, not a guarantee that the framework assigns statuses automatically by method. Inspect whatever status the backend returns, and let the BFF change statuses only under an **explicit transformation contract**.

### When Multiple Methods Share One Target

You can use `@RequestMapping(path=..., method={...})` to match several methods and then dispatch with `switch`/`if` to supported helpers. However, avoid cramming all methods into one controller when auth, validation, and body-size policies differ. **Per-method handlers** are easier to test and prevent accidentally routing DELETE through GET.

## 10. WebFlux: Same Idea, Returning Mono<ResponseEntity<?>>

In an application using `spring-cloud-gateway-proxyexchange-webflux`, the import and return type change:

~~~java
package example.bff.reactive;

import java.net.URI;

import org.springframework.cloud.gateway.webflux.ProxyExchange;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReactiveCatalogProxyController {

    private static final URI CATALOG =
        URI.create("http://localhost:9090");

    @GetMapping("/bff/catalog/{id}")
    public Mono<ResponseEntity<?>> getItem(
            @PathVariable long id,
            ProxyExchange<byte[]> proxy) throws Exception {

        return proxy
            .uri(CATALOG.resolve("/catalog/items/" + id).toString())
            .get();
    }
}
~~~

**Never place both MVC and WebFlux controllers with overlapping mappings** in the same application. Choose one stack clearly.

WebFlux POST example:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

@PostMapping(
    path = "/bff/orders",
    consumes = MediaType.APPLICATION_JSON_VALUE)
public Mono<ResponseEntity<?>> createOrder(
        @RequestBody byte[] body,
        ProxyExchange<byte[]> proxy) throws Exception {

    if (body.length > 64 * 1024) {
        return Mono.just(ResponseEntity.status(413).build());
    }

    return proxy.uri("http://localhost:9091/orders")
        .body(body)
        .post();
}
~~~

This is an illustrative method inside a WebFlux controller. `@RequestBody byte[]` still **aggregates the request body** in memory before calling `post()`; writing it in reactive style does not turn it into a **streaming upload**. If you need to proxy large files, SSE, WebSockets, or full-duplex streams, evaluate **Gateway Server WebFlux** or dedicated routing, and enforce body limits at every layer.

### Never Call subscribe() or block() Yourself

~~~java
// Do NOT write this inside a WebFlux controller:
proxy.uri(target).get().subscribe(...);

// And do NOT block the event loop to extract ResponseEntity:
ResponseEntity<?> response = proxy.uri(target).get().block();
~~~

The publisher returned by the controller must be **subscribed to and lifecycle-managed by the framework**. If you need extra processing, compose with `map`/`flatMap`/`onErrorResume`; avoid swallowing real errors or leaking full stack traces to clients.

## 11. Paths and Queries: Never Build URIs From Unchecked Strings

A convenient pattern is extracting the request suffix:

~~~java
@GetMapping("/bff/files/**")
public ResponseEntity<?> fileProxy(
        ProxyExchange<byte[]> proxy) throws Exception {

    String tail = proxy.path("/bff/files/");
    return proxy.uri("http://localhost:9092/files/" + tail).get();
}
~~~

This illustrates the `proxy.path(...)` helper from the documentation. **Do not treat this as a complete SSRF/path-traversal defense.** If a client-controlled suffix is concatenated straight into a URI, edge cases with encoding, `?`, `#`, `..`, repeated slashes, percent-encoded slashes, or URL normalization can cause the Gateway and backend to interpret the path differently.

### Safer Workflow

1. Pick only from **approved origins/targets**.
2. Use strongly typed or regex-validated path variables (such as `long id`).
3. For a string path segment, validate charset and length, then encode **per segment**.
4. For query params, use `UriComponentsBuilder` and preserve repeated values when required by business logic.
5. Test URIs containing Unicode, whitespace, `%2F`, `..`, `?`, `#`, and duplicate query keys.
6. Verify which request path and query the backend actually receives.
7. Never let parameters such as `targetUrl`, `host`, or `callback` determine the outbound URI without an allowlist.

### Avoiding Open Proxy / SSRF

Do not write:

~~~java
// ANTI-PATTERN: turns the controller into an open proxy vulnerable to SSRF.
@GetMapping("/bff/proxy")
ResponseEntity<?> unsafe(
        @RequestParam String url,
        ProxyExchange<byte[]> proxy) throws Exception {
    return proxy.uri(url).get();
}
~~~

The `url` input could be swapped for `http://127.0.0.1/...`, metadata hosts, or unauthorized internal endpoints. **Never use this pattern in real applications.**

Instead, select targets via server-side codes:

~~~java
@GetMapping("/bff/public-info")
ResponseEntity<?> safe(
        @RequestParam String source,
        ProxyExchange<byte[]> proxy) throws Exception {

    String target = switch (source) {
        case "catalog" -> "http://localhost:9090/catalog/public-info";
        case "articles" -> "http://localhost:9093/articles/public-info";
        default -> null;
    };

    if (target == null) {
        return ResponseEntity.badRequest().build();
    }
    return proxy.uri(target).get();
}
~~~

This `switch` snippet uses modern Java syntax; target URIs are **server-defined**, never derived from free-form client strings. For production, add target selection permissions, TLS, egress controls, rate limits, and SSRF defense-in-depth.

## 12. Request Headers: Sensitive, Skipped, and Forwarded

In documented Proxy Exchange lines, there are special header categories:

- **Sensitive headers:** commonly `Cookie` and `Authorization` by default, **not automatically included in downstream requests**.
- **Skipped headers:** documented in recent lines as `Content-Length` and `Host`, because forwarding them verbatim can break when the downstream body/host differs from the incoming request.
- **Proxy/forwarding headers:** supports `X-Forwarded-*` headers; verify trust sources and append/rewrite behavior for your exact version.

Example when forwarding a POST from a BFF:

~~~http
POST /bff/orders HTTP/1.1
Host: bff.example.test
Authorization: Bearer client-token
Cookie: SESSION=client-session
Content-Type: application/json
Content-Length: 25

{"itemId":42,"qty":1}
~~~

The downstream request **should not be assumed identical byte-for-byte**. The HTTP client used by ProxyExchange may generate a new `Host` and recalculate framing; `Authorization`/`Cookie` may be stripped per sensitive policy.

### Why Are Authorization and Cookie Usually Stripped?

A client token may have an audience scoped strictly to the BFF, not to the backend. Forwarding the raw token or cookie to another service can:

- Leak credentials across trust boundaries.
- Cause backends to accept bearer tokens with the wrong audience.
- Accidentally share session cookies not intended for the downstream host.
- Expose tokens across logs/traces of more services than necessary when debugging.

If the backend genuinely needs to authenticate the BFF, design **service-to-service authentication**, mTLS, token exchange, or an audience-scoped downstream token. **Never disable sensitive filtering app-wide just to make one test case pass.**

### Setting Headers by Contract

~~~java
return proxy
    .uri("http://localhost:9090/catalog/items/42")
    .header("X-Edge-Request-Id", "lab-correlation-123")
    .get();
~~~

`header(name, value...)` sets a header for the **downstream call**. The lab value is a constant, but in production a correlation ID should be generated/normalized by a trusted source, never taken raw from user input. Avoid adding identity headers like `X-Authenticated-User` or `X-Tenant-Id` unless the backend has an established trust contract.

### Hop-by-Hop Headers

Headers such as `Connection`, `Keep-Alive`, `Proxy-Authenticate`, `Proxy-Authorization`, `TE`, `Trailer`, `Transfer-Encoding`, `Upgrade`, and any names listed in `Connection` have **per-hop** semantics. A compliant HTTP proxy must not blindly replay values that no longer apply.

Do not assume every edge case is handled identically by ProxyExchange across all versions and protocols. If you manually copy `HttpHeaders` or use a response mapper, strip hop-by-hop headers and test raw HTTP traffic.

## 13. Response Status/Body/Headers: Preserving the Downstream Contract

`ProxyExchange.get()` and sibling methods return a `ResponseEntity` in MVC or a `Mono<ResponseEntity>` in WebFlux. Based on the downstream body, status, and headers, the controller can **return them as-is** or **explicitly transform them**.

| Downstream Returns | What the BFF Should Consider |
|---|---|
| `200 OK` + JSON | Return accurate content type and body |
| `201 Created` + `Location` | Preserve new-resource semantics; check whether Location leaks internal hosts |
| `202 Accepted` | Preserve async task semantics |
| `204 No Content` | Do not attach a body |
| `304 Not Modified` | Emit no body; handle validators properly |
| `400/422` | Input error; do not turn into 500 |
| `401/403` | Never return 200/success fallback that defeats security semantics |
| `404` | Preserve missing-resource semantics per API contract |
| `409/412` | Conflict/concurrency status; do not retry blindly |
| `429` + `Retry-After` | Respect quotas and wait directives per contract |
| `502/503/504` | Distinguish downstream failures from HTTP client failures |

**Not every non-2xx returned by downstream becomes a Java exception.** The HTTP client mechanism and how ProxyExchange maps statuses can affect behavior, so test real 4xx/5xx codes rather than extrapolating from a single 200 GET path.

### Response Mapper When Modifying Headers

The Proxy Exchange documentation provides verb overloads accepting a **mapper** that converts the downstream `ResponseEntity` into the client `ResponseEntity`.

Conceptual example (matching the MVC API with `get(Function<...>)`):

~~~java
@GetMapping("/bff/public/42")
public ResponseEntity<?> publicItem(
        ProxyExchange<byte[]> proxy) throws Exception {

    return proxy
        .uri("http://localhost:9090/catalog/items/42")
        .get(response -> {
            // Example: prevent internal deployment headers from reaching clients.
            org.springframework.http.HttpHeaders outgoing =
                new org.springframework.http.HttpHeaders();

            outgoing.putAll(response.getHeaders());
            outgoing.remove("X-Internal-Backend-Node");

            return new ResponseEntity<>(
                response.getBody(),
                outgoing,
                response.getStatusCode());
        });
}
~~~

**This snippet is solely a response mapping pattern.** Check HTTP hop-by-hop headers, `Set-Cookie`, `Location`, CORS, `Content-Length`, `ETag`, `Content-Encoding`, and body-dependent headers before forwarding. If you modify the body, re-evaluate all related metadata.

Never inject `Cache-Control: public` onto responses containing tenant-specific or personal data. Response mapping **does not substitute for response cache correctness**.

## 14. MVC forward() Differs From HTTP Proxying to a Backend

In **Proxy Exchange MVC**, the documentation also describes a `forward(String)` method to **forward to an internal handler within the same application**.

~~~java
@GetMapping("/bff/local")
public String localForward(
        ProxyExchange<byte[]> proxy) throws Exception {

    return proxy.forward("/internal/handler");
}
~~~

**Note:** Exact return types and behavior of `forward(...)` depend on the versioned MVC API and how Spring MVC handles forwarded views/dispatchers. This example illustrates **local forwarding**, not an outbound HTTP call, and **should not be copied without checking the Javadoc**. Do not assume WebFlux Proxy Exchange has the same `forward` method.

| Behavior | `proxy.uri(...).get()` | MVC `proxy.forward(...)` |
|---|---|---|
| Crosses network to another service | Yes, if URI targets another server | No; internal dispatch to handler |
| Separate downstream HTTP status/body | Yes | Determined by in-app handler |
| Needs egress/TLS policy | Yes | No outbound hop, but must control handler/path |
| Risk | SSRF, header leaks, timeouts/downstream errors | Bypassing handler/management paths if forwarded improperly |

Never let users freely choose a forward path into `/actuator` or privileged internal endpoints. Forwarding is an in-app dispatch tool, **not an authorization mechanism**.

## 15. Body, Streaming, Multipart, and Size Limits

For ProxyExchange, using `byte[]` for request bodies and responses is simple but incurs significant **memory costs**:

- `@RequestBody byte[]` holds the payload in memory when the handler receives the request.
- `ProxyExchange<byte[]>` may hold the response body as a byte array.
- High concurrency multiplies memory usage by both request body and response body sizes.
- If the backend returns a long stream or SSE, `ResponseEntity<byte[]>` is unsuited for **unbounded streams**.
- For multipart payloads, decoding and re-encoding can alter `boundary` and `Content-Length`.

### Impact on File Uploads

| Upload | Recommendation |
|---|---|
| Small JSON, capped at 64 KiB | ProxyExchange with validated body can be reasonable |
| 100 MiB or multi-GiB files | Consider Gateway Server streaming or a dedicated upload service |
| Multi-part multipart requests | Test boundaries, temp storage, and body converters |
| Signed/checksummed files | Do not alter raw bytes before verification |
| Resumable uploads | Use an API with part IDs, offsets, checksums, and idempotency |

Do not raise codec buffers and Servlet multipart limits indefinitely to “fix ProxyExchange”. If you need end-to-end streaming with backpressure, a full Gateway Server is better suited than a BFF controller holding full byte arrays.

### Range / 206 Downloads

A client may send `Range: bytes=0-1023`, and the backend returns `206 Partial Content` with `Content-Range`. When ProxyExchange executes GET, verify whether the incoming `Range` header is forwarded downstream per policy, and whether the response preserves the right status, body length, and `ETag`/`Content-Range`.

**Never merge multiple ranges or alter bytes while keeping the old `Content-Range`.** If the BFF must serve large file downloads, `byte[]` can spike memory proportionally; prefer an explicit streaming download design.

## 16. Retry, CircuitBreaker, RateLimiter, and Service Discovery in Proxy Exchange

Because this is a **controller-style proxy**, do not assume Gateway Server's `Retry`, `RequestRateLimiter`, `CircuitBreaker` factories, or route predicates will run merely because they are on the classpath.

### Protection Layers That Must Be Designed Explicitly

| Need | Approach in Proxy Exchange |
|---|---|
| Authentication | Matching Spring Security for MVC/WebFlux |
| Authorization | Verify principal/scopes/resource ownership before outbound call |
| Rate limiting | Servlet/WebFlux filter, middleware, backend limit, or dedicated coordinator |
| Retry | HTTP client/retry policy with bounded attempts + backoff + deadline |
| Circuit breaker | Resilience4j/Spring Cloud CircuitBreaker or stack-appropriate client wrapper |
| Service discovery | Client resolver/load balancer/service catalog used by the app; do not assume `ProxyExchange.uri("lb://...")` works like Gateway Server |
| TLS | HTTPS client trust store/certificate validation + mTLS if needed |
| Observability | Micrometer/tracing spans per controller, target service, status, and latency |
| Response caching | Dedicated cache policy; avoid shared-caching user data |

### Do Not Assume `lb://` Works in ProxyExchange

In Gateway Server, `lb://service-id` URIs carry special meaning through the load-balancer filter chain. ProxyExchange normally expects a URI its module's HTTP client can call directly. **Do not casually write**:

~~~java
proxy.uri("lb://catalog-service/catalog/items/42").get();
~~~

expecting Gateway Server's LoadBalancer filter to resolve it. If service discovery is required, use URI resolution or client integration **documented for your exact Proxy Exchange version**, or resolve allowed targets at the application layer. Never construct hostnames directly from client input.

### Retries Can Duplicate Side Effects

A payment POST may be **processed successfully** by the backend while the response is lost on the return path; a BFF retry will send a second POST. Therefore:

- Never retry POST/PATCH blindly.
- Design idempotency keys **enforced by the backend**.
- Cap attempts, backoff, per-attempt timeouts, and **overall deadlines**.
- Never retry 401/403 or input errors like 400/422 as if they were outages.
- When receiving `429`/`Retry-After`, obey quota policies.
- If the BFF's caller also retries and the backend SDK retries as well, total outbound attempts can multiply beyond expectations.

### Circuit Breakers and Errors

A circuit breaker protecting downstream calls can produce a JSON fallback. **Do not turn every backend failure into 200**; for APIs requiring failure semantics, return 503/504 or the appropriate contract status. Once a response is committed (streaming), you cannot always switch to a fresh JSON fallback.

## 17. Security: Do Not Turn the BFF Into an Open Proxy

A proxy controller has authority to send HTTP requests from the BFF server. If callers can choose the target URL themselves, a public endpoint becomes an **SSRF entry point**.

~~~mermaid
flowchart TD
    U["Client"] --> A["Spring Security + input validation"]
    A --> D{"Approved target code?"}
    D -->|No| R["400/403 + audit"]
    D -->|Yes| M["Server-side mapping → URI"]
    M --> E["Network egress + DNS/TLS policy"]
    E --> B["Downstream service"]
    B --> C["Response mapper + header safety"]
    C --> U
    X["Raw url/host from client"] -.->|"Never used directly"| M
~~~

### Minimum Policy

1. **Specify origins/targets from vetted configuration**, never letting callers pass free-form URIs.
2. **Validate every path/query segment** and control URL encoding; never concatenate arbitrary raw paths/queries.
3. **Block sensitive internal destinations** with egress firewalls/NetworkPolicies, not just hostname string checks.
4. For HTTPS, **never disable TLS certificate/hostname verification**; if client identity is needed, use mTLS per contract.
5. Never forward `Authorization`/`Cookie` across trust boundaries unnecessarily. Use service identities when backends need them.
6. Never trust client-supplied `X-Forwarded-For`, `Host`, `X-Authenticated-User`, or `X-Tenant-Id` as authentication proof.
7. Use **Spring Security** to verify controller and resource access permissions before outbound calls.
8. Bound request body sizes, response sizes, timeouts, connection pools, and concurrent calls.
9. Never log raw tokens, cookies, sensitive request bodies, queries with PII, or exception messages in metric labels.
10. Especially for `POST`, `PUT`, `PATCH`, `DELETE`, verify **CSRF** if the app uses cookie-authenticated browser sessions; never disable CSRF carelessly.
11. If supporting CORS, allow only vetted origins/headers/methods; OPTIONS preflight is not a business call to forward indiscriminately.
12. Ensure backends still enforce resource authorization; the BFF does not replace all downstream protections.

**`ProxyExchange.header(...)` is not authentication.** Adding a BFF-generated header is only trustworthy when the backend verifies the caller/service identity properly.

## 18. Lab: Creating an Echo Backend to Inspect Method, Path, Body, and Headers

To verify each HTTP method, a lab backend at `http://localhost:9091` can return responses containing the method, path, and some **non-sensitive** metadata.

Example Spring MVC controller strictly for a **test backend**, not ProxyExchange:

~~~java
package example.backend.lab;

import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MethodEchoController {

    @RequestMapping(
        path = "/lab/echo",
        method = {
            RequestMethod.GET,
            RequestMethod.POST,
            RequestMethod.PUT,
            RequestMethod.PATCH,
            RequestMethod.DELETE
        })
    public ResponseEntity<Map<String, Object>> echo(
            jakarta.servlet.http.HttpServletRequest request,
            @RequestBody(required = false) byte[] body) {

        return ResponseEntity.ok(Map.of(
            "method", request.getMethod(),
            "path", request.getRequestURI(),
            "bytes", body == null ? 0 : body.length
        ));
    }
}
~~~

The backend does not echo tokens, cookies, or user data. For `HEAD`/`OPTIONS`, add dedicated endpoints or use a mock HTTP server that implements their exact semantics; the echo controller above intentionally covers only the five most common methods.

### Corresponding ProxyExchange Route in the BFF

For the `/lab/echo` backend, create a dedicated controller following one rule per method, illustrated here with a POST handler:

~~~java
@PostMapping("/bff/lab/echo")
public ResponseEntity<?> proxyLabPost(
        @RequestBody byte[] body,
        ProxyExchange<byte[]> proxy) throws Exception {

    return proxy
        .uri("http://localhost:9091/lab/echo")
        .body(body)
        .post();
}
~~~

The GET/PUT/PATCH/DELETE handler methods follow Sections 4–7, simply pointing the target URI to `http://localhost:9091/lab/echo`.

### Step 1 — GET

~~~bash
curl -i "http://localhost:8080/bff/lab/echo"
~~~

Expect the backend to record `method=GET`, `path=/lab/echo` when the BFF has the matching GET handler.

### Step 2 — Small JSON POST

~~~bash
curl -i -X POST \
  -H "Content-Type: application/json" \
  --data-binary '{"itemId":42,"qty":1}' \
  "http://localhost:8080/bff/lab/echo"
~~~

The backend should see `method=POST` and `bytes` matching the raw payload sent. If the byte count differs, inspect body conversion, charset, Content-Encoding, and serialization.

### Step 3 — PUT

~~~bash
curl -i -X PUT \
  -H "Content-Type: application/json" \
  --data-binary '{"name":"new-title"}' \
  "http://localhost:8080/bff/lab/echo"
~~~

### Step 4 — PATCH

~~~bash
curl -i -X PATCH \
  -H "Content-Type: application/merge-patch+json" \
  --data-binary '{"name":"updated"}' \
  "http://localhost:8080/bff/lab/echo"
~~~

### Step 5 — DELETE

~~~bash
curl -i -X DELETE \
  "http://localhost:8080/bff/lab/echo"
~~~

With DELETE, expect no body if none was sent. Never test against real production resources; lab endpoints must not delete sensitive data.

### Step 6 — HEAD and OPTIONS

~~~bash
curl -I "http://localhost:8080/bff/items/42"

curl -i -X OPTIONS \
  "http://localhost:8080/bff/items/42"

# CORS preflight differs from plain OPTIONS:
curl -i -X OPTIONS \
  -H "Origin: https://app.example.test" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: Content-Type" \
  "http://localhost:8080/bff/orders"
~~~

Compare the empty body of HEAD, any `Allow` header, and the actual CORS policy. The HTTP status may be produced by Spring Security or a Servlet CORS filter before reaching the controller; record **which component produced the response** rather than assuming every OPTIONS was proxied.

### Step 7 — Disallow Raw Target URLs

~~~bash
# Run only if the BFF has a lab endpoint taking targetCode (not a raw url).
curl -i "http://localhost:8080/bff/public-info?source=unknown"
~~~

Expect the code to be rejected; never feed real loopback/metadata addresses into an open-proxy endpoint to test in production.

## 19. End-to-End Testing Matrix

| Case | Primary Expectation | Secondary Checks |
|---|---|---|
| GET existing item | Downstream GET, accurate status/body | Query, Content-Type, ETag |
| GET missing item | 404 per contract | Not silently turned into 200 |
| GET repeated query | Preserves defined semantics | No dropped parameters or bad encoding |
| POST small JSON | Downstream POST with exact bytes | Content-Type/length, authorization |
| POST malformed JSON | 400/422 per policy | No stack trace leaked |
| Non-idempotent POST timeout | No blind retries | Idempotency/deduplication |
| PUT replace resource | Downstream PUT | ETag/If-Match, concurrency |
| PATCH document | Downstream PATCH | Media type, partial update correctness |
| Authorized DELETE | Downstream DELETE | 204 without body, audit |
| Unauthenticated DELETE | 401/403 before outbound | Backend never called |
| HEAD | No response body | Accurate headers/ETag |
| OPTIONS preflight | CORS responds per policy | Does not bypass security |
| 201 + Location | Does not leak internal hostname | Preserve/normalize Location per contract |
| 429 + Retry-After | No retry storm | Quota policy |
| Downstream 5xx | Accurate error semantics | Timeouts/circuit breaker/fallback |
| Incoming Authorization/Cookie | Not forwarded accidentally | Sensitive header policy |
| Host/Content-Length | Valid downstream framing | No erroneous header copying |
| Large body/response | Limits enforced | Memory, concurrency, timeouts |
| Client-supplied URL | No open proxy created | SSRF/egress controls |
| Bad TLS certificate | Connection safely rejected | Trust-all not enabled |
| Multiple BFF nodes | Consistent behavior | Metrics/traces/rollouts |

**Never measure “correct proxying” solely by HTTP 200.** For methods with side effects, verify **which method the backend actually received and that the side effect occurred exactly once**.

## 20. Troubleshooting Common Errors

| Symptom | Likely Causes to Check | How to Resolve |
|---|---|---|
| Cannot inject `ProxyExchange` | Wrong MVC/WebFlux module or auto-configuration | Verify artifacts/stack and argument resolver |
| Package not found at compile time | Imported class from another version | Use exact module package: `gateway.mvc` or `gateway.webflux` |
| GET 404 before reaching backend | `@GetMapping` did not match | Check URL, context path, security |
| Backend returns 404 despite controller match | Wrong downstream URI/path | Check `uri(...)`, path variables, queries |
| POST backend receives empty body | Missing `body(...)` or body resolver consumed/transformed it | Test byte count, media type, handler signatures |
| POST has body but wrong Content-Length | Bytes changed while trying to forward old header | Do not copy hop-specific framing |
| PUT/PATCH returns 405 | Backend lacks method; wrong proxy mapping or HTTP client | Inspect both hops |
| DELETE returns 200 instead of 204 | Controller/serializer altered response | Preserve status/body contract |
| HEAD contains a body | Handler/proxy response mapping violates HEAD semantics | Use `head()` if supported and test |
| OPTIONS gets 401/403 | CORS/Security blocked preflight | Configure CORS policy properly before controller |
| User logs in fine but backend returns 401 | Sensitive Authorization not forwarded automatically | Use service identity/token exchange; do not relax globally |
| Cookie does not reach backend | Sensitive header policy | Evaluate trust boundary; do not treat as a bug |
| Backend sees wrong BFF Host | Copied Host manually or wrong proxy routing | Let HTTP client generate Host matching target |
| Query/encoding corrupted | Raw URI concatenation, double encoding, lost repeated params | Use `UriComponentsBuilder` and contract tests |
| `lb://` does not work | Confused Gateway Server LB filter with ProxyExchange client | Use a supported resolver/client |
| Open proxy discovered | Controller accepts raw `url`/`host` | Switch to server-side allowlist + egress ACL |
| 503 spikes after adding retries | Retry storm, missing deadline | Reduce attempts, add backoff and circuit breaker |
| Multipart/streaming consumes too much memory | `byte[]` body + response aggregation | Choose a streaming architecture |
| Trace does not link downstream | HTTP client lacks tracing instrumentation | Verify instrumentation and propagation |
| Only one node fails | Different BOM/version/config/target trust | Compare deployments and config sources |

### Six-Layer Inspection Procedure

1. **Controller mapping:** did the request hit the right `@GetMapping`/`@PostMapping`?
2. **ProxyExchange injection:** are the MVC/WebFlux module and argument resolver aligned?
3. **Target URI:** is `proxy.uri(...)` an approved destination with accurate path/query/encoding?
4. **Request forwarding:** do the HTTP method, body bytes, and headers reaching the backend match the contract?
5. **Downstream response:** were status, body, headers, and exception/timeout mappings altered?
6. **Cross-cutting policies:** are authentication, rate limiting, retries, circuit breakers, TLS, and observability integrated separately and measurable?

Never “quick-fix” issues by letting handlers accept `RequestMethod.values()`, accepting raw URLs, or forwarding all Authorization/Cookies; those shortcuts create security bypasses.

## 21. Pre-Production Checklist

- [ ] I distinguish **Proxy Exchange** from **Gateway Server WebFlux/Server MVC**.
- [ ] I selected the right `proxyexchange-webmvc` or `proxyexchange-webflux` artifact for my web stack.
- [ ] I understand `ProxyExchange<byte[]>` is a controller parameter, not a route predicate.
- [ ] I use `get()` for GET and preserve query/path semantics.
- [ ] I use `body(body).post()` for POST with payloads and bound body sizes early.
- [ ] I distinguish PUT replacement from PATCH partial updates; tested Content-Type/ETag/concurrency.
- [ ] I enforce resource permissions on DELETE and preserve 204/404 status contracts.
- [ ] I know HEAD must have no response body and OPTIONS/CORS preflight have distinct responsibilities.
- [ ] I do not assume TRACE/CONNECT/WebSocket have equivalent ProxyExchange helpers.
- [ ] I do not confuse MVC `ResponseEntity` with WebFlux `Mono<ResponseEntity>` or call `block()` on the event loop.
- [ ] I do not let clients pick target URLs; all URIs come from server-side allowlists/mappings.
- [ ] I validate/encode path segments, query values, repeated parameters, and host trust.
- [ ] I know default sensitive headers include Cookie and Authorization in documented releases.
- [ ] I understand skipped headers like Host/Content-Length may not be forwarded because framing changes.
- [ ] I handle hop-by-hop headers properly instead of copying every HTTP header blindly.
- [ ] I verify `201 Location`, `204`, `304`, `429 Retry-After`, and downstream 4xx/5xx statuses.
- [ ] I do not use response mappers to leak internal backend headers or invalidate Content-Length/ETag.
- [ ] I do not treat MVC `proxy.forward()` as a remote HTTP proxy or let callers forward to admin handlers.
- [ ] I do not use `byte[]` to proxy large files/SSE/unbounded streams without proving bounded memory.
- [ ] I enforce Spring Security, resource-level authorization, and CSRF/CORS per client type.
- [ ] I design rate limits, circuit breakers, retries, and service discovery **specifically for Proxy Exchange**, rather than expecting Gateway Server factories to run automatically.
- [ ] I configure per-attempt timeouts/overall deadlines, idempotency for POST/PATCH, and strict retry conditions.
- [ ] I protect TLS and DNS/egress, and never disable certificate validation.
- [ ] I monitor incoming requests, outbound attempts, backend latency/status, P95/P99, and correlation IDs.
- [ ] I ran GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS tests through both the BFF and the echo backend.
- [ ] I tested negative scenarios: unauthorized, missing target, malformed body, partial download, open proxy, and retry storm.

## Official References

- [Spring Cloud Gateway — Proxy Exchange Gateway with Spring Web MVC or WebFlux](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-proxy-exchange.html) — artifacts, injecting `ProxyExchange`, MVC/WebFlux examples, paths, headers, and response mappers.
- [Spring Cloud Gateway 4.3 — Proxy Exchange](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-proxy-exchange.html) — verifying behavior of a specific release train.
- [Spring Cloud Gateway 5.0 — Proxy Exchange](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-proxy-exchange.html) — version upgrade comparison.
- [Spring Cloud Gateway — Project](https://spring.io/projects/spring-cloud-gateway) — choosing compatible release trains and BOMs.
- [Spring Framework — Spring MVC Controller Methods](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html) — `@RequestMapping`, `@RequestBody`, `ResponseEntity`.
- [Spring Framework — WebFlux Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html) — `Mono<ResponseEntity<?>>` and reactive handlers.
- [Spring Security — Servlet](https://docs.spring.io/spring-security/reference/servlet/index.html) — authentication and authorization in MVC.
- [Spring Security — Reactive](https://docs.spring.io/spring-security/reference/reactive/index.html) — authentication and authorization in WebFlux.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110) — GET/HEAD/POST/PUT/PATCH/DELETE/OPTIONS, status codes, representations, and hop-specific fields.
- [OWASP — SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html) — URI allowlists, DNS, egress, and trust boundaries.

**Remember:** **ProxyExchange** allows a **Spring MVC or WebFlux** controller to actively call downstream services via `get()`, `body(...).post()`, `put()`, `patch()`, `delete()`, and other supported HTTP methods. To forward accurately, **preserve method, path/query, payload, and response status/headers per contract**, while authenticating callers, blocking arbitrary target URIs/SSRF, controlling sensitive/hop-by-hop headers, and bounding memory and retries. **Proxy Exchange is a controller-style proxy tool, not a shortcut to obtain all of Gateway Server's route and filter policies.**
