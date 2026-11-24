# FaultTolerantStepBuilder

In Spring Batch, `FaultTolerantStepBuilder` is a builder that extends configuration for a chunk-oriented Step when controlled error handling is needed. It allows declaring which exceptions can be retried, which exceptions can be skipped, limits on the number of attempts or skipped items, rollback policy, backoff, and related listeners.

This builder is created from `SimpleStepBuilder` via the `faultTolerant()` method. It does not automatically make every error recoverable. The application must still classify exceptions according to business logic, design the Reader/Processor/Writer to handle re-invocation safely, and clearly define which data is allowed to be skipped.

## 1. Where does FaultTolerantStepBuilder fit in Step configuration?

A typical chunk-oriented Step has an `ItemReader`, `ItemProcessor`, and `ItemWriter`. Without fault tolerance configured, an unhandled exception causes the Step to fail according to the transaction policy.

When retry or skip is needed, call `.faultTolerant()` on the chunk Step builder:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, ProcessedOrder>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(20)
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
```

`faultTolerant()` transitions the configuration to `FaultTolerantStepBuilder`, adding methods related to skip, retry, and rollback. The Reader, Processor, Writer, and commit interval components are still configured just like in a regular chunk Step.

The builder is a configuration API at Step creation time. When the Job runs, Spring Batch uses the configured policies to coordinate transactions and handle exceptions.

## 2. Fault tolerance does not mean ignoring every error

The goal of fault tolerance is to distinguish recoverable errors from errors that should stop the Job. For example:

| Error type | Typically appropriate behavior |
|---|---|
| Malformed CSV line, invalid record | Skip if business rules allow excluding that record. |
| Temporary database deadlock or recoverable connection error | Retry with a limit and backoff. |
| Missing required configuration or wrong schema | Usually fail immediately so operators fix the configuration. |
| Programming error such as unexpected `NullPointerException` | Usually fail; do not skip to hide bugs. |
| Item violating a business rule that cannot be skipped | Fail or route to a separate handling workflow. |

Do not broadly configure `.skip(Exception.class)`. That can allow a Job to complete even when infrastructure errors, programming bugs, or serious data errors have occurred. Choose specific exceptions with a clear business rationale.

## 3. Skipping exceptions with skip() and skipLimit()

`skip()` declares the exception types allowed to be skipped. `skipLimit()` sets the limit on the total number of skips for a Step execution, counted across read, process, and write errors.

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, ProcessedOrder>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(FlatFileParseException.class)
        .skip(InvalidOrderException.class)
        .skipLimit(10)
        .build();
```

In this example, unparseable file lines and invalid orders can be skipped. The maximum total skip count is 10. When a subsequent skippable error exceeds the limit, the Step fails.

`skipLimit` is a combined limit across read skip, process skip, and write skip, not 10 errors per phase.

| Cumulative skip count | Result with `skipLimit(10)` |
|---:|---|
| 0–9 | Eligible errors can continue to be skipped. |
| 10 | The 10th error is still within the limit. |
| 11 | The next error exceeds the limit and causes the Step to fail. |

If no skip rule is configured, errors are not considered skippable by default. You can use `noSkip()` to exclude a specific exception from a broader skip group already declared:

```java
.faultTolerant()
.skip(Exception.class)
.noSkip(IllegalStateException.class)
.skipLimit(10)
```

However, declaring skip on a broad superclass and then excluding individual exceptions easily misses edge cases. It is usually better to list the specific skippable exceptions upfront.

## 4. Skipping in Reader, Processor, and Writer

Spring Batch can skip errors in all three phases of a chunk:

### Read skip

The Reader throws an exception while reading data. For example, `FlatFileItemReader` encounters a malformed line and throws `FlatFileParseException`. If the exception is configured as skippable, the framework can skip the bad line and continue reading.

### Process skip

The Processor throws an exception when an item fails a business rule, such as a missing customer code or an invalid monetary amount. If the exception is allowed to be skipped, that item is not passed to the Writer.

### Write skip

