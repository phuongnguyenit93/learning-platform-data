# Controlling Element Splitting with the splittable Attribute

In Spring Cloud Stream, a producer can return a finite stream containing multiple elements. For example, a single repository query might return a list of pending order events waiting to be sent. When using a reactive supplier `Supplier<Flux<T>>`, the framework needs to know whether each element in the stream should become an individual message or whether the entire stream should be forwarded as a single unit. The `splittable` attribute of `@PollableBean` controls this decision.

By default, `splittable` is `true`: Spring Cloud Stream splits the stream and sends each element as a separate message. Setting `splittable = false` instructs the framework to keep the returned `Flux` intact without running the element-splitting step. This attribute is useful when building reactive producers with finite data fetched in batches, but you must understand its exact scope to avoid confusing it with partitioning, batching, or creating a list payload.

## 1. Context: Reactive Suppliers with Finite Data

A regular `Supplier<T>` is invoked by the framework via a poller. Each time it is called, the supplier returns a single value, and that value is emitted to the output binding.

```java
@Bean
Supplier<OrderEvent> orderEvent() {
    return () -> new OrderEvent("order-1001");
}
```

A reactive supplier has the type `Supplier<Flux<T>>` and returns a publisher. For a supplier representing a continuous stream, the framework typically calls `get()` once to receive the stream and subscribes to process elements emitted by that stream. This fits continuously live data sources.

Another case is a supplier that queries finite data in batches, such as fetching records from an outbox table or orders waiting to be emitted. In that scenario, the supplier needs to be called periodically to fetch the next batch. Spring Cloud Function provides the `@PollableBean` annotation to mark finite reactive suppliers that require re-polling. Spring Cloud Stream uses this metadata when creating the source and handling its output.

For example, a single query returns three events:

```java
Flux<OrderEvent> events = Flux.just(
    new OrderEvent("order-1001"),
    new OrderEvent("order-1002"),
    new OrderEvent("order-1003")
);
```

If this stream is emitted in split mode, the framework sends three separate messages. If unsplit, the framework forwards the `Flux` as an unsplit stream. That choice is expressed through the `splittable` attribute.

## 2. Role of @PollableBean and splittable

In modern versions of Spring Cloud Function, `@PollableBean` resides in the package:

```java
import org.springframework.cloud.function.context.PollableBean;
```

This annotation marks a finite reactive supplier bean that should be invoked by the poller. It serves as metadata so integration layers like Spring Cloud Stream can apply polling and process the output.

The `splittable` attribute determines whether the framework splits elements in the reactive result:

| Setting | Behavior |
|---|---|
| `@PollableBean` | Defaults to `splittable = true` |
| `@PollableBean(splittable = true)` | Each element of the stream is emitted as a separate message |
| `@PollableBean(splittable = false)` | Skips the splitting step; keeps the `Flux` returned by the supplier intact for the downstream processing path |

You can explicitly declare `true` even though it is the default. Being explicit helps readers see that each element is an independent message unit.

Remember that `splittable` is an attribute of the `@PollableBean` annotation, not a binding property in `application.yml`. Do not try to configure it by inventing keys like `spring.cloud.stream.bindings.output.splittable`.

Spring Cloud Function provides the annotation to mark the supplier. The annotation itself does not perform polling or message emission; integration frameworks like Spring Cloud Stream handle those behaviors. Therefore, calling the supplier directly in a unit test still returns a `Flux`; the splitting step must be verified at the integration layer.

## 3. Splitting a Stream into Individual Messages with splittable = true

Suppose a service periodically queries pending order events waiting to be sent. Each event needs to be sent individually so consumers can process, retry, and track it independently.

```java
@Configuration
public class PendingOrderSource {

    @PollableBean(splittable = true)
    public Supplier<Flux<OrderEvent>> pendingOrderEvents(
            OrderRepository repository) {

        return () -> Flux.fromIterable(
            repository.findPendingEvents()
        );
    }
}
```

The example assumes `findPendingEvents()` returns a finite list of `OrderEvent` items. On each poll, the supplier queries a fresh list and converts it into a `Flux`.

When `splittable = true`, if a query returns three elements, the output is split as follows:

```text
Single poll
    |
    v
Flux<OrderEvent>
    |
    +-- OrderEvent(order-1001) --> Message 1
    |
    +-- OrderEvent(order-1002) --> Message 2
    |
    +-- OrderEvent(order-1003) --> Message 3
```

Each message passes through the output binding as an independent unit of data. Example binding configuration:

```yaml
spring:
  cloud:
    function:
      definition: pendingOrderEvents
    stream:
      bindings:
        pendingOrderEvents-out-0:
          destination: orders.pending
          content-type: application/json
  integration:
    poller:
      fixed-delay: 5000
```

The `pendingOrderEvents-out-0` binding connects the producer to the `orders.pending` destination. `fixed-delay` sets the wait interval between polls in milliseconds; a value of `5000` corresponds to five seconds. Poller settings control when the supplier is invoked, while `splittable` controls how the returned stream is handled. The two settings have distinct responsibilities.

