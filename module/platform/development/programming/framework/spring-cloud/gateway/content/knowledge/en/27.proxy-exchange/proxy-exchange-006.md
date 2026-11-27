# Adding Headers and Mapping the Returned ResponseEntity

## 1. Why Does Proxy Exchange Need to Control Both HTTP Directions?

In microservices architectures, **Spring Cloud Gateway** helps build a unified entry point: routing requests via predicates, coordinating filter chains, transforming paths/headers, discovering services, and protecting traffic with authentication/authorization, rate limiting, circuit breakers, retries, TLS, and observability. For tasks that call for writing **proxy logic directly inside a controller**, Spring Cloud Gateway also offers the **Proxy Exchange** variant, letting you use a `ProxyExchange<T>` object as a handler parameter.

Suppose a client calls `GET /api/catalog/items/42`; the controller wants to call `GET https://catalog.internal.example/items/42`, add a header identifying the **trusted internal caller**, receive the Catalog response, and add a header for the client. There are two independent steps:

1. **Outbound request:** Build the URL, pick the HTTP method, and **set headers sent to Catalog**.
2. **Inbound → outbound response:** Receive `ResponseEntity<T>` from Catalog, and **map status, headers, and body** onto the `ResponseEntity<S>` returned to the client.

If you conflate these two directions, you can add headers to the wrong side, leak JWTs, pass backend cookies to browsers, drop `Content-Type`, write an invalid `Content-Length`, or turn HTTP 503 into 200 without realizing it.

~~~mermaid
flowchart LR
    C["Client"] -->|"Request headers / body"| H["MVC or WebFlux controller"]
    H -->|"ProxyExchange.header(...) / uri(...) / get(...)"| B["Catalog backend"]
    B -->|"HTTP status, headers, body"| M["ResponseEntity mapper"]
    M -->|"Final status, safe headers, body"| C
~~~

**Topic:** “Adding Headers and Mapping the Returned ResponseEntity”, in the **Proxy Exchange** chapter. This lesson focuses on using `ProxyExchange` deliberately without confusing it with **Gateway Server WebFlux** or **Gateway Server Web MVC** route/filter configurations.

### Learning Objectives

After this lesson, you will be able to:

1. Identify the exact **direction** of headers when calling `proxy.header(...)` versus modifying `ResponseEntity`.
2. Use `ProxyExchange<byte[]>`, `.uri(...)`, `.get(...)`, and the mapper overload `Function<ResponseEntity<T>, ResponseEntity<S>>`.
3. Preserve or intentionally modify **HTTP status, Content-Type, Cache-Control, ETag, Location, Set-Cookie, and body**.
4. Distinguish `HttpHeaders.add`, `set`, `put`, and multi-value header rules.
5. Understand defaults for **sensitive headers** such as `Authorization`, `Cookie` and **skipped headers** such as `Host`, `Content-Length` per version.
6. Choose a **header allowlist** policy, strip hop-by-hop headers, and prevent clients from controlling upstreams or token egress.
7. Explain the difference between **Proxy Exchange MVC** returning `ResponseEntity` and **Proxy Exchange WebFlux** returning `Mono<ResponseEntity>`.
8. Write a stub backend and HTTP integration tests proving **which headers the backend received** and **which response the client received**.
9. Handle transport errors, HTTP 4xx/5xx, large/streaming response bodies, redirects, and caching according to contract.

> **Version scope:** Primary examples use **Proxy Exchange MVC** from Spring Cloud Gateway lines containing `org.springframework.cloud.gateway.mvc.ProxyExchange`. Artifacts were renamed across releases; if using WebFlux, substitute the matching dependency, package/API, and return type for your version. Do not assume Gateway Server's `GlobalFilter` or `GatewayFilterFactory` configurations apply to Proxy Exchange.

## 2. Proxy Exchange Is a Different Variant From Gateway Server

Spring Cloud Gateway distinguishes two implementation styles:

| Feature | Gateway **Proxy Exchange** | Gateway **Server** |
| --- | --- | --- |
| Declaration point | `@GetMapping`, `@PostMapping`, and controllers/handlers accepting `ProxyExchange` | Route definitions, route predicates, filter factories/DSL |
| Primary role | Build a few HTTP proxy endpoints with direct application logic | Full routing gateway and shared infrastructure policies |
| Web MVC | `ProxyExchange<T>` in MVC controller, returns `ResponseEntity<T>` | Server Web MVC built on WebMvc.fn and its own filter chain |
| WebFlux | `ProxyExchange<T>` in reactive controller, returns `Mono<ResponseEntity<T>>` | Server WebFlux with `ServerWebExchange`, `GatewayFilter`, `Mono<Void>` |
| Adding request headers | `proxy.header(...)` or `proxy.headers(...)` | Route filters such as `AddRequestHeader` per variant |
| Mapping response | Mapper passed to `get/post/put/...` or building `ResponseEntity` after call | Route response filters / dedicated HTTP infrastructure |
| Policy enforcement | Spring MVC/WebFlux, Spring Security, and custom controller code | Gateway route predicates/filters plus Spring Security |

**Installing Proxy Exchange does not mean** Gateway Server's `Retry`, `CircuitBreaker`, `TokenRelay`, and `RequestRateLimiter` filters automatically appear in controllers. To get those policies, choose the right variant, dependencies, and integrations—or use Gateway Server when infrastructure routing dominates. **Do not rebuild a full-featured Gateway Server out of ProxyExchange controllers.**

### Two HTTP Hops and Two Header Sets

~~~text
Hop 1: Client -> Proxy Exchange application
    Client request headers
       |
       v
    Controller/Spring Security decides trusted data
       |
       v
Hop 2: Proxy Exchange -> Upstream service
    Selected/modified request headers for upstream
       |
       v
    Upstream response: status + headers + body
       |
       v
    Controller mapper builds ResponseEntity for client
       |
       v
Hop 1: Proxy Exchange application -> Client
    Client-facing response headers
~~~

A `X-Gateway-Source` header placed on the outbound request is **not** a response header. Conversely, an `X-Proxy-Handled` header added to the returned `ResponseEntity` is **not automatically sent to the backend**. When debugging, always ask: **“Who receives this header?”**

## 3. Dependencies and Return Types: MVC vs. WebFlux

Recent Spring Cloud Gateway lines provide dedicated artifacts:

~~~xml
<!-- Proxy Exchange MVC: pick the right version via Spring Cloud BOM. -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-gateway-proxyexchange-webmvc</artifactId>
</dependency>
~~~

~~~xml
<!-- Use only when the app is Proxy Exchange WebFlux. -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-gateway-proxyexchange-webflux</artifactId>
</dependency>
~~~

In releases prior to the artifact rename, names like `spring-cloud-gateway-mvc` or `spring-cloud-gateway-webflux` were used for **Proxy Exchange**. Today, clearly distinguish `proxyexchange-...` artifacts from `server-...` artifacts; the Spring Cloud BOM must match your project's Spring Boot version.

### 3.1. MVC: Returning ResponseEntity Directly

~~~java
import org.springframework.cloud.gateway.mvc.ProxyExchange;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class SimpleMvcProxyController {

    @GetMapping("/demo/image")
    ResponseEntity<byte[]> image(ProxyExchange<byte[]> proxy) throws Exception {
        return proxy.uri("http://127.0.0.1:9001/images/logo.png").get();
    }
}
~~~

This example is **strictly for a lab environment**, assuming backend 9001 serves an image. A Servlet/MVC controller may invoke its HTTP client blocking-style; configure connect/response timeouts and connection pools appropriately for deployment.

### 3.2. WebFlux: Returning Mono<ResponseEntity<?>>

~~~java
import org.springframework.cloud.gateway.webflux.ProxyExchange;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class SimpleReactiveProxyController {

    @GetMapping("/demo/image")
    Mono<ResponseEntity<byte[]>> image(ProxyExchange<byte[]> proxy) {
        return proxy.uri("http://127.0.0.1:9001/images/logo.png").get();
    }
}
~~~

**Use only one of the two examples matching your real stack.** The `webflux.ProxyExchange` package and method signatures may differ across releases; check the Javadoc for your locked dependency. Never call `block()` or `subscribe()` inside a WebFlux controller to extract `ResponseEntity`, as that breaks reactive/cancellation lifecycles.

### 3.3. What Does Generic T Mean?

In `ProxyExchange<T>`, **`T` is the response body type** materialized by the HTTP client/converters. For instance:

| `T` | Good Fit | Risks |
| --- | --- | --- |
| `byte[]` | Forwarding JSON bytes, images, or small files without domain parsing | May hold the entire body in memory |
| `String` | Text responses with known charset | Can alter bytes/encoding or corrupt binary payloads |
| DTO | Need to read/modify schema-backed JSON fields | Handles only matching content types/JSON; risks dropping undeclared fields |
| `Object` or `?` | Passthrough/generic response demos | Message converters and conversion behavior must be verified |

If the response is **video, large files, SSE/NDJSON, or long-lived streams**, do not assume `ProxyExchange<byte[]>` is an efficient streaming mechanism. Verify buffering, connection lifetimes, backpressure, and choose an appropriate proxy tool.

## 4. What Does ResponseEntity Contain?

Spring's `ResponseEntity<T>` is an object with three parts:

~~~text
ResponseEntity<T>
   |
   +-- HttpStatusCode: 200, 201, 204, 301, 304, 404, 503...
   |
   +-- HttpHeaders:
   |     Content-Type
   |     Cache-Control
   |     ETag
   |     Set-Cookie
   |     Location
   |     Vary
   |     ...
   |
   +-- T body: byte[], String, DTO, or null
~~~

