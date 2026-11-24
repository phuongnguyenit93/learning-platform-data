# Routing Items by Type

In Spring Batch, a step can read multiple types of items from the same data stream. For example, an integration file may contain customers, orders, and payments; or an API may return events with different structures. Each item type may require its own processing logic, validation, and write destination.

**Routing** is classifying each item and forwarding it to the right processor or writer. Spring Batch supports this pattern through `ClassifierCompositeItemProcessor` and `ClassifierCompositeItemWriter`. Both use a `Classifier` to pick a delegate based on the current item.

Per-item routing differs from `CompositeItemProcessor`: a composite processor runs multiple processors in a chain for the same item, whereas a classifier composite selects one processing branch based on item type. Picking the right pattern keeps pipelines readable, avoids large `if/else` chains, and keeps logic for each data type independent.

## 1. When Do You Need to Route Items by Type?

Consider a data source with records like these:

```text
CUSTOMER,C001,Nguyen An
ORDER,O100,C001,250.00
PAYMENT,P900,O100,250.00
CUSTOMER,C002,Tran Binh
```

A reader can convert each line into a common input object, while processing depends on record type:

- `CUSTOMER`: validate customer info and update the customer repository.
- `ORDER`: verify the customer exists, normalize the order, and save the order.
- `PAYMENT`: verify payment status and write to the payment ledger.

If all logic lives in a single processor or writer, that class must know every data type and contain many conditional branches. Adding a new record type easily impacts existing code.

Routing splits the flow by type:

```text
                    ItemReader
                        |
                        v
                 Common input item
                        |
                        v
                    Classifier
                  /     |      \
                 /      |       \
                v       v        v
          Customer   Order    Payment
          processor processor processor
                \      |       /
                 \     |      /
                  v    v     v
                Common output item
                        |
                        v
                Writer or continue
```

Each item is classified individually. Items of different types can still sit in the same chunk and be processed through different branches.

## 2. Distinguishing Routing from CompositeItemProcessor

The two components have similar names yet different purposes:

| Component | How It Works | When Appropriate |
|---|---|---|
| `CompositeItemProcessor` | Runs delegate processors sequentially in configured order. Previous processor output is next processor input. | One item must go through multiple shared transformation steps, e.g., validate → normalize → enrich. |
| `ClassifierCompositeItemProcessor` | Picks one processor based on the item and runs the chosen processor. | Each item type needs a different processing branch. |
| `ClassifierCompositeItemWriter` | Picks the right writer for each item. | Different output types must be written to different tables, files, or destinations. |

Example of a shared processing chain:

```text
CustomerInput
     |
     v
ValidateProcessor
     |
     v
NormalizeProcessor
     |
     v
EnrichProcessor
     |
     v
Customer
```

This is `CompositeItemProcessor`, because every item goes through the steps in the same order.

Example of per-type processing:

```text
InboundEvent
     |
     v
  Classifier
    /    \
   v      v
Customer  Order
Processor Processor
```

This is `ClassifierCompositeItemProcessor`, because the classifier picks exactly one branch for the item.

The two patterns can be combined: the classifier selects a processor by type, and the selected processor can itself be a `CompositeItemProcessor` running multiple transformation steps inside that branch.

## 3. Designing a Common Input Data Type

A clean way to keep routing under control is using an interface or sealed interface as the common input type.

Example with modern Java:

```java
public sealed interface InboundEvent
        permits CustomerCreated, OrderPlaced, PaymentReceived {
}

public record CustomerCreated(
        String customerId,
        String name,
        String email) implements InboundEvent {
}

public record OrderPlaced(
        String orderId,
        String customerId,
        BigDecimal amount) implements InboundEvent {
}

public record PaymentReceived(
        String paymentId,
        String orderId,
        BigDecimal amount) implements InboundEvent {
}
```

`InboundEvent` is the common type returned by the reader. Each record has its own structure, yet all can pass through the same step:

```java
ItemReader<InboundEvent> eventReader = ...;
```

If using a Java version without sealed interfaces/records, you can use a regular interface and classes implementing it.

Another option is a common DTO with a `type` field:

```java
public record IncomingRecord(
        String type,
        String recordId,
        Map<String, Object> payload) {
}
```

