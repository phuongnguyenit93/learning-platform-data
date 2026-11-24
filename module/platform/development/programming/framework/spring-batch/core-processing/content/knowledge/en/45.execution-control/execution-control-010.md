# Graceful Stop at Checkpoint in Spring Batch

## 1. The Problem: Safely Stopping a Job While Processing Data

In Spring Batch operations, a job may process millions of records over minutes or hours. Operators sometimes have to stop a job because a maintenance window is starting, the data source has an issue, a downstream service is overloaded, or processing needs to shift to another instance. If the process is terminated abruptly, uncommitted output, reader positions, and restart metadata can fall out of sync.

**Graceful stop at checkpoint** is the practice of asking Spring Batch to finish in a controlled manner so already-committed units of work are preserved, recovery state is saved, and the job transitions to **STOPPED** once it genuinely halts. When restartable, the job resumes from the saved state instead of starting over from the beginning.

A simple flow:

~~~text
Input records
     |
     v
Chunk 1: read -> process -> write -> COMMIT + CHECKPOINT
     |
     v
Chunk 2: read -> process -> write -> COMMIT + CHECKPOINT
     |
     |    <-- STOP request received
     v
In-flight chunk completes or rolls back depending on failure condition
     |
     v
Spring Batch detects the stop request
     |
     v
JobExecution: STOPPING -> STOPPED
     |
     v
Restart same JobInstance from valid checkpoint
~~~

The word **graceful** here describes the job cooperating with the framework's stop mechanism. It does not mean every thread interrupts instantaneously when the request is sent, or that writes already sent to external systems automatically roll back.

### Why Is the Checkpoint Such an Important Boundary?

In chunk-oriented processing, a **chunk** consists of a group of items read, processed, and written within an appropriate transaction scope. Once the chunk commits successfully, Spring Batch persists the state needed for recovery—typically the read position in the Step's **ExecutionContext**.

With chunk size = 100:

- The first chunk can write and commit records 1–100.
- The next chunk processes 101–200.
- When a stop arrives while the second chunk is running, the framework normally waits for the interruption checkpoint before ending the Step. The safe checkpoint boundary is the state recorded through commit.
- Upon restart, the reader can restore the saved state and continue with the remaining records.

Do not assume a stop command guarantees the exact number of processed records is a multiple of 100: the final chunk may be smaller, filtering/skipping/retrying may happen, a commit may roll back, or multi-threaded processing may be used. Committed output data is the true proof of results.

## 2. Distinguishing Graceful Stop, Fail, Shutdown, and Kill

| Termination Type | How It Is Triggered | Typical Status | Recoverability |
|---|---|---|---|
| Spring Batch graceful stop | `JobOperator.stop(executionId)` or a Step validly signaled to terminate | `STOPPING` then `STOPPED` | Restarts from checkpoint if Job/Step support it |
| Error inside Step | Unhandled exception or exceeded retry/skip limit | `FAILED` | Restartable if configuration permits |
| Job finishes successfully | Entire flow completes | `COMPLETED` | Does not normally restart the same completed JobInstance |
| Stop requested after current Step | Flow configuration or `JobOperator` stop, depending on setup | `STOPPED` upon clean stop | Resumes according to flow and Step state |
| Process kill, `SIGKILL`, host crash | Abrupt external termination outside framework control | Metadata may remain `STARTED`/`STARTING` | May require reconciling state and partial data before restart |

**`STOPPING` is a transitional state**, not proof that the job has fully stopped. An orchestrator must launch a replacement job or publish outputs under policy only after confirming the execution actually reached the proper terminal state.

**`COMPLETED` differs from `STOPPED`.** When `STOPPED`, part of the data may have committed, yet the full job output is incomplete. Consumers must not treat partial output as a completed batch.

## 3. Components Involved in Stopping

Key Spring Batch components:

