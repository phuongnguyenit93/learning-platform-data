# Reader Failures Midway in Spring Batch

In chunk-oriented processing, an `ItemReader` supplies items to the step one at a time. A reader can read from a file, a database, a message queue, an API, or a custom data source. While reading, the source can encounter errors: a malformed file line, a lost database connection, an API timeout, or data that cannot be decoded. When an error occurs midway, Spring Batch must decide whether to retry the read operation, skip the faulty record, or stop the step.

It is important to distinguish a **read error** from the **end of input**. `ItemReader.read()` returning `null` means there are no more items; throwing an exception means the read operation encountered an error. If you turn an error into `null`, the job may end successfully even though the data after it has not been fully read.

## 1. The ItemReader Contract and Midway Failures

The basic contract of `ItemReader<T>` is very simple:

- Return an item when the next piece of data is read.
- Return `null` when the source is out of data.
- Throw an exception when the read operation cannot be completed.

Example of a reader that reads orders from a data source:

```java
public class OrderReader implements ItemReader<Order> {

    private final Iterator<Order> orders;

    public OrderReader(List<Order> source) {
        this.orders = source.iterator();
    }

    @Override
    public Order read() {
        if (!orders.hasNext()) {
            return null; // EOF: no more items
        }
        return orders.next();
    }
}
```

With a real reader, an error can appear after some items have already been read successfully. For example, a file has 1,000 lines but line 501 is malformed. The reader has provided the earlier lines, and then throws `FlatFileParseException` when parsing the faulty line.

```text
Lines 1..500     -> read successfully
Line 501         -> parse error
Lines 502..1000  -> not yet read
```

Spring Batch cannot infer on its own whether that error is bad data that can be skipped or an infrastructure error that requires stopping. The application must configure a policy appropriate to the exception type and the business requirements.

## 2. Distinguishing Read Errors, EOF, and Invalid Data

The following three situations have different meanings:

| Situation | Reader behavior | Meaning |
| --- | --- | --- |
| Out of data | Returns `null` | Normal end of input. |
| An item is read | Returns an object | Passes the item to the processor if one is configured. |
| Cannot read or parse | Throws an exception | There is an error that needs to be retried, skipped, or made to fail the step. |

Example with a CSV file:

- The file has been read to the end: the reader returns `null`.
- A line has all the columns and the correct format: the reader returns an `Order` object.
- A line is missing a required column or contains a value that cannot be converted: the reader may throw `FlatFileParseException`.
- The file cannot be opened due to access permissions or a wrong path: the reader may throw an I/O exception. This is usually a configuration or environment error and should not automatically be treated as a data line that can be skipped.

Do not write a reader like `catch (Exception e) { return null; }`. That approach turns an error midway through the source into an EOF signal, causing the remaining items to be skipped and the step to possibly be marked complete. Let the exception propagate or convert it into a meaningful exception for the fault tolerance policy to handle.

## 3. Common Types of Read Errors

### Data Format Errors

The source may contain a record with the wrong structure, missing fields, the wrong data type, or that does not satisfy the parsing rules. With a file reader, Spring Batch can provide information such as the faulty line through `FlatFileParseException`. This is usually a candidate for skip if the business allows continuing without processing that record.

### Temporary Connection Errors

A database connection reset, a socket timeout, or a remote service temporarily not responding can be transient errors. If the operation can be safely performed again, retry may be more appropriate than skip. Skipping a connection error can cause a large block of data to go unread while the job keeps running.

### Authentication or Configuration Errors

An expired credential, revoked access permission, wrong file name, or a nonexistent schema is usually not resolved by repeated retries or by skipping a record. These are usually errors that require stopping the job to fix the configuration or access permissions.

### Data or Source State Errors

A custom reader may encounter corrupted data, a cursor that is no longer valid, an expired pagination token, or a source that changes while being read. You need to determine whether the error belongs to an individual item or makes it impossible to continue traversing the source.

## 4. Choosing Between Retry, Skip, and Fail

Spring Batch provides a fault-tolerant chunk step to handle recoverable errors. The decision usually depends on the nature of the error:

| Strategy | Use when | Desired result |
| --- | --- | --- |
| Retry | The error is transient and the read operation can be safely retried. | Retry the operation up to the configured limit. |
| Skip | A specific record is invalid and can be excluded from this run according to a business rule. | Skip the faulty item and continue reading the next items. |
| Fail | An infrastructure, configuration, or data error where continuing could make the result wrong. | Stop the step/job to deal with the cause. |

Examples:

- A CSV line is malformed but the other lines are still independent: it can be skipped if the business accepts it.
- An API temporarily returns a timeout but can be called again with the same cursor/token: it can be retried.
- Unable to authenticate with the database or unable to read a mandatory input file: it usually should fail.

