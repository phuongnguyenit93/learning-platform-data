# RetryListener

In Spring Batch, `RetryListener` is a hook that allows an application to observe the lifecycle of an operation executed under retry. The listener can log each failed attempt, collect metrics, record diagnostic metadata, or perform supplementary actions when a retry operation opens and closes.

`RetryListener` belongs to Spring Retry's retry mechanism, which Spring Batch uses in chunk Steps configured with fault tolerance. The listener helps observe the retry process, while `RetryPolicy` and Step configuration decide which exceptions are retried and the maximum number of attempts. Therefore, the listener does not replace `.retry(...)`, `.retryLimit(...)`, or the skip policy.

## 1. Where Does RetryListener Fit in Spring Batch?

In a chunk-oriented Step, the reader, processor, or writer can throw an exception. If the exception is configured as retryable, Spring Batch uses the retry mechanism to re-attempt the operation according to the declared policy.

```text
Chunk Step
   |
   v
Reader / Processor / Writer
   |
   +-- Succeeds -------------------------> Continue chunk
   |
   +-- Throws exception
          |
          v
      RetryPolicy
          |
          +-- Retries remaining? --------> Retry callback
          |                                  |
          |                                  v
          |                             RetryListener
          |
          +-- Retries exhausted / no retry
                    |
                    v
             Skip policy or Step failure
```

`RetryListener` receives callbacks throughout the lifecycle of a retry execution. It is commonly used to observe:

- When a retry operation begins.
- When an attempt ends with an exception.
- When the retry operation finishes with success or failure.

The listener does not itself decide whether an exception is retried. That decision belongs to Spring Retry's retry policy and the fault-tolerant Step configuration.

## 2. RetryListener Comes from Spring Retry

The `RetryListener` interface resides in the `org.springframework.retry` package. Its core contract consists of three callbacks:

```java
public interface RetryListener {

    <T, E extends Throwable> boolean open(
            RetryContext context,
            RetryCallback<T, E> callback);

    <T, E extends Throwable> void onError(
            RetryContext context,
            RetryCallback<T, E> callback,
            Throwable throwable);

    <T, E extends Throwable> void close(
            RetryContext context,
            RetryCallback<T, E> callback,
            Throwable throwable);
}
```

Newer Spring Retry versions may add other default callbacks depending on the library version. The three callbacks above are the primary ones to understand when integrating the listener with Spring Batch.

### open

`open` is called when a retry operation begins, before any attempts are executed. It receives `RetryContext` and `RetryCallback`.

The method returns a boolean:

- `true`: allows the retry operation to start.
- `false`: instructs Spring Retry to terminate the retry operation before executing the callback, per the framework's retry termination mechanism.

Normally, the listener returns `true`. Return `false` only when there is an explicit reason to prevent the operation from starting; do not use this callback to replace input validation or business logic.

### onError

`onError` is called when a callback execution ends with an exception. If the policy permits another attempt, the callback may run again.

This is an appropriate place to:

- Record the exception type and retry count.
- Increment a failed-attempt metric.
- Log correlation details such as `JobExecution` ID or an approved business key.
- Monitor frequently occurring transient errors.

Do not treat every `onError` invocation as the final failure of the item. An exception may be transient on one attempt, and a subsequent retry can succeed.

### close

`close` is called when the retry operation ends. The `throwable` parameter holds the final error if the operation ended in failure; on success, there is normally no final throwable.

This callback is suited for:

- Recording the final outcome of the retry operation.
- Closing a metric or trace opened in `open`.
- Logging retry success after one or more failures.
- Recording retry exhaustion if the operation failed after reaching the limit.

Do not put critical business data-writing logic inside `close`. The listener is an observation and operational support point; it does not replace the writer or the chunk transaction.

## 3. What Information Does RetryContext Hold?

`RetryContext` is the context of a retry operation. It tells the listener how many attempts the operation has made and what the latest exception is.

Commonly used APIs:

| API | Meaning |
|---|---|
| `getRetryCount()` | Number of retries recorded in the current context. |
| `getLastThrowable()` | Most recent recorded exception. |
| `getAttribute(key)` | Reads an attribute attached to the context. |
| `setAttribute(key, value)` | Stores an attribute in the context. |
| `removeAttribute(key)` | Removes an attribute from the context. |

`RetryContext` has a lifecycle tied to the retry operation. It is useful for sharing data across callbacks of the same operation, such as start time, correlation ID, or a flag indicating an error occurred.

Do not confuse `RetryContext` with `ExecutionContext`:

| Object | Purpose |
|---|---|
| `RetryContext` | Temporary state of a single retry operation within the running process. |
| `ExecutionContext` | Job/Step state persisted durably in `JobRepository` to support sharing and restarts. |

`RetryContext` is not a durable checkpoint. Do not use it to replace reader checkpoints or store progress that must survive a process stop.

## 4. Implementing RetryListener

You can implement `RetryListener` to log when an operation starts, fails an attempt, and finishes.

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.retry.RetryCallback;
import org.springframework.retry.RetryContext;
import org.springframework.retry.RetryListener;

public class BatchRetryListener implements RetryListener {

    private static final Logger log =
            LoggerFactory.getLogger(BatchRetryListener.class);

    @Override
    public <T, E extends Throwable> boolean open(
            RetryContext context,
            RetryCallback<T, E> callback) {

        log.debug("Retry operation started");
        return true;
    }

    @Override
    public <T, E extends Throwable> void onError(
            RetryContext context,
            RetryCallback<T, E> callback,
            Throwable throwable) {

        log.warn("Retry attempt {} failed: {}",
                context.getRetryCount(),
                throwable.getClass().getSimpleName());
    }

    @Override
    public <T, E extends Throwable> void close(
            RetryContext context,
            RetryCallback<T, E> callback,
            Throwable throwable) {

        if (throwable == null) {
            log.debug("Retry operation completed successfully");
        } else {
            log.error("Retry operation exhausted or terminated", throwable);
        }
    }
}
```

This example only logs and does not alter the retry policy. `getRetryCount()` provides the attempt count recorded in the context; how attempt numbers are displayed should follow the semantics of the Spring Retry version in use, avoiding assumptions that every callback invocation starts from the exact same number.

In production applications, add `JobExecution` ID, `StepExecution` ID, or business keys if they can be retrieved safely. Avoid logging full items or sensitive data.

## 5. Registering RetryListener on a Fault-Tolerant Step

In Spring Batch 5, `RetryListener` can be registered on `FaultTolerantStepBuilder` alongside the retry configuration:

```java
@Bean
RetryListener batchRetryListener() {
    return new BatchRetryListener();
}

