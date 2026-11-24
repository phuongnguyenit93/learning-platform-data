# Rollback when the reader, processor, or writer fails

In Spring Batch, a chunk Step typically processes data in transactions whose boundaries follow the chunk. If an error occurs while reading, processing, or writing an item, the transaction of the current chunk may be rolled back. The changes belonging to that transaction are undone if the resources participate in the same transaction manager; chunks committed earlier are kept.

Understanding rollback correctly helps you determine which data has been saved, which components may be called again, and when you need to restart the Job. The reader, processor, and writer each produce errors in different ways, but all of them sit within the chunk processing cycle. You need to distinguish a database rollback from side effects in external systems such as files, message queues, or HTTP APIs, because those side effects are not automatically undone by an ordinary JDBC transaction.

## 1. Transaction boundaries in chunk processing

A chunk Step reads, processes, and writes a group of items before committing. For example, with `chunk(100, transactionManager)`, Spring Batch processes at most 100 items in a chunk and then commits the transaction. The last chunk may be smaller if the reader has run out of data.

```text
Chunk 1                         Chunk 2
BEGIN                           BEGIN
  Reader                           Reader
  Processor                        Processor
  Writer                           Writer
COMMIT                          Writer throws exception
                                ROLLBACK
                                (Chunk 2 is not committed)

Chunk 3 (if the Step continues per policy)
BEGIN
  Reader / Processor / Writer
COMMIT
```

Each chunk has its own transaction boundary. Therefore:

- If chunk 1 has committed, chunk 1's data still exists when chunk 2 rolls back.
- If chunk 2 has not committed, the database changes participating in chunk 2's transaction are undone.
- After the error is handled by skip/retry or the Job is restarted, Spring Batch can continue according to the policy and the saved state.
- Rollback does not mean the whole Job is returned to its initial state.

The transaction manager is passed in when configuring the chunk Step:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

In the example, the transaction manager coordinates the transaction for each chunk. If the writer uses the same datasource and transaction manager, the writer's database writes can participate in that transaction.

## 2. What happens when the reader, processor, or writer fails?

An error can arise at any stage of the cycle:

```text
ItemReader
   |
   +-- exception --> rollback chunk / skip / retry / fail
   |
   v
ItemProcessor
   |
   +-- exception --> rollback chunk / skip / retry / fail
   |
   v
ItemWriter
   |
   +-- exception --> rollback chunk / skip / retry / fail
   |
   v
Commit
```

The specific behavior depends on the transaction manager, rollback rules, fault tolerance configuration, and exception type. If an exception is allowed to be retried or skipped, the framework can perform additional operations to continue. If the error is not handled by the policy, the Step typically ends in the `FAILED` state.

| Component | Example error | Common effect |
|---|---|---|
| Reader | A CSV line cannot be parsed, the data source connection is lost | The current chunk may roll back; the exception is skipped/retried or fails the Step. |
| Processor | Data missing a required field, a calculation error, or a reference service timeout | The current chunk may roll back; the item may be skipped/retried per configuration. |
| Writer | Database timeout, constraint violation, or batch write error | Changes in the current write transaction may roll back; the writer may be called again during error handling. |

Do not assume every exception has the same policy. You need to classify data errors that can be skipped, transient errors that can be retried, and serious errors that must fail the Step.

## 3. Rollback when ItemReader fails

`ItemReader` is responsible for obtaining items from the data source. A reader can read from CSV, a database, a message queue, an API, or other sources. When the reader throws an exception, the chunk being processed may roll back according to the Step's transaction and rollback rules.

For example, a file reader encountering a malformed line:

```java
@Bean
FlatFileItemReader<OrderInput> orderReader(
        Resource inputResource) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(inputResource)
            .delimited()
            .names("orderId", "customerId", "amount")
            .targetType(OrderInput.class)
            .build();
}
```

If a line of data cannot be parsed, the reader may throw `FlatFileParseException`. If this exception is configured to be skipped and the reader can continue reading, the Step can skip the faulty line. If it is not skipped, the error may fail the Step.

### The reader may be called again after a rollback

With many readers that are not transactional sources, rolling back the database transaction cannot return the read source to its previous state. For example, a JDBC rollback does not make a physical file “roll back” to the previous line or undo a GET request already sent to an API.

