# Reactive Types and Backpressure in Spring Integration WebFlux

## 1. Core Problem: Receiver Processes Slower Than Sender

Imagine an integration flow receiving order events over HTTP, transforming data, and forwarding it to a storage service or broker. During traffic spikes, the HTTP layer can receive data faster than the business processing layer can keep up. If messages keep arriving and accumulating without bounds, the application will suffer rising memory usage, higher latency, and eventually resource exhaustion. If threads are held waiting on each connection or I/O operation, concurrency capacity is also constrained.

In the **WebFlux Adapter** chapter of the **SPRING_INTEGRATION_ADAPTERS** module, we use inbound/outbound adapters, gateways, pollers, and `MessageChannel`s to connect external systems over HTTP, files, SFTP, JMS, AMQP, Kafka, and databases. **Reactive types** describe how a component emits or consumes data asynchronously; **backpressure** lets the receiver signal how much data it is ready to handle. Together, these two concepts determine whether combining Spring WebFlux with Spring Integration runs stably under load.

Real-world example: an external HTTP service emits a stream of delivery status updates. Spring Integration ingests the data, reconciles orders in a database, and emits events to Kafka. If the database can only handle a bounded number of concurrent messages, the ingestion flow needs throttling or bounded buffering; merely having `WebClient` or `Flux` in the configuration **does not automatically solve** this problem.

~~~mermaid
flowchart LR
    A["Reactive HTTP source"] -->|"Publisher: data"| B["MessageChannel"]
    B --> C["Consumer / Handler"]
    C --> D["Database or broker"]
    C -.->|"request(n): demand if in the same Reactive Streams chain"| B
    B -.->|"demand propagates if source supports it"| A
~~~

Demand signaling in the diagram only applies when components belong to **the same compatible publisher/subscriber chain**. Crossing a plain queue, a synchronous API, or a broker with its own ACK protocol creates a boundary across which backpressure cannot automatically propagate.

## 2. What Contract Is Reactive Streams?

Reactive Streams specifies asynchronous element exchange with control over how much data is requested. Four primary interfaces:

| Component | Role | Related example |
|---|---|---|
| `Publisher<T>` | Supplies a sequence of elements of type `T` to a subscriber | `Flux<OrderEvent>`, `Mono<Quote>` |
| `Subscriber<T>` | Registers to receive elements; handles data/completion/error signals | Consumer at the end of a reactive flow |
| `Subscription` | Link between publisher and subscriber; has `request(n)` and `cancel()` | Request 8 more elements or stop receiving |
| `Processor<T,R>` | Both receives and emits data; defined in the spec | Transformations between source and sink |

Typical signal sequence:

1. Subscriber registers with publisher via `subscribe(...)`.
2. Publisher invokes `onSubscribe(subscription)`.
3. Subscriber calls `request(n)`, with positive `n`, to grant *demand*.
4. Publisher emits **no more than the granted demand** via `onNext(item)`, or terminates via `onComplete()` or `onError(error)`.
5. Subscriber may request more or `cancel()` when no longer needing data.

~~~mermaid
sequenceDiagram
    participant Pub as Publisher
    participant Sub as Subscriber
    Sub->>Pub: subscribe()
    Pub-->>Sub: onSubscribe(subscription)
    Sub->>Pub: request(2)
    Pub-->>Sub: onNext(A)
    Pub-->>Sub: onNext(B)
    Note over Pub,Sub: Publisher waits for further demand
    Sub->>Pub: request(1)
    Pub-->>Sub: onNext(C)
    Pub-->>Sub: onComplete()
~~~

**Backpressure does not mean automatically slowing down every external data source.** It works directly when the publisher honors demand. With an HTTP webhook, a partner system can still send additional requests independently; with Kafka/JMS, pausing or limiting consumption requires client/broker-specific coordination mechanisms.

## 3. Common Reactive Types

Project Reactor is the reactive foundation used by Spring Integration, with two most familiar types:

| Type | Potential item count | Terminal signal | Scenario |
|---|---|---|---|
| `Mono<T>` | 0 or 1 | Complete or error | HTTP response with a single JSON object, single record lookup |
| `Flux<T>` | 0 to many | Complete, error, or unbounded | SSE, multiple records, event streams |
| `Publisher<T>` | General interface | Per Reactive Streams | Generic API without coupling directly to Reactor |
| `Mono<Void>` | No result payload | Complete or error | Sending data where only completion status matters |
| `Flux<Message<T>>` | Multiple **messages** | Per Publisher | Reactive event source supplying individual messages to the flow |
| `Message<Flux<T>>` | **One message** holding **one Flux** | Depends on how downstream consumes payload | Streaming HTTP request/response held as a `Publisher` payload |

Distinguishing the last two types is critical:

~~~text
Flux<Message<OrderEvent>>
  ├─ Message<OrderEvent>("event-1")
  ├─ Message<OrderEvent>("event-2")
  └─ Message<OrderEvent>("event-3")

Message<Flux<OrderEvent>>
  └─ payload = Flux<OrderEvent>
       ├─ event-1
       ├─ event-2
       └─ event-3
~~~

With `Flux<Message<OrderEvent>>`, each `onNext` signal is already a Spring Integration message. With `Message<Flux<OrderEvent>>`, the flow sees only **one message**; a publisher-aware step or splitter is required to process individual events. Never cast the payload to `OrderEvent` when it is actually a `Flux<OrderEvent>`.

### 3.1. Short Code Illustrating Mono and Flux

~~~java
import reactor.core.publisher.Mono;
import reactor.core.publisher.Flux;

Mono<String> oneOrder = Mono.just("ORD-1001");

Flux<String> multipleOrders =
    Flux.just("ORD-1001", "ORD-1002", "ORD-1003");

Mono<String> maybeOrder = Mono.empty();
Flux<String> failedOrders =
    Flux.error(new IllegalStateException("Remote source unavailable"));
~~~

`Mono.just`/`Flux.just` create publishers; `Mono.empty` completes without emitting an item, while `Flux.error` emits an error. **Never use `null` as an `onNext` element**: Reactive Streams forbids `null` data signals; when there is no value, use `Mono.empty()` or an alternative data contract.

## 4. Building Publishers and Execution Timing

A Reactor chain has two phases: **pipeline assembly** and **actual subscription**. Many publishers are *cold*: each subscriber triggers its own execution. Some sources are *hot*: emitting data independently of any specific subscriber, or broadcasting events to multiple subscribers depending on how the source is configured.

~~~java
import reactor.core.publisher.Flux;

Flux<Integer> sequence = Flux.defer(() -> {
    System.out.println("Creating source on subscribe");
    return Flux.range(1, 3);
});

// Not yet subscribed: lambda inside defer has not run.
sequence.subscribe(i -> System.out.println("first: " + i));
sequence.subscribe(i -> System.out.println("second: " + i));
~~~

In the example above, `Flux.defer` delays creating the source until each subscription. Each new `subscribe` runs the lambda again. This is useful for HTTP operations or queries when properly wrapped as deferred publishers.

Conversely, Spring Integration's `FluxMessageChannel` has an internal hot `Flux` acting as a sink for messages sent via `send()`. You must consider when subscribers are ready, buffering, and endpoint lifecycles; do not treat `send()` as a guarantee that "the consumer has finished processing."

**Note on subscription:** calling `subscribe()` manually at arbitrary layers breaks error propagation, cancellation, and backpressure from the root pipeline. In Spring Integration, let the endpoint/reactive consumer or HTTP runtime manage subscriptions per contract, unless you are deliberately implementing the final terminal subscription boundary.

## 5. Observing Backpressure via request(n)

The following Reactor snippet is pure Java, running independently of Spring Integration. It uses `BaseSubscriber` to explicitly request element counts:

~~~java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public class DemandDemo {
    public static void main(String[] args) {
        Flux.range(1, 5)
            .doOnRequest(n -> System.out.println("requested=" + n))
            .subscribe(new BaseSubscriber<Integer>() {
                @Override
                protected void hookOnSubscribe(Subscription subscription) {
                    request(2);
                }

                @Override
                protected void hookOnNext(Integer value) {
                    System.out.println("received=" + value);
                    request(1);
                }
            });
    }
}
~~~

Initially, the subscriber requests only 2 elements. As each element arrives, it calls `request(1)` to grant additional demand. With a synchronous `Flux.range` source, exact emission order and consecutive logs depend on how Reactor schedules requests issued inside callbacks; the key takeaway is that **the publisher may only emit up to the total granted demand**, rather than pushing unboundedly regardless of the subscriber.

### 5.1. Backpressure vs. Rate Limiting

Suppose a source attempts to emit data quickly while downstream can only complete tasks more slowly. Several throttling mechanisms exist, each solving a different problem:

| Mechanism | What it adjusts | What it does not guarantee |
|---|---|---|
| `request(n)` | Number of items subscriber wants to receive | That non-demand-aware sources will stop on their own |
| `limitRate(k)` | How Reactor splits upstream demand into chunks | Exact requests/second or absolute CPU bounds |
| `flatMap(mapper, concurrency)` | Number of concurrently subscribed inner publishers | Fixed memory; prefetch/buffers and produced values still apply |
| `concatMap(mapper)` | Sequential inner publisher processing, preserves order | High throughput when operations are slow |
| `onBackpressureBuffer(capacity)` | Bounded buffer at a hot/fast source segment | Durable storage or zero message loss on overflow |
| HTTP rate limiter | Request rate in/out at the HTTP boundary | Reactive Streams demand across all adapters |
| Queue/broker | Buffers and decouples pace, can persist durably | Automatic backpressure to all upstreams |

If `onBackpressureBuffer` fills up, an explicit overflow/error policy is needed. For business events that cannot be lost, switching to `onBackpressureDrop` or `onBackpressureLatest` causes data loss and is usually inappropriate. When dropping items is acceptable (e.g., certain telemetry), document the rule and monitor drop counts.

### 5.2. Example Limiting Concurrent Work

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import java.time.Duration;

Flux<String> processed = Flux.range(1, 20)
    .limitRate(8)
    .flatMap(i ->
        Mono.delay(Duration.ofMillis(100))
            .map(tick -> "processed-" + i),
        4); // At most 4 active inner publishers at the same time.

processed.subscribe(
    System.out::println,
    error -> System.err.println("failed: " + error));
~~~

Here `limitRate(8)` shapes input requesting behavior and parameter `4` caps concurrent inner publishers in `flatMap`. It does **not** mean processing exactly 8 items per second. `flatMap` does not guarantee preserving output order when inner publishers finish at different times; if business logic requires strict sequential order, use `concatMap` or an appropriate serialization approach. For controlled application shutdown, manage `Disposable`/subscriptions rather than relying on a bare `main` example.

## 6. Channel Choice Determines IntegrationFlow Behavior

In Spring Integration, `MessageChannel` decouples the sender from the receiver. The very same handler behaves very differently depending on the channel wired ahead of it:

| Channel | Dispatch style | Interaction with backpressure |
|---|---|---|
| `DirectChannel` | Subscriber receives message synchronously on the calling path | Does not establish Reactive Streams demand; blocking handlers can block the caller |
| `ExecutorChannel` | Dispatches work via `TaskExecutor` | Offloads thread; needs pool and queue limits, not automatically a reactive pipeline |
| `QueueChannel` | Internal queue for polling consumer | Uses capacity/timeout limits and poller; not a `Publisher` |
| `FluxMessageChannel` | `MessageChannel` **and** `Publisher<Message<?>>` | Supports reactive subscription, `request(n)`, and linking upstream `Publisher`s |
| External broker (JMS/Kafka/AMQP) | Per driver/adapter mechanism | Has its own prefetch, consumer concurrency, ACK, retries, and buffers |

