# Continuous Data Streams and Receive Rate Control

In many applications, data does not arrive as isolated individual requests but appears continuously: market prices change, sensors emit readings, users generate events, logs are written continuously, or order statuses are updated over time. When a producer emits data faster than a consumer can process it, the system can accumulate queues, increase latency, consume excessive memory, and eventually become overloaded.

A data stream models a sequence of elements emitted over time. Controlling the receive rate means coordinating the amount of data delivered to the consumer so that processing speed and system resources remain within acceptable bounds. In the Spring ecosystem, you need to understand the relationship between an individual `Message`, a multi-element reactive stream, and backpressure mechanisms to choose the right tool.

## 1. Why Are Data Streams and Rate Control Needed?

Suppose a monitoring system receives 5,000 measurements per second, while a consumer can process only 1,000 measurements per second. If the producer keeps sending continuously, unprocessed data grows by roughly 4,000 elements every second. Over time, the queue can exhaust memory or data arrives at the consumer too late to remain useful.

Similar situations occur when:

- An application receives high-volume events from users or IoT devices.
- A service consumes data from a broker or logging system.
- An endpoint streams continuous data to a browser.
- A pipeline performs multiple transformations, database writes, or external service calls.
- Multiple consumers read data concurrently at different processing speeds.

The primary issues include:

**Overloaded consumer:** CPU, memory, database connections, or thread pools are overutilized.

**Growing backlog:** queued data accumulates, increasing end-to-end latency.

**Data loss:** if a queue fills up and the policy drops elements, some events may be discarded.

**Resources held too long:** messages remain in memory or in flight for too long, reducing capacity to serve new requests.

**Unstable throughput:** traffic often spikes in bursts, so configurations adequate under low load can fail under peak load.

Therefore, streaming design must answer three questions: how data is emitted, how the consumer signals its capacity to accept data, and what the system does when the producer outpaces the consumer.

## 2. Distinguishing a Message from a Stream

In Spring Messaging, `Message<T>` is a single message unit consisting of a payload and headers. For example, a message might contain a temperature reading along with information about the sending device.

A stream is a sequence of multiple elements emitted over time. Each element may be a simple value or a `Message<T>`. You can picture it as:

~~~text
Stream
  |
  +--> Message 1: payload + headers
  +--> Message 2: payload + headers
  +--> Message 3: payload + headers
  +--> ...
~~~

`Message` describes the structure of one element; a stream describes how many elements are emitted and consumed. Using `MessageChannel` alone does not create a backpressure protocol. Sending may be synchronous or asynchronous depending on the channel implementation, and the `send` operation itself does not provide the full demand protocol of Reactive Streams.

This is a key point when combining Spring Messaging with Spring WebFlux, Reactor, RSocket, or a broker: you must identify which layer implements load regulation.

## 3. Reactive Streams and Demand Signals

Reactive Streams is a specification for asynchronous data exchange with flow control. It defines four roles:

- **Publisher:** the data source.
- **Subscriber:** the component receiving and processing data.
- **Subscription:** the relationship between publisher and subscriber, through which the subscriber requests data or cancels subscription.
- **Processor:** a component that both receives and emits data, often used to transform or connect stages in a pipeline.

A subscriber first receives an `onSubscribe` notification. Then the subscriber calls `request(n)` to signal it is ready to receive at most `n` elements. The publisher emits data via `onNext` up to the requested demand. When the stream finishes normally, the publisher calls `onComplete`; if an unrecoverable error occurs, the publisher calls `onError`. The subscriber can also call `cancel()` to stop receiving.

Basic signal flow:

~~~text
Subscriber                    Publisher
    |                             |
    |<------ onSubscribe ---------|
    |                             |
    |-------- request(3) -------->|
    |<--------- onNext(1) --------|
    |<--------- onNext(2) --------|
    |<--------- onNext(3) --------|
    |                             |
    |-------- request(2) -------->|
    |<--------- onNext(4) --------|
    |<--------- onNext(5) --------|
    |                             |
    |<--------- onComplete -------|
