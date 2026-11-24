# Using Listeners for Metrics and Auditing

Spring Batch provides listeners so applications can observe milestones in the lifecycle of a Job, Step, chunk, and individual item. This is the right place to measure duration, record processing counts, track errors, and build an audit trail for batch operations.

Metrics and audits serve different purposes. Metrics help answer how fast or slow the system is running, how many items were processed, and how many errors occurred. Audits record which process performed what work, on which unit of data, at what time, and with what outcome. Listeners can supply data for both, though you must choose the right callbacks and design storage to fit transaction boundaries.

## 1. What is a Listener in Spring Batch?

A listener is a callback invoked by Spring Batch at specific points during execution. The application implements a listener interface or uses supported listener annotations, then registers the listener on a Job or Step.

Commonly used listener groups:

| Listener | Observation Scope | Example Usage |
|---|---|---|
| `JobExecutionListener` | Before and after Job | Audit Job runs, measure total duration |
| `StepExecutionListener` | Before and after Step | Step-level metrics, record Step outcome |
| `ChunkListener` | Before and after chunk, and on chunk error | Count chunks, observe chunk-level errors |
| `ItemReadListener` | Before/after read and on read error | Count read items, record source errors |
| `ItemProcessListener` | Before/after process and on process error | Measure processing duration, track filters |
| `ItemWriteListener` | Before/after write and on write error | Observe writer and write errors |
| `SkipListener` | When an item is skipped | Audit discarded records |

Listeners do not replace `ItemReader`, `ItemProcessor`, or `ItemWriter`. They observe or supplement actions at lifecycle points; responsibility for reading, processing, and writing remains with the respective components.

## 2. Choosing Listeners by the Level to Measure

Not every metric should be recorded at the item level. Choose callbacks at the granularity required to avoid generating excessive logs or metrics.

- To measure total runtime of a Job: use `JobExecutionListener`.
- To measure duration and counters of each Step: use `StepExecutionListener`.
- To count committed chunks or observe chunk errors: use `ChunkListener`.
- To know which item failed to read or process: use `ItemReadListener` or `ItemProcessListener`.
- To know how many items the writer received and when write errors occur: use `ItemWriteListener`.
- To audit skipped items: use `SkipListener`.

General observation flow:

~~~text
JobExecutionListener.beforeJob()
        |
        v
StepExecutionListener.beforeStep()
        |
        v
ChunkListener.beforeChunk()
        |
        v
ItemReadListener / ItemProcessListener
        |
        v
ItemWriteListener
        |
        v
ChunkListener.afterChunk()
        |
        v
StepExecutionListener.afterStep()
        |
        v
JobExecutionListener.afterJob()
~~~

A Step may have many chunks; inside each chunk, the reader, processor, and writer can be invoked multiple times or not at all if there are no corresponding items. Error and skip callbacks are invoked according to circumstances and fault-tolerance configuration.

## 3. JobExecutionListener for Job-Level Metrics and Auditing

`JobExecutionListener` has two primary callbacks:

- `beforeJob(JobExecution)`: invoked before the Job executes its Steps.
- `afterJob(JobExecution)`: invoked when the Job finishes, whether the outcome is completion or failure.

The listener can extract the Job name, `JobExecution` ID, `JobInstance` ID, `JobParameters`, `BatchStatus`, and `ExitStatus` to create an audit record.

~~~java
public class JobAuditListener implements JobExecutionListener {

    private final JobAuditService auditService;

