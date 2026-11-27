# Timeout and cancellation in RSocket Adapter

## 1. Context: requests taking too long and clients no longer needing results

In module **SPRING_INTEGRATION_ADAPTERS**, applications use inbound/outbound adapters, gateways, pollers, and `MessageChannel` to exchange messages with external systems; both request/reply contracts, error handling, and connection lifecycles must be controlled. In the **RSocket Adapter** chapter, two common scenarios are **timeouts** when an operation fails to respond on time and **cancellation** when the receiver actively stops an ongoing interaction.

For example, a warehouse management app calls route `inventory.stock` to read stock levels. If the database query takes 15 seconds while the UI only waits 2 seconds, the client should not wait forever. On another route, `inventory.events` returns a continuous stream of events; when the user closes the screen, the client must stop the stream so the server does not keep holding resources.

~~~text
Request-response:
  Client ---- inventory.stock ----> Server -> IntegrationFlow -> DB
  Client -- 2 seconds elapsed --X
  Server may still be running the DB query.

Request-stream:
  Client ---- inventory.events ---> Server
  Client <--- event 101 ----------- Server
  Client <--- event 102 ----------- Server
  Client -- CANCEL ---------------> Server
  Server must stop emitting and release subscription/resources.
~~~

After this lesson, you can:

- Distinguish **client-side timeouts**, **server/IntegrationFlow timeouts**, **disconnect timeouts**, and **business deadlines**.
- Explain how `Mono.timeout(...)`, `Flux.timeout(...)`, and Reactive Streams cancellation affect RSocket.
- Know when RSocket can emit a `CANCEL` frame, and what cancellation **does not guarantee**.
- Design safe cancellation paths across `@MessageMapping`, `MessageChannel`, and messaging gateways.
- Test slow scenarios, clients giving up, stream cancellation, leaked resources, and unknown business outcomes.

## 2. Distinguishing timeout, cancellation, and connection errors

| Term | Who initiates? | What happens | Note |
| --- | --- | --- | --- |
| **Request timeout** | Usually caller-set deadline | Publisher errors if no signal arrives on time | May cancel upstream subscription |
| **Stream idle timeout** | Consumer or producer | No next element within a time window | Differs from total stream duration |
| **Cancellation** | Subscriber no longer needs signals | Sends cancel request upstream | Does not mean side effects rolled back |
| **Connection timeout/keepalive failure** | Transport/RSocket | Peer considered disconnected | Can fail multiple streams together |
| **Business deadline** | Business contract | Rejects or stops overdue tasks | Must be enforced at execution site and state persisted |
| **Retry** | Recovery policy | Re-subscribes/resends operation after error | Can spawn new requests and repeat side effects |

A **timeout** normally terminates with `onError`, such as Reactor's `TimeoutException`. **Cancellation** is a signal from subscriber to publisher; by itself it is **not** `onError`. When a client uses `take(3)`, downstream can complete normally after three elements while upstream receives a cancel signal.

Time limits must carry an unambiguous meaning. Does "2 seconds" mean waiting for **one response**, the maximum gap **between two events**, or the total time allowed for **a business transaction**? Each interpretation requires different code.

## 3. How does RSocket propagate cancellation?

RSocket is a protocol supporting request-response, fire-and-forget, request-stream, and request-channel over transports like TCP or WebSocket. For interactions expecting a response stream, the initiator may lose interest in the result before the interaction finishes.

At the protocol level, RSocket defines a **`CANCEL`** frame carrying the stream ID to ask the peer to end the corresponding stream/interaction. RSocket supports cancellation for applicable interaction models such as request-response, request-stream, and request-channel; **fire-and-forget** has no reply stream for the caller to keep awaiting.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as RSocket server
    participant F as IntegrationFlow
    C->>S: REQUEST_STREAM inventory.events
    S->>F: Subscribe/read data
    S-->>C: PAYLOAD event 101
    S-->>C: PAYLOAD event 102
    Note over C: User closes screen
    C->>S: CANCEL (streamId)
    Note over S,F: Cancel publisher if still active
    S--xF: Cancel subscription/cleanup
