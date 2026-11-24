# Listener Order

In Spring Batch, listeners allow an application to observe or add behavior at specific points in the lifecycle of a job, step, chunk, and individual item. A job may register multiple listeners of the same type, or a single listener may implement multiple interfaces. In those cases, callback order determines which listener runs first, which runs next, and what data downstream listeners see.

To understand listener order, distinguish two ordering layers:

- **Processing lifecycle order:** the job wraps its steps; a step wraps its chunks or tasklet executions; a chunk coordinates item read, process, and write callbacks.
- **Order among multiple listeners of the same type:** when multiple listeners handle the same callback, the framework invokes them according to their order in the composite listener. For before/after callback pairs, the order is typically stack-like: opening callbacks run in registration order, and closing callbacks run in reverse order.

Do not view all listeners as a single flat global callback list. Each listener type is bound to a different boundary, and a callback's position relative to the transaction is just as important as its invocation order.

## 1. Listener Groups in Spring Batch

Spring Batch provides listeners at several levels:

| Listener | Scope | Typical Callbacks | Purpose |
|---|---|---|---|
| `JobExecutionListener` | Entire job execution | `beforeJob`, `afterJob` | Prepare or summarize a job run |
| `StepExecutionListener` | Single step execution | `beforeStep`, `afterStep` | Record step status and outcome |
| `ChunkListener` | Single chunk/tasklet execution | `beforeChunk`, `afterChunk`, `afterChunkError` | Observe chunk and transaction boundaries |
| `ItemReadListener` | Single item read | `beforeRead`, `afterRead`, `onReadError` | Monitor the reader |
| `ItemProcessListener` | Single item processed | `beforeProcess`, `afterProcess`, `onProcessError` | Monitor the processor |
| `ItemWriteListener` | Single chunk write | `beforeWrite`, `afterWrite`, `onWriteError` | Monitor the writer |
| `SkipListener` | Single skipped item | `onSkipInRead`, `onSkipInProcess`, `onSkipInWrite` | Record skipped items by phase |
| `RetryListener` | Single retry operation | `open`, `onError`, `close` | Observe the retry lifecycle |

Some interface names and signatures may differ across Spring Batch versions. For example, writers in Spring Batch 5 receive `Chunk`, whereas older versions used `List`. When implementing, follow the API of your project's version.

## 2. Callback Order Across the Job Lifecycle

At the top level, `JobExecutionListener` wraps the entire job execution. `beforeJob` runs when the job is about to execute; steps are then orchestrated; `afterJob` runs when the job execution ends.

For a job with two steps, the general order can be visualized as:

```text
JobExecutionListener.beforeJob
  StepExecutionListener.beforeStep (step 1)
    Chunk/item callbacks of step 1
  StepExecutionListener.afterStep (step 1)

  StepExecutionListener.beforeStep (step 2)
    Chunk/item callbacks of step 2
  StepExecutionListener.afterStep (step 2)
JobExecutionListener.afterJob
```

If the flow has conditions, branches, or parallel steps, step order depends on the flow and orchestration mechanism. However, job-level listeners still wrap the lifecycle of the corresponding job execution.

`beforeJob` is suited for preparing job-scoped resources or logging startup. `afterJob` is suited for summarizing the final status, sending operational notifications, or releasing job-level resources. Do not use listeners for large business tasks that ought to be modeled as dedicated steps.

## 3. Callback Order Within a Step

`StepExecutionListener` wraps a single step execution:

1. `beforeStep(stepExecution)` is invoked before the step's main processing.
2. The step runs tasklet or chunk-oriented processing.
3. `afterStep(stepExecution)` is invoked when the step ends and can return an additional or custom `ExitStatus`.

Example:

```java
public class StepAuditListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        log.info("Starting step {}", stepExecution.getStepName());
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        log.info("Step {} ended with {}",
                stepExecution.getStepName(), stepExecution.getStatus());
        return stepExecution.getExitStatus();
    }
}
```

`afterStep` can return an `ExitStatus` to combine with the current exit status. Thus, this listener not only observes but can also influence flow routing if it alters the exit code. Keep that behavior intentional and test step transitions.