| API | Meaning |
| --- | --- |
| `response.getStatusCode()` | Upstream status received by the HTTP client and wrapped by ProxyExchange into ResponseEntity |
| `response.getHeaders()` | Upstream header set, possibly multiple values per name |
| `response.getBody()` | Body converted to type `T` by converters |
| `ResponseEntity.status(status)` | Starts building a new response with the specified status |
| `ResponseEntity.headers(headers)` | Attaches the selected headers to the new response |
| `ResponseEntity.body(value)` | Sets the body matching the data type |
| `new ResponseEntity<>(body, headers, status)` | Explicitly constructs a response with all three parts |

**A mapper's goal is not always to change status**; most proxies should **preserve the original status** and adjust only headers/body per policy. When upstream validly returns 404, the client should get 404—not 200 with an error body. An upstream 503 does not magically become 200 just because the mapper completed normally.

### 4.1. ResponseEntity Is Not a Committed HTTP Response

Inside the controller, `ResponseEntity` is a **response description** that Spring MVC/WebFlux will serialize into HTTP status/headers/body. Once a request/response starts streaming onto the socket, status and headers may already be committed and cannot be revised. ProxyExchange's mapper normally runs **before the controller returns the response**, but returning `ResponseEntity` does not mean all bytes have reached the client yet.

### 4.2. A Mapper Can Transform Type T Into S

The `get(Function<ResponseEntity<T>, ResponseEntity<S>>)` overload lets you take an upstream response of type `T` and build a response of type `S`. For example, when upstream returns JSON text, the app can transform it into a DTO or a standardized error model if required by contract.

Do not deserialize `byte[]` into a JSON DTO just to add a header: deserializing and re-serializing can alter charset, field order, numeric precision, unknown fields, and `Content-Length`. If you only need to adjust headers, **keep the body as bytes**.

## 5. Distinguishing Upstream Headers From Client Headers

This is the most critical point of this lesson:

| Desired Action | Where to Apply | Who Receives the Result? |
| --- | --- | --- |
| Add `X-Gateway-Source` to Catalog call | `proxy.header("X-Gateway-Source", "catalog-edge")` | **Catalog backend** |
| Set multiple selective outbound headers | `proxy.headers(HttpHeaders)` | **Catalog backend** |
| Block forwarding `Cookie`/`Authorization` | ProxyExchange sensitive-header policy + separate authn/authz | Backend **does not receive** those credentials |
| Add `X-Proxy-Handled` when replying to client | Mapper creates new `ResponseEntity`, calls `headers.set(...)` | **Client** |
| Keep upstream `ETag` for client | Mapper copies valid header | **Client** |
| Replace upstream HTTP status with fallback status | Conditional mapper/error policy | **Client**, without altering the backend outcome that already occurred |

First example:

~~~java
return proxy
        .uri("http://127.0.0.1:9001/catalog/items/42")
        .header("X-Gateway-Source", "catalog-edge")
        .get();
~~~

According to `ProxyExchange`'s Javadoc API, `header(String, String...)` **sets a header for the downstream call** (meaning the **request to the backend**). Although some docs loosely phrase it as “headers to downstream response”, the reliable way to add a **response header sent to the client** is to use a `ResponseEntity` mapper and verify both sides with an HTTP test.

Second example:

~~~java
return proxy
        .uri("http://127.0.0.1:9001/catalog/items/42")
        .get(upstream -> ResponseEntity
                .status(upstream.getStatusCode())
                .headers(upstream.getHeaders())
                .header("X-Proxy-Handled", "catalog-edge")
                .body(upstream.getBody()));
~~~

The second sample shows mapper usage; it is **not safe for every backend yet** because it copies all upstream headers verbatim. Next, we write a version with a **response header allowlist** that avoids copying hop-by-hop or secret headers. `.header(...)` on the **`ResponseEntity` builder** sets a client-facing response header, **unlike** `.header(...)` on **`ProxyExchange`**.

## 6. Complete MVC Example: Adding Request Headers and Mapping ResponseEntity

Design a **read-only** API:

- Client calls `GET /api/catalog/items/{id}`.
- Controller accepts only `id` containing letters, digits, hyphens/underscores; never accepts client-supplied URIs or hosts.
- Backend URL comes from **trusted configuration**, never concatenated from the client's `Host` header.
- Outbound request adds `X-Gateway-Source: catalog-edge`.
- Client response preserves Catalog's status and body bytes within policy, forwarding only an **allowlist of response headers**.
- Response adds `X-Proxy-Handled: catalog-edge`.
- Never copy `Set-Cookie`, `Location`, or hop-by-hop headers arbitrarily; redirects require their own policy.

Java example for **Proxy Exchange MVC**, matching the `proxyexchange-webmvc` artifact model:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.gateway.mvc.ProxyExchange;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/catalog")
public final class CatalogProxyController {

    private final String backendBaseUrl;

    public CatalogProxyController(
            @Value("${catalog.backend-base-url}") String backendBaseUrl
    ) {
        // In production: validate scheme, host, and port at startup.
        this.backendBaseUrl = backendBaseUrl;
    }

    @GetMapping("/items/{id}")
    public ResponseEntity<byte[]> getItem(
            @PathVariable String id,
            ProxyExchange<byte[]> proxy
    ) throws Exception {
        if (!id.matches("[A-Za-z0-9_-]{1,40}")) {
            return ResponseEntity.badRequest().build();
        }

        String target = backendBaseUrl + "/catalog/items/" + id;

        return proxy.uri(target)
                .header("X-Gateway-Source", "catalog-edge")
                .header(HttpHeaders.ACCEPT_ENCODING, "identity")
                .get(this::mapCatalogResponse);
    }

    private ResponseEntity<byte[]> mapCatalogResponse(
            ResponseEntity<byte[]> upstream
    ) {
        // Do not forward internal redirects without a Location policy.
        if (upstream.getStatusCode().is3xxRedirection()) {
            return ResponseEntity.status(HttpStatus.BAD_GATEWAY).build();
        }

        // Simple lab policy: handle uncompressed responses only.
        String encoding = upstream.getHeaders()
                .getFirst(HttpHeaders.CONTENT_ENCODING);
        if (encoding != null && !encoding.equalsIgnoreCase("identity")) {
            return ResponseEntity.status(HttpStatus.BAD_GATEWAY).build();
        }

        HttpHeaders safe = new HttpHeaders();
        copyValues(upstream.getHeaders(), safe, HttpHeaders.CONTENT_TYPE);
        copyValues(upstream.getHeaders(), safe, HttpHeaders.CACHE_CONTROL);
        copyValues(upstream.getHeaders(), safe, HttpHeaders.ETAG);
        copyValues(upstream.getHeaders(), safe, HttpHeaders.LAST_MODIFIED);
        copyValues(upstream.getHeaders(), safe, HttpHeaders.VARY);

        // This header belongs to the client response, not the backend request.
        safe.set("X-Proxy-Handled", "catalog-edge");

        // Body is untouched; do not copy Content-Length from upstream.
        return new ResponseEntity<>(
                upstream.getBody(),
                safe,
                upstream.getStatusCode()
        );
    }

    private static void copyValues(
            HttpHeaders source,
            HttpHeaders target,
            String name
    ) {
        List<String> values = source.get(name);
        if (values != null && !values.isEmpty()) {
            target.put(name, new ArrayList<>(values));
        }
    }
}
~~~

Sample configuration for the **lab environment**, never using client-supplied URIs:

~~~yaml
server:
  port: 8080

catalog:
  backend-base-url: http://127.0.0.1:9001
~~~

### 6.1. Why Does the Code Above Use a Response Header Allowlist?

Suppose Catalog returns:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "item-42-v3"
Cache-Control: public, max-age=60
Connection: keep-alive
Set-Cookie: INTERNAL_SESSION=abc; HttpOnly
X-Internal-Cluster: blue

{"id":"42","name":"Keyboard"}
~~~

The illustrated mapper keeps only `Content-Type`, `ETag`, `Cache-Control`, and the other allowlisted headers; it **does not send** `Connection`, `Set-Cookie`, or `X-Internal-Cluster` to the client. The client also receives:

~~~http
X-Proxy-Handled: catalog-edge
~~~

**Must verify in practice:** Message converters/HTTP clients may handle headers, bodies, or decompression in their own way; in some setups, response `Content-Length` may be recalculated by the framework. Do not treat this ASCII JSON example as proof that every binary or streaming response will pass through byte-for-byte.

### 6.2. Final Status Still Matches Upstream Status

With the mapper above:

| Upstream | Client Response | Explanation |
| --- | --- | --- |
| 200 + JSON | 200 + JSON | Success result preserved |
| 404 + JSON error | 404 + JSON error | Missing-resource error not turned into 200 |
| 503 + JSON error | 503 + JSON error | Outage not masked |
| 204 No Content | 204, no body | No-body semantics preserved |
| 304 Not Modified | 304, no body | ETag/Last-Modified/Vary allowed if backend is valid |
| 302 + internal `Location` | 502 in the **illustrative policy** | Do not leak internal redirects without rewrite/allowlist rules |

The table assumes backend 4xx/5xx responses are turned into `ResponseEntity` by ProxyExchange/the client in your version. Some HTTP clients/converters may **throw exceptions for certain responses or transport failures**; test specifically rather than treating the table as an absolute guarantee.

### 6.3. Why Not Use `headers(upstream.getHeaders())`?

Many headers can be sensitive data or meaningful only for the backend → Gateway hop:

- `Set-Cookie` may set cookies with the wrong domain/path or push backend sessions to the browser.
- `Location` may point to internal hosts, untrusted hosts, or unexpected redirects.
- `Connection`, `Transfer-Encoding`, and `Keep-Alive` are hop-by-hop.
- `Content-Length` may be wrong if the body was decoded/re-encoded or sent over a different transport.
- `Server`, `Via`, and `X-Internal-*` may leak topology/metadata.
- Security headers like `Access-Control-Allow-Origin`, `Strict-Transport-Security`, or CSP must have **one policy owner** at the right HTTP boundary.

