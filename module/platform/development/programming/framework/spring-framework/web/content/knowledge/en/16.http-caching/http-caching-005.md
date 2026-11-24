# ShallowEtagHeaderFilter, Response Generation Cost, and Optimization Limits in Spring MVC

## 1. The Problem: Does an HTTP 304 Really Save CPU?

A Spring MVC application exposes `GET /api/reports/summary`. The controller queries the DB, calls another service, constructs a DTO, and Jackson serializes it into a 500 KiB JSON payload. Most of the data rarely changes. When a client already has the body, it sends `If-None-Match` to ask whether the representation has changed. The server returns `304 Not Modified` without resending the 500 KiB.

The common misconception: **with `ShallowEtagHeaderFilter`, the controller still runs, the DB is still queried, the DTO is still computed, and the response body is still rendered into a buffer**. The filter can only compute the ETag after having the response bytes; therefore, it primarily **saves bandwidth**, and **does not avoid CPU, query, or rendering work**.

Lesson objectives:

- Understand HTTP `ETag`, `If-None-Match`, `304`, `Cache-Control`, strong/weak validators, and representation variants.
- Trace `ShallowEtagHeaderFilter` step by step: wrapping the response, caching the body, computing MD5, comparing ETags, and picking 200/304.
- Distinguish **bandwidth** from **CPU, DB I/O, serialization, memory, and GC**.
- Understand default eligibility limits by method/status/`no-store`, streaming/async issues, and `disableContentCaching`.
- Use `WebRequest.checkNotModified(...)` with an early-known validator to **avoid generating the body** when the client already holds the latest version.
- Build a Spring Boot 3 / Java 17 app with shallow, early-ETag, `no-store`, and streaming endpoints, plus MockMvc tests verifying both status codes and handler execution counts.

**Scope:** Spring MVC Servlet stack, Spring Framework 6.x, and Spring Boot 3.x. Spring WebFlux uses different reactive abstractions; do not port this Servlet filter to WebFlux.

## 2. HTTP Conditional GET and ETag

### 2.1. First Request

The client does not yet have a response:

```http
GET /api/reports/summary HTTP/1.1
Host: localhost:8080

HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-cache
ETag: "report-v15"

{"status":"ready","total":42}
```

`ETag` is a **validator for a resource's representation**, here hypothetically revision `report-v15`. The client stores the body and validator if HTTP caching policy allows.

### 2.2. Revalidation

The client checks again:

```http
GET /api/reports/summary HTTP/1.1
If-None-Match: "report-v15"

HTTP/1.1 304 Not Modified
ETag: "report-v15"
Cache-Control: no-cache
```

When the validator matches, the 304 response **carries no new representation body**. The client reuses its cached copy per HTTP semantics. The `ETag` header in these examples is illustrative; with `ShallowEtagHeaderFilter`, Spring computes the tag from bytes rather than a literal revision.

| Concept | Role |
| --- | --- |
| `ETag` | Validator sent by the server alongside the representation |
| `If-None-Match` | Client asks the server to check if the cached copy is still valid |
| `304 Not Modified` | No need to transfer the body over the network again |
| `Cache-Control: no-cache` | Cache may store, but must revalidate before reuse |
| `Cache-Control: no-store` | Do not store the response in any HTTP cache |
| `Cache-Control: private` | Allows private caching, forbids shared-cache storage |
| `Last-Modified` | Modification-timestamp validator when data supports it |
| `If-Modified-Since` | Timestamp-based conditional GET |
| `Vary` | Request headers that produce distinct response variants |
| `If-Match` | Different precondition, typically preventing overwrites on PUT/PATCH |

**Do not confuse `If-None-Match` and `If-Match`.** `If-None-Match` is typically for revalidating GETs; `If-Match` is a key precondition on updates for optimistic concurrency. `ShallowEtagHeaderFilter` does not handle DB updates, does not replace versions/transactions, and does not enforce `If-Match` preconditions.

### 2.3. Strong and Weak ETags

```http
ETag: "report-v15"
ETag: W/"report-v15"
```

- **Strong validator:** guarantees representation equivalence under HTTP strong validation semantics. Suited for byte-exact needs and `If-Match` when generated properly.
- **Weak validator:** prefixed with `W/`, indicating equivalence sufficient for cache revalidation but unsuitable as a strong validator.
- On conditional GET, `If-None-Match` uses **weak comparison**; `If-Match` requires **strong comparison**.
- An ETag is not an access token, digital signature, MAC, or authentication mechanism. Never treat tag contents as credentials.

`ShallowEtagHeaderFilter#setWriteWeakETag(true)` emits weak ETags. The demo enables it because we only care about revalidation. Never treat default strong MD5 tags as a guarantee that compression or representation variants across the entire system are handled.

### 2.4. ETags Belong to the Representation, Not Just the DB Entity

If the same URL returns different JSON by `Accept-Language`, user role, query parameter, or media type, the representations differ. The server must produce an ETag matching the actual variant and provide proper cache metadata:

```http
Cache-Control: private, no-cache
Vary: Accept-Language
```

