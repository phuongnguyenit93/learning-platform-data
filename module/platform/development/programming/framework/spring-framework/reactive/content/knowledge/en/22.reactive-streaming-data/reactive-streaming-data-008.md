# Disconnects, Sequence Cancellation, and Resource Cleanup

**Context:** Spring Framework Reactive → **Continuous Data Streaming**.

In WebFlux, a request can keep a publisher active far longer than a typical request/response: SSE, NDJSON, file downloads, cursor queries, message broker connections, or continuous data streams. When the client closes a tab, cancels a subscription, loses network connectivity, or stops reading the response, the server needs to stop work that no longer has a recipient and release opened resources.

Three concepts must be distinguished:

- **Disconnect:** the connection or HTTP stream between client and server is no longer usable. This is an event at the transport/server adapter layer.
- **Cancellation:** the downstream subscriber sends a cancel signal via the Reactive Streams subscription to tell the upstream publisher to stop emitting data. In Reactor, cancellation is a distinct terminal condition, not an `onError`.
- **Cleanup/release:** closing cursors, connections, file handles, subscriptions, timers, buffers, or other resources allocated to the pipeline.

A client disconnect typically leads to cancellation of the response publisher, though detection may be delayed until the next write attempt. Cancellation can propagate back up the reactive chain, but **does not automatically undo side effects that have already happened**. The application must bind resources to the subscription lifecycle and define how to close them across complete, error, and cancel alike.

## 1. Lifecycle of a streaming response

Example SSE endpoint emitting data over time:

```java
@GetMapping(path = "/updates",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<Update>> updates() {
    return updateService.stream()
            .map(update -> ServerSentEvent.builder(update).build())
            .doOnCancel(() -> log.info("client cancelled updates stream"))
            .doFinally(signal ->
                    log.info("updates stream finished: {}", signal));
}
```

This is a WebFlux snippet requiring service, DTO, logger, and imports. The controller returns a `Flux` to the framework; the server adapter registers a subscriber to write events to the HTTP response. If the client disconnects while the stream is active, the server can cancel the body-writing subscription. `doOnCancel` and `doFinally` help observe that lifecycle.

General flow:

```text
Client                         WebFlux server
  |                                  |
  | GET /updates                    |
  |--------------------------------->|
  |                                  | subscribe response Flux
  |<---------------------------------| HTTP 200 + headers
  |                                  |
  |<---------------------------------| event 1
  |<---------------------------------| event 2
  |                                  |
  X client closes tab / network lost |
                                     | transport detects write failure
                                     | cancel response subscription
                                     v
                              response Flux receives cancel
                                     |
                                     v
                              cancellation propagates upstream
                                     |
                                     v
                              resource cleanup runs
```

Not every disconnect is detected the instant the network link drops. The OS, TCP, TLS, reverse proxies, and server may hold data in buffers; the server only learns the client is gone when an I/O operation detects an error or a timeout occurs.

Spring emphasizes that for streaming responses such as `text/event-stream`, `application/jsonl`, or `application/x-ndjson`, applications should send periodic data to detect client disconnects earlier. An SSE comment, empty event, or no-op payload can serve as a heartbeat when protocol-compatible. The heartbeat interval must be shorter than the proxy/load balancer idle timeout and chosen according to the deployment environment.

## 2. Disconnects do not always surface as an exception

When a client closes the connection, the server may observe:

- A response write error from the transport.
- Cancellation of the subscriber writing the body.
- A timeout when there is no I/O progress.
- A request body read error if the client disconnects during an upload.
- No immediate signal if no subsequent I/O occurs to detect it.

Therefore, do not design cleanup solely around `doOnError`. A disconnect can enter the cancellation branch without emitting `onError` to the business publisher.

| Situation | Observable reactive signal | Meaning |
|---|---|---|
| Publisher finishes normally | `onComplete` | Stream completed successfully |
| Service emits an error | `onError` | Stream failed |
| Client cancels subscription | `cancel` | Subscriber no longer wants to receive data |
| Server detects socket write failure | May be error or cancel depending on adapter/write path | Transport can no longer write |
| Client goes silent without sending FIN/RST | No immediate signal | Heartbeats/timeouts needed to detect |

Cancellation has no HTTP status of its own. If the response has not committed yet, the server may still have an opportunity to handle errors via HTTP mechanisms. Once status/headers have been sent and the stream body has started, the server cannot go back to change the response into a JSON 500. Once the client has left, trying to send an extra error body is pointless anyway.

