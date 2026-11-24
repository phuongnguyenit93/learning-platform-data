# Retry listener

`RetryListener` is a Spring Retry callback that lets you observe the lifecycle of a retry operation. In Spring Batch, this listener can be attached to a fault-tolerant chunk step to record when a retry operation begins, each failed attempt, and the final outcome.

Listeners are useful for logging, metrics, tracing, and diagnosing transient errors. They let you track retries without embedding observability logic into readers, processors, or writers. However, a listener does not replace `RetryPolicy`, `BackOffPolicy`, skip policy, or transaction manager: each component has its own responsibility.

## 1. Where does RetryListener sit in batch processing?

In a chunk-oriented step, Spring Batch can retry operations when the reader, processor, or writer encounters an exception configured as retryable. The retry mechanism invokes `RetryListener` callbacks around the retry operation.

```text
Chunk processing
      |
      v
Reader / Processor / Writer
      |
      +-- success ------------------------> continue chunk
      |
      +-- retryable exception
               |
               v
        RetryListener.open()
               |
               v
        Execute callback
               |
               +-- failure --> RetryListener.onError()
               |                    |
               |                    v
               |              RetryPolicy decides
               |                    |
               |                    +-- retry again
               |                    +-- end retry
               |
               +-- success
               |
               v
        RetryListener.close()
               |
               v
        Chunk continues recovery/commit
```

`RetryListener` observes a single retry operation. In a chunk with multiple failing items or multiple retries, the listener can be invoked many times within a single step execution. Do not assume this listener runs only once per job.

## 2. Main callbacks

In Spring Batch 5, the listener comes from the `org.springframework.retry` package. The core callbacks are:

| Callback | Timing | Purpose |
|---|---|---|
| `open(context, callback)` | Before the first execution of the retry operation | Initialize observability data or decide whether the operation is allowed to start |
| `onError(context, callback, throwable)` | After each unsuccessful execution | Record the exception and failed attempt |
| `close(context, callback, throwable)` | After the final attempt, whether succeeded or failed | Summarize the outcome and clean up temporary state |

`open` returns a `boolean`. Returning `true` lets the retry operation proceed. Returning `false` vetoes the entire operation and raises `TerminatedRetryException`; this is not the normal way to represent a non-retryable exception. Use `RetryPolicy` to decide which exceptions are retried.

`onError` is invoked after each failed attempt. If an operation is retried multiple times, this callback can be invoked multiple times for the same item or operation.

`close` is invoked once when the retry operation finishes. The `throwable` parameter represents the final exception if the operation ended in failure; when the operation succeeds, this value is normally `null`.

## 3. RetryListener in Spring Batch 5

Commonly used types live in Spring Retry:

```java
import org.springframework.retry.RetryCallback;
import org.springframework.retry.RetryContext;
import org.springframework.retry.RetryListener;
```

You can implement the `RetryListener` interface directly. The methods are generic so the callback can wrap various result and exception types.

```java
public class BatchRetryListener implements RetryListener {

    private static final Logger log =
        LoggerFactory.getLogger(BatchRetryListener.class);

    @Override
    public <T, E extends Throwable> boolean open(
            RetryContext context, RetryCallback<T, E> callback) {
        log.debug("Retry operation started");
        return true;
    }

    @Override
    public <T, E extends Throwable> void onError(
            RetryContext context,
            RetryCallback<T, E> callback,
            Throwable throwable) {
        log.warn(
            "Retry attempt {} failed: {}",
            context.getRetryCount(),
            throwable.toString()
        );
    }

    @Override
    public <T, E extends Throwable> void close(
            RetryContext context,
            RetryCallback<T, E> callback,
            Throwable throwable) {
        if (throwable == null) {
            log.debug(
                "Retry operation completed after {} retry attempt(s)",
                context.getRetryCount()
            );
        } else {
            log.error(
                "Retry operation exhausted after {} retry attempt(s)",
                context.getRetryCount(),
                throwable
            );
        }
    }
}
```

This is a basic observability listener. `context.getRetryCount()` provides the retry count recorded in the retry context; verify the exact counting behavior with integration tests against your project's Spring Retry version if metrics need to distinguish precisely between the initial attempt and additional retries.

Do not assume `onError` only runs once retries are exhausted. This callback is invoked after every failure, even when the policy still allows further attempts.

## 4. Registering the listener on a chunk step

In Spring Batch 5, `FaultTolerantStepBuilder` provides a `.listener(RetryListener)` overload to register a retry listener. The listener must be attached within the fault-tolerant step configuration.