For personal data, never set `Cache-Control: public` carelessly. `304` does not perform authorization: every request must still be authenticated and authorized properly so private information is never leaked.

## 3. How Does ShallowEtagHeaderFilter Work?

`org.springframework.web.filter.ShallowEtagHeaderFilter` extends `OncePerRequestFilter`. Instead of knowing the version up front from a repository, the filter needs the **rendered body** to compute a digest.

```text
Client GET /api/reports/summary
    │
    ▼
ShallowEtagHeaderFilter
    ├── prepares ContentCachingResponseWrapper
    │
    ▼
filterChain.doFilter(request, wrappedResponse)
    │
    ├── DispatcherServlet selects controller
    ├── queries DB / calls service / checks authz
    ├── builds domain model / DTO
    ├── renders template or Jackson serializes
    └── writes ENTIRE bytes into response wrapper
    │
    ▼
Filter reads body bytes
    ├── checks if response is eligible
    ├── hashes bytes with MD5, builds ETag
    ├── compares against request If-None-Match
    │     ├── matches → 304, does not send new body
    │     └── differs → writes ETag and copies body to client
    └── finishes processing
```

**Do not confuse this with a server-side response cache.** The filter does not store a built response from an earlier request to serve later requests without running the controller. It recomputes the tag by regenerating the body on the current request.

### 3.1. Algorithmic Idea, Not Full Source

```java
// PSEUDOCODE, do not use in place of the framework.
ContentCachingResponseWrapper wrapper =
        new ContentCachingResponseWrapper(response);

chain.doFilter(request, wrapper);   // Controller already finished!

byte[] bytes = wrapper.getContentAsByteArray();
String etag = md5AsHttpEtag(bytes);

if (ifNoneMatchMatches(request, etag)) {
    response.setStatus(304);
    // Do not send the computed body.
} else {
    response.setHeader("ETag", etag);
    wrapper.copyBodyToResponse();
}
```

Spring's real implementation handles additional HTTP status checks, existing ETags, async lifecycles, response commitment, headers, and streams. The snippet above illustrates the **execution order**, not a production-safe implementation.

### 3.2. What "Once Per Request" Means

This filter extends `OncePerRequestFilter` and has special async handling. Do not interpret `OncePerRequestFilter` as "strictly once regardless of dispatch/thread." A single HTTP request can have an initial `REQUEST` dispatch and a subsequent `ASYNC` dispatch. When mapped by the container for the right dispatcher types, `ShallowEtagHeaderFilter` participates in the final stage to compute the ETag once the async response completes.

### 3.3. Why Does the Filter Compute MD5?

Spring uses an **MD5 digest of the response content** to generate the ETag. Its purpose is cache content comparison, **not** cryptographic tamper resistance against attackers. MD5 has known cryptographic weaknesses; if security integrity is needed, use dedicated mechanisms like TLS, signatures, or SRI as appropriate.

If even one byte changes, the digest changes. Thus fields like request timestamps, random IDs, trace IDs, or unstable serialization ordering will reduce hit rates even when business content looks unchanged.

## 4. Default Conditions for Emitting a Shallow ETag

Spring 6.x Javadoc documents the factors in `isEligibleForEtag(...)`:

1. Response is not yet **committed**.
2. Response status is **2xx**.
3. Request method is **GET**.
4. `Cache-Control` does not contain `no-store` (or the header is absent).

| Request/response | Eligible by default? | Reason |
| --- | --- | --- |
| GET 200, no Cache-Control | Eligible | Method and status match |
| GET 200, `Cache-Control: no-cache` | Eligible | `no-cache` allows storage with revalidation |
| GET 200, `Cache-Control: no-store` | No | No-store policy |
| GET 404 | No | Not 2xx |
| GET 500 | No | Not 2xx |
| POST 201 | No | GET-only by default |
| PUT/PATCH/DELETE | No | Does not implement conditional writes |
| HEAD | No under default GET-only eligibility | HEAD has separate response semantics |
| GET with already-committed response | No | Cannot modify headers/status in time |

**Important:** just because a response is ineligible to *emit an ETag* does not mean wrappers and body buffering are automatically skipped. To truly avoid buffering for a large/streaming route, **exclude it in filter registration** or call the API to disable caching before writing.

You can override `isEligibleForEtag(...)` in a subclass when a custom policy is truly needed, though most cases are better served by keeping defaults and designing explicit endpoint/cache policies.

## 5. True Cost: Network, CPU, Heap, and GC

### 5.1. Cost Model

Let:

- `R`: time to query DB, call remote services, run domain logic, and render/serialize the body.
- `H(B)`: cost to hash a response body of B bytes.
- `M(B)`: cost of buffering/copying/heap/GC for holding B bytes.
- `N(B)`: cost of transmitting B bytes over the network.

```text
GET 200 without shallow filter:
  server ≈ R
  network ≈ N(B)

GET 200 with shallow:
  server ≈ R + H(B) + M(B)
  network ≈ N(B)

GET 304 with shallow:
  server ≈ R + H(B) + M(B)
  network ≈ small header bytes

GET 304 with early version/ETag check:
  server ≈ cheap metadata/version read
  network ≈ small header bytes
```