The allowlist in the example **fits only the Catalog read API**. For file downloads, video, range requests, intentional redirects, or browser sessions, design a different header list and test thoroughly instead of copying that allowlist verbatim.

## 7. Using HttpHeaders Correctly: add, set, put, and Multi-Value Headers

An HTTP response can contain multiple values for the same header, such as `Vary`, `Cache-Control`, or especially `Set-Cookie`. Spring's `HttpHeaders` supports a structure similar to `MultiValueMap<String, String>`.

| Operation | Result | When to Use |
| --- | --- | --- |
| `headers.add("Vary", "Accept-Language")` | **Appends** a value, keeping existing values | When adding to a value set with full semantic understanding |
| `headers.set("X-Proxy-Handled", "catalog-edge")` | **Replaces** the value list with a single value | Gateway-owned single-value headers |
| `headers.put(name, List.of(...))` | Sets the entire value list for the header | Intentionally copying a multi-value header |
| `headers.get(name)` | Returns `List<String>` or null | When all values must be preserved |
| `headers.getFirst(name)` | Returns the first value | Appropriate only when the contract allows one value |
| `headers.remove(name)` | Deletes a header | Redacting or stripping transport headers |

Example adding a response header without changing status or body:

~~~java
private static ResponseEntity<byte[]> withMarker(
        ResponseEntity<byte[]> upstream
) {
    HttpHeaders copy = new HttpHeaders();
    upstream.getHeaders().forEach((name, values) ->
            copy.put(name, new ArrayList<>(values)));

    copy.set("X-Proxy-Handled", "catalog-edge");
    return new ResponseEntity<>(
            upstream.getBody(),
            copy,
            upstream.getStatusCode()
    );
}
~~~

This snippet illustrates **copying instead of mutating the upstream object**, yet it is **not a security policy** because it copies *all* response headers. In production, combine copying with an allowlist and hop-by-hop cleanup as in Section 6. Value lists are newly allocated to avoid accidentally sharing mutable lists with the original response.

### 7.1. Do Not Overwrite Multi-Value Headers by Mistake

Example:

~~~java
HttpHeaders headers = new HttpHeaders();
headers.add(HttpHeaders.VARY, "Accept-Encoding");
headers.add(HttpHeaders.VARY, "Accept-Language");

// This operation replaces and loses the two previous values:
headers.set(HttpHeaders.VARY, "Origin");
~~~

If the goal is to preserve upstream `Vary` and add another dimension for downstream caches, merge values carefully and avoid duplicates or non-standard behavior. For `Set-Cookie`, **never** join multiple cookies with commas like an ordinary header list; respect cookie-specific semantics and `Domain`, `Path`, `Secure`, `HttpOnly`, and `SameSite` attributes.

### 7.2. Header Case-Insensitivity

Per HTTP rules, header names are **case-insensitive**: `X-Request-Id` and `x-request-id` are semantically identical. Spring's `HttpHeaders` provides the proper case-insensitive API. Never write a custom `HashMap<String, String>` with case-sensitive matching to filter credentials or hop-by-hop headers.

### 7.3. Never Put Newlines or Control Characters Into Headers

Header values coming from clients or backends may contain untrusted data. If you take a raw query string and set it as a response header, validate its length and strip control characters. Prevent HTTP response splitting / CRLF injection, and never let users freely choose header names or `Location` values.

## 8. Outbound Headers: When to Use header(...) and headers(...)?

A client request may arrive as:

~~~http
GET /api/catalog/items/42 HTTP/1.1
Host: api.example.test
Accept: application/json
X-Gateway-Source: attacker
Authorization: Bearer <client-token>
Cookie: SESSION=<session-id>
~~~

The Gateway wants to send to Catalog:

~~~http
GET /catalog/items/42 HTTP/1.1
Host: catalog.internal.example
Accept: application/json
X-Gateway-Source: catalog-edge
~~~

To set a single internal header with an **application-controlled** value:

~~~java
proxy.uri(targetUri)
        .header("X-Gateway-Source", "catalog-edge")
        .get();
~~~

To send multiple intentional outbound headers:

~~~java
HttpHeaders additional = new HttpHeaders();
additional.set("X-Gateway-Source", "catalog-edge");
additional.set("X-Request-Class", "public-read");

return proxy.uri(targetUri)
        .headers(additional)
        .get();
~~~

Per `ProxyExchange`'s Javadoc, `header(...)` and `headers(...)` set **headers for the downstream request**; `headers(...)` may add to or override inbound headers depending on the implementation. **Do not confuse them with `ResponseEntity.headers(...)`**, which sets headers on the client response.

### 8.1. Why Not Copy Authorization From the Client?

ProxyExchange lines have a **default sensitive headers** list, commonly `Cookie` and `Authorization` — they are not forwarded automatically to the backend. This is a **useful guardrail** when proxying to services that do not need user sessions, though it does not replace a security review:

1. The backend may require a token issued specifically **for that backend** with the right audience and scopes.
2. Conditional token exchange / `TokenRelay` may be needed, but never drop default sensitive-header blocking just to “stop the backend returning 401”.
3. If modifying `proxy.sensitive(...)`, verify whether the API **replaces** or appends to the list in your version, and keep `authorization`/`cookie` blocked where needed.
4. Never send refresh tokens or ID tokens to resource servers; never send client tokens to vendor domains outside the intended audience.
5. Backends must authenticate and authorize independently: an unsigned `X-Gateway-Source` header without verified identity is not an authorization mechanism.

### 8.2. “Skipped” Headers Differ From “Sensitive” Headers

Recent Proxy Exchange documentation distinguishes:

| Group | Common Examples | Why |
| --- | --- | --- |
| **Sensitive inbound headers** | `Authorization`, `Cookie` | Prevent credential leakage in outbound requests |
| **Skipped request headers** | `Host`, `Content-Length` | The backend hop has a different host/transport/body encoding |
| **Proxy-related headers** | `X-Forwarded-*`, `Forwarded` | Requires identifying the trusted proxy chain |
| **Request application headers** | `Accept`, `X-Gateway-Source` | Forward only when needed by the backend and allowed by contract |

**Exact defaults can change across releases and auto-configurations.** Manually copying client-sent `Content-Length` to the backend can break body framing if the HTTP client changes the body or transfer encoding. Likewise, never force the public Gateway's `Host` onto connections to internal backends.

### 8.3. Forwarded Headers Are Not Proof of Identity

If ProxyExchange runs behind a trusted ingress, it may need forwarding metadata so the backend knows the public scheme/host. However, browser-supplied headers such as `X-Forwarded-Host: attacker.example` **must never be trusted automatically**. Configure trusted proxies/edge normalization per version and forbid using `X-Forwarded-Host` directly as a backend target.

## 9. Mapping ResponseEntity With a Function: Right Order, Right Type

ProxyExchange's HTTP method overloads accept a mapper:

~~~java
// Conceptual signature of MVC ProxyExchange:
<S> ResponseEntity<S> get(
        Function<ResponseEntity<T>, ResponseEntity<S>> mapper);
~~~

With WebFlux ProxyExchange, the result is wrapped in a `Mono`:

~~~java
// WebFlux model: publisher returns the mapped ResponseEntity.
Mono<ResponseEntity<S>> response = proxy.get(mapper);
~~~

The mapper receives the response **already produced by the HTTP call**; it is not a pre-request filter, is not responsible for authorization, and must not fire extra outbound calls without understanding side effects.

### 9.1. Three Options When Mapping

| Option | Action | When Appropriate |
| --- | --- | --- |
| **Selective pass-through** | Preserve status/body, forward only allowed headers | Catalog GETs, metadata, small binaries |
| **Response enrichment** | Preserve status/body, add Gateway-owned headers | `X-Proxy-Handled`, internal cache metadata |
| **Response transformation** | Intentionally parse/modify body/status | API adapters with a dedicated contract and stable schema |

Example mapper preserving the result:

~~~java
return proxy.uri(target)
        .get(response -> new ResponseEntity<>(
                response.getBody(),
                approvedResponseHeaders(response.getHeaders()),
                response.getStatusCode()
        ));
~~~

Here `approvedResponseHeaders` is an **application-defined** function. There is no “magically safe” `ResponseEntity` mapper; your own logic must specify which headers to forward.

### 9.2. Mapper Changing Type T → S

Suppose upstream returns a `LegacyProduct` DTO, while the client expects `CatalogProduct`. Pattern:

~~~java
// Sketch example: LegacyProduct/CatalogProduct are application-defined.
return proxy.uri(target)
        .get(upstream -> {
            if (!upstream.getStatusCode().is2xxSuccessful()) {
                // Error body of LegacyProduct cannot be assumed to be a valid DTO.
                return mapErrorResponse(upstream);
            }

            CatalogProduct mapped = adapt(upstream.getBody());
            return ResponseEntity.status(upstream.getStatusCode())
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(mapped);
        });
~~~

This is **pattern pseudocode**, not a self-compiling file: `LegacyProduct`, `CatalogProduct`, `adapt`, and `mapErrorResponse` must be implemented by the application. When changing the body, control status, null bodies, JSON converters, charsets, caching validators (`ETag`), and `Content-Length`. For personal resources or transactions, never turn auth errors or upstream 503s into fake successes.

### 9.3. Do Not Turn Every Status Into 200

~~~java
// ANTI-PATTERN: backend 404/500/503 also turns into 200.
return proxy.uri(target)
        .get(upstream -> ResponseEntity.ok(upstream.getBody()));
~~~