| Component | Role in Graceful Stop |
|---|---|
| `JobOperator` | Job control interface receiving stop/restart requests |
| `JobRepository` | Persists JobInstance, JobExecution, StepExecution, and metadata |
| `JobExplorer` | Reads execution info to monitor status |
| `JobExecution` | State of one job run attempt; can transition `STARTED → STOPPING → STOPPED` |
| `StepExecution` | Status, counters, and ExecutionContext of a Step |
| `ExecutionContext` | State data saved to restore reader/writer/processor when needed |
| `ItemStream` | `open`, `update`, `close` contract for stateful components |
| `PlatformTransactionManager` | Manages chunk commit/rollback across transactional resources |
| `ChunkListener` | Hook before/after a chunk; useful when checking custom stop signals after commit |

A **JobInstance** is a logical unit of work identified by Job name and identifying JobParameters. A **JobExecution** is one execution attempt of a JobInstance. If the previous execution is `STOPPED` and the job is restartable, restarting normally creates a **new JobExecution under the same JobInstance**.

For stop/restart to work reliably between the control process and the batch process, both must access the **same JobRepository**. Reading a local copy or sending commands to a process backed by a different repository will not control the target job.

## 4. Sending a Stop Command via JobOperator

For a running job, the standard mechanism is sending the stop request by **`jobExecutionId`**, not merely `jobName` when multiple runs or concurrent jobs exist.

Example application service using Spring Batch:

~~~java
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.stereotype.Service;

@Service
public class BatchExecutionControlService {

    private final JobOperator jobOperator;

    public BatchExecutionControlService(JobOperator jobOperator) {
        this.jobOperator = jobOperator;
    }

    public boolean requestStop(long executionId) throws Exception {
        // Requests stop; returning true does not mean the job is already STOPPED.
        return jobOperator.stop(executionId);
    }

    public Long restartStoppedExecution(long stoppedExecutionId)
            throws Exception {
        return jobOperator.restart(stoppedExecutionId);
    }
}
~~~

Here exception signatures are simplified to focus on control flow; in applications handle specific Spring Batch exceptions such as **`NoSuchJobExecutionException`**, **`JobExecutionNotRunningException`**, **`JobRestartException`**, and other restart conditions.

Control flow example:

~~~text
POST /operations/batch-executions/831/stop

1. Verify executionId 831 belongs to a controllable batch.
2. Call JobOperator.stop(831).
3. Record the stop request; return status "stop requested".
4. Monitor JobExplorer/JobRepository.
5. Report "stopped" only when actual status becomes STOPPED.
~~~

Do not return HTTP 200 meaning "already stopped" immediately after calling stop, because stop is cooperative. Admin endpoints require dedicated authentication and authorization to avoid stopping the wrong job.

### What Happens After Calling Stop?

Once accepted, the stop request is reflected in the execution state (typically **`STOPPING`**); the running job detects that flag at Spring Batch's interruption checkpoint, ends the Step via the stop mechanism, and finally persists status **`STOPPED`** if no other issue occurs.

Stop latency depends on:

- Whether the current chunk is large or small.
- Whether the reader, processor, or writer is waiting on I/O or external API calls.
- Whether transaction commit or rollback is slow.
- Whether a Tasklet runs a long loop without checking stop signals.
- Whether the job has multiple Steps, partitions, or remote workers to coordinate.

If a thread hangs indefinitely on a network call, `JobOperator` cannot guarantee an immediate stop; you need client-side timeouts and cooperative checks in code.

## 5. Designing a Step with a Recoverable Checkpoint

Example job reading a CSV file of orders and writing to a database. Each record has an ID and an amount; the job receives **`inputFile`** and **`batchId`** as identifying JobParameters.

Data file:

~~~csv
orderId,amount
O001,100.00
O002,45.50
O003,80.00
O004,25.00
O005,10.00
~~~

Target table:

~~~sql
CREATE TABLE imported_order (
    batch_id VARCHAR(64) NOT NULL,
    order_id VARCHAR(64) NOT NULL,
    amount DECIMAL(18, 2) NOT NULL,
    PRIMARY KEY (batch_id, order_id)
);
~~~

The key `(batch_id, order_id)` helps detect or block duplicates within a batch. However, a **unique constraint alone does not make a writer idempotent**: if an already-written record is replayed, a plain INSERT can still fail. You need upsert rules or idempotency checks wherever infrastructure might repeat operations.

### 5.1. A Reader That Persists Its Read Position

