# Distinguishing Reactive Functions from the Reactive Kafka Binder and Checking Support Status

In Spring Cloud Stream, writing a function that accepts or returns Flux or Mono is not enough to conclude that the entire application processes reactively from broker to broker. A reactive function describes how application code works with a data stream. The binder decides how Spring Cloud Stream connects that stream to Kafka, RabbitMQ, or Pulsar. If the binder uses an imperative message-channel API, Reactor operators can still execute inside the function, but the delivery boundary with the broker does not automatically become Reactive Streams.

The Reactive Kafka Binder used to provide a Kafka integration path based on Reactor Kafka, using KafkaReceiver and KafkaSender to support more end-to-end backpressure. However, Reactor Kafka has been announced as discontinued and the Reactive Kafka Binder has been deprecated, with artifact removal noted in some release trains. Therefore, when learning or maintaining Spring Cloud Stream, clearly distinguish a function's reactive capabilities from the binder's support status for the exact version in use.

## 1. Two Distinct Layers: Reactive Functions and Reactive Binders

A reactive function belongs to the Spring Cloud Function programming model. It uses Project Reactor types such as Flux<T> and Mono<T> to represent a multi-element stream or a single asynchronous result.

A reactive binder belongs to the middleware integration layer. It must receive and send data using a reactive broker/client API so that demand and backpressure can propagate across the application boundary to the data source.

| Concept | Responsibility | Example |
|---|---|---|
| Reactive function | Processes data streams with Reactor | Function<Flux<Order>, Flux<OrderView>> |
| Imperative Kafka binder | Connects bindings to Kafka via message channels/listener containers | spring-cloud-starter-stream-kafka |
| Reactive Kafka Binder | Connects bindings to Kafka via the Reactor Kafka API | spring-cloud-stream-binder-kafka-reactive in versions that provided the artifact |
| Reactive Streams | Publisher/Subscriber protocol with demand and backpressure | Flux, Mono, Subscription |

The key distinction is that using a reactive API in a function does not automatically make the binder reactive. A Function<Flux<T>, Flux<R>> can run with the standard Kafka binder, yet only processing inside the function has Reactor semantics. When the binder is message-channel based, fetching records from Kafka and sending records to Kafka still follow the standard binder's mechanics.

## 2. How Does a Reactive Function Work?

Spring Cloud Function supports Supplier, Function, and Consumer with reactive types. For example, a Function can receive Flux<OrderEvent>, filter events, and transform each element:

~~~java
import java.util.function.Function;
import reactor.core.publisher.Flux;

public record OrderEvent(String orderId, int quantity) {}

public record OrderView(String orderId, String category) {}

@Bean
Function<Flux<OrderEvent>, Flux<OrderView>> toOrderView() {
    return events -> events
        .filter(event -> event.quantity() > 0)
        .map(event -> new OrderView(
            event.orderId(),
            event.quantity() >= 10 ? "BULK" : "NORMAL"
        ));
}
~~~

The function above is not called once per OrderEvent the way an imperative Function is. A reactive function is a stream-initializing function: the framework calls it to obtain the output Flux and connects that stream to the input stream. Operators then execute as data flows through the pipeline.

~~~mermaid
flowchart LR
    A["Flux<OrderEvent>"] --> B["filter"]
    B --> C["map"]
    C --> D["Flux<OrderView>"]
~~~

Operators such as map, filter, concatMap, flatMap, and onErrorResume describe how data is processed. When there is a subscriber and demand, new elements emit through the pipeline. Some operators introduce internal buffers or prefetch, so choose operators and concurrency limits suitable for your load.

## 3. Reactive Functions with the Standard Kafka Binder

An application can declare a reactive function while still using the message-channel-based Kafka binder. Example dependency:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-kafka</artifactId>
</dependency>
~~~

Binding configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: toOrderView
    stream:
      bindings:
        toOrderView-in-0:
          destination: orders.events
          group: order-viewer
          content-type: application/json
        toOrderView-out-0:
          destination: orders.views
          content-type: application/json
