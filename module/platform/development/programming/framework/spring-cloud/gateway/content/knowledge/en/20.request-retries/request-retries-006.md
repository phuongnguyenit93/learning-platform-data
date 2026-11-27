# Caching Request Bodies During Retries and Memory Cost

## 1. Why Is Retrying a Request With a Body Harder Than Retrying a GET?

In a **Spring Cloud Gateway** architecture, clients call a public endpoint; Spring Cloud Gateway Server WebFlux matches a route with predicates, executes the filter chain, optionally transforms paths/headers, resolves an instance via service discovery, and sends an HTTP request to a microservice. When the backend returns a transient failure or the connection drops, the **Retry GatewayFilter Factory** can retry the call.

For a bodyless `GET /api/products/42`, retrying is straightforward: the Gateway can issue a new request with the same method, path, and headers. For:

~~~http
POST /api/orders HTTP/1.1
Host: api.example.test
Content-Type: application/json
Idempotency-Key: order-7b23

{"sku":"A-42","quantity":2}
~~~

the request body arrives as a **reactive stream** and is normally consumed only once. If the Gateway streams all its bytes during the first attempt, where would the second attempt read the data from? To replay it, the Gateway needs to **retain a re-readable copy of the body**, or have a safely replayable data source.

According to the **Retry GatewayFilter Factory** documentation for Spring Cloud Gateway Server WebFlux, when retries are enabled for HTTP methods with a body, the Gateway **caches the body**, which can cause memory pressure. The body is stored in the `ServerWebExchangeUtils.CACHED_REQUEST_BODY_ATTR` exchange attribute as an `org.springframework.core.io.buffer.DataBuffer` in documented versions.

This is the focus of **"Caching Request Bodies During Retries and Memory Cost"** in the **Request Retries** chapter. The lesson connects to routing, filter chains, request/header transformations, service discovery, authentication, rate limiting, circuit breakers, TLS, and observability, centering on two questions:

1. How does an already-read body still reach the backend intact on **each retry attempt**?
2. What are the memory cost, latency impact, and business safety implications of doing so?

> **Scope:** This lesson uses **Spring Cloud Gateway Server WebFlux** on compatible Spring Boot/Spring Cloud versions. Gateway Server MVC has separate `cacheBody` and `AdaptCachedBody` mechanisms; **do not copy** Server MVC configurations into WebFlux.

## 2. Understanding "Retry" Accurately in the Gateway

Suppose the Gateway routes to `orders-service` and configures:

~~~yaml
filters:
  - name: Retry
    args:
      retries: 2
      statuses:
        - BAD_GATEWAY
      methods:
        - GET
~~~

`retries: 2` means up to **two additional attempts** after the initial call—meaning up to **three total attempts** for a single client request. It does **not** mean two total attempts.

~~~text
Client sends 1 request
       |
       +--> Attempt 1 --> backend returns 502
       |
       +--> Attempt 2 --> backend returns 502
       |
       +--> Attempt 3 --> backend returns 200
       |
       +--> Client receives final 200 response
~~~

Only failures permitted by the retry policy (statuses, status series, exceptions, methods, and other version constraints) trigger another attempt. If the backend returns 400 and the policy only retries 502, the Gateway must not repeat just because Retry is configured.

### 2.1. Key Parameters

| Parameter | Role | Caution |
| --- | --- | --- |
| `retries` | Number of **additional** tries | Typical max total attempts = `1 + retries` |
| `statuses` | Specific HTTP statuses eligible for retry | For example `BAD_GATEWAY`, `SERVICE_UNAVAILABLE` |
| `series` | Status groups, e.g., all 5xx | Too broad a setting can retry non-recoverable logic bugs |
| `methods` | HTTP methods allowed to retry | Docs list default as `GET` only; POST needs extreme care |
| `exceptions` | Exceptions eligible for retry | Distinguish pre-connect errors from post-processing failures |
| `backoff` | Delay and growth between attempts | Must bound total latency; use jitter if supported by version |
| `jitter`, `timeout` | Options in newer Gateway releases | Check version semantics; do not assume they cap the whole request |

Gateway WebFlux 5.x docs list Retry defaults when enabled: `retries=3`, `series=5XX`, `methods=GET`, exceptions `IOException` and `TimeoutException`, backoff/jitter disabled, and no filter-specific timeout unless configured. **Never deploy these defaults to every production API** without assessing capacity impact.

### 2.2. Retry Does Not Guarantee the Backend Has Not Processed the Request

Two different scenarios produce the exact same symptom ("Gateway received no response"):

~~~text
A. Gateway failed to connect to backend
   → backend likely never received the request

B. Backend created the order, then the connection dropped while returning the response
   → Gateway does not know whether the side effect completed
~~~