A common DTO is useful when the source is a JSON envelope or a message with a discriminator. However, `Map<String, Object>` reduces type safety and complicates payload conversion. When each type's structure is clear, dedicated classes are usually easier to validate and maintain.

## 4. Choosing Item Type via Discriminator

The classifier needs a stable rule to determine the branch. You can use:

- Actual Java type (`instanceof`, class metadata).
- A discriminator field such as `type`, `eventType`, or `recordKind`.
- A business code or record ID prefix if that is an explicit data contract.
- A combination of fields when a single field is insufficient.

Example classifying by Java type:

```java
Classifier<InboundEvent, String> eventTypeClassifier = event -> {
    if (event instanceof CustomerCreated) {
        return "CUSTOMER";
    }
    if (event instanceof OrderPlaced) {
        return "ORDER";
    }
    if (event instanceof PaymentReceived) {
        return "PAYMENT";
    }
    throw new IllegalArgumentException(
            "Unsupported event type: " + event.getClass().getName());
};
```

Example classifying by discriminator:

```java
Classifier<IncomingRecord, String> recordTypeClassifier = record -> {
    return switch (record.type()) {
        case "CUSTOMER" -> "CUSTOMER";
        case "ORDER" -> "ORDER";
        case "PAYMENT" -> "PAYMENT";
        default -> throw new IllegalArgumentException(
                "Unsupported record type: " + record.type());
    };
};
```

Do not guess record types from arbitrary strings if the source format does not specify that contract. Validate discriminators right at the read boundary or in the classification step so unknown data is not misrouted.

## 5. What Is Classifier?

`Classifier<C, T>` is an abstraction that takes an input object of type `C` and returns a classification result of type `T`:

```java
public interface Classifier<C, T> {
    T classify(C classifiable);
}
```

A classifier does not have to return a string. It can return a processor, writer, strategy, or any delegate fitting the routing goal.

Example classifier returning a branch name:

```java
Classifier<InboundEvent, String> classifier = event -> {
    if (event instanceof CustomerCreated) return "customer";
    if (event instanceof OrderPlaced) return "order";
    if (event instanceof PaymentReceived) return "payment";
    throw new IllegalArgumentException("Unknown event");
};
```

A classifier returning a branch name is only one classification step. `ClassifierCompositeItemProcessor` and `ClassifierCompositeItemWriter` normally use a classifier that directly returns the corresponding delegate to invoke.

Keep classifiers simple, deterministic, and free of side effects. Do not call APIs, write to databases, or mutate business state inside `classify()`. Classification should be a fast, independently testable decision.

## 6. Routing to a Processor with ClassifierCompositeItemProcessor

`ClassifierCompositeItemProcessor<I, O>` selects one `ItemProcessor` for each input item. Selected processors must produce output compatible with type `O`.

Suppose diverse event types all map to a normalized model:

```java
public record NormalizedEvent(
        String eventId,
        String eventType,
        String aggregateId,
        String description) {
}
```

Dedicated processors:

```java
ItemProcessor<CustomerCreated, NormalizedEvent> customerProcessor = event ->
        new NormalizedEvent(
                event.customerId(),
                "CUSTOMER_CREATED",
                event.customerId(),
                "Customer " + event.name() + " created");

ItemProcessor<OrderPlaced, NormalizedEvent> orderProcessor = event ->
        new NormalizedEvent(
                event.orderId(),
                "ORDER_PLACED",
                event.orderId(),
                "Order amount " + event.amount());

ItemProcessor<PaymentReceived, NormalizedEvent> paymentProcessor = event ->
        new NormalizedEvent(
                event.paymentId(),
                "PAYMENT_RECEIVED",
                event.orderId(),
                "Payment amount " + event.amount());
```

Creating the processor-selecting classifier:

```java
Classifier<InboundEvent, ItemProcessor<?, ? extends NormalizedEvent>> classifier = event -> {
    if (event instanceof CustomerCreated) {
        return customerProcessor;
    }
    if (event instanceof OrderPlaced) {
        return orderProcessor;
    }
    if (event instanceof PaymentReceived) {
        return paymentProcessor;
    }
    throw new IllegalArgumentException(
            "Unsupported event type: " + event.getClass().getName());
};

ClassifierCompositeItemProcessor<InboundEvent, NormalizedEvent> router =
        new ClassifierCompositeItemProcessor<>();
router.setClassifier(classifier);
```