Example using Spring Batch builder style supporting JobRepository and a transaction manager:

~~~java
import java.math.BigDecimal;

public record OrderRow(String orderId, BigDecimal amount) {
}
~~~

~~~java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
public FlatFileItemReader<OrderRow> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderRow>()
            .name("checkpointableOrderReader")
            .resource(new FileSystemResource(inputFile))
            .linesToSkip(1)
            .delimited()
            .names("orderId", "amount")
            .fieldSetMapper(fields -> new OrderRow(
                    fields.readString("orderId"),
                    fields.readBigDecimal("amount")))
            .saveState(true)
            .build();
}
~~~

**`saveState(true)`** enables the reader to save its state into the Step ExecutionContext at chunk checkpoints. The reader name must stay stable so state keys match on restart. **`@StepScope`** creates an instance bound to the StepExecution and injects job parameters at the right time.

If state saving is disabled or a custom reader does not implement **`ItemStream`**, restarts may read from the start or fail to restore exact position. When a delegate reader is hidden inside a composite, ensure the stream is registered with the Step so `open`/`update`/`close` callbacks execute.

### 5.2. A Writer Participating in the Step Transaction

~~~java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.ItemWriter;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@Bean
@StepScope
public ItemWriter<OrderRow> orderWriter(
        JdbcTemplate jdbcTemplate,
        @Value("#{jobParameters['batchId']}") String batchId) {

    return chunk -> {
        for (OrderRow order : chunk) {
            jdbcTemplate.update(
                    """
                    INSERT INTO imported_order (batch_id, order_id, amount)
                    VALUES (?, ?, ?)
                    """,
                    batchId,
                    order.orderId(),
                    order.amount());
        }
    };
}
~~~

When **`JdbcTemplate`** uses a datasource managed by the chunk's transaction manager, chunk writes commit or roll back together in the same transaction. This example uses INSERT so commit state is easy to observe; real systems need duplicate-handling policies for restarts and retries.

### 5.3. Step and Job

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        FlatFileItemReader<OrderRow> orderReader,
        ItemWriter<OrderRow> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderRow, OrderRow>chunk(100, transactionManager)
            .reader(orderReader)
            .writer(orderWriter)
            .build();
}

@Bean
public Job importOrdersJob(
        JobRepository jobRepository,
        Step importOrdersStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .start(importOrdersStep)
            .build();
}
~~~

With a sample file of only five items and chunk size 100, the job usually processes everything in one chunk and finishes; **it is hard to observe stopping across multiple checkpoints**. In checkpoint tests, use more items or a small chunk size such as 2 to produce multiple real commits.

### When Is the Checkpoint Actually Persisted?

A successful chunk follows these general steps:

1. Reader supplies items for the chunk.
2. Processor and writer process items per configuration.
3. ItemStream updates recoverable state into ExecutionContext.
4. Transaction commits, updating metadata per repository/transaction configuration.
5. Job proceeds to the next chunk or handles a stop signal.

The crux is **recovering from the latest persisted state**, not from a position held only in memory. If business resources and JobRepository use separate transactions, evaluate the risk of committing in one place while the checkpoint is not yet persisted in the other.

## 6. Intentionally Stopping After a Chunk Commit

When business rules call for "stop at the nearest checkpoint", you can check a stop flag after a chunk commits successfully. **`ChunkListener.afterChunk`** is a helpful hook because it runs after a chunk commits in standard chunk processing.

Suppose a shared service lets you look up a stop signal:

~~~java
public interface StopSignal {
    boolean isStopRequested(String batchId);
}
~~~

Listener:

~~~java
import org.springframework.batch.core.ChunkListener;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.stereotype.Component;

@Component
public class CheckpointStopListener implements ChunkListener {

    private final StopSignal stopSignal;

    public CheckpointStopListener(StopSignal stopSignal) {
        this.stopSignal = stopSignal;
    }

    @Override
    public void afterChunk(ChunkContext context) {
        Object rawBatchId = context.getStepContext()
                .getJobParameters().get("batchId");

        if (rawBatchId instanceof String batchId
                && stopSignal.isStopRequested(batchId)) {
            context.getStepContext()
                    .getStepExecution()
                    .setTerminateOnly();
        }
    }
}
~~~

