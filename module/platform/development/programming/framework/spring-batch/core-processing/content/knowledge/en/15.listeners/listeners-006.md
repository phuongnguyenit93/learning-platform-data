# ItemWriteListener

`ItemWriteListener` is a Spring Batch listener used to observe the data-writing lifecycle in a chunk-oriented step. The listener provides callbacks before the writer is invoked, after the writer finishes normally, and when the writer throws an exception.

The listener is useful for logging, tracking item counts, measuring write duration, or recording operational errors. It allows placing observability logic around the write phase without stuffing logging and metrics into `ItemWriter`.

Remember that `afterWrite` means the writer method returned normally; it does not by itself prove the chunk transaction has committed. If an action must run only after commit, use a mechanism tied to transaction commit or an outbox.

## 1. Where Does ItemWriteListener Sit in a Chunk?

In chunk-oriented processing, Spring Batch reads items, passes each item through the processor, and hands the output group of items to the writer. `ItemWriteListener` wraps the writer call for each chunk.

```text
Chunk transaction starts
        |
        v
   ItemReader
        |
        v
   ItemProcessor
        |
        v
   beforeWrite(chunk)
        |
        v
   ItemWriter.write(chunk)
        |
        +---- writer succeeds ----> afterWrite(chunk)
        |
        +---- writer throws error -> onWriteError(exception, chunk)
        |
        v
   Transaction completion steps
        |
        v
   Commit or rollback
```

The listener operates per chunk, not via separate callbacks per individual item. If a chunk contains 100 items, `beforeWrite` and `afterWrite` are normally invoked once for that group, not 100 times.

## 2. Three Main Callbacks

In Spring Batch 5, `ItemWriteListener<T>` receives a `Chunk`:

```java
public interface ItemWriteListener<S> extends StepListener {
    default void beforeWrite(Chunk<? extends S> items) { }
    default void afterWrite(Chunk<? extends S> items) { }
    default void onWriteError(Exception exception, Chunk<? extends S> items) { }
}
```

The three callbacks have different meanings:

| Callback | Timing | Common Purpose |
|---|---|---|
| `beforeWrite(items)` | Immediately before calling `ItemWriter.write` | Log write start, chunk size, or start timestamp |
| `afterWrite(items)` | After `ItemWriter.write` returns normally | Record writer call completion and item count handled by the writer |
| `onWriteError(exception, items)` | When `ItemWriter.write` throws an exception | Log the error and associated chunk details |

Callbacks receive the chunk passed to the writer. `onWriteError` receives both the exception and the chunk, but does not automatically pinpoint which exact item in the chunk caused the error.

## 3. Implementing ItemWriteListener

Example listener that logs for an order import step:

```java
public class OrderWriteListener implements ItemWriteListener<Order> {

    private static final Logger log =
        LoggerFactory.getLogger(OrderWriteListener.class);

    @Override
    public void beforeWrite(Chunk<? extends Order> items) {
        log.debug("Starting write for {} orders", items.size());
    }

    @Override
    public void afterWrite(Chunk<? extends Order> items) {
        log.info("Writer completed for {} orders", items.size());
    }

    @Override
    public void onWriteError(
            Exception exception,
            Chunk<? extends Order> items) {
        log.error(
            "Writer failed for a chunk containing {} orders",
            items.size(),
            exception
        );
    }
}
```

The example uses `Logger` to log the item count and exception. The listener does not modify items, swallow errors, or re-invoke the writer itself. If extra details are needed for investigation, log only non-sensitive identifiers instead of dumping the entire payload.

## 4. Registering the Listener on a Step

You can declare the listener as a Spring bean and attach it to the step with `.listener(...)`:

```java
@Bean
OrderWriteListener orderWriteListener() {
    return new OrderWriteListener();
}

@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderRow> orderReader,
        ItemProcessor<OrderRow, Order> orderProcessor,
        ItemWriter<Order> orderWriter,
        OrderWriteListener orderWriteListener) {

    return new StepBuilder("importOrders", jobRepository)
        .<OrderRow, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .listener(orderWriteListener)
        .build();
}
```