```java
@Bean
BatchRetryListener batchRetryListener() {
    return new BatchRetryListener();
}

@Bean
Step callPartnerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Request> reader,
        ItemProcessor<Request, Response> processor,
        ItemWriter<Response> writer,
        BatchRetryListener retryListener) {

    return new StepBuilder("callPartner", jobRepository)
        .<Request, Response>chunk(20, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientPartnerException.class)
        .retryLimit(3)
        .listener(retryListener)
        .build();
}
```

In this example, `TransientPartnerException` is the error type permitted to retry. `retryLimit(3)` sets the retry limit per the builder's configuration; the listener solely observes the retry lifecycle. If different retry rules are needed per exception, configure an appropriate `RetryPolicy` and keep the listener independent of that decision.

Do not confuse the `.listener(RetryListener)` overload with overloads for `ItemReadListener`, `ItemProcessListener`, `ItemWriteListener`, `SkipListener`, or `ChunkListener`. They have different callbacks and scopes.

## 5. Using RetryContext to hold state within a retry operation

`RetryContext` holds the state of a retry operation, such as retry count, latest exception, and temporary attributes. You can use context attributes to store a start timestamp or correlation ID for logging.

```java
public class TimedRetryListener implements RetryListener {

    private static final String START_KEY = "batch.retry.startedAt";

    @Override
    public <T, E extends Throwable> boolean open(
            RetryContext context, RetryCallback<T, E> callback) {
        context.setAttribute(START_KEY, System.nanoTime());
        return true;
    }

    @Override
    public <T, E extends Throwable> void close(
            RetryContext context,
            RetryCallback<T, E> callback,
            Throwable throwable) {
        Object value = context.getAttribute(START_KEY);
        if (value instanceof Long startedAt) {
            long elapsedNanos = System.nanoTime() - startedAt;
            recordRetryDuration(elapsedNanos, throwable == null);
        }
    }
}
```

`recordRetryDuration` is an application-provided metric helper. Using attributes on `RetryContext` keeps state scoped to the exact retry operation rather than storing it in mutable fields of a singleton listener.

`RetryContext` is transient state of the retry mechanism. It does not replace Spring Batch's `ExecutionContext`, which persists durable checkpoints for restart. Do not store unique business checkpoints inside the retry context.

## 6. Which attempts can RetryListener observe?

The callbacks have distinct scopes:

- `open`: once before the retry operation starts.
- `onError`: after each unsuccessful attempt.
- `close`: once after the final attempt.

Example of an item failing twice and then succeeding:

```text
open()
  attempt 1 -> exception -> onError()
  attempt 2 -> exception -> onError()
  attempt 3 -> success
close(throwable = null)
```

Example of an item failing until the limit is exhausted:

```text
open()
  attempt 1 -> exception -> onError()
  attempt 2 -> exception -> onError()
  attempt 3 -> exception -> onError()
close(throwable = lastException)
```

`onError` indicates that an attempt failed, not that the item was ultimately skipped. After retries finish, Spring Batch still applies recovery and skip policies. An error may exhaust retries and fail the step instead of being skipped.

## 7. RetryListener is not RetryPolicy

`RetryPolicy` decides whether retrying is permitted after an exception. `RetryListener` observes the retry lifecycle. Both components can be used together, but their responsibilities must not be merged.

| Component | Responsibility | Example |
|---|---|---|
| `RetryPolicy` | Decides whether retrying may continue | Retry up to three times on timeout |
| `BackOffPolicy` | Determines the wait interval between attempts | Exponential backoff |
| `RetryListener` | Observes start, per-attempt errors, and completion | Log exceptions, record metrics |
| Skip policy | Decides whether a failing item may be discarded | Skip data errors up to a limit |
| Transaction manager | Manages commit/rollback | Roll back chunk when exception requires it |

Do not use a listener to count errors and decide retries yourself when `RetryPolicy` already manages attempt limits. Doing so creates two sources of truth and complicates testing.

## 8. RetryListener and onSuccess in Spring Retry 2.x

Spring Retry 2.0 versions added the `onSuccess(context, callback, result)` callback, invoked when the callback returns successfully. This method does not exist in all older versions, so only override it when your project dependency supports it.

```java
@Override
public <T, E extends Throwable> void onSuccess(
        RetryContext context,
        RetryCallback<T, E> callback,
        T result) {
    log.debug("Retry callback returned successfully");
}
```

`onSuccess` has special semantics: a listener may throw a new exception to trigger a retry under the policy based on the returned result. Therefore, if the purpose is purely logging or metrics, do not throw exceptions from this callback. For code that must remain compatible across multiple Spring Retry versions, check the managed dependency's interface before adding this method.

## 9. Listeners do not decide the final outcome of the step

