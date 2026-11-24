# Skip limit and retry limit

In Spring Batch, `skipLimit` and `retryLimit` are two key limits when configuring fault tolerance for a chunk-oriented Step. `skipLimit` caps the number of items the Step is allowed to skip due to errors. `retryLimit` caps the number of retry attempts for an operation that throws an exception classified as retryable.

These two limits address two different scenarios. Retry suits transient errors capable of self-recovery, such as deadlocks or temporarily unavailable external services. Skip suits per-item errors that business rules permit excluding from the output, such as a malformed file line. When an exception is both retryable and skippable, Spring Batch prioritizes retry; if retries are exhausted and the error still occurs, the skip policy decides whether the item can be skipped.

## 1. What is skip limit?

`skipLimit` specifies the total number of items allowed to be skipped in a Step. An item is counted as skipped only when the thrown exception is configured as skippable and the policy permits skipping it.

Example:

```java
.faultTolerant()
.skip(FlatFileParseException.class)
.skipLimit(10)
```

With this configuration, the Step can skip up to 10 items that throw `FlatFileParseException`. When an 11th item needs to be skipped, the Step exceeds the limit and ends in failure.

Skip limit is a combined limit across all three phases—read, process, and write; it is not a separate budget for each phase.

| Phase | Counter | Example |
|---|---|---|
| Read | `readSkipCount` | Unparseable file line |
| Process | `processSkipCount` | Order violating a data rule |
| Write | `writeSkipCount` | An item rejected by the writer per skip policy |

The Step's total skip count is reflected in `skipCount`. With `skipLimit(10)`, total skips across all three counters must not exceed 10. For example, if the Step has skipped 6 read errors and 4 process errors, the budget is exhausted. If the writer needs to skip one more item, the Step will exceed the limit.

When no skip limit is configured, the Step does not allow skipping items by default. Both skippable exception types and the total limit must be explicitly configured if business rules permit dropping data.

## 2. What is retry limit?

`retryLimit` specifies the retry cap for exceptions classified as retryable. Retry is useful when an error may disappear upon re-execution, for example:

- Database deadlock or temporary lock contention.
- HTTP 503 or brief timeout from a dependent service.
- Connection errors recoverable after a wait interval.
- Certain transient resource errors during writes.

Configuration example:

```java
.faultTolerant()
.retry(DeadlockLoserDataAccessException.class)
.retryLimit(3)
```

In this example, deadlock errors belong to the retryable group and the framework is allowed to retry up to the configured limit. `retryLimit` applies to the failing processing attempt under the retry policy, not the maximum number of items in the Step and not the Step's overall rollback count.

The initial attempt and subsequent retries are distinct concepts. How total attempts are counted depends on the retry policy/API of the Spring Batch and Spring Retry versions used by the project; when exact invocation counts matter, observe them via `RetryListener` or test on your exact version. What matters in design is setting a finite limit and understanding which exceptions the retry policy applies to.

Without retry configured, an error is not automatically retried just because it looks transient. Retryable exceptions and the retry limit must be declared explicitly.

## 3. Comparing skipLimit and retryLimit

| Criterion | `skipLimit` | `retryLimit` |
|---|---|---|
| Controls | Total number of items allowed to be skipped | Number of retry attempts for retryable errors |
| Unit of meaning | Skipped item in the Step | Retry attempt of an operation/item per policy |
| Goal | Accept dropping failing items per business rules | Recover from transient errors |
| When exceeded | Step fails when another skip is needed | No further retries; error is evaluated by skip policy or fails the Step |
| Scope | Read, process, and write | Depends on where the error occurs and the retry policy |
| Success outcome | Item is bypassed and Step continues if skip budget remains | Operation succeeds on retry, item is still processed |

The two limits do not replace each other. An error may be retried without being skippable; if retries are exhausted, the Step fails. Another error may not be retried at all yet be skipped immediately if business rules permit. An exception can be both retryable and skippable; in that case retry is applied first, then skip is evaluated if retries fail.

## 4. Combining skip and retry in configuration