## 3. Cancellation is a distinct signal, not onError

Reactive Streams has three terminal signals commonly observed:

- `onComplete`: the publisher completes normally.
- `onError`: the publisher terminates due to an error.
- `Subscription.cancel()`: the subscriber asks the publisher to stop.

In Reactor, `doOnCancel` observes cancellation; `doFinally` receives `SignalType.CANCEL` in addition to `ON_COMPLETE` and `ON_ERROR`.

Example:

```java
Flux<Long> stream = Flux.interval(Duration.ofSeconds(1))
        .doOnCancel(() -> log.info("upstream cancel received"))
        .doFinally(signal ->
                log.info("upstream terminal signal: {}", signal));

return stream.take(5);
```

Once `take(5)` has received five items, it completes downstream and cancels upstream because it needs no more data. This is operator-triggered cancellation, not a client disconnect. It illustrates that any operator that no longer needs upstream can generate cancellation.

**Do not use `onErrorResume` to catch cancellation.** Cancellation is not an error signal, so error fallbacks are not a cleanup mechanism for disconnects. If resources must be cleaned up, bind cleanup to a resource scope or the cancellation lifecycle.

## 4. Cancellation propagates upstream through the reactive chain

Suppose a pipeline is:

```java
return repository.openCursor()
        .flatMapMany(cursor -> cursor.readRows())
        .map(this::toDto)
        .filter(this::visibleToClient)
        .publishOn(Schedulers.parallel())
        .doFinally(signal -> metrics.record(signal.name()));
```

If downstream cancels the subscription, cancellation propagates back through the operators to the source. Operators may stop requesting more items, cancel inner publishers, and clear internal queues according to their contracts.

Several operators create or manage inner subscriptions:

- `flatMap` can cancel active inner publishers.
- `switchMap` cancels the old publisher when switching to a new one.
- `take` cancels upstream after enough items.
- `timeout` cancels the source when time expires.
- `next` needs only the first item and cancels the rest.
- `publishOn` and prefetching operators may hold items in queues; discarded items must be cleaned up if the data type requires it.

Cancellation does not guarantee every external library or API stops instantaneously. A Reactive Streams–compliant publisher can propagate cancel, while an underlying driver, SDK, native call, or blocking operation may require its own cancellation API.

## 5. doOnCancel and doFinally

These two operators serve different purposes:

| Operator | When it runs | Used for |
|---|---|---|
| `doOnCancel(Runnable)` | When subscriber calls cancel; callback runs before cancel propagates upstream | Recording client/operator cancel, incrementing counters |
| `doFinally(Consumer<SignalType>)` | After complete, error, or cancel has propagated downstream/upstream per lifecycle | Terminal signal metrics, durations, completion logs |
| `doOnError(Consumer)` | When an error signal occurs | Logging errors, classifying exceptions |
| `doOnComplete(Runnable)` | On normal completion | Observing successful completion |

Example:

```java
return eventService.stream()
        .doOnCancel(() -> metrics.increment("stream.cancelled"))
        .doOnError(error ->
                log.warn("stream failed", error))
        .doFinally(signal ->
                metrics.recordTermination(signal.name()));
```

Notes:

1. `doOnCancel` does not run when the publisher completes or errors normally.
2. `doOnError` does not run merely because the subscriber cancelled.
3. `doFinally` runs for complete, error, and cancel alike.
4. `doFinally`'s callback is synchronous and does not return a publisher to await async cleanup.
5. `doFinally` executes after the terminal signal has been forwarded; therefore downstream code may finish before side effects inside the callback complete.
6. Multiple chained `doFinally` operators can observe callbacks in reverse order because each runs after the signal passes through the operator.

Use observation operators for logging/metrics. Do not treat `doOnCancel` as the sole place to close database connections, files, or cursors if closing must be guaranteed and may be asynchronous.

## 6. Managing resources with using

Reactor's `using` resembles try-with-resources: create a resource per subscription, create a publisher using that resource, and clean up when the sequence completes, errors, or cancels.

Example with a synchronously closed cursor:

```java
Flux<Row> rows = Flux.using(
        cursorFactory::open,
        cursor -> cursor.readRows(),
        Cursor::close);
```

This is an illustrative snippet; `CursorFactory` and `Cursor` are application abstractions. Each subscriber gets its own resource. Cleanup is invoked when the sequence ends or the subscriber cancels.