If the backend returns `{"error":"NOT_FOUND"}` with HTTP 404, the client receives HTTP 200 in this anti-pattern, corrupting caching, retry policies, monitoring, SLOs, and frontend logic.

### 9.4. Do Not Treat the Final Status as Proof the Proxy Succeeded

A synthetic fallback HTTP 200 does not prove the backend returned a valid result, and an HTTP 503 returned by the proxy could be a **backend 503** or a **gateway transport error**. Log and metric `upstreamStatus`, `finalStatus`, `outcome`, and timing separately, without logging raw tokens or bodies.

## 10. Content-Type, Content-Length, and Content-Encoding When Mapping Bodies

When the mapper **does not alter body bytes**, keeping the backend's `Content-Type` is usually sensible if the backend is trusted and follows a standard contract. However, certain headers belong to **transport framing** or are tied to the exact body bytes and cannot be copied carelessly.

| Header | When Body Bytes Are Unchanged | When Body Is Transformed |
| --- | --- | --- |
| `Content-Type` | Keep if contract/charset matches | Update to media type + charset of new body |
| `Content-Length` | Let framework compute; do not copy old length blindly if unsure | Drop old value; compute or let framework recompute |
| `Content-Encoding` | Keep **only if** actual bytes still use that encoding | Remove/update if decompressed or recompressed |
| `ETag` | Keep if representation is preserved intact | Must recompute or drop old validator |
| `Last-Modified` | Keep only if representation semantics are unchanged | Re-evaluate |
| `Vary` | Keep dimensions affecting representation | Add new dimensions if response varies by request |
| `Content-Range` | Keep only if forwarding exact byte range | Do not send unchanged if body changed |
| `Cache-Control` | Follow origin policy and API contract | Must match sensitivity/freshness of new body |

### 10.1. Changing the Body While Keeping the Old ETag Is a Logic Bug

~~~text
Backend:
  ETag: "product-42-v5"
  Body: {"sku":"42","price":1000}

Gateway adapter:
  Body: {"id":"42","priceText":"1.000 VND"}
  ETag: "product-42-v5"     <-- must be revisited
~~~

If the upstream ETag validates the old representation, reusing it for a transformed representation can cause caches and conditional GETs to return out-of-contract results. In some cases you can derive a new validator from the data version and a deterministic transformation; otherwise, dropping `ETag` is safer.

### 10.2. Charset and Unicode

Suppose a JSON body contains Vietnamese text. Converting `byte[]` to `String` and re-encoding with the JVM default charset can corrupt UTF-8 or `Content-Length`. Use message converters and charsets per contract. **Byte length does not equal Java character count**; never set `Content-Length` to `string.length()`.

### 10.3. Empty Bodies

HTTP 204, 304, or HEAD must not be forced into returning `{}` JSON. `ResponseEntity` can have a null body; if a mapper injects a body on disallowed status codes, the container may drop it or clients/parsers may fail. Follow standard HTTP response semantics and test with an HTTP client.

### 10.4. When the Response Is Compressed

In the Catalog example, the controller sets `Accept-Encoding: identity` on the outbound request and **rejects responses carrying a `Content-Encoding` other than `identity`** so the allowlist policy never accidentally sends compressed bytes without the header describing the encoding.

Real systems can support gzip/br and streaming, but you must verify **which bytes the backend returns**, whether the HTTP client decompresses automatically, and whether the response mapper preserves or updates `Content-Encoding`, `Vary: Accept-Encoding`, and `Content-Length` consistently. **Never strip `Content-Encoding` blindly while the body remains compressed.**

## 11. Redirects and Location: Do Not Leak Internal Hosts

A backend returns:

~~~http
HTTP/1.1 302 Found
Location: http://catalog.internal.example/admin/export
~~~

If the mapper copies `Location` verbatim to the public response, browsers may be directed to an internal hostname/path or an untrusted host. This can leak topology, create an **open redirect**, or break authentication flows.

### Three Policy Options

| Policy | Scenario | What to Verify |
| --- | --- | --- |
| **Block redirects** | JSON API proxy where redirects are disallowed | Return a controlled error; never expose internal `Location` |
| **Allowlist-based Location rewrite** | Backend redirects internally to a valid public path | Compare scheme/host/port/path, strip userinfo, normalize URI properly |
| **Allow redirects to approved hosts** | OAuth login or CDN redirects by design | Accept only known hosts/destinations; control tokens/cookies |

The Catalog controller in Section 6 intentionally **blocks 3xx and returns 502** because the Catalog GET contract is direct JSON. This is not a universal policy: OAuth callbacks, download links, or APIs with intentional redirects need dedicated handling.

### Avoid Building Location With Unchecked Strings

Do not write:

~~~java
// ANTI-PATTERN: host comes from client, enabling arbitrary redirects.
String redirect = request.getHeader("X-Forwarded-Host") + "/login";
return ResponseEntity.status(302)
        .header(HttpHeaders.LOCATION, redirect)
        .build();
~~~

`X-Forwarded-Host` is trustworthy only when ingress/edge controls the proxy chain. Use a configured public base URL or origin allowlist instead of trusting arbitrary headers sent by Internet clients. For post-authentication redirects, protect `state`, `nonce`, and callback URIs per your application's OIDC/OAuth standards.

### The HTTP Client Might Auto-Follow Redirects

Not every HTTP client hands a 302 back to the mapper; some follow redirects **before** returning `ResponseEntity`. Blocking 3xx in the mapper alone is **not enough** to guarantee the HTTP client never connected to a third-party host. Configure **redirect policies and egress allowlists on the HTTP client**, verify actual version behavior, and monitor destination connections.

## 12. Set-Cookie, Sessions, and Sensitive Response Headers

When proxying to a service, `Set-Cookie` must not be copied unconditionally:

~~~http
Set-Cookie: INTERNAL_SESSION=abc; Path=/; HttpOnly; SameSite=Lax
~~~

If the backend sets a cookie for its own domain/path and the Gateway forwards it to the client unchanged, the browser may store the cookie under an unintended context. Worse, if the Gateway returns a cookie holding backend session info or turns a bearer token into an unprotected cookie, it widens credential exposure.

### Selective Rules

1. **Public Catalog:** normally **do not forward `Set-Cookie`** from the backend if the API does not use sessions.
2. **Authentication endpoints:** if the response needs cookies, specify which cookies are allowed, their domain/path, `Secure`, `HttpOnly`, `SameSite`, and TTL/rotation; do not merely rename headers.
3. **Multiple `Set-Cookie` headers:** keep them as separate header fields; never join them with commas or call `getFirst` and drop other cookies.
4. **Proxy Exchange sensitive request headers** (`Cookie`, `Authorization` blocked by default) are **separate** from response `Set-Cookie` forwarding policy.
5. **Cache-Control:** personal or token-bearing responses typically require `private, no-store` per contract; never use public caching for session data.

An allowlist permitting only `Content-Type` and `Cache-Control` fits a simple catalog API, but **not** a login endpoint that legitimately sets cookies. Design each endpoint group according to permissions and data sensitivity.

### HSTS, CORS, and Response Security Headers

`Strict-Transport-Security` belongs to the **public HTTPS origin**, never copied automatically from an internal HTTP backend. Similarly, `Access-Control-Allow-Origin` must not be copied blindly from the backend when the Gateway is the public origin; configure CORS explicitly by allowed origins and credentials policy. `Content-Security-Policy`, `X-Content-Type-Options`, and `Referrer-Policy` must each have an explicitly defined infrastructure or application owner.

**Never emit conflicting duplicate headers** across controller, Spring Security, Servlet filters, and ingress; test the final response at the client after all layers.

## 13. Hop-by-Hop Headers: Why Not Forward Everything?

An HTTP proxy creates **two hops**. Certain headers control **only the current hop's connection** and must never cross to the other hop as entity metadata.

### List Commonly Requiring Control

| Header | Meaning / Risk |
| --- | --- |
| `Connection` | Lists hop-by-hop options and controls the current connection |
| `Keep-Alive` | Per-hop keep-alive parameters; not an end-to-end chain policy |
| `Transfer-Encoding` | How bytes are framed on the current connection |
| `TE` | Transfer-coding/trailer semantics |
| `Trailer` | Message framing trailer metadata |
| `Upgrade` | Protocol upgrades such as WebSockets; requires dedicated handling |
| `Proxy-Authenticate` / `Proxy-Authorization` | Per-hop proxy authentication, not application access tokens |

Under HTTP rules, **in addition to those fixed names**, the `Connection` header can list **custom headers that must also be stripped** when forwarding. For example:

~~~http
Connection: keep-alive, X-Debug-Transport
X-Debug-Transport: socket-123
~~~

The proxy must recognize that `X-Debug-Transport` here applies only to the current connection; **blocking only a fixed list of names is insufficient** if you copy headers in bulk. With a tight allowlist as in Section 6, you never copy unknown headers in the first place, reducing risk.

### A General Sanitizer Must Inspect Connection Tokens

~~~java
// Pseudocode for a general response sanitizer:
Set<String> hopByHop = new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
hopByHop.addAll(Set.of(
        "Connection", "Keep-Alive", "Transfer-Encoding",
        "TE", "Trailer", "Upgrade",
        "Proxy-Authenticate", "Proxy-Authorization"));

List<String> connectionValues =
        upstream.getHeaders().get(HttpHeaders.CONNECTION);
if (connectionValues != null) {
    for (String connectionValue : connectionValues) {
        for (String token : connectionValue.split(",")) {
            hopByHop.add(token.trim());
        }
    }
}

// Copy only if !hopByHop.contains(name)
// Still must check secrets, caching, Location, and Content-Length.
~~~

This snippet is a **sketch**, assuming `Set`, `List`, and `TreeSet` imports. It shows how to parse the `Connection` header, not a complete production sanitizer: you also need to handle invalid values, bound header/token counts, HTTP/2 rules (which forbid many hop-by-hop fields), trailers, compression, and special responses.