The Writer throws an exception while writing data. This case is more complex because the Writer typically receives an entire chunk. Spring Batch may need to isolate the failing item by retrying or writing in smaller batches depending on the configuration and the Writer's capabilities.

The corresponding counters on `StepExecution`:

| Counter | Meaning |
|---|---|
| `readSkipCount` | Number of read errors skipped. |
| `processSkipCount` | Number of processing errors skipped. |
| `writeSkipCount` | Number of write errors skipped. |
| `skipCount` | Total number of skips. |
| `filterCount` | Number of items filtered because the Processor returned `null`; not a skip. |

In operations, inspect each counter separately to see whether errors come from the read source, processing rules, or write target. A Job with a high `skipCount` may complete, yet input data quality still needs investigation.

## 5. Retrying exceptions with retry() and retryLimit()

Retry is suitable for transient errors that are likely to resolve on re-attempt, such as deadlocks or short-lived database access errors. `retry()` declares the exception types allowed to be retried; `retryLimit()` caps the number of attempts according to the policy.

```java
import org.springframework.dao.TransientDataAccessException;

return new StepBuilder("updateOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
```

`TransientDataAccessException` is the family of data access errors considered potentially transient. You can choose a more specific exception if you only want to retry a particular error type.

Retry differs from skip:

- Retry re-attempts the failed operation in hopes that the next attempt succeeds.
- Skip accepts dropping the item after the error is classified as skippable and the limit has not been exceeded.
- If retries are exhausted and the exception is also in the skip group, the skip policy may allow skipping the item; otherwise, the Step fails.

Do not retry indefinitely. Excessive retries can prolong the Job, hold resources, and overload the target system. Retry also cannot fix permanent data errors such as malformed dates or missing required codes.

## 6. Backoff between retry attempts

If retry attempts happen immediately, multiple workers may retry simultaneously while the service is overloaded or the database is experiencing contention. Backoff introduces a wait interval between attempts to give the system time to recover.

Spring Retry provides backoff policies that can be configured with `FaultTolerantStepBuilder`. For example, using `ExponentialBackOffPolicy`:

```java
import org.springframework.retry.backoff.ExponentialBackOffPolicy;

ExponentialBackOffPolicy backOffPolicy = new ExponentialBackOffPolicy();
backOffPolicy.setInitialInterval(500L);
backOffPolicy.setMultiplier(2.0);
backOffPolicy.setMaxInterval(5_000L);

return new StepBuilder("updateOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .backOffPolicy(backOffPolicy)
        .build();
```

The example starts with a 500 ms wait, increases the interval by a multiplier of 2, and caps it at 5 seconds. Specific values depend on SLAs, target system timeouts, and the number of concurrent workers.

Backoff does not replace database or HTTP client timeouts. If a call hangs without a timeout, the retry policy may not regain control in time. Configure timeouts for every external resource.

## 7. Using custom RetryPolicy and SkipPolicy

`retry()`/`retryLimit()` and `skip()`/`skipLimit()` work well for simple rules. When conditions depend on more factors, you can use custom policies.

### SkipPolicy

`SkipPolicy` decides whether an exception should be skipped based on the exception and the current skip count:

```java
import org.springframework.batch.core.step.skip.SkipLimitExceededException;
import org.springframework.batch.core.step.skip.SkipPolicy;

public class OrderSkipPolicy implements SkipPolicy {

    @Override
    public boolean shouldSkip(Throwable throwable, long skipCount)
            throws SkipLimitExceededException {

        if (throwable instanceof InvalidOrderException) {
            return skipCount < 10;
        }

        return false;
    }
}
```

Registering the policy:

```java
.faultTolerant()
.skipPolicy(new OrderSkipPolicy())
```

When using `skipPolicy`, the policy is responsible for deciding both the skip condition and the skip limit. Avoid simultaneously adding multiple `skip()`/`skipLimit()` rules that make the policy confusing.

### RetryPolicy

A custom `RetryPolicy` can decide whether to retry an exception based on error type, attempt count, or context information. It can be registered with `.retryPolicy(...)` when you need a policy beyond a simple exception list and retry limit.