`using` fits resources with synchronous, fast close operations that do not block the event loop. If `close()` can block for a long time, do not call it directly on an I/O thread; use an async API or offload blocking work to an appropriate scheduler.

Do not create a cursor once in a singleton field and share it across subscribers. One client cancelling could close a resource another client is still using.

## 7. Managing async cleanup with usingWhen

Database connections, leases, remote subscriptions, or transactions may need to close asynchronously. Use `usingWhen` to declare cleanup separately for the three termination paths:

```java
Flux<Row> rows = Flux.usingWhen(
        connectionFactory.acquire(),
        connection -> queryRows(connection),
        connection -> connection.closeAsync(),
        (connection, error) ->
                connection.rollbackAsync()
                        .then(connection.closeAsync()),
        connection -> connection.closeAsync()
);
```

This is a structural example; `acquire`, `queryRows`, `closeAsync`, and `rollbackAsync` represent real resource APIs. Cleanup functions must return a Publisher. If the system has no transaction, the error branch can simply close the resource; do not call rollback when there is no transaction.

Commonly used overloads:

- `usingWhen(resourcePublisher, resourceClosure, asyncCleanup)`: uses one shared cleanup publisher for all terminal paths.
- `usingWhen(resourcePublisher, resourceClosure, asyncComplete, asyncError, asyncCancel)`: separate cleanup for complete, error, or cancel.

Crucially, every operation requiring the open resource must reside inside `resourceClosure`. Do not use the connection outside the publisher scope after cleanup has run.

Async cleanup can fail. Reactor may turn a cleanup error into the terminal error replacing the original terminal signal on certain paths. Log/metric cleanup failures, set appropriate timeouts on close operations, and define a policy if resource closing fails.

## 8. Database transactions and cancellation

In a reactive transaction, the transaction lifecycle must be bound to a publisher managed by the framework/transaction manager. With R2DBC, use Spring reactive transaction management or `TransactionalOperator` instead of manually opening connections and subscribing manually.

Example:

```java
return transactionalOperator.transactional(
        orderRepository.save(order)
                .then(auditRepository.save(auditRecord))
);
```

If the pipeline terminates with an error, the transaction manager can roll back. If the subscription is cancelled before the transaction finishes, the transaction manager performs cleanup/rollback according to the semantics of the transaction resource and manager in use.

However:

- Cancellation is not a universal rollback command for every system.
- An HTTP call already sent to a payment provider is not automatically undone.
- A message already published to a broker may have already reached a consumer.
- A written file or sent email does not vanish when the client disconnects.
- A database commit may have already happened before cancellation is observed.

For operations with important side effects, use proper transaction boundaries, idempotency keys, outboxes, job states, or reconciliation. Do not rely on cancellation as an exactly-once guarantee.

## 9. DataBuffer and pooled memory

In WebFlux, `DataBuffer` represents a byte region. On some servers such as Reactor Netty, buffers can be pooled and reference-counted. If application code directly consumes or creates `DataBuffer`, you must understand ownership and when to release.

When using `@RequestBody Mono<Dto>`, `Flux<Dto>`, or standard response DTOs, let codecs and the HTTP layer manage buffers. Manual release is usually unnecessary.

When code handles `Flux<DataBuffer>` directly:

- Once done reading a buffer, release it exactly once via `DataBufferUtils.release(buffer)` when your code owns it.
- If holding a buffer for later reading, guarantee release upon completion and on error/cancel.
- If operators may drop items or hold items in prefetch queues, consider `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` at the right position.
- Do not release buffers still owned by the framework/codec.
- Do not retain unnecessarily; if retain is called, there must be a matching release.
- Do not read a buffer after releasing it.

Example reading a raw body and releasing each buffer after copying bytes:

```java
Flux<byte[]> chunks = request.getBody()
        .map(buffer -> {
            try {
                byte[] bytes = new byte[buffer.readableByteCount()];
                buffer.read(bytes);
                return bytes;
            }
            finally {
                DataBufferUtils.release(buffer);
            }
        });
```

This is an illustrative snippet when the application has received ownership to consume buffers. If upstream operators can prefetch or discard DataBuffers before reaching `map`, add cleanup for discarded items and verify ownership at each step.

Discard hook example:

```java
Flux<DataBuffer> filtered = request.getBody()
        .filter(this::isAccepted)
        .doOnDiscard(
                DataBuffer.class,
                DataBufferUtils::release);
```