In Spring configuration, you can declare the router as a bean and inject delegate processors via constructor/method parameters. The classifier ensures `CustomerCreated` goes to `customerProcessor`, `OrderPlaced` goes to `orderProcessor`, and `PaymentReceived` goes to `paymentProcessor`.

Because delegates have different input types, the classifier must pick the right processor for the right object type. Choosing the wrong one causes internal generic casts inside the routing component to throw `ClassCastException` when the processor is invoked. Do not rely on generic types to substitute for discriminator checks.

## 7. Processor Routing in Spring Configuration

Each processor can be declared as a separate bean and then combined:

```java
@Bean
ItemProcessor<CustomerCreated, NormalizedEvent> customerCreatedProcessor() {
    return event -> new NormalizedEvent(
            event.customerId(),
            "CUSTOMER_CREATED",
            event.customerId(),
            event.name());
}

@Bean
ItemProcessor<OrderPlaced, NormalizedEvent> orderPlacedProcessor() {
    return event -> new NormalizedEvent(
            event.orderId(),
            "ORDER_PLACED",
            event.orderId(),
            event.amount().toPlainString());
}

@Bean
ClassifierCompositeItemProcessor<InboundEvent, NormalizedEvent> eventRouter(
        ItemProcessor<CustomerCreated, NormalizedEvent> customerCreatedProcessor,
        ItemProcessor<OrderPlaced, NormalizedEvent> orderPlacedProcessor) {

    ClassifierCompositeItemProcessor<InboundEvent, NormalizedEvent> router =
            new ClassifierCompositeItemProcessor<>();

    router.setClassifier(event -> {
        if (event instanceof CustomerCreated) {
            return customerCreatedProcessor;
        }
        if (event instanceof OrderPlaced) {
            return orderPlacedProcessor;
        }
        throw new IllegalArgumentException("Unsupported event: " + event);
    });

    return router;
}
```

The condensed example declares only two event types; if `PaymentReceived` exists, add a corresponding processor and branch. In larger applications, extract classifier construction into a separate factory/configuration class so step configuration does not bloat.

## 8. Combining Routing with CompositeItemProcessor

A branch may need multiple sequential processing steps. In that case, build a `CompositeItemProcessor` for each type and let the classifier select the right composite.

Example:

```java
ItemProcessor<CustomerCreated, NormalizedEvent> customerPipeline =
        new CompositeItemProcessorBuilder<CustomerCreated, NormalizedEvent>()
                .delegates(
                        validateCustomerCreated,
                        normalizeCustomerCreated,
                        mapCustomerCreated)
                .build();

ItemProcessor<OrderPlaced, NormalizedEvent> orderPipeline =
        new CompositeItemProcessorBuilder<OrderPlaced, NormalizedEvent>()
                .delegates(
                        validateOrderPlaced,
                        normalizeOrderPlaced,
                        mapOrderPlaced)
                .build();
```

Then the classifier selects `customerPipeline` or `orderPipeline` by event type. This structure separates two decisions:

1. Which branch should handle the item?
2. Within that branch, which transformations does the item go through?

This is a suitable combination when each data type has its own pipeline while the final output still shares a single type.

## 9. Routing Items to Writers with ClassifierCompositeItemWriter

Sometimes a processor normalizes data, yet outputs still have multiple types that must be written to different destinations. `ClassifierCompositeItemWriter<T>` picks a writer based on each item.

Example shared output:

```java
public sealed interface ExportRecord
        permits CustomerExport, OrderExport {
}

public record CustomerExport(
        String customerId,
        String name) implements ExportRecord {
}

public record OrderExport(
        String orderId,
        BigDecimal amount) implements ExportRecord {
}
```

Suppose there are two specialized writers:

```java
ItemWriter<CustomerExport> customerExportWriter = ...;
ItemWriter<OrderExport> orderExportWriter = ...;
```

`ClassifierCompositeItemWriter<ExportRecord>` needs delegates whose accepted type is compatible with the common item type. You can create adapters to check types and convert chunks for specialized writers:

```java
ItemWriter<ExportRecord> customerWriterAdapter = items -> {
    Chunk<CustomerExport> customerItems = new Chunk<>();
    for (ExportRecord item : items) {
        if (!(item instanceof CustomerExport customer)) {
            throw new IllegalArgumentException("Expected CustomerExport");
        }
        customerItems.add(customer);
    }
    customerExportWriter.write(customerItems);
};

ItemWriter<ExportRecord> orderWriterAdapter = items -> {
    Chunk<OrderExport> orderItems = new Chunk<>();
    for (ExportRecord item : items) {
        if (!(item instanceof OrderExport order)) {
            throw new IllegalArgumentException("Expected OrderExport");
        }
        orderItems.add(order);
    }
    orderExportWriter.write(orderItems);
};
```

Classifier selecting adapters:

```java
Classifier<ExportRecord, ItemWriter<? super ExportRecord>> writerClassifier = record -> {
    if (record instanceof CustomerExport) {
        return customerWriterAdapter;
    }
    if (record instanceof OrderExport) {
        return orderWriterAdapter;
    }
    throw new IllegalArgumentException(
            "Unsupported export record: " + record.getClass().getName());
};

ClassifierCompositeItemWriter<ExportRecord> routingWriter =
        new ClassifierCompositeItemWriter<>();
routingWriter.setClassifier(writerClassifier);
```

Adapters keep type checks in one place and protect specialized writers from receiving the wrong item type. For systems with many record types, you can build a generic adapter taking `Class<T>` to check/cast and convert chunks.

## 10. Generic Type Considerations When Routing Writers

Java generics do not allow treating `ItemWriter<CustomerExport>` as `ItemWriter<ExportRecord>`. This is the invariance of generic types. Even though `CustomerExport` is a subtype of `ExportRecord`, a specialized writer only knows how to write `CustomerExport` and cannot safely accept an `OrderExport`.

Therefore, when using `ClassifierCompositeItemWriter<ExportRecord>`, delegates must accept `ExportRecord` or an appropriate supertype. An adapter checking each element and converting to `Chunk<CustomerExport>` or `Chunk<OrderExport>` is a clear way to preserve type safety at the boundary.

Avoid raw casts such as:

```java
ItemWriter rawWriter = customerExportWriter;
```

Raw types bypass compile-time checks and push errors to runtime. If casting is unavoidable, isolate it inside a small adapter with `instanceof` checks and tests for data types.

## 11. Declaring a Routing Writer in a Step

A step can use a classifier writer as its primary writer:

```java
@Bean
Step exportRecordsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<ExportRecord> exportRecordReader,
        ItemProcessor<ExportRecord, ExportRecord> exportProcessor,
        ClassifierCompositeItemWriter<ExportRecord> routingWriter) {

    return new StepBuilder("exportRecordsStep", jobRepository)
            .<ExportRecord, ExportRecord>chunk(200, transactionManager)
            .reader(exportRecordReader)
            .processor(exportProcessor)
            .writer(routingWriter)
            .build();
}
```

If delegate writers implement `ItemStream` or `StepExecutionListener`, ensure they are registered with the step so lifecycle callbacks fire. A composite/router does not necessarily forward every lifecycle contract of its delegates automatically.

Example with stateful writers:

```java
return new StepBuilder("exportRecordsStep", jobRepository)
        .<ExportRecord, ExportRecord>chunk(200, transactionManager)
        .reader(exportRecordReader)
        .processor(exportProcessor)
        .writer(routingWriter)
        .stream(customerFileWriter)
        .stream(orderFileWriter)
        .build();
```

Explicit stream registration is especially important for file writers needing `open`, `update`, and `close` to save checkpoints. If delegates are not opened/closed under the proper lifecycle, restarts may fail or resources may leak.

## 12. Route by Type or Route by Business Condition?

A classifier does not have to rely on class type. It can be based on an attribute or business status.

Example:

```java
Classifier<Payment, ItemWriter<? super Payment>> paymentWriterClassifier = payment -> {
    return switch (payment.status()) {
        case SETTLED -> settledPaymentWriter;
        case REFUNDED -> refundedPaymentWriter;
        case PENDING -> pendingPaymentWriter;
    };
};
```

Routing by type fits when structure or handlers differ by record type. Routing by status fits when the same object type requires different handling by status.

If classification conditions depend on queries or complex logic, extract them into a pure policy/service for separate testing. Avoid embedding I/O calls inside a classifier because the classifier may be called per item, increasing latency and complicating retry control.

## 13. Handling Unsupported Item Types

A classifier must define explicit behavior when encountering an unknown type. Three common strategies exist:

**Fail fast:** throw an exception and fail the step. Use when an unknown type indicates unsupported data or schema version.

```java
default -> throw new UnsupportedRecordTypeException(record.type());
```

**Route to rejected writer:** send the item to storage for unsupported data so operations can investigate. This must preserve the raw payload, source reference, and rejection reason.

**Controlled ignore:** use only when the source contract permits ignoring specific event types and skips are recorded. Do not use a default no-op if doing so can silently drop data.

Do not route unknown types to a default success writer. A newly appearing type could represent an important schema change; ignoring it could let the batch complete with missing data.

## 14. Distinguishing Routing Errors from Skips

Failing to find a delegate is a routing configuration/logic error, not automatically a skip. If the classifier throws an exception, the step handles it according to the step's fault-tolerance policy.

Example:

```java
.faultTolerant()
.skip(InvalidCustomerRecordException.class)
.skipLimit(100)
```

If the classifier throws `UnsupportedRecordTypeException`, the exception is only skipped if configured accordingly. However, do not put classifier errors into the skip policy just to keep the job running; determine whether it is a per-item error and whether business rules accept dropping it.

For unknown data types, it is usually better to write a rejected item with full payload and reason. For classifier errors caused by missing delegate beans or misconfiguration, fail the step to fix the deployment issue.

## 15. Filtering After Routing to a Processor

The selected processor can still return `null` to filter an item. In that case, the item was classified and handled in its branch, yet no output goes to the writer.

Example:

```java
ItemProcessor<CustomerCreated, NormalizedEvent> customerProcessor = event -> {
    if (event.email() == null || event.email().isBlank()) {
        return null; // Only filter if this is an accepted business rule.
    }
    return normalize(event);
};
```

If email is required and a missing email is a data error, throw `InvalidCustomerException` instead of filtering. That lets the skip policy and `SkipListener` record the faulty item.

The classifier does not alter processor semantics. `null` from a processor remains a filter; exceptions remain governed by the step's retry/skip/fail policies.

## 16. Routing and Transaction Boundaries

Writer branches are usually invoked within the same chunk transaction of the step. If writers write to the same database and join the same transaction manager, the transaction can roll back database changes when one delegate writer fails.

However, if the routing writer sends data across multiple resource types:

- Database A.
- Database B.
- Filesystem.
- HTTP API or message broker.

then a local transaction does not automatically guarantee all resources commit/roll back atomically. For example, writer A wrote a file, writer B wrote to the database and threw an error; the database transaction may roll back while the already-written file is not automatically deleted.

Ways to reduce risk:

- Route to writers sharing a transaction resource when atomicity is needed.
- Use staging files and publish after the database transaction finishes.
- Use an outbox to emit events after commit.
- Use idempotency keys for APIs/brokers.
- Have a reconciliation process for branches that cannot roll back together.

Routing separates target write logic, yet does not create a distributed transaction.

## 17. Write Order and Consistency

A chunk can contain multiple item types. The classifier writer dispatches each item to its corresponding delegate. Do not rely on delegate writer invocation order unless that order is guaranteed by the contract of the component/version in use.

Chunk example:

```text
Customer C1
Order O1
Customer C2
Payment P1
Order O2
```

If data is grouped by writer, write order across types may differ from input order. This can matter when:

- One writer depends on data produced by another writer.
- Output files must preserve source order.
- Events must be emitted in aggregate order.
- Consumers rely on record order for processing.

If global ordering is a requirement, use a single writer with sequential dispatch logic, or split the flow into explicitly ordered steps. When items are independent, delegate routing is usually preferable.

## 18. When to Split into Multiple Steps Instead of Routing in One Step?

Per-item routing fits when record types come from one source and must be processed within the same chunk lifecycle. However, if types require different transaction, checkpoint, retry, skip, or scheduling configurations, multiple steps can be easier to operate.

| Need | Suitable Choice |
|---|---|
| Each item picks one processor in the same chunk | `ClassifierCompositeItemProcessor`. |
| Each output item picks its own writer in the same step | `ClassifierCompositeItemWriter`. |
| Each type needs its own chunk size or retry/skip policy | Split into separate steps or partition input beforehand. |
| Each type needs its own job flow | Conditional flows or multiple jobs/steps. |
| Need concurrent processing of independent streams | Partitioning or split flows after splitting data. |
| Need to preserve global order across types | Single writer with sequential dispatch or explicitly ordered pipeline. |

