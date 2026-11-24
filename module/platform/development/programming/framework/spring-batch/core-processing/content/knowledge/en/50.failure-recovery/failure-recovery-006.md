# Killed Processes in Spring Batch: Incident Detection and Safe Recovery

## 1. Context: The Process Vanishes Mid-Batch Job

Suppose `dailyOrderImportJob` is importing 2 million orders. After processing roughly 1.2 million records, the JVM is abruptly terminated by the operating system or deployment platform. When the application starts back up, the question is not just **running the job again**: you must determine which data committed, which checkpoints were persisted, what metadata failed to update, and whether the previous run has truly terminated.

In Spring Batch, a *killed process* differs from a step throwing an exception and terminating cleanly. A normal error passes through the framework's exception handling, allowing it to persist `BatchStatus.FAILED` in `JobRepository`. When the JVM/process dies before cleanup can run, the repository may still record the job as `STARTED` even though no program is running anymore.

Common causes:

- `kill -9 <pid>` on Linux or equivalent forced termination commands.
- Container receiving `SIGKILL`, getting OOM-killed, or deleted after graceful termination expires.
- Host/VM power loss, kernel panic, or node failure.
- JVM crash where the runtime terminates without executing shutdown hooks.
- Orchestrator automatically restarting a pod/process due to failed liveness probes, exceeded memory limits, or deployment policies.

The *failure recovery* goal in this chapter is: **restore the ability to rerun without assuming data committed or metadata is consistent, while preventing duplicate execution of the same work**.

```text
JobExecution #5100: STARTED
    |
    +-- Step A: COMPLETED
    |
    +-- Step B: STARTED
            |
            +-- chunks 1...N committed
            +-- chunk N+1 processing
                    |
                 SIGKILL
                    X

New process starts
    |
    +-- JobRepository may still report STARTED
    +-- Step B has checkpoint up to last commit
    +-- Must verify old process is dead and decide recovery
    +-- Only then restart the exact JobInstance
```

## 2. Distinguishing Graceful Shutdown from Forced Kill

| Situation | What Happens | Expected Metadata | Restartable Immediately? |
|---|---|---|---|
| Step throws an exception caught by framework | Spring Batch ends error flow, cleans resources, updates repository | Usually `FAILED` | Yes, if job/step are restartable and data is valid. |
| `JobOperator.stop(...)` while process is alive | **Cooperative** stop request; framework finishes at safe stop point | Usually transitions `STOPPING` then `STOPPED` | Once actually `STOPPED`, if job permits. |
| `SIGTERM` with controlled shutdown | Opportunity to run hooks and close Spring context | Depends on version and config; does not guarantee `STOPPED` | Only if repository status and checkpoints allow. |
| `SIGKILL` / OOM kill / crash | No chance to run `finally`, completion callbacks, or hooks | Can stay stuck `STARTED`/`STARTING`/`STOPPING` | No, verify and recover metadata first. |
| Machine running yet step blocks for a long time | Process and job may actually still be working | May legitimately stay `STARTED` | Never blindly assume the job is dead. |

`SIGTERM` requests process termination and usually allows cleanup; `SIGKILL` forces the kernel to stop the process and cannot be caught or delayed by the JVM. However, even an application receiving `SIGTERM` may be forcibly terminated before the framework finishes writing status, especially when blocked on I/O or processing a long chunk.

**`JobOperator.stop` is not equivalent to an OS kill command.** It is a cooperative batch stop request. If business code is stuck in a loop without yielding control or waiting on an un-timed-out request, stopping can be delayed. Never conclude from a successful `stop(...)` call that the repository has already transitioned to `STOPPED`.

## 3. What State Exists in `JobRepository` After a Crash?

With a JDBC `JobRepository`, Spring Batch stores metadata across `BATCH_*` tables. Tables to inspect during investigation:

| Table | Recovery-Relevant Data |
|---|---|
| `BATCH_JOB_INSTANCE` | Job name, instance identity derived from identifying parameters. |
| `BATCH_JOB_EXECUTION` | Execution run, `STATUS`, `EXIT_CODE`, start/end times, `LAST_UPDATED`. |
| `BATCH_JOB_EXECUTION_PARAMS` | `JobParameters` supplied at launch. |
| `BATCH_JOB_EXECUTION_CONTEXT` | Job-level `ExecutionContext`. |
| `BATCH_STEP_EXECUTION` | Per-step state, read/write/skip/commit/rollback counts. |
| `BATCH_STEP_EXECUTION_CONTEXT` | Step-level checkpoints and restart state. |

An illustrative example:

```text
BATCH_JOB_EXECUTION
JOB_EXECUTION_ID  STATUS   EXIT_CODE  END_TIME
5100              STARTED  UNKNOWN    NULL

BATCH_STEP_EXECUTION
STEP_EXECUTION_ID  STEP_NAME       STATUS     READ_COUNT
7100               downloadFiles   COMPLETED  0
7101               importOrders    STARTED    1200000
```

Values above are illustrative only. **`STATUS=STARTED` in the database does not prove the process is still alive.** The repository knows only the updates the application managed to write before dying, and has no universal built-in detector for `SIGKILL` across every node.

### 3.1. Relevant Statuses

| `BatchStatus` | Key Operational Meaning |
|---|---|
| `STARTING` | Framework created the execution but has not yet transitioned into processing. |
| `STARTED` | According to metadata, the job or step is active. May be a stale leftover after a crash. |
| `STOPPING` | Stop requested; may not yet have finished stopping. |
| `STOPPED` | Stopped cleanly; restartable if configuration permits. |
| `FAILED` | Execution failed; restartable if restart data is valid. |
| `COMPLETED` | Execution finished; the corresponding instance generally cannot be rerun with the same identifying parameters. |
| `ABANDONED` | Execution explicitly abandoned; cannot be restarted via standard mechanisms. |
| `UNKNOWN` | Ambiguous state; investigate before restarting. |

`BatchStatus` differs from `ExitStatus`: `BatchStatus` represents execution state, while `ExitStatus` is the exit code used for job flow transitions. When a process dies, either may fail to reflect the final outcome. Never edit `EXIT_CODE='COMPLETED'` just to clear dashboard alerts.

### 3.2. Read-Only Metadata Queries

The SQL below illustrates the default Spring Batch 5.x schema. Table/column names can differ by version or custom `tablePrefix`.

```sql
SELECT
    ji.JOB_NAME,
    ji.JOB_INSTANCE_ID,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.EXIT_CODE,
    je.START_TIME,
    je.END_TIME,
    je.LAST_UPDATED
FROM BATCH_JOB_EXECUTION je
JOIN BATCH_JOB_INSTANCE ji
  ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
WHERE je.STATUS IN ('STARTING', 'STARTED', 'STOPPING')
ORDER BY je.LAST_UPDATED;
```

Querying steps for an execution:

```sql
SELECT
    STEP_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    EXIT_CODE,
    READ_COUNT,
    WRITE_COUNT,
    COMMIT_COUNT,
    ROLLBACK_COUNT,
    LAST_UPDATED
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :jobExecutionId
ORDER BY STEP_EXECUTION_ID;
```

`:jobExecutionId` represents a bind parameter for query tools or JDBC; depending on the SQL client, `?` may be used. Use only verified execution IDs in the target environment. **Never treat an unchanged `LAST_UPDATED` as sole proof that a process died**: a long tasklet, blocked step, or metadata connection outage can also halt updates to this column.

## 4. Impact on Transactions and Business Data

### 4.1. Which Chunks Are Preserved?

In a chunk-oriented step, Spring Batch executes read/process/write operations within chunk transaction boundaries. With a transactional database and properly configured transaction manager:

```text
Chunk 1 (1..100)   -> COMMIT
Chunk 2 (101..200) -> COMMIT
Chunk 3 (201..300) -> JVM killed before COMMIT

General expectation:
  - DB changes from chunks 1 and 2 persist.
  - Uncommitted DB changes from chunk 3 typically roll back
    when the connection/transaction closes or DB detects dead session.
  - Latest checkpoint lets the reader resume from the saved position.
```

This is a baseline model, **not a guarantee that every writer is exactly-once**. Outcomes also depend on transactions, database engines, connection pools, how readers/writers and `ExecutionContext` persist, and crash timing. If a writer sends HTTP requests, writes files, publishes to Kafka, or writes to another datasource outside the transaction, those side effects may already have happened even if metadata rolled back.

### 4.2. Four Different Kill Points

| Kill Point | Potential Consequence |
|---|---|
| Before starting a chunk | Earlier chunks retain committed results; terminal status is unrecorded. |
| Mid-read/process inside a chunk | In-flight work stops; on transactional DBs, uncommitted work typically rolls back. |
| During commit | Commit outcome can be ambiguous from the app's view; verify directly in DB rather than guessing. |
| After external side effect succeeds, before checkpoint/metadata persists | On restart, the same item may be reprocessed and repeat the side effect. |

Reliable failure recovery must be designed to handle **the uncertainty gap between side effects and checkpoints**. Specifically, if a job sends emails or calls payment APIs, never rely solely on `readCount` to decide whether an action already ran.

### 4.3. `ExecutionContext` Is Not a Live Counter of Current Progress

