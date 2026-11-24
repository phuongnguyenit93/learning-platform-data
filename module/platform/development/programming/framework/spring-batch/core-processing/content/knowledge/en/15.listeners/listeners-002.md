# StepExecutionListener Before and After a Step

In Spring Batch, `StepExecutionListener` allows an application to execute logic at two key points in a Step's lifecycle: immediately before the Step begins processing and after the Step finishes. The listener receives a `StepExecution` object, enabling it to read the Step's status, `JobParameters`, `ExecutionContext`, timestamps, and counters.

`beforeStep()` is commonly used to log start information, check runtime conditions, or prepare data that depends on `StepExecution`. `afterStep()` is commonly used to log outcomes, aggregate metrics, or adjust `ExitStatus` to route the Job flow. `afterStep()` is called when the Step ends, even if the Step fails, so you should check the status before running logic meant only for successful runs.

## 1. What is StepExecutionListener?

`StepExecutionListener` is a Step-level listener. It provides callbacks before and after a single Step execution:

```java
public interface StepExecutionListener extends StepListener {

    void beforeStep(StepExecution stepExecution);

    ExitStatus afterStep(StepExecution stepExecution);
}
```

Both callbacks receive the same `StepExecution` type, but are invoked at different times:

| Callback | Timing | Common Purpose |
|---|---|---|
| `beforeStep()` | Before the Step begins its main processing | Log start, read `JobParameters`, check preconditions, prepare runtime metadata |
| `afterStep()` | After the Step finishes processing | Log outcome, read counters, summarize errors, return a custom `ExitStatus` |

`StepExecution` represents a specific execution of a Step. It holds the Step name, ID, `BatchStatus`, `ExitStatus`, start/end times, `ExecutionContext`, and counters such as items read, written, filtered, skipped, committed, or rolled back.

A listener is not a separate Step in the Job. It is registered on a Step and invoked by the framework during that Step's lifecycle.

## 2. Lifecycle of beforeStep and afterStep Calls

When a Job runs a Step, Spring Batch creates or retrieves the corresponding `StepExecution` and invokes the listener before starting Step processing. Once the Step completes or fails, the framework invokes the post-Step listener with the execution's metadata.

```text
JobLauncher
    |
    v
Job starts Step
    |
    v
Create / prepare StepExecution
    |
    v
beforeStep(stepExecution)
    |
    v
Open streams and execute Step
    |
    +--> Tasklet or chunk processing
    |       |
    |       +--> read / process / write / commit
    |
    v
Step ends: COMPLETED / FAILED / STOPPED / ...
    |
    v
afterStep(stepExecution)
    |
    v
Finish metadata updates and continue Job flow
```

`beforeStep()` is called once per `StepExecution`. In a chunk-oriented Step, it is not called before each chunk or before each item. Similarly, `afterStep()` is called at the Step level, not after each time the writer writes a chunk.

`afterStep()` is invoked when the Step ends, including when processing fails. Therefore, this callback is suitable for recording the final result or classifying the status, but you should not assume the Step always succeeded when the callback is invoked.

## 3. Implementing StepExecutionListener via Interface

Example listener logging start details and post-Step outcomes:

```java
public class ImportStepListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        String businessDate = stepExecution.getJobParameters()
                .getString("businessDate");

        log.info(
                "Starting step={}, executionId={}, businessDate={}",
                stepExecution.getStepName(),
                stepExecution.getId(),
                businessDate
        );
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        log.info(
                "Finished step={}, status={}, exitStatus={}, read={}, written={}",
                stepExecution.getStepName(),
                stepExecution.getStatus(),
                stepExecution.getExitStatus(),
                stepExecution.getReadCount(),
                stepExecution.getWriteCount()
        );

        return stepExecution.getExitStatus();
    }
}
```

In `beforeStep()`, the listener can read `JobParameters` through `StepExecution`. This is how you obtain runtime parameters without holding them in mutable fields of the listener.

In `afterStep()`, the listener reads the status and counters after Step processing has finished. The logging example above helps correlate logs with a specific `StepExecution` ID, which is useful when a `JobInstance` undergoes multiple restarts.

## 4. Registering the Listener on a Step

The listener must be registered in the Step configuration for Spring Batch to invoke its callbacks. With modern Java configuration:

```java
@Bean
public ImportStepListener importStepListener() {
    return new ImportStepListener();
}

@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, Order> processor,
        ItemWriter<Order> writer,
        ImportStepListener listener) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .listener(listener)
            .build();
}
```