    public JobAuditListener(JobAuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public void beforeJob(JobExecution execution) {
        auditService.recordStarted(
                execution.getId(),
                execution.getJobInstance().getJobName(),
                execution.getJobInstance().getId());
    }

    @Override
    public void afterJob(JobExecution execution) {
        auditService.recordFinished(
                execution.getId(),
                execution.getJobInstance().getJobName(),
                execution.getStatus().name(),
                execution.getExitStatus().getExitCode());
    }
}
~~~

Register the listener when declaring the Job:

~~~java
@Bean
Job importOrdersJob(
        JobRepository jobRepository,
        JobAuditListener jobAuditListener,
        Step importOrdersStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .listener(jobAuditListener)
            .start(importOrdersStep)
            .build();
}
~~~

A `JobInstance` can have multiple `JobExecution` records due to restarts; therefore, store the `JobExecution` ID to distinguish individual runs while storing the `JobInstance` ID to link runs belonging to the same logical unit of work.

If a Job is launched asynchronously, the HTTP request may complete immediately after receiving the `JobExecution`. A Job-level listener is the right place to record the final outcome once the Job actually finishes.

## 4. StepExecutionListener for Timing and Counters

`StepExecutionListener` provides `beforeStep` and `afterStep`. The `StepExecution` object contains rich information for metrics and auditing:

- Step name and associated `JobExecution`.
- `BatchStatus` and `ExitStatus`.
- Start and end timestamps.
- Read count, write count, and filter count.
- Read/process/write skip counts.
- Commit count and rollback count.

Example listener using Micrometer to record duration and counters:

~~~java
public class StepMetricsListener implements StepExecutionListener {

    private final MeterRegistry registry;
    private long startedAtNanos;

    public StepMetricsListener(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void beforeStep(StepExecution execution) {
        startedAtNanos = System.nanoTime();
    }

    @Override
    public ExitStatus afterStep(StepExecution execution) {
        String jobName =
                execution.getJobExecution().getJobInstance().getJobName();
        String stepName = execution.getStepName();
        String status = execution.getStatus().name();

        Timer.builder("batch.step.duration")
                .tag("job", jobName)
                .tag("step", stepName)
                .tag("status", status)
                .register(registry)
                .record(Duration.ofNanos(
                        System.nanoTime() - startedAtNanos));

        counter("batch.step.items.read", jobName, stepName, status)
                .increment(execution.getReadCount());
        counter("batch.step.items.written", jobName, stepName, status)
                .increment(execution.getWriteCount());
        counter("batch.step.items.filtered", jobName, stepName, status)
                .increment(execution.getFilterCount());
        counter("batch.step.items.skipped", jobName, stepName, status)
                .increment(
                        execution.getReadSkipCount()
                        + execution.getProcessSkipCount()
                        + execution.getWriteSkipCount());

        counter("batch.step.chunks.committed", jobName, stepName, status)
                .increment(execution.getCommitCount());
        counter("batch.step.chunks.rolledback", jobName, stepName, status)
                .increment(execution.getRollbackCount());

        return execution.getExitStatus();
    }

    private Counter counter(
            String name, String job, String step, String status) {
        return Counter.builder(name)
                .tag("job", job)
                .tag("step", step)
                .tag("status", status)
                .register(registry);
    }
}
~~~

The example requires the corresponding Micrometer and Spring Batch imports. Because the listener stores `startedAtNanos` in a field, ensure a single instance is not shared concurrently across multiple `StepExecution` instances. You can scope the listener per `StepExecution` or store the start timestamp keyed by execution ID if using a singleton listener.

Register on the Step:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        StepMetricsListener stepMetricsListener,
        ItemReader<Order> reader,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .writer(writer)
            .listener(stepMetricsListener)
            .build();
}
~~~

The timer measures duration from `beforeStep` to `afterStep`. Counters in the example are incremented using the aggregated figures on `StepExecution` when the Step completes. When a Job restarts, the rerun has a new execution; per-execution metrics thus reflect each attempt, while dashboards can aggregate by Job and Step.

Some Spring Batch versions and configurations include built-in metric/observation integration via Micrometer. Check existing built-in metrics before creating custom metrics with conflicting names. Custom listeners remain useful when you need extra business dimensions or dedicated auditing.

## 5. Measuring Items at Read, Process, and Write Levels

Item listeners allow observing each stage in detail.

### ItemReadListener

Callbacks:

- `beforeRead()`: before calling the reader.
- `afterRead(item)`: after reading an item.
- `onReadError(exception)`: when reading throws an error.

~~~java
public class ReadAuditListener implements ItemReadListener<Order> {

    private final ItemAuditService auditService;

