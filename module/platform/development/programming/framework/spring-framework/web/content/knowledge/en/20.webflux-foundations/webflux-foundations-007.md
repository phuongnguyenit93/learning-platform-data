# Spring WebFlux — Errors, Cancellation, Timeouts, and Resource Cleanup

## 1. Objectives and Context

Spring WebFlux is built on Reactive Streams and Reactor (`Mono`/`Flux`). In a reactive application, an HTTP request does not necessarily mean a Servlet thread waiting until the controller returns. A request can be an **asynchronous sequence of signals** triggered by subscription, processed through operators, and ending in completion, error, or cancellation.

Real-world scenarios:

- A client calls an API backed by a slow upstream dependency; after 2 seconds it must time out and return a safe message.
- A browser opens Server-Sent Events (SSE) and then closes the tab: the application must release the subscription, stream resources, and decrement active connections.
- WebClient receives an HTTP response, yet the code never reads the body: pooled connections/`DataBuffer` instances may leak if low-level APIs are misused.
- A service holds an asynchronous resource (connection, session, cursor) and is cancelled mid-stream: cleanup must run on cancel too, not only on completion.
- A stream has already sent status 200 and some bytes before erroring: the HTTP response is committed, so it cannot “switch to 500 JSON” on the same response.

After this lesson, you will be able to:

1. Distinguish `onNext`, `onComplete`, `onError`, and `cancel()` per Reactive Streams; understand why **cancel is not `onError`**.
2. Use `onErrorResume`, `onErrorMap`, `onErrorReturn`, `doOnError`, `doFinally`, `doOnCancel`, and `retryWhen` in a controlled manner.
3. Distinguish Reactor's `timeout(Duration)`, network timeouts in Reactor Netty/WebClient, and gateway/client timeouts.
4. Use `Flux.using`/`Mono.using` for synchronous resources and `usingWhen` for asynchronous resource cleanup across **complete/error/cancel**.
5. Know when pooled `DataBuffer` instances and response bodies must be released, especially when working directly with streaming/raw buffers.
6. Use WebFlux `@RestControllerAdvice`, `ProblemDetail`, `ResponseStatusException`, and `WebExceptionHandler` at the right layer without leaking stack traces to clients.
7. Design SSE/WebClient streaming resource lifecycles, backpressure, cancellation propagation, retry idempotency, and observability.
8. Run a **Java 17 / Spring Boot 3.5.0 / Spring Framework 6.2** demo tested with `WebTestClient` and `StepVerifier`.

**Scope:** Spring WebFlux reactive stack. Spring MVC uses Servlet async `SseEmitter`/`DeferredResult` and has a different lifecycle. Do not use MVC `ResponseBodyEmitter` or `AsyncRequestNotUsableException` as primary WebFlux solutions.

## 2. Reactive Streams: Three Terminal Signals and One Cancellation Action

A `Publisher<T>` can emit:

~~~text
onSubscribe(Subscription)
      |
      +-- request(n) -------------------------+
      |                                       |
      v                                       v
onNext(value) ... onNext(value) ...    onComplete()
      |                                       ^
      +-------------------------------> onError(error)
      |
      +-- cancel() [subscriber -> upstream]
~~~

The diagram illustrates the possible paths, not a sequence where multiple terminal signals occur together: by protocol, after **`onComplete` or `onError`**, the publisher must not emit further `onNext` or another terminal signal.

- `onNext(T)`: data, occurring 0 or more times for `Flux`, and at most once for `Mono`.
- `onComplete()`: successful completion, no more data.
- `onError(Throwable)`: failure termination, no further normal `onNext` in that publisher.
- `Subscription.cancel()`: a signal **from downstream/subscriber to upstream** indicating no more data is needed; **not an `onError`** and does not necessarily produce `onComplete` for the cancelling subscriber.

**Cancellation is not an error.** For example, `take(1)` proactively cancels upstream after receiving one element; that is expected completion, not a system failure.

### 2.1. Why Must You Understand Cancel?

If you only write:

~~~java
.doOnError(error -> releaseResource())
~~~

then resources can leak when a browser closes the connection or a consumer calls `take(1)` and cancels. If you only use:

~~~java
.doOnComplete(() -> releaseResource())
~~~

cleanup also fails to run on error or cancel.

Better when you only need a terminal observation side effect:

~~~java
.doFinally(signal -> recordTermination(signal))
~~~

`SignalType` receives values such as `ON_COMPLETE`, `ON_ERROR`, or `CANCEL` depending on lifecycle. `doFinally` runs when the sequence terminates for any terminal/cancel reason per Reactor semantics. The callback must be **non-blocking** and thread-safe.

For owned resources specifically, prefer **resource scoping** with `using`/`usingWhen` rather than wiring manual callbacks together.

### 2.2. Cold and Hot Publishers

| Kind | Example | Consequence on Cancel |
| --- | --- | --- |
| Cold | `Mono.fromCallable(...)`, reactive repository query | Each subscription typically initiates its own work; cancelling stops upstream at the publisher level |
| Hot/shared | Shared `Sinks.Many`, shared Kafka consumer, `publish().refCount()` | Cancelling one subscriber does not necessarily stop the shared producer |
| Finite | `Flux.range(1, 10)` | Can complete very quickly before cancellation is observed |
| Infinite | `Flux.interval(...)`, SSE/live updates | Must manage cancellation, backpressure, and request lifetime |

Cancelling a subscription **does not guarantee** all external work has stopped. For instance, a blocking JDBC driver, an already-dispatched upstream HTTP request, or a third-party job may still be running. Reactive cancellation is **cooperative/best-effort** depending on the data source and adapter.

## 3. Error-Handling Operators: Picking the Right Semantics

In Reactor, an error is a **terminal signal**. Recovery operators do not “resume emitting the remaining items from the old source”; typically they replace the failed portion with a new fallback publisher/value.

### 3.1. Selection Table

| Operator | Meaning | When to Use |
| --- | --- | --- |
| `doOnError(consumer)` | Side effect upon seeing an error; **does not swallow error** | Logging/metrics/tracing |
| `onErrorReturn(value)` | Emits one fallback value, then completes | Clear, safe default |
| `onErrorResume(function)` | Switches to a fallback publisher | Cache fallback, policy-driven recovery |
| `onErrorMap(function)` | Transforms exception type, remains an error | Mapping domain/transport exceptions |
| `onErrorComplete()` | Converts an error into empty completion | Only when intentionally ignoring errors |
| `retryWhen(Retry...)` | Re-subscribes to the **source** per policy | Transient errors with idempotency and bounds |
| `doFinally(consumer)` | Observes complete/error/cancel | Metrics and terminal cleanup side effects |
| `doOnCancel(action)` | Runs on cancel | Stopping custom producers or recording cancel metrics |
| `onErrorContinue(...)` | Continues processing certain items per operator semantics | Avoid as default due to complex scoping/behavior |

### 3.2. doOnError Does Not Fix Errors