Calling `.listener(listener)` registers the listener on the Step. When the Step executes, Spring Batch invokes `beforeStep()` and `afterStep()` according to the Step lifecycle.

A single listener can be registered on multiple Steps if its logic is reusable. However, avoid storing per-run state in mutable fields of a singleton listener. Runtime data should be read from `StepExecution` or stored in the appropriate `ExecutionContext`.

## 5. Using @BeforeStep and @AfterStep Annotations

Spring Batch also supports annotations to declare callbacks on listener beans. This is helpful when you want to keep listener logic in a component without implementing the interface directly:

```java
@Component
public class ImportAuditListener {

    @BeforeStep
    public void beforeStep(StepExecution stepExecution) {
        log.info(
                "Starting {} with executionId={}",
                stepExecution.getStepName(),
                stepExecution.getId()
        );
    }

    @AfterStep
    public ExitStatus afterStep(StepExecution stepExecution) {
        log.info(
                "Step {} ended with {}",
                stepExecution.getStepName(),
                stepExecution.getStatus()
        );

        return stepExecution.getExitStatus();
    }
}
```

Register this bean on the Step with `.listener(importAuditListener)`. The annotations designate callback methods; they do not automatically make every bean in the application context a listener for every Step.

When using annotations, method signatures must match the callback contract: `@BeforeStep` takes `StepExecution` and returns `void`; `@AfterStep` takes `StepExecution` and may return `ExitStatus`.

## 6. Data Available from StepExecution

`StepExecution` provides metadata about the Step execution. Some commonly used getters:

| Getter | Information |
|---|---|
| `getId()` | ID of the `StepExecution` |
| `getStepName()` | Step name |
| `getJobExecution()` | `JobExecution` containing this `StepExecution` |
| `getJobParameters()` | `JobParameters` of the Job run |
| `getStatus()` | `BatchStatus` of the Step |
| `getExitStatus()` | Current `ExitStatus` of the Step |
| `getStartTime()` | Start timestamp |
| `getEndTime()` | End timestamp, if finished |
| `getReadCount()` | Number of items read successfully |
| `getWriteCount()` | Number of items written successfully |
| `getFilterCount()` | Number of items filtered by the processor |
| `getSkipCount()` | Total number of skipped items |
| `getCommitCount()` | Number of recorded commits |
| `getRollbackCount()` | Number of recorded rollbacks |
| `getExecutionContext()` | Step-level `ExecutionContext` |

For example, a listener can log metrics after the Step:

```java
@Override
public ExitStatus afterStep(StepExecution stepExecution) {
    log.info(
            "step={}, read={}, write={}, filter={}, skip={}, commit={}, rollback={}",
            stepExecution.getStepName(),
            stepExecution.getReadCount(),
            stepExecution.getWriteCount(),
            stepExecution.getFilterCount(),
            stepExecution.getSkipCount(),
            stepExecution.getCommitCount(),
            stepExecution.getRollbackCount()
    );

    return stepExecution.getExitStatus();
}
```

Do not infer committed item counts solely from `writeCount` or transaction counts solely from `readCount`. Filtering, skipping, retrying, rollbacks, and a final chunk smaller than the commit interval can cause these counters to differ.

## 7. Distinguishing BatchStatus and ExitStatus

These two statuses have different meanings:

- `BatchStatus` describes the Step's lifecycle state managed by Spring Batch, such as `STARTED`, `COMPLETED`, `FAILED`, `STOPPED`, or `ABANDONED`.
- `ExitStatus` describes the Step's exit outcome using an exit code and description. It is commonly used to decide the next branch in the Job flow.

For example, a Step may complete technically while having some skipped items. In that case, `BatchStatus` can still be `COMPLETED`, while the application wants to set `ExitStatus` to `COMPLETED_WITH_SKIPS` so the Job flow routes to a suitable handling branch.

`afterStep()` can return a custom `ExitStatus`. Spring Batch combines the returned value with the Step's current `ExitStatus`. Example:

```java
public class SkipStatusListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        // No pre-Step processing needed.
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getStatus() == BatchStatus.COMPLETED
                && stepExecution.getSkipCount() > 0) {
            return new ExitStatus(
                    "COMPLETED_WITH_SKIPS",
                    "Step completed with skipped items"
            );
        }

        return stepExecution.getExitStatus();
    }
}
```

The listener only assigns an exit code describing completion with skips. It does not turn a `FAILED` Step into `COMPLETED`, because the condition in the example applies only when `BatchStatus` is `COMPLETED`.