~~~

Interpret the scope of `CANCEL` accurately:

1. It is a **request to stop sending/receiving more data** for an RSocket interaction, allowing active resources to be released.
2. A `CANCEL` might not be sent if the stream already finished, the connection already dropped, or the request never hit the wire. Observed behavior depends on cancellation timing.
3. A `CANCEL` frame is **not** a command to roll back a transaction, purge queued messages, or undo REST/API calls already dispatched to another system.
4. The server must use cancellation-aware async APIs or configure explicit cleanup when handlers hold external resources.
5. There may be latency between the peer receiving `CANCEL` and actually halting work; never infer server state solely from closing a screen.

### Backpressure differs from cancellation

For request-stream/channel, RSocket uses item-count requests (**`REQUEST_N`**) to coordinate demand. When the consumer requests no more items, the producer must honor the granted demand. **Backpressure** regulates rate; **cancellation** requests terminating the subscription entirely.

| Signal | Meaning | Example |
| --- | --- | --- |
| `REQUEST_N(5)` | Consumer has demand for 5 more elements | Load next page of events |
| No further request | May be pausing/processing | Pause increasing demand |
| `CANCEL` | Consumer no longer needs the stream | Leaving the dashboard screen |
| `ERROR` | Interaction terminates with error | Decoder or handler throws |
| `COMPLETE` or matching terminal signal | Interaction finished | Finished emitting finite results |

Never build systems assuming "no `REQUEST_N` means the stream cancels itself". An uncancelled stream can keep holding state and resources.

## 4. Reactor timeouts: Mono and Flux have different meanings

### 4.1. `Mono.timeout` for request-response

Suppose the caller allows waiting at most two seconds:

~~~java
import java.time.Duration;
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.core.publisher.Mono;

record StockQuery(String sku) {}
record StockReply(String sku, int available) {}

class StockClient {
    private final RSocketRequester requester;

    StockClient(RSocketRequester requester) {
        this.requester = requester;
    }

    Mono<StockReply> getStock(String sku) {
        return requester.route("inventory.stock")
            .data(new StockQuery(sku))
            .retrieveMono(StockReply.class)
            .timeout(Duration.ofSeconds(2));
    }
}
~~~

`timeout` starts counting from **subscription** to the publisher, not when creating the `Mono` variable. If the deadline expires without a matching result signal, Reactor emits `TimeoutException` and cancels the upstream subscription. When the RSocket request-response is active over a healthy connection, cancellation can propagate as a `CANCEL` frame to the server.

Remember: **a client timeout does not prove the server did nothing**. If the server already committed an inventory update or pushed an event to Kafka, that outcome can persist after the client gives up waiting.

### 4.2. `Flux.timeout` is usually an inter-element timeout

~~~java
import java.time.Duration;
import reactor.core.publisher.Flux;

Flux<InventoryEvent> events = requester
    .route("inventory.events")
    .data(new InventorySubscription("warehouse-a"))
    .retrieveFlux(InventoryEvent.class)
    .timeout(Duration.ofSeconds(5));
~~~

With the `Flux.timeout(Duration)` overload, the timer applies before the first element arrives and **resets for the wait interval before each subsequent element**. An event stream running for hours remains valid as long as an element arrives at least every < 5 seconds.

Never write `Flux.timeout(Duration.ofSeconds(5))` thinking it means "the stream must finish after 5 seconds". If the goal is **capping total viewing duration**, use `take(Duration)`:

~~~java
Flux<InventoryEvent> tenSecondPreview = requester
    .route("inventory.events")
    .data(new InventorySubscription("warehouse-a"))
    .retrieveFlux(InventoryEvent.class)
    .take(Duration.ofSeconds(10));
~~~

