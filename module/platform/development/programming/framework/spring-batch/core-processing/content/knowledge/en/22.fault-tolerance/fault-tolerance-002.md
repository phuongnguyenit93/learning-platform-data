# Combining skip and retry

In Spring Batch, `retry` and `skip` are two fault tolerance mechanisms commonly combined in a chunk-oriented Step. Retry allows re-attempting an operation that has a chance of succeeding after a transient error. Skip allows bypassing a failing item that business rules permit excluding from the output, so the Step can continue processing the remaining items.

The two mechanisms solve two different kinds of situations. For example, a database deadlock when writing can usually be retried because the transaction may succeed on the next attempt. A record with an invalid format can be skipped if business rules allow dropping that record. If an exception is configured as both retryable and skippable, Spring Batch typically prioritizes retry first; once retries are exhausted, the skip policy decides whether the item can be skipped or the Step must fail.

## 1. What problems do retry and skip solve?

In chunk processing, Spring Batch reads items, processes them with an `ItemProcessor`, and writes the results with an `ItemWriter`. Exceptions can occur at any stage.

| Mechanism | Purpose | Suitable examples |
|---|---|---|
| Retry | Re-attempt transient errors likely to self-recover | Deadlock, lock contention, temporary service call timeout |
| Skip | Bypass failing items per business policy | Malformed file lines, records violating rules that may be dropped |

Retry does not mean ignoring an error. If the next attempt succeeds, the item is still processed normally. Skip means accepting that the failing item is excluded from the primary processing output while recording the skip.

Consider a file with 1,000 orders:

- An order with a malformed date may be skipped if business rules allow it.
- A database write encountering a deadlock can be retried to re-attempt the same operation.
- If retries are exhausted and the error still occurs, Spring Batch checks whether the exception belongs to the skippable group.
- If the exception is neither retryable nor skippable, the Step ends in failure.

## 2. Configuring retry and skip in a Step

Spring Batch enables fault-tolerant behavior via `.faultTolerant()` on the chunk Step builder. You can then declare retryable exceptions, the retry limit, skippable exceptions, and the skip limit.

```java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .retry(DeadlockLoserDataAccessException.class)
            .retryLimit(3)
            .skip(FlatFileParseException.class)
            .skipLimit(20)
            .build();
}
```

In this example:

- `DeadlockLoserDataAccessException` is treated as a retryable error.
- `retryLimit(3)` caps the number of retry attempts under the configured policy.
- `FlatFileParseException` is allowed to be skipped.
- `skipLimit(20)` caps the total number of skipped items in the Step.

The exceptions and limits in this example are illustrative. Choose specific exception types based on your reader, processor, writer, and actual business rules. API classes or packages may vary across Spring Batch and Spring Framework versions in your project.

## 3. How does Spring Batch combine retry and skip?

When an item encounters an exception, Spring Batch classifies the error according to the fault tolerance configuration. If the error is configured as retryable, the framework retries according to the retry policy. If the retries still fail, the skip policy can be applied if the exception is also allowed to be skipped and the skip limit has not been exceeded.

```text
Read / Process / Write item
          |
          v
       Exception
          |
          v
  Is exception retryable?
       /       \
     Yes        No
      |          |
      v          v
   Retries     Check
  remaining?   skip policy
    /   \
  Yes   Exhausted
   |       |
   v       v
 Retry   Is exception skippable?
          /       \
        Yes        No
         |          |
         v          v
   Skip item     Step FAILED
  if skip limit remains
```

The key point is that retry is used to overcome transient errors; skip is the final decision allowing the item to be dropped. If an exception is not configured as retryable, Spring Batch can evaluate the skip policy directly. If an exception is retried and exhausts the retry limit, it is only skipped if the skip policy allows it.

Do not configure the same exception in both retry and skip just to "make sure the Job keeps going". Clearly define the business intent: recoverable errors should be retried; data errors acceptable to discard should be skipped.

## 4. retryLimit and skipLimit are not the same counter

The two limits control two different things:

| Property | What does it limit? | When the limit is exceeded |
|---|---|---|
| `retryLimit` | Number of retries for errors matching the retry policy | No further retries; the framework proceeds according to the skip policy or fails the Step |
| `skipLimit` | Total number of items allowed to be skipped in the Step | The Step fails when the skip count exceeds the limit |

`skipLimit` is counted across read, process, and write skips combined. The corresponding counters are `readSkipCount`, `processSkipCount`, and `writeSkipCount`; the total skip count is tracked on `StepExecution`.

