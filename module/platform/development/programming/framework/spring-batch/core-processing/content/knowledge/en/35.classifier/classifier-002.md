# Classifying by Payload Type

In Spring Batch, a chunk sometimes contains multiple different payload types. For example, an integration stream might receive `OrderCreated`, `OrderCancelled`, and `PaymentReceived` within the same read. Each payload type needs to be written to a separate table, file, or destination system. In that case, the application needs to classify items by payload type and select the appropriate writer.

Spring Batch provides `ClassifierCompositeItemWriter<T>` to route items to delegate writers based on a `Classifier`. The classifier receives an item and returns the writer that will process it. This approach works when each item only needs to go to the selected writer. If every item must be written to all writers, use `CompositeItemWriter` instead of a classifier writer.

Classification can be based on the object's actual Java type, a discriminator field such as `payloadType` in JSON, or a business attribute. You need to define a clear payload contract, handle unsupported types, and keep type mapping safe and explicit.

## 1. What Is a Payload Type?

A payload is the data portion carrying business information. In an event system or consolidated import, a payload can represent multiple event types:

```text
Input stream
    |
    +--> OrderCreated
    |
    +--> OrderCancelled
    |
    +--> PaymentReceived
    |
    +--> RefundRequested
```

Each type can have a different structure and different write rules:

| Payload type | Key data | Example write destination |
|---|---|---|
| `OrderCreated` | Order ID, customer, amount | Orders table |
| `OrderCancelled` | Order ID, reason, cancelledAt | Cancellation history table |
| `PaymentReceived` | Payment ID, order ID, amount | Payments table |
| `RefundRequested` | Payment ID, refund amount, reason | Refund requests table |

If all payloads are read into a common type, such as `DomainEvent`, the processor can handle shared logic and the writer can classify by subtype to write to the right destination.

## 2. Two Ways to Determine Payload Type

Two sources of information are commonly used for classification.

**Runtime Java type:** the item has already been deserialized into a concrete object. You can use `instanceof` or check the class/interface to determine the subtype.

```java
if (payload instanceof OrderCreated created) {
    // Process OrderCreated
} else if (payload instanceof PaymentReceived payment) {
    // Process PaymentReceived
}
```

**Discriminator in data:** the raw payload has a field such as `type`, `eventType`, or `payloadType`. For example, JSON contains `"type": "ORDER_CREATED"`. The application reads the discriminator, checks an allowlist, and deserializes the payload data into the corresponding class.

Both approaches can work together: the discriminator determines the class during deserialization; then the Classifier routes based on the actual Java type. This allows writers to work with strongly typed domain models instead of repeatedly parsing JSON strings.

## 3. Payload Model Sharing a Common Interface

When payloads belong to the same business domain, declare a shared interface or base class:

```java
public sealed interface DomainEvent
        permits OrderCreated, OrderCancelled, PaymentReceived {
}

public record OrderCreated(
        long orderId,
        long customerId,
        BigDecimal amount
) implements DomainEvent {
}

public record OrderCancelled(
        long orderId,
        String reason
) implements DomainEvent {
}

public record PaymentReceived(
        long paymentId,
        long orderId,
        BigDecimal amount
) implements DomainEvent {
}
```

In this Java 17 example, `sealed interface` restricts the permitted subtypes. If the project uses an older Java version, a regular interface or abstract class can be used.

The reader can return `DomainEvent`; the classifier accepts this common type and selects a writer by subtype. A common type gives the Step a clear contract while preserving each item's concrete type information.

## 4. Classifier in Spring

`Classifier<C, T>` is a simple abstraction: it accepts an input object and returns a classification result. For writer routing, the input is the payload and the result is the delegate writer.

Conceptually, a classifier looks like this:

```java
public interface Classifier<C, T> {
    T classify(C classifiable);
}
```

Example classifier for `DomainEvent`:

```java
public class DomainEventWriterClassifier
        implements Classifier<DomainEvent, ItemWriter<? super DomainEvent>> {

    private final ItemWriter<? super DomainEvent> orderWriter;
    private final ItemWriter<? super DomainEvent> cancellationWriter;
    private final ItemWriter<? super DomainEvent> paymentWriter;

    public DomainEventWriterClassifier(
            ItemWriter<? super DomainEvent> orderWriter,
            ItemWriter<? super DomainEvent> cancellationWriter,
            ItemWriter<? super DomainEvent> paymentWriter) {
        this.orderWriter = orderWriter;
        this.cancellationWriter = cancellationWriter;
        this.paymentWriter = paymentWriter;
    }

    @Override
    public ItemWriter<? super DomainEvent> classify(DomainEvent event) {
        if (event instanceof OrderCreated) {
            return orderWriter;
        }
        if (event instanceof OrderCancelled) {
            return cancellationWriter;
        }
        if (event instanceof PaymentReceived) {
            return paymentWriter;
        }

        throw new IllegalArgumentException(
                "Unsupported payload type: " + event.getClass().getName()
        );
    }
}
```

A classifier should be deterministic, easy to test, and free of side effects. It only selects the write destination; writing the data is the responsibility of the delegate writer.

## 5. Using ClassifierCompositeItemWriter

`ClassifierCompositeItemWriter<T>` accepts a classifier to decide the writer for each item. It can be configured with a builder:

```java
@Bean
public ClassifierCompositeItemWriter<DomainEvent> eventWriter(
        Classifier<DomainEvent, ItemWriter<? super DomainEvent>> eventWriterClassifier) {

    return new ClassifierCompositeItemWriterBuilder<DomainEvent>()
            .classifier(eventWriterClassifier)
            .build();
}
```

When the Step invokes the writer with a chunk containing multiple subtypes, the classifier determines the appropriate delegate for each item. Items classified to the same delegate are passed to that delegate for writing.

Example of a mixed chunk:

```text
Chunk<DomainEvent>
  [OrderCreated, PaymentReceived, OrderCancelled, OrderCreated]
                    |
                    v
          ClassifierCompositeItemWriter
                    |
          +---------+----------+
          |         |          |
          v         v          v
      OrderWriter PaymentWriter CancellationWriter
       [2 items]   [1 item]       [1 item]
```

Unlike `CompositeItemWriter`, the classifier writer does not send every item to every delegate. Each item is routed according to the classification result.

## 6. Delegate Writers with a Common Type

If the writers can accept the common type `DomainEvent`, configuration is fairly straightforward:

```java
@Bean
public ItemWriter<DomainEvent> orderEventWriter(OrderRepository repository) {
    return chunk -> {
        for (DomainEvent event : chunk) {
            OrderCreated created = (OrderCreated) event;
            repository.insert(created.orderId(), created.customerId(), created.amount());
        }
    };
}
```

However, a common type can force code to cast inside the writer. If a specialized delegate writer wants to accept `ItemWriter<OrderCreated>`, you need an adapter responsible for checking and converting the type from the common interface to the subtype.

## 7. Type-Safe Adapter for Specialized Writers

An adapter can implement `ItemWriter<DomainEvent>`, verify that each item has the expected subtype, and then forward the chunk to the specialized writer:

```java
public class TypedEventWriter<P extends DomainEvent>
        implements ItemWriter<DomainEvent> {

    private final Class<P> payloadType;
    private final ItemWriter<P> delegate;

    public TypedEventWriter(Class<P> payloadType, ItemWriter<P> delegate) {
        this.payloadType = payloadType;
        this.delegate = delegate;
    }

    @Override
    public void write(Chunk<? extends DomainEvent> chunk) throws Exception {
        Chunk<P> typedChunk = new Chunk<>();

        for (DomainEvent event : chunk) {
            if (!payloadType.isInstance(event)) {
                throw new IllegalArgumentException(
                        "Expected " + payloadType.getName()
                                + " but received " + event.getClass().getName()
                );
            }
            typedChunk.add(payloadType.cast(event));
        }

        delegate.write(typedChunk);
    }
}
```

An adapter keeps business writers with concrete generic types while satisfying the common writer type that the classifier must return. Checking the subtype in the adapter catches classifier configuration errors early instead of performing unsafe casts deep inside the writer.

If the adapter wraps a delegate that implements `ItemStream`, the adapter must also forward `open()`, `update()`, and `close()`, or the Step must register the delegate stream explicitly. Never skip lifecycle management when a child writer holds state/checkpoints.

## 8. Complete Configuration with Specialized Writers

Suppose there are three writers:

```java
@Bean
public ItemWriter<OrderCreated> orderCreatedWriter(OrderRepository repository) {
    return chunk -> repository.insertCreatedOrders(chunk.getItems());
}

@Bean
public ItemWriter<OrderCancelled> orderCancelledWriter(OrderRepository repository) {
    return chunk -> repository.insertCancellations(chunk.getItems());
}

@Bean
public ItemWriter<PaymentReceived> paymentReceivedWriter(PaymentRepository repository) {
    return chunk -> repository.insertPayments(chunk.getItems());
}
```

Create an adapter for each subtype:

```java
@Bean
public ItemWriter<DomainEvent> orderCreatedAdapter(
        ItemWriter<OrderCreated> orderCreatedWriter) {
    return new TypedEventWriter<>(OrderCreated.class, orderCreatedWriter);
}

@Bean
public ItemWriter<DomainEvent> orderCancelledAdapter(
        ItemWriter<OrderCancelled> orderCancelledWriter) {
    return new TypedEventWriter<>(OrderCancelled.class, orderCancelledWriter);
}

@Bean
public ItemWriter<DomainEvent> paymentReceivedAdapter(
        ItemWriter<PaymentReceived> paymentReceivedWriter) {
    return new TypedEventWriter<>(PaymentReceived.class, paymentReceivedWriter);
}
```

Classifier:

```java
@Bean
public Classifier<DomainEvent, ItemWriter<? super DomainEvent>> eventWriterClassifier(
        ItemWriter<DomainEvent> orderCreatedAdapter,
        ItemWriter<DomainEvent> orderCancelledAdapter,
        ItemWriter<DomainEvent> paymentReceivedAdapter) {

    return event -> {
        if (event instanceof OrderCreated) {
            return orderCreatedAdapter;
        }
        if (event instanceof OrderCancelled) {
            return orderCancelledAdapter;
        }
        if (event instanceof PaymentReceived) {
            return paymentReceivedAdapter;
        }
        throw new IllegalArgumentException(
                "Unsupported event: " + event.getClass().getName()
        );
    };
}
```

Classifier composite:

```java
@Bean
public ClassifierCompositeItemWriter<DomainEvent> domainEventWriter(
        Classifier<DomainEvent, ItemWriter<? super DomainEvent>> eventWriterClassifier) {

    return new ClassifierCompositeItemWriterBuilder<DomainEvent>()
            .classifier(eventWriterClassifier)
            .build();
}
```

Each specialized writer only receives its exact subtype. The adapter performs type checking and converts the chunk before invoking the delegate.

## 9. Classifying with instanceof or getClass()?

Two common checks:

```java
if (payload instanceof OrderCreated) {
    // route
}
```

and:

```java
if (payload.getClass() == OrderCreated.class) {
    // route
}
```

`instanceof` accepts objects that are instances of a subtype or matching implementation. `getClass() == ...` matches only that exact runtime class.

Usually, `instanceof` is more appropriate when classifying polymorphically, especially when subclasses or proxies are involved. Exact class checks should only be used when the contract requires excluding all subtypes.

Avoid classifying with `getClass().getSimpleName()` or class name strings because it easily breaks on rename/refactor and is hard to control with input data. Use Java types, an enum discriminator, or an explicit registry.

## 10. Classifying with a Discriminator Field

A reader cannot always produce a Java subtype right from the start. A payload may be read as an envelope:

```java
public record EventEnvelope(
        String payloadType,
        JsonNode payload
) {
}
```

Example JSON:

```json
{
  "payloadType": "PAYMENT_RECEIVED",
  "payload": {
    "paymentId": 9001,
    "orderId": 1001,
    "amount": 125.50
  }
}
```

An allowlist registry can be used to convert the discriminator into a subtype:

```java
public class EventPayloadMapper {

    private final ObjectMapper objectMapper;

    public EventPayloadMapper(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public DomainEvent toDomainEvent(EventEnvelope envelope) throws JsonProcessingException {
        return switch (envelope.payloadType()) {
            case "ORDER_CREATED" -> objectMapper.treeToValue(
                    envelope.payload(), OrderCreated.class);
            case "ORDER_CANCELLED" -> objectMapper.treeToValue(
                    envelope.payload(), OrderCancelled.class);
            case "PAYMENT_RECEIVED" -> objectMapper.treeToValue(
                    envelope.payload(), PaymentReceived.class);
            default -> throw new IllegalArgumentException(
                    "Unknown payloadType: " + envelope.payloadType());
        };
    }
}
```