### HTTP/2 and Streaming

HTTP/2 prohibits several connection-specific fields common in HTTP/1.1. When a proxy translates protocols across client, Gateway, and upstream, copying `Connection`/`Transfer-Encoding` verbatim can cause rejected messages or framing errors. Let the HTTP server and HTTP client manage transport, forwarding only contract-approved end-to-end headers.

## 14. Status 4xx/5xx, Transport Errors, and Fallbacks Must Be Separated

A backend can **return a valid HTTP response with status 503**, or the connection can **fail before any response arrives**. These are two distinct classes of situations:

~~~mermaid
flowchart TD
    Call["ProxyExchange.get(mapper)"] --> D{"Did HTTP call get a response?"}
    D -->|Yes| R["ResponseEntity: status/headers/body"]
    R --> M["Mapper: preserve or transform intentionally"]
    D -->|No| E["Transport exception: DNS/TCP/TLS/timeout..."]
    E --> P["Exception handler / fault policy"]
    P --> F["502/503/504 per contract"]
    M --> C["Response sent to client"]
    F --> C
~~~

| Case | Typical Handling | What Not to Do |
| --- | --- | --- |
| Backend returns 404 (item missing) | Preserve 404 and safe error body | Turn into 200 by default |
| Backend returns 400 (client input) | Preserve 400 if genuinely client-caused | Retry endlessly and blame a backend outage |
| Backend returns 401/403 | Enforce authentication/authorization boundary | Turn into 200 or leak internal `WWW-Authenticate` needlessly |
| Backend returns 429 | Typically preserve 429, control `Retry-After` | Retry immediately ignoring quota |
| Backend returns 500/503 | Usually preserve status with safe body/headers; policy-based fallback | Swallow error and return bogus data |
| TCP connect refused | Error handler returns 502/503 per contract | Leak exception message containing host/token to client |
| Response timeout | May return 504 if contract fits | Assume backend has not executed side effects |
| TLS certificate/hostname failure | Fail closed, alert, and fix trust | Disable certificate verification to “retry” |

### 14.1. A Narrow I/O Error Handler for ProxyExchange MVC

In Proxy Exchange MVC lines using Spring's REST client, I/O failures may be wrapped in `ResourceAccessException`. Illustrative handler:

~~~java
import java.util.Map;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.client.ResourceAccessException;

@RestControllerAdvice(assignableTypes = CatalogProxyController.class)
class CatalogProxyErrorAdvice {

    @ExceptionHandler(ResourceAccessException.class)
    ResponseEntity<Map<String, String>> upstreamIoUnavailable() {
        return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                .cacheControl(CacheControl.noStore())
                .body(Map.of(
                        "code", "CATALOG_UPSTREAM_IO_FAILURE",
                        "message", "Catalog service is temporarily unavailable"
                ));
    }
}
~~~

This example avoids exposing raw exception messages or backend addresses to clients. It **does not attempt to catch every `RuntimeException`**, does not guarantee catching every exception across all HTTP clients/versions, and does not replace Spring Security 401/403 handling.

### 14.2. Errors After Response Commit

For short `byte[]` bodies, the mapper typically runs before MVC writes the body to the client. However, with streaming or partially written responses, if the backend breaks mid-stream you **cannot replace HTTP 200 with a 503 JSON error on the same connection**. You must abort/close the stream per protocol and let clients retry or resume as appropriate.

### 14.3. Retries and Circuit Breakers Are Not Built Into ProxyExchange

Proxy Exchange is a utility for **controller-based HTTP calls**. A ProxyExchange route does not automatically inherit Gateway Server's `Retry GatewayFilter` or `CircuitBreaker GatewayFilter`. If your app adds retries in the HTTP client or service layer, cap attempts, set deadlines, enforce idempotency, and watch for load amplification. Never auto-retry order/payment POSTs when the backend may have committed while the response was lost.

## 15. Caching Headers, ETag, Vary, and Conditional GET

Catalog APIs frequently use caching to reduce upstream load. However, because the Gateway acts as a proxy/adapter, it must know **which representation is being cached**.

### 15.1. Conditional Request Example

First client call:

~~~http
GET /api/catalog/items/42 HTTP/1.1
Accept: application/json
~~~

Backend returns:

~~~http
HTTP/1.1 200 OK
ETag: "item-42-v3"
Cache-Control: public, max-age=60
Content-Type: application/json

{"id":"42","name":"Keyboard"}
~~~

Next client call:

~~~http
GET /api/catalog/items/42 HTTP/1.1
If-None-Match: "item-42-v3"
~~~

If `If-None-Match` is forwarded properly and the backend confirms the representation is unchanged, the backend can return `304 Not Modified` with no body. The mapper must preserve status 304 and valid validators, not convert it to 200 with empty JSON.

**Do not assume ProxyExchange always forwards every conditional header.** Verify default blocked headers, request adapters, and backend counters. Furthermore, if the mapper alters the JSON, the upstream `ETag` may no longer accurately represent what the client receives.

### 15.2. Vary Is Part of the Cache Key

Suppose the backend varies responses by `Accept-Language` or `Accept-Encoding`:

~~~http
Vary: Accept-Language, Accept-Encoding
~~~

If the Gateway drops `Vary` while keeping `Cache-Control: public`, a shared cache could serve the wrong language or encoding to another client. Conversely, setting `Vary: Authorization` on sensitive data does not guarantee safety; many personal APIs still require `Cache-Control: private, no-store` per contract.

### 15.3. 304/204/HEAD and Null Bodies

| Method/Status | Rule |
| --- | --- |
| GET 200 | Body matching `Content-Type` and `Content-Encoding` |
| GET 304 | Emit no message body; preserve valid validators and cache headers |
| 204 No Content | Do not attach an arbitrary body; response has no representation payload |
| HEAD | Return metadata matching GET per contract, **without a response body** |
| GET 206 Partial Content | Keep byte range, `Content-Range`, and `Content-Length` matching the actual body slice |

The `CatalogProxyController` example in Section 6 declares only GET, not a full file proxy supporting Range/HEAD. When extending, test those methods and conditional headers directly instead of extrapolating from plain GET success.

## 16. Choosing Between Returning an Error and Preserving the Upstream Response

A proxy has two error categories:

1. **Upstream returned an HTTP response:** e.g., 404/429/503 with headers and error body.
2. **Proxy received no HTTP response:** e.g., DNS failure, TCP refused, TLS trust failure, socket reset, or deadline exceeded.

### 16.1. Preserve Status or Map to Another Code?

| Error Source | Sample Policy | Notes |
| --- | --- | --- |
| Client sends malformed ID | Controller returns 400 without calling upstream | Error body does not echo raw input needlessly |
| Backend reports item missing | Preserve 404 | Do not cache errors indefinitely unless contract allows |
| Backend rate-limited | Preserve 429 or defined policy | `Retry-After` needs explicit handling if forwarded |
| Backend unavailable returning 503 | Preserve 503 in example | Error body/headers must be filtered |
| TCP connection refused | Controller advice returns 502 in example | Distinct from an explicit backend 503 |
| TLS certificate invalid | Connection fails, operations alerted | Never disable certificate verification |
| Response missed deadline | May return 504 per contract | Never assume the backend had no side effects |

If `get(mapper)` throws an exception on 4xx/5xx in a specific client implementation, configure the HTTP client's error handling or handle it at the exception layer. Never write `catch(Exception ex)` and return 200 `"OK"`.

### 16.2. Should Retry-After Be Forwarded?

The backend may return `Retry-After: 10` on HTTP 429/503. The allowlist in Section 6 **does not forward this header**; that is a minimal lab policy. If your API expects guided client retries, add `Retry-After` to the allowlist **after validating its value and understanding its source**, factoring in deadlines, rate limiting, and overall retry budgets.

Never fabricate `Retry-After: 30` just because a circuit breaker waits 30 seconds before probing; that is no guarantee the backend will recover in 30 seconds.

### 16.3. Fallbacks Must Not Fabricate Success

Suppose a user places an order:

~~~text
POST order -> backend commits -> response connection reset
ProxyExchange receives no response
~~~

The system **cannot conclude** the order was not created. If the Gateway auto-retries POST and the backend lacks an idempotency key/deduplication, the order could be created twice. If the Gateway substitutes a default 201, the client gets a misleading view of the transaction. You need operation IDs, idempotency contracts, and reliable status lookups—not a mapper guessing from HTTP status.

## 17. Security: Header Propagation Is Not Authorization

Proxy Exchange typically lives inside an MVC/WebFlux controller containing business logic. Every header added or removed can affect the **trust boundary**:

~~~mermaid
flowchart TD
    C["Internet client"] --> S["Spring Security: authenticate/authorize"]
    S --> CTR["ProxyExchange controller"]
    CTR --> P["Outbound header policy"]
    P --> D["Approved upstream destination"]
    D --> B["Backend validates audience / permissions"]
    B --> R["ResponseEntity mapper: allowlist"]
    R --> C
~~~

### 17.1. Never Forward Tokens Where They Are Not Needed

ProxyExchange's default sensitive headers typically block `Authorization` and `Cookie` from inbound requests. For a business service to receive a token:

- Know the **service audience** and permitted scopes.
- Send only a resource-server access token or an intentional exchanged token—never ID tokens or refresh tokens.
- Connect to upstreams over TLS with hostname/certificate verification, and mTLS when appropriate.
- The backend must independently verify signature, audience, resource ownership, and tenant.
- Never let clients supply `targetUrl` or `serviceId` as the destination.

**Never replace `proxy.sensitive()` defaults with an empty list just to bypass a 401.** Doing so can leak user sessions to unintended backends or vendors.

