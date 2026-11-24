# Commit Failures in Spring Batch: Causes, Impact, and Recovery

## 1. Why Is a Commit Failure More Dangerous Than an Ordinary Item Processing Error?

In Spring Batch, a **chunk-oriented** Step typically reads multiple items, transforms them, writes the output, and then requests the transaction to **commit**. When a processor throws an exception before writing, the application usually knows which item failed. When an error happens **right at commit time**, the more critical question is:

> Has the data been durably confirmed by the database, and does Spring Batch's checkpoint accurately reflect that state?

For example, a job importing 10,000 orders with `chunk(100)`:

~~~text
Read O001 ... O100
       |
       v
Process, validate
       |
       v
Writer INSERT into database
       |
       v
COMMIT transaction
       |
       +--- Succeeded ----------> Checkpoint confirmed
       |
       +--- Error before commit -> Rollback if transaction still usable
       |
       +--- Connection lost at COMMIT
                |
                +--> DB did not commit?
                |
                +--> DB committed, but ACK lost?
~~~

On the last branch, the application may receive only a communication exception and **cannot tell whether the actual commit succeeded or failed**. Rerunning blindly with `INSERT` risks duplicates or unique constraint errors. Ignoring the error risks missing data.

**Commit failure** belongs to **Failure recovery** because it imposes three simultaneous requirements:

1. **Determine transaction status:** confirmed rollback, confirmed commit, or unknown outcome.
2. **Assess durable state:** actual output, metadata, and checkpoints.
3. **Recover safely:** ability to restart/reprocess without dropping records, writing duplicates, or repeating side effects.

Never equate an exception thrown during `commit()` with certainty that the transaction rolled back.

## 2. Transaction Boundaries of a Chunk

In chunk-oriented processing, Spring Batch organizes reading, processing, and writing into transactional units:

~~~text
StepExecution
   |
   +-- Chunk #1
   |     Begin transaction
   |     Reader:    items 1..100
   |     Processor: transform / filter
   |     Writer:    write data
   |     ItemStream.update(ExecutionContext)
   |     Update StepExecution / checkpoint metadata
   |     Commit transaction
   |
   +-- Chunk #2
   |     Begin transaction
   |     Reader:    items 101..200
   |     ...
   |
   +-- Chunk #N
         ...
~~~

This is a high-level view: exact ordering and metadata synchronization depend on the Step implementation and transaction infrastructure. Under standard configuration, the framework updates Step state and `ExecutionContext` at checkpoint boundaries. However, **atomicity between business data and Batch metadata can only be expected when those operations genuinely participate in the same transaction/resource**.

Components involved:

| Component | Responsibility |
|---|---|
| `PlatformTransactionManager` | Begins, commits, and rolls back the Step's transactions |
| `ItemReader` | Reads input; may maintain position/state across chunks |
| `ItemProcessor` | Transforms, filters, or raises business errors |
| `ItemWriter` | Writes output to DB, files, or external systems |
| `ItemStream` | `open`, `update`, `close` for restartable state |
| `ExecutionContext` | Persists checkpoints and values needed for recovery |
| `StepExecution` | Read/write/skip counters, status, and metadata for a Step run |
| `JobRepository` | Persists JobInstance, JobExecution, StepExecution, and ExecutionContext |

When the writer uses a **JDBC datasource sharing the same transaction manager** as the Step, the writer's INSERT/UPDATE operations can roll back with the chunk transaction. Conversely, an HTTP request, sent email, published message, or written file typically **does not roll back automatically** when Spring Batch rolls back the database transaction.

### Distinguishing a Successful Write from a Successful Commit

A `jdbcTemplate.update(...)` call returning affected row counts means the database executed the statement inside the current transaction; **it does not guarantee the change has committed**. A writer can finish writing 100 items and then fail during commit.

Similarly, `writeCount` reflects Step tracking mechanics, not independent proof that 100 records are durably stored across all external systems. When investigating commit failures, inspect actual target data alongside metadata and transaction state.

## 3. Types of Failures at Commit Time