`doOnDiscard` only affects upstream operators that support discard and items dropped by those operators. The hook is not a mechanism to free every object on every path. Cleanup hooks must be contract-safe and avoid double releases.

With multipart streaming via `PartEvent`, each event's content must be consumed, relayed elsewhere, or released. Skipping a file part without consuming/releasing its DataBuffers can leak pooled memory.

## 10. Blocking I/O and limitations of cancellation

A blocking call does not automatically become cancellable just because it is placed inside a Reactor pipeline.

Example moving a legacy blocking call off the event loop:

```java
Mono<Result> result = Mono.fromCallable(
                () -> legacyClient.fetch(id))
        .subscribeOn(Schedulers.boundedElastic());
```

This avoids running the blocking operation on an I/O event-loop thread. However, downstream cancellation **does not guarantee** the blocking library stops immediately. You may need:

- Connect/read timeouts in the HTTP client or JDBC driver.
- Library statement close/cancel APIs.
- Interruptible operations if supported by the library.
- Timeouts and bounds on pending tasks.
- Truly reactive drivers such as R2DBC when suitable.

Do not call `block()` inside controllers, WebFilters, or the event loop. Do not manually call `subscribe()` to detach work from a request without a dedicated owner/lifecycle.

If the client disconnects yet business work must continue, enqueue a durable job and return a job ID. A background worker has a lifecycle independent of the HTTP subscription; do not rely on a response subscription whose client has left to perform durable background work.

## 11. Heartbeats for SSE and long streams

A stream silent for a long time can prevent a proxy or server from noticing the client has vanished. Heartbeats create periodic activity so the write layer detects broken connections sooner.

SSE comment heartbeat example:

```java
Flux<ServerSentEvent<Update>> heartbeats =
        Flux.interval(Duration.ofSeconds(20))
                .map(tick ->
                        ServerSentEvent.<Update>builder()
                                .comment("keep-alive")
                                .build());

Flux<ServerSentEvent<Update>> response =
        Flux.merge(
                updateService.stream()
                        .map(update ->
                                ServerSentEvent.builder(update).build()),
                heartbeats
        );
```

This is a snippet for a long-lived stream; choose an interval matching reverse proxy/load balancer idle timeouts. SSE comments do not generate business events for the client, yet they generate writes on the connection. Because the heartbeat is an infinite source, the response stays open even if the update publisher completes; that is intentional for live streams. If the response should end along with the update source, design an appropriate lifecycle/merge instead of merging an unbounded infinite heartbeat.

Heartbeats do not prove the client processed events. They only help detect certain broken connections earlier; TCP/proxies can still buffer or drop under their own conditions.

## 12. Multiple subscribers and shared stream sources

Distinguish per-client subscriptions from shared data sources:

- **Cold publisher:** each subscriber can trigger an independent execution. Client A cancelling stops A's subscription.
- **Hot publisher:** the source may emit independently of subscribers. Client A cancelling does not necessarily stop the source.
- **Shared publisher:** multiple clients share a multicast source. One client leaving should not close resources other clients still need.
- **Ref-counted source:** the upstream source can disconnect when the remaining subscriber count drops to a configured threshold, such as 0.

For example, `publish().refCount(1)` can disconnect upstream when no subscribers remain. This fits when the source only needs to exist while at least one client is present. If the source must keep running even with zero clients, use a dedicated lifecycle and shutdown policy.

Do not store mutable request-specific state in fields of a singleton service or share a single cursor across multiple clients. Create per-subscription state using `defer` or appropriate resource operators.

## 13. Cancellation is neither rollback nor retry

Cancellation means the subscriber no longer wants to receive data. It does not assert that:

- Every command sent to the database was cancelled.
- Remote services did not process the request.
- The broker did not receive the message.
- The transaction rolled back.
- The client can retry without creating duplicate side effects.

Retries in Reactor primarily handle error signals; cancellation is not an error for `retry()` to re-trigger automatically. If a client reconnects and wants to resume the stream, the API needs an explicit resume protocol, such as event ID/sequence, Last-Event-ID for SSE, cursors, or checkpoints.

For data-writing commands, use idempotency keys and optimistic concurrency so clients can retry safely when uncertain whether the server committed before the connection dropped.

## 14. Standalone runnable Java 17+ program: observing cancel and closing resources

This example uses Reactor Core to simulate a synchronous cursor. `take(1)` receives one row and then cancels upstream. `Flux.using` closes the cursor when the sequence is cancelled.