~~~

In this configuration, toOrderView is a reactive function, while the selected binder is the standard Kafka binder. Spring Cloud Stream still uses the binder's message-channel and consumer/producer mechanisms to exchange messages with Kafka.

What the application gets:

- Ability to use Flux and Mono to write data-processing pipelines.
- Ability to use Reactor operators to transform, combine, or process asynchronously within the function scope.
- Ability to structure code in a reactive style without rewriting all business logic into callbacks or imperative loops.

What the application does not automatically get simply by using Flux/Mono:

- Backpressure from a subscriber does not automatically cross the message channel to the Kafka fetch loop.
- The Kafka producer/consumer does not automatically become a reactive KafkaSender/KafkaReceiver.
- You must not infer end-to-end load throttling solely from the function's reactive signature.

Thus, a reactive function with a standard binder is typically a reactive model at the processing layer. The boundary with the broker still follows that binder's model.

## 4. What Did the Reactive Kafka Binder Provide?

The Reactive Kafka Binder was a separate binder built on Reactor Kafka. On the receiving side, the binder used KafkaReceiver to produce a reactive stream of records. On the sending side, the binder used KafkaSender to publish records. When both ends were connected with reactive APIs, demand and backpressure could participate in data consumption and emission.

Conceptual diagram:

~~~mermaid
flowchart LR
    K[("Kafka topic")] --> R["KafkaReceiver"]
    R --> F["Reactive function<br/>Flux / Mono"]
    F --> S["KafkaSender"]
    S --> O[("Kafka topic")]
    F -. "Demand / backpressure" .-> R
    S -. "Reactive send result" .-> F
~~~

Example function:

~~~java
@Bean
Function<Flux<String>, Flux<String>> uppercase() {
    return values -> values.map(String::toUpperCase);
}
~~~

In terms of signature, this function can run with both the standard Kafka binder and the Reactive Kafka Binder. The difference lies in the underlying connection path:

| Component | Standard Kafka binder | Reactive Kafka Binder |
|---|---|---|
| Broker-side consumer | Kafka listener/message channel | Reactor Kafka KafkaReceiver |
| Broker-side producer | Kafka producer/message channel | Reactor Kafka KafkaSender |
| Reactive function | Supported | Supported |
| Backpressure inside function | Yes, within Reactor pipeline scope | Yes |
| Backpressure across Kafka boundary | Not guaranteed by message-channel-based binder | Was the goal of the reactive binder |
| Current status | Maintained binder in Spring Cloud Stream ecosystem | Deprecated; artifact removed in some release trains |

The Maven coordinates of the old binder used to be:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-binder-kafka-reactive</artifactId>
</dependency>
~~~

This snippet is only for recognizing the dependency in legacy applications. Do not copy it into new projects if your release train's BOM no longer manages it or release notes announce its removal.

Do not add both binders and assume the framework will pick the reactive path. Dependencies and the active binder must be explicitly determined in configuration. When an application has multiple binders on the classpath, each binding's binder property can also determine the effective binder.

## 5. Support Status of the Reactive Kafka Binder

Support status changed following the decision to discontinue Reactor Kafka. Read the release notes for your exact Spring Cloud release train rather than relying on an old blog example or a reference page that still exists.

Key milestones announced by Spring:

| Milestone | Details |
|---|---|
| 2025-05-20 | Project Reactor announced Reactor Kafka will stop being maintained in the future; Spring Cloud Stream's Reactor Kafka Binder and Spring for Apache Kafka's reactive template were marked deprecated and slated for removal |
| Spring Cloud Stream 4.3.0 | Reactive Kafka Binder documentation explicitly states the binder is deprecated and will be removed in a future release |
| Spring Cloud 2025.1.0 | Release notes state the org.springframework.cloud:spring-cloud-stream-binder-kafka-reactive artifact was removed from the release train due to Reactor Kafka being discontinued |
| Spring Cloud 2026.0.0 | Release train announcement continues listing deprecation of the Reactive Kafka Binder due to Reactor Kafka being discontinued |