Retrying a second time in scenario B can **create two orders**. Caching the body solves **byte replayability**, **not business idempotency**. For POSTs that process payments, create orders, send emails, issue OTPs, or mutate data, design idempotency keys, unique constraints, and downstream-aligned retry policies.

## 3. Why Can't a Request Body in WebFlux Be Re-Read Automatically?

Spring WebFlux models the request body as a `Flux<DataBuffer>` or corresponding reactive stream. With streaming, bytes can be read from the socket incrementally in chunks rather than materialized upfront as an immutable byte array.

~~~mermaid
flowchart LR
    C["Client<br/>POST + request body"] --> R["Reactor Netty<br/>incoming byte stream"]
    R --> B["Flux<DataBuffer><br/>read in chunks"]
    B --> F["Gateway filter chain"]
    F --> N["NettyRoutingFilter"]
    N --> U["Downstream service"]
~~~

A body source read from an HTTP socket normally **cannot be re-subscribed to replay the original input bytes** once consumed, because sockets cannot rewind. Spring WebFlux also uses `DataBuffer` instances that may come from pooled memory with reference counting. If a custom filter reads the body without properly reconstructing the request, downstream receives an empty body; if it retains buffers without proper lifecycle release, direct memory leaks.

When WebFlux Retry supports methods with bodies, the framework can **cache the body so later attempts can reuse it**. This data stays attached to the same `ServerWebExchange` via the attribute:

~~~java
ServerWebExchangeUtils.CACHED_REQUEST_BODY_ATTR
~~~

Per WebFlux Retry docs, the object stored in this attribute is a `DataBuffer`. However, **never manually read, retain, or release this attribute in custom code without understanding version details and reference counting**. Buffer APIs and release timing are delicate framework responsibilities; test for leaks whenever writing low-level body-handling `GlobalFilter`s.

### 3.1. How Does Retry Body Caching Differ From `CacheRequestBody`?

| Mechanism | Purpose | Note |
| --- | --- | --- |
| **Retry** with body-bearing methods | Ensures body can be replayed on eligible attempts | May hold `DataBuffer` on the exchange and cause memory pressure |
| **`CacheRequestBody` GatewayFilter Factory** | Reads and caches body for other filters, optionally converting to a Java class | Also incurs buffering/deserialization cost; not free |
| **`ModifyRequestBody`** | Reads, decodes, transforms, and produces a new body | May allocate extra copies or intermediate objects |
| **`ReadBody` route predicate** | Reads body to evaluate route matching | Requires caching for downstream handling; cannot act as pure streaming |
| **`RequestSize` GatewayFilter** | Rejects payloads exceeding allowed size | Enforces size limits; does not replace retry/idempotency policies |

These mechanisms can interact within the same request; **never assume only a single copy of the body exists across the whole pipeline**. When combining `CacheRequestBody`, `ModifyRequestBody`, and Retry on one route, benchmark and verify filter ordering, buffer sizes, and version behavior. Do not blindly add `CacheRequestBody` when Retry already caches the body; it may be redundant overhead.

### 3.2. Server MVC Uses Different Configuration

**Gateway Server MVC** docs discuss `cacheBody: true` alongside the `AdaptCachedBody` filter. In Gateway **Server WebFlux**, Retry documentation describes body caching automatically for body-bearing methods; WebFlux setups do not copy `AdaptCachedBody` from MVC. Mixing the two guides causes misconfiguration or missing filters.

## 4. Memory Cost: Retained Bytes Are the Real Issue

Suppose each POST request carries a body of size `B` bytes; at a given instant `N` requests are in flight at the Gateway, each retaining its body for retries.

Total memory retained for **payloads** can be roughly estimated as:

\[
M_{\text{payload}} \approx \sum_{i=1}^{N} B_i
\]

With uniform body sizes:

\[
M_{\text{payload}} \approx N \times B
\]

Hypothetical examples:

| Body Size | Concurrent Requests Retaining Body | Minimum Payload Retained (Simple Model) |
| --- | ---: | ---: |
| 16 KiB | 100 | Roughly 1.6 MiB |
| 512 KiB | 400 | Roughly 200 MiB |
| 2 MiB | 400 | Roughly 800 MiB |
| 8 MiB | 150 | Roughly 1,200 MiB ≈ 1.17 GiB |

**This estimates raw payload size, not actual JVM RAM usage.** Real memory consumption can be higher due to pooled buffer overhead, allocator padding, copies, JSON objects, TLS buffers, response aggregation, unrelated requests, filter chains, and garbage collector pressure.

### 4.1. Does `retries=3` Multiply Body Memory by Four?

**Not necessarily.** If the Gateway holds **a single cached body** and reuses it across attempts, `retries=3` does **not by default** store four separate copies of the same body.

However, more attempts typically **extend request lifetimes**, holding buffers longer. When a backend slows down or fails, concurrent in-flight requests rise, driving up total memory even with one cache per request. If another filter copies or deserializes the body, actual copies can still multiply.