### 6.1. FluxMessageChannel

`FluxMessageChannel` is a specialized channel combining `MessageChannel` with `Publisher<Message<?>>`. It holds an internal hot `Flux` to accept messages sent via `send()`, and also implements `ReactiveStreamsSubscribableChannel` to bridge an upstream `Publisher<Message<?>>` when downstream subscribes.

This channel is **neither** a standard `SubscribableChannel` **nor** a `PollableChannel`. Therefore, you do not use `@Poller` as with `QueueChannel`; consumers must be Reactive Streams compatible. Spring Integration provides `ReactiveStreamsConsumer` so `MessageHandler`s can participate in the reactive chain.

Key points to remember:

- When upstream is natively a Reactive Streams–compliant `Publisher<Message<?>>`, downstream demand can influence upstream emission schedules.
- When a producer calls the synchronous `channel.send(message)` API rapidly into the hot sink, no magic mechanism forces the producer to wait on system-wide demand. You must design buffering, send rates, and overload behavior.
- To preserve backpressure across multiple endpoints, intermediate endpoints must maintain reactive composition. A handler calling blocking JDBC directly or pushing into an unbounded queue weakens or breaks end-to-end regulation.

### 6.2. ReactiveStreamsConsumer and Asynchronous Processing

In Spring Integration, `ReactiveStreamsConsumer` bridges a reactive channel and a `MessageHandler`. Since Spring Integration 5.5, consumer endpoints also offer a `reactive()` option to bring consumer logic into the Reactive Streams model. Since 6.1, Java DSL supports `handleReactive(...)` for a `ReactiveMessageHandler` returning `Mono<Void>`, enabling clean integration of asynchronous side effects.

With a standard output channel, a handler returning a reactive payload may need an `async` mechanism and a suitable subscriber to consume the publisher. When the output channel is a `ReactiveStreamsSubscribableChannel`, the framework can hook the publisher into the reactive chain instead of forcing `block()` inside the handler. Always distinguish **a publisher serving as a message payload** from **a publisher orchestrating messages across the flow**.

## 7. Spring Integration Example: FluxMessageChannel and ReactiveMessageHandler

The configuration below illustrates a reactive branch in Spring Integration 6.1+. In the example, the consumer simulates non-blocking work with `Mono.delay`; in a real application, replace it with an appropriate reactive API.

~~~java
package com.example.integration;

import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.FluxMessageChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import reactor.core.publisher.Mono;

@Configuration
@EnableIntegration
public class ReactiveOrderFlowConfiguration {

    public record OrderEvent(String eventId, String orderId) {}

    @Bean
    public FluxMessageChannel reactiveOrders() {
        return new FluxMessageChannel();
    }

    @Bean
    public IntegrationFlow processReactiveOrders() {
        return IntegrationFlow.from("reactiveOrders")
            .handleReactive(message ->
                Mono.delay(Duration.ofMillis(100))
                    .doOnNext(ignored -> System.out.println(
                        "Processed: " + message.getPayload()))
                    .then())
            .get();
    }
}
~~~

In a Spring Boot app with `spring-boot-starter-integration`, the beans above are registered in the `ApplicationContext`. To send a message to the channel from Java code:

~~~java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

// channel injected via @Qualifier("reactiveOrders").
boolean accepted = channel.send(
    MessageBuilder.withPayload(
        new ReactiveOrderFlowConfiguration.OrderEvent(
            "evt-001", "ORD-1001"))
        .build());
~~~

**Limitations of the example:** calling `send` is an imperative producer call; `send` succeeding only indicates channel acceptance per its contract, not that the handler finished, HTTP ACKed, or data was durably saved. Backpressure is most effective when **both upstream and downstream** use subscription-driven Reactive Streams; an imperative `send` caller needs its own overload protection policy.