    public ReadAuditListener(ItemAuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public void beforeRead() {
        // Can start measuring read duration if genuinely needed.
    }

    @Override
    public void afterRead(Order item) {
        auditService.recordRead(item.getId());
    }

    @Override
    public void onReadError(Exception exception) {
        auditService.recordReadFailure(
                exception.getClass().getSimpleName());
    }
}
~~~

`afterRead` is invoked only when the reader returns an item. When the reader returns `null` to signal EOF, there is no item to pass to `afterRead`. Do not use `afterRead` to count `read()` invocations or detect EOF.

### ItemProcessListener

Callbacks:

- `beforeProcess(item)`: before the processor processes an item.
- `afterProcess(item, result)`: after the processor returns a result.
- `onProcessError(item, exception)`: when the processor throws an error.

~~~java
public class ProcessMetricsListener
        implements ItemProcessListener<Order, Order> {

    private final MeterRegistry registry;

    public ProcessMetricsListener(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void beforeProcess(Order item) {
        // No need to emit per-item metrics if aggregate counters suffice.
    }

    @Override
    public void afterProcess(Order item, Order result) {
        if (result == null) {
            registry.counter("batch.item.filtered").increment();
        }
    }

    @Override
    public void onProcessError(Order item, Exception exception) {
        registry.counter(
                "batch.item.process.errors",
                "exception", exception.getClass().getSimpleName())
                .increment();
    }
}
~~~

A processor returning `null` means the item was filtered. `afterProcess` receives a `null` result in that case. `StepExecution`'s filter count can also be used to aggregate filtered items, avoiding per-item metric emission when granular detail is unnecessary.

### ItemWriteListener

Callbacks:

- `beforeWrite(chunk)`: before the writer writes a chunk.
- `afterWrite(chunk)`: after the writer completes writing normally.
- `onWriteError(exception, chunk)`: when the writer throws an error.

~~~java
public class WriteAuditListener implements ItemWriteListener<Order> {

    private final MeterRegistry registry;

    public WriteAuditListener(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void beforeWrite(Chunk<? extends Order> chunk) {
        registry.counter("batch.writer.calls").increment();
    }

    @Override
    public void afterWrite(Chunk<? extends Order> chunk) {
        registry.counter("batch.writer.items")
                .increment(chunk.size());
    }

    @Override
    public void onWriteError(
            Exception exception,
            Chunk<? extends Order> chunk) {
        registry.counter(
                "batch.writer.errors",
                "exception", exception.getClass().getSimpleName())
                .increment();
    }
}
~~~

`afterWrite` indicates that the writer call returned normally. Do not equate this callback with guaranteeing that the chunk transaction has committed. An error later in the same transaction can still cause the chunk to roll back. Hence, metrics from `afterWrite` should be interpreted as items handled normally by the writer at callback time, while final post-Step figures should come from `StepExecution` counters.

If you want to audit an action only when the business transaction commits, design a mechanism tied to the transaction or a transactional outbox rather than treating `afterWrite` as the final commit signal.

## 6. ChunkListener for Tracking Individual Chunks

`ChunkListener` provides these callbacks:

- `beforeChunk(context)`: before processing a chunk.
- `afterChunk(context)`: after a chunk finishes processing successfully.
- `afterChunkError(context)`: when chunk processing encounters an error.

~~~java
public class ChunkMetricsListener implements ChunkListener {

    private final MeterRegistry registry;

    public ChunkMetricsListener(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void beforeChunk(ChunkContext context) {
        registry.counter("batch.chunk.started").increment();
    }

    @Override
    public void afterChunk(ChunkContext context) {
        registry.counter("batch.chunk.completed").increment();
    }

    @Override
    public void afterChunkError(ChunkContext context) {
        registry.counter("batch.chunk.errors").increment();
    }
}
~~~

`ChunkListener` is useful when you need the count of completed chunks, failed chunks, or per-chunk timing. When measuring timing, store state per execution or thread; avoid a shared singleton variable when Steps run concurrently.

`ChunkListener` does not provide the list of items in the same way `ItemWriteListener` does. When per-item auditing is needed, use the corresponding item listener or business service. When stable aggregate numbers are needed, `StepExecution` counters are usually simpler and consume fewer resources.

## 7. SkipListener for Recording Skipped Items

When a Step is configured with skip, a failing item can be bypassed so the Job continues. This is worth recording because the output may omit that item.

`SkipListener` provides these callbacks:

- `onSkipInRead(exception)`: skippable read error; the framework has no valid item to pass to the callback.
- `onSkipInProcess(item, exception)`: an item was read, failed in the processor, and was skipped.
- `onSkipInWrite(item, exception)`: an item reached the writer, failed to write, and was skipped.

~~~java
public class OrderSkipAuditListener
        implements SkipListener<Order, Order> {

    private final SkipAuditService auditService;

    public OrderSkipAuditListener(SkipAuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public void onSkipInRead(Throwable exception) {
        auditService.recordReadSkip(
                exception.getClass().getSimpleName());
    }

    @Override
    public void onSkipInProcess(Order item, Throwable exception) {
        auditService.recordItemSkip(
                item.getId(),
                "PROCESS",
                exception.getClass().getSimpleName());
    }

    @Override
    public void onSkipInWrite(Order item, Throwable exception) {
        auditService.recordItemSkip(
                item.getId(),
                "WRITE",
                exception.getClass().getSimpleName());
    }
}
~~~

`SkipListener` is suited for recording business identifiers and the failing phase. Avoid storing full objects or sensitive content in audits unless necessary.

Spring Batch coordinates skip callbacks within the chunk's fault-tolerant lifecycle so an item is not reported as skipped repeatedly across normal rollbacks/retries. Even so, the audit service should still enforce deduplication keyed by `JobExecution`/`StepExecution`, item key, and skip type, especially if audits are sent outside the transaction.

## 8. Registering Multiple Listeners on a Step

You can register corresponding listeners using `.listener(...)` calls on `StepBuilder`.

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        StepMetricsListener stepMetricsListener,
        ChunkMetricsListener chunkMetricsListener,
        ReadAuditListener readAuditListener,
        ProcessMetricsListener processMetricsListener,
        WriteAuditListener writeAuditListener,
        OrderSkipAuditListener skipAuditListener,
        ItemReader<Order> reader,
        ItemProcessor<Order, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .listener(stepMetricsListener)
            .listener(chunkMetricsListener)
            .listener(readAuditListener)
            .listener(processMetricsListener)
            .listener(writeAuditListener)
            .listener(skipAuditListener)
            .faultTolerant()
            .skip(InvalidOrderException.class)
            .skipLimit(20)
            .build();
}
~~~

This configuration illustrates the listener types that can be registered together on a Step. In real applications, register only the listeners you actually need; avoid creating multiple callbacks for the same event if they emit duplicate metrics or audits.

Job-level listeners are registered on `JobBuilder`, while Step-level listeners are registered on `StepBuilder`. You can extract listeners into separate beans for easier testing and environment-specific configuration.

## 9. Distinguishing Metrics, Technical Audits, and Business Audits

These three data categories have different storage requirements.

| Category | Question Answered | Example Fields |
|---|---|---|
| Metric | How fast/slow is the Job running? | Duration, read/write count, error count |
| Technical audit | Which execution ran? | `JobExecution` ID, Step, status, timestamp |
| Business audit | What business action was performed? | Batch ID, business key, action, outcome |

Metrics are normally aggregated and retained for short or medium windows. Technical audits need to trace executions over time. Business audits may have compliance or long-term retention requirements.

Do not use metrics to replace audits, because metrics generally do not preserve individual events. Conversely, do not write an audit record for every single item if you only need total item counts; audit data volume can grow very rapidly.

## 10. Designing Audit Records

A technical audit record can include:

- Job and Step names.
- `JobInstance` ID, `JobExecution` ID, and `StepExecution` ID.
- Batch ID or non-sensitive business key.
- Event: `STARTED`, `COMPLETED`, `FAILED`, `SKIPPED`.
- Occurrence timestamp.
- `BatchStatus` and `ExitStatus`.
- Read/write/filter/skip counts where relevant.
- Standardized error code or exception type.
- Correlation ID linking logs and launch requests.

Example audit JSON:

~~~json
{
  "event": "STEP_COMPLETED",
  "jobName": "importOrdersJob",
  "jobExecutionId": 108,
  "stepExecutionId": 214,
  "stepName": "writeOrdersStep",
  "status": "COMPLETED",
  "readCount": 1200,
  "writeCount": 1185,
  "filterCount": 15,
  "skipCount": 0
}
~~~

This illustrates the structure; field names and formats can be tailored to your audit system. Keep execution identifiers for cross-referencing with `JobRepository` and avoid putting unnecessary personal data or secrets into events.

## 11. Auditing and Transactions: Listeners Do Not Create Atomicity Automatically

This is the most critical point when writing audits from listeners.

The `afterWrite` callback is invoked after the writer returns, yet the chunk transaction may not have committed yet. If a listener sends an audit event to an external system and the database transaction then rolls back, the audit may claim the item was written when business data never actually committed.

Similarly, if a listener writes an audit using an independent database transaction, the audit can commit even if the business transaction fails. That may be desirable for technical audits recording failures, but it is not equivalent to a business audit confirming committed data.

Choose a strategy based on purpose:

### Technical audits recording runs and errors

Start, completion, and error events can be written to a separate audit store. Define the policy if the audit store is unavailable: whether to fail the Job, retry the audit write, or log a warning. For mandatory audit requirements, do not silently ignore audit write failures.

### Business audits must be atomic with data

If business rows and audit rows must commit or roll back together, write both within the same transactional resource. One approach is inserting the audit/outbox row inside the writer or business service participating in the chunk transaction.

~~~text
Chunk transaction
       |
       +--> INSERT business order
       |
       +--> INSERT audit/outbox event
       |
       v
     COMMIT
       |
       v
Publisher reads outbox and emits event
~~~

The publisher can dispatch the event after commit. If sending fails, it retries; the receiver should support idempotency or deduplication. This reduces the risk of emitting an audit event when the business transaction never committed.

### Post-commit audits

Transaction synchronization or an outbox can execute actions after commit. However, a post-commit callback writing to another system can still fail midway. An outbox is usually better when you must guarantee events are not lost after the business transaction commits.

Do not rely on a listener as an exactly-once guarantee for external effects. You need deduplication keys and retry/reconciliation capabilities.

## 12. Recording Metrics with Micrometer

Micrometer provides commonly used meter types:

- **Counter:** counts events or items.
- **Timer:** measures duration and invocation counts.
- **Gauge:** observes a current value, such as active running Jobs given a suitable state source.
- **DistributionSummary:** tracks distribution of values such as payload size or items per chunk.

Example measuring chunk size:

~~~java
DistributionSummary chunkSizeSummary =
        DistributionSummary.builder("batch.chunk.payload.bytes")
                .tag("job", "importOrdersJob")
                .tag("step", "writeOrdersStep")
                .register(registry);

chunkSizeSummary.record(payloadBytes);
~~~

You can record chunk size, writer duration, or items per chunk to identify bottlenecks. Choose meaningful meters and clear units; for example, name or document byte units consistently.

### Avoiding excessive cardinality

Do not put continuously changing values into metric tags:

- `JobExecution` ID or `StepExecution` ID.
- Customer ID, Order ID, or file path.
- Request ID or correlation ID.
- Exception names containing dynamic text.
- Arbitrary `JobParameters` values.

Each tag combination creates a separate time series. Attaching per-execution or per-item IDs to metrics can explode series counts, consuming memory and overloading the metrics backend.

Use bounded-value tags such as job name, step name, status, environment, and normalized error category. Put granular IDs into logs or audit events.

## 13. Correlation IDs and Logging Context

When a Job is triggered by an HTTP request, scheduler, or message broker, a correlation ID links request logs with Job and Step logs.

You can pass a correlation ID as a non-identifying `JobParameters` entry if that value does not alter `JobInstance` identity. Note that non-identifying parameters are still persisted in metadata; use only non-sensitive values.

A listener can populate `JobExecution` ID or correlation ID into the logging context, such as SLF4J's MDC:

~~~java
public class StepLoggingListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution execution) {
        MDC.put("jobExecutionId",
                String.valueOf(execution.getJobExecutionId()));
        MDC.put("stepExecutionId",
                String.valueOf(execution.getId()));
    }

    @Override
    public ExitStatus afterStep(StepExecution execution) {
        MDC.remove("jobExecutionId");
        MDC.remove("stepExecutionId");
        return execution.getExitStatus();
    }
}
~~~

Always clean up MDC when the Step ends so values from a prior execution do not linger on reused threads. If the Step processes concurrently or offloads work to another executor, MDC does not automatically propagate to new threads; use proper context propagation and cleanup on each thread.

Do not place tokens, passwords, or sensitive data into MDC. Every log emitted on that thread can automatically include MDC values.

## 14. Listeners and Retry/Skip

In a fault-tolerant Step, an operation can be retried before succeeding or being skipped. Thus, listener callbacks do not always map one-to-one with a final business outcome.

Example:

~~~text
Item A:
  processor is called
  writer writes successfully
  chunk commits

Item B:
  writer is called
  transient error
  rollback
  retry
  writer succeeds
  chunk commits
~~~

Some callbacks can be called multiple times due to retries. If each callback generates an external audit event outside the transaction, the audit system may record multiple events for the same item.

To avoid confusion:

- Use `StepExecution` counters to report aggregate Step-end results.
- Use `SkipListener` to record items actually skipped per Spring Batch's lifecycle.
- Attach deduplication keys to audit events by execution, item, and event type.
- Do not treat `beforeWrite`/`afterWrite` as proof that the chunk committed.
- Include the attempt number explicitly if tracking retries, but do not substitute attempt metrics for final outcomes.

If detailed retry tracking is needed, integrate Spring Retry listeners or corresponding observability hooks matching your version/fault-tolerance setup. Add them only when attempt counts and retry causes are needed; avoid logging every retry attempt at high data volumes.

## 15. Performance When Listeners Run Per Item

Item listeners can run millions of times in a single Job. Even a small operation such as synchronous logging, an HTTP call, or inserting an audit row per item can noticeably slow down the Step.

Guidelines:

- Do not make synchronous network calls from item callbacks unless strictly necessary.
- Avoid object allocations, string formatting, or large payload serialization per item when aggregate metrics suffice.
- Reuse counters and timers via `MeterRegistry`.
- Write detailed audits per business requirements; consider batch inserts or an outbox.
- Do not log every item at `INFO` level in large Jobs.
- Use sampling or `DEBUG`-level logging for high-volume diagnostic data.
- Do not let a listener hold a shared lock that forces worker threads to wait on each other.

If a listener updates mutable state, verify whether the Step runs multi-threaded. A singleton listener can be shared across multiple executions; do not store per-execution state in mutable singleton fields without isolation or synchronization.

## 16. Handling Errors When Recording Metrics or Audits

Metrics and audits should not alter Job outcomes unexpectedly. Define clear policies for each data category.

| Recording Type | When Target Store Fails | Policy Options |
|---|---|---|
| Operational metrics | Registry/exporter temporarily fails | Prefer non-blocking behavior; use proper buffering/export |
| Mandatory technical audit | Audit store unavailable | May fail the Job or write to a durable fallback per requirements |
| Atomic business audit | Outbox write fails | Roll back business transaction with the chunk |
| Diagnostic logs | Logging backend temporarily fails | Use configured appenders/buffering; never log secrets |

Do not catch and ignore every exception in a listener. If auditing is mandatory, silently ignoring failures leaves audit gaps. Conversely, if metrics are supporting telemetry, failing the Job merely because an exporter is temporarily unreachable may be undesirable.

Separating metrics, technical audits, and business audits helps decide accurately whether an observability error may affect business processing.

## 17. Protecting Data in Metrics and Audits

Listeners often have access to `JobParameters`, items, and exceptions. These sources can contain sensitive information.

Do not record in metrics, logs, or audits:

- Passwords, API tokens, private keys, and credentials.
- Full request/response bodies containing personal data.
- Payment details or unnecessary personal identifiers.
- Exception messages that may expose SQL statements or sensitive parameters.
- Entire `JobParameters` without controlling their contents.

Prefer recording approved business identifiers, status, error category, and execution ID. Restrict read access to audit stores and enforce organizational retention policies.

## 18. Testing Listeners

Listeners should be tested at two levels.

### Unit tests

Verify the listener receives callbacks and emits metrics/audits with the right data. Mock `AuditService` or use `SimpleMeterRegistry` to assert counters and timers.

~~~java
@Test
void afterStepRecordsReadAndWriteCounts() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    StepMetricsListener listener = new StepMetricsListener(registry);

    JobInstance instance = new JobInstance(1L, "importOrdersJob");
    JobExecution jobExecution = new JobExecution(instance);
    StepExecution execution =
            new StepExecution("writeOrdersStep", jobExecution);

    execution.setReadCount(120L);
    execution.setWriteCount(115L);
    execution.setFilterCount(5L);
    execution.setStatus(BatchStatus.COMPLETED);

    listener.beforeStep(execution);
    ExitStatus result = listener.afterStep(execution);

    assertEquals(ExitStatus.COMPLETED, result);
    assertEquals(
            120.0,
            registry.get("batch.step.items.read").counter().count());
    assertEquals(
            115.0,
            registry.get("batch.step.items.written").counter().count());
}
~~~

This test illustrates asserting metrics after callbacks. In real tests, populate all required fields appropriate for your Spring Batch version.

### Integration tests

Run a real Job/Step and verify:

- `beforeJob`/`afterJob` run at the right lifecycle points.
- `beforeStep`/`afterStep` record the right status and execution ID.
- Item listeners run when items are read, processed, and written.
- `SkipListener` records the right skip categories.
- Chunk listeners record chunk completions and errors.
- Retries do not create unintended duplicate audits.
- Failed Jobs still emit an appropriate terminal technical audit.
- Listeners do not alter `ExitStatus` unintentionally.
- Metrics do not create high-cardinality tags.
- MDC is cleared after the Step finishes.

Include tests for completed Jobs, failed Jobs, skipped Steps, and Job restarts. For outbox audits, confirm business rows and outbox rows commit or roll back together.

## 19. Observing Jobs After Execution

Listeners record metrics and audits during execution. For historical queries, combine that data with metadata from `JobRepository` and `JobExplorer`.

`JobExplorer` allows reading persisted `JobInstance`, `JobExecution`, and `StepExecution` records. Metadata supplies Spring Batch's standard statuses and counters; the audit store provides detailed events or business context; the metrics backend shows trends over time.

An operational dashboard can display:

| Group | Indicators |
|---|---|
| Job | Run count, completed/failed, duration |
| Step | Duration, read/write/filter/skip counts |
| Chunk | Chunks completed, rollbacks, chunk duration |
| Writer | Call count, items written, write errors |
| Audit | Execution ID, business key, outcome, skip events |
| System | Queue lag, database latency, relevant CPU and memory |

Do not substitute metrics for detailed execution history. When investigating a specific run, query by `JobExecution` ID and correlate metadata, logs, and audit events.

## 20. Workflow for Implementing Listeners for Metrics and Auditing

When designing observability for a Job, follow this order:

1. Determine whether you need Job-, Step-, chunk-, or item-level visibility.
2. Select the listener interfaces matching the required callbacks.
3. Use `StepExecution` counters for aggregate numbers instead of counting manually when already provided.
4. Use Micrometer `Timer`, `Counter`, or `DistributionSummary` for metrics exported to monitoring.
5. Keep metric tags low-cardinality; place execution IDs in logs and audits.
6. Clarify how technical audits and business audits differ in transaction requirements.
7. Use an outbox or the same transactional resource if audits must be atomic with business data.
8. Generate idempotency keys for audit events that may be retried or replayed.
9. Define the policy when metrics/audit stores are unavailable.
10. Test successful Jobs, failed Jobs, skips, retries, restarts, and concurrent runs.

Listeners allow observing the Spring Batch lifecycle at exact processing points. `StepExecutionListener` and `JobExecutionListener` fit aggregate metrics and execution audits; item and chunk listeners provide finer detail; `SkipListener` records discarded items. When you clearly distinguish callbacks, transaction boundaries, metric cardinality, and audit requirements, applications can monitor Jobs effectively without distorting processing outcomes.

