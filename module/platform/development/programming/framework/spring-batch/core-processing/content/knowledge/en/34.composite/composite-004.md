# CompositeItemWriter in Spring Batch

CompositeItemWriter is an aggregating writer in Spring Batch. It receives a chunk from a step and forwards that same chunk sequentially to multiple ItemWriter delegates. This approach fits when a processed item must be written to multiple destinations, such as saving business data to a database, exporting a report file, and recording an audit entry.

The key characteristic of CompositeItemWriter is fan-out: every delegate receives the entire chunk in the configured order. It does not split items conditionally, does not transform items, and does not create a distributed transaction across systems. Whether writes are atomic depends on the transaction manager and each delegate's ability to participate in transactions.

## 1. What Problem Does CompositeItemWriter Solve?

A chunk-oriented step typically has one ItemWriter. In practice, however, a single processing pass may require multiple outputs:

- Writing normalized orders to a business table.
- Writing a copy of the data to an audit table.
- Exporting a CSV file for a downstream system.
- Updating a statistics or import status table.
- Sending data to an auxiliary system.

If a processor performs these writes directly, the processor produces side effects before the step reaches transaction commit. That makes retries, rollbacks, and skips harder to predict. A cleaner organization is to let the processor produce the output item and let the writer handle persisting it.

CompositeItemWriter allows combining multiple writers into a single writer registered on the step:

~~~text
Reader
  |
  v
Processor
  |
  v
Chunk<Order>
  |
  v
CompositeItemWriter
  |
  +----> DatabaseWriter
  |
  +----> AuditWriter
  |
  +----> FileWriter
~~~

Each delegate receives the same chunk. If a chunk contains 100 orders, DatabaseWriter, AuditWriter, and FileWriter are all invoked with those 100 orders.

## 2. How CompositeItemWriter Differs from a Routing Writer

Do not confuse a composite writer with a writer that chooses one delegate per item:

| Component | How It Works | When to Use |
| --- | --- | --- |
| CompositeItemWriter | Sends the entire chunk to every delegate in order | One item needs to be written to multiple targets |
| ClassifierCompositeItemWriter | Uses a classifier to choose a writer for each item | Each item only needs to go to one target determined by type/condition |
| Single ItemWriter | Writes the chunk to one target | Only one output exists |

For example, if an order must be both saved to the database and exported to a file, CompositeItemWriter fits. If DOMESTIC orders must go to writer A while INTERNATIONAL orders go to writer B, ClassifierCompositeItemWriter is usually used.

CompositeItemWriter does not filter items. If a chunk contains orders of different types, all delegates still receive the entire chunk.

## 3. How CompositeItemWriter Hands Off the Chunk

Conceptually, the composite writer's behavior looks like this:

~~~java
for (ItemWriter<? super T> delegate : delegates) {
    delegate.write(chunk);
}
~~~

Delegates are invoked sequentially in declared order. The first delegate finishes before the second delegate starts. If one delegate throws an exception, the write call stops at that delegate and the exception propagates back to the step; subsequent delegates are not called in that attempt.

Order example:

~~~text
Delegates:
  1. databaseWriter
  2. auditWriter
  3. fileWriter

Call write(chunk):
  databaseWriter.write(chunk) -> succeeded
  auditWriter.write(chunk)    -> succeeded
  fileWriter.write(chunk)     -> exception

Result:
  Step receives exception from writer
  Chunk transaction is handled per rollback policy
  fileWriter did not complete
~~~

Delegate order therefore matters. Configure it in an order that is easy to understand and matches dependencies between outputs. However, call order does not guarantee commit order across independent systems.

## 4. Configuring with CompositeItemWriterBuilder

In Spring Batch 5, you can build a composite writer using CompositeItemWriterBuilder:

~~~java
@Bean
CompositeItemWriter<Order> orderCompositeWriter(
        ItemWriter<Order> databaseOrderWriter,
        ItemWriter<Order> auditOrderWriter) {

    return new CompositeItemWriterBuilder<Order>()
        .delegates(List.of(
            databaseOrderWriter,
            auditOrderWriter
        ))
        .build();
}
~~~

Then register the composite writer on the step:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        CompositeItemWriter<Order> orderCompositeWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderCompositeWriter)
        .build();
}
~~~

The step only needs to know about one ItemWriter, while that bean coordinates the delegate writers. Each delegate can still be declared as a separate bean for reuse or independent testing.