`ItemStream` defines `open`, `update`, and `close` callbacks. Stateful readers/writers can use `ExecutionContext` to restore positions. The framework calls `update(...)` to save state prior to commit in alignment with the chunk lifecycle. When restarting the same `JobInstance`, step state can be reloaded from the previous execution.

```text
Persisted StepExecutionContext:
  reader.current.count = 200

Process killed after reading up to item 240 in the next chunk.

On restart:
  reader uses persisted checkpoint,
  do not assume it can resume precisely from item 240.
```

Actual key names depend on the reader implementation and stream name. `FlatFileItemReader`, `JdbcCursorItemReader`, and `JdbcPagingItemReader` have different restart requirements; verify `saveState`, instance names, stable sort keys, behavior when source data mutates, and that the reader is registered as an `ItemStream`.

Checkpoints do not mean "exactly N business records were processed"; retries/skips, rollbacks, filters, and external side effects can cause `read`/`write` counts to diverge.

## 5. Why Restarting the Application Alone Is Not Enough

When the application boots back up, Spring Batch does not by default scan all old `STARTED` runs and flip them to `FAILED`. The repository may still believe the prior execution is running. If the same job name and **identifying `JobParameters`** are requested again, the result may be `JobExecutionAlreadyRunningException` or a metadata-state restart error.

Relationship to remember:

```text
JobInstance = jobName + identifying JobParameters

JobInstance #100 (dailyOrdersJob, businessDate=2026-11-16)
    |
    +-- JobExecution #5100 -> STARTED (process already dead)

When invoked again with the same businessDate:
    -> Repository detects old execution recorded as running
    -> Does not automatically create a safe restart
```

Appending `run.id=System.currentTimeMillis()` just to "make it run now" creates a **new JobInstance**, bypassing the prior instance's checkpoints and raising the risk of duplicate writes. That is suitable only when business truly wants a fresh run with idempotency or prior cleanup already handled—not as a default workaround for a killed process.

## 6. Runbook When Detecting a Killed Process

A recovery process should separate **detection**, **verification**, **data assessment**, **decision**, and **relaunch**.

### Step 1: Verify the Old Process Has Terminated

Collect environment-appropriate signals:

- On host: process/PID, exit code, OOM killer logs, systemd journal, JVM crash logs if present.
- On Kubernetes: pod status, container `lastState.terminated.reason`, exit code, `OOMKilled` events, previous container logs, node events.
- On scheduler: which job was triggered, how many replicas/schedulers exist, when the next schedule fires.
- On DB: remaining sessions/transactions/locks, and whether another worker process could still be executing the same work.

Do not mark an execution `FAILED` merely because a pod vanished from a dashboard: another replica or distributed worker may still be running it. With partitioning/remote chunking, inspect worker nodes and message queues as well.

### Step 2: Pinpoint the Exact `JobInstance` and `JobExecution`

Record `jobName`, identifying parameters, `jobInstanceId`, `jobExecutionId`, step execution IDs, and current stored status. Inspect metadata via `JobExplorer` or read-only SQL; if an investigation snapshot is required, follow operational and data-access policies.

Example with Spring Batch 5.x:

```java
JobExecution execution = jobExplorer.getJobExecution(5100L);

if (execution == null) {
    throw new IllegalArgumentException("Unknown job execution ID");
}

System.out.println("Job: "
        + execution.getJobInstance().getJobName());
System.out.println("Status: " + execution.getStatus());
System.out.println("Instance ID: "
        + execution.getJobInstance().getInstanceId());
```

This is a read example assuming a `JobExplorer` bean is injected; it modifies no metadata. Avoid printing full `JobParameters` and `ExecutionContext` directly to operational logs since they may hold sensitive data.

### Step 3: Assess Checkpoints and Committed Results

Cross-check three information sources:

1. **Metadata:** `StepExecution`, counts, `ExecutionContext`, and the job/configuration version active when the job started.
2. **Business data:** rows/files/messages genuinely persisted, unique keys, processing statuses, reconciliation tables.
3. **External systems:** API calls, emitted messages, uploaded files, sent emails, transaction IDs, or idempotency keys.

If external operations lack deduplication, restarting can repeat side effects. When uncertain, verify against target outputs and prepare an appropriate remediation action before resuming.

### Step 4: Block Duplicate Triggers During Incident Handling

If the scheduler remains active, another cron trigger may relaunch the same job while metadata is being repaired. In multi-instance systems, enforce coordination so only one recovery action operates on a business key. Pause schedules per operational runbook or use a designed distributed lock/lease/claim table; never assume a dead process automatically cleared every application lock.

### Step 5: Decide `FAILED` to Restart or `ABANDONED` to Drop

