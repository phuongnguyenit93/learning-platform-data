# ChunkListener Before and After a Chunk

In Spring Batch, a chunk-oriented Step reads and processes a group of items and writes that group within a single transaction. `ChunkListener` lets an application observe key milestones of the chunk lifecycle: before processing begins, after a chunk commits successfully, and after a chunk rolls back due to an error.

This listener is useful for logging, metrics, technical auditing, and tracking processing duration. It tells you when a chunk started, whether it committed or rolled back, and how far the Step has progressed. `ChunkListener` does not replace `ItemReader`, `ItemProcessor`, or `ItemWriter`; it observes the chunk lifecycle while those components handle data processing.

## 1. What is a Chunk in Spring Batch?

In chunk-oriented processing, Spring Batch calls the reader repeatedly to fetch items, passes each item through the processor if configured, and then passes the processed group of items to the writer. When the commit interval is reached or the reader signals the end of input, the writer writes the chunk and the transaction is committed.

Example of a Step with chunk size 3 and a reader supplying 7 items:

```text
Source: A B C D E F G

Chunk 1: [A, B, C] -> Processor -> Writer -> Commit
Chunk 2: [D, E, F] -> Processor -> Writer -> Commit
Chunk 3: [G]       -> Processor -> Writer -> Commit
```

The final chunk may contain fewer items than the commit interval. When the reader returns `null`, Spring Batch still finishes processing and writing the remaining items in the final chunk before ending the Step.

Each chunk is a transactional unit according to the Step configuration. If the writer succeeds and the transaction commits, changes participating in the transaction are persisted. If an error causes the chunk to roll back, changes belonging to that transaction are rolled back according to the capabilities of the transaction manager and participating resources.

## 2. What Callbacks Does ChunkListener Provide?

`ChunkListener` defines three main callbacks:

```java
public interface ChunkListener extends StepListener {

    void beforeChunk(ChunkContext context);

    void afterChunk(ChunkContext context);

    void afterChunkError(ChunkContext context);
}
```

Meaning of each callback:

| Callback | Timing | Common Purpose |
|---|---|---|
| `beforeChunk()` | After the chunk transaction starts and before reading/processing/writing the chunk | Record start time, create correlation data, or log context |
| `afterChunk()` | After the chunk has committed successfully | Record chunk completion, update metrics, or log counters |
| `afterChunkError()` | After the chunk rolls back due to an error | Record error, rollback time, and diagnostic details |

These callbacks belong to the chunk lifecycle. They are not called once per item; a single chunk may contain many items but has only one corresponding callback cycle.

## 3. Callback Order Relative to the Transaction

For a successfully processed chunk, the general flow is as follows:

```text
Start transaction
        |
        v
beforeChunk(context)
        |
        v
ItemReader reads items
        |
        v
ItemProcessor processes items (if present)
        |
        v
ItemWriter writes chunk
        |
        v
Commit transaction
        |
        v
afterChunk(context)
```

If an error causes the transaction to roll back:

```text
Start transaction
        |
        v
beforeChunk(context)
        |
        v
Read / process / write
        |
        v
       Error
        |
        v
Rollback transaction
        |
        v
afterChunkError(context)
```

`beforeChunk()` is invoked after the transaction has begun. Therefore, database operations in this callback can participate in the chunk's transaction if they use the same transaction manager and resource. If the chunk rolls back, those changes can also roll back.

`afterChunk()` is invoked after the chunk commits. Consequently, a database operation executed in this callback is no longer inside the just-committed chunk transaction; if a separate transaction is needed, the application must configure one appropriately. Do not assume operations inside `afterChunk()` can roll back together with the data the writer just persisted.

`afterChunkError()` is invoked after the chunk rolls back. This callback is suitable for recording error details or metrics. If error audit records must be persisted to the database, consider using a separate transaction because the chunk transaction has already rolled back.

## 4. Implementing ChunkListener via Interface

You can create a bean implementing `ChunkListener`:

```java
@Component
public class ImportChunkListener implements ChunkListener {

    private static final Logger log =
            LoggerFactory.getLogger(ImportChunkListener.class);

    @Override
    public void beforeChunk(ChunkContext context) {
        StepExecution stepExecution = context.getStepContext()
                .getStepExecution();

        log.info("Starting chunk: jobExecutionId={}, step={}, readCount={}",
                stepExecution.getJobExecutionId(),
                stepExecution.getStepName(),
                stepExecution.getReadCount());
    }

    @Override
    public void afterChunk(ChunkContext context) {
        StepExecution stepExecution = context.getStepContext()
                .getStepExecution();

        log.info("Chunk committed: step={}, readCount={}, writeCount={}",
                stepExecution.getStepName(),
                stepExecution.getReadCount(),
                stepExecution.getWriteCount());
    }

    @Override
    public void afterChunkError(ChunkContext context) {
        StepExecution stepExecution = context.getStepContext()
                .getStepExecution();

        log.warn("Chunk rolled back: jobExecutionId={}, step={}",
                stepExecution.getJobExecutionId(),
                stepExecution.getStepName());
    }
}
```

The listener retrieves `StepExecution` from `ChunkContext` to log the Step name, `JobExecution` ID, and counters. In production applications, use a logger instead of `System.out.println`, and avoid logging full payloads or sensitive data.

Counters such as `readCount` and `writeCount` are useful for observing progress, but they do not always correspond one-to-one with the exact number of business side effects that occurred. Retries, skips, filtering, and rollbacks can make counter interpretation more nuanced. When exact business metrics are needed, record them according to dedicated domain rules.

## 5. Registering ChunkListener on a Step

In Spring Batch 5, you can register the listener using `StepBuilder.listener()`:

```java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> reader,
        ItemProcessor<CustomerInput, Customer> processor,
        ItemWriter<Customer> writer,
        ImportChunkListener chunkListener) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<CustomerInput, Customer>chunk(500, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .listener(chunkListener)
            .build();
}
```

When the Step runs, Spring Batch calls the corresponding callbacks around each chunk. One listener can be registered across multiple Steps if observation logic is shared, but distinguish Step names in logs and do not store mutable per-chunk state in shared fields.

## 6. Accessing Data via ChunkContext

Each callback receives a `ChunkContext`. This context provides `StepContext` and attributes associated with the current chunk processing attempt.

Example of retrieving `StepExecution` information:

```java
@Override
public void beforeChunk(ChunkContext context) {
    StepExecution stepExecution = context.getStepContext()
            .getStepExecution();

    Long jobExecutionId = stepExecution.getJobExecutionId();
    Long stepExecutionId = stepExecution.getId();
    String stepName = stepExecution.getStepName();
}
```

You can read `JobParameters` and context maps via `StepContext`:

```java
StepContext stepContext = context.getStepContext();
Map<String, Object> jobParameters = stepContext.getJobParameters();
Map<String, Object> stepValues = stepContext.getStepExecutionContext();
Map<String, Object> jobValues = stepContext.getJobExecutionContext();
```

`ChunkContext` is the context for the current chunk processing execution. Do not confuse it with `ExecutionContext`, which Spring Batch persists in `JobRepository`. If you need to store durable checkpoints for restart, update `StepExecution.getExecutionContext()` or let an `ItemStream`-implementing reader manage its state. Temporary attributes in `ChunkContext` are not a durable storage replacement for `ExecutionContext`.

## 7. Using ChunkListener to Measure Processing Time

An application can use a listener to record when a chunk starts and finishes. If you store the timestamp in `ChunkContext`, the subsequent callback can retrieve it from the same context:

```java
@Component
public class ChunkTimingListener implements ChunkListener {

    private static final String START_NANOS = "chunk.startNanos";

    private static final Logger log =
            LoggerFactory.getLogger(ChunkTimingListener.class);

    @Override
    public void beforeChunk(ChunkContext context) {
        context.setAttribute(START_NANOS, System.nanoTime());
    }

    @Override
    public void afterChunk(ChunkContext context) {
        logDuration(context, "committed");
    }

    @Override
    public void afterChunkError(ChunkContext context) {
        logDuration(context, "rolled-back");
    }

    private void logDuration(ChunkContext context, String outcome) {
        Object start = context.getAttribute(START_NANOS);
        if (start instanceof Long startNanos) {
            long elapsedMillis =
                    (System.nanoTime() - startNanos) / 1_000_000;
            log.info("Chunk {} after {} ms", outcome, elapsedMillis);
        }
    }
}
```