Beyond `FluxMessageChannel`, Java DSL also supports starting an `IntegrationFlow` from a `Publisher<Message<T>>` and exporting a flow as a reactive publisher via `toReactivePublisher()`. These are useful bridges when the source is already Reactor (`Flux` from WebClient or R2DBC) or when downstream wants to subscribe directly.

## 8. WebFlux Inbound: Flux Payloads and HTTP SSE

### 8.1. Receiving Streaming HTTP Request Bodies

Spring Integration WebFlux can configure `requestPayloadType` using `ResolvableType` for reactive payloads. Concise example:

~~~java
import org.springframework.core.ResolvableType;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.webflux.dsl.WebFlux;
import reactor.core.publisher.Flux;

@Bean
public IntegrationFlow incomingStringStream() {
    return IntegrationFlow
        .from(WebFlux.inboundChannelAdapter("/stream/events")
            .requestMapping(m -> m.methods(HttpMethod.POST))
            .requestPayloadType(
                ResolvableType.forClassWithGenerics(
                    Flux.class, String.class))
            .statusCodeFunction(m -> HttpStatus.ACCEPTED))
        .channel(c -> c.queue("streamPayloadQueue"))
        .get();
}
~~~

This configuration **illustrates the HTTP → MessageChannel boundary**, matching the Spring Integration documentation API. Downstream receives a message whose payload is `Flux<String>` and must **subscribe/split at the right place** to process each element. The `QueueChannel` here holds messages containing a publisher; the queue itself does **not** understand `request(n)` for items inside that payload. Configure appropriate pollers/handlers and verify codecs and actual client media types when using streaming requests.

### 8.2. Returning a Flux as Server-Sent Events

When an HTTP client needs a stream of status updates, `WebFlux.inboundGateway(...)` can take the flow's reply publisher and write it as SSE, for example:

~~~java
import java.time.Duration;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.webflux.dsl.WebFlux;
import reactor.core.publisher.Flux;

@Bean
public IntegrationFlow progressSse() {
    return IntegrationFlow
        .from(WebFlux.inboundGateway("/api/progress")
            .requestMapping(m -> m
                .methods(HttpMethod.GET)
                .produces(MediaType.TEXT_EVENT_STREAM_VALUE)))
        .handle((payload, headers) ->
            Flux.interval(Duration.ofMillis(500))
                .take(4)
                .map(i -> "progress-" + i))
        .get();
}
~~~

Test with HTTP GET after starting the application:

~~~bash
curl -N -H 'Accept: text/event-stream' \
  http://localhost:8080/api/progress
~~~

WebFlux handles serializing the stream as `text/event-stream`; the runtime manages demand and cancellation along the HTTP connection. However, **proxies, clients, networks, and intermediate buffers** can alter per-event latency. If a client disconnects mid-stream, the HTTP subscription may cancel, yet work already dispatched to databases, thread pools, or brokers is not guaranteed to cancel automatically.

## 9. WebFlux Outbound Gateway: Mono Reply or Flux Reply?

For outbound HTTP, `WebFluxRequestExecutingMessageHandler` uses `WebClient` to invoke external services. The following two configurations serve different response shapes.

**Single JSON object:**

~~~java
.handle(WebFlux.outboundGateway(
        "http://localhost:9090/api/orders/status")
    .httpMethod(HttpMethod.GET)
    .expectedResponseType(OrderStatus.class))
~~~

The gateway decodes the body according to `OrderStatus.class` and produces a reply message; the forwarded payload is usually `OrderStatus` rather than `Mono<OrderStatus>`. This marks the distinction between **the publisher used for HTTP I/O mechanics** and **the payload type Spring Integration passes downstream**.

**HTTP response containing a multi-element stream:**

~~~java
.handle(WebFlux.outboundGateway(
        "http://localhost:9090/api/orders/updates")
    .httpMethod(HttpMethod.GET)
    .expectedResponseType(OrderStatus.class)
    .replyPayloadToFlux(true))
~~~