Example Job importing orders from a file:

- File line parse errors are allowed to be skipped.
- Invalid orders are allowed to be skipped per business rules.
- Database deadlocks are retried.
- Prolonged database connection loss is not skipped; once retries are exhausted, the Step must fail.

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

`DeadlockLoserDataAccessException` is configured for retry only. If the error persists after the retry policy exhausts its attempts, it is not skipped and the Step fails. `FlatFileParseException` and `InvalidOrderException` are configured as skippable; as long as total skips do not exceed 50, the Step can continue.

The exceptions above are examples only. Choose specific exceptions actually thrown by your reader, processor, writer, or clients. Do not copy a generic exception list without verifying whether each error is recoverable or permitted by business rules to be skipped.

## 5. When an exception is both retryable and skippable

An exception can be declared in both the retry policy and the skip policy. In that case, Spring Batch retries first. If the operation succeeds on a retry, the item is processed normally and is not counted as skipped. If retries are exhausted and the exception still occurs, the framework checks the skip policy; if the exception is skippable and skip budget remains, the item is skipped.

Example:

```java
.faultTolerant()
.retry(TransientImportException.class)
.retryLimit(2)
.skip(TransientImportException.class)
.skipLimit(10)
```

With this illustrative configuration, `TransientImportException` is retried according to the retry policy. If the attempts still fail, the item can be skipped provided the Step's skip limit has not been exceeded.

Think carefully before making the same exception both retryable and skippable. If the error is actually an infrastructure outage, skipping can cause data loss. If the error is an unprocessable record, retrying usually just wastes time without improving the chance of success. The policy must reflect the root cause of the error.

## 6. Skip limit is shared across read, process, and write

Skip limit is a Step-wide total budget and does not reset when moving from read to process or write.

Suppose `skipLimit(5)`:

| Phase | New skips | Cumulative skips after phase |
|---|---:|---:|
| Read | 2 | 2 |
| Process | 1 | 3 |
| Write | 2 | 5 |
| Next write | 1 | 6 — limit exceeded |

When a sixth item needs to be skipped, the Step exceeds `skipLimit(5)` and fails. Separate counters help identify where errors occurred, while the limit applies to the sum.

This matters when assessing data quality. A Step might skip few read errors but many process errors; looking only at individual counters can cause operators to miss that total skips are approaching the threshold.

## 7. Classifying exceptions: retryable, skippable, or fatal

Before configuring limits, classify errors by recoverability and business decision.

| Error type | Examples | Typically appropriate policy |
|---|---|---|
| Transient | Deadlock, HTTP 503, brief timeout | Bounded retry, possibly with backoff |
| Isolated invalid data | Malformed date, nonexistent code | Skip if business accepts; otherwise fail |
| Configuration | Missing required parameter, wrong table name | Fail early; retrying usually does not help |
| Prolonged infrastructure outage | Database unavailable, prolonged broker disconnect | Bounded retry then fail; usually do not skip |
| Programming bug | Null pointer, broken invariant | Fail and fix bug; avoid broad skipping |

A useful rule of thumb:

- Retry when the same operation has a chance of succeeding after external conditions change.
- Skip when dropping that individual item is acceptable from a business standpoint.
- Fail when correctness cannot be guaranteed if execution continues.

Do not use `retry(Exception.class)` or `skip(Exception.class)` broadly. Those configurations can catch unrecoverable errors or severe system failures.

## 8. Using noRetry and noSkip to exclude exceptions

Spring Batch lets you declare exceptions to exclude from retry or skip policies. This is useful when using a parent exception as a default while certain subclasses require different handling.

For example, allowing most data errors to be skipped while not skipping missing file errors:

```java
.faultTolerant()
.skip(Exception.class)
.noSkip(FileNotFoundException.class)
.skipLimit(20)
```

Example retrying most data access errors while not retrying configuration errors:

```java
.faultTolerant()
.retry(DataAccessException.class)
.noRetry(BadSqlGrammarException.class)
.retryLimit(3)
```