These sums are a **mental model**, not exact benchmark formulas across all environments. Internal costs vary with the Servlet stack and allocator.

### 5.2. Numeric Illustration, Not a Benchmark

| Stage | GET 200 no filter | Shallow GET 304 | Early GET 304 |
| --- | ---: | ---: | ---: |
| Read version | 2 ms | 2 ms | 2 ms |
| Query data | 60 ms | 60 ms | 0 ms |
| Build DTO | 30 ms | 30 ms | 0 ms |
| JSON serialize | 20 ms | 20 ms | 0 ms |
| Hash/wrapper | 0 ms | 5 ms | 0 ms |
| Network body | 600 KiB | 0 KiB | 0 KiB |
| Total backend work | 112 ms | 117 ms | 2 ms |

Numbers are purely illustrative for comparison; do not claim shallow 304 is always slower than 200, as observed latency also includes network, TLS, proxies, and caching. What is certain is that **rendering and queries do not magically vanish**.

### 5.3. Memory

If a wrapper holds a 5 MiB response per request, 100 concurrent requests can require roughly 500 MiB for **just one layer of body bytes**, excluding other buffers, Java objects, and copies. Actual footprint can be much larger. Therefore:

- Check p95/p99 body size and concurrent requests, not just averages.
- Measure allocation rate, GC pauses, heap, and RSS.
- Inspect async/streaming endpoints before mapping the filter to `/**`.
- Set appropriate timeouts for heavy requests.
- Never enable shallow caching for large file downloads just to check a "standard HTTP caching" box.

### 5.4. When Is the ETag Unstable?

A body might include:

```json
{
  "report": "same-result",
  "generatedAt": "2026-10-21T10:01:00Z",
  "nonce": "random-each-request"
}
```

On the next GET, `generatedAt` or `nonce` differs, so the body hash changes and the client gets `200` again. If those fields carry no required business value, consider removing them from the cacheable representation or moving them to separate metadata. Never falsify real data just to keep hashes identical.

## 6. no-cache, no-store, private, and Fresh Caches

ETag is a validator; `Cache-Control` is the storage/freshness policy:

| Header | Practical meaning |
| --- | --- |
| `no-cache` | Cache may store, but must revalidate before reuse |
| `no-store` | Cache must not store the response |
| `private` | Private caches may store; shared caches must not |
| `public, max-age=300` | Caches may reuse while fresh for 300 seconds |
| `max-age=31536000, immutable` | Useful for asset URLs with immutable hashes/versions |
| `Vary: Accept-Language` | Different language representations get distinct cache keys |
| `Vary: Accept-Encoding` | Distinguishes gzip/br/identity variants per HTTP semantics |

A **fresh cache hit in a browser or CDN** can keep the request from reaching the backend at all, saving CPU. A **revalidation sent to the server and answered with 304 by the shallow filter** still executes queries and rendering. Those are two different optimization layers.

For user-specific data, always evaluate `Cache-Control: private` or `no-store`, sessions/authorization, cookies, and shared caches. ETag does not replace authentication. If content contains sensitive data that must not be stored, prefer `no-store` over trying to compute ETags.

## 7. Strong Validators and HTTP Representation Variants

If a server or proxy compresses the body with gzip/brotli, different encoded representations differ byte-for-byte. HTTP strong validators must consistently correspond to their respective representations; never unconditionally share a strong validator across variants that are not strong-equivalent.

With the shallow filter:

- The ETag is computed from bytes observed by the wrapper at the filter's position in the chain.
- Compression may happen in the Servlet container, another filter, or a proxy, altering representation coding.
- Weak ETags are often more appropriate for cache revalidation when two representations are semantically equivalent, while still requiring accurate HTTP semantics and `Vary`.
- Proxies/CDNs may add, strip, or rewrite ETags; verify the actual response observed by clients.
- ETags contain no "security proof"; never use them as authorization tokens or tamper-proof checksums against attackers.

To avoid mistakes:

1. Add `Vary: Accept-Encoding` when encoded variants depend on that header.
2. Inspect actual ETag responses behind your reverse proxy/CDN.
3. Use content-versioned filenames for static frontend assets.
4. Test with real browsers and multiple content encodings.
5. Avoid stacking two mechanisms that both set ETags on the same response without understanding their interaction.

## 8. Streaming and Long Responses: When to Disable Shallow Caching?

A streaming response aims to send bytes **as soon as data is produced**, without waiting for the entire body. Buffering in the shallow filter defeats that goal.

Scenarios to exclude:

- `StreamingResponseBody` for large file downloads.
- Server-Sent Events (SSE; `text/event-stream`).
- Video/audio downloads and byte-range requests.
- Multi-million-row CSV exports or on-the-fly ZIP streams.
- Long-lived or unbounded responses.
- Endpoints with sensitive data marked `Cache-Control: no-store`.

Spring provides:

```java
ShallowEtagHeaderFilter.disableContentCaching(request);
```

**Must be called before writing bytes to the response.** This API requires the Servlet request passing through the filter; it controls the filter's response-caching wrapper. It does not turn an endpoint into a backpressure-aware infinite stream; you still must design streams, threads, and timeouts properly.

