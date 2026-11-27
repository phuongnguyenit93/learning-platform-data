# Streaming, Backpressure, and Long-Lived Connection Lifecycles

In Spring Cloud LoadBalancer, `WebClient` can call a service by **service ID** instead of a fixed host/port address. With normal responses, the request goes to a `ServiceInstance` and completes quickly. Yet when the response is a **long-lived stream** such as Server-Sent Events (SSE) or continuous NDJSON, a single instance selection can last seconds, minutes, or even longer. How you manage **backpressure, connections, cancellation, timeouts, and retries** directly affects resource usage and reliability.

This lesson belongs to the **WebClient** chapter of the **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING** module. The goal is understanding non-blocking reactive communication with `Mono` and `Flux`, how LoadBalancer picks an instance for a stream, the limits of backpressure over HTTP, and applying these alongside **service discovery, health checks, retries, timeouts, and observability**. `RestClient` and OpenFeign can also call by service name, but the examples below focus on `WebClient`'s reactive stream lifecycle.

> Context: uses Spring Boot WebFlux with a compatible Spring Cloud version, Java 17+. The example is a self-contained practice lab requiring no Eureka: two instances are declared using `SimpleDiscoveryClient`. Do not use test endpoints for real data or production traffic.

## 1. How Does Streaming Differ from a Short HTTP Response?

With a standard JSON request:

~~~text
GET /api/items/42  ->  HTTP 200 + one JSON object  ->  End of response
~~~

With server streaming, a single HTTP response can carry many sequential messages:

~~~text
GET /api/stock/events  ->  HTTP 200 Content-Type: text/event-stream
                          event: stock
                          data: {"sku":"sku-42","quantity":8}

                          event: stock
                          data: {"sku":"sku-42","quantity":9}

                          ... continues until closed/cancelled/errored
~~~

Three concepts must be kept distinct:

- **HTTP connection/stream**: the transport channel; in HTTP/1.1 it may hold a connection open long-term, while HTTP/2 can multiplex multiple HTTP streams over one TCP connection.
- **Reactive publisher**: `Flux<T>` represents an asynchronous sequence of multiple elements that may complete, fail, or continue indefinitely.
- **Selected service instance**: where WebClient sends that **specific HTTP request**; LoadBalancer does not automatically route each element inside a response to a new instance.

A `Flux` does not automatically imply a response is streaming over the network: `Flux.just(...)` can emit pre-existing elements. Conversely, `bodyToFlux(...)` with `text/event-stream` or NDJSON can decode items as data arrives.

## 2. Instance Selection Model for a Subscription

Suppose `order-service` calls `catalog-service` via `@LoadBalanced WebClient.Builder`.

~~~mermaid
sequenceDiagram
    autonumber
    participant Caller as order-service
    participant WC as WebClient
    participant LB as Spring Cloud LoadBalancer
    participant Supplier as ServiceInstanceListSupplier
    participant A as catalog-a
    participant B as catalog-b

    Caller->>WC: Subscribe to SSE Flux
    WC->>LB: Select catalog-service
    LB->>Supplier: Fetch candidates
    Supplier-->>LB: [A, B]
    LB-->>WC: Select B
    WC->>B: GET /api/stock/events
    B-->>WC: HTTP 200 text/event-stream
    B-->>WC: SSE event #1
    WC-->>Caller: StockEvent #1
    B-->>WC: SSE event #2
    WC-->>Caller: StockEvent #2
    Note over Caller,B: B holds this stream request until completion/cancel/error
~~~

Key point: **one instance is selected per HTTP request/subscription**; events #1 and #2 do not alternate between A and B via Round Robin. When a **new subscription** or **re-subscription after retry** occurs, LoadBalancer can make a fresh selection, depending on filter behavior, policy, and retry settings.

From this it follows:

1. While B is serving an active stream, a new health check marking B unhealthy **does not guarantee the open stream automatically switches to A**.
2. If B stops abruptly, the stream may emit an error signal or time out. Recovery requires a controlled reconnect/resubscribe policy.
3. New instances appearing in discovery normally affect **new calls**, not re-balancing already-established streams.
4. If some subscribers receive very long-lived streams, they can concentrate on the instances chosen initially; round-robin over **opened connections** does not equate to balancing event count, CPU, or active subscriber count.