The Reactive Kafka Binder reference page in Spring Cloud Stream 5.1.0 documentation is still published, yet the top of the page continues warning that the binder has been deprecated since 4.3.0 and will be removed in the future. Release notes across trains are not completely identical in wording between deprecated and removed. Therefore, the existence of a documentation page does not prove an artifact is still released or supported in a specific BOM.

Practical rules:

1. Do not choose Reactive Kafka Binder as the default for new projects.
2. Check the release notes for the exact Spring Cloud release train you use.
3. Inspect dependency management/BOM and the artifact repository to confirm whether the artifact actually exists for that version.
4. If the artifact is no longer in the train, do not force an old version into the dependency graph just to make the build pass.
5. If maintaining a legacy application using this binder, document its deprecated status, evaluate a migration plan, and check Reactor Kafka's support timeline.

## 6. Inspecting Actual Dependencies and Versions

Do not look solely at dependency declarations in build files. Inspect the dependency tree after importing the Spring Cloud BOM.

With Maven:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.cloud:spring-cloud-stream-binder-kafka-reactive
./mvnw dependency:tree -Dincludes=io.projectreactor.kafka:reactor-kafka
./mvnw help:effective-pom
~~~

With Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-cloud-stream-binder-kafka-reactive --configuration runtimeClasspath
./gradlew dependencyInsight --dependency reactor-kafka --configuration runtimeClasspath
./gradlew dependencies --configuration runtimeClasspath
~~~

When reading the output:

- If no reactive binder artifact appears in the dependency graph, the application is not using that binder even if functions accept Flux.
- If the artifact appears via a transitive dependency, identify which module pulls it in and why.
- Verify whether the Reactor Kafka version aligns with the train and BOM in use.
- Check binding initialization logs to see which binder is actually selected.
- Do not manually override old Reactor Kafka or binder versions if the release train no longer manages them.

You can also search Maven Central using the exact coordinates and version published in the release notes. Finding an artifact at an older version only proves it was once published, not that it remains maintained or compatible with current Spring Cloud Stream.

## 7. Appropriate Direction for New Applications

Current Spring Cloud Stream documentation guides users to continue using the message-channel-based Kafka binder with reactive types if they want to write functions using Reactor. Reactive scenarios must be handled explicitly with Project Reactor while understanding the binder's boundaries.

Example of an asynchronous processing Function with bounded concurrency:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderResult>> processOrders(
        OrderService orderService) {
    return events -> events
        .flatMap(orderService::process, 8);
}
~~~

Here flatMap allows up to eight concurrent process tasks within the operator scope. If completion order must match input order, use concatMap:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderResult>> processInOrder(
        OrderService orderService) {
    return events -> events
        .concatMap(orderService::process);
}
~~~

Choose operators based on business requirements:

| Operator | Behavior | When to use |
|---|---|---|
| map | Synchronously transforms each element | Fast calculations without I/O |
| concatMap | Converts each element to a Publisher and waits in order | Need sequential processing or preserving output order |
| flatMap | Runs inner Publishers concurrently | Need higher throughput and can accept out-of-order results |
| flatMap with concurrency | Limits concurrent inner tasks | Need to cap active requests or connections |
| onErrorResume | Translates errors into a replacement stream | Have a fallback policy or business failure outcome |
| retryWhen | Resubscribes to source on error per policy | Transient errors and safely repeatable operations |

Concurrency in flatMap only limits tasks inside the pipeline. It does not replace consumer binding concurrency configuration nor does it control the number of Kafka partitions.

## 8. Reactive Consumers and Why Mono<Void> Is Needed

Consumer<T> has a void return type. When declaring Consumer<Flux<T>>, the framework receives no returned Publisher to know when reactive processing completes or to subscribe to it. Therefore, Spring Cloud Stream documentation recommends expressing a reactive consumer as Function<Flux<T>, Mono<Void>> and terminating the pipeline with then().