Do not configure `skip(Exception.class)` broadly. An exception that is too broad can cause connection errors, programming errors, or serious data errors to be skipped. Classify specific exceptions and skip only the cases that the application can prove are safe to skip.

## 5. Configuring Skip for Read Errors

With a chunk step, you can enable fault tolerance and declare the exceptions that are allowed to be skipped:

```java
@Bean
Step importOrdersStep(JobRepository jobRepository,
                      PlatformTransactionManager transactionManager,
                      ItemReader<Order> orderReader,
                      ItemProcessor<Order, Order> orderProcessor,
                      ItemWriter<Order> orderWriter) {
    return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(FlatFileParseException.class)
        .skipLimit(10)
        .build();
}
```

In this example, the step allows skipping up to the number of errors set by the configured `skipLimit`, with `FlatFileParseException` as the skippable exception type. If the limit is exceeded, the step fails. The skip limit is counted jointly across read, process, and write errors in the step; it is not an independent quota for each phase.

When the reader encounters a line with a parse error, Spring Batch can apply the skip policy, record a read skip, and continue with the next data if the reader can safely continue. With `FlatFileItemReader`, the parse exception usually carries the line information and the faulty content, which helps with logging or recording the record that needs to be reprocessed.

Skip should be used only when the faulty item can be removed without breaking the correctness of the whole batch. If one bad record makes the following records impossible to interpret correctly, or the input data has a structural shift from some position onward, fail may be the more appropriate choice.

## 6. Configuring Retry for Transient Read Errors

For errors that are likely to clear up after a period of time, you can configure retry:

```java
@Bean
Step readRemoteOrdersStep(JobRepository jobRepository,
                          PlatformTransactionManager transactionManager,
                          ItemReader<Order> remoteOrderReader,
                          ItemWriter<Order> orderWriter) {
    return new StepBuilder("readRemoteOrdersStep", jobRepository)
        .<Order, Order>chunk(50, transactionManager)
        .reader(remoteOrderReader)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
}
```

Here, `TransientDataAccessException` represents the group of data access errors that may be temporary. `retryLimit` limits the number of attempts according to Spring Batch's policy. When recovery is not possible within that limit and there is no appropriate skip policy, the step will fail.

Retry is useful only if the repeated call has a chance of succeeding and does not cause unwanted side effects. The reader must be designed so that a failed read does not silently lose or jump over an item. With a paginated API, you need to know whether the current page token is preserved after a timeout. With a cursor, you need to know how the connection and read position can be recovered.

You can combine retry and skip, but you need to understand the order as well as the interaction of the retry policy, skip policy, and rollback. A transient error can be retried; if it still fails afterward, it can be skipped only when that exception type is also allowed and skipping fits the business. Do not use skip as a fallback for every retry that has run out of attempts.

## 7. Not Every Read Error Can Be Skipped

An exception that occurs in `read()` does not always represent a distinct item. For example:

- `FlatFileParseException` can identify a specific faulty line.
- A field conversion error may affect only one record.
- A lost database connection may leave the reader not knowing where the cursor is.
- An authentication or schema error may make the entire source unreadable.

With a per-record error, skip can continue from the next item if the reader supports it. With a source or connection error, skipping may be meaningless because the reader cannot determine the next record. If you are not sure the reader is still at a valid position, fail and recover the source instead of assuming it can be skipped.

When you need control by complex conditions, you can provide your own `SkipPolicy` instead of just declaring an exception class. The policy should limit the error types, limit the number of skips, and record the reason so that operators know which data was not processed.

## 8. Monitoring Errors with ItemReadListener

`ItemReadListener<T>` provides callbacks to observe the reading process:

- `beforeRead()` runs before a reader call.
- `afterRead(T item)` runs after an item is read.
- `onReadError(Exception ex)` runs when the reader throws an exception.

Example of logging when the reader encounters an error:

```java
public class OrderReadListener implements ItemReadListener<Order> {

    private static final Logger log =
        LoggerFactory.getLogger(OrderReadListener.class);

    @Override
    public void beforeRead() {
        // Can record a metric or trace before the read operation.
    }

    @Override
    public void afterRead(Order item) {
        // Do not write the item's sensitive data in full to the log.
    }

    @Override
    public void onReadError(Exception ex) {
        log.warn("Cannot read the next order", ex);
    }
}
```

Register the listener with the step:

```java
.listener(new OrderReadListener())
```

A listener helps observe errors but does not decide retry or skip by itself. It is the fault tolerance policy that decides how the framework handles the exception. Avoid performing non-idempotent business operations in `onReadError()`, because the callback may be called again when the read operation is retried.

## 9. Recording Skipped Records with SkipListener

When a read error is accepted for skipping, `SkipListener` has the callback `onSkipInRead(Throwable t)`. Unlike skips in the processor or writer, the read callback does not receive the input item because the reader was unable to create a valid item.

