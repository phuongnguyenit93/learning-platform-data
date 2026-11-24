# Metadata Update Failures in Spring Batch: Detection and Recovery

A chunk that finishes processing data yet fails to update metadata can put Spring Batch in a harder situation than an ordinary business error. Output data may already have changed while `JobRepository` failed to persist `StepExecution`, `ExecutionContext`, or the terminal status. Subsequently, a rerun might re-read already processed items, hit locking errors, or reject restarts because the old execution still shows `STARTED`.

**Metadata update failure** is an incident occurring while creating, updating, or committing execution state that Spring Batch must persist durably to know where a job stands and from where it can restart. This topic belongs to **Failure recovery** because recovery decisions must rely on both **what metadata state actually committed** and **what business effects actually completed**.

This article focuses on Spring Batch **5.2.x**, a JDBC `JobRepository`, and chunk-oriented processing. Principles around transactions, consistency, idempotency, and checkpoints apply across other versions too, though several packages and APIs differ in Spring Batch 6.x.

## 1. What Is Spring Batch Metadata and Why Must It Be Persisted?

Spring Batch maintains several layers of information over time:

| Object / Data | Role | Example |
| --- | --- | --- |
| `JobInstance` | Logical job run identified by job name and identifying `JobParameters` | `importOrders` for `businessDate=2026-11-15` |
| `JobExecution` | A single attempt to run a job | Execution `4812`, status `STARTED` or `FAILED` |
| `StepExecution` | A single execution of a step | `loadOrders`, `readCount=600`, `writeCount=590` |
| `JobExecutionContext` | Job-level shared state | Input file ID, cross-step aggregation markers |
| `StepExecutionContext` | Step-level checkpoint / state needed for restart | Reader line count, file offset, API page |
| `JobParameters` | Inputs and identifying parts of `JobInstance` | `businessDate`, `tenant` |

With a **JDBC JobRepository** and default table prefix, this data is primarily stored in:

```text
BATCH_JOB_INSTANCE
BATCH_JOB_EXECUTION
BATCH_JOB_EXECUTION_PARAMS
BATCH_STEP_EXECUTION
BATCH_JOB_EXECUTION_CONTEXT
BATCH_STEP_EXECUTION_CONTEXT
```

`JobRepository` is the primary API Spring Batch uses to write metadata; `JobExplorer` is the API for reading stored metadata. This information is essential for the framework to decide whether to create a new execution, resume an existing `JobInstance`, skip already completed steps, and restore reader/writer state.

**Never assume metadata errors mean "only wrong dashboard numbers."** If `ExecutionContext` is not saved cleanly after a chunk, the next restart can revert to an older checkpoint; if the terminal status is not recorded, dashboards may show an execution stuck as `STARTED` even after the process died.

## 2. Chunk Processing Order and When Metadata Is Written

For a typical chunk step, the simplified lifecycle is:

```text
JobLauncher launches Job
         |
         v
JobRepository creates JobExecution / StepExecution
         |
         v
           BEGIN TRANSACTION
                  |
                  v
         ItemReader -> ItemProcessor
                  |
                  v
           ItemWriter writes data
                  |
                  v
        Reader/Writer update state
                  |
                  v
         StepExecution / ExecutionContext
       updated via JobRepository
                  |
                  v
          COMMIT or ROLLBACK
                  |
                  v
         Next chunk (if any)
                  |
                  v
    End Step, persist status / exit code
                  |
                  v
    End Job, persist status / exit code
```

In Spring Batch 5.2, `StepExecution` and `ExecutionContext` metadata are normally updated **before the chunk commits**. `JobRepository` must be configured with proper transactions so restart metadata is not persisted arbitrarily outside processing boundaries.

This diagram is a conceptual model, not the exhaustive internal callback order for every step type. `JobExecution` is also updated at dedicated lifecycle points; some step types or item writers have transaction mechanics different from standard JDBC chunks.

### What If an Error Happens Before Commit?

When business data writes and metadata participate in **a single database transaction**, an exception rolling back the transaction will normally undo both the chunk's data and the corresponding metadata. The pre-chunk recovery point remains reusable, provided no side effects occurred on out-of-transaction resources.