After the mapping step, the writer classifier only needs to classify Java subtypes. This separation keeps reading/deserializing data separate from choosing the destination writer.

Do not use arbitrary class names from a payload to call `Class.forName()` or enable broad polymorphic deserialization on untrusted data. Discriminators must be mapped through an allowlist of permitted types.

## 11. When Should You Classify Earlier in the Processor?

If the input payload is an envelope or a common type, `ItemProcessor` can convert it into a concrete subtype before the writer runs. Then the classifier writer routes by runtime type.

```java
@Bean
public ItemProcessor<EventEnvelope, DomainEvent> eventProcessor(
        EventPayloadMapper payloadMapper) {
    return payloadMapper::toDomainEvent;
}
```

Flow:

```text
ItemReader<EventEnvelope>
          |
          v
ItemProcessor<EventEnvelope, DomainEvent>
          |
          v
ClassifierCompositeItemWriter<DomainEvent>
          |
          +--> OrderCreated writer
          +--> OrderCancelled writer
          +--> PaymentReceived writer
```

A processor is well suited for parsing discriminators, normalizing payloads, and validating data. The classifier writer focuses on deciding the write destination. Separating responsibilities makes each part easier to test independently.

If classification does not require transforming the object, you can classify directly based on an existing field or subtype. There is no need to create a processor just to turn an enum into a writer if the classifier can do that simply.

## 12. Fallback for Unsupported Payload Types

Unknown payload types should not be silently ignored. Two common strategies exist:

**Fail fast:** throw an exception when encountering an unsupported subtype. Suitable when a new payload indicates the schema contract has changed and the application needs updating.

**Route to a quarantine/dead-letter writer:** store unsupported payloads in an isolated location for investigation, if business rules allow the Job to continue.

Example classifier with fallback:

```java
return event -> {
    if (event instanceof OrderCreated) {
        return orderCreatedAdapter;
    }
    if (event instanceof OrderCancelled) {
        return orderCancelledAdapter;
    }
    if (event instanceof PaymentReceived) {
        return paymentReceivedAdapter;
    }
    return unsupportedEventWriter;
};
```

A fallback writer should record enough information for investigation, such as event ID, discriminator, source file, batch ID, and the reason it is unsupported. Do not log secrets or full sensitive data.

If using a fallback, decide whether the Step outcome should be considered normally completed or needs a custom `ExitStatus` such as `COMPLETED_WITH_UNSUPPORTED_PAYLOADS`. Track the number of items sent to quarantine and set business thresholds if needed.

## 13. Classifier by Enum or Business Property

Not every payload has its own subtype. All items may share the same Java type while carrying a `category` or `destination` property:

```java
public record TransactionPayload(
        String transactionId,
        TransactionType type,
        BigDecimal amount
) {
}

public enum TransactionType {
    DEPOSIT,
    WITHDRAWAL,
    FEE
}
```

A classifier can be based on the enum:

```java
Classifier<TransactionPayload, ItemWriter<? super TransactionPayload>> classifier = payload ->
        switch (payload.type()) {
            case DEPOSIT -> depositWriter;
            case WITHDRAWAL -> withdrawalWriter;
            case FEE -> feeWriter;
        };
```

This approach fits when payload structures are identical but write rules differ by category. If the type determines different schemas and fields, Java subtypes usually express the contract better.

## 14. ClassifierCompositeItemWriter vs CompositeItemWriter

The two writers have similar names but different behavior:

| Requirement | Appropriate writer |
|---|---|
| Write every item to every destination | `CompositeItemWriter` |
| Select one writer per item by payload type | `ClassifierCompositeItemWriter` |
| Some items must go to multiple destinations, others to only one | Classifier returns an appropriate composite writer for each group, or design custom routing |
| Select a processor by input type | `ClassifierCompositeItemProcessor` |

Do not use `CompositeItemWriter` if the goal is routing by payload type, because it will call every delegate for the same chunk. That could cause a payment to be written to the orders table or vice versa.

## 15. What Role Does ClassifierCompositeItemProcessor Play?

`ClassifierCompositeItemProcessor<I, O>` is the analogous mechanism at the process stage: the classifier selects the appropriate `ItemProcessor` for the item. It does not select a writer.

Example:

```java
ClassifierCompositeItemProcessor<DomainEvent, ProcessedEvent> processor =
        new ClassifierCompositeItemProcessorBuilder<DomainEvent, ProcessedEvent>()
                .classifier(event -> {
                    if (event instanceof OrderCreated) {
                        return orderCreatedProcessor;
                    }
                    if (event instanceof PaymentReceived) {
                        return paymentReceivedProcessor;
                    }
                    return defaultEventProcessor;
                })
                .build();
```

Choose a classifier processor when each payload type has different processing rules. Choose a classifier writer when the goal is routing processed items to the right write destination. Both can be used in the same Step if business requirements call for it.

## 16. Registering the Classifier Writer in a Step

After creating `ClassifierCompositeItemWriter`, pass it to the Step:

```java
@Bean
public Step routeDomainEventsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<DomainEvent> eventReader,
        ItemProcessor<DomainEvent, DomainEvent> eventProcessor,
        ClassifierCompositeItemWriter<DomainEvent> eventWriter) {

    return new StepBuilder("routeDomainEventsStep", jobRepository)
            .<DomainEvent, DomainEvent>chunk(100, transactionManager)
            .reader(eventReader)
            .processor(eventProcessor)
            .writer(eventWriter)
            .build();
}
```

Spring Batch invokes the classifier writer at the write stage of each chunk. The reader and processor still operate under their normal contracts. If the processor returns `null`, the item is filtered and is not passed to the writer.

If delegate writers hold state such as file writers, ensure `ItemStream` lifecycle is managed. `ClassifierCompositeItemWriter` and its builder support streams depending on the Spring Batch version; check the API you are using. If a delegate stream is not automatically managed by the composite, register the delegate with `.stream(...)` on the Step or wrap lifecycle explicitly. Avoid calling `open/update/close` twice for the same delegate.

## 17. Transactions When Routing to Multiple Writers

A single chunk can contain multiple payload types, so during one write call the classifier writer may invoke several different delegates. The transaction boundary is still managed by the Step and `PlatformTransactionManager`.

If delegates write to the same database and share the same transaction, changes can roll back together with the chunk. However, if a delegate writes a file, sends an HTTP request, or publishes a message, the database transaction does not automatically undo those side effects.

For example, a chunk contains:

```text
[OrderCreated, PaymentReceived, OrderCancelled]
```

The classifier may invoke three corresponding writers. If the payment writer succeeds and then the order-cancellation writer throws an exception, the chunk transaction can roll back database operations participating in the same transaction. External side effects require separate mechanisms.

Do not assume every writer will commit atomically just because they are invoked from the same classifier composite. If you need consistency between a database and messages/files, consider an outbox, idempotency keys, or splitting publishing into a separate Step.

## 18. Retry, Skip, and Idempotency

When a delegate fails, the exception is returned to the Step and the fault-tolerance policy can retry or skip depending on the error type. During a retry, the classifier and writer may be invoked again for the same item/chunk.

Guidelines:

- The classifier should be deterministic: the same payload must select the same writer within the same logic version.
- Writers must be idempotent if side effects can be executed multiple times.
- Use business keys or event IDs to prevent duplicate writes.
- Do not skip unexplained routing errors; a payload without a writer is usually a contract error.
- If falling back to quarantine, record counts and reasons for operational monitoring.
- Do not retry configuration errors such as missing writers or unsupported subtypes when retrying cannot change the outcome.

Example configuring retry for transient database errors:

```java
return new StepBuilder("routeDomainEventsStep", jobRepository)
        .<DomainEvent, DomainEvent>chunk(100, transactionManager)
        .reader(eventReader)
        .writer(eventWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
```

Only configure exceptions appropriate for the actual delegates. Do not use broad `retry(Exception.class)` or `skip(Exception.class)` because that can hide mapping and routing bugs.

## 19. Managing Order and Determinism

The classifier writer selects a writer per item. When a chunk has multiple payload types, you should not rely on ordering between delegates to enforce business dependencies.

For example, do not assume `OrderCreated` will always be written before `PaymentReceived` just because it appeared earlier in the chunk or because the order writer was declared first. If a payment requires the order to already exist, you should:

- Sort and process data by explicit rules before writing if possible.
- Split event types into ordered Steps.
- Use appropriate foreign keys/retries/reconciliation.
- Design writers to handle non-guaranteed arrival order.