Register the listener on the Step:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderRow, OrderRow>chunk(100, transactionManager)
        .reader(orderReader)
        .writer(orderWriter)
        .listener(checkpointStopListener)
        .build();
~~~

This snippet replaces Step creation in section 5.3. Calling **`setTerminateOnly()`** marks the StepExecution as needing termination; the framework checks it at the Step's interruption point. Use this mechanism when the application already has its own custom stop signal, while for external administrative requests **`JobOperator.stop(executionId)`** is generally the better control API.

Key caveats:

- Do not block indefinitely inside `afterChunk`, because the listener is part of the Step lifecycle.
- Tie the stop signal to the exact **`batchId`/`executionId`** so you do not stop a concurrent job by mistake.
- With **chunk size = 100**, the stop flag might be raised mid-chunk; the listener only sees it at the post-commit boundary.
- There is a brief window between interruption checks; do not promise stopping at an exact absolute record number if processing is complex.
- With multi-threaded Steps, partitioned Steps, or remote workers, "stopping every worker together at a global checkpoint" needs separate coordination. Each partition may have its own checkpoint.

**Never use `Thread.stop()`, `System.exit()`, `kill -9`, or abruptly close the datasource** as a graceful stop mechanism. Those can interrupt commits or bypass persisting restart state.

## 7. Tracking STOPPING to STOPPED

Calling stop is a control request; the monitoring system must read status afterward. Illustrative polling helper:

~~~java
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.explore.JobExplorer;

public BatchStatus currentStatus(
        JobExplorer jobExplorer,
        long executionId) {

    JobExecution execution = jobExplorer.getJobExecution(executionId);
    if (execution == null) {
        throw new IllegalArgumentException(
                "Unknown job execution: " + executionId);
    }
    return execution.getStatus();
}
~~~

A controller or scheduler can invoke this periodically with a bounded timeout and polling interval. Avoid tight loops hitting JobRepository thousands of times per second. Also handle cases where status transitions to `FAILED` due to another error while `STOPPING`.

| Observed Status | Interpretation |
|---|---|
| `STARTING` / `STARTED` | Job has not stopped yet; stop request may not have arrived or been processed yet |
| `STOPPING` | Stop requested/in progress; do not launch a replacement execution yet |
| `STOPPED` | Stopped cleanly; verify restart conditions before calling restart |
| `FAILED` | Job failed; investigate the failure before deciding to restart |
| `COMPLETED` | Job finished successfully; it may have completed before stop was processed |
| `UNKNOWN` / `ABANDONED` | Handle operationally per repository state; do not assume resumable |

**`ExitStatus`** and **`BatchStatus`** are separate concepts. A flow may use custom exit codes; when deciding whether a job is still running or restartable, rely on execution status and job policy rather than just a raw exit-code string.

### Is a Stop Request Always Accepted?

No. The `executionId` might not exist, the job may have already finished, or its current state may disallow stopping. Handle errors and re-check the repository instead of retrying stop endlessly. When multiple actors control the same execution, a race can happen: the job completes naturally just before the stop command applies.

## 8. Restarting from Checkpoint After STOPPED

To resume a stopped job, use Spring Batch's restart mechanism with the **same JobInstance**. With JobOperator:

~~~java
long stoppedExecutionId = 831L;
Long newExecutionId = jobOperator.restart(stoppedExecutionId);
~~~

Expected behavior:

~~~text
JobInstance(importOrdersJob, identifying parameters)
        |
        +-- JobExecution #831: STOPPED
        |       StepExecution importOrdersStep
        |       ExecutionContext: checkpointed reader position
        |
        +-- JobExecution #844: STARTED ... COMPLETED
                importOrdersStep restores saved position
                final output complete
~~~

Safe restart preconditions usually include:

1. The Job is configured as **restartable**, not blocked by restart policies.
2. JobRepository and ExecutionContext from the prior run remain intact.
3. Readers/writers and required stateful components support recovery.
4. Input content and ordering have not changed for readers relying on positional checkpoints.
5. Previously committed outputs remain consistent, and the writer avoids duplicate writes on replay.
6. Incomplete downstream Steps and flow routing are clearly defined.