~~~

Demand is the number of elements the subscriber allows the publisher to emit next. A Reactive Streams-compliant publisher must not emit `onNext` beyond the requested demand. This mechanism creates a form of backpressure flowing from consumer back to producer.

In practice, a pipeline may contain intermediate operators. Operators can buffer a number of elements internally, batch requests, or switch data across schedulers. Therefore, backpressure must be understood across the entire pipeline, including buffers and external data sources.

## 4. Flux and Mono in the Spring Ecosystem

Project Reactor is the reactive library used by Spring WebFlux. Its two core data types are:

| Type | Element Count | Use Cases |
|---|---:|---|
| Mono<T> | 0 or 1 | A single result, such as looking up a record |
| Flux<T> | 0 to many | Lists, event streams, or continuous data |

`Flux<T>` implements `Publisher` from Reactive Streams. A subscriber can control a `Flux`'s demand via `Subscription`. `Mono<T>` also supports the reactive protocol but emits at most one element.

Example of a sequential source:

~~~java
Flux<Integer> numbers = Flux.range(1, 5);
~~~

Example of a time-based source:

~~~java
Flux<Long> ticks = Flux.interval(Duration.ofSeconds(1));
~~~

`Flux.interval` emits values periodically. With an unbounded source like this, the application must define when to cancel the subscription, such as when the client disconnects or when the task no longer needs data.

In Spring:

- **Spring WebFlux** uses `Mono` and `Flux` for reactive HTTP handling. An endpoint can return a `Flux` to stream multiple elements, such as Server-Sent Events.
- **Spring Messaging** provides the `Message` structure, headers, and channel/handler abstractions. These abstractions describe individual messages and communication points.
- **Spring RSocket** combines messaging models with interaction modes such as request-response, fire-and-forget, request-stream, and request-channel. Handlers can accept or return `Flux` to process multi-element streams.
- **Reactor** provides operators to transform, combine, regulate, and handle errors within a pipeline.

Do not equate `MessageChannel` with `Flux`. `MessageChannel` is an abstraction for sending a single `Message`; `Flux` is a `Publisher` emitting a sequence of elements under the Reactive Streams protocol. When bridging the two models, you need an adapter or integration mechanism with clear policies for buffering, errors, cancellation, and receive rate.

## 5. Backpressure: Consumer Controlling Data Volume

Backpressure is the mechanism by which a consumer signals back how much data it can accept. Instead of letting the producer emit freely without bound, the consumer requests batches of elements matching its processing capacity.

For example, a consumer can request 50 elements, finish processing them, and only then request another 50 elements. If it is busy writing to a database, it can delay the next request. When a client cancels its subscription, the stream can stop the corresponding work.

Backpressure is useful when:

- Consumer throughput varies with load.
- Processing steps have varying costs.
- The producer is capable of honoring demand signals.
- The pipeline needs to bound the amount of data waiting in memory.

However, backpressure cannot automatically slow down every external data source. A UDP-only emitter, a non-pausable callback, or an event source that does not support demand can keep emitting even while the consumer is busy. For such sources, the application must choose buffering, dropping, sampling, rate-limiting, or durable storage policies at the ingestion boundary.

Backpressure also does not equate to business confirmation or data durability confirmation. `request(1)` only expresses demand for the next element; it does not prove that a database transaction committed or that an event was processed successfully in business terms.

## 6. Ways to Control the Receive Rate

No single policy fits every kind of data. Choose based on the importance of each element and the controllability of the source.

### 6.1. Batch Requesting with `request(n)`

The subscriber requests only a fixed number of elements. After finishing the current batch, it requests the next batch. This directly expresses Reactive Streams demand.

Suitable when the consumer can decide when to pull more data and wants to avoid receiving too many elements at once.

