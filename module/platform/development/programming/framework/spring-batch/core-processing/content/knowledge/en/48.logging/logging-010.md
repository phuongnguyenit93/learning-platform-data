# Restart Point Logging in Spring Batch

When a Spring Batch job encounters an error while processing millions of records, operators immediately ask: **“Where will the next run resume from?”**. A log line like `Read 25,000 records` or `Job failed` is not enough to answer that. Spring Batch relies on metadata in `JobRepository` and `ItemStream` checkpoint state to determine recoverability. The purpose of **restart point logging** is to give humans visibility into that state, reconcile it against committed results, and investigate subsequent runs.

Within the **Logging** topic of **Spring Batch Core Processing**, this lesson explains what a restart point means, authoritative data sources, where to log in the chunk/step lifecycle, how to configure listeners, and common mistakes that make logs report a different resume point than the actual checkpoint.

## 1. What Is a Restart Point?

A **restart point** is a persisted position or state sufficient for a job/step to resume when re-executed after a failure or stop. For a stateful `ItemReader`, this might be the next item index, file line number, data page, offset, or a reader-managed token. Not every step has an “Nth line” restart point: a tasklet might use a completion flag, a reader might use the last processed record key, and a multi-step job can skip already completed steps.

Consider a chunk-oriented step with 100 records per chunk:

```text
Input: 1 ------------------------------------------------------ 1000
       |       |       |       |       |        |
       v       v       v       v       v        v
      100     200     300     400     500      600
       C       C       C       C       C        X

C = chunk commit succeeded, checkpoint state persisted
X = error while processing the next chunk

Reader may have speculatively read up to record 570.
The latest durable checkpoint may still be the position after record 500.
Restart must rely on the saved checkpoint, not the number 570 in read logs.
```

When restarting the same `JobInstance`, the reader is initialized with the saved `ExecutionContext` and restores its state from there. Depending on the implementation, the reader may re-read items from the uncommitted chunk; that fits **at-least-once semantics at uncommitted boundaries** and requires writers/side effects to be safe under retries.

**Restart point logging is not a checkpoint storage mechanism.** Logs are observational evidence, whereas Spring Batch recovers from metadata/state written by the framework and `ItemStream` into `JobRepository`. Deleting logs does not lose checkpoints; deleting `ExecutionContext` in the repository can destroy restartability even if logs remain.

## 2. Distinguishing Read Progress, Write Progress, and Checkpoints

Three concepts often confused:

| Concept | Information Source | Sufficient to Determine Restart Point? |
| --- | --- | --- |
| **Read progress** | `StepExecution.getReadCount()`, logs in `ItemReader.read()` | No. Read counts can include uncommitted work, and data order may vary |
| **Write progress** | `getWriteCount()`, writer logs, target record counts | Not necessarily. Counters do not reveal reader cursors, and non-transactional targets may receive data before an error |
| **Persisted checkpoint** | `ExecutionContext` updated by `ItemStream.update()` and saved by `JobRepository` | Primary recovery basis for restartable streams, paired with job/step status metadata |

For example, `Processed record id=INV-570` may have been logged before the transaction rolled back. Treating record 570 as the **restart point** could cause operators to skip uncommitted records 501–570. Conversely, logging `checkpoint committed: nextIndex=500` after the chunk transaction succeeds aligns closely with recoverable state.

Even a “checkpoint committed” message must be interpreted alongside the application's transaction setup. If business data is written to a target outside `JobRepository`'s transaction (an API, object storage, broker, or separate database without coordination), checkpoints and side effects may not commit atomically.

## 3. What Metadata Relates to Restarts?

`JobRepository` uses the following entities:

```text
Job(name = importOrdersJob)
  |
  v
JobInstance (job name + identifying JobParameters)
  |
  +-- JobExecution #101 (FAILED)
  |     |
  |     +-- StepExecution #501: importOrdersStep FAILED
  |           |
  |           +-- StepExecutionContext: checkpoint at last committed chunk
  |
  +-- JobExecution #102 (COMPLETED after restart)
        |
        +-- StepExecution #502: importOrdersStep COMPLETED
```

### `JobInstance` and Identifying Parameters