Structure:

```text
reactor-cancellation-demo/
├── pom.xml
└── src/main/java/demo/CancellationDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>reactor-cancellation-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.7.17</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/CancellationDemo.java`:

```java
package demo;

import reactor.core.publisher.Flux;

public class CancellationDemo {

    static final class Cursor {
        void close() {
            System.out.println("cursor closed");
        }
    }

    public static void main(String[] args) {
        Flux.using(
                Cursor::new,
                cursor -> Flux.just("row-1", "row-2")
                        .doOnCancel(() ->
                                System.out.println("source doOnCancel"))
                        .doFinally(signal ->
                                System.out.println(
                                        "source doFinally=" + signal)),
                Cursor::close
        )
        .take(1)
        .doFinally(signal ->
                System.out.println(
                        "downstream doFinally=" + signal))
        .doOnNext(row -> System.out.println("row=" + row))
        .blockLast();
    }
}
```

Run with JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.CancellationDemo
```

**Expected standard output:**

```text
row=row-1
source doOnCancel
source doFinally=CANCEL
cursor closed
downstream doFinally=ON_COMPLETE
```

Explanation:

1. `Flux.using` creates the cursor upon subscription.
2. Source emits `row-1`; `take(1)` has enough data so it cancels upstream.
3. Source observes cancel via `doOnCancel`.
4. `doFinally` on the source receives `SignalType.CANCEL` after cancel propagates upstream.
5. `using` invokes `Cursor.close()` to release the resource.
6. Downstream of `take(1)` completes normally, so the outer `doFinally` receives `ON_COMPLETE`.
7. `blockLast()` is used only in `main` so the demo program waits; do not put it in WebFlux handlers.

The program simulates operator-driven cancellation. On client disconnect, the server adapter is the component that can issue cancellation to the response publisher; resource cleanup follows the exact same principles.

## 15. Testing cancellation

### 15.1. StepVerifier tests cancel and cleanup

For pure Reactor pipelines, `StepVerifier` can send cancel explicitly:

```java
AtomicBoolean cancelled = new AtomicBoolean();

Flux<Long> stream = Flux.interval(Duration.ofMillis(100))
        .doOnCancel(() -> cancelled.set(true));

StepVerifier.create(stream)
        .expectNext(0L)
        .thenCancel()
        .verify();