### 17.2. Gateway-Added Headers Are Not Secrets by Themselves

`X-Gateway-Source: catalog-edge` is useful for diagnostics, but another HTTP client can forge that header when calling the backend directly if the backend is reachable. If the backend trusts only Gateway requests, enforce **network segmentation, service identity, TLS/mTLS, or cryptographic credentials**, not just matching a static header string.

### 17.3. CORS and Authorization

CORS is a browser policy; it **does not grant API authorization**. If a ProxyExchange controller serves a public frontend on another origin, configure CORS properly in Spring MVC/WebFlux/Security and test OPTIONS preflights. Never reflect every `Origin` with `Access-Control-Allow-Credentials: true` unconditionally.

MVC Spring Security uses `SecurityFilterChain`/Servlet `HttpSecurity`; WebFlux uses `SecurityWebFilterChain`/`ServerHttpSecurity`. **Do not mix up security chains just because both variants support ProxyExchange.**

### 17.4. Client-Provided Headers Can Cause SSRF or Open Redirects

Untrusted inputs include `Host`, `X-Forwarded-Host`, `Forwarded`, `?url=` queries, redirect targets, and upstream hint headers. Using them to construct `proxy.uri(...)` lets callers aim the HTTP client at metadata services, localhost/admin endpoints, or external systems while carrying credentials or tracing headers along.

**Safer design:** backend URIs come from trusted configuration, path parameters are validated/encoded, the HTTP client restricts scheme/host/port, and egress policies block unapproved private destinations. Redirect following must obey the same policy.

## 18. ProxyExchange and Heavy Loads: Do Not Assume byte[] Is Streaming

`ProxyExchange<byte[]>` is convenient for holding payload bytes without knowing JSON schemas, but it may materialize large responses in memory before building `ResponseEntity`.

Suppose 200 concurrent requests each receive a 4 MiB backend body:

\[
200 \times 4\ \text{MiB} = 800\ \text{MiB}
\]

This figure covers **only one copy of the body per request in theory**, before adding object overhead, TLS buffers, outbound client buffers, and copies made in mappers/converters. Under real load, memory may be higher or lower depending on streaming/buffering implementations.

### 18.1. Workloads Requiring Specialized Solutions

| Workload | Risk With `ResponseEntity<byte[]>` Mapper |
| --- | --- |
| 1 KB JSON | Usually fits well; easy to preserve status/headers |
| 20 MB JSON/image | Body buffering and GC/memory spikes |
| 2 GB download | Should not be buffered into `byte[]` |
| SSE/NDJSON | Long-lived stream, data must flush incrementally; mapper may be unsuitable |
| Multipart upload | Body replay/copying can break boundaries and spike memory |
| Video/range requests | Needs exact `Content-Range`, `Accept-Ranges`, 206, cache validators |
| WebSocket upgrade | Not a short HTTP GET/`ResponseEntity`; requires dedicated upgrade support |

Depending on your stack, use streaming tools, Servlet async, WebFlux `DataBuffer`s, or **Gateway Server** when proxying heavy/varied traffic with infrastructure policies. Never collect a stream into an unbounded `List<byte[]>` or `ByteArrayOutputStream` just to “make editing a response header easy”.

### 18.2. Resource Limits and Timeouts

Proxy Exchange MVC may use blocking HTTP clients or version-specific client abstractions, requiring connection pooling, connect timeouts, response/read timeouts, and concurrent request caps. WebFlux requires watching subscriber cancellation and `DataBuffer` lifetimes. **Completion time of `get()` does not cover the entire user-operation deadline** when network/serialization/streaming occurs in other layers.

### 18.3. Committed Responses Cannot Be Rebuilt

Once the client has received HTTP 200 and several kilobytes of body, you cannot emit a new HTTP 503 response inside **the same message**. If upstream disconnects mid-stream, abort/close the transport per protocol, record telemetry, and let the client retry/resume at the application layer if needed; never append a JSON error into the middle of a file or SSE frame.

## 19. Stub Backend: Observing Real Headers and Generating Multiple Responses

A reliable testing technique is running a stub backend **separate from the Proxy Exchange app**, used solely in the lab. It should return headers the mapper is expected to **keep** as well as headers the mapper is expected to **strip**.

Stub application on port `9001`:

~~~java
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CatalogStubController {

    private final AtomicInteger requests = new AtomicInteger();

    @GetMapping("/catalog/items/{id}")
    public ResponseEntity<byte[]> getItem(
            @PathVariable String id,
            @RequestHeader(
                    name = "X-Gateway-Source", required = false
            ) String gatewaySource,
            @RequestHeader(
                    name = HttpHeaders.AUTHORIZATION, required = false
            ) String authorization,
            @RequestHeader(
                    name = HttpHeaders.COOKIE, required = false
            ) String cookie
    ) {
        requests.incrementAndGet();

        if ("missing".equals(id)) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(bytes("{\"error\":\"NOT_FOUND\"}"));
        }
        if ("busy".equals(id)) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(bytes("{\"error\":\"UPSTREAM_BUSY\"}"));
        }
        if ("empty".equals(id)) {
            return ResponseEntity.noContent().build();
        }
        if ("redirect".equals(id)) {
            return ResponseEntity.status(HttpStatus.FOUND)
                    .location(URI.create(
                            "http://catalog.internal.example/admin"))
                    .build();
        }

        String body = "{\"id\":\"" + id + "\""
                + ",\"seenGatewaySource\":\"" + gatewaySource + "\""
                + ",\"sawAuthorization\":" + (authorization != null)
                + ",\"sawCookie\":" + (cookie != null)
                + "}";

        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .eTag("\"catalog-item-v1\"")
                .header(HttpHeaders.CACHE_CONTROL, "public, max-age=60")
                .header(HttpHeaders.SET_COOKIE,
                        "INTERNAL_SESSION=fake; HttpOnly")
                .header("X-Internal-Node", "node-blue")
                .body(bytes(body));
    }

    private static byte[] bytes(String text) {
        return text.getBytes(StandardCharsets.UTF_8);
    }

    int callCount() {
        return requests.get();
    }
}
~~~

**This is a test backend, not production code.** It deliberately returns a fake internal cookie and topology header to verify that the gateway filters them out; use test data only, **never echo real tokens/secrets**. `callCount()` is an accessor for an in-process test harness and must never be exposed as a public endpoint. If tests run the Gateway and stub in two processes, read counters through an authorized test interface or use an HTTP stub tool with a request journal.

### Responses From the Stub

| Backend URL | Status | Notable Content |
| --- | ---: | --- |
| `/catalog/items/42` | 200 | JSON, ETag, Cache-Control, Set-Cookie, X-Internal-Node |
| `/catalog/items/missing` | 404 | Valid error JSON |
| `/catalog/items/busy` | 503 | Backend-busy JSON |
| `/catalog/items/empty` | 204 | No body |
| `/catalog/items/redirect` | 302 | Location pointing to fake internal host |

### How Are Request/Header Policies Verified?

The controller in Section 6 sets `X-Gateway-Source: catalog-edge` and filters `Authorization`/`Cookie` per the active ProxyExchange defaults. When the client tries sending:

~~~http
GET /api/catalog/items/42 HTTP/1.1
X-Gateway-Source: attacker
Authorization: Bearer fake-demo-token
Cookie: SESSION=fake-demo
~~~

The stub backend should see `seenGatewaySource=catalog-edge`, `sawAuthorization=false`, and `sawCookie=false` **if the active version/runtime preserves those defaults**. If not, that signals a config/header-propagation issue to investigate—do not force tests to pass by trusting client-supplied headers.

## 20. HTTP Integration Tests: Inspecting Both Backend and Client Sides

For Proxy Exchange **MVC**, a real HTTP test traversing the Servlet container and outbound HTTP client is far more valuable than unit-testing the mapper alone. Example using JDK 17+ `HttpClient`, JUnit 5, and Spring Boot:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "catalog.backend-base-url=http://127.0.0.1:9001")
class CatalogProxyIntegrationTest {

    @LocalServerPort
    int port;

    private final HttpClient http = HttpClient.newHttpClient();

    private HttpResponse<String> call(String itemId) throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("http://127.0.0.1:" + port
                        + "/api/catalog/items/" + itemId))
                // Headers solely to test anti-spoofing and sensitive forwarding.
                .header("X-Gateway-Source", "attacker")
                .header("Authorization", "Bearer fake-demo-token")
                .header("Cookie", "SESSION=fake-demo")
                .GET()
                .build();

        return http.send(request, HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void addsOutboundHeaderAndFiltersResponseHeaders() throws Exception {
        HttpResponse<String> result = call("42");

        assertEquals(200, result.statusCode());
        assertTrue(result.body().contains(
                "\"seenGatewaySource\":\"catalog-edge\""));
        assertTrue(result.body().contains("\"sawAuthorization\":false"));
        assertTrue(result.body().contains("\"sawCookie\":false"));

        assertEquals("catalog-edge",
                result.headers().firstValue("X-Proxy-Handled").orElse(""));
        assertFalse(result.headers().firstValue("Set-Cookie").isPresent());
        assertFalse(result.headers()
                .firstValue("X-Internal-Node").isPresent());
        assertTrue(result.headers().firstValue("ETag").isPresent());
    }

    @Test
    void keepsNotFoundAndServiceUnavailableStatuses() throws Exception {
        assertEquals(404, call("missing").statusCode());
        assertEquals(503, call("busy").statusCode());
    }

    @Test
    void doesNotExposeInternalRedirect() throws Exception {
        HttpResponse<String> result = call("redirect");
        assertEquals(502, result.statusCode());
        assertFalse(result.headers().firstValue("Location").isPresent());
    }
}
~~~