For example, a system might retry database connection errors but not validation errors. When using a custom policy, write clear unit tests for each exception and retry threshold; avoid keeping mutable counters in a singleton policy if the policy is shared across multiple Steps or JobExecutions.

## 8. Distinguishing retry and rollback

Retry does not mean the current transaction continues from the exact failing statement. In chunk processing, an exception may roll back the chunk transaction before the framework performs the next attempt. The retry attempt may run in a new transaction.

```text
Chunk attempt 1
  BEGIN
  READ / PROCESS / WRITE
  Deadlock exception
  ROLLBACK
       |
       v
Backoff
       |
       v
Chunk attempt 2
  BEGIN
  Re-execute required operations
  WRITE succeeds
  COMMIT
```

Previously committed chunks are preserved. The failing chunk may have to be reprocessed. Therefore, the Processor and Writer must tolerate being invoked again, and side effects outside the transaction need an idempotency key or transactional outbox.

If a Writer both updates the database and makes an HTTP call, rolling back the database cannot undo an HTTP request already processed by the external system. A retry may send the request again. Avoid executing non-idempotent side effects directly in the retry path.

## 9. noRollback() adjusts the rollback policy

By default, many exceptions during chunk processing cause the transaction to roll back. `noRollback()` specifies an exception that does not roll back the transaction:

```java
.faultTolerant()
.skip(NonCriticalValidationException.class)
.noRollback(NonCriticalValidationException.class)
```

The two configurations have different roles:

- `skip()` determines which exceptions can be skipped.
- `noRollback()` controls whether that exception triggers a transaction rollback.

`noRollback()` does not mean the exception disappears or the item is automatically written. The exception must still be handled according to the skip/retry policy and execution flow. Use it only when the transaction state remains consistent without a rollback.

For example, if the Processor detects a validation condition that does not affect any data already modified in the transaction, `noRollback` might be considered. However, if the Writer has already written partial data and then encounters an exception, allowing a commit may leave an incomplete state. Carefully analyze the exact timing and impact of the exception before applying it.

## 10. processorNonTransactional() and Processor re-invocation

In a fault-tolerant Step, an item may go through processing logic again when a chunk rolls back or retries. If the Processor is non-transactional and re-invoking it is unnecessary, you can use `processorNonTransactional()` so Spring Batch caches the processing result and avoids calling the Processor again for an already-processed item in applicable retry scenarios.

```java
return new StepBuilder("enrichOrdersStep", jobRepository)
        .<Order, EnrichedOrder>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .processorNonTransactional()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
```

This option is appropriate when the Processor produces a deterministic result for the same input and does not need to run again after a rollback. It does not make the Processor thread-safe, nor does it protect the Writer's side effects. If the Processor depends on external data that can change between attempts or has side effects that need to re-execute, think carefully before caching results.

## 11. KeyGenerator and item identification during retry

In some cases, the framework needs to identify already-processed items to manage caching/retry. If the item's `equals()` and `hashCode()` do not accurately reflect business identity, you can configure a `KeyGenerator` to produce a stable key.

```java
import org.springframework.batch.item.KeyGenerator;

KeyGenerator orderKeyGenerator = item -> {
    Order order = (Order) item;
    return order.sourceSystem() + ":" + order.sourceOrderId();
};
```

Registering it in the fault-tolerant Step configuration:

```java
.faultTolerant()
.keyGenerator(orderKeyGenerator)
```

The key must be stable across retries and restarts. Do not use an in-memory index or a fresh UUID on every call. `KeyGenerator` supports item identification within the internal mechanism of fault-tolerant processing; it does not replace database unique constraints and does not by itself prevent duplicate business records.

## 12. Attaching SkipListener to record skipped items

`SkipListener` provides separate callbacks for read, process, and write errors:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;