`take(Duration)` stops receiving after that duration and normally **completes downstream**, rather than emitting `TimeoutException`. It cancels upstream if the source has not finished. Pick `timeout` when **missing data on time is an error**, and `take` when **time-boxed viewing is a normal completion**.

### 4.3. `take(n)` and explicit disposal

~~~java
Flux<InventoryEvent> firstThree = requester
    .route("inventory.events")
    .data(new InventorySubscription("warehouse-a"))
    .retrieveFlux(InventoryEvent.class)
    .take(3);
~~~

After three elements, downstream completes and upstream receives cancel. Since the client is no longer waiting, the server should release the source subscription. In web or mobile apps, disposing the `Disposable` returned by `subscribe()` is typically tied to the screen/component lifecycle:

~~~java
Disposable subscription = requester
    .route("inventory.events")
    .data(new InventorySubscription("warehouse-a"))
    .retrieveFlux(InventoryEvent.class)
    .subscribe(
        event -> render(event),
        error -> showError(error)
    );

// When screen is closed:
subscription.dispose();
~~~

`render(...)` and `showError(...)` are placeholder UI callbacks. In WebFlux or reactive handler methods, usually **return the `Flux`/`Mono` for the framework to manage subscriptions**, instead of calling `subscribe()` inside the service layer and losing cancellation control.

## 5. Server example: observing cancellation and cleanup

The snippet below illustrates a request-stream endpoint running on Spring Boot 3 / Spring Framework 6. A `Flux.interval` source stops when its subscription is cancelled. Adding `doFinally` distinguishes termination reasons:

~~~java
import java.time.Duration;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;
import reactor.core.publisher.SignalType;

record InventorySubscription(String warehouseId) {}
record InventoryEvent(String warehouseId, long sequence) {}

@Controller
class InventoryRSocketController {
    private static final Logger log =
        LoggerFactory.getLogger(InventoryRSocketController.class);

    @MessageMapping("inventory.events")
    Flux<InventoryEvent> events(@Payload InventorySubscription request) {
        return Flux.interval(Duration.ofMillis(250))
            .map(index -> new InventoryEvent(
                request.warehouseId(),
                index + 1
            ))
            .doOnCancel(() -> log.info(
                "RSocket consumer cancelled warehouse={}",
                request.warehouseId()
            ))
            .doFinally(signal -> {
                if (signal == SignalType.CANCEL) {
                    log.info("Source cleaned after cancel");
                } else {
                    log.info("Source terminated with {}", signal);
                }
            });
    }
}
~~~

When the client calls `take(3)` or cancels the subscription, the endpoint's reactive source receives cancel, and `Flux.interval` stops scheduling emissions per Reactor mechanics. `doFinally` runs on complete, error, and cancel alike, making it suited for shared **resource cleanup** across all termination paths.

If the real source connects to an external service, hook cleanup into the subscription lifecycle. Pseudocode example:

~~~java
Flux<InventoryEvent> fromExternalFeed(String warehouseId) {
    return Flux.create(sink -> {
        ExternalSubscription handle = externalFeed.subscribe(
            warehouseId,
            sink::next,
            sink::error
        );

        sink.onDispose(handle::close);
    });
}
~~~

Here, `externalFeed` and `ExternalSubscription` are **illustrative** APIs, not built-in Spring classes. `onDispose` ensures resource closure when the sink completes, errors, or cancels. Production code must also handle backpressure, race conditions between emitting events and closing the handle, and errors during disposal.

### Cancellation is usually observable on both sides

- **Client:** `doOnCancel` or `doFinally(SignalType.CANCEL)` fires when cancelling the local subscription.
- **Server:** live publishers receive cancel from the RSocket layer, and cleanup callbacks run when the signal reaches that subscription.
- **External systems:** only learn about cancellation if the server **explicitly propagates cancellation intent** to the corresponding HTTP client, Kafka subscription, DB query, or job.

Never assume the server rolled back or aborted a DB query just because the client logged "cancelled".

## 6. Server timeouts and client timeouts must align