Examples in this article use Spring Batch 5's chunk-based API, where ItemWriter.write receives a Chunk. Legacy Spring Batch 4 projects may use the write(List<? extends T>) signature; use the API matching your running version.

## 5. Database Writer and Audit Writer Example

One delegate can write order data using JdbcBatchItemWriter:

~~~java
@Bean
JdbcBatchItemWriter<Order> databaseOrderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
        .dataSource(dataSource)
        .sql("""
            insert into imported_order
                (source_order_id, customer_id, total, status)
            values
                (:sourceOrderId, :customerId, :total, :status)
            """)
        .beanMapped()
        .assertUpdates(true)
        .build();
}
~~~

The second delegate writes audit records:

~~~java
@Bean
JdbcBatchItemWriter<Order> auditOrderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
        .dataSource(dataSource)
        .sql("""
            insert into order_import_audit
                (source_order_id, event_type, imported_at)
            values
                (:sourceOrderId, 'IMPORTED', :importedAt)
            """)
        .beanMapped()
        .assertUpdates(true)
        .build();
}
~~~

Composite writer:

~~~java
@Bean
CompositeItemWriter<Order> orderCompositeWriter(
        JdbcBatchItemWriter<Order> databaseOrderWriter,
        JdbcBatchItemWriter<Order> auditOrderWriter) {

    return new CompositeItemWriterBuilder<Order>()
        .delegates(List.of(databaseOrderWriter, auditOrderWriter))
        .build();
}
~~~

Both delegates receive the same orders produced by the processor. If both writers use the same datasource and the step's transaction manager, the write statements can join the same chunk transaction. When one delegate fails before commit, the transaction can roll back database changes made within the chunk.

This does not mean every database writer in every configuration is automatically atomic. Verify they use the right datasource, transaction manager, and transaction-bound connections.

## 6. Combining a Database Writer with a File Writer

A common scenario is writing data to a database while also generating a file for a downstream system:

~~~java
@Bean
FlatFileItemWriter<Order> orderFileWriter(
        @Value("#{jobParameters['outputFile']}") Resource outputFile) {

    return new FlatFileItemWriterBuilder<Order>()
        .name("orderFileWriter")
        .resource(outputFile)
        .lineAggregator(order ->
            order.sourceOrderId() + "," +
            order.customerId() + "," +
            order.total()
        )
        .headerCallback(writer ->
            writer.write("sourceOrderId,customerId,total"))
        .shouldDeleteIfExists(true)
        .build();
}
~~~

Combining the file writer with the database writer:

~~~java
@Bean
CompositeItemWriter<Order> orderCompositeWriter(
        ItemWriter<Order> databaseOrderWriter,
        ItemWriter<Order> orderFileWriter) {

    return new CompositeItemWriterBuilder<Order>()
        .delegates(List.of(databaseOrderWriter, orderFileWriter))
        .build();
}
~~~

This is a configuration example; in production you must clarify whether the file is a temporary artifact, final output file, or staging file awaiting publish. The filesystem typically does not participate in the same database transaction. FlatFileItemWriter has its own transaction/lifecycle support mechanisms, but you should not infer that database and file writes on any filesystem can roll back atomically like a database transaction.

A safer design may write a staging file per execution, complete the step, and only then publish/rename the file in a final step. If the job fails, the staging file can be kept for restart or cleaned up under a retention policy.

## 7. Which Delegates Receive the Items?

Every delegate receives the entire input chunk of the composite writer. The composite writer does not make separate copies per delegate and does not convert items automatically.

Example:

~~~java
List<Order> orders = List.of(orderA, orderB, orderC);
compositeWriter.write(new Chunk<>(orders));
~~~

Result:

- databaseWriter receives orderA, orderB, and orderC.
- auditWriter receives orderA, orderB, and orderC.
- fileWriter receives orderA, orderB, and orderC.

If a delegate only needs a subset of items, you need an appropriate filtering/routing writer or pipeline changes before reaching the composite writer. Do not expect the composite writer to filter by attributes automatically.

Because delegates may receive the exact same object instances, avoid mutating mutable items inside write. If the first delegate modifies an order and the second delegate receives the modified order, the outcome becomes order-dependent. Use immutable items, or build separate representations in processors or specialized writers.

## 8. Delegate Order and Dependencies Between Outputs

The delegate list is configured in execution order. For example:

~~~java
.delegates(List.of(
    databaseOrderWriter,
    auditOrderWriter,
    orderFileWriter
))
~~~

This order can be useful if auditing needs to reference data written to the database or a file should be written after normalized data is persisted. However, if a later delegate needs a database-generated ID, remember that the composite writer passes the same current items; it does not reload items after the first delegate writes.

If you need generated keys or outputs from an earlier delegate to form inputs for a later delegate, perform that in a processor/service before the writer, or use a custom coordinating writer with an explicit contract. Do not rely on the first delegate mutating an object to implicitly pass data to the next delegate.

If the second output can only be generated after the first output has committed, the two operations are no longer a single composite writer call within a simple transaction. Consider a subsequent step, events/outbox, or an explicitly stateful workflow.

## 9. CompositeItemWriter and Chunk Transactions

CompositeItemWriter invokes delegates while the step is writing a chunk. It does not open a new transaction per delegate. Transactions are typically controlled by the step and the PlatformTransactionManager passed to the chunk configuration.

For delegates sharing a transaction:

~~~text
BEGIN CHUNK TRANSACTION
  databaseWriter.write(chunk)
  auditWriter.write(chunk)
  fileWriter.write(chunk)
COMMIT
~~~

If a delegate throws an exception before commit, the step handles the transaction according to its rollback policy. Operations participating in that transaction can be rolled back.

However, rollback only affects resources participating in that transaction. For example:

- Two JDBC writers sharing a datasource/transaction manager can roll back together.
- Calling an HTTP API from a writer does not automatically roll back requests already processed by the remote service.
- Writing to the filesystem is not inherently undone by a database transaction.
- Writing to another datasource is not automatically atomic with the step's datasource.

Thus, the composite writer helps organize multiple outputs, but it is not a distributed transaction coordinator.

## 10. What Happens If the Second Delegate Fails?

Suppose the composite has two delegates:

1. databaseWriter writes successfully.
2. externalWriter sends data to an external system but times out.

The step receives the exception from externalWriter. If the database write is still inside an uncommitted transaction, the database can roll back. However, the external system may already have received and processed the request even though the client did not receive a response.

When the chunk is retried or the job restarts, the same items may be sent again. The external system needs an idempotency key or deduplication mechanism.

A timeout does not prove the remote operation did not happen. It may have succeeded on the server with only the response lost. Resending without idempotency can duplicate data or side effects.

## 11. Retry, Rollback, and Idempotency

Writers can be invoked multiple times for the same chunk due to retries, rollbacks, or restarts. The composite writer does not record that one delegate finished before another delegate failed.

Example:

~~~text
Attempt 1:
  databaseWriter -> succeeded in transaction
  externalWriter -> timeout
  transaction rollback

Attempt 2:
  databaseWriter -> called again
  externalWriter -> called again
~~~

If the database transaction rolls back properly, the first database write has no lasting effect. However, the external operation may already have occurred and must be protected against duplicates.

Measures:

- Use a stable business key or operation ID per item/event.
- Design database writers as upserts or inserts with unique constraints where appropriate.
- Require downstream APIs to support idempotency keys.
- Write outbox events in the same database transaction as business data.
- Have a separate publisher send outbox events and mark status upon acknowledgment.
- Record delivery status so retries can be controlled.

Idempotency must be designed into each destination. Having one writer in the composite run earlier does not guarantee the next delegate runs only once.

## 12. Using Transactional Outbox Instead of Direct Remote Calls

If a chunk needs to both save to the database and emit events, the transactional outbox pattern is usually more reliable than calling HTTP directly inside a composite writer:

~~~text
Chunk transaction
  |
  +--> insert business rows
  |
  +--> insert outbox events
  |
  +--> COMMIT

Separate publisher
  |
  +--> read pending outbox rows
  +--> send event with stable event ID
  +--> mark event published
~~~

Business rows and outbox rows are written in the same database transaction. If the chunk rolls back, both roll back. The publisher handles sending events with its own retry/idempotency mechanism.

You can place the database writer and outbox writer inside CompositeItemWriter if both use the same transaction manager and the same transaction-bound datasource. You can also use a custom writer to write both under a single business contract. What must be ensured is that both operations genuinely participate in the same transaction.

An outbox does not guarantee a remote consumer receives events exactly once. Consumers should still deduplicate by event ID because message brokers generally provide at-least-once semantics.

## 13. ItemStream Lifecycle of Delegates