@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter,
        RetryListener batchRetryListener) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(200, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .faultTolerant()
            .retry(TransientDataAccessException.class)
            .retryLimit(3)
            .listener(batchRetryListener)
            .build();
}
```

In the example:

- `.faultTolerant()` enables fault-tolerance configuration for the chunk Step.
- `.retry(TransientDataAccessException.class)` specifies the error type eligible for retry.
- `.retryLimit(3)` sets the retry limit according to Spring Batch configuration.
- `.listener(batchRetryListener)` registers callbacks observing the retry lifecycle.

`RetryListener` does not automatically make any arbitrary exception retryable. If an exception is not permitted by the policy, the listener cannot turn it into a retryable error simply by logging in `onError`.

## 6. How Does RetryListener Differ from RetryPolicy?

These two components have distinct responsibilities:

| Component | Responsibility |
|---|---|
| `RetryPolicy` | Decides whether to retry the current exception or whether the limit is exhausted. |
| `RetryListener` | Observes the retry lifecycle and receives details about attempts. |
| `BackOffPolicy` | Controls the wait interval between retry attempts. |
| `SkipPolicy` | Decides whether a failing item can be skipped after an exception occurs. |
| `SkipListener` | Receives callbacks when an item is actually skipped. |

For example, a Step configures retry for `TransientDataAccessException`. When the writer encounters this exception, the retry policy determines whether to retry. `RetryListener` records the failed attempt. If retries are exhausted, the Step may fail or handle the error via the skip policy if the exception is also skippable and fault-tolerance flow permits it.

Do not place business decisions like "skip this record" inside `RetryListener`. Use a processor returning `null` for filtering, a skip policy for skippable exceptions, and a retry policy for recoverable errors.

## 7. Distinguishing RetryListener from Other Listeners

Spring Batch has multiple listener types invoked at different stages. Choosing the right listener keeps code clear and avoids putting logic in the wrong callback.

| Listener | When Called | Primary Purpose |
|---|---|---|
| `RetryListener` | During a retry operation lifecycle | Observe retry attempts and final outcome. |
| `SkipListener` | When an item is skipped due to an exception | Record the skipped item and reason. |
| `StepExecutionListener` | Before/after a Step | Audit Step status and exit status. |
| `ChunkListener` | Before/after a chunk | Observe chunk boundaries. |
| `ItemReadListener` | Before/after reading or on read error | Observe the reader. |
| `ItemProcessListener` | Before/after processing or on processor error | Observe the processor. |
| `ItemWriteListener` | Before/after writing or on writer error | Observe the writer. |

For example, if you need to know that an order was ultimately skipped after exhausting retries, `SkipListener` is the right place to record the item. `RetryListener` only tells you the operation had failed attempts and how it ended.

## 8. RetryListener and Retries in Reader, Processor, and Writer

In a fault-tolerant chunk Step, errors can occur in any component. The retry listener attaches to the Step's retry mechanism and observes retry operations executed by the framework.

### Reader

The reader can hit transient errors when accessing a data source, such as connection timeouts. If the exception is configured for retry, the listener can record the attempts. With file readers or non-transactional sources, understand how buffering and read-position recovery work on rollback.

### Processor

The processor may call reference services or perform computations depending on external systems. When transient errors occur, retry can be appropriate. However, the processor should avoid non-idempotent side effects because it can be called again.

### Writer

The writer may encounter deadlocks or temporary database access errors. Retry can help recover. In some write-retry situations, Spring Batch may roll back and re-invoke the writer with the chunk or smaller groups of items to isolate the failure. Do not assume each callback corresponds to exactly one single item.

Because retry granularity can depend on error type and chunk handling, the listener should record context and exception type rather than inferring that one `onError` call always represents a single distinct business item.

## 9. Tracking Retry Counts and Exceptions

`RetryContext` lets you read the attempt count and the latest exception. You can use this data to build metrics:

```java
@Override
public <T, E extends Throwable> void onError(
        RetryContext context,
        RetryCallback<T, E> callback,
        Throwable throwable) {

    retryAttemptsCounter.increment();

    log.warn("Retry count={}, exceptionType={}",
            context.getRetryCount(),
            throwable.getClass().getName());
}
```

In an application with Micrometer, you can record counters or timers tagged by Job/Step name and exception type. Limit the tag set to avoid high cardinality; do not put order ID, customer ID, or arbitrary exception messages into metric tags.

Useful metrics:

- Total retry attempts.
- Operations completing successfully after retry.
- Operations exhausting retries and failing.
- Retry rate by exception type.
- Duration from retry open to close.

A steadily rising retry count may indicate an overloaded database, an unstable external service, or overly tight timeouts. Use metrics to find root causes rather than simply increasing the retry limit.

## 10. Logging Safely in RetryListener

`RetryListener` is typically invoked when errors happen, so logs must provide sufficient diagnostic info without leaking data.

Do log:

- Job and Step names when context is available.
- `JobExecution` ID or `StepExecution` ID.
- Exception type and attempt count.
- Business keys approved for logging.
- Final outcome of the retry operation.

Avoid logging:

- Passwords, tokens, API keys, or secrets.
- Full payloads containing personal data.
- SQL statements with sensitive parameters.
- Exception messages if they contain sensitive details from external systems.

If the listener needs access to execution context, obtain details from the appropriate context or pass correlation IDs. Do not store large business payloads in `RetryContext` just for logging.

## 11. Thread Safety and Listener Scope

Listeners are typically registered as shared beans. In applications with multiple concurrent Jobs or multi-threaded Steps, callbacks can be called from multiple threads.

Therefore:

- Do not store per-operation retry counts in mutable fields of a singleton listener.
- Use `RetryContext` to hold data belonging to a single retry operation.
- Use thread-safe metric implementations.
- If writing audit records to a database, use a transactional service with proper deduplication.
- Do not retain references to items or exceptions longer than the required lifecycle.

For example, do not use a `currentRetryCount` field in a singleton listener to track individual items; two concurrent operations can overwrite each other's values. Data specific to a retry operation belongs in `RetryContext` or a structure keyed by execution/correlation ID.

## 12. Combining RetryListener with BackOffPolicy

Rapid consecutive retries can put heavy load on a struggling database or external service. `BackOffPolicy` controls the wait interval between attempts; `RetryListener` observes the attempts and outcomes.

Example configuring a timed backoff:

```java
.faultTolerant()
.retry(TransientDataAccessException.class)
.retryLimit(4)
.backOffPolicy(new ExponentialBackOffPolicy())
.listener(batchRetryListener)
```

`ExponentialBackOffPolicy` increases the wait interval between attempts according to the policy configuration. You can configure the initial interval, multiplier, and maximum interval as needed. Balance wait times against maximum Job runtime and business SLAs.

The listener does not introduce backoff itself. To adjust wait intervals, configure `BackOffPolicy`; to record attempts, use `RetryListener`.

## 13. When Retries Are Exhausted

When the retry policy no longer permits further attempts, the retry operation ends with the final exception. The `close` callback can record the failed outcome. Afterward, Step behavior depends on fault-tolerance configuration:

- If the exception is skippable and the skip limit is not exceeded, the item may be skipped.
- If the exception is not skippable, the Step typically fails.
- If appropriate recovery logic is configured, the framework may run a post-retry recovery branch per configuration.

Do not assume `RetryListener` can itself decide what happens after retry exhaustion. Use retry policy, skip policy, recovery callbacks, or Job flow transitions to define that behavior.

## 14. RetryListener and Idempotency

Retrying means an operation can execute multiple times. If the operation produces side effects, ensure repetition does not corrupt data.

For example, a writer sends a payment request to an external API. If the API processed the request but the response timed out, Spring Batch may retry and send the request again. If the API lacks idempotency support, the customer could be charged twice.

Mitigations:

- Use stable idempotency keys tied to the business operation.
- Use unique business keys or upserts when writing to a database.
- Avoid calling APIs or sending emails inside processors or writers if retries cannot be controlled safely.
- Use a transactional outbox to publish events after the primary data transaction commits.
- Record request states for reconciliation before retrying high-impact operations.

`RetryListener` helps observe retries, but it does not make a non-idempotent operation safe. Idempotency must be guaranteed by the business design and target systems.

## 15. Testing RetryListener

You can unit-test the listener independently by calling callbacks with an appropriate `RetryContext`, or integration-test a Step experiencing transient failures.

Cases to verify:

- `open` is invoked when a retry operation begins.
- `onError` records the exception of a failed attempt.
- When a subsequent retry succeeds, `close` records a successful operation.
- When the retry limit is exhausted, `close` receives the final error.
- The listener does not alter retry policy or swallow exceptions.
- Concurrent retry operations do not mix state.
- Logs and metrics contain no sensitive data.

A simple listener unit test can use a mock logger/metric or a thread-safe recorder to verify callbacks. Step-level integration tests are more valuable when confirming Spring Batch actually invokes the listener according to the configured retry policy.

## 16. Common Pitfalls

### Thinking RetryListener decides whether an exception is retried

The listener primarily observes the retry lifecycle. `.retry(...)`, `.retryLimit(...)`, or `RetryPolicy` decides whether an exception is retried.

### Treating every onError as a final failure

`onError` is called for a single failed attempt; the operation may still succeed afterward. Check the `close` callback and Step status for the final result.

### Using RetryListener to skip items

The listener does not replace `SkipPolicy` or `SkipListener`. Explicitly configure skipping for item-level exceptions allowed to be ignored.

### Retrying every exception

Retrying permanent data errors or programming bugs will not help recovery. Only retry exceptions likely to be transient and operations that are safe to repeat.

### Storing per-operation state in a singleton field

Multiple concurrent executions may share the listener. Use `RetryContext` or thread-safe state keyed by correlation ID.

### Logging full payloads

Retries frequently happen around bad data or external errors. Uncontrolled payload logging can expose personal data or secrets. Log only business keys and approved details.

### Thinking retry guarantees exactly-once execution

Retries can re-invoke an operation. You need idempotency, unique keys, or an outbox to prevent duplicate side effects.

## 17. Workflow for Implementing RetryListener

When adding `RetryListener` to a chunk Step, follow this sequence:

1. Identify transient exception types that are genuinely retryable.
2. Configure `.faultTolerant()`, `.retry(...)`, and `.retryLimit(...)` on the Step.
3. Choose a `BackOffPolicy` if a wait interval is needed between attempts.
4. Implement `RetryListener` with `open`, `onError`, and `close`.
5. Use `RetryContext` to read the retry count and latest exception.
6. Register the listener via `.listener(retryListener)` on the fault-tolerant Step builder.
7. Emit metrics/logs by Job, Step, and exception type; avoid logging sensitive payloads.
8. Ensure the listener is thread-safe if Jobs/Steps can run concurrently.
9. Test successful retry, retry exhaustion, post-retry skip, and side effects when operations are re-invoked.
10. Monitor retry rates to tune policies and address root causes.

## Conclusion

`RetryListener` is a Spring Retry hook used by Spring Batch in fault-tolerant Steps to observe the retry lifecycle. `open` runs when the operation starts, `onError` records a failed attempt, and `close` runs when the operation concludes. The listener can use `RetryContext` to track retry counts and the latest exception, write logs, or emit metrics. It does not replace `RetryPolicy`, `.retry(...)`, `.retryLimit(...)`, `BackOffPolicy`, or `SkipListener`. Retry only recoverable errors, keep listeners thread-safe, and ensure operations with side effects are designed to be idempotent.
