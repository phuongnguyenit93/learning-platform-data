# Classifier-Selected Composite Writer

In Spring Batch, ClassifierCompositeItemWriter enables selecting a target writer on a per-item basis. Instead of sending the entire chunk to every delegate, the composite consults a Classifier to determine the appropriate writer for each item and then routes that item to the corresponding delegate.

This approach is useful when a Step reads multiple kinds of records that must be emitted to different destinations: priority versus standard orders, transactions by type, valid records versus quarantined records, or data routed by tenant. The Classifier decides the route; the delegate writer handles writing the data. To configure it properly, you need to understand how the composite groups items by delegate, child writer lifecycles, chunk transactions, and behavior when a delegate fails.

## 1. What Problem Does ClassifierCompositeItemWriter Solve?

Suppose a Step reads all Orders from a source. Each Order has a priority attribute. Priority orders must be written to a dedicated file, while remaining orders are written to a standard file.

You can create two independent writers:

- priorityOrderWriter: writes priority orders.
- standardOrderWriter: writes standard orders.

The Classifier inspects each Order and returns the matching writer. ClassifierCompositeItemWriter coordinates invoking these writers within the same Step.

~~~text
                 Chunk<Order>
          [A, B, C, D, E, F]
                    |
                    v
             Classifier<T>
             /           \
     priority = true    priority = false
           |                 |
           v                 v
   Priority writer     Standard writer
           |                 |
           v                 v
   priority.csv        standard.csv
~~~

The composite does not need to know whether a writer targets a file, a database, or a service. It only needs a classifier that returns an appropriate ItemWriter.

## 2. Distinguishing CompositeItemWriter and ClassifierCompositeItemWriter

The two composites serve different purposes.

| Component | Dispatch Behavior | Example |
|---|---|---|
| CompositeItemWriter | Sends the same chunk to delegates one by one | Write a record to the database and also write an audit file |
| ClassifierCompositeItemWriter | Classifies each item and sends it to the chosen delegate | Priority orders to file A, standard orders to file B |

With CompositeItemWriter, all delegates normally receive the same set of items. With ClassifierCompositeItemWriter, an item is classified to pick one target writer; it is not automatically sent to every writer.

For example, a chunk of 5 items:
- 2 items with priority = true.
- 3 items with priority = false.

ClassifierCompositeItemWriter sends the two priority items to writer A and the remaining three items to writer B. CompositeItemWriter would send all 5 items to writer A and then all 5 items to writer B.

If the requirement is to write one item to multiple destinations, consider CompositeItemWriter or a custom coordinating writer. If the requirement is to choose one write destination based on item content, ClassifierCompositeItemWriter is a better fit.

## 3. Classifier Is the Writer Selection Strategy

Classifier is a strategy that accepts an object and returns a classification result. In this case, the result is an ItemWriter capable of writing the item type being processed.

Conceptually:

~~~java
public interface Classifier<C, T> {
    T classify(C classifiable);
}
~~~

For Order, the classifier takes an Order and returns an ItemWriter<? super Order>:

~~~java
Classifier<Order, ItemWriter<? super Order>> classifier =
        order -> order.isPriority()
                ? priorityWriter
                : standardWriter;
~~~

A classifier should have a clear rule, be easy to test, and remain deterministic throughout a run. Do not let a classifier perform side effects itself such as writing files, updating databases, or making HTTP calls; those actions belong to delegate writers.

A classifier can be based on:
- A field such as transaction type or status.
- An enum or business code.
- Tenant or region.
- Amount threshold or priority level.
- Subtype class when a chunk contains multiple subtypes.
- A result normalized by an ItemProcessor.

## 4. Configuring ClassifierCompositeItemWriter in Java

A common configuration pattern is creating the delegates first, then setting the classifier on ClassifierCompositeItemWriter.

~~~java
@Bean
ClassifierCompositeItemWriter<Order> orderRoutingWriter(
        @Qualifier("priorityOrderWriter")
        ItemWriter<Order> priorityWriter,
        @Qualifier("standardOrderWriter")
        ItemWriter<Order> standardWriter) {

    ClassifierCompositeItemWriter<Order> writer =
            new ClassifierCompositeItemWriter<>();

    writer.setClassifier(order ->
            order.isPriority()
                    ? priorityWriter
                    : standardWriter);

    return writer;
}
~~~

In the example:
- Order is the input item type.
- setClassifier(...) receives the writer selection strategy.
- The classifier returns a delegate based on the priority attribute.
- The composite handles grouping and invoking delegates.