Some writers require lifecycle callbacks:

- open(ExecutionContext): open files, cursors, or resources.
- update(ExecutionContext): save state/checkpoints.
- close(): flush and release resources.

CompositeItemWriter implements ItemStream and can forward lifecycle callbacks to delegates implementing ItemStream. By default, it manages stream delegates; the ignoreItemStream option can change this behavior.

Example:

~~~java
CompositeItemWriter<Order> writer =
    new CompositeItemWriterBuilder<Order>()
        .delegates(List.of(databaseWriter, flatFileWriter))
        .build();
~~~

When the composite writer is registered on a step, Spring Batch invokes the composite's lifecycle and the composite forwards to stream delegates per configuration. Thus, FlatFileItemWriter can open the file before writing and close/flush when the step ends.

Do not set ignoreItemStream(true) if delegates need open/update/close and nothing else manages their lifecycle.

## 14. When to Use ignoreItemStream?

The builder provides the ignoreItemStream(boolean) option. When enabled, the composite writer skips forwarding ItemStream lifecycle callbacks to delegates.

~~~java
CompositeItemWriter<Order> writer =
    new CompositeItemWriterBuilder<Order>()
        .delegates(List.of(databaseWriter, flatFileWriter))
        .ignoreItemStream(true)
        .build();
~~~

Only use this when delegate lifecycles are managed separately and explicitly—for instance, when stream delegates are already registered directly with the step via .stream(delegate), or when delegates do not need a lifecycle.

If a delegate needs open() to open a file but the composite ignores streams and the step does not register the delegate separately, the writer may fail on write or fail to flush/close resources properly.

Another option is having a wrapper/custom writer implement ItemStreamWriter and forward callbacks. When managing lifecycle manually, ensure each delegate is opened/closed in the exact scope and cleanup occurs even when the step fails.

## 15. Registering Streams When Delegates Are Inside Wrappers

Not every wrapper exposes ItemStream. For example, an adapter might only implement ItemWriter while holding FlatFileItemWriter in a field. Spring Batch may only see the adapter, not the inner stream delegate.

If the composite is configured to ignore streams, or a delegate is buried inside a wrapper unrecognized by the composite, register the stream delegate with the step:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
    .<Order, Order>chunk(100, transactionManager)
    .reader(reader)
    .writer(compositeWriter)
    .stream(flatFileWriter)
    .build();
~~~

Avoid registering the same stream through multiple paths if that causes lifecycle callbacks to fire twice. Pick one clear owner: the composite forwards lifecycle, the step registers the delegate independently, or the wrapper forwards it itself.

## 16. Error Handling in Delegates and Skip Policies

If a delegate throws an exception, the exception propagates to the step. The step applies rollback, retry, or skip according to the fault-tolerance configuration.

Example:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
    .<OrderInput, Order>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(orderCompositeWriter)
    .faultTolerant()
    .retry(TransientDataAccessException.class)
    .retryLimit(3)
    .skip(InvalidOrderException.class)
    .skipLimit(10)
    .build();
~~~

Only configure retry for transient errors that can self-heal, such as certain temporary database/network failures. Do not retry deterministic mapping errors or validation errors. Also consider which delegate throws the exception; if the same exception type is used for both transient and business errors, the policy may apply too broadly.

If an earlier delegate already caused external side effects before a later delegate failed, chunk-level skipping or retrying can repeat those side effects. Use idempotency or split external operations into separate steps with durable state.

## 17. CompositeItemWriter Does Not Make All Outputs Atomic

A design mistake is assuming that invoking multiple delegates in one CompositeItemWriter means all destinations commit or roll back together. That is only true if the resources genuinely participate in the same transaction coordinator.

Example:

| Delegate | Resource | Can it roll back with the JDBC transaction? |
| --- | --- | --- |
| JdbcBatchItemWriter same datasource | Transaction-bound database | Usually yes |
| JdbcBatchItemWriter different datasource | Separate transaction | Not automatically |
| FlatFileItemWriter | Filesystem | Not inherently atomic with DB |
| HTTP writer | Remote service | No |
| Message producer | Broker | Only with properly configured transaction integration; not automatic |

If multiple resources must commit together, choose an appropriate distributed transaction mechanism or design a workflow/outbox/saga. Do not infer guarantees merely from delegate ordering.

## 18. Writer Delegates Should Share the Item Type