Example:

```java
@GetMapping("/reports/stream")
public void stream(HttpServletRequest request,
                   HttpServletResponse response) throws IOException {

    ShallowEtagHeaderFilter.disableContentCaching(request);

    response.setContentType("text/plain;charset=UTF-8");
    response.getWriter().write("chunk-one\n");
    response.getWriter().flush();
    response.getWriter().write("chunk-two\n");
    response.getWriter().flush();
}
```

*Illustrative snippet inside a `@RestController` importing `HttpServletRequest`, `HttpServletResponse`, and `IOException`. Complete project in section 10.*

When you know upfront which endpoints stream, register `ShallowEtagHeaderFilter` only on a narrow URL prefix **excluding streaming routes**. That avoids wrapping requests that never need shallow ETags.

### 8.1. Async and DispatcherType.ASYNC

`ShallowEtagHeaderFilter` extends `OncePerRequestFilter` and overrides `shouldNotFilterAsyncDispatch()` so it **does not skip** the `ASYNC` dispatch by default. The goal is to defer ETag computation until the async response finishes.

However, two layers are involved:

1. The Servlet container must **map the filter to `DispatcherType.ASYNC`**.
2. The filter itself must permit participating in the `ASYNC` dispatch.

Example:

```java
registration.setDispatcherTypes(EnumSet.of(
    DispatcherType.REQUEST,
    DispatcherType.ASYNC));
registration.setAsyncSupported(true);
```

If the container doesn't map `ASYNC`, `shouldNotFilterAsyncDispatch` returning `false` alone is not enough. When a controller returns `Callable` or `DeferredResult`, the `REQUEST` dispatch can finish before the response completes; the filter needs the right lifecycle mapping to compute the final ETag.

### 8.2. Error Dispatches and Already-Committed Responses

Default eligibility requires a `2xx` status and an uncommitted response. When a controller fails, `4xx`/`5xx` responses normally do not get shallow ETags. Once the Servlet container has committed headers/body, status can no longer be changed to `304`.

Combining multiple filters such as response compression, security, logging, and shallow caching requires testing filter order and wrappers. Never register the same filter redundantly via both `@Component` and `FilterRegistrationBean`.

## 9. Stronger Solution: Early ETag from Version/Metadata

If a resource has a cheap-to-read revision or `lastModified`, check the validator **before** running full queries.

```text
GET /reports/cheap, If-None-Match: "report-v42"
    │
    ├─ Read revision = 42 (cheap)
    ├─ build ETag = "report-v42"
    ├─ WebRequest.checkNotModified(etag)
    │      ├─ true: 304, return early
    │      └─ false: continue
    ├─ Query large dataset
    ├─ Build report DTO
    └─ Serialize JSON 200
```

Spring MVC provides `WebRequest.checkNotModified(...)`:

```java
@GetMapping("/reports/cheap")
public Map<String, String> cheap(WebRequest request) {
    String etag = "\"report-v42\"";  // from real revision
    if (request.checkNotModified(etag)) {
        return null;                 // skip building body on match
    }
    return expensiveService.generateReport();
}
```

*Illustrative snippet (not a standalone class); the complete example below uses counters to demonstrate skipping.*

Prerequisite: the validator must **change whenever anything affecting the representation changes**. If you only read table A's version while the response also depends on table B, locale, permissions, or external services, `304` can be wrong and leave clients with stale data. Keep versions/snapshots synchronized and distinguish variants.

### 9.1. Do Not Confuse with Optimistic Concurrency

`ShallowEtagHeaderFilter` does not handle `If-Match` for PUT/PATCH. If a client sends:

```http
PUT /api/reports/7 HTTP/1.1
If-Match: "v42"
Content-Type: application/json

{"title":"Changed"}
```

the server must verify the version/validator **inside an atomic transaction or conditional update**. On mismatch, return an appropriate status such as `412`. Use JPA `@Version`, database CAS, or proper optimistic locking; shallow GET ETags do not protect data from lost updates.

## 10. Spring Boot 3 + Java 17 Demo

The project highlights the difference between two questions:

- How many bytes does the client receive after revalidation?
- How many times did the controller/backend actually build the response?

Endpoints:

| Endpoint | Purpose |
| --- | --- |
| `GET /reports/shallow` | Builds the same JSON every time; shallow filter computes a weak ETag |
| `GET /reports/cheap` | Early-known version validator `"report-v1"` |
| `GET /reports/no-store` | No-store policy; emits no new shallow ETag |
| `GET /reports/stream` | Disables buffering before writing |
| `GET /metrics` | Counters illustrating how much work ran |

Uses Spring Boot **3.3.13**, Java 17+, and Maven. No database is used so the example stays focused on HTTP semantics; in production, replace counters and literal versions with real data sources.

### 10.1. Structure

```text
shallow-etag-demo/
├── pom.xml
└── src/
    ├── main/java/example/
    │   ├── ShallowEtagDemoApplication.java
    │   └── ReportController.java
    └── test/java/example/
        └── EtagBehaviorTest.java
```

