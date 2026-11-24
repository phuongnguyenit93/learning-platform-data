# Avoiding block() on the Event Loop and Retrying Non-Idempotent Requests

## 1. Scenario: How One HTTP Client Can Both Stall the System and Cause Duplicate Side Effects

A Spring Boot service calls a partner's HTTP API to read a product catalog and create orders. Both operations may go through `WebClient`, yet they carry **two completely different risks**:

1. **Execution-thread risk:** a developer calls `webClient.get().retrieve().bodyToMono(...).block()` inside a WebFlux handler. A thread multiplexing many connections gets pinned waiting for the result; on Reactor non-blocking schedulers, `block()` can even throw `IllegalStateException` immediately. p95/p99 latency climbs, connections wait longer, and overall throughput drops.
2. **Business-semantics risk:** a developer adds `retryWhen(Retry.max(3))` to every HTTP request. For `POST /payments`, if the server already recorded the transaction and the response was lost, retrying creates a second transaction unless the server deduplicates it. An HTTP timeout or 503 **does not prove the server-side effect never happened**.

**Never use retries to mask blocking**, and never assume `WebClient` automatically guarantees "exactly once". You must solve the two issues at **two distinct layers**: non-blocking coordination at runtime and idempotency guarantees in the API/server contract.

This lesson belongs to the **HTTP client** section of Spring Boot web-runtime and focuses on:
- Reactor Netty's event loop, `Mono`/`Flux`, `block()`, `subscribe()`, `subscribeOn`/`publishOn`, and `Schedulers.boundedElastic()`.
- Retries as **resubscription**, error filtering, backoff + jitter, timeouts, replayable request bodies, and retry budgets.
- HTTP safe/idempotent methods per RFC 9110; risks with `POST`/`PATCH`, including 502/503/504 and network timeouts.
- `Idempotency-Key`, atomic deduplication, payload fingerprinting, handling in-flight operations, TTLs, and multi-instance deployments.
- A **runnable Java 17+ Spring Boot example**: a GET failing with 503 then succeeding, a POST that **already applied its side effect before returning 503**, and a client retrying with the same key while producing only one business effect.
- Testing, logs/metrics, warnings when calling live services, and alternatives when idempotency cannot be guaranteed.

> **Practice version:** Spring Boot 3.5.x, Java 17+, `spring-boot-starter-webflux`, `WebClient` + Project Reactor. For Boot 4.x, match starters and APIs to that version. The demo runs standalone on `localhost:8080` without calling a real payment gateway; the in-RAM object store is **illustrative only** and insufficient for production.

## 2. Distinguishing the HTTP Client from the Web Server, and MVC from WebFlux

Spring Framework offers two main HTTP client programming models:

| Client | Invocation style | Key characteristic | Typical fit |
|---|---|---|---|
| `RestClient` / `RestTemplate` | Synchronous/blocking API | Caller waits until a response arrives | MVC/JDBC applications or synchronous jobs |
| `WebClient` | `Mono`/`Flux`, reactive | Keeps the call chain non-blocking off the event loop | WebFlux, streaming, asynchronous composition |
| Reactor Netty `HttpClient` | Low-level reactive network client | Controls connections, timeouts, and transport | Customizing Netty transport beneath `WebClient` |

**`WebClient` works in both Spring MVC and Spring WebFlux.** An MVC controller running on a Servlet thread can call `WebClient.block()` at a synchronous boundary once capacity is sized; that is **not the same failure as calling `block()` on a WebFlux event loop**. Still, because the caller waits anyway, pure MVC systems are often simpler with `RestClient`.

In **Spring WebFlux**, handlers should return `Mono<T>`, `Flux<T>`, or compatible reactive wrappers so the runtime subscribes itself. Never force WebFlux into a synchronous model by calling `block()` inside `@GetMapping`.

### What Is an Event Loop?

Reactor Netty uses a relatively small set of event-loop threads to handle many asynchronous HTTP connections. While awaiting socket/network I/O, a thread serves other connections instead of idling on one request. Threads are typically named like `reactor-http-nio-*`, depending on the environment.

Diagram:

~~~text
Inbound HTTP request -> Reactor Netty event loop
                            |
                            +--> WebFlux handler returns Mono
                                      |
                                      +--> WebClient request (async)
                                      |
                                      +--> callback when response arrives
                                      |
                                      +--> write response to caller
                            |
                            +--> event loop stays free for other connections
~~~

If any code ties up an event-loop thread for hundreds of milliseconds or seconds, all other connections on that loop suffer. Having "many CPU cores" cannot save you if every event-loop thread is blocked by `Thread.sleep`, JDBC, synchronous filesystem/network I/O, or `block()`.

**Non-blocking does not mean infinitely fast.** Even without blocking, an app remains bounded by connection pools, CPU, downstream concurrency, memory, event-loop lag, and backpressure.

## 3. Why Is `Mono.block()` an Anti-Pattern on the Event Loop?

Counter-example in a WebFlux application:

~~~java
// WRONG when running on the event loop in a WebFlux handler.
@GetMapping("/orders/{id}")
public OrderDto order(@PathVariable String id) {
    return webClient.get()
            .uri("/remote/orders/{id}", id)
            .retrieve()
            .bodyToMono(OrderDto.class)
            .block(); // Blocks the handler's executing thread.
}
~~~

This is an illustrative fragment; `OrderDto` and `webClient` are not defined standalone. When a callback/handler runs on a thread marked `NonBlocking`, Reactor typically throws an error like:

~~~text
java.lang.IllegalStateException:
block()/blockFirst()/blockLast() are blocking,
which is not supported in thread reactor-http-nio-...
~~~

Exact messages and thread names vary by version and runtime. **Do not rely on this exception as your sole blocking detector**: blocking operations such as file I/O, JDBC, or `Thread.sleep` may not throw this exception yet still stall the event loop.

### The Right Way: Return the Publisher and Let WebFlux Manage Subscription

~~~java
// RIGHT fragment inside a WebFlux controller.
@GetMapping("/orders/{id}")
public Mono<OrderDto> order(@PathVariable String id) {
    return webClient.get()
            .uri("/remote/orders/{id}", id)
            .retrieve()
            .bodyToMono(OrderDto.class);
}
~~~

The request is described as a pipeline, and **the framework subscribes** at the HTTP processing boundary. The handler spawns no extra thread, never calls `block()`, and never calls `subscribe()` manually.

When chaining transformations or additional service calls:

~~~java
// Fragment: orderClient and inventoryClient are configured WebClients.
Mono<OrderView> view(String id) {
    return orderClient.get()
            .uri("/orders/{id}", id)
            .retrieve()
            .bodyToMono(OrderDto.class)
            .flatMap(order ->
                inventoryClient.get()
                    .uri("/stock/{sku}", order.sku())
                    .retrieve()
                    .bodyToMono(StockDto.class)
                    .map(stock -> new OrderView(order, stock))
            );
}
~~~