Because the listener is attached to the step, it receives write events from the writer in that step. If a job has multiple data-writing steps, register a listener on each step with the matching item type or use a shared listener if the contract and observation scope are compatible.

## 5. beforeWrite: Observing Before Writing

`beforeWrite` runs right before the writer call. This is the appropriate place to:

- Log that a chunk is about to be written.
- Record the number of items about to be written.
- Start timing the writer call.
- Add correlation details to logs, such as job execution ID or step name.

Example starting a timer:

```java
public class TimedOrderWriteListener implements ItemWriteListener<Order> {

    private final ThreadLocal<Long> startedAt = new ThreadLocal<>();

    @Override
    public void beforeWrite(Chunk<? extends Order> items) {
        startedAt.set(System.nanoTime());
    }

    @Override
    public void afterWrite(Chunk<? extends Order> items) {
        Long start = startedAt.get();
        if (start != null) {
            long elapsedNanos = System.nanoTime() - start;
            recordWriteDuration(elapsedNanos, items.size());
        }
        startedAt.remove();
    }

    @Override
    public void onWriteError(
            Exception exception,
            Chunk<? extends Order> items) {
        startedAt.remove();
    }
}
```

This illustrates measuring elapsed time across two callbacks; `recordWriteDuration` is an application metric method. If the step runs concurrently, timing state must be isolated per thread or per execution. `ThreadLocal` must be cleaned up on both success and error paths to avoid retaining state on thread pools.

Do not use `beforeWrite` to modify items in order to change output data. Data normalization and transformation belong in the reader/processor; the writer receives items already prepared per the pipeline contract.

## 6. afterWrite: The Writer Call Completed

`afterWrite` is invoked when `ItemWriter.write` returns normally. It is suited for recording a successful writer call or updating metrics on how many items the writer processed.

```java
@Override
public void afterWrite(Chunk<? extends Order> items) {
    successfulWriteCalls.increment();
    writtenItems.add(items.size());
    log.debug("Writer returned normally for {} orders", items.size());
}
```

The metrics in the example can be Micrometer counters or application-managed counters. Name metrics clearly to reflect the number of times the writer returned normally or items sent to the writer.

### afterWrite does not mean commit

`afterWrite` occurs after the writer method returns, yet still during chunk processing. The chunk transaction has not necessarily committed yet. An error occurring during transaction completion or commit can cause the chunk to roll back after `afterWrite` has already run.

Therefore, avoid using `afterWrite` to:

- Send external notifications stating that data has committed.
- Update other systems as though the business transaction is guaranteed complete.
- Permanently mark items as done in a non-transactional store.

If events must be emitted only after transaction commit, use appropriate transaction synchronization or write the event to an outbox in the same transaction as the business data and publish it after commit. This prevents emitting success notifications for rolled-back data.

## 7. onWriteError: Recording Writer Errors

`onWriteError` is invoked when the writer throws an exception. The listener receives the exception and the entire chunk passed to the writer in that call.

```java
@Override
public void onWriteError(
        Exception exception,
        Chunk<? extends Order> items) {

    log.error(
        "Failed to write {} orders; exception type={}",
        items.size(),
        exception.getClass().getSimpleName(),
        exception
    );
}
```

This callback is useful for observing SQL errors, connection failures, or file-write errors. It can also record error metrics and correlation info to help trace `JobExecution`/`StepExecution`.

The listener must not catch the writer exception and treat it as resolved. The exception must continue through Spring Batch according to transaction, retry, and skip policies. If the listener swallows errors or re-invokes the writer itself, the step status may not reflect the real outcome.

### onWriteError does not necessarily identify the failing item

The writer receives the entire chunk in one call. If the writer throws an error while writing one of the items, the listener typically knows only which chunk failed and which exception was thrown; it does not always know the exact failing item.

For example, a chunk has 100 orders and the database raises a unique constraint error. If the exception does not contain the offending key or the writer does not provide it, `onWriteError` cannot deduce the failing item from the chunk alone.