**Do not create a new JobInstance by adding a random parameter and call that a restart.** A new JobInstance may read from the beginning because it does not inherit the old instance's checkpoint.

### Relationship with allowStartIfComplete and startLimit

In a multi-Step job, a Step already marked **`COMPLETED`** in a prior execution is normally skipped on restart, unless configured with **`allowStartIfComplete(true)`** to run again. **`startLimit`** bounds how many times a Step can start. If you have a validation or cleanup Step that must always re-run, design the flow and restart options per business requirements.

Do not arbitrarily rename Job structures or Step names between `STOPPED` and restart, because existing metadata is keyed by these names and changing them can make resumption unpredictable.

## 9. Stateful Readers/Writers and ExecutionContext

**ExecutionContext** is where Spring Batch persists serializable values needed for restarts. It is scoped to StepExecution and JobExecution. In chunk processing, components implementing **`ItemStream`** update state into the context via **`update(ExecutionContext)`** before checkpoints.

Example custom reader tracking an index:

~~~java
import java.util.List;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.ItemStreamReader;

public class IndexedOrderReader implements ItemStreamReader<OrderRow> {

    private static final String POSITION = "indexedOrderReader.position";

    private final List<OrderRow> items;
    private int index;

    public IndexedOrderReader(List<OrderRow> items) {
        this.items = items;
    }

    @Override
    public OrderRow read() {
        if (index >= items.size()) {
            return null;
        }
        return items.get(index++);
    }

    @Override
    public void open(ExecutionContext executionContext) {
        index = executionContext.containsKey(POSITION)
                ? executionContext.getInt(POSITION)
                : 0;
    }

    @Override
    public void update(ExecutionContext executionContext) {
        executionContext.putInt(POSITION, index);
    }

    @Override
    public void close() {
        // No external resources to release.
    }
}
~~~

This sample reader assumes an **immutable input List preserving exact order** across restarts; it is unsuitable as-is for mutating data sources or multi-threaded readers. In real applications, prefer built-in readers like `FlatFileItemReader`/`JdbcPagingItemReader` when appropriate and write custom streams only when needed.

Checkpoints do not automatically save internal state of arbitrary processors or custom caches. If logic keeps persistent state across chunks, that component needs its own save/restore strategy or must implement `ItemStream` and be properly registered on the Step.

### Reader Cursors and Changing Data Sources

For files, never modify the file being consumed by a JobInstance before restarting. For database paging, use stable sort keys, consistent query predicates, and snapshot/watermark strategies to avoid missing or duplicating items if rows are inserted/deleted while the job is stopped.

If a reader declares **`saveState(false)`** for a non-restartable run, do not expect it to resume accurately from a checkpoint after a graceful stop. Controlled stopping and accurate resumption are two distinct properties.

## 10. Keeping Output Consistent Across Stop/Restart

For DB writers sharing the chunk transaction, data committed before stopping normally stays in the target table; uncommitted work rolls back. For REST APIs, message brokers, emails, files, or separate datasources, external side effects do not automatically join Spring Batch's transaction.

Example:

~~~text
Chunk 1:
  DB insert O001..O100 -> commit
  ExecutionContext stores position 100

Chunk 2:
  Call API to create transaction for O101
  API succeeds
  Connection times out before response
  DB chunk rolls back

Stop and restart:
  May reprocess O101
  API risks receiving a duplicate request
~~~

Therefore, design in:

- Stable **idempotency keys**, e.g. `(batchId, orderId)` for side-effecting calls.
- **Unique constraints** or controlled upserts in the output database.
- **Staging/READY markers:** publish the batch only after all Steps and output reconciliation complete.
- **Transactional outbox** when database transactions must coordinate with emitting external events.
- **Reconciliation** across inputs, processing state, and external service responses after restart.
- **Do not reuse an output file consumers are already reading:** write to a temporary `batchId`/version path and publish upon `COMPLETED`.

`JobExecution` becoming `STOPPED` does not prove output is complete. Keep business batch statuses such as **`PROCESSING`**, **`STOPPED`**, **`READY`**, and **`FAILED`** separate from operational metadata when downstream consumers make decisions.