Client timeouts protect **the caller's wait time**. Server timeouts protect **server resources**. Align both in time order and per contract:

~~~mermaid
flowchart LR
    C["Client: timeout 2s"] --> R["RSocket handler"]
    R --> I["Spring Integration gateway"]
    I --> S["Service / DB"]
    S --> I
    I --> R
    R --> C
~~~

If the server takes 4 seconds to process while the client waits only 2 seconds, the client may cancel after 2 seconds while the server keeps working. To enforce **execution limits**, place timeouts close to the underlying resource—such as DB query timeouts, HTTP client timeouts, or job deadlines.

### Responder-side timeout

~~~java
import java.time.Duration;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
class StockRSocketController {
    private final StockQueryService queryService;

    StockRSocketController(StockQueryService queryService) {
        this.queryService = queryService;
    }

    @MessageMapping("inventory.stock")
    Mono<StockReply> stock(@Payload StockQuery query) {
        return queryService.findStock(query.sku())
            .timeout(Duration.ofSeconds(4));
    }
}

// Reactive service; internal example calls non-blocking DB/HTTP client.
interface StockQueryService {
    Mono<StockReply> findStock(String sku);
}
~~~

For truly reactive sources, cancel can propagate into the data driver or HTTP client depending on implementation. Even so, an already-committed transaction or operation cannot be "recalled" merely by cancelling; explicit application rules are required.

## 7. Spring Integration boundary: what receives cancellation?

An integration flow typically looks like:

~~~mermaid
flowchart LR
    A["RSocketRequester"] --> B["@MessageMapping / inbound gateway"]
    B --> C["MessageChannel"]
    C --> D["IntegrationFlow"]
    D --> E["Service / DB / external adapter"]
    E --> D
    D --> B
    B --> A
~~~

When `@MessageMapping` returns a `Mono` or `Flux`, Spring can preserve the publisher chain and propagate cancel signals if inner components follow Reactive Streams. However, once a request crosses into a **synchronous messaging gateway** or enters a queue/job, caller cancellation neither recalls the sent message nor guarantees stopping a running handler.

### 7.1. Bridging to a synchronous IntegrationFlow

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

record StockQuery(String sku) {}
record StockReply(String sku, int available) {}

@MessagingGateway
interface StockGateway {
    @Gateway(requestChannel = "stockLookupInput")
    StockReply lookup(StockQuery query);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
class StockFlowConfiguration {
    private final StockRepository repository;

    StockFlowConfiguration(StockRepository repository) {
        this.repository = repository;
    }

    @Bean
    IntegrationFlow stockFlow() {
        return IntegrationFlow.from("stockLookupInput")
            .handle(StockQuery.class, (query, headers) ->
                new StockReply(
                    query.sku(),
                    repository.findAvailable(query.sku())
                )
            )
            .get();
    }
}

interface StockRepository {
    int findAvailable(String sku);
}
~~~

The responder can protect the RSocket event loop using a scheduler:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import java.time.Duration;

@Controller
class StockGatewayResponder {
    private final StockGateway gateway;

    StockGatewayResponder(StockGateway gateway) {
        this.gateway = gateway;
    }

