# Skipping Unprocessable Items

In Spring Batch, skip is a mechanism that allows a chunk Step to skip an item when it encounters an exception that has been defined as acceptable, and then continue processing the remaining items. This mechanism is useful when a data source contains a few isolated erroneous records, yet business rules still allow completing the valid portion of the data.

For example, a Job importing 100,000 order lines may encounter a few lines with malformed formatting, missing required fields, or duplicate keys. Stopping the entire Job for individual data errors would be inefficient. You can configure Spring Batch to skip specific exceptions, limit the number of skipped items, and record those items for correction or reconciliation.

Skip is a controlled decision. You should not skip every exception just so the Job finishes successfully. An item-level data error can be skipped if business rules allow it; database connection errors, configuration errors, or programming bugs usually require retry or failing the Step.

## 1. Where does skip operate in chunk processing?

A chunk Step executes a read, process, and write cycle. Exceptions can arise at any stage:

```text
ItemReader
    |
    +-- skippable exception --> Read skip
    |
    v
ItemProcessor
    |
    +-- skippable exception --> Process skip
    |
    v
ItemWriter
    |
    +-- skippable exception --> Write skip
    |
    v
Commit chunk
```

Skip only applies to exceptions configured in a fault-tolerant Step that are still within the allowed limit. If an exception is not skippable or the skip count exceeds the limit, the Step may end in the `FAILED` status.

| Stage | Error example | Result when skippable |
|---|---|---|
| Read | Unparseable CSV line | Skips the unreadable record and continues if the reader can recover. |
| Process | Negative amount or missing order ID | Skips the invalid input item. |
| Write | Duplicate key record per business rules | Skips the unwritable output item, if the framework can isolate the failing item and the policy allows it. |

Skip does not make a Step completely error-free. It indicates that the Step continued according to policy despite some skipped items. Therefore, you need to monitor the skip count and report failing items.

## 2. Basic skip configuration

With Spring Batch 5, you can enable fault tolerance and declare skippable exceptions on a chunk Step:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter,
        SkipListener<OrderInput, Order> orderSkipListener) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(200, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .faultTolerant()
            .skip(InvalidOrderException.class)
            .skipLimit(50)
            .listener(orderSkipListener)
            .build();
}
```

In this example:

- `.faultTolerant()` enables error-handling configuration for the chunk Step.
- `.skip(InvalidOrderException.class)` allows skipping the specified data exception.
- `.skipLimit(50)` sets the limit on the total number of skipped items in the Step.
- `.listener(orderSkipListener)` registers a listener to record skipped items.

With this configuration, up to 50 skips are accepted. If a 51st skip occurs, the limit is exceeded and the Step fails. The skip limit applies cumulatively across read, process, and write errors, not 50 for each stage.

Set a clear limit based on business requirements. If a Job importing 100,000 lines allows at most 20 bad lines, configure the corresponding limit and monitor the error rate. Too high a number can let the Job complete even when source data quality has severely degraded.

## 3. Which exceptions can be skipped?

Only skip exceptions that the application clearly understands and where skipping the item will not distort business outcomes to an unacceptable degree.

Examples to consider:

- `FlatFileParseException`: a file line cannot be parsed according to the expected format.
- `InvalidOrderException`: an item violates the data rules of an order.
- `DuplicateKeyException`: a record has a duplicate key and business rules specify that duplicates must be discarded.
- A custom domain exception indicating that an item is ineligible for processing.

Examples that generally should not be skipped by default:

- `DataAccessResourceFailureException`: the database or data resource is unreachable.
- `TransientDataAccessException`: a transient error that may be better suited for retry.
- `FileNotFoundException`: a required input file does not exist, which is usually a configuration or Job-level input error.
- `OutOfMemoryError`: a critical resource error, not a skippable item error.
- Unexpected programming-bug exceptions such as `NullPointerException`.

The final classification depends on business rules. For example, `DuplicateKeyException` may be a skippable item error in an import Job, or it may indicate corrupted target data or a duplicate Job run if the system requires each record to be written exactly once.

Do not configure `.skip(Exception.class)` as a catch-all approach. That can mask infrastructure and programming errors, causing the Job to report completion with missing data.

## 4. Skipping in the read stage (read skip)

A read skip occurs when the `ItemReader` throws an exception while reading an item and that exception is configured as skippable.

For example, a CSV reader can throw `FlatFileParseException` when a line lacks enough columns or contains malformed values:

```java
.faultTolerant()
.skip(FlatFileParseException.class)
.skipLimit(25)
```

If the reader can resume from the appropriate position after the bad line, Spring Batch can skip that line and read the next one. Check the specific reader's behavior, because not all data-source errors allow safe continuation.

For instance, a single-line parse error is usually isolated to an individual record. However, losing a database connection or having a file closed mid-stream can leave the reader unable to continue. Skipping such errors can drop a large chunk of data or leave the read state unreliable.

### SkipListener when the reader fails

For a read skip, Spring Batch does not yet have a complete item to pass to the listener. Therefore, the callback has the signature `onSkipInRead(Throwable t)` and receives only the exception:

```java
@Override
public void onSkipInRead(Throwable exception) {
    log.warn("Could not read input record: {}",
            exception.getClass().getSimpleName());
}
```

Some exceptions such as `FlatFileParseException` can provide the line number or source details. You can use that information to write an error report. Do not log the entire line content if the data contains personal or confidential information.

## 5. Skipping in the process stage (process skip)

A process skip occurs when the `ItemProcessor` throws an exception for an item. This is a common case during data validation or when applying business rules.

Example:

```java
public class OrderProcessor implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput item) {
        if (item.orderId() == null || item.orderId().isBlank()) {
            throw new InvalidOrderException("Order ID is required");
        }