~~~java
import reactor.core.publisher.Mono;

@Bean
Function<Flux<OrderEvent>, Mono<Void>> saveOrders(
        OrderService orderService) {
    return events -> events
        .concatMap(orderService::save)
        .then();
}
~~~

Mono<Void> indicates the pipeline completes without emitting result values. The framework can work with the returned Publisher. If you actually use Consumer<Flux<T>>, your code must subscribe to the Flux itself; otherwise, the pipeline may never execute.

Do not call subscribe() arbitrarily inside a Function returning Flux or Mono. Subscribing manually creates a processing stream detached from the returned Publisher, preventing the framework from fully tracking completion, errors, and pipeline lifecycle. Only use explicit subscribe when an API requires a void Consumer and the application takes responsibility for managing the subscription.

## 9. Error Handling and Retries in Reactive Functions

Spring Cloud Stream has error-handling and retry mechanisms at the imperative message handler boundary. With imperative functions, the framework calls the handler per message and can wrap each call with retry logic.

A reactive function is invoked to build the stream, and the framework does not control every internal operation once the pipeline is wired. Consequently, errors occurring while Flux runs must be handled with Reactor operators.

Example:

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

@Bean
Function<Flux<OrderEvent>, Flux<OrderResult>> processSafely(
        OrderService orderService) {
    return events -> events
        .flatMap(event -> orderService.process(event)
            .onErrorResume(error ->
                Mono.just(OrderResult.failed(event.orderId(), error.getMessage()))
            ), 8);
}
~~~

The example above turns each order's error into a failed outcome so one element's failure does not necessarily terminate the whole stream. If retries are needed, place retryWhen around each event's Publisher:

~~~java
events.flatMap(event ->
    orderService.process(event)
        .retryWhen(Retry.backoff(3, Duration.ofMillis(200)))
        .onErrorResume(error ->
            Mono.just(OrderResult.failed(event.orderId(), "PROCESSING_FAILED"))
        ),
    8
);
~~~

Retries can re-invoke an operation that partially executed. If process writes to a database, emits events, or calls external services, design idempotency and timeouts. Avoid infinite retries or retrying every error type; invalid data errors generally do not resolve on retry.

## 10. Backpressure Does Not Mean System-Wide Load Limits

Reactive Streams backpressure lets a subscriber request how many elements it can handle. A compatible publisher can adjust emission rates based on demand. Yet to apply this from Kafka to the function and back, each component at the boundary must support that reactive protocol.

With the standard Kafka binder:

- The Kafka consumer is driven by the binder's consumer/listener configuration.
- Messages are transferred via the message-channel mechanism.
- The reactive function can process Publishers internally.
- Demand in Flux does not automatically propagate back as a request to reduce Kafka consumer fetches.

Therefore, when using the standard binder, you still must design operational limits:

- Limit concurrency of asynchronous tasks inside flatMap.
- Control concurrent requests to databases or HTTP services.
- Configure consumer concurrency, poll records, pause/resume, or appropriate binder/client throttling mechanisms.
- Set timeouts and queue/buffer bounds at boundaries where data can accumulate.
- Monitor consumer lag, processing time, and pending request counts.

If an operator creates an unbounded buffer or calls external services with excessive concurrency, using Flux alone will not prevent memory growth. Backpressure helps when source, operators, and sink all honor demand; if any component does not, dedicated bounding strategies are required.

## 11. Testing Reactive Functions

You can test Reactor pipelines independently of the Spring Context using StepVerifier:

~~~java
import java.util.function.Function;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class OrderFunctionTest {

    @Test
    void filtersInvalidEventsAndMapsValidOnes() {
        Function<Flux<OrderEvent>, Flux<OrderView>> function =
            events -> events
                .filter(event -> event.quantity() > 0)
                .map(event -> new OrderView(
                    event.orderId(),
                    event.quantity() >= 10 ? "BULK" : "NORMAL"
                ));

        StepVerifier.create(function.apply(Flux.just(
                new OrderEvent("A-1", 2),
                new OrderEvent("A-2", 12),
                new OrderEvent("A-3", 0)
            )))
            .expectNext(new OrderView("A-1", "NORMAL"))
            .expectNext(new OrderView("A-2", "BULK"))
            .verifyComplete();
    }
}
~~~

Tests should verify:

1. Emitted values and ordering when ordering is a business requirement.
2. Empty streams and zero-data cases.
3. Errors being propagated, substituted, or retried according to policy.
4. Concurrency limits on asynchronous tasks.
5. Cancellation and completion when the subscriber stops receiving data.

The Test Binder is useful for checking application bindings and message conversion, but it does not prove a message-channel binder supports end-to-end backpressure. To verify real behavior with Kafka, run integration tests using the exact binder, client, broker, and version planned for deployment.

## 12. Choosing Based on Requirements

| Requirement | Recommended choice |
|---|---|
| Want to use map/filter/flatMap to write processing logic | Reactive function with Flux/Mono |
| Want to use Spring Cloud Stream and Kafka with a maintained configuration | Standard Kafka binder |
| Want to use RabbitMQ with reactive functions | Standard Rabbit binder combined with Reactor in the function; do not assume a reactive transport |
| Want end-to-end Kafka backpressure via Reactive Kafka Binder | Check release train status first; do not choose for new projects as the binder is deprecated/removed in several trains |
| Operating a legacy app using Reactive Kafka Binder | Check artifact, Reactor Kafka version, support timeline, and migration plan |
| Need bounded asynchronous processing | Use flatMap with appropriate concurrency or concatMap when ordering is needed |
| Need per-message retries inside a reactive pipeline | Use retryWhen/onErrorResume in Reactor and ensure idempotency |

An architectural decision must consider both the function API and the actual binder. If the primary goal is readable and composable processing code, reactive functions can still be valuable with standard binders. If the goal is backpressure from broker to consumer and back, verify transport capabilities and binder support status rather than looking only at Flux/Mono signatures.

## 13. Support Status Verification Checklist

Before selecting the Reactive Kafka Binder or upgrading an application using it:

1. Record the Spring Boot and Spring Cloud release train versions.
2. Read the Reactive Kafka Binder page in documentation for the exact version.
3. Read the release train's release notes for deprecation, removal, or migration entries.
4. Check whether the spring-cloud-stream-binder-kafka-reactive artifact exists in the BOM and repository for that exact version.
5. Inspect the dependency tree to see where Reactor Kafka is pulled from.
6. Read official announcements regarding the Reactor Kafka lifecycle.
7. Verify acknowledgement, offset commit, retry, and backpressure APIs for the exact binder/version.
8. Run integration tests against a real broker and measure load behavior.
9. Plan replacements if the binder or dependency is deprecated/removed.

Official sources to check regularly:

- [Spring Cloud Stream - Reactive Functions support](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html): how reactive functions are invoked, reactive Consumer limitations, and differences when using non-reactive binders.
- [Spring Cloud Stream - Reactive Kafka Binder Overview](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-reactive-binder/overview.html): deprecation warning and binder status in current documentation.
- [Spring Cloud Stream - Reactive Kafka Binder Examples](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-reactive-binder/examples.html): KafkaReceiver, KafkaSender, offset acknowledgement, and reactive examples.
- [Reactor Kafka Project Will Be Discontinued](https://spring.io/blog/2025/05/20/reactor-kafka-discontinued/): decision to stop maintaining Reactor Kafka and deprecate related components.
- [Spring Cloud 2025.1.0 Release Announcement](https://spring.io/blog/2025/11/25/spring-cloud-2025-1-0-aka-oakwood-has-been-released/): note that the Reactive Kafka Binder artifact was removed from the release train.
- [Spring Cloud 2026.0.0 Release Announcement](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/): current release train details and deprecation notes.