| Decision | When Appropriate? | Consequence |
|---|---|---|
| Recover execution to restart | Old process confirmed dead, checkpoints trustworthy, side effects safe, job restartable | Permits creating a new `JobExecution` under **the same JobInstance**. |
| Mark `ABANDONED` | Run cannot/should not continue via restart or another business remediation path was chosen | Execution is abandoned; cannot restart via standard flow. |
| Leave unchanged and investigate | Process liveness, transaction outcome, side effects, or data consistency still unconfirmed | Do not launch new work for the same business key. |

**Never automate this decision solely from `LAST_UPDATED` age.** A long-running job can still be actively working, and only an operator/system with sufficient evidence should alter repository state.

### Step 6: Restart the Exact Instance and Verify Post-Recovery

Once status has been recovered via the API/procedure matching your Spring Batch version, relaunch with **the exact same identifying parameters** and monitor the new `JobExecution`. Verify which steps skip as already completed, which step resumes from checkpoint, and reconcile business output against pre-crash data.

## 7. Spring Batch 5.x: Handling Executions Stuck in `STARTED`

In Spring Batch 5.2.x, `JobOperator` provides `stop(long executionId)`, `restart(long executionId)`, and `abandon(long executionId)`, but **does not yet have** 6.x's `recover(JobExecution)`.

```java
// Spring Batch 5.x: execute only when the execution is already in
// FAILED or STOPPED state and eligible for restart.
long newExecutionId = jobOperator.restart(failedExecutionId);
```

If an execution remains `STARTED` after a crash, calling `restart(...)` alone is insufficient. Spring Batch 5.2 documentation requires operators to verify the process is truly dead and manually transition status to `FAILED` when restart data is valid, or `ABANDONED` if abandoning it. A dedicated admin tool should handle **consistent job/step state, transactions, and metadata** via `JobRepository` or a controlled mechanism suited to that version.

Never treat an SQL snippet like this as a complete recovery procedure:

```sql
-- Example of INCOMPLETE operation, do not use as a runbook:
-- UPDATE BATCH_JOB_EXECUTION SET STATUS = 'FAILED'
-- WHERE JOB_EXECUTION_ID = 5100;
```

Updating a single column can leave `ExitStatus`, `StepExecution`, `LAST_UPDATED`, optimistic-locking versions, or `ExecutionContext` inconsistent. For critical production jobs, build and review an admin recovery tool tested against your exact version instead of running ad-hoc DML in production.

**Distinguish `abandon` from `restart`:** `jobOperator.abandon(jobExecutionId)` marks an execution abandoned and **does not make it restartable**. If your goal is resuming unfinished work, do not use `ABANDONED` as an automatic step before `restart`. If reprocessing from scratch with a new instance is required, treat that as an explicit business decision addressing idempotency and existing output.

## 8. Spring Batch 6.x: `JobOperator.recover(...)`

Starting in **Spring Batch 6.0**, the API adds `JobOperator.recover(JobExecution)` to recover an execution stuck in `STARTED` after an abnormal shutdown. The method marks the execution `FAILED` and records a `recovered=true` flag in the execution context to allow restart under the new mechanism.

Illustrative snippet for handling after **confirming** the old process is gone, restart data is valid, and rerunning is safe:

```java
// Example using Spring Batch 6.x API.
// jobExplorer and jobOperator are Spring Batch beans.

JobExecution staleExecution = jobExplorer.getJobExecution(5100L);
if (staleExecution == null) {
    throw new IllegalArgumentException("Execution not found");
}

// This is an impactful administrative operation; invoke only after investigation.
JobExecution recovered = jobOperator.recover(staleExecution);
JobExecution restarted = jobOperator.restart(recovered);

System.out.println("Restarted execution ID: " + restarted.getId());
```

This is not code to run automatically on application startup. Gate it behind authorization controls, verify no live process remains, and ensure only one operator/worker recovers a given execution. You may separate `recover` and `restart` so an operator can confirm the intermediate state.

If an execution is already `FAILED`/`STOPPED`, do not call `recover` by default; use the standard restart path. If metadata is `UNKNOWN` or checkpoints are invalid, do not force a restart by flipping statuses without fixing the underlying issue.

### 8.1. API Differences Between 5.x and 6.x