## 3. Configuring WebClient to Call by Service ID

In Gradle with a compatible Spring Boot/Spring Cloud BOM:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
~~~

On the caller application, declare two `catalog-service` instances via static discovery:

~~~yaml
server:
  port: 18090

spring:
  application:
    name: order-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:18081
              - uri: http://localhost:18082
~~~

Spring Cloud integrates LoadBalancer into `WebClient.Builder` beans marked with `@LoadBalanced`:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
class CatalogWebClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }

    @Bean
    WebClient catalogWebClient(
            @Qualifier("loadBalancedWebClientBuilder")
            WebClient.Builder builder) {
        return builder
            .baseUrl("http://catalog-service")
            .build();
    }
}
~~~

When calling `catalogWebClient.get().uri("/api/stock/events")`, the host in the base URL is interpreted as a service ID. After choosing an instance, LoadBalancer integration replaces the logical target with the physical address.

**Common mistake:** using `WebClient.create("http://catalog-service")` or a manually constructed builder lacking `@LoadBalanced` configuration while expecting it to use Spring Cloud discovery. In that case requests go to normal DNS instead of passing through LoadBalancer.

## 4. Writing an SSE Server Runnable as Two Instances

To observe long-lived connections directly, this backend example generates one SSE event per second. Start the **same WebFlux application** on two ports with different `instance.id` values.

~~~java
import java.time.Duration;
import java.time.Instant;

import org.springframework.core.env.Environment;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

record StockEvent(
    String sku,
    int quantity,
    String instanceId,
    long sequence,
    Instant generatedAt
) {}

@RestController
class StockEventController {

    private final String instanceId;

    StockEventController(Environment environment) {
        this.instanceId = environment.getProperty(
            "instance.id", "catalog-unknown");
    }

    @GetMapping(
        value = "/api/stock/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    Flux<ServerSentEvent<StockEvent>> events() {
        return Flux.interval(Duration.ofSeconds(1))
            .map(sequence -> {
                StockEvent event = new StockEvent(
                    "sku-42",
                    10 + (int) (sequence % 5),
                    instanceId,
                    sequence,
                    Instant.now()
                );

                return ServerSentEvent.<StockEvent>builder()
                    .id(Long.toString(sequence))
                    .event("stock")
                    .data(event)
                    .build();
            });
    }
}
~~~

You need a Spring Boot application entrypoint, such as a class annotated with `@SpringBootApplication`, along with the `spring-boot-starter-webflux` dependency. Suppose the application is packaged as `catalog-events.jar`:

~~~bash
java -jar catalog-events.jar --server.port=18081 --instance.id=catalog-a
java -jar catalog-events.jar --server.port=18082 --instance.id=catalog-b
~~~

Before using LoadBalancer, confirm both instances serve SSE directly:

~~~bash
curl -N -i http://localhost:18081/api/stock/events
curl -N -i http://localhost:18082/api/stock/events
~~~

curl's `-N` flag disables output buffering when displaying output, making continuous SSE messages easy to observe. Stop with Ctrl+C.

**Note on demo data:** `sequence` generated by `Flux.interval` restarts for each subscription rather than acting as a durable offset. Therefore, this example **does not guarantee replay** or exactly-once delivery on reconnect. Production requires a durable event source and stable ID/cursor mechanism.

## 5. Reading SSE with WebClient and `bodyToFlux`

Spring Framework provides `ServerSentEvent<T>` to represent SSE ID, event name, and data. Use `ParameterizedTypeReference` to preserve the generic type of the data:

~~~java
import java.util.Objects;

import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Flux;

@Service
class CatalogEventGateway {

    private final WebClient catalogWebClient;

    CatalogEventGateway(WebClient catalogWebClient) {
        this.catalogWebClient = catalogWebClient;
    }

    Flux<StockEvent> stockEvents() {
        return catalogWebClient.get()
            .uri("/api/stock/events")
            .accept(MediaType.TEXT_EVENT_STREAM)
            .retrieve()
            .bodyToFlux(
                new ParameterizedTypeReference<
                    ServerSentEvent<StockEvent>>() {}
            )
            .map(ServerSentEvent::data)
            .filter(Objects::nonNull);
    }
}
~~~

