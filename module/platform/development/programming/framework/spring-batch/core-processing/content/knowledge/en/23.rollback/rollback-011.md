# Inspecting Metadata State After Rollback

In Spring Batch, a chunk's rollback and the final status of a Job/Step are two distinct concepts. When a chunk transaction rolls back, uncommitted business changes are undone within the scope of resources participating in the transaction. Step metadata such as counters, statuses, and `ExecutionContext` are managed by JobRepository so Spring Batch can track progress and support restarts.

To properly inspect state after a rollback, examine `BatchStatus`, `ExitStatus`, `StepExecution` counters, `ExecutionContext`, and committed business data together. A rollback does not necessarily fail the Step: if a transient error succeeds on retry, the Step can still finish `COMPLETED` while recording rollbacks. Conversely, if the process stops abruptly, metadata may remain in `STARTED` status because the framework could not persist a terminal outcome.

## 1. Distinguishing Rollback from Step Status

Rollback is an action taken by the transaction manager on a transaction. `BatchStatus` describes the lifecycle state of a Step or Job. The two concepts are related, not identical.

For example, a chunk of 100 items encounters a deadlock in the writer:

1. Spring Batch opens a transaction for the chunk.
2. The reader reads items, the processor processes them, and the writer begins writing.
3. The database throws a deadlock exception.
4. The chunk transaction rolls back.
5. The retry policy re-attempts the operation or chunk per configuration.
6. The next attempt succeeds and the chunk commits.
7. The Step continues processing remaining chunks.

In this situation a rollback occurred, yet the Step can still finish with `BatchStatus.COMPLETED`. Rollback count can be greater than 0 even when the Job succeeds.

If retries are exhausted and the error is not skipped, the Step typically ends in `FAILED`. Its parent Job then usually fails per flow rules. If the application is killed mid-transaction, final metadata may not have been updated to failed; it may still reflect an active execution.

## 2. Metadata Layers to Inspect

Spring Batch stores metadata across multiple layers. When investigating a rollback, never inspect only a single field or table.

| Object | What to Inspect | Question to Answer |
|---|---|---|
| `JobExecution` | `BatchStatus`, `ExitStatus`, start/end times | Did the Job complete, fail, stop, or remain running? |
| `StepExecution` | `BatchStatus`, `ExitStatus`, read/write/skip/commit/rollback counters | Which Step hit an error and how far did chunks progress? |
| Step `ExecutionContext` | Reader/writer checkpoints and Step state | From which checkpoint will a restart resume? |
| Job `ExecutionContext` | Data shared across Steps | Which coordination data can downstream Steps reuse? |
| Business data | Committed records in the database or target systems | Which changes actually persist after rollback? |

Metadata shows what Spring Batch recorded; business data shows the actual state in target systems. When the two do not share a transaction or non-transactional side effects exist, cross-check both.

## 3. BatchStatus and ExitStatus After Rollback

`BatchStatus` represents execution lifecycle status, such as:

| BatchStatus | Meaning |
|---|---|
| `STARTING` | Execution is initializing |
| `STARTED` | Execution is running |
| `COMPLETED` | Execution completed normally |
| `FAILED` | Execution failed |
| `STOPPING` | Currently stopping |
| `STOPPED` | Execution stopped |
| `ABANDONED` | Execution marked not to be restarted normally |
| `UNKNOWN` | Status cannot be determined |

`ExitStatus` describes the exit outcome, usually comprising an exit code and description—for example, `COMPLETED`, `FAILED`, `STOPPED`, or a custom code like `COMPLETED_WITH_SKIPS`.

After a rollback, status depends on downstream handling:

- If retry succeeds, the Step can continue and ultimately finish `COMPLETED`.
- If the exception is skipped within the skip limit, the Step can continue and finish `COMPLETED` with skip count greater than 0.
- If the exception is non-retryable, non-skippable, or exceeds limits, the Step typically ends `FAILED`.
- If the Job is stopped gracefully, the Step/Job can finish `STOPPED`.
- If the process is killed abruptly before terminal metadata is saved, repository status may remain `STARTED`.