public class OrderSkipListener
        implements SkipListener<Order, ProcessedOrder> {

    private static final Logger log =
            LoggerFactory.getLogger(OrderSkipListener.class);

    @Override
    public void onSkipInRead(Throwable throwable) {
        log.warn("Read skip: {}", throwable.getMessage());
    }

    @Override
    public void onSkipInProcess(Order item, Throwable throwable) {
        log.warn("Process skip for order {}: {}",
                item.sourceOrderId(), throwable.getMessage());
    }

    @Override
    public void onSkipInWrite(ProcessedOrder item, Throwable throwable) {
        log.warn("Write skip for order {}: {}",
                item.sourceOrderId(), throwable.getMessage());
    }
}
```

Registering the listener in the builder:

```java
.faultTolerant()
.skip(InvalidOrderException.class)
.skipLimit(10)
.listener(orderSkipListener)
```

`onSkipInRead()` has no item parameter because the Reader may fail before constructing the object. For file parsing errors, you can extract the line number and source details from a specific exception such as `FlatFileParseException`.

If the listener writes rejects to a database, file, or sends messages, remember that the chunk may roll back and items may be reprocessed. Use a unique key scoped to JobInstance/business key, upsert, or an outbox to avoid duplicate reject records and notifications.

## 13. Complete FaultTolerantStepBuilder example

The following example combines retry, backoff, skip, noRollback, and SkipListener:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, ProcessedOrder> orderProcessor,
        ItemWriter<ProcessedOrder> orderWriter,
        OrderSkipListener orderSkipListener) {

    ExponentialBackOffPolicy backOffPolicy = new ExponentialBackOffPolicy();
    backOffPolicy.setInitialInterval(500L);
    backOffPolicy.setMultiplier(2.0);
    backOffPolicy.setMaxInterval(5_000L);

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, ProcessedOrder>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .faultTolerant()
            .retry(TransientDataAccessException.class)
            .retryLimit(3)
            .backOffPolicy(backOffPolicy)
            .skip(FlatFileParseException.class)
            .skip(InvalidOrderException.class)
            .skipLimit(10)
            .noRollback(NonCriticalValidationException.class)
            .listener(orderSkipListener)
            .build();
}
```

`Order`, `ProcessedOrder`, `InvalidOrderException`, and `NonCriticalValidationException` are application domain types. `FlatFileParseException` must be imported from the Spring Batch FlatFile module. The configuration above is only an example: `NonCriticalValidationException` should only be used in `noRollback` if the transaction remains safe without rolling back. If that exception does not need to be skipped, do not add it to the skip policy just to keep the Step running.

In real systems, choose retry and skip exceptions so they do not overlap unintentionally. If an exception is configured for both retry and skip, understand the policy order and the outcome after retries are exhausted. Writing tests for key exception types helps prevent a configuration that looks reasonable from producing unexpected behavior.

## 14. FaultTolerantStepBuilder and restart

Retry/skip typically handles errors within the same Step execution. If the Step still fails, the Job can be restarted with the same identifying JobParameters if the Job allows restarts.

```text
JobExecution #1: FAILED
  Chunk 1: COMMITTED
  Chunk 2: contains skipped item, COMMITTED
  Chunk 3: retries exhausted, ROLLED BACK

Restart same JobInstance
  |
  v
JobExecution #2
  Reader restores checkpoint after Chunk 2
  Chunk 3 is reprocessed
```

Key points to keep in mind:

- The Reader must support state persistence if it needs to resume from a checkpoint.
- Items in already-committed chunks, including skipped items, are normally not re-read on a standard restart.
- Items belonging to a rolled-back chunk may be re-read and reprocessed.
- `SkipListener` may be called again for items reprocessed after a rollback; reject writes must be idempotent.
- The Writer must tolerate retry/restart and not create duplicate data.
- Do not change identifying JobParameters if the goal is to restart the same JobInstance.

`FaultTolerantStepBuilder` does not guarantee restartability on its own. It configures how errors are handled inside the Step; restart also depends on `JobRepository`, `ExecutionContext`, `ItemStream`, and business data design.

## 15. Impact of transactions and external side effects outside the database

Retry often goes hand in hand with rollback. If the Writer updates a database and calls an external API in the same write call, rolling back the database cannot revoke an API call that already succeeded.

For example:

```text
Chunk transaction
  |
  +--> UPDATE imported_order
  +--> POST event to external service (success)
  +--> Error on another item
  |
  +--> ROLLBACK database
  |
  +--> Retry may send the same external event again
```