The example uses `System.nanoTime()` to measure elapsed time within the same process; do not use it as a historical timestamp or checkpoint. `ChunkContext` attributes exist only for the current chunk context.

With retries, the same chunk logic may go through multiple attempts, and callbacks may be invoked for each attempt. Therefore, measurements should be interpreted as the duration of that specific attempt rather than always representing the total business processing time for a group of items.

## 8. ChunkListener with Retry, Skip, and Rollback

In a fault-tolerant Step, an error can cause a chunk to roll back and then be retried. In that case, the listener can observe multiple starts and errors before an attempt succeeds.

Example:

```text
Attempt 1:
  beforeChunk
  read / process / write
  deadlock
  rollback
  afterChunkError

Attempt 2:
  beforeChunk
  read / process / write
  commit
  afterChunk
```

The actual flow can be more complex depending on error type, retry policy, buffering, and fault-tolerance configuration. Do not assume a `beforeChunk()` call is always paired with exactly one `afterChunk()`; a chunk can undergo rollbacks and multiple attempts.

`afterChunkError()` is useful for recording a rolled-back attempt. It does not mean the entire Step has permanently failed: Spring Batch can retry and the chunk can subsequently commit successfully. To determine the final outcome of a Step, use `StepExecutionListener` or `JobExecutionListener`.

Skips can also occur inside a chunk while the chunk still commits in the end. In that case, `afterChunk()` is called for the committed chunk; skipped item counts should be inspected via the counters or an appropriate item-level listener.

## 9. Distinguishing ChunkListener from Other Listeners

Spring Batch has multiple listeners because each observes a different scope:

| Listener | Scope | Typical Callbacks |
|---|---|---|
| `ChunkListener` | One chunk | `beforeChunk`, `afterChunk`, `afterChunkError` |
| `ItemReadListener` | One item read | `beforeRead`, `afterRead`, `onReadError` |
| `ItemProcessListener` | One item processed | `beforeProcess`, `afterProcess`, `onProcessError` |
| `ItemWriteListener` | One group of items written | `beforeWrite`, `afterWrite`, `onWriteError` |
| `StepExecutionListener` | Entire single Step execution | `beforeStep`, `afterStep` |
| `JobExecutionListener` | Entire single Job execution | `beforeJob`, `afterJob` |

Choose the listener based on the question you need to answer:

- Want to measure the duration of a chunk or record commits/rollbacks: use `ChunkListener`.
- Want to know which item failed to read: use `ItemReadListener`.
- Want to observe an item rejected or filtered by the processor: use `ItemProcessListener`.
- Want to know which group of items the writer wrote or what error occurred: use `ItemWriteListener`.
- Want to record the start/end state of a Step: use `StepExecutionListener`.
- Want to record the start/end state of a Job: use `JobExecutionListener`.

Do not use `ChunkListener` to modify item contents. Transforming or filtering items belongs in `ItemProcessor`; writing data belongs in `ItemWriter`.

## 10. Annotations Can Be Used Instead of the Interface

In addition to implementing `ChunkListener`, Spring Batch supports listener annotations for the corresponding callbacks, such as `@BeforeChunk`, `@AfterChunk`, and `@AfterChunkError`.

Example:

```java
public class AnnotatedChunkAudit {

    @BeforeChunk
    public void before(ChunkContext context) {
        log.info("Chunk is starting");
    }

    @AfterChunk
    public void after(ChunkContext context) {
        log.info("Chunk has committed");
    }

    @AfterChunkError
    public void afterError(ChunkContext context) {
        log.warn("Chunk was rolled back");
    }
}
```

Register the annotated object with the Step via `.listener(annotatedChunkAudit)`. Annotations are handy when you want to group multiple callbacks in a class without `implements ChunkListener`. The interface is often clearer if you need to declare all three callbacks or reuse the listener in standard Java style.

## 11. Notes When Callbacks Perform Business Operations

`ChunkListener` should generally focus on observability. If a callback writes audit records, sends notifications, or calls APIs, understand the transaction boundaries clearly.

### Do not send critical notifications based solely on afterChunk

`afterChunk()` runs after the chunk has committed. If the application stops after commit but before the callback finishes, the chunk has been persisted while the notification has not been sent. If the callback sends the notification and then fails before recording delivery status, a retry or restart may send a duplicate.