This is a design fragment; `OrderDto`, `StockDto`, and `OrderView` are assumed records/DTOs. `flatMap` composes asynchronous work; `map` is for fast synchronous transformations. **Never call blocking methods inside a `map` lambda.**

## 4. Manual `subscribe()` Is Also Usually Wrong in a Controller

Counter-example:

~~~java
@GetMapping("/fire-and-forget")
public String wrong() {
    webClient.post()
            .uri("/remote/orders")
            .retrieve()
            .bodyToMono(Void.class)
            .subscribe(); // Detached from request lifecycle, no error management.
    return "queued";
}
~~~

This is **not** proof the order was recorded. The handler returns `queued` before any result arrives, and HTTP failures happen after the response is already sent. Cancellation, tracing, retries, lifecycle, and error propagation lose connection, and testing becomes brittle.

Pick the right approach for your goal:
- **Caller needs the result:** return `Mono<Receipt>` or `Mono<ResponseEntity<...>>` so the framework awaits non-blockingly.
- **True background work:** persist a durable job into a queue/outbox with state/idempotency, return `202 Accepted` with an operation ID, and expose a status endpoint. Never treat an unmonitored `subscribe()` as a reliable queue.
- **Tests, `main`, or controlled synchronous boundaries:** subscribing or blocking where lifecycle is understood is fine, just never inside callbacks running on an event loop.

A cold **`Mono` (cold publisher)** can **re-send the HTTP request if subscribed to again**. Accidental double subscription is therefore another cause of duplicate side effects independent of `retryWhen`.

## 5. When Stuck with a Synchronous Library: Use `boundedElastic` Properly

Not every dependency has a non-blocking driver. You may have JDBC, document-signing libraries, synchronous SDKs, or blocking filesystem APIs. Never invoke them directly on the Reactor event loop.

Valid example wrapping **a single blocking call** (service fragment):