## 4. Callback Order Within a Chunk

In a chunk-oriented step, `ChunkListener` wraps a chunk. General order:

```text
Chunk transaction starts
ChunkListener.beforeChunk
  ItemReadListener callbacks
  ItemProcessListener callbacks
  ItemWriteListener callbacks
Chunk transaction commits successfully
ChunkListener.afterChunk
```

If the chunk fails and the transaction rolls back, the framework can invoke `afterChunkError` per the lifecycle. Some timing details depend on step type and framework version; what matters is distinguishing callbacks before/after the writer call from callbacks after the chunk transaction finishes.

`beforeChunk` normally runs after the chunk transaction has started and before the reader is called. `afterChunk` runs after the chunk finishes successfully and the transaction has committed. `afterChunkError` is used when the chunk encounters an error and the transaction rolls back.

Example:

```java
public class ChunkAuditListener implements ChunkListener {

    @Override
    public void beforeChunk(ChunkContext context) {
        log.debug("Chunk started");
    }

    @Override
    public void afterChunk(ChunkContext context) {
        log.debug("Chunk committed");
    }

    @Override
    public void afterChunkError(ChunkContext context) {
        log.warn("Chunk failed and was rolled back");
    }
}
```

Do not place non-repeatable side effects inside callbacks that can be invoked on retry. If post-commit notifications are needed, use a mechanism ensuring idempotency or emit events via an outbox; relying solely on callback logs does not provide an exactly-once guarantee.

## 5. Callback Order Around Individual Items

Within a chunk, each item passes through the reader and processor; results are then collected for the writer. Item-level listeners have their own order.

### Reader

```text
ItemReadListener.beforeRead
ItemReader.read
  ├─ succeeds with item -> ItemReadListener.afterRead(item)
  ├─ end of data (null) -> no afterRead for item
  └─ exception -> ItemReadListener.onReadError(exception)
```

`afterRead` runs only when the reader returns an item. `null` signals end of data, not an item. If the reader throws an exception, the error callback runs per the step's listener mechanism.

### Processor

```text
ItemProcessListener.beforeProcess(item)
ItemProcessor.process(item)
  ├─ returns output -> ItemProcessListener.afterProcess(item, output)
  ├─ returns null -> item is filtered; afterProcess is called with null output
  └─ exception -> ItemProcessListener.onProcessError(item, exception)
```

A processor returning `null` is normal filtering, not a skip. The `afterProcess` callback can receive a `null` output; listeners must handle that case.

### Writer

```text
ItemWriteListener.beforeWrite(chunk)
ItemWriter.write(chunk)
  ├─ succeeds -> ItemWriteListener.afterWrite(chunk)
  └─ exception -> ItemWriteListener.onWriteError(exception, chunk)
```

The writer receives a group of items. A single writer call can persist multiple records, and during retry or skip scanning, the writer can be called again. Hence, do not treat every `beforeWrite` as a committed write.

## 6. Summary Order Table for a Successful Chunk

For a simple chunk of two items, with no filtering, retry, or skip, the order can be described as follows:

| Order | Callback/Activity | Scope |
|---:|---|---|
| 1 | `ChunkListener.beforeChunk` | Chunk start |
| 2 | `ItemReadListener.beforeRead` | Reading item 1 |
| 3 | `ItemReader.read` returns item 1 | Reader |
| 4 | `ItemReadListener.afterRead(item1)` | Reader |
| 5 | `ItemProcessListener.beforeProcess(item1)` | Processor |
| 6 | `ItemProcessor.process(item1)` | Processor |
| 7 | `ItemProcessListener.afterProcess(item1, output1)` | Processor |
| 8–13 | Similar read/process callbacks for item 2 | Reader/processor |
| 14 | `ItemWriteListener.beforeWrite(chunk)` | Writer |
| 15 | `ItemWriter.write(chunk)` | Writer |
| 16 | `ItemWriteListener.afterWrite(chunk)` | Writer |
| 17 | Commit chunk transaction | Transaction |
| 18 | `ChunkListener.afterChunk` | Chunk end |