`JobInstance` identity rests on the job name and `JobParameters` with `identifying=true`. For example, `businessDate=2026-11-16` is an identifying parameter for a business period. A **true restart** creates a new `JobExecution` for the **same JobInstance**; adding a fresh `UUID` to identifying parameters on each run causes Spring Batch to create a brand-new instance and process everything from the beginning.

### `StepExecution` and Status

Each step execution has its own `StepExecution` holding `getStatus()`, `getExitStatus()`, timestamps, `readCount`, `writeCount`, `commitCount`, `rollbackCount`, and skip counts. These help investigate runs, yet do not replace reader checkpoints. Already `COMPLETED` steps are normally skipped during a restart unless explicitly configured otherwise, such as with `allowStartIfComplete(true)`.

### `ExecutionContext`

`StepExecution.getExecutionContext()` holds step state key/value pairs. An `ItemStreamReader` can store its read position under its own key. With a JDBC `JobRepository`, the framework persists snapshots into `BATCH_STEP_EXECUTION_CONTEXT`. `JobExecutionContext` also exists for job-scoped state; do not arbitrarily move step checkpoints into the job context.

**There is no universal `restartPoint` key across all readers.** Keys depend on the implementation, configured reader name, and checkpoint strategy. For some built-in readers, internal keys relate to items read. For custom readers, developers define the keys. Never try to read an assumed internal key name across all reader types.

## 4. Checkpoint Persistence Lifecycle Within a Chunk

For a chunk-oriented step with a Spring Batch-managed `ItemStream`, the conceptual flow is:

```text
Step starts / restarts
    |
    +-- ItemStream.open(saved ExecutionContext)
    |      restore offset/position
    v
Begin chunk transaction
    |
    +-- Reader.read() multiple times
    +-- Processor.process()
    +-- Writer.write(chunk)
    +-- ItemStream.update(ExecutionContext)
    +-- Spring Batch updates metadata/context via JobRepository
    |
    +-- COMMIT transaction
    |      |
    |      +-- ChunkListener.afterChunk()
    |             log observed point after commit
    |
    +-- On error: ROLLBACK and afterChunkError()
    v
Next chunk / step ends
    |
    +-- ItemStream.close()
```

This diagram shows the general idea; exact callbacks and transaction details vary by reader, writer, transaction manager, step type, and Spring Batch version. Most importantly, distinguish **state prepared before commit** from **state successfully committed**.

### Why Not Log “Committed” Inside `ItemStream.update()`?

`update(ExecutionContext)` is typically called to put the new checkpoint value into context **before the chunk transaction commits**. If the transaction later rolls back, that new value was only an in-memory candidate checkpoint and may not be persisted as a durable restart point. Logs inside `update()` should therefore use labels like `checkpoint_candidate`, avoiding `checkpoint_committed`.

`ChunkListener.afterChunk(ChunkContext)` is a much better spot to log after a chunk completes successfully. Still, logging itself can fail or drop on process crashes, so never treat logs as absolute truth. Whenever determining the exact restart point is critical, reconcile the repository against target data and external sources.

### Why Not Log “Restart Point” Inside `ItemReadListener.afterRead()`?

`afterRead()` runs as soon as the reader returns an item, before processing, writing, and committing. If a job reads 500 items and the writer fails, logging the last read item does not prove 500 items were committed. Read-event logs help diagnose bad items, not durable checkpoints.

## 5. What Should a Restart Point Log Model Include?

A structured record should carry these fields:

| Field | Role | Example |
| --- | --- | --- |
| `event` | Distinguish event type | `batch.checkpoint.committed` |
| `jobName` | Job name | `importOrdersJob` |
| `jobInstanceId` | Ties executions of one logical run | `930` |
| `jobExecutionId` | Specific run attempt | `1482` |
| `stepName` | Processing step | `importOrdersStep` |
| `stepExecutionId` | Step execution attempt | `3419` |
| `businessDate`/`inputVersion` | Scope of processed data | `2026-11-16`, `v17` |
| `readerName` | Distinguish multiple readers/states in one step | `ordersReader` |
| `checkpointKey` | Application/reader key name | `orders.reader.nextIndex` |
| `checkpointValue` | Observed value at log time | `500` |
| `readCount`, `writeCount`, `filterCount`, `skipCount` | Cumulative step progress | `500`, `498`, `2`, `0` |
| `commitCount`, `rollbackCount` | Transaction diagnostics | `5`, `0` |
| `status`, `exitCode` | Status when step/job finishes | `FAILED`, `FAILED` |
| `timestamp` and `traceId` | Correlate logs across components | `2026-11-17T02:05:00Z` |