        if (item.amount() == null || item.amount().signum() <= 0) {
            throw new InvalidOrderException("Order amount must be positive");
        }

        return new Order(
                item.orderId(),
                item.customerId(),
                item.amount());
    }
}
```

If `InvalidOrderException` is configured for skip, the failing item is not passed to the writer and the Step can continue with other items.

Process skip is appropriate when the error belongs to an individual item, such as a missing required field or a domain rule violation. If the processor encounters a transient error when calling a reference service, retry may be more suitable. If the processor hits a programming bug, do not skip automatically because it can corrupt results across many items.

`SkipListener.onSkipInProcess` receives the input item and the exception:

```java
@Override
public void onSkipInProcess(
        OrderInput item,
        Throwable exception) {

    log.warn("Skipping order input {} because of {}",
            item.orderId(),
            exception.getClass().getSimpleName());
}
```

This is the right place to record the skipped item's business key, provided the data is allowed to be logged.

## 6. Skipping in the write stage (write skip)

A write skip occurs when the `ItemWriter` throws an exception while writing an item or chunk. For example, an order with a duplicate key may be rejected by the database.

```java
.faultTolerant()
.skip(DuplicateKeyException.class)
.skipLimit(100)
```

Write skip is more complex than process skip because the writer receives a group of items. If a chunk write fails, the framework needs to identify which item caused the error before skipping that specific item. During this process, the chunk transaction may roll back and the writer may be invoked again with smaller groups or individual items to locate the failing element.

Therefore, the writer must tolerate being called again. If the writer only writes to a database within the Step-managed transaction, rollback can undo uncommitted writes. If the writer sends HTTP requests, writes files, or publishes messages outside the transaction, side effects may have already occurred before the exception was thrown; re-invocation may produce duplicate data.

`SkipListener.onSkipInWrite` receives the output item and the exception:

```java
@Override
public void onSkipInWrite(Order item, Throwable exception) {
    log.warn("Could not write order {}: {}",
            item.orderId(),
            exception.getClass().getSimpleName());
}
```

Only skip writer errors if the error can be isolated to a single item and business rules allow discarding that item. Database connection loss or an invalid schema is generally not an item-specific error.

## 7. SkipLimit and how errors are bounded

A skip limit protects the Job from skipping too many items. It is a combined limit across read skips, process skips, and write skips.

Example:

```java
.faultTolerant()
.skip(FlatFileParseException.class)
.skip(InvalidOrderException.class)
.skip(DuplicateKeyException.class)
.skipLimit(20)
```

With a limit of 20, the Step can continue after up to 20 skipped items belonging to the configured exception types. When a subsequent skip pushes the total past 20, the Step fails.

Do not interpret the skip limit as the number of exceptions allowed across the entire Job or as a separate limit per exception type. It belongs to the Step and applies to the total skip count across the stages in that Step.

### Choosing a skip limit based on business requirements

You can choose the limit based on:

- Absolute count, for example at most 20 bad lines.
- Data volume, for example the maximum number of errors in a known import batch.
- Quality threshold, for example an error rate that does not exceed the business-acceptable level.

`skipLimit` is a count, not a percentage. If you need a percentage-based policy, you can use a custom `SkipPolicy` or a separate aggregation check mechanism. Clearly define the denominator and evaluation timing to avoid inconsistent skip decisions.

## 8. Skip and noSkip

You can declare exceptions to skip and exceptions not to skip. For example, allow skipping a general data exception while excluding a critical error:

```java
.faultTolerant()
.skip(Exception.class)
.noSkip(FatalImportException.class)
.skipLimit(50)
```

This is an example of how exclusions can be declared, not a recommendation to skip every `Exception`. In real applications, declare specific exception classes and broaden them only when you thoroughly understand the exception hierarchy.

When exception types have an inheritance relationship, Spring Batch classifies them according to the configured exception types. Verify the specificity/precedence of exception types to ensure a critical error is not accidentally classified as skippable due to an overly broad superclass.

## 9. Using a custom SkipPolicy

When skip rules are more complex than an exception list, you can implement `SkipPolicy`. The policy receives the exception and the current skip count to decide whether skipping is allowed.

Basic contract:

```java
public interface SkipPolicy {
    boolean shouldSkip(Throwable throwable, long skipCount)
            throws SkipLimitExceededException;
}
```

Example policy limiting skips for a business error type:

```java
public class InvalidOrderSkipPolicy implements SkipPolicy {