This illustrates the flow of a simple successful chunk. In practice, the reader may be called once more to return `null` at end of data; the processor may filter items; retry/skip may repeat some callbacks; and the framework may invoke additional stream/checkpoint callbacks.

## 7. Order When Multiple Listeners of the Same Type Exist

A step may register multiple listeners implementing the same interface—for example, two `ItemWriteListener` beans for metrics and auditing. Spring Batch combines them through a composite listener.

For paired before/after callbacks, the typical composite listener rule is:

- Opening callbacks such as `beforeWrite` or `beforeStep` run in the order listeners are sorted/registered.
- Closing callbacks such as `afterWrite` or `afterStep` run in reverse order, like unwinding an opened stack.
- Error callbacks are generally dispatched according to the corresponding composite listener's rules; do not guess the order if the application depends on it without verifying against your version.

Example with two listeners A and B registered in order A then B:

```text
beforeWrite: A -> B
ItemWriter.write(...)
afterWrite:  B -> A
```

Stack-like invocation lets listener B finish before listener A, much like an outer wrapper opening first and closing last.

If callback logic depends on order, declare the order explicitly using the mechanism supported by your Spring Batch version and configuration style, then write a test recording the actual sequence. Do not rely on bean scan order or arbitrary application context initialization order.

## 8. A Listener Implementing Multiple Interfaces

A single class can implement multiple listener interfaces:

```java
public class BatchAuditListener implements
        JobExecutionListener,
        StepExecutionListener,
        ChunkListener {

    // beforeJob / afterJob
    // beforeStep / afterStep
    // beforeChunk / afterChunk / afterChunkError
}
```

This groups related audit logic in one class, but does not mean all callbacks run back-to-back. Each method is still called at its respective lifecycle boundary.

If the same object is registered at multiple levels, be aware it can receive callbacks across multiple scopes. For instance, `beforeStep` will run for every step where it is registered, while `beforeJob` runs once per job execution. Avoid accidentally registering the same listener redundantly at job level, step level, and via annotations; otherwise, the same callback may run multiple times.

## 9. Listener Registration and Declaration Order

With Java configuration, listeners are usually attached to a job or step with `.listener(...)`:

```java
@Bean
public Step importStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemWriter<Order> writer,
        StepAuditListener stepAuditListener,
        ChunkAuditListener chunkAuditListener,
        OrderReadListener orderReadListener,
        OrderWriteListener orderWriteListener) {

    return new StepBuilder("importStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .writer(writer)
            .listener(stepAuditListener)
            .listener(chunkAuditListener)
            .listener(orderReadListener)
            .listener(orderWriteListener)
            .build();
}
```

This snippet shows listeners attached to the step. Not every listener interface can be registered everywhere; builders generally accept compatible listeners and auto-detect the interfaces an object implements. For other APIs or versions, use the proper overload and registration site.

For ordering multiple listeners of the same type, use a supported ordering mechanism such as registration order or `Ordered`/`@Order` if the composite listener in that version honors ordering. Avoid relying on bean injection order if it is not explicitly specified.

## 10. Annotation Listeners and Execution Order

Spring Batch supports listener annotations on methods, such as:

- `@BeforeJob`, `@AfterJob`.
- `@BeforeStep`, `@AfterStep`.
- `@BeforeChunk`, `@AfterChunk`, `@AfterChunkError`.
- `@BeforeRead`, `@AfterRead`, `@OnReadError`.
- `@BeforeProcess`, `@AfterProcess`, `@OnProcessError`.
- `@BeforeWrite`, `@AfterWrite`, `@OnWriteError`.
- `@OnSkipInRead`, `@OnSkipInProcess`, `@OnSkipInWrite`.

Example:

```java
public class OrderListener {

    @BeforeWrite
    public void beforeWrite(Chunk<? extends Order> items) {
        log.debug("About to write {} orders", items.size());
    }

    @AfterWrite
    public void afterWrite(Chunk<? extends Order> items) {
        log.debug("Writer returned successfully for {} orders", items.size());
    }

    @OnWriteError
    public void onWriteError(
            Exception exception,
            Chunk<? extends Order> items) {
        log.warn("Write failed for {} orders", items.size(), exception);
    }
}
```

