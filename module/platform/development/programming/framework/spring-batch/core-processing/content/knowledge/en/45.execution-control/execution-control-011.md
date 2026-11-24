# Never Kill a Process Mid-Critical Write in Spring Batch

## 1. The Problem: Stopping a Batch Job Without Corrupting Data

In **Spring Batch Core Processing**, a job may be writing payment data, updating millions of records, generating report files, or sending messages to another system. When deploying a new release, performing host maintenance, reclaiming a pod, or canceling an erroneous run, **killing the process immediately** can strike right when an important write operation (*critical write*) is underway.

Typical consequences:

- The database committed business data, yet batch progress was not fully recorded.
- An external API already processed the transaction, while the JVM was stopped before receiving and saving the response.
- A half-written export file was picked up by another system as if it were complete.
- An uncommitted chunk rolled back; upon restart it is reprocessed, causing duplicate side effects if the writer is not idempotent.
- Metadata in `JobRepository` stays stuck at `STARTED` because the process vanished without updating its final status.

The operational principle is: **request a controlled job stop, wait for a safe write boundary, confirm persisted status, and only then terminate the process**. At the same time, the system must remain recoverable if the JVM is still forcibly terminated due to hardware failure, power loss, `SIGKILL`, or grace-period expiration. No application-level mechanism can guarantee the operating system will never terminate a process during a critical write.

In the **Execution control** chapter, the goal is not merely knowing which command stops a job, but designing transaction boundaries, stop signals, timeouts, and restart strategies to preserve accurate business outcomes.

## 2. What Is a Critical Write?

A **critical write** is a processing region where interrupting at the wrong instant can leave state written across one or more systems inconsistent with the actual outcome of the work.

Example in a settlement job:

```text
ItemReader
   |
   v
ItemProcessor
   |
   v
ItemWriter
   |
   +-- INSERT payment_ledger into DB ---------+
   |                                          |
   +-- UPDATE transaction_status -------------+-- critical write
   |                                          |
   +-- Send request to payment service -------+
   |
   v
Update Batch metadata / checkpoint
```

The risk depends on **which system owns the commit**, not just on lines of code. Two SQL statements on the same connection and transaction commit or roll back as one unit. By contrast, an HTTP request does not automatically roll back with a JDBC transaction.

| Write Type | Safe Boundary You Can Rely On | Risk If Process Dies Mid-Flight |
| --- | --- | --- |
| Writing to one database in a transaction | Transaction committed or rolled back; outcome may still need verification | Client does not know if commit succeeded; next run may replay |
| Writing to multiple independent databases | No single atomic commit by default | DB A committed while DB B did not |
| Calling a payment HTTP/API | Downstream outcome and API idempotency key | API succeeded, but caller died before saving state |
| Publishing to Kafka/RabbitMQ | Broker acknowledgment and broker transactions if enabled | Sent without receiving ack; retry republishes |
| Writing export report files | Complete temp file, closed handle, published via rename/manifest | Consumer reads partial file, or file published before checkpoint saved |
| Writing to object storage | Upload completed and object/manifest published | Incomplete upload or duplicate object created on retry |

Hence, "never kill mid-critical write" has two layers:

1. **Execution control:** proactively defer stopping until the batch passes a safe boundary.
2. **Data correctness:** design writes with transactions, idempotency, and reconciliation so recovery still works after an abrupt stop.

You cannot replace the second layer with a promise that "operations will never kill mid-flight."

## 3. Distinguishing Stop, Graceful Shutdown, and Kill

| Action | How It Works | What It Guarantees |
| --- | --- | --- |
| Stop request via `JobOperator.stop(executionId)` | Flags a stop request; Spring Batch and steps cooperate to stop where signals are checked | Gives the job a **chance** to finish active work and transition status |
| Application/JVM graceful shutdown | Process receives termination signal, running shutdown lifecycles/hooks within allowed limits | Can clean up resources if timeouts and lifecycles are configured properly |
| `SIGTERM` on Linux | Asks the process to exit; JVM typically initiates standard shutdown | Not automatically equivalent to `JobOperator.stop`; does not guarantee jobs/chunks finished |
| `SIGKILL` / forced kill | OS terminates the process without running JVM cleanup | Skips `finally` blocks, shutdown hooks, and application cleanup |
| Force-deleted Pod, host power loss | Process vanishes unexpectedly | Only data confirmed by durable storage systems can be trusted |