~~~text
Payload bytes per request:       B
Request retention duration:      T
Average incoming request rate:   λ

Concurrent requests ≈ λ × T in steady state.
Body memory ≈ λ × T × B (+ overhead).
~~~

This is a rough application of Little's Law, **not an exact forecast** under bursts, backpressure, uneven timeouts, or streaming.

### 4.2. Both Heap and Direct Memory Must Be Monitored

In WebFlux/Reactor Netty, many buffers are pooled **direct/off-heap** allocations. Looking solely at `-Xmx` or heap charts can miss memory pressure. Symptoms include:

- `OutOfMemoryError: Direct buffer memory` or native buffer allocation failures;
- rising process RSS/container memory and Kubernetes `OOMKilled` events;
- GC pressure when bodies are decoded into heap `String`, `byte[]`, or JSON objects;
- rising p95/p99 latency, queued requests, and open connections;
- memory leaks from custom filters failing to release `DataBuffer`s properly.

Monitor **JVM heap, Netty direct memory, process RSS, container memory, in-flight requests, and payload sizes** together; never just bump heap size to cure every issue.

### 4.3. How Long Do Buffers Stay Alive?

Buffer lifetime depends on how your version's Retry/`CacheRequestBody` handles exchange completion, cancellation, timeouts, and downstream filters. Never assume buffers are freed immediately after one failed attempt. Test all cases:

- Retry succeeds on the second attempt;
- retries exhausted, returning final error;
- client cancels mid-backoff;
- backend connection/timeout aborted;
- backend responds early before reading the full body;
- Gateway under overload or shutting down.

For custom `DataBuffer` processing, follow Spring `DataBufferUtils` contracts strictly; never call `retain()` or `release()` ad hoc inside a filter just to "save memory."

## 5. Protecting Against Oversized Bodies: `RequestSize`

Spring Cloud Gateway WebFlux provides the **`RequestSize` GatewayFilter Factory**. It bounds request size via `maxSize` and per documentation returns **413 Payload Too Large** when a request is rejected:

~~~yaml
filters:
  - name: RequestSize
    args:
      maxSize: 128KB
~~~

`maxSize` accepts a `DataSize` value with units like `KB`/`MB`. If `RequestSize` is enabled without specifying a limit, Gateway docs cite a **5 MB** default; **that is not a global limit for routes that do not use `RequestSize`**.

### 5.1. Filter Ordering Should Be Intentional

A route should only enable body retries after enforcing payload limits:

~~~text
Client request
    ↓
Route predicates
    ↓
StripPrefix              (transform path once)
    ↓
RequestSize max 128KB    (guard payload before Retry)
    ↓
Retry methods POST       (cache/replay body; may repeat downstream filters)
    ↓
NettyRoutingFilter       (dispatch request to backend)
~~~

Placing **`RequestSize` before `Retry`** in filter declaration checks size before accepting retry caching; confirm actual runtime order when custom `GlobalFilter`s or explicit orders exist. Relying on `Content-Length` alone is insufficient in every scenario: clients can send chunked/streaming bodies or inaccurate headers. Coordinate limits across ingress, HTTP server, filters, and downstream, and test **chunked requests**.

### 5.2. `spring.codec.max-in-memory-size` Is Not a Complete Solution

Spring WebFlux lets you configure buffer limits for certain **decoders/`HttpMessageReader`s**, such as `spring.codec.max-in-memory-size` in supporting Spring Boot lines. Never treat it as the **sole guaranteed cap for all body caching in Gateway Retry**:

- Retry uses its own `DataBuffer` caching path, which depending on version may not share the decoder limit.
- `ModifyRequestBody` or JSON controllers may hit `DataBufferLimitException` while raw proxy streaming takes another code path.
- Multipart file uploads use different thresholds/disk spill settings than regular form fields.
- Bumping `max-in-memory-size` to tens of MiB just to silence exceptions can worsen OOM risk.

**Right approach:** enforce size limits at ingress, avoid retrying large uploads/streams, measure actual memory, and load-test your specific Gateway version.

## 6. Safe Retry Configuration for GET and for a POST Lab

### 6.1. Start With Bodyless GET