Do not use a classifier to cram completely divergent logic into one step when branches have fundamentally different operational requirements. Splitting steps provides independent status, metrics, restart boundaries, and fault-tolerance settings.

## 19. Routing via a Map Classifier

When the number of types is large, a map from type to delegate can be cleaner than many `if/else` branches. You can use `SubclassClassifier` or a custom `Classifier` backed by a map lookup.

Example custom class-based classifier:

```java
Map<Class<?>, ItemProcessor<?, ? extends NormalizedEvent>> processors =
        new HashMap<>();
processors.put(CustomerCreated.class, customerProcessor);
processors.put(OrderPlaced.class, orderProcessor);
processors.put(PaymentReceived.class, paymentProcessor);

Classifier<InboundEvent, ItemProcessor<?, ? extends NormalizedEvent>> classifier = event -> {
    ItemProcessor<?, ? extends NormalizedEvent> processor =
            processors.get(event.getClass());

    if (processor == null) {
        throw new UnsupportedRecordTypeException(
                event.getClass().getName());
    }
    return processor;
};
```

Looking up `event.getClass()` only matches the exact class. If subclasses or proxies exist, decide whether to search by superclass/interface. `SubclassClassifier` can help when classifying along an inheritance hierarchy; configure a default value or explicit missing-type behavior.

The map classifier should be made immutable after configuration so no thread modifies the delegate map while the step is running.

## 20. Routing by Enum or Normalized Discriminator

If items are a common DTO, parse the type string into an enum early:

```java
public enum RecordType {
    CUSTOMER,
    ORDER,
    PAYMENT
}

public record IncomingRecord(
        RecordType type,
        String id,
        String payload) {
}
```

The classifier can use a switch expression:

```java
Classifier<IncomingRecord, RecordHandler> handlerClassifier = record ->
        switch (record.type()) {
            case CUSTOMER -> customerHandler;
            case ORDER -> orderHandler;
            case PAYMENT -> paymentHandler;
        };
```

When parsing `type` from a String, handle null/unrecognized values before creating the enum. If enum parsing fails, reject the record or fail the job per contract. Do not assign an arbitrary default type just to avoid an exception.

## 21. Classifiers and Delegate Idempotency

Routing sends an item to a specific delegate, yet retries/restarts can still invoke that delegate multiple times if a transaction rolls back or a step reruns.

For example, a payment event routes to `paymentWriter`. If the writer calls a partner API and times out, a retry may resend the payment. The classifier does not know whether the API already processed the request.

Delegates must be designed for source/target semantics:

- Database: unique keys, upserts, or processed-state checks.
- HTTP API: stable idempotency keys per event ID.
- Message broker: transactional outbox or deduplication keys.
- File: separate output per batch/partition and writer checkpoints.
- External side effects: persist status/reconciliation when request outcomes are unknown.

Idempotency keys should derive from stable business identity, never generating a new UUID on each retry. For instance, `paymentId` or `eventId` can be used to detect repeated processing.

## 22. Registering Delegate Streams and Listeners

Composite/routing components typically only expose their primary contract, such as `ItemProcessor` or `ItemWriter`. Internal delegates may additionally implement `ItemStream` or listener interfaces.

If a delegate writer is `FlatFileItemWriter`, it must be opened, state-updated, and closed per step lifecycle. If the composite does not forward `ItemStream`, register the delegate via `.stream(...)` in step configuration.

Similarly, if a delegate needs `StepExecutionListener`, `ChunkListener`, or other listeners, verify lifecycle callbacks are registered. Do not assume Spring Batch automatically discovers objects nested inside a classifier.

Example:

```java
return new StepBuilder("routeAndWriteStep", jobRepository)
        .<InboundEvent, ExportRecord>chunk(100, transactionManager)
        .reader(eventReader)
        .processor(eventRouter)
        .writer(routingWriter)
        .stream(customerFileWriter)
        .stream(orderFileWriter)
        .listener(stepSummaryListener)
        .build();
```

Delegates must be injected and registered as the exact instances used by the classifier. If a classifier constructs a new writer on each `classify` call, the step cannot manage lifecycles or checkpoints consistently for those instances.

## 23. Tracking Item Counts per Branch

