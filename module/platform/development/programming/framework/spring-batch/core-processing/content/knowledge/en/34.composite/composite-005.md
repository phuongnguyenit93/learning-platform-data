# Writing the Same Item to Multiple Writers

In Spring Batch, a Step sometimes needs to write the same set of items to multiple destinations. For example, each processed order may need to be saved to a database while also exported to a CSV file for another system, or a record may need to be written to both a business table and an audit table. `CompositeItemWriter<T>` supports this by calling multiple `ItemWriter` delegates in the configured order.

Each delegate receives the same chunk of items that the composite receives. The composite does not transform items on its own and does not create a distributed transaction across destinations. Therefore, when using multiple writers, you need to understand call order, delegate lifecycle, transaction boundaries, rollback behavior, and the idempotency of each target.

## 1. What is CompositeItemWriter?

`CompositeItemWriter<T>` is an `ItemWriter<T>` that acts as a coordinator. It holds a list of writer delegates and forwards the same chunk to each writer in the configured order.

For example, a Step processing `Order` needs to write to two places:

- `JdbcBatchItemWriter<Order>` saves orders to a database.
- `FlatFileItemWriter<Order>` exports the same orders to a CSV file.

```text
ItemReader<Order>
       |
       v
ItemProcessor<Order, Order>
       |
       v
Chunk<Order>
       |
       v
CompositeItemWriter<Order>
       |
       +------> JdbcBatchItemWriter ------> Database
       |
       +------> FlatFileItemWriter -------> CSV file
```

If a chunk has 100 `Order`s, each delegate is called with that chunk. The composite does not split the 100 items into two groups and does not pick a single writer per item.

## 2. How CompositeItemWriter Differs from a Routing Writer

Two requirements are commonly confused:

- Writing every item to all writers: use `CompositeItemWriter`.
- Selecting one suitable writer for each item: use `ClassifierCompositeItemWriter` or an equivalent routing mechanism.

| Criterion | `CompositeItemWriter` | `ClassifierCompositeItemWriter` |
|---|---|---|
| Rule | Calls every delegate for the same chunk | Selects a delegate via classifier for each item |
| Where is an item written? | All writers in the list | The writer selected for that item |
| Example | Save to DB and export audit file simultaneously | Domestic orders to writer A, international to writer B |
| Write count | Once per delegate | Once on the classified writer |

If the requirement is "every order is both saved to the database and written to a file", `CompositeItemWriter` fits. If the requirement is "type A orders go to database A, type B go to database B", a routing writer is needed.

## 3. Configuring CompositeItemWriter with a Builder

Spring Batch provides `CompositeItemWriterBuilder<T>` to declare the list of delegates:

```java
@Bean
public CompositeItemWriter<Order> orderCompositeWriter(
        JdbcBatchItemWriter<Order> databaseOrderWriter,
        FlatFileItemWriter<Order> orderFileWriter) {

    return new CompositeItemWriterBuilder<Order>()
            .delegates(List.of(databaseOrderWriter, orderFileWriter))
            .build();
}
```

The delegate list determines the call order. In the example, the database writer is called first, followed by the file writer. The order should be chosen deliberately because one delegate may complete before the next delegate encounters an error.

The composite should be configured once in the application context. Writer delegates are injected and lifecycle-managed by Spring. Do not recreate delegates inside each `write()` call, as doing so loses configured state, checkpoints, and resources.

## 4. Example with Two Writers: Database and CSV File

Suppose an `Order` needs to be saved to the `processed_order` table and simultaneously exported to `processed-orders.csv`.

Database writer:

```java
@Bean
public JdbcBatchItemWriter<Order> databaseOrderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO processed_order (order_id, customer_name, amount)
                    VALUES (:orderId, :customerName, :amount)
                    """)
            .beanMapped()
            .build();
}
```

File writer:

```java
@Bean
@StepScope
public FlatFileItemWriter<Order> orderFileWriter(
        @Value("#{jobParameters['outputFile']}") String outputFile) {

    return new FlatFileItemWriterBuilder<Order>()
            .name("orderFileWriter")
            .resource(new FileSystemResource(outputFile))
            .delimited()
            .delimiter(",")
            .names("orderId", "customerName", "amount")
            .saveState(true)
            .build();
}
```

