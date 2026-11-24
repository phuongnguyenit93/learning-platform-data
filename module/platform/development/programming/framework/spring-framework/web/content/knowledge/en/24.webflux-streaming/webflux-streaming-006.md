# Unsubscribing, Client Disconnects, and Resource Cleanup in Streaming WebFlux

## 1. Problem: Client Stops Reading While Server Keeps Streaming

A Spring WebFlux endpoint may return `Flux<ServerSentEvent<T>>` to push continuous events to a browser, or return `Flux<DataBuffer>` to transfer a large file. Unlike a one-shot JSON response, a stream can live a long time, carry many events/bytes, and hold **per-subscription resources**: timers, broker subscriptions, database cursors, upstream HTTP connections, file channels, or pooled buffers.

Example:

~~~java
@GetMapping(
        path = "/api/ticks",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> ticks() {
    return Flux.interval(Duration.ofSeconds(1))
            .map(i -> ServerSentEvent.<String>builder()
                    .event("tick")
                    .id(Long.toString(i))
                    .data("tick-" + i)
                    .build());
}
~~~

This is a **fragment** needing a Spring `@RestController` class with imports. A browser may use `EventSource`, then close the tab or call `eventSource.close()` after a few events. Once the client loses interest, the server should stop emitting data, cancel upstream subscriptions, and clean up resources. However, you must distinguish:

- **`cancel()`**: a signal in Reactive Streams/Project Reactor sent by downstream to cancel a subscription.
- **Client disconnect**: an event on the HTTP/transport socket that can lead to `cancel()` on the response publisher **when the adapter detects it**.
- **Resource cleanup**: releasing real objects (listeners/files/DB connections/pooled buffers), not merely incrementing a "cancelled" counter.
- **Business rollback**: undoing already-occurred side effects; it does not happen automatically just because a subscription was cancelled.

**Never claim that closing a client tab immediately delivers `SignalType.CANCEL` to the server, or that `cancel` guarantees stopping a blocking JDBC query.** When and how the transport detects disconnects depends on TCP/HTTP, read/write activity, proxies, server adapters, and timing.

### Objectives

After this lesson, you will be able to:
1. Distinguish the three signals `onComplete`, `onError`, and `cancel`, and their corresponding Reactor callbacks.
2. Understand the signal flow from browser `EventSource.close()` or HTTP stream cancellation through Netty/WebFlux/Publisher.
3. Use `doOnCancel`, `doFinally(SignalType)`, `Flux.using`, and `Flux.usingWhen` properly.
4. Guarantee cleanup across **every** outcome: success, error, timeout, and cancellation; avoid double-close and resource leaks.
5. Clarify **synchronous** cleanup vs. **asynchronous** cleanup, as well as the role of `doOnDiscard`/`DataBufferUtils.release`.
6. Examine cold/hot publishers, independent subscriptions, shared upstreams, and multi-client multiplexing.
7. Design SSE heartbeats/reconnects, timeouts, proxy buffering, and graceful shutdown.
8. Write a Java 17 + Spring Boot 3.3.5 WebFlux demo, and test with `StepVerifier.thenCancel()` and HTTP `WebTestClient`.
9. Recognize when a client disconnect should **not** roll back a job/transaction or abort a durable workflow.

This lesson is scoped to **Spring WebFlux/Project Reactor and HTTP streaming**—do not confuse these mechanisms with Servlet MVC `SseEmitter`/`DeferredResult`. Demo code is compatible with Spring Framework 6.1.x and Reactor 3.6.x managed by Spring Boot 3.3.5.

## 2. Reactive Streams: A Subscription Is a Lifecycle Contract

A `Publisher<T>` emits signals to a `Subscriber<T>` via a `Subscription`. In Reactor, `Flux<T>` and `Mono<T>` implement this contract.

~~~text
Publisher<T>  ---onSubscribe(subscription)--->  Subscriber<T>
                 <------ request(n) ----------
                 ------ onNext(item) -------->
                 ------ onNext(item) -------->
                 ------ onComplete() -------->  [terminal]

or             ------ onError(error) -------->  [terminal]

or             <---------- cancel() ----------  [downstream cancels]
~~~

The three endings differ:
- **Complete**: the source signals it finished emitting successfully; Subscriber receives `onComplete`.
- **Error**: the source terminates with an error; Subscriber receives `onError`.
- **Cancel**: downstream calls `Subscription.cancel()`; it is **not an onComplete/onError sent to the subscriber**, and it can occur before the source finishes.

The Reactive Streams contract concerns **stopping further requests/signals** after cancellation, subject to asynchrony and race conditions. It does not by itself define HTTP status codes, transaction semantics, file descriptor cleanup, or why the client closed TCP.

### 2.1. One Request Often Creates One Subscription, Yet Never Treat It as a Law for All Publishers

With an annotated WebFlux controller returning `Flux`, the framework normally subscribes to write the HTTP response. However, one logical request can trigger multiple publishers/inner subscriptions via `flatMap`, `retryWhen`, `switchIfEmpty`, `zip`, or HTTP codecs. Each subscription has its own lifecycle; for instance, `retryWhen` can **re-subscribe** to a cold source.

Therefore:
- **Per-subscription** resources must open and close per subscription attempt.
- `doOnSubscribe` does not inherently execute only once per HTTP request under every configuration.
- A cached/shared/hot multicast `Flux` may not cancel upstream immediately when **one** client leaves.

### 2.2. Demand Does Not Mean Keeping the Connection Alive

`request(n)` describes how many additional items downstream can accept (backpressure). `cancel()` terminates the subscription. Dropping demand to zero is not necessarily cancellation, and a temporarily slow subscriber does not mean the browser disconnected.

### 2.3. Usually Only One Terminal Signal Fires

A compliant source emits `onComplete` **or** `onError` once, never both. Cancellation is an asynchronous request and can race with a terminal signal already in flight.

This means cleanup must be **idempotent** and must never depend on assuming one specific callback always wins every race.

## 3. Signal Flow: From HTTP Client to Reactor Cancellation

### 3.1. SSE Client Actively Closing

~~~javascript
const source = new EventSource("/api/ticks");

source.addEventListener("tick", event => {
  console.log(event.data);
});

document.querySelector("#stop").addEventListener("click", () => {
  source.close();
});
~~~

This is browser JavaScript for a page containing a `#stop` button, not a full frontend project. `EventSource.close()` stops the EventSource connection and automatic reconnection; it does not call a separate HTTP "cancel" endpoint.

On the server:

~~~text
Browser EventSource
      |
      | HTTP GET /api/ticks
      v
Reactor Netty HTTP connection
      |
      v
WebFlux HandlerResultHandler / SSE writer
      |
      v
Flux<ServerSentEvent> subscription
      |
      +--- onNext(event 0) --> encoded bytes --> network
      +--- onNext(event 1) --> encoded bytes --> network
      |
      ... browser closes / network breaks ...
      |
      +--- adapter detects disconnect/write error
      |
      +--- may cancel response subscription
      |           |
      |           +--> doOnCancel
      |           +--> doFinally(CANCEL)
      |           +--> using/usingWhen cleanup
      |
      +--- or error/termination path according to transport/timing
~~~

**The diagram shows a common possibility**, not a 1:1 promise that HTTP disconnects always report an instant `CANCEL`. In practice you may observe `ON_ERROR` from a write failure or another request termination; an abrupt client network drop is sometimes detected only on the next write or timeout.

### 3.2. No Guarantee That "the Client Has Finished Reading the Event"

The server emitting `onNext(event)` does not prove the browser has:
1. Received all TCP bytes.
2. Parsed the SSE event.
3. Executed the JavaScript listener.
4. Recorded the business action.
5. Durably persisted the event.

If important events need **at-least-once delivery** or acknowledgements, add event IDs, a replay store, consumer offset/ack protocols, and idempotency. `onNext`/write completion does not replace application-level acknowledgement.

### 3.3. Graceful Close, Abrupt Disconnect, and Proxies

Clients may stop due to `EventSource.close()`, navigating away, network drops, refreshes, request timeouts, or reverse proxies closing idle connections. A proxy may keep an upstream socket open after the downstream browser leaves, or buffering/timeouts may delay disconnect detection.

Do not build cleanup logic assuming "browsers always send an immediate FIN". You need:
- Bounded timeouts and server-side liveness policies.
- Periodic heartbeats when the streaming protocol allows.
- Cancellation-aware upstream clients.
- Per-subscription cleanup and server-shutdown cleanup.

## 4. Reactor Operators: complete, error, cancel, and finally

### 4.1. `doOnComplete` Is Only for Normal Completion

~~~java
Flux<Long> stream = Flux.range(1, 3)
        .map(Integer::longValue)
        .doOnComplete(() -> recordCompleted());
~~~

`recordCompleted()` is an undefined fragment. The callback runs only when the source completes normally; it is **insufficient** for resource cleanup on infinite or cancelled streams.

### 4.2. `doOnError` Only Observes Errors

~~~java
Flux<String> stream = fetchEvents()
        .doOnError(ex -> logSafeFailure(ex));
~~~

`fetchEvents`/`logSafeFailure` are fragments. `doOnError` is for error observability—it performs no retry/recovery and does not run on cancellation alone. Avoid logging raw headers/tokens or messages containing personal data.

### 4.3. `doOnCancel` Runs When the Subscription Is Cancelled

~~~java
Flux<Long> stream = Flux.interval(Duration.ofSeconds(1))
        .doOnCancel(() -> incrementCancelledSubscriptions());
~~~

In Reactor, the callback runs before cancellation propagates upstream at that operator's position. If cancellation comes from `take(2)` or `timeout`, the callback fires even without a browser closing its connection.

Never equate a `cancelledSubscriptions` metric with "users closing tabs": downstream operators, tests, retries, server shutdowns, and other cancellation paths all trigger cancellation.

### 4.4. `doFinally(SignalType)` Covers All Three Outcomes

~~~java
Flux<Long> stream = Flux.interval(Duration.ofSeconds(1))
        .doFinally(signal -> {
            switch (signal) {
                case ON_COMPLETE -> record("complete");
                case ON_ERROR -> record("error");
                case CANCEL -> record("cancel");
                default -> record("other");
            }
        });
~~~

`record` is an undefined fragment. Reactor `SignalType` has additional constants, yet these three are the key ones for termination. The `doFinally` callback runs when the sequence terminates or is cancelled; it may execute **after the terminal signal has passed downstream**, and chained `doFinally` operators can run in reverse order.

**Test caveat:** a `StepVerifier.verifyComplete()` returning does not always guarantee asynchronous `doFinally` side effects are immediately visible; use synchronization/latches/bounded awaits when assertions depend on that callback.

### 4.5. Callback Comparison Table

| Operator | onComplete | onError | cancel | Used For |
| --- | --- | --- | --- | --- |
| `doOnComplete` (Flux) | Yes | No | No | Tracking success |
| `doOnError` | No | Yes | No | Error logs/metrics |
| `doOnCancel` | No | No | Yes | Tracking cancellation |
| `doOnTerminate` | Yes | Yes | No | Side effects on terminal signals |
| `doAfterTerminate` | Yes | Yes | No | Side effects after complete/error |
| `doFinally` | Yes | Yes | Yes | Recording completion/latency metrics |
| `using` | Yes | Yes | Yes | Owning/closing synchronous resources |
| `usingWhen` | Yes | Yes | Yes | Resource lifecycle with async cleanup publishers |

**Key takeaway:** `doFinally` is a callback for side effects; **it is not magic that turns closing an async connection into an awaitable transaction**. When cleanup is async, `usingWhen` is the stronger abstraction.

## 5. Resources Must Belong to the Subscription, Not the Controller Method

### 5.1. Anti-Pattern: Opening Resources Too Early

~~~java
@GetMapping("/events")
public Flux<Event> events() {
    ExternalSubscription subscription = registerListener();
    return subscription.events();
}
~~~

This is an **anti-pattern fragment** with undeclared `Event` and `ExternalSubscription`. The listener opens eagerly when the controller method runs—before the upstream reactive publisher is subscribed—and has no close path on request cancellation. If the response fails before subscription or retries create multiple subscribers, it leaks.

Design the producer lazily:

~~~java
return Flux.defer(() -> {
    ExternalSubscription listener = registerListener();
    return listener.events()
            .doFinally(signal -> listener.close());
});
~~~

This is still an illustrative fragment, suitable only if `close()` is **synchronous, fast, and idempotent** and the listener belongs strictly to this subscription. For true resource ownership, prefer `Flux.using`; for cleanup requiring an async publisher, use `Flux.usingWhen`.

### 5.2. `Flux.defer`

`Flux.defer(Supplier<Publisher<T>>)` constructs a new publisher for **each subscription**. It helps avoid opening a listener before subscription, yet does not guarantee closing if you forget to attach a cleanup operator.

### 5.3. One Resource Shared Across Multiple Clients

If you set up a global WebSocket/Kafka consumer or `Sinks.Many` and multiple HTTP SSE clients subscribe to it, **one** client cancelling must not `close()` the shared resource for everyone.

Two distinct designs:
- **Per-client**: each subscription owns its own listener/resource; `using`/`usingWhen` closes that client's resource.
- **Shared hot source**: one resource serves many subscribers; its lifetime belongs to the application/shared service using controlled reference counting or application shutdown; per-client cleanup cancels only **that client's subscription branch**.

Never attach `doFinally(sharedConnection::close)` to individual client responses, because the first client leaving would break everyone else's stream.

## 6. `Flux.using`: Opening and Closing Synchronous Resources

`Flux.using` is conceptually like Java's `try-with-resources` for a long-lived publisher:

~~~java
Flux<String> lines = Flux.using(
        () -> openResource(),
        resource -> resource.events(),
        resource -> resource.close());
~~~

This fragment assumes `openResource()` returns a resource with `events()` and `close()`. Reactor invokes the resource supplier **on subscribe**, runs the derived publisher, and closes the resource when the stream completes, errors, or cancels.

### 6.1. Rule: "One Resource, One Owner"

Every new subscription needs its own resource if the resource is not share-safe:
- Open the resource inside `using`'s supplier, not from an eager global variable.
- Only the official resource creator/owner may close it; never have multiple operators release it.
- Cleanup should be idempotent in case external layers fire a stop signal more than once.
- Never store resources in `ThreadLocal`: Reactor operators can switch threads across schedulers.
- If closing can block, never execute it in a Netty event-loop callback; use an async API or a suitable scheduler.

### 6.2. Cleanup on `take(n)`

~~~java
Flux<Long> finiteView =
        Flux.using(
                () -> openCounterResource(),
                resource -> Flux.interval(Duration.ofMillis(50)),
                resource -> resource.close())
            .take(2);
~~~

`openCounterResource` is a fragment. `take(2)` sends cancellation upstream after two items; the resource still cleans up. **Downstream `take` can signal `onComplete` to the subscriber while upstream receives `cancel`.** Therefore, never use `doFinally(CANCEL)` as sole proof that "the client disconnected": `take` in tests also produces `CANCEL`.

### 6.3. Cleanup Must Be Fast If Synchronous

If `close()` performs:
- a slow blocking network call,
- `Future.get()`,
- waiting on a database lock,
- flushing a file for seconds,

it can occupy the event-loop thread as cancellation propagates through the operator. When the resource supports async close, use `usingWhen`. If forced to call blocking legacy close, isolate onto a bounded worker respecting queue/timeout limits; never put `Thread.sleep` inside `doFinally` on the Netty loop.

## 7. `Flux.usingWhen`: Resources with Asynchronous Cleanup

When opening and closing a resource are both publishers, use `usingWhen`. Conceptual example:

~~~java
Flux<Event> events = Flux.usingWhen(
        openAsyncConnection(),                      // Mono<Connection>
        connection -> connection.events(),           // Flux<Event>
        connection -> connection.closeAsync(),       // Mono<Void> on complete
        (connection, error) -> connection.closeAsync(), // Mono<Void> on error
        connection -> connection.closeAsync());      // Mono<Void> on cancel
~~~

This is a **fragment** for a hypothetical external API, not standalone runnable code. `openAsyncConnection()`, `Connection.events()`, and `closeAsync()` must be genuinely non-blocking, return publishers, and have clear resource ownership.

### 7.1. Why All Three Cleanup Paths?

The full overload accepts:
1. `asyncComplete` when the resource-using publisher completes normally.
2. `asyncError` on error; can adjust rollback/cleanup per error.
3. `asyncCancel` when downstream cancels.

If completion/error cleanup fails, `usingWhen` follows Reactor Javadoc rules for error precedence/suppression—do not assume the original body error always remains untouched in what the client sees. **On cancel there is no downstream consumer left to receive a new error response**; cleanup errors must be logged/metered at the right layer with retries/compensation if policy requires.

### 7.2. Simple Resources vs. Transactions

For instance, a reactive database resource might manage a transaction:
- **Complete** ⇒ commit.
- **Error** ⇒ rollback.
- **Cancel** ⇒ handle cancellation per transaction policy (typically rollback if still open).

However, never assume `usingWhen` alone replaces Spring's `ReactiveTransactionManager` or `TransactionalOperator`. Transaction management has many edge cases (savepoints, context, drivers, connection reuse, isolation). For R2DBC, use Spring's reactive transaction facilities rather than hand-rolling commit/rollback on every SSE subscription.

### 7.3. Never Use `doFinally` Indiscriminately as a Substitute

Wrong with async close:

~~~java
return resource.events()
        .doFinally(signal ->
                resource.closeAsync().subscribe());
~~~

This fragment is "fire-and-forget": cleanup subscribes detachedly, errors are hard to monitor, and it is not composed into the resource lifecycle. `usingWhen` gives you a single operator managing completion/error/cancel cleanup with a proper contract.

## 8. `Disposable`, Schedulers, and Timer Cancellation

`Flux.interval(...)` uses a scheduler to emit ticks, and upstream subscriptions normally stop scheduling when cancelled. When returning `Flux.interval` from a WebFlux handler, **never manually call `subscribe()` inside the controller** to hold a `Disposable` if your goal is simply streaming to the client.

Wrong:

~~~java
@GetMapping("/wrong")
public Flux<Long> wrong() {
    Disposable orphan = Flux.interval(Duration.ofSeconds(1))
            .subscribe(i -> audit(i));
    return Flux.interval(Duration.ofSeconds(1));
}
~~~

This is an illustrative fragment with undefined `audit`. `orphan` is an independent subscription—client disconnects on the returned Flux **do not cancel** it; unless disposed, the timer/audit keeps running forever. Fix by returning a single composed publisher:

~~~java
@GetMapping("/right")
public Flux<Long> right() {
    return Flux.interval(Duration.ofSeconds(1))
            .doOnNext(i -> recordSafeMetric(i));
}
~~~

`recordSafeMetric` is also a fragment, yet the side effect is tied to the actual response subscription. If you need a shared background broadcast, manage its lifecycle in an application service (start/stop with bean lifecycle) rather than spawning a new `subscribe()` on every HTTP request.

### 8.1. `Disposable.dispose()` and `Subscription.cancel()`

The Reactor `Disposable` returned when you manually `subscribe(...)` normally supports `dispose()` to request subscription cancellation. In a WebFlux controller, the framework owns the HTTP response subscriber; you **do not** manually call `dispose`. For application-created custom schedulers or shared consumers, the application owns the lifecycle and disposes on shutdown.

## 9. SSE: Heartbeats, Reconnects, and Event IDs

### 9.1. Why Does SSE Need Heartbeats?

An SSE stream may go minutes without a business event. Reverse proxies, load balancers, or browser/network middleboxes have idle timeouts; if no bytes travel, connections may be closed. Heartbeats can:
- Emit an SSE **comment** like `: keepalive`, ignored as a business event by `EventSource`.
- Emit a dedicated `heartbeat` event that the frontend can handle/ignore.
- Emit pings per infrastructure-specific protocols when appropriate.

Heartbeats help **detect/keep connections alive** in some environments; they do not guarantee every proxy lets streams live forever. Tune intervals to fit idle timeouts, and verify proxy response buffering.

### 9.2. SSE Event Format

~~~text
id: 42
event: book-updated
data: {"id":7,"version":3}

: keepalive

~~~

An empty line terminates an SSE event. `id` enables the client to send `Last-Event-ID` on reconnect. **`EventSource` auto-reconnects per browser policy**, yet the server can only replay missed events if the app stores history/offsets; emitting IDs alone does not guarantee exactly-once delivery.

### 9.3. EventSource Reconnects May Open a New Subscription

If a client loses connectivity and the browser reconnects:
- The server may see the **old subscription cancel/close**.
- The new request creates a **new subscription** and a new resource.
- If replaying via `Last-Event-ID`, reading offsets/authorizing the stream must enforce user/tenant scope and retention.
- Duplicate events are a real possibility; frontends must be idempotent when applying side effects.

Never design cleanup assuming "the old stream always closes before the new one opens": network races can open the new stream before the server notices the old one died.

### 9.4. Applications Should Bound Stream Lifetimes

An SSE endpoint can stream indefinitely, yet must enforce policies:
- Subscription concurrency limits per user/tenant when needed.
- Backend listener/connection limits and reconnect limits.
- Heartbeat / idle timeout / maximum session lifetime.
- Backpressure/slow-consumer policies.
- Graceful shutdown/rolling-deploy strategies.
- Auth token expiry/re-auth behavior.

Keeping SSE open indefinitely does not mean keeping a DB transaction open indefinitely; generally never do that.

## 10. Client Disconnect Does Not Always Mean Instant `CANCEL`

### 10.1. You Cannot Always Know Immediately That a User Closed a Tab

Over TCP, a server may only detect a disconnect when:
- A socket read/write encounters an error or EOF.
- A transport/HTTP server callback reports the channel inactive.
- Keepalive/heartbeats or idle timeouts trigger.
- A proxy closes the upstream connection.

If the server sends nothing for a long period, a network break may go unnoticed for a while. A `Flux.never()` emitting nothing makes noticing disappeared clients even harder depending on adapters/proxies. Thus streaming endpoints should consider heartbeats/liveness and timeout cleanup.

### 10.2. `doFinally` Does Not Measure "Tabs Closed"

Ideal telemetry distinguishes:
- `ON_COMPLETE`: stream finished per contract.
- `ON_ERROR`: stream failed upstream, in encoding, or at transport.
- `CANCEL`: downstream no longer wants data from this single subscription.
- Network diagnostics: separate socket/HTTP logs/metrics and proxy disconnects.
- Business session changes: login/logout/revocation, not raw transport.

The exact same client stopping a stream might not emit the exact same terminal signal across every stack/version.

### 10.3. Does `doOnError` on the Source See Socket Write Errors?

Not always. A socket error may occur **downstream of the source Flux** inside the HTTP writer, which then cancels the source; `doOnError` on the upstream source may never see `onError`, receiving `CANCEL` instead. Therefore, observing transport errors requires instrumentation at the WebFlux/Netty layer or server metrics in addition to `doOnError` on business publishers.

## 11. Cleanup After the Response Is Committed

Streaming HTTP normally writes headers/status before the body finishes. Once SSE has emitted a few events, status 200 may already be **committed**. Afterward, an upstream exception:
- Cannot reliably be turned into status 500 with `ProblemDetail`.
- Cannot reliably deliver a valid "error" event to an already-disconnected client.
- May require closing the stream and letting the client reconnect.
- If the protocol permits an in-band error event, you must design the event schema without expecting to alter the already-sent HTTP status.

`ServerHttpResponse.isCommitted()` tells you whether the response is marked committed in the abstraction, yet never treat it as a rollback switch. Pre-commit and post-commit error handling are two distinct problems.

### 11.1. Do Not Register Cleanup with `then` After an Infinite Stream

~~~java
return response.writeWith(dataBuffers)
        .then(Mono.fromRunnable(resource::close));
~~~

This is a fragment; if the streaming publisher is infinite, `then` will **never run** until completion, and on cancellation `then` is not a reliable cleanup mechanism. Use resource operators `using`/`usingWhen` or lifecycle-appropriate `doFinally`.

## 12. Streaming DataBuffer: Pooled Memory and Ownership

When streaming bytes directly:

~~~java
Flux<DataBuffer> body = request.getBody();
return response.writeWith(body);
~~~

This is a fragment, not a complete HTTP proxy. `DataBuffer` may be backed by pooled Netty `ByteBuf`; proper release/retain becomes critical when requests/responses cancel.

### 12.1. Core Rules

- **The producer owns** a buffer before handing it off downstream.
- Once a `DataBuffer` is passed to `ServerHttpResponse.writeWith(...)`, the response writer is responsible for consuming/coordinating release per contract; never release the same buffer **before the writer reads it**.
- If the app reads a buffer itself and does **not** forward it, call `DataBufferUtils.release(buffer)` when done, including on error paths.
- If an operator drops/discards buffers before downstream sees them, `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` helps when the operator supports discard hooks.
- Cancellation can cause buffered/prefetched buffers to be discarded; verify actual operator semantics and run Netty leak detection in an appropriate environment.
- If retaining a buffer for another async task/subscriber, balance `DataBufferUtils.retain`/`release` by ownership; never use an already-released buffer.

**Never blindly call release across every operator**: double release or use-after-release corrupts data/native memory. Follow Spring/Reactor codec contracts, and whenever raw byte manipulation is unnecessary, **let codecs/Resource abstractions** manage buffers.

### 12.2. Anti-Pattern: Releasing Before Writing

~~~java
Flux<DataBuffer> broken = source
        .doOnNext(DataBufferUtils::release);

return response.writeWith(broken);
~~~

Wrong because the response writer receives a buffer that may already be released.

### 12.3. Anti-Pattern: Consuming Without Releasing

~~~java
return DataBufferUtils.join(request.getBody())
        .map(buffer -> {
            byte[] bytes = new byte[buffer.readableByteCount()];
            buffer.read(bytes);
            return bytes; // if pooled, not yet released!
        });
~~~

Besides missing release, unbounded `join` risks memory exhaustion. For small bodies, use the `join(publisher, maxByteCount)` overload and:

~~~java
return DataBufferUtils.join(request.getBody(), 1024)
        .map(buffer -> {
            try {
                byte[] bytes = new byte[buffer.readableByteCount()];
                buffer.read(bytes);
                return bytes;
            } finally {
                DataBufferUtils.release(buffer);
            }
        });
~~~

This fragment requires `request` and imports; exceeding max bytes throws `DataBufferLimitException`. For large payloads, **never** aggregate; stream to a file/object store with explicit limits and handle partial uploads/cancellations.

### 12.4. Cancellation While Writing Files

When using `DataBufferUtils.write(...)`, know the contract of your chosen overload:
- Some overloads **do not auto-release source DataBuffers**; docs require subscribing `DataBufferUtils.releaseConsumer()` on source buffers when needed.
- Overloads writing to `Path` or `AsynchronousFileChannel` have their own ownership and completion semantics.
- If an upload cancels, the file may be a **partial file**. Enforce a policy to delete temp files or use staged uploads with atomic rename on completion.
- Never mark an incomplete file upload as "succeeded" in a database merely because a file was opened and a few chunks were written.

## 13. Does Cancellation Really Stop Upstream?

### 13.1. Reactive HTTP Clients Like WebClient

If a handler streams data from `WebClient`:

~~~java
return webClient.get()
        .uri("/upstream/events")
        .retrieve()
        .bodyToFlux(Event.class);
~~~

This fragment assumes a `WebClient` bean and `Event` type. When the subscriber cancels, the Reactor Netty client can cancel/close the exchange or stop reading depending on implementation/timing, saving resources. However, it does not guarantee the remote server rolled back side effects or stopped emitting events before noticing the disconnect.

### 13.2. JDBC or Legacy Blocking Code

~~~java
return Flux.fromIterable(ids)
        .map(id -> blockingRepository.findById(id));
~~~

If `blockingRepository` is synchronous JDBC/JPA, `map` can block the event loop. Downstream cancellation while a JDBC call is running **is not guaranteed to interrupt the driver** or roll back the query. You need:
- Driver statement/query/socket timeouts.
- Bounded executors/schedulers for blocking legacy calls.
- Connection pool limits, circuit breakers/overload policies.
- Idempotency and transaction boundaries.
- Explicit cancel APIs if supported by the driver, with race handling.

With fully reactive I/O (R2DBC/WebClient), compose publishers without calling `block()`. Never promise that "returning Flux" automatically makes a database non-blocking.

### 13.3. CPU-Bound Work

A heavy CPU computation may ignore cancellation until finishing a work block. To make it interruptible, break it into small chunks, check cancellation/cooperative flags per API, and assign an appropriate compute pool. Cancelling a subscriber does not instantly halt a native JVM CPU routine.

## 14. Timeouts, Retries, and Cancellation Differ

### 14.1. `timeout` Typically Emits an Error Downstream and Cancels Upstream

~~~java
Flux<Long> guarded = Flux.interval(Duration.ofSeconds(2))
        .timeout(Duration.ofMillis(500));
~~~

Downstream, `timeout` emits `TimeoutException`. Upstream on `Flux.interval`, the operator receives `CANCEL` because timeout cancelled the old subscription. Thus the exact same request can observe:
- downstream `doFinally(ON_ERROR)` after timeout,
- upstream `doFinally(CANCEL)` due to timeout cancellation.

Conclusion: **`SignalType` depends on where the operator is placed**, not an absolute label for the whole HTTP request.

### 14.2. Retries Recreate Resources and Subscriptions

~~~java
Flux<Event> stream = openEvents()
        .retryWhen(Retry.backoff(3, Duration.ofMillis(200)));
~~~

This is a fragment. On error, `retryWhen` can re-subscribe, opening a new resource. With `using`/`usingWhen`, the old subscription must clean up per lifecycle before the new resource is used. Avoid infinite retries on SSE: they cause reconnect storms, duplicate side effects, and exhausted subscription quotas.

### 14.3. A Cancelled Request Does Not Mean a 504 Timeout Response

HTTP 504 means gateway timeout per semantics; 503 means service unavailable; 408 means request timeout per server policy. Client disconnects usually **have no response receiver left** for a new error body/status, so never blindly turn every `CANCEL` into HTTP 504.

## 15. Shared Streams: `publish().refCount()`, `share()`, and Lifecycle

If a service keeps a shared "hot" event source:

~~~java
Flux<Event> shared = source.publish().refCount(1);
~~~

This fragment assumes `source` emits event objects. `refCount(1)` subscribes upstream when at least one subscriber is present and can cancel upstream when subscriber count drops to 0. Exact behavior also depends on `refCount(n, gracePeriod)`, sources, and other operators.

**Important:** if a shared resource belongs to the whole application, do not close it just because one SSE subscriber cancels. Consider:
- `Sinks.Many` with an application-level owner.
- A shared broker consumer with ref counting.
- Managed per-client subscription disposables that leave the broker consumer open.
- Bounded replay/history stores when `Last-Event-ID` is needed.
- Per-client backpressure/slow-consumer policies.

### 15.1. `cache()` Can Retain Both Data and Upstream

`Flux.cache()` or `replay()` can retain items in memory per policy and replay them to new subscribers. On infinite streams, unbounded caches risk memory leaks and keep upstream running after the last client leaves. Never slap `cache()` onto SSE just to "avoid duplicate DB calls" without defining lifecycle/retention.

### 15.2. `Sinks.Many`: Per-Subscriber Cleanup vs. Shared Sink

When multiple SSE clients read from a shared sink, cancelling one subscriber stops that subscriber's receiving branch; it does not complete the shared sink for other clients. If you manually register listeners on a sink/hot data structure, remove listener references/metadata to prevent growing lists, and monitor `currentSubscriberCount` or equivalent metrics.

## 16. Runnable Example: Spring Boot 3.3.5 / Java 17 / WebFlux SSE

The example provides three endpoints:
- `GET /api/stream`: infinite SSE where each subscription opens a `StreamLease` resource and closes it on complete/error/cancel via `Flux.using`, updating counters.
- `GET /api/finite`: finite SSE of two events to test HTTP encoding/response completion.
- `GET /api/metrics`: diagnostic snapshot of `active`, `closed`, and `cancelled` counters.

The demo uses no DB, Kafka, credentials, proxy, or external HTTP dependencies. Each `StreamLease` only adjusts counters, so `close` is **fast, synchronous**, and safe for `Flux.using`. When replacing it with a broker listener/DB connection that closes asynchronously, switch to `usingWhen` instead of blocking inside `close`.

~~~text
webflux-stream-lifecycle/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/streamdemo/
    │   ├── StreamDemoApplication.java
    │   ├── stream/StreamLease.java
    │   ├── stream/StreamService.java
    │   └── web/StreamController.java
    └── test/java/com/example/streamdemo/
        ├── StreamServiceTest.java
        └── StreamHttpTest.java
~~~

### 16.1. Gradle Config

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-stream-lifecycle'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Include only `spring-boot-starter-webflux` so Boot runs Reactor Netty per standard setup. Java 17+ and a compatible Gradle wrapper must be present when running commands. `spring-boot-starter-web` can cause Boot to choose the MVC type if present alongside the WebFlux starter.

### 16.2. Main Application

`src/main/java/com/example/streamdemo/StreamDemoApplication.java`:

~~~java
package com.example.streamdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StreamDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(StreamDemoApplication.class, args);
    }
}
~~~