For notifications or events that must be emitted reliably alongside committed data, consider a transactional outbox: write the outbox record within the same chunk transaction, and have a separate publisher dispatch the event and mark it sent idempotently.

### Do not use afterChunkError to replace error handling

`afterChunkError()` is invoked to observe a rollback. It must not swallow the original exception or mark the Step as successful. Retry, skip, and failure decisions belong to the Step's fault-tolerance mechanism; final outcomes must be reflected in metadata.

### Do not assume callbacks can roll back an already committed chunk

When `afterChunk()` is called, the chunk transaction has already committed. If the callback throws an exception, the committed chunk data is not automatically rolled back. The Step may fail while the chunk remains persisted in the database. On restart, the committed chunk may not be reprocessed, so post-commit tasks need their own recovery strategy.

## 12. Thread Safety When a Step Runs Concurrently

If a Step is configured to run with multiple threads or partitions execute concurrently, listener callbacks can be invoked concurrently on the same listener bean depending on registration and execution model.

Do not store the state of the current chunk in a shared mutable field:

```java
// Not safe if multiple chunks run concurrently
private long currentChunkStart;
```

One thread can overwrite another thread's value. Store timestamps or temporary data in `ChunkContext`, or use thread-safe metrics mechanisms. If shared counters are needed, use appropriate concurrent data types and remember that callback order across workers does not reflect a global item order.

Injected listeners and services must also be thread-safe under concurrent calls. Avoid holding connections, cursors, or per-chunk objects in fields of a singleton bean. Use the callback context to access the corresponding execution data.

## 13. Monitoring Chunks and Useful Metrics

`ChunkListener` can enrich Job observability. Useful metrics typically include:

- Number of chunks started, committed, and rolled back.
- Processing duration per chunk and p50/p95/p99 distributions.
- Items read, written, filtered, and skipped.
- Retry count and chunks exhausting retries.
- Rollback rate by Step or Job.
- Throughput in items/second.
- `JobExecution` ID, `StepExecution` ID, and relevant business keys.

When logging, attach a correlation ID to link application logs with database or external service logs. Do not log passwords, access tokens, or full personal data of items.

If the chunk count is very high, avoid logging an `INFO` line on every callback, which rapidly inflates log volume. You can use `DEBUG` for per-chunk events, aggregated metrics for dashboards, and `WARN` for rollbacks or errors needing investigation.

## 14. Common Mistakes

**Confusing `afterChunk` as a pre-commit callback:** `afterChunk()` is called after the chunk has committed successfully. If you need to observe before processing, use `beforeChunk()`.

**Assuming `afterChunkError` means the Job is `FAILED`:** the callback only indicates that a chunk rolled back. The chunk may be retried and the Step can still complete successfully.

**Using the listener to process individual items:** `ChunkListener` is not called once per item. Use `ItemReadListener`, `ItemProcessListener`, or `ItemWriteListener` as needed.

**Writing data in `afterChunk` and expecting rollback alongside the writer:** the chunk transaction commits before the callback. Use a separate transaction or an outbox if matching guarantees are needed.

**Holding timestamps or items in shared fields:** this can cause race conditions under concurrent execution. Store temporary data in `ChunkContext` or use thread-safe mechanisms.

**Using `ChunkContext` as a durable checkpoint:** temporary `ChunkContext` attributes do not replace `ExecutionContext`. Use `StepExecutionContext` or `ItemStream` for restart state.

**Counting callbacks as unique business chunks:** retries can produce multiple attempts and multiple callbacks for the same unit of work. Distinguish attempts, rollbacks, and committed chunks.

## Conclusion

`ChunkListener` provides three callbacks to observe the chunk lifecycle: `beforeChunk()` runs after the transaction starts, `afterChunk()` runs after the chunk commits, and `afterChunkError()` runs after the chunk rolls back. The listener is suited for logging, timing, and collecting chunk-level metrics. Use `ChunkContext` for temporary callback data, `ExecutionContext` for durable checkpoints, and item- or Step-level listeners when a different observation scope is required. When retries or concurrent execution are involved, callbacks can occur multiple times or concurrently; therefore, listeners must be thread-safe and should not contain business side effects lacking recovery mechanisms.