These are illustrative configurations for exception hierarchies. Verify the actual exception types and classifiers used by your Spring Batch version. A specific error may be wrapped inside another exception; inspect the root cause and classification order to avoid unintended policy behavior.

When configuring broadly and then excluding, document the reason for every `noSkip` or `noRetry`. In many systems, explicitly declaring only the exceptions to handle is clearer and less risky.

## 9. Retry and skip in the read phase

The Reader can throw exceptions when reading files, parsing data, or querying a database. If an error is transient such as a recoverable connection failure, retry can be configured for that exception. If a file line is malformed and allowed to be dropped, skip can be configured.

Example:

```java
.faultTolerant()
.retry(TransientDataAccessException.class)
.retryLimit(3)
.skip(FlatFileParseException.class)
.skipLimit(25)
```

With read-skip, no valid item is returned from the failed read; the reader must be able to advance to the next record per its implementation contract. With built-in file readers, the framework can identify the failing line position and continue. With custom readers, design post-exception behavior carefully so it does not loop infinitely at the same position or mistakenly skip multiple records.

If the reader reads from a transactional queue, a rollback can cause the broker to redeliver the message. Distinguish item skipping from message redelivery and configure the transaction/reader accordingly.

## 10. Retry and skip in the process phase

The Processor can throw exceptions when validating or transforming an item. For example, an order with a negative amount is invalid:

```java
public class ValidateOrderProcessor implements ItemProcessor<Order, Order> {

    @Override
    public Order process(Order order) {
        if (order.getAmount().signum() < 0) {
            throw new InvalidOrderException(
                    "Negative amount for order " + order.getId()
            );
        }

        return order;
    }
}
```

If `InvalidOrderException` belongs to the skip policy, the item can be skipped. If the processor calls an external service and receives a transient timeout, it can be retried if that operation is safe to repeat.

The processor should avoid non-idempotent side effects. When retry or rollback causes the processor to be re-invoked, sending emails, creating transactions, or incrementing field counters could occur multiple times. Prefer stateless processors and place side effects in the writer or a mechanism with explicit transactions/idempotency.

## 11. Retry and skip in the write phase

The Writer typically receives an entire chunk. If an item causes the writer to throw an exception, the chunk transaction may roll back. With retry, the framework can re-invoke the write operation; with write-skip, the framework can split the item set to isolate the failing item, depending on configuration and writer type.

Example:

```java
.faultTolerant()
.retry(DeadlockLoserDataAccessException.class)
.retryLimit(3)
.skip(InvalidOrderException.class)
.skipLimit(20)
```

The writer must tolerate being re-invoked. When writing to a database with the same transaction manager, rollback can undo uncommitted writes. When the writer sends messages, calls HTTP APIs, or writes files outside the transaction, rollback does not automatically undo side effects that already occurred.

For non-transactional write targets, use idempotency keys, unique constraints, an outbox, or staging. Do not retry a writer with unsafe-to-repeat side effects solely because an exception looks transient.

## 12. Retry limit is not the Step's rollback count

A retry can entail rolling back the chunk transaction, but `retryLimit` and `rollbackCount` are not the same counter.

- Retry limit belongs to the retry policy for classified exceptions/items.
- Rollback count is the transaction rollback counter recorded at the Step level.
- A rollback can happen due to non-retryable errors, writer errors, commit errors, or other causes.
- A retry may involve re-invoking reader/processor/writer according to the fault-tolerance mechanism and cannot be inferred accurately from rollback count alone.

If you need to measure actual retry attempts, use a `RetryListener` or dedicated metric. Do not use `rollbackCount` as a substitute for retry count.

## 13. Backoff between retry attempts

For transient errors, retrying immediately over and over can overload the target system even more. Backoff inserts a wait interval between attempts, optionally increasing with each failure.

Conceptual backoff example:

```text
Retry 1: wait 200 ms
Retry 2: wait 400 ms
Retry 3: wait 800 ms
```

This is an illustrative example, not Spring Batch's default values. A `BackOffPolicy` can be configured through the API matching your project's Spring Batch/Spring Retry version.

