# Reactive backpressure in RSocket

## 1. Context: when the producer is faster than the consumer

In module **SPRING_INTEGRATION_ADAPTERS**, applications connect external systems into Spring Integration via inbound/outbound adapters, gateways, pollers, and `MessageChannel`. A crucial requirement when exchanging over RSocket is controlling **data transfer rate**: the server may emit thousands of inventory updates per second, while the client's processing flow and database can only write a few hundred updates.

Suppose route `inventory.events` continuously emits inventory events. If every event is accepted without throttling, buffers grow, latencies compound, and out-of-memory errors can occur. **Reactive backpressure** lets the consumer signal how many more elements it is ready to receive, allowing the producer to cap emission to match demand.

~~~text
Event source  ------->  RSocket  ------->  Spring Integration  ---> DB
    fast             transports frames       processes slowly

Unbounded: 500 events/s arrive, 200 events/s processed
        -> backlog grows by ~300 events/s

With backpressure:
  Consumer requests N elements
  Producer emits only up to valid demand
  Intermediate components must honor or propagate demand
~~~

The **Reactive backpressure in RSocket** lesson, part of the **RSocket Adapter** chapter, helps you:

- Understand the relationship between **`Publisher`**, **`Subscriber`**, **`Subscription`**, and element demand.
- Distinguish `REQUEST_N`, `CANCEL`, timeouts, and request-reply semantics in RSocket.
- Observe demand propagating from `RSocketRequester` to a responder with `Flux`.
- Spot where backpressure breaks when bridging into queues, blocking gateways, or non-demand-aware push sources.
- Choose concurrency limits, prefetch sizes, buffers, overload handling, and appropriate business strategies.
- Test real demand, slow-consumer conditions, and resource release.

## 2. Reactive Streams core: the receiver controls demand

Per the Reactive Streams model:

| Component | Role | Application example |
| --- | --- | --- |
| `Publisher<T>` | Supplies elements according to demand signals | `Flux<StockEvent>` |
| `Subscriber<T>` | Consumes elements and manages demand | Reactor-provided or custom subscriber |
| `Subscription` | Control channel between both sides | `request(n)` and `cancel()` |
| `onNext(T)` | Delivers one element | One `StockEvent` |
| `onError(Throwable)` | Terminates with error | Codec failure, source failure, buffer overflow |
| `onComplete()` | Completes normally | Finished sending finite list |

Basic flow:

~~~mermaid
sequenceDiagram
    participant S as Subscriber
    participant P as Publisher
    S->>P: subscribe()
    P-->>S: onSubscribe(subscription)
    S->>P: request(2)
    P-->>S: onNext(event 1)
    P-->>S: onNext(event 2)
    Note over P: No further demand yet
    S->>P: request(1)
    P-->>S: onNext(event 3)
    S->>P: cancel()
    Note over P,S: Stop subscription, cleanup
~~~

Core rules:

1. On a normal subscription, a publisher **must not emit `onNext` beyond total granted demand**.
2. `request(n)` with `n > 0` adds demand; multiple requests accumulate up to a cap and may be interpreted as very large/unbounded demand.
3. `request(0)` or negative values are **invalid** per Reactive Streams; never use them to "pause". To stop receiving temporarily, simply stop requesting more.
4. `cancel()` indicates the subscriber wants no further data. It is not an error and does not undo completed business operations.
5. Only a **subscriber that actually paces its requests** creates useful backpressure. A method returning `Flux` does not guarantee the source at the far end will slow down.

**Backpressure is a flow-control mechanism, not durable storage.** If an external source cannot pause emission, data still needs buffering, dropping, persisting to a store, or an explicitly defined overload policy.

## 3. `REQUEST_N`: how RSocket sends demand over the network

RSocket builds backpressure directly into multi-element interactions. When a subscriber on one side asks for more data, RSocket uses **request N** to cap how many subsequent payloads the peer may emit in that direction.

### 3.1. Related frames