### 10.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>shallow-etag-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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
```

### 10.3. ShallowEtagDemoApplication.java

```java
package example;

import java.util.EnumSet;
import java.util.List;

import jakarta.servlet.DispatcherType;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.core.Ordered;
import org.springframework.web.filter.ShallowEtagHeaderFilter;

@SpringBootApplication
public class ShallowEtagDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShallowEtagDemoApplication.class, args);
    }

    @Bean
    FilterRegistrationBean<ShallowEtagHeaderFilter> etagFilter() {
        ShallowEtagHeaderFilter filter = new ShallowEtagHeaderFilter();
        filter.setWriteWeakETag(true);

        FilterRegistrationBean<ShallowEtagHeaderFilter> registration =
                new FilterRegistrationBean<>(filter);

        registration.setName("shallowEtagFilter");

        // Only apply to known endpoints.
        // /reports/cheap uses domain version ETag: must not be re-hashed.
        registration.setUrlPatterns(List.of(
                "/reports/shallow",
                "/reports/no-store",
                "/reports/stream"));

        registration.setDispatcherTypes(EnumSet.of(
                DispatcherType.REQUEST,
                DispatcherType.ASYNC));
        registration.setAsyncSupported(true);
        registration.setOrder(Ordered.LOWEST_PRECEDENCE - 10);
        return registration;
    }
}
```

**Configuration explanation:**

- `FilterRegistrationBean` is Spring Boot's mechanism for registering a Servlet filter with explicit URL patterns.
- `setWriteWeakETag(true)` emits weak tags for revalidation, not for conditional writes.
- `/reports/cheap` is omitted from the filter mapping because the controller already provides an early ETag.
- `ASYNC` support is declared explicitly in case async handlers are added later.
- Do not also annotate `ShallowEtagHeaderFilter` with `@Component`, avoiding duplicate registration.
- Filter order affects interactions with other wrappers, security, and compression filters; test in your deployment environment if those are present.

### 10.4. ReportController.java

```java
package example;

import java.io.IOException;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.filter.ShallowEtagHeaderFilter;

@RestController
public class ReportController {

    private final AtomicInteger shallowRenderCount = new AtomicInteger();
    private final AtomicInteger cheapRenderCount = new AtomicInteger();

    @GetMapping("/reports/shallow")
    public ResponseEntity<Map<String, String>> shallow() {
        shallowRenderCount.incrementAndGet();

        return ResponseEntity.ok()
                .cacheControl(CacheControl.noCache())
                .body(Map.of("message", "unchanged-report"));
    }

    @GetMapping("/reports/no-store")
    public ResponseEntity<Map<String, String>> noStore() {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(Map.of("message", "sensitive-demo"));
    }

    @GetMapping("/reports/cheap")
    public Map<String, String> cheap(WebRequest request) {
        // In practice, read revision from metadata before building body.
        String etag = "\"report-v1\"";
        if (request.checkNotModified(etag)) {
            return null; // Do not increment counter; do not render body
        }

        cheapRenderCount.incrementAndGet();
        return Map.of("message", "unchanged-report");
    }

    @GetMapping("/reports/stream")
    public void stream(HttpServletRequest request,
                       HttpServletResponse response) throws IOException {
        ShallowEtagHeaderFilter.disableContentCaching(request);
        response.setContentType("text/plain;charset=UTF-8");
        response.getWriter().write("chunk-one\n");
        response.getWriter().flush();
        response.getWriter().write("chunk-two\n");
        response.getWriter().flush();
    }

    @GetMapping("/metrics")
    public Map<String, Integer> metrics() {
        return Map.of(
                "shallowRenderCount", shallowRenderCount.get(),
                "cheapRenderCount", cheapRenderCount.get());
    }

    public int shallowRenders() {
        return shallowRenderCount.get();
    }

    public int cheapRenders() {
        return cheapRenderCount.get();
    }
}
```

In `shallow()`, the counter increments **before** the controller returns the Map and Jackson builds the body; the filter decides `304` **after** that work runs. In `cheap()`, `WebRequest.checkNotModified` executes before the counter, so matching revalidation requests return immediately.

`CacheControl.noCache()` does not block `304`, unlike `CacheControl.noStore()`. The stream endpoint calls `disableContentCaching` before any writes to avoid buffering the full body for hashing.

`/metrics` is purely for learning; in real systems, do not expose arbitrary counters or operational details that could leak backend internals.

### 10.5. Running with Maven

In the directory containing `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

First call:

```bash
curl -i http://localhost:8080/reports/shallow
```

Expected body:

```json
{"message":"unchanged-report"}
```

The response includes `Cache-Control: no-cache` and a weak ETag like `W/"0..."`. The hash depends on exact serialized bytes; **do not invent or hardcode the hash**.

Capture the actual ETag and revalidate:

```bash
curl -sS -D headers.txt -o body.json \
  http://localhost:8080/reports/shallow

ETAG=$(grep -i '^ETag:' headers.txt \
  | head -1 | cut -d' ' -f2 | tr -d '\r')

curl -i -H "If-None-Match: $ETAG" \
  http://localhost:8080/reports/shallow

curl -sS http://localhost:8080/metrics
```