Annotations change how methods are declared, not the lifecycle position of the callbacks. If the same class is registered multiple times or both registered as an interface listener and scanned/detected via annotations, there is a risk of duplicate callback execution. Pick one consistent registration approach per listener.

## 11. SkipListener Has a Special Position

`SkipListener` differs from regular read/process/write observation listeners. It is called when the framework decides to actually skip an item according to the skip policy.

Key callbacks:

```java
public interface SkipListener<I, O> {
    void onSkipInRead(Throwable t);
    void onSkipInProcess(I item, Throwable t);
    void onSkipInWrite(O item, Throwable t);
}
```

`onSkipInRead` receives no item because the reader threw an error before creating an item. `onSkipInProcess` receives the skipped input item. `onSkipInWrite` receives the output item that could not be written.

An important detail is that Spring Batch designs `SkipListener` so skip callbacks are invoked once per skipped item and close to chunk commit time, enabling skip recording using transactional resources. This differs from `onWriteError`, which may be invoked multiple times during retries or while scanning for the failing item.

Example:

```java
public class OrderSkipListener implements SkipListener<Order, OrderRecord> {

    @Override
    public void onSkipInRead(Throwable t) {
        log.warn("An input record could not be read", t);
    }

    @Override
    public void onSkipInProcess(Order item, Throwable t) {
        log.warn("Order {} was skipped during processing", item.getId(), t);
    }

    @Override
    public void onSkipInWrite(OrderRecord item, Throwable t) {
        log.warn("Order {} was skipped during writing", item.getId(), t);
    }
}
```

If the listener writes error records to a database, use an appropriate transactional resource so the audit commits with the chunk as designed. If audits must persist even when the transaction rolls back, use a separate mechanism and account for possible duplicate writes on retry.

## 12. RetryListener and Repeated Callbacks

When a step has a retry policy, `RetryListener` can observe the retry lifecycle. Callbacks normally include `open`, `onError`, and `close`, tied to a single retry operation.

Key points to remember:

- `onError` can be called multiple times if the operation fails repeatedly.
- A successful retry does not mean the item was skipped.
- Item listeners can receive callbacks multiple times when a chunk or operation is retried.
- Do not place non-idempotent side effects inside retry callbacks.

For example, if `onError` sends an email on every failure, an item retried three times could generate three emails. This callback is suited for metrics or logs tagged with an attempt identifier; operational alerts should use aggregation or idempotency.

## 13. Callback Timing and Transaction Boundaries

Listener order is not only about before versus after. You must know whether a callback runs before commit, after commit, or during rollback.

| Callback | Relative Position | Design Implication |
|---|---|---|
| `beforeChunk` | After chunk transaction starts, before processing items | Can observe chunk start; avoid slow work extending the transaction |
| `beforeRead` / `afterRead` | Around a single read | Suitable for observing reader; not a checkpoint |
| `beforeProcess` / `afterProcess` | Around a single item processing call | Suitable for metrics/tracing; callbacks can repeat on retry |
| `beforeWrite` / `afterWrite` | Around a writer call | `afterWrite` only shows writer returned normally; does not prove transaction committed |
| `onWriteError` | When writer throws an exception | May be called again during retry/skip scanning |
| `SkipListener` | When an item is decided to be skipped, near commit time | Suited for recording skipped items; understand audit resource transactions |
| `afterChunk` | After chunk completes and commits successfully | Suited for recording committed chunks |
| `afterChunkError` | When chunk fails and rolls back | Suited for error metrics; do not assume non-transactional resources rolled back |
| `afterStep` | When step ends | Can adjust `ExitStatus`; not a post-chunk callback |
| `afterJob` | When job execution ends | Suited for summarizing final status |

For example, `ItemWriteListener.afterWrite` is called after the writer method returns, yet the chunk transaction can still fail later, such as when updating metadata or committing the database. If an action must run only after a successful commit, `ChunkListener.afterChunk` sits closer to that boundary. For side effects needing durable guarantees, an outbox remains more reliable than sending directly inside a listener.