```java
public class OrderSkipListener implements SkipListener<Order, Order> {

    private static final Logger log =
        LoggerFactory.getLogger(OrderSkipListener.class);

    @Override
    public void onSkipInRead(Throwable t) {
        log.error("An input record was skipped", t);
    }

    @Override
    public void onSkipInProcess(Order item, Throwable t) {
        log.error("Order {} was skipped during processing", item.getId(), t);
    }

    @Override
    public void onSkipInWrite(Order item, Throwable t) {
        log.error("Order {} was skipped during writing", item.getId(), t);
    }
}
```

Register the listener:

```java
.listener(new OrderSkipListener())
```

With a read skip, the exception may contain the line or faulty record information, depending on the reader. If you need to store the faulty data in a quarantine table, extract the safe information from the exception and do it in a mechanism with an appropriate transaction, idempotency, and retry capability. `SkipListener` is called when the framework determines that an item is skipped; do not assume the exception always contains the entire input content.

Spring Batch designs the skip callback to notify that an item was skipped exactly once within the chunk's skip-processing scope. When writing faulty data to a system outside the transaction, you still need to guard against duplicate writes and handle the case where the chunk transaction rolls back.

## 10. How Does a Reader Failure Mid-Chunk Affect the Transaction?

Chunk-oriented processing manages a group of items within a transaction boundary. If the reader throws an exception and the exception is not handled by retry or skip, the current chunk cannot complete as a successful chunk; the transaction will be handled according to the step's rollback behavior.

Example with a commit interval of 100:

```text
Read items 1..60
       |
       v
The reader encounters an exception on the next read
       |
       +---- If the error is retried and the re-read succeeds
       |          -> continue gathering the chunk
       |
       +---- If the error is skipped and the reader can continue
       |          -> record a read skip, continue processing
       |
       +---- If the error cannot be retried/skipped
                  -> roll back the transaction
                  -> the step/job fails
```

On rollback, the transactional changes in the uncommitted chunk are undone. The earlier committed chunks remain in effect. Therefore, a midway error usually does not mean the entire job returns to its initial state; it usually stops at the nearest commit boundary.

If the reader reads from a resource that does not participate in the target database's transaction, a database rollback does not automatically return the reader to the correct position before reading. The framework has buffering mechanisms and readers have their own state, but a custom reader must still ensure that the read behavior is recoverable. Do not assume that every file, API, or queue source automatically rolls back together with the database transaction.

## 11. Restart After a Reader Failure

When a job fails and is restarted, Spring Batch uses the metadata in the `JobRepository` together with the `ExecutionContext` to determine the committed progress. Readers that support restart typically implement `ItemStream`:

- `open(ExecutionContext)` restores the previous state or initializes the reader.
- `update(ExecutionContext)` writes the current state to save a checkpoint.
- `close()` releases resources.

With `FlatFileItemReader`, the read state can be saved so that on restart the reader continues from the appropriate position. Give the reader a stable name and enable state saving if restart is needed. Many built-in readers support this mechanism; a custom reader must implement checkpointing correctly itself.

The checkpoint is usually saved at the commit boundary. If an error occurs before the current chunk commits, the restart usually relies on the previous chunk's checkpoint. That means some items already read in the previous run may be read again. The writer and business operations should have idempotency or a unique key when rerunning could create duplicate side effects.

A reader that does not save state may start again from the beginning or be unable to restore the read position accurately. Do not enable restart for a custom reader until you have clearly determined how it restores the position and handles items that were read but not yet committed.

## 12. How Should a Custom Reader Be Designed for Safe Recovery?

A custom reader should have a clear boundary between fetching an item, confirming that the item has been consumed, and saving the checkpoint. If the source is a paginated API, you need to save an appropriate token or page key. If the source is a database table, you can use an ascending key or a query over a stable window. If the source is a file, you can save the read position or use a built-in reader.

Important principles:

- Do not update the durable checkpoint before the chunk containing that item is committed.
- Be able to recover from the last committed checkpoint.
- Do not turn a transient error into EOF.
- If a read fails after the source has already consumed an item, there must be a way to determine whether that item can be read again or has been lost.
- Use a source with a stable order or a stable pagination key to avoid missing/duplicate reads when data changes.
- If you retry the same request, make sure the request does not lose the cursor or change the source state unexpectedly.

With an API-based reader, for example, do not simply increment the page number in memory before confirming that the entire chunk is committed. Design the checkpoint so that a restart reuses the last committed page or continuation token, while the writer tolerates reprocessing if there is a rollback.

## 13. Example of a Restartable File Reader Configuration

`FlatFileItemReader` is a built-in reader suitable for line-based files. The following example illustrates configuring the reader name and saving state:

```java
@Bean
FlatFileItemReader<Order> orderFileReader(Resource inputFile) {
    return new FlatFileItemReaderBuilder<Order>()
        .name("orderFileReader")
        .resource(inputFile)
        .delimited()
        .names("id", "customerId", "amount")
        .fieldSetMapper(fieldSet -> new Order(
            fieldSet.readString("id"),
            fieldSet.readString("customerId"),
            fieldSet.readBigDecimal("amount")
        ))
        .saveState(true)
        .build();
}
```

This reader can provide parse error information such as `FlatFileParseException`, and its state is saved to support restart. You need to ensure the input file still has the same content on restart. If the file is replaced or edited between two runs, the restored line position may point to different content.

You can configure skipping parse errors as in the earlier section, and also attach a listener to record errors. For a file that must be complete, consider failing instead of skipping if the number of errors exceeds a threshold or if structurally wrong data makes the following lines unreliable.

## 14. Testing Readers That Fail Midway

You should test at least the following scenarios:

1. The reader reads some items successfully and then throws an exception that is not skippable: the step must fail.
2. The reader encounters an exception configured for skip: the step continues and the read skip count increases.
3. The reader encounters a transient exception that is retried: the read operation is retried up to the configured limit.
4. The reader fails after one or more chunks have been committed: the restart continues from the correct checkpoint.
5. The reader returns `null`: the step ends normally and the read skip count does not increase.
6. The reader cannot continue after a source error: the step fails instead of silently skipping the rest.

A simulated reader can throw an error at a determined position so that the test reproduces reliably:

```java
public class FailingOnceReader implements ItemReader<Integer> {

    private int next = 1;
    private boolean failed;

    @Override
    public Integer read() {
        if (next == 4 && !failed) {
            failed = true;
            throw new IllegalStateException("Simulated read failure");
        }
        if (next > 6) {
            return null;
        }
        return next++;
    }
}
```

This reader is suitable for illustrating a transient error within the same reader instance. In a retry test, configure retry for `IllegalStateException` and confirm that the reader continues to provide data. For a real restart test, the `failed` and `next` state in this example is not durably saved; you need a reader that implements `ItemStream` or a test reader recreated from a checkpoint to test restart across another execution.

When using `JobLauncherTestUtils`, you can launch the test job and check the `JobExecution`, `StepExecution`, `readCount`, `readSkipCount`, `commitCount`, `rollbackCount`, and the final status. If testing skip, confirm that `SkipListener.onSkipInRead()` is called and the faulty record is recorded exactly once by design.

## 15. Common Mistakes When Handling Midway Reader Failures

**Swallowing the exception and returning null:** the step interprets this as EOF and may end successfully even though the source still has data. Propagate the exception or classify the error clearly.

**Skipping connection errors:** skipping a connection exception can cause the entire remaining data to go unread. Skip only errors tied to a specific record where it is safe to continue.

**Retrying an unsafe operation:** if the reader has already consumed an item before throwing the exception, the retry may read the next item or cause duplication. Design the reader to keep or restore the read position.

**Setting the skip limit too high:** a large limit can hide widespread corrupt input data. Choose a threshold based on business requirements and monitor the skip count.

**Not saving the reader's state:** the job may not know where to continue after a restart. Use a reader that supports `ItemStream` or implement an appropriate checkpoint yourself.

**The source file changes between runs:** the checkpoint may no longer correspond to the file content. Store immutable files or check a checksum/source identifier before restart.

**Not distinguishing read errors from processor errors:** errors in `read()` count toward `readSkipCount`; errors in `process()` count toward `processSkipCount`. Use listeners and the counters of the right phase to investigate.

**Not checking committed data:** a restart may re-read some items. Reconcile with the target system and design an idempotent writer to avoid duplicate writes.

## 16. How to Choose a Handling Strategy in Production

When implementing a reader, first classify the errors that can arise. Individual data errors can be skipped if the business allows; transient infrastructure errors can be retried if the read operation can be safely redone; configuration or authentication errors, or loss of the ability to determine the read position, should usually make the step fail.

Next, configure `skip`, `skipLimit`, `retry`, and `retryLimit` deliberately. Attach an `ItemReadListener` to observe read errors and a `SkipListener` to record the records that were actually skipped. Monitor the number of retries, read skips, rollbacks, and the job status to detect a degrading data source.

Finally, design the reader to be recoverable from the last committed checkpoint. Test mid-chunk errors, restart, and situations where the source data changes. For systems outside the database transaction, ensure the writer has idempotency or a reconciliation process so that reprocessing does not corrupt the data.

A reader that fails midway is a normal operational situation that must be anticipated in batch processing. When you correctly distinguish EOF from exceptions, choose retry/skip/fail according to the nature of the error, and save a recoverable read state, a Spring Batch job can handle faulty data in a controlled way while still protecting the completeness and consistency of the results.