Do not infer that any rollback forces `BatchStatus` to be `FAILED`. Always inspect final status alongside exceptions and counters.

## 4. StepExecution Counters

`StepExecution` holds counters reflecting Step activity:

| Counter | Meaning |
|---|---|
| `readCount` | Number of items read successfully |
| `writeCount` | Number of items written successfully |
| `filterCount` | Number of items filtered by the processor |
| `readSkipCount` | Number of items skipped during read |
| `processSkipCount` | Number of items skipped during processing |
| `writeSkipCount` | Number of items skipped during write |
| `skipCount` | Total number of skipped items |
| `commitCount` | Number of commits recorded for the Step |
| `rollbackCount` | Number of rollbacks recorded for the Step |

For instance, a Step with `readCount=500`, `writeCount=490`, `filterCount=5`, `skipCount=5` may have read 500 items, filtered 5, and skipped 5, leaving the writer to write 490 items. If `rollbackCount=2`, the Step recorded two rollbacks during execution; that does not mean all 500 items were rolled back.

Counters must be read alongside execution status and history. Depending on failure timing, retries, transactions, and framework version, in-memory values and committed metadata may differ while the Step is still running. Once execution finishes and metadata updates settle, counters provide a solid basis for analyzing outcomes.

`rollbackCount` is not a retry count. A rollback can stem from a non-retryable error, commit error, or other failure; retry policies may also re-invoke operations through different execution paths. If exact retry counts are needed, instrument the retry policy or use a `RetryListener`.

## 5. ExecutionContext After Rollback

Restartable readers typically store checkpoints in the Step `ExecutionContext`. Example reader persisting the last committed ID:

```java
private static final String LAST_ID_KEY = "ordersReader.lastCommittedId";

@Override
public void update(ExecutionContext context) {
    context.putLong(LAST_ID_KEY, lastCommittedId);
}

@Override
public void open(ExecutionContext context) {
    lastCommittedId = context.getLong(LAST_ID_KEY, 0L);
    openSourceAfter(lastCommittedId);
}
```

In chunk processing, Spring Batch invokes `ItemStream.update()` at Step state-saving points. When checkpoints are persisted in the matching transaction, they represent committed progress.

Suppose the reader committed up to order ID 4000. The next chunk reads IDs 4001–4100, yet the writer errors and the transaction rolls back. If the Step restarts later, the durable checkpoint must still represent the latest committed progress, namely ID 4000. The reader will re-read from ID 4001 according to query rules.

This works only when the reader supports `ItemStream`/restarts, `saveState` is enabled if required by the reader, and the data source stays stable. Stateless readers may not know where to resume after process termination.

## 6. In-Process Rollback vs. Restart After Crash

These two situations leave different metadata footprints.

### Rollback While the Application Continues Running

When a chunk rolls back while the process remains alive, Spring Batch can retry or replay already-read items per fault-tolerance policy. The Step keeps running. If retry succeeds, the Step can complete with `BatchStatus.COMPLETED` while the rollback count reflects the rollback that happened.

### Process Terminated Abruptly

If the JVM is killed or the server loses power mid-transaction, in-memory buffers are lost. The framework may not have time to update `BatchStatus` and `endTime` in JobRepository. `JobExecution`/`StepExecution` rows may remain `STARTED` even though no thread is executing anymore.

In that case, verify whether the execution is genuinely still running before intervening. Do not casually relaunch the same `JobInstance` while the repository still marks an execution active; Spring Batch may reject the launch because an execution is in progress.

Operational procedures should rely on `JobExplorer`/`JobOperator` and system recovery runbooks to handle stuck executions. Never edit `BATCH_*` tables directly just to flip `STARTED` to `FAILED` without fully understanding locks, versions, metadata, and business data.

## 7. Reading Metadata with JobExplorer