Approaches to handle this:

1. Use a stable idempotency key when calling APIs.
2. Write events to a transactional outbox in the same transaction as the business data.
3. Have a separate Step send messages after the data has committed.
4. Use a compensating action if the external system does not support idempotency and the action may need to be undone.

Do not put `REQUIRES_NEW` on every operation in the Writer to avoid rollback. That can commit partial data while the outer chunk fails, complicating restarts and consistency.

## 16. Testing fault-tolerant configurations

Test each policy individually along with several integration scenarios. Do not just assert that the Job ends with `COMPLETED`; verify which items were written, which items were skipped, and which operations were retried.

### Testing SkipPolicy

```java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class OrderSkipPolicyTest {

    private final OrderSkipPolicy policy = new OrderSkipPolicy();

    @Test
    void skipsInvalidOrderWithinLimit() throws Exception {
        assertTrue(policy.shouldSkip(
                new InvalidOrderException("Invalid amount"), 2));
    }

    @Test
    void doesNotSkipUnexpectedException() throws Exception {
        assertFalse(policy.shouldSkip(
                new IllegalStateException("Unexpected state"), 0));
    }
}
```

### Testing retry

You can mock a dependency so that the first call throws a transient error and the next call succeeds. Verify the invocation count matches the limit and the result is written only once. For custom retry policies, test both retryable and non-retryable exceptions.

### Testing the Step

With `spring-batch-test` and `JobLauncherTestUtils`, create test data containing valid items, skippable items, and items causing non-retryable errors. Verify:

- `BatchStatus` and `ExitStatus` of the Job/Step.
- `readSkipCount`, `processSkipCount`, `writeSkipCount`, and `filterCount`.
- Invocation counts of Reader/Processor/Writer if that is an important requirement.
- Contents of target tables and reject tables.
- Behavior when restarting the same JobInstance after a chunk rollback.
- No duplicate records or notifications.

When testing retry, use a deterministic recoverable error so the test does not depend on external networks or databases. When testing real deadlocks, maintain a separate integration test with an appropriate database and clear timeouts.

## 17. Common configuration mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Skipping `Exception.class` too broadly | Programming or infrastructure errors are ignored. | Only skip explicitly defined business exceptions. |
| Confusing `skipLimit` with `retryLimit` | Incorrect error behavior limits. | Skip limit counts skipped items; retry limit caps attempt counts. |
| Retrying permanent data errors | The Job wastes time on errors that cannot self-heal. | Use validation/skip or fail according to business rules. |
| Retrying without backoff | Workers may repeatedly overload a struggling system. | Use appropriate backoff and timeouts. |
| Using `noRollback()` as a way to ignore exceptions | Transactions may commit incomplete data. | Distinguish rollback policy from skip policy and verify consistency. |
| Processor has side effects while cached via `processorNonTransactional()` | Results or side effects no longer match subsequent attempts. | Use only when the Processor is safe, deterministic, and needs no re-execution. |
| Non-idempotent Writer | Retry or restart creates duplicate data. | Unique constraints, upsert, idempotency key, or outbox. |
| SkipListener writes rejects directly without deduplication | Reprocessed items can create duplicate reject records. | Use unique keys and idempotent writes. |
| Configuring policies without testing the exception hierarchy | Exception subclasses may be classified unexpectedly. | Test both specific exceptions and related superclasses/subclasses. |

## Conclusion

`FaultTolerantStepBuilder` extends chunk Step configuration to handle errors via retry, skip, and rollback policies. `skip()`/`skipLimit()` determines which items may be skipped and caps total skips; `retry()`/`retryLimit()` with backoff handles transient errors; `noRollback()` adjusts whether an exception rolls back the transaction. `SkipPolicy`, `RetryPolicy`, `SkipListener`, `processorNonTransactional()`, and `KeyGenerator` support cases requiring finer control. Fault tolerance configuration is only reliable when paired with a checkpoint-capable Reader, an idempotent Writer, proper handling of non-transactional side effects, and realistic restart testing.