Composite writer:

```java
@Bean
public CompositeItemWriter<Order> orderCompositeWriter(
        JdbcBatchItemWriter<Order> databaseOrderWriter,
        FlatFileItemWriter<Order> orderFileWriter) {

    return new CompositeItemWriterBuilder<Order>()
            .delegates(List.of(databaseOrderWriter, orderFileWriter))
            .build();
}
```

Here the file path is obtained from JobParameters via `@StepScope`, while the database writer uses the Spring-managed `DataSource`. The file writer has a stable name and enables `saveState(true)` to support checkpoints/restarts.

## 5. Registering CompositeItemWriter in a Step

The composite writer is passed into the Step like a regular writer:

```java
@Bean
public Step exportProcessedOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, Order> orderProcessor,
        CompositeItemWriter<Order> orderCompositeWriter) {

    return new StepBuilder("exportProcessedOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderCompositeWriter)
            .build();
}
```

With a chunk size of 100, Spring Batch calls `orderCompositeWriter.write(...)` for the current chunk. The composite calls the database writer and file writer in turn with the same `Order` items.

In modern Spring Batch versions, `CompositeItemWriter` implements `ItemStreamWriter` and can forward lifecycle callbacks to delegates implementing `ItemStream`. If using an older version or if a delegate is hidden inside a wrapper/proxy that the framework does not recognize, check stream registration and register the delegate explicitly with `.stream(...)` on the Step if needed. Do not register lifecycle twice for the same delegate.

## 6. Delegate Call Order

The composite calls delegates in the order of the configured list. For example:

```java
.delegates(List.of(databaseWriter, fileWriter, auditWriter))
```

The order is:

1. `databaseWriter.write(chunk)`.
2. `fileWriter.write(chunk)`.
3. `auditWriter.write(chunk)`.

If one delegate throws an exception, the composite call cannot finish normally. Subsequent delegates may not be called. Delegates that ran earlier may already have caused side effects.

Order delegates based on the transactional characteristics and reliability of each target. Order does not create atomicity across systems; it only defines method invocation order.

If a delegate needs data generated by another delegate, consider moving that data generation into a processor or a service with a clear contract. Do not rely on an earlier writer mutating items in place for a later writer to observe new values.

## 7. Every Delegate Receives the Same Chunk

`CompositeItemWriter` sends the same chunk to each delegate. Therefore, writer delegates must accept the same item type and interpret the data with the same meaning.

For example:

```text
Chunk<Order> = [orderA, orderB, orderC]

databaseWriter.write([orderA, orderB, orderC])
fileWriter.write([orderA, orderB, orderC])
auditWriter.write([orderA, orderB, orderC])
```

If targets require different data representations, you can:

- Use separate extractors/mappers inside each writer.
- Use a shared model containing enough data for all targets.
- Normalize or enrich items in a processor before reaching the composite.
- Write an `ItemWriter` adapter for one target to map the model to the target schema.

Avoid letting one delegate mutate received objects in a way that affects the next delegate. Items should be treated as immutable inputs during fan-out. If a target needs a different transformation, build a separate DTO/representation inside the delegate.

## 8. CompositeItemWriter Does Not Create Transactions

The composite only coordinates writer calls. Chunk transactions are managed by the Step and `PlatformTransactionManager`.

If all delegates write to the same database using the same transaction manager, write statements can participate in the same transaction. When one delegate fails, rollback can undo uncommitted database changes from earlier delegates.

However, if delegates write to different resource types—such as a database, files, HTTP APIs, and a message broker—a database transaction does not automatically undo all external side effects.

| Write Target | Does DB transaction rollback automatically undo it? |
|---|---|
| Tables in the same database/transaction | Usually yes, if sharing the transaction manager/resource |
| Another database with a separate transaction manager | No, unless an appropriate transaction coordination mechanism is used |
| Plain files | No distributed atomicity; the writer may have its own transactional buffering |
| HTTP API | No |
| Email or notification systems | No |
| Message broker | Only if the broker participates in a properly coordinated transaction |

Therefore, having `CompositeItemWriter` call multiple writers in one Step should not be interpreted as all targets committing or rolling back atomically together.

## 9. What Happens if the Second Writer Fails?