| Situation | What the Application Typically Sees | Data State | Handling Direction |
|---|---|---|---|
| Validation or constraint detected before commit | Exception from writer/flush | Transaction can usually roll back | Fix data or apply appropriate skip/retry policy |
| Transaction marked rollback-only | `UnexpectedRollbackException` or related exception | Cannot commit as expected | Find what marked rollback-only earlier |
| Deadlock/serialization conflict rejected by database | Transaction/concurrency exception | Transaction aborted or rolled back by DB | Retry **the whole transaction unit** when safe |
| Database connection lost before COMMIT is sent | Connection/transaction error | May roll back on connection close; verify per DB engine | Check actual state and replay safety |
| COMMIT processed but response lost | Timeout/I/O exception on commit call | **Indeterminate from exception alone** | Reconcile DB + checkpoint; idempotent replay |
| Post-commit callback failure | Exception from `afterCommit` or post-commit task | DB may **already be committed** | Never assume rollback; decouple post-commit logic |
| Output DB and Batch metadata use separate transactions | One commits, the other fails | Output and checkpoint can diverge | Use unified architecture or reconciliation |
| Writer calls out-of-transaction API/file | Job/Step FAILED or DB rollback | External side effects may still exist | Idempotency, outbox, staging, and auditing |

Exceptions from Spring layers such as `TransactionSystemException`, `CannotCreateTransactionException`, `UnexpectedRollbackException`, JDBC drivers, or databases carry different names by context. **An exception class name does not always tell whether the database committed.** Inspect the root cause, SQLState/vendor code, transaction manager, database logs, and persisted state.

### 3.1. Pre-Commit Failure

For example, a writer writes invalid data triggering a unique constraint violation, or a component calls `setRollbackOnly()`. When a transaction is deterministically aborted, writes **within that same transaction** are not considered committed. Spring Batch can mark the Step FAILED and on restart resume from the saved checkpoint.

Do not assume the entire chunk rolled back if the writer also uses external APIs, storage, or connections managing independent transactions.

### 3.2. Failure Due to Ambiguous Commit Outcome

Suppose the database receives `COMMIT`, durably writes its transaction log, and then the TCP connection drops before acknowledging the application:

~~~text
Application                         Database
    |                                 |
    |----------- COMMIT ------------->|
    |                                 | transaction committed
    |<---- ACK lost due to network ---X
    |
    +---- Receives SQLException / timeout
          but commit outcome is unknown
~~~

This is an **ambiguous commit outcome**. A recovery mechanism assuming "exception means data was not written" risks duplicates. Conversely, assuming it was written loses data if COMMIT never succeeded.

### 3.3. Post-Commit Failure

An `afterCommit` callback can throw an exception after the DB resource has finished committing. The exception still propagates to the application, yet **it cannot roll back an already committed transaction**. Post-commit work such as event publishing should be retried via a dedicated reliable mechanism like an outbox rather than asking the database to "undo" a completed commit.

## 4. What Happens to JobExecution, StepExecution, and Checkpoints?

Spring Batch does not use a single field to describe everything that occurred:

- **`BatchStatus`** indicates the execution state recorded by the framework (`STARTED`, `FAILED`, `STOPPED`, `COMPLETED`, ...).
- **`ExitStatus`** provides the Step/Job exit code, configurable/adjustable for flow transitions.
- **`StepExecution`** stores Step counters and status.
- **`ExecutionContext`** stores checkpoints/state needed for restarts.
- **Target database** holds the actual business data.

In a commit failure, these sources **may disagree on progress boundaries** if transactions are not unified or a failure strikes while updating metadata.

Example with chunk size 100:

~~~text
Chunk #1: O001..O100
  Business DB: COMMITTED
  ExecutionContext: checkpoint=100

Chunk #2: O101..O200
  Writer sent data successfully
  COMMIT returned ambiguous error

Observed after incident:
  StepExecution: may be FAILED or metadata still STARTED
  Business DB: may or may not contain O101..O200
  ExecutionContext: may be at 100 or a newer state
~~~

Never take final `readCount` or `writeCount` and declare "committed up to record X." In a fault-tolerant step, rollbacks, retries, filters, skips, and prefetching cause counters/reader positions to differ from final output record counts.

### When JobRepository and Business Data Share the Same Database

If both writes use **the same datasource and the same physical transaction**, chunk commit can make business data and metadata updates an atomic unit: either both commit or both roll back per database guarantees. This makes restarts far more predictable.

Still, overall `JobExecution` status records (such as final FAILED/COMPLETED), logs, metrics, and out-of-transaction calls have their own lifecycles. **Do not extrapolate chunk atomicity into a distributed transaction across every system component.**

### When Using Two Datasources

If the writer writes business data to DB A while JobRepository uses DB B with a separate transaction manager:

~~~text
              Chunk processing
                /          \
               v            v
          Business DB A   Batch metadata DB B
               |            |
            COMMIT A      COMMIT B
               |            |
          Succeeded        Failed
~~~

The result can be persisted output rows while the checkpoint failed to advance. On restart, the reader re-reads already written items, causing duplicates if the writer is not idempotent. `@Transactional` alone does not create an atomic commit across two independent databases.