Example for **Gateway Server WebFlux 5.x**:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-read
              uri: http://localhost:9091
              predicates:
                - Path=/api/catalog/**
                - Method=GET
              filters:
                - StripPrefix=1
                - name: Retry
                  args:
                    retries: 2
                    statuses:
                      - BAD_GATEWAY
                      - SERVICE_UNAVAILABLE
                    methods:
                      - GET
                    backoff:
                      firstBackoff: 100ms
                      maxBackoff: 400ms
                      factor: 2
                      basedOnPreviousValue: false
~~~

On this route, Retry applies only to GET; no POST body replay is needed. Measure real response times, attempt counts, and backend load before raising retry counts.

### 6.2. Body-Bearing POST: Enable Only When Idempotency Is Understood

An **intentional lab example retrying POST** to observe body caching—not a default recommendation for general APIs:

~~~yaml
server:
  port: 8080

spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: post-body-retry-lab
              uri: http://localhost:9091
              predicates:
                - Path=/api/retry/**
                - Method=POST
              filters:
                - StripPrefix=2
                - name: RequestSize
                  args:
                    maxSize: 128KB
                - name: Retry
                  args:
                    retries: 1
                    statuses:
                      - BAD_GATEWAY
                    methods:
                      - POST
                    backoff:
                      firstBackoff: 100ms
                      maxBackoff: 200ms
                      factor: 2
                      basedOnPreviousValue: false
~~~

The client calls `POST /api/retry/echo`, and the backend sees `POST /echo` because `StripPrefix=2` runs before Retry. `retries=1` permits at most two attempts. `RequestSize` caps the lab payload, though you should still test real behavior with chunked transfers and additional filters.

### 6.3. Equivalent Configuration for Gateway WebFlux 4.2/4.3

For Gateway Server WebFlux 4.2/4.3, the routes list uses the `spring.cloud.gateway.routes` prefix:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: post-body-retry-lab
          uri: http://localhost:9091
          predicates:
            - Path=/api/retry/**
            - Method=POST
          filters:
            - StripPrefix=2
            - name: RequestSize
              args:
                maxSize: 128KB
            - name: Retry
              args:
                retries: 1
                statuses:
                  - BAD_GATEWAY
                methods:
                  - POST
                backoff:
                  firstBackoff: 100ms
                  maxBackoff: 200ms
                  factor: 2
                  basedOnPreviousValue: false
~~~

**Pick the single routes namespace matching your release**—do not declare both in one project. Newer WebFlux releases typically use `spring-cloud-starter-gateway-server-webflux`, while earlier 4.x releases use `spring-cloud-starter-gateway`. Align the Spring Cloud BOM with Spring Boot and do not add Servlet MVC starters to a WebFlux Gateway.

## 7. Lab: Backend Returns 502 First, 200 Second

To verify whether Retry **actually sends the exact same body on the next attempt**, build a Spring Boot WebFlux echo backend at `localhost:9091`. The backend reads raw bytes, computes **SHA-256**, tracks attempt counts per lab ID, and intentionally returns `502` on attempt 1 and `200` on attempt 2.

**Important:** This backend is purely for observation and creates no real orders or transactions. Never cite it as proof that business POSTs are safe to retry.

### 7.1. Backend Setup

Create a Boot project with `spring-boot-starter-webflux`. File `src/main/resources/application.yml`:

~~~yaml
server:
  port: 9091

spring:
  application:
    name: retry-body-lab-backend
~~~

Startup class `src/main/java/demo/retry/RetryLabApplication.java`:

~~~java
package demo.retry;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RetryLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(RetryLabApplication.class, args);
    }
}
~~~

Controller `src/main/java/demo/retry/RetryEchoController.java`:

~~~java
package demo.retry;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class RetryEchoController {

    // Lab-only in-memory counter, not a production idempotency store.
    private final Map<String, AtomicInteger> attempts =
            new ConcurrentHashMap<>();

    @PostMapping(
            path = "/echo",
            consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    public Mono<ResponseEntity<Map<String, Object>>> echo(
            @RequestHeader("X-Lab-Request-Id") String requestId,
            @RequestBody Mono<byte[]> rawBody) {

        return rawBody.map(bytes -> {
            int attempt = attempts
                    .computeIfAbsent(requestId, ignored -> new AtomicInteger())
                    .incrementAndGet();

            Map<String, Object> result = new LinkedHashMap<>();
            result.put("requestId", requestId);
            result.put("attempt", attempt);
            result.put("bytes", bytes.length);
            result.put("sha256", sha256(bytes));

            HttpStatus status = attempt == 1
                    ? HttpStatus.BAD_GATEWAY
                    : HttpStatus.OK;

            return ResponseEntity.status(status)
                    .header("X-Backend-Attempt", Integer.toString(attempt))
                    .body(result);
        });
    }

    private String sha256(byte[] bytes) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(bytes);
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException(error);
        }
    }
}
~~~

`Mono<byte[]>` and `Content-Type: application/octet-stream` let the backend read payload bytes to compute checksums. This test endpoint is bounded by backend memory/codecs; do not use it for large production uploads. The `attempts` map lives only in one process and never evicts keys, so it fits only short lab runs.

### 7.2. Starting the Services

In the backend terminal:

~~~bash
./mvnw spring-boot:run
~~~

In another Gateway terminal, using the version-appropriate config from Section 6.2 or 6.3:

~~~bash
./mvnw spring-boot:run
~~~

On Windows, use `mvnw.cmd spring-boot:run` or an installed Maven binary. This is a hands-on guide; this lesson **does not claim the code was built or tested in the repository**.

### 7.3. Sending POST Through the Gateway

~~~bash
curl -i "http://localhost:8080/api/retry/echo" \
  -X POST \
  -H "Content-Type: application/octet-stream" \
  -H "X-Lab-Request-Id: body-replay-001" \
  --data-binary "retry-demo-payload"
~~~

When the backend has never seen `body-replay-001`, the **expected** result is:

- Attempt 1 hits the backend at `/echo`; backend reads 18 bytes and returns `502 BAD_GATEWAY`.
- The Retry filter catches the allowed 502 status and issues a second attempt.
- Attempt 2 reaches the backend with **18 bytes and the exact same SHA-256**, and backend returns `200 OK`.
- The client receives the final response with JSON `attempt=2` and header `X-Backend-Attempt: 2`.

**Illustrative** response (avoiding fake SHA-256 values so no inaccurate checksum is fabricated):

~~~http
HTTP/1.1 200 OK
X-Backend-Attempt: 2
Content-Type: application/json

{"requestId":"body-replay-001","attempt":2,"bytes":18,"sha256":"<hash-computed-by-backend>"}
~~~

To independently verify the raw-byte checksum on a machine with `sha256sum`:

~~~bash
printf '%s' 'retry-demo-payload' | sha256sum
~~~

If the body was lost or altered through the Gateway, the byte count/checksum at the backend will differ. If the response is 502 with `attempt=1`, check whether the route enables POST Retry, the filter loaded under the right namespace, and the status matches retry criteria.

### 7.4. Comparing Against Calling the Backend Directly

~~~bash
curl -i "http://localhost:9091/echo" \
  -X POST \
  -H "Content-Type: application/octet-stream" \
  -H "X-Lab-Request-Id: direct-001" \
  --data-binary "retry-demo-payload"
~~~

The first direct call normally returns **502**, as there is no Gateway Retry. Calling again with the **same** `X-Lab-Request-Id` makes the backend return **200**, proving backend behavior is deterministic. Through the Gateway, both attempts happen inside **a single client request**.

### 7.5. Distinguishing an Attempt Counter From Real Data

In this lab code, `requestId` is merely a key to count attempts. It is **not** a production idempotency implementation: there is no transactional persistence, no TTL, no payload mismatch check for the same ID, and no cross-process safety. Never copy this `ConcurrentHashMap` pattern into a payment/order deduplication system.

## 8. Testing Large Payloads and Concurrent Requests

### 8.1. Testing Oversized Payloads

The lab route limit is `128KB`. On a Unix shell, generate a temporary test payload **outside the repo**:

~~~bash
dd if=/dev/zero of=/tmp/retry-payload-256k.bin bs=1024 count=256
curl -i "http://localhost:8080/api/retry/echo" \
  -X POST \
  -H "Content-Type: application/octet-stream" \
  -H "X-Lab-Request-Id: too-large-001" \
  --data-binary "@/tmp/retry-payload-256k.bin"
~~~

The expected result from `RequestSize` is **413 Payload Too Large**, and the backend should never receive the rejected body. If another environment behaves differently, inspect filter order, transport, `Content-Length`, size enforcement on streaming/chunked requests, and upstream proxy configurations.

**Do not use this test as an excuse to bump the limit to hundreds of MiB**: the goal is verifying memory safeguards, not stressing an uncapped system. On Windows, create a binary file with an appropriate tool and pass `curl.exe --data-binary "@file.bin"`.

### 8.2. Testing Small Bodies Under High Concurrency

On a test machine, run a controlled load generator (JMeter, k6, Gatling, or equivalent). Example test plan:

~~~text
Route:       POST /api/retry/echo
Body sizes:  1 KiB, 32 KiB, 128 KiB
Concurrency: 10 → 50 → 100
Backoff:     100 ms
Retries:     1
Duration:    step up gradually; never target production systems
~~~

Measure **process RSS**, heap/non-heap/direct memory, in-flight requests, p95/p99 latency, backend 502s, final 200s, backend attempt counts, and 413/5xx/OOM rates. Compare three configurations: **no POST retry**, **POST retry with small bodies**, and **POST retry under load with size limits**.

During concurrent load tests, never reuse the same `X-Lab-Request-Id` across multiple **logical client requests**; sharing it would make the backend counter return 200 on the first attempt of subsequent requests and skew conclusions.

### 8.3. Consequences of Large Bodies Held Too Long

Suppose 400 requests run concurrently, each with a 2 MiB body. Even in the minimal model, payloads already occupy around **800 MiB** before overhead. If the backend degrades, retries with backoff lengthen every request, growing the number of concurrently held cached bodies. This is a form of **retry-induced memory amplification**, even when Retry keeps only **one cached body copy** per request.

Therefore, good practice limits **all of body size, in-flight request count, retries, per-attempt timeout, and overall request deadline**, rather than tuning `maxSize` in isolation.

## 9. Filter Order: Which Filters Does Retry Re-Execute?

Spring Cloud Gateway warns that Retry **re-executes all filters placed after it** in the matching chain. This matters when downstream filters have **side effects**:

~~~yaml
filters:
  - name: Retry
    args:
      retries: 2
      methods:
        - POST
  - AddRequestHeader=X-Attempt-Trace, repeated
~~~

An `AddRequestHeader` filter running after Retry can append the header again on repeated attempts. For custom filters, the risk is greater: logging events, deducting quotas, publishing messages, reading bodies, generating correlation IDs, or mutating state may run multiple times.

### 9.1. Deliberate Placement Before vs. After Retry

| Filter / Function | Typically Placed | Reason |
| --- | --- | --- |
| JWT/session authentication | Security `WebFilter` before proxy | Do not re-authenticate per backend retry or trust unverified tokens |
| Payload limit `RequestSize` | Before Retry | Reject oversized bodies before caching/replaying |
| Deterministic path rewrite `StripPrefix` | Before Retry in lab | Avoid re-stripping the path on each attempt |
| Client-request rate limit | Before Retry if charging one quota per client request | Avoid deducting multiple quotas due to filter re-runs |
| Immutable correlation ID header | Before Retry or designed idempotently | Keep the same ID across attempts |
| HTTP routing | Downstream segment wrapped by Retry | Allows executing the next attempt |
| Retry attempt metrics | Inside the attempt scope, explicitly designed | Count individual backend calls without conflating with client requests |

These are design recommendations, **not an absolute ordering across all `GlobalFilter`/custom filters**. The Gateway merges and sorts filters by order; verify effective order and test. If a filter after Retry has side effects, make it idempotent or attempt-aware.

### 9.2. `CacheRequestBody`/`ModifyRequestBody` and Retry

If a route runs `ModifyRequestBody` before Retry, the body may be transformed once and Retry replays the **transformed body**, depending on version/flow. If placed after Retry, transformation may execute **multiple times**. For HMAC signatures, encryption, or checksums, know precisely which body bytes are signed/transmitted and keep `Content-Length`/`Content-Type` consistent.

Never manually coalesce/release `DataBuffer`s to "save memory" without benchmarks and full mastery of pooled buffers. When multiple body reads are required, prefer official filters and check your exact version's documentation.

## 10. Idempotency: Replaying Exact Bytes Can Still Cause Business Bugs

A POST request may be **non-idempotent**: sending it twice is not equivalent to sending it once.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway
    participant O as orders-service
    C->>G: POST /orders + Idempotency-Key: K1
    G->>O: Attempt 1, body B
    Note over O: Persisted order #123
    O--xG: Connection dropped before response
    G->>O: Attempt 2, same body B
    alt Backend has proper dedup
        Note over O: Recognizes K1, creates no extra order
        O-->>G: Order #123 result
    else No dedup
        Note over O: May create order #124
        O-->>G: Second order response
    end
    G-->>C: Final result
~~~

**Idempotency keys** must be implemented in the backend or business-controlling layer, not merely injected as a header by the Gateway. Example policy:

1. Client sends a stable `Idempotency-Key` for **one logical action**, unchanged across attempts.
2. Backend binds the key to caller/tenant/endpoint and request fingerprint, persisting state in a durable store.
3. If the same key + request already finished, backend returns the stored result; if still running, returns an intentional status.
4. If the same key arrives with a different payload, backend rejects to prevent mismatch/duplication.
5. Enforces TTL and unique constraints/transactions to handle concurrent requests.

**Not every POST carrying an idempotency key is safe to auto-retry**: check the API contract, duplicate suppression, and committed state. In particular, avoid default retries for payments, OTP issuance, multi-part uploads, or device-control commands.

## 11. Requests That Should Not Cache/Replay Bodies Conventionally

| Request Type | Risk | Approach |
| --- | --- | --- |
| Hundreds of MiB/GiB file uploads | Caching entire body causes OOM/native pressure | Do not retry at Gateway; stream directly, upload to object storage, or use resumable uploads |
| Multipart file uploads | Multiple buffers/temp files and metadata | Use multipart mechanisms with strict limits/cleanup; avoid repeated caching |
| Unbounded streams / long chunked bodies | Body size unknown upfront; caching may never finish | Do not buffer/retry whole body; design reconnect/resume protocols |
| SSE/WebSocket/gRPC streaming | Connection/stream semantics differ from single HTTP request | Use dedicated stream retry/reconnect with resume offsets |
| Payment/order-creation POSTs | Side effects despite 502 responses | Retry only when backend guarantees an idempotency contract |
| Bodies holding secrets/tokens | Extra body copies linger in memory longer | Minimize retention, guard logs/heap dumps, fail fast on timeout |
| Bodyless GET/HEAD | No POST-style body cache needed | Prefer cautious retries with backoff and capped attempts |

When handling high volume, a sound architectural choice is letting the Gateway **stream-proxy without full-body caching**, while retries live at the client or a storage layer with proper resume/idempotency support. Ensure this fits product SLAs and fault tolerance goals.

## 12. Timeout, Backoff, Jitter, and Retry Storms

**Retries increase total wait duration** rather than curing an overloaded backend. With:

~~~text
Attempt 1: times out after 2 seconds
Backoff: 100 ms
Attempt 2: times out after 2 seconds
Backoff: 200 ms
Attempt 3: times out after 2 seconds
~~~

the request can hold body buffers and connections for **over six seconds** plus backoff and overhead, even though each attempt only waited two seconds. Define an **end-to-end deadline** independently of per-attempt limits.

Jitter reduces synchronized retries across multiple Gateway replicas after a shared outage. Even though Gateway 5.x exposes `jitter.randomFactor`, verify support and semantics in your active version; never paste newer properties into a 4.x config assuming they take effect.

### 12.1. Retry Storms and Load Balancing

At 1,000 requests/s when all hit 503:

~~~text
No Retry:   backend sees ~1,000 attempts/s
retries=2:  can climb toward ~3,000 attempts/s
~~~

This is a **simple worst-case estimate**, not a field measurement. When load balancing picks different instances across attempts, retries can spill load from unhealthy backends onto healthy ones, triggering a **cascading failure**. Combine retry budgets, circuit breakers, concurrency limits, deadlines, rate limiting, and health-based discovery.

**One client request ≠ one backend attempt.** Logs and metrics must record both client requests and backend attempts so traffic amplification is visible.

### 12.2. Combining Retry with Circuit Breakers

The ordering of `Retry` and `CircuitBreaker` filters determines what counts as a failure and when the circuit opens. If a circuit breaker wraps the entire retry chain, one logical request is accounted for differently than if the breaker is invoked per attempt. Design filter order, retryable failures, fallbacks, and metrics intentionally, and test in practice; **never turn both on with defaults** merely to "increase resilience."

## 13. Observing Body Caching and Protecting Sensitive Data

Worthwhile metrics to track:

- `gateway.request.inflight`: active requests and lifetimes;
- `gateway.retry.attempts`: attempts per logical request, grouped by route;
- `gateway.retry.success_after_retry`: recovery rate after retries;
- `gateway.retry.exhausted`: requests still failing on the final retry;
- bucketed request body size distribution, **never tagged by request ID**;
- JVM heap, direct memory, Netty allocator memory, process RSS/container usage;
- backend connections, timeouts, 502/503s, cancellations, and client disconnects;
- 413 rejection rate due to request size.

Exact metric names depend on your instrumentation or integrated libraries; **do not assume every name above is a built-in Gateway metric**.

### 13.1. What Must Not Be Logged

Never log raw `Authorization` headers, session cookies, request bodies with personal data, access tokens, payment details, or the contents of `CACHED_REQUEST_BODY_ATTR`. Cached bodies stay in memory until exchange completion; logging them creates **extra copies** and exposure risks.

When verifying body integrity in labs, log **SHA-256 and byte length** rather than raw payloads. Even in production, evaluate whether checksums can correlate across requests before logging them.

### 13.2. Debugging Signals

| Symptom | Possible Cause | What to Inspect |
| --- | --- | --- |
| Second attempt receives empty body | Earlier filter consumed body, Retry didn't match method/status, bad request decorator | Filter order, cached body, backend byte counts |
| Memory climbs during POST retries | Cached bodies held across many concurrent requests or extra copies created | RSS, direct memory, in-flight count, body sizes, retry duration |
| `DataBufferLimitException` | A decoder/filter buffered body past its limit | Specific codec/filter; do not just bump `maxInMemorySize` |
| 413 before reaching backend | `RequestSize`/ingress rejected payload | `maxSize`, `Content-Length`, and chunked transfers |
| Client gets 200 yet two orders exist | POST retried without idempotency | Backend transactions, unique keys, attempt counts |
| Repeated body has wrong checksum | Body transform ran multiple times or encoding changed | Raw-byte hash at backend, `Content-Type`/`Content-Length` |
| Filter after Retry runs multiple times | Retry wraps downstream chain | Reorder filters or make downstream filters idempotent |
| GET works, POST times out/OOMs | Only POST caches bodies | Cap body size and concurrency; consider disabling POST retries |
| Client cancels yet memory stays high | Buffer reference leak or broken cancellation cleanup in custom filter | `DataBufferUtils` release, allocator metrics, leak detection |
| Retries 5xx then keeps hitting 429 | Rate limiter and Retry ordering violates policy | Compare client requests vs. backend attempts |

## 14. Production Deployment Checklist

- [ ] Enable Retry only for **recoverable methods and statuses/exceptions**, favoring bodyless GET/HEAD where appropriate.
- [ ] For body-bearing POST/PUT/PATCH, enforce a real **idempotency contract**; never rely on body caching to stop duplicates.
- [ ] Understand `retries` as **additional tries** and cap total attempts.
- [ ] Recognize WebFlux body caching ties into `CACHED_REQUEST_BODY_ATTR` and may use pooled `DataBuffer`s.
- [ ] Enforce `RequestSize`/ingress limits and test `Content-Length`, chunked requests, multipart uploads, and large payloads.
- [ ] Verify ordering of Retry relative to `StripPrefix`, `RequestSize`, body modifiers, rate limiters, and circuit breakers.
- [ ] Configure per-attempt timeouts, overall deadlines, backoff, and version-supported jitter.
- [ ] Measure heap **and direct memory** under concurrent load; do not just raise `-Xmx`.
- [ ] Test successful retries, exhausted attempts, client cancellation, backend timeouts, connection resets, and post-commit backend failures.
- [ ] Never enable body retries for large uploads, streams, or non-replay-safe workflows.
- [ ] Never manually retain/release `DataBuffer`s in custom filters without strictly following ref-count contracts.
- [ ] Keep idempotency keys identical across attempts and validate them in a durable backend store.
- [ ] Ensure retries never push backend load over budget; align circuit breaker, load balancer, and rate limiter configs.
- [ ] Separate client requests from backend attempts in logs/traces/metrics without logging sensitive bodies or tokens.
- [ ] Maintain a runbook for RSS/memory spikes, `OOMKilled`, widespread 502/503s, and dialing down retries.

## 15. Self-Check Questions

**1. Why does retrying a POST require caching the body?**

Because an incoming HTTP body is typically a single-consumption reactive stream; subsequent attempts need a replayable data source, since you cannot expect the socket to re-read already-consumed bytes.

**2. With `retries: 2`, how many attempts occur at most?**

Normally **three**: one initial attempt plus two additional retries.

**3. Does enabling `retries: 3` force the Gateway to hold four copies of the body in memory?**

No. The Gateway can reuse a single cached body; the main risk comes from **in-flight concurrency, body size, buffer retention duration, and extra copies made by other filters**.

**4. Why is setting `spring.codec.max-in-memory-size=100MB` not a safe solution?**

Because that limit applies to specific codecs/decoders rather than governing all Retry body caches; raising it sharply also lets each request buffer larger bodies and pushes the system toward OOM.

**5. The backend created an order yet returned 502 due to a dropped connection, and the Gateway retries the same body. Is that safe?**

Not automatically safe. The backend must support **idempotency keys/transactions** to detect duplicates and return a consistent result.

**6. Why should `RequestSize` be placed before `Retry`?**

To reject oversized payloads before committing to body caching/replay, lowering memory exhaustion risk. Still test with custom filters and chunked transfers.

## 16. References

1. [Spring Cloud Gateway Server WebFlux — Retry GatewayFilter Factory](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/retry-factory.html): Retry parameters, `DataBuffer` body caching, and memory warnings.
2. [Spring Cloud Gateway Server WebFlux 4.2 — Retry](https://docs.spring.io/spring-cloud-gateway/reference/4.2/spring-cloud-gateway/gatewayfilter-factories/retry-factory.html): parameters and route config for the 4.x namespace.
3. [Spring Cloud Gateway Server WebFlux — RequestSize](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/requestsize-factory.html): `maxSize`, 413, and request size limits.
4. [Spring Cloud Gateway Server WebFlux — CacheRequestBody](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/cacherequestbody-factory.html): reading/caching bodies for downstream filters.
5. [Spring Framework WebFlux — Reactive Core, DataBuffer](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): pooled/direct buffers, cleanup, and memory.
6. [Spring Framework WebFlux — HTTP Codecs](https://docs.spring.io/spring-framework/reference/web/webflux/config.html): decoder/reader memory limits.
7. [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): idempotent methods, status codes, and retry considerations.

**Key Takeaway:** Retrying a body-bearing HTTP request in WebFlux Gateway requires **body replayability**, and the framework may **cache `DataBuffer`s per exchange** across attempts. Body caching increases retained memory during high concurrency or backend slowdowns; **retries extend buffer lifetimes**, even if they do not clone a fresh copy per attempt. Bound payload sizes, concurrency, timeouts, and retry budgets; verify filter ordering and **business idempotency** before enabling retries for POST/PUT/PATCH.