### 16.3. `StreamLease`: Per-Subscription Resource Owner

`src/main/java/com/example/streamdemo/stream/StreamLease.java`:

~~~java
package com.example.streamdemo.stream;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

final class StreamLease implements AutoCloseable {

    private final AtomicInteger active;
    private final AtomicInteger closed;
    private final AtomicBoolean disposed = new AtomicBoolean();

    StreamLease(AtomicInteger active, AtomicInteger closed) {
        this.active = active;
        this.closed = closed;
        active.incrementAndGet();
    }

    @Override
    public void close() {
        if (disposed.compareAndSet(false, true)) {
            active.decrementAndGet();
            closed.incrementAndGet();
        }
    }
}
~~~

`AtomicBoolean.compareAndSet(false, true)` ensures `close` is idempotent, preventing double-decrementing `active` if another component tries to close again. Using `AtomicInteger`s does not represent distributed metrics across pods; production needs external monitoring or properly labeled counters/gauges.

### 16.4. `StreamService`: Creating Resources Right at Subscription Time

`src/main/java/com/example/streamdemo/stream/StreamService.java`:

~~~java
package com.example.streamdemo.stream;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.SignalType;

@Service
public class StreamService {

    private final AtomicInteger active = new AtomicInteger();
    private final AtomicInteger closed = new AtomicInteger();
    private final AtomicInteger cancelled = new AtomicInteger();