When server and codec support streaming responses, the reply message carries a **`Flux<OrderStatus>` payload**. You must process this publisher downstream (e.g., via a reactive splitter) if the goal is to produce individual messages. Setting `replyPayloadToFlux(true)` does not automatically split it into `Flux<Message<OrderStatus>>`.

If the remote returns a regular response (without a streaming media type), do not enable this option mechanically. For streaming, verify **no unbounded buffering**, consumption rate, and behavior when upstream or the user closes the connection.

## 10. Backpressure Boundaries When Connecting External Systems

Backpressure propagates directly only through compatible components. Across adapters in this module, distinguish:

| System / segment | Typical throttling mechanism | Do not assume |
|---|---|---|
| WebFlux inbound request body | Subscriber demand, codecs, HTTP limits | That external HTTP clients will stop sending new requests |
| WebFlux outbound `WebClient` | Reactive publisher, client connector, and limits | That the partner API receives data strictly at IntegrationFlow's demand |
| `FluxMessageChannel` | Publisher/subscriber and `request(n)` | That synchronous `send()` converts into complete backpressure |
| Synchronous JDBC | Connection pool, executor, rate limit | That blocking JDBC runs safely on the event loop |
| R2DBC / reactive driver | Publisher demand, pool/concurrency | That every DB operation completes fast or needs no transaction |
| JMS / AMQP | Listener concurrency, prefetch, ACK, queue limits | That reactive demand propagates back through the broker arbitrarily |
| Kafka | Poll/batch, pause/resume, consumer lag, offset commit | That Reactor `request(n)` directly drives all offsets/polls |
| File / SFTP polling | `maxMessagesPerPoll`, poll interval, I/O load | That regular pollers follow Reactive Streams like `Flux` |

In Spring Integration, a `SourcePollingChannelAdapter` whose output is a `ReactiveStreamsSubscribableChannel` can be bridged to Reactor-based emission driven by downstream demand. Still, trigger intervals, actual source reads, and source limits must be examined; filesystems or SFTP do not acquire Reactive Streams protocols merely because the flow uses `FluxMessageChannel`.

### 10.1. Three Integration Patterns to Distinguish

~~~mermaid
flowchart TB
    subgraph Reactive["End-to-end reactive chain"]
      R1["Publisher"] --> R2["FluxMessageChannel"] --> R3["ReactiveStreamsConsumer"]
      R3 -.->|"backward demand"| R2
      R2 -.->|"backward demand"| R1
    end
    subgraph Buffered["Queue-buffered path"]
      Q1["HTTP / source"] --> Q2["QueueChannel (bounded)"] --> Q3["Poller"] --> Q4["Handler"]
    end
    subgraph External["Broker-backed path"]
      E1["IntegrationFlow"] --> E2["Kafka / JMS / AMQP"] --> E3["Another consumer"]
    end
~~~

All three patterns can serve integration problems, yet each follows its own rules: reactive demand, queue capacity/timeouts, or broker ACK/prefetch/offsets. Measure and manage **each boundary**, rather than applying a single blanket solution to every data source.

## 11. Handling Blocking Sources in a Reactive Flow

A common mistake is calling blocking JDBC or `Thread.sleep` directly inside a `map`/`flatMap` executing on the event loop:

~~~java
// Do not do this if repository.findById is a blocking JDBC call:
// Assumes findById returns Optional<Order> like Spring Data.
Flux<Optional<Order>> wrong = incoming.map(
    event -> jdbcRepository.findById(event.orderId()));
~~~

One way to isolate blocking calls at the Reactor layer:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Flux<Order> better = incoming.flatMap(event ->
    Mono.fromCallable(() ->
            jdbcRepository.findById(event.orderId()))
        .subscribeOn(Schedulers.boundedElastic())
        .flatMap(optional -> Mono.justOrEmpty(optional)),
    8);
~~~