Backoff is helpful for database contention or rate-limited HTTP services. Combine it with per-call timeouts, total retry time, and maximum Step duration. Avoid setting a large retry limit with long backoff without accounting for how long the Job may be held open.

For HTTP 429/503, if the service returns `Retry-After`, the client should respect that guidance when appropriate. For permanent data errors, backoff does not help; skip or fail per business rules.

## 14. Listeners for monitoring retry and skip

`SkipListener` helps record skipped items at each phase:

```java
public class ImportSkipListener implements SkipListener<Order, Order> {

    @Override
    public void onSkipInRead(Throwable throwable) {
        log.warn("Skip during read: {}", throwable.getMessage());
    }

    @Override
    public void onSkipInProcess(Order item, Throwable throwable) {
        log.warn("Skip order {} during process: {}",
                item.getId(), throwable.getMessage());
    }

    @Override
    public void onSkipInWrite(Order item, Throwable throwable) {
        log.warn("Skip order {} during write: {}",
                item.getId(), throwable.getMessage());
    }
}
```

Registering the listener:

```java
.listener(new ImportSkipListener())
```

`RetryListener` can observe retry attempts and outcomes. Specific APIs depend on the Spring Retry version used with Spring Batch. Use listeners to log exception type, item key, and attempt count; avoid creating non-idempotent side effects inside callbacks.

## 15. Monitoring StepExecution counters

After the Step completes, counters can be read to evaluate processing quality:

| Counter | Meaning |
|---|---|
| `readCount` | Number of items read successfully |
| `writeCount` | Number of items written successfully |
| `readSkipCount` | Number of items skipped while reading |
| `processSkipCount` | Number of items skipped while processing |
| `writeSkipCount` | Number of items skipped while writing |
| `skipCount` | Total number of items skipped |
| `commitCount` | Number of commits recorded |
| `rollbackCount` | Number of rollbacks recorded |

Example metrics-logging listener:

```java
public class ImportMetricsListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        log.info("Starting step {}", stepExecution.getStepName());
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        log.info(
                "step={}, read={}, write={}, readSkip={}, processSkip={}, " +
                "writeSkip={}, totalSkip={}, commits={}, rollbacks={}",
                stepExecution.getStepName(),
                stepExecution.getReadCount(),
                stepExecution.getWriteCount(),
                stepExecution.getReadSkipCount(),
                stepExecution.getProcessSkipCount(),
                stepExecution.getWriteSkipCount(),
                stepExecution.getSkipCount(),
                stepExecution.getCommitCount(),
                stepExecution.getRollbackCount()
        );

        return stepExecution.getExitStatus();
    }
}
```

`rollbackCount` is not an exact retry count. To observe retries, use `RetryListener` or metrics from the retry policy. `skipCount` is the metric to compare against `skipLimit`; individual counters help pinpoint which phase caused errors.

## 16. Setting ExitStatus when skips exceed a business threshold

Sometimes a Step has not exceeded `skipLimit`, yet the skip count is still higher than the data quality threshold acceptable to the business. For example, the Step allows up to 100 skipped items to avoid failing immediately, but if more than 20 items are skipped, manual review is required.

You can use a `StepExecutionListener` to return a custom `ExitStatus` after the Step:

```java
public class SkipThresholdListener implements StepExecutionListener {

    private final int warningThreshold;

    public SkipThresholdListener(int warningThreshold) {
        this.warningThreshold = warningThreshold;
    }

    @Override
    public void beforeStep(StepExecution stepExecution) {
        // No pre-step processing needed.
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getStatus() == BatchStatus.COMPLETED
                && stepExecution.getSkipCount() > warningThreshold) {
            return new ExitStatus(
                    "COMPLETED_WITH_SKIPS",
                    "Skip count exceeded business warning threshold"
            );
        }

        return stepExecution.getExitStatus();
    }
}
```