If business logic truly fails, let an exception in the Tasklet/chunk fail the Step or use an appropriate stop mechanism. Do not just change `ExitStatus` to `FAILED` in a listener and assume `BatchStatus` changed with it.

## 8. Using ExitStatus to Route Job Flow

A Job flow can choose the next step based on a Step's exit code. A listener can classify the outcome, while the Job definition decides the corresponding branch.

Example of logical branches:

```text
importOrdersStep
    |
    +-- COMPLETED ----------------------> nextStep
    |
    +-- COMPLETED_WITH_SKIPS -----------> reviewSkippedOrdersStep
    |
    +-- FAILED -------------------------> errorHandlingStep / Job failed
```

With the Java flow builder, you can declare transitions by exit code:

```java
@Bean
public Job importJob(
        JobRepository jobRepository,
        Step importOrdersStep,
        Step reviewSkippedOrdersStep,
        Step nextStep) {

    return new JobBuilder("importJob", jobRepository)
            .start(importOrdersStep)
                .on("COMPLETED_WITH_SKIPS").to(reviewSkippedOrdersStep)
            .from(importOrdersStep)
                .on("COMPLETED").to(nextStep)
            .from(importOrdersStep)
                .on("*").fail()
            .end()
            .build();
}
```

The flow above illustrates selecting transitions by exit code; declare all branches needed for your actual Job. When using the wildcard `*`, place specific transitions first so outcomes are classified as intended.

Do not confuse exit codes with `BatchStatus`. Flow transitions match against `ExitStatus.exitCode`, so if the listener returns `COMPLETED_WITH_SKIPS`, the transition must use that exact string.

## 9. Using beforeStep to Read Parameters and Prepare Data

`beforeStep()` is suited for reading input parameters or preparing metadata needed for Step processing. For example, a listener validating the business date:

```java
public class BusinessDateListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        String businessDate = stepExecution.getJobParameters()
                .getString("businessDate");

        if (businessDate == null || businessDate.isBlank()) {
            throw new IllegalArgumentException("businessDate is required");
        }

        log.info("Preparing Step for businessDate={}", businessDate);
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        return stepExecution.getExitStatus();
    }
}
```

Checking preconditions before the Step starts helps catch configuration errors early. However, critical `JobParameters` validation should also live at the launch layer or in a `JobParametersValidator` where appropriate, so invalid requests are rejected before the Job starts.

Do not place heavy business work or hard-to-reverse side effects in `beforeStep()`. This callback is not a chunk transaction; if it calls an API or writes a file and the Step then fails, the side effect has already occurred. Use a Tasklet or dedicated Step if the operation needs clear transactions, retry, skip, or checkpointing.

## 10. Using afterStep to Summarize Outcomes

`afterStep()` is a convenient place to read final counters and record outcomes. For example, if the number of skipped items exceeds a threshold, the application can set a custom exit code to trigger a review step:

```java
public class ImportResultListener implements StepExecutionListener {

    private final int warningThreshold;

    public ImportResultListener(int warningThreshold) {
        this.warningThreshold = warningThreshold;
    }

    @Override
    public void beforeStep(StepExecution stepExecution) {
        log.info("Import Step started: {}", stepExecution.getStepName());
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        int skipped = stepExecution.getSkipCount();

        if (stepExecution.getStatus() == BatchStatus.COMPLETED
                && skipped > warningThreshold) {
            return new ExitStatus(
                    "COMPLETED_WITH_WARNINGS",
                    "Skipped item count exceeded threshold: " + skipped
            );
        }

        return stepExecution.getExitStatus();
    }
}
```

This listener only classifies the outcome after the Step finishes. If you need to send notifications or update external systems, consider when transactions have committed and whether the operation can be retried. `afterStep()` should not be treated as a post-commit callback for every external resource.

## 11. How beforeStep and afterStep Differ from Item/Chunk Listeners

Spring Batch provides several listener types, each matching a specific scope:

| Listener | Scope | Typical Callbacks |
|---|---|---|
| `JobExecutionListener` | Single Job execution | `beforeJob`, `afterJob` |
| `StepExecutionListener` | Single Step execution | `beforeStep`, `afterStep` |
| `ChunkListener` | Single chunk | `beforeChunk`, `afterChunk`, `afterChunkError` |
| `ItemReadListener` | Single item read | `beforeRead`, `afterRead`, `onReadError` |
| `ItemProcessListener` | Single item process | `beforeProcess`, `afterProcess`, `onProcessError` |
| `ItemWriteListener` | Single writer call for a chunk | `beforeWrite`, `afterWrite`, `onWriteError` |