If the writer targets an HTTP API, file, separate queue, or uses a **different** transaction manager from `JobRepository`, business data and metadata may not commit/roll back together. Partial effects may succeed while checkpoints fail to save, risking **duplicate processing** on rerun.

## 3. Common Metadata Failure Modes

| Incident Category | Typical Symptom | Potential Impact |
| --- | --- | --- |
| Lost connection to metadata DB | `CannotGetJdbcConnectionException`, SQL connection timeout, connection reset | Cannot create/update execution, context, or status |
| Database locked/contended | Lock wait timeout, deadlock, transaction timeout | Update or commit fails; chunk may roll back |
| Optimistic locking conflict | `OptimisticLockingFailureException` due to mismatched `VERSION` column | Two threads/agents modify execution state concurrently or use stale objects |
| Schema/permission error | Missing table, column, sequence, or `INSERT`/`UPDATE` privilege | Cannot create or update metadata as expected |
| Unserializable `ExecutionContext` | Context data incompatible with serializer, payload too large | Cannot save checkpoint, failing chunk or step completion |
| Data constraints | String exceeds column limit, constraint violation, invalid data | Writing `EXIT_MESSAGE` or context/status fails |
| Wrong transaction boundary | Metadata and business data use different transactions without consistency strategy | One commits while the other fails; restart can repeat side effects |
| Sudden JVM/pod termination | Process dies between update and commit | Repository may retain `STARTED` or stale checkpoint |
| Ambiguous commit outcome | Connection drops during COMMIT, client misses acknowledgment | Cannot immediately know whether DB committed or rolled back without verification |

Exact exception names depend on the JDBC driver, database platform, transaction manager, and Spring exception translation. Do not hardcode every incident to a single exception class; logs should capture the **root cause**, relevant SQL state/vendor code, and execution ID.

### Optimistic Locking Differs from Connection Errors

Tables such as `BATCH_JOB_EXECUTION` and `BATCH_STEP_EXECUTION` include a `VERSION` column. When updating metadata, Spring Batch applies optimistic locking to prevent overwriting updates made elsewhere to the same execution.

```text
StepExecution id=9207, VERSION=12

Thread A reads version 12
Thread B reads version 12

Thread A updates -> version 13 (succeeds)
Thread B updates with version 12 -> mismatch
                                   |
                                   v
                      OptimisticLockingFailureException
```

This signals a **state conflict**, not a transient glitch that is always safe to retry immediately. Merely wrapping `jobRepository.update(stepExecution)` in retries without resolving execution ownership and state can overwrite checkpoints or mask concurrency bugs.

Look for the root cause: multiple threads mutating the same `StepExecution`, two launchers driving the same execution, custom code manually updating the repository, stale entities held too long, or manual metadata edits.

## 4. Consistency Matrix Between Business Data and Metadata

Consider a chunk writing 100 items to the target and saving the checkpoint "processed through item 500."

| Business Data | Metadata / Checkpoint | Meaning on Restart |
| --- | --- | --- |
| Uncommitted | Uncommitted | Chunk can be reprocessed from the old checkpoint; this is the desired rollback case |
| Committed | Committed | Normally resumes cleanly from the new checkpoint |
| **Committed** | **Uncommitted / unknown** | Risk of reprocessing 100 items, causing duplicates or double API calls |
| **Uncommitted** | **Committed** | Risk of dropping items because checkpoint points ahead while business output was not written |
| Commit outcome unknown | Metadata commit unknown | Must investigate via durable traces rather than guessing from client exceptions |

The two middle imbalanced rows are especially dangerous when components use **different transaction managers**, when the writer performs non-transactional side effects, or when custom code manages commits contrary to Batch conventions.

### Single Database and Single Transaction

When business JDBC operations and JDBC `JobRepository` genuinely join a single local transaction on **the same datasource/connection**, pre-commit failures typically roll back both together. Still, verify actual wiring: matching transaction manager bean names or identical database URLs alone do not prove every operation shares the same transaction.

