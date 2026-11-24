# Writing a Custom ItemWriter

In Spring Batch, `ItemWriter<T>` is the component that receives the output items of a chunk and writes them to a destination. Spring Batch provides many built-in writers for databases, files, and common formats. When the destination or write rules do not fit built-in writers, the application can implement `ItemWriter<T>` directly.

A custom writer typically needs to make four things clear: receiving the items in a chunk properly, writing according to the target system's contract, letting exceptions propagate to the framework when writing fails, and ensuring behavior aligned with transactions and restarts. A writer should not control the `Job` loop itself, commit transactions manually, or silently drop failing items.

The examples in this lesson use the Spring Batch 5 API, where `ItemWriter` accepts `Chunk<? extends T>`. In Spring Batch 4 and earlier, the legacy writer signature took `List<? extends T>`; use the API matching your project's version.

## 1. When Do You Need a Custom ItemWriter?

A custom writer is appropriate when the application needs to:

- Write to an internal system without a built-in writer.
- Call a partner API to submit a batch of records.
- Apply batch-specific rules before persisting.
- Write simultaneously to multiple destinations according to an explicit policy.
- Integrate with a custom library or protocol.
- Wrap an existing writer to add validation, metrics, or auditing.

If a built-in writer already meets your needs, prefer using it. For instance, `JdbcBatchItemWriter` fits JDBC inserts/updates, `FlatFileItemWriter` fits text files, and `JsonFileItemWriter` fits JSON arrays. A custom writer increases your responsibility for transactions, resource lifecycles, retries, and restarts that the framework already handles in built-in implementations.

## 2. ItemWriter in Chunk-Oriented Processing

A chunk `Step` executes a read, process, and write flow:

```text
ItemReader
    |
    v
ItemProcessor
    |
    v
Chunk<T>
    |
    v
ItemWriter.write(chunk)
    |
    v
Transaction commit
```

The reader produces items. The processor may transform items or return `null` to filter them out. Remaining items are collected into a chunk and passed to the writer. The writer receives the entire chunk in a single call; it must not assume each call contains only one item.

Example `Step` with chunk size 100:

```java
return new StepBuilder("exportOrdersStep", jobRepository)
        .<Order, OrderExport>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .build();
```

If there are 235 output items, the writer will typically be called with three chunks of sizes 100, 100, and 35. The chunk size determines the group of items written in one `Step` transaction; it is not the number of threads or `Job` runs.

## 3. The ItemWriter Contract in Spring Batch 5

The `ItemWriter<T>` interface has a `write` method accepting a `Chunk`:

```java
package org.springframework.batch.item;

public interface ItemWriter<T> {
    void write(Chunk<? extends T> chunk) throws Exception;
}
```

Key points:

- `T` is the item type the writer receives.
- `Chunk<? extends T>` holds the items for the current write call.
- The method can throw an exception to signal to the framework that the write failed.
- The writer does not return a list of written items; the outcome is signaled by returning normally or throwing an exception.
- The framework coordinates transactions, retries, skips, and commits according to `Step` configuration.

In Spring Batch 5, you can iterate over items with `chunk.getItems()`:

```java
@Override
public void write(Chunk<? extends Order> chunk) {
    for (Order order : chunk.getItems()) {
        // Write each order.
    }
}
```

Do not call `reader.read()` inside a writer. Reader, processor, and writer have distinct roles in the pipeline; reading more items inside the writer breaks the framework's chunk and checkpoint control.

## 4. Simple Custom Writer Writing to a Database

Example writer using `JdbcTemplate` to write orders into a target table:

```java
public class JdbcOrderWriter implements ItemWriter<OrderExport> {

    private static final String INSERT_SQL = """
            INSERT INTO exported_orders
                (order_id, customer_id, amount, currency)
            VALUES (?, ?, ?, ?)
            """;

    private final JdbcTemplate jdbcTemplate;

    public JdbcOrderWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void write(Chunk<? extends OrderExport> chunk) {
        for (OrderExport order : chunk.getItems()) {
            jdbcTemplate.update(
                    INSERT_SQL,
                    order.orderId(),
                    order.customerId(),
                    order.amount(),
                    order.currency());
        }
    }
}
```