When you need to identify the specific item skipped after recovery, use `SkipListener.onSkipInWrite(item, exception)`. This is a separate callback from `ItemWriteListener.onWriteError` and has per-skipped-item semantics.

## 8. Distinguishing ItemWriteListener and SkipListener

Both listeners are often used together, yet observe two different things:

| Listener | Callback | Information Scope | Purpose |
|---|---|---|---|
| `ItemWriteListener` | `beforeWrite` | Chunk about to be written | Observe write start |
| `ItemWriteListener` | `afterWrite` | Chunk handled normally by writer | Observe writer call completion |
| `ItemWriteListener` | `onWriteError` | Exception and failing chunk | Observe failed writer call |
| `SkipListener` | `onSkipInWrite` | Specific skipped item and exception | Record item discarded after recovery |

For instance, the writer attempts to write a chunk and throws an exception. `onWriteError` can record the failed chunk. If the fault-tolerance policy determines an item is skipped, `onSkipInWrite` records that item. If the chunk is retried and subsequently succeeds, the write listener may be called again across attempts.

Do not use `onWriteError` as the final statistic for skipped items. A failing chunk may succeed on retry, or an error may fail the step without skipping any item.

## 9. Listeners During Retry and Skip

When a step is configured with retry, a writer call can be retried. Hence, `beforeWrite` and its companion callbacks may appear multiple times for the same data. `onWriteError` records each time the writer throws an error; `afterWrite` records calls where the writer returns normally.

Example fault-tolerance configuration:

```java
return new StepBuilder("importOrders", jobRepository)
    .<OrderRow, Order>chunk(100, transactionManager)
    .reader(orderReader)
    .processor(orderProcessor)
    .writer(orderWriter)
    .faultTolerant()
    .retry(TransientDataAccessException.class)
    .retryLimit(3)
    .skip(InvalidOrderException.class)
    .skipLimit(50)
    .listener(orderWriteListener)
    .build();
```

This is an illustrative configuration: transient write errors can be retried per policy, while specific data errors can be skipped if they occur at an eligible stage. Choose exceptions and limits according to business rules.

When designing metrics, distinguish:

- Number of writer calls.
- Number of times the writer threw an exception.
- Number of times the writer returned normally.
- Number of items passed to the writer.
- Number of items actually skipped after recovery.
- Number of chunks finally committed.

These numbers are not equivalent. For instance, a chunk may be called on the writer twice: failing the first time and succeeding the second time. Simply summing items in `afterWrite` can double-count the same items when retries happen.

## 10. Callbacks and Transaction Boundaries

`ItemWriteListener` callbacks run within the chunk's write processing flow. They do not create separate transactions and do not commit or roll back data themselves.

```text
Chunk transaction
    |
    +--> beforeWrite
    |
    +--> ItemWriter.write
    |       |
    |       +--> returns normally: afterWrite
    |       |
    |       +--> throws exception: onWriteError
    |
    +--> complete step/chunk transaction
            |
            +--> COMMIT
            |
            +--> ROLLBACK if error
```

The listener can access metadata through appropriate mechanisms when needed, but should not manage the step's transactions itself. If the listener writes to the same datasource and transaction manager, changes can join the chunk transaction. If it writes to a different datasource or calls external systems, consistency must be handled separately.

## 11. Do Not Place Data-Writing Business Logic in a Listener

A listener is a lifecycle observation hook, not a substitute for a writer or processor. Avoid placing important business operations in callbacks because they can be re-invoked by retries or run before transaction commit.

Appropriate tasks:

- Controlled technical logging.
- Incrementing metrics for item counts and writer call duration.
- Adding correlation IDs or step info to logs.
- Recording exceptions for diagnostics.

Tasks to reconsider or place in other components:

- Transforming items: do this in `ItemProcessor`.
- Writing target data: do this in `ItemWriter`.
- Persisting reject records for skipped items: use `SkipListener` or a dedicated reject mechanism.
- Publishing post-commit events: use an outbox or transaction synchronization.
- Performing critical business state changes: place in a service/writer with explicit transactions.