### Two Databases or Non-Database Resources

```text
             Chunk transaction
                  |
          +-------+--------+
          |                |
          v                v
   Business DB        Metadata DB
   COMMIT OK           UPDATE FAILED
          |                |
          +-------+--------+
                  |
                  v
      Risk of reprocessing items on restart
```

If using two separate resource managers without properly configured distributed commit protocols, Spring Batch does not automatically merge two transactions into one atomic transaction. In practice, many systems choose an **idempotent writer** and reconciliation over distributed transactions.

For REST APIs, email, object storage, and message brokers, plan a dedicated strategy because a JDBC `PlatformTransactionManager` generally cannot undo external side effects.

## 5. When Might Metadata Not Reflect Actual State?

Separate two questions:

1. **What actually happened?** Did the process send requests or write target data?
2. **What did Spring Batch record?** What status and checkpoint remain in the repository after committed transactions?

Example: a job processes three chunks and then loses connection to the metadata DB at completion:

```text
JobExecution 4812
    |
    +-- Chunk 1: business + metadata COMMITTED
    +-- Chunk 2: business + metadata COMMITTED
    +-- Chunk 3: business + metadata COMMITTED
    |
    +-- Step finished processing
    |
    +-- UPDATE final StepExecution status -> FAILURE
    |
    +-- JobExecution may not be saved as COMPLETED
```

In this example, the written data is not necessarily wrong, yet **the final status** may remain unpersisted. Depending on failure location and exception handling, the repository may show `STARTED`, `FAILED`, `UNKNOWN`, or a previous state; never assume Spring Batch can always write `FAILED` right after the repository DB fails.

**An old status row proves what metadata was saved, not that the process is still alive.** If a pod is killed without graceful shutdown, the execution can stay "stuck" as `STARTED`; Spring Batch does not automatically infer process death from metadata.

Similarly, `JobExecution.getStatus()` in an in-memory object may have updated while the DB write transaction failed. When investigating, re-read metadata **from a fresh connection/transaction** instead of trusting objects held in memory by a thread.

## 6. What Does `JobRepository` Write, and When?

Key methods in Spring Batch 5.2:

| API | Responsibility |
| --- | --- |
| `createJobExecution(jobName, jobParameters)` | Creates an execution and enforces job instance/concurrency constraints |
| `add(stepExecution)` | Persists a new `StepExecution` along with its initial execution context |
| `update(jobExecution)` | Updates `JobExecution` metadata; **does not automatically persist execution context** |
| `update(stepExecution)` | Updates `StepExecution` metadata; **does not automatically persist execution context** |
| `updateExecutionContext(jobExecution)` | Persists job-level `ExecutionContext` |
| `updateExecutionContext(stepExecution)` | Persists step-level `ExecutionContext` |

When using standard builders and tasklet/chunk machinery, **Spring Batch calls the repository at the appropriate times automatically**. You generally do not need to call `update(stepExecution)` after every successful writer invocation. Manually modifying counts, versions, or checkpoints outside framework control easily conflicts with transactions and optimistic locking.

### `ExecutionContext` Determines the Restart Point

A stateful reader, such as `FlatFileItemReader` with state saving enabled, uses `ExecutionContext` to store a recoverable position. When a chunk commits cleanly, the corresponding checkpoint must be durably saved. If side effects occurred while the context failed to save, restarting can re-read from the previous position.

Logical example:

```text
Before chunk: checkpoint = 400

Chunk 401..500:
  Writer sends 100 items -> target system accepts
  Metadata update/checkpoint 500 -> FAILED

Restart from checkpoint 400:
  401..500 re-executed -> must handle duplicates safely
```

Within a single database transaction, side effects rolled back so re-reading is right. With out-of-transaction systems, this is why writer idempotency is essential.

## 7. Configuring Transactions for Step and Repository