A stop request is **not** confirmation that the job has stopped. For instance, `JobOperator.stop(123L)` can return once the request is dispatched, while `JobExecution` remains `STOPPING` or `STARTED` and the writer is still running.

Distinguish common statuses:

- `STARTED`: batch is executing according to persisted metadata.
- `STOPPING`: stop has been requested, but stopping has not finished yet.
- `STOPPED`: job stopped via controlled mechanisms, potentially eligible for restart if configuration allows.
- `COMPLETED`: job finished normally; not a "stop" needing restart.
- `FAILED`: execution ended due to an error; restartable if the job/step is designed as restartable.
- `UNKNOWN` or metadata stuck in `STARTED` after a crash: investigate real state before deciding to proceed.

**Note:** status in `JobRepository` is observational data, not an absolute lock against external kills. If a node dies, the process has no way to write `FAILED` or `STOPPED`.

## 4. Chunk Transactions Are Natural Stop Boundaries

In a Spring Batch chunk-oriented step, reader/processor assemble a group of items; the writer persists them within the chunk's transaction. When the transaction succeeds, business data and the corresponding checkpoint state commit according to repository and transaction manager settings.

```text
Chunk #1
  READ -> PROCESS -> WRITE -> COMMIT   [safe boundary]

Chunk #2
  READ -> PROCESS -> WRITE -> COMMIT   [safe boundary]

Chunk #3
  READ -> PROCESS -> WRITE -> COMMIT   [safe boundary]

                     ^ stop request arrives during WRITE of Chunk #2
                     |
                     +-- job needs a chance to finish current chunk,
                         persist status, and only then stop
```

For standard chunk steps, Spring Batch checks the stop signal at appropriate orchestration points. A stop request normally does not sever an active SQL statement mid-flight. However, **do not assume every active write is guaranteed to commit**: connection timeouts, rollbacks, exceptions, JVM shutdown, and non-transactional resources can still intervene.