### Large Chunk Sizes vs. Stop Wait Times

Large chunk sizes reduce commits and metadata updates, but increase how much work may need to finish before stopping. Small chunks create more checkpoints at the cost of higher transaction and I/O overhead.

| Chunk Size | Typical Impact |
|---|---|
| 10 | Frequent checkpoints, fairly responsive stop, but many commits |
| 100 | Balances throughput and restart granularity for many workloads |
| 1,000 | Fewer commits, but may wait longer for the active chunk |

These are intuitive illustrations, not fixed optimal settings. Choose chunk size based on single-chunk duration, DB resources, item size, retry/skip rules, stop latency requirements, and rollback cost.

## 11. Long Tasklets Must Cooperate with Stop Signals

Not every Step uses chunks. A **Tasklet** might loop over thousands of objects within a single `execute` call. Without checking state, `JobOperator.stop` cannot intervene mid-loop.

A better design splits work into short units and persists progress. Illustrative example:

~~~java
import org.springframework.batch.core.StepContribution;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;

public class IncrementalTasklet implements Tasklet {

    private final WorkService workService;

    public IncrementalTasklet(WorkService workService) {
        this.workService = workService;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) throws Exception {

        boolean hasMore = workService.processOneUnit();

        // Each time execute returns, the framework can manage
        // transactions, Step status, and stop requests.
        return hasMore ? RepeatStatus.CONTINUABLE : RepeatStatus.FINISHED;
    }
}
~~~

**`WorkService`** is an illustrative interface. If `processOneUnit` modifies state outside a DB transaction, add explicit checkpoints and idempotency. Returning `CONTINUABLE` does not automatically persist a business cursor: you need persisted progress if accurate restarts are required.

If a Tasklet must perform long work inside one `execute` invocation, check stop conditions at safe cancelable intervals, enforce I/O timeouts, and use `StepExecution`-compatible APIs when signaling termination. Never swallow interrupt exceptions and keep looping indefinitely.

## 12. Testing Graceful Stop at Checkpoint

A useful integration test runs a **real Spring Batch Step/Job** with a `JobRepository` and output store in a test environment, then proves stop is accepted, committed data stays intact, restart resumes accurately, and final output has no duplicates.

Prerequisites to prepare:

1. An immutable input file with more records than two chunks.
2. A small chunk size, such as **2**, so checkpoints are easy to observe.
3. A dedicated test database with metadata schema and output table.
4. A stop control mechanism triggered after the first chunk (test listener or `JobOperator` from another thread).
5. Business keys to query exact outputs after each execution.
6. Latches/barriers for synchronization when waiting on a chunk, avoiding guesswork `Thread.sleep` durations.

### 12.1. Example: Stopping After the First Chunk via a Test Listener

This provides a deterministic test of the **`terminateOnly` at checkpoint** path. The listener bean is for testing only and emits the stop signal once:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.batch.core.ChunkListener;
import org.springframework.batch.core.scope.context.ChunkContext;

public class StopOnceAfterChunkListener implements ChunkListener {

    private final AtomicBoolean shouldStop = new AtomicBoolean(true);

    @Override
    public void afterChunk(ChunkContext context) {
        if (shouldStop.compareAndSet(true, false)) {
            context.getStepContext()
                    .getStepExecution()
                    .setTerminateOnly();
        }
    }
}
~~~

The test configures a Step with **`chunk(2, transactionManager)`**, attaches the listener, and feeds a file with six valid orders. When the first chunk commits, the callback sets `terminateOnly`; the framework detects it and stops the Step. The test verifies `STOPPED` status and committed output, then restarts once the listener will not emit stop a second time.

A JUnit 5 test skeleton:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;

class CheckpointStopIT {

    // Inject JobLauncherTestUtils, JobOperator, JdbcTemplate
    // and test config including StopOnceAfterChunkListener.