| Task | Spring Batch 5.2.x | Spring Batch 6.x |
|---|---|---|
| Gracefully stop execution | `JobOperator.stop(long)` | `JobOperator.stop(JobExecution)` (ID overloads may be deprecated). |
| Restart `FAILED`/`STOPPED` execution | `JobOperator.restart(long)` | `JobOperator.restart(JobExecution)` (ID overloads may be deprecated). |
| Recover execution stuck `STARTED` after crash | Controlled operational/admin metadata recovery procedure | `JobOperator.recover(JobExecution)` since 6.0. |
| Abandon execution without restarting | `JobOperator.abandon(long)` | `JobOperator.abandon(JobExecution)` (ID overloads may be deprecated). |
| Dedicated shutdown hook for `JobExecution` | No 6.x `JobExecutionShutdownHook` | `JobExecutionShutdownHook` since 6.0. |

When copying code examples, note package changes in Spring Batch 6.x: `JobExecution` moves under `org.springframework.batch.core.job`; `JobParameters` under `org.springframework.batch.core.job.parameters`. The 5.x line keeps `org.springframework.batch.core.JobExecution` and `org.springframework.batch.core.JobParameters`.

## 9. Designing Jobs to Survive Process Kills

### 9.1. Split Work into Reasonably Sized Chunks

Chunk processing bounds how many items live inside one transaction and creates progress checkpoints. In Spring Batch 5.x:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

`Order` and the reader/processor/writer beans are application classes. Chunk size 100 is only an example; the right size depends on per-item cost, transaction length, locks, DB round trips, and restart requirements. Too large a chunk forces reworking lots of items after a kill; too small increases commit and repository update overhead.

### 9.2. Stateful Readers/Writers Need `ItemStream`

For example, a file reader must track lines/positions read. `ItemStream` implementations can persist checkpoints in the step's `ExecutionContext`. Ensure:

- State saving is enabled on reader/writer (`saveState=true` where supported and desired).
- Streams are properly registered with the step; `ItemStream` delegates hidden inside composites may require `.stream(delegate)`.
- Checkpoint keys remain stable across runs and do not collide when multiple readers/writers share a step.
- Input data stays immutable between initial run and restart; if a file is modified/overwritten, old offsets break.
- With paging, sort keys are unique/stable and re-querying will not drop or duplicate rows on data changes.

`ExecutionContext` helps resume near the saved checkpoint, yet does not automatically prevent duplicate side effects. If the reader read ahead while the writer had not committed, replaying the uncommitted slice is normal and must be handled safely by the writer.

### 9.3. Distinguish Completed Steps from Steps Needing Rerun

On job restart, steps whose prior execution was `COMPLETED` are typically skipped unless `.allowStartIfComplete(true)` is set. Incomplete steps are evaluated by status, restartability, start limit, and flow.

```java
return new StepBuilder("validateInput", jobRepository)
        .tasklet(validateTasklet, transactionManager)
        .allowStartIfComplete(false)
        .build();
```

Here `validateTasklet` is an application bean. This is common when a completed input check can safely be skipped. For steps that must always rerun (e.g., re-verifying a file still exists), set `allowStartIfComplete(true)` intentionally. If `.startLimit(1)` is configured, a previously attempted step may not be allowed to run again; factor start limits into recovery planning.

### 9.4. Design Idempotent Writers

An idempotent writer can receive the same input multiple times without creating unintended duplicate rows or side effects. Common techniques:

- Unique constraints on business keys (such as `businessDate`, `orderId`) to block duplicate inserts.
- Conditional upsert/update with controlled state transitions; understand target database syntax and transaction behavior.
- A `processed_event`/`outbox` table recording event IDs in the same transaction as business changes.
- For external APIs, pass idempotency keys actually enforced by the target service.
- For file outputs, write to a temporary name, complete/flush, then publish/rename using atomic filesystem/storage operations if supported, avoiding blind overwrites.

PostgreSQL example (illustrating duplicate-insert protection only):

```sql
CREATE TABLE imported_order (
    business_date DATE NOT NULL,
    order_id BIGINT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    PRIMARY KEY (business_date, order_id)
);

INSERT INTO imported_order (business_date, order_id, amount)
VALUES (:businessDate, :orderId, :amount)
ON CONFLICT (business_date, order_id)
DO NOTHING;
```

`DO NOTHING` works when an existing record is considered finished and needs no update. If the same key with different values indicates a business error, **do not use `DO NOTHING` to mask discrepancies**; compare contents, versions, or apply explicit reconciliation rules.

## 10. Limits of Exactly-Once with External Side Effects

Spring Batch manages transactions/checkpoints, yet cannot ensure non-database operations commit together unless they join a coordinated transaction.

Example of a step calling a payment API:

```text
1. Read order-25
2. Send charge(order-25) request -> API already charged
3. JVM killed before DB writes processed=true
4. Restart re-reads order-25
5. Send charge(order-25) request again -> risk of double charge
```

To recover properly, the system needs an idempotency contract with the API, such as a stable `paymentRequestId` enforced by the receiver. Adding exception handlers or increasing retries cannot solve a case where an external call **already succeeded before the caller persisted the outcome**.