If atomicity across multiple resources is strictly mandatory, design distributed coordination fitting your requirements and infrastructure; for many practical jobs, **idempotent writer + reconciliation + staging/outbox** is simpler to operate and recover than assuming simultaneous commits.

## 5. First-Response Procedure When Suspecting a Commit Failure

Do not immediately rerun the job repeatedly. Verify scope and consequences first:

1. **Identify the execution:** jobName, jobExecutionId, jobInstanceId, StepExecutionId, batchId, and failure timestamp.
2. **Identify resources:** which DB/file/API the writer targets, how many transaction managers exist, and whether JobRepository shares the database.
3. **Read the exception chain:** whether the error occurred in the writer, flush, commit, post-commit callback, or metadata persistence.
4. **Preserve evidence:** logs with correlation IDs, Step metadata, checkpoints, and transaction IDs if supported by the DB; avoid deleting output.
5. **Inspect durable data:** query by batchId and business key, comparing against the input snapshot or expected set.
6. **Assess out-of-transaction side effects:** whether events/APIs/files were emitted and whether idempotency keys exist.
7. **Choose recovery strategy:** restart from checkpoint when consistent; reconcile and idempotently replay when uncertain; quarantine output if needed.
8. **Reconcile after recovery:** mark READY or release data to downstream only after verification passes.

Decision diagram:

~~~text
Commit exception
       |
       v
Is transaction rollback confirmed?
       | Yes
       v
  Restart from valid checkpoint
       |
       +--> Verify idempotent writer / external effects

       Unclear
       |
       v
Inspect output DB + JobRepository + external receipts
       |
       +--> Missing output: controlled replay
       |
       +--> Output complete: avoid rewriting; fix progress per runbook
       |
       +--> Partial/mismatched output: quarantine,
            reconcile per key, then idempotent replay
~~~

Every step involving metadata status updates must be governed by a runbook. Never manually flip `BATCH_JOB_EXECUTION.STATUS` to COMPLETED or alter reader positions via SQL just because output "looks complete": doing so can make JobRepository and restart flows contradictory.

## 6. Designing Target Data for Recoverability

Suppose a job imports orders from a frozen source where each valid input creates exactly one output row. Define:

- `batchId`: business batch identifier and reconciliation scope.
- `orderId`: unique business key within a batch.
- `amount`: normalized amount per business rules.
- `sourceHash`: stable fingerprint of key input fields (when distinguishing the exact same item from a new version).

Example PostgreSQL table:

~~~sql
CREATE TABLE imported_order (
    batch_id     VARCHAR(64) NOT NULL,
    order_id     VARCHAR(64) NOT NULL,
    amount       NUMERIC(18, 2) NOT NULL,
    source_hash  VARCHAR(64) NOT NULL,
    PRIMARY KEY (batch_id, order_id)
);
~~~

A unique key on `(batch_id, order_id)` prevents physical duplicates in the table. However, **a unique constraint does not mean the writer can replay safely**: a second `INSERT` can still throw an error and fail the Step.

A concrete idempotency strategy must specify:

| Situation on Replay | Desired Behavior |
|---|---|
| Key does not exist yet | INSERT new record |
| Key exists and content matches | Treat as already processed; create no duplicate |
| Key exists but amount/hash differs | Raise conflict for reconciliation; do not silently overwrite |
| Record already consumed downstream | Do not mutate abruptly; use versioning/correction workflow |

Some jobs use `INSERT ... ON CONFLICT DO NOTHING` (PostgreSQL) to skip repeated rows. This is safe only when **a mechanism exists to detect conflicting payloads for the same key**. Otherwise, the job can report success while target data retains stale values from an older input.

### Example Writer with Conflict Detection

In a naive model, a writer tries INSERT and upon duplicate key re-reads the existing row to verify equivalence. That illustrates the **business intent**, but you must not run a failing JDBC statement and continue querying inside the same PostgreSQL transaction: after an SQL error, a PostgreSQL transaction may enter an aborted state.

Instead of catching SQL exceptions in a broken transaction, use an atomic conditional UPSERT and inspect the row count:

~~~sql
INSERT INTO imported_order (batch_id, order_id, amount, source_hash)
VALUES (:batchId, :orderId, :amount, :sourceHash)
ON CONFLICT (batch_id, order_id)
DO UPDATE SET
    amount = imported_order.amount
WHERE imported_order.amount = EXCLUDED.amount
  AND imported_order.source_hash = EXCLUDED.source_hash;
~~~

In PostgreSQL, if the key collides with different data, the `WHERE` condition fails so `RETURNING` yields zero rows; the application can check the returned row count and report a **conflict**. Example using `RETURNING order_id` for clarity:

~~~sql
INSERT INTO imported_order (batch_id, order_id, amount, source_hash)
VALUES (:batchId, :orderId, :amount, :sourceHash)
ON CONFLICT (batch_id, order_id)
DO UPDATE SET amount = imported_order.amount
WHERE imported_order.amount = EXCLUDED.amount
  AND imported_order.source_hash = EXCLUDED.source_hash
RETURNING order_id;
~~~

This demonstrates the **"insert new or accept identical existing record"** policy. Even a no-op UPDATE can fire triggers/audits or create row versions depending on the database, so evaluate cost and side effects in production. Another option is staging tables plus set-based reconciliation queries before merging.

All SQL in these examples uses PostgreSQL syntax; on Oracle, SQL Server, or MySQL, build equivalent approaches matching each database's semantics and isolation levels.

## 7. Example Chunk Step with Transactions and Checkpoints

This example uses Spring Batch 5+, reading a frozen CSV file via `inputFile` and writing orders to the DB. The illustration highlights **commit points and restartability**, without assuming this configuration alone handles every ambiguous commit failure.

Input file:

~~~csv
orderId,amount,sourceHash
O001,100.00,hash-o001-v1
O002,45.50,hash-o002-v1
O003,80.00,hash-o003-v1
O004,25.00,hash-o004-v1
~~~

Data type:

~~~java
import java.math.BigDecimal;

public record OrderRow(
        String orderId,
        BigDecimal amount,
        String sourceHash) {
}
~~~

Stateful reader:

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
            .name("importOrderReader")
            .resource(new FileSystemResource(inputFile))
            .linesToSkip(1)
            .delimited()
            .names("orderId", "amount", "sourceHash")
            .fieldSetMapper(fields -> new OrderRow(
                    fields.readString("orderId"),
                    fields.readBigDecimal("amount"),
                    fields.readString("sourceHash")))
            .saveState(true)
            .build();
}
~~~