The writer receives the entire chunk and writes each item in turn. `JdbcTemplate` binds values to a prepared statement, avoiding string concatenation of inputs into SQL. If a write throws `DataAccessException`, the exception propagates to Spring Batch so the chunk transaction is handled per policy.

In production, if high throughput is needed, you can use `JdbcTemplate.batchUpdate` or `NamedParameterJdbcTemplate` to send batched SQL. The implementation must preserve semantics: write errors must propagate, and success must not be reported when part of the operation failed.

## 5. Registering a Custom Writer as a Spring Bean

You can define the writer using `@Bean`:

```java
@Bean
ItemWriter<OrderExport> orderExportWriter(JdbcTemplate jdbcTemplate) {
    return new JdbcOrderWriter(jdbcTemplate);
}
```

Then inject it into the `Step`:

```java
@Bean
Step exportOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, OrderExport> orderProcessor,
        ItemWriter<OrderExport> orderExportWriter) {

    return new StepBuilder("exportOrdersStep", jobRepository)
            .<Order, OrderExport>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderExportWriter)
            .build();
}
```

If the application has multiple `ItemWriter` beans of the same type, use `@Qualifier` to specify the right writer. Bean names should describe the target or purpose, such as `orderExportWriter` or `customerArchiveWriter`.

`@StepScope` is not needed for every custom writer. A stateless writer that does not depend on `JobParameters` and is safe to share can be a singleton. Use `@StepScope` only when execution-specific resources or parameters are needed, or when the writer holds `Step`-scoped state.

## 6. Transactions When a Custom Writer Uses JDBC

A custom writer using `JdbcTemplate` can participate in the chunk transaction if `JdbcTemplate` uses the same `DataSource` and transaction manager as the `Step`. In that case, JDBC statements execute on the connection bound to the current Spring transaction.

```text
Chunk transaction
    |
    +--> Writer: INSERT order 1
    +--> Writer: INSERT order 2
    +--> Writer: INSERT order 3
    +--> Exception while writing order 3
    |
    v
Rollback transaction
    |
    +--> Uncommitted changes in transaction are rolled back
```

This only holds when the resource actually participates in the same transaction. If the writer uses a different `DataSource` than the transaction manager, opens standalone connections manually, or calls an external system, chunk rollback will not automatically undo those changes.

Do not call `connection.commit()` or `transactionManager.commit()` manually inside `write`. The framework manages transaction boundaries. Committing manually can persist data before the chunk finishes, breaking rollback if the processor or writer encounters an error.

## 7. Do Not Swallow Exceptions in write

A writer must signal failure by throwing an exception. Do not catch an exception and only log it:

```java
// Not recommended
@Override
public void write(Chunk<? extends OrderExport> chunk) {
    try {
        persist(chunk);
    } catch (DataAccessException exception) {
        log.error("Could not write orders", exception);
        // Framework will think write succeeded.
    }
}
```

If the writer does not throw an exception, Spring Batch may consider the chunk successfully written and proceed to commit. Failing items can then vanish from the pipeline while the `Job` still reports `COMPLETED`.

Let the exception propagate to the framework or wrap it in a contextual exception while preserving the cause:

```java
try {
    persist(order);
} catch (DataAccessException exception) {
    throw new OrderWriteException(
            "Could not persist order " + order.orderId(),
            exception);
}
```

Do not wrap all exceptions into the same type if doing so loses the ability to classify transient, data, or configuration errors. Preserve the cause chain so retry/skip policies and operators can identify the root cause.

## 8. Batch Writing Instead of Item-by-Item

A `jdbcTemplate.update` loop is easy to understand, but makes one JDBC round trip per item. For large chunks, you can use batch updates to reduce round trips:

```java
public class JdbcOrderWriter implements ItemWriter<OrderExport> {

    private final JdbcTemplate jdbcTemplate;

    public JdbcOrderWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void write(Chunk<? extends OrderExport> chunk) {
        jdbcTemplate.batchUpdate(
                """
                INSERT INTO exported_orders
                    (order_id, customer_id, amount, currency)
                VALUES (?, ?, ?, ?)
                """,
                chunk.getItems(),
                chunk.size(),
                (statement, order) -> {
                    statement.setLong(1, order.orderId());
                    statement.setString(2, order.customerId());
                    statement.setBigDecimal(3, order.amount());
                    statement.setString(4, order.currency());
                });
    }
}
```

Batch updates can boost throughput, though drivers and databases differ in how they report batch failures. Test scenarios where one row violates a constraint, when a batch times out, and when a transaction rolls back. Do not assume every driver pinpoints the exact failing item in the same way.

## 9. Custom Writer Writing to an External API

A custom writer may send items to an external service:

```java
public class PartnerOrderWriter implements ItemWriter<OrderExport> {

    private final PartnerClient partnerClient;

    public PartnerOrderWriter(PartnerClient partnerClient) {
        this.partnerClient = partnerClient;
    }

    @Override
    public void write(Chunk<? extends OrderExport> chunk) {
        for (OrderExport order : chunk.getItems()) {
            partnerClient.upsertOrder(
                    order.orderId(),
                    order,
                    "order-export-" + order.orderId());
        }
    }
}
```

This example assumes the partner API supports idempotent operations or idempotency keys. If an HTTP call succeeds on the server but the client times out before receiving the response, Spring Batch may retry the writer. The retry must send the same key so the target system does not create duplicate side effects.

A chunk JDBC transaction cannot roll back an HTTP request already processed by a partner. For critical integrations, consider writing an outbox record within the chunk transaction and letting a separate relay dispatch requests. Calling an API directly from a writer is appropriate only when retry, timeout, and deduplication semantics are well defined.

## 10. The Writer Receives a Chunk, Not Its Own Transaction Manager

A custom writer may write multiple items per call, but it should not open a new transaction per item if changes across the chunk are expected to commit or roll back together.

Inappropriate example:

```java
for (OrderExport order : chunk.getItems()) {
    transactionTemplate.execute(status -> {
        repository.save(order);
        return null;
    });
}
```

If each item commits independently, a failure on the last item leaves earlier items committed even though the chunk failed. This breaks the atomicity readers normally expect from chunk transactions.

If business requirements truly demand per-item transactions, design an appropriate `Step`/flow and document the semantics explicitly. Do not accidentally create independent transactions just because a custom writer wants control over writes.

## 11. Stateful Custom Writers: ItemStreamWriter

A simple `ItemWriter` suffices for stateless writers. If a writer manages resources or needs to persist state for restarts, implement `ItemStreamWriter<T>`, which combines `ItemWriter<T>` and `ItemStream`.

`ItemStream` defines three callbacks:

```java
public interface ItemStream {
    void open(ExecutionContext executionContext)
            throws ItemStreamException;

    void update(ExecutionContext executionContext)
            throws ItemStreamException;

    void close() throws ItemStreamException;
}
```

Roles:

- `open`: open resources and restore state from `ExecutionContext`.
- `update`: save current state to checkpoint alongside the chunk.
- `close`: release handles/resources when the `Step` lifecycle finishes normally.

Example custom writer wrapping another writer and adding validation:

```java
public class ValidatingOrderWriter
        implements ItemStreamWriter<OrderExport> {

    private final ItemStreamWriter<OrderExport> delegate;

    public ValidatingOrderWriter(
            ItemStreamWriter<OrderExport> delegate) {
        this.delegate = delegate;
    }

    @Override
    public void write(Chunk<? extends OrderExport> chunk)
            throws Exception {

        for (OrderExport order : chunk.getItems()) {
            if (order.orderId() == null || order.amount() == null) {
                throw new IllegalArgumentException(
                        "Order id and amount are required");
            }
        }

        delegate.write(chunk);
    }

    @Override
    public void open(ExecutionContext executionContext)
            throws ItemStreamException {
        delegate.open(executionContext);
    }

    @Override
    public void update(ExecutionContext executionContext)
            throws ItemStreamException {
        delegate.update(executionContext);
    }

    @Override
    public void close() throws ItemStreamException {
        delegate.close();
    }
}
```