Once a retry operation finishes, the outcome still depends on the retry policy, skip policy, exceptions, and step transaction semantics.

Examples:

- An attempt fails, a subsequent retry succeeds: the operation continues and the listener closes the retry context with a successful result.
- Retries exhausted, exception is skippable and skip limit remains: Spring Batch may skip the item and continue the step.
- Retries exhausted, exception is not skippable: the step may fail.
- An attempt succeeds, yet a commit error occurs afterward: the chunk can still roll back; `RetryListener.close` does not prove the chunk committed.

Hence, never treat `close(throwable == null)` as proof that data was committed to the database. It only indicates that the retry callback returned normally.

## 10. Distinguishing RetryListener from other listeners

Spring Batch offers many listeners for different phases. Picking the right one avoids miscounting or placing logic at the wrong boundary.

| Listener | Observes | Scope |
|---|---|---|
| `RetryListener` | Attempts inside a retry operation | A single retry sequence |
| `ItemReadListener` | Before/after read and read errors | A single item read |
| `ItemProcessListener` | Before/after process and process errors | A single item through the processor |
| `ItemWriteListener` | Before/after write and write errors | A chunk write |
| `SkipListener` | Items actually skipped | A single item discarded after recovery |
| `ChunkListener` | Before/after chunk and chunk errors | A single chunk transaction |
| `StepExecutionListener` | Step start/end | A single StepExecution |

For instance, `RetryListener.onError` may be called multiple times while an item is retried. `SkipListener.onSkipInProcess` only records items actually skipped after recovery. Do not use `onError` counts in place of skip counts.

## 11. RetryListener and SkipListener when retries are exhausted

Suppose a processor calls a partner service. The first and second calls time out, and the third still fails. If the exception is configured as skippable and the skip limit is not yet exceeded, Spring Batch can discard that item.

```text
RetryListener.open()
  attempt 1 -> timeout -> RetryListener.onError()
  attempt 2 -> timeout -> RetryListener.onError()
  attempt 3 -> timeout -> RetryListener.onError()
RetryListener.close(lastException)

Recovery:
  SkipListener.onSkipInProcess(item, lastException)
```

In this example, the retry listener records the failed attempts; the skip listener records the decision to discard the item. If the exception is not skippable, the skip callback never fires and the step may end in failure.

Do not write a reject record inside `RetryListener.onError`, because the item might still succeed on a subsequent retry attempt. Use `SkipListener` or an appropriate recovery mechanism once it is certain the item was actually skipped.

## 12. RetryListener and transaction rollback

A retry operation can run inside a chunk transaction and interact with rollback/recovery. Listeners do not open new transactions, commit, or roll back data.

```text
Chunk transaction
    |
    +--> retry operation
             |
             +--> attempt failed
             +--> onError
             +--> policy permits retry
             +--> next attempt
             +--> close
    |
    v
Spring Batch continues chunk recovery/commit/rollback
```

When retries cross transaction boundaries, certain operations may be re-invoked. Writers or processors with side effects outside the transaction need idempotency keys, outbox patterns, or reconciliation mechanisms. A listener only observes events; it does not make side effects safe under repetition.

## 13. Safe logging and metrics

A retry listener is often a good place to gather telemetry on dependent system stability. Useful details include:

- Configured job/step name or dependency name.
- Exception category and attempt count.
- Duration of the retry operation.
- Final outcome: succeeded or retries exhausted.
- Correlation ID or execution ID if available in context.

Avoid logging full items or JobParameters. Payloads may contain personal data, payment details, or credentials. For metrics, avoid high-cardinality labels like order ID, request ID, or tenant ID; use stable labels such as job, step, dependency, and exception type.

For instance, a listener can increment a counter in `onError` and record duration in `close`. If you want to count items ultimately skipped, use a skip listener or StepExecution skip counts instead of inferring from the retry listener.

## 14. Thread safety and state in listeners

Listener beans are typically Spring-managed singletons. A step can run multiple items, partitions, or job executions concurrently. Therefore, do not store state for a single retry operation in shared mutable fields.

Unsafe example:

```java
public class UnsafeRetryListener implements RetryListener {
    private long startedAt;

    @Override
    public <T, E extends Throwable> boolean open(
            RetryContext context, RetryCallback<T, E> callback) {
        startedAt = System.nanoTime();
        return true;
    }
}
```

Two concurrent retry operations can overwrite each other's `startedAt`. Use attributes on `RetryContext` for per-operation state; use thread-safe counters/meters for metrics. If you must use `ThreadLocal`, clean up state along every exit path, including failures.

## 15. Multiple RetryListeners and callback order