Suppose the composite calls the database writer first and then the file writer:

```text
CompositeItemWriter.write(chunk)
       |
       +--> databaseWriter.write(chunk)  succeeded
       |
       +--> fileWriter.write(chunk)      throws exception
       |
       v
Chunk transaction rollback (if exception triggers rollback)
```

If the database writer participates in the Step's transaction, uncommitted database changes can be rolled back. For the file writer, behavior depends on the implementation and how it manages transaction buffers/checkpoints. An output file or non-transactional external side effect may already have been altered and will not be reverted by database rollback.

On retry, the composite may invoke delegates again. The database writer may re-write the same items; the file writer may re-write or restore position per its state. Targets that do not support rollback require idempotency or a separate recovery mechanism.

If the first delegate already sent an HTTP request successfully and the second delegate fails, a retry may resend the HTTP request. Use an idempotency key per business item or chunk to prevent duplicate side effects.

## 10. Transactional Buffering in FlatFileItemWriter

`FlatFileItemWriter` supports saving state and has transactional buffering to coordinate file writes with chunk processing. This handles rollbacks in normal Step scenarios much better than a writer that writes raw bytes directly to a file without state.

However, transactional buffering does not turn the filesystem into a resource participating in an XA transaction with the database. A process or host crash right at publish/flush time may still require reconciliation. If strict consistency between database and file is required, consider writing temporary files per chunk or per Job, publishing the file only after the database transaction/Step completes, and using a manifest/status to manage publishing.

A generally safe pattern is:

1. Write business data to the database within the transaction.
2. Write the export event to an outbox in the same transaction.
3. Have a separate Step/Job read the outbox and generate the file or send messages.
4. Mark the event as published using an idempotency key.

An outbox commits both the business data and the publishing intent in the database together. File/message delivery can still be retried, while duplicates can be identified and handled.

## 11. Lifecycle of ItemStream Delegates

Some delegates such as `FlatFileItemWriter` implement `ItemStreamWriter` because they must open files, save position, and close resources. The composite writer must forward lifecycle events so delegates are managed properly.

In modern Spring Batch versions, `CompositeItemWriter` can by default call `open()`, `update()`, and `close()` for delegates implementing `ItemStream`. The builder has an `ignoreItemStream(...)` option; do not enable ignoring lifecycle if any delegate needs checkpoints or resource cleanup.

For example:

```java
return new CompositeItemWriterBuilder<Order>()
        .delegates(List.of(databaseWriter, fileWriter))
        .ignoreItemStream(false)
        .build();
```

If using an older API version or a custom composite that does not forward lifecycle, register stream delegates directly on the Step:

```java
return new StepBuilder("exportOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .writer(compositeWriter)
        .stream(fileWriter)
        .build();
```

Choose one clear lifecycle mechanism. If the composite already manages the delegate, do not register the same delegate a second time if doing so causes `open/update/close` to be called repeatedly. Check your project's Spring Batch version and test the actual lifecycle behavior.

## 12. Checkpoints and Restarts with Multiple Writers

Each delegate may maintain its own state. For instance, a file writer stores file position, while another writer stores its own metadata. The composite needs to ensure delegate states are updated at checkpoints.

On restart:

1. Spring Batch opens the composite writer.
2. The composite forwards `open()` to registered stream delegates.
3. Each delegate restores state from the Step `ExecutionContext`.
4. On chunk commit, the composite forwards `update()` to delegates.
5. When the Step ends, the composite forwards `close()` to release resources.

Writer names and ExecutionContext keys must be stable. If two delegates use the same state key, they can overwrite each other. Give each writer a distinct name and keep that name stable across deployments while older Jobs may still be restarted.

A checkpoint only describes progress saved by Spring Batch. It does not guarantee every external side effect completed exactly once. For example, an HTTP API may have received data before the process crashed prior to metadata commit; restarting may resend the request. Write targets need idempotency or a reconciliation mechanism.

## 13. Configuring ignoreItemStream

`ignoreItemStream` controls whether the composite forwards ItemStream lifecycle callbacks to delegates in versions that expose this option.

- `false`: the composite manages lifecycle for delegates implementing `ItemStream`.
- `true`: the composite skips delegate lifecycle; the application must register/manage streams elsewhere if delegates require lifecycle callbacks.