CompositeItemWriter<T> takes a list of delegates compatible with item type T. Delegates can accept ItemWriter<? super T>, allowing a writer to accept a supertype of the item.

Example:

~~~java
ItemWriter<Auditable> auditWriter = ...;
ItemWriter<Order> orderWriter = ...;

CompositeItemWriter<Order> composite =
    new CompositeItemWriterBuilder<Order>()
        .delegates(List.of(orderWriter, auditWriter))
        .build();
~~~

Order can implement Auditable, so the audit writer receives orders. However, if a delegate needs a completely different output type, convert it beforehand in a processor or write a strongly typed adapter. Do not cast raw types to get past the compiler; that can cause ClassCastException at runtime.

## 19. Using an Adapter When a Target Needs a Different Representation

A database writer might need Order, while a file writer needs OrderCsvRow. You cannot place two writers with unrelated input types into the same CompositeItemWriter<Order> if the file writer only accepts OrderCsvRow.

You can create an adapter:

~~~java
public class OrderCsvWriter implements ItemWriter<Order> {

    private final ItemWriter<OrderCsvRow> delegate;

    public OrderCsvWriter(ItemWriter<OrderCsvRow> delegate) {
        this.delegate = delegate;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) throws Exception {
        List<OrderCsvRow> rows = chunk.getItems().stream()
            .map(OrderCsvRow::from)
            .toList();
        delegate.write(new Chunk<>(rows));
    }
}
~~~

The composite writer still receives Order; the adapter converts each order into the appropriate representation and calls the file writer delegate. If the inner delegate implements ItemStream, the adapter must also forward lifecycle callbacks or register the stream delegate separately with the step.

Another option is for the processor to produce an output envelope containing the needed representations:

~~~java
public record OrderWriteModel(
    Order order,
    OrderCsvRow csvRow
) {}
~~~

Writer adapters receive the same OrderWriteModel and select the portion of data to write. This keeps transformations in the processor and clarifies the output contract.

## 20. Composite Writer and Side-Effect Order

The composite writer calls delegates sequentially, yet does not guarantee an earlier delegate's side effect is durable before the next delegate runs. If the database writer participates in a transaction, SQL statements may still be uncommitted when the file writer is called.

Example:

~~~text
BEGIN DB TRANSACTION
  databaseWriter -> INSERT order (uncommitted)
  fileWriter     -> write CSV line
COMMIT DB
~~~

If DB commit fails after the file has been written, the file may contain orders that were never persisted in the database. Reversing delegate order does not solve the underlying problem; it only changes which side effect can happen first.

For consistency between DB and file, consider:

- Writing a staging file and publishing it after the database step succeeds.
- Generating the file from committed database data in a subsequent step.
- Recording a manifest/publish status so retries are safe.
- Naming artifacts by JobExecution or batch ID.
- Using cleanup/reconciliation for leftover temporary files after failures.

## 21. Multi-Threaded Steps and Delegate Thread Safety

CompositeItemWriter invokes delegates sequentially within a single write() call, but that does not mean the writer is safe when multiple threads call the composite concurrently.

In a multi-threaded step, partitioning, or executor configuration, determine whether multiple threads share one writer instance or each worker has its own instance. If sharing an instance, every delegate may also be called concurrently from different threads.

Check the delegates:

- Are there mutable per-chunk/item fields?
- Do they write to the same file or output stream?
- Do they obtain JDBC resources per invocation or hold connections/cursors in fields?
- Do they support concurrent writes?
- Does write order need synchronization?

CompositeItemWriter does not create locks, clone delegates, or serialize concurrent calls. If a delegate is not thread-safe, use partition-specific writers, properly synchronized writers, or change the step model. SynchronizedItemStreamWriter can serialize writes for some writers, though you still must check open/update/close and delegate semantics.

Do not share a single FlatFileItemWriter across multiple parallel workers without a design guaranteeing ordering and safety. You can use per-partition files and merge them in a later step.

## 22. Do Not Use CompositeItemWriter to Replace a Multi-Step Flow

Composite writer fits when outputs belong to the same chunk and must be invoked in the same write phase. If one output must run after another output has completed/committed, use multiple steps in the job flow.

Example:

~~~text
ImportStep
  Reader -> Processor -> DatabaseWriter
       |
       v
ExportStep
  DatabaseReader -> FileWriter
       |
       v
PublishStep
  Publish artifact / notify downstream
~~~

Splitting steps allows:

- Clear transaction boundaries per output.
- Independent restart of each step.
- Separate retry or skip policies.
- Re-running export without re-importing the source.
- Separate status and metrics tracking.

In return, you must manage step dependencies and committed data. Do not pack all writers into one composite merely to reduce the number of steps in a job.

## 23. Testing Delegate Order and Invocation Counts

Unit tests can use mock writers to verify all delegates receive the chunk and are called in order:

~~~java
@Test
void writesChunkToEveryDelegateInConfiguredOrder() throws Exception {
    ItemWriter<Order> first = mock(ItemWriter.class);
    ItemWriter<Order> second = mock(ItemWriter.class);

    CompositeItemWriter<Order> writer =
        new CompositeItemWriterBuilder<Order>()
            .delegates(List.of(first, second))
            .build();

    Chunk<Order> chunk = new Chunk<>(List.of(orderA, orderB));
    writer.write(chunk);

    InOrder inOrder = inOrder(first, second);
    inOrder.verify(first).write(chunk);
    inOrder.verify(second).write(chunk);
}
~~~

This test verifies the fan-out contract. You can add checks for:

- First delegate is invoked before the second delegate.
- Every delegate receives the exact items in the chunk.
- Later delegates are not called if an earlier delegate throws an exception.
- Exceptions propagate back to the caller.
- Empty delegate lists or invalid configurations are detected at initialization per the running builder/version behavior.

Do not test the composite writer solely with mocks and conclude transactions/rollbacks work. Transactions require integration tests against real resources.

## 24. Testing Rollback When a Delegate Fails

For database delegates sharing a datasource and transaction manager, integration tests should verify rollback:

1. Delegate A writes to the first table.
2. Delegate B intentionally throws an exception.
3. Step ends FAILED or retries per configuration.
4. Verify the first table contains no data from the uncommitted chunk.

Example failing writer:

~~~java
public class FailingAuditWriter implements ItemWriter<Order> {

    @Override
    public void write(Chunk<? extends Order> chunk) {
        throw new IllegalStateException("Audit write failed");
    }
}
~~~

If the preceding database writer participates properly in the step's transaction, the chunk's inserts can roll back. Tests should use a real transaction manager and datasource like production. Mock writers do not prove transaction participation.

If two delegates use two different datasources, write tests for failure windows to identify which data may already have committed. Do not expect automatic rollback without a shared transaction coordinator.

## 25. Testing Delegate ItemStream Lifecycle

For file writers or resource-managing writers, verify open, update, and close are invoked through the composite:

~~~java
class TrackingStreamWriter implements ItemWriter<Order>, ItemStream {

    private int opens;
    private int updates;
    private int closes;

    @Override
    public void open(ExecutionContext context) {
        opens++;
    }

    @Override
    public void update(ExecutionContext context) {
        updates++;
    }

    @Override
    public void close() {
        closes++;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) {
        // Test writer only records lifecycle.
    }
}
~~~

After building the composite with this delegate, tests call the composite's lifecycle or run a real step and assert callbacks were forwarded. Unit tests can verify delegation; integration tests verify lifecycle occurs at the right times in the step.

If the composite is configured with ignoreItemStream(true), tests must confirm the stream delegate is registered directly or managed by another owner. Do not let a writer pass unit tests only to fail when the step opens files in production.

## 26. Testing Retries and Duplicate Side Effects

If the first delegate writes to the database while the second sends HTTP/messages, test the case where the second delegate times out after the remote system received the request. A mock server can accept the request without returning a response; a subsequent retry will resend the request.

Tests should verify:

- Idempotency key stays identical across retries.
- Remote service applies the operation only once for the same key.
- Database transaction rolls back/commits per configuration.
- Job restart does not generate a new operation ID for the same item operation.
- Logs and audits can trace attempt counts and final outcomes.

Do not only assert the number of composite write() calls. What matters is that side effects in each system end up accurate after retries.

## 27. Skip and Write Skips in a Composite

If an exception from one delegate falls under the skip policy, Spring Batch can treat it as a write failure and apply skipping as configured. However, when earlier delegates were already called before the exception occurred, those earlier delegates may have created side effects.

Example:

~~~text
databaseWriter -> completed write
auditWriter    -> throws InvalidOrderException
fileWriter     -> not called yet
Step           -> handles write skip per policy
~~~

If the transaction rolls back the chunk, database writes can be undone. However, if the audit writer wrote to a non-transactional resource, that data may remain. A skipped item does not automatically delete side effects already emitted to external systems.