Spring Batch has a mechanism for buffering the items already read in a chunk to support rollback/retry. By default, items already read may be retained so they do not have to be re-read from the source when the transaction rolls back. For transactional sources such as some message queues, the reader can be configured according to the transactional queue model so that a rollback returns the message to the queue instead of relying on the default buffer.

When using a custom reader, you need to understand clearly whether it supports `ItemStream`, whether it stores state, and whether it can restore the read position. Do not assume every data source can roll back a read operation.

### Read errors and skip

A read skip occurs when the reader throws an exception configured to be skippable:

```java
.faultTolerant()
.skip(FlatFileParseException.class)
.skipLimit(50)
```

`SkipListener.onSkipInRead` receives the exception but not the item, because the reader may not have been able to create a complete item. If you need to record the error position, you can use the line or data source information that the exception provides.

Do not skip a database connection loss exception or a general infrastructure error just to let the Job continue. If the reader cannot guarantee that it reads the next piece of data correctly, the Step should fail so that it can be investigated or restarted.

## 4. Rollback when ItemProcessor fails

`ItemProcessor` validates or transforms an item. When `process` throws an exception, the chunk step handles the exception according to the rollback rules and the configured skip/retry policy.

For example:

```java
public class OrderProcessor implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput item) {
        if (item.amount() == null || item.amount().signum() <= 0) {
            throw new InvalidOrderException("Order amount must be positive");
        }

        return toOrder(item);
    }
}
```

If `InvalidOrderException` is allowed to be skipped, Spring Batch can skip the faulty item and continue. If the exception is not skipped and cannot be retried successfully, the Step may fail. If the exception is retried, the processor may be called again for that item.

### The processor should limit side effects

A processor should typically focus on computation and object transformation. If the processor sends email, writes files, or calls external APIs, those operations do not roll back automatically when the database transaction rolls back.

An unsafe example:

```java
@Override
public Order process(OrderInput item) {
    notificationClient.send("Processing order " + item.orderId());
    return toOrder(item);
}
```

If the chunk rolls back and the processor is called again, the notification may be sent multiple times. A safer approach is to produce the result in the processor and then emit the notification via an outbox or a separate Step that has a mechanism to prevent duplicate sends.

### noRollback for certain exceptions

In some cases, an application can determine that an exception does not require rolling back the transaction. Spring Batch supports configuring `noRollback(...)` for a chunk step:

```java
.faultTolerant()
.noRollback(NonCriticalValidationException.class)
```

Only use this option when you clearly understand the transaction state and the side effects of the exception. If the exception occurs after part of the work has already changed data without rollback, the Step must continue in a consistent state. Do not use `noRollback` to mask database write errors or to avoid rollback without analysis.

## 5. Rollback when ItemWriter fails

`ItemWriter` receives the items that have been read and processed in the chunk. A writer typically writes multiple items in one call, such as a batch insert or batch update. If the writer throws an exception, the chunk transaction is typically rolled back.

An example writer writing to a database:

```java
@Bean
JdbcBatchItemWriter<Order> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO orders
                        (order_id, customer_id, amount)
                    VALUES
                        (:orderId, :customerId, :amount)
                    """)
            .beanMapped()
            .build();
}
```

If the writer writes some records and then hits an error, and all write operations participate in the same transaction, the database rollback will undo the changes in that transaction. Earlier chunks that have committed still exist.

### The writer may be called again

When there is a write error and skip/retry is configured, Spring Batch can roll back the chunk, retry the operation, or analyze the items to identify the item causing the error. In some write skip processing paths, the writer may be called again with smaller groups of items or with individual items to find the faulty record.

Therefore, the writer must be designed to tolerate being called again. With a JDBC writer participating in the transaction, a rollback can undo the earlier write. But if the writer calls an API, writes a file, or sends a message outside the transaction, the side effect may already have happened and the repeated call may produce duplicate results.

### Write skip

If an exception from the writer is configured to be skipped, Spring Batch can skip the item causing the error if the framework can identify that item and continuing is safe:

```java
.faultTolerant()
.skip(DuplicateOrderException.class)
.skipLimit(100)
```