    private final long limit;

    public InvalidOrderSkipPolicy(long limit) {
        this.limit = limit;
    }

    @Override
    public boolean shouldSkip(Throwable throwable, long skipCount) {
        boolean invalidOrder = throwable instanceof InvalidOrderException;
        return invalidOrder && skipCount < limit;
    }
}
```

If the policy returns `false`, the exception is not skipped and is propagated according to the Step's mechanism. A custom policy must explicitly handle critical errors, unknown errors, and limits. Note that `skipCount` is the number of skips already recorded in the policy context, so test the limit boundary to ensure the required behavior.

Register the policy on the Step with `.skipPolicy(...)` instead of simple skip configuration:

```java
.faultTolerant()
.skipPolicy(new InvalidOrderSkipPolicy(50))
```

When using a custom policy, the policy is responsible for deciding which cases are skipped. Do not mix `.skip(...)`, `.noSkip(...)`, and a custom policy without understanding the builder's precedence and behavior in the version you are using.

## 10. Recording skipped items with SkipListener

`SkipListener` provides stage-specific callbacks so the application can store the reason or generate a reject report:

```java
public class OrderSkipListener implements SkipListener<OrderInput, Order> {

    @Override
    public void onSkipInRead(Throwable exception) {
        log.warn("Read skip: {}", exception.getMessage());
    }

    @Override
    public void onSkipInProcess(
            OrderInput item,
            Throwable exception) {
        log.warn("Process skip for order {}: {}",
                item.orderId(), exception.getMessage());
    }

    @Override
    public void onSkipInWrite(
            Order item,
            Throwable exception) {
        log.warn("Write skip for order {}: {}",
                item.orderId(), exception.getMessage());
    }
}
```

You can use the listener to:

- Record the business key of the failing item.
- Store the exception type and skip reason.
- Record the source line number or read position.
- Generate a reject file for users to correct data.
- Emit metrics on the number of skipped items by error type.

### Transaction considerations when writing rejects

If the listener writes rejects to a database, determine which transaction that operation participates in. With the same datasource/transaction manager, the reject record may be committed or rolled back with the chunk transaction depending on configuration and callback timing. If writing through a different transaction manager or external system, there is no automatic atomicity guarantee.

Design reject persistence to avoid duplicate records upon chunk rollback/retry. You can use a unique key based on batch ID, source, line number, or business key; or write rejects through an idempotent outbox/audit store. Do not assume every listener callback always produces only a single external side effect regardless of retries.

## 11. How does skip differ from filter?

Both filter and skip prevent an item from reaching the writer, but their meanings differ:

| Criterion | Filter | Skip |
|---|---|---|
| Cause | The item is valid but does not belong in the required output. | An exception occurred during reading, processing, or writing. |
| How it works | Processor returns `null`. | Configure the exception in the skip policy. |
| Counter | `filterCount`. | `readSkipCount`, `processSkipCount`, `writeSkipCount`. |
| SkipListener | Not invoked. | Invoked when the item is actually skipped. |
| Skip limit | Does not consume the skip limit. | Counts toward the skip limit. |
| Example | Excluding cancelled orders from a report. | Discarding orders missing a required ID per policy. |

Do not return `null` to hide invalid data if error reporting is required. Conversely, do not throw an exception and skip a valid item just because it falls outside the report scope.

## 12. Combining retry and skip

Retry and skip can coexist in a fault-tolerant Step, but they address different situations:

- **Retry:** try again when an exception is likely transient and the operation can be safely re-executed.
- **Skip:** bypass an item when the error has been defined as acceptable.
- **Fail:** stop the Step when the error cannot safely continue or exceeds limits.

Example:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(200, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skip(FlatFileParseException.class)
        .skipLimit(50)
        .build();
```