With multi-target composites, skip policies must be designed alongside each delegate's semantics. If a failure at a secondary target must not discard data at the primary target, consider isolating the secondary target into a separate step/outbox rather than skipping the whole item.

## 28. Monitoring and Operating a Composite Writer

When a job runs in production, logs and metrics should reveal which delegate is slow or failing. You can wrap writers with a timing decorator:

~~~java
public class TimedOrderWriter implements ItemWriter<Order> {

    private final String name;
    private final ItemWriter<Order> delegate;
    private final MeterRegistry meterRegistry;

    public TimedOrderWriter(
            String name,
            ItemWriter<Order> delegate,
            MeterRegistry meterRegistry) {
        this.name = name;
        this.delegate = delegate;
        this.meterRegistry = meterRegistry;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) throws Exception {
        Timer.Sample sample = Timer.start(meterRegistry);
        try {
            delegate.write(chunk);
        } finally {
            sample.stop(meterRegistry.timer(
                "batch.writer.duration",
                "writer", name
            ));
        }
    }
}
~~~

The decorator above measures writer invocation duration even when an exception occurs. If the delegate implements ItemStream, the decorator must also forward lifecycle callbacks so open/update/close are not lost.

Metrics can include:

- Chunks and items written per delegate.
- Write duration of each delegate.
- Exception/retry counts.
- Items skipped in the write phase.
- Staging files created/published.
- Pending/failed outbox events.

Do not log full sensitive payloads just to debug a writer. Use job execution ID, step execution ID, and appropriate business keys for tracing.

## 29. Common Mistakes When Using CompositeItemWriter

**Thinking each delegate receives a portion of the chunk:** every delegate receives the entire chunk. Use a classifier writer if routing is needed.

**Assuming delegate order equals commit order:** call order does not guarantee independent resources commit together. Verify transaction participation.

**Thinking the composite creates a distributed transaction:** it only coordinates writer calls. Use a transaction coordinator/outbox/workflow if multi-resource consistency is needed.

**Making direct HTTP calls and retrying:** remote side effects may have succeeded despite a client timeout. Use idempotency keys or an outbox.

**Later delegate needing generated IDs from an earlier delegate:** the composite does not reload updated items from the database. Generate required data before the writer or use a coordinator with an explicit contract.

**Forgetting ItemStream lifecycle:** file/cursor delegates do not get open/update/close. Let the composite forward streams or register delegates separately.

**Enabling ignoreItemStream without another owner:** resources may not be opened/closed. Only ignore lifecycle when it is explicitly managed elsewhere.

**Using delegates with mismatched item types:** raw casts can cause runtime errors. Use adapters or a shared output model.

**Assuming thread safety:** the composite invokes delegates sequentially within one write call, yet multiple threads can call the same instance concurrently. Check concurrency for every delegate.

**Using a composite instead of a multi-step flow:** outputs with separate dependencies/commits often need separate steps for clean restart and operation.

**Testing only mock invocations:** mock tests do not prove rollback, stream lifecycle, or idempotency. Add integration tests for real resources.

## 30. Workflow for Designing CompositeItemWriter in Production

First, determine whether all outputs genuinely need the same items/chunks. If all destinations need the same data, use CompositeItemWriter; if items must be routed by type, use a classifier writer. Keep the delegate list in a clear order and ensure item types are compatible.

Next, configure each delegate independently and compose them with CompositeItemWriterBuilder. Identify which transaction manager, datasource, and resources join the chunk transaction. For delegates implementing ItemStream, ensure lifecycle is forwarded by the composite or managed separately by the step. Do not enable ignoreItemStream without a replacement owner.

Finally, design retry/skip rules based on the actual side effects of each target. Use idempotency keys for operations that can be re-invoked, an outbox for events that must be emitted after commit, and separate steps for outputs with distinct transaction/lifecycle semantics. Test delegate order, rollback, stream lifecycle, retries, restarts, and concurrency with both unit tests and integration tests.

CompositeItemWriter is a straightforward way to send the same chunk to multiple writers in a configured order. It gives the step a single unified write point and reuses specialized delegates. Yet transactions, restarts, idempotency, thread safety, and resource lifecycles are still governed by configuration and each delegate. When fan-out semantics and transaction limits are well understood, a composite writer can support multiple outputs while preserving batch job operability and recoverability.