Example chunk step in Spring Batch 5.2.x:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .writer(writer)
            .build();
}
```

In this example, `Order` is an application domain type. `transactionManager` governs the chunk transaction; `jobRepository` persists metadata. These two dependencies may share a database or use separate datasources. **Seeing both passed to the builder does not prove both participate in one transaction.**

When a unified local JDBC transaction is needed, inspect transaction wiring for both the repository and step, configure the datasource and transaction manager properly, and verify via integration tests. In multi-datasource setups, use `@Qualifier` on beans like `jobRepository` and `businessTransactionManager` to avoid accidental mis-injection.

Example explicitly specifying a transaction manager for the step:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        @Qualifier("businessTransactionManager")
                PlatformTransactionManager businessTx,
        ItemReader<Order> reader,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, businessTx)
            .reader(reader)
            .writer(writer)
            .build();
}
```

This snippet requires importing `org.springframework.beans.factory.annotation.Qualifier`. If `businessTransactionManager` does not govern the same datasource/transaction used by `JobRepository`, understand the risk of committed business data with uncommitted metadata. When atomicity across two databases is required, consider appropriate distributed transaction management or idempotent/outbox designs.

Never blindly raise `transaction timeout` or change isolation levels to cure every metadata failure. Deadlocks, overload, optimistic locking, and serialization errors have distinct causes; diagnose accurately before tuning.

## 8. Idempotent Writer Strategies to Prevent Duplicates on Restart

Whenever atomicity between data and metadata cannot be guaranteed, the writer should allow **reprocessing the same item without creating duplicate side effects**.

Suppose orders have a unique `orderId`. If the target database supports unique constraints:

```sql
CREATE TABLE processed_order (
    order_id VARCHAR(64) PRIMARY KEY,
    amount DECIMAL(18, 2) NOT NULL,
    processed_at TIMESTAMP NOT NULL
);
```

One strategy is **upsert** by `order_id`; reprocessing an order with identical data keeps the final row accurate. Upsert syntax varies across PostgreSQL, MySQL, SQL Server, and Oracle; do not use the same SQL dialect for every database.

PostgreSQL example illustrating idempotency by business key:

```sql
INSERT INTO processed_order(order_id, amount, processed_at)
VALUES (:orderId, :amount, :processedAt)
ON CONFLICT (order_id)
DO UPDATE SET
    amount = EXCLUDED.amount;
```

Note: preserving `processed_at` on update is a business choice in this example; if other audit timestamps exist, specify update rules explicitly. **Upsert does not solve every problem:** if the writer increments balances, sends emails, transfers funds, or calls billing APIs, resending the same item can create new side effects. In those cases, use an **idempotency key** honored by the target system, or an outbox/inbox mechanism with durable deduplication.

Example key for a side effect:

```text
idempotencyKey = jobName + ":" + businessDate + ":" + businessEntityId
```

Bind the key to the **logical work** so restarts of the same `JobInstance` emit the exact same key, rather than using `jobExecutionId`: that ID changes on every restart and would make the target treat the same business operation as a brand-new request. Naturally, key rules must reflect the domain; one entity may legitimately produce multiple distinct transactions if business rules allow.

## 9. Incident Response Procedure When Production Reports Metadata Update Errors

When logs indicate `JobRepository` errors or lost metadata DB connections, prioritize **verifying facts before restarting**:

### Step 1 — Isolate the Execution

Collect:

- `jobName`, `jobInstanceId`, `jobExecutionId`, `stepName`, `stepExecutionId`.
- Identifying `JobParameters` (within allowed logging/display rules), data period, and start time.
- Exception type, cause chain, SQLState/vendor error code, and failure timestamp.
- Pod/JVM/worker health and DB/connection pool metrics at failure time.
- Side-effect traces: target rows, request IDs, message IDs, output files, or external API responses.

Do not start by editing `STATUS` in the database. An execution still marked `STARTED` may actually be running on another node, or it may be unclear whether the target committed.

### Step 2 — Re-read Metadata from a Durable Source

Use `JobExplorer` or read-only queries on a fresh connection/transaction. Inspect `JobExecution`, `StepExecution`, `VERSION`, `LAST_UPDATED`, and relevant context/checkpoint state.

Cases to distinguish:

| Observation | Follow-up Question |
| --- | --- |
| `STARTED` yet process is dead | When was the last commit? Were any out-of-transaction effects left unconfirmed? |
| `FAILED` with valid checkpoint | Is the job designed to be restartable? How far did target writes get? |
| `COMPLETED` yet launcher/log reported error | Did commit finish while the client failed to receive the result? |
| No new `JobExecution` row | Did failure happen before or inside execution creation? Did another node launch the same instance? |
| `VERSION` conflict | Are concurrent writers hitting the same execution or is an entity stale? |
| Context fails to deserialize | Is the serializer/schema compatible with the prior deployment? Which context entry failed? |

### Step 3 — Reconcile Business Side Effects

Count and compare business keys in target data against committed checkpoints, e.g., "have orders up to `orderId=500` been processed?" For external systems, check request status using idempotency keys or correlation IDs; never blindly re-call an API just because the final log line missed a response.

### Step 4 — Restore Infrastructure Then Decide Recovery

Confirm the metadata database is stable, permissions/schema/connection pools are healthy, and no other execution is still running the same work. Then:

- **Normal restart:** when the execution is restartable, checkpoints are trustworthy, and writers are idempotent or side effects rolled back.
- **Reconcile and controlled replay:** when data wrote while checkpoints lagged, deduplicate or remediate business state before rerunning.
- **Orphaned execution recovery:** when the process died leaving metadata `STARTED`, apply the version-appropriate recovery procedure and verify checkpoint validity before permitting restart.
- **Halt and investigate:** when commit outcomes are indeterminate or severe duplication risks exist, do not force continuation by changing `JobParameters`.

### Step 5 — Monitor the Rerun

Keep identifying `JobParameters` unchanged if the goal is **restarting the same `JobInstance`**. Monitor the new `JobExecution`, corresponding `StepExecution`s, checkpoints, actual persisted record counts, and duplicate signals. Keep an audit trail: who authorized replay, based on what facts, what was reconciled, and final status.

## 10. Reading Execution State via `JobExplorer`

A read-only service helps operational tools inspect executions from the repository. Example for Spring Batch 5.2.x:

```java
import java.util.Comparator;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.stereotype.Service;

@Service
public class MetadataIncidentInspector {
    private final JobExplorer jobExplorer;

    public MetadataIncidentInspector(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public void inspect(long executionId) {
        JobExecution job = jobExplorer.getJobExecution(executionId);
        if (job == null) {
            throw new IllegalArgumentException(
                    "Unknown JobExecution: " + executionId);
        }

        System.out.printf(
                "job=%s jobExecutionId=%d status=%s exit=%s%n",
                job.getJobInstance().getJobName(),
                job.getId(),
                job.getStatus(),
                job.getExitStatus().getExitCode());

        job.getStepExecutions().stream()
                .sorted(Comparator.comparing(StepExecution::getStepName))
                .forEach(step -> System.out.printf(
                        "step=%s stepExecutionId=%d status=%s " +
                        "read=%d write=%d commit=%d rollback=%d%n",
                        step.getStepName(),
                        step.getId(),
                        step.getStatus(),
                        step.getReadCount(),
                        step.getWriteCount(),
                        step.getCommitCount(),
                        step.getRollbackCount()));
    }
}
```

This snippet uses `System.out` to show output; in real applications, emit structured logs or DTOs with proper access controls. `getJobExecution(...)` returns `null` if the ID does not exist. Counters reflect persisted metadata and do not necessarily cover out-of-transaction side effects.

**Note:** reading `StepExecution` via the API does not mean you have verified all of `ExecutionContext`. When deciding to restart, also check checkpoints and target data through application-designed checks; do not interpret `readCount`/`writeCount` as absolute proof of unique business records.

## 11. Diagnostic Metadata SQL — Read-Only

For a JDBC `JobRepository` with default table prefix `BATCH_`:

```sql
SELECT
    ji.JOB_NAME,
    ji.JOB_INSTANCE_ID,
    je.JOB_EXECUTION_ID,
    je.VERSION AS JOB_VERSION,
    je.STATUS AS JOB_STATUS,
    je.EXIT_CODE,
    je.CREATE_TIME AS JOB_CREATE_TIME,
    je.START_TIME AS JOB_START_TIME,
    je.END_TIME AS JOB_END_TIME,
    je.LAST_UPDATED AS JOB_LAST_UPDATED,
    se.STEP_EXECUTION_ID,
    se.VERSION AS STEP_VERSION,
    se.STEP_NAME,
    se.STATUS AS STEP_STATUS,
    se.READ_COUNT,
    se.WRITE_COUNT,
    se.COMMIT_COUNT,
    se.ROLLBACK_COUNT,
    se.LAST_UPDATED AS STEP_LAST_UPDATED
FROM BATCH_JOB_EXECUTION je
JOIN BATCH_JOB_INSTANCE ji
  ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
LEFT JOIN BATCH_STEP_EXECUTION se
  ON se.JOB_EXECUTION_ID = je.JOB_EXECUTION_ID
WHERE je.JOB_EXECUTION_ID = :executionId
ORDER BY se.STEP_EXECUTION_ID;
```

`:executionId` is a named parameter for tools like `NamedParameterJdbcTemplate`. In SQL clients, use the matching bind syntax. If the schema uses a custom table prefix or was upgraded across versions, adjust table/column names to match the active schema.

Fields to pay attention to:

- `JOB_VERSION`/`STEP_VERSION` help identify metadata mutations and investigate optimistic locking.
- `JOB_LAST_UPDATED`/`STEP_LAST_UPDATED` show when metadata was last persisted, **not a guaranteed heartbeat**; a long-running tasklet may not commit for a long period.
- `COMMIT_COUNT`/`ROLLBACK_COUNT` describe transaction behavior recorded by the framework, **not verification** of side effects in external APIs.
- `STARTED` or `UNKNOWN` requires verifying the actual process; do not fix it with manual SQL `UPDATE` statements.

### What to Avoid

**Do not** run "quick fixes" like:

```sql
-- DO NOT EXECUTE: illustrates a dangerous operation.
UPDATE BATCH_JOB_EXECUTION
SET STATUS = 'FAILED'
WHERE JOB_EXECUTION_ID = :executionId;

-- DO NOT EXECUTE: loses checkpoint and breaks restart history.
DELETE FROM BATCH_STEP_EXECUTION_CONTEXT
WHERE STEP_EXECUTION_ID = :stepExecutionId;
```

They bypass versioning rules, transactions, related statuses, and cross-table invariants. Perform metadata recovery only via the application's standard procedure after confirming the execution is no longer running, checkpoints are reusable, and data has been reconciled.

## 12. Jobs Left `STARTED` After a Crash: The Right Way to Understand It

Some metadata errors prevent the process from recording `FAILED`; a sudden crash can also leave status as `STARTED`. Standard launch/restart commands may reject creating a new execution for the same `JobInstance` because the repository believes the previous execution is still active.

Do not swap identifying parameters for a timestamp/UUID to "dodge" the error; doing so creates a **new JobInstance** and can reprocess all data, defeating checkpoints.

In **Spring Batch 5.2.x**, Spring Batch documentation notes that after an ungraceful shutdown, status can remain `STARTED`, requiring operators to verify the execution truly stopped and apply a controlled procedure to transition it to a recoverable state if checkpoints remain valid. `ABANDONED` is not synonymous with `FAILED`: an `ABANDONED` execution/job does not follow the normal restart flow of a `FAILED` execution.

In **Spring Batch 6.x**, `JobOperator.recover(jobExecution)` is documented for recovering an execution that did not terminate cleanly before restarting. **Do not copy 6.x examples verbatim into a 5.2.x project**; choose the recovery path supported by your running version and preserve full audit trails.

Recovery actions must happen **only after** verifying the old worker is dead and business state is safe to resume. An "orphaned" execution in the database might actually be a live job whose connection to the dashboard dropped.

## 13. Preventing Metadata Failures and Reducing Impact

### 13.1. Separate Monitoring for Metadata Infrastructure

Monitor connection pools, DB reachability, lock waits/deadlocks, query latency, transaction timeouts, and storage capacity of `JobRepository`. Configure dedicated alerts for the metadata database rather than measuring only business status in target tables.