This example shows that a decorator must forward all three lifecycle callbacks to the delegate. If it calls only `delegate.write` and omits `open`, `update`, and `close`, the inner writer may fail to open resources, save checkpoints, or close files properly.

When registering the decorator, ensure Spring Batch recognizes the bean as an `ItemStreamWriter` or registers the stream delegate explicitly. Do not hide the `ItemStream` interface when wrapping a stateful writer.

## 12. Saving Custom State in ExecutionContext

If a writer manages its own state, `update` writes state to `ExecutionContext` and `open` restores it. Keys should have a dedicated prefix, be stable, and avoid collisions with other components.

Conceptual example:

```java
private static final String LAST_WRITTEN_ID =
        "customOrderWriter.lastWrittenId";

@Override
public void open(ExecutionContext context) {
    if (context.containsKey(LAST_WRITTEN_ID)) {
        lastWrittenId = context.getLong(LAST_WRITTEN_ID);
    } else {
        lastWrittenId = 0L;
    }
}

@Override
public void update(ExecutionContext context) {
    context.putLong(LAST_WRITTEN_ID, lastWrittenId);
}
```

This only illustrates saving state. In an actual writer, update `lastWrittenId` only after the item/chunk writes succeed under your chosen transaction semantics. If the resource is outside the transaction, `ExecutionContext` state may commit at a different point than the side effect; idempotency or reconciliation is required.

Do not store large objects, connections, streams, or credentials in `ExecutionContext`. Store small, serializable values sufficient to restore resource state.

## 13. Resource Lifecycle and Closing Resources

A writer managing files, sockets, or cursors must close resources following the lifecycle. Clarify resource ownership:

- If the writer creates the resource itself, it is normally responsible for closing it.
- If the resource is injected externally, define the ownership contract so shared resources are not closed prematurely.
- If a delegate writer manages the resource, the decorator must forward the lifecycle.
- Do not close a connection managed by Spring's transaction manager by pulling and closing the transaction-bound connection manually.

`close()` releases resources when the framework finishes the stream lifecycle normally. An abruptly killed process may never invoke `close()`. For temporary files or external resources, provide dedicated crash cleanup/recovery mechanisms.

## 14. Retry and Write Failures

If `write` throws an exception covered by the retry policy, Spring Batch can retry the write operation according to fault-tolerance settings. Therefore, a custom writer must tolerate repeated invocations.

Principles:

- Retry only recoverable errors, such as deadlocks or transient connection failures.
- Configure appropriate retry limits and backoff.
- Do not retry deterministic data errors like missing required fields.
- Do not swallow exceptions and return normally.
- If the writer has non-transactional side effects, use idempotency keys or deduplication.
- Do not keep shared mutable state that becomes corrupted across retries.

Example configuration:

```java
return new StepBuilder("exportOrdersStep", jobRepository)
        .<Order, OrderExport>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
```

`retryLimit` and attempt counting must be understood per the Spring Batch API/version in use. If retry exhaustion should fall back to skipping, configure an explicit skip policy and test the interaction between retry and skip.

## 15. Skip and Write Failures

Spring Batch can skip an item if an exception from the writer is permitted by the skip policy and the skip limit has not been exceeded. In some cases, the framework isolates the failing item by retrying smaller groups or individual items; thus, the writer may be invoked multiple times with varying chunk sizes when write-skip is enabled.

This means a custom writer must not:

- Assume a chunk always has a fixed size.
- Produce non-repeatable side effects on the first write call assuming the framework will not re-invoke it.
- Mutate chunk contents or remove items from the list without an explicit contract.
- Rely on an item's index within a chunk as a persistent ID.

Example skip configuration for data errors:

```java
.faultTolerant()
.skip(InvalidOrderException.class)
.skipLimit(20)
```

For data errors, it is usually better to validate in the processor so invalid items are caught before the writer triggers side effects. The writer should focus on writing validated items.