| Frame/signal | Effect | Notes |
| --- | --- | --- |
| `REQUEST_STREAM` | Starts request-stream, carries **initial request N** | Accompanied by route and data/metadata per contract |
| `REQUEST_CHANNEL` | Starts request-channel, including initial request N for responder | Bidirectional streams have independent demand |
| `REQUEST_N` | Grants additional elements the receiver is ready to accept | Applies to the corresponding stream |
| `PAYLOAD` | Carries encoded data/metadata item | Must respect granted demand and stream state |
| `CANCEL` | Requests stopping the interaction/stream | Distinct from temporarily requesting no more |
| `ERROR` | Terminates interaction with error | Does not substitute for backpressure |

For **request-stream**, initial request N travels inside the opening `REQUEST_STREAM` frame; subsequent demand can be sent via `REQUEST_N`. Therefore, do not expect **every** single `request(...)` call to produce a separate `REQUEST_N` frame: demand may be batched into the initial frame or optimized by the implementation.

### 3.2. Backpressure by interaction model

| RSocket interaction | Outcome | Where does backpressure apply? |
| --- | --- | --- |
| Request-response | At most one business reply | No repeated request N needed for single response |
| Fire-and-forget | No business reply payload | Not a stream model with request N |
| Request-stream | Multiple responses from responder | Requester paces how many responses are emitted |
| Request-channel | Bidirectional element streams | Each direction obeys the receiver's demand for that direction |

Example of a finite request-stream:

~~~mermaid
sequenceDiagram
    participant C as Client / requester
    participant R as RSocket responder
    C->>R: REQUEST_STREAM inventory.snapshot (initial N=2)
    R-->>C: PAYLOAD item 1
    R-->>C: PAYLOAD item 2
    Note over R,C: Producer has no further demand for item 3
    C->>R: REQUEST_N(2)
    R-->>C: PAYLOAD item 3
    R-->>C: PAYLOAD item 4
    C->>R: CANCEL
~~~

This diagram illustrates **protocol-level element limits**. Exact frame counts, demand batching, prefetching, fragmentation, and scheduler timing depend on library and transport. One `request(1)` in Reactor does not necessarily map to **exactly one network frame** in every configuration.

### 3.3. Two directions in request-channel

In request-channel, the client sends a `Publisher<RequestItem>` and receives a `Publisher<ReplyItem>`. The **server** controls demand for incoming request items; the **client** controls demand for incoming reply items. Both directions operate independently:

~~~text
Client                                Server
  request items --------------------->  Server receives per server-side demand
  reply items   <---------------------  Client receives per client-side demand

Both directions can send REQUEST_N / CANCEL depending on stream state.
~~~

Do not use a single "window size" variable assuming both directions always advance at the same speed. If one side aggregates multiple request items before emitting replies, bound intermediate queues/buffers and handle stall conditions.

## 4. Server example: emitting a `Flux` on demand

In Spring Boot 3 / Spring Framework 6, `@MessageMapping` can return `Flux<T>` for a request-stream route. The snippet below uses `Flux.range`, a **cold** demand-aware publisher, to demonstrate without external event brokers.

### 4.1. DTOs and responder

~~~java
record SnapshotQuery(String warehouseId) {}

record StockEvent(String warehouseId, int sequence, int available) {}
~~~

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
class StockSnapshotRSocketController {
    private static final Logger log =
        LoggerFactory.getLogger(StockSnapshotRSocketController.class);

    @MessageMapping("inventory.snapshot")
    Flux<StockEvent> snapshot(@Payload SnapshotQuery query) {
        return Flux.range(1, 100)
            .map(sequence -> new StockEvent(
                query.warehouseId(),
                sequence,
                1000 - sequence
            ))
            .doOnRequest(n ->
                log.debug("Downstream requested {} more items", n))
            .doOnCancel(() -> log.debug("Snapshot cancelled"));
    }
}
~~~

When the client subscriber requests data, demand flows through RSocket into the server's Reactor chain. `Flux.range` only emits within remaining demand, so there is no need to collect all 100 events into a `List` upfront.