The classifier should only decide the route. If logic depends on order, that is a separate orchestration requirement that must be expressed explicitly.

## 20. Observing Payload Routing

In operations, you need to know where each payload type is routed and how many items are rejected. Metrics or logs can be recorded in the classifier, but avoid introducing side effects that affect primary processing.

Useful metrics:

- Number of `OrderCreated` items routed to the order writer.
- Number of `PaymentReceived` items routed to the payment writer.
- Number of items sent to fallback/quarantine.
- Number of discriminator mapping errors.
- Number of delegate errors by payload type.
- Write duration per destination.

For logs, record the event ID, payload type, JobExecution ID or batch ID, and target destination. Do not log the full payload if it contains personal information, payment details, or sensitive data.

`StepExecution` counters can be used for overall item counts, but per-payload-type statistics require custom metrics or type-tagged listeners/writer wrappers.

## 21. Testing Classifier and Writer Routing

Test the classifier independently and test the composite writer with a chunk containing multiple payload types.

Example classifier unit test:

```java
@Test
void routesPaymentReceivedToPaymentWriter() {
    ItemWriter<DomainEvent> paymentWriter = chunk -> { };
    ItemWriter<DomainEvent> orderWriter = chunk -> { };

    Classifier<DomainEvent, ItemWriter<? super DomainEvent>> classifier = event ->
            event instanceof PaymentReceived ? paymentWriter : orderWriter;

    assertSame(paymentWriter, classifier.classify(
            new PaymentReceived(9001L, 1001L, new BigDecimal("25.00"))
    ));
}
```

Cases to test:

1. Each subtype is routed to the right delegate.
2. Mixed chunks are split accurately by payload type.
3. Unsupported payload types go to fallback or fail the Step per policy.
4. Invalid discriminators are rejected before writing.
5. Adapters reject wrong subtypes instead of casting unsafely.
6. Delegate writers receive the right items and right data types.
7. Delegate failures cause the Step to handle transactions/retries as configured.
8. Retries do not create duplicates in the database, API, or broker.
9. Delegates implementing `ItemStream` are opened/updated/closed following the proper lifecycle.
10. Job restarts preserve routing logic and required input versions.

Classifier unit tests do not prove transaction behavior. Integration tests with JobRepository, a transaction manager, and real resources are needed to verify rollback, retry, restart, and side effects.

## 22. Common Pitfalls

**Using CompositeItemWriter when routing by type is needed.** Composite writer sends every item to every delegate. Use `ClassifierCompositeItemWriter` when each item selects one writer.

**Comparing classes by string name.** Renaming a class can break routing. Use `instanceof`, an enum, or an allowlist registry.

**Not handling unknown payload types.** The classifier can throw an exception or route to quarantine. Do not let items be dropped without a trace.

**Using unchecked casts inside a writer.** An item of the wrong subtype can cause a `ClassCastException` during writing. Use a type-checking adapter.

**Allowing a discriminator to pick arbitrary classes.** External data must not determine runtime classes via arbitrary `Class.forName()`. Use explicit mappings.

**Assuming writers run in business order.** Routing does not replace orchestration. Split into Steps or design explicit dependencies if ordering matters.

**Assuming a Step transaction rolls back every destination.** Files, HTTP, and brokers may retain side effects. Use idempotency, outbox, or reconciliation.

**Forgetting delegate lifecycle.** Stateful writers need `ItemStream` properly registered. Check composite and Step configuration.

## 23. When Should You Use ClassifierCompositeItemWriter?

Use `ClassifierCompositeItemWriter` when a chunk can contain multiple payload types and each item must be written to a matching writer. Define a common type for payloads, write a deterministic classifier based on subtype or business properties, and configure delegate writers with compatible types.

If payloads arrive as JSON with a discriminator, validate the type against an allowlist and deserialize into a Java subtype before routing. Use an adapter when a specialized writer needs its own generic type. Define a fallback for unknown types, manage the lifecycle of stateful delegates, and ensure writers are idempotent under retry/restart.

If every item must be written to all destinations, use `CompositeItemWriter`. If you need to select a processor by payload type, use `ClassifierCompositeItemProcessor`. Distinguishing these three needs properly makes pipelines easier to read, more type-safe, and prevents writing data to the wrong destination.