After the first two GETs succeed, the second response is `304` with no body, while `shallowRenderCount` has incremented twice. That proves the filter **does not skip the controller**.

Compare:

```bash
curl -i http://localhost:8080/reports/cheap

curl -i -H 'If-None-Match: "report-v1"' \
  http://localhost:8080/reports/cheap

curl -sS http://localhost:8080/metrics
```

The matching revalidation returns `304`; `cheapRenderCount` does not increment because the early check skipped body creation. On a busy server with other traffic, absolute counter values may differ; observe the delta per request.

The `curl` commands above use POSIX shell line continuation. On Windows PowerShell, use `curl.exe` and the corresponding variable syntax.

### 10.6. no-store and Streaming

```bash
curl -i http://localhost:8080/reports/no-store
curl -i http://localhost:8080/reports/stream
```

For `no-store`, the response should not receive a new shallow ETag from the filter. For stream, the response text is:

```text
chunk-one
chunk-two
```

Do not conclude "streaming is optimized" just by seeing two lines in `curl`: measure time-to-first-byte and run real HTTP integration tests if true streaming is a core requirement.

## 11. Testing with MockMvc

MockMvc does not run a full network/TLS/CDN/Servlet container stack. To verify filter behavior reliably, this test **attaches the filter directly** to MockMvc rather than assuming MockMvc processes every `FilterRegistrationBean` setting like embedded Tomcat. A fresh controller instance per test keeps counter assertions deterministic.

File `src/test/java/example/EtagBehaviorTest.java`:

```java
package example;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.filter.ShallowEtagHeaderFilter;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class EtagBehaviorTest {

    private ReportController controller;
    private MockMvc filteredMvc;
    private MockMvc plainMvc;

    @BeforeEach
    void setup() {
        controller = new ReportController();
        ShallowEtagHeaderFilter filter = new ShallowEtagHeaderFilter();
        filter.setWriteWeakETag(true);

        filteredMvc = MockMvcBuilders.standaloneSetup(controller)
                .addFilters(filter)
                .build();

        // Controller with early version ETag has no shallow filter.
        plainMvc = MockMvcBuilders.standaloneSetup(controller).build();
    }

    @Test
    void firstGetHasBodyAndWeakEtag() throws Exception {
        MvcResult result = filteredMvc.perform(get("/reports/shallow"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.CACHE_CONTROL, "no-cache"))
            .andExpect(jsonPath("$.message").value("unchanged-report"))
            .andReturn();

        String etag = result.getResponse().getHeader(HttpHeaders.ETAG);
        assertNotNull(etag);
        assertTrue(etag.startsWith("W/\""));
        assertEquals(1, controller.shallowRenders());
    }

    @Test
    void shallow304StillExecutesControllerTwice() throws Exception {
        MvcResult first = filteredMvc.perform(get("/reports/shallow"))
            .andExpect(status().isOk())
            .andReturn();

        String etag = first.getResponse().getHeader(HttpHeaders.ETAG);
        assertNotNull(etag);

        filteredMvc.perform(get("/reports/shallow")
                    .header(HttpHeaders.IF_NONE_MATCH, etag))
            .andExpect(status().isNotModified())
            .andExpect(content().string(""));

        // 304, yet backend built the body twice.
        assertEquals(2, controller.shallowRenders());
    }

    @Test
    void unknownValidatorReturnsFull200Response() throws Exception {
        filteredMvc.perform(get("/reports/shallow")
                    .header(HttpHeaders.IF_NONE_MATCH, "\"other\""))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("unchanged-report"));

        assertEquals(1, controller.shallowRenders());
    }

    @Test
    void noStoreDoesNotProduceShallowEtag() throws Exception {
        filteredMvc.perform(get("/reports/no-store"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.CACHE_CONTROL, "no-store"))
            .andExpect(header().doesNotExist(HttpHeaders.ETAG))
            .andExpect(jsonPath("$.message").value("sensitive-demo"));
    }

    @Test
    void earlyValidatorSkipsSecondRendering() throws Exception {
        plainMvc.perform(get("/reports/cheap"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.ETAG, "\"report-v1\""))
            .andExpect(jsonPath("$.message").value("unchanged-report"));

        assertEquals(1, controller.cheapRenders());

        plainMvc.perform(get("/reports/cheap")
                    .header(HttpHeaders.IF_NONE_MATCH, "\"report-v1\""))
            .andExpect(status().isNotModified())
            .andExpect(content().string(""));

        // Controller still handles the conditional request,
        // but payload generation was skipped.
        assertEquals(1, controller.cheapRenders());
    }

    @Test
    void noValidatorMeansRenderAgain() throws Exception {
        plainMvc.perform(get("/reports/cheap"))
            .andExpect(status().isOk());
        plainMvc.perform(get("/reports/cheap"))
            .andExpect(status().isOk());
        assertEquals(2, controller.cheapRenders());
    }

    @Test
    void streamCanBypassContentCaching() throws Exception {
        filteredMvc.perform(get("/reports/stream"))
            .andExpect(status().isOk())
            .andExpect(header().doesNotExist(HttpHeaders.ETAG))
            .andExpect(content().string(
                    containsString("chunk-one\nchunk-two\n")));
    }

    @Test
    void identicalBodiesHaveSameGeneratedEtag() throws Exception {
        MvcResult one = filteredMvc.perform(get("/reports/shallow"))
            .andExpect(status().isOk())
            .andReturn();
        MvcResult two = filteredMvc.perform(get("/reports/shallow"))
            .andExpect(status().isOk())
            .andReturn();

        assertEquals(
                one.getResponse().getHeader(HttpHeaders.ETAG),
                two.getResponse().getHeader(HttpHeaders.ETAG));
        assertEquals(2, controller.shallowRenders());
    }
}
```