In this configuration, transient data-access errors are retried up to the limit. Defined data errors can be skipped. When an exception is configured for both retry and skip, Spring Batch generally retries first; if retries fail and the exception is still skippable, it can be skipped per policy. Run integration tests with actual exceptions to confirm the final outcome, especially when the writer may cause rollback and be re-invoked.

Do not retry deterministic data errors like a missing required field if nothing can change the data between attempts. Likewise, do not skip persistent infrastructure errors just to prevent the Job from failing.

## 13. Rollback and the impact of skip

Chunks are typically processed inside a transaction. When an exception occurs, the current chunk transaction may roll back before the framework finishes retrying or skipping. Previously committed chunks remain intact.

When skipping an item:

- The failing item is not processed/written successfully in the main pipeline.
- Spring Batch continues with other items if policy allows.
- The corresponding skip count is updated.
- `SkipListener` can record the item and exception.

With a write skip, the framework may roll back the chunk and then try writing items in smaller groups to isolate the failing item. Consequently, the writer needs to tolerate re-invocation. Operations outside the transaction such as HTTP, email, or files do not roll back automatically and require idempotency.

Skip does not mean rolling back the entire Job. Already committed chunks persist; the current chunk is handled according to the transaction and fault-tolerance policy.

## 14. Tracking skip counts in StepExecution

`StepExecution` stores separate counters for each stage:

| Counter | Meaning |
|---|---|
| `readSkipCount` | Number of items skipped when the reader throws an exception. |
| `processSkipCount` | Number of items skipped when the processor throws an exception. |
| `writeSkipCount` | Number of items skipped when the writer throws an exception. |
| `skipCount` | Total number of skips in the Step. |
| `readCount` | Number of items successfully read by the reader. |
| `writeCount` | Number of items written by the writer according to Step metadata. |
| `filterCount` | Number of items excluded by the processor returning `null`. |

You can query these counters via `StepExecution` or `JobExplorer` to display on an operations dashboard. Do not look solely at `BatchStatus.COMPLETED` and conclude all items were processed; a Step can complete with some skips within the limit.

For example, an import run with `readCount = 10,000`, `processSkipCount = 12`, `writeSkipCount = 3`, and `filterCount = 100` shows that items were excluded by both mechanisms. Use `SkipListener` and separate filter auditing to know the exact business key and reason for each item.

Do not apply a fixed formula to every Step such as `readCount = writeCount + filterCount + skipCount`. A writer can produce multiple outputs per input, a processor can filter, retry/rollback complicates the execution flow, and the counters reflect different stages.

## 15. Example: importing a file and generating a reject report

Suppose a Job imports an orders CSV file. Requirements:

- Skip unparseable lines.
- Skip orders missing an ID or having an invalid amount.
- Stop the Job if more than 30 items fail.
- Record the business key and cause of skipped items.
- Retry transient database errors during writing.

Processor throwing a business exception:

```java
public class OrderProcessor implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput input) {
        if (input.orderId() == null || input.orderId().isBlank()) {
            throw new InvalidOrderException("Missing order ID");
        }

        if (input.amount() == null || input.amount().signum() <= 0) {
            throw new InvalidOrderException("Amount must be positive");
        }

        return new Order(input.orderId(), input.amount());
    }
}
```