~~~java
Mono<Item> mono = service.load(id)
        .doOnError(error -> log.warn(
                "item_lookup_failed id={} kind={}",
                id, error.getClass().getSimpleName()));
~~~

If upstream emits an error, the subscriber still receives the error unless a recovery operator exists downstream.

Never rely on `doOnError` as the sole resource-cancellation handler. And never log raw exception messages for arbitrary business errors if messages could contain SQL, passwords, or PII.

### 3.3. Conditional onErrorResume

~~~java
Mono<Product> result = remoteCatalog.find(id)
        .onErrorResume(RemoteServiceUnavailable.class,
                ex -> cachedCatalog.find(id));
~~~

This is a fragment: requires application services/types. Only fall back on recoverable error types. Never turn 403 authorization errors, 400 validation errors, or `NullPointerException` bugs into cached data as if they succeeded.

### 3.4. onErrorMap Preserves Error Semantics

~~~java
return upstream.fetch(id)
        .onErrorMap(TimeoutException.class,
                ex -> new CatalogTimeoutException(ex));
~~~

Mapping low-level errors to domain-level exceptions lets the WebFlux layer return consistent statuses. The demo below likewise maps `TimeoutException` to `ApiTimeoutException` and returns HTTP 504.

### 3.5. onErrorComplete Can Mask Failures

~~~java
Flux<AuditEvent> events = auditRepository.read()
        .onErrorComplete();
~~~

If audit data is critical, turning errors into completion hides data loss. Only use it for **optional** operations with metrics and an explicit “best-effort” contract.

### 3.6. onErrorResume After Timeout

~~~java
Mono<Item> result = remote.fetch(id)
        .timeout(Duration.ofMillis(500))
        .onErrorResume(TimeoutException.class,
                ex -> cache.find(id));
~~~

Here the `timeout` operator can emit `TimeoutException` downstream and cancel upstream. If the cache fallback returns a result, downstream sees success. Crucial rule: **never serve stale data when the API contract demands strict consistency**.

## 4. Cancellation and Hooks in Reactor

### 4.1. doOnCancel vs. doFinally

~~~java
Flux<Long> source = Flux.interval(Duration.ofSeconds(1))
        .doOnCancel(() -> metrics.incrementCancelled())
        .doFinally(signal -> metrics.incrementFinished(signal));
~~~

The snippet uses a custom `metrics` variable. `doOnCancel` runs only on cancellation; `doFinally` covers cancel, complete, and error.

Understand **operator placement**. Placing `doFinally` **before** `timeout` can observe `CANCEL` when timeout cancels upstream; placing it **after** `timeout` can observe `ON_ERROR` when downstream receives `TimeoutException`.

~~~java
Mono<String> result = remote()
        .doFinally(signal -> log.info("upstream={}", signal))
        .timeout(Duration.ofSeconds(2))
        .doFinally(signal -> log.info("downstream={}", signal));
~~~

When `remote()` has not emitted before timeout triggers, typically:

~~~text
upstream=CANCEL
downstream=ON_ERROR
~~~

Exact log ordering may vary from the illustration due to propagation and scheduling; verify with `StepVerifier`. This distinction matters when recording metrics so you do not double-count `CANCEL` + `ERROR` as two failed HTTP requests.

### 4.2. take(n) Proactively Cancels the Source

~~~java
Flux<Integer> firstTwo = Flux.range(1, 1_000_000)
        .doFinally(signal -> log.info("source={}", signal))
        .take(2);
~~~

Once downstream receives two elements and completes, `take(2)` can cancel the upstream source (unless the source already terminated). Source-side `doFinally` may thus see `CANCEL`, while subscriber-side sees `ON_COMPLETE`. This is valid behavior, not a data error.

### 4.3. Cancellation from Client Disconnect

In WebFlux, when the connection/response consumer cancels, the response subscription typically receives cancel. However:

- There is no guarantee a user closing a tab is detected **instantaneously** by the server across every topology.
- Data may be buffered by sockets, Netty, or reverse proxies.
- If the publisher is a shared hot source, cancelling one subscription does not automatically shut down the global source.
- If the source calls a blocking library, cancel might not halt the operation immediately.

Therefore, design cleanup around the **subscription lifecycle** and protect per-client resource scopes rather than relying solely on “broken pipe” exceptions.

### 4.4. Do Not Call subscribe() Arbitrarily Inside a Controller

Wrong ownership:

~~~java
@GetMapping("/start")
Mono<String> start() {
    remoteJob().subscribe(value -> log.info("job={}", value));
    return Mono.just("started");
}
~~~

With this pattern, the subscription is created **outside the response lifecycle**; client cancellation does not naturally propagate to that job and errors can be lost. If it is genuinely a long-lived task independent of the request, use a properly managed service/job queue. If the result belongs to the request, **return the publisher** for WebFlux to subscribe/cancel.

Likewise, avoid `block()` or `Thread.sleep()` on Netty event loops; doing so degrades capacity to serve concurrent requests. For legacy blocking calls, use `Schedulers.boundedElastic()` in a controlled way, preferring native reactive drivers.

## 5. Timeouts: Reactor Operator, Network, Server, and Gateway

### 5.1. Reactor Timeout

~~~java
Mono<String> response = remoteCall()
        .timeout(Duration.ofSeconds(2));
~~~

If the source fails to emit the expected signal before the deadline, Reactor emits `TimeoutException`, cancels the upstream subscription, and terminates downstream with an error.

Fallback variant:

~~~java
Mono<String> response = remoteCall()
        .timeout(Duration.ofSeconds(2), Mono.just("cached"));
~~~

Downstream receives the fallback on timeout. However, the external remote operation might still be running even though the local Publisher received cancel; cancellation cannot “undo” an already-executed HTTP/SQL write.

### 5.2. Timeout vs. Deadline

If an API request flows A → B → C, a separate 2-second timeout at each hop can add up beyond the client's SLA. For end-to-end deadlines, propagate remaining budget, cancel downstream upon expiry, and measure from request start. Reactor `timeout` is an operator-level policy, not a distributed deadline protocol.

### 5.3. Different Types of Timeouts

| Timeout | Layer | When It Applies |
| --- | --- | --- |
| Reactor `timeout(Duration)` | Publisher chain | Protects logic and signal wait duration |
| HTTP client response timeout | Reactor Netty `HttpClient`/`WebClient` | Bounds response read time at transport |
| Connect timeout | TCP/socket client | Establishing TCP connection takes too long |
| Read/write timeout | Network handlers | Socket makes no I/O progress |
| Server idle/request timeout | Netty/server config | Caps idle connections/requests per setup |
| Gateway/ingress timeout | Nginx/Envoy/CDN | Proxy closes upstream/downstream |
| Caller/client deadline | Browser/mobile/other service | Caller stops waiting and may cancel |

A request may be cancelled by the client **before** the server's timeout fires. Or a gateway may time out before Reactor's timeout, leaving the client with a gateway-generated 504. Observe both sides instead of assuming every `TimeoutException` has a single cause.

### 5.4. WebClient Timeouts

A Reactor Netty fragment:

~~~java
HttpClient nettyClient = HttpClient.create()
        .responseTimeout(Duration.ofSeconds(3));

WebClient client = WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(nettyClient))
        .build();
~~~

Imports: `reactor.netty.http.client.HttpClient`, `org.springframework.http.client.reactive.ReactorClientHttpConnector`, `org.springframework.web.reactive.function.client.WebClient`. This is a configuration fragment, not a complete application. Connect timeout requires separate channel option setup if needed; do not confuse `responseTimeout` with the total pipeline deadline including decoding/business processing.

### 5.5. Timeouts and Cleanup

When timeout cancels the upstream Publisher, resource cleanup depends on whether the source supports cancellation. For an asynchronous resource, use `usingWhen(..., asyncCancel)` to release on cancellation. Do not use `doOnError` alone, because upstream may see `CANCEL` rather than `ON_ERROR`.

## 6. Releasing Resources with using and usingWhen

### 6.1. Flux.using — Synchronous Resources

Example creating a `Lease` that increments an active count on subscribe and decrements on complete/error/cancel:

~~~java
Flux<String> events = Flux.using(
        () -> new Lease(),
        lease -> Flux.interval(Duration.ofSeconds(1))
                .map(n -> "tick-" + n),
        Lease::close
);
~~~

`Lease` must implement `close()`; this is a fragment. The resource supplier runs **on subscribe**, not at assembly time. `Flux.using` handles cleanup throughout the publisher's lifecycle.

Compare with creating the lease outside the publisher:

~~~java
Lease lease = new Lease();
Flux<String> events = Flux.interval(Duration.ofSeconds(1))
        .doFinally(signal -> lease.close());
~~~

The second form creates the resource **as soon as the method is called**. If the publisher is never subscribed to, the lease can leak. `using` scopes the resource accurately to the subscription.

### 6.2. Mono.using

For resources with synchronous closing:

~~~java
Mono<String> result = Mono.using(
        () -> new LocalHandle(),
        handle -> Mono.fromSupplier(handle::read),
        LocalHandle::close
);
~~~

This fragment assumes `LocalHandle` has `read()` and `close()` that do not throw checked exceptions or handle them properly. If `read()` is blocking I/O, `Mono.fromSupplier` itself **does not make it non-blocking**. Offload appropriately or use a reactive API.

### 6.3. usingWhen — Asynchronous Resources

For R2DBC transactions, reactive sessions, or resources with a close publisher:

~~~java
Mono<Result> result = Mono.usingWhen(
        connectionFactory.create(),
        connection -> executeQuery(connection),
        connection -> connection.close(),
        (connection, error) -> connection.close(),
        connection -> connection.close()
);
~~~

This is a general fragment where `executeQuery(connection)` returns an appropriate publisher and `Result` is application-defined. The cleanup functions are:

1. **asyncComplete:** releases when the source completes successfully.
2. **asyncError:** releases when the source errors (receives the `Throwable`).
3. **asyncCancel:** releases when the subscription is cancelled.

If resource closing itself can fail, define how cleanup errors are handled. Never treat close errors as “unimportant” if they can exhaust a pool; define logging/metrics and recovery policies without exposing secrets.

### 6.4. Differences Between doFinally and usingWhen

- `doFinally`: synchronous side-effect callback, useful for logs/metrics/small release actions.
- `using`: resource lifecycle with synchronous cleanup, scoped per subscriber.
- `usingWhen`: **reactive/asynchronous** cleanup that awaits a closing Publisher and branches on complete/error/cancel.
- `doOnCancel`: supplementary cancel hook, insufficient for releasing resources on success/error.

If cleanup is an asynchronous network operation, `doFinally(() -> resource.close().subscribe())` is a common **anti-pattern**: you create a fire-and-forget subscription where close errors detach from the lifecycle and become hard to test. Use `usingWhen` or a reactive transactional API.

### 6.5. Cleanup Exactly Once

Within a pipeline, `using`/`usingWhen` manages the resource per subscription. However, if a resource is also referenced by an external callback, scheduler, or shutdown hook, they could race to call close. Use a state guard (e.g., `AtomicBoolean.compareAndSet(false, true)`) if close is not idempotent.

Never double-close by combining `Flux.using(..., Lease::close)` with an unguarded `doFinally(sig -> lease.close())`, and never put a global singleton resource inside `using` to close per subscriber if that resource is shared application-wide.

## 7. Backpressure, Discards, and Pooled DataBuffer

### 7.1. Backpressure Is Part of the Lifecycle

Reactive Streams lets subscribers request an element count `request(n)`. If a client is slow or a subscriber cancels, prefetched/buffered elements may be discarded. Operators like `flatMap`, `publishOn`, `buffer`, and `onBackpressureBuffer` have distinct semantics and storage costs.

A `Flux.interval` whose downstream does not request fast enough can emit an overflow error rather than waiting indefinitely. Do not assume `interval` is backpressure-safe under arbitrary load.

Choose an explicit policy:

- Bounded queues with per-client caps.
- `onBackpressureLatest()` or sampling/throttling when only the “latest value” is needed.
- `limitRate`/prefetch tuning where appropriate.
- Durable storage/replay if every event must be preserved.
- Cancellation propagation all the way to the real producer, not just response encoding.

### 7.2. DataBuffer May Hold Pooled Native Memory

In Spring WebFlux, the `DataBuffer` abstraction has implementations backed by pooled/reference-counted buffers such as Netty `ByteBuf`. When application code retains, slices, drops, or passes buffers outside the codec contract, you may need to **release** buffers you own.

Example:

~~~java
DataBufferUtils.release(buffer);
~~~

Never apply this blindly when the framework still owns the buffer and will release it; double-release causes errors. Release only when lifecycle ownership is clear.

### 7.3. doOnDiscard for Buffered Elements

Some operators discard elements on cancel/filter/overflow. If your application processes pooled `DataBuffer` instances it owns:

~~~java
Flux<DataBuffer> data = source
        .filter(this::shouldKeep)
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
~~~

This is a fragment: `source` is `Flux<DataBuffer>` and `shouldKeep` is application-defined; correctness depends on operator placement and ownership. `doOnDiscard` only helps on operators supporting discard hooks and **does not cover every memory leak path**. Read each operator's Javadoc and plan releases across retry, split, cancel, and buffer/error paths.

### 7.4. Do Not Manually Decode DataBuffers by Holding Raw ByteBufs Unboundedly

Where possible, use `bodyToMono(Dto.class)`, `bodyToFlux(Dto.class)`, codecs, or `DataBufferUtils.write/read` with clear lifecycles. Manipulate raw `DataBuffer` directly only when binary/protocol streaming truly requires it and memory/resource cleanup tests are in place.

An `OutOfMemoryError: Direct buffer memory` can stem from buffer leaks, inadequate backpressure, oversized request bodies, or unbounded network pipelines. Never guess a single root cause without metrics/profiling.

## 8. WebClient: Consuming and Releasing HTTP Response Bodies

### 8.1. retrieve Is Usually the Best Starting Point