**Illustrative test, not executed in this lesson.** To run it, you need:

1. A **Proxy Exchange MVC** app running on `RANDOM_PORT` with `CatalogProxyController`.
2. A **separate** stub backend listening on port 9001.
3. Spring Boot Test, JUnit 5, and the matching JDK Java HTTP Client dependencies.
4. Test routing **without a Security FilterChain blocking anonymous/fake tokens**, or an intentional test authentication setup. When real Spring Security is enabled, the fake `fake-demo-token` may be rejected before reaching the controller; security should be tested in its own suite.
5. An HTTP client/ProxyExchange configuration in your version that passes HTTP 404/503 to the mapper as responses; if a client version throws exceptions instead, the integration setup must reflect your designed policy.
6. **Disable automatic redirect following on the lab's outbound HTTP client** before expecting `doesNotExposeInternalRedirect` to return 502. If the HTTP client follows redirects automatically, the mapper may never see status 302; handle/block redirects at the transport and destination egress policy layers.

In CI, it is better to start the stub on a **dynamic port** and inject the backend URL from runtime test resources rather than relying on port 9001 being free or risking parallel test collisions.

### Why Also Keep a Stub Request Journal?

An assertion on `seenGatewaySource` in the body is valuable, yet insufficient on its own:

- The system might have made **two** outbound attempts due to HTTP client/SDK retries.
- `Authorization` might have been sent on one of the attempts.
- The route might have redirected to another host before receiving the final response.
- A real token might have leaked into logs even if the final backend didn't receive it.

Therefore, the integration harness should record **outbound request count, method/path, destination host, accepted header names, and outcomes**, without storing raw secrets. A single-request test normally expects exactly one outbound call when retries and redirects are disabled.

## 21. Complete Header and ResponseEntity Testing Matrix

| Test | Setup | Expectation |
| --- | --- | --- |
| A. Add outbound header | Client sends `X-Gateway-Source: attacker` | Backend sees trusted value `catalog-edge` |
| B. Sensitive: Authorization | Client sends test token | Backend does not receive it under default blocking policy |
| C. Sensitive: Cookie | Client sends test cookie | Backend does not receive it under default blocking policy |
| D. Add response header | Backend returns 200 | Client receives `X-Proxy-Handled: catalog-edge` |
| E. Strip internal response header | Backend returns `X-Internal-Node` | Client does not receive it |
| F. Strip Set-Cookie | Backend returns fake cookie | Client does not receive it |
| G. Preserve status 404 | Backend item missing | Client gets 404, error body preserved per contract |
| H. Preserve status 503 | Backend busy | Client gets 503, not converted to 200 |
| I. No content | Backend returns 204 | Client gets 204, no fabricated body |
| J. ETag/Cache-Control | Backend sends validators | Client receives matching allowlisted headers |
| K. Redirect | Backend returns 302 with internal Location | Proxy does not leak Location; sample policy returns 502 |
| L. Compression | Backend returns gzip despite `identity` request | Compressed bytes not sent as uncompressed JSON |
| M. Multi-value headers | Backend returns multiple `Vary` values | Allowed value list preserved |
| N. Hop-by-hop | Backend returns Connection/Transfer-Encoding | Not copied as entity headers |
| O. Invalid item ID | ID contains invalid characters | Controller returns 400, **never calls upstream** |
| P. Transport failure | Backend stopped or TCP reset | Controller advice returns controlled error; no URL/token leaked |
| Q. TLS error | Invalid backend certificate | Connection fails; verification not bypassed |
| R. Large body | Response of tens of MiB | No OOM, buffering analyzed; limit enforced |
| S. SSE partial response | Stream terminates mid-way | Never attempts changing status after commit |
| T. Concurrent requests | Many simultaneous requests | No mixed headers/bodies across users |
| U. Security | JWT lacking permission | Rejected at security layer before outbound call |
| V. Retry budget | Backend fails continuously | Outbound attempts do not exceed policy |

Do not inspect only the final response because **a 200 does not tell you which headers the backend received**; nor inspect only the backend because **a valid outbound request does not prove the client response is safe**. Both sides require dedicated assertions.

### Testing the Mapper Purely Without Sockets

To test header policies quickly, extract `mapCatalogResponse` into a **package-private class/bean** and invoke it directly with synthetic `ResponseEntity<byte[]>` inputs. Assertions should check status, kept/stripped headers, body reference/bytes, and 204/302/503 cases. This unit test runs fast, but **does not replace** HTTP integration tests for actual header forwarding.

## 22. Diagnosing Header-Addition and ResponseEntity-Mapping Bugs

A broken proxy can manifest as **the backend missing a header**, **the client missing a header**, or **the wrong HTTP status/body**. Isolate the cause by identifying **which hop is missing the data**.

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Client does not see `X-Gateway-Source` | Header was added to `ProxyExchange` outbound request, not response | Use the `ResponseEntity` mapper to add response headers |
| Backend does not see `X-Proxy-Handled` | Header was added to final response, not outbound request | Use `proxy.header(...)` when the backend should receive it |
| Backend sees client-spoofed header | Outbound header policy did not override or didn't run | Check `proxy.header` and stub backend request journal |
| Backend does not see Authorization | ProxyExchange blocks sensitive headers by default | Review trust boundary and token audience; do not open wholesale |
| Backend receives unexpected token | Sensitive policy altered or headers forwarded manually | Close egress, fix policy, inspect logs/traces, rotate exposed tokens |
| Client sees internal `Set-Cookie` | Mapper copied all response headers | Use an allowlist or adjust cookie policy per contract |
| Client gets 302 pointing to internal host | `Location` forwarded unchecked | Block/allowlist-rewrite `Location`, configure HTTP client redirect policy |
| Proxy returns 200 instead of backend 404 | Mapper used `ResponseEntity.ok(...)` | Keep `upstream.getStatusCode()` unless contract transforms codes |
| 204 response has JSON body | Mapper injected payload into no-content status | Return null/empty body for 204/304/HEAD |
| Response loses `Content-Type` | Header omitted from allowlist or body changed type | Preserve or set valid media type |
| Gzipped body displays corrupted | Body bytes and `Content-Encoding` out of sync | Handle compression consistently; test `Accept-Encoding` |
| Browser cache serves wrong language | `Vary` stripped while keeping public cache policy | Forward `Vary` properly or change caching policy |
| Browser does not update after JSON transform | Kept `ETag` from old representation | Compute new `ETag` or drop old validator |
| Content-Length mismatch | Copied old length after rewriting body | Drop old header and let framework recalculate |
| Multi-value header lost | Used `getFirst` or `set` replacing all values | Use `get` + intentional list copy |
| 401/403 before ProxyExchange | Spring Security Servlet/WebFlux rejected it | Inspect security chain and token/audience; do not blame mapper |
| 502 yet backend received no request | DNS/TCP/TLS/redirect/egress failed before backend handler | Inspect transport exceptions, certificates, and destination policy |
| Timeouts make client wait too long | Missing appropriate timeout/pool budgets | Set deadlines and cap outbound resources |
| Response mapper never runs on backend error | HTTP client threw exception before creating `ResponseEntity` | Add narrow fault handler; test per implementation |
| Mapper runs multiple times per operation | Client/HTTP client retries or reactive resubscription | Measure attempts; keep mapper free of side effects |
| Memory spikes when downloading files | `byte[]` materializes oversized bodies | Use streaming/bounded buffering or suitable Gateway Server |
| Cookie leaked in logs | Logging raw `HttpHeaders`/exceptions/URIs | Log allowlisted metadata; purge/rotate secrets per incident response |

### Eight-Step Investigation Procedure

1. **Route/controller match:** did `@GetMapping` match, or did the request fail with 404/405 before ProxyExchange?
2. **Security:** did Spring Security return 401/403 before the handler?
3. **Destination:** is `proxy.uri(...)` driven by config or client? Are scheme/host/port valid and permitted?
4. **Outbound headers:** which header names/values did the stub backend see? Were `Authorization`/`Cookie` blocked properly?
5. **Upstream outcome:** was there a valid HTTP response, or a DNS/connect/TLS/timeout failure?
6. **Mapper:** was it invoked? Which headers did it copy, and did it preserve `getStatusCode()` and `getBody()`?
7. **Client response:** are status, headers, and body on the wire accurate? Did ingress/CDN modify anything further?
8. **Cross-cutting:** did retries, caching, CORS, compression, response commit, or logging cause unexpected changes?

**Never enable full HTTP exchange dumps** for diagnostics. Use a stub backend logging safe header names/metadata, standard trace IDs, and correlation between inbound and outbound calls.

## 23. Operations: Telemetry, Load Limits, and Change Policy

A ProxyExchange controller may look simple, yet it remains a **security-sensitive HTTP proxy**. Production deployments need at minimum:

| Goal | Signal / Control |
| --- | --- |
| Measure inbound HTTP | Method, template path, status, latency |
| Measure outbound HTTP | Allowlisted target service, status, timeouts, TLS/connect errors |
| Measure attempts | Distinguish client requests from retry/redirect attempts |
| Bound concurrency | HTTP client connection pool, Servlet threads / WebFlux resources |
| Bound body size | Max payload size, timeouts, streaming policy |
| Measure fallbacks | Distinguish backend 503 from gateway-generated 502/503 |
| Security | Sensitive-header stripping, TLS/mTLS, destination validation |
| Response contract | Status/`Content-Type`/`Cache-Control`/`ETag`/`Location`/`Set-Cookie` policies |
| Observability hygiene | Never log JWTs, cookies, raw URL queries, or personal bodies |
| Release safety | Regression tests for 2xx, 3xx, 4xx, 5xx, timeouts, and compression |

### 23.1. Two Different Units of Measurement

Suppose 1,000 inbound requests arrive at the controller, and the HTTP client retries 10% of requests once. Then:

~~~text
Inbound ProxyExchange controller requests = 1,000
Outbound HTTP attempts                   = 1,100
Backend successful responses             = depends on each attempt's outcome
Final client responses                   = 1,000 (if all complete)
~~~

With a bounded retry policy, attempts can exceed inbound requests; with a fail-fast circuit breaker, many inbound requests may make zero outbound calls. Therefore, **never infer backend call counts from final client HTTP statuses**.

### 23.2. Notes on Spring Cloud LoadBalancer / Service Discovery

ProxyExchange does not automatically resolve service discovery like a Gateway Server `lb://` route in all implementations. If you need discovery-based instance selection, use a compatible integration/HTTP client, a trusted `ServiceInstance` source, and service identity/egress policies. Never accept a service ID from client queries/headers to access arbitrary registered services.

### 23.3. Header Policy Changes Must Be Reviewed

A seemingly small change like adding:

~~~java
proxy.header(HttpHeaders.AUTHORIZATION, bearerToken);
~~~

can expose credentials to a backend where they were previously blocked. If `bearerToken` originates from the client request, this alters the **trust boundary** and requires review for audience, scope, destination, TLS, logs, and timeouts. Likewise, allowing `Set-Cookie` to be copied into responses can alter browser sessions or CORS behavior.

**Never treat header changes as mere formatting tweaks.** Any header affecting identity, caching, redirects, cookies, or transport can alter access control and API correctness.

### 23.4. Canary / Rollback

When deploying a new mapper:

1. Baseline 2xx/4xx/5xx rates and latency before the change.
2. Run regression tests with dummy tokens, dummy cookies, redirects, and error bodies.
3. Canary a controlled traffic slice; watch for JSON decoding, CORS, and caching errors.
4. Verify `X-Proxy-Handled` and allowlisted headers on client responses.
5. Confirm the backend **receives no extra credentials** outside the contract.
6. Keep a rollback ready in case the mapper emits out-of-policy statuses or headers.

Across multiple app instances/replicas, mapper versions can temporarily diverge during rollouts; attach a **secret-free** deployment revision tag to telemetry to tell them apart.

## 24. Hands-On Practice: Adding Headers and Mapping Responses Safely

**Scenario:** You are building a proxy controller for Catalog. The backend returns simple JSON along with `Set-Cookie` and `X-Internal-Node` that clients must not receive. You need to add `X-Gateway-Source` **only to the outbound request** and `X-Proxy-Handled` **only to the client response**.

### Part A — Preparation

1. Choose **Proxy Exchange MVC** or **Proxy Exchange WebFlux** using the matching artifact/version from the Spring Cloud BOM.
2. Start the Catalog stub from Section 19 on port 9001 in the lab or a dynamic test-harness port.
3. Configure the trusted backend base URL; never take URLs from the client.
4. Create `CatalogProxyController` as in Section 6 with GET and validated item IDs.
5. Ensure the lab sets request-body/response size limits, connect/read timeouts, and a TLS policy matching the test goals.

### Part B — Two Header Directions

1. Send `GET /api/catalog/items/42` with `X-Gateway-Source: attacker` from the client.
2. Confirm the backend receives `X-Gateway-Source: catalog-edge` set by the controller.
3. Send `Authorization: Bearer fake-demo-token` and a test cookie in an environment **with no real data**.
4. Confirm the backend does not receive either credential under the active sensitive policy.
5. Confirm the client receives `X-Proxy-Handled: catalog-edge` and **does not receive** `Set-Cookie`/`X-Internal-Node` from the stub.
6. Confirm the returned client body has the matching ID and valid UTF-8.

### Part C — Response Mapping

| Test | Action | Expectation |
| --- | --- | --- |
| 200 | Request ID `42` | Status 200, JSON Content-Type, marker header |
| 404 | Request ID `missing` | Status 404 not converted to 200 |
| 503 | Request ID `busy` | Status 503 per contract |
| 204 | Request ID `empty` | No body injected |
| 302 | Request ID `redirect` | Internal Location not leaked; sample policy returns 502 |
| ETag | Backend sends ETag | Client receives validator when representation is unchanged |
| Cache-Control | Backend sends cache policy | Client receives allowlisted header for public data |
| Compression | Stub forces encoded body | Compressed body not sent without `Content-Encoding` |
| Response header count | Backend sends multiple `Vary` values | No dropped or duplicated values |
| Unknown header | Backend sends `X-Internal-Node` | Client does not receive it |

### Part D — Build an Anti-Pattern, Then Fix It

In an **isolated lab**:

1. Temporarily replace the mapper with `ResponseEntity.ok(upstream.getBody())`.
2. Call ID `missing` or `busy` and verify the status is corrupted.
3. Restore the mapper preserving `upstream.getStatusCode()`.
4. Temporarily copy all headers with `.headers(upstream.getHeaders())` and observe internal cookies and headers leaking to the client.
5. Restore the **response allowlist** while keeping appropriate `Content-Type`/`ETag`/`Vary`.
6. Try modifying the JSON body without removing the old `ETag`/`Content-Length` and explain the consequences; **never** ship the anti-pattern to production.
7. Verify behavior with an HTTP client rather than relying solely on mapper unit tests.

### Part E — Security and Operations

1. Enable Spring Security for MVC/WebFlux; test anonymous, valid-token, and under-privileged tokens.
2. Never let clients set upstream URI/Host, and never disable TLS hostname verification.
3. Configure timeouts/budgets, and never retry non-idempotent POSTs.
4. Use the stub backend's request journal to confirm outbound attempts do not exceed policy.
5. Verify logs/traces contain no JWTs, cookies, full URI queries, or personal response bodies.
6. For large payloads/streaming, evaluate a streaming-capable approach instead of unbounded `byte[]`.
7. Document the HTTP client's redirect policy: blocking 302 in the mapper only works if the HTTP client does not follow redirects to untrusted hosts first.

### Lab Completion Sheet

| Item | Evidence Required |
| --- | --- |
| Dependency | `proxyexchange-webmvc` or `proxyexchange-webflux` matching BOM |
| Route/controller | `@GetMapping` and backend URI from trusted config |
| Outbound header | Request journal records `X-Gateway-Source` accurately |
| Sensitive headers | No `Authorization`/`Cookie` sent to backend |
| Response mapper | Accurate status/body, marker header added |
| Redaction | No `Set-Cookie`/`X-Internal-Node`/internal `Location` exposed |
| Caching | Consistent `Content-Type`/`ETag`/`Vary`/`Cache-Control` |
| Faults | 404/503/302/timeout outcomes match contract |
| Security | Anonymous/user/ops permissions enforced, no bypasses |
| Performance | Appropriate body, timeout, and concurrency limits |

**Passing criteria:** The learner accurately explains **which headers go to the backend**, **which headers return to the client**, uses a mapper without losing status/body, enforces an allowlist preventing credential/metadata leaks, and verifies both sides of the HTTP exchange.

## 25. Summary

- **Proxy Exchange** lets a Spring MVC/WebFlux controller call a backend directly via `ProxyExchange<T>` and receive `ResponseEntity<T>`. It is a **different variant from Gateway Server**.
- **`proxy.header(...)` and `proxy.headers(...)`** set **outbound request headers to the backend**, per API/Javadoc. They do not automatically add headers to the client response.
- **`proxy.get(mapper)`** and corresponding HTTP method overloads accept a `Function<ResponseEntity<T>, ResponseEntity<S>>`, letting you build response **status, headers, and body** matching your contract.
- **Never turn 404/429/503 statuses into 200** just to report “success”. Preserve upstream codes where meaningful, and separate transport failures lacking a `ResponseEntity`.
- **Selectively copy response headers:** `Content-Type`, `ETag`, `Vary`, and `Cache-Control` may need preservation; `Set-Cookie`, `Location`, hop-by-hop headers, `Content-Length`, and internal metadata need explicit policies.
- **Default sensitive request headers** such as `Authorization`/`Cookie` are typically not forwarded; never disable this guardrail without verifying token audiences and trusted destinations.
- **`ResponseEntity` does not automatically handle all streaming/binary/redirect/cache cases**. When changing bodies, account for `Content-Encoding`, validators, multi-value headers, response commit, and memory.
- **Verify from both sides:** the stub backend proves outbound headers/method/path; the HTTP client proves client status/headers/body. Test 200, 204, 302, 404, 503, TLS, timeouts, tokens, compression, and large bodies.
- **Version compatibility matters:** Proxy Exchange MVC/WebFlux artifacts, packages, and API methods must align with the Spring Boot/Spring Cloud BOM; never copy Gateway Server route filters into ProxyExchange controllers.

When adding headers or mapping responses in **SPRING_CLOUD_GATEWAY Proxy Exchange**, always identify **the exact HTTP hop, header ownership, and `ResponseEntity` contract**. A secure proxy not only routes requests to the right destination, but also returns **the right status, right body, and strictly permitted headers** to the client.

### References

- **Spring Cloud Gateway — Proxy Exchange Gateway with Spring Web MVC or WebFlux:** https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-proxy-exchange.html
- **ProxyExchange MVC Javadoc (e.g., 4.1.x API):** https://javadoc.io/static/org.springframework.cloud/spring-cloud-gateway-mvc/4.1.4/org/springframework/cloud/gateway/mvc/ProxyExchange.html
- **Spring Cloud Gateway — Server vs. Proxy Exchange Overview:** https://docs.spring.io/spring-cloud-gateway/reference/intro.html

> **When cross-referencing docs:** Prose descriptions in some older guides may blur the distinction between “downstream call” and “downstream response”. To confirm the direction of `header(...)`, check the **Javadoc and source/API of your running version** and test HTTP behavior on both the upstream and client sides.