Here `doOnRequest` logs requests at that operator position. Logged values **need not equal wire `REQUEST_N` counts**: Reactor may prefetch or resize requests between operators. To verify wire behavior, add integration tests over RSocket and frame instrumentation when needed.

### 4.2. Client using RSocketRequester

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeTypeUtils;
import reactor.core.publisher.Flux;

class StockSnapshotClient {
    private final RSocketRequester requester;

    StockSnapshotClient(RSocketRequester.Builder builder) {
        this.requester = builder
            .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
            .tcp("localhost", 7000);
    }

    Flux<StockEvent> snapshot(String warehouseId) {
        return requester.route("inventory.snapshot")
            .data(new SnapshotQuery(warehouseId))
            .retrieveFlux(StockEvent.class);
    }
}
~~~

`retrieveFlux(StockEvent.class)` creates a publisher for response data. Subscription starts when a consumer subscribes, and demand depends on the **downstream operator/subscriber chain**. Calling plain `subscribe(event -> ...)` normally requests an unbounded amount, which does not demonstrate slow-consumer pacing.

## 5. Controlling demand on the client

### 5.1. Using `BaseSubscriber` to see `request(n)` clearly

A learning example with fast processing work:

~~~java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;

Flux<StockEvent> stream = client.snapshot("warehouse-a");

stream.subscribe(new BaseSubscriber<StockEvent>() {
    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        request(1);
    }

    @Override
    protected void hookOnNext(StockEvent event) {
        System.out.println("Received: " + event.sequence());
        request(1);
    }

    @Override
    protected void hookOnError(Throwable error) {
        System.err.println("Stream failed: " + error);
    }

    @Override
    protected void hookOnComplete() {
        System.out.println("Snapshot completed");
    }
});
~~~

At the **Reactive Streams demand** level, this subscriber requests one additional element after processing each item. Never place a **blocking** JDBC/HTTP call inside `hookOnNext`, because callbacks can execute on an event loop or latency-sensitive scheduler. For real I/O, prefer a reactive chain with bounded concurrency; if a blocking API is unavoidable, move it to an appropriate scheduler and cap concurrency.

This demo also omits cancellation handling: in a UI, dispose the `Subscription`/`Disposable` per screen lifecycle when the user stops watching the stream.

### 5.2. Using `concatMap` to tie demand to async processing

Suppose `StockEventStore` is a **non-blocking** event persistence service and `save(...)` completes once saving is confirmed:

~~~java
import reactor.core.publisher.Mono;

interface StockEventStore {
    Mono<Void> save(StockEvent event);
}
~~~

We can process each event sequentially:

~~~java
Mono<Void> consumeInOrder(
        StockSnapshotClient client,
        StockEventStore store) {

    return client.snapshot("warehouse-a")
        .concatMap(event -> store.save(event), 1)
        .then();
}
~~~

Here `concatMap` preserves order and limits inner publisher subscriptions. Argument `1` is the **prefetch** used in this example, avoiding requesting a large batch upfront from upstream. Only when the prior save completes does the chain advance.

If parallel work is allowed, `flatMap` with bounded concurrency can raise throughput:

~~~java
Mono<Void> consumeWithBoundedConcurrency(
        StockSnapshotClient client,
        StockEventStore store) {

    int maxConcurrentSaves = 8;

    return client.snapshot("warehouse-a")
        .flatMap(
            event -> store.save(event),
            maxConcurrentSaves,
            1
        )
        .then();
}
~~~

At most **8 save publishers** are subscribed concurrently via that operator; actual throughput also depends on DB connection pools, threads, CPU, and surrounding operators. `flatMap` does not preserve completion order. When events must update the same record in sequence order, use `concatMap`, key-based partitioning, or ordered synchronization.

**Crucial requirement:** `store.save(event)` must reflect real completion. If the method merely pushes the event into a queue and returns `Mono.empty()`, demand can keep rising even while backend workers fall behind.

## 6. Spring Integration boundary: does demand flow through?

A typical path:

~~~mermaid
flowchart LR
    A["RSocket subscriber"] --> B["RSocket responder / requester"]
    B --> C["Reactive Publisher"]
    C --> D["MessageChannel / IntegrationFlow"]
    D --> E["DB / JMS / Kafka / HTTP adapter"]
~~~

The question is not merely "does RSocket have backpressure?", but **does every component along the chain actually honor downstream demand?**

| Integration boundary | Typical behavior | Risk to control |
| --- | --- | --- |
| RSocket `Flux` → Reactor operator | Demand propagates via Reactive Streams when supported | Operator-introduced prefetch or buffers |
| `DirectChannel` → synchronous handler | Dispatches on caller thread, executes inline | Blocking handlers can stall the caller thread |
| `ExecutorChannel` / executor | Hands off to a thread pool | Executor queue depth and pending tasks |
| `QueueChannel` → poller | Messages queued and polled later | Queue grows fast if producer is unbounded |
| `FluxMessageChannel` | Supports Reactive Streams consumption | Must wire publisher/subscriber properly; buffers and subscriptions still need management |
| Outbound HTTP/JMS/Kafka adapter | Separate protocol and send mechanics | RSocket demand does not automatically flow through every external adapter |

Spring Integration provides reactive flow support, yet **you cannot infer every `MessageChannel` has backpressure just from its name**. For instance, an inbound RSocket handler may take a `Flux` and call a **synchronous** messaging gateway; that bridge must pace concurrent requests or move blocking work onto a suitable scheduler.

### 6.1. Combining RSocket with a synchronous messaging gateway

Suppose the application has a Spring Integration flow enriching each event via a synchronous business step. Example DTOs:

~~~java
record StockView(
    String warehouseId,
    int sequence,
    int available,
    String label
) {}
~~~

Declaring the gateway and IntegrationFlow:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@MessagingGateway
interface StockEnrichmentGateway {
    @Gateway(requestChannel = "stockEnrichmentInput")
    StockView enrich(StockEvent event);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
class StockEnrichmentConfiguration {

    @Bean
    IntegrationFlow stockEnrichmentFlow() {
        return IntegrationFlow.from("stockEnrichmentInput")
            .handle(StockEvent.class, (event, headers) ->
                new StockView(
                    event.warehouseId(),
                    event.sequence(),
                    event.available(),
                    "CHECKED"
                )
            )
            .get();
    }
}
~~~

Responder connecting each `Flux` element to the gateway:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Controller
class StockEnrichedRSocketController {
    private final StockEnrichmentGateway gateway;

    StockEnrichedRSocketController(StockEnrichmentGateway gateway) {
        this.gateway = gateway;
    }