Standard `StepExecution` counters provide total read, filtered, written, and skipped counts. They do not automatically break down how many items went through each branch.

You can add metrics by type:

- `routed.customer.count`
- `routed.order.count`
- `routed.payment.count`
- `routed.unknown.count`
- Processing duration per processor.
- Error counts per delegate/exception type.

Do not create high-cardinality metric tags such as customer ID, order ID, or payment ID. Use record type and outcome as tags; keep business keys in logs with correlation IDs or audit tables.

You could increment counters directly inside the classifier, though classifiers should stay pure and fast. Another approach is wrapping delegates with a processor/decorator that records metrics when invoked, or placing listeners/observers at appropriate boundaries. Ensure metrics do not alter business outcomes if the metrics backend is temporarily down.

## 24. Testing the Classifier Independently

Because a classifier is pure logic, it is easy to test on its own. Tests should cover every supported type and unsupported types.

```java
@Test
void classifiesEachSupportedEventType() {
    assertThat(classifier.classify(
            new CustomerCreated("C001", "An", "an@example.com")))
            .isSameAs(customerProcessor);

    assertThat(classifier.classify(
            new OrderPlaced("O001", "C001", new BigDecimal("20.00"))))
            .isSameAs(orderProcessor);
}

@Test
void rejectsUnsupportedEventType() {
    InboundEvent unsupported = createUnsupportedEventForTest();

    assertThatThrownBy(() -> classifier.classify(unsupported))
            .isInstanceOf(UnsupportedRecordTypeException.class);
}
```

With sealed interfaces, the compiler can help catch missing cases when adding a new subtype to an exhaustive switch expression. When using open interfaces or String discriminators, tests must verify the default branch works.

## 25. Testing ClassifierCompositeItemProcessor

Tests for a processor router must verify items reach the right delegate and produce expected output types/transformations.

```java
@Test
void routesCustomerAndOrderToDifferentProcessors() throws Exception {
    NormalizedEvent customerOutput = router.process(
            new CustomerCreated("C001", "Nguyen An", "an@example.com"));

    NormalizedEvent orderOutput = router.process(
            new OrderPlaced("O001", "C001", new BigDecimal("20.00")));

    assertThat(customerOutput.eventType()).isEqualTo("CUSTOMER_CREATED");
    assertThat(orderOutput.eventType()).isEqualTo("ORDER_PLACED");
}
```

Beyond outputs, use mocks/spies to verify the right processor ran once and other branch processors were not called. Tests for unsupported types must assert the appropriate exception.

If delegate processors have side effects, verify routing does not invoke the wrong delegate and retries do not duplicate side effects. Ideally, processors focus on data transformation while I/O lives in writers or idempotent services.

## 26. Testing ClassifierCompositeItemWriter

Writer router tests must confirm each item goes to the right writer. Example mixed-type chunk:

```text
CustomerExport C001
OrderExport O100
CustomerExport C002
OrderExport O101
```

Tests should verify:

- Customer writer receives only `CustomerExport`.
- Order writer receives only `OrderExport`.
- No items are lost or written twice.
- Whether writers receive empty chunks is handled per component/version semantics.
- Unsupported types fail or route to a rejected writer per design.
- Exceptions from a delegate propagate so the step applies transaction/fault-tolerance policies.

Mock `ItemWriter`s can capture chunks forwarded to each delegate. For casting writer adapters, also test receiving an unexpected item type to verify errors are surfaced clearly.

## 27. Integration Testing Routing in a Chunk Step

Unit testing a classifier does not prove the entire step works properly. Integration tests should run the job/step with a source containing multiple record types and inspect the corresponding outputs.

An integration test should verify:

1. Reader produces the expected subtype or discriminator for each record.
2. Classifier picks the right processor.
3. Processor outputs have expected types/metadata.
4. Writer router dispatches items to the right delegates.
5. All writers/streams are opened and closed per lifecycle.
6. Transactions roll back on delegate writer failures per resource transaction rules.
7. Skip/retry policies apply properly to configured exception types.
8. Counters/metrics accurately reflect per-type item counts.
9. Restarts neither duplicate nor lose items.

If delegates write to multiple different resources, tests must verify behavior when one resource succeeds and another fails. Do not assume a database transaction automatically undoes files or HTTP calls.

## 28. Common Mistakes When Routing Items