Step configuration example in Spring Batch 5.x:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step persistPaymentsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Payment> reader,
        ItemProcessor<Payment, Payment> processor,
        ItemWriter<Payment> writer) {

    return new StepBuilder("persistPaymentsStep", jobRepository)
            .<Payment, Payment>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

Here `Payment` is an illustrative application model. This configures a chunk of 100 items (except the final chunk) and wraps chunk processing in a transaction boundary. To protect the writer's SQL writes, the writer must use a **`DataSource` and transaction manager wired into the step's transaction**. If the writer calls a second database or an external API, the step transaction does not automatically make those operations atomic together.

**Choosing chunk size is a trade-off:**

- Larger chunks can reduce commit overhead, but lengthen how long you must wait to stop safely.
- Smaller chunks surface stop checks more frequently, yet increase transaction overhead.
- A writer spending minutes on a single I/O call will still make graceful stop slow even with a tiny chunk size.

Measure the **longest chunk duration under realistic load** rather than inferring stop time from item counts.

## 5. Safe Application-Layer Job Stop Procedure

An appropriate operational sequence for a batch handling critical business work:

1. **Block new execution starts:** stop schedulers/launchers from dispatching new jobs or put the instance into drain mode.
2. **Identify running executions:** obtain `executionId` and inspect `JobRepository` or `JobExplorer`.
3. **Send stop through Spring Batch:** call `JobOperator.stop(executionId)` while the JVM running the execution is still alive.
4. **Wait for confirmation:** watch status transition from `STARTED`/`STOPPING` to `STOPPED`, or `COMPLETED` if the job finishes in time; handle `FAILED` per incident procedures.
5. **Verify critical writes passed durable boundaries:** no transactions remain open, partial files are unpublished, outbox/operation state is consistent.
6. **Shut down the process gracefully:** only after no execution remains active should the scheduler/container/service exit.
7. **Record operational audit trail:** save requester/actor, timestamp, execution ID, stop outcome, and restart decision.

Example calling Spring Batch's admin API (Spring Batch 5.x):

```java
import org.springframework.batch.core.launch.JobOperator;

public class BatchStopService {

    private final JobOperator jobOperator;

    public BatchStopService(JobOperator jobOperator) {
        this.jobOperator = jobOperator;
    }

    public void requestStop(long executionId) throws Exception {
        // Sends stop request; cannot assume job is already STOPPED.
        jobOperator.stop(executionId);
    }
}
```

This assumes the context provides a properly configured `JobOperator`. In real applications, admin controllers/CLIs need authentication, authorization, and auditing. Never expose stop actions on an unprotected HTTP endpoint.

A simple observation loop using `JobExplorer`:

```java
JobExecution execution = jobExplorer.getJobExecution(executionId);
if (execution == null) {
    throw new IllegalArgumentException("Unknown execution: " + executionId);
}

BatchStatus status = execution.getStatus();
// STOPPED or COMPLETED: job ended according to observable metadata.
// STOPPING/STARTED: keep observing; not yet considered stopped.
// FAILED/UNKNOWN: transition to investigation, reconciliation, and recovery.
```

The polling loop needs an **operational deadline**, logging, and a fresh read from the repository on each check. Do not keep reusing a previously fetched `JobExecution` object because its in-memory fields will not update automatically. Nor should you busy-wait in a tight spin loop.

If the program is a CLI batch that runs one job and exits immediately, stopping from another admin JVM only helps if the running execution can actually receive and process the stop request. Design a real control channel before relying on that API call.

## 6. When You Must Stop Inside a Very Long Writer

Not every step has short chunks. A tasklet might generate a multi-GB file or a writer might wait on a slow network call. Waiting for a chunk boundary may then exceed the grace period.

Design approaches:

- **Break work into small checkpoints:** split a protracted critical write into units with explicit transactions and completion states.
- **Set intentional timeouts:** HTTP clients, JDBC sockets/queries, and I/O operations must have proper timeouts; timeouts must not be shorter than valid processing time for a unit of work.
- **Check stop signals at safe points:** inside long loops, halt only after completing or rolling back one write unit.
- **Do not blindly swallow `InterruptedException`:** when interrupted, handle it per the resource's contract and preserve the interrupt flag if that layer cannot finish cleanly.
- **Track durable state per unit:** identify which operations committed, which are pending, and which need reconciliation.

For example, a file-generating tasklet in a loop should not check for stop only at the end of a multi-hour file. It can write checkpointed blocks, stage an unpublished temp file, and expose the file to consumers only once complete.

Not every `Thread.interrupt()` safely aborts a SQL statement or HTTP call. Exact behavior depends on drivers, clients, transactions, and timeouts. **Never rely on forced thread interruption as an atomicity mechanism.**

## 7. Protecting Critical Database Writes

### 7.1. Group Related Changes in One Transaction

For a payment event, business logic may need to insert a ledger entry and mark the request processed:

```sql
BEGIN;

INSERT INTO payment_ledger (operation_id, account_id, amount)
VALUES (:operationId, :accountId, :amount);

UPDATE payment_request
SET status = 'POSTED'
WHERE operation_id = :operationId;

COMMIT;
```

This illustrates two statements on the **same database and same transaction**. If the connection drops before commit, the database rolls back the uncommitted transaction. Yet if the process dies right after the database commits and before the client receives confirmation, the client cannot tell whether the command succeeded.

Thus, **"transactional" and "idempotent" solve two distinct problems**:

- Transactions ensure changes within the same scope commit or roll back atomically per database rules.
- Idempotency ensures that replaying the same valid request does not apply the business effect a second time.

### 7.2. Use Business Keys to Allow Safe Retries

PostgreSQL example:

```sql
CREATE TABLE payment_ledger (
    operation_id VARCHAR(100) PRIMARY KEY,
    account_id   VARCHAR(100) NOT NULL,
    amount       NUMERIC(18, 2) NOT NULL
);
```

The writer might receive a replayed event after restart:

```sql
INSERT INTO payment_ledger (operation_id, account_id, amount)
VALUES (:operationId, :accountId, :amount)
ON CONFLICT (operation_id) DO NOTHING;
```

A unique constraint provides a guardrail against duplicate writes, even if two workers try inserting concurrently. However, `DO NOTHING` will not detect an existing `operationId` being resent with a different `amount`. If that represents a business conflict, compare payloads and fail/quarantine instead of silently ignoring it.

Example `ItemWriter` using `JdbcTemplate`, suited for Spring Batch 5.x:

```java
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@Bean
ItemWriter<Payment> paymentWriter(JdbcTemplate jdbcTemplate) {
    return chunk -> {
        for (Payment payment : chunk) {
            jdbcTemplate.update("""
                    INSERT INTO payment_ledger
                        (operation_id, account_id, amount)
                    VALUES (?, ?, ?)
                    ON CONFLICT (operation_id) DO NOTHING
                    """,
                    payment.operationId(),
                    payment.accountId(),
                    payment.amount()
            );
        }
    };
}
```

This assumes `Payment` is a Java record with three matching accessors and PostgreSQL is the database. Wire `JdbcTemplate` into the step's transaction. When inspecting `StepExecution.getWriteCount()`, never assume it equals the count of **new** rows in the ledger: the writer may have processed items that the database skipped due to key conflicts.

### 7.3. Commit Boundary with JobRepository

Spring Batch updates checkpoint metadata and counters through `JobRepository`. Under standard configuration, the framework coordinates those updates with the chunk transaction; yet consistency depends on the actual configuration of `DataSource`, `PlatformTransactionManager`, and transaction participation.

If business writes target DB A while batch metadata lives in DB B, you cannot assume both commit atomically merely because they run in the same step. When fault tolerance across two datastores is needed, design retries/idempotency and reconciliation, or adopt a proven transaction-coordination strategy.

## 8. Critical Writes with External Side Effects: Outbox and Idempotency Keys

Suppose a writer saves a result to the database and calls a money-transfer API:

```text
BEGIN DB TRANSACTION
  INSERT payment_result
  HTTP POST /transfer
COMMIT DB TRANSACTION
```

This design is fragile. The API might transfer funds while the database rolls back. Or the database commits and the process dies before saving the response. Spring Batch cannot automatically roll back an HTTP transaction executed on another system.

### 8.1. Transactional Outbox

A widely used pattern:

```text
Spring Batch chunk transaction
    |
    +-- INSERT business_result --------------+
    |                                        |  COMMIT in same DB
    +-- INSERT outbox_event -----------------+
                                                  |
                                                  v
                                         Outbox dispatcher
                                                  |
                                                  v
                                         External API / Broker
                                                  |
                                                  v
                                         Mark delivered / retry
```

Business rows and outbox rows are saved in the **same transaction**. A separate worker dispatches outbox events externally. If that worker dies after sending but before marking delivered, it may resend after restarting. Therefore, the receiving consumer/API must process using a durable **idempotency key**.

Example outbox table:

```sql
CREATE TABLE payment_outbox (
    event_id      VARCHAR(100) PRIMARY KEY,
    operation_id  VARCHAR(100) NOT NULL,
    payload       JSONB NOT NULL,
    status        VARCHAR(20) NOT NULL DEFAULT 'PENDING'
);
```

`event_id` should be derived deterministically from the operation being sent, or saved when the business transaction is first created. Never generate a fresh random UUID on every retry of the **same event**, or downstream receivers cannot recognize duplicates.

A consumer can store `idempotency_key` alongside its processing outcome in its own database and reject duplicate effects. This achieves **effectively-once business outcomes** over at-least-once delivery; never claim that using an outbox alone guarantees single-delivery at the network layer.

### 8.2. An API Timeout Does Not Mean Failure

When an HTTP client times out, at least two possibilities exist:

1. The request never reached the server or the server did not execute it.
2. The server executed it successfully, but the response arrived late or was lost.

In case (2), retrying with a new operation ID can create a duplicate transaction. Resend with the **same idempotency key**, query the outcome if the API supports lookup, and mark final failure only with proof. Safe stopping must also allow operations in an "unknown outcome" state to be persisted and reconciled.

## 9. Safe File Writes: Never Publish Partial Files

For jobs exporting CSV/JSON/report files, consumers may watch the output directory while the writer is still writing. If the writer writes directly to `report.csv`, killing the process can leave a file with the official name containing only partial data.

A safer workflow:

```text
1. Create report-<jobKey>.csv.tmp
2. Write full content to the temp file
3. Flush and sync to storage if strict durability is required
4. Close the write handle
5. Publish via atomic rename/move when the filesystem supports it
6. Persist a durable manifest/checkpoint
7. Allow consumers to read only finalized filenames or manifested outputs
```

Java example:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public void publishReport(Path outputDirectory, String content)
        throws IOException {

    Path temp = Files.createTempFile(
            outputDirectory, "report-", ".tmp");
    Path finalFile = outputDirectory.resolve("report.csv");

    try {
        Files.writeString(temp, content, StandardCharsets.UTF_8);

        // Example requiring atomic move; do not silently fall back to
        // non-atomic move if the contract requires atomic publication.
        Files.move(temp, finalFile, StandardCopyOption.ATOMIC_MOVE);
    } catch (AtomicMoveNotSupportedException unsupported) {
        // Choose an alternative publication strategy fitting the filesystem.
        throw unsupported;
    } finally {
        // If move succeeded, temp no longer exists; if it failed, clean up temp file.
        Files.deleteIfExists(temp);
    }
}
```

This snippet illustrates **publication via atomic move**, not a complete solution for durability, filename collisions, or concurrent writers. `Files.writeString` closes the file after writing, yet does not guarantee data is `fsync`ed to physical media by default. Power-loss-resilient systems need `FileChannel.force(...)`/directory sync per OS and filesystem capabilities; on network filesystems or object storage, rename semantics may differ.

Also consider crashing **after rename succeeds but before checkpointing**. A restart could regenerate the file. Therefore:

- Name final files from stable business keys / job instances.
- Do not overwrite an already-published file unless the contract permits it.
- Store checksums, record counts, and status manifests for reconciliation.
- Have the restart step verify whether the output already completed before rewriting.

If using Spring Batch's `FlatFileItemWriter`, study how it stores state in `ExecutionContext` and its append/restart policies. Writer restartability and **publishing files to consumers** are two distinct responsibilities to design separately.

## 10. Kubernetes and Time for Graceful Termination

A pod being deleted or replaced receives a termination request. Kubernetes gives containers a grace period; once expired, the runtime can forcibly kill remaining processes.

Example configuration:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: payment-batch
spec:
  terminationGracePeriodSeconds: 180
  containers:
    - name: batch
      image: your-registry/payment-batch:version
```

`180` seconds is merely an **example**, not a universal recommendation for every job. Base the grace period on measured stop times, commit/rollback times, and valid dependency timeouts. For a chunk that can take 10 minutes, setting 180 seconds does not guarantee the chunk completes.

### 10.1. Draining Before the Pod Stops

A production system should follow a drain sequence:

```text
Deployment/Operator requests drain
      |
      v
Prevent scheduler from assigning new jobs
      |
      v
Send stop to active executions
      |
      v
Observe JobRepository + actual write status
      |
      v
Reach safe boundary (STOPPED/COMPLETED)
      |
      v
Allow pod to exit gracefully
```

Drain control can be implemented via a dedicated operator, internal admin tooling, or a `preStop` hook. However, **`preStop` runs within the grace-period budget** and only helps if the endpoint/hook genuinely waits until writes are safe. If the hook only calls "request stop" and returns immediately, the container can still receive the kill signal before the chunk finishes.

Conceptual hook example:

```yaml
lifecycle:
  preStop:
    exec:
      command:
        - /bin/sh
        - -c
        - "curl --fail --silent http://127.0.0.1:8080/internal/batch/drain"
```

This only works when the image includes `/bin/sh` and `curl`, the app exposes a secured internal endpoint, and `/internal/batch/drain` **returns success only after jobs have stopped safely**. Account for timeouts, authentication, calling the endpoint during shutdown, and fallback behavior if the endpoint fails to respond. `preStop` is not a final shield against node failures or forced kills.

### 10.2. Spring Boot Graceful Shutdown Does Not Automatically "Drain" Every Batch Job

In Spring Boot you can configure:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=180s
```

This helps manage shutdown lifecycles of supported components, especially the web server. It **does not automatically turn every running `JobExecution` into `STOPPED`** or make an HTTP writer atomic. A batch deployment needs explicit integration to stop accepting new jobs, request stops, wait for writers/steps at safe points, and then shut down the JVM.

Never use a liveness probe as a routine business job-cancellation mechanism: probes can restart a container right in the middle of a critical write. Readiness, liveness, and stop conditions must be tailored to the process's role.

### 10.3. Other Platforms

On VMs or systemd services, the principle is identical: before stopping the service, drain the scheduler, request stop, and wait for termination. On Windows services, handle Windows service lifecycle signals rather than assuming POSIX `SIGTERM`. On every platform, establish timeouts and procedures for when a job fails to stop safely within the budget.

## 11. If the Process Still Gets Killed: Recovering After a Crash

No graceful strategy eliminates every infrastructure failure. A difficult scenario:

```text
T0: Step begins chunk #8
T1: Writer sends commit to database
T2: Database commit succeeds
T3: JVM receives SIGKILL before receiving ack and fully persisting status
T4: System restarts job
```

At T4, you cannot conclude the transaction rolled back just because the earlier client received no response. **The outcome may be uncertain.**

Recovery should rely on durable evidence:

1. Confirm the old process is truly gone so two workers never process the same job.
2. Inspect `JobRepository`, `JobInstance`/`JobExecution` state, and saved checkpoints.
3. Inspect business data by `operationId` or idempotency key, comparing against expected outcomes.
4. Check non-database side effects: pending outbox rows, processed API transactions, published files, dispatched messages.
5. If metadata is stuck in `STARTED` after a crash, follow a **project-verified recovery procedure** to reconcile status before restarting; never edit `BATCH_*` tables arbitrarily.
6. Restart the **same job instance** when resuming from a checkpoint, or create a new execution per business rules when re-running from the start.
7. Confirm final data has no duplicates and record investigation findings.

### Why Not Just Re-Run with a New `run.id`?

A `JobInstance` is identified by job name plus **identifying JobParameters**. Adding a new `run.id` usually creates a new instance; it is not equivalent to restarting from the failed run's checkpoint.

If the job's reader saves `ExecutionContext`, restarting the right instance lets it resume from saved state. Still, the reader may replay a portion of records, especially when external side effects are outside the transaction. Checkpoints and idempotency **complement each other**.

## 12. Preventing Duplicate Runs When an Old Process Is Not Fully Dead

An unsuccessful drain can lead to this scenario:

```text
Worker A: processing operation 123, temporarily loses network
Orchestrator: assumes A is dead
Worker B: starts processing operation 123
Worker A: network recovers, continues writing
```

Heartbeats or timeouts alone may not suffice. For operations that must never run concurrently, combine:

- **Unique constraints / idempotency keys** at the final effect sink.
- **Distributed leases/locks** with expiry and controlled renewal.
- Monotonically increasing **fencing tokens** so downstream sinks reject stale writers after ownership moves to a new worker.
- **Single active execution policies** or job-level locks stored in reliable infrastructure.

A lease can expire while a process pauses due to long GC or network stalls. If the old worker then resumes writing, a mere "lease expired" flag in the controller may not stop it. Fencing tokens must be **validated by the resource receiving the write** to block a writer that lost ownership.

Spring Batch manages job metadata and state, yet cannot replace distributed synchronization for every external resource.

## 13. Designing Tests for Stopping Safely Around Critical Writes

An integration test that only runs a job to `COMPLETED` does not verify stop safety. Simulate controlled interruptions:

| Test Case | Stop/Failure Point | Expectation |
| --- | --- | --- |
| S01 | Stop while job is reading items | Job reaches `STOPPED` without corrupting output |
| S02 | Stop while writer executes a chunk | Current chunk completes or rolls back per contract; no partial data |
| S03 | Stop after DB commit before application logs ack | Retry/restart creates zero duplicates by business key |
| S04 | HTTP service succeeds but response is lost | Resending same idempotency key causes no second effect |
| S05 | Crash before final file publication | Consumers never see a partial file under the final name |
| S06 | Crash after publishing file before checkpoint | Recovery detects existing file and checks checksum/manifest |
| S07 | Restart same `JobInstance` | Processes only remaining work or replays safely; no duplicated results |
| S08 | Grace period shorter than valid writer duration | Clear alert and reconciliation path; never assumes stop completed |
| S09 | Two workers contend for one operation | Only one business effect commits |

### Using Latches to Set Deterministic Stop Points

Instead of calling `Thread.sleep(500)` hoping the job happens to be inside the writer, build a test writer wrapper with `CountDownLatch`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriter;

final class BlockingWriter<T> implements ItemWriter<T> {

    final CountDownLatch enteredWrite = new CountDownLatch(1);
    final CountDownLatch allowWriteToContinue = new CountDownLatch(1);

    private final ItemWriter<T> delegate;

    BlockingWriter(ItemWriter<T> delegate) {
        this.delegate = delegate;
    }

    @Override
    public void write(Chunk<? extends T> chunk) throws Exception {
        enteredWrite.countDown();

        if (!allowWriteToContinue.await(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Writer was not released");
        }

        delegate.write(chunk);
    }
}
```

In the test, launch the job with an **asynchronous** launcher so the test thread keeps control. Wait for `enteredWrite`, call `jobOperator.stop(executionId)`, then release `allowWriteToContinue`. Monitor execution until terminal status and assert business data.

```text
Test thread                         Job thread
-----------                         ----------
launch async ---------------------> read/process
await enteredWrite                 enter writer; signal latch
request stop                       wait allowWriteToContinue
release writer -------------------> finish writer/commit or rollback
poll status                        observe stop at safe point
assert output and checkpoint
```

This is a **test synchronization technique**, not a writer for production. Never await a latch unboundedly; set a timeout and always release in `finally` so the test suite cannot hang. To simulate real process loss, run the test in a **separate process/container** against an external test database; throwing an exception inside the same JVM cannot fully simulate killing a process.

For forced-kill cases, tests must recognize possible outcome states (uncommitted, or committed with lost ack) and verify that reconciliation/idempotency still converges to a single business result.

## 14. Monitoring and Operational Runbooks

To decide whether a process can safely exit, operators need multi-layer visibility:

| Signal | Operational Value |
| --- | --- |
| `jobExecutionId`, `jobName`, `JobParameters` | Pinpoints the exact run being stopped |
| `BatchStatus` and last update timestamp | Tracks stop progress, spots potentially stuck executions |
| Current Step and active chunk | Estimates wait time until a safe boundary |
| Chunk duration p95/p99 and max | Grounds grace periods in real measurements |
| Open transactions and commit errors | Detects slow or abnormal writes |
| Counts of `PENDING`, `IN_PROGRESS`, `COMMITTED` operations | Identifies work not yet durably confirmed |
| Outbox queue depth and publish lag | Tracks external side effects still pending completion |
| Temp/final/manifest files | Separates files in progress from published files |
| Retry rate and duplicate-key hits | Surfaces replays, races, or broken recovery |

A runbook can specify:

**Before maintenance:** prevent scheduler from dispatching new jobs, issue stop, wait for all executions to reach `STOPPED` or `COMPLETED`; note any pending operations.

**If deadline expires:** inspect stuck steps, I/O timeouts, and transaction state; evaluate whether to extend waiting or proceed to crash recovery. Never automatically treat `STOPPING` as "safe to kill."

**Once the process is gone:** reconcile database, outbox, output files, and metadata. Restart only after confirming no old process retains execution ownership over the workload and unknown outcomes are resolved.

In production, any "Force stop" button should require explicit authorization and audit logging. Operators should see clear warnings about executions with in-flight writes, not merely a generic "Running" label.

## 15. Common Misconceptions

### "Sending SIGTERM Is Completely Safe"

`SIGTERM` gives the JVM a chance to shut down, yet code may not have received a Spring Batch stop signal, a writer may be waiting on I/O, and the grace period may expire. You need an explicit drain/job-stop flow plus crash-recovery capability.

### "Just Use `@PreDestroy` to Commit Transactions"

`@PreDestroy` and shutdown hooks do not run on `SIGKILL`, process crashes, or power loss. Nor should you start new business transactions during shutdown just to mask an incomplete write. Transactions and idempotency belong in the normal processing flow.

### "Enabling Retry Guarantees Zero Data Loss"

Retries can **duplicate side effects** if an operation succeeded without the caller knowing. Retries must be paired with idempotency keys or reliable reconciliation.

### "JobRepository Still Shows `STARTED` So the JVM Must Be Running"

An abrupt process death can leave metadata at `STARTED`. Verify actual process liveness, leases/ownership, and restart conditions; never infer reality solely from a stale status column.

### "JobRepository Checkpointed, So External Writes Must Be Consistent"

Checkpoints track batch progress. An HTTP call, file rename, or message publish has its own commit/ack lifecycle. Ensure idempotency or an outbox at every integration boundary.

### "Change `run.id` to Restart Faster"

A new `run.id` usually creates a new `JobInstance`, risking reprocessing all data. When resuming from a checkpoint, use the proper restart mechanism with the same instance and identifying parameters.

### "Ignore All Duplicate Key Errors and Move On"

Key collisions can be benign replays or serious data conflicts. Skip only when the contract allows and payloads match; otherwise fail or quarantine.

### "Setting Chunk Size = 1 Eliminates Critical Writes"

Tiny chunks shorten average transaction duration, yet can still be killed right at commit time. A single item making a 30-second API call is still a long critical write, and crashing after commit before ack can still occur.

## 16. Practice Exercises

**Exercise 1 – Controlled stop.** Create a Spring Batch job with `chunk(10)`, a JDBC writer, and 100 items. Launch asynchronously and call `JobOperator.stop(executionId)` after confirming the writer entered a chunk. Measure time from stop request to `STOPPED`, and verify record counts and checkpoint state.

**Exercise 2 – Unknown commit.** Design a writer using `operationId` as a unique key. Simulate a commit succeeding while the caller misses the ack. Re-run the same operation, assert the ledger table still contains one row, and check that the payload was not altered.

**Exercise 3 – Partial file.** Write reports to a `.tmp` file and publish via rename only upon completion. Simulate an exception mid-write; verify consumers never see a final-named file with partial data. Test crashing after publication and design a restart rule to recognize already-completed files.

**Exercise 4 – Grace period.** Measure the longest writer/chunk duration in a load test and compare it with your configured `terminationGracePeriodSeconds`. Design a drain path so the process exits only when no protected write remains; describe fallback behavior if the grace period expires.

**Exercise 5 – External API.** Send an event via an outbox; simulate a failure after the consumer succeeds but before the dispatcher marks it delivered. Replay the event with the same idempotency key and verify only one business effect is recorded.

**Exercise 6 – Restart.** Fail a job after several chunks commit. Keep `JobRepository` metadata intact; restart the exact job instance, verify zero duplicate writes, and check final output matches a clean end-to-end run.

## 17. Key Takeaways

**Never killing a process mid-critical write** starts as an execution-control discipline: stop accepting new work, ask Spring Batch to stop, wait for stopped status and safe commit boundaries, and only then terminate the JVM/container. That discipline must be backed by fault-tolerant design: **properly scoped transactions, idempotency keys, checkpoints, outboxes or atomic file publication, plus reconciliation and restart runbooks**. That way, even if a process is forced down at the worst possible moment, the system can still determine what was persisted and finish the job without duplicating business effects.

### References

- [Spring Batch Reference — Job](https://docs.spring.io/spring-batch/reference/job.html)
- [Spring Batch Reference — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html)
- [Spring Batch Reference — JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html)
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html)
- [Kubernetes — Pod Lifecycle and Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination)
- [Spring Boot Reference — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html)