`JobExplorer` is a read-only API for querying JobRepository metadata. Use it to retrieve `JobExecution`, `StepExecution`, and `ExecutionContext` instead of hand-writing SQL queries.

Example reading `JobExecution` and `StepExecution` states:

```java
public void inspectJobExecution(
        JobExplorer jobExplorer,
        long jobExecutionId) {

    JobExecution jobExecution = jobExplorer.getJobExecution(jobExecutionId);
    if (jobExecution == null) {
        log.warn("JobExecution {} was not found", jobExecutionId);
        return;
    }

    log.info(
            "jobExecutionId={}, jobInstanceId={}, status={}, exitStatus={}, start={}, end={}",
            jobExecution.getId(),
            jobExecution.getJobInstance().getId(),
            jobExecution.getStatus(),
            jobExecution.getExitStatus(),
            jobExecution.getStartTime(),
            jobExecution.getEndTime()
    );

    for (StepExecution stepExecution : jobExecution.getStepExecutions()) {
        log.info(
                "step={}, stepExecutionId={}, status={}, exitStatus={}, " +
                "read={}, write={}, skips={}, commits={}, rollbacks={}",
                stepExecution.getStepName(),
                stepExecution.getId(),
                stepExecution.getStatus(),
                stepExecution.getExitStatus(),
                stepExecution.getReadCount(),
                stepExecution.getWriteCount(),
                stepExecution.getSkipCount(),
                stepExecution.getCommitCount(),
                stepExecution.getRollbackCount()
        );
    }
}
```

Exact API names may vary slightly by Spring Batch version. `JobExplorer` suits monitoring dashboards, admin endpoints, or investigation tools because it uses framework abstractions rather than coupling application code directly to metadata table names.

When inspecting a running execution, data can change mid-query. To analyze final outcomes, re-read after execution ends or after recovery finishes.

## 8. Querying Metadata Tables Directly

In the standard JDBC repository schema, metadata typically resides in `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION`, `BATCH_JOB_EXECUTION_CONTEXT`, and `BATCH_STEP_EXECUTION_CONTEXT`. Table prefixes/names can be customized; schemas may also differ across Spring Batch versions.

### Viewing JobExecution Status

```sql
SELECT
    JOB_EXECUTION_ID,
    JOB_INSTANCE_ID,
    STATUS,
    EXIT_CODE,
    EXIT_MESSAGE,
    START_TIME,
    END_TIME,
    LAST_UPDATED
FROM BATCH_JOB_EXECUTION
WHERE JOB_EXECUTION_ID = :jobExecutionId;
```

This query shows whether the `JobExecution` is `STARTED`, `COMPLETED`, `FAILED`, or another status, along with exit code and end time.

### Viewing Status and Counters of Each StepExecution

```sql
SELECT
    STEP_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    EXIT_CODE,
    EXIT_MESSAGE,
    READ_COUNT,
    WRITE_COUNT,
    FILTER_COUNT,
    READ_SKIP_COUNT,
    PROCESS_SKIP_COUNT,
    WRITE_SKIP_COUNT,
    COMMIT_COUNT,
    ROLLBACK_COUNT,
    START_TIME,
    END_TIME,
    LAST_UPDATED
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :jobExecutionId
ORDER BY STEP_EXECUTION_ID;
```

When a Step experiences rollbacks, examine `ROLLBACK_COUNT` alongside `COMMIT_COUNT`, read/write counters, and `STATUS`. Do not conclude data was lost from `ROLLBACK_COUNT` alone; reconcile committed counts against target data.

### Viewing Step ExecutionContext

```sql
SELECT
    STEP_EXECUTION_ID,
    SHORT_CONTEXT,
    SERIALIZED_CONTEXT
FROM BATCH_STEP_EXECUTION_CONTEXT
WHERE STEP_EXECUTION_ID = :stepExecutionId;
```