If a listener throws an exception, the callback can disrupt step execution. Therefore, logging and metrics inside a listener should be appropriately reliable; avoid letting observability system errors fail the batch if operational policy does not require it.

## 12. Thread Safety and Shared Listeners

Spring listener beans are typically singletons and can be shared across multiple runs or threads depending on step configuration. Do not store mutable per-chunk state in ordinary fields if the listener can be invoked concurrently.

Unsafe example:

```java
public class UnsafeListener implements ItemWriteListener<Order> {
    private long currentChunkStart;

    @Override
    public void beforeWrite(Chunk<? extends Order> items) {
        currentChunkStart = System.nanoTime();
    }
}
```

If two threads share the listener, one thread can overwrite the other's start time. Use per-execution/per-thread state, thread-safe metrics, or avoid storing state in the listener. With `ThreadLocal`, clear the data on both success and error paths.

When using partitioning, each step execution may have its own listener instance or share one depending on bean configuration and scope. Verify the actual lifecycle and test concurrency before adding mutable state.

## 13. Useful Logging and Metrics

Listener logs should help answer operational questions:

- Which job and step are writing?
- How many items are in the chunk?
- How long did the writer call take?
- What kind of error occurred and what is the correlation ID?
- Which attempt is this if retries are involved?

Do not log full objects or sensitive data. Use approved business identifiers, execution IDs, and item counts. For metrics, avoid high-cardinality labels like order ID or tenant ID; instead use stable labels such as job name, step name, outcome, and exception category.

## 14. Common Pitfalls

| Mistake | Consequence | How to Handle |
|---|---|---|
| Confusing `afterWrite` with transaction commit | May emit success notifications before chunk rolls back | Use an after-commit hook or outbox for post-commit events |
| Assuming `onWriteError` identifies the failing item | Only chunk and exception are known unless writer supplies specific item info | Use `SkipListener.onSkipInWrite` when skipped items are needed |
| Counting items in `afterWrite` as unique committed items | Retries can count the same items multiple times | Separate writer-call metrics from committed-item metrics |
| Swallowing exceptions in a listener | Hides errors or alters step processing outcome | Let writer exceptions flow through Spring Batch; listeners must not swallow errors |
| Performing external side effects in `afterWrite` | Side effects may persist even if chunk rolls back | Use an outbox or after-commit synchronization |
| Keeping mutable state in a singleton listener | Race conditions under parallel execution | Use thread-safe or per-execution state |
| Logging the entire chunk | Increases log volume and risks exposing sensitive data | Log counts, safe IDs, and correlation metadata |

## 15. Testing ItemWriteListener

You can unit-test the listener independently by invoking callbacks directly with sample chunks, while also integration-testing through a step to verify callbacks are invoked in the right scenarios.

Scenarios to include:

1. Writer returns normally: `beforeWrite` and `afterWrite` are invoked.
2. Writer throws an exception: `beforeWrite` and `onWriteError` are invoked; `afterWrite` is not treated as a success callback for that call.
3. Retry: confirm the listener records each attempt according to desired metrics.
4. Skip on write error: distinguish chunk-level `onWriteError` from item-level `SkipListener.onSkipInWrite`.
5. Commit fails after writer returns: confirm `afterWrite` is not mistaken for commit proof.
6. Concurrent execution: listener does not mix state or metrics across executions.

In integration tests, you can use a stub/mock writer to control when the writer returns or throws exceptions. Check `JobExecution`/`StepExecution` status and transactional data to confirm the listener only observes events along the designed boundaries.

## Conclusion

`ItemWriteListener` provides three chunk-level callbacks: `beforeWrite` runs before the writer, `afterWrite` runs when the writer returns normally, and `onWriteError` runs when the writer throws an exception. The listener is suited for logging, metrics, and error observation; it does not replace `ItemWriter`, `SkipListener`, or transaction management.

In particular, `afterWrite` does not mean data has committed. When retries occur, callbacks can appear multiple times for the same chunk; when you need to record skipped items, use `SkipListener`. Keep listeners stateless or thread-safe, avoid non-idempotent side effects, and use an outbox or after-commit hook for actions permitted only after commit.