Generally emit **events at key milestones** rather than dumping the entire `ExecutionContext` after every item. Per-item logging in large batches spikes I/O and buries useful signal; `ExecutionContext` can also hold sensitive data, long state strings, or objects awkward to serialize.

**Illustrative** JSON log record:

```json
{
  "timestamp": "2026-11-17T02:05:00Z",
  "level": "INFO",
  "event": "batch.checkpoint.committed",
  "jobName": "importOrdersJob",
  "jobInstanceId": 930,
  "jobExecutionId": 1482,
  "stepName": "importOrdersStep",
  "stepExecutionId": 3419,
  "businessDate": "2026-11-16",
  "readerName": "ordersReader",
  "checkpointKey": "orders.reader.nextIndex",
  "checkpointValue": 500,
  "readCount": 500,
  "writeCount": 498,
  "filterCount": 2,
  "commitCount": 5
}
```

For ID-based readers, replace index `500` with a key such as `lastCommittedOrderId` if that is the reader's actual checkpoint. Ensure the reader's query/ordering lets it resume safely from that key. Never manually write the last logged business ID into `ExecutionContext` if it does not match committed transaction state.

## 6. Example: Custom Reader Saving Checkpoints to `ExecutionContext`

To see the checkpoint mechanism clearly, consider a simple reader reading sequentially from a fixed list. This is a teaching example for **Spring Batch 5.x**, suitable for small fixtures. In production, file/database readers should use built-in restartable implementations and verify source stability.

```java
package com.example.batch;

import java.util.List;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.ItemStreamReader;

public final class RestartableOrderReader
        implements ItemStreamReader<String> {

    // Key owned by this reader: identifies the next item to read.
    public static final String NEXT_INDEX_KEY = "orders.reader.nextIndex";

    private final List<String> orders;
    private int nextIndex;

    public RestartableOrderReader(List<String> orders) {
        this.orders = List.copyOf(orders);
    }

    @Override
    public void open(ExecutionContext executionContext) {
        nextIndex = executionContext.containsKey(NEXT_INDEX_KEY)
            ? executionContext.getInt(NEXT_INDEX_KEY)
            : 0;
    }

    @Override
    public String read() {
        if (nextIndex >= orders.size()) {
            return null;
        }
        return orders.get(nextIndex++);
    }

    @Override
    public void update(ExecutionContext executionContext) {
        // Framework persists this state to the repository at checkpoint.
        executionContext.putInt(NEXT_INDEX_KEY, nextIndex);
    }

    @Override
    public void close() {
        // No file/socket to close in this in-memory example.
    }
}
```

On the first run, `open()` receives an empty context and starts at `nextIndex=0`. After writing the first chunk (say, two items), `update()` puts `nextIndex=2` into the context and the framework persists it at the checkpoint. If the second chunk fails before commit, the repository still retains the committed offset `2`. On restart of the same job instance, a **fresh reader instance** reopens the context and reads starting from the third element.

```text
Input          : [A001, A002, A003, A004, A005]
Chunk size     : 2

Chunk #1       : A001, A002  -> commit succeeded
Checkpoint     : orders.reader.nextIndex = 2

Chunk #2       : A003, A004  -> writer fails and rolls back
Persisted state: orders.reader.nextIndex = 2

Restart        : read() resumes from A003
```

This is a minimal `ItemStreamReader` example; it does not handle concurrency, transaction-aware buffering, or mutating inputs. If the `List` is ordered differently on rerun, `nextIndex=2` points to different data. Offset-based readers therefore require immutable inputs across related executions, or a more stable positioning strategy.

### Registering the Reader in the Step

```java
@Bean
@StepScope
RestartableOrderReader ordersReader() {
    return new RestartableOrderReader(
        List.of("A001", "A002", "A003", "A004", "A005")
    );
}

@Bean
Step importOrdersStep(JobRepository repository,
                      PlatformTransactionManager transactionManager,
                      RestartableOrderReader ordersReader,
                      ItemWriter<String> ordersWriter,
                      RestartPointLoggingListener loggingListener) {
    return new StepBuilder("importOrdersStep", repository)
        .<String, String>chunk(2, transactionManager)
        .reader(ordersReader)
        .writer(ordersWriter)
        .listener((StepExecutionListener) loggingListener)
        .listener((ChunkListener) loggingListener)
        .build();
}
```