`SHORT_CONTEXT` usually holds a truncated or text representation of the context; `SERIALIZED_CONTEXT` may be used depending on serializer and schema configuration. Do not edit these columns directly via SQL to force a checkpoint to a different position.

Column names can vary by schema/version and database. Verify the JobRepository schema actually installed by the application before running operational queries.

## 9. Reconciling Metadata with Business Data

Metadata and business data may live in the same database or in separate resources. When sharing the same transaction manager and transaction, business data updates and metadata checkpoints can commit/roll back consistently. When using multiple transaction managers or non-transactional side effects, atomicity cannot be assumed.

For example, a writer inserts 50 orders into the database in the chunk transaction. If the 51st insert fails and the transaction rolls back, the 50 uncommitted inserts can be undone. Corresponding metadata checkpoints must also revert to prior committed progress if managed in the same transaction.

Conversely, if the writer sent 50 messages to a broker and failed on the 51st message, rolling back the database transaction does not retract messages already accepted by the broker. Metadata may show the chunk did not commit while the external system already has side effects. On restart/retry, idempotency keys or inbox/outbox patterns are required to prevent duplicates.

When investigating, build a reconciliation checklist:

| Check | Source | Goal |
|---|---|---|
| Latest checkpoint | Step `ExecutionContext` | Know where the reader will resume |
| Commit/rollback counters | `StepExecution` | Understand Step-level transaction history |
| Written records | Target database | Verify which business changes actually exist |
| Dispatched messages/APIs/files | Target system or audit logs | Detect non-rollbackable side effects |
| Exceptions and exit messages | Job/Step metadata and application logs | Identify root cause of rollback/failure |

## 10. Example Analysis of a Step After Rollback

Suppose a Step imports 1,000 items with a commit interval of 100. Post-completion metadata shows:

| Field | Illustrative Value |
|---|---:|
| `readCount` | 1.000 |
| `writeCount` | 1.000 |
| `commitCount` | 10 |
| `rollbackCount` | 2 |
| `skipCount` | 0 |
| `BatchStatus` | `COMPLETED` |
| `ExitStatus` | `COMPLETED` |

A reasonable interpretation is that the Step experienced two rollbacks during execution, yet retries or recovery succeeded; ultimately all 1,000 items were written and 10 chunks committed. These figures are illustrative only; do not deduce exact invocation counts from counters alone.

Another case:

| Field | Illustrative Value |
|---|---|
| `readCount` | 450 |
| `writeCount` | 400 |
| `commitCount` | 4 |
| `rollbackCount` | 1 |
| `BatchStatus` | `FAILED` |
| `ExitStatus` | `FAILED` |
| `ExecutionContext` | Checkpoint at last committed chunk |

The Step committed four chunks, and then the next chunk failed. When restarting the same `JobInstance`, the reader can resume from the last committed chunk's checkpoint. Still, check whether the writer has non-transactional side effects before rerunning the uncommitted portion.

## 11. STARTED Status After Process Kill

A common operational incident is a Job being killed mid-chunk. The database transaction may roll back when the connection closes, yet the JVM had no chance to run Step completion callbacks and update final metadata status.

Metadata tables may then still show:

```text
BATCH_JOB_EXECUTION.STATUS  = STARTED
BATCH_STEP_EXECUTION.STATUS = STARTED
END_TIME                    = NULL
```

This is not proof that the Job is still actively running. Nor is it proof that transactions rolled back completely across every resource. Inspect processes/workers, database sessions, locks, logs, and target system states.

Recovery procedures must use authorized operational tools/APIs such as `JobOperator` or dedicated admin runbooks. Mark an old execution as `FAILED`/`ABANDONED` only after confirming no worker remains active and understanding impacts on checkpoints, locks, and target data.

Do not launch the same `JobInstance` again while the old execution is still considered running. JobRepository can reject duplicate launches to protect metadata and data.

## 12. JobExplorer and JobOperator Have Different Roles