A writer failure due to a constraint can be an error specific to the item's data, or it can reflect a broader problem such as a wrong schema, a lost database connection, or a transaction timeout. Only skip exceptions that the business allows to be ignored. Do not skip every `DataAccessException`, because that can let the Job complete with missing data caused by a system failure.

## 6. The current chunk rolls back, earlier chunks remain committed

A Job processing 1,000 items with a chunk size of 100 typically has many transactions. Suppose the first four chunks commit successfully and the fifth chunk hits a writer error:

| Chunk | Status | Database data |
|---|---|---|
| 1 (items 1–100) | `COMMITTED` | Kept. |
| 2 (items 101–200) | `COMMITTED` | Kept. |
| 3 (items 201–300) | `COMMITTED` | Kept. |
| 4 (items 301–400) | `COMMITTED` | Kept. |
| 5 (items 401–500) | `ROLLED BACK` | Changes belonging to chunk 5's transaction are undone. |
| 6 onward | Not yet run | Waiting for the Step to continue or be restarted. |

Rollback does not delete the data of the four committed chunks. If the Step fails, the Job can be restarted according to the policy and the saved checkpoint. The reader/writer need to support restart, and write operations need to be safe when re-run.

This is an important reason to choose an appropriate chunk size. A chunk that is too large can increase the amount of work in one transaction and the number of items that must be reprocessed. A chunk that is too small can increase commit and metadata costs.

## 7. Configuring skip and retry when the reader, processor, or writer fails

Spring Batch lets you classify exceptions and apply skip/retry on a chunk step:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(FlatFileParseException.class)
        .skip(InvalidOrderException.class)
        .skipLimit(100)
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
```

In the example:

- A malformed CSV line can be skipped if the reader continues safely.
- An item that violates business rules can be skipped according to the policy.
- A transient database error can be retried up to the limit.
- An error not covered by the skip/retry policy can fail the Step.

Retry suits errors that are likely to recover on their own, for example a transient timeout or a deadlock. Skip suits item errors that are known to be ignorable. Configuration errors, prolonged connection loss, or unreliable source data usually need to fail the Step.

When retries reach their limit, the exception can still fail the Step if there is no appropriate skip policy. Avoid configuring skip and retry too broadly for the same group of exceptions without clearly understanding the final behavior.

## 8. Rollback and skip listeners

`SkipListener` provides callbacks to record items skipped at each stage:

```java
public class OrderSkipListener implements SkipListener<OrderInput, Order> {

    @Override
    public void onSkipInRead(Throwable exception) {
        log.warn("Read skip: {}", exception.getMessage());
    }

    @Override
    public void onSkipInProcess(OrderInput item, Throwable exception) {
        log.warn("Process skip for order {}: {}",
                item.orderId(), exception.getMessage());
    }

    @Override
    public void onSkipInWrite(Order item, Throwable exception) {
        log.warn("Write skip for order {}: {}",
                item.orderId(), exception.getMessage());
    }
}
```

A listener is useful for producing reject reports or logging business keys. However, when saving a faulty item to the database, you need to understand the transaction and the timing of the callback. Do not assume a standalone reject write is always committed together with the chunk's transaction or is never called again. You can use an appropriate transaction manager/repository, an outbox, or an idempotent audit mechanism to avoid duplicate error records and maintain consistency.

## 9. Reader buffering, ItemStream, and checkpoints

A transaction rollback does not necessarily return the reader to the exact original state of the source. Spring Batch typically buffers the items already read in a chunk so they can be reprocessed after a rollback without re-reading the source. With a transactional queue, you can configure `readerIsTransactionalQueue()` when the reader uses a source where a rollback returns messages to the queue.

Readers/writers can implement `ItemStream` to manage state through callbacks:

- `open(ExecutionContext)`: restores state when the Step starts or restarts.
- `update(ExecutionContext)`: writes the checkpoint that needs to be saved.
- `close()`: releases resources.

The checkpoint is typically stored in the Step `ExecutionContext` via the JobRepository at update points appropriate to the chunk. On restart, the reader can continue from the last committed position.

An example of the idea of saving the read position:

```java
public class StatefulReader implements ItemStreamReader<OrderInput> {

    private int currentIndex;