Illustrative writer with `JdbcTemplate` and a plain `INSERT` so commit scenarios can be observed:

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
                    INSERT INTO imported_order
                        (batch_id, order_id, amount, source_hash)
                    VALUES (?, ?, ?, ?)
                    """,
                    batchId,
                    order.orderId(),
                    order.amount(),
                    order.sourceHash());
        }
    };
}
~~~

Step and Job:

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
            .<OrderRow, OrderRow>chunk(2, transactionManager)
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

In a real application, both `@Bean` methods belong in a `@Configuration` class, infrastructure beans must be defined, and `JobRepository`/transaction manager must point to the appropriate datasource. With `chunk(2)`, a four-record file forms two commit units when all records are valid.

This plain `INSERT` writer example **is not yet idempotent**. If the DB commits while the checkpoint fails to update, restarting can hit a duplicate key error. Before running in production, replace it with a replay-safe policy or ensure metadata and business data share consistent atomicity.

## 8. Can Commit Errors Be Retried or Skipped Automatically?

In Spring Batch, `faultTolerant()`, `retry(...)`, `skip(...)`, and `skipLimit(...)` primarily handle failures during **read/process/write** operations inside fault-tolerant chunk processing. An error thrown **when the transaction manager commits at the chunk boundary** sits in a different place than a per-item exception.

Therefore:

- Do not assume `.retry(SomeSQLException.class)` will always retry an error raised inside `PlatformTransactionManager.commit()`.
- Do not treat `.skip(Exception.class)` as a fix for commit failures; no single item is guaranteed to be the culprit.
- Do not wrap the entire JobLauncher in retries with randomized parameters: that creates new JobInstances and writes duplicate output.
- Do not retry a transaction when the outcome is ambiguous and the writer is non-idempotent.
- If the database returns a concurrency error meaning the transaction clearly aborted, retrying the entire chunk can be appropriate, provided it aligns with database/transaction manager guarantees and your designed retry policy.

In particular, **`noRollback(...)` does not turn a failed commit into a successful commit**. That option adjusts rollback policy for certain exceptions during chunk processing; it does not guarantee safe continuation after a commit failure.

### When Is Retry Useful?

| Error | Example | Typical Consideration |
|---|---|---|
| Transient read/process | API timeout, retryable read deadlock | Bounded retry with backoff |
| Transient pre-commit write | DB lock timeout while writing | Chunk retry if state and side effects permit |
| Explicitly rejected commit | Serialization conflict aborting the transaction | Retry entire transaction when idempotent |
| Ambiguous commit outcome | Lost ACK after COMMIT | Reconcile first; safe replay by business key |
| Permanent constraint violation | Duplicate key with differing payload | Stop/quarantine to resolve data conflict |
| Metadata commit diverges from output | Business DB and batch DB out of sync | Repair/reconcile per runbook, not blind retry |

Safe retryability depends on **idempotency** and **isolation of side effects**, not merely marking an exception `retryable`.

## 9. Fault Injection to Distinguish Pre-Commit and Post-Commit

For Failure recovery, testing only errors inside `ItemWriter.write()` is insufficient: those errors usually occur **before the framework invokes commit**. To test transaction boundaries, use an integration environment and controlled fault-injection hooks.

### 9.1. Simulating a Pre-Commit Failure

In Spring transactions, you can register a **TransactionSynchronization** while a transaction is active. The `beforeCommit` callback runs before the transaction commits. If it throws an exception, the transaction typically rolls back per transaction manager rules.

Example of a test-only component:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public final class BeforeCommitFailureInjector {

    private final AtomicBoolean failNext = new AtomicBoolean(true);

    public void registerForCurrentTransaction() {
        if (!TransactionSynchronizationManager.isSynchronizationActive()) {
            throw new IllegalStateException("No active synchronization");
        }

        TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void beforeCommit(boolean readOnly) {
                        if (failNext.compareAndSet(true, false)) {
                            throw new IllegalStateException(
                                    "TEST_FAIL_BEFORE_COMMIT");
                        }
                    }
                });
    }
}
~~~

This test helper must be invoked **inside the target chunk transaction**, for instance from a test-configured writer. Do not invoke it randomly during context startup when no transaction exists.

What to observe in tests: the error fires before commit, the transaction rolls back per the active manager, the chunk's output is not exposed, the job records the appropriate status, and post-restart data is accurate.

### 9.2. Simulating a Failure After Commit Has Completed

In a test environment, an `afterCommit` callback can intentionally throw an exception:

~~~java
TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                throw new IllegalStateException(
                        "TEST_FAIL_AFTER_COMMIT");
            }
        });
~~~

This models a **post-commit callback failure**: DB changes may already have committed before the application receives the exception. It is **not equivalent** to simulating a JDBC disconnect right at COMMIT or emulating every transaction manager failure mode.

When testing this scenario, do not rigidly assert that `BatchStatus` must always be FAILED or data must roll back across every setup. Observe and record:

- Exactly when the exception is thrown.
- Whether the DB output already committed.
- What state the Spring Batch checkpoint holds.
- What final status `JobExecution`/`StepExecution` records.
- Whether a restart duplicates records.

Throwing inside post-commit callbacks can affect execution flow and logging, so use injectors only in isolated tests; never leave fault-injection code in production.

### 9.3. Simulating Real COMMIT Errors at the Connection Layer

To test **ambiguous commit outcomes**, you need a closer-to-production integration setup:

- A dedicated test database with production-like transaction semantics.
- A network proxy or test harness capable of dropping the connection **after the DB receives COMMIT but before the client receives the acknowledgment**, if supported by the tool/driver.
- Database logs or audits with transaction markers to verify actual commit outcomes.
- Real workers and `JobRepository` in tests, not just a mocked `PlatformTransactionManager`.

This kind of test is hard to control deterministically because COMMIT/ACK timing is a race. Ensure the test can handle both the committed case and the rolled-back case, then verify whether your recovery algorithm produces accurate final output under **both outcomes**.

Never treat a mocked `commit()` throwing an exception as proof that a real network dropped an ACK after commit. Mocking only tests how the application reacts to an exception, not durable DB state.

## 10. Test Scenarios for Recovering After a Commit Failure

Suppose the input has six valid orders, `chunk(2)`, and each order must yield exactly one output row:

~~~text
O001, O002  -> Chunk 1
O003, O004  -> Chunk 2
O005, O006  -> Chunk 3
~~~

Core scenarios:

| Case | Fault Injection Point | What to Verify |
|---|---|---|
| Baseline | No fault | Job COMPLETED; all six orders, zero duplicates |
| Pre-commit of chunk 2 | `beforeCommit` or controlled DB rejection | Uncommitted chunk rolls back; checkpoint/target consistent |
| Post-commit of chunk 2 | Test transaction `afterCommit` | Target may already have O003/O004 even though app sees an exception |
| Ambiguous COMMIT response | Proxy/database chaos | Safe recovery whether actual commit happened or not |
| Metadata DB failure | Intentionally separated metadata source | Output/checkpoint divergence detected |
| Writer with external side effect | API receives request then DB fails | No duplicate side effect on restart |
| File writer flushing | Storage/file error | Temporary output stays isolated and is not published early |
| Second-run restart | First run fails, second succeeds | Same JobInstance; final output accurate |
| Repeated retries of same record | Replay same batchId/orderId | Idempotent; conflicting payloads must be detected |

### Example Assertions on Final Data

For the `imported_order` table after successful recovery:

~~~sql
-- Enough records for the right batch.
SELECT COUNT(*)
FROM imported_order
WHERE batch_id = :batchId;

-- No duplicate business keys.
SELECT batch_id, order_id, COUNT(*) AS occurrences
FROM imported_order
WHERE batch_id = :batchId
GROUP BY batch_id, order_id
HAVING COUNT(*) > 1;

-- No missing records compared to source snapshot.
SELECT s.order_id
FROM staging_order s
WHERE s.batch_id = :batchId
  AND NOT EXISTS (
      SELECT 1
      FROM imported_order t
      WHERE t.batch_id = s.batch_id
        AND t.order_id = s.order_id
  );
~~~

If `staging_order` does not exist in your application, tests can compare against the expected ID list from fixture files. **`COUNT(*)` alone is insufficient**: one missing record plus one duplicate keeps the total count identical. For critical payloads, verify amounts/hashes per transform rules too.

### Do Not Time Failure Injection with Sleep

Commit failure tests should target a deterministic **chunk/transaction**, such as an injector with an invocation counter, a writer callback after a fixed record set, or a test-controlled transaction manager proxy. Avoid `Thread.sleep(100)` before killing the DB: on CI, timing variance can hit the wrong chunk.

When simulating real network failures, log transaction markers to distinguish failures before vs. after commit; the test allows an indeterminate outcome while proving the reconciliation algorithm handles both safely.

## 11. Restarting a JobInstance After a Commit Error

Spring Batch persists checkpoints to support restarting incomplete Steps. Restart correctness relies on immutable inputs, `ItemStream` state persistence, and writer side-effect safety.

Example:

~~~text
JobInstance #410: importOrdersJob(batchId=B42)
    |
    +-- JobExecution #900: FAILED
    |     Chunk 1 committed
    |     Chunk 2 commit outcome ambiguous
    |
    +-- JobExecution #904: restart
          Resumes from checkpoint found by framework
          Writer must tolerate replaying O003/O004 if needed
~~~

**Restart** means continuing the same JobInstance using Spring Batch metadata, typically creating a new JobExecution. **Do not add a random identifying parameter** on the second run and call it a restart: that creates a different JobInstance and can reprocess the entire input.

Example with JobOperator:

~~~java
long failedExecutionId = 900L;

// Call only after evaluating status and restart eligibility.
Long restartedExecutionId = jobOperator.restart(failedExecutionId);
~~~

This assumes `jobOperator` is injected and the execution is eligible for restart. Restart calls can be rejected if the job is non-restartable, the execution has not finished, the Step exceeded `startLimit`, inputs changed, or metadata is inconsistent.

### What If the Checkpoint Advances Ahead of Output?

If JobRepository commits a new checkpoint while business output failed to commit (two resources not sharing a transaction), restarting may **skip** items absent from the target. Unique keys cannot solve this data-loss bug. Reconcile expected input against actual output, then recover missing keys.

### What If Output Advances Ahead of the Checkpoint?

If output committed while the checkpoint stayed behind, restarting re-reads items already in the DB. An idempotent writer can ignore the replay safely; a plain INSERT writer will hit duplicate constraint errors.

Because divergence in either direction is possible in multi-resource architectures, **exact-set reconciliation** must be part of recovery whenever atomicity is not guaranteed.

## 12. File Output and Commit Failures

Not every writer targets a database. With `FlatFileItemWriter`, checkpoints can help restart a file, yet filesystems do not have JDBC transaction semantics. A flush/close error, power loss, file mutation, or consumer reading an in-progress file can leave output incomplete, duplicated, or partially written.

A common strategy:

~~~text
job execution
    |
    v
Write batch-B42-v1.csv.part
    |
    v
Close file, verify schema/records/checksum
    |
    v
Create batch-B42-v1.csv (if publish operation is safe)
    |
    v
Write manifest/READY marker
    |
    v
Consumers start reading
~~~

Notes:

- **Do not treat file existence as proof of a successful commit**.
- On restart, keep input versions fixed and understand the writer's append/truncate/state modes.
- Never publish temporary files when the JobExecution is still FAILED or STOPPED.
- Rename can be atomic on a suitable single filesystem, but is not atomic by default across storage backends or object stores.
- On cloud object storage, use immutable object keys/versions and emit a manifest/READY marker only after verification.
- Once a version is published to consumers, do not overwrite it in place during repair; emit a new version/correction per contract.

File writer options like `saveState`, `transactional`, `shouldDeleteIfExists`, and `appendAllowed` must be understood for your specific Spring Batch version and restart strategy. Do not apply a universal option template to every job.

## 13. Side Effects to APIs, Message Brokers, and Other Systems

This is the most common source of divergence after commit failures:

~~~text
Step transaction (DB)
        |
        +-- INSERT order into DB (uncommitted)
        |
        +-- Call HTTP API to send notification
        |      API sent successfully
        |
        +-- Database COMMIT fails
               |
               v
        DB rollback
        Notification is not automatically retracted
~~~

On restart, the job can send the notification a second time. Even if JobRepository and the business DB share a transaction, the HTTP call **is not part of that transaction**.

### Transactional Outbox

When events must be emitted after DB writes, one option is writing an **outbox event in the same transaction** as the business record:

~~~text
Business transaction:
    INSERT/UPDATE imported_order
    INSERT outbox_event(event_id, batch_id, order_id, payload)
    COMMIT

Independent publisher:
    Read unpublished outbox rows
    Send message
    Record published status
~~~

When the DB commit fails, both output and outbox records roll back together if they truly share the transaction. When DB commit succeeds but the publisher loses the broker ACK, the publisher can resend. Consumers therefore still need **idempotency keys/event IDs** and duplicate handling.

### APIs with Side Effects

For payments, reservations, or external order creation, use a stable idempotency key, typically derived from **batchId + business key + operation type**.

~~~http
POST /reservations
Idempotency-Key: B42-O003-RESERVE
Content-Type: application/json

{"orderId":"O003","quantity":2}
~~~

When a response times out, retry with **the same idempotency key** so the target service recognizes it as the same action. Still verify the target service contract genuinely enforces idempotency over the required retention window; sending the header alone does not prove deduplication on the receiver.

In ambiguous commit outcomes, you may need to query a **receipt/status API** by idempotency key before retrying.

## 14. Monitoring and Auditing Commit Errors

A commit incident needs enough context for investigation without logging secrets or sensitive payloads.

Example log event:

~~~text
event=chunk.commit.failed
jobName=importOrdersJob
jobInstanceId=410
jobExecutionId=900
stepExecutionId=1901
batchId=B42
chunkSequence=2
transactionResource=orders-datasource
exceptionClass=TransactionSystemException
rootSqlState=08006
commitOutcome=UNKNOWN
observedAt=2026-11-16T03:25:00+07:00
~~~

This is an illustrative structure. Do not infer `commitOutcome=ROLLED_BACK` solely from `SQLState=08006`: a connection drop does not prove the database rolled back the transaction. If the root cause or vendor code gives an authoritative database guarantee, audits can classify it specifically after verification.

Useful metrics:

| Metric | Meaning |
|---|---|
| `batch_chunk_commit_failures_total` | Commit-phase failures by job/Step/resource |
| `batch_job_failures_total` | Jobs ending as FAILED |
| `batch_recovery_attempts_total` | Recovery workflow executions |
| `batch_output_reconciliation_mismatch_total` | Batches with missing/extra/mismatched data |
| `batch_replay_conflicts_total` | Colliding business keys with differing payloads |
| `batch_last_success_timestamp` | Most recent time output became ready successfully |
| `batch_recovery_duration_seconds` | Time from failure detection to recovery completion |

Metric names here are **suggested application conventions**, not default Spring Batch meters.

In metrics, use low-cardinality labels such as `job`, `step`, `resource`, and `failureClass`. Values like `jobExecutionId`, `batchId`, and `orderId` belong in logs, traces, and audits to prevent unbounded time-series growth.

### Do Not Swallow Commit Exceptions

If an application-level listener or wrapper catches a commit-phase exception, **never downgrade it to a WARN and report Job COMPLETED** before determining data state. Doing so can cause downstream consumers to ingest partial output.

For uncertain failures, transition the business batch to **RECOVERY_REQUIRED** or **QUARANTINED** in a dedicated control store. Because updating a control store can itself fail, synchronize that state with JobRepository and maintain an independent reconciliation process.

## 15. Practical Operational Runbook

A recovery workflow suitable for production jobs:

### Phase A — Isolate and Collect Evidence

1. Pause automated scheduler retries for the affected batch or hold a batchId lock.
2. Confirm no other execution is concurrently writing the same business keys.
3. Record JobExecutionId, StepExecutionId, batchId, input version, commit logs, and error chain.
4. Check whether downstream has already read or received output.

### Phase B — Reconcile State

1. Read `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION`, and ExecutionContext via approved APIs or queries.
2. Inspect the actual output set by batchId in the real database/storage.
3. Compare against the input snapshot and transformation rules; detect **missing, unexpected, duplicate, or mismatched** records.
4. Check receipts in external APIs, outbox, or brokers when side effects exist.
5. Determine state: **rollback confirmed**, **commit confirmed**, or **outcome still unknown**.

### Phase C — Recover

1. If rollback is confirmed and checkpoints are valid: restart via Spring Batch with a replay-safe writer.
2. If commit is confirmed but metadata lagged/missed: resolve the divergence per runbook without rushing into a new JobInstance.
3. If the outcome is unclear: replay via business key/idempotency or reconcile and process missing records under a controlled remediation execution.
4. If incorrect side effects were already published: use business correction/compensation rather than deleting DB rows and assuming external systems reverted too.

### Phase D — Close the Incident

1. Run final output verification against the contract.
2. Confirm no concurrent execution owns the batch.
3. Record recovery audit and map the original JobExecution to the recovery execution.
4. Update business status to READY only after all mandatory checks pass.
5. Document root cause, remediation, and regression tests to prevent recurrence.

If JobRepository metadata stays `STARTED` after a process crash, **do not run direct SQL `UPDATE STATUS`** in production just to unblock restarts. Check whether the process is alive, whether transactions or scheduler locks remain open, and follow the recovery documentation for your Spring Batch version. Manual metadata edits must be a controlled last resort.

## 16. Common Mistakes

**"An exception during commit means rollback."** False when DB COMMIT succeeded and the ACK dropped or a post-commit callback threw. Always verify durable data.

**"The writer threw no error, so output committed."** Writers typically run before commit; the database can still reject the commit or the transaction may be rollback-only.

**"`readCount`/`writeCount` accurately show committed records."** Counters do not replace output and checkpoint reconciliation, especially with retries and rollbacks.

**"Spring Batch handles distributed transactions across all datasources automatically."** Sharing an annotation or Job does not give two databases/APIs an atomic commit.

**"Just retry the Job with new parameters."** New identifying parameters create a new JobInstance, which may re-read from the beginning and cause duplicates.

**"A unique constraint is enough for idempotency."** Constraints block physical duplicates but can make replays FAIL. Define how existing keys are handled and check for payload mismatches.

**"ON CONFLICT DO NOTHING is always safe."** It can hide new inputs whose values differ from previously stored rows. Compare hashes/amounts and raise conflicts on mismatches.

**"Skip commit errors like skipping bad items."** A commit failure is a transaction/chunk issue; no single faulty item can be isolated to skip safely.

**"Every DB error is retryable."** There are permanent errors, serialization errors with clear aborts, and connection errors with uncertain outcomes; classify properly.

**"Using Thread.sleep then killing the DB is an accurate test."** Timing varies between local machines and CI; inject faults at transaction boundaries and assert actual outcomes.

**"A DB transaction rolls back sent HTTP requests."** Out-of-transaction side effects require idempotency, outboxes, or compensation.

**"Job COMPLETED guarantees correct output."** Job status is an execution signal; after recovery, still verify record sets, values, uniqueness, and publish preconditions.

**"Spring Batch metadata tables can be edited freely."** A wrong edit pushes checkpoints, execution status, and output further out of sync; follow a runbook with evidence.

**"If the file exists, it is ready to consume."** Files may be incomplete or unverified; publish via manifest/version/READY markers after completion.

## 17. Principles for Designing Recoverability

To handle **commit failures** safely in Spring Batch Core Processing, design from the start around these principles:

1. **Identify real transaction boundaries** for business data, Batch metadata, and every external side effect.
2. **Account for uncertain outcomes:** commit exceptions can arrive after the DB finished committing.
3. **Persist recoverable checkpoints** via `ItemStream`/ExecutionContext and stable inputs per JobInstance.
4. **Design idempotent replays** using business keys, version/payload checks, and explicit merge or conflict rules.
5. **Reconcile durable results** against expected sets, not just status or counters.
6. **Separate publishing from temporary writes** so consumers receive only completed, verified outputs.
7. **Test pre-commit, post-commit, and ambiguous commit outcomes** using fault injection tailored to the target failure layer.
8. **Operate with IDs and runbooks:** jobExecutionId, stepExecutionId, batchId, transaction resource, input version, and recovery audits.

The hardest part of a commit failure is not always getting the job running again, but **knowing which work truly completed and replaying the uncertain slice without corrupting data correctness**. When transaction boundaries, checkpoints, idempotency, and reconciliation are designed together, Spring Batch can recover from commit errors while preserving completeness, uniqueness, and output traceability.