For example, if `skipLimit(5)` is set and the Step has already skipped 3 items during reading and 2 items during processing, the total has reached 5. If another item needs to be skipped, the Step exceeds the limit and fails instead of skipping that item.

Do not use `retryLimit` to limit the total number of failing items in a Step. One error can be retried multiple times; multiple different items can also trigger retries. `skipLimit` is the limit on how many items may be acceptably skipped.

## 5. Classifying exceptions by error nature

Fault tolerance design should start from the root cause of errors, not from a desire to let the Job always run to completion.

| Error category | Examples | Typically appropriate policy |
|---|---|---|
| Transient errors | Deadlock, lock timeout, service temporarily unavailable | Retry with a limit, possibly with backoff |
| Single-item data errors | Malformed date, invalid business code | Skip if business rules permit; otherwise fail |
| Configuration errors | Wrong table name, missing required parameter, insufficient permissions | Fail early; retrying usually will not help |
| Prolonged infrastructure outages | Prolonged database disconnect, broker down | Retry with a limit or fail for operator intervention |
| Programming errors | Null pointer from a bug, violated invariant | Usually fail and fix the bug; do not skip broadly |

Retrying overly broad exceptions such as `Exception.class` can cause the Job to retry unrecoverable errors, extend execution time, and obscure the root cause. Skipping overly broad exceptions is equally dangerous because it can bypass infrastructure errors or programming bugs, leading to missing data while the Job still reports completion.

Prefer configuring specific exceptions. If you use a parent exception, verify that every subclass shares the same retry or skip policy.

## 6. Retry and skip across read, process, and write phases

Exceptions can arise in three different phases. How the framework identifies the failing item and how you observe it also differ.

### Errors while reading (read)

The Reader can throw an exception when reading a file, parsing a line, or querying a data source. For example, a malformed file line can produce `FlatFileParseException`. If bad lines are allowed to be skipped, configure skip for this exception.

```java
.faultTolerant()
.skip(FlatFileParseException.class)
.skipLimit(20)
```

For transient data source connection errors, retry can be configured if the reader and data source support safe re-invocation. Verify whether the reader preserves a consistent read position after an exception.

### Errors while processing (process)

The Processor can throw an exception when validating or transforming an item. For example, an invalid business value can be skipped according to rules:

```java
public class ValidateOrderProcessor implements ItemProcessor<Order, Order> {

    @Override
    public Order process(Order order) {
        if (order.getAmount().signum() < 0) {
            throw new InvalidOrderException("Negative order amount");
        }

        return order;
    }
}
```

If `InvalidOrderException` is configured as skippable, that item is skipped when the skip policy permits. The Processor should avoid non-idempotent side effects because it may be invoked again during retry or chunk recovery.

### Errors while writing (write)

The Writer can throw an exception when inserting into a database, writing a file, or sending a message. Retry can help with deadlocks or transient errors. Skip can apply to errors tied to a specific item, provided the writer and business rules support identifying that item.

Write-skip is more complex than read/process-skip because the writer normally receives an entire chunk. When an item in the chunk fails, Spring Batch may roll back the chunk and re-invoke the writer with smaller subsets of items to isolate the failing item, depending on the fault tolerance mechanism and writer type. Therefore, the writer must tolerate multiple invocations and must be idempotent if side effects are not undone by the transaction.

## 7. Example combining transient errors and data errors

Suppose a Job imports orders from a file into a database:

- Unparseable file lines: skip if business rules allow.
- Database deadlock: retry because the transaction may succeed on the next attempt.
- Orders with negative amounts: skip if defined as invalid records that can be discarded.
- Prolonged database disconnection: retry with a limit; once retries are exhausted, the Step fails because this error is not skipped.

```java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .retry(DeadlockLoserDataAccessException.class)
            .retryLimit(3)
            .skip(FlatFileParseException.class)
            .skip(InvalidOrderException.class)
            .skipLimit(50)
            .build();
}
```

In this configuration, `DeadlockLoserDataAccessException` is retried but not skipped. If the deadlock persists after the maximum number of attempts, the Step fails. The declared data exceptions can be skipped as long as total skips do not exceed 50.

This is an illustrative configuration. If data exceptions can also occur in the writer or reader, verify the actual exception type and where it is thrown. The skip/retry policy must align with the contract of each phase's component.

## 8. Retry requires limits and backoff

Continuous unbounded retries can hold transactions, threads, and connections for too long. A good retry policy typically has:

- A cap on the number of retry attempts.
- Classification of specific transient errors.
- A wait interval between retries when the target system needs time to recover.
- Increasing backoff when appropriate, preventing multiple workers from retrying in a burst.
- Logging and metrics to observe retry counts, exception types, and wait durations.

Backoff is commonly used for errors such as HTTP 429/503 or database contention. A `BackOffPolicy` can be configured via the builder in Spring Batch versions that support the corresponding API. For external services, also respect `Retry-After`, timeouts, and service rate limits.

Do not retry permanent validation errors such as malformed dates or missing parameters. The same invalid input will usually remain invalid on the next attempt.

## 9. Rollback and writer re-invocation

In chunk processing, an exception can roll back the chunk transaction. On retry, Spring Batch may re-invoke the processor or writer for the affected item/chunk. Therefore, you must understand the side effects of each component.

For a database writer sharing the same transaction manager, uncommitted changes are typically rolled back with the chunk. On retry, the writer can write again without leaving behind inserts from the failed attempt.

For HTTP APIs, email, files, or message brokers, a database rollback does not automatically undo side effects that already occurred. For example, a writer sends 20 messages and fails on the 21st; if the chunk is retried, the first 20 messages may be sent again.

To prevent duplicates:

- Use a stable idempotency key for each item or message.
- Use unique constraints or upserts for database records where appropriate.
- Use an outbox to record the publish intent in the same business transaction.
- For files, write to a temporary location and publish after completion, or use a checkpoint-capable writer.
- Avoid external non-transactional side effects in the processor.

Retry is only safe when re-execution does not produce duplicate or incorrect business outcomes.

## 10. Writer and write-skip require special care

When a writer receives a chunk of multiple items, it may write several items before encountering an exception. If the writes participate in the same transaction, rollback can undo the partial writes. If not, partially written data may remain.

To support write-skip, Spring Batch may need to re-invoke the writer with smaller groups of items to isolate the failing item. A writer therefore must not assume each chunk is invoked only once. It needs to:

- Never catch an exception and return normally if data was not written.
- Throw appropriate exceptions so the framework can apply retry/skip.
- Tolerate re-invocation after rollback.
- Use transactions or idempotency for write operations.
- Avoid irreversible side effects before knowing the final outcome.

If a writer can only write the entire chunk as a single bulk operation and cannot identify the failing item, consider staging, pre-write validation, or splitting operations so bad records can be isolated.

## 11. SkipListener and RetryListener

Listeners help observe skipping and retrying. `SkipListener` provides callbacks for each phase:

| Callback | When is it called? |
|---|---|
| `onSkipInRead(Throwable)` | When a read error is accepted for skipping |
| `onSkipInProcess(item, Throwable)` | When an item is skipped due to a processor error |
| `onSkipInWrite(item, Throwable)` | When an item is skipped due to a writer error |

Example recording skipped items:

```java
public class ImportSkipListener implements SkipListener<Order, Order> {

    @Override
    public void onSkipInRead(Throwable throwable) {
        log.warn("Skipped input while reading: {}", throwable.getMessage());
    }

    @Override
    public void onSkipInProcess(Order item, Throwable throwable) {
        log.warn("Skipped order {} during processing: {}",
                item.getId(), throwable.getMessage());
    }

    @Override
    public void onSkipInWrite(Order item, Throwable throwable) {
        log.warn("Skipped order {} during writing: {}",
                item.getId(), throwable.getMessage());
    }
}
```

Register the listener via `.listener(skipListener)` in the Step configuration. Use the listener to record the reason, item ID, and source location for investigation or error reporting.

Spring Retry's `RetryListener` can be used to observe the retry lifecycle, depending on the version and builder API in use. Do not send emails or call non-idempotent APIs directly inside retry/skip callbacks; callbacks may be invoked inside a transaction or during recovery. If durable error records need to be stored, use an appropriate transactional mechanism or outbox.

## 12. Counting skips and monitoring Step results

`StepExecution` provides the following counters:

| Counter | Meaning |
|---|---|
| `readSkipCount` | Number of items skipped in the read phase |
| `processSkipCount` | Number of items skipped in the process phase |
| `writeSkipCount` | Number of items skipped in the write phase |
| `skipCount` | Total number of items skipped |
| `readCount` | Number of items read successfully |
| `writeCount` | Number of items written successfully |
| `rollbackCount` | Number of rollbacks recorded |

You can log metrics after the Step:

```java
public class ImportMetricsListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        // No need to initialize separate mutable counters.
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        log.info(
                "step={}, read={}, write={}, readSkip={}, processSkip={}, " +
                "writeSkip={}, retry-related rollbacks={}",
                stepExecution.getStepName(),
                stepExecution.getReadCount(),
                stepExecution.getWriteCount(),
                stepExecution.getReadSkipCount(),
                stepExecution.getProcessSkipCount(),
                stepExecution.getWriteSkipCount(),
                stepExecution.getRollbackCount()
        );

        return stepExecution.getExitStatus();
    }
}
```

`rollbackCount` is not an exact retry count: a rollback can happen for multiple reasons, and a retry may involve different operations depending on the phase. If you need to measure retries, use a retry listener or dedicated metrics.

## 13. noRollback does not mean skip

Spring Batch lets you configure certain exceptions not to roll back the transaction via `noRollback(...)` in a fault-tolerant Step. This is an advanced option and requires a clear understanding of the exception type and when side effects occur.

`noRollback` only changes rollback behavior for the specified exception type. It does not automatically mark an item as skippable, does not replace `skip(...)`, and does not retry the exception unless a retry policy is configured.

Conceptual example:

```java
.faultTolerant()
.skip(InvalidOrderException.class)
.skipLimit(20)
.noRollback(InvalidOrderException.class)
```

Use `noRollback` only when keeping the changes already made in the transaction is business-valid and safe. If an exception occurs after the writer has written incomplete data, not rolling back can cause the chunk to commit a partial state. For many Steps, retries, and skips, the default rollback behavior is easier to reason about; only change it when the consequences are fully understood.

## 14. Common misconceptions

**Assuming retry and skip are two names for the same thing.** Retry re-attempts the operation; skip accepts dropping the item. Choose based on root cause and business requirements.

**Assuming an exception that exhausts retries is automatically skipped.** Only when the exception belongs to the skip policy and the skip limit has not been exceeded can the item be skipped. Otherwise, the Step fails.

**Assuming skipLimit applies separately to each phase.** The skip limit is a Step-wide total, summing skips across read, process, and write.

**Retrying every exception.** Validation errors, configuration mistakes, or bugs usually do not disappear on retry. Choose specific transient exceptions.

**Skipping infrastructure errors.** Ignoring a database outage or unavailable broker can lead to data loss. These errors usually require bounded retries or failure.

**Assuming rollback undoes every side effect.** Rollback only affects resources participating in the transaction. APIs, emails, files, and messages require idempotency or dedicated recovery mechanisms.

**Assuming the writer is only called once.** Retry and write-skip can cause the writer to be re-invoked. The writer must tolerate replay.

**Using noRollback instead of skip.** NoRollback only changes transaction behavior; the skip policy determines whether an item can be skipped.

## 15. Testing when combining retry and skip

A meaningful test must verify both the final outcome and the execution counts:

1. Create an item that causes a transient error on the first attempt but succeeds on the next; verify retry occurs and the item is still written.
2. Create an item causing a data error covered by the skip policy; verify the item is skipped and remaining items continue.
3. Create an exception that is both retryable and skippable; verify retry is applied first and after retries are exhausted, the skip policy determines the outcome.
4. Create enough failing items to exceed the skip limit; verify the Step fails.
5. Throw a non-retryable and non-skippable exception; verify the Step fails immediately per policy.
6. Make the writer fail after partial work; verify transaction rollback or idempotency prevents duplicate writes when the writer is re-invoked.
7. Check `readSkipCount`, `processSkipCount`, `writeSkipCount`, `skipCount`, `writeCount`, and the Step status.

For retries with backoff, tests should use a controllable policy or clock so they do not wait for long real-time delays. For external side effects, use a fake service or test container to verify idempotency keys and the number of transactions actually created.

## 16. Design rules when using retry and skip together

Classify exceptions before configuring: transient errors are retried with a limit; discardable data errors are skipped; configuration errors, programming errors, and unrecoverable infrastructure errors should fail the Step. If an exception is both retryable and skippable, explicitly decide whether business rules allow dropping the item after retries are exhausted.

Set explicit `retryLimit` and `skipLimit`, monitor counters, and record skipped items with listeners. Ensure reader/processor/writer tolerate re-invocation; in particular, the writer must be idempotent if write operations are not completely rolled back. For side effects outside the transaction, consider an outbox or idempotency key rather than relying on rollback.

Combining retry and skip properly helps a Job recover from transient errors, continue processing when encountering isolated skippable data issues, and still fail clearly when the system cannot guarantee a correct result.