The example assumes `findById` returns `Optional<Order>` as in Spring Data; `import java.util.Optional;` is needed for the first snippet. `Mono.justOrEmpty(optional)` skips empty results. In a real application, you may want to emit an error or a NOT_FOUND result rather than skipping silently. Moving blocking calls onto `boundedElastic` and capping concurrency in `flatMap` **does not replace** database connection pools, transaction boundaries, or database load limits. For complex flows, a genuinely reactive API like R2DBC reduces paradigm switching.

When using `publishOn(scheduler)` or `subscribeOn(scheduler)`, understand the difference:

- `subscribeOn` affects the subscription context and the corresponding upstream stages.
- `publishOn` switches downstream execution to the given scheduler, with its own queue/prefetch and thread-switching overhead.
- Neither turns a blocking operation into a non-blocking one; they only change where that operation executes.
- `Schedulers.boundedElastic()` has internal bounds, yet external concurrency control is still required when DB/API resources are tightly constrained.

## 12. Errors, Cancellation, Retries, and Idempotency

Reactive Streams carries three primary signals: data `onNext`, successful completion `onComplete`, and error termination `onError`. An unhandled error terminates the corresponding chain; retry creates a fresh subscription/execution attempt as configured.

~~~java
Flux<String> resilient = remoteUpdates()
    .timeout(Duration.ofSeconds(3))
    .retryWhen(
        reactor.util.retry.Retry
            .backoff(2, Duration.ofMillis(200))
            .filter(error -> isTransient(error)))
    .doOnError(error -> recordFailure(error));
~~~

This is a skeleton example: `remoteUpdates()`, `isTransient(...)`, and `recordFailure(...)` must be implemented by the application. `Retry.backoff(2, ...)` performs **at most two retries** after the initial attempt for errors passing the filter. Do not retry codec, authentication, or validation errors; likewise, do not retry side-effecting POSTs unless the external system supports idempotency.

**Cancellation** occurs when downstream no longer wants data. For instance, an HTTP client closes an SSE connection; the publisher may receive a cancel signal. That does **not guarantee** a message already sent to Kafka was recalled or a database transaction rolled back. Define explicit cancellation contracts whenever work crosses system boundaries.

**Spring Integration's error channel** and Reactor's `onErrorResume`/`retryWhen` serve different error-handling layers. With a `ReactiveMessageHandler` inside `ReactiveStreamsConsumer`, errors can stay within the reactive pipeline. When routing into imperative adapters or queues, errors can also surface as `ErrorMessage`, advice, or poller retries. Test each error path directly rather than guessing behavior from channel type names.

### 12.1. Choosing a Strategy When Downstream Is Too Slow

| Data | Preferred strategy | Risks to accept or handle |
|---|---|---|
| Payment/order commands | Durable queue/broker, load limits, retries, idempotency | Duplicate events, backlog, ACK/commit |
| Telemetry for real-time charts | Controlled `onBackpressureLatest`/drop, track drop counts | Loss of intermediate data points |
| Report streams needing all records | Demand and bounded buffers or durable staging | Higher latency, longer streams |
| Synchronous HTTP queries | Request/concurrency limits and timeouts, return 429/503 when needed | Clients must retry per policy |

Never use an unbounded buffer to "solve" backpressure. A buffer only relocates where data piles up; it does not increase downstream processing capacity.

## 13. Observability and Testing

A reactive flow that passes with a handful of items in a demo can still fail under real load. Metrics to track include:

1. **Ingress rate / completion rate:** messages arriving and completing over time.
2. **In-flight operations:** active HTTP/DB requests and live subscriptions.
3. **Buffer/queue depth:** waiting elements and maximum wait time; alert before overflow.
4. **Latency:** p50/p95/p99 across each hop: HTTP → channel → handler → broker/DB.
5. **Errors/cancellations/retries:** counts of `onError`, timeouts, cancellations, dropped messages, and retries.
6. **Infrastructure:** event-loop saturation, thread pools, connection pools, consumer lag, HTTP 429/5xx statuses, and memory/GC.

