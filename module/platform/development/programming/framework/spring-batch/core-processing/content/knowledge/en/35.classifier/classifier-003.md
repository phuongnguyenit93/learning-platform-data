# Classifying by Field or Business State in Spring Batch

In a chunk-oriented Step, each item sometimes needs to follow a different processing branch. For example, paid orders are written to the paid file, cancelled orders are written to the cancelled file, and orders requiring inspection are sent to a review queue. Another case is having the same input type where each business state requires a separate processor.

Spring Batch supports this routing style with **Classifier** and classifier-based composite components. **ClassifierCompositeItemWriter** selects a writer for each item; **ClassifierCompositeItemProcessor** selects the corresponding processor. A classifier can be based on a direct field such as type, status, or category, or on a business state derived from multiple properties.

The key point is that a classifier only decides which branch an item follows. It does not create additional Steps, does not alter transaction boundaries, and does not guarantee that side effects across all delegates roll back together. When routing to multiple files, databases, or external systems, you must design resource lifecycle, idempotency, and output publishing appropriately.

This lesson explains Classifier, classifying by field and business state, configuring writer/processor routing, handling invalid values, the role of ItemStream delegates, effects on chunks and transactions, and testing strategies.

Configuration examples use Spring Batch 5 chunk-based APIs. For Spring Batch 4, some writer APIs use `List` instead of `Chunk`; adjust for your project's version.

## 1. The Item Routing Problem

Suppose a Job imports orders from a common source. Each Order has a status:

~~~text
orderId,status,total
O-1001,PAID,120.00
O-1002,CANCELLED,75.00
O-1003,REVIEW,980.00
O-1004,PAID,45.00
~~~

Output requirements:

- PAID is written to paid-orders.csv.
- CANCELLED is written to cancelled-orders.csv.
- REVIEW is written to review-orders.csv.

If using an ordinary writer, the writer must inspect status itself and write to the right resource. That can be done with a custom ItemWriter, but as the number of branches grows or routing logic changes, the code quickly becomes hard to maintain.

Classifier separates the classification decision from the writer. Each item is passed to the classifier; the classifier returns the matching delegate; the composite writer forwards the item to that delegate.

~~~mermaid
flowchart TD
    A["ItemReader"] --> B["ItemProcessor (optional)"]
    B --> C["ClassifierCompositeItemWriter"]
    C --> D{"Classifier"}
    D -->|PAID| E["Paid writer"]
    D -->|CANCELLED| F["Cancelled writer"]
    D -->|REVIEW| G["Review writer"]
~~~

Every item still belongs to the same Step and the same chunk flow. Routing does not create a new JobExecution or StepExecution.

## 2. What Is a Classifier?

Spring Framework provides the Classifier interface to map an input object to a result:

~~~java
public interface Classifier<C, T> extends Serializable {
    T classify(C classifiable);
}
~~~

Where:

- C is the type of object to classify.
- T is the classification result, typically a delegate such as ItemWriter or ItemProcessor.
- classify() takes an object and returns the selected branch.

A Classifier can be written as a lambda:

~~~java
Classifier<Order, String> classifier =
    order -> order.status().name();
~~~

Or implemented as a dedicated class:

~~~java
public class OrderStatusClassifier
        implements Classifier<Order, String> {

    @Override
    public String classify(Order order) {
        return order.status().name();
    }
}
~~~

A Classifier is not required to return a String or an enum. It can return any type appropriate for its purpose. With a composite writer, the result is usually an ItemWriter; with a composite processor, the result is an ItemProcessor.

### A Classifier Should Be Pure Decision Logic

A good classifier typically:

- Reads fields or state already present on the item.
- Returns the same result for the same input.
- Does not mutate the item.
- Does not write to a database or call APIs.
- Does not hold state that depends on item order.
- Handles null and unrecognized values explicitly.

If you need to call a service to determine risk level, perform that enrichment in a processor first, then have the classifier read the risk level attached to the item. Calling an API inside a classifier introduces side effects into routing and makes behavior unpredictable on retry.

## 3. Classifying by a Direct Field

The simplest approach is routing by an existing field.

Example model:

~~~java
public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED,
    REVIEW
}

public record Order(
    String orderId,
    OrderStatus status,
    BigDecimal total
) {
}
~~~

Classifier by status:

~~~java
Classifier<Order, OrderStatus> statusClassifier =
    Order::status;
~~~

The enum result can be used to choose a writer:

~~~java
ItemWriter<Order> selectWriter(Order order) {
    return switch (order.status()) {
        case PAID -> paidWriter;
        case CANCELLED -> cancelledWriter;
        case REVIEW -> reviewWriter;
        case NEW -> newOrderWriter;
    };
}
~~~