Normally keep `false` when stateful delegates are present. Only set `true` when lifecycle is explicitly managed elsewhere and duplicate registration has been avoided.

Do not use `ignoreItemStream(true)` just to silence open/close errors in a Step. If a file writer is not opened or does not save checkpoints, a restart may write at the wrong position or leak file handles.

## 14. When Do You Need a Writer Adapter?

The composite requires delegates to accept an item type compatible with `T`. If one target requires a different schema, you can create an adapter:

```java
public class OrderAuditWriter implements ItemWriter<Order> {

    private final ItemWriter<OrderAuditRecord> delegate;

    public OrderAuditWriter(ItemWriter<OrderAuditRecord> delegate) {
        this.delegate = delegate;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) throws Exception {
        List<OrderAuditRecord> auditRecords = chunk.getItems().stream()
                .map(order -> new OrderAuditRecord(
                        order.getOrderId(),
                        "ORDER_PROCESSED",
                        order.getAmount()))
                .toList();

        delegate.write(new Chunk<>(auditRecords));
    }
}
```

The composite can accept `OrderAuditWriter` alongside the database writer. The adapter converts `Order` to `OrderAuditRecord` and calls its delegate.

If the adapter wraps an `ItemStream` delegate, the adapter must also forward lifecycle callbacks or the Step must register the stream delegate explicitly. Do not forward only `write()` and forget `open/update/close()` when the delegate is stateful.

## 15. CompositeItemWriter and Processors

Processors run before writers and are usually the right place to normalize an item once before fan-out. For example, a processor adds `processedAt`, computes status, or generates an audit ID; every delegate afterward receives the same result.

```java
@Bean
public ItemProcessor<Order, ProcessedOrder> orderProcessor(Clock clock) {
    return order -> new ProcessedOrder(
            order.getOrderId(),
            order.getCustomerName(),
            order.getAmount(),
            Instant.now(clock)
    );
}
```

Then the composite has type `CompositeItemWriter<ProcessedOrder>` and delegates accept `ProcessedOrder`.

Avoid having each writer modify the same input object. Delegate invocation order should not alter the data seen by the next delegate. If one target needs a different data shape, an adapter producing a separate representation is clearer.

## 16. Exception Handling and Retry

When a delegate throws an exception, the composite cannot consider the chunk successfully written to all targets. The exception is handed back to the Step for transaction and fault-tolerance policy handling.

For example:

```java
return new StepBuilder("exportOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .writer(compositeWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
```

Only retry recoverable errors. If the database already wrote and the file writer fails, a retry may invoke the database writer again. Ensure database writes are idempotent, for example using a unique key/upsert or ensuring transaction rollback truly covers the write.

Do not retry an HTTP writer if the API does not support idempotency and each call creates a new transaction. In that case, a retry can produce duplicates even though the Step ultimately commits once.

Skipping also requires care. If one delegate fails to write an item while other delegates already wrote it, skipping the whole item can leave targets in an inconsistent state. Define clearly whether a skip policy fits fan-out and whether reconciliation is in place.

## 17. Idempotency When Writing to Multiple Targets

Idempotency means repeating the same operation does not create duplicate or incorrect business results. With a composite writer, idempotency is especially important because delegates can be re-invoked after rollback/retry/restart.

Common approaches:

- Use a business key/unique constraint for database inserts.
- Use upserts or versioned writes when appropriate for the domain.
- Send an idempotency key to HTTP APIs.
- Put a unique event ID in messages and let consumers deduplicate.
- Write files to a path keyed by JobInstance/batch ID, then publish once.
- Use outbox/inbox tables to manage event publishing and consumption.
- Persist separate publish status to support retries and reconciliation.

Do not use `write()` invocation counts or delegate order as business identifiers. Keys must remain stable per item or event across retries.

## 18. CompositeItemWriter and Multiple Databases

If all writers use the same database transaction and the same `DataSource` managed by the Step's transaction manager, operations can join the same transaction. When using multiple independent databases, a standard `PlatformTransactionManager` does not automatically coordinate an atomic commit across all databases.

Options:

- Use a transaction coordinator/XA if true distributed atomicity is required and supported by the infrastructure.
- Use an outbox to record intent to update the secondary database within the primary transaction, then process asynchronously.
- Use idempotent upserts and reconciliation if eventual consistency is acceptable.
- Split into separate Steps so each target has independent retry/restart, tracking completion status by batch ID.

CompositeItemWriter fits synchronous fan-out in one Step when delegates have compatible transaction semantics. It is not a replacement for a transaction coordinator.

## 19. When Should You Split into Multiple Steps?

Not every multi-target write case should use CompositeItemWriter. If targets have different SLAs, retry policies, or recovery models, splitting into multiple Steps can be easier to operate.

For example:

```text
read + validate + write database
              |
              v
       commit main data
              |
              v
     export file from database
              |
              v
      publish to external API
```

Advantages of multiple Steps:

- Each target has its own checkpoint and retry.
- A publish failure does not require re-reading the original source.
- The export/publish Step can be rerun without rewriting business data.
- Status of each stage is easier to monitor.

In return, you need to store a batch ID or query condition so the later Step picks up the exact dataset committed by the earlier Step. If you need to write to all targets in the same chunk and they have compatible transaction semantics, CompositeItemWriter can be simpler.

## 20. Common Misconceptions

**Thinking CompositeItemWriter splits items across delegates.** It sends the same chunk to all delegates. To route by item, use a classifier writer.

**Thinking the composite creates a shared transaction.** Transactions are managed by the Step/transaction manager; the composite only invokes writers.

**Thinking all targets roll back together.** Only resources participating in the corresponding transaction are rolled back. Files, HTTP, email, and brokers may retain side effects.

**Ignoring delegate order.** Writers are called in configured order. Later delegates may not run if an earlier delegate fails.

**Letting an earlier writer mutate items for a later writer.** Delegates receive the same objects/chunk; mutation creates order dependencies and unpredictable bugs.

**Forgetting ItemStream delegate lifecycle.** File writers need open/update/close. Verify whether the composite forwards lifecycle or if the Step registered the stream separately.

**Registering a stream delegate twice.** Lifecycle callbacks may be invoked repeatedly. Pick one clear management mechanism.

**Retrying a non-idempotent writer.** A delegate that already produced side effects may be called again after a failure in another delegate. Use idempotency keys or an outbox.

**Using a composite even when targets need independent operation.** Split into separate Steps when independent checkpoints, retries, and recovery are needed.

## 21. Testing CompositeItemWriter

Test both fan-out behavior and failure handling when a delegate fails:

1. Configure two delegates and verify both receive the same items in the chunk.
2. Configure three delegates and verify call order matches the list.
3. Make the first delegate throw an exception; verify subsequent delegates are not treated as having written successfully.
4. Make the second delegate throw an exception after the first ran; verify transaction rollback for transactional resources.
5. Verify the file writer restores state after rollback/restart under realistic configuration.
6. Verify `open()`, `update()`, and `close()` are forwarded the expected number of times to ItemStream delegates.
7. Verify stream delegates hidden in wrappers are explicitly registered.
8. Trigger retries and verify database/API/file do not create duplicates.
9. Verify skip policies do not cause targets to drift out of sync.
10. Run a Job restart after one chunk committed and another chunk did not commit.

Unit tests with mock writers verify ordering and passed chunks. Integration tests with a real database, filesystem, and transaction manager are needed to verify rollback, buffering, and restart. If HTTP or a broker is involved, check side effects on the target system using idempotency keys.

## 22. Choosing a Multi-Target Write Strategy

Use `CompositeItemWriter` when the same item/chunk must be written synchronously to every writer delegate. Configure delegates in a deliberate order, ensure all accept the same item type, and do not mutate input objects. If delegates hold state, manage the `ItemStream` lifecycle and checkpoints properly.

Before adopting it, determine the transaction boundaries of each target. Writers sharing a database transaction can roll back together; files and external systems require buffering, idempotency, an outbox, or reconciliation. If each target needs independent retry/restart, consider splitting into separate Steps. If each item should go to only one target, use a routing writer.

CompositeItemWriter makes data fan-out inside a chunk Step straightforward. True consistency still depends on the transaction manager, delegate lifecycle, rollback capability, and how each target handles repeated writes after retries or restarts.