`JobExplorer` is primarily for reading metadata. It fits status checks, execution history, and checkpoint inspection.

`JobOperator` provides operational actions such as start, restart, stop, or querying information per the Spring Batch version's API. It is a tool for controlling executions under framework rules, not an excuse to skip verifying whether an old execution is still alive.

When discovering a stuck execution after a crash:

1. Use `JobExplorer` to identify the relevant `JobInstance`, `JobExecution`, and `StepExecution`.
2. Inspect processes/workers and database sessions to confirm the execution is no longer active.
3. Reconcile checkpoints against committed business data.
4. Execute the approved recovery procedure using `JobOperator` or the application's admin tool.
5. Restart with the same identifying `JobParameters` if resuming the same `JobInstance`.
6. Monitor the new execution and verify no duplicate side effects occur.

Available APIs and permissions depend on application configuration. Never expose endpoints allowing arbitrary users to alter execution statuses or trigger restarts without operational controls.

## 13. Common Misconceptions

**Assuming rollback always makes the Step FAILED.** Retries can recover from errors and the Step can still complete. Check the final status.

**Assuming rollbackCount equals retry count.** They are two distinct metrics. Use retry instrumentation if exact attempt counts are needed.

**Assuming readCount equals committed item count.** Read items may belong to rolled-back chunks. Check write/commit counters and checkpoints.

**Assuming ExecutionContext always holds the very last item read by the reader.** Durable checkpoints must reflect committed progress. Uncommitted chunks should not be treated as finished.

**Assuming a process crash automatically updates status to FAILED.** If the process cannot run final callbacks, metadata may remain `STARTED`. A recovery procedure is needed.

**Checking only metadata without checking target data.** Non-transactional side effects can persist despite chunk rollback. Reconcile business data and external systems.

**Editing BATCH_* tables directly to force a restart.** Metadata is tied to versions, contexts, and transactions. Use controlled APIs and operational procedures.

## 14. Testing Metadata After Rollback

To verify application behavior, write integration tests using `JobRepository` and an appropriate transaction manager:

1. Create a Step reading several items and a writer intentionally throwing an exception in the first chunk.
2. Verify the chunk transaction rolls back and uncommitted database changes are absent.
3. Configure retry so the subsequent attempt succeeds; verify the Step finishes `COMPLETED` and the rollback counter is recorded appropriately.
4. Simulate exhausted retries; verify the Step/Job ends `FAILED` with the cause in the exit message.
5. Inspect `ExecutionContext` after commit to confirm checkpoints reflect the last committed chunk.
6. Stop the Job between chunks and restart the same `JobInstance`; verify the reader restores the right position.
7. If non-transactional side effects exist, verify idempotency/outbox prevents duplicates across retries or restarts.
8. Verify metadata state when an execution terminates abruptly using a test environment capable of simulating process failure.

Do not assert solely on a single `rollbackCount` value. Verify status, exit code, counters, `ExecutionContext`, and final business data. A test using an in-memory repository recreated between runs does not prove durable checkpoints survive process restarts.

## 15. Post-Rollback Inspection Workflow

When a chunk rolls back, first determine whether it was a rollback retried in-process, an error that failed the Step, or a process crash mid-execution. Next, inspect `JobExecution` and `StepExecution` to read `BatchStatus`, `ExitStatus`, counters, and exceptions. Check Step `ExecutionContext` to find the last saved checkpoint, then reconcile against business data and side effects in external systems.

If the Step is still running, monitor the execution. If retry recovers, confirm the Step finishes and target data is consistent. If the Step failed, restart the same `JobInstance` with original identifying parameters after fixing the root cause. If metadata remains `STARTED` after a crash, confirm no active worker remains and follow a controlled recovery workflow before restarting.

Proper metadata inspection distinguishes a recovered rollback from a failed or stuck execution. Combining `JobExplorer`, `JobRepository`, `ExecutionContext`, logs, and business data reveals what committed, what must be re-run, and which side effects require reconciliation.