**Most important takeaway of the tests:** `shallow304StillExecutesControllerTwice` must verify **both 304 and counter=2**. Merely asserting status 304 never proves reduced server work.

The `earlyValidatorSkipsSecondRendering` test proves the opposite: `304` after `checkNotModified` with no increase in the body-creation counter. When async or streaming behavior matters, add tests against a real embedded Servlet container since MockMvc does not fully simulate network buffering or async callback lifecycles.

### 11.1. Reliability and Limits of Unit/Integration Tests

- `MockMvcBuilders.standaloneSetup` tests the MVC request pipeline and manually attached filters.
- `@SpringBootTest(webEnvironment = RANDOM_PORT)` tests Servlet registration and real HTTP requests in an embedded container.
- Browsers or tests behind a reverse proxy verify caching, CORS, TLS, content encoding, and cookies.
- Load tests measure CPU, DB, GC, and latency under realistic workloads.
- Never extrapolate whole-app efficiency from a single MD5 microbenchmark.

## 12. When Should You Use ShallowEtagHeaderFilter?

| Endpoint type | Assessment | Reason |
| --- | --- | --- |
| Small JSON, cheap to build, rarely changes | Potentially suitable | Simple bandwidth savings on revalidation |
| Small HTML without a cheap version | Potentially suitable | Minimal setup to emit body-derived ETag |
| Dashboards with heavy DB/service calls | Insufficient to reduce backend load | Full processing still executes |
| APIs with cheap row version/`updatedAt` | Prefer early ETag | Can return 304 before querying/rendering |
| CSS/JS with hashed filenames | Prefer CDN/static resource cache | Fits the static resource layer |
| Exports of hundreds of MiB | Avoid shallow | Body buffering hurts memory and latency |
| SSE/streaming | Avoid or disable buffering | Must flush immediately without waiting for full body |
| Private user data requiring `no-store` | Usually unsuitable | Policy forbids caching |
| GET API with fresh timestamp in body per call | Low effectiveness | ETag changes every request |
| PUT/PATCH with `If-Match` | Wrong tool | Needs explicit versioning, transactions, concurrency |
| GET behind compressing proxy and CDN | Must test representation variants | ETag, `Vary`, and encodings can interact |

**Never "enable the filter as broadly as possible."** For endpoints with very different characteristics, register selective URL patterns or maintain a tested exclusion policy.

## 13. Common Mistakes

| Misconception | Risk | Fix |
| --- | --- | --- |
| "304 means the controller didn't run" | Overestimating CPU/DB savings | With shallow, the body was rendered before comparison |
| "Filter keeps old bodies in RAM across requests" | Wrong architecture; no server cache | Distinguish per-request wrapper from a response cache |
| "MD5 is a security signature" | Wrong threat model | Only use MD5 ETags as cache validators |
| "Weak ETag works in If-Match" | Violates strong comparison | Conditional writes need dedicated strong validators |
| "no-cache equals no-store" | Wrong cache policy | `no-cache` requires revalidation; `no-store` forbids storage |
| "Disabling cache after response was sent helps streaming" | Too late | Call `disableContentCaching` before writing |
| "Shallow ETag optimizes 1 GiB downloads" | Poor heap/GC/TTFB | Exclude streaming/downloads from the filter |
| "Setting the async flag is enough" | Missing Servlet dispatcher mapping | Register both `REQUEST`/`ASYNC` and `asyncSupported` |
| "CORS/ETag protects user data" | Shared cache leak risk | Use authentication, authorization, `private`/`no-store` |
| "Semantically identical bodies always share bytes" | Constantly changing ETags | Stabilize serialization, fields, and variants |
| "One strong ETag unconditionally fits gzip and identity" | Broken representation semantics | Align `Vary` and validators per variant |
| "Filter handles PUT If-Match automatically" | Lost updates | Implement optimistic locking and `If-Match` explicitly |
| "Enabling the filter definitely cuts latency 50%" | Ignores render vs. bandwidth bottlenecks | Benchmark p95 CPU, network, and GC |
| "Routes needing privacy should still be cached public" | Shared caches can leak data | Pick cache policies carefully |
| "Registering filter with both @Component and RegistrationBean" | Hard-to-debug double registration | Pick one clear registration method |
| "304 body has empty JSON to parse" | Client error | Handle 304 per HTTP client / cache semantics |

## 14. Measurement and Optimization Checklist