This snippet shows an illustrative configuration fragment; `ordersWriter`, `JobRepository`, transaction manager, and imports are provided by the application. `@StepScope` creates a reader instance per step execution, preventing stale cursors on singletons across runs. When a reader is registered directly via `.reader(...)` and implements `ItemStream`, the step manages `open/update/close`; when wrapped inside a delegate hidden from the framework, register the stream explicitly via `.stream(...)` so checkpoints work.

For built-in readers like `FlatFileItemReader` or `JdbcPagingItemReader`, configure a unique name and `saveState(true)` when restart is desired; consult implementation docs to see how offsets are stored. Never use `saveState(false)` if you expect the reader to resume after failures.

## 7. Logging After Commit with `ChunkListener`

A listener can log events when a step starts, after each successful chunk, when a chunk fails, and when the step ends. The Spring Batch 5.x example below reads the checkpoint key defined by the reader above; if absent, it logs `unknown` instead of inventing a fake position.

```java
package com.example.batch;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;
import org.springframework.batch.core.ChunkListener;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.batch.item.ExecutionContext;

public final class RestartPointLoggingListener
        implements StepExecutionListener, ChunkListener {

    private static final Logger log =
        LoggerFactory.getLogger(RestartPointLoggingListener.class);

    private static final String CURSOR_KEY =
        RestartableOrderReader.NEXT_INDEX_KEY;

    @Override
    public void beforeStep(StepExecution stepExecution) {
        log.info(
            "event=batch.step.started jobExecutionId={} stepExecutionId={} "
                + "step={} restoredCursor={} businessDate={}",
            stepExecution.getJobExecutionId(),
            stepExecution.getId(),
            stepExecution.getStepName(),
            safeCursor(stepExecution.getExecutionContext()),
            stepExecution.getJobParameters().getString("businessDate")
        );
    }

    @Override
    public void afterChunk(ChunkContext context) {
        StepExecution step = context.getStepContext().getStepExecution();

        log.info(
            "event=batch.checkpoint.committed jobExecutionId={} "
                + "stepExecutionId={} step={} cursor={} read={} write={} "
                + "filter={} commits={} rollbacks={}",
            step.getJobExecutionId(),
            step.getId(),
            step.getStepName(),
            safeCursor(step.getExecutionContext()),
            step.getReadCount(),
            step.getWriteCount(),
            step.getFilterCount(),
            step.getCommitCount(),
            step.getRollbackCount()
        );
    }

    @Override
    public void afterChunkError(ChunkContext context) {
        StepExecution step = context.getStepContext().getStepExecution();
        log.warn(
            "event=batch.chunk.rolled_back jobExecutionId={} "
                + "stepExecutionId={} step={} read={} rollbacks={} "
                + "message=Checkpoint in memory may not be committed",
            step.getJobExecutionId(),
            step.getId(),
            step.getStepName(),
            step.getReadCount(),
            step.getRollbackCount()
        );
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        log.info(
            "event=batch.step.finished jobExecutionId={} stepExecutionId={} "
                + "step={} status={} exitCode={} read={} write={} "
                + "commits={} rollbacks={}",
            stepExecution.getJobExecutionId(),
            stepExecution.getId(),
            stepExecution.getStepName(),
            stepExecution.getStatus(),
            stepExecution.getExitStatus().getExitCode(),
            stepExecution.getReadCount(),
            stepExecution.getWriteCount(),
            stepExecution.getCommitCount(),
            stepExecution.getRollbackCount()
        );
        return null; // Preserve the exit status decided by the step.
    }

    private static String safeCursor(ExecutionContext context) {
        return context.containsKey(CURSOR_KEY)
            ? String.valueOf(context.getInt(CURSOR_KEY))
            : "unknown";
    }
}
```

`afterChunk(...)` runs after a chunk completes successfully in standard chunk processing, making it a solid milestone to report *a commit boundary completed*. `afterChunkError(...)` signals a chunk error; **never** read the in-memory `ExecutionContext` in that callback and claim it is a persisted checkpoint. On failure, determine the durable restart point from metadata restored on the next run or from the repository after transaction rollback finishes.