`StockEvent` on the caller must have JSON-compatible fields matching the backend, such as the same five-field record. The publisher returned from `stockEvents()` is typically **cold** with respect to the HTTP request: each subscription can initiate a new request, corresponding to one instance selection and a separate SSE stream.

If you only need the payload and not the ID or event name, appropriate decoders can read it directly; however, if reconnect/replay is anticipated, preserve full `ServerSentEvent<T>` to capture `id()`.

### Streaming Forward to the Caller's Client

Example of a WebFlux controller acting as a stream proxy:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

@RestController
class StockStreamController {

    private final CatalogEventGateway gateway;

    StockStreamController(CatalogEventGateway gateway) {
        this.gateway = gateway;
    }

    @GetMapping(
        value = "/demo/stock-stream",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    Flux<StockEvent> stockStream() {
        return gateway.stockEvents();
    }
}
~~~

Start the stream through the caller:

~~~bash
curl -N http://localhost:18090/demo/stock-stream
~~~

Inspect each event's `instanceId` field: within a normal subscription, consecutive events come from the same instance. Opening **two curl terminals** creates two separate subscriptions, which may be routed to different instances.

Because WebFlux manages the HTTP request's subscription, the controller simply **returns the publisher** without calling `subscribe()` manually. When downstream disconnects, cancellation normally propagates upstream to release the running request.

## 6. Subscription, Demand, and Three Terminal Signals

Reactive Streams defines the protocol between publisher and subscriber:

1. Subscriber receives `onSubscribe(subscription)`.
2. Subscriber expresses demand via `request(n)` with positive `n`.
3. Publisher emits at most the amount of items matching unfulfilled demand via `onNext`.
4. The stream terminates via **`onComplete`**, **`onError`**, or subscriber calling **`cancel`**.

A simple diagram:

~~~mermaid
sequenceDiagram
    participant S as Subscriber
    participant P as Publisher
    S->>P: subscribe()
    P-->>S: onSubscribe(subscription)
    S->>P: request(2)
    P-->>S: onNext(event1)
    P-->>S: onNext(event2)
    Note over P,S: Without new demand, must not exceed request(n) contract
    S->>P: request(1)
    P-->>S: onNext(event3)
    S->>P: cancel()
    Note over P,S: Stop emitting and clean up resources
~~~

**Backpressure** means downstream demand can influence upstream emission or buffering rates inside a reactive pipeline. Yet an important limit must be understood: **an external SSE server is not obliged to understand or honor Reactor's `request(n)` demand**.

`WebClient.bodyToFlux` and decoders integrate demand with receiving and decoding. However, sockets, HTTP buffers, the TCP receive window, HTTP/2 flow control, and how the server sends data determine how many bytes actually keep arriving. Backpressure in a Java pipeline **is not an end-to-end guarantee** that the server stops producing events when the subscriber slows down.

### Subscriber Overload Example

If the server emits 1,000 events/second while the consumer processes only 100 events/second, storing all pending events grows rapidly. Increasing buffer sizes without bounds merely postpones running out of memory.

Choose an explicit policy: slow down the source, bound concurrency, coalesce events, drop intermediate messages only when business rules allow, or reject/close the connection so clients reconnect and resume from a durable source.

## 7. Backpressure Operators: Using the Right Tool for the Job

| Operator | Purpose | Pitfall to Avoid |
|---|---|---|
| `limitRate(n)` | Tunes upstream request batch size | Not an events/sec cap and does not automatically slow external servers |
| `onBackpressureBuffer(...)` | Buffers events when downstream lags | Unbounded buffers can exhaust RAM; specify capacity and overflow policy |
| `onBackpressureDrop(...)` | Drops events when there is no demand | Unsuitable for transactions requiring every event to be processed |
| `onBackpressureLatest()` | Keeps the latest event, dropping older ones | Suits snapshots/state updates; unsuitable for audit logs |
| `sample(Duration)` | Samples periodically, reducing observation rate | Drops intermediate events |
| `flatMap(..., concurrency)` | Limits concurrent asynchronous operations | Does not directly throttle network rate; event order may change |
| `concatMap(...)` | Processes sequentially, preserving order | Throughput drops if any task is slow |

For **price updates or snapshot-style stock feeds** for a UI, keeping only the latest state is sometimes acceptable. For **ledgers, money transfers, orders, or ordered CDC**, dropping events violates the contract; use a durable broker, offsets, replay mechanisms, and idempotent handling.

### Example Controlling Concurrent Work

Suppose `persistAsync(event)` returns `Mono<Void>` from a **non-blocking** storage library:

~~~java
Flux<StockEvent> events = gateway.stockEvents();

Flux<Void> processed = events
    .limitRate(32)
    .flatMap(event -> persistAsync(event), 4);
~~~

`flatMap(..., 4)` caps concurrent async operations in this processing stage at four. `limitRate(32)` tunes upstream demand; it is **not** equivalent to "receive only 32 events/second." If order must be preserved, consider `concatMap` or an appropriate serialization strategy.

This example is an illustrative pipeline snippet: `persistAsync` is an application-implemented function, not a built-in Spring Cloud API.

### Example Keeping Only the Latest State

~~~java
Flux<StockEvent> latestForUi = gateway.stockEvents()
    .onBackpressureLatest()
    .sample(Duration.ofSeconds(1));
~~~

This fits when each event represents a **current snapshot** of inventory and users do not need every intermediate value. It is **unsuitable** if each event is a `+1` or `-1` delta that must all be applied; dropping an event yields an incorrect total.

If choosing `onBackpressureBuffer`, set a capacity limit and decide explicitly whether overflow errors, drops data, or disconnects; never use an unbounded buffer for streams of indefinite length.

## 8. Never Block the Event Loop While Processing Events

`WebClient` with Reactor Netty normally uses the event loop to perform network I/O and push signals through reactive pipelines. Calling blocking functions (plain JDBC, `Thread.sleep`, slow file handling) directly inside `map`, `doOnNext`, or callbacks on the event loop can stall many connections simultaneously.

**Do not:**

~~~java
return gateway.stockEvents()
    .doOnNext(event -> blockingRepository.save(event));
~~~

If forced to integrate a blocking library, isolate it on an appropriate scheduler and bound concurrency:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Flux<StockEvent> saved = gateway.stockEvents()
    .flatMap(event ->
        Mono.fromCallable(() -> blockingRepository.save(event))
            .subscribeOn(Schedulers.boundedElastic()),
        4
    );
~~~

`boundedElastic` assists with bounded blocking work, yet it does not convert a blocking API into non-blocking. Monitor connections, queued tasks, and thread exhaustion risks; if a reactive database driver exists, prefer a non-blocking pipeline from the start.

Never call `block()`, `blockLast()`, or `toIterable()` inside a reactive WebFlux handler: those operations block threads and can stall the event loop.

## 9. Lifecycle of a Long-Lived Streaming Connection

An SSE subscription typically passes through these phases:

~~~mermaid
stateDiagram-v2
    [*] --> NEW
    NEW --> SELECTING: subscribe
    SELECTING --> CONNECTING: ServiceInstance selected
    SELECTING --> FAILED: no instance
    CONNECTING --> STREAMING: HTTP 200 and receiving body stream
    CONNECTING --> FAILED: connection error / timeout
    STREAMING --> STREAMING: receive next event
    STREAMING --> COMPLETED: server closes normally
    STREAMING --> FAILED: I/O error / read timeout
    STREAMING --> CANCELLED: subscriber cancels
    FAILED --> RETRYING: policy permits
    RETRYING --> SELECTING: re-subscribe, select new instance
    COMPLETED --> [*]
    CANCELLED --> [*]
    FAILED --> [*]
~~~

Manage each phase explicitly:

- **Opening**: acquires a connection or logical HTTP stream; may wait in the connection pool.
- **Running**: holds transport and decoder resources throughout the response; the request does not finish after the first event.
- **Server completes**: handles completion; physical connections can only be reused under HTTP client/transport conditions.
- **Errored**: releases resources and decides whether to retry/reconnect; never retain publishers indefinitely in memory.
- **Cancelled**: stops reading upstream and releases corresponding resources; exact behavior depends on connector, socket state, and protocol.

With HTTP/1.1, an open SSE response generally occupies one active connection. With HTTP/2, multiple logical streams can share one TCP connection, **yet each stream still consumes server and client resources**. Do not treat "TCP connection count" alone as sufficient for assessing streaming load.

### Why Does the Connection Pool Require Attention?

A caller with 500 users holding simultaneous SSE connections to the same service ID maintains hundreds of logical requests. If pool/transport or server limits are low, new connections queue for resources; prolonged pending acquisition causes errors or timeouts.

For long-lived connections, measure:

| Metric | Purpose |
|---|---|
| Active/pending/idle connections | Does the pool still have capacity for new requests? |
| Active SSE/HTTP streams | How many streams are currently held open? |
| Stream duration and received event count | Are streams healthy or stalled? |
| Reconnect frequency / I/O errors | Are clients flapping across instances? |
| Heap/direct memory, decoder buffers | Are buffers leaking or bloating? |
| Selected instance and streams per instance | Is LoadBalancer creating connection hotspots? |
| Time-to-first-event and inter-event interval | Are there heartbeat or data-source issues? |

Measuring pool metrics depends on the connector (e.g., Reactor Netty) and observability setup; not every application gets all these labels out of the box.

## 10. Timeouts and Heartbeats for Non-Terminating Streams

For short HTTP responses, teams often configure small response/read timeouts. Yet SSE may **stay intentionally silent** for long stretches when no events occur. If the HTTP client interprets silence as missing data past the timeout, it can close a healthy stream.

Distinguish:

- **Connect timeout**: limits time to open a connection to the instance.
- **Response/read timeout**: depending on HTTP connector, may limit periods with no data arriving on the connection/response.
- **Time-to-first-event**: time from subscribe until the first message arrives.
- **Application idle deadline**: custom threshold set by the application to detect stalled streams per business requirements.

Example Reactor Netty configuration for a client **used with SSE events/heartbeats spaced under 45 seconds apart**:

~~~java
import java.time.Duration;

import io.netty.channel.ChannelOption;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

@Configuration(proxyBeanMethods = false)
class StreamingClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        HttpClient httpClient = HttpClient.create()
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3_000)
            .responseTimeout(Duration.ofSeconds(45));

        return WebClient.builder()
            .clientConnector(new ReactorClientHttpConnector(httpClient));
    }
}
~~~