| Symptom | Common Cause | Resolution |
|---|---|---|
| `ClassCastException` in processor | Classifier chose a delegate whose input type differs from the actual item. | Check subtypes/discriminators and keep adapters type-safe. |
| Item goes to wrong writer | Incorrect discriminator mapping or overly broad default route. | Normalize types before routing and test all branches. |
| New type silently dropped | Default delegate is a no-op or unrecorded filter. | Fail fast or route to rejected with auditing. |
| One item handled by multiple branches | Using multiple independent `if` blocks instead of picking one delegate. | Use switch/else-if or a classifier returning a single delegate. |
| Later processor does not run | A processor in a chain returned `null` and filtered the item. | Distinguish composite chains from classifier routing and inspect filters. |
| Writer fails to restart | `ItemStream` delegate was not registered on the step. | Register `.stream(delegate)` and keep names/resources stable. |
| Delegate listener not invoked | Listener sits inside composite without registration. | Register listener explicitly on step or use a forwarding wrapper. |
| Partial writes across systems | Delegates use different resources/transaction managers. | Use outbox, staging, idempotency, and reconciliation. |
| Output order shifts | Writer router groups/calls delegates without preserving global order. | Do not rely on implicit order; use a single sequential writer if order is required. |
| Metric counts inflated | Counting inside classifier multiple times or during retries. | Define metrics as attempts vs final items and place at proper boundaries. |
| Overly complex step configuration | Each type has separate retry/skip/chunk policies forced together. | Split into separate steps or job flows. |

## 29. Workflow for Designing Type-Based Routing

When implementing routing, settle these decisions in order:

1. **Define item types:** subtypes, enum discriminator, or payload field?
2. **Define output contract:** do branches share an output type or have distinct outputs?
3. **Choose routing point:** before processor, after processor, or at writer?
4. **Pick component:** `ClassifierCompositeItemProcessor`, `ClassifierCompositeItemWriter`, or custom router.
5. **Create delegates:** each branch gets a processor/writer with clear responsibility and matching types.
6. **Handle unknown types:** fail, reject, or audited ignore per business contract.
7. **Protect generic types:** use common interfaces or type-checked adapters; avoid raw casts.
8. **Register lifecycles:** ensure `ItemStream` delegates and listeners are managed by the step.
9. **Define transactions:** verify whether delegates share a transaction resource or need outbox/staging.
10. **Clarify ordering:** if outputs must preserve source order, do not rely on implicit delegate call order.
11. **Ensure idempotency:** retries/restarts must not create duplicate side effects.
12. **Measure:** track item counts and errors per branch without high-cardinality metrics.
13. **Test:** test classifier, each delegate, router writer, and the entire chunk step.

## 30. Key Takeaways

- Routing picks a processor or writer per item; it is not a sequential transformation chain.
- `CompositeItemProcessor` runs all delegates in order; `ClassifierCompositeItemProcessor` picks one delegate via classifier.
- `ClassifierCompositeItemWriter` picks the appropriate writer for each output item.
- `Classifier` is pure classification logic, should rely on explicit subtypes or discriminators, and should avoid I/O/side effects.
- Processor branches can take different subtypes while producing a shared output contract if the pipeline needs a single output type.
- Java generics are invariant; `ItemWriter<Subtype>` cannot substitute directly for `ItemWriter<Supertype>`. Use type-checked adapters when needed.
- Unsupported types should fail, reject, or be ignored with auditing; do not use a silent default no-op that drops data.
- A classifier can be combined with `CompositeItemProcessor` so each branch has its own sequential pipeline.
- `ItemStream`/listener delegates must be registered with the step if the composite does not forward lifecycle callbacks.
- Routing within a chunk does not create a distributed transaction; multiple resources need outbox, staging, idempotency, or reconciliation.
- Do not assume delegate writer call order preserves global input order.
- If types need different chunk sizes, retry/skip, or restart policies, consider splitting into separate steps.
- Test all branches, unknown types, filters, writer failures, transactions, lifecycles, and restarts.

Routing items by type lets one step handle diverse data formats while keeping per-type logic independent. Define stable discriminators, select exactly one delegate per item, use common types or type-checked adapters, and make unsupported-type handling explicit. When delegates have properly managed lifecycles, transactions, and idempotency, classifier routing becomes an extensible and operable way to organize Spring Batch pipelines.