### 6.2. Limiting Upstream Requests with `limitRate`

In Reactor, `limitRate(n)` adjusts how a pipeline requests data from upstream in batches. This prevents a downstream step from requesting a huge amount of data all at once.

Example:

~~~java
Flux.range(1, 1000)
    .limitRate(32)
    .subscribe(this::process);
~~~

Here, `limitRate` regulates the request amounts forwarded upstream to the source. It is not an exact elements-per-second limiter. If the requirement is at most 100 events per second, use a time-based limiting policy or an appropriate rate limiter.

### 6.3. Buffering Data

A buffer stores elements while the consumer cannot keep up. Buffering can absorb short traffic bursts, but explicit bounds must be set.

- **Bounded buffer:** holds at most a fixed number of elements; when full, overflow behavior must be defined.
- **Unbounded buffer:** risks unbounded memory growth if the producer consistently outpaces the consumer.
- **Dead-letter or durable storage:** more suitable when data is critical and needs error recovery/reprocessing, depending on broker or storage capabilities.

Buffering only postpones the problem when the producer's average rate consistently exceeds the consumer's. It does not solve a sustained load imbalance.

### 6.4. Dropping Elements or Keeping Only the Latest Value

For telemetry or UI state data, it is not always necessary to process every sample. You can choose to drop new elements on overload, or retain only the latest element.

Reactor provides operators such as `onBackpressureDrop()` and `onBackpressureLatest()` for suitable scenarios. This policy reduces memory pressure, but means some values will not be processed. Do not use it for business events that must be fully preserved, such as payment commands or order state changes.

### 6.5. Slowing Down or Time-Based Sampling

`delayElements(Duration)` introduces a delay between elements delivered downstream. `sample(Duration)` samples periodically, while time-based `window` or `buffer` can group elements together.

These operators are helpful for data presentation or paced processing. However, `delayElements` is not a global rate limiter and does not enforce an events-per-second limit across multiple subscribers. For strict traffic-shaping requirements, use a time-based rate limiter or quota mechanism.

### 6.6. Limiting Concurrent Processing Tasks

Even when the receive rate is appropriate, a consumer can still spawn too many concurrent tasks. `flatMap` allows concurrent processing of elements; a concurrency limit can be set to bound running tasks. `concatMap` processes sequentially, useful when ordering must be preserved or only one task may run at a time.

Controlling concurrency protects resources such as connection pools, external APIs, and thread pools. Balance throughput against latency.

## 7. Choosing a Policy by Data Type

| Data Type | Typically Suitable Policy | Reason |
|---|---|---|
| Payment commands, orders | Backpressure, durable queue, bounded retries | Events must not be arbitrarily dropped |
| High-frequency sensor readings | Sampling, keeping latest value, or bounded buffer | Fresh values are usually more useful than stale samples |
| Market prices | Demand-driven stream, short buffer, and stale-drop policy per requirements | Needs low latency and fresh data |
| Logs and audit | Durable broker/queue, batching, and consumer control | Needs preservation and traceability |
| UI state | Latest, sample, or per-client throttling | No need to send every intermediate change |

Clearly identify which data may be dropped, which must be stored, maximum wait times, and acceptable latency before choosing operators.

## 8. Example: Receiving Messages in Batches with Reactor

The following example creates a `Flux` of 10 Spring `Message` instances. The subscriber requests only the first three elements. Only after finishing each batch of three elements does it request the next batch.

The example uses Java 17, Spring Messaging 6.2.8, and Reactor Core 3.7.6. This is a standalone console program for observing the demand protocol; it does not start a broker or a WebFlux server.

Project structure:

~~~text
stream-demand-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── StreamDemandDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>stream-demand-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.7.6</version>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### src/main/java/demo/StreamDemandDemo.java

~~~java
package demo;