~~~java
Mono<ProductDto> product = webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .bodyToMono(ProductDto.class);
~~~

By default, `retrieve()` turns 4xx/5xx responses into `WebClientResponseException` per WebClient semantics (unless customized). With DTO decoding, the framework manages most of the response body lifecycle.

Never call `block()` on a WebFlux event loop; return `Mono<ProductDto>` or compose further.

### 8.2. exchangeToMono / exchangeToFlux

When status control depends on the response:

~~~java
Mono<ProductDto> product = webClient.get()
        .uri("/products/{id}", id)
        .exchangeToMono(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.bodyToMono(ProductDto.class);
            }
            if (response.statusCode().value() == 404) {
                return Mono.empty();
            }
            return response.createError();
        });
~~~

Per Spring Framework 6.2 documentation, once the Publisher returned by `exchangeToMono`/`exchangeToFlux` completes, if the response body **has not been consumed**, the framework inspects/releases it to prevent leaks. In the fragment above, status 404 intentionally ignores the body; `exchangeToMono` handles releasing the remainder per contract.

**Never decode the body downstream after the `exchangeToMono` callback finishes**: the body may already have been released. If you need error body content, decode it **inside the response function**.

### 8.3. Why Was the Old exchange() Dangerous?

The low-level `exchange()` API was deprecated because code easily forgot to consume/release the body on some branch, causing connection/memory leaks. Avoid writing:

~~~java
// Anti-pattern with legacy exchange() API:
return webClient.get().uri("/resource")
        .exchange()
        .flatMap(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return Mono.just("ok"); // Body left unconsumed!
            }
            return Mono.just("error");
        });
~~~

Prefer `retrieve()` or `exchangeToMono`/`exchangeToFlux`. If working manually with `ClientResponse` at a lower level, understand `bodyToMono`/`bodyToFlux`, `releaseBody()`, and decoding paths.

### 8.4. Timeouts and WebClient Errors

Different error sources:

| Error | What to Check |
| --- | --- |
| DNS/connect failure | Host, proxy, connect timeout, network |
| HTTP 404/429/500/503 | `WebClientResponseException`/status policy |
| Reactor timeout | Timeout operator and cancellation propagation |
| Response decode error | Content-Type/body shape/`max-in-memory-size` |
| Client cancel | Downstream no longer needs response; not necessarily `onError` |
| Pool exhaustion | Connection leaks, pool size, slow upstream, unconsumed bodies |
| OutOfMemoryError/DirectMemory | Pooled buffer ownership, unbounded buffering |

Do not collapse everything into an unclassified HTTP 500 "unknown". And never expose raw upstream URLs with query tokens or response bodies containing secrets in public error payloads.

## 9. HTTP Exception Handling in WebFlux

### 9.1. Controller-Level and Global Advice

WebFlux supports `@ExceptionHandler` on controllers or `@RestControllerAdvice`. For HTTP APIs, use `ProblemDetail`/`ErrorResponse` to standardize errors.

Example fragment:

~~~java
@RestControllerAdvice
class ApiErrorHandler {
    @ExceptionHandler(UpstreamTimeoutException.class)
    ResponseEntity<ProblemDetail> timeout(
            UpstreamTimeoutException ex) {
        ProblemDetail body = ProblemDetail.forStatusAndDetail(
                HttpStatus.GATEWAY_TIMEOUT,
                "Upstream service did not respond in time");
        body.setTitle("Gateway timeout");
        body.setProperty("code", "UPSTREAM_TIMEOUT");
        return ResponseEntity.status(HttpStatus.GATEWAY_TIMEOUT)
                .body(body);
    }
}
~~~

This is a fragment; exception classes/imports and application configuration must exist. `ProblemDetail` provides HTTP status/title/detail/type/instance; extension properties can be serialized into JSON via Spring/Jackson support.

### 9.2. WebExceptionHandler Is a Lower-Level Layer

`WebExceptionHandler` sits in the WebFlux processing chain, handling exceptions from `WebFilter`/target `WebHandler`. For regular controller APIs, prefer `@RestControllerAdvice` and WebFlux default exception handling before writing custom low-level handlers.

A custom `WebExceptionHandler` introduces ordering subtleties and risks when a response is already committed. Once committed, you cannot reset status/headers as if no bytes were sent.

### 9.3. 400 / 404 / 409 / 429 / 503 / 504 / 500

Do not map every reactive error to 500. A guideline:

| Condition | Typical Appropriate HTTP Status | Notes |
| --- | --- | --- |
| Invalid request input | 400 | Validation, unsupported/missing parameters |
| Resource does not exist | 404 | Do not reveal existence of forbidden resources |
| Business conflict/version mismatch | 409 or 412 | Depends on contract |
| Rate limited | 429 | May include `Retry-After` if appropriate |
| Service unavailable/overloaded | 503 | May include retry policy |
| Gateway/upstream timeout | 504 | When the app acts as a gateway to upstream |
| Unclassified internal bug | 500 | Generic message, log internal correlation ID |
| Subscriber cancel/client disconnected | **Not a self-emitted HTTP status** | Do not pretend to return 499/500 after client left |

An app calling a remote dependency that times out does not universally have to return 504; that is an API contract choice. Distinguish upstream timeout from **client** giving up. Note that `499` in Nginx logs is a proxy-specific code, not a standard HTTP status for WebFlux to “return after cancel”.

### 9.4. Never Expose Sensitive Information

Error payloads must **never** include:

- Stack traces, internal class/method names.
- Database URLs, SQL, credentials, tokens, cookies.
- Raw upstream error bodies that may hold PII or secrets.
- File system paths, internal hostnames, provider access keys.
- Arbitrary exception messages containing unsanitized user input.

Use stable error codes and server-side request/trace IDs in logs. If clients need a correlation ID, expose a server-generated header and allow it via CORS if cross-origin. Never trust unvalidated incoming correlation IDs to build unbounded log fields.

### 9.5. When the HTTP Response Is Already Committed

In SSE streaming or chunked response bodies:

~~~text
HTTP/1.1 200 OK
Content-Type: text/event-stream

event: update
data: {"progress":20}
~~~

if the publisher errors after headers/body have started, the application **cannot change 200 to 500 JSON** on that HTTP response. Error handlers can change status only before the response commits. Once streaming has begun:

- If the channel is still usable, you can map business failures to an **in-band SSE application error event** within the stream protocol.
- If transport/write already failed, simply stop/cancel/release resources and log/record metrics; never attempt to write a second HTTP response.
- A streaming publisher error does not turn into a JSON `ProblemDetail` after commit; the connection may close and the client handles reconnect/error logic.

## 10. Proper Retries and Subscription Cancellation

### 10.1. retryWhen Only for Transient Errors

~~~java
return webClient.get()
        .uri("/catalog/{id}", id)
        .retrieve()
        .bodyToMono(CatalogDto.class)
        .retryWhen(Retry.backoff(2, Duration.ofMillis(100))
                .filter(this::isTransientFailure));
~~~