## 14. Callback Order When Errors Occur

When an item or chunk encounters an error, the callback sequence differs from the success path.

Example where the processor throws an exception and it is skipped:

```text
ItemProcessListener.beforeProcess(item)
ItemProcessor.process(item) -> exception
ItemProcessListener.onProcessError(item, exception)
Framework applies retry/skip policy
SkipListener.onSkipInProcess(item, exception)  (if item is actually skipped)
Remaining items continue through the chunk flow
Chunk transaction commits if the resulting chunk is valid
ChunkListener.afterChunk
```

If a retry succeeds, `onProcessError` may have been called, while `SkipListener.onSkipInProcess` is not called for that item because it was not skipped. If the error cannot be handled, the chunk may roll back and the step fail; in that case, `afterChunk` does not run for a committed chunk.

Example where the writer throws an error:

```text
ItemWriteListener.beforeWrite(chunk)
ItemWriter.write(chunk) -> exception
ItemWriteListener.onWriteError(exception, chunk)
Transaction rollback
Framework retries or scans to locate the failing item if skip is configured
  - writer may be called again
  - onWriteError may be called again
If an item is skipped:
  SkipListener.onSkipInWrite(item, exception)
If the chunk completes after error handling:
  transaction commit
  ChunkListener.afterChunk
If unrecoverable:
  step ends as FAILED
```

This diagram illustrates general behavior; exact callback counts and ordering depend on retry/skip policies, writer type, and Spring Batch version. When relying on a specific sequence, verify it with tests on your project's version.

## 15. Ordering Multiple Listeners: Audit and Metrics Example

Suppose there are two listeners of the same type:

- `MetricsWriteListener` measures write duration.
- `AuditWriteListener` logs business info about the chunk.

If registered in the order metrics then audit, opening and closing callbacks can run as:

```text
MetricsWriteListener.beforeWrite
AuditWriteListener.beforeWrite
ItemWriter.write
AuditWriteListener.afterWrite
MetricsWriteListener.afterWrite
```

Reverse closing order is useful when the first listener opens a resource or starts a timer and the second listener adds inner handling; on exit, the second finishes first and then the first stops the timer.

If metrics need to measure writer time alone, start the timer in `beforeWrite` and stop it in `afterWrite`. To measure transaction commit duration too, `afterWrite` is not enough; measure in `afterChunk` or use appropriate transaction instrumentation.

Do not let `AuditWriteListener.afterWrite` emit external success notifications before the transaction commits. If the commit subsequently fails, the notification will not match the data. Write audits inside the transaction or emit post-commit events via an outbox.

## 16. Exception Handling in Listeners

Listeners are part of the execution flow. If a callback throws an exception, the impact depends on listener type and callback timing:

- Exceptions in pre-operation callbacks like `beforeRead` or `beforeWrite` can prevent the main operation from proceeding and fail the step.
- Exceptions in post-operation callbacks can fail the chunk/step depending on the callback and lifecycle.
- Exceptions in error or skip listeners can disrupt error handling itself.
- Exceptions in `afterStep` or `afterJob` follow specific framework handling rules; do not assume they are always treated like processor/writer exceptions.

Therefore, listeners should perform short, error-controlled tasks and avoid slow external service calls. If a listener is a mandatory audit component, explicitly decide whether an audit error is allowed to fail the job.

Do not blindly catch and ignore every exception. If auditing is mandatory, swallowing errors can break auditability. Conversely, if metrics are purely observational, you may handle metric-recording failures to avoid disrupting the job, provided that policy is explicitly defined.

## 17. Testing Listener Order

When listener order matters, test the actual order rather than merely checking that each listener was called.

A simple technique is using a shared event list in tests:

```java
class RecordingListener implements ItemWriteListener<Order> {

    private final String name;
    private final List<String> events;

    RecordingListener(String name, List<String> events) {
        this.name = name;
        this.events = events;
    }

    @Override
    public void beforeWrite(Chunk<? extends Order> items) {
        events.add(name + ".beforeWrite");
    }

    @Override
    public void afterWrite(Chunk<? extends Order> items) {
        events.add(name + ".afterWrite");
    }

    @Override
    public void onWriteError(Exception ex, Chunk<? extends Order> items) {
        events.add(name + ".onWriteError");
    }
}
```