## 16. Writer and Filter Are Not the Same

A processor returns `null` to filter out a valid item that does not need to be written. The writer receives the remaining items. If a writer silently drops items without notifying the framework, counters and audit trails become inaccurate.

| Need | Appropriate component |
|---|---|
| Exclude an item by business condition | `ItemProcessor` returning `null` |
| Transform an item to an output model | `ItemProcessor` |
| Write items to destination | `ItemWriter` |
| Skip an item due to an allowed exception | Skip policy and `SkipListener` |
| Log before/after a write operation | `ItemWriteListener` |

Do not use the writer to replace the processor for complex filtering rules. Doing so makes testing harder and obscures how many items were filtered versus actually written.

## 17. ItemWriteListener and Writer Responsibilities

`ItemWriteListener` lets you observe the write lifecycle:

- `beforeWrite`: before the writer is invoked.
- `afterWrite`: after the writer completes normally.
- `onWriteError`: when the writer throws an exception.

Listeners suit logging, metrics, and auditing. They do not replace the writer and should not write the same output again.

Example:

```java
public class OrderWriteListener implements ItemWriteListener<OrderExport> {

    @Override
    public void beforeWrite(Chunk<? extends OrderExport> items) {
        log.debug("Writing {} orders", items.size());
    }

    @Override
    public void afterWrite(Chunk<? extends OrderExport> items) {
        log.info("Wrote {} orders", items.size());
    }

    @Override
    public void onWriteError(
            Exception exception,
            Chunk<? extends OrderExport> items) {
        log.error("Could not write {} orders", items.size(), exception);
    }
}
```

Register the listener on the `Step` with `.listener(orderWriteListener)`. During retries, callbacks may execute multiple times; logs and metrics should reflect attempts and not mistake every `afterWrite` for a final business commit if the transaction can still roll back.

## 18. Composite and Routing Writers

If the only goal is sending the same items to multiple writers, Spring Batch offers `CompositeItemWriter`. If you need to choose a writer by item type, consider `ClassifierCompositeItemWriter` or a version-appropriate routing pattern.

Do not build a complex orchestrating writer from scratch if built-in components cover the case. However, a custom composite can be warranted when enforcing ordering rules, specialized error handling, or coordination across distinct targets.

When writing to multiple destinations, define the transaction boundary. If one writer writes to a database and another calls an API, the database transaction cannot roll back the API call. If the first writer succeeds and the second fails, a retry may call the first writer again. Each target needs a shared transaction or proper idempotency/deduplication.

## 19. Thread Safety and Scope

A singleton writer can be invoked from multiple executions or threads if the application runs partitioned/multi-threaded `Step`s or concurrent `Job`s. Decide explicitly whether the writer is safe to share.

Stateless writers using `JdbcTemplate` can usually be singletons because `JdbcTemplate` is designed for shared use. However, a writer holding mutable fields like current file, counter, buffer, or current tenant requires an isolated scope or proper synchronization.

Principles:

- Do not store the current item in a singleton field.
- Do not share a single `BufferedWriter` across multiple `Job`s without explicit ownership/locking.
- Use `@StepScope` when resources, paths, or state belong to a `StepExecution`.
- Do not maintain static mutable state for retry counts or item lists.
- If the writer can be called concurrently, verify that collaborators and resources are thread-safe.
- Test two `Job`s running in parallel with distinct outputs.

## 20. Idempotency When the Writer Is Re-Invoked

A chunk can be written again after rollback/retry or when restarting from a checkpoint. If the writer creates side effects outside a transaction, prevent duplicates.

Example measures:

- Database: unique business keys, upserts, or operation IDs.
- HTTP API: stable idempotency keys tied to the business operation.
- Message broker: stable event IDs and consumer-side deduplication.
- File: staging paths per `JobInstance`, checksums, and idempotent publishing.
- Multiple resources: outbox/inbox patterns or reconciliation.

Do not generate a fresh random idempotency key inside each `write` call. The key must represent the business operation and stay identical across retries and restarts.