Fragment with an application-defined `isTransientFailure`. `retryWhen` **re-subscribes** to the source. If the source has side effects like a payment POST, retrying can create duplicate transactions without idempotency keys/deduplication.

Do not retry:

- 400 validation errors.
- 401/403 without a deliberate token-refresh flow.
- 404 when the resource genuinely does not exist.
- Unrecoverable business conflicts.
- Non-idempotent commands lacking idempotency safeguards.

You may retry certain network resets/429/503 responses after accounting for rate limits, jitter, attempt caps, and retry budgets. Backoff prevents retry storms when upstream is overloaded.

### 10.2. Retry and Timeout Ordering

These two forms **differ**:

~~~java
remoteCall()
    .timeout(Duration.ofSeconds(1))
    .retryWhen(Retry.max(2));
~~~

Each subscription attempt gets a 1-second timeout. Whereas:

~~~java
remoteCall()
    .retryWhen(Retry.max(2))
    .timeout(Duration.ofSeconds(1));
~~~

A single 1-second deadline wraps the entire retry sequence. Design **per-attempt timeouts and overall budgets** intentionally rather than swapping operator order for aesthetics.

### 10.3. Retry Does Not Resume the Old Source

If a `Flux` emitted 5 records and then errored, a retry subscription may re-emit those 5 records. Consumers must support idempotency/deduplication or use checkpoints/cursors to resume. This is especially hazardous for transactional writes or event-stream processing.

### 10.4. Cancelling During Retry/Backoff

When a client cancels while waiting in backoff, the Reactor-managed subscription stops further emissions and retry scheduling per operator semantics. Still, never assume external side effects were rolled back. For service-initiated tasks, tie ownership/cancellation directly to the publisher lifecycle.

## 11. SSE and Client Disconnects in WebFlux

A WebFlux endpoint can return:

~~~java
@GetMapping(path = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<ServerSentEvent<String>> events() {
    return Flux.interval(Duration.ofSeconds(1))
            .map(n -> ServerSentEvent.<String>builder()
                    .id(Long.toString(n))
                    .event("tick")
                    .data("tick-" + n)
                    .build())
            .doFinally(signal -> log.info(
                    "sse_terminated signal={}", signal));
}
~~~

This is a fragment assuming `log` and necessary imports. `Flux.interval` emits on a scheduler; when downstream cancels, the subscription stops the timer. If a browser closes SSE, WebFlux's network handler usually propagates cancel, though detection timing depends on the network and proxies.

### 11.1. SSE Heartbeats

An SSE comment can serve as a heartbeat:

~~~text
: keepalive

~~~

In Spring WebFlux, the builder:

~~~java
ServerSentEvent.<String>builder()
        .comment("keepalive")
        .build();
~~~

Comment-only SSE frames normally do not fire application message events in browsers, yet produce bytes so proxies do not treat the connection as idle. If a gateway buffers responses, heartbeats may not reach clients promptly. Test through real proxies with buffering disabled if required.

### 11.2. Last-Event-ID and Replay

Browser `EventSource` reconnects automatically and can send `Last-Event-ID` when the stream uses event IDs. To resume without dropping events, the server must store durable event IDs/retention and replay from a cursor. If a stream only generates in-memory `Flux.interval`, **never promise exactly-once delivery**. Reconnects can create fresh subscriptions and miss or duplicate events depending on design.

### 11.3. Hot Publishers Shared Across Multiple Clients

Suppose an application-wide `Sinks.Many<T>` serves as producer. When client A cancels, never shut down the Sink and cut off client B. Clean up **per-client subscriptions** or per-client resources; the shared producer has an independent application lifecycle. On hot sources, you must distinguish subscriber cancellation from producer shutdown.

## 12. Runnable Project: Spring Boot 3.5, Java 17

The demo focuses on:

- `GET /api/items/ok`: returns normal JSON.
- `GET /api/items/slow`: slow Mono with 150ms Reactor timeout, mapped to a custom exception returning HTTP 504 `ProblemDetail`.
- `GET /api/items/missing`: returns HTTP 404 via `ResponseStatusException`.
- `GET /api/items/boom`: internal error mapped by advice to generic 500 without leaking the exception message.
- `GET /api/events`: SSE streaming using `Flux.using` with a per-subscription lease and `doFinally`, cleaning up across complete/error/cancel.
- `GET /api/active`: demo endpoint counting active SSE subscriptions.
- Tests use `WebTestClient` and `StepVerifier` to verify HTTP error bodies, timeouts, cancel/cleanup, and virtual time.

### 12.1. Structure

~~~text
webflux-lifecycle-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/demo/WebFluxLifecycleApplication.java
    └── test/
        └── java/demo/WebFluxLifecycleTest.java
~~~

### 12.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>webflux-lifecycle-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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

**Do not add `spring-boot-starter-web` to the demo.** If both MVC and WebFlux starters exist, Spring Boot typically picks the MVC application type by default, defeating the reactive-stack tests.

### 12.3. WebFluxLifecycleApplication.java

Save all of the following Java code into `src/main/java/demo/WebFluxLifecycleApplication.java`. There is only one public top-level class; the remaining classes/records are package-private. The demo calls no external internet services and runs standalone with Maven dependencies.

~~~java
package demo;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class WebFluxLifecycleApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxLifecycleApplication.class, args);
    }
}

record Item(String id, String title) {
}

class ApiTimeoutException extends RuntimeException {
    ApiTimeoutException(Throwable cause) {
        super("The dependency timed out", cause);
    }
}

@Service
class ItemService {
    Mono<Item> find(String id) {
        return Mono.defer(() -> {
            if ("missing".equals(id)) {
                return Mono.error(new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Item not found"));
            }
            if ("boom".equals(id)) {
                return Mono.error(new IllegalStateException(
                        "internal database password=secret"));
            }

            Mono<Item> source = "slow".equals(id)
                    ? Mono.delay(Duration.ofSeconds(3))
                            .map(n -> new Item(id, "Late"))
                    : Mono.just(new Item(id, "Ready"));

            return source
                    .timeout(Duration.ofMillis(150))
                    .onErrorMap(TimeoutException.class,
                            ApiTimeoutException::new);
        });
    }
}

@Service
class EventService {
    private static final Logger LOG =
            LoggerFactory.getLogger(EventService.class);

    private final AtomicInteger active = new AtomicInteger();

    Flux<ServerSentEvent<String>> events() {
        return Flux.using(
                () -> new Lease(active),
                lease -> Flux.interval(Duration.ofMillis(100))
                        .map(n -> ServerSentEvent.<String>builder()
                                .id(Long.toString(n))
                                .event("tick")
                                .data("tick-" + n)
                                .build()),
                Lease::close
        ).doFinally(signal ->
                LOG.info("sse_terminated reason={}", signal));
    }

    int activeConnections() {
        return active.get();
    }

    private static final class Lease implements AutoCloseable {
        private final AtomicInteger active;
        private final AtomicBoolean closed = new AtomicBoolean();

        Lease(AtomicInteger active) {
            this.active = active;
            active.incrementAndGet();
        }