import org.reactivestreams.Subscription;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public class StreamDemandDemo {

    public static void main(String[] args) {
        Flux<Message<Integer>> stream = Flux.range(1, 10)
                .map(value -> MessageBuilder.withPayload(value)
                        .setHeader("source", "sensor-01")
                        .build());

        stream.subscribe(new BaseSubscriber<Message<Integer>>() {
            private int receivedInBatch;

            @Override
            protected void hookOnSubscribe(Subscription subscription) {
                System.out.println("Subscribed; request 3");
                request(3);
            }

            @Override
            protected void hookOnNext(Message<Integer> message) {
                System.out.println("Received: " + message.getPayload());
                receivedInBatch++;

                if (receivedInBatch == 3 && message.getPayload() < 10) {
                    receivedInBatch = 0;
                    System.out.println("Request next 3");
                    request(3);
                }
            }

            @Override
            protected void hookOnComplete() {
                System.out.println("Completed");
            }

            @Override
            protected void hookOnError(Throwable error) {
                System.err.println("Stream failed: " + error.getMessage());
            }
        });
    }
}
~~~

Run in the directory containing `pom.xml`:

~~~shell
mvn -q compile exec:java -Dexec.mainClass=demo.StreamDemandDemo
~~~

Output:

~~~text
Subscribed; request 3
Received: 1
Received: 2
Received: 3
Request next 3
Received: 4
Received: 5
Received: 6
Request next 3
Received: 7
Received: 8
Received: 9
Request next 3
Received: 10
Completed
~~~

Explanation:

1. `Flux.range(1, 10)` creates a source of ten elements.
2. `map(...)` wraps each number into a Spring `Message<Integer>` and adds a `source` header.
3. `BaseSubscriber` lets you control demand with `request(n)`.
4. `hookOnSubscribe` requests the first three elements.
5. `hookOnNext` processes each `Message`. Once three elements have been received, the subscriber requests three more.
6. When the source runs out of data, the subscriber receives `hookOnComplete`.

`Flux.range` is a synchronous and finite source, so the example runs quickly on a single execution thread. It illustrates element counts requested via Reactive Streams; it does not simulate a time-based limit such as 100 events per second. In a real application, a consumer can request the next batch after completing data writes or when a resource becomes ready.

## 9. Connecting Streams with Spring Messaging

Spring Messaging provides `Message` and abstractions for components to exchange messages. When an application needs streaming, Reactor and corresponding transport integrations can be used.

For example, an RSocket handler can return a `Flux` to stream data continuously:

~~~java
@Controller
public class TelemetryController {

    @MessageMapping("telemetry")
    public Flux<Telemetry> streamTelemetry() {
        return Flux.interval(Duration.ofSeconds(1))
                .map(sequence -> new Telemetry(sequence, sequence * 0.5));
    }
}

public record Telemetry(long sequence, double value) {
}
~~~

This is a handler snippet and must be placed inside an application configured with an RSocket server and the corresponding dependencies. A client sending a request-stream to the `telemetry` route receives the stream of values. RSocket supports stream interactions and Reactive Streams demand mechanics.

A WebFlux endpoint can return a `Flux` to transmit data as Server-Sent Events:

~~~java
@GetMapping(value = "/telemetry", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<Telemetry>> telemetry() {
    return Flux.interval(Duration.ofSeconds(1))
            .map(sequence -> ServerSentEvent.builder(
                    new Telemetry(sequence, sequence * 0.5))
                    .event("measurement")
                    .build());
}
~~~

This snippet requires a WebFlux controller and corresponding HTTP configuration. Server-Sent Events fit unidirectional streams from server to browser. If two-way communication or routing multiple message types is required, consider WebSocket or RSocket according to requirements.

When connecting a `Flux` to a `MessageChannel` or broker, inspect how the adapter translates demand into actual receive/send operations. Never assume every channel or broker supports `request(n)` identically. An adapter may require prefetch limits, bounded queues, acknowledgements, or dedicated overflow policies.

## 10. Errors and Stream Lifecycle

A stream has a clear lifecycle:

- `onNext`: an element is emitted to the subscriber.
- `onError`: the stream terminates due to an error.
- `onComplete`: the source completes normally.
- `cancel`: the subscriber actively stops receiving.

In unbounded streaming applications, `onComplete` may not occur until the source closes. When a client disconnects, cancel the subscription and release resources such as connections, timers, or listeners.

Some error-handling principles:

**Do not retry every error infinitely:** invalid data errors or business errors usually do not resolve on retry. Limit retry attempts and record the cause.

**Set timeouts when waiting on external resources:** a single element stuck calling an API or writing to a database can cause the backlog to grow.

**Distinguish element-level errors from stream-wide errors:** depending on design, handle an individual element's error and continue, or terminate the entire stream when state is no longer safe.

**Release on cancellation:** use hooks or cleanup mechanisms to close resources when a subscriber cancels or the stream ends.

**Propagate correlation/trace context:** link logs across the producer, processing steps, and consumer to investigate latency or failures.

## 11. Common Misconceptions

**Assuming `Flux` automatically rate-limits per second:** `Flux` supports demand and backpressure, but does not impose a quota like 100 elements per second by itself. Distinguish element-count control from time-based limits.

**Assuming `limitRate` is a rate limiter:** `limitRate` regulates batch request sizes sent upstream. It does not guarantee a fixed rate per second.

**Assuming buffers solve long-term overload:** buffers only absorb short-term mismatches. If the producer consistently outpaces the consumer, the buffer will fill up or grow unboundedly if no threshold is set.

**Assuming backpressure can stop every external source:** only publishers or adapters supporting throttling can respond to demand. Non-pausable sources need buffering, sampling, dropping, or durable storage policies.

**Assuming `MessageChannel` already has backpressure:** `MessageChannel` represents sending a `Message`. Sending, buffering, and processing depend on the implementation; it does not carry the Reactive Streams protocol by itself.

**Assuming `request(n)` is business confirmation:** `request(n)` only asks the publisher to emit up to `n` elements. It does not confirm committed data or completed transactions.

**Using drop policies for critical events:** drop/latest fit certain telemetry or UI streams, but can corrupt business state if used for payments, orders, or audits.

## 12. Checklist for Designing a Data Stream

Before putting a stream into production, answer:

1. Does the data source support backpressure or pausing emission?
2. How many elements per second and how many concurrent elements can the consumer process?
3. May data be dropped, sampled, or kept as latest value only?
4. What is the maximum buffer size and what is the behavior when the buffer is full?
5. Must ordering be preserved by a business key?
6. When a client cancels or a service stops, how are subscriptions and resources released?
7. How many times are errors retried, and is there a dead-letter queue or durable storage?
8. Are there metrics for throughput, backlog, latency, overflows, errors, and active subscription counts?
9. Are limits applied per subscriber, per tenant, or system-wide?
10. How are security and authorization enforced for publishers, consumers, and routes?

## 13. Key Takeaways

- A `Message` is a single unit of data; a stream is a sequence of elements emitted over time.
- Reactive Streams uses `Publisher`, `Subscriber`, and `Subscription` to propagate demand.
- `request(n)` signals that the subscriber is ready to receive up to `n` more elements; `cancel()` stops the subscription.
- `Flux` represents 0 to many elements; `Mono` represents 0 or 1 element.
- Backpressure regulates flow when the publisher can honor demand.
- `limitRate` adjusts batched requests, whereas a rate limiter controls traffic over time.
- Buffering, dropping, latest, sampling, and concurrency limits are distinct policies; choose according to data criticality.
- Spring Messaging's `MessageChannel` does not inherently provide Reactive Streams backpressure. When integrating with Reactor, WebFlux, RSocket, or brokers, understand the adapter and transport-level flow-control policies.