A basic demand test can use `reactor-test` and `StepVerifier`:

~~~groovy
// testImplementation in build.gradle
testImplementation 'io.projectreactor:reactor-test'
~~~

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class BackpressureTest {
    @Test
    void emitsOnlyAfterDemand() {
        Flux<Integer> numbers = Flux.range(1, 3);

        StepVerifier.create(numbers, 0)
            .thenRequest(1)
            .expectNext(1)
            .thenRequest(2)
            .expectNext(2, 3)
            .verifyComplete();
    }
}
~~~

The test sets initial request to `0` and then grants demand in steps. It verifies a basic Reactor publisher; it does **not** prove end-to-end backpressure across HTTP servers, databases, queues, and brokers. To test a real system, add tests with slow HTTP clients, slow consumers, cancelled requests, full queues, and server error responses.

## 14. Applied Exercises

1. Run `DemandDemo`, replace `request(2)` with `request(1)`, and trace the order of `doOnRequest` and `onNext` signals. Explain why demand count is not a requests-per-second limit.
2. Use `Flux.range(1, 20)` with `flatMap(..., 4)`, replace it with `concatMap(...)`, and measure differences in concurrency and output ordering.
3. Create a `FluxMessageChannel` as in Section 7, send a message from Java, and observe the consumer. Explain why `send() == true` does not indicate processing has finished.
4. Configure an inbound HTTP payload of `Flux<String>`, send a request using a streaming-capable codec, and add a downstream consumer that handles the publisher properly. Compare `Message<Flux<String>>` with `Flux<Message<String>>`.
5. Call a remote HTTP API emitting SSE, configure an outbound gateway with `replyPayloadToFlux(true)`, and process each item via a reactive subscriber or splitter. Observe behavior when the server pauses emitting.
6. Simulate a slow downstream and a fast source; add a bounded buffer, observe overflow, and then try a load-shedding/throttling strategy suitable for data that must not be lost.
7. Introduce a blocking JDBC operation into the example, move it to `boundedElastic`, and cap concurrency. Monitor DB request counts and wait times before/after the change.
8. Cancel SSE mid-stream and configure an HTTP timeout. Identify which segment cancels, which keeps running, and what happens if a message was already sent to Kafka/JMS.

**Reasoning scenario:** an application receives payment webhooks at burst rates, writes to a database, and emits Kafka notifications. Identify where Reactive Streams boundaries end, which mechanisms prevent message loss, how load is bounded, and when returning HTTP `202 Accepted` is permitted. Does merely changing `DirectChannel` to `FluxMessageChannel` satisfy all requirements?

## 15. References

- [Spring Integration Reference — Reactive Streams Support](https://docs.spring.io/spring-integration/reference/reactive-streams.html): reactive contract, `FluxMessageChannel`, `ReactiveStreamsConsumer`, `handleReactive`, source adapters, and Java DSL.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): differences among `DirectChannel`, `QueueChannel`, `ExecutorChannel`, and `FluxMessageChannel`.
- [Spring Integration Reference — WebFlux Support](https://docs.spring.io/spring-integration/reference/webflux.html): inbound `Flux` request payloads, SSE, outbound `replyPayloadToFlux`, and `WebClient`.
- [Project Reactor Reference — Backpressure](https://projectreactor.io/docs/core/release/reference/): `request(n)`, `BaseSubscriber`, `limitRate`, `flatMap`, and overflow strategies.
- [Reactive Streams Specification](https://www.reactive-streams.org/): `Publisher`, `Subscriber`, and `Subscription` interfaces, and non-blocking backpressure principles.

> **Takeaway:** `Mono` and `Flux` model asynchronous data; `request(n)` expresses receiver demand. `FluxMessageChannel` can propagate demand inside a reactive Spring Integration flow, yet backpressure does not automatically cross independent HTTP clients, blocking JDBC, queues, or brokers. Stable design combines load limits, proper buffering, error handling, idempotency, and observability at every connection boundary.