        @Override
        public void close() {
            if (closed.compareAndSet(false, true)) {
                active.decrementAndGet();
            }
        }
    }
}

@RestController
class ApiController {
    private final ItemService items;
    private final EventService events;

    ApiController(ItemService items, EventService events) {
        this.items = items;
        this.events = events;
    }

    @GetMapping("/api/items/{id}")
    Mono<Item> item(@PathVariable String id) {
        return items.find(id);
    }

    @GetMapping(path = "/api/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    Flux<ServerSentEvent<String>> stream() {
        return events.events();
    }

    @GetMapping("/api/active")
    Mono<Integer> active() {
        return Mono.fromSupplier(events::activeConnections);
    }
}

@RestControllerAdvice
class ApiErrors {
    @ExceptionHandler(ApiTimeoutException.class)
    ResponseEntity<ProblemDetail> timeout(ApiTimeoutException ex) {
        ProblemDetail body = ProblemDetail.forStatusAndDetail(
                HttpStatus.GATEWAY_TIMEOUT,
                "Upstream did not respond in time");
        body.setTitle("Gateway timeout");
        body.setProperty("code", "UPSTREAM_TIMEOUT");
        return ResponseEntity.status(HttpStatus.GATEWAY_TIMEOUT)
                .body(body);
    }

    @ExceptionHandler(IllegalStateException.class)
    ResponseEntity<ProblemDetail> internal(IllegalStateException ex) {
        // Never send ex.getMessage() to the user.
        ProblemDetail body = ProblemDetail.forStatusAndDetail(
                HttpStatus.INTERNAL_SERVER_ERROR,
                "An unexpected error occurred");
        body.setTitle("Internal server error");
        body.setProperty("code", "INTERNAL_ERROR");
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(body);
    }
}
~~~

### 12.4. Key Design Details

1. `Mono.defer` constructs the publisher per subscription rather than triggering work at assembly time.
2. `slow` uses a source emitting after 3 seconds, yet `timeout(150ms)` emits an error; `onErrorMap` translates it to a clear business exception.
3. HTTP 504 is the **policy for this demo scenario where the API acts as an upstream gateway**. Other applications might choose 503 or another appropriate status.
4. `boom` carries an internal message to demonstrate that advice returns a generic message without leaking secrets.
5. `events()` creates a `Lease` via `Flux.using` **on subscribe**; cleanup runs on downstream complete/error/cancel.
6. `AtomicBoolean` in `Lease` guards against double-close if ownership expands or external callbacks also invoke close.
7. `Flux.interval` is an infinite source; browser disconnect/cancel stops the per-subscription timer per normal Reactor semantics.
8. `doFinally` only logs the reason; real cleanup lives in `using` to guarantee resource ownership.
9. `activeConnections` is not a security-grade metric; demo endpoints must be secured or removed in production.
10. The demo has no auth/CSRF, no real upstream integration, and no streaming buffers; focus is on teaching proper lifecycle first.

### 12.5. Running

~~~bash
mvn spring-boot:run
~~~

In another terminal:

~~~bash
curl -i http://localhost:8080/api/items/ok
~~~

Equivalent response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":"ok","title":"Ready"}
~~~

Test timeout:

~~~bash
curl -i http://localhost:8080/api/items/slow
~~~

Status 504 and equivalent `ProblemDetail` JSON:

~~~json
{
  "type":"about:blank",
  "title":"Gateway timeout",
  "status":504,
  "detail":"Upstream did not respond in time",
  "code":"UPSTREAM_TIMEOUT"
}
~~~

Actual responses may add `instance` and extra headers; JSON field order is not fixed.

Test internal error:

~~~bash
curl -i http://localhost:8080/api/items/boom
~~~

Expected 500 with a generic body omitting `password=secret`. Trying `missing` returns HTTP 404.

### 12.6. Opening SSE and Cancelling Client-Side

~~~bash
curl -N -i http://localhost:8080/api/events
~~~

Example stream start:

~~~text
id:0
event:tick
data:tick-0

id:1
event:tick
data:tick-1

~~~

Actual SSE formatters may vary field order. In another terminal:

~~~bash
curl -s http://localhost:8080/api/active
~~~

With one active subscription, JSON can be:

~~~json
1
~~~

After pressing Ctrl+C in curl, cancellation can propagate back to the WebFlux Publisher and `Flux.using` closes the lease; active returns to 0 once the server **observes** connection close/cancellation. Exact timing is not guaranteed due to TCP/proxy buffering.

## 13. Testing: WebTestClient and StepVerifier

Save `src/test/java/demo/WebFluxLifecycleTest.java`:

~~~java
package demo;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@WebFluxTest(controllers = ApiController.class)
@Import({ItemService.class, EventService.class, ApiErrors.class})
class WebFluxLifecycleTest {
    @Autowired
    WebTestClient http;

    @Autowired
    EventService events;

    @Test
    void normalItemIs200() {
        http.get().uri("/api/items/ok").exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo("ok")
            .jsonPath("$.title").isEqualTo("Ready");
    }

    @Test
    void missingItemIs404() {
        http.get().uri("/api/items/missing").exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void slowItemIsMappedTo504WithSafeBody() {
        http.get().uri("/api/items/slow").exchange()
            .expectStatus().isEqualTo(504)
            .expectBody()
            .jsonPath("$.code").isEqualTo("UPSTREAM_TIMEOUT")
            .jsonPath("$.detail").isEqualTo(
                    "Upstream did not respond in time");
    }

    @Test
    void internalErrorDoesNotExposeSecret() {
        http.get().uri("/api/items/boom").exchange()
            .expectStatus().is5xxServerError()
            .expectBody()
            .jsonPath("$.code").isEqualTo("INTERNAL_ERROR")
            .jsonPath("$.detail").isEqualTo(
                    "An unexpected error occurred")
            .jsonPath("$.detail").value(value ->
                    assertTrue(!String.valueOf(value)
                            .contains("password=secret")));
    }

    @Test
    void takeOneCancelsUpstreamAndCleansLease() {
        int before = events.activeConnections();

        StepVerifier.create(events.events().take(1))
            .expectNextMatches(event ->
                    "tick".equals(event.event())
                    && "tick-0".equals(event.data()))
            .verifyComplete();

        assertEquals(before, events.activeConnections());
    }

    @Test
    void timeoutCancelsUpstreamSource() {
        AtomicBoolean cancelled = new AtomicBoolean();

        StepVerifier.withVirtualTime(() ->
                Mono.<String>never()
                    .doOnCancel(() -> cancelled.set(true))
                    .timeout(Duration.ofSeconds(2)))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(2))
            .expectError(TimeoutException.class)
            .verify();

        assertTrue(cancelled.get());
    }