Use @Qualifier when multiple beans implement ItemWriter. Injecting by type alone when multiple candidates exist can cause Spring to fail with NoUniqueBeanDefinitionException.

Exact packages and method signatures must match your Spring Batch version. In Spring Batch 5, ItemWriter takes a Chunk; in older versions, the write signature may take a List.

## 5. Declaring Delegate Writers

Delegates are the writers that actually perform writes. They may share the same item type while differing in resources or storage mechanisms.

Example of two file writers:

~~~java
@Bean
@StepScope
FlatFileItemWriter<Order> priorityOrderWriter(
        @Value("#{jobParameters['priorityOutput']}")
        String outputPath) {

    return new FlatFileItemWriterBuilder<Order>()
            .name("priorityOrderWriter")
            .resource(new FileSystemResource(outputPath))
            .delimited()
            .names("id", "customerId", "amount", "priority")
            .saveState(true)
            .build();
}

@Bean
@StepScope
FlatFileItemWriter<Order> standardOrderWriter(
        @Value("#{jobParameters['standardOutput']}")
        String outputPath) {

    return new FlatFileItemWriterBuilder<Order>()
            .name("standardOrderWriter")
            .resource(new FileSystemResource(outputPath))
            .delimited()
            .names("id", "customerId", "amount", "priority")
            .saveState(true)
            .build();
}
~~~

The two writers have separate state, separate names, and separate output paths. @StepScope enables receiving JobParameters when the Step actually executes. If resources are fixed and writers do not need late binding, another appropriate scope can be used.

Do not share a single writer instance across multiple routes if the writer holds separate state or resources. Each delegate should have a clear lifecycle and output resource.

## 6. Wiring the Composite Writer into a Step

The Step uses ClassifierCompositeItemWriter as its primary writer:

~~~java
@Bean
Step routeOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ClassifierCompositeItemWriter<Order> orderRoutingWriter,
        FlatFileItemWriter<Order> priorityOrderWriter,
        FlatFileItemWriter<Order> standardOrderWriter) {

    return new StepBuilder("routeOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(orderReader)
            .writer(orderRoutingWriter)
            .stream(priorityOrderWriter)
            .stream(standardOrderWriter)
            .build();
}
~~~

In this example, the delegates are FlatFileItemWriters, so they have an ItemStream lifecycle. Register them on the Step via .stream(...) so Spring Batch invokes open, update, and close.

This point is critical: ClassifierCompositeItemWriter is only responsible for dispatching writes per classifier; the composite itself does not replace the lifecycle of stream delegates. If you omit registering ItemStream delegates, file writers may not be opened/closed and their checkpoints may not be saved as expected.

If a delegate is purely a stateless writer that does not implement ItemStream, it does not need to be registered as a stream. Check the actual interfaces implemented by each delegate.

## 7. The Composite Groups Items by Delegate

ClassifierCompositeItemWriter does not necessarily invoke a delegate once per individual item. It classifies items in the chunk, groups them by selected writer, and then calls each writer with its corresponding group of items.

Example:

~~~text
Input chunk:
  A(priority)
  B(standard)
  C(priority)
  D(standard)
  E(priority)

After classification:
  Priority writer: [A, C, E]
  Standard writer: [B, D]

Delegates receive:
  priorityWriter.write([A, C, E])
  standardWriter.write([B, D])
~~~

This grouping allows delegates to continue chunk-based processing, leveraging batch inserts or sequential writes more efficiently than calling write item by item.

Item order within each delegate's group preserves their order of appearance in the chunk. However, do not rely on invocation order across delegates as a business contract. If global ordering across routes is required, design for it explicitly or sort/coordinate before writing.

## 8. How Many Delegates Does an Item Go To?

With a typical classifier, each item is sent to the writer returned by the classifier. If the classifier always returns exactly one delegate, each item has one route.

Example:
- Order A -> priority writer.
- Order B -> standard writer.
- Order C -> priority writer.

If you want one item written to multiple destinations, a classifier composite is not a broadcast mechanism. You can:
- Return a writer adapter that calls multiple child writers.
- Use CompositeItemWriter inside one route.
- Build a dedicated coordinating writer for that rule.

Example adapter for a priority route that writes to both database and audit:

~~~java
@Bean
CompositeItemWriter<Order> priorityAuditWriter(
        ItemWriter<Order> databaseWriter,
        ItemWriter<Order> auditWriter) {

    return new CompositeItemWriterBuilder<Order>()
            .delegates(databaseWriter, auditWriter)
            .build();
}
~~~

The classifier can pick priorityAuditWriter for priority Orders and standardWriter for other Orders. Ensure child delegates with an ItemStream lifecycle are properly registered on the Step if they require open/update/close.

## 9. Classifying by Enum or Business Type

An easy-to-manage rule uses an enum instead of scattered boolean conditions.

~~~java
public enum OrderChannel {
    PRIORITY,
    STANDARD,
    INTERNATIONAL
}
~~~

Classifier:

~~~java
@Bean
ClassifierCompositeItemWriter<Order> orderRoutingWriter(
        ItemWriter<Order> priorityWriter,
        ItemWriter<Order> standardWriter,
        ItemWriter<Order> internationalWriter) {

    Map<OrderChannel, ItemWriter<? super Order>> writers =
            Map.of(
                    OrderChannel.PRIORITY, priorityWriter,
                    OrderChannel.STANDARD, standardWriter,
                    OrderChannel.INTERNATIONAL, internationalWriter);

    ClassifierCompositeItemWriter<Order> composite =
            new ClassifierCompositeItemWriter<>();

    composite.setClassifier(order -> {
        ItemWriter<? super Order> writer =
                writers.get(order.getChannel());

        if (writer == null) {
            throw new IllegalArgumentException(
                    "Unsupported order channel: " + order.getChannel());
        }

        return writer;
    });

    return composite;
}
~~~

Using a map fits when routes are fixed and configured at application startup. If a classifier has many branches or needs independent testing, extract it into its own class rather than leaving an overly long lambda in bean configuration.

Do not return null when no route exists. Explicitly define a default writer, a reject writer, or throw an exception so the Step fails. A forgotten route could otherwise leave items unwritten.

## 10. Classifying by Multiple Conditions

A classifier can combine multiple attributes. For example, classifying by tenant first, then by transaction type:

~~~java
classifier.setClassifier(item -> {
    if (item.isRejected()) {
        return rejectedWriter;
    }

    if (item.getAmount().compareTo(bigAmountLimit) >= 0) {
        return highValueWriter;
    }

    if (item.isInternational()) {
        return internationalWriter;
    }

    return standardWriter;
});
~~~

Condition order is part of the business rule. If an item matches multiple conditions, the first branch wins. Write clear precedence and test overlapping cases.

If classification logic depends on external data, such as looking up a configuration table or calling a service, avoid making separate network/database queries per item when possible. Load rules or mappings once, cache safely per Job/Step, or resolve routes in a processor.

Classifiers should be fast and deterministic for the same item within the same run. If rules change mid-Job, an item might be routed differently during retry or restart.

## 11. Classifying by Subtype

Some Jobs handle multiple subtypes in the same stream. You can use a classifier based on runtime type:

~~~java
Classifier<BaseEvent, ItemWriter<? super BaseEvent>> eventClassifier =
        event -> {
            if (event instanceof OrderCreatedEvent) {
                return orderEventWriter;
            }
            if (event instanceof PaymentReceivedEvent) {
                return paymentEventWriter;
            }
            throw new IllegalArgumentException(
                    "Unsupported event type: " + event.getClass().getName());
        };
~~~

Returned writers must accept BaseEvent or be wrapped in an adapter with explicit type checking and conversion. An ItemWriter<OrderCreatedEvent> cannot automatically accept Chunk<BaseEvent> simply because every OrderCreatedEvent is a BaseEvent. Do not use unchecked casts to bypass generic type safety.

If routes have different schemas, a processor can convert each input into a shared envelope containing the route and normalized payload, and delegates can read that envelope. Use this design only when needed; do not overcomplicate the model if delegates can share the same item type.

## 12. Using ItemProcessor to Normalize Routes

A classifier can classify domain objects directly, yet in many systems an ItemProcessor is the right place to compute routes and validate data.

Example:

~~~java
public record RoutedOrder(
        Order order,
        OrderChannel channel) {
}

@Bean
ItemProcessor<Order, RoutedOrder> routeOrderProcessor() {
    return order -> {
        OrderChannel channel =
                order.isPriority()
                        ? OrderChannel.PRIORITY
                        : OrderChannel.STANDARD;

        return new RoutedOrder(order, channel);
    };
}
~~~

The composite writer then classifies RoutedOrder by channel. Delegates can accept RoutedOrder or use adapters that extract Order before writing.

Advantages:
- Business rules can be tested independently.
- Chosen routes can be logged.
- Invalid items can be rejected before the writer.
- Retries do not recompute from mutable configuration if the route is already pinned on the item.

If a processor returns null to filter an item, that item never reaches the writer and the classifier is not called for it. Distinguish intentional filtering from missing routes.

## 13. Classifiers Must Remain Stable Across Retries and Restarts

A Job can retry a chunk or restart after a failure. If a classifier picks different routes across repeated attempts for the same item, data can end up written in multiple places or missing where expected.

Risk examples:
- Routing based on exchange rates or configuration state that changes over time.
- Routing based on an external service that returns different results on retry.
- Routing based on current wall-clock time.
- Routing based on a mutable field altered by a processor or delegate.

To maintain consistency:
- Base routing on stable input data or finalized business keys.
- If routing depends on configuration, pin a version/configuration ID for the Job.
- Do not mutate classification fields after an item has been routed.
- Keep JobParameters and data sources identical on restart.
- If routes can change per business logic, persist the chosen route in durable data or staging.

The classifier does not record route history in JobRepository. If you need an audit trail of where each item went, record routes in an audit table/file or domain metadata.

## 14. Chunk Transactions When Multiple Delegates Are Invoked

ClassifierCompositeItemWriter runs during the write phase of a chunk. Delegates are invoked within the scope of the same chunk processing pass, and JDBC writers using the same transaction manager/DataSource can join that chunk transaction.

Example with two delegates writing two tables in the same database:

~~~text
Chunk transaction begins
    |
    +--> priorityWriter.write(priorityItems)
    |
    +--> standardWriter.write(standardItems)
    |
    v
Chunk transaction commits
~~~

If a delegate throws an exception, the Step handles the chunk according to its rollback/retry/skip policy. Database changes participating in the same transaction can be rolled back.

However:
- Two delegates using two different DataSources do not automatically share an atomic transaction.
- Filesystems, HTTP services, and message brokers do not automatically join JDBC transactions.
- One delegate may already have produced external side effects before a later delegate fails.

Therefore, a composite writer is not a distributed transaction coordinator. If consistency across multiple systems is required, consider an outbox, staging, idempotent consumers, post-commit publishing, or an explicitly supported distributed transaction mechanism.

## 15. Failures Across Delegates and Partial Writes

Suppose a chunk has items for writer A and writer B. The composite calls A successfully and then B throws an exception.

The outcome depends on resource types:
- If A and B write to the same database in the same transaction, rollback can undo both.
- If A writes a file and then B fails writing to the database, the file may already contain data even though the chunk rolled back.
- If A calls HTTP successfully and then B fails, the remote side effect is not automatically retracted.
- If A and B use two independent database transactions, one may commit while the other rolls back.

Do not assume the composite automatically undoes earlier delegates. For external side effects, design:
- Idempotency keys per JobInstance/item ID.
- Writing to staging and publishing after Job completion.
- Outbox tables inside the database transaction.
- Controlled reconciliation or compensation.
- Safe retries for each delegate.

If a route is unwritable, you should normally let the chunk fail or move items to reject/quarantine per business rules. Do not silently ignore exceptions, as that can leave missing data while the Job reports COMPLETED.

## 16. Skip and Retry When a Delegate Writer Fails

ClassifierCompositeItemWriter does not define retry or skip policies itself. Those policies are configured on the Step.

Example:

~~~java
return new StepBuilder("routeOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .writer(orderRoutingWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skipLimit(20)
        .build();
~~~

This is a general example; fault-tolerance configuration APIs may vary by Spring Batch version. Only retry recoverable errors, such as transient connection errors or deadlocks per application policy. Only skip allowed business errors and record excluded items.

If a delegate writer already produced non-transactional side effects and then threw an exception, a retry may invoke the writer again and create duplicate side effects. Idempotency or detection of already-written items is required.

## 17. ItemStream Delegates Must Be Registered Separately

ClassifierCompositeItemWriter focuses on classifying and calling writers. If delegates are ItemStreamWriter or ItemStream, ensure the Step manages each delegate's lifecycle.

Examples:
- FlatFileItemWriter needs to open files, update checkpoints, and close files.
- Stateful custom writers need to restore state in open.
- Resource-using writers need timely closing.

Register each delegate on the Step:

~~~java
return new StepBuilder("routeOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .writer(orderRoutingWriter)
        .stream(priorityOrderWriter)
        .stream(standardOrderWriter)
        .build();
~~~

If a delegate is a CompositeItemWriter containing child streams, verify lifecycle propagation of that composite and register streams per the framework version's contract. Do not assume that merely invoking a writer through a wrapper guarantees every delegate automatically receives open/update/close.

Keep stream names and state keys stable. On restart, each writer must restore its own resource and checkpoint properly.

## 18. Step-Scoped Writers and Late Binding

Delegate writers may need JobParameters or Step ExecutionContext, such as output paths by date, tenant, or JobInstance. In that case, declare the delegate with @StepScope.

Example:

~~~java
@Bean
@StepScope
FlatFileItemWriter<Order> priorityOrderWriter(
        @Value("#{jobParameters['priorityOutput']}")
        String outputPath) {

    return new FlatFileItemWriterBuilder<Order>()
            .name("priorityOrderWriter")
            .resource(new FileSystemResource(outputPath))
            .delimited()
            .names("id", "customerId", "amount")
            .saveState(true)
            .build();
}
~~~

The composite can be created in the ApplicationContext with proxy delegates. Actual target writers are only instantiated when the Step scope becomes active and JobParameters are available.

Do not call methods on target writers directly before the Step runs. Let Spring manage proxies and resource lifecycles.

## 19. Routing to a Reject Writer

A common pattern is separating valid and invalid records:

~~~java
composite.setClassifier(item ->
        item.isValid()
                ? acceptedWriter
                : rejectedWriter);
~~~

The reject writer can write faulty records along with reasons to a quarantine file or inspection table. This is helpful when business rules want valid data processed while still preserving rejected records.

Distinguish:
- Business-invalid items: can be routed to a reject writer if the Job is allowed to continue.
- Writer infrastructure failures: such as disk full or database unavailable; normally must fail the chunk.
- Unexpected classifier failures: code bugs or missing routes; must fail clearly.

Do not turn every exception into a rejected item. If the writer fails to write the reject file, the Job must also reflect failure so faulty data is not lost.

## 20. Routing by Tenant or Partition

A classifier can pick writers by tenant, though be careful with route count. If each tenant has a dedicated writer, the writer map can grow large and open resource count scales with tenants.

For a small, fixed number of routes, a tenant -> writer map can make sense. For thousands of tenants or dynamic routes, consider:
- Writing to one table with a tenant_id column.
- Writing to a shared resource with a partition key.
- Using a partitioned Step so each worker handles one tenant or tenant group.
- Using a writer adapter that manages resources under a well-designed lifecycle.

ClassifierCompositeItemWriter does not create separate StepExecutions per route. It simply picks a delegate within the current Step. If each tenant needs isolated transactions, restarts, concurrency, or resources, partitioning may fit better than routing inside one writer.

## 21. Write Order and Stability

Because the composite groups items by delegate before invoking writers, overall processing order across routes can differ from original input order.

Example input:

~~~text
A -> writer 1
B -> writer 2
C -> writer 1
D -> writer 2
~~~

Writer 1 receives [A, C]; writer 2 receives [B, D]. Do not assume output side effects will interleave in A, B, C, D order.

If global ordering is a business requirement:
- Use a single writer processing each item in order.
- Build an adapter that writes sequentially to the right target per item.
- Split data into separate streams and coordinate in a downstream step.
- Store sequence numbers so consumers can reconstruct order.

Within each delegate, per-chunk item order can be preserved, though order across chunks also depends on how the Step reads and commits. Do not use routing to guarantee cross-system ordering without an explicit design.

## 22. Thread Safety and Concurrency

In a multi-threaded Step, the same ClassifierCompositeItemWriter or delegates may be invoked concurrently depending on the execution model. The classifier should be thread-safe and hold no unsynchronized mutable state.

Checklist:
- Are delegate writers thread-safe?
- Do writers hold a shared file stream?
- Can two threads write to the same resource simultaneously?
- Does the classifier use a mutable map or counter?
- Are routes determined independently per item?
- Are delegate checkpoints updated safely?

@StepScope creates a target per StepExecution, not a separate writer per thread within the same StepExecution. If delegates are not thread-safe, use partitioning with separate resources or an explicitly designed serialization mechanism.

In partitioning, each worker StepExecution should receive its own delegate/resource keyed by partition. Do not let multiple workers write to the same file or share mutable writer state without coordination.

## 23. Logging and Metrics per Route

When you need visibility into routed data, record metrics per delegate:
- Number of items sent to each writer.
- Number of delegate write calls.
- Write duration per route.
- Error and retry counts.
- Rejected item counts.
- JobExecution ID and Step name.

You can wrap delegates with writer adapters to count items before/after writing. Ensure counters do not alter transaction semantics or introduce race conditions in a multi-threaded Step.

Do not log full payloads. Use permitted business keys or IDs to trace items. Metric tags should have a bounded number of routes; avoid very high-cardinality tags like item IDs or tenant IDs.

## 24. Testing ClassifierCompositeItemWriter

Test the classifier independently as well as integration with the Step.

### Unit Testing the Classifier

Verify:
- Priority items select the priority writer.
- Standard items select the standard writer.
- Other enums or item types select the right routes.
- Null values or unsupported routes are handled explicitly.
- Precedence rules among multiple conditions match business logic.

### Unit Testing the Composite

Use fake/mock writers to verify:
- Every item is classified properly.
- Delegates only receive items belonging to their route.
- Items within each group preserve expected order.
- Empty chunks cause no side effects.
- Delegate errors propagate to the Step.
- No items are silently dropped when the classifier finds no route.

### Integration Testing the Step

| Scenario | What to Verify |
|---|---|
| Chunk has only one route | Only the matching delegate receives items |
| Chunk has multiple routes | Delegates receive their respective item groups |
| One delegate fails | Chunk/Step reflects failure per policy |
| Two delegates write in the same DB transaction | Proper rollback when one delegate fails |
| Delegate is an ItemStream | open/update/close are called |
| Restart | Each delegate restores its checkpoint accurately |
| Output files | No duplicate writes or lost items after restart |
| Multi-threaded Step | Delegates and classifier are concurrency-safe |
| Invalid route | Job fails or rejects per defined rule |

Do not check only write invocation counts. Verify the actual data written by each delegate and the final state in JobRepository.

## 25. Common Mistakes

**Using CompositeItemWriter when you only want to pick one target.** Every delegate receives the same chunk and data gets written multiple times.

**Classifier returning null.** No valid writer exists for the item; define a default/reject writer or fail explicitly.

**Injecting multiple ItemWriters without Qualifiers.** Spring may fail to resolve a unique bean.

**Assuming every delegate receives the entire chunk.** Each delegate only receives the group of items classified for it.

**Assuming order across routes is preserved.** The composite groups by writer, so global side-effect ordering is not guaranteed.

**Forgetting to register ItemStream delegates.** File writers or stateful writers miss lifecycle callbacks.

**Multiple delegates writing to the same file.** Can cause resource contention or corrupted output.

**Classifier using rules that change across retries.** The same item may go to a different route upon reprocessing.

**Retrying non-idempotent external side effects.** Items may be written/sent twice.

**Sharing non-thread-safe writers.** Multi-threaded Steps can trigger race conditions.

**Using tenant routing instead of partitioning when isolation is needed.** Routes still share one StepExecution and lack independent lifecycles.

**Assuming multiple delegates form a distributed transaction.** The composite only dispatches calls; it does not make external systems commit atomically together.

## 26. Workflow for Implementing a Classifier-Selected Composite Writer

When you need to route items to different writers, follow these steps:

1. Define routing rules and the number of supported targets.
2. Choose ClassifierCompositeItemWriter if each item needs one delegate.
3. Use CompositeItemWriter if the same item must be sent to multiple delegates.
4. Create delegate writers accepting the appropriate item type or write strongly typed adapters.
5. Build a pure, deterministic classifier with a branch for invalid routes.
6. Configure ClassifierCompositeItemWriter with setClassifier.
7. Attach the composite to the Step's writer(...).
8. Register ItemStream delegates separately with stream(...) when needed.
9. Define transactions and idempotency for delegates writing to multiple resources.
10. Keep rules, output paths, and checkpoints stable across retries/restarts.
11. Check thread safety if the Step runs concurrently; consider partitioning when per-route isolation is needed.
12. Test routing, item grouping, exceptions, rollbacks, restarts, and actual output data.

ClassifierCompositeItemWriter separates the routing decision from the write operation. The classifier picks a writer per item; the composite groups items by delegate and invokes the writers; delegates manage resources and persistence. When classification rules are stable, delegate lifecycles are fully registered, and transactions/side effects are designed properly, a Step can coordinate multiple write targets while keeping Spring Batch's observability and restartability.