This is an **alternative configuration** to the builder bean presented in section 3, not a second bean to register under the same name. `responseTimeout` in Reactor Netty must be understood per connector mechanics and version: on streams with silent gaps exceeding the threshold, requests can be closed even while the socket remains alive. Never pick a 45-second timeout arbitrarily without verifying event frequency, heartbeats, and infrastructure proxies/load balancers.

### Heartbeat

An SSE server can send comment lines starting with `:` per the SSE format or emit a heartbeat event to keep the channel alive. Conceptual example:

~~~text
: heartbeat

event: stock
data: {"sku":"sku-42","quantity":8}

: heartbeat
~~~

Heartbeats help detect or prevent proxies/clients from closing idle connections, but must align with timeouts across every layer: server, ingress, gateway, proxy, connector, and application. Avoid overly frequent heartbeats when subscriber counts are large.

**`Flux.timeout(Duration)`** can enforce an inter-event deadline, though it is not identical to an HTTP connector byte-read timeout; an SSE comment can keep a socket alive without emitting a `StockEvent` item. Therefore, configuring both requires knowing exactly which signal each monitors.

## 11. Cancellation: Closing Requests When Users Leave the Page

If a controller returns `Flux` directly, WebFlux usually forwards cancellation signals from disconnected HTTP clients to the upstream publisher. You can add lifecycle logs to verify:

~~~java
import reactor.core.publisher.SignalType;

Flux<StockEvent> stream = gateway.stockEvents()
    .doOnSubscribe(s -> log.info("SSE subscribed"))
    .doOnCancel(() -> log.info("SSE cancelled"))
    .doFinally(signal -> log.info("SSE finished: {}", signal));
~~~

`doFinally` runs when the stream completes, errors, or is cancelled; `SignalType` can be `ON_COMPLETE`, `ON_ERROR`, or `CANCEL`. The snippet assumes an application-declared logger named `log`.

In unit/integration tests, use `take(5)` to intentionally terminate a long subscription after five items:

~~~java
Flux<StockEvent> fiveEvents = gateway.stockEvents().take(5);
~~~

Once five items arrive, `take` cancels upstream and releases that subscription per reactive lifecycle rules. Do not expect every SSE stream to close automatically after five events; this is a caller-side limit added to bound test duration.

**Avoid calling `subscribe()` manually in a service** just to make an HTTP request "run immediately." Losing the reference to `Disposable` makes cancelling on user disconnect difficult. Controllers should return publishers for the framework to manage; if a genuine background subscription is needed, own and dispose of it cleanly with application lifecycle.

## 12. Handling HTTP 4xx/5xx and Mid-Stream Errors

With `retrieve()`, initial HTTP `4xx/5xx` statuses are typically represented as `WebClientResponseException` unless customized with `onStatus`:

~~~java
Flux<ServerSentEvent<StockEvent>> events =
    catalogWebClient.get()
        .uri("/api/stock/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .retrieve()
        .onStatus(
            status -> status.value() == 404,
            response -> Mono.error(
                new IllegalStateException("SSE endpoint not found"))
        )
        .bodyToFlux(
            new ParameterizedTypeReference<
                ServerSentEvent<StockEvent>>() {}
        );
~~~

`onStatus` handles only **HTTP response statuses**. If LoadBalancer fails to find an instance, connect times out, DNS fails, or a connection resets mid-stream, there may be no HTTP response for `onStatus` callbacks to inspect.

Once the server has sent HTTP 200 and started streaming, a mid-stream failure **cannot retroactively change that response's already-sent status to 503**. Typically the stream emits an error/cancel/close signal. If an SSE message carries a business payload like `{"error":"..."}`, that is a **data event** requiring its own contract, not automatically equivalent to HTTP 5xx.

### Pitfall: Swallowing Errors into an Empty Stream

~~~java
// Caution: dropping all errors makes it hard for callers to know data was interrupted.
return gateway.stockEvents()
    .onErrorResume(error -> Flux.empty());
~~~

This snippet can make a stream appear to finish cleanly to callers even though a dependency failed. Only use such fallbacks when business semantics accept it and ensure observability/alerting exists. For inventory or pricing feeds, silent truncation can be more dangerous than surfacing a clear error.

## 13. Retry and Reconnect: Re-Subscribing Rather Than Resuming the Old Socket

For long-lived streams, retrying is not just "re-running a short request." When a connection breaks, a new subscription can select a different instance. However, the producer does not automatically know which events the subscriber received prior to failure.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant LB as LoadBalancer
    participant B as catalog-b
    participant A as catalog-a

    C->>LB: Subscribe SSE
    LB-->>C: Select B
    C->>B: GET /events
    B-->>C: event id=101
    B-->>C: event id=102
    Note over B: B stops abruptly
    B--xC: Stream errors
    Note over C: Bounded retry/backoff
    C->>LB: Re-subscribe
    LB-->>C: May select A
    C->>A: GET /events (cursor if available)
    A-->>C: Resume or replay per contract
~~~

Example of **bounded** retry for recoverable I/O errors:

~~~java
import java.time.Duration;

import org.springframework.web.reactive.function.client.WebClientRequestException;
import reactor.util.retry.Retry;

Flux<StockEvent> resilient = gateway.stockEvents()
    .retryWhen(
        Retry.backoff(5, Duration.ofSeconds(1))
            .maxBackoff(Duration.ofSeconds(15))
            .filter(error ->
                error instanceof WebClientRequestException)
    );
~~~

This code is only a minimal example:

- `retryWhen` re-subscribes after matching errors; each retry may re-run instance selection.
- After exhausting allowed attempts, the final error must still be handled/observed; never create uncontrolled infinite reconnect loops.
- Server errors arriving as HTTP `503` may need different policies and `Retry-After`; do not blindly retry all `4xx` or JSON errors.
- Some mid-stream connection failures may surface as exception types other than `WebClientRequestException`. Inspect your connector's actual exception classes/causes and tune predicates accordingly.
- Retrying after receiving events can **duplicate events** or **leave gaps**, even when the new request succeeds.

### `Last-Event-ID` and Replay

SSE supports an `id` field on each event; clients can send a `Last-Event-ID` header upon reconnecting. With `WebClient`, the application **must maintain cursor/reconnect logic itself** if this feature is desired; the simple `retryWhen` above does not automatically carry the latest received event ID.

Example sending a caller-stored cursor:

~~~java
Flux<ServerSentEvent<StockEvent>> eventsFrom(String lastId) {
    return catalogWebClient.get()
        .uri("/api/stock/events")
        .headers(headers -> {
            if (lastId != null && !lastId.isBlank()) {
                headers.set("Last-Event-ID", lastId);
            }
        })
        .accept(MediaType.TEXT_EVENT_STREAM)
        .retrieve()
        .bodyToFlux(
            new ParameterizedTypeReference<
                ServerSentEvent<StockEvent>>() {}
        );
}
~~~

This is only **building the request with a cursor**, not a complete reconnect implementation. To resume accurately from the point of interruption, the server must:

1. Emit **system-wide stable event IDs** (not counters resetting per connection).
2. Persist events in a store replayable by ID/offset.
3. Allow any instance chosen on reconnect to access the same data store or compatible forwarding mechanism.
4. Define rules when cursors expire, replay data is gone, or clients receive duplicates.
5. Support idempotent/deduplicating processing on consumers where needed.

In the `Flux.interval` example from section 4, event IDs repeat on every subscription, so `Last-Event-ID` **is insufficient for accurate recovery**. Never claim exactly-once delivery merely because retry and `Last-Event-ID` were added.

## 14. LoadBalancer, Health Checks, and Open Connections

LoadBalancer picks candidates from `ServiceInstanceListSupplier`. The supplier chain can combine discovery, caching, zone preferences, or health checks. Those mechanisms steer **newly opened requests** away from unsuitable instances, but they do not migrate an already-open SSE response to another server.

Example:

| Event | Subscription Currently Receiving from B | New Subscription |
|---|---|---|
| B stays healthy | Continues receiving events | May select A or B |
| Health check marks B unhealthy while socket stays open | May continue receiving from B | Can avoid B per supplier policy |
| B stops, TCP resets | Stream errors/cancels; requires reconnect | May select A if A is in list |
| A newly added to discovery | B's stream does not move to A | May select A once supplier refreshes |
| All instances filtered out | Open streams do not necessarily drop immediately | New requests may fail during selection |

Health behavior when **no healthy instances remain** may fall back depending on supplier/version. Never assume every case returns an empty list; verify the actual candidate set.

If the application requires **sticky streaming sessions** or state stored only on B, reconnecting to A loses state. In those scenarios, design a shared event store, session replication, or controlled routing affinity rather than expecting Round Robin to preserve continuity.

## 15. Observing Long-Lived Streams in Production

For SSE, counting HTTP requests alone is insufficient. One request can run for an hour and carry millions of events.

| Signal Group | Suggested Measurements |
|---|---|
| Load balancing | Service ID, selected instance, stream open rate per instance |
| Connections | Active SSE streams, active/pending connections, connection failures |
| Stream quality | Time-to-first-event, inter-event spacing, stream length |
| Backpressure | Consumer throughput, bounded queue size, overflow/drop counts |
| Retries | Reconnect count, backoff, disconnect reason, and post-reconnect instance |
| Health | Discovery instance set, probe status, convergence time |
| Data | Latest event ID, duplicate/gap counts if replay exists |
| Resources | Heap/direct memory, CPU, event-loop latency, pool saturation |

You can combine Micrometer/Actuator, Reactor Netty metrics, server metrics, and `doOnSubscribe`/`doFinally` lifecycle logs. Use a consistent correlation/trace ID to tie stream open, instance selection, and stream close together. Avoid logging full SSE payloads or putting unbounded event IDs/user IDs into metric tags due to security and cardinality concerns.

### Lab Verifying Cancellation and Instance Switching

1. Start two backends on ports `18081`, `18082` and the caller on `18090`.
2. Open `curl -N http://localhost:18090/demo/stock-stream`. Record `instanceId` from events; verify events within one connection come from a single instance.
3. Open several additional terminals/consumers; observe independent subscriptions and LoadBalancer distribution.
4. Stop a consumer with Ctrl+C; confirm `doOnCancel` or `doFinally(CANCEL)` logs and active stream count drops.
5. Stop the backend serving an active stream; observe error/disconnect behavior. If a retry policy is active, inspect re-subscription and the newly selected instance.
6. Restart the backend; verify new requests can route to it once discovery/supplier refreshes.
7. Deliberately slow down a consumer; measure queues/memory, then test bounded concurrency or business-appropriate drop policies.
8. Increase concurrent SSE connections in a test environment to test pool limits, pending acquisition, and server capacity. Never run this stress test against a live user-facing environment.

Results to record:

| Scenario | Expected Observation | Crucial Distinction |
|---|---|---|
| Single SSE subscriber | One instance serves the entire stream | Does not Round Robin per event |
| Multiple subscribers | Each subscription can select independently | Fairness in connection count differs from load fairness |
| Client cancels | Upstream cancelled and resources freed | Avoid leaking stray background subscriptions |
| Backend dies mid-stream | Error or connection close | Already-sent HTTP status does not turn into 503 |
| Reconnect | New request and potential new instance choice | Event replay does not happen automatically |
| Slow consumer | Buffers/concurrency expose bottlenecks | Demand does not always throttle server speed |
| Heartbeat slower than timeout | May close due to idle timeout | Connection liveness differs from business events |
| Health excludes B | New requests can avoid B | Existing streams do not auto-migrate |

## 16. Common Design Mistakes

- Assuming `@LoadBalanced` picks a new instance for **each event** in an SSE response; in reality it selects the target when sending the HTTP request.
- Using `WebClient.create()` instead of a `@LoadBalanced` builder and expecting service-ID URLs to go through Spring Cloud discovery.
- Calling `collectList()` or `blockLast()` on an infinite `Flux`: requests never complete or memory grows unboundedly.
- Using Reactor `cache()` on an infinite `Flux` without history bounds: can retain unbounded emitted events, completely different from LoadBalancer's instance cache.
- Using unbounded `onBackpressureBuffer()` when the server emits faster than the subscriber processes.
- Using `onBackpressureLatest()` for business events that must never be dropped.
- Calling blocking code directly on the Reactor event loop.
- Opening subscriptions via manual `subscribe()` without retaining the `Disposable` to cancel later.
- Setting read/response timeouts shorter than event/heartbeat intervals.
- Retrying indefinitely without ensuring replay, idempotency, and duplicate/gap handling.
- Grouping initial HTTP status errors together with mid-stream I/O errors without trace differentiation.
- Measuring only request rate while ignoring concurrent streams, event rate, connection pools, and stream lifetimes.

## 17. Implementation Checklist and Conclusion

Before releasing a streaming service using WebClient with Spring Cloud LoadBalancer, answer:

1. Is this continuous SSE/NDJSON streaming, or finite JSON better served by `Mono<T>`?
2. Are `@LoadBalanced WebClient.Builder` and service IDs aligned with discovery?
3. For each subscription, is it understood that the instance is **selected once** and kept for the duration of that HTTP response?
4. Does the stream ever finish naturally? Who cancels it when downstream disconnects?
5. Can Reactor demand reach the real source, or does it only affect client buffers/decoders?
6. For slow consumers, is the policy a bounded queue, snapshot dropping, load shedding, or replay?
7. Is any blocking task running on the event loop?
8. Do connect, response/read idle, and application idle timeouts align with heartbeats?
9. Are active connections/streams and pending acquisitions bounded, measured, and alerted on?
10. When retrying, are attempt counts bounded and is a cursor/`Last-Event-ID` provided if zero data loss is required?
11. If reconnecting to another instance, can both access the same event source and replay mechanism?
12. Are health checks and discovery designed for **new requests**, rather than assuming open streams auto-migrate?
13. Do logs/traces clearly distinguish instance selection, initial response, I/O failure, cancellation, and reconnect?

**Core principle:** `WebClient` supports reactive streaming responses, **yet backpressure is only effective across components that honor demand**; it does not fully throttle HTTP server emission rates by itself. Spring Cloud LoadBalancer selects a `ServiceInstance` **per HTTP request** rather than distributing individual SSE events. Operating long-lived connections reliably requires combining streaming decoders, lifecycle-correct cancellation, bounded concurrency and buffers, heartbeat-aligned timeouts, well-defined retry/replay semantics, and continuous per-instance load observability.