Even if the writer writes only to a database within the chunk transaction, rollback undoes uncommitted changes. Still, consider unique keys when multiple `Job`s might process the same business record or when commit status is ambiguous after a connection failure.

## 21. Validation in a Custom Writer

A writer may verify technical preconditions before writing—for example, non-null objects, required IDs present, or chunk size within API limits. Complex business rules, however, generally belong in the processor or a separate validator.

Example simple check:

```java
private void validate(OrderExport order) {
    if (order.orderId() == null) {
        throw new InvalidOrderException("orderId is required");
    }
    if (order.amount() == null || order.amount().signum() < 0) {
        throw new InvalidOrderException("amount must be non-negative");
    }
}
```

If the writer validates the entire chunk up front, one invalid item fails the whole write call. If a skip policy is enabled, the framework may need to isolate the bad item. When items must be rejected individually, validating in the processor typically identifies and records errors more cleanly before the writer receives the chunk.

Do not mutate items or strip items out of the chunk inside the writer. Perform data transformations in the processor so output types and counters remain consistent.

## 22. Logging and Metrics

The writer is a good place to record chunk-level write telemetry:

- `Job`/`Step` name or operation category.
- Number of items in the chunk.
- Write execution duration.
- Target destination or destination type.
- Success or failure outcome.
- Exception category and retry attempt when context is available.

Avoid logging full items or sensitive payloads. Do not use order IDs or customer IDs as high-cardinality metric tags. When item-level traceability is required, use structured logging with appropriate access controls.

`afterWrite` only indicates that the writer returned normally; the chunk transaction can still roll back afterward. When reporting "committed" metrics, observe after actual commit or via appropriate metadata/counters—never conflate write success with transaction commit.

## 23. Testing a Custom ItemWriter

Write unit tests for writer logic and integration tests for transaction/`Step` behavior.

### Unit Testing with Mock Collaborators

Example JDBC writer test:

```java
@Test
void writesEveryItemInChunk() {
    JdbcTemplate jdbcTemplate = mock(JdbcTemplate.class);
    JdbcOrderWriter writer = new JdbcOrderWriter(jdbcTemplate);

    OrderExport first = new OrderExport(
            1001L, "C001", new BigDecimal("250000.00"), "VND");
    OrderExport second = new OrderExport(
            1002L, "C002", new BigDecimal("175000.00"), "VND");

    Chunk<OrderExport> chunk = new Chunk<>();
    chunk.add(first);
    chunk.add(second);

    writer.write(chunk);

    verify(jdbcTemplate, times(2)).update(
            anyString(), any(), any(), any(), any());
}
```

The test verifies that the writer passes every item to its collaborator. You can check exact parameters per call with `ArgumentCaptor` when field mapping is critical.

### Testing Exception Propagation

```java
@Test
void propagatesDatabaseFailure() {
    JdbcTemplate jdbcTemplate = mock(JdbcTemplate.class);
    when(jdbcTemplate.update(
            anyString(), any(), any(), any(), any()))
            .thenThrow(new DataAccessResourceFailureException("database down"));

    JdbcOrderWriter writer = new JdbcOrderWriter(jdbcTemplate);
    Chunk<OrderExport> chunk = new Chunk<>();
    chunk.add(new OrderExport(
            1001L, "C001", new BigDecimal("250000.00"), "VND"));

    assertThatThrownBy(() -> writer.write(chunk))
            .isInstanceOf(DataAccessResourceFailureException.class);
}
```

The goal is verifying that the writer does not swallow exceptions. Real tests should match the mock signature to the exact `JdbcTemplate` overload in the project's Spring Framework version.

### Transaction Integration Testing

With a test database, construct a chunk with multiple items and force one write statement to fail. After the `Step` rolls back, verify no rows from the uncommitted chunk exist if all operations share the transaction. Also verify that previously committed chunks remain intact.

### Testing Retry, Skip, and Restart

- Writer hits transient error then succeeds: verify invocation count and final data.
- Writer hits data error: verify skip/fail behavior per policy.
- Retry exhaustion: verify `Step` status and failure exception.
- Restart: verify writer reopens the right resource and state.
- External sink: verify identical idempotency keys avoid duplicate side effects.
- Concurrent execution: verify state and outputs of separate `Job`s do not mix.