Before deciding to enable shallow ETags:

1. Measure the ratio of requests carrying `If-None-Match` and the `304` rate.
2. Compare transmitted body bytes and egress before vs. after.
3. Measure p50/p95/p99 latency, CPU, and DB query count **on both 200 and 304 requests**.
4. Measure p95/p99 body size, peak heap, allocation rate, and GC pauses under high concurrency.
5. Confirm clients/browsers actually send conditional GETs and HTTP caches behave as intended.
6. If the bottleneck is CPU/DB, prioritize early version/ETag checks or server-side caching.
7. If the bottleneck is asset bandwidth, use content-hashed static filenames, `max-age`, and CDNs.
8. For large/streaming bodies, exclude from the shallow filter and verify flushing and timeouts.
9. If responses vary by locale/authorization/encoding, check `Vary`, `private`, `no-store`, and role checks.
10. Test gzip/proxy interactions, async dispatch, and final `ETag` headers.
11. Use MockMvc for logic and HTTP integration tests for network/container behavior.
12. Never treat `304` as "proof" of reduced backend load without backend metrics.

## 15. Review Questions

**1.** Does `ShallowEtagHeaderFilter` compute the ETag before or after the controller?  
**Answer:** After the response body has been generated.

**2.** When the ETag matches, what status does the filter return?  
**Answer:** `304 Not Modified` for eligible conditional GETs.

**3.** Does a shallow 304 skip SQL queries?  
**Answer:** No. Queries may have already executed completely.

**4.** What is the primary benefit of a shallow 304?  
**Answer:** Reducing response body bytes transferred over the network.

**5.** Which hash does the filter use to compute ETags from bytes?  
**Answer:** MD5 in the Spring 6.x implementation.

**6.** What is the purpose of `setWriteWeakETag(true)`?  
**Answer:** Emitting weak ETags formatted as `W/"..."`.

**7.** Should weak shallow ETags be used in `If-Match`?  
**Answer:** No; conditional writes need strong comparison and dedicated concurrency control.

**8.** Is `Cache-Control: no-store` eligible for shallow ETag by default?  
**Answer:** No.

**9.** Does `Cache-Control: no-cache` forbid storing the response?  
**Answer:** No; it requires revalidation before reuse.

**10.** If a body is 20 MiB, what is the harm of buffering the whole body in the filter?  
**Answer:** Increases memory/GC pressure and delays flushing bytes to the client.

**11.** How can you stream without shallow buffering?  
**Answer:** Exclude the route from the filter mapping or call `disableContentCaching(request)` before writing.

**12.** Why is `DispatcherType.ASYNC` needed?  
**Answer:** Allows the filter to participate in the final async dispatch and compute the ETag at the right time.

**13.** What should you do when cheap version metadata is available?  
**Answer:** Call `WebRequest.checkNotModified(etag)` before expensive rendering.

**14.** If the version stays unchanged while the body changes, is an early 304 valid?  
**Answer:** No; the validator must reflect the entire representation.

**15.** Do HTTP `If-None-Match` and `If-Match` serve the same purpose?  
**Answer:** No; cache revalidation and write preconditions are distinct.

**16.** Why do timestamp or random fields lower the 304 rate?  
**Answer:** Response body bytes keep changing, changing the ETag hash.

**17.** Does a CDN cache hit that never calls the backend reduce server CPU?  
**Answer:** Yes, it can—but that comes from the cache layer, not the filter skipping the handler.

**18.** Which metrics prove real optimization?  
**Answer:** CPU, DB, GC, and latency alongside egress bytes and 304 rates.

**19.** Does ETag replace authentication or authorization?  
**Answer:** No. Validators do not govern access permissions.

**20.** Does status 304 carry a new JSON body?  
**Answer:** No; it carries no new representation body.

## 16. Official Documentation

- [Spring Framework 6.2 — Shallow ETag Filter](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html): body buffering, MD5, 304 vs. CPU limits, ASYNC mapping.
- [Spring Framework 6.2 — ShallowEtagHeaderFilter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/filter/ShallowEtagHeaderFilter.html): `setWriteWeakETag`, eligibility, `disableContentCaching`.
- [Spring Framework 6.2 — HTTP Caching](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-caching.html): conditional GET, `WebRequest.checkNotModified`, and ETag/Last-Modified.
- [Spring MVC — Async Requests](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html): Servlet MVC async request lifecycle.
- [Spring Boot 3.3 — Servlet Filters](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): `FilterRegistrationBean`.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): ETag validators, 304, HTTP conditional requests.
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111): `Cache-Control` directives, freshness/revalidation, and cache storage.
- [Spring Framework — MVC Test](https://docs.spring.io/spring-framework/reference/6.2/testing/spring-mvc-test-framework.html): MockMvc testing.

**Conclusion:** `ShallowEtagHeaderFilter` needs the **entire body** before computing an ETag. Its 304 saves bandwidth, **not the queries, serialization, and rendering that already ran**. When cheap revisions exist, early conditional GET lets the backend skip heavy work. For streaming, large bodies, private data, or multiple variants, design appropriate caching policies and verify with real metrics.