Every metadata failure log should include:

```json
{
  "eventType": "batch.metadata.update.failed",
  "jobName": "importOrders",
  "jobExecutionId": "4812",
  "stepName": "loadOrders",
  "stepExecutionId": "9207",
  "operation": "updateExecutionContext",
  "errorType": "DataAccessException",
  "sqlState": "08006",
  "message": "Could not persist batch checkpoint"
}
```

This is an **application-defined example schema**, not a full event emitted automatically by Spring Batch. `sqlState` depends on the driver/vendor. Never log raw `ExecutionContext` or parameters containing tokens, PII, or sensitive data.

### 13.2. Keep `ExecutionContext` Small and Compatible

`ExecutionContext` should hold **checkpoints needed for restart**, not entire object graphs or large file contents. Avoid storing non-serializable objects, objects tied to open connections, or Java structures that break compatibility across deployments. When changing serializers or checkpoint models, plan migrations because unfinished executions may need to restart under a newer application release.

### 13.3. Design for Safe Replay

- Idempotent writers, unique business keys, and validation at write time.
- Idempotency keys for external APIs and queues, keeping keys stable across restarts of the same logical work.
- Outbox/inbox or durable delivery state tracking for side effects lacking a shared transaction.
- Keep identifying `JobParameters` stable on restarts; never bump `run.id` to work around errors.
- Never read/write metadata tables directly outside framework APIs and approved recovery procedures.

### 13.4. Avoid Updating the Same Execution from Multiple Places

Never let multiple job runners manage the same `JobExecution`. With partitioning, let the framework manage each partition's `StepExecution`, and never share mutable `StepExecution` state across workers. Avoid manually calling `JobRepository.update` from listeners or background threads; use appropriate management APIs to control jobs.

### 13.5. Plan Reliability for the Metadata DB

`JobRepository` should not use a transient database if jobs must restart after crashes. Metadata backups and restores must align with business rules; **restoring stale metadata** alongside newer target data can reprocess already written records. HA, retention, and backup/restore plans must be rehearsed against realistic recovery scenarios.

## 14. Testing Metadata Update Failures

An integration test for recovery is far more valuable than merely mocking `JobRepository.update(...)` to throw an exception. What must be verified is **target data state, metadata, and restart behavior**—what remains after real transactions.

You can design the following cases on an **isolated test database**:

| Scenario | How to Simulate | What to Observe |
| --- | --- | --- |
| Metadata DB unavailable before launch | Temporarily disable repository datasource | No valid execution created; no side effects started |
| Connection lost while updating checkpoint | Inject fault in datasource proxy/test fixture at target point | Did chunk roll back or business commit independently? How far did context persist? |
| `ExecutionContext` unserializable | Supply serializer-incompatible checkpoint data in isolated test | Exception fails at context-write boundary and is not swallowed |
| Optimistic lock conflict | Create controlled concurrent updates to the same execution | Conflict error raised; version/stale state not overwritten |
| External API accepted data but metadata failed | Stub API records request by idempotency key, repository fails | Restart creates no duplicate side effects |
| Process dies after chunk commit | Controlled termination of test worker after predefined point | What remains in repository, and does recovery resume from valid checkpoint? |
| DB reports commit error / uncertain outcome | Inject fault on test commit/connection | Recovery verifies durable data instead of guessing outcome |

Integration tests should query using **a fresh read connection** after the fault rather than comparing in-JVM `JobExecution` objects. For external APIs, stubs can record accepted idempotency keys and assert no business operation produced side effects twice.

### Example Invariant Checks After Restart

Suppose input has 200 order IDs and the writer enforces unique business keys. After deliberately failing during metadata updates and performing controlled recovery, the test asserts:

```java
// Pseudocode for integration test: use actual repository/test fixtures.
assertEquals(200, businessOrderRepository.count());
assertEquals(200, businessOrderRepository.countDistinctOrderIds());

JobExecution lastExecution = jobExplorer.getJobExecution(restartedExecutionId);
assertNotNull(lastExecution);
assertEquals(BatchStatus.COMPLETED, lastExecution.getStatus());
```