## 24. Common Mistakes

### Treating a Chunk as a Single Item

In Spring Batch 5, `write` accepts `Chunk`, not a single object. Iterate over all items in the chunk and understand the chunk size configured on the `Step`.

### Using the Legacy List Signature

`write(List<? extends T>)` does not match the Spring Batch 5 interface. Use the `write(Chunk<? extends T>)` signature matching the current version.

### Swallowing Exceptions and Only Logging

The framework assumes the write succeeded and may commit the chunk. Let exceptions propagate so retry, skip, or fail policies trigger.

### Manually Committing Transactions

Committing inside the writer breaks the chunk transaction boundary. Let Spring Batch coordinate transactions.

### Calling Non-Idempotent APIs in a Writer

Retries after timeouts can repeat side effects. Use idempotency keys, outboxes, or reconciliation.

### Forgetting the ItemStream Lifecycle When Wrapping a Writer

Delegates may not be opened, checkpointed, or closed. Forward `open`, `update`, and `close`.

### Keeping Mutable State in a Singleton

Concurrent executions can overwrite each other's state. Use stateless writers, `StepScope`, or explicit synchronization/ownership.

### Putting Deep Business Validation in the Writer

It becomes difficult to isolate failing items and apply skips. Validate data before the writer, typically in the processor.

### Assuming Write Success Means Committed

The transaction can still roll back after the write callback returns. Distinguish writer completion from chunk commit.

### Reimplementing Built-In Writers

Custom code can miss checkpointing, encoding, rollback, and restart edge cases. Prefer built-in writers when they satisfy requirements.

## 25. Custom ItemWriter Design Workflow

When writing a custom writer, follow this sequence:

1. Identify the output type and target destination.
2. Check whether a built-in writer already meets requirements.
3. Choose stateless `ItemWriter<T>` or stateful/resource-managing `ItemStreamWriter<T>`.
4. Implement `write(Chunk<? extends T>)` and process all items in the chunk.
5. Let exceptions propagate; wrap with causes if additional context is needed.
6. Verify the transaction manager and whether resources participate in chunk transactions.
7. Never commit or roll back manually inside the writer.
8. If there are external side effects, design idempotency keys, outboxes, or deduplication.
9. If the writer is stateful, implement `open`, `update`, and `close` and store compact state in `ExecutionContext`.
10. Ensure the writer is thread-safe or scoped per `StepExecution`.
11. Register the writer as a bean and inject it into the `Step`.
12. Add an `ItemWriteListener` for metrics/auditing if needed, without replacing writer logic.
13. Unit test chunk mapping and exception propagation.
14. Integration test transactions, retries, skips, restarts, and concurrency.

| Need | Choice |
|---|---|
| Stateless writer, database write in same transaction | `ItemWriter<T>` + `JdbcTemplate` sharing DataSource/transaction manager |
| Writer managing files/cursors and checkpoints | `ItemStreamWriter<T>` |
| Wrapping a built-in writer for validation | Decorator forwarding `write`, `open`, `update`, `close` |
| Writing to an external API | Custom writer with timeouts, retry policy, and idempotency |
| Writing the same items to multiple targets | `CompositeItemWriter` if suitable; verify per-target transaction behavior |
| Only logging/metrics around writes | `ItemWriteListener` |

## Conclusion

Write a custom `ItemWriter<T>` in Spring Batch 5 by implementing `write(Chunk<? extends T>)` and processing every item in the chunk according to the destination contract. A writer should focus on writing, propagate exceptions to the framework, and let the `Step` manage transactions, retries, skips, and commits. If the writer manages resources or needs checkpoints, implement `ItemStreamWriter<T>` and forward `open`, `update`, and `close`; when calling external systems, guarantee idempotency because retries can repeat side effects. Keep writers stateless and thread-safe whenever possible, use appropriate DTOs, test exception propagation, transactions, restarts, and concurrency, and prefer built-in writers whenever they meet your requirements.