Step configured with skip and retry:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(250, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(FlatFileParseException.class)
        .skip(InvalidOrderException.class)
        .skipLimit(30)
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .listener(orderSkipListener)
        .build();
```

With this design, parse and validation errors can be skipped up to a limit of 30; transient database errors are retried. If total skips exceed 30, the Step fails so operators can review data quality.

In a real implementation, the reject report should record both unparseable source lines and parsed-but-invalid items. For a read skip, the listener does not receive a complete item; you can extract the line number or safe raw data from the exception. For process/write skips, the listener receives the corresponding item.

## 16. Handling errors when the skip limit is exceeded

When the skip count exceeds the limit, Spring Batch throws a skip limit exceeded exception and the Step fails. The Job flow can use transitions based on the Step result to route to an error-reporting Step, send notifications, or stop the Job per policy.

Do not automatically raise the skip limit every time the Job fails. First inspect:

- Which exception type accounts for most of the skip count.
- Whether errors occur in the reader, processor, or writer.
- Whether source data has changed abnormally.
- Whether the error is genuinely item-specific or an infrastructure outage.
- Whether the error rate exceeds the quality threshold accepted by the business.

If the error rate spikes abruptly, stopping the Job and fixing the data source may be safer than continuing to skip. The skip limit is a guardrail, not a target to exhaust.

## 17. Restarting after a Step with skips or failure

If a Step completes successfully with a skip count within the limit, the Job usually continues its flow. Skipped items are not automatically retried in a subsequent normal run; to reprocess them, the application needs a reprocessing workflow or a corrected input.

If a Step fails because the skip limit was exceeded or an unhandled exception occurred, the Job can be restarted if state and configuration permit. Upon restart:

- The JobInstance and identifying parameters must remain the same if continuing the previous business run.
- Readers supporting `ItemStream`/checkpointing can resume from the last committed position.
- Previously committed chunks are generally not reprocessed in the same Step restart.
- Uncommitted chunks must be reprocessed according to checkpoint and fault-tolerance policy.
- The writer must be safe if an item is re-sent due to rollback/restart.

Do not delete metadata or directly edit `StepExecution` to bypass the skip limit. If failed items need reprocessing, persist reject data with business keys and create a dedicated Job/Step with clear identification.

## 18. Common mistakes

### Skipping all exceptions

This can hide database errors, configuration errors, or programming bugs. Only skip specific exceptions permitted by business rules.

### Setting the skip limit too high

The Job may complete even when most data was skipped. Choose the limit according to quality requirements and monitor the error rate.

### Confusing skip with filter

Filter is when the processor returns `null` for a valid item that needs no output. Skip handles exceptions. The two mechanisms have different counters and listeners.

### Skipping transient errors instead of retrying

Timeouts or deadlocks may recover. Skipping immediately can lose data; consider bounded retry with backoff.

### Failing to record skipped items

Without a `SkipListener` or reject store, it is hard to identify which records need fixing and rerunning. Persist the business key, source, and reason in accordance with security policies.

### Writing rejects non-idempotently

The listener or writer can be re-invoked during transaction rollback/retry. Use a unique key or deduplication mechanism for reject records.

### Assuming write skip can always isolate one failing item

The writer receives an entire chunk; an error may affect the whole batch or target resource. Only skip when the framework can isolate the item and the error is genuinely skippable.

### Restarting without checking checkpoints

A stateless reader may reread from the start or miss data if source state changed. Check `ExecutionContext` and the writer before restarting.

## 19. Decision workflow for whether an item can be skipped

When an item cannot be processed, classify the cause before configuring:

1. Is the item valid but outside the required output? If yes, use filtering by returning `null`.
2. Is there an exception tied to an individual item? If not, investigate infrastructure or system errors.
3. Is the exception permitted to be skipped by business rules? If yes, configure `.skip(...)` or `SkipPolicy`.
4. Is the error likely transient and the operation safe to repeat? If yes, consider `.retry(...)` before deciding to skip.
5. What is the maximum acceptable total number of failing items? Set an appropriate `skipLimit`.
6. Which business key, source line, and cause must be stored for reconciliation? Register a `SkipListener`.
7. If the limit is exceeded, should the Job fail, stop, or transition to an error-reporting Step? Design the flow clearly.
8. On restart, does the reader have a checkpoint and can the writer re-execute safely?

| Situation | Appropriate mechanism |
|---|---|
| A malformed CSV line that can be ignored | Read skip for the specific parse exception. |
| An item missing a required field | Process skip for the validation exception. |
| A duplicate-key record per business rules | Write skip if the error belongs to the item and can be safely isolated. |
| Temporary database timeout | Bounded retry with backoff. |
| Prolonged database disconnection | Fail Step, restore infrastructure, then restart. |
| Valid item outside report scope | Filter by returning `null`. |
| Failing items exceed quality threshold | Fail Step and handle reject data. |

## Conclusion

Skip enables Spring Batch to bypass items encountering exceptions defined as acceptable in the reader, processor, or writer. Use `.skip(...)` to declare error types, `.skipLimit(...)` to bound total skipped items, and `SkipListener` to record items and causes. Only skip item-level errors; use retry for transient errors and let the Step fail when system or data issues prevent safe continuation. Distinguish skip from filter, monitor skip counters, and ensure reject reporting and the writer handle rollback/retry without creating duplicate side effects.