    @Test
    void stopAndRestartFromCommittedCheckpoint() throws Exception {
        JobParameters params = new JobParametersBuilder()
                .addString("batchId", "B-TEST-001")
                .addString("inputFile", "/test-data/orders-six.csv")
                .toJobParameters();

        JobExecution first = jobLauncherTestUtils.launchJob(params);
        assertEquals(BatchStatus.STOPPED, first.getStatus());

        // Check committed output for batch B-TEST-001 at stop point;
        // expected count depends on fixture and chunk size.

        Long resumedId = jobOperator.restart(first.getId());
        JobExecution resumed = jobExplorer.getJobExecution(resumedId);
        // If launcher is async: wait for execution to finish with timeout.
        // Assert BatchStatus.COMPLETED and output has exactly 6 order_ids,
        // no duplicate records, accurate values.
    }
}
~~~

This is a **skeleton** requiring injected beans and real fixtures to run. If `JobOperator.restart` uses a synchronous launcher, the returned execution status may already be terminal; if asynchronous, wait with a bounded timeout before asserting.

For a stronger test, verify after the `STOPPED` execution:

| Condition | Expected Result in `chunk = 2` Example |
|---|---|
| First chunk finishes | First two orders are committed |
| `terminateOnly` requested after first commit | Job transitions to `STOPPED` |
| Reader checkpoint | Position corresponding to two processed records is saved |
| Before restart | Output contains only the committed portion; batch is not marked `READY` |
| Restart same JobInstance | Creates a new JobExecution, resumes remaining records |
| After restart | Output contains all six unique keys, zero duplicates, accurate values |
| Audit/counters | Per-JobExecution item counts can be distinguished from total batch output |

Never rely solely on the **restart execution's `writeCount`** to judge final output: the new execution only writes remaining items; records committed by the earlier execution are already in the target table.

### 12.2. Testing the JobOperator.stop Path from a Control Thread

The listener test above verifies checkpoint stopping, yet **does not test the `JobOperator.stop` API**. Write a dedicated test:

1. Launch the Job asynchronously or on another test thread.
2. Obtain the exact `executionId` of the running job via a callback/listener or `JobExplorer`.
3. Use a latch signaling that at least one chunk committed while pausing subsequent work at a safe point to avoid races.
4. Call **`jobOperator.stop(executionId)`** from the control thread.
5. Release the latch and wait for the execution to reach terminal status with a timeout.
6. Assert `STOPPED` status, checkpoints, and output; then restart and reconcile final output.

Avoid unbounded wait loops or fixed-millisecond sleeps since CI load fluctuates. Ensure the test database and `JobRepository` do not shut down before the job finishes stopping.

## 13. Additional Scenarios to Test

| Scenario | What to Observe |
|---|---|
| Stop before first chunk | There may be no output yet; status and restartability are valid |
| Stop right after commit | Checkpoint matches committed data |
| Stop while writer is executing | Does not corrupt output; stops after proper transaction handling |
| Stop during a slow external API call | Timeout applies; does not hang in `STOPPING` forever |
| Stop inside a long Tasklet | Tasklet has cooperative checkpoints; otherwise stop latency grows |
| Stop an already `COMPLETED` job | Does not falsely report stop success; handles current state |
| Stop racing with job completion | Handles race cleanly; reads final status from repository |
| Stop with retry/skip | Do not use `readCount` as sole checkpoint; verify actual output |
| Restart with same identifying parameters | Resumes from checkpoint instead of creating a new batch |
| Restart after source file was modified | Must block or version appropriately because checkpoint may be invalid |
| Stop with multiple partitions | Track each worker/partition status and final output |
| Process killed abruptly | Do not confuse crash with graceful stop; follow metadata recovery runbook |
| DB write and message send in same chunk | Verify outbox/idempotency; zero external duplicates |
| Job with already `COMPLETED` Step | Configure restart flow properly to avoid unintentionally re-running completed Steps |

A thorough test verifies all three layers: **Spring Batch status**, **checkpoint/restart behavior**, and **output consistency**. Asserting `STOPPED` alone is insufficient when writers produce external side effects.

## 14. Real-World Monitoring and Operations

Record fields that help accurately evaluate stop actions:

~~~text
jobName             = importOrdersJob
jobInstanceId       = 410
jobExecutionId      = 831
batchId             = B20261116
action              = STOP_REQUESTED
requestTime         = 2026-11-16T09:30:00+07:00
lastStep            = importOrdersStep
lastCommittedChunk  = 15
currentBatchStatus  = STOPPING
eventualBatchStatus = STOPPED
restartExecutionId  = 844
~~~

This is an audit example, not live log output. Only record **`lastCommittedChunk`** if the application genuinely tracks that value. Never infer checkpoints solely from `readCount`, because filters, skips, rollbacks, and reader implementations alter counts.

Useful metrics:

- Duration from **`STOP_REQUESTED`** to **`STOPPED`**.
- Count of executions stuck in `STOPPING` longer than an operational threshold.
- Latest checkpoint position or committed chunk count, where reliable data exists.
- Restart frequency and post-restart success rate.
- Missing/duplicate output record counts after restart.
- I/O timeouts and duplicate external idempotency-key hits.

On dashboards, clearly separate **stop requested**, **stopped**, **restarting**, and **completed**. A scheduler must not trigger a replacement job merely upon seeing a "stop requested" event; wait for terminal status and verify source data locks/ownership.

### Stop and Restart Runbook

1. Identify the exact `jobExecutionId`, `batchId`, and active Steps/partitions.
2. Send a stop request via `JobOperator` or supported control mechanism.
3. Monitor until `STOPPED`; if prolonged, inspect I/O timeouts, thread dumps, transactions, and worker health.
4. Verify partial outputs and checkpoints; do not publish incomplete data.
5. Confirm the reason for stopping is resolved and input sources plus repository remain consistent.
6. Restart the same `JobInstance` when appropriate; record the new `JobExecutionId`.
7. Reconcile all output for `batchId`, and only then publish `READY`.

If the process dies while `STOPPING`, never manually edit statuses in metadata tables via SQL without a controlled recovery procedure. Assess open locks, active transactions, side effects, and real state before deciding to adjust metadata or re-run.

## 15. Common Mistakes

**Assuming `JobOperator.stop` kills threads immediately.** It is a cooperative stop request; response time depends on chunks, tasklets, and I/O. Provide checkpoints and proper timeouts.

**Calling stop and assuming the job is already `STOPPED`.** `STOPPING` is transitional; monitor until a terminal status before acting further.

**Confusing checkpoints with `readCount`.** Readers can prefetch, retry, or roll back; reconcile committed output and `ItemStream` state as the basis for recovery.

**Assuming every reader is automatically restartable.** Stateful readers must persist needed state; custom delegates must participate in `ItemStream` and `ExecutionContext`.

**Passing new job parameters to restart.** That creates a new JobInstance and may reprocess from the start; use the proper restart mechanism on the stopped execution.

**Modifying source files between stop and restart.** Checkpoint offsets may point to the wrong record. Keep input files immutable or process a new batch/version.

**Keeping state only in memory.** After a crash or restart in another process, memory state is lost. Use `JobRepository` and durable stores.

**Checking only `BatchStatus` and ignoring outputs.** A writer might have sent API calls or written files even when a DB transaction rolled back. Reconcile and enforce idempotency.

**Treating `STOPPED` as equivalent to `FAILED` or `COMPLETED`.** `STOPPED` is a controlled halt where work is incomplete and restartable per policy.

**Assuming all partitions stop at one global checkpoint.** Each worker has its own transaction/checkpoint; coordinate partitions and reconcile the combined final output.

**Forcing repository status to `STOPPED` while the job still runs.** Directly mutating metadata creates false state, risking two executions writing concurrently. Always prefer control APIs and defined recovery procedures.

## 16. Design Principles

Graceful stop at checkpoint in Spring Batch is the coordination of **execution control mechanisms**, **chunk transaction boundaries**, **recoverable ExecutionContext**, and **idempotent output**. `JobOperator` issues the stop request, yet reader/writer design, chunk duration, and how outputs are published determine whether stopping and restarting is truly safe.

When building long-running jobs, prefer chunks short enough for responsive stopping, stateful components properly registered with the Step, immutable input per JobInstance, `STOPPING → STOPPED` status monitoring, and post-restart output reconciliation. That way, jobs can pause for operational needs without sacrificing completeness, accuracy, or data traceability.