With three elements in one poll and splitting enabled, the framework performs three message emissions. If the next poll returns two elements, that cycle creates two more messages. The message count depends on how many elements the supplier actually returns in each poll.

## 4. Keeping the Stream Intact with splittable = false

There are cases where the downstream processing layer needs to receive the reactive stream as a single unit to apply further transformations or custom orchestration. In that case, you can set `splittable = false`:

```java
@Configuration
public class PendingOrderBatchSource {

    @PollableBean(splittable = false)
    public Supplier<Flux<OrderEvent>> pendingOrderBatch(
            OrderRepository repository) {

        return () -> Flux.fromIterable(
            repository.findPendingEvents()
        );
    }
}
```

With this setting, the framework does not split the `Flux` elements into individual messages at that step. The supplier passes the intact reactive stream to the downstream processing path.

Distinguish keeping a `Flux` intact from creating a single message whose payload is `List<OrderEvent>`. Setting `splittable = false` does not automatically aggregate elements into a list, does not create a batch DTO, and does not define a wire format for a broker to serialize a `Flux` object. If your goal is to send a single message containing the entire list, create an explicit batch payload type—such as `OrderEventBatch` containing `List<OrderEvent>`—and emit that payload type from an appropriate source. Only use `splittable = false` when the downstream processing path truly expects an unsplit reactive stream and downstream components support that representation.

Example explicit batch payload type:

```java
public record OrderEventBatch(
    String batchId,
    List<OrderEvent> events
) {}
```

A supplier emitting `OrderEventBatch` emits a single batch object according to the application contract. This is the explicit way to model cases where producer and consumer need to exchange an entire batch of data in one payload.

## 5. Comparing Both Modes on the Same Data

Suppose the supplier returns:

```java
return () -> Flux.just(
    new OrderEvent("order-1001"),
    new OrderEvent("order-1002"),
    new OrderEvent("order-1003")
);
```

Stream-processing outcome:

| Criterion | `splittable = true` | `splittable = false` |
|---|---|---|
| Split elements | Yes | No |
| Separate messages created by split step | One message per element | No per-element messages created in the split step |
| Downstream processing unit | Individual elements | Intact `Flux` stream |
| Consumer receiving individual events | Suitable | Not the behavior requested by this configuration |
| Use case | Emitting independent events | Downstream layer needs an unsplit reactive stream |

When choosing a mode, start from the output contract expected by the consumer. If the consumer expects `OrderEvent` and processes each order individually, choose split mode. If the application has another reactive pipeline that needs to process the entire publisher, you can keep the stream unsplit and verify the data types supported by each subsequent step.

## 6. splittable Is Not Partitioning or Batching

These three concepts solve different problems.

### Splitting

Splitting turns a multi-element stream into individual messages. For example, a `Flux<OrderEvent>` with three elements is split into three messages. The goal is to define message boundaries at the application layer.

### Partitioning

Partitioning determines which broker partition a message is written to. With Kafka, a partition key ensures events sharing a key land in the same partition to preserve per-partition ordering. Partitioning does not create extra messages from one element, nor does it alter the element count of a `Flux`.

### Batching

Batching groups multiple items into a single data unit processed or sent as a batch. A batch payload typically needs an explicit contract, such as `OrderEventBatch`. Batching can reduce send operations, but consumers must understand the batch structure and process the inner elements.

| Mechanism | Question Solved | Example |
|---|---|---|
| Splitting | How many messages is a multi-element stream converted into? | Three elements become three messages |
| Partitioning | Which partition is each message routed to? | Same order key goes to the same Kafka partition |
| Batching | What data unit are multiple elements grouped into? | One batch containing a list of 100 events |

Do not use `splittable` as a substitute for partition key configuration or to enable batching. If you need all three, design each step explicitly and verify the final result on the broker.

## 7. Choosing splittable Based on Event-Processing Requirements

Split mode is generally appropriate when:

- Each element is an independent business event.
- Consumers can process each event without needing to know about other events in the same poll.
- You want to track, retry, or route failed messages to a DLQ at the individual event level.
- You want the broker to distribute individual messages across consumers by consumer group and partition.
- Each event has its own ID, schema, or metadata.

Keeping the stream unsplit is appropriate when:

- The next component needs to operate on the entire publisher.
- A reactive pipeline will continue filtering, transforming, or combining data before establishing message boundaries.
- The processing path explicitly supports the preserved data type.
- The application has its own strategy for converting the stream into sendable payloads.

If the final consumer expects one message per element, split at the right boundary before the output binding. If the consumer expects a batch payload, model the batch as a concrete data type and test serialization rather than expecting `splittable` to fabricate a batch automatically.

## 8. Polling, Stream Size, and Data State

A pollable supplier is normally invoked periodically. If each invocation queries data from a database, control both the number of returned rows and the state of each record.

Operational principles:

- Return a finite stream per poll. Do not use `@PollableBean` on an infinite publisher meant to be subscribed to once as a continuous reactive source.
- Bound the number of records per query to avoid building an oversized stream in memory.
- Have a strategy to mark records as claimed, emitted, or needing re-emission. Otherwise, subsequent polls may re-emit the same data.
- Use stable event IDs so consumers can recognize already-processed events.
- Ensure consumers are idempotent because messages may be redelivered after failures or when emission state was not yet recorded.
- Monitor query duration, elements per poll, successfully emitted messages, and errors.

Do not assume a single poll with multiple elements forms an atomic transaction. When each element is emitted separately, an error on one element can be handled differently from elements that were already sent successfully. Retries, acknowledgments, and DLQs depend on the binder, broker, and error-handling settings. If business rules require all records in a batch to succeed or fail together, design an appropriate transaction or coordination mechanism instead of relying on `splittable`.

## 9. Testing Splitting Behavior

Test at two levels.

### Unit Testing the Supplier

Unit tests verify that the supplier returns a finite stream with the right elements in the right order:

```java
@Test
void supplierReturnsPendingOrderEvents() {
    Supplier<Flux<OrderEvent>> supplier =
        () -> Flux.just(
            new OrderEvent("order-1001"),
            new OrderEvent("order-1002")
        );

    StepVerifier.create(supplier.get())
        .expectNextMatches(event ->
            event.orderId().equals("order-1001"))
        .expectNextMatches(event ->
            event.orderId().equals("order-1002"))
        .verifyComplete();
}
```

This test only verifies the content returned by the supplier. It does not prove that the framework applied `splittable`.

### Integration Testing with the Spring Cloud Stream Test Binder

Use the Test Binder to boot the Spring context, register the pollable supplier, and inspect messages passing through the output binding. With `splittable = true`, emit a stream of three elements and assert that three distinct messages arrive with matching payloads. With `splittable = false`, verify that the pipeline receives the unsplit stream as designed by the application.

When testing the poller, control timing and supplier invocation counts so tests remain deterministic. You can use dedicated delay settings in tests or invoke the appropriate component directly if supported by your framework version. Avoid letting tests depend on long or non-deterministic default poll schedules.

The Test Binder verifies wiring and framework behavior in memory. When you need to verify serializers, actual broker records, header mapping, partition keys, or delivery acknowledgments, add integration tests with Kafka, RabbitMQ, or Pulsar accordingly.

## 10. Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Reactive supplier runs only once | Supplier is not marked pollable, so the framework treats it as a continuous reactive source | Use `@PollableBean` for a supplier producing a finite stream that needs periodic polling |
| Every element is sent as an unexpected separate message | `splittable` defaults to `true` | Set `splittable = false` if the pipeline must keep the stream intact |
| Consumer expects one batch but receives multiple messages | Element splitting is enabled | Create an explicit batch payload or redesign the pipeline |
| Consumer cannot process an unsplit Flux | Downstream path expects per-element payloads or does not support publishers | Use split mode or add an appropriate conversion step |
| Duplicate data emitted across polls | Re-querying the same records or incorrect claim/checkpoint state | Manage emission state and design idempotency |
| Supplier unit test passes but message count is wrong | Unit test bypasses post-processors and the binder | Add integration tests with the Test Binder |

## 11. Annotation Naming Differences Across Versions

Annotation names can differ across Spring Cloud Function generations:

- Older versions used `@PollableSupplier`.
- Newer versions use `@PollableBean` in the `org.springframework.cloud.function.context` package.

When working on a project, use a compatible Spring Boot and Spring Cloud release train, then check the actual Spring Cloud Function dependency to pick the right annotation. Do not mix examples from two API generations in the same application.

In modern examples, `@PollableBean(splittable = true)` or `@PollableBean(splittable = false)` expresses intent directly. Polling and output handling remain the responsibility of Spring Cloud Stream and its binders.

## 12. Pre-Deployment Checklist

- Confirm whether the supplier returns finite data or a continuous stream.
- Use `@PollableBean` for a finite reactive supplier that needs to be re-polled.
- Choose `splittable = true` if each element must become a separate message.
- Choose `splittable = false` only when the downstream processing path expects an intact `Flux`.
- Do not confuse splitting with partitioning or batching.
- Configure a dedicated poller for data-querying frequency.
- Bound the size of each poll and track record state.
- Design event IDs, retries, and idempotency to handle redelivery.
- Test the supplier, post-split message count, and binder behavior.
- Verify against a real broker if serialization, partitions, or delivery guarantees matter.

## 13. References

- [Spring Cloud Stream Reference — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html), Suppliers (Sources) section.
- [Spring Cloud Function Reference — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html), Supplier section.

The `splittable` attribute defines message boundaries when a pollable reactive supplier returns multiple elements. Default mode splits each element into an individual message; disabling splitting preserves the reactive stream for the next processing step. Choosing the right mode based on the output contract helps producers emit events consistently and ensures consumers process the exact data unit the application expects.