    @Override
    public void open(ExecutionContext context) {
        currentIndex = context.getInt("currentIndex", 0);
    }

    @Override
    public void update(ExecutionContext context) {
        context.putInt("currentIndex", currentIndex);
    }

    @Override
    public void close() {
        // Close the resource if the reader is holding one.
    }

    @Override
    public OrderInput read() {
        // Read the item at currentIndex and increment the index when there is an item.
        return readNextItem();
    }
}
```

This is an illustrative skeleton; a real reader needs to handle the data source, the end-of-data state, thread safety, and the exact rules for updating the index. Do not update the checkpoint before the corresponding work has been committed if that could cause a restart to skip items that have not been written.

## 10. A transaction only rolls back resources participating in the transaction

A JDBC transaction manager typically coordinates transactions on the configured datasource. It does not automatically create a distributed transaction across every resource the Step uses.

For example:

| Task in the chunk | Can it roll back with the JDBC transaction? |
|---|---|
| `INSERT` via the same datasource/transaction manager | Yes, if the operation participates in that transaction. |
| `UPDATE` on the same database connection transaction | Yes. |
| Writing to another database with a different transaction manager | Not automatically. |
| Sending an HTTP request to an external service | No. |
| Sending email | No. |
| Writing a file on the filesystem | No. |
| Publishing a message to a broker that does not participate in the transaction | Not automatically. |

If the writer performs both a database write and an API call, a transaction rollback can only undo the managed database part. The API may have already processed the request. When the chunk is retried, the API may receive the same request again.

Commonly used approaches:

- Design the API to accept an idempotency key to recognize repeated requests.
- Write the business data and an outbox event in the same transaction, then publish the outbox with a separate component.
- Split the external side effect into a separate Step after the main data has committed.
- Use a business key and a reconciliation process to detect results that have already been processed.

## 11. Rollback rules and checked exceptions

Rollback behavior is influenced by the transaction attribute and rollback rules. In the Spring ecosystem, the general default of a transaction attribute is typically to roll back on `RuntimeException` and `Error`; checked exceptions may need an explicit rollback rule depending on how the exception propagates through the transaction layer and the Step configuration.

When designing exceptions for the reader, processor, or writer:

- Use specific exceptions to distinguish data errors from system errors.
- Determine which exceptions must roll back the transaction.
- Determine which exceptions can be retried or skipped.
- Only use `noRollback` for cases where you clearly understand data consistency.
- Check the actual transaction manager and transaction attribute in the application configuration.

Do not infer rollback solely from whether an exception is checked or unchecked without looking at the path the exception takes through Spring Batch and the transaction manager. Test with the actual transaction manager, especially if the writer has multi-step operations.

## 12. Tracking rollbacks in StepExecution

`StepExecution` stores counters useful for diagnosis:

| Counter | Meaning |
|---|---|
| `readCount` | Number of items read successfully. |
| `writeCount` | Number of items written by the writer according to Step statistics. |
| `filterCount` | Number of items the processor filtered by returning `null`. |
| `readSkipCount` | Number of items skipped during read. |
| `processSkipCount` | Number of items skipped during processing. |
| `writeSkipCount` | Number of items skipped during write. |
| `commitCount` | Number of transaction commits. |
| `rollbackCount` | Number of transaction rollbacks. |

For example, a steadily increasing `rollbackCount` can indicate that the writer is hitting errors, a database deadlock, or a timeout. An increasing `processSkipCount` can indicate that the source data is invalid. Combine the counters with the failure exception, logs, reader position, and the target data results.

The counters do not replace business auditing. A Step may be `COMPLETED` but still have items that were filtered or skipped per policy. To understand which data was excluded, you need to store the business key and the reason via an appropriate audit mechanism.

## 13. Restart after a chunk rollback

If an exception is not handled by skip/retry and the Step fails, the Job can be restarted if the JobInstance and the configuration allow it. Spring Batch creates a new `JobExecution` for the re-run, while the earlier execution history is retained.

On restart:

- Chunks that committed earlier are typically not reprocessed in the same Step restart.
- A chunk that did not commit is not considered complete.
- The reader can restore the checkpoint from the ExecutionContext if it supports restart.
- The writer needs to avoid duplicate writes if side effects have already occurred outside the transaction.
- A completed Step is typically skipped; `allowStartIfComplete(true)` can allow a completed Step to re-run in an appropriate restart.

Do not delete metadata or directly edit the `BATCH_STEP_EXECUTION` state to force a restart. Before restarting, determine which chunks have committed, whether the read source has a stable checkpoint, and which side effects the external systems have already received.

## 14. Example: the writer fails and the chunk rolls back

Suppose a Step reads 300 orders with a chunk size of 100. The first two chunks are written successfully. In the third chunk, the writer fails because one record violates a unique constraint.

If the exception is not skipped:

1. The writer throws an exception within the third chunk's transaction.
2. The transaction manager rolls back the write operations belonging to the third chunk.
3. The Step records the error and may end as `FAILED`.
4. The two committed chunks remain in the database.
5. If the Job is restarted, the reader continues from the appropriate saved checkpoint and the Step processes the unfinished portion.

If the exception is configured to be skipped and the framework can identify the faulty item:

1. The chunk may roll back to be reprocessed under the fault tolerance mechanism.
2. The item causing the error is skipped according to the skip policy.
3. The remaining items are written if the writer and transaction allow it.
4. The skip count is updated and `SkipListener` can record the item.
5. The Step continues until the data runs out or another error occurs.

This shows that a write skip can be more complex than a process skip because the writer receives the whole chunk. The writer needs consistent behavior when called again and must not create uncontrolled side effects outside the transaction.

## 15. Common mistakes when handling rollback

### Thinking rollback will delete the data of earlier chunks

Each chunk has its own transaction. Rollback only affects the current uncommitted transaction and the resources participating in that transaction. Earlier committed chunks still exist.

### Thinking the reader always returns to the exact old position in the source

The read source may not be transactional. Spring Batch may buffer items already read; a custom reader needs to support `ItemStream` and checkpoints if it wants stable restarts. Check the source type and how the reader manages state.

### The writer writes part of the data and then throws an exception, but there is no appropriate transaction

If a write operation does not participate in the transaction or the writer calls an external system, part of the side effects may remain after a rollback. Use the transaction manager matching the resource, idempotency, or an outbox.

### The processor calls an API and then the chunk rolls back

A database rollback does not undo an API call. The processor may be called again on retry, causing duplicate requests. Limit side effects in the processor or use an idempotency key.

### Skipping every exception so the Job always completes

Database errors, configuration errors, or programming errors cannot always be ignored. Only skip item-level exceptions that are understood and permitted by the business.

### Using noRollback to avoid every rollback

Not rolling back can retain partial changes and leave the data in an inconsistent state. Only configure noRollback for specific exceptions after clearly analyzing the impact.

### Restarting without checking side effects outside the transaction

A file may have been moved, a message published, or an API may have received the request even though the Step did not get to record the completed state. Check the actual data and ensure idempotency before restarting.

## 16. Procedure for diagnosing reader, processor, or writer errors

When a chunk rolls back, you can investigate in this order:

1. Identify the failed JobExecution and StepExecution.
2. Read the failure exception and stack trace to learn whether the error appeared in the reader, processor, or writer.
3. Look at `rollbackCount`, `commitCount`, the read/write/skip counts, and the update time.
4. Identify the current uncommitted chunk and the earlier committed chunks.
5. Check whether the transaction manager, datasource, and resources participate in the transaction.
6. See whether the reader has buffering, `ItemStream`, and a stable checkpoint.
7. Check whether the writer or processor has side effects outside the transaction that have already occurred.
8. Decide whether the error should be retried, skipped, or fail the Step.
9. Before restarting, reconcile the business data and design to prevent duplicate writes/sends.

## Conclusion

When the reader, processor, or writer fails in a chunk Step, the current chunk's transaction is typically rolled back according to the rollback rules and the transaction manager. Chunks committed earlier are kept. The reader may need buffering or a checkpoint to recover its position; the processor should limit side effects because it can be called again; the writer needs to participate in the transaction or have an idempotency mechanism when writing to external systems. Skip and retry allow some errors to be handled in a controlled manner, while errors from which it is not safe to continue should fail the Step for investigation or restart.