The Job flow can use this exit code to route to a review Step. This is a business warning threshold, distinct from `skipLimit`: `skipLimit` decides whether the Step may continue dropping items or must fail; the warning threshold decides which branch the Job follows after the Step completes.

## 17. Choosing limits based on business rules and real data

Do not pick `skipLimit` just because you want the Job to always finish. Determine the acceptable level of data errors and the impact of dropping each item type.

For example:

- A file with 10 million lines may accept at most 5 formatting errors.
- A financial reconciliation Job does not allow skipping any transaction; `skipLimit(0)` or omitting skip configuration is more appropriate.
- A reference catalog import Job may accept a few invalid codes, provided it clearly reports the list of dropped items.

Retry limits should also be based on the target system's actual recovery time. If deadlocks are usually resolved after one short retry, a small limit with backoff may suffice. If a service experiences long outages, consider total timeouts, the retry policy, and restarting the Job after failure.

Record metrics across runs to tune limits. If a Step frequently comes close to the skip limit, that may signal a data quality or upstream issue, not simply a reason to raise the limit.

## 18. Common misconceptions

**Assuming `skipLimit` is a per-phase limit.** Skip limit is the total across read, process, and write skips within the same Step.

**Assuming `retryLimit` caps the number of failing items.** Retry limit controls re-attempting an operation/item per the retry policy; it is not a Step-wide error budget.

**Assuming exhausting retries always leads to a skip.** Only when the exception belongs to the skip policy and skip budget remains is the item skipped. Otherwise, the Step fails.

**Assuming retry and skip can be configured broadly for all Exceptions.** That can hide programming, configuration, or infrastructure errors. Classify specific exceptions.

**Assuming skipping an item has no business impact.** Skipping leaves the output missing that item. Use it only when business rules allow and with proper recording.

**Using rollback count to measure retries.** The two counters mean different things. Use `RetryListener` or dedicated retry metrics.

**Ignoring writer side effects during retries.** The writer can be re-invoked after rollback. APIs/messages/files need idempotency or recovery mechanisms.

**Raising skipLimit to avoid Job failures.** A large limit can allow a Job to complete with too much dropped data. Set thresholds according to quality requirements.

## 19. Testing skipLimit and retryLimit

A useful test suite should verify both per-item behavior and final Step state:

1. Create a transient error that fails on the first attempt but succeeds on retry; verify the item is written and skip count does not increase.
2. Create an item with a skippable but non-retryable exception; verify the item is skipped immediately and the Step continues while skip budget remains.
3. Create an exception that is both retryable and skippable; verify retry runs first, then the item is skipped only after retries are exhausted.
4. Create a number of skippable items equal to `skipLimit`; verify the Step can complete if remaining items succeed.
5. Add one more skippable item beyond the limit; verify the Step fails.
6. Create a retryable, non-skippable error exceeding the retry limit; verify the Step fails rather than silently dropping the item.
7. Trigger errors in read, process, and write to verify the phase-specific counters.
8. Have the writer write partially and then throw an exception; verify transaction rollback or idempotency prevents duplicate data on replay.

For retry policies with backoff, use test configurations or a controllable clock to avoid long real-time waits. For databases, use a real transaction manager and suitable test database to verify actual rollback. For APIs or brokers, check the number of side effects on the target system rather than only asserting method invocation counts.

## 20. How to design skip limit and retry limit

First, classify exceptions by root cause: transient errors for retry, discardable data errors for skip, configuration or programming errors for fail. Set a finite `retryLimit` for retryable exceptions and consider backoff when the target system needs time to recover. Set `skipLimit` according to business-acceptable data error levels, remembering it sums read, process, and write skips.

If an exception is both retryable and skippable, explicitly verify whether dropping the item after retries fail is safe. Monitor retries with `RetryListener`, skips with `SkipListener`, and `StepExecution` counters. Ensure the writer tolerates replay and non-transactional side effects have idempotency.

A good fault-tolerant configuration is not aimed at forcing every Job to run to completion. It lets the system recover from transient errors, continue when encountering isolated items permitted to be dropped, and fail clearly when data correctness cannot be guaranteed.