An enum constrains the valid value set and makes the branches to handle explicit. If input data comes from strings like "paid", "Paid", or "PAID", normalize and parse it into an enum before routing.

### Classifying by Type or Category

The same pattern applies to customer type (INDIVIDUAL, BUSINESS), payment method (CARD, BANK_TRANSFER, CASH), record category (HEADER, DETAIL, TRAILER), source system (CRM, ERP, PARTNER), or priority (HIGH, NORMAL, LOW).

Avoid passing arbitrary strings throughout the pipeline if the value set can be represented by an enum or an explicit domain type. Strong types help the compiler and tests catch missing branches.

## 4. Classifying by Multiple Fields

A routing decision can depend on multiple fields. For example, an order only enters the HIGH_VALUE branch when status is PAID and total reaches the threshold.

~~~java
Classifier<Order, String> routeClassifier = order -> {
    if (order.status() == OrderStatus.CANCELLED) {
        return "CANCELLED";
    }

    if (order.status() == OrderStatus.PAID
            && order.total().compareTo(
                new BigDecimal("1000.00")
            ) >= 0) {
        return "HIGH_VALUE";
    }

    if (order.status() == OrderStatus.PAID) {
        return "PAID";
    }

    return "PENDING";
};
~~~

Condition ordering matters. If PAID is checked before the HIGH_VALUE condition, every paid order is routed to PAID and the HIGH_VALUE branch is never selected.

When there are multiple conditions, express priority order clearly and test boundary values.

### Using a Dedicated Method for Business Rules

Avoid long lambdas containing many business rules. Extract a method:

~~~java
public OrderRoute classifyOrder(Order order) {
    if (order.status() == OrderStatus.CANCELLED) {
        return OrderRoute.CANCELLED;
    }

    if (order.status() == OrderStatus.PAID
            && order.total().compareTo(highValueLimit) >= 0) {
        return OrderRoute.HIGH_VALUE;
    }

    if (order.status() == OrderStatus.PAID) {
        return OrderRoute.PAID;
    }

    return OrderRoute.PENDING;
}
~~~

Then the classifier simply invokes this method. Business rules can be unit tested independently of Spring Batch.

## 5. How Do Field and Business State Differ?

A field is direct data on the object, such as status, type, region, or total. Business state can be derived from multiple fields and context.

For example:

- An order has status PAID, yet is flagged fraudHold.
- A customer has status ACTIVE, yet has exceeded their credit limit.
- A payment has status RECEIVED, yet has not been reconciled.
- A record has type STANDARD, yet belongs to a batch running in correction mode.

Business state can be modeled with its own enum:

~~~java
public enum OrderRoute {
    NORMAL,
    HIGH_VALUE,
    MANUAL_REVIEW,
    CANCELLED
}
~~~

A processor or domain service determines the route:

~~~java
public OrderRoute determineRoute(Order order) {
    if (order.isFraudHold()) {
        return OrderRoute.MANUAL_REVIEW;
    }

    if (order.status() == OrderStatus.CANCELLED) {
        return OrderRoute.CANCELLED;
    }

    if (order.status() == OrderStatus.PAID
            && order.total().compareTo(highValueLimit) >= 0) {
        return OrderRoute.HIGH_VALUE;
    }

    return OrderRoute.NORMAL;
}
~~~

The classifier then relies solely on the computed route:

~~~java
Classifier<Order, OrderRoute> classifier =
    Order::route;
~~~

This separation makes business decisions easy to test while keeping the classifier simple and free of enrichment.

## 6. Using ClassifierCompositeItemWriter

ClassifierCompositeItemWriter routes each item to the ItemWriter chosen by the classifier.

Configuration example:

~~~java
@Bean
ClassifierCompositeItemWriter<Order> orderRouterWriter(
        @Qualifier("paidOrdersWriter")
        ItemWriter<Order> paidOrdersWriter,
        @Qualifier("cancelledOrdersWriter")
        ItemWriter<Order> cancelledOrdersWriter,
        @Qualifier("reviewOrdersWriter")
        ItemWriter<Order> reviewOrdersWriter,
        @Qualifier("pendingOrdersWriter")
        ItemWriter<Order> pendingOrdersWriter) {

    return new ClassifierCompositeItemWriterBuilder<Order>()
        .classifier(order -> switch (order.status()) {
            case PAID -> paidOrdersWriter;
            case CANCELLED -> cancelledOrdersWriter;
            case REVIEW -> reviewOrdersWriter;
            case NEW -> pendingOrdersWriter;
        })
        .build();
}
~~~

The builder takes a classifier that returns the matching writer. Each item is sent to the writer corresponding to that item's own state.

If the classifier cannot find a delegate, do not return null. Define a fallback branch or throw a clear exception for the Step to handle per policy.