    @Test
    void onErrorResumeProvidesExplicitFallback() {
        StepVerifier.create(
                Mono.<String>error(
                        new IllegalStateException("temporary"))
                    .onErrorResume(IllegalStateException.class,
                            e -> Mono.just("fallback")))
            .expectNext("fallback")
            .verifyComplete();
    }
}
~~~

Run:

~~~bash
mvn test
~~~

**Meaning of each test group:**

- `WebTestClient` checks HTTP response statuses/bodies of the WebFlux controller and advice.
- `StepVerifier` verifies cancellation/lease cleanup when downstream calls `take(1)`, without relying on fake TCP sockets.
- `StepVerifier` virtual time tests timeout/cancellation without waiting two real seconds.
- The `onErrorResume` test proves the fallback is a **replacement publisher**.
- Real client-disconnect tests must run against embedded Netty/staging and close the socket while the server is writing; `@WebFluxTest` slice tests do not replace network/proxy testing.

**Limitations:** Cleanup tests rely on `Flux.using` implementation details. If refactored to a shared/hot publisher, ownership tests must change. The real-time 150ms test depends on the environment's scheduler; you can raise test-specific timeouts on very slow CI without removing error/cancel distinctions.

## 14. Testing Asynchronous Resources and Releases

### 14.1. Test Resource Cleanup Across All Three Paths

With `usingWhen`, design tests for:

~~~text
Case A: source emits value + completes
  -> asyncComplete runs
Case B: source emits error
  -> asyncError runs
Case C: downstream cancels subscription
  -> asyncCancel runs
~~~

Use counters or a mocked reactive connection with `StepVerifier`/`PublisherProbe`. If `usingWhen`'s cleanup Publisher itself errors, verify whether the primary error is replaced/suppressed per Reactor API and log/meter accurately.

### 14.2. Do Not Use doFinally to Fire-and-Forget Subscribe to Close

Wrong:

~~~java
.doFinally(signal -> connection.close().subscribe())
~~~

If `close()` returns `Mono<Void>`, this creates an unowned subscription whose close errors are hard to handle and may go untested. Use `usingWhen` instead so the close Publisher is awaited/observed by the framework per contract.

### 14.3. Verifying DataBuffer Release

When code owns pooled buffers, tests should cover:

- Normal request completion, all `DataBuffer` instances consumed/released.
- Mid-stream cancellation.
- Downstream codec errors.
- Filter/drop/skip/prefetch discards.
- Concurrent subscribers (if the source is shared).
- Bounded memory under slow readers.

Avoid writing unit tests assuming “releasing twice is harmless”. Reference-counted buffers throw errors on double-release or access-after-release. Never reuse a `DataBuffer` already released downstream.

## 15. Distinguishing WebFlux Cancellation from MVC Servlet Disconnects

| Topic | Spring WebFlux | Spring MVC |
| --- | --- | --- |
| Main model | Reactive Streams, non-blocking pipeline | Servlet stack; Servlet-based async processing |
| Streaming returns | `Flux<ServerSentEvent<T>>`, `Flux<DataBuffer>` | `SseEmitter`, `ResponseBodyEmitter`, `StreamingResponseBody` |
| Client cancel | Cancellation typically propagates into subscription | Container async error/write-failure callbacks |
| Cleanup | `using`/`usingWhen`/`doFinally`/`doOnCancel` | `onCompletion`/`onTimeout`/`onError` and resource owner |
| Timeouts | Reactor `timeout`, Netty/HTTP/gateway timeouts | Servlet async timeout, emitter timeout, proxy |
| Error status after commit | Cannot change already-sent HTTP status | Same HTTP limitation |
| Blocking I/O | Avoid on event loop | Can run on workers, still consumes threads |
| Backpressure | Reactive Streams request/cancel | Depends on async writes/callbacks and I/O behavior |

**Never use `SseEmitter.completeWithError` in WebFlux**, as that is a Servlet MVC API. Likewise, never treat WebFlux subscriber cancellation as identical to MVC's `onCompletion` callback.

## 16. Common Mistakes to Avoid

1. **Treating CANCEL as onError.** `onErrorResume` does not handle subscriber cancellation; place cleanup in `using`/`usingWhen`/`doFinally` per ownership.
2. **Using `doOnError` to close resources.** Misses normal completion and cancellation.
3. **Fire-and-forget `subscribe()` to close resources.** Detaches lifecycle and loses close errors.
4. **Creating resources outside `Mono.defer`/`using`.** Leaks if the Publisher is never subscribed to.
5. **Closing a shared producer when one client unsubscribes.** Breaks other active clients.
6. **Using `retryWhen` on non-idempotent payment POSTs.** Causes duplicate operations.
7. **Retrying all 4xx errors and logic bugs.** Worsens failures and amplifies load.
8. **Using `timeout` without understanding cancel propagation.** Background/external side effects may keep running.
9. **Retaining pooled `DataBuffer` after framework release.** Causes access-after-release/memory-safety bugs.
10. **Forgetting to release bodies from legacy WebClient `exchange()`.** Leaks connection pools and direct memory.
11. **Putting raw response bodies in error logs/public errors.** Leaks sensitive data.
12. **Catching `Throwable` with unconditional `onErrorComplete`.** Hides bugs and causes silent data loss.
13. **Trying to change status/headers after stream commit.** Cannot emit a new 500 response.
14. **Calling `block()` or `Thread.sleep()` on the event loop.** Stalls the entire reactive server.
15. **Keeping unbounded queues for slow SSE clients.** Causes OOM on weak networks.
16. **Using `userId`/`requestId` as metric labels.** Causes metric cardinality explosion.
17. **Not capping concurrent connections and per-tenant subscriptions.** Exhausts resources.
18. **Assuming cancel rolls back remote side effects.** No guarantee exists.
19. **Assuming HTTP 499 is a standard server-emitted status.** It is a proxy-specific code.
20. **Checking only HTTP status without testing cleanup.** Easily leaks on timeout/cancel.
21. **Assuming successful send means client receipt.** Proxy/TCP buffers delay observation.
22. **Relying solely on MockWebServer/slice tests to verify socket disconnect semantics.** Run real integration tests for high-stakes paths.

## 17. Logging and Observability

Distinguish terminal signals clearly:

~~~text
request_completed   status=200 result=success
request_failed      status=504 errorCategory=UPSTREAM_TIMEOUT
stream_cancelled    endpoint=/api/events reason=client-or-downstream-cancel
stream_terminated   endpoint=/api/events signal=CANCEL lifetimeMs=...
resource_released   type=reactive-lease outcome=closed
~~~

These logs are **examples**; never conclude a client closed a tab solely from `SignalType.CANCEL`. A valid `take(1)` also cancels upstream.

Useful metrics:

- HTTP status and latency by route template.
- Upstream timeout/circuit-breaker rates.
- Active reactive subscriptions/SSE sessions.
- Cancellation counts by endpoint and bounded reason groups.
- Resource lease active/acquired/released counts and cleanup failures.
- Netty connection pool active/idle/pending acquires.
- `DataBuffer`/direct memory and allocator metrics.
- Retry attempts, fallback rates, and backpressure overflows.
- Event-loop saturation/blocked operations.
- Gateway client resets/read timeouts.

Never place tokens, cookies, raw bodies, stack traces, or PII into responses or high-cardinality metrics. Correlation/trace IDs help locate logs, not prove identity/authentication.

## 18. Production Checklist

- [ ] Complete, error, and cancel are classified separately in lifecycle and metrics.
- [ ] Errors map cleanly to domain types and appropriate HTTP statuses without leaking internals.
- [ ] `onErrorResume`/`onErrorComplete` are used only when fallback/suppression matches the contract.
- [ ] Retries are bounded with idempotency, jitter/backoff, and overall deadline budgets.
- [ ] Timeout operators are positioned properly relative to retry and recovery.
- [ ] Cancellation propagates to sources; external blocking side effects have dedicated cancellation or intentional policy.
- [ ] Synchronous resources use `using`/try-with-resources with clear ownership; async resources use `usingWhen` or reactive transaction APIs.
- [ ] Cleanup across complete/error/cancel is tested and never double-closes shared resources.
- [ ] WebClient response bodies are consumed/released, with no leak-prone legacy `exchange()` calls remaining.
- [ ] Pooled raw `DataBuffer` instances are released when app-owned, including on discard/cancel paths.
- [ ] Streams enforce bounded queues/backpressure/quotas, avoiding uncontrolled infinite publishers.
- [ ] No attempts are made to send a new HTTP status/`ProblemDetail` after response commit.
- [ ] SSE defines reconnect/`Last-Event-ID`/replay contracts and is tested for proxy buffering/timeouts.
- [ ] No blocking JDBC/filesystem calls run on Reactor Netty event loops.
- [ ] `WebTestClient`, `StepVerifier`, and embedded-network integration tests cover timeouts/cancels/cleanup.
- [ ] Active resources/connection pools/cleanup failures are metered and alerted.
- [ ] TLS/CORS/authz/cookies/CSRF are designed explicitly, never treating cancellation/timeouts as security controls.

## 19. Practice Exercises

**Exercise 1 — Three Signals:** `Flux.range(1,10).take(1)` finishes after the first item. Which signal does upstream see? Which does downstream see? Why should an error metric not be incremented?

**Exercise 2 — doFinally:** Write `Mono.never().timeout(Duration.ofSeconds(2))` with `doFinally` before and after `timeout`. Use `StepVerifier` virtual time to record upstream `CANCEL` and downstream `ON_ERROR`.

**Exercise 3 — Error Mapping:** An API calls an upstream returning `TimeoutException`. Map it via `onErrorMap` to a domain exception and have advice return a 504 `ProblemDetail` with a stable code and no raw exception message.

**Exercise 4 — Cancellation:** A client closes an `EventSource` reading `Flux.interval`. Analyze how cancel propagates upstream, per-subscription cleanup, and why a shared hot producer must not be shut down.

**Exercise 5 — Resources:** Write `Flux.using` for an `AutoCloseable` resource. Test complete, error, and cancel with `StepVerifier`; assert `acquired == released`.

**Exercise 6 — Async Close:** A reactive DB session has `close()` returning `Mono<Void>`. Use `usingWhen` with `asyncComplete`, `asyncError`, and `asyncCancel` instead of `close().subscribe()` inside `doFinally`.

**Exercise 7 — WebClient:** Migrate legacy WebClient `.exchange()` to `exchangeToMono`, explaining 404 body release and error paths. If you need the error body, where must it be decoded?

**Exercise 8 — DataBuffer:** A `Flux<DataBuffer>` is filtered and discarded on cancel. Who owns the buffers, when are `DataBufferUtils.release`/`doOnDiscard` used, and why is double-release dangerous?

**Exercise 9 — Retry:** Design retries for an idempotent GET with backoff + jitter + deadline. Why is copying that exact policy to a payment POST dangerous?

**Exercise 10 — Streaming Commit:** SSE has emitted HTTP 200 and three events, then hits a business error. Why can't the status change to 500? Design an in-band app-error event if the stream is still usable.

**Exercise 11 — Timeout Layers:** A browser sees 504 after 30s even though the server's Reactor timeout is set to 60s. Which proxy/WebClient layers should be checked?

**Exercise 12 — Backpressure:** Producer emits 1,000 events/second; client reads 10 events/second. Choose bounded queue/drop/coalesce or durable replay for progress data vs. financial transactions.

**Exercise 13 — Testing:** Write a `StepVerifier` test proving an `onErrorResume` fallback does not run when the source is cancelled, and use `PublisherProbe` or `AtomicBoolean` to verify cleanup.

**Exercise 14 — Blocking Source:** Wrap a legacy blocking SDK call in `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` and explain why cancellation does not guarantee the SDK call stops immediately.

## 20. Key Takeaways

- In Reactor, **complete, error, and cancel are distinct**; cancellation is a downstream-to-upstream signal, not an `onError`.
- `doFinally` observes `ON_COMPLETE`, `ON_ERROR`, and `CANCEL`; resource lifecycles should use `using`/`usingWhen`.
- `timeout` emits `TimeoutException` downstream and cancels the source on expiry, yet external operations may keep running.
- `onErrorResume` switches to a fallback Publisher rather than resuming the original failed source at the error point.
- `retryWhen` re-subscribes and can replay side effects/records; enforce idempotency and deadlines.
- WebClient `retrieve`/`exchangeToMono`/`exchangeToFlux` are safer than legacy `exchange()` when not explicitly managing body release.
- Pooled `DataBuffer` instances require **clear ownership** to avoid leaks or double-release.
- Once a response is committed, stream errors cannot become a new HTTP 500 JSON response; use in-band events when possible or cancel/cleanup.
- Cancelling one subscription does not shut down shared producers or roll back remote side effects.
- Tests must verify **both data/statuses and cleanup on cancel/error/timeout**.

## 21. Official Documentation

- [Spring Framework 6.2 — WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux.html): reactive stack, backpressure, and overview.
- [Spring Framework 6.2 — WebFlux Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html): `ProblemDetail`/`ErrorResponse` and controller advice.
- [Spring Framework 6.2 — WebFlux Exceptions](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-exceptions.html): `@ExceptionHandler`.
- [Spring Framework 6.2 — WebClient exchange](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-exchange.html): `exchangeToMono`/`exchangeToFlux`, response body release.
- [Spring Framework 6.2 — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/6.2/core/databuffer-codec.html): pooled `DataBuffer` lifecycle and release.
- [Project Reactor — Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): `onErrorResume`, `onErrorMap`, `retry`, `doFinally`, `using`.
- [Project Reactor — Dealing with Objects that Need Cleanup](https://projectreactor.io/docs/core/release/reference/advancedFeatures/cleanup.html): reference counting, discard, cleanup.
- [Reactor Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): `using`, `usingWhen`, `doFinally`, `timeout`, `doOnCancel`.
- [Reactor StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): virtual time, cancellation/termination tests.
- [Reactive Streams 1.0.4 Specification](https://www.reactive-streams.org/reactive-streams-1.0.4-spec-javadoc/org/reactivestreams/Subscription.html): `request(n)`, cancel contract.
- [HTTP Semantics — RFC 9110](https://www.rfc-editor.org/rfc/rfc9110): status codes, committed HTTP response semantics.