    @MessageMapping("inventory.enriched-snapshot")
    Flux<StockView> snapshot(@Payload SnapshotQuery query) {
        return Flux.range(1, 100)
            .map(i -> new StockEvent(
                query.warehouseId(),
                i,
                1000 - i
            ))
            .concatMap(event ->
                Mono.fromCallable(() -> gateway.enrich(event))
                    .subscribeOn(Schedulers.boundedElastic()),
                1
            );
    }
}
~~~

This is a **bounded bridge**:

1. `Flux.range` produces events only on demand.
2. `concatMap(..., 1)` bounds sequential execution and prefetch in this example.
3. `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` moves the synchronous gateway off the RSocket event loop.
4. The gateway passes the event through `MessageChannel` and `IntegrationFlow` and returns `StockView`.
5. The RSocket response stream emits `StockView` per client demand.

Because the gateway call here is **blocking**, client cancellation does not immediately abort an in-progress call inside the gateway, DB, or another adapter. `boundedElastic()` also does not turn a blocking API into non-blocking. Use truly reactive services when end-to-end cancellation/coordination is needed, or enforce concurrency caps and timeouts on underlying resources.

**Do not register two responders for the same route** if keeping the earlier `inventory.snapshot` example. Here route `inventory.enriched-snapshot` separates the contracts.

### 6.2. When sending messages to a queue or poller

Suppose a fast producer feeds `QueueChannel` while a poller consumes slowly:

~~~text
RSocket inbound
   -> QueueChannel (capacity ?)
   -> poller (maxMessagesPerPoll ?)
   -> handler

If channel accepts/ACKs the send before handler processes:
  upstream completed != business processing completed.
~~~

A bounded queue prevents unbounded memory growth, yet **a full queue causes blocking, errors, or send rejections**, depending on configuration. It will not automatically push demand back to the RSocket client if the bridge simply calls `send(...)` as a side effect and returns immediately.

When designing:

- Set an explicit **capacity** and monitor queued message counts.
- Separate queued acceptance, successful processing, and business commit.
- Cap executor tasks, `maxMessagesPerPoll`, and upstream receive rates.
- For data that cannot be lost, use a durable message store/broker with retry/deduplication policies.
- Avoid assuming cancelling an RSocket stream cancels queued/polled jobs.

## 7. Backpressure cannot solve every source type

### 7.1. Cold sources supporting demand

`Flux.range`, `Flux.fromIterable`, or many reactive-driver publishers wait for downstream demand before emitting. This is the simplest setup to prove `REQUEST_N` works.

~~~java
Flux<Integer> cold = Flux.range(1, 1_000_000)
    .doOnRequest(n ->
        System.out.println("requested = " + n));
~~~

Without `collectList()`, this source never needs to allocate a million objects in memory at once. However, if you add `collectList()` afterward, memory buffering the whole dataset can still be huge.

### 7.2. Hot/push sources that ignore demand

Sensors, legacy library callbacks, UDP receivers, or external brokers can push data continuously even when the RSocket subscriber requests no more. In Reactor, a callback wired via `Flux.create` or a sink without an explicit backpressure policy risks unbounded accumulation.

Anti-pattern example:

~~~java
// Illustrates risk: externalFeed emits at its own pace.
Flux<StockEvent> events = Flux.create(sink ->
    externalFeed.onEvent(sink::next)
);
~~~

`externalFeed` is a placeholder API. This snippet **lacks lifecycle cleanup, buffer limits, error management, and backpressure**—never use it directly in production.

Pick an explicit policy when the source cannot slow down:

| Policy | Tool/example | Best for |
| --- | --- | --- |
| Propagate demand to source | Reactive driver, `sink.onRequest(...)` | Pull-capable sources |
| Bounded buffer, error on overflow | `onBackpressureBuffer(capacity)` + overflow handler | Short bursts without unbounded RAM growth |
| Drop excess elements | `onBackpressureDrop(...)` | Telemetry or metrics that tolerate sample loss |
| Keep latest element | `onBackpressureLatest()` | Dashboard state where intermediate changes can be skipped |
| Persist durably and replay | Broker/event log + checkpoints | CDC, orders, transactions that cannot be lost |
| Reject/pause source | App-level or transport flow control | Upstream capable of pausing |

A **bounded buffer** surfaces overload clearly; it **does not magically make a push source honor demand**. When full, apply an error or drop policy accepted by the business contract. For critical data, never use drop/latest as a "fix" for congestion without replay.

### 7.3. `Flux.interval` and time-driven sources

~~~java
Flux<Long> ticks = Flux.interval(Duration.ofMillis(100));
~~~

A clock-driven source may error if the subscriber does not request items in time; in Reactor, `Flux.interval` can emit an error when demand is missing for a tick. It **differs** from `Flux.range`, which is finite and waits on demand.

To learn demand pacing, start with `Flux.range` or a true `onRequest` source. When using time-driven sources, test zero-demand, full-buffer, and cancellation behaviors.

## 8. Commonly misunderstood Reactor operators

| Operator | Primary meaning | What to watch |
| --- | --- | --- |
| `limitRate(32)` | Splits downstream demand into bounded upstream request batches | Does not prove memory is bounded at every layer |
| `concatMap(mapper, prefetch)` | Preserves order, paces inner publishers and prefetch | Per-item latency can cap throughput |
| `flatMap(mapper, concurrency, prefetch)` | Bounded parallel processing | Does not preserve completion order; bound resources |
| `publishOn(scheduler, prefetch)` | Switches execution context via a prefetched queue | Scheduler queue and pending tasks can build backlogs |
| `onBackpressureBuffer(capacity)` | Buffers when downstream is slow, up to a limit | Set overflow policy; may still request heavily upstream |
| `onBackpressureDrop(...)` | Discards elements that cannot be delivered on time | Use only when losing events is acceptable |
| `onBackpressureLatest()` | Retains latest state when downstream is slow | May skip intermediate states |
| `take(n)` | Completes after n elements and cancels upstream | Terminates stream; distinct from temporarily slowing down |
| `timeout(Duration)` | Errors when waiting too long for next signal | Timeout is not `REQUEST_N` |
| `retryWhen(...)` | Re-subscribes after error | May re-receive data or re-run side effects |

Example of batching upstream requests:

~~~java
Flux<StockEvent> controlled = client.snapshot("warehouse-a")
    .limitRate(32)
    .doOnRequest(n ->
        System.out.println("Consumer requested " + n));
~~~

`limitRate(32)` shapes how **upstream requests** are split into batches; it does not mean "only 32 messages exist in RAM across the entire system", because codecs, other operators' prefetches, queues, drivers, and brokers also hold data. Account for the whole pipeline when sizing memory.

Specifically, `onBackpressureBuffer(...)` often **decouples direct backpressure propagation** from downstream to upstream by absorbing items for later consumption. Never sprinkle buffers casually everywhere and assume end-to-end demand control.

## 9. Calculating load and buffer budgets

A simple operational math check:

- Source emits an average of **500 events/sec**.
- Handler processes only **200 events/sec**.
- The **300 events/sec** surplus must go somewhere: wait at the source, buffer, persist durably, or get dropped.
- Without control, after **10 seconds** roughly **3,000 events** sit unprocessed—before accounting for bursts or metadata/payload sizes.

Backpressure works when **the source can throttle emission** per demand, or when the system enforces clear limits/policies at the boundary of an unthrottlable source. Network bandwidth is only one piece: pressure also hits encode/decode CPU, DB connection pools, memory queues, and blocking task counts.

### Considerations for buffer sizing

For instance, to absorb a brief 2-second burst with a 300 events/sec deficit, the buffer needs at least **600 events** plus safety headroom. Yet picking 600 is only valid when:

1. Bursts and processing rates at target load have been measured.
2. Average and maximum event byte sizes are known.
3. Maximum wait times and overflow policies are defined.
4. Queue depth, memory, latency, and dropped events are monitored.
5. Consequences of data loss/duplicates are accepted and replay exists if required.

**Backpressure does not replace capacity planning.** When a source stays faster than processing capacity over long periods, no finite buffer fixes the root cause; throttle upstream, scale consumers, or change the architecture.

## 10. How do cancellation, timeouts, and resume relate?

Backpressure regulates **wanting more items**; cancellation signals **wanting no more items**; timeouts and resume address different failure modes.

| Mechanism | Meaning | Does not guarantee |
| --- | --- | --- |
| `REQUEST_N` | Grants more demand to the stream | Messages persisted in database |
| `CANCEL` | Requests ending the stream/interaction | Rolling back applied side effects |
| `timeout(...)` | Stops waiting past Reactor deadline | Producer immediately halts blocking work |
| Reconnect | Opens new transport/connection for new requests | Preserving old demand and subscriptions |
| Resume | Attempts recovering stateful RSocket session | Business-layer exactly-once |
| Checkpoints/idempotency | Persists progress and handles duplicates at app layer | Protocol auto-creating a durable event log |

For example, while streaming `inventory.events`, if demand drops to zero while transport stays alive, the stream is simply **waiting for demand**. If the client cancels, the source should clean up resources. If transport drops and resume fails, a new subscription cannot tell which events the consumer already committed; application checkpoints/offsets are needed for safe replay.

### Flows with write side effects

If each item updates inventory or creates an invoice:

~~~text
RECEIVE event #103
  -> validate
  -> apply business change + store checkpoint atomically
  -> COMMIT
  -> allow/request next item
~~~

This is the desired logical sequence. With prefetched streams, **multiple events may already reside in memory before commit**, so never equate `REQUEST_N` with business processing confirmation. If events are critical and must survive restarts, use a durable broker/event store with checkpoints and deduplication rather than relying solely on RSocket flow control.

## 11. Testing demand properly

### 11.1. Reactor unit tests with `StepVerifier`

With Reactor Test (`reactor-test`), start a subscription with **0 initial demand**, then request explicitly:

~~~java
import java.time.Duration;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

Flux<Integer> source = Flux.range(1, 3);

StepVerifier.create(source, 0)
    .expectSubscription()
    .expectNoEvent(Duration.ofMillis(50))
    .thenRequest(2)
    .expectNext(1, 2)
    .thenRequest(1)
    .expectNext(3)
    .verifyComplete();
~~~

Key point: `StepVerifier.create(source, 0)` sets the **test subscriber's initial demand** to 0; this is valid and **differs** from calling `Subscription.request(0)`, which violates Reactive Streams. If code emits `onNext` before the test subscriber grants demand, the test catches the bug.

This unit test only proves the publisher follows Reactive Streams. It **does not yet verify** translating demand into `REQUEST_STREAM`/`REQUEST_N` over the network.

### 11.2. Integration testing over RSocket

When running a real responder (such as `inventory.snapshot`) and `RSocketRequester`:

1. Create a subscriber granting small increments of demand, such as 1, then 2, then 5.
2. Observe actual items received, ordering, and complete/error signals.
3. Observe `doOnRequest` on the server; verify nothing emits before matching demand arrives.
4. Cancel mid-stream; verify cleanup callbacks run and active task/subscription counts do not grow.
5. Add slow processing in the subscriber; monitor throughput, CPU, queues, memory, and wait times.
6. Test hot/`Flux.interval` sources under low demand to verify actual buffer/drop/error policies.
7. Bridge through a Spring Integration gateway/`QueueChannel`; check whether anything receives faster than it processes, and measure backlogs.

The `request(n)` counts in unit tests, `doOnRequest` logs, and wire `REQUEST_N` frames can differ due to prefetching, batching, and initial requests. Base tests on **never emitting past granted demand at each boundary**, alongside resource bounds and business contracts.

### 11.3. Minimum test matrix

| Test | Expectation |
| --- | --- |
| Subscriber has not requested yet | Demand-aware source emits no `onNext` past demand |
| Batched requests 2 → 3 | Receives at most granted demand at the inspected boundary |
| `take(3)` | Downstream completes; upstream cancelled if still active |
| Slow consumer, cold source | Producer paces emission without unbounded queue growth |
| Slow consumer, hot source | Triggers declared bounded buffer/drop/error policy |
| `flatMap(..., 8)` | At most 8 concurrent inner executions at that operator |
| Bridge to synchronous gateway | Does not block event loop and bounds task count |
| Multiple concurrent clients | One client cannot starve all resources |
| Disconnect mid-stream | Proper cancellation/reconnect/resume and checkpoints |
| Side-effecting events then retry | Dedup/idempotency prevents duplicate business execution |

## 12. Common errors and fixes

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Memory grows despite using `Flux` | Fast push producer, `collectList`, or unbounded buffer/queue | Audit each boundary and bound buffers/concurrency |
| `doOnRequest` logs huge numbers | Default subscriber requests unbounded or operator prefetches | Use `BaseSubscriber` to learn; configure pipeline per demand |
| Thinking `request(0)` means "pause" | Misunderstanding Reactive Streams | Stop requesting more, or use a dedicated pause mechanism |
| Stream errors when demand is low | `Flux.interval`/push source does not wait for demand | Use demand-aware source or drop/buffer/error policy |
| RSocket has backpressure yet queue fills | Bridge pushes to channel before downstream commits | Bound capacity, control boundary flow, persist durably if needed |
| `flatMap` corrupts update ordering | Parallel tasks finish out of order | Use `concatMap` or key-partitioning with transactional guards |
| Processing slows down using `concatMap` | Strictly sequential per-item execution | Increase bounded concurrency if business rules allow |
| Stream cancelled yet DB job keeps running | Underlying blocking/queued work already accepted | Set timeouts, lifecycle cleanup, and dedicated job cancellation |
| Critical events lost under drop/latest | Chose a telemetry-oriented policy | Switch to durable event log with replay |
| Request-channel stalls in both directions | Missing demand/overflow or circular dependency between sides | Analyze each direction and intermediate buffers separately |

When debugging, trace in order: **subscriber demand → Reactor operators → RSocket `REQUEST_N`/`PAYLOAD` → responder source → Spring Integration channel → downstream resource**. Attach correlation IDs and stream IDs to telemetry while avoiding logging sensitive payloads.

## 13. Practice exercises

### Exercise A — Observing `REQUEST_N`

Build server `inventory.snapshot` returning 100 events from `Flux.range`. Have the client use `BaseSubscriber` requesting 1, 2, and 5 items; count `onNext` deliveries. If using an RSocket frame inspector, compare the initial `REQUEST_STREAM` and subsequent `REQUEST_N` frames with `doOnRequest` logs. Explain discrepancies caused by prefetching or batching.

### Exercise B — Database writes with bounded concurrency

Implement `StockEventStore.save(event)` returning `Mono<Void>`. Compare `concatMap(..., 1)` against `flatMap(..., 8, 1)` for throughput and commit ordering. For a SKU requiring sequential updates, prove why ordering or transactional guards must be enforced.

### Exercise C — Bridging into Spring Integration

Build a flow through `@MessageMapping` → `StockEnrichmentGateway` → `MessageChannel` → synchronous handler. Run 5 concurrent subscribing clients. Measure active tasks, wait times, and queue depths; explain why `boundedElastic` and concurrency limits are two separate decisions.

### Exercise D — Push sources and overload policies

Simulate a 500 events/sec source while the consumer handles 200 events/sec. Test a bounded buffer, drop/latest, and persisting to a replayable broker. Record lost data, latency, and memory. Pick separate solutions for a temperature dashboard vs. order-change data.

## 14. Key takeaways

- **Backpressure** is how a subscriber paces how many elements a publisher may emit; demand travels via `Subscription.request(n)`.
- For request-stream, RSocket carries **initial request N** in `REQUEST_STREAM` and uses `REQUEST_N` for more. For request-channel, each direction has independent demand.
- `RSocketRequester.retrieveFlux(...)` and `@MessageMapping` can build reactive pipelines, yet you must inspect prefetching, queues, and Spring Integration boundaries to confirm end-to-end demand respect.
- `Flux.range` is ideal for learning demand; hot/push sources may need buffering, dropping, or upstream throttling. No finite buffer can absorb a sustained rate deficit forever.
- `concatMap` preserves order; `flatMap` adds bounded concurrency; `publishOn`, `limitRate`, and `onBackpressure...` operators each affect demand and memory differently.
- **CANCEL, timeouts, reconnect/resume, idempotency, and checkpoints** solve different problems than backpressure. A client requesting more items does not mean prior items committed to business storage.
- When pairing RSocket adapters/gateways with `MessageChannel`, test both Reactive Streams signals **and** actual throughput of the underlying database, queue, poller, or HTTP/JMS/Kafka adapter.

## Further reading

- [Reactive Streams Specification](https://www.reactive-streams.org/): `Publisher`, `Subscriber`, and `Subscription` contracts.
- [RSocket Protocol](https://rsocket.io/about/protocol/): `REQUEST_STREAM`, `REQUEST_CHANNEL`, `REQUEST_N`, `PAYLOAD`, and `CANCEL` frames.
- [Project Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/): backpressure, `BaseSubscriber`, `StepVerifier`, prefetch, and operators.
- [Spring Framework RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): `RSocketRequester`, `@MessageMapping`, and Reactor integration.
- [Spring Integration Reference](https://docs.spring.io/spring-integration/reference/): `MessageChannel`, `FluxMessageChannel`, gateways, pollers, and Reactive Streams support.