In the test, create two listeners, register them on the step in a defined order, run a chunk, and compare the actual event list against the expected sequence.

Example expectation when the writer succeeds:

```java
assertEquals(List.of(
        "metrics.beforeWrite",
        "audit.beforeWrite",
        "audit.afterWrite",
        "metrics.afterWrite"
), events);
```

This illustrates the opening/closing rule of a composite listener. Verify the order under your application's actual version and registration mechanism. If using `@Order` or `Ordered`, write tests confirming the composite listener honors that ordering.

### Testing error scenarios

Add tests when the writer throws an exception to verify:

- `beforeWrite` is called before the writer runs.
- `onWriteError` receives the expected exception.
- `afterWrite` is not treated as a success callback for the failed write.
- Retries can cause corresponding callbacks to appear multiple times.
- `SkipListener` is invoked only if an item is actually skipped.
- `afterChunk` reflects only successfully completed chunks; rolled-back chunks follow the appropriate error callback.

If tests must verify transaction commit/rollback, run integration tests with a real transaction manager and resource rather than only mocking the writer.

## 18. Avoid Relying on Bean Initialization Order

In a Spring application context, bean creation order is not a valid contract for controlling listener order. Beans can be initialized earlier or later depending on the dependency graph, lazy initialization, and context configuration.

If listener order affects outcomes:

- Register listeners in an explicit order in job/step configuration.
- Use `Ordered` or `@Order` if supported by that version's composite listener.
- Do not rely on component-scan order.
- Do not register the same listener through multiple mechanisms.
- Write tests verifying the actual callback sequence.

If two listeners do not need to depend on each other, it is best to keep them independent. A metrics listener should not require an audit listener to run first; an audit listener should not rely on uncommitted side effects of another listener.

## 19. Listener Order in Concurrent Steps

When a step uses multi-threading, partitioning, or remote chunking, callbacks still follow the lifecycle of each execution/chunk, but there is no stable global order across workers.

For example, partition A may call `beforeChunk` before partition B, yet B may commit before A. Logs from different threads can interleave. Do not infer global business order solely from listener log timestamps.

In concurrent environments:

- Attach execution ID, step name, partition ID, or correlation ID to logs.
- Use thread-safe metrics and avoid unsynchronized mutable counters.
- Do not use listeners as a locking or data-synchronization mechanism between workers.
- Do not assume `afterChunk` of one partition runs before or after another partition.
- If a global publishing order is needed, create an aggregation step after all partitions finish.

Listener order within a composite for the same execution differs from completion order across multiple concurrent executions.

## 20. Principles to Remember

- Listeners have distinct scopes: job, step, chunk, item, skip, and retry.
- `JobExecutionListener` wraps the job; `StepExecutionListener` wraps the step; `ChunkListener` wraps the chunk.
- Item listeners wrap individual read, process, or write calls; write listeners operate on the whole chunk.
- Opening callbacks typically run in registration/sorted order; closing callbacks typically run in reverse order in a composite listener.
- Do not treat `afterWrite` as proof of transaction commit; `afterChunk` is tied to successful chunk completion.
- `onWriteError` can run multiple times during retries or skip scans; `SkipListener` reflects only items actually skipped.
- A processor returning `null` is a filter, not a skip.
- Listener exceptions can impact the step; keep callbacks short and define clear error policies.
- When multiple listeners of the same type exist, declare order explicitly per your version's API and test the actual sequence.
- Do not rely on bean creation or component-scan order.
- In parallel processing, cross-worker order is not global; use correlation IDs and aggregation steps when needed.
- Post-write side effects need proper transactions, idempotency, or an outbox to avoid false notifications on rollback/retry.

Understanding listener order helps place auditing, metrics, error handling, and orchestration in the right places across the Spring Batch lifecycle. When you clearly distinguish callbacks by job/step/chunk/item level, opening and closing order across multiple listeners, and transaction commit/rollback boundaries, applications avoid misreporting status or triggering duplicate side effects.