You can register multiple listeners if you want to separate logging, metrics, and tracing. Spring Retry invokes `open` in registration order; `onError` and `close` callbacks are invoked in reverse order.

```java
.faultTolerant()
.retry(TransientPartnerException.class)
.retryLimit(3)
.listener(retryLoggingListener)
.listener(retryMetricsListener)
.build();
```

Keep the listener list short and avoid making one listener depend on another listener's execution order unnecessarily. If one listener writes state that another reads, document the order explicitly and test it. Do not let listeners slow down the retry path with network calls or heavy queries.

## 16. Avoiding side effects in RetryListener

Listeners can be invoked repeatedly and at times before chunk commit. Hence, do not place critical business actions inside callbacks:

- Do not send a success email from `close` just because the retry callback returned normally.
- Do not create a reject record inside every `onError` since a later attempt may succeed.
- Do not mutate business data or invoke writers from a listener.
- Do not call external services synchronously merely to emit metrics or logs.

If you need post-commit notifications, use an outbox or transaction synchronization. If you need to persist discarded items, use `SkipListener` and design idempotent reject writes. If you need to make retry decisions, use `RetryPolicy`.

## 17. Common mistakes

| Mistake | Consequence | Remedy |
|---|---|---|
| Confusing `RetryListener` with `RetryPolicy` | Listener fails to control retry counts properly | Keep decisions in policy; listener only observes |
| Writing rejects in `onError` | An item may be logged as rejected even though a later attempt succeeded | Record rejects only when the item is actually skipped |
| Treating successful `close` as chunk committed | May report success before transaction rollback | Distinguish retry callbacks from commit boundaries |
| Using mutable fields in a singleton listener | Concurrent retries overwrite each other's state | Use `RetryContext` attributes or thread-safe state |
| Returning `false` from `open` to reject an exception | Raises `TerminatedRetryException` at the wrong layer | Use `RetryPolicy` to classify exceptions |
| Calling external APIs synchronously in retry listener | Adds latency and may introduce failures in the retry path | Use lightweight metrics/logs or a queue/outbox |
| Counting `onError` as skipped items | One item can fail multiple times and then succeed | Use `SkipListener` and execution counters |
| Using `onSuccess` without checking version | Incompatible with older dependencies or triggers unintended retries | Verify Spring Retry version and never throw exceptions when only observing |

## 18. Testing RetryListener

A listener can be unit-tested independently by invoking callbacks with a sample `RetryContext`, yet integration tests through a fault-tolerant step are needed to confirm Spring Batch registers and invokes the listener across its proper lifecycle.

Cases to include:

1. Callback succeeds on first attempt: `open` and `close` are called; no `onError`.
2. Failure followed by success: `onError` is called for each failed attempt and `close` receives a successful final outcome.
3. Retries exhausted: `onError` is called for each failed attempt and `close` receives the final exception.
4. `open` returns `false`: confirm the operation is vetoed and the corresponding error propagates.
5. Multiple listeners: confirm callback ordering matches expectations.
6. Retry combined with skip: retry listener observes attempts; skip listener receives only items actually discarded.
7. Concurrent execution: state and metrics do not mix across retry operations.
8. Commit failure after writer: do not interpret `close` as proof the chunk committed.

Tests should assert callback counts, final exceptions, retry counts, skip counts, and transactional data—not merely check that logs contain a warning line.

## 19. Process for implementing RetryListener

When adding a retry listener to a step, follow this sequence:

1. Identify which errors are retryable and configure `RetryPolicy` or `.retry(...)` first.
2. Decide what needs observation: attempts, exceptions, duration, dependency, and final outcome.
3. Implement `open`, `onError`, and `close` with lightweight logic and no business side effects.
4. Register the listener on `FaultTolerantStepBuilder` via `.listener(retryListener)`.
5. Use `RetryContext` for transient per-operation state.
6. Use `SkipListener` if you need to know which items were actually skipped after recovery.
7. Test immediate success, retry success, retry exhaustion, skip, rollback, and concurrency.
8. Verify logs/metrics contain no sensitive payloads or high-cardinality labels.

## Conclusion

`RetryListener` provides callbacks to observe retry operations in Spring Batch: `open` before the first attempt, `onError` after each failed attempt, and `close` after the final attempt. In Spring Batch 5, a listener can be registered on a fault-tolerant chunk step using the `.listener(RetryListener)` overload.

Listeners fit logging, metrics, tracing, and temporary state cleanup. They do not decide whether an exception is retried, do not replace skip policies, and do not prove a chunk committed. Keep listeners lightweight and thread-safe, use `RetryContext` for per-operation state, use `SkipListener` to record discarded items, and keep all business side effects in components with explicit transactions and idempotency.