    public Flux<ServerSentEvent<String>> events() {
        return Flux.using(
                () -> new StreamLease(active, closed),
                lease -> Flux.interval(
                        Duration.ZERO, Duration.ofMillis(100))
                        .map(index -> ServerSentEvent.<String>builder()
                                .event("tick")
                                .id(Long.toString(index))
                                .data("tick-" + index)
                                .build()),
                StreamLease::close)
                .doFinally(signal -> {
                    if (signal == SignalType.CANCEL) {
                        cancelled.incrementAndGet();
                    }
                });
    }

    public Flux<ServerSentEvent<String>> finite() {
        return Flux.just("alpha", "beta")
                .map(word -> ServerSentEvent.<String>builder()
                        .event("word")
                        .data(word)
                        .build());
    }

    public int activeCount() {
        return active.get();
    }

    public int closedCount() {
        return closed.get();
    }

    public int cancelledCount() {
        return cancelled.get();
    }
}
~~~

Intentional design decisions:
1. Do not create `StreamLease` in the controller or singleton constructor: `Flux.using` calls the supplier when **each subscriber** subscribes.
2. `Flux.interval(Duration.ZERO, 100 ms)` emits ticks without `Thread.sleep`. Event loops are not blocked waiting for timers.
3. Builds `ServerSentEvent` with event name `tick`, sequential event ID, and text payload.
4. `StreamLease::close` is invoked by `using` on complete, error, and cancel; it is idempotent.
5. `doFinally(CANCEL)` only records **subscription cancellation**—never claim it is 100% proof a user left the page.
6. `finite()` is separated to test finite SSE HTTP bodies.
7. `active` rises and falls as clients subscribe/cancel; the metrics endpoint is an async snapshot, not a point-in-time transactional invariant.
8. If a client silently loses network, `active` may stay positive until transport detection/timeout. Use heartbeats/monitoring rather than force-closing whenever a metric shifts.