In this example, `safeCursor(...)` reads only the application key `orders.reader.nextIndex`. If swapped for `FlatFileItemReader`, key names and state semantics differ. Ideally, build a logging helper tailored to your project's reader/step with a clearly defined `cursor` meaning instead of relying on internal keys not guaranteed stable across versions.

### Logging Configuration and Log Levels

`INFO` fits step start/finish milestones or checkpoints throttled cleanly for operations. When chunks are tiny and jobs process millions of items, one log line per chunk floods logs. Log every chunk at `DEBUG` and emit `INFO` at coarser chunk counts or time intervals, **while ensuring final state remains verifiable in `JobRepository`**.

Basic configuration example in `application.yml`:

```yaml
logging:
  level:
    com.example.batch.RestartPointLoggingListener: INFO
    org.springframework.batch: INFO
```

When using JSON structured logging (Logback encoders/observability stacks), emit `event`, `jobExecutionId`, `stepExecutionId`, `businessDate`, and `checkpoint` as separate fields for easy filtering. The SLF4J snippet above uses `key=value` pairs inside the message for readability without requiring a specific encoder.

## 8. Logging Recovery When a Step Restarts

A crucial part of restart logging is a comparable event pair:

```text
Execution 1482: batch.checkpoint.committed cursor=500
Execution 1482: batch.step.finished status=FAILED

Execution 1483: batch.step.started restoredCursor=500
Execution 1483: batch.checkpoint.committed cursor=600
Execution 1483: batch.step.finished status=COMPLETED
```

Given the same `JobInstance` and identifying parameters, this sequence shows the second execution started with the restored checkpoint. Still, `beforeStep` logs only prove the context value was loaded into the step; verify that the reader actually applied `open(...)` properly, output data is right, and no side effects duplicated.

Distinguish three IDs:

- `jobInstanceId`: logical work identifier, usually unchanged across restarts.
- `jobExecutionId`: each run/restart gets a new ID.
- `stepExecutionId`: each step execution gets a new ID; already completed steps skipped on restart may not create a new execution.

Emit an operational event `batch.restart.requested` containing the original execution, `requestedBy`, `reasonCode`, and business key, followed by the new execution's `batch.step.started` log. Spring Batch does not automatically log “who clicked restart” or business justification in a custom audit schema; the application/scheduler must supply that context.

### Do Not Confuse a Restart with a Fresh Start

Suppose `businessDate=2026-11-16` is an identifying parameter:

```java
JobParameters sameInstance = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16")
    .toJobParameters();
```

When the prior job ended `FAILED`/`STOPPED` and configuration allows restart, Spring Batch resumes that instance with its saved metadata. Yet if launch code always does this:

```java
JobParameters newInstance = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16")
    .addString("runId", UUID.randomUUID().toString())
    .toJobParameters();
```

an identifying `runId` creates a brand-new instance. Unless that is desired, design identifying parameters around the data period and restart policy. In Spring Batch 5.x, `JobOperator.restart(failedExecutionId)` is one way to request restarting an execution by metadata; configure `JobOperator`/registry properly and handle non-restartable cases. Never inject random parameters to “force a rerun” and call it a restart.

## 9. Reading Restart State with `JobExplorer`

Logs can rotate out or be lost on process crashes. To look up an existing execution, `JobExplorer` provides a metadata read API that operations dashboards can cross-check.

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;

public final class BatchExecutionInspectionService {
    private final JobExplorer jobExplorer;