assertThat(cancelled).isTrue();
```

This is a test snippet requiring Reactor Test, JUnit/AssertJ, and imports. `thenCancel()` verifies the publisher reacts to cancellation without needing `Thread.sleep`.

If resource cleanup must be verified, use a fake resource with a counter or latch; assert cleanup is invoked exactly once. With `usingWhen`, cleanup is asynchronous, so tests should wait for the cleanup publisher to complete using proper synchronization tools or StepVerifier timeouts rather than guessing with fixed sleep durations.

### 15.2. Integration testing over real HTTP

`WebTestClient.bindToController` or binding a router directly can test handler logic but does not fully simulate transport-level disconnects. To test client abort behavior:

1. Start the WebFlux application on a real embedded server, usually with `RANDOM_PORT`.
2. Create a streaming endpoint that does not end immediately, with `doOnCancel` or a cleanup marker.
3. Use a real HTTP client (such as `WebClient`) to subscribe to the response body.
4. After receiving one or a few items, cancel the subscription/close the response.
5. Wait for the cleanup signal using a latch or test probe with a timeout.
6. Assert the source received cancel and the resource was released.
7. Repeat for normal completion and error to confirm all three termination paths.

Transport tests depend on the server adapter and proxy. A test running over an in-memory exchange is not enough to prove socket disconnects in production.

### 15.3. Cases to include in the test suite

- Normal completion closes resources.
- Errors close resources and preserve the original error per policy.
- Cancellation closes resources.
- Cancellation before resource acquisition completes does not leak resources.
- Async cleanup failures or timeouts are observed.
- Slow clients do not cause unbounded queue growth.
- Heartbeats help detect stale connections within the expected timeframe.
- One client cancelling does not break other clients' streams when sources are shared.
- Aborted multipart/request body uploads properly release DataBuffers/PartEvents.
- Side effects have idempotency when clients reconnect or retry.

## 16. Common mistakes

1. **Using only doOnError for cleanup.** Cancellation is not an error signal; use resource scopes or cancellation-aware cleanup.
2. **Using only doOnComplete.** That callback does not run on error or cancel.
3. **Thinking doFinally automatically awaits async cleanup.** The doFinally callback does not return a Publisher; use usingWhen for async cleanup.
4. **Calling close() on the event loop when close blocks.** Switch to an async API or an appropriate scheduler.
5. **Creating a resource outside the publisher and sharing it across subscribers.** One subscriber cancelling can close another subscriber's resource.
6. **Using using for slow async close.** Use usingWhen to await the cleanup publisher.
7. **Forgetting the cancel branch of usingWhen.** When different cleanup is needed, provide asyncCancel explicitly.
8. **Assuming disconnects are detected instantaneously.** Transport may only detect on the next write or timeout.
9. **Not sending heartbeats on long-silent streams.** Proxies may close idle connections or the server detects disconnects late.
10. **Treating cancel as rollback.** External side effects may have already completed; use transactions/idempotency/reconciliation.
11. **Treating cancel as retry.** Retry operators handle errors, not automatic resubscription on cancel.
12. **Manually subscribing inside a controller so work continues after disconnect.** Creates unowned work; if background execution is needed, enqueue a durable job.
13. **Calling block inside a reactive chain.** Blocks the event loop and breaks cancellation/backpressure.
14. **Reading DataBuffer without releasing.** Pooled memory can leak on error/cancel.
15. **Releasing DataBuffer twice.** Can cause reference-count errors; establish ownership and release exactly once.
16. **Assuming doOnDiscard handles every dropped object.** The hook only applies to discard-capable upstream operators and does not replace full-lifecycle cleanup.
17. **Skipping PartEvent during multipart upload.** Every content buffer must be consumed, relayed, or released.
18. **Keeping connections/cursors in singleton fields.** Concurrent requests can share or prematurely close resources.
19. **Using timeout as conclusive proof the client disconnected.** Timeout only means no signal arrived within the chosen window; causes may be network, slow client, or slow upstream.
20. **Not testing with a real server.** In-memory tests cannot prove transport cancellation.

## 17. Production design checklist

Before taking long streams to production, verify:

- **Disconnect detection:** which server adapter is running? What is the proxy idle timeout? Are heartbeats present?
- **Cancellation path:** does the response publisher receive cancel? Which operators hold inner subscriptions or queues?
- **Resource ownership:** per subscriber, how are cursors, connections, files, and broker subscriptions created?
- **Cleanup:** use `using` or `usingWhen`? Do complete, error, and cancel all have resource-closing paths?
- **Cleanup failure:** are timeouts, logs, and metrics in place when closing fails?
- **DataBuffer:** who owns it, who retains/releases, and are discard/error/cancel handled?
- **Blocking calls:** are real timeout/cancel APIs present, or only offloading to boundedElastic?
- **Transactions:** are reactive transactions bound to the right publisher scope?
- **Side effects:** could commits happen before disconnect? Are idempotency keys/outbox/reconciliation present?
- **Shared streams:** does one subscriber cancelling affect other subscribers or the global source?
- **Background work:** has work that must live independently been moved to durable jobs/queues?
- **Observability:** are complete, error, cancel, transport reset, timeout, and cleanup failure distinguished?
- **Testing:** are both StepVerifier tests and real-server HTTP integration tests present?
- **Capacity:** are stream counts, heartbeats, connections, queues, and cleanup tasks bounded?

**Key takeaway:** Disconnect is a transport event; cancellation is a Reactive Streams signal; cleanup is a resource-management responsibility. WebFlux can propagate cancellation from the response writer back to the publisher when the server detects the client is no longer receiving data. Use `doOnCancel`/`doFinally` to observe, `using` for synchronous resources, `usingWhen` for async cleanup, and manage `DataBuffer` by ownership. Cancellation does not automatically roll back side effects; tasks that must continue after the client leaves must have an independent, durable lifecycle.

## References

- Spring Framework — [Reactive Core: WebFlux streaming, disconnect detection and DataBuffer](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html).
- Spring Framework — [Data Buffers and Codecs: release, retain, join and discard](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html).
- Spring Framework — [Functional Endpoints: request body streaming and PartEvent ownership](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html).
- Project Reactor — [Dealing with Objects that Need Cleanup](https://projectreactor.io/docs/core/release/reference/advancedFeatures/cleanup.html).
- Project Reactor — [Flux Javadoc: using and usingWhen](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- Project Reactor — [Mono Javadoc: doOnCancel and doFinally](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html).