This is **pseudocode** because `businessOrderRepository`, fault injection, and restart procedures are project-defined. Asserting 200 applies only when the test genuinely expects all inputs to succeed with no filters/skips. `BatchStatus.COMPLETED` comes from `org.springframework.batch.core.BatchStatus` in Spring Batch 5.x.

A thorough test also reconciles the first run, checkpoints, external call counts, and business data, avoiding inferring "no duplicates" solely from total `writeCount`: that counter tracks framework-recorded items per `StepExecution`, not unique target rows.

## 15. Common Recovery Pitfalls

| Symptom or Practice | Why It Is Problematic | Better Approach |
| --- | --- | --- |
| Flipping long-running `STARTED` to `FAILED` manually | Worker may still be alive, or checkpoint may be invalid | Verify liveness, metadata, and target data, then follow recovery procedure |
| Changing `run.id` to rerun immediately | Creates a new `JobInstance`, risking full reprocessing | Preserve identifying parameters to restart the right instance |
| Retrying every repository exception endlessly | Can mask optimistic locking, schema bugs, or ambiguous commits | Classify exceptions; retry only when operation and transaction are safe |
| Deleting context tables to let job "keep going" | Destroys checkpoints and breaks restartability | Restore metadata via controlled procedure with backups and reconciliation |
| Trusting "write successful" logs as DB commit | Writer may have written inside an uncommitted transaction | Verify persisted data and actual commits |
| Trusting `COMPLETED` on a Java object | Terminal state may not have committed to repository | Re-read repository on a fresh transaction/connection |
| Treating an old `LAST_UPDATED` as proof of process death | Long chunks/tasklets may not write metadata for a while | Combine health checks, logs, metrics, and thread/pod state |
| Using different transaction managers for data and metadata blindly | Can cause business commit / checkpoint rollback | Design unified transactions, idempotency, or outboxes |
| Manually editing `VERSION` to bypass lock errors | Bypasses optimistic locking, risking overwriting valid state | Investigate concurrent writers and stale entities |
| Never rehearsing DB failures in CI/staging | Duplicates/lost checkpoints discovered only during production outages | Inject faults and assert data invariants |
| Checking only JobExecution status, ignoring StepExecution context | Hard to know resume point and committed item count | Inspect execution, valid context, and target data |
| Ignoring metadata during backup/restore | Post-restore restarts may rely on stale state | Align backup, restore, retention policies, and verify recovery |

## 16. References

- [Spring Batch 5.2 — Configuring a JobRepository, transaction configuration](https://docs.spring.io/spring-batch/reference/5.2/job/configuring-repository.html)
- [Spring Batch 5.2 — Configuring a Step](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/configuring.html)
- [Spring Batch 5.2 — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing.html)
- [Spring Batch 5.2 — Transaction Attributes](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/transaction-attributes.html)
- [Spring Batch 5.2 — Controlling Rollback](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/controlling-rollback.html)
- [Spring Batch 5.2 — Advanced Metadata Usage and handling dead processes](https://docs.spring.io/spring-batch/reference/5.2/job/advanced-meta-data.html)
- [Spring Batch 5.2 — Meta-Data Schema](https://docs.spring.io/spring-batch/reference/5.2/schema-appendix.html)
- [Spring Batch 5.2 API — `JobRepository`](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/repository/JobRepository.html)
- [Spring Batch 5.2 API — `JobExplorer`](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/explore/JobExplorer.html)
- [Spring Batch 6 — Advanced Metadata Usage, recovering a job](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html)

When metadata updates fail, simultaneously evaluate **whether the execution is actually still alive**, **which metadata committed**, **which business data was affected**, and **which checkpoint can be trusted for restart**. `JobRepository` stores state for framework recovery, yet it cannot automatically undo side effects outside the transaction. Consequently, clear transaction boundaries, idempotent writers, log events carrying execution IDs, reconciliation procedures, and controlled recovery form the foundation for a Spring Batch job to recover safely from metadata incidents.