### 16.5. SSE + Metrics Controller

`src/main/java/com/example/streamdemo/web/StreamController.java`:

~~~java
package com.example.streamdemo.web;

import com.example.streamdemo.stream.StreamService;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class StreamController {

    private final StreamService streams;

    public StreamController(StreamService streams) {
        this.streams = streams;
    }

    @GetMapping(
            path = "/stream",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> stream() {
        return streams.events();
    }

    @GetMapping(
            path = "/finite",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> finite() {
        return streams.finite();
    }

    @GetMapping(
            path = "/metrics",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Map<String, Integer>> metrics() {
        return Mono.fromSupplier(() -> Map.of(
                "active", streams.activeCount(),
                "closed", streams.closedCount(),
                "cancelled", streams.cancelledCount()));
    }
}
~~~

No `subscribe()` or `block()` in the controller. WebFlux manages subscriptions and the SSE HTTP writer. Because this is a demo, the metrics endpoint is public; production metrics must follow deployment security policies and never leak detailed client/user data.

### 16.6. Why Didn't the Demo Use `doFinally(close)` to Close the Resource?

`doFinally(lease::close)` can still work for a **per-subscriber independent** resource that closes quickly and is created lazily; however, `using` expresses **ownership** more clearly and prevents eagerly opening resources outside the reactive chain. When closing requires a non-blocking publisher, switch to `usingWhen`.

## 17. Unit Tests: Deterministic Cancellation Triggered by the Test

`StepVerifier` can verify subscription lifecycles **deterministically at the Reactor level** without simulating broken networks.

`src/test/java/com/example/streamdemo/StreamServiceTest.java`:

~~~java
package com.example.streamdemo;

import com.example.streamdemo.stream.StreamService;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.SignalType;
import reactor.test.StepVerifier;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class StreamServiceTest {

    @Test
    void cancelStopsSourceAndReleasesOwnedResource() {
        StreamService service = new StreamService();

        StepVerifier.create(service.events())
                .expectNextCount(2)
                .thenCancel()
                .verify(Duration.ofSeconds(3));

        assertEquals(0, service.activeCount());
        assertEquals(1, service.closedCount());
    }

    @Test
    void usingClosesWhenSourceCompletesNormally() {
        AtomicBoolean closed = new AtomicBoolean();

        Flux<String> flux = Flux.using(
                () -> "resource",
                resource -> Flux.just("a", "b"),
                resource -> closed.set(true));

        StepVerifier.create(flux)
                .expectNext("a", "b")
                .verifyComplete();

        assertTrue(closed.get());
    }

    @Test
    void usingClosesWhenSourceErrors() {
        AtomicBoolean closed = new AtomicBoolean();

        Flux<String> flux = Flux.using(
                () -> "resource",
                resource -> Flux.concat(
                        Flux.just("a"),
                        Flux.error(new IllegalStateException("broken"))),
                resource -> closed.set(true));

        StepVerifier.create(flux)
                .expectNext("a")
                .expectErrorMessage("broken")
                .verify();

        assertTrue(closed.get());
    }

    @Test
    void doFinallySeesCancelButThatDoesNotMeanNetworkDisconnect() {
        AtomicReference<SignalType> reason = new AtomicReference<>();

        Flux<Long> flux = Flux.interval(Duration.ofMillis(10))
                .doFinally(reason::set);

        StepVerifier.create(flux)
                .expectNextCount(2)
                .thenCancel()
                .verify(Duration.ofSeconds(3));

        // doFinally callback may lag behind downstream;
        // do not assert reason.get() immediately here.
    }
}
~~~

**Explaining the assertions:**
- The first test uses the **test subscriber calling `thenCancel`**, with no TCP client. It proves `using` cleans up on cancellation—**not that Netty detects browser close in 0 ms**.
- Complete/error tests verify closing on the other two branches.
- The last test intentionally skips asserting `doFinally` right after `verify` due to downstream/upstream callback ordering subtleties; if you need the exact reason, use a `CountDownLatch` inside the callback and `await` with a timeout instead of arbitrary `Thread.sleep`.
- Exact tick payloads are not asserted since timing/schedulers vary; only item count is checked before cancelling.
- With simple synchronous `Flux.using` cleanup, closed resource state can be checked right after `StepVerifier` termination/cancellation in this demo.
- All tests should complete within seconds under normal scheduler health; slow CI machines may still hit test timeouts if overloaded, so configure accordingly.

### 17.1. Testing `doFinally(CANCEL)` with a Latch When Needed

If you want to assert the callback deterministically:

~~~java
CountDownLatch finalized = new CountDownLatch(1);
AtomicReference<SignalType> reason = new AtomicReference<>();

Flux<Long> flux = Flux.interval(Duration.ofMillis(10))
        .doFinally(signal -> {
            reason.set(signal);
            finalized.countDown();
        });

StepVerifier.create(flux)
        .expectNextCount(2)
        .thenCancel()
        .verify(Duration.ofSeconds(3));

assertTrue(finalized.await(2, TimeUnit.SECONDS));
assertEquals(SignalType.CANCEL, reason.get());
~~~

This is a **fragment for a JUnit test** requiring imports for `CountDownLatch`, `TimeUnit`, `Flux`, `StepVerifier`, `AtomicReference`, and assertions. Use bounded `await` in tests—**never** call `CountDownLatch.await()` inside a production event-loop handler.

## 18. WebTestClient: Testing Real SSE Without Assuming Instant Disconnects

HTTP/Netty tests can verify a finite stream encodes as SSE, while service-level cancellation was tested in the previous section.

`src/test/java/com/example/streamdemo/StreamHttpTest.java`:

~~~java
package com.example.streamdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class StreamHttpTest {

    @Autowired
    WebTestClient client;

    @Test
    void finiteSseHasEventFramingAndCompletes() {
        client.get()
                .uri("/api/finite")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM)
                .expectBody(String.class)
                .value(body -> {
                    assertTrue(body.contains("event:word"));
                    assertTrue(body.contains("data:alpha"));
                    assertTrue(body.contains("data:beta"));
                });
    }

    @Test
    void metricsEndpointIsReadable() {
        client.get()
                .uri("/api/metrics")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.active").isNumber()
                .jsonPath("$.closed").isNumber()
                .jsonPath("$.cancelled").isNumber();
    }
}
~~~

No sleeping or opening infinite connections is needed in these HTTP tests. When testing real TCP disconnects:
1. Use a client whose API lets you cancel the response-body subscription or close the connection in a controlled way.
2. Consume at least one SSE event to confirm the stream truly subscribed and performed I/O.
3. Cancel the body subscription or close the client connection.
4. Wait with a **bounded deadline** for the `active` metric to settle—never assert instantaneously.
5. Test real proxies/load balancers too if production uses those layers.

Never write deterministic assertions claiming "Netty always emits CANCEL within 1 ms" across all OSes/containers/CI runners. HTTP tests and Reactor unit tests **complement each other**.

### 18.1. Example: WebTestClient Explicitly Cancelling the Response Body

~~~java
FluxExchangeResult<ServerSentEvent<String>> result =
        client.get()
                .uri("/api/stream")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .returnResult(
                        new ParameterizedTypeReference<ServerSentEvent<String>>() {});

StepVerifier.create(result.getResponseBody())
        .expectNextCount(2)
        .thenCancel()
        .verify(Duration.ofSeconds(5));
~~~

This fragment requires imports for `FluxExchangeResult`, `ServerSentEvent`, `ParameterizedTypeReference`, `StepVerifier`, `Duration`, and a `WebTestClient client` field. It explicitly cancels the downstream body publisher; it makes no claim about how each transport/runtime observes the socket. To assert server cleanup, use bounded polling/await on server metrics and maintain test isolation.

## 19. Running the Demo with curl

In a project with a valid Gradle wrapper:

~~~bash
./gradlew test
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test
.\gradlew.bat bootRun
~~~

Run commands sequentially in the shell; do not start `bootRun` if tests have not passed. `build.gradle`/`settings.gradle` do not create a Gradle wrapper on their own; if missing, generate one with a compatible Gradle installation.

### 19.1. Non-Terminating Stream

~~~bash
curl -N -i 'http://localhost:8080/api/stream' \
  -H 'Accept: text/event-stream'
~~~

Example repeating payload:

~~~text
id:0
event:tick
data:tick-0

id:1
event:tick
data:tick-1

id:2
event:tick
data:tick-2

~~~

In the terminal, press Ctrl+C to cancel on the client side. `curl -N` disables curl's output buffering so events appear promptly. **Do not** interpret this example as exact raw HTTP byte ordering/line endings across every server; Spring's SSE encoder may order fields differently by implementation.

### 19.2. Observing Counters

~~~bash
curl -i 'http://localhost:8080/api/metrics'
~~~

Example while one subscriber is active:

~~~json
{"active":1,"closed":0,"cancelled":0}
~~~

Once cancellation is observed by the server and cleanup completes, you may see:

~~~json
{"active":0,"closed":1,"cancelled":1}
~~~

**Only an illustrative output for a fresh JVM with one subscriber.** With multiple clients, reconnects, HTTP tests, or varying timing, counters differ. Browser/client disconnects do not always update them instantaneously.

### 19.3. Finite SSE

~~~bash
curl -N -i 'http://localhost:8080/api/finite'
~~~

Expected HTTP 200, `Content-Type: text/event-stream`, and two events, followed by response completion. This helps contrast a true `ON_COMPLETE` stream against a cancelled stream.

### 19.4. Browser Test

~~~javascript
const events = new EventSource("http://localhost:8080/api/stream");
events.addEventListener("tick", e => console.log(e.lastEventId, e.data));

// Later:
events.close();
~~~

If the frontend sits on a **different origin**, configure **CORS for SSE GET** accordingly, and check cookie/auth policies when using credentials. The demo does not enable CORS automatically, so this browser snippet is easiest to test from the same origin or a dev environment with CORS allowed. Never enable wildcard origins with credentials casually.

## 20. Real Resource Cleanup: Files, Broker Subscriptions, Connections, Cursors

| Resource | When Opened | Proper Cleanup | Caution |
| --- | --- | --- | --- |
| `Flux.interval` timer | On subscribe | Cancel upstream schedule | Never manually `subscribe()` orphan timers |
| Per-client message listener | When subscriber registers | Unregister listener by right ID/token | Never unregister app-wide shared listeners |
| Broker topic subscription | When creating streaming subscription | Cancel/close per subscription | Shared consumers have separate owners |
| R2DBC cursor/connection | When reactive query/transaction starts | Framework reactive close/rollback | Never hold DB transactions open endlessly for SSE |
| JDBC cursor (blocking) | On bounded worker | Close connection/result set + driver timeout | Cancel signals may not interrupt queries |
| `InputStream`/`FileChannel` | When file reading begins | Close channel on complete/error/cancel | Never run blocking close on Netty loop |
| Upload temp file | When creating staged file | Delete temp on error/cancel; atomic finalize on success | Avoid marking partial uploads as succeeded |
| `DataBuffer`/Netty `ByteBuf` | When allocating/receiving buffers | Release by right owner; discard hook as needed | Double release / use-after-release |
| WebClient upstream HTTP | When downstream subscribes | Cancel body publisher/network exchange | Remote side effects do not roll back |
| Shared thread pool/Scheduler | At bean startup | Dispose at application shutdown | Never shut down global pools per client |
| Shared hot source/Sink | At application setup | Close via shared owner/ref count | One client cancelling must not stop all clients |

Never open a resource as a singleton and close it via `doFinally` on **individual** user streams: that causes classic "user A disconnects and breaks user B's data" bugs.

## 21. Shutdown and Rolling Deployments

### 21.1. Graceful Shutdown Does Not Mean Every Stream Completes

During a rolling-restart deploy:
- The server may stop accepting new connections while long-lived SSE streams stay active.
- Grace periods on the HTTP server, load balancer, and orchestrator cap wait times.
- Once the grace period expires, connections are still severed and Reactor streams receive cancellation/errors depending on the stack.
- Browser `EventSource` can auto-reconnect to a new pod.
- If replay is needed, event offsets must live outside the pod.

With Spring Boot, configure graceful shutdown and phase timeouts for your version, then actually test with long-lived streams; never assume servers wait forever.

### 21.2. Never Keep Per-Client Mutable State in a Static Map Forever

If maintaining a subscription registry, unregister on complete/error/cancel, bound entry counts, and avoid retaining `ServerWebExchange`/credentials/body buffers long-term. If a process dies abruptly, no `doFinally` runs—rely on TTLs/leases/recovery in external resources.

### 21.3. Distributed Cancellation

In multi-replica setups:
- Each HTTP connection belongs to one server instance.
- Redis/Kafka/DB cursors may live outside the instance and require ownership/lease semantics.
- Reconnects may land on a different replica.
- Cleanup on an old replica may lag or fail to run if a node crashes.
- Use TTLs, durable offsets, idempotency, and external lease expiration when long-lived state matters.

## 22. Meaningful Observability and Metrics

Measure:
- Active SSE subscriptions per endpoint/feature (never attach raw user IDs as high-cardinality labels).
- Subscriptions completed/errored/cancelled by signal—**never** label `CANCEL` as "user closed tab".
- Duration and bytes/events delivered (clearly distinguishing "sent" vs. client-acknowledged).
- Resource leases opened/closed, pending cleanups, and cleanup error counts.
- Upstream client/DB pool active/idle, cancellations, and driver timeout rates.
- Netty HTTP connections, network write failures, and proxy idle timeouts.
- Reconnect rates, `Last-Event-ID` replay lag, and duplicate event handling.
- Scheduler queues/threads for any blocking legacy cleanup.
- Unreleased DataBuffers/direct memory/leak detector logs in staging.

In logs, include only safe trace/request IDs; never log `Authorization`, cookies, raw personal SSE payloads, or full client IP histories against policy. Reactor Context helps propagate trace metadata across thread-switching callbacks; never assume `ThreadLocal`/MDC propagates across reactive chains automatically.

### 22.1. Distinguishing Logical Streams, HTTP Connections, and Upstream Sources

One logical user session can open multiple HTTP connections over reconnects. One connection corresponds to one response publisher, while multiple publishers may share a broker consumer. Metrics must reflect the right layer instead of counting everything as "active users".

### 22.2. Cleanup Counters Alone Cannot Detect Memory Leaks

Seeing `opened == closed` after a load test is a good indicator, yet does not prove pooled `ByteBuf`s were released, queued buffers were freed, or listener references aren't retained. Combine heap/native memory profiling, Netty leak detection, resource metrics, cancellation tests, and ownership code reviews.

## 23. Common Bugs and Fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Closing tab leaves broker listener alive | Opened outside subscription without unregistering | `using`/`usingWhen` with per-subscriber owner |
| `doOnComplete` never runs on infinite SSE | Stream never completes or is cancelled | `doFinally`/resource operator |
| `doOnError` misses client disconnects | Write error occurs downstream; upstream gets cancel | Track Netty/HTTP errors and cancellation cleanup |
| `CANCEL` counter climbs with `take(1)` | `take` cancels upstream after enough items | Do not label that as tab closed |
| Reconnect opens new stream while old stays open | Delayed network/proxy detection | Bounded idle timeouts/heartbeats, TTLs/leases |
| One client disconnect breaks all clients | Per-client cleanup closed shared resource | Separate ownership/ref counting |
| JDBC query keeps running after timeout | Blocking driver ignores cancel | Driver timeouts, bounded workers, explicit cancel if supported |
| `.block()` in cleanup causes Netty lag | Blocking close on event loop | `usingWhen`/non-blocking close or proper scheduler |
| Cleanup builds publisher and drops it | Calling `closeAsync()` without composing | `usingWhen` or return managed publisher |
| `subscribe()` in controller runs forever | Orphan subscription detached from response | Return publisher instead of manual subscribe |
| Cancelled buffered upload leaves junk files | Missing partial-file cleanup | Staging + delete on error/cancel |
| Native memory keeps climbing | Unbalanced DataBuffer retain/release | Ownership review, `doOnDiscard`, leak detector |
| Cannot return 500 JSON mid-SSE | Status 200 already committed | In-band error/reconnect/close policy |
| Flaky cleanup unit tests | Asserting too early after `doFinally` | Bounded latch/await, avoid arbitrary `Thread.sleep` |
| Client misses dead streams | Proxy holds idle connection | SSE heartbeats and matching timeouts |
| Rolling restart severs streams | Grace periods/long-lived connections | Reconnect+replay, graceful shutdown policy |
| Duplicate events after reconnect | Missing event IDs/idempotency | `Last-Event-ID`/history and idempotent consumers |
| Events lost when client closes | `onNext` is not an ACK | Durable event log/offset/ack protocol |
| Infinite Flux `cache` leaks memory | Unbounded `cache()` | Bounded replay/`refCount`/retention |
| Spring MVC `SseEmitter` used in Netty WebFlux | Mixing up the two web stacks | WebFlux `Flux<ServerSentEvent<T>>` |

### Debugging Workflow

1. Verify `spring-boot-starter-webflux`, reactive runtime, and exact package imports.
2. Trace the data path: controller → publishers/operators → HTTP writer → Netty/socket.
3. Identify **when** resources open and **who** owns them.
4. Search for manual `subscribe()`, `block()`, `Thread.sleep`, or eager resource construction.
5. Verify `doFinally` and `using`/`usingWhen` attach at the right upstream boundary.
6. Distinguish cold/per-client sources from hot/shared ones to avoid accidentally closing shared sources.
7. For real disconnects, inspect Netty logs, HTTP connection metrics, and proxy idle timeouts.
8. Audit buffer ownership, release/discard/cancel paths, and partial-file cleanup.
9. Test complete/error/cancel with `StepVerifier`; test HTTP SSE with `WebTestClient`.
10. Bound async cleanup tests; never assert arbitrary wall-clock timings for real disconnects.
11. Load-test many clients, reconnect storms, and slow consumers.
12. Test app shutdown/pod kills to observe cases where cleanup callbacks never run and TTLs are required.

## 24. Production Checklist

- [ ] Every per-client stream subscription has a clear resource owner and lifetime.
- [ ] Resources open lazily on subscribe, never eagerly left dangling.
- [ ] Complete/error/cancel paths clean up via `using`/`usingWhen`.
- [ ] Synchronous cleanup is fast; async close is never fire-and-forget `subscribe()` in `finally`.
- [ ] Close is idempotent against races/double notifications.
- [ ] No `block()` or blocking JDBC on the Netty event loop.
- [ ] Driver/client timeouts and cancellation semantics are properly understood.
- [ ] Client disconnects are treated as best-effort signals, never promised instantaneous.
- [ ] SSE heartbeats, reconnect policies, and event IDs/replay configured as needed.
- [ ] Side effects are idempotent; cancellation never implicitly rolls back committed transactions.
- [ ] Shared hot sources have dedicated owners/`refCount`, safe from one client closing all.
- [ ] Raw DataBuffers release per ownership; discard/cancel/partial-file paths handled.
- [ ] Timeouts, slow consumers, overload, and backpressure have limits.
- [ ] Status/headers after commit are never treated as modifiable like unsent responses.
- [ ] `StepVerifier` tests cover complete/error/cancel with bounded timeouts.
- [ ] HTTP SSE and cancellation tested via `WebTestClient` and real clients in staging.
- [ ] Metrics separate `ON_COMPLETE`/`ON_ERROR`/`CANCEL`/HTTP disconnects and cleanup outcomes.
- [ ] Graceful shutdown does not substitute for durable replay or lease expiration.
- [ ] Logs/traces exclude tokens, cookies, and raw personal SSE events.

### Self-Check Questions

**1.** How does `cancel()` differ from `onComplete()`?

**Answer:** `cancel` is downstream asking to stop a subscription; `onComplete` is the source signaling successful completion. Cancel is not an `onComplete` delivered to the subscriber.

**2.** Does `doOnError` catch every client disconnect?

**Answer:** No. Socket write errors can happen downstream so upstream receives cancel, or disconnects may not be detected immediately.

**3.** What should you use to clean up across complete, error, and cancel?

**Answer:** `doFinally` for side-effect callbacks/metrics; `Flux.using` for synchronously closed resources; `Flux.usingWhen` when cleanup is an async publisher.

**4.** Why can `take(2)` trigger upstream `doFinally(CANCEL)`?

**Answer:** After receiving two items, `take` cancels upstream even while the downstream subscriber completes normally.

**5.** Does a client disconnecting automatically roll back a just-committed DB update?

**Answer:** No. Transport cancellation is not a business transaction rollback; explicit transaction boundaries, idempotency, and compensation are required.

**6.** If a shared sink has 50 SSE clients, should the first client cancelling close the sink?

**Answer:** No, unless a shared owner/`refCount` policy determines no clients remain. Per-client cleanup cleans up only that client's subscription.

**7.** Why is `Flux.usingWhen` better than `doFinally(() -> closeAsync().subscribe())`?

**Answer:** `usingWhen` integrates cleanup publishers into the resource lifecycle across complete/error/cancel cleanly; subscribing inside a callback detaches from the flow and hides errors.

**8.** Is releasing a raw `DataBuffer` in `doOnNext` before passing it to `writeWith` safe?

**Answer:** No. The writer may read an already-released buffer; keep ownership clear and release only where usage finishes.

**9.** Does SSE `id` guarantee exactly-once delivery?

**Answer:** No. A replay store, offsets/acks, and idempotent consumers are needed depending on reliability requirements.

**10.** Does a passing `StepVerifier` cancel test prove Netty reports client tab close immediately?

**Answer:** No. It only verifies Reactor cancellation semantics; transport/proxy disconnect detection must be tested separately with HTTP clients and staging networks.

## 25. Official References

- [Spring Framework — WebFlux Annotated Return Values](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/return-types.html): `Flux<ServerSentEvent>` and HTTP streaming.
- [Spring Framework — WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html): functional handlers/routers and reactive response streaming.
- [Spring Framework — WebFlux Overview](https://docs.spring.io/spring-framework/reference/web/webflux.html): Reactive Streams server infrastructure and non-blocking I/O.
- [Spring Framework — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html): pooled buffers, ownership/release, codecs.
- [Spring Framework — DataBufferUtils Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html): `retain`, `release`, `join`, `write` utilities.
- [Project Reactor 3.6 — Handling Errors / Using Resources and Finally](https://projectreactor.io/docs/core/3.6.11/reference/index.html#_using_resources_and_the_finally_block): `using`/`doFinally`.
- [Project Reactor — Reactor Core API: Flux](https://projectreactor.io/docs/core/3.6.11/api/reactor/core/publisher/Flux.html): `using`, `usingWhen`, `doOnCancel`, `doFinally`.
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/3.6.11/reference/index.html#testing): `thenCancel` and timeouts.
- [Project Reactor — Hot Versus Cold](https://projectreactor.io/docs/core/3.6.11/reference/index.html#reactor.hotCold): `share`, `refCount`, per-subscription behavior.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): reactive HTTP tests.
- [Spring Framework — ServerSentEvent Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/codec/ServerSentEvent.html): `event`, `data`, `id`, `retry`.
- [Reactive Streams Specification](https://www.reactive-streams.org/): `Subscription.request(n)` and `Subscription.cancel()`.
- [MDN — Using Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events): `EventSource`, event stream format, reconnect, and browser lifecycle.

**Key takeaway:** When an HTTP streaming client stops caring, downstream **may** cancel the reactive subscription and ask upstream to stop emitting. Yet `cancel` is not identical to an instant disconnect, is not a transaction rollback, and does not automatically close all resources. Open resources per subscription, use `using`/`usingWhen` to clean up across complete/error/cancel, understand buffer ownership, manage heartbeats/reconnects, and verify transport behavior with dedicated tests. For shared sources, separate per-client lifetimes from application lifetimes.
