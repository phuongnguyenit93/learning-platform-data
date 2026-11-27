# ReactiveStreamsProducer

## 1. Objectives and Scope

In the **Reactive support** chapter of the **SPRING_INTEGRATION_CORE** module, this lesson explores the producer role that ingests a Reactive Streams flow and feeds each event into Spring Integration's `Message → MessageChannel → endpoint` model.

After this lesson, you can:

- Distinguish among `Publisher<T>`, `Message<Publisher<T>>`, and `Publisher<Message<T>>`.
- Connect a Reactor source with Java DSL using `IntegrationFlow.from(publisher)`.
- Build a lifecycle-managed inbound adapter using `MessageProducerSupport.subscribeToPublisher(...)`.
- Identify where demand propagates, where blocking may occur, and where errors must be handled.
- Test messages, headers, and demand using `StepVerifier`.

**Naming note:** `ReactiveStreamsProducer` in the title refers to the producer role of a Reactive Streams flow. The examples below use the actual Spring Integration APIs `MessageProducerSupport`, `FluxMessageChannel`, and `IntegrationFlow`; do not assume there is a Spring Integration class named `ReactiveStreamsProducer` to import.

The examples use **Java 17 and Spring Integration 6.5.x** as an API baseline. This is an illustrative baseline, not a claim about the latest version. Spring, Spring Integration, and Reactor dependencies must be managed using a mutually compatible version set for your application. The base API is documented in [MessageProducerSupport Javadoc](https://docs.spring.io/spring-integration/api/org/springframework/integration/endpoint/MessageProducerSupport.html).

## 2. What Problem Does the Producer Solve?

Suppose the system receives order events from a driver providing `Flux<OrderEvent>`. The integration flow must add the source identifier to headers, drop invalid orders, normalize order IDs, and pass them to a business processor.

If you manually call `subscribe()` in business code and send each element to a channel yourself, the application has to manage subscriptions, errors, and shutdown on its own. A Spring-managed adapter centralizes the responsibility of connecting the source to an endpoint; filtering and transformation logic can still be expressed with familiar Integration components.

```mermaid
flowchart LR
    A[Publisher OrderEvent] --> B[Producer: create Message]
    B --> C[FluxMessageChannel]
    C --> D[Filter]
    D --> E[FluxMessageChannel]
    E --> F[Transformer]
    F --> G[FluxMessageChannel]
    G --> H[Reactive handler]
```

The arrows above show data direction. Demand flows in the opposite direction within each wired Reactive Streams chain. Every channel, adapter, or external client boundary must be inspected separately; merely seeing a `Flux` at the input is not enough to conclude the entire system supports backpressure.

## 3. Reactive Streams Contract Essentials

### 3.1. Four Components

| Component | Responsibility | Relation to Integration Flow |
|---|---|---|
| `Publisher<T>` | Allows subscribing to a sequence of elements | Event source from a driver or Reactor |
| `Subscriber<T>` | Receives subscription and signals | Stream consumer side |
| `Subscription` | Receives `request(n)` and `cancel()` | Controls demand and cancels consumption |
| `Processor<T, R>` | Both consumes and emits data | Intermediate contract; rarely implemented manually with Reactor |

A subscription follows a signal sequence like:

```text
onSubscribe(subscription)
    request(n) from subscriber
    onNext(item) up to remaining cumulative demand
    ...
    onComplete() or onError(error)
```

`request(n)` requires `n > 0`. `onComplete` and `onError` are terminal signals and do not wait for element demand. `cancel()` requests emission to stop; concrete resource cleanup depends on the source and adapter. The original specification is published at [Reactive Streams](https://www.reactive-streams.org/).

### 3.2. Demand Does Not Equal In-Flight Task Count

If a subscriber requests 8 items, that does not automatically spawn 8 threads or guarantee that only 8 database queries are running. Concurrent task count depends on operators such as `flatMap`, concurrency settings, prefetch, and intermediate queues.

Design example: the target service allows only 16 concurrent requests. You must cap in-flight calls at the service-invocation step; increasing producer buffers only delays overload. When measuring the system, separate received message count, in-flight task count, and queued message count.

### 3.3. Reactive Does Not Automatically Pick a New Thread

A `Flux` can execute synchronously on the subscribing thread. `publishOn` switches where downstream operators run; `subscribeOn` affects source subscription. These two operators control execution scheduling; they do not turn a blocking driver into a non-blocking one. See [Reactor: Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html).

## 4. Data Shapes at the Producer Boundary

| Type | Meaning | When to Use |
|---|---|---|
| `Flux<OrderEvent>` | Stream of business payloads | Data source API |
| `Message<OrderEvent>` | One event with headers | Unit of exchange in Spring Integration |
| `Publisher<Message<OrderEvent>>` | Stream of messages | Input for DSL accepting a Publisher |
| `Message<Flux<OrderEvent>>` | Single message containing the whole publisher as payload | Specialized reactive payload handling |

Example converting each event into a message:

```java
Flux<Message<OrderEvent>> messages = events.map(event ->
        MessageBuilder.withPayload(event)
                .setHeader("source", "orders-api")
                .setHeader("businessKey", event.id())
                .build());
```

Here there is one message per event. Conversely, `MessageBuilder.withPayload(events).build()` creates only a single message whose payload is the `Flux` object; its elements have not yet become independent messages.

Use a stable business key like `businessKey` for deduplication. `MessageHeaders.ID` is a framework message identifier; recreating a message during a source replay can generate a different ID even for the same order.

## 5. Two Ways to Bring a Publisher into Spring Integration

### 5.1. Using Java DSL Directly

If the source already provides a suitable publisher and does not need a custom adapter, you can declare:

```java
@Bean
IntegrationFlow orderInputFlow(OrderClient client) {
    Flux<Message<OrderEvent>> input = Flux.defer(client::events)
            .map(event -> MessageBuilder.withPayload(event)
                    .setHeader("source", "orders-api")
                    .setHeader("businessKey", event.id())
                    .build());

    return IntegrationFlow.from(input)
            .handleReactive(message -> Mono.fromRunnable(() ->
                    System.out.println(message.getPayload())));
}
```

This is an illustrative configuration using the application contract `OrderClient.events(): Flux<OrderEvent>`. Key imports are `IntegrationFlow`, `Message`, `MessageBuilder`, `Flux`, `Mono`, and `Bean`. `OrderEvent` is defined in the complete example later in this lesson.

`Flux.defer` defers calling `client.events()` until subscription time. It is useful when you need to recreate the read operation for each subscription; `defer` itself creates no extra threads.

The DSL overload accepting `Publisher` uses an internal `FluxMessageChannel` to wire the source into the flow. Details of this overload declaration are in the [IntegrationFlow 6.5.0 Source](https://github.com/spring-projects/spring-integration/blob/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/dsl/IntegrationFlow.java).

### 5.2. Building a Lifecycle-Managed Producer

When you need to encapsulate connection logic, name the endpoint, or control start/stop, create a subclass of `MessageProducerSupport`. Inside `doStart()`, build the `Publisher<Message<?>>` chain and pass it to `subscribeToPublisher(...)`.

```text
Spring starts endpoint
    → doStart()
    → build Publisher<Message<?>>
    → subscribeToPublisher(...)
    → output channel receives source
```

The producer is responsible for fetching data and building messages. Filters, transformers, and business processing should live in separate flow steps for easier reuse and testing.

## 6. Complete Example: Order Event Producer

### 6.1. Preparing Dependencies

The example below uses a plain Spring context. If your project already has a BOM or dependency management compatible with Spring Integration 6.5.x, the required dependencies look like:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-core</artifactId>
    </dependency>
    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-core</artifactId>
    </dependency>
    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

This is a dependency list, not a complete `pom.xml`. Without dependency management, you must declare compatible versions; you cannot use this versionless XML snippet as a standalone Maven project.

### 6.2. Program Code

Place the following code in a Java file named `ReactiveOrderDemo.java` in your practice project. The simulated source is a finite cold publisher, making it easy to observe the flow without a broker or external service.

```java
import java.util.Locale;
import java.util.Objects;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.FluxMessageChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.endpoint.MessageProducerSupport;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class ReactiveOrderDemo {

    public record OrderEvent(String id, long amount) {
    }

    public static final class OrderEventProducer extends MessageProducerSupport {

        private final Supplier<Flux<OrderEvent>> sourceFactory;

        public OrderEventProducer(Supplier<Flux<OrderEvent>> sourceFactory) {
            this.sourceFactory = Objects.requireNonNull(sourceFactory);
        }

        @Override
        protected void doStart() {
            Flux<Message<OrderEvent>> messages =
                    Flux.defer(this.sourceFactory::get)
                            .map(event -> MessageBuilder.withPayload(event)
                                    .setHeader("source", "demo-orders")
                                    .setHeader("businessKey", event.id())
                                    .build());

            subscribeToPublisher(messages);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableIntegration
    public static class Config {

        @Bean
        CountDownLatch delivered() {
            return new CountDownLatch(2);
        }

        @Bean
        OrderEventProducer orderProducer() {
            return new OrderEventProducer(() -> Flux.just(
                    new OrderEvent("o-101", 120_000),
                    new OrderEvent("o-102", 0),
                    new OrderEvent("o-103", 450_000)));
        }

        @Bean
        IntegrationFlow orderFlow(OrderEventProducer orderProducer,
                                  CountDownLatch delivered) {
            return IntegrationFlow.from(orderProducer)
                    .channel(new FluxMessageChannel())
                    .filter(OrderEvent.class,
                            event -> event.amount() > 0,
                            endpoint -> endpoint.discardChannel("nullChannel"))
                    .channel(new FluxMessageChannel())
                    .transform(OrderEvent.class, event -> new OrderEvent(
                            event.id().toUpperCase(Locale.ROOT),
                            event.amount()))
                    .channel(new FluxMessageChannel())
                    .handleReactive(message -> Mono.fromRunnable(() -> {
                        System.out.printf("%s | source=%s%n",
                                message.getPayload(),
                                message.getHeaders().get("source"));
                        delivered.countDown();
                    }));
        }
    }

    public static void main(String[] args) throws InterruptedException {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            boolean finished = context.getBean(CountDownLatch.class)
                    .await(5, TimeUnit.SECONDS);
            if (!finished) {
                throw new IllegalStateException("Did not receive two valid orders in time");
            }
        }
    }
}
```

The expected output has two valid normalized orders, such as:

```text
OrderEvent[id=O-101, amount=120000] | source=demo-orders
OrderEvent[id=O-103, amount=450000] | source=demo-orders
```

`o-102` is rejected by the filter and routed to `nullChannel`. In an application that needs to audit rejected orders, replace this destination with a flow recording rejection reasons. If asynchronous processing is added, output order must be determined by operators and concurrency configuration rather than inferred from input declaration order.

### 6.3. Reading the Example by Responsibility

- `sourceFactory` lets the producer obtain a fresh publisher on startup; `Flux.just` is a replayable source in this example.
- The producer adds `source` and `businessKey` before handing messages to the output channel.
- The `FluxMessageChannel` instances maintain reactive boundaries between endpoints.
- The transformer only alters the payload; the `source` header is preserved so the final step can observe the data origin.
- `handleReactive` takes a function returning `Mono<Void>`; the framework manages the subscription for that processing step.
- `CountDownLatch` only lets the console program wait for results before closing the context. Never place `await()` inside a reactive handler.

Console printing is an observation aid for the exercise, not a high-performance I/O pattern. When replacing it with a real client, return the client's publisher from the handler so completion and errors stay in the same processing chain.

## 7. Why the Output Channel Determines Source Wiring

`FluxMessageChannel` is both a `MessageChannel` and a `Publisher<Message<?>>`, and it also implements `ReactiveStreamsSubscribableChannel`. As a result, it can accept an upstream publisher instead of only receiving individual external `send()` calls. These contracts are listed in the [FluxMessageChannel 6.5 Javadoc](https://docs.spring.io/spring-integration/docs/6.5.x/api/org/springframework/integration/channel/FluxMessageChannel.html).

With `subscribeToPublisher(...)`, the producer inspects the output channel type. Channels supporting reactive streams are handed the publisher directly; for standard channels, the base class subscribes to the source and forwards each message via standard message sending. This branching logic is shown in the [MessageProducerSupport 6.5.0 Source](https://github.com/spring-projects/spring-integration/blob/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/endpoint/MessageProducerSupport.java).

| Output Channel | Model to Understand | Design Consequence |
|---|---|---|
| `FluxMessageChannel` | Has Publisher contract and upstream subscription | Suitable for propagating demand between reactive segments |
| `DirectChannel` | Sends message directly to handler in a synchronous call | Does not provide `Subscription.request(n)` to the sender |
| `QueueChannel` | Producer writes to queue, consumer pulls messages | Requires managing queue capacity and consumption rate |
| `ExecutorChannel` | Hands processing off to an executor | Requires managing thread pools, work queues, and async errors |

A slow handler on a `DirectChannel` can make the send call wait longer. That is the synchronous effect of a Java method call, not the Reactive Streams demand contract.

`FluxMessageChannel` also exposes the imperative `send()` API. In this lesson the producer uses publisher wiring; do not assume every `send()` call is non-blocking. When integrating a callback-based source that only pushes data, decide separately how to handle a receiver that is unready or falling behind. Exact send behavior can be checked in the [FluxMessageChannel 6.5.0 Source](https://github.com/spring-projects/spring-integration/blob/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/channel/FluxMessageChannel.java).

## 8. Lifecycle, Cold/Hot Sources, and Resubscription

### 8.1. Cold Publishers and Hot Publishers

With the cold source in the example, each subscription can re-read the three orders. With a hot source such as a live event stream, late subscribers may miss earlier events if the source lacks storage or replay.

`Flux.defer` creates or fetches a source on subscription; it does not add history to a hot source. Therefore, ask specifically: on restart, does the driver reopen a query, register a new listener, or resume from a particular offset?

### 8.2. Start and Stop

In the adapter design, `doStart()` builds the chain while Spring manages the endpoint. `MessageProducerSupport` holds the subscription for publisher wiring and handles cancellation on stop. If you override `doStop()` to close custom resources, call `super.doStop()` to preserve base-class behavior.

The example code does not override `doStop()` because it does not own a client requiring closure. For per-subscription resources, consider `usingWhen` or driver cleanup hooks to tie resource release to complete, error, and cancel signals.

### 8.3. What Restart Does Not Guarantee

Restart does not guarantee resuming from the exact last record, nor does it provide exactly-once delivery. For instance, `Flux.just` replays its data upon resubscription. With external sources, define offsets, acknowledgments, commit operations, and business-level deduplication.

Also distinguish source completion from shared channel completion. A finite publisher ending does not mean every subscriber of a `FluxMessageChannel` must immediately receive `onComplete`; the channel may still be wired to other sources. This directly impacts how tests are written.

## 9. Handling Errors at the Right Boundary

### 9.1. Distinguishing Source Errors from Message Errors

| Error Category | Example | Where to Place Policy |
|---|---|---|
| Connection/source read error | Connection drops while receiving events | Source publisher and adapter |
| Invalid data | Amount equals 0 | Filter or business branch |
| Per-message processing error | Order persistence fails | Handler/endpoint and appropriate recovery branch |
| Application setup error | Missing output channel | Bean configuration and endpoint initialization |

An `onError` terminates the active subscription. `doOnError` only observes without recovering. `onErrorResume` switches to a fallback publisher; `retryWhen` resubscribes to the upstream segment it wraps. See [Reactor: Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html).

### 9.2. Bounded Retries for the Right Error Types

If a driver signals connection errors with `IOException`, you can place the following policy before message construction:

```java
Flux<OrderEvent> input = Flux.defer(sourceFactory::get)
        .retryWhen(Retry.backoff(3, Duration.ofMillis(200))
                .maxBackoff(Duration.ofSeconds(2))
                .filter(IOException.class::isInstance));
```

Additional imports are `java.io.IOException`, `java.time.Duration`, and `reactor.util.retry.Retry`. In practice, filter for the exception types the driver actually emits. This configuration allows up to three retries after the initial subscription; once retries are exhausted, the error still needs to be handled and recorded.

Operator placement scopes retries. A retry placed on the source publisher does not automatically wrap downstream handlers across channels. A data error in a transformer does not become a source read error merely because the whole flow uses Reactor.

Before retrying, consider the case where an order was already persisted but acknowledgment failed. Re-reading can cause duplicate processing. A business key `businessKey` and idempotent writes must be designed where side effects occur.

### 9.3. `errorChannel` and `onError` Are Two Mechanisms Requiring Explicit Wiring

Spring Integration has a model for sending `ErrorMessage` to an error channel for corresponding error handlers. Reactor has subscription `onError` signals. The mere existence of an `errorChannel` bean does not guarantee every error from a driver publisher turns into an `ErrorMessage`.

Identify which component catches errors, which creates `ErrorMessage`, and which subscriber observes terminal failures. You can proactively route source errors into a business error publisher or an error flow, but define whether to stop, recover, or retry afterward. Refer to error message mechanics in [Spring Integration: Error Handling](https://docs.spring.io/spring-integration/reference/6.5/error-handling.html).

## 10. Working with Blocking I/O

If you must call a synchronous API, wrap the call in `Mono.fromCallable` and move it onto an appropriate scheduler:

```java
Mono<OrderEvent> oneOrder = Mono.fromCallable(() -> legacyClient.load(orderId))
        .subscribeOn(Schedulers.boundedElastic());
```

This is an illustrative pattern where `legacyClient.load(...)` is a blocking application call. Do not call `load()` first and pass the result into `Mono.just(...)`, because that executes the operation immediately on the current thread.

`boundedElastic` isolates blocking calls from threads that must stay non-blocking; it still has thread and queue limits. Cap concurrent requests according to the target system's capacity, and configure timeouts on the client or processing chain. Switching threads does not create backpressure for an external source that does not support pausing or throttling emission.

## 11. Testing the Producer and Reactive Channels

### 11.1. Behaviors to Observe

The practice exercise has three separate test boundaries:

1. The producer wraps payloads into messages and adds the right headers.
2. The subscriber receives data according to the demand it issues.
3. The full flow filters out invalid orders and produces two normalized results.

The test below focuses on the first two boundaries. It uses the producer from section 6, but does not register `ReactiveOrderDemo.Config`, so no competing business consumer steals items.

```java
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.FluxMessageChannel;
import org.springframework.integration.config.EnableIntegration;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ReactiveOrderProducerTest {

    @Configuration(proxyBeanMethods = false)
    @EnableIntegration
    static class TestConfig {

        @Bean
        FluxMessageChannel output() {
            return new FluxMessageChannel();
        }

        @Bean
        ReactiveOrderDemo.OrderEventProducer producer(FluxMessageChannel output) {
            var producer = new ReactiveOrderDemo.OrderEventProducer(() -> Flux.just(
                    new ReactiveOrderDemo.OrderEvent("o-101", 120_000),
                    new ReactiveOrderDemo.OrderEvent("o-102", 0),
                    new ReactiveOrderDemo.OrderEvent("o-103", 450_000)));
            producer.setOutputChannel(output);
            producer.setAutoStartup(false);
            return producer;
        }
    }

    @Test
    void receivesMessagesWithExplicitDemand() {
        try (var context = new AnnotationConfigApplicationContext(TestConfig.class)) {
            var channel = context.getBean(FluxMessageChannel.class);
            var producer = context.getBean(ReactiveOrderDemo.OrderEventProducer.class);

            try {
                StepVerifier.create(Flux.from(channel), 0)
                        .then(producer::start)
                        .thenRequest(1)
                        .assertNext(message -> {
                            assertEquals(new ReactiveOrderDemo.OrderEvent(
                                    "o-101", 120_000), message.getPayload());
                            assertEquals("demo-orders",
                                    message.getHeaders().get("source"));
                            assertEquals("o-101",
                                    message.getHeaders().get("businessKey"));
                        })
                        .thenRequest(1)
                        .assertNext(message -> assertEquals(
                                new ReactiveOrderDemo.OrderEvent("o-102", 0),
                                message.getPayload()))
                        .thenCancel()
                        .verify(Duration.ofSeconds(5));
            }
            finally {
                producer.stop();
            }
        }
    }
}
```

`StepVerifier` subscribes first and then starts the producer. Initial demand is 0; each `thenRequest(1)` grants permission to receive one more message at the subscriber boundary. The test ends with cancellation and has a timeout to prevent hanging when the flow emits nothing. Using `StepVerifier` is guided in [Reactor: Testing](https://projectreactor.io/docs/core/release/reference/testing.html).

Because the test has no filter, the second message is still `o-102`. It also does not prove the upstream source is requested strictly one item at a time: channels or operators may prefetch. To verify upstream read volume and concurrency, measure directly at the source or I/O step.

To test the full flow, use the business configuration and collect output at the final step, asserting `O-101`, `O-103`, preservation of the `source` header, and absence of `O-102`. When testing cancellation, observe source cleanup callbacks; calling `thenCancel()` on one channel subscriber alone is not enough to prove all upstream resources were released immediately.

## 12. Common Issues and Remedies

| Symptom | Cause to Check | Remedy |
|---|---|---|
| Source emits no data | No subscription yet, producer not started, or flow disconnected | Check lifecycle and where the subscriber is registered |
| Startup fails due to missing output channel | Producer declared without attaching a channel | Wire via DSL or `setOutputChannel(...)` |
| Single message has a `Flux` payload | Wrapped the entire publisher in one message | Map each element to a `Message` when events must be processed individually |
| Memory grows with load | Fast source, large queues/prefetch, or slow tasks | Measure queues and in-flight work, cap concurrency at slow steps |
| Restart reprocesses orders | Cold source or external source replays | Use proper offsets/acks and idempotency by business key |
| Source errors appear only in Reactor logs | No policy defined for source error signals | Attach error policy on the publisher and explicit observation branch |
| Test waits forever for completion | Conflating a finite source with the channel's lifecycle | Assert the expected messages then cancel, stop beans, and close context |
| Reactive flow suffers thread starvation | Blocking call inside an operator or handler | Isolate blocking calls or use a proper reactive client |

## 13. Applying to a Real Integration Flow

For a system receiving orders from a reactive source, you can split responsibilities as follows: the producer connects the source and attaches business identifiers; filters enforce acceptance criteria; transformers normalize data; routers pick branches by order type; handlers call target systems. If an aggregator is needed, define group completion timing, timeouts, and memory bounds, especially when the source can run indefinitely.

Gateways typically serve inbound calls into a flow with request/reply semantics. The producer in this lesson serves sources proactively emitting multiple events; each event does not inherently have a gateway caller waiting for a reply. Therefore, design replies, acknowledgments, and errors to match the integration boundary's role.

When choosing an implementation approach, prefer `IntegrationFlow.from(publisher)` for sources already suited to the DSL; use an adapter extending `MessageProducerSupport` when you need to encapsulate connection and lifecycle management. Flow quality depends on wiring the right contracts at each boundary, bounding in-flight work, and proving behavior when the source completes, fails, or cancels.