If you want to log once when a Step starts, use `StepExecutionListener`. If you want to time individual chunks or observe per-write errors, use the chunk- or item-level listener instead. Do not use `afterStep()` to replace `afterWrite()` or `afterChunk()`, because `afterStep()` runs only once at the end of the Step.

## 12. ExecutionContext and Data the Listener Needs to Keep

If a listener needs to pass a value from the start of a Step to the end of the Step, an object field can be used only when you are sure the listener serves a single execution and does not run concurrently. However, with shared singleton beans or parallel Steps, mutable fields can be shared unintentionally.

For state that must survive restarts or be persisted in metadata, use the Step `ExecutionContext`:

```java
public class StepStateListener implements StepExecutionListener {

    private static final String START_MARKER = "audit.started";

    @Override
    public void beforeStep(StepExecution stepExecution) {
        stepExecution.getExecutionContext().putString(
                START_MARKER,
                Instant.now().toString()
        );
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        String startedAt = stepExecution.getExecutionContext()
                .getString(START_MARKER, "unknown");

        log.info("Step startedAt={}", startedAt);
        return stepExecution.getExitStatus();
    }
}
```

The example above demonstrates accessing the Step context. If the data is only for logging, use `StepExecution.getStartTime()` instead of storing a duplicate. If durable state across restarts is required, understand when the context is persisted by `JobRepository`; an in-memory update does not mean it has been flushed to the database immediately.

## 13. Notes on Exceptions and Side Effects in Listeners

A listener participates in the Step lifecycle but does not replace the transaction logic of a Tasklet or chunk. Be careful with exceptions and side effects:

- Do not use exceptions in `afterStep()` as the primary way to fail a Step that has already run. Let business errors occur during Step execution or return an appropriate `ExitStatus` for the flow.
- Do not assume `afterStep()` is only called when the Step succeeds; always check `BatchStatus` before handling success results.
- Do not send emails, call transactional APIs, or publish messages without a deduplication mechanism. A listener can be invoked again in another `StepExecution` when the Job restarts.
- Do not record a success status outside the transaction and assume Step metadata has definitely committed.
- Do not keep mutable execution state in a singleton listener if multiple `StepExecution` instances can run concurrently.
- Do not arbitrarily alter `BatchStatus` in a listener. Use `ExitStatus` to classify outcomes and use the Step's error handling to represent real failures.

If side effects must happen only after data is committed, use an appropriate transaction synchronization mechanism, an outbox, or a separate Step. Regardless of which listener is used, external operations still require idempotency if retries are possible.

## 14. Common Misconceptions

**Assuming `beforeStep()` runs before every chunk.** This callback runs once at the start of a `StepExecution`. To run logic before each chunk, use `ChunkListener`.

**Assuming `afterStep()` runs only on success.** The callback is invoked when the Step finishes even on failure. Check `stepExecution.getStatus()`.

**Assuming returning a new `ExitStatus` changes `BatchStatus`.** `ExitStatus` describes the exit outcome and routes the flow; `BatchStatus` describes the lifecycle state. The two fields are not identical.

**Assuming a listener is automatically applied to all Steps.** You must register the listener on the Step or configure it through an explicit mechanism.

**Storing `StepExecution` in a singleton listener field.** Multiple executions can run concurrently and overwrite each other's data. Use the callback parameter as the source of data.

**Sending success notifications in `afterStep()` without considering commits.** The post-Step callback does not guarantee that all external side effects outside the transaction committed atomically together.

**Using a listener to implement the Step's entire business logic.** Listeners are suited for lifecycle hooks, observability, and outcome classification. Business work requiring clear transactions and restartability belongs in a Tasklet or reader/processor/writer.

## 15. Choosing the Right Callback

Use `beforeStep()` when you need to know which `StepExecution` is about to run, read `JobParameters`, log start metadata, or perform lightweight runtime checks. Use `afterStep()` when you need to read the final status and counters, log the outcome, or return a custom `ExitStatus` so the Job flow selects the next branch.

If you need per-chunk or per-item handling, pick the listener at the corresponding scope. If you need business logic with transactions, retry, skip, or checkpointing, place the logic in the Step rather than relying on lifecycle callbacks. Understanding the invocation timing and the difference between `BatchStatus` and `ExitStatus` makes `StepExecutionListener` a practical tool for monitoring and controlling Job flows.