    public BatchExecutionInspectionService(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public void inspect(long jobExecutionId) {
        JobExecution execution = jobExplorer.getJobExecution(jobExecutionId);
        if (execution == null) {
            throw new IllegalArgumentException(
                "Unknown jobExecutionId: " + jobExecutionId);
        }

        for (StepExecution step : execution.getStepExecutions()) {
            System.out.printf(
                "step=%s, id=%d, status=%s, read=%d, write=%d%n",
                step.getStepName(),
                step.getId(),
                step.getStatus(),
                step.getReadCount(),
                step.getWriteCount()
            );
            // Selectively read context keys defined by the application itself.
        }
    }
}
```

This example uses Spring Batch 5.x imports; in Spring Batch 6.x, core packages may change. `JobExplorer` is intended for read operations. Never manually edit `BATCH_STEP_EXECUTION_CONTEXT` or `BATCH_JOB_EXECUTION.STATUS` via SQL to move a restart point: doing so breaks metadata consistency and can cause data loss or unintended re-reads.

### Read-Only SQL for Execution Reconciliation

With the standard JDBC schema in Spring Batch 5.x, inspect step-level metadata:

```sql
SELECT
    je.JOB_EXECUTION_ID,
    ji.JOB_INSTANCE_ID,
    ji.JOB_NAME,
    je.STATUS AS job_status,
    se.STEP_EXECUTION_ID,
    se.STEP_NAME,
    se.STATUS AS step_status,
    se.READ_COUNT,
    se.WRITE_COUNT,
    se.COMMIT_COUNT,
    se.ROLLBACK_COUNT,
    se.START_TIME,
    se.END_TIME
FROM BATCH_JOB_EXECUTION je
JOIN BATCH_JOB_INSTANCE ji
  ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
LEFT JOIN BATCH_STEP_EXECUTION se
  ON se.JOB_EXECUTION_ID = je.JOB_EXECUTION_ID
WHERE je.JOB_EXECUTION_ID = :execution_id;
```

`BATCH_STEP_EXECUTION_CONTEXT` and `BATCH_JOB_EXECUTION_CONTEXT` store serialized context snapshots managed by the framework's serializer. Do not assume a single universal JSON `SELECT` works across every database and version. Use Batch APIs or the matching serializer to inspect them, and expose only approved keys.

## 10. Special Cases Requiring Attention

### 10.1. Non-Stateful Readers

Some readers are not `ItemStream`s, or are configured with `saveState(false)`. `readCount` and `writeCount` still appear in step metadata, yet **that does not mean the reader will restore its position**. For restartable jobs, use readers honoring `open/update/close` or design idempotent reprocessing from the source.

### 10.2. Input File Changes Between Runs

For file offsets, `nextIndex=500` makes sense only if the file and parsing logic stay unchanged. Swapping the source file at the same path can cause restarts to skip or corrupt records. Include `inputFileId`, object version, or checksum in the execution trail, and keep the source snapshot immutable until the processing period finishes.

### 10.3. Database Paging/Cursor Readers and Ordering

SQL paging/cursor readers require deterministic ordering for reliable restarts. If a query lacks a deterministic `ORDER BY` or source rows mutate heavily, a saved offset or row count can point to different rows. With `JdbcPagingItemReader`, configure a unique, suitable sort key and understand the implementation's restart semantics; never assume read row count equals the last primary key.

### 10.4. Writers or External APIs Without Rollback Support

If a step calls an external API or writes a file outside the metadata transaction, rolling back the database does not undo external side effects. Restart point logs must be paired with idempotency keys, transactional outboxes, or target-system confirmation trails. Never claim “no items after the checkpoint were ever processed” when non-transactional side effects exist.

### 10.5. Multi-Threaded Steps and Partitioning

When a step uses multiple threads or partitioning, there is not always a single linear offset. Checkpoints may require **partition key + stepExecutionId + cursor**. Listeners can execute on different threads, counters mutate concurrently, and asynchronous log backends do not guarantee strict ordering. `MDC` (Mapped Diagnostic Context) also does not propagate automatically across threads; explicit context propagation is required.

Sample partition log:

```text
event=batch.checkpoint.committed
jobExecutionId=1482
stepExecutionId=3420
partition=region-HCM
cursor=orderId:45000
```

Logging `cursor=45000` without partition/step identity leaves operators unable to tell which slice owns that cursor. With remote chunking, workers and managers also need a shared correlation ID or chunk/partition ID to stitch logs together.

### 10.6. Tasklet Steps Without Chunked Items

A tasklet may perform a monolithic action, flip a flag, or run a custom business operation. `readCount`/`writeCount` can be 0 even when work finished. For restartable tasklets, log milestones such as `stage=UPLOAD_DONE`, `lastPageToken`, or a durably stored transaction code. State storage must match the tasklet's transaction and idempotency strategy rather than blindly forcing file line offsets.

### 10.7. Steps Already Completed Before Job Failure

Consider a job `extractStep -> transformStep -> publishStep`. If `publishStep` fails after the first two steps are `COMPLETED`, a restart can skip the completed steps and re-execute only the failing one. Here the restart point is both the **set of completed steps** and the context of the resuming step. Logs should show job flow and skipped-on-restart steps rather than assuming every step reopens an offset.

### 10.8. Failure Before the First Checkpoint

If a job dies before the first commit, the context may contain only initial state or lack the key altogether. Logs should show `restoredCursor=unknown` or the reader's defined initial state. Never assume it is safe to start from item 1 if external side effects occurred before transaction rollback.

## 11. Restart Point Logging and Security

`ExecutionContext` and `JobParameters` may hold filenames, access tokens, customer data, or intermediate values. Logging the entire context via `context.toString()` or serializing every key is a major security risk.

Prefer:

- **Technical identifiers:** `jobExecutionId`, `stepExecutionId`, `jobName`, `businessDate`, `partitionId`, and reader name.
- **Non-sensitive checkpoints:** index, offset, or reference-tokenized record ID if permitted.
- **Error codes and categories:** `READ_TIMEOUT`, `INVALID_FORMAT`, `CONSTRAINT_VIOLATION`; avoid raw payloads.
- **Trace/correlation IDs:** connect logs to schedulers and workers without copying input data.
- **Sampling/throttling:** reduce log volume for tiny chunks while preserving start, error, and finish events.

If record keys hold sensitive info, use internal reference tokens or policy-compliant hashes/tokens. For audit requirements, ship logs to a centralized store with dedicated retention and access controls; never treat `INFO` logs as an immutable system of record.

## 12. Test Scenario for Restart Logging

A strong integration test should induce a **real failure after at least one commit**, then restart the same `JobInstance` and verify both data and checkpoints. Use a test database and deterministic fixtures—never run tests against production metadata.

### Scenario Layout

Suppose there are five orders and chunk size 2:

| Phase | Action | Expected Outcome |
| --- | --- | --- |
| First execution | Chunk #1 writes A001, A002 successfully | Output has 2 codes; checkpoint `nextIndex=2` |
| First execution | Chunk #2 tries A003, A004 but writer throws before commit | Execution `FAILED`; chunk #2 transaction rolls back; persisted checkpoint remains `2` |
| Restart | Same identifying `JobParameters`; new reader opens saved context | Logs show `restoredCursor=2`; reader resumes from A003 |
| Restart | Writer succeeds and finishes A003, A004, A005 | New execution `COMPLETED`; output has 5 unique codes |
| Reconciliation | Inspect `JobRepository`, output, and logs | Same `JobInstance`, two `JobExecution`s; checkpoint logs match committed data |

The mock writer should fail **deterministically once** and flip state for the restart. For SQL writers, use a transaction manager bound to the same datasource, unique keys, or idempotent upserts; if calling external APIs outside transactions, add assertions checking for duplicate side effects.

### Example State Assertions

The snippet below illustrates assertions after a failed run and restart (Spring Batch 5.x). `first`, `restarted`, and `jdbcTemplate` are prepared by the test:

```java
assertThat(first.getStatus()).isEqualTo(BatchStatus.FAILED);
assertThat(restarted.getStatus()).isEqualTo(BatchStatus.COMPLETED);

assertThat(restarted.getJobInstance().getId())
    .isEqualTo(first.getJobInstance().getId());

assertThat(restarted.getId()).isNotEqualTo(first.getId());

List<String> result = jdbcTemplate.queryForList(
    "SELECT order_code FROM imported_orders ORDER BY order_code",
    String.class
);
assertThat(result).containsExactly("A001", "A002", "A003", "A004", "A005");
```

To verify logs, use a capture appender or `OutputCaptureExtension` in Spring Boot Test. Assert `batch.checkpoint.committed` after the first chunk, `batch.step.finished status=FAILED` after the failed run, and `batch.step.started restoredCursor=2` after restart. However, **test success must rely on output data and metadata**, not solely log string matching, because logs themselves can be miswritten or lost on abrupt termination.

### Edge Cases Worth Testing

1. Failure before the first checkpoint: `ExecutionContext` has no committed offset.
2. Failure after one or more committed chunks: restart resumes from the last valid milestone.
3. Failure right at chunk boundary or inside `ItemStream.update()`: rollback produces no bogus checkpoint.
4. `STOPPED` instead of `FAILED`: verify restart policy and status logs.
5. Reader with `saveState(false)`: do not expect resumption from old offsets.
6. Mutated or replaced input: verify version/checksum detection before restarting.
7. Multiple partitions: logs and checkpoints are isolated per partition/step execution.

## 13. Common Logging and Restart Point Pitfalls

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Log shows `readCount=570`, restarts at item 501 | 70 items read in a rolled-back chunk; read count is not persisted checkpoint | Log after commit and inspect saved context |
| Logged “checkpoint committed” right after `read()` | Callback fires before writer/commit | Rename to read progress; log committed in `afterChunk` |
| `restoredCursor=unknown` despite expected restart | Reader did not save state, wrong key, `ItemStream` not registered, or new instance | Check `saveState`, reader name, stream registration, and identifying params |
| Restart re-reads entire input | New identifying UUID per launch or context not persisted | Keep the same `JobInstance` for restarts; verify repository/context |
| Reader skips records after restart | Offset saved inaccurately or source input mutated | Verify `open/update`, transactions, input versioning, sort/order |
| Writer creates duplicates despite exact offset restart | Non-transactional side effect or non-idempotent writer | Design unique keys, outboxes, deduplication, and reconciliation |
| One cursor number logged across multiple partitions | Missing partition ID/`stepExecutionId` | Log checkpoints per partition |
| Execution failed with no finish log | JVM/Pod died before final listener, or log buffer not flushed | Cross-check JobRepository and liveness/monitoring |
| Excessive logs slow down batch | Logging tiny chunks/items at INFO | Lower frequency; use metrics for continuous stats |
| Data lost after manually “fixing” context | Direct edits to `BATCH_*` or checkpoint state | Use restart APIs and controlled recovery runbooks |
| Secrets leaked into logs | Printing full `ExecutionContext` or sensitive parameters | Allowlist loggable fields and redact |

## 14. Operational Runbook When a Job Fails

When a job ends `FAILED` or stops abnormally, follow this investigation sequence:

1. **Locate the execution:** identify `jobName`, `jobExecutionId`, business key, and input source ID.
2. **Identify the failing step:** inspect `StepExecution` along with `BatchStatus`, `ExitStatus`, timestamps, exceptions, and skip/rollback counts.
3. **Read the durable checkpoint:** cross-check step execution state in `JobRepository`, `ExecutionContext` keys owned by the reader, and the latest commit log.
4. **Verify committed output:** check what effects successful chunks had on target databases/files/APIs, and whether any side effects went untracked in the repository.
5. **Choose a recovery strategy:** restart the same instance, run a controlled full reprocess, or reconcile manually. Never alter identifying parameters just to bypass a start error.
6. **Observe the next execution:** verify `restoredCursor`, new execution ID, counters, and output data; confirm zero missing or duplicate records.

For critical systems, maintain a dashboard linking old and new `JobExecution`s by `JobInstance`, showing latest commits, business keys, and output health. When logs and repository disagree after a crash, prioritize persisted metadata plus target-system commit evidence; logs may be lost or emitted before a transaction finished.

## 15. Conclusion

`Restart point logging` is the practice of observing Spring Batch's recovery state. **Readers/steps save state into `ExecutionContext`, `JobRepository` persists checkpoints, and logs help operators understand that state and reconcile committed data.** A solid design clearly records job/step execution identity, data period, per-reader checkpoints, counters, and failure status; emits checkpoint events after commit; protects sensitive data; and verifies restarts via integration tests with real failures.

The core principle is **never treat the last read item number or an arbitrary log line as the “source of truth” for resume position**. Restart points must align with durable metadata, transactions, and the idempotency strategy of the entire pipeline.

## References

- [Spring Batch Reference — Configuring a Step](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): chunk lifecycle and transaction commits.
- [Spring Batch Reference — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): `open`, `update`, `close` contract and checkpointing via `ExecutionContext`.
- [Spring Batch Reference — Configuring a Job](https://docs.spring.io/spring-batch/reference/job/configuring.html): `JobInstance`, `JobExecution`, restarts, and job configuration.
- [Spring Batch Reference — Meta-Data Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): `JobRepository` metadata tables, especially step execution context.
- [Spring Batch Reference — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html): monitoring batch executions and metrics.
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): testing jobs/steps, failures, and restarts.
