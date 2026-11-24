# Classification Errors and Skip in Spring Batch

In a batch job with multiple item types, the writer may need to pick a write destination based on each item's properties. For example, domestic orders are written to table A, international orders to table B, while records of an unsupported type must be quarantined or handled as errors. Spring Batch provides ClassifierCompositeItemWriter to route items to the appropriate writer.

When classification or a delegate writer fails, the step must decide whether to retry, skip, or stop the job. These two error groups must be distinguished: classification errors indicate the item could not determine a write destination; delegate errors indicate a destination was chosen yet the write operation failed. Classifying exceptions properly lets the batch skip bad data in a controlled way while still failing when infrastructure or configuration is broken.

## 1. What Does ClassifierCompositeItemWriter Do?

ClassifierCompositeItemWriter receives a chunk and uses a Classifier to pick an ItemWriter for each item. Each item is forwarded to a delegate based on the classification result.

~~~text
Chunk<Order>
  |
  v
ClassifierCompositeItemWriter
  |
  +-- Order type DOMESTIC ------> domesticWriter
  |
  +-- Order type INTERNATIONAL -> internationalWriter
  |
  +-- Order type PARTNER --------> partnerWriter
~~~

This is routing: each item goes to one selected delegate. Unlike CompositeItemWriter, where every delegate receives the entire chunk, the classifier writer picks a writer per item.

| Writer | Behavior |
| --- | --- |
| CompositeItemWriter | Sends the same chunk to all delegates in configured order |
| ClassifierCompositeItemWriter | Selects one delegate per item |
| Custom grouping writer | Classifies items, groups by destination, then calls each delegate once per group |

For example, a chunk has 5 orders: 3 domestic and 2 international. The classifier writer forwards the 3 domestic items to domesticWriter and the 2 international items to internationalWriter. It does not copy each order to both writers.

## 2. Distinguishing Classification Errors from Write Errors

There are two points where exceptions can arise:

1. **Inside the classifier:** the system cannot find a valid route for the item, or classification logic detects invalid data.
2. **Inside the delegate writer:** a route was chosen, yet writing to the database, file, API, or other target failed.

Example:

~~~text
Order 101
  classifier -> DOMESTIC
  domesticWriter -> write succeeds

Order 102
  classifier -> UNKNOWN
  -> UnroutableOrderException
  -> no delegate is invoked for this item

Order 103
  classifier -> INTERNATIONAL
  internationalWriter -> database timeout
  -> TransientDataAccessException
~~~

Order 102's error may be a single record's data error. Order 103's error may be a transient infrastructure error. You should not apply the exact same skip/retry policy to both groups.

## 3. Configuring ClassifierCompositeItemWriter

In Spring Batch 5, you can create ClassifierCompositeItemWriter and attach a classifier via setClassifier:

~~~java
@Bean
ClassifierCompositeItemWriter<Order> orderRoutingWriter(
        ItemWriter<Order> domesticWriter,
        ItemWriter<Order> internationalWriter) {

    ClassifierCompositeItemWriter<Order> writer =
        new ClassifierCompositeItemWriter<>();

    writer.setClassifier(order -> {
        return switch (order.market()) {
            case DOMESTIC -> domesticWriter;
            case INTERNATIONAL -> internationalWriter;
        };
    });

    return writer;
}
~~~

This example assumes market() is a two-value enum. If the enum or source data can contain other routes, define an explicit fallback branch or exception rather than letting an invalid route reach a writer.

Registering the writer on the step:

~~~java
@Bean
Step routeOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ClassifierCompositeItemWriter<Order> orderRoutingWriter) {

    return new StepBuilder("routeOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(reader)
        .writer(orderRoutingWriter)
        .build();
}
~~~

ClassifierCompositeItemWriter is responsible for invoking the classifier and the selected writer. The step still manages chunk transactions and fault tolerance.

## 4. Classifiers Should Be Simple, Deterministic, and Side-Effect-Free

A classifier should rely on data already present in the item, such as an enum, customer type, region, or destination code. The same item must produce the same result within a run.

Avoid calling a database or HTTP API from a classifier to decide routes item by item. That can trigger N+1 queries/network calls, cause routes to shift between retries, and complicate error control. If lookups are needed for classification, enrich items earlier in a processor or use a cache/reference service with clear lifecycle and concurrency guarantees.

Testable classifier example:

~~~java
private ItemWriter<? super Order> classify(
        Order order,
        ItemWriter<Order> domesticWriter,
        ItemWriter<Order> internationalWriter) {

    return switch (order.market()) {
        case DOMESTIC -> domesticWriter;
        case INTERNATIONAL -> internationalWriter;
    };
}
~~~

Do not store currentWriter or currentOrder in mutable fields of the classifier. The writer can be used across multiple executions or threads; routes should be computed from the invocation arguments.

## 5. Handling Unsupported Routes

Two main strategies exist when an item has no valid route:

- Select a quarantine/reject writer to store the record along with the reason it could not be processed.
- Throw a custom-typed exception so the step applies skip or fail.

Example:

~~~java
public class UnroutableOrderException extends RuntimeException {

    public UnroutableOrderException(String message) {
        super(message);
    }
}
~~~

Classifier:

~~~java
writer.setClassifier(order -> {
    if (order.market() == null) {
        throw new UnroutableOrderException(
            "Order " + order.id() + " has no market"
        );
    }

    return switch (order.market()) {
        case DOMESTIC -> domesticWriter;
        case INTERNATIONAL -> internationalWriter;
    };
});
~~~

If an invalid type is a per-record data error and business rules allow skipping, configure skip for UnroutableOrderException. If an invalid route indicates the entire file uses an incompatible schema or deployment configuration is wrong, fail the job instead of skipping en masse.

Never return null as a way to say "no writer". Return an explicit reject writer or throw a meaningful exception. A null delegate usually causes confusing runtime errors and fails to express the business cause.

## 6. Using a Reject Writer When Error Records Must Be Kept

Skipping prevents an item from continuing through the main writers. If you need to retain the record for correction and reprocessing, use a reject/quarantine writer:

~~~java
@Bean
ItemWriter<Order> rejectedOrderWriter(JdbcTemplate jdbcTemplate) {
    return chunk -> {
        for (Order order : chunk) {
            jdbcTemplate.update("""
                insert into rejected_order
                    (source_order_id, reason, rejected_at)
                values (?, ?, current_timestamp)
                """,
                order.id(),
                "Unsupported market"
            );
        }
    };
}
~~~

The classifier can route explicitly:

~~~java
writer.setClassifier(order -> {
    if (order.market() == null) {
        return rejectedOrderWriter;
    }

    return switch (order.market()) {
        case DOMESTIC -> domesticWriter;
        case INTERNATIONAL -> internationalWriter;
    };
});
~~~

A reject writer should persist enough details to trace back to the source, such as source file/batch ID, business key, error, and timestamp. If payloads are sensitive, store only permitted fields and apply appropriate retention.

A reject writer is a business route. It differs from SkipListener, which is invoked when Spring Batch decides to skip an item due to an exception. Both can be used, yet avoid writing the same record twice.

## 7. Errors in the Classifier Are Handled in the Write Phase

The classifier is called inside ClassifierCompositeItemWriter.write(). If the classifier throws an exception, the exception propagates out of the writer and the step treats it as a write-phase error.

Example:

~~~java
writer.setClassifier(order -> {
    if (order.market() == null) {
        throw new UnroutableOrderException(
            "Missing market for order " + order.id()
        );
    }
    return writerFor(order.market());
});
~~~

If UnroutableOrderException is declared as a skip exception, Spring Batch can skip the item per skip policy. If it is not skippable, the exception fails the step after any configured retry policy is exhausted.

Do not catch exceptions inside the classifier and return a default writer just to keep the job going. That could write items into the wrong table or wrong system. If a fallback route exists, name it and state its purpose clearly, such as unknownMarketWriter.

## 8. Errors from Delegate Writers

After the classifier picks a writer, the delegate can fail because of:

- Validation or constraint errors for a record.
- Duplicate keys or conflicting data.
- Database connection timeouts or deadlocks.
- Files unable to open/write or disk full.
- HTTP service returning errors or timing out.
- Misconfigured writers or missing resources.

Categorize errors by root cause:

| Error category | Examples | Typically appropriate handling |
| --- | --- | --- |
| Invalid record data | Missing required field, unsupported route | Skip or quarantine if permitted |
| Transient error | Deadlock, connection reset, service unavailable | Bounded retry |
| Configuration error | Missing writer, wrong table, missing output path | Fail fast |
| Persistent system error | Disk full, incompatible schema | Usually fail and fix root cause |
| Unclassified error | Uncategorized runtime exception | Fail and investigate |

Do not configure skip on an overly broad superclass such as Exception just so the job does not stop. Doing so can hide programming bugs, configuration errors, or infrastructure failures while silently losing many items.

## 9. Configuring Skip for Classification Errors

Spring Batch allows configuring skip exceptions on the step:

~~~java
return new StepBuilder("routeOrdersStep", jobRepository)
    .<Order, Order>chunk(100, transactionManager)
    .reader(reader)
    .writer(orderRoutingWriter)
    .faultTolerant()
    .skip(UnroutableOrderException.class)
    .skipLimit(50)
    .build();
~~~

In this example, up to 50 items throwing UnroutableOrderException can be skipped. Exceeding the limit fails the step. skipLimit is a total limit for skips across the step, not a separate limit per exception type or for the write phase alone.

Spring Batch can apply skip to errors occurring in read, process, or write. Verify which phase an exception actually occurs in and test with a real job; do not infer from an exception's name that it only occurs in one phase.

If a wrong route indicates a critical file-wide error, do not configure skip for that exception. Letting the step fail catches producer/schema/configuration drift early.

## 10. How Is the Skip Limit Counted?

skipLimit(n) caps the total number of skipped items in the step. Once the limit is reached and another skippable error occurs, the step fails.

Example of skipLimit(3):

~~~text
Item 10 -> skip count 1
Item 21 -> skip count 2
Item 35 -> skip count 3
Item 44 -> next error -> step FAILED
~~~

Skips across read, process, and write all contribute to the skip count. Thus, if the step already skipped many parse errors in the reader, fewer classification errors remain within the skip allowance.

Set the limit based on data quality and SLAs. Too high a limit can let a job complete even when most data is bad; too low a limit can prevent a batch with a few valid error records from finishing.

## 11. Combining Retry and Skip

Retry is for errors likely to resolve on their own. Skip is for items that cannot be processed under current rules yet business policy permits omitting them.

Example:

~~~java
return new StepBuilder("routeOrdersStep", jobRepository)
    .<Order, Order>chunk(100, transactionManager)
    .reader(reader)
    .writer(orderRoutingWriter)
    .faultTolerant()
    .retry(TransientDataAccessException.class)
    .retryLimit(3)
    .skip(UnroutableOrderException.class)
    .skipLimit(50)
    .build();
~~~

Here:

- UnroutableOrderException is skipped per data policy.
- TransientDataAccessException is retried up to the limit.
- Exceptions outside the retry/skip policies fail the step.

When an exception is configured for both retry and skip, Spring Batch attempts retries first; once the retry policy exhausts attempts, the skip policy decides whether to skip the item. Avoid overlapping policies without a clear reason.

Do not retry deterministic routing errors. The same item with the same data will usually keep having no route on the next attempt.

## 12. Using SkipListener to Record Skipped Items

SkipListener lets the application receive details about skipped items in each phase:

- onSkipInRead(Throwable): failed to create an item from the source.
- onSkipInProcess(item, Throwable): item failed while processed by the processor.
- onSkipInWrite(item, Throwable): item failed while written by the writer.

Example:

~~~java
public class OrderSkipListener
        implements SkipListener<OrderInput, Order> {

    private final RejectedOrderRepository rejectedOrders;

    public OrderSkipListener(RejectedOrderRepository rejectedOrders) {
        this.rejectedOrders = rejectedOrders;
    }

    @Override
    public void onSkipInRead(Throwable throwable) {
        log.warn("Could not read an order", throwable);
    }

    @Override
    public void onSkipInProcess(OrderInput item, Throwable throwable) {
        rejectedOrders.record(item.id(), "PROCESS", throwable);
    }

    @Override
    public void onSkipInWrite(Order item, Throwable throwable) {
        rejectedOrders.record(item.id(), "WRITE", throwable);
    }
}
~~~

Register the listener with listener(orderSkipListener) on the step builder. In real code, the listener's input/output generics must match the step. If the reader returns OrderInput and the processor returns Order, onSkipInProcess receives the input while onSkipInWrite receives the output.

Skip listeners fit auditing and statistics. If error records must be persisted durably, write through a resource participating in an appropriate transaction or use a dedicated quarantine mechanism. Do not just log and assume records can be recovered later.

## 13. How SkipListener Differs from ItemWriteListener

These two listeners serve different purposes:

| Listener | Callbacks | Meaning |
| --- | --- | --- |
| ItemWriteListener | beforeWrite, afterWrite, onWriteError | Tracks a writer/chunk invocation |
| SkipListener | onSkipInWrite | Records the specific item the framework decided to skip |

onWriteError usually only knows the exception and the chunk sent to the writer; it does not itself identify which item caused the failure. onSkipInWrite receives the specific item identified as skipped.

With ClassifierCompositeItemWriter, delegates are invoked per item, so an exception can arise right at the item being routed. Even so, transactions remain chunk-scoped; identifying the item does not mean each item has its own transaction.

## 14. Write-Phase Skip and Chunk Rollback

In a chunk-oriented step, the writer is invoked inside the chunk transaction. If a delegate fails, by default the step rolls back the transaction per exception policy. Items in the chunk may have to be reprocessed.

For writers receiving an entire chunk, the framework does not always know which item failed. In a fault-tolerant step, Spring Batch can roll back and scan items individually to pinpoint the failing item and apply skip. Exact execution paths depend on the writer, rollback policy, and framework version.

ClassifierCompositeItemWriter already calls delegates per item in its loop, so an exception from a delegate happens while handling a specific item. Still, the exception escapes the write(chunk) call and sends the chunk through the step's rollback/retry/skip mechanism.

Do not treat a delegate succeeding once as proof its side effects committed. If the transaction rolls back, database writes can be undone; files or remote calls might not be undone.

## 15. Delegates Can Be Invoked Again on Retry or Write Skip

Suppose a chunk has three items:

~~~text
Chunk: A, B, C

First invocation:
  A -> routed writer succeeds
  B -> routed writer throws exception
  C -> not processed yet

Chunk rolls back
Retry/scan per fault-tolerant policy:
  A may be sent again
  B is checked and may be skipped
  C is sent as the framework continues processing
~~~

Actual invocation counts depend on retry/skip configuration and how the writer is called during scanning. What is essential is designing delegates to be safe when re-invoked.

Database writers should use unique keys or upserts where appropriate. API writers should send idempotency keys. File writers need checkpoints/transactional buffers and proper restart paths. Do not perform an unrepeatable external side effect inside a delegate assuming the writer runs only once.

## 16. Distinguishing Data Errors from Infrastructure Errors

An error can occur inside a delegate that should not be skipped:

- DataAccessResourceFailureException: datasource unreachable.
- Timeouts to external systems.
- File system out of space.
- Exhausted connection pool.
- Authentication/authorization errors due to misconfiguration.

If you skip these errors, the step may mark items as processed even though data was never written at the destination. That causes silent data loss.

Conversely, an error like UnroutableOrderException can be skippable if:

- The error affects only the current item.
- Other items can still be processed independently.
- Skipped records are audited or quarantined as required.
- Data owners accept reprocessing them later.

Name and type exceptions by business cause, not solely by where they are thrown. An error from a writer is not automatically skippable.

## 17. Fallback Writer or Exception?

When the classifier cannot find a route, choosing between fallback and exception depends on the contract:

| Scenario | Handling |
| --- | --- |
| An official OTHER group is supported | Route to otherWriter |
| Record is invalid yet must be retained | Route to reject/quarantine writer |
| Record is invalid and allowed to be dropped | Throw dedicated exception, configure skip and audit |
| Unknown route shows producer broke schema | Fail job |
| Unknown route due to missing writer config | Fail fast, do not skip |

A fallback must have business meaning. Do not use a default writer to write all unknown routes into a normal table, as bad data could be treated as valid.

## 18. ClassifierCompositeItemWriter and Performance

ClassifierCompositeItemWriter routes each item by invoking a delegate per item. This keeps code simple and ties delegate errors to the item being processed, yet can reduce batch efficiency if delegates are designed for large chunks.

For example, a JdbcBatchItemWriter receiving a singleton chunk per order will not batch all 100 orders into one JDBC batch the way it would when receiving the whole chunk:

~~~text
Chunk with 100 items
  |
  +-- writer A.write(chunk of 1 item)
  +-- writer B.write(chunk of 1 item)
  +-- writer A.write(chunk of 1 item)
  +-- ...
~~~

If throughput is critical, you can write a custom routing writer that groups items by route and invokes each delegate once with that group's chunk. Note that grouping can change write ordering across routes.

## 19. Grouping Items by Route Before Calling Delegates

Conceptual example for a grouping writer:

~~~java
public class GroupingOrderWriter implements ItemWriter<Order> {

    private final Function<Order, Market> classifier;
    private final Map<Market, ItemWriter<Order>> delegates;

    public GroupingOrderWriter(
            Function<Order, Market> classifier,
            Map<Market, ItemWriter<Order>> delegates) {
        this.classifier = classifier;
        this.delegates = delegates;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) throws Exception {
        Map<Market, List<Order>> groups = new LinkedHashMap<>();

        for (Order order : chunk) {
            Market market = classifier.apply(order);
            if (market == null || !delegates.containsKey(market)) {
                throw new UnroutableOrderException(
                    "No writer for order " + order.id()
                );
            }
            groups.computeIfAbsent(market, key -> new ArrayList<>())
                .add(order);
        }

        for (Map.Entry<Market, List<Order>> entry : groups.entrySet()) {
            delegates.get(entry.getKey())
                .write(new Chunk<>(entry.getValue()));
        }
    }
}
~~~

This is an illustrative structure; production implementations must manage generic types, exception attribution, and the ItemStream lifecycle. LinkedHashMap preserves the order routes first appeared in the chunk, and item order within each group is preserved.

Grouping alters global ordering. For example, a chunk A1, B1, A2 is written as A1, A2, then B1. If ordering across routes matters, do not group or use another writer design that preserves order.

## 20. Registering Delegate ItemStreams

ClassifierCompositeItemWriter is a routing writer; the step cannot automatically infer every delegate writer the classifier might pick to manage their lifecycles. If delegates implement ItemStream, register them with the step:

~~~java
return new StepBuilder("routeOrdersStep", jobRepository)
    .<Order, Order>chunk(100, transactionManager)
    .reader(reader)
    .writer(orderRoutingWriter)
    .stream(domesticWriter)
    .stream(internationalWriter)
    .build();
~~~

This is especially important for FlatFileItemWriter, cursor-holding readers/writers, or custom writers opening resources in open(). Without proper open, state update, or close lifecycle calls, the job can fail on write, drop buffered data, or leak resources.

If using a wrapper around a delegate, the wrapper must forward open, update, close or register the delegate stream directly. Pick one clear owner so callbacks are not invoked twice.

## 21. Step Scope and Multiple Routes

If each route needs its own parameters from job/step execution, you can declare delegate writers as StepScope. For instance, each writer receives a different output path or a tenant parameter.

~~~java
@Bean
@StepScope
FlatFileItemWriter<Order> domesticWriter(
        @Value("#{jobParameters['domesticOutput']}") Resource output) {

    return new FlatFileItemWriterBuilder<Order>()
        .name("domesticOrderWriter")
        .resource(output)
        .lineAggregator(OrderLineAggregator::toLine)
        .build();
}
~~~

The classifier should be wired with the corresponding proxies/dependencies and only access targets once step scope is active. Do not initialize or call step-scoped targets when the application context has no active StepExecution.

Each delegate needs a unique stream name within the step if it saves execution context. Two stateful writers sharing the same name can cause checkpoint key collisions.

## 22. Retry Policy for Transient Delegate Errors

For example, a database-writing route can hit deadlocks or transient connection errors. You can retry exceptions identified as transient:

~~~java
return new StepBuilder("routeOrdersStep", jobRepository)
    .<Order, Order>chunk(100, transactionManager)
    .reader(reader)
    .writer(orderRoutingWriter)
    .faultTolerant()
    .retry(DeadlockLoserDataAccessException.class)
    .retry(TransientDataAccessException.class)
    .retryLimit(3)
    .skip(UnroutableOrderException.class)
    .skipLimit(50)
    .build();
~~~

The exact list of exceptions must match the database/driver and Spring version in use. Some transient exceptions sit within another exception's hierarchy; avoid duplicate or overly broad configurations unintentionally.

If infrastructure errors persist past the retry limit, the step should fail for the scheduler or operator to handle. Skipping a connection error does not get data written.

## 23. Custom SkipPolicy for Complex Rules

When skipping depends on error counts, route types, or context, you can use a custom SkipPolicy:

~~~java
public class RoutingSkipPolicy implements SkipPolicy {

    private final long maxUnroutable;

    public RoutingSkipPolicy(long maxUnroutable) {
        this.maxUnroutable = maxUnroutable;
    }

    @Override
    public boolean shouldSkip(Throwable throwable, long skipCount)
            throws SkipLimitExceededException {

        if (throwable instanceof UnroutableOrderException) {
            if (skipCount < maxUnroutable) {
                return true;
            }
            throw new SkipLimitExceededException(
                maxUnroutable,
                throwable
            );
        }

        return false;
    }
}
~~~

Then attach the policy to the step via skipPolicy. A custom policy must handle all exceptions and limits accurately; returning false means the exception is not skippable. Never return true for every RuntimeException.

If the rule is simply skipping one exception type with a fixed cap, the skip and skipLimit DSL is easier to read and less error-prone.

## 24. Testing the Classifier Independently

A classifier is pure logic, so it can be unit tested without a Spring Batch context:

~~~java
@Test
void routesDomesticOrderToDomesticWriter() {
    ItemWriter<Order> domestic = mock(ItemWriter.class);
    ItemWriter<Order> international = mock(ItemWriter.class);

    Classifier<Order, ItemWriter<? super Order>> classifier =
        order -> order.market() == Market.DOMESTIC
            ? domestic
            : international;

    assertThat(classifier.classify(domesticOrder))
        .isSameAs(domestic);
    assertThat(classifier.classify(internationalOrder))
        .isSameAs(international);
}
~~~

Also test:

- Every supported enum/route has a writer.
- Null or unknown values are handled per policy.
- Routes do not depend on mutable state of the classifier.
- The same item always yields the same route.
- No route returns null.

If the classifier uses a mapping table, test completeness of the mapping to catch a newly added enum type lacking a writer.

## 25. Testing Writer Routing Fan-Out

Unit tests for ClassifierCompositeItemWriter should verify each item is forwarded to the right delegate:

~~~java
@Test
void sendsEachItemOnlyToItsClassifiedWriter() throws Exception {
    ItemWriter<Order> domestic = mock(ItemWriter.class);
    ItemWriter<Order> international = mock(ItemWriter.class);

    ClassifierCompositeItemWriter<Order> writer =
        new ClassifierCompositeItemWriter<>();
    writer.setClassifier(order ->
        order.market() == Market.DOMESTIC
            ? domestic
            : international
    );

    writer.write(new Chunk<>(List.of(
        domesticOrder,
        internationalOrder,
        secondDomesticOrder
    )));

    verify(domestic, times(2)).write(any());
    verify(international, times(1)).write(any());
}
~~~

Because the writer routes item by item, each delegate can be called multiple times during a single write(chunk). If you need to verify exact items, use an ArgumentCaptor or verify singleton chunks contain the expected business keys.

Add a test when the classifier throws UnroutableOrderException: no delegate is invoked for the failing item and the exception propagates outward.

## 26. Testing Skip in the Write Phase

To test skipping realistically, run a step with a reader providing valid orders and one order with no route. Configure skip for UnroutableOrderException and attach a SkipListener.

Assertions:

- The step completes when error counts stay within the skip limit.
- Valid orders are written to the right delegates.
- The unroutable order is not written to business writers.
- SkipListener.onSkipInWrite receives the right business key and exception.
- Skip count in StepExecution equals the number of skipped items.
- Exceeding the skip limit causes the step to end FAILED.

Example dataset:

~~~text
Order 1 -> DOMESTIC
Order 2 -> UNKNOWN
Order 3 -> INTERNATIONAL
~~~

Expected result: order 1 goes to domestic writer, order 3 goes to international writer, order 2 is skipped/audited per policy. Do not check only job status; verify actual data at every destination.

## 27. Testing Delegate Failures and Rollback

Create a delegate writer that intentionally fails on a specific business key:

~~~java
public class FailingDomesticWriter implements ItemWriter<Order> {

    @Override
    public void write(Chunk<? extends Order> chunk) {
        if (chunk.getItems().stream()
                .anyMatch(order -> order.id() == 102L)) {
            throw new InvalidDomesticOrderException(
                "Order 102 is invalid"
            );
        }
    }
}
~~~

Integration tests must verify:

1. The right delegate writer was chosen.
2. The exception occurred in the write phase.
3. The chunk rolls back according to transaction policy.
4. If the exception is skipped, only valid items are written in the end.
5. If the exception is not skipped, the step fails and uncommitted chunk data is absent from transactional tables.

For external delegates, asserting database rollback alone is not enough. Mock the service or broker to verify idempotency and side effects after retry.

## 28. Testing Retry and Route Idempotency

A writer might fail transiently on the first attempt and succeed on retry. Tests should simulate:

~~~text
Order 201 -> route INTERNATIONAL
Attempt 1 -> internationalWriter timeout
Attempt 2 -> internationalWriter succeeds
~~~

Verify:

- The classifier selects the same route on every attempt.
- Business key/idempotency key remains unchanged.
- No duplicate rows/events appear after retry.
- Retry count is recorded accurately.
- Once retry limit is exhausted, the step fails or skips per policy.

If the classifier depends on mutable state like attemptNumber or API results, routes can change between attempts. Compute routes from stable data or persist resolved routes durably if business rules demand it.

## 29. Monitoring Errors and Skips in Production

A routing batch should track item counts per route and error counts:

- Items classified per route.
- Items with no route.
- Errors per delegate.
- Retries and skips per phase.
- Processing duration per delegate.
- Records in quarantine/reject store.
- Failed item ratio over total items.

Logs should include job execution ID, step execution ID, route, business key, and exception type. Do not log full payloads if they contain sensitive data.

If the unroutable rate spikes suddenly, the producer may have added a new type or the contract changed. Threshold alerts catch this early. Do not blindly raise skip limits when a job fails; first determine whether errors are valid new data, schema drift, or missing delegate configuration.

## 30. Common Pitfalls with Classification and Skip

**Returning null when no route exists:** confusing runtime errors with no business semantics. Throw a custom exception or route to a reject writer.

**Skipping every RuntimeException:** can hide configuration, database, or programming bugs. Only skip explicitly identified record errors.

**Retrying deterministic classification errors:** the same data will keep failing to find a route. Use skip/quarantine or fail.

**Skipping connection errors:** items may be marked skipped even though they were never written to the destination. Retry or fail infrastructure errors.

**Classifier calling APIs/databases per item:** causes N+1 calls and unstable routes on retry. Enrich earlier or use controlled lookups.

**Assuming each delegate receives a sub-chunk:** ClassifierCompositeItemWriter routes item by item and invokes writers per item. Consider a grouping writer if batch efficiency is needed.

**Forgetting to register delegate ItemStreams:** file/cursor writers may not be opened/updated/closed. Register delegate streams with the step.

**Confusing SkipListener with ItemWriteListener:** write error listener tracks writer invocations; SkipListener records items actually skipped.

**Not testing skip limits:** jobs can skip too many records. Set limits per data quality and test threshold breaches.

**Not auditing skipped records:** bad data cannot be traced or reprocessed. Persist business key, source, and reason.

**Lack of idempotency on retry:** a delegate may have produced side effects before an error was detected. Use unique keys, upserts, idempotency keys, or outboxes.

**Sharing a non-thread-safe writer:** multiple partitions may call a delegate concurrently. Design writers to match the step's concurrency model.

## 31. Production Workflow for Classification Errors and Skip

First, identify valid routes and the data source used for classification. Use enums or value objects instead of arbitrary strings; classifiers should be pure, deterministic, and make no external service calls. For unsupported routes, explicitly choose fallback, quarantine, skip, or fail per the data contract.

Next, create dedicated exceptions for classification errors and classify delegate exceptions by root cause. Configure skip for droppable record errors, retry for transient infrastructure errors, and let configuration/critical errors fail the step. Set an overall step skip limit and attach a SkipListener to audit skipped items. Ensure ItemStream delegates have their lifecycles registered with the step.

Finally, test the classifier independently, test every route, test unknown routes, test write exceptions, rollback, retry, skip limits, and ItemStream lifecycles. Inspect actual data at each destination and idempotency when delegates are re-invoked. Monitor route counts, retries, skips, and quarantine in production to detect schema drift or write-target failures.

Classification errors and skips are part of routing design, not merely exception configuration. ClassifierCompositeItemWriter selects one delegate per item; classifier errors and delegate errors require separate policies. When routes are stable, exceptions are classified accurately, skips are bounded, and failed items are audited, the job can proceed with valid records while still exposing infrastructure or configuration bugs that need attention.