The *transactional outbox* pattern helps when emitting events after DB updates: write both business state and an outbox row in one transaction; a separate worker dispatches events and marks them sent, while consumers still deduplicate redeliveries. Outbox narrows the gap between DB and messaging yet still needs idempotent consumers; never claim it delivers universal exactly-once guarantees across all systems.

## 11. Preventing Unwanted Kills in Deployment

### 11.1. Kubernetes: `SIGTERM` and `terminationGracePeriodSeconds`

Kubernetes sends termination signals to containers upon pod deletion, and may send `SIGKILL` once the grace period expires. Illustrative pod/job workload:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: order-import
spec:
  backoffLimit: 1
  template:
    spec:
      restartPolicy: Never
      terminationGracePeriodSeconds: 120
      containers:
        - name: batch
          image: example/order-import:1.0
          resources:
            requests:
              memory: 512Mi
            limits:
              memory: 1Gi
```

Image, memory, and timing values here are purely illustrative. `terminationGracePeriodSeconds` provides a **window** for controlled shutdown; it does not guarantee a 30-minute step stops in 120 seconds. If the timeout expires, the container is still killed. On Java, verify shutdown hooks, bean lifecycles, and job-stop mechanisms actually work with container signals and entrypoints.

`backoffLimit`/`restartPolicy` govern **Kubernetes-level** retries, not **Spring Batch-level** `JobExecution` restarts. A fresh pod may relaunch with the same parameters against the same `JobRepository`, colliding with a leftover `STARTED` state. If each pod generates a random identifying `run.id`, duplicate-processing risks grow even higher.

### 11.2. Spring Batch 6.x: Shutdown Hook for Job Executions

Spring Batch 6.0 adds `JobExecutionShutdownHook` to send a stop signal when the JVM exits along a normal shutdown path:

```java
Thread hook = new JobExecutionShutdownHook(jobExecution, jobOperator);
Runtime.getRuntime().addShutdownHook(hook);
```

`jobExecution` is the tracked execution and `jobOperator` is configured. This is a 6.x API example; manage hook registration/deregistration around your launcher's actual lifecycle. Hooks **cannot execute on `SIGKILL`, kernel OOM kills, or JVM crashes that bypass shutdown sequences**. On 5.x, implement shutdown handling suited to your stack; do not copy classes introduced in 6.0.

### 11.3. `JobOperator.stop(...)` Is a Cooperative Stop Request

In Spring Batch 5.x:

```java
boolean requested = jobOperator.stop(jobExecutionId);
// requested == true: signal was sent, does not guarantee job is already STOPPED.
```

The framework needs an opportunity to reach a state-check point to complete stopping. For code making long API calls, configure controlled timeouts, handle cancellation properly, and avoid tight loops that ignore interruption. Once cleanly stopped, persist `STOPPED` along with checkpoints before allowing restarts.

### 11.4. Scheduling and Multiple Replicas

If multiple replicas run `@Scheduled`, each replica can fire simultaneously. `JobRepository` helps reject duplicate concurrent job instances, yet cannot replace full coordination, idempotency, and business locking. After a crash, schedulers may refire against stuck metadata, or spawn new instances if identifying parameters shift.

With Kubernetes `CronJob`, `concurrencyPolicy: Forbid`/`Replace` controls Jobs visible to the controller, **without guaranteeing business-level exactly-once execution**. Combine it with `JobRepository` and deduplication controls.

## 12. Testing Killed-Process Scenarios

### 12.1. Never Kill the JVM Running the Whole JUnit Suite

Calling `System.exit(...)`, `Runtime.getRuntime().halt(...)`, or killing the test-runner JVM PID terminates the entire test run, losing reports and failing the suite. To test real crashes, launch the batch inside **a separate process/container** and kill **only** that test process/container.

Recovery tests typically divide into two tiers:

1. **Standard integration test:** throw an exception in processor/writer so the framework marks `FAILED`; use restart APIs to verify checkpoints and idempotency.
2. **Isolated-process crash test:** forcibly kill the JVM mid-job; read metadata from a durable DB across restarts, apply version-appropriate recovery, and rerun.

Tier 1 validates restart logic under controlled conditions. Tier 2 tests the stale `STARTED` metadata caused by abrupt process loss.

### 12.2. Realistic Kill Test Scenario

Prepare an isolated test environment:

- A test database hosting JDBC `JobRepository` and business tables, surviving across two process lifetimes (do not use in-memory H2 that vanishes when the process dies, unless run as an external H2 server).
- A fixed job `jobName`/identifying `JobParameters`, with restartable reader/writer.
- Enough data or a controlled synchronization point between chunks so you know when the process is actively processing.
- A way to observe at least one committed chunk in the DB along with its output rows.

Suggested scenario:

```text
1. Create a clean test database and load 1,000 records.
2. Launch JVM A with job=importOrders, businessDate=2026-11-16.
3. Wait until several chunks commit and metadata shows STARTED.
4. Send SIGKILL to JVM A (isolated test environment).
5. Confirm JVM A is no longer alive and old connections have closed.
6. Inspect BATCH_JOB_EXECUTION, BATCH_STEP_EXECUTION, context, output rows.
7. Apply recovery appropriate for Spring Batch 5.x or 6.x.
8. Launch JVM B with the same identifying parameters.
9. Verify job finishes, records are accurate, and no duplicates exist.
10. Reconcile JobExecution and StepExecution counts under the same JobInstance.
```

To simulate `SIGKILL` in Linux/container tests, you can use `kill -9 <test-pid>` or `docker kill --signal=KILL <test-container>`, **only when the PID/container belongs strictly to an isolated test environment**. Kill commands should stay outside production Java code and never target production services. In CI, configure timeouts/cleanups so failed test runs do not leak containers or test databases.

### 12.3. Key Assertions After Restart

| Assertion | What It Proves |
|---|---|
| No old process remains | Recovery does not run concurrently with a live worker. |
| `JobInstance` unchanged | Restart uses the right business key rather than creating a new instance to dodge old state. |
| New `JobExecution` created | The rerun is tracked distinctly in the repository. |
| Already `COMPLETED` steps skipped per config | Completed-step side effects are not repeated. |
| Interrupted step receives valid checkpoint | Processing resumes from persisted state. |
| Output rows/files/events match business rules | No dropped records or unintended duplicates. |
| Final `BatchStatus` accurate | Job genuinely completed or failed diagnostically. |

For ambiguous commit outcomes or external side effects, checking `COMPLETED` alone is insufficient; verify idempotency keys, outboxes, and final target data. Crash testing at multiple points (before/during/after commit) exposes risk windows missed by happy-path tests.

## 13. Observability to Detect Executions Hung After Kill

Useful telemetry to log/measure before incidents happen:

| Signal | Purpose |
|---|---|
| `jobName`, approved business keys | Identifies the workload and data period. |
| `jobInstanceId`, `jobExecutionId`, `stepExecutionId` | Correlates logs, metrics, and `JobRepository`. |
| `BatchStatus`, `ExitStatus` | Shows last persisted status. |
| `readCount`, `writeCount`, `commitCount`, `rollbackCount` | Estimates progress recorded in metadata. |
| `LAST_UPDATED` timestamp | Hints when metadata last updated; not proof of process liveness. |
| Application/scheduler-level heartbeat | Separates truly live processes from stale repository records. |
| Pod exit code, OOM events, node status | Classifies abrupt termination causes. |
| DB locks/sessions and external side effects | Assesses safety of rerunning. |

To alert on stuck executions, combine **running status**, **SLA threshold exceeded**, **missing heartbeat**, and **absence of an owning live worker**. Never flip statuses or trigger auto-restarts solely from a query like `STATUS='STARTED' AND LAST_UPDATED < NOW() - INTERVAL '10 minutes'`.

For multi-hour jobs, a slow uncommitted step creates long metadata gaps; an independent heartbeat outside business transactions improves diagnostics. Still, heartbeats need clear lifecycle/ownership rules so another process never writes "alive" after an execution has ended.

## 14. Common Mistakes When Recovering Killed Processes

| Symptom | Possible Cause | Remedy |
|---|---|---|
| Restart throws `JobExecutionAlreadyRunningException` despite dead process | Stale `JobExecution` stuck in `STARTED` | Confirm worker is truly dead, recover metadata per version API/procedure. |
| No `FAILED` status after `kill -9` | JVM had no chance to run cleanup/`finally` | Expected possibility; inspect repository and recover cleanly. |
| Restart spawns another job instance and writes duplicates | Added identifying `run.id`/timestamp to bypass error | Keep same identifying business parameters for restart; enforce idempotency. |
| Job restarts yet reprocesses chunks already sent to API | External side effect not atomic with checkpoint | Use idempotency keys/outbox and business reconciliation. |
| File reader reads from wrong position | Input file changed or `ItemStream`/checkpoint misconfigured | Keep inputs immutable, enable state, verify reader restart. |
| `JobRestartException` after editing metadata | Inconsistent step status/ExecutionContext, non-restartable job, or exceeded start limit | Recover via supported tooling, reconcile metadata and step config. |
| `JobRepository` still shows locks/sessions | DB has not yet detected dead TCP connection, lingering transaction, or another process | Check sessions/transactions and clear via DBA procedure before retrying. |
| A `COMPLETED` step runs again | `allowStartIfComplete(true)` set or different JobInstance created | Check flow, identifying parameters, and step side effects. |
| Marked `abandon` then unable to restart | `ABANDONED` means discarded, not recoverable | Follow `FAILED`/`recover` flow when restarting is the goal. |
| Job passes Java-error tests yet fails after kill | Standard tests hit exception handlers; crashes omit final status | Add isolated-process crash tests against durable DB. |
| Kubernetes spawns new pod yet job stalls | Old process died leaving `STARTED` metadata | Coordinate owner-based recovery before relaunching. |
| Step/job completion logs never appear | `afterStep`/`afterJob` never ran | Rely also on repository, heartbeats, and container log systems. |

## 15. Designing Production Recovery Procedures

A batch platform running long-lived jobs should standardize these decisions before deployment:

1. **Work key:** which job name + identifying `JobParameters` accurately represent the data period, tenant, or input file?
2. **Persistence:** does `JobRepository` use a durable database with the right schema version, accessible after JVM death?
3. **Transactions:** do reader/writer and metadata share an appropriate transaction or exist external side effects?
4. **Checkpoints:** is every reader/writer restartable, is input immutable, and when are positions saved?
5. **Idempotency:** which operations can replay, and where are deduplication keys and reconciliation enforced?
6. **Graceful shutdown:** can `stop` be requested and `STOPPED` awaited within the grace period; which Spring Batch API is used?
7. **Stale executions:** who has authority to verify process death and decide `FAILED` vs. `ABANDONED`?
8. **Version-specific recovery:** 5.x uses controlled metadata admin procedures; 6.x offers `JobOperator.recover` when appropriate.
9. **Scheduler coordination:** how do you prevent firing a new run while an old execution is still running or recovering?
10. **Verification:** after restart, inspect statuses, checkpoints, business metrics, and external side effects.

### Practice Exercises

**Exercise 1 — Comparing exceptions vs. process kill**

- Build a job with a chunk step reading 200 records from a test database and writing to a target table.
- In run A, intentionally throw an exception after a few chunks to observe `FAILED` and normal restart.
- In run B, run the job in a separate JVM and kill it after several chunks commit; observe that status may remain `STARTED`.
- Explain why the two cases require different handling procedures.

**Exercise 2 — Recovering the exact `JobInstance`**

- Choose `businessDate` as an identifying parameter and `triggerSource` as non-identifying.
- Observe an initial run getting killed and recovered; restart with the same `businessDate`.
- Verify `JobInstance` stays unchanged while a new `JobExecution` is created.
- Try adding an identifying `run.id` and analyze the risk of spawning a new instance and losing checkpoints.

**Exercise 3 — Out-of-transaction side effects**

- Simulate a writer calling an external API that succeeds, followed by a crash before persisting `processed=true`.
- Build a stable idempotency key from the business key and verify repeated calls do not duplicate results.
- Contrast with a writer writing solely to the same transactional database.

**Exercise 4 — Recovery runbook**

- Design a checklist of evidence required before declaring an execution dead.
- Compare `FAILED`, `STOPPED`, `ABANDONED`, and `STARTED` when deciding on restart.
- For Spring Batch 6.x, practice `JobOperator.recover(...)` on an isolated test DB; for 5.x, document a controlled metadata admin procedure instead of ad-hoc SQL.
- Write assertions verifying final DB results, not just `BatchStatus.COMPLETED`.

## 16. Official References

- [Spring Batch 5.2 — Advanced Metadata Usage](https://docs.spring.io/spring-batch/reference/5.2/job/advanced-meta-data.html): stopping jobs, `JobOperator`, handling executions after process death, and `ABANDONED`.
- [Spring Batch 6.x — Advanced Metadata Usage](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html): graceful shutdown, `JobExecutionShutdownHook`, and recovery with `JobOperator.recover`.
- [Spring Batch 6.x — `JobOperator` Javadoc](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/launch/JobOperator.html): contracts for `stop`, `restart`, `recover`, and `abandon`.
- [Spring Batch 5.2 — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/restart.html): `startLimit`, `allowStartIfComplete`, and step restart behavior.
- [Spring Batch 5.2 — ItemStream](https://docs.spring.io/spring-batch/reference/5.2/readers-and-writers/item-stream.html): `open`, `update`, `close`, `ExecutionContext`, and checkpoints.
- [Spring Batch — What's New in Version 6](https://docs.spring.io/spring-batch/reference/whatsnew.html): graceful shutdown support added in 6.0.