~~~java
Mono<Customer> loadCustomer(String id) {
    return Mono.fromCallable(() -> legacyJdbcClient.findCustomer(id))
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

Requires imports `reactor.core.publisher.Mono` and `reactor.core.scheduler.Schedulers`; `legacyJdbcClient` and `Customer` come from the real project. `Mono.fromCallable` defers execution until subscription, while `subscribeOn(Schedulers.boundedElastic())` moves **source execution** onto a scheduler built for bounded blocking work.

**Never "fix" it like this:**

~~~java
// WRONG: blocking happens before the Mono is even created.
Customer value = legacyJdbcClient.findCustomer(id);
return Mono.just(value).subscribeOn(Schedulers.boundedElastic());
~~~

In the broken snippet, JDBC blocks the current thread before `subscribeOn` ever takes effect. `Mono.just(...)` wraps an already-computed value and does not defer `findCustomer`.

### `subscribeOn` vs. `publishOn`

| API | Effect |
|---|---|
| `subscribeOn(scheduler)` | Selects the scheduler for **subscription/source execution**; fits `fromCallable` around legacy blocking calls |
| `publishOn(scheduler)` | Switches execution context for **downstream operators** from that point onward |
| `Schedulers.boundedElastic()` | Bounded pool intended for waiting/blocking tasks, not the event loop |
| `Schedulers.parallel()` | Intended for CPU/non-blocking work; never offload blocking I/O here |
| `Schedulers.single()` | Single shared worker; do not use for blocking I/O |

`boundedElastic` does not make JDBC reactive. It isolates blocking off the event loop; if blocking calls exceed scheduler limits, tasks queue up and latency still climbs. For heavy database workloads, consider **R2DBC** or a service architecture with properly sized thread pools, connection pools, and concurrency budgets.

Never call `block()` inside `Mono.fromCallable` just to "legitimize" using `WebClient` when you could keep the reactive pipeline intact. For unavoidable blocking SDKs, isolate an **actual synchronous call** and monitor capacity.

## 6. What Does Retry in Reactor Actually Mean?

This call:

~~~java
someMono.retryWhen(Retry.backoff(2, Duration.ofMillis(100)))
~~~

does not "resume" the same failed HTTP response. Reactor **resubscribes to the upstream publisher** after an `onError` signal according to the Retry strategy. When upstream is a cold `WebClient` HTTP request, **every new subscription can send a brand-new HTTP request**.

With `Retry.backoff(2, ...)`:
- Initial run: first attempt.
- At most **two retries** after eligible errors.
- At most **three attempts** total.
- No retry occurs once the publisher succeeds or fails with an error rejected by `filter`.
- When retries exhaust, Reactor throws a retry-exhausted exception wrapping the last cause unless customized with `onRetryExhaustedThrow`.

A sound retry chain covers:
1. **Eligibility:** is the operation safe to repeat?
2. **Error classification:** which errors are likely transient?
3. **Budget:** max retries and total time limit?
4. **Backoff/jitter:** prevent clients from retrying in lockstep.
5. **Observability:** distinguish attempts, retry reasons, exhaustion, and final outcomes.
6. **Idempotency:** if side effects exist, what ensures only one business effect happens?

### Retry Is Resubscription; It Does Not Understand Business Semantics

~~~text
subscribe #1 -> POST /charge -> server already recorded transaction
             -> response lost / timeout / 503
                         |
                         v
                 retryWhen(...)
                         |
                         v
subscribe #2 -> POST /charge -> server may record transaction a second time
~~~

The critical question **is not** "can the HTTP client retry?" but "**after retrying, does the system preserve exactly one business effect?**"

## 7. Idempotent and Safe Methods per RFC 9110

HTTP defines method semantics by standard, independent of what an HTTP client hopes.

| Method | Safe per semantics? | Idempotent per RFC 9110? | Retry guidance |
|---|---|---|---|
| `GET` | Yes | Yes | Usually eligible for transient retries if endpoint honors GET semantics |
| `HEAD` | Yes | Yes | Similar to GET |
| `OPTIONS` | Yes | Yes | Evaluate per contract and intermediaries |
| `TRACE` | Yes | Yes | Commonly disabled in real deployments |
| `PUT` | No | Yes | Can retry the same replacement state if API honors PUT semantics |
| `DELETE` | No | Yes | Idempotent in **intended effect**; 404 after repeat delete can still be valid |
| `POST` | No | **Not guaranteed** | Never auto-retry without an idempotency contract |
| `PATCH` | No | **Not guaranteed** | Safe to retry only when the patch operation/contract is idempotent |

Per **RFC 9110 §9.2.2**, a method is idempotent if the **intended effect on the server** of multiple identical requests is the same as for a single such request. It **does not require identical HTTP responses**: the first `DELETE` may return 204 while a repeat returns 404, yet the intended state remains that the resource is deleted.

**Safe** and **idempotent** are distinct: `GET` is safe (requests no server state change), whereas `PUT`/`DELETE` are idempotent while mutating state.

### Method Name Cannot Rescue a Broken Endpoint Design

If `GET /transfer-money` actually transfers money, it violates GET semantics even if a developer assumes "GET is retryable". Conversely, `POST /operations` can be designed to be **business-idempotent** via keys and deduplication; once that contract is verified, the client has a valid basis to retry.

Nor does `PUT` eliminate every hazard: a server might emit notifications per request, conditional `If-Match` headers can alter repeat outcomes, or an upstream API might violate standard semantics. Verify the **business effects that matter**.

## 8. Why Timeout or 503 Does Not Prove a POST Failed

Suppose a client calls `POST /payments`:

~~~text
T0 Client sends request, amount = 500, order = O-1
T1 Server receives request and writes transaction to DB
T2 Server commits successfully
T3 Load balancer closes connection / client times out
T4 Client sees no response
T5 Client retries POST
T6 Server records transaction a second time if not deduplicated
~~~

The client only knows it **has not received confirmation**, not whether T2 committed. This is an **ambiguous outcome**, also called an "unknown outcome".

Similarly:
- `502 Bad Gateway`: the gateway may lose the upstream connection after upstream already committed.
- `503 Service Unavailable`: can occur before or after a layer accepts/processes the request.
- `504 Gateway Timeout`: upstream may continue executing after the gateway times out.
- TCP reset / read timeout: the request may already have reached the server.
- Client cancellation: canceling the client publisher does not roll back an already-committed server effect.

**Never establish a rule that "POST returning 5xx definitely did not execute".** An error response signals an HTTP processing failure, not proof of a rolled-back transaction.

### When Can You Retry a POST?

Only when an explicit **contract/proof** exists, such as:
- The server accepts `Idempotency-Key` and guarantees the same key + payload produce **one effect** within the retention window.
- The POST endpoint has documented, tested idempotent semantics.
- The client can prove the request **was never applied**, which is rarely provable from generic network errors.
- The client performs **status reconciliation** via an operation ID and the server confirms no effect occurred.

Even with keys, handle duplicates arriving from **two clients or multiple replicas**, not only retries within one `WebClient` in one JVM.

## 9. Retries with Error Filtering, Bounds, and Backoff

For an idempotent GET endpoint, an illustrative policy:

~~~java
// Reactive WebClient call fragment using Reactor, not a standalone class.
Mono<Catalog> catalog = webClient.get()
        .uri("/catalog")
        .retrieve()
        .bodyToMono(Catalog.class)
        .retryWhen(
            Retry.backoff(2, Duration.ofMillis(100))
                .maxBackoff(Duration.ofSeconds(1))
                .jitter(0.5)
                .filter(error ->
                    error instanceof WebClientResponseException e
                        && (e.getStatusCode().value() == 503
                            || e.getStatusCode().value() == 429))
        );
~~~

Imports: `reactor.util.retry.Retry`, `java.time.Duration`, `org.springframework.web.reactive.function.client.WebClientResponseException`. `Catalog` is an assumed DTO. With `retrieve()`, 4xx/5xx become `WebClientResponseException` by default; `onStatus(...)` can customize mapping.

**This is only an example policy**, not automatically "production-safe": 
- `429 Too Many Requests` can include `Retry-After`, which should **govern wait time**. `Retry.backoff` does not automatically parse or honor `Retry-After`.
- `503` may also carry `Retry-After`; consult partner docs.
- Network connection resets/timeouts can also be transient, provided the policy verifies **request semantics** and retry budgets.
- Never blindly retry `400`, `401`, `403`, `404`, `409`, or `422`. They usually require fixing requests, credentials, permissions, or conflicts.
- For GET, `404` is normally not resolved by immediate retries unless the API explicitly documents eventual consistency.
- `Retry.max(n)` or `Retry.backoff(n, ...)` specifies **n retries**, distinct from **n total attempts**.

### Backoff + Jitter

~~~text
Attempt #1  -> 503
Wait ~100 ms (with jitter)
Attempt #2  -> 503
Wait ~200 ms (with jitter, capped by maxBackoff)
Attempt #3  -> 200 or final failure
~~~

Timings above illustrate `minBackoff` of 100ms with exponential backoff; with jitter enabled, waits **are not fixed**. The goal is preventing a "retry storm" where thousands of clients hit 503 simultaneously and retry in unison 100ms later.

**Enforce a total retry budget**, not just `maxRetries`. If a request has a 2s deadline while backoff plus per-attempt timeouts total 10s, the caller breaches its SLO. Coordinate max attempts, response timeouts, total elapsed time, connection counts, and concurrent in-flight calls.

## 10. Where to Place `timeout` Relative to `retryWhen`?

Reactor's `timeout(Duration)` signals `TimeoutException` if the pipeline does not emit in time. Operator placement changes its scope:

~~~java
// Each attempt gets its own timeout; retryWhen can retry
// TimeoutException if the policy filter permits.
Mono<Catalog> perAttempt = fetchCatalog()
        .timeout(Duration.ofSeconds(2))
        .retryWhen(retryPolicy);
~~~

~~~java
// Timeout covers the whole pipeline including retries + backoff.
Mono<Catalog> overall = fetchCatalog()
        .retryWhen(retryPolicy)
        .timeout(Duration.ofSeconds(5));
~~~

These are fragments; `fetchCatalog` and `retryPolicy` are declared in a real service.

- **Attempt timeout** before `retryWhen` bounds each subscription; if the retry filter excludes `TimeoutException`, that failure **is not retried**.
- **Overall timeout** after `retryWhen` bounds the total operation.
- Both can be combined under a clear policy, provided cancellation and user-facing errors are tested.
- HTTP connector bounds (Reactor Netty `responseTimeout`, connect timeout, pool acquire timeout) are separate limits. A transport timeout **still does not prove the server did not commit**.

**Never abuse ultra-short timeouts** to "fail fast": they turn normal slow responses into retry cascades, amplifying downstream load and creating more uncertain outcomes.

## 11. Retrying at the Right Place: Retry Only the Retryable HTTP Portion

Reactor retries **re-subscribe the entire upstream pipeline** ahead of the operator. Suppose you have:
- `debitWallet()`: deducts funds without idempotency.
- `notifyPartner()`: sends an HTTP request.

Counter-example:

~~~java
// WRONG: debitWallet() sits upstream of retryWhen and can execute again.
return debitWallet()
        .then(notifyPartner())
        .retryWhen(Retry.max(2));
~~~

If `debitWallet()` is a cold publisher causing a side effect per subscription, this can debit the wallet multiple times. Moving retry onto the HTTP branch (once the partner guarantees idempotency) narrows the scope:

~~~java
// Structural illustration; still requires proper outbox/transaction design.
return debitWallet()
        .then(notifyPartner().retryWhen(partnerSafeRetry));
~~~

**Do not assume the second version guarantees exactly-once**: if `debitWallet` and `notifyPartner` span two systems, you still need an outbox, saga, or reconciliation. Moving `retryWhen` simply prevents accidentally re-running upstream side effects.

### Never Swallow Errors Before Retrying

~~~java
// Counter-example: HTTP error turns into a success fallback,
// so retryWhen below never sees onError.
return fetch()
    .onErrorReturn(fallbackValue)
    .retryWhen(retryPolicy);
~~~

To retry transient errors before falling back, order them properly:

~~~java
return fetch()
    .retryWhen(retryPolicy)
    .onErrorReturn(fallbackValue);
~~~

Still, fallback values can hide stale data. Define explicitly when cached/stale fallbacks are acceptable versus when an explicit error must be returned.

## 12. Request Bodies Must Be Replayable

`retryWhen` resubscribes upstream. With `WebClient`, the request body must come from a source that can be re-emitted:

~~~java
// Typically re-serializes cleanly from the same immutable DTO.
.bodyValue(new OrderRequest("O-1", 500))
~~~

Riskier case:

~~~java
// Fragment: reads an InputStream once; source may not be replayable.
// Do not copy this pattern into real apps to retry file uploads.
.body(BodyInserters.fromDataBuffers(oneShotDataBufferFlux))
~~~

A single-pass file-stream `Flux<DataBuffer>`, stateful external publisher, or closed stream may **not be replayable** across retries. If body-carrying requests are retried, ensure **replayability** (fresh stream per attempt, durable source, or bounded buffers with proper `DataBuffer` lifecycle).

Also keep these consistent across attempts:
- JSON/file byte payload.
- Request method and URL.
- `Idempotency-Key`.
- Significant fields used in server fingerprinting.
- Authentication context (refresh tokens via a dedicated flow rather than infinite inline retries).
- Retry count and deadline.

A retried POST reusing the same key with a different body **violates the contract** and must be rejected by the server, never treated as continuing the same operation.

## 13. `Idempotency-Key`: Business Mechanism Protecting POST

The client generates a **unique key for one business operation**, for example:

~~~http
POST /orders HTTP/1.1
Content-Type: application/json
Idempotency-Key: 7c7c6a4c-29db-46c6-90cc-89d066eb72e1

{"orderId":"O-1","cents":500}
~~~

If the client retries, it **resends the exact same key + exact same payload**:

~~~http
POST /orders HTTP/1.1
Content-Type: application/json
Idempotency-Key: 7c7c6a4c-29db-46c6-90cc-89d066eb72e1

{"orderId":"O-1","cents":500}
~~~

Values above are illustrative. Real keys must have strong randomness (such as UUIDs) and never be reused across **two** distinct operations. When a user clicks "Buy" twice after an operation was already confirmed, the business logic must decide whether that is a **retry of the same operation** or a **new order**.

### Generate the Key Outside Retry Scope

Right:

~~~java
// Fragment: key created once per business operation.
String key = UUID.randomUUID().toString();
OrderRequest command = new OrderRequest("O-1", 500);
Mono<OrderReceipt> call = sendOrder(key, command)
        .retryWhen(safePostRetry);
~~~

Wrong if each attempt generates a new key:

~~~java
// WRONG: each resubscription generates a different key; server sees a new order.
Mono<OrderReceipt> call = Mono.defer(() ->
        sendOrder(UUID.randomUUID().toString(), command))
        .retryWhen(safePostRetry);
~~~

If `sendOrder` already attaches `retryWhen` internally, do not wrap another retry layer outside without tracking total attempts. Centralize retry policy in one observable, categorized place.

### A Key Alone Is Insufficient Without Server Enforcement

Sending `Idempotency-Key` from the client is just an HTTP header—it **does not automatically lock** any transaction. The server needs an explicit contract, typically executing:

1. Authenticate user/tenant and validate input.
2. Canonicalize or hash a payload fingerprint together with scope identifiers.
3. Look up/register the key **atomically** in a shared durable store.
4. If the key is new, execute the operation **once**, durably saving status and result.
5. If the key exists and the payload **matches**: return the stored result or an in-progress status.
6. If the key exists and the payload **differs**: reject, typically with `409 Conflict` (per contract).
7. If the operation is currently in-flight concurrently: return an appropriate status such as `409`/`202` per contract; the client polls/reconciles instead of firing unlimited concurrent requests.
8. Keep TTL/retention longer than the retry window and any user retry window.

### Scope and Security of Idempotency Keys

Deduplication must scope keys by **tenant/principal + endpoint/operation type + key** (or equivalent). Never let user A replay results from user B's key. The store can retain a body hash/fingerprint and a reference to the business record; avoid storing plaintext secrets or card numbers in an idempotency cache.

An idempotency key is a **request identifier**, not an access token. Still, because it correlates with sensitive operations, avoid excessive logging/exposure and generate unpredictable keys. Never use a one-second timestamp as a sole key.

**In practice:** the `Idempotency-Key` header name is widely adopted and covered by an IETF HTTPAPI Internet-Draft; exact semantics (which errors replay, retention, mismatch status codes) still depend on the **API provider's contract**. Never assume every service handles the header identically.

## 14. Runnable Demo: WebFlux + WebClient, GET Retries and Non-Duplicating POST

This demo is **a Spring Boot 3.5.x application calling its own internal HTTP endpoints over localhost** so no third-party service is needed. It simulates:
- `GET /server/catalog` returning 503 on the first request and 200 on the next.
- `GET /client/catalog` calling the server via `WebClient` and retrying 503 without calling `block()`.
- `POST /server/orders` **recording one side effect** per key, intentionally returning 503 the first time **after recording**, and returning the stored receipt on repeat calls with the same key.
- `POST /client/orders` preserving the key/payload and retrying **once** on 503 without creating a second side effect.
- `GET /debug/state` exposing request counts and recorded side effects in RAM.

> **Warning:** `ConcurrentHashMap`/`AtomicInteger` in this demo are **single-instance in-memory state** with no durable transactions, no cluster safety across restarts, and no real payment gateway. **Never apply this in-memory pattern directly** to production payments or orders.

### 14.1. Project Setup

Generate a project with Spring Initializr:
- Java 17+, Spring Boot 3.5.x, Gradle.
- Dependency **Spring Reactive Web (WebFlux)**—do not add the MVC starter to this lesson.

With Boot's Gradle plugin/dependency management configured, the dependency fragment is:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

This is a fragment inside a Boot project, not the entire `build.gradle`. Projects generated by Initializr include the Gradle wrapper.

### 14.2. Complete Single-File Java Code

Create `src/main/java/demo/retry/RetryDemoApplication.java`:

~~~java
package demo.retry;

import java.time.Duration;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

@SpringBootApplication
@RestController
public class RetryDemoApplication {

    private final WebClient client =
            WebClient.create("http://localhost:8080");

    private final AtomicInteger catalogAttempts = new AtomicInteger();
    private final AtomicInteger appliedOrders = new AtomicInteger();

    private final Map<String, StoredOrder> orders =
            new ConcurrentHashMap<>();
    private final Set<String> failedOnceKeys =
            ConcurrentHashMap.newKeySet();

    public static void main(String[] args) {
        SpringApplication.run(RetryDemoApplication.class, args);
    }

    public record Catalog(String name) { }
    public record OrderRequest(String orderId, int cents) { }
    public record OrderReceipt(
            String orderId, int cents, String status) { }

    private record StoredOrder(
            OrderRequest request, OrderReceipt receipt) { }

    // Retry only 503; max 1 retry (at most 2 attempts).
    private static Retry retry503Once() {
        return Retry.backoff(1, Duration.ofMillis(100))
                .maxBackoff(Duration.ofMillis(300))
                .jitter(0.2)
                .filter(ex ->
                    ex instanceof WebClientResponseException w
                        && w.getStatusCode().value() == 503
                );
    }

    // ========== Mock downstream: idempotent GET ==========
    @GetMapping("/server/catalog")
    public ResponseEntity<Catalog> serverCatalog() {
        if (catalogAttempts.incrementAndGet() == 1) {
            return ResponseEntity
                    .status(HttpStatus.SERVICE_UNAVAILABLE).build();
        }
        return ResponseEntity.ok(new Catalog("catalog-ready"));
    }

    // ========== WebClient GET: never blocks event loop ==========
    @GetMapping("/client/catalog")
    public Mono<Catalog> clientCatalog() {
        return client.get()
                .uri("/server/catalog")
                .retrieve()
                .bodyToMono(Catalog.class)
                .retryWhen(retry503Once());
    }

    // ========== Mock downstream: deduplicated POST ==========
    @PostMapping(
            path = "/server/orders",
            consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<OrderReceipt> serverOrder(
            @RequestHeader("Idempotency-Key") String key,
            @RequestBody OrderRequest command) {

        if (key.isBlank()
                || command.orderId() == null
                || command.orderId().isBlank()
                || command.cents() <= 0) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid order");
        }

        StoredOrder stored = orders.computeIfAbsent(key, k -> {
            appliedOrders.incrementAndGet();
            return new StoredOrder(
                    command,
                    new OrderReceipt(
                            command.orderId(),
                            command.cents(),
                            "APPLIED")
            );
        });

        // Do not alter payload while reusing the same key.
        if (!stored.request().equals(command)) {
            return ResponseEntity
                    .status(HttpStatus.CONFLICT).build();
        }

        // Simulate failure AFTER the effect was already recorded.
        if (failedOnceKeys.add(key)) {
            return ResponseEntity
                    .status(HttpStatus.SERVICE_UNAVAILABLE).build();
        }

        return ResponseEntity.ok(stored.receipt());
    }

    // ========== WebClient POST: preserve key, retry 503 only ==========
    @PostMapping(
            path = "/client/orders",
            consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<OrderReceipt> clientOrder(
            @RequestHeader("Idempotency-Key") String key,
            @RequestBody OrderRequest command) {

        return client.post()
                .uri("/server/orders")
                .header("Idempotency-Key", key)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(command)
                .retrieve()
                .bodyToMono(OrderReceipt.class)
                .retryWhen(retry503Once())
                // Preserve downstream status for non-retried errors like 409.
                .onErrorMap(
                    WebClientResponseException.class,
                    ex -> new ResponseStatusException(
                        ex.getStatusCode(),
                        "Downstream rejected order", ex)
                );
    }

    @GetMapping("/debug/state")
    public Map<String, Integer> state() {
        return Map.of(
            "catalogAttempts", catalogAttempts.get(),
            "appliedOrders", appliedOrders.get(),
            "uniqueKeys", orders.size()
        );
    }
}
~~~

**Why is this code non-blocking?** WebFlux handlers return `Mono`, WebClient requests run asynchronously, and there is no `block()` or `Thread.sleep`. The demo's `AtomicInteger`/`ConcurrentHashMap` structures perform fast in-RAM operations with no blocking I/O. Reactor Netty can serve client → server requests on the same app without stalling the event loop.

**Why is POST retry safe in this demo?** The mock server **deduplicates by key** via `computeIfAbsent`, returning the previous `StoredOrder` for matching payloads; the side-effect counter increments only when registering a new key. `failedOnceKeys` simulates the first call **committing** yet returning 503. This illustrates the single-JVM concept and **is not a production architecture**.

**Note on `onErrorMap`:** when the server returns 409, `retrieve()` produces a `WebClientResponseException`. Without proper mapping, a proxy API might turn downstream statuses into unexpected frontend codes. Placing `onErrorMap` **after `retryWhen`** allows 503s to retry per policy while mapping non-retryable statuses to `ResponseStatusException`. Retry-exhausted exceptions may be wrapped by Reactor; production needs full error policies for exhaustion too.

### 14.3. Startup

From the project root:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

By default the server listens on `http://localhost:8080`. Stop any other process using that port. If you change `server.port`, update **both** the hardcoded `WebClient.create(...)` URL in the demo; production should inject `WebClient.Builder` with an environment-configured base URL.

### 14.4. Testing GET with Retries

~~~bash
curl -sS -i http://localhost:8080/client/catalog
~~~

On a freshly started JVM, the catalog server returns 503 on the first call and 200 on the second. `WebClient` catches 503, Reactor retries once, and the final response returns `200 OK` with **expected JSON body**:

~~~json
{"name":"catalog-ready"}
~~~

Subsequent GET calls succeed immediately without retries. `catalogAttempts` will read at least 2 after the first test; earlier calls to catalog alter the counter.

### 14.5. Testing POST: 503 Failure Yet Only One Effect

The client generates one key per operation; in the manual curl example we use `order-demo-1` for visibility:

~~~bash
curl -sS -i \
  -H 'Idempotency-Key: order-demo-1' \
  -H 'Content-Type: application/json' \
  -d '{"orderId":"O-1","cents":500}' \
  http://localhost:8080/client/orders
~~~

Flow:
1. WebClient sends POST #1 with key `order-demo-1`.
2. `serverOrder` saves `StoredOrder` and increments `appliedOrders` to 1.
3. Server intentionally returns **503** after saving.
4. WebClient receives 503 `WebClientResponseException`, waits for backoff, and retries.
5. WebClient sends POST #2 with the **same key and same body**.
6. Server finds the existing `StoredOrder`, **does not increment `appliedOrders`**, and returns the receipt.

Expected final HTTP body:

~~~json
{"orderId":"O-1","cents":500,"status":"APPLIED"}
~~~

**This is the crucial point:** if the mock server incremented the counter on every POST without deduplication, retrying would produce **two effects**. We achieved one effect only because **the server inspects the key and stored state**, not through any magic in `retryWhen`.

### 14.6. Checking State

~~~bash
curl -sS http://localhost:8080/debug/state
~~~

If after startup you called `GET /client/catalog` once and `POST /client/orders` once as above, the three JSON numbers will be:
- `catalogAttempts = 2`
- `appliedOrders = 1`
- `uniqueKeys = 1`

JSON output looks like:

~~~json
{"catalogAttempts":2,"appliedOrders":1,"uniqueKeys":1}
~~~

JSON field order is not guaranteed with `Map.of(...)`. If additional API calls or tests ran earlier, counters will differ. Check the numeric field values rather than comparing raw body strings verbatim.

Try **resending the exact same POST** with key `order-demo-1` and identical payload: the server replays the existing receipt and `appliedOrders` stays 1.

### 14.7. Same Key with Different Payload Must Be Rejected

~~~bash
curl -sS -i \
  -H 'Idempotency-Key: order-demo-1' \
  -H 'Content-Type: application/json' \
  -d '{"orderId":"O-2","cents":500}' \
  http://localhost:8080/client/orders
~~~

The server detects a different `orderId` under the same key and returns **409 Conflict** per demo policy. The client does not retry 409, and `onErrorMap` maps the downstream status to `ResponseStatusException` so the caller sees 409; exact error JSON fields depend on Spring Boot error configuration. `appliedOrders` stays 1.

Sending a **new key** for a new order increments the counter to 2 as a distinct business operation; never reuse the same key across multiple real orders.

## 15. Why the Demo Is Insufficient for Production

The demo uses in-memory storage and `computeIfAbsent` to illustrate the mechanics. Production typically runs multiple replicas and restarts:

~~~text
Client POST (key=K) -> instance A: records payment
Client retry K      -> instance B: B does not see K if stored only in RAM
                                  -> risks recording payment a second time
~~~

True business-level idempotency requires a **shared, durable store**:
1. A unique constraint or lock guaranteeing **one key per scope** is registered atomically.
2. Store the payload fingerprint, status (`IN_PROGRESS/SUCCEEDED/FAILED`), and result per contract.
3. Use database transactions tying key registration to the business record, or recovery design when they cannot share a single atomic DB.
4. For external side effects (sending money through a third party), use **outboxes, sagas, workflow orchestration, or reconciliation**; a local DB transaction alone cannot prove end-to-end exactly-once across distributed systems.
5. Handle concurrent requests with the same key: the second request may wait briefly, receive 202 + polling, or receive a conflict/in-progress status per contract.
6. Set TTL long enough; once a record expires out of retention, the key looks new again. Clients must respect the protection window.
7. Replay stored responses per policy once completed, including status and safely reproducible body fields.

### Is Redis `SETNX` Enough?

`SET key value NX` can assist with temporarily **claiming a key**, yet:
- The key's TTL may expire while the operation is still running.
- A worker can crash between claiming the key and committing the effect.
- Two systems do not share one atomic transaction.
- A Redis lock alone never proves exactly-once semantics.

When the side effect lives in a database, a cleaner pattern is **a unique business key + transaction in that same DB**, paired with a transactional outbox for post-commit events. When the side effect lives in a partner system, rely on the partner's idempotency contract or reconciliation.

## 16. Response Replay, 202, and In-Progress Keys

Not every API returns the final receipt immediately:

~~~text
POST /payments (Idempotency-Key: K)
   -> 202 Accepted + operationId

GET /operations/{id}
   -> PENDING / SUCCEEDED / FAILED
~~~

This fits long-running operations well. When a client times out after POST, it should look up `operationId`/`merchantOrderId` or retry with the same key per contract rather than initiating a fresh payment.

When receiving K again:
- **Already succeeded:** return the saved receipt or lookup link.
- **In progress:** return the same operation ID / pending status.
- **Key exists with different fingerprint:** reject explicitly.
- **Never seen K:** proceed only after atomic key registration.
- **Recorded failure:** whether to replay the failure or allow retry must be a **documented server rule**. Never silently turn a terminal business failure into a brand-new operation under the same key.

If the server returns `202` and the client assumes "payment succeeded", business logic breaks. `202` means accepted for processing, not proof the final effect completed.

## 17. `Retry-After`, Rate Limiting, and Backpressure

### 429 and 503 Do Not Mean "Retry Immediately"

A server may respond:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 5
~~~

`Retry-After` can be delay seconds or an HTTP-date per HTTP semantics. Clients must parse and honor it when required by the contract, account for total deadlines, and skip retries that exceed the budget. `Retry.backoff` **does not automatically interpret this header** when given only a `WebClientResponseException` inside a generic retry filter.

If thousands of `WebClient` instances retry together:
- Downstream faces a "retry storm".
- Connection pool queues and acquisition timeouts climb.
- Event-loop resources and memory suffer pressure even without `block()`.
- Retries prolong or worsen the outage.

Systemic defenses:
- Exponential backoff + jitter.
- Bounded total attempts and overall deadlines.
- Circuit breakers, bulkheads/concurrency limits, and rate limiters where needed.
- Service/tenant-level retry budgets, not just per-HTTP-call settings.
- Honoring `Retry-After` and server-side load shedding.
- Tracing/metrics distinguishing initial requests from retry attempts.

**Specifically for non-idempotent POSTs:** rate limiters and circuit breakers only shed load—**they do not create idempotency**. You still need server deduplication or status reconciliation.

## 18. Timeouts and Retries Are Not the Same Failure

Suggested policy summary **after classifying semantics**:

| Signal | Idempotent GET/HEAD | POST/PATCH without idempotency |
|---|---|---|
| `429` with `Retry-After` | Can retry after valid delay | Do not auto-retry; require dedupe contract and budget |
| Transient `503` | Can back off and retry | Effect may already be applied; never blind-retry |
| `502/504` from proxy | Can retry with limits | Outcome may be unknown; reconcile or use idempotency key |
| Clear connect failure before sending bytes | Can retry | Retry only if **proven** unapplied; generic exceptions are insufficient |
| Read timeout awaiting response | Can retry GET | Outcome unknown; may already have committed |
| `400/401/403/409/422` | Normally do not retry same request | Never blind-retry |
| Deserialization error | Usually a contract/schema bug | Never retry endlessly |
| Cancelled by caller | Stop pipeline per lifecycle | Do not assume upstream effect rolled back |

Some APIs permit retrying `POST` with a fixed unique request ID; keep such policies **per endpoint**, not globally by HTTP method or status code. Without idempotency or lookup endpoints, the safe choice is returning **unknown/pending** and reconciling rather than issuing a duplicate command.

## 19. What to Observe in Logs and Metrics

Track:
- **Event-loop lag** and HTTP client/server p50/p95/p99 latency.
- Reactor Netty connection counts, active/idle/pending acquire counts, and connection timeouts.
- 4xx/5xx error rates, separating connect timeouts, response timeouts, and read timeouts.
- Attempts per operation and retry-exhaustion rates.
- Total duration including initial call + backoff + retries—not only the last attempt's latency.
- `Idempotency-Key` replay rates, key mismatch/conflict rates, in-flight dedupe hits, and status reconciliations.
- Executed business side-effect counts compared against total HTTP attempts.
- Circuit breaker, rate-limiter, and bulkhead states where used.

**Never put raw idempotency keys, customer IDs, or `Authorization` tokens into Prometheus/Micrometer labels**: that leaks sensitive data and causes extreme metric cardinality. Use safe trace/correlation IDs and route templates alongside controlled logs.

### Signs of Blocking

Common symptoms:
- Reactor Netty threads appear in thread dumps waiting on JDBC, file I/O, or `Thread.sleep`.
- Logs report `block() are blocking, which is not supported...`.
- Event-loop latency climbs even while CPU looks low.
- When one downstream slows down, unrelated APIs sharing the event loop slow down too.

**BlockHound** can help catch some blocking calls on non-blocking threads in dev/test, though it does not guarantee catching every library or compatibility across all JVM versions. Event-loop profiling and load testing remain essential.

## 20. Common Mistakes and Fixes

| Symptom | Common cause | Fix |
|---|---|---|
| `IllegalStateException` on `block()` in WebFlux | Blocking on a `NonBlocking` event-loop thread | Return `Mono`/`Flux` and compose with `flatMap`; never block in handlers |
| No exception thrown, yet latency spikes | `Thread.sleep`, JDBC, or blocking SDK inside callbacks | `Mono.fromCallable(...).subscribeOn(boundedElastic)` or use truly reactive client |
| API returns 200/202 early, downstream fails later | Manual fire-and-forget `subscribe()` | Return publisher or use durable queue/outbox with operation ID |
| Every retry creates a new order | POST not deduplicated | Stable idempotency key + atomic server dedupe |
| Sent key yet still created duplicate orders | In-memory server store, multi-instance, or TTL too short | Shared store, unique constraint/transaction, proper TTL/reconcile |
| Same key with different body | Client regenerates payload on retry or reuses key | Payload fingerprint, 409 conflict, one key per operation |
| Retries never trigger | `onErrorResume`/`onErrorReturn` swallowed error before `retryWhen` | Put retry before fallback; keep `onError` aligned with policy |
| More calls than expected | `Retry.max(3)` means 3 retries + 1 initial attempt | Count total attempts across all retry layers |
| Call failed yet server still processed it | Timeout/503 after commit | Never treat transport error as rollback; query operation state |
| Upload body empty on retry | One-shot source stream | Use replayable body or fresh source per attempt |
| Service crashes during recovery | All clients retry in unison | Exponential backoff + jitter, `Retry-After`, retry budgets |
| Retrying 401/403 forever | Authentication/authorization failure | Refresh credentials properly; never blind-retry |
| Retrying 409 repeats operation | Key conflict or business conflict | Handle conflict per contract; never mint a new key for the same operation |
| `block()` works in MVC, yet throughput is low | Servlet thread pinned while waiting | Pick `RestClient` for sync or async design with sized capacity |
| Retry at end of pipeline double-debits wallet | `retryWhen` wraps upstream business side effects | Narrow retry scope; use outbox/reconciliation for distributed workflows |
| Config says "2 retries" with no visibility into actual retries | Attempts and effects are unmeasured | Emit attempt counts, retry reasons, and dedupe hit metrics |
| Downstream impacted by HTTP/2 stream resets | Client cannot tell if effect committed | Enforce idempotency contracts/status lookup for non-idempotent operations |

## 21. Testing: Look Beyond HTTP 200 Responses

### Testing Pure Resubscription

With test dependencies `spring-boot-starter-test` and `io.projectreactor:reactor-test` (Gradle fragment):

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

**Standalone test** example at `src/test/java/demo/retry/RetrySemanticsTest.java`:

~~~java
package demo.retry;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.retry.Retry;

import static org.junit.jupiter.api.Assertions.assertEquals;

class RetrySemanticsTest {

    @Test
    void retriesResubscribeSource() {
        AtomicInteger subscriptions = new AtomicInteger();

        Mono<String> upstream = Mono.defer(() -> {
            if (subscriptions.incrementAndGet() == 1) {
                return Mono.error(
                    new IllegalStateException("temporary"));
            }
            return Mono.just("ok");
        });

        StepVerifier.create(upstream.retryWhen(Retry.max(1)))
                .expectNext("ok")
                .verifyComplete();

        assertEquals(2, subscriptions.get());
    }
}
~~~

This JUnit 5 class runs with matching dependencies. It proves `retryWhen(Retry.max(1))` subscribes to the source **twice** when the first attempt fails; **it does not prove HTTP POST safety**.

Run:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

When tests pass, Gradle reports `BUILD SUCCESSFUL` (exact output varies by Gradle version). Never assert only retry request counts while ignoring server-side effect counts.

### Essential Integration Test Scenarios

| Scenario | What to verify |
|---|---|
| GET returns 503 first, 200 second | Client returns 200; attempt count matches policy |
| POST commits then returns 503 | Retry with same key **does not increment** business effect count |
| Same key, different payload | Server rejects; no new effect created |
| Two concurrent POSTs with same key | Only one operation claims/commits per policy |
| Client times out after commit | Operation remains queryable; no duplicate command issued blindly |
| Server restarts between attempts | Durable store/unique constraint preserves idempotency |
| Requests hit two replicas | Deduplication works across nodes |
| Idempotency record TTL expires | Client does not assume ultra-late retries are harmless |
| Non-replayable streaming body | Retry policy skips or recreates valid source |
| POST missing key | Fails fast per contract on critical endpoints |
| 429 with `Retry-After` | Backoff honors retry delay and overall deadline |
| 400/401/403/409 | Not retried automatically |
| Cancelled subscriber | Does not assume remote effect rolled back |
| Event-loop blocking | Handler never calls `block()`/JDBC directly; latency stays stable |

### Note on Mocking the HTTP Client

`StepVerifier` above tests Reactor mechanics. For real `WebClient` HTTP behavior, use a **mock HTTP server / WireMock / MockWebServer** or the local `/server/*` demo to emit controlled 503/200 sequences. Crucially, test **commit followed by lost response**; mocking only pre-commit 503s misses the biggest duplicate-payment bug.

## 22. When to Prefer `RestClient` Over `WebClient`

In a **Spring MVC** app handling requests on Servlet threads, synchronous HTTP calls can be an intentional design. In that case:

~~~java
// Sync MVC fragment; RestClient bean/imports exist in project.
String body = restClient.get()
        .uri("/catalog")
        .retrieve()
        .body(String.class);
~~~

This is intentional blocking programming. Do not try to make it non-blocking by switching to `WebClient` and appending `.block()` when no reactive composition is needed. Even with `RestClient`, **retry idempotency rules remain identical**: an unsafe synchronous POST retry causes duplicates just like `WebClient`.

If a WebFlux application calls mostly blocking-only downstream SDKs, weigh carefully:
- Isolate blocking SDKs on `boundedElastic` with bounded concurrency.
- Adopt genuinely reactive clients on high-I/O paths.
- Separate synchronous services/workers where that boundary fits better.
- Measure memory, thread pools, and connection pools instead of merely changing controller return types.

There is no universal rule that "WebFlux is faster than MVC" or "`boundedElastic` handles infinite tasks".

## 23. Safe HTTP Client Implementation Checklist

- [ ] Identify whether the HTTP caller runs on a WebFlux event loop, Servlet thread, scheduled worker, or background job.
- [ ] Never call `block()`, `Thread.sleep`, or JDBC directly on a Reactor event loop.
- [ ] Return publishers from reactive handlers; never call manual `subscribe()` to spawn unmonitored work.
- [ ] Wrap unavoidable blocking SDKs with `fromCallable` + `subscribeOn(boundedElastic)`.
- [ ] Classify every outbound endpoint (GET/HEAD/PUT/DELETE vs. POST/PATCH) by **actual semantics**, not just method name.
- [ ] Filter retryable errors and enforce max retries plus an overall deadline.
- [ ] Use backoff + jitter and honor `Retry-After` where applicable.
- [ ] Never infinitely retry unrecoverable 4xx errors, schema mismatches, or bad credentials.
- [ ] Never auto-retry POST/PATCH without an explicit idempotency contract or reconciliation.
- [ ] Generate `Idempotency-Key` once **before** retry scope and keep the payload identical.
- [ ] Deduplicate server-side by key + fingerprint + tenant/operation scope **atomically** in a durable store.
- [ ] Handle concurrent in-flight requests, TTLs, expired keys, response replay, and key conflicts.
- [ ] Never claim "exactly once" solely from `retryWhen` or a Redis lock.
- [ ] Design outboxes, sagas, or reconciliation for multi-system transactions.
- [ ] Ensure streaming request bodies are replayable or excluded from retries.
- [ ] Test server commit followed by 503/timeout, multi-replica routing, and restarts.
- [ ] Monitor attempts, dedupe hits, operation outcomes, event-loop lag, and pool saturation.
- [ ] Never put raw tokens, sensitive idempotency keys, or PII into logs or metric labels.

## 24. Self-Check Questions

**1.** Can a WebFlux controller call `WebClient.bodyToMono(...).block()` "just to grab the value easily"?

**Answer:** You should not. It can block or throw `IllegalStateException` on non-blocking event-loop threads. Return `Mono`/`Flux` and compose with `map`/`flatMap`.

**2.** Does `Mono.fromCallable(legacyCall).subscribeOn(Schedulers.boundedElastic())` make legacy I/O non-blocking?

**Answer:** No. It offloads blocking work to an appropriate pool to protect the event loop. The I/O still blocks a worker thread and remains bounded by pool/queue limits.

**3.** Does `Retry.backoff(2, ...)` mean at most two HTTP calls?

**Answer:** No. Up to two **retries** plus the initial attempt equals up to three total attempts when eligible errors keep occurring.

**4.** Does a POST returning HTTP 503 mean the server did not create the order?

**Answer:** No. The server may have committed before returning 503, or a gateway failed on the response path. The client outcome is unknown.

**5.** Can POST requests never be retried under any circumstance?

**Answer:** No. You can retry when the endpoint contract guarantees idempotency or you have proof the request was not applied. Never **blindly auto-retry** without guarantees.

**6.** Does `PUT`/`DELETE` idempotency mean two calls must return identical HTTP responses?

**Answer:** No. Idempotency governs intended server effect, not identical status/body; a first `DELETE` returning 204 and a second returning 404 still satisfies semantics.

**7.** Is generating a fresh UUID for `Idempotency-Key` on each retry a good idea?

**Answer:** No. Keep one key per **operation** across all attempts. A new key makes the server treat the retry as a separate operation.

**8.** Does adding `Idempotency-Key` to request headers guarantee exactly-once execution?

**Answer:** No. The server needs atomic deduplication, durable storage, payload fingerprinting, scoping, and recovery; cross-system effects may also need outboxes/sagas/reconciliation.

**9.** What can happen if `retryWhen` wraps `debitWallet().then(notifyPartner())`?

**Answer:** Retrying resubscribes to the entire upstream chain, potentially repeating `debitWallet` if it is a side-effecting cold publisher. Narrow the retry scope and design transactions safely.

**10.** Why does `Retry.backoff` not automatically honor `429`'s `Retry-After` header?

**Answer:** The strategy only inspects exceptions and backoff config; it does not automatically parse downstream HTTP headers. The application needs a custom adapter/logic and budget.

**11.** What should the server do when the same key arrives with a different payload?

**Answer:** Never execute the new payload as the same operation. Reject per contract—the demo returns `409 Conflict`.

**12.** Why look up order status after a `WebClient` timeout?

**Answer:** Because the request may already have committed. Lookup/reconciliation verifies the actual outcome before issuing a new command.

## 25. Official References

- [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html)
- [Project Reactor — FAQ: How Do I Wrap a Synchronous, Blocking Call?](https://projectreactor.io/docs/core/release/reference/faq.html#faq.wrap-blocking)
- [Project Reactor — Retry and Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
- [Project Reactor — RetryBackoffSpec JavaDoc](https://projectreactor.io/docs/core/release/api/reactor/util/retry/RetryBackoffSpec.html)
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
- [Spring Framework — WebClient retrieve() and onStatus](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html)
- [Spring Framework — WebClient configuration / Reactor Netty resources](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html)
- [Spring Framework — WebFlux Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods.html)
- [RFC 9110 §9.2.2 — Idempotent Methods](https://www.rfc-editor.org/rfc/rfc9110.html#name-idempotent-methods)
- [RFC 9110 — Retry-After](https://www.rfc-editor.org/rfc/rfc9110.html#field.retry-after)
- [IETF HTTPAPI — Idempotency-Key Header (Internet-Draft; check latest status)](https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/)

**Core takeaway:** non-blocking `WebClient` pays off only when you **never block the event loop** and **never detach subscriptions uncontrollably**. `retryWhen` simply re-runs a publisher on error—it **does not** guarantee a single business effect. Especially for POST/PATCH, demand **real server-side idempotency contracts, stable keys, durable atomic deduplication, and status reconciliation** before enabling bounded retries.