### Writers Selected per Item

For example, a chunk has four orders:

~~~text
[O-1001 PAID, O-1002 CANCELLED, O-1003 REVIEW, O-1004 PAID]
~~~

Routing result:

~~~text
paidOrdersWriter:
  O-1001
  O-1004

cancelledOrdersWriter:
  O-1002

reviewOrdersWriter:
  O-1003
~~~

Each item is forwarded only to the writer returned by the classifier. If the same item must be written to multiple destinations, ClassifierCompositeItemWriter is not a fan-out tool; use CompositeItemWriter or a custom writer that performs multiple writes.

## 7. Configuring Delegate Writers

Delegates can be FlatFileItemWriter, JdbcBatchItemWriter, or custom ItemWriters.

Example file writers:

~~~java
@Bean
@StepScope
FlatFileItemWriter<Order> paidOrdersWriter(
        @Value("#{jobParameters['paid.output']}") String output) {

    return new FlatFileItemWriterBuilder<Order>()
        .name("paidOrdersWriter")
        .resource(new FileSystemResource(output))
        .lineAggregator(orderLineAggregator())
        .encoding(StandardCharsets.UTF_8.name())
        .saveState(true)
        .build();
}

@Bean
@StepScope
FlatFileItemWriter<Order> cancelledOrdersWriter(
        @Value("#{jobParameters['cancelled.output']}") String output) {

    return new FlatFileItemWriterBuilder<Order>()
        .name("cancelledOrdersWriter")
        .resource(new FileSystemResource(output))
        .lineAggregator(orderLineAggregator())
        .encoding(StandardCharsets.UTF_8.name())
        .saveState(true)
        .build();
}
~~~

Each writer has a distinct and stable name, its own output resource, its own state for restarts, the same item type Order, and appropriate encoding/line aggregator settings.

Output paths must be distinct and deterministically resolved for the same JobInstance. Do not let two delegates accidentally write to the same file.

## 8. Registering Delegate ItemStreams with the Step

This is an important detail when using a composite writer.

ClassifierCompositeItemWriter is responsible for routing, but it does not itself manage the ItemStream lifecycle of every delegate. If delegates such as FlatFileItemWriter need open(), update(), and close(), register them with the Step.

Example:

~~~java
@Bean
Step routeOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ClassifierCompositeItemWriter<Order> orderRouterWriter,
        FlatFileItemWriter<Order> paidOrdersWriter,
        FlatFileItemWriter<Order> cancelledOrdersWriter,
        FlatFileItemWriter<Order> reviewOrdersWriter,
        FlatFileItemWriter<Order> pendingOrdersWriter) {

    return new StepBuilder("routeOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .writer(orderRouterWriter)
        .stream(paidOrdersWriter)
        .stream(cancelledOrdersWriter)
        .stream(reviewOrdersWriter)
        .stream(pendingOrdersWriter)
        .build();
}
~~~

Stream registration lets Spring Batch invoke the delegates' lifecycles and persist required state. If you omit a delegate, that writer might still receive write() calls without being opened, checkpointed, or closed properly.

### Why Not Just Register the Composite?

The composite writer routes to a delegate at runtime. The Step does not necessarily discover every ItemStream held inside the classifier. Therefore, register delegate streams explicitly or use a composite that implements ItemStream and forwards lifecycle properly.

If a delegate does not implement ItemStream and holds no resources, you do not need to register a stream for it.

## 9. Classifying by Normalized Business State

In real systems, input fields may not be enough to determine the branch. For example, source status might be an unnormalized string or must be combined with information from a service.

You can create an enrichment processor:

~~~java
@Bean
ItemProcessor<RawOrder, Order> orderEnrichmentProcessor(
        OrderPolicyService policyService) {

    return raw -> {
        Order order = map(raw);
        OrderRoute route = policyService.determineRoute(order);

        return order.withRoute(route);
    };
}
~~~

Then the classifier just reads the route:

~~~java
.classifier(order -> switch (order.route()) {
    case NORMAL -> normalWriter;
    case HIGH_VALUE -> highValueWriter;
    case MANUAL_REVIEW -> reviewWriter;
    case CANCELLED -> cancelledWriter;
})
~~~

Benefits:

- Business rules live in a service or processor that can be tested independently.
- The classifier makes no API or database calls.
- A classification call produces a consistent result.
- The determined route can be logged on the item.
- Writers are only responsible for writing data.

If business state changes over time, decide when to snapshot the state. Do not let the same item be classified differently across retries just because the classifier reads a mutable data source.

## 10. Using ClassifierCompositeItemProcessor

Not every routing branch needs a different writer. Sometimes the same input type needs different processors based on field or state.

ClassifierCompositeItemProcessor selects one ItemProcessor for each input:

~~~java
@Bean
ClassifierCompositeItemProcessor<RawOrder, Order> routedOrderProcessor(
        ItemProcessor<RawOrder, Order> retailProcessor,
        ItemProcessor<RawOrder, Order> wholesaleProcessor,
        ItemProcessor<RawOrder, Order> correctionProcessor) {

    return new ClassifierCompositeItemProcessorBuilder<RawOrder, Order>()
        .classifier(raw -> switch (raw.type()) {
            case "RETAIL" -> retailProcessor;
            case "WHOLESALE" -> wholesaleProcessor;
            case "CORRECTION" -> correctionProcessor;
            default -> throw new IllegalArgumentException(
                "Unsupported order type: " + raw.type()
            );
        })
        .build();
}
~~~

Step configuration:

~~~java
return new StepBuilder("processOrdersStep", jobRepository)
    .<RawOrder, Order>chunk(100, transactionManager)
    .reader(rawOrderReader)
    .processor(routedOrderProcessor)
    .writer(orderWriter)
    .build();
~~~

Each delegate processor receives an input item and returns an output of the same type Order. If a processor returns null, that is standard ItemProcessor filtering behavior: the item is not passed to the writer.

### When to Classify in the Processor vs the Writer?

| Requirement | Appropriate location |
|---|---|
| Same input but requires different transformation rules | ClassifierCompositeItemProcessor |
| Item is already complete, only need to choose write destination | ClassifierCompositeItemWriter |
| Need both different transformations and different write targets | Both can be used |
| Same item must be written to all destinations | CompositeItemWriter |
| Branches have different multi-Step workflows | Flow/Job or separate Steps |

Do not move business logic into the writer just because a classifier writer is convenient. Place transformations in processors and output routing in writers.

## 11. Classifying by Parsed Fields

If the source has status as a String, normalize it first:

~~~java
public OrderStatus parseStatus(String rawStatus) {
    if (rawStatus == null || rawStatus.isBlank()) {
        throw new InvalidOrderStatusException(
            "Missing order status"
        );
    }

    try {
        return OrderStatus.valueOf(
            rawStatus.trim().toUpperCase(Locale.ROOT)
        );
    } catch (IllegalArgumentException ex) {
        throw new InvalidOrderStatusException(
            "Invalid order status: " + rawStatus,
            ex
        );
    }
}
~~~

Avoid making the classifier handle multiple string variants on every call. Parsing and validation belong at the input or processor boundary.

For invalid data, you can skip the item per policy and write a reject record, route to a quarantine writer if you want to preserve raw input, or fail the Step if the value indicates the entire file/batch violates the contract.

The policy must be explicit. Do not silently convert an unrecognized status into PAID or a default branch that could cause business side effects.

## 12. Fallback Branches and Unclassifiable Data

A classifier must define how to handle every possible state.

One approach is using a fallback writer:

~~~java
.classifier(order -> {
    if (order.status() == null) {
        return rejectedOrdersWriter;
    }

    return switch (order.status()) {
        case PAID -> paidOrdersWriter;
        case CANCELLED -> cancelledOrdersWriter;
        case REVIEW -> reviewOrdersWriter;
        case NEW -> pendingOrdersWriter;
    };
})
~~~

If a null status cannot occur after validation, you can fail explicitly:

~~~java
.classifier(order -> {
    if (order.status() == null) {
        throw new InvalidOrderStatusException(
            "Cannot route order with missing status"
        );
    }

    return writerFor(order.status());
})
~~~

The choice depends on business requirements:

- **Reject/quarantine:** need to store invalid data for investigation.
- **Fail:** invalid data prevents the entire batch from continuing.
- **Fallback:** an unsupported state can still be safely handled on a dedicated branch.

Never return null as a fallback. The composite writer has no valid delegate to write the item and can cause a confusing NullPointerException.

## 13. Classifying by Thresholds and Boundaries

A classifier can use amount, quantity, or risk score:

~~~java
private OrderRoute classifyByAmount(Order order) {
    BigDecimal amount = order.total();

    if (amount == null || amount.signum() < 0) {
        return OrderRoute.MANUAL_REVIEW;
    }

    if (amount.compareTo(new BigDecimal("10000.00")) >= 0) {
        return OrderRoute.HIGH_VALUE;
    }

    return OrderRoute.NORMAL;
}
~~~

When using thresholds, determine:

- Is the threshold inclusive or exclusive?
- How are null values handled?
- Scale and rounding of BigDecimal.
- Are currencies uniform?
- Is currency conversion needed before classification?
- Is the threshold taken from JobParameters or configuration snapshotted per JobInstance?

Use BigDecimal.compareTo() for amount comparisons rather than equals(), because equals() also considers scale. For example, 10.0 and 10.00 have the same numeric value but are not equal according to equals().

### Testing Right at the Boundary

If the threshold is 10,000:

| Value | Expected branch |
|---:|---|
| 9,999.99 | NORMAL |
| 10,000.00 | HIGH_VALUE |
| 10,000.01 | HIGH_VALUE |
| null | MANUAL_REVIEW or exception |
| -1.00 | MANUAL_REVIEW or exception |

Boundary tests prevent bugs from mistakenly using > instead of >=.

## 14. Classifying by Multi-Step Business State

A business state can be derived from payment status, fraud checks, and due dates:

~~~java
public OrderRoute determineRoute(Order order) {
    if (order.isCancelled()) {
        return OrderRoute.CANCELLED;
    }

    if (order.isFraudHold()) {
        return OrderRoute.MANUAL_REVIEW;
    }

    if (!order.isPaid()) {
        return OrderRoute.PENDING_PAYMENT;
    }

    if (order.isPastDue()) {
        return OrderRoute.OVERDUE;
    }

    return OrderRoute.NORMAL;
}
~~~

Priority order is part of the business rule. Which branch does an order that is both cancelled and fraudHold take? The code above gives CANCELLED higher priority. If business rules differ, change the rule and tests accordingly.

Model the rule in a clearly named class such as OrderRoutingPolicy rather than scattering conditions throughout Spring configuration.

## 15. Classifying by Raw Fields vs Persisted State

Some applications store both original fields and processing state:

~~~java
public record Payment(
    String paymentType,
    PaymentStatus status,
    ReconciliationState reconciliationState
) {
}
~~~

Example routes:

- BANK_TRANSFER and PENDING_RECONCILIATION -> reconciliation writer.
- CARD and SETTLED -> settled card writer.
- FAILED -> failed payment writer.
- REFUNDED -> refund writer.

Do not infer state solely from paymentType if reconciliation state actually determines the action. Use the field representing authoritative state or a policy combining multiple fields.

If state is computed across multiple tables, snapshot it onto the item before routing. This keeps the classifier pure and makes results stable throughout the chunk.

## 16. ClassifierCompositeItemWriter vs CompositeItemWriter

The two components serve different goals.

| Component | Behavior |
|---|---|
| ClassifierCompositeItemWriter | Selects one writer per item |
| CompositeItemWriter | Sends the same chunk to configured delegates |
| Custom routing writer | Can group items by route and invoke each delegate once |
| FlatFileItemWriter | Writes items as lines in a file |
| JdbcBatchItemWriter | Writes items to a database in batches |

Example:

- An Order must be written to exactly one file based on status: ClassifierCompositeItemWriter.
- An Order must be written simultaneously to an audit table and a file: CompositeItemWriter or a custom fan-out writer.
- A chunk has multiple routes and needs separate bulk inserts per group: a custom grouping writer may be more efficient.

Do not use ClassifierCompositeItemWriter when the intent is broadcasting an item to every delegate. It is routing, not fan-out.

## 17. Impact of Routing on Chunks and Performance

ClassifierCompositeItemWriter receives a chunk from the Step and classifies each item. The selected delegate receives the corresponding item; standard implementations invoke the writer item by item, so delegates may receive write calls with very small chunks.

For example, a chunk has 100 items, with 70 going to writer A and 30 to writer B. The composite may invoke delegates multiple times instead of calling A once with a 70-item chunk and B once with a 30-item chunk.

This can affect performance if a delegate optimizes by batch, such as JdbcBatchItemWriter or an API-calling writer.

If you need to group items by route, you can implement a chunk-grouping writer:

~~~java
public class GroupingRoutingWriter<T> implements ItemWriter<T> {

    private final Classifier<T, ItemWriter<? super T>> classifier;

    public GroupingRoutingWriter(
            Classifier<T, ItemWriter<? super T>> classifier) {
        this.classifier = classifier;
    }

    @Override
    public void write(Chunk<? extends T> items) throws Exception {
        Map<ItemWriter<? super T>, List<T>> groups =
            new LinkedHashMap<>();

        for (T item : items) {
            ItemWriter<? super T> delegate = classifier.classify(item);

            if (delegate == null) {
                throw new IllegalStateException(
                    "Classifier did not return a writer"
                );
            }

            groups.computeIfAbsent(
                delegate,
                ignored -> new ArrayList<>()
            ).add(item);
        }

        for (Map.Entry<ItemWriter<? super T>, List<T>> entry
                : groups.entrySet()) {
            entry.getKey().write(new Chunk<>(entry.getValue()));
        }
    }
}
~~~

This example groups items by delegate and calls each writer once per sub-chunk. When using such a custom writer, you must still register ItemStream delegates with the Step and check write ordering, transactions, restarts, and resource lifecycle.

Do not optimize grouping before measuring performance. For file writers or small item counts, standard ClassifierCompositeItemWriter can be simpler and fast enough.

## 18. Transactions When Multiple Delegates Write in One Chunk

Classifier does not create separate transactions per branch. Delegate invocations occur while the Step processes the chunk.

If delegates write to the same database and participate in the same transaction manager, a transaction rollback can undo the chunk's database changes.

However, if one delegate writes a file and then the next delegate writes to the database and the database fails, the written file is not automatically rolled back like a database transaction.

~~~mermaid
flowchart TD
    A["Chunk starts transaction"] --> B["Route item 1 to file writer"]
    B --> C["Route item 2 to database writer"]
    C --> D{"Database write succeeded?"}
    D -->|Yes| E["Commit chunk"]
    D -->|No| F["Roll back database transaction"]
    F --> G["Output file may already contain data"]
~~~

For important output files, write to a dedicated staging resource per JobInstance or run ID. Only publish after the entire Step/Job succeeds and the file is fully verified.

If multiple databases or external systems do not share a transaction manager, do not assume a local transaction can roll back all side effects. Use an outbox, idempotency keys, staging, or compensating workflows depending on architecture.

## 19. Restart and State Across Multiple Delegates

If each delegate is an ItemStreamWriter, each writer needs a distinct name and ExecutionContext key. For example:

- paidOrdersWriter.
- cancelledOrdersWriter.
- reviewOrdersWriter.

Register all delegate streams with the Step so Spring Batch opens, updates, and closes them.

On restart:

- The same JobInstance must use the same identifying JobParameters.
- Output resources must point to the exact files from that run.
- Writer names and state keys must remain stable.
- Delegates must restore their respective positions.
- Do not allow two JobExecutions to write to the same file concurrently.
- If classifier rules change between runs, evaluate the impact on already-written items and remaining items.

### Changing the Classifier Between Restarts

Suppose on the first run status PAID was written to file A, and after deploying a new version the PAID rule routes to file B. When restarting the old JobInstance, unprocessed items may go to file B while committed items remain in file A.

The result can split the same batch across two outputs under two different rules. Therefore, business routing policies must remain stable for the lifetime of a JobInstance or be versioned/snapshotted in JobParameters.

If the policy changes, you may need to start a new JobInstance and rerun under a controlled business process.

## 20. Classification and Skip/Retry

A classifier can throw an exception when data is invalid or no route can be determined. Exceptions raised in a processor or writer are handled by the Step according to the corresponding fault-tolerance policy.

Example:

~~~java
return new StepBuilder("routeOrdersStep", jobRepository)
    .<OrderInput, Order>chunk(100, transactionManager)
    .reader(orderReader)
    .processor(orderProcessor)
    .writer(orderRouterWriter)
    .faultTolerant()
    .skip(UnknownOrderStatusException.class)
    .skipLimit(20)
    .build();
~~~

However, distinguish field parsing errors, invalid business state, missing writers for a route, transient delegate errors, and file write errors. If a classifier runs inside the writer and throws an exception, the framework may treat it as a write failure. Do not turn route configuration errors into skippable data errors if skipping drops items without a reject record.

## 21. Do Not Use Classifier to Split a Job into Independent Workflows

ClassifierCompositeItemWriter fits when branches only differ in write destination while belonging to the same Step and chunk lifecycle.

If each state needs its own transaction manager, retry/skip policy, commit interval, listeners/checkpoints, Step flow, or independent schedule, consider classifying first and running separate Steps, or using a flow/Job with conditional transitions.

A writer classifier does not create those operational boundaries.

## 22. Classification in Partitioning

Classifier and partitioning solve two different problems.

- Classifier selects a delegate per item.
- Partitioner splits a data source into multiple StepExecutions/workers.

Both can be combined: each worker processes a range, and then a writer classifier routes items in that range to the appropriate outputs.

However, pay attention to:

- Each worker needs its own resources if writers are stateful.
- Do not let multiple partitions write to the same file without synchronization.
- Output paths should include the partition ID or use concurrency-safe writers.
- Each worker must have its own ExecutionContext.
- Aggregate outputs after the manager confirms all workers succeeded.

If you only need to split files by status, you do not need partitioning just to create branches. If you need higher throughput via parallelism, design partitioning separately.

## 23. Testing the Classifier Independently

Business policies should have dedicated unit tests. Example:

~~~java
@Test
void routesPaidHighValueOrderToHighValueRoute() {
    Order order = new Order(
        "O-2001",
        OrderStatus.PAID,
        new BigDecimal("1500.00")
    );

    assertEquals(
        OrderRoute.HIGH_VALUE,
        routingPolicy.classifyOrder(order)
    );
}
~~~

Test branches:

- Every enum value.
- Null status if possible.
- Blank or invalid fields.
- Thresholds just below, equal to, and just above.
- Multiple simultaneous conditions.
- Priority state when two rules match at once.
- Null or negative monetary amounts.

Unit testing a classifier does not require a Spring context if the policy is a plain Java class.

## 24. Testing ClassifierCompositeItemWriter

You can use fake writers appending items to Lists to verify routing:

~~~java
@Test
void routesItemsToMatchingWriters() throws Exception {
    List<Order> paid = new ArrayList<>();
    List<Order> cancelled = new ArrayList<>();

    ItemWriter<Order> paidWriter =
        chunk -> paid.addAll(chunk.getItems());

    ItemWriter<Order> cancelledWriter =
        chunk -> cancelled.addAll(chunk.getItems());

    ClassifierCompositeItemWriter<Order> router =
        new ClassifierCompositeItemWriterBuilder<Order>()
            .classifier(order -> order.status() == OrderStatus.PAID
                ? paidWriter
                : cancelledWriter)
            .build();

    Chunk<Order> items = new Chunk<>();
    items.add(new Order(
        "O-1", OrderStatus.PAID, new BigDecimal("10.00")
    ));
    items.add(new Order(
        "O-2", OrderStatus.CANCELLED, new BigDecimal("20.00")
    ));
    items.add(new Order(
        "O-3", OrderStatus.PAID, new BigDecimal("30.00")
    ));

    router.write(items);

    assertEquals(List.of("O-1", "O-3"),
        paid.stream().map(Order::orderId).toList());

    assertEquals(List.of("O-2"),
        cancelled.stream().map(Order::orderId).toList());
}
~~~

This test verifies each item is forwarded to the right delegate. You can add writer spies to verify how many times delegates are called and the chunk sizes they receive.

With standard ClassifierCompositeItemWriter, do not assume a delegate receives one chunk combining all items for the same route. If performance depends on bulk writes, test the grouping behavior of your custom writer separately.

## 25. Testing ClassifierCompositeItemProcessor

The composite processor should also be tested across every branch:

~~~java
@Test
void selectsProcessorByInputType() throws Exception {
    ItemProcessor<RawOrder, Order> retail =
        raw -> new Order(raw.id(), OrderStatus.NEW, raw.total());

    ItemProcessor<RawOrder, Order> wholesale =
        raw -> new Order(raw.id(), OrderStatus.REVIEW, raw.total());

    ClassifierCompositeItemProcessor<RawOrder, Order> processor =
        new ClassifierCompositeItemProcessorBuilder<RawOrder, Order>()
            .classifier(raw -> "WHOLESALE".equals(raw.type())
                ? wholesale
                : retail)
            .build();

    Order result = processor.process(
        new RawOrder("O-10", "WHOLESALE", new BigDecimal("50.00"))
    );

    assertEquals(OrderStatus.REVIEW, result.status());
}
~~~

Test cases where a delegate processor returns null to confirm items are filtered as intended. Test unknown types to ensure an explicit fallback or exception.

## 26. Testing Step Integration and Real Output

Classifier unit tests do not verify whether Spring Batch opens delegate writers, whether ItemStream delegates are registered properly, whether JobParameters bind to output paths, whether transactions and StepExecution counters are accurate, whether output files have valid contents, or whether restarts restore each writer's state.

Use **spring-batch-test** and JobLauncherTestUtils to run a real Step. After running, verify:

1. BatchStatus and ExitStatus.
2. Read, write, filter, and skip counts.
3. Item counts in each output.
4. No items appear in multiple branches if exclusive routing is required.
5. No items are lost.
6. Files are closed and readable.
7. Delegate streams open/close following proper lifecycle.

Do not merely check that files exist. Parse or read back their contents to confirm the right items landed in each route.

## 27. Testing Failure and Restart Across Multiple Outputs

Create a multi-chunk test and intentionally fail one delegate:

1. The first chunk writes several items to the outputs.
2. The next chunk encounters an error in one delegate.
3. Verify the Step is FAILED and transactions roll back as configured.
4. Inspect which files received data and confirm an appropriate staging/publish policy.
5. Restart with the same JobInstance and identifying JobParameters.
6. Verify each delegate restores its checkpoint accurately.
7. Verify no items are lost or duplicated according to the designed semantics.
8. Only publish outputs after the entire Step/Job succeeds.

For database writers in the same transaction, verify rollback via database state. For file writers, verify separately because the filesystem does not automatically participate in database transactions.

## 28. Observability and Routing Audits

In production batch jobs, you need to know which decision routed each item when investigating data issues.

You can emit structured logs containing JobExecution ID, StepExecution ID, item business key, selected route, routing policy version, delegate/output resource, write outcome, and exception.

Avoid logging full items if they contain sensitive data. Use appropriate business keys or correlation IDs.

If durable auditing per route is needed, consider storing the route in a column or audit table. Do not rely solely on text logs to reconstruct business decisions.

### Snapshotting Policy Version

If routing policies can change, pass the policy version via JobParameters or store it in JobExecutionContext. On restart, inspect the version and ensure the JobInstance uses the same rule.

Example parameter:

~~~java
.addString("routingPolicyVersion", "v3", true)
~~~

If the policy version is an identifying parameter, it participates in determining the JobInstance. If its purpose is purely metadata, it can be marked non-identifying, though restarts must still restore the same value as designed. This choice must align with the batch's business identity.

## 29. Common Implementation Pitfalls

### Returning null When No Delegate Is Found

The composite cannot write an item through a null writer. Use a fallback writer or throw a meaningful exception.

### Handling Only Common States

A new enum or field value can leave the classifier missing a branch. Use switch exhaustiveness when possible and test all states.

### Classifying by Unnormalized Strings

"paid", "PAID", and "Paid" may go to different branches. Parse and normalize before routing.

### Calling APIs Inside a Classifier

Each classify call may repeat the API call on retry, increasing latency and producing unstable results. Enrich earlier in a processor.

### Using ClassifierCompositeItemWriter to Broadcast

The classifier selects one delegate per item. To write to multiple destinations, use CompositeItemWriter or custom fan-out.

### Forgetting to Register Delegate ItemStreams

A delegate may still receive writes without proper open/update/close lifecycle calls. Register streams with the Step.

### Sharing an Output Resource

Two writers may overwrite or interleave data. Each delegate needs its own resource or an explicit synchronized write mechanism.

### Thinking Routing Creates Separate Transactions

All delegates still run within the Step's chunk lifecycle. A classifier does not create a separate transaction boundary.

### Assuming Files Roll Back with the Database

A file may already be flushed even when the database transaction rolls back. Use staging and publish.

### Changing Routing Rules Across Restarts

Items before and after restart may go to different branches. Version or snapshot policies.

### Using a Writer Classifier for Workflows with Independent Lifecycles

If each route needs its own retry, transaction, or Step flow, model it as Steps/flows rather than only swapping delegate writers.

### Ignoring Performance When Delegates Receive Single Items

A batch-optimized writer may be called repeatedly with tiny chunks. Measure performance and consider a grouping writer when needed.

## 30. Workflow for Designing Field or Business-State Routing

When building routing, you can follow this sequence:

1. **Identify the item:** which fields can be used for classification?
2. **Identify the state:** is the route a direct field or a derived business state?
3. **Normalize data:** parse enums, normalize strings, and check for nulls.
4. **Write the policy:** place priority order and boundary rules into a testable method/class.
5. **Choose the routing point:** processor if different transformations are needed; writer if only choosing the write destination.
6. **Declare delegates:** each writer/processor has clear configuration and ownership.
7. **Register streams:** every ItemStream delegate must be managed by the Step.
8. **Design fallback:** reject, quarantine, or fail for invalid routes.
9. **Check transactions:** determine which delegates share a transaction and which outputs need staging.
10. **Design restart:** keep resources, checkpoints, and policy versions stable.
11. **Test:** all branches, boundaries, unknown states, failures, restarts, and actual outputs.
12. **Observe:** log routes, execution IDs, and policy versions appropriately.

## 31. Key Takeaways

- Classifier maps an item to a classification result, usually a delegate writer or processor.
- Field-based classification directly uses status, type, category, or source.
- Business-state classification can combine multiple fields and requires clear priority rules.
- Normalize and validate data before the classifier runs.
- Classifiers should be pure, deterministic, and never call APIs/databases or produce side effects.
- ClassifierCompositeItemWriter selects one writer per item.
- ClassifierCompositeItemProcessor selects a processor per input item.
- CompositeItemWriter has fan-out semantics, unlike routing.
- ClassifierCompositeItemWriter does not automatically manage every ItemStream delegate's lifecycle; register streams with the Step.
- Routing does not create separate Steps or transaction boundaries.
- File outputs do not automatically roll back with database transactions; use staging and publish.
- Unknown states require a fallback or explicit exception, never returning null.
- Routing policies must remain stable across restarts or be versioned.
- Standard classifier writers may invoke delegates item by item; consider grouping if bulk writes are needed.
- Test all branches, boundaries, delegate lifecycles, real outputs, and restarts.

Classifier separates routing decisions from data reading and writing logic. When fields are normalized, business states are computed consistently, delegates have clear lifecycles, and outputs are controlled for transactions/restarts, a single Step can handle multiple item types while keeping the batch flow easy to understand and test.