    @MessageMapping("inventory.stock")
    Mono<StockReply> read(@Payload StockQuery query) {
        return Mono.fromCallable(() -> gateway.lookup(query))
            .subscribeOn(Schedulers.boundedElastic())
            .timeout(Duration.ofSeconds(4));
    }
}
~~~

The classes in this section are an **alternative example** to the reactive responder/service earlier; do not declare both `@MessageMapping("inventory.stock")` endpoints simultaneously in the same application. Synchronous work is offloaded from the event loop via `boundedElastic()`. Still, if the client cancels while `repository.findAvailable(...)` is blocked on JDBC, the call may keep running; Reactor does not guarantee immediately halting blocking work or rolling back transactions.

For synchronous resources, coordinate:

1. **Query/driver** or external API timeouts, such as an appropriate query time limit.
2. **Messaging gateway** request/reply timeouts if waiting on an asynchronous reply channel.
3. **RSocket caller/responder** wait limits to protect user experience and resources.
4. **Idempotency, task state, and resource cleanup** once execution has begun.

Putting `Mono.timeout` at the top of the chain does not replace the other three items.

### 7.2. When a flow uses a queue or poller

Suppose an inbound request enters a queue and a poller picks it up later:

~~~text
RSocket request
   -> send message into queue channel
   -> poller processes after 5 seconds

Client times out after 2 seconds
   -> no longer needs reply
   -> message may still be in queue / already picked up by poller
~~~

If work must still execute after the client disconnects (such as generating a report), design the API as **submit job → return job ID → poll status / controlled job cancel**. If work truly must stop, define a `CANCEL_REQUESTED` state and have workers check safe cancellation points; never rely on RSocket `CANCEL` as the sole source of truth.

## 8. Deadlines and time budgets across multiple adapters

A request can traverse a chain:

~~~text
RSocket inbound
  -> Spring Integration channel
  -> HTTP outbound gateway
  -> remote service
  -> database
  -> reply
~~~

If each layer independently sets 5 seconds while the caller only waits 3 seconds, the server may keep consuming resources long after the caller left. Distinguish:

- **Client timeout:** when the caller stops waiting.
- **Overall deadline:** contractual end-to-end completion limit.
- **Per-hop timeout:** time allotted to HTTP, DB, JMS reply, or a specific adapter.
- **Cancellation policy:** when work can abort vs. when it must finish and persist state for caller lookup.

Across multiple services, you can pass a deadline or remaining budget in a validated header, having each layer recompute remaining time against its own clock. For example:

~~~text
Request logical deadline: max 3000 ms
  RSocket + decode + routing: 100 ms spent
  Gateway/HTTP request: granted matching budget
  DB: has own timeout, does not wait past deadline
  Reply: reserve time for encoding and sending back
~~~

This is a **design pattern**; there is no mandatory built-in header named `deadline` in RSocket/Spring Integration. When accepting timestamp deadlines from clients, account for clock skew and bound what clients may request. For critical operations, enforce server-side deadlines using trusted server time and disallow unbounded client extensions.

### Timeout selection guide

| Scenario | What to configure | Reasonable behavior |
| --- | --- | --- |
| Interactive inventory lookup | Client 2–3s; server/service separate limit | Report timeout and allow re-query |
| Long-lived event stream | Appropriate idle timeout or application heartbeat | Avoid short total timeouts that prematurely kill streams |
| Order creation | Deadline + idempotency key | Query status after timeout before retrying |
| Multi-minute report job | Return job ID and track status | Cancel job via controlled business API |
| Flaky RSocket transport | KEEPALIVE / reconnect / resume | Recover connection; handle business timeouts separately |

These durations are illustrative; measure real latencies, system load, and SLA requirements before configuring production.

## 9. Does timeout automatically send CANCEL?

Consider request-response `inventory.stock`:

~~~mermaid
sequenceDiagram
    participant C as Client Reactor
    participant R as RSocket responder
    participant G as IntegrationFlow/DB
    C->>R: REQUEST_RESPONSE inventory.stock
    R->>G: lookup sku
    Note over C: Mono.timeout(2s) expires
    C--xR: CANCEL if stream still active
    C-->>C: onError(TimeoutException)
    Note over G: Synchronous query may still be running
    G-->>R: Late result returned
    Note over R: Caller no longer waiting for reply
~~~

When the upstream subscription is still bound to an RSocket request over an active transport, Reactor cancellation normally translates into sending RSocket `CANCEL`. However, **verify this behavior in your actual setup** rather than treating it as certainty that the server stopped working.

Specifically:

- If the client calls `subscribe()` manually and **never disposes the `Disposable`**, requests can continue even after closing the screen.
- If a server handler calls `subscribe()` on another publisher without lifecycle management, that background work can outlive cancellation.
- Once a message enters a `QueueChannel`, JMS/Kafka, or an executor, cancelling the request subscription does not remove queued work.
- If the server already finished and only the reply was lost, cancellation cannot undo completed work.
- If transport already dropped, cancel signals may never reach the peer; server-side timeouts/cleanup are still essential.

## 10. Timeout errors and retry policies

Timeouts raise the question: "Should we resend?". The answer depends on **operation semantics**, because timeouts never tell you how far the server got.

| Operation | After timeout | Handling |
| --- | --- | --- |
| Read-only `inventory.stock` | Can retry on transient failures | Backoff, retry cap, overall timeout |
| Order-creating `orders.submit` | Outcome may already be committed | Keep idempotency key; check status before retrying |
| `payment.capture` | Hard-to-revert side effects | Never auto-retry blindly; use tokens/idempotency and query transaction |
| `inventory.events` stream | Retry creates a **new** subscription | Use checkpoints/replay/dedup if zero event loss is required |
| `report.cancel` | Stopping a job is separate business logic | Confirm job state; do not confuse with RSocket `CANCEL` |

### Retry for read-only routes only

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

Mono<StockReply> lookupWithRetry(String sku) {
    return Mono.defer(() -> requester
            .route("inventory.stock")
            .data(new StockQuery(sku))
            .retrieveMono(StockReply.class)
            .timeout(Duration.ofSeconds(2)))
        .retryWhen(
            Retry.backoff(2, Duration.ofMillis(300))
                .filter(error -> error instanceof TimeoutException)
        );
}
~~~

This is an **illustrative policy** for side-effect-free queries. In production:

- Classify additional retryable transport errors and exclude validation/authentication failures.
- Account for **overall deadlines**: three attempts of 2 seconds each can exceed user wait budgets.
- Avoid infinite retries or synchronized client retry storms; use backoff and jitter.
- Never reuse this code for write commands lacking idempotency/status lookup.

## 11. Observing and testing timeouts/cancellation

A meaningful test suite must go through a real RSocket responder or an environment replicating the subscription lifecycle. Directly invoking `@MessageMapping` Java methods cannot test `CANCEL` propagation.

### Test matrix

| Case | How to reproduce | What to verify |
| --- | --- | --- |
| Fast request | Server replies before client timeout | Client gets normal `onNext` and `onComplete` |
| Server slower than client timeout | Delay handler past threshold | Client receives timeout error; server tracks execution state |
| Stream cancelled after three events | Client calls `take(3)` | Downstream completes; server stops subscription and cleans up |
| Stream idle too long | `Flux.timeout(Duration)` | Client reports inter-element timeout error; upstream cancelled |
| Stream capped by total duration | `take(Duration)` | Client completes normally without leaking subscriptions |
| Multiple streams on one connection | Cancel one stream | Other streams continue unaffected |
| Client loses network before sending CANCEL | Sever transport | Server cleans up via connection/timeout detection, not solely CANCEL |
| Blocking DB running on client cancel | Configure slow driver | Do not claim rollback; observe query/job and resources |
| Write commits yet reply is lost | Inject fault after commit | Retry with same request ID creates no duplicate record |
| Stream retry without checkpoint | Interrupt then re-subscribe | Exposes duplicate/lost event risks; drive replay design |

### Logging/metrics

Depending on deployment, track:

- Timeout counts per **route**, actual processing durations, and configured timeouts.
- Publisher cancel, complete, and error counts plus active subscriptions.
- Queue/`MessageStore` depth, poller wait times, and tasks finishing after caller departure.
- DB/HTTP/JMS latencies, per-adapter timeout rates, and retry counts.
- Correlation ID, request ID, idempotency key, and post-timeout resolution status.

Never log tokens, PII, or full sensitive payloads just to diagnose timeouts. Pair a "caller timed out" log with a "server completed/failed" log via correlation ID; the two events can occur at different times.

## 12. Troubleshooting

| Symptom | Possible cause | Isolation steps |
| --- | --- | --- |
| Client hits 2s timeout yet server still writes DB | Cancellation does not roll back blocking/transactions | Check DB timeouts, idempotency, and transactions |
| Stream keeps running after closing screen | Subscription undisposed, or detached `subscribe()` on server | Tie lifecycle to `Disposable` and upstream cleanup |
| `Flux.timeout` errors after 5s with no event | Inter-element timeout mistaken for total stream limit | Use heartbeats/longer idle timeout, or `take(Duration)` for total cap |
| Cancelling one stream kills all other streams | Connection failure instead of stream cancel, or broken shared resource cleanup | Separate `CANCEL` frames from transport errors and resource lifecycles |
| Retries create duplicate orders | Treated timeout as guaranteed unprocessed | Use unique request ID per business intent |
| Queued messages still process after cancel | Channel/poller already accepted message | Design state machines and dedicated job cancellation |
| Too-short timeouts fail heavily under load | Unmeasured latency, insufficient downstream budget | Measure p95/p99, tune timeouts/load shedding |
| Work lingers long after client timeout | Outbound HTTP/DB/JMS lacks deadline/timeout | Set explicit timeouts on downstream adapters/clients |
| No `CANCEL` seen in server logs | Request already finished, transport dropped, or frame unsent | Inspect subscriptions, RSocket frames, and cancel timing |
| `onErrorResume` creates illusion of completion | Fallback hides upstream error while side work continues | Audit resource lifecycles and fallback result semantics |

To diagnose, trace in order: **request deadline → Reactor signal (complete/error/cancel) → RSocket stream/transport → Spring Messaging handler → `MessageChannel` → IntegrationFlow → downstream timeout/transaction**. Ensure each layer has matching logs and metrics.

## 13. Practice exercises

### Exercise A — Request-response timeout

Create route `inventory.stock` returning data after an intentional delay. Configure `Mono.timeout(Duration.ofSeconds(2))` on the client. Test server delays of 1 second and 4 seconds; explain why one succeeds and one times out. Record whether the server actually halts work after the client times out.

### Exercise B — Stream cancellation and resource release

Create route `inventory.events` emitting an event every 250 ms. Have the client use `take(3)`. On the server, use `doFinally` and a mock source with `close()` to verify cleanup runs exactly once. Then test cancelling via `Disposable.dispose()` before the first event arrives.

### Exercise C — Timeouts across IntegrationFlow

Design a request flowing through `@MessageMapping` → messaging gateway → `MessageChannel` → slow service. Set an RSocket client timeout, a gateway reply timeout, and a service/DB timeout. For each timeout, note what expires, which signal is emitted, and whether business work may still be running.

### Exercise D — Never retry side effects unconditionally

Simulate route `orders.submit` committing to the DB while its reply is lost. Add `requestId` and a database unique constraint. Retry with the same `requestId` and verify only one order is created. Distinguish subscription cancellation from business transaction cancellation.

## 14. Key takeaways

- **Timeouts** cap waiting time; **cancellation** signals no further interest in a subscription. RSocket provides a `CANCEL` frame to ask for terminating an active stream.
- `Mono.timeout` fits request-response; `Flux.timeout(Duration)` usually guards wait intervals **between** events. `take(Duration)` and `take(n)` complete downstream and cancel upstream when criteria are met.
- RSocket cancellation can propagate through reactive publishers, yet **never automatically rolls back databases, purges queues/jobs, or aborts blocking operations**.
- In Spring Integration, distinguish request timeouts, gateway reply timeouts, downstream adapter timeouts, and end-to-end business deadlines; enforce appropriate limits at each layer.
- A timeout never determines whether side effects committed. **Retrying write commands requires idempotency and status lookup.**
- Tests must observe **Reactor signals**, **server subscriptions**, **external resources**, and **business state** after caller timeouts/cancellation.
