# Handling Partial Completion and Persisting Checkpoints at the Business Layer

## 1. Scenario: a task completed part of its work before being interrupted

In **Spring Cloud Task**, a Spring Boot application accepts arguments, processes work with a clear termination point, records execution status into **TaskRepository**, and exits. For example, a reconciliation task processes 10,000 daily transactions starting at 2:00 AM.

At transaction 6,001, the JVM stops due to an out-of-memory error. Data for the previous 6,000 transactions was already written to the database. The operator needs to relaunch it, yet **must not reprocess already-completed transactions** and **must not skip transactions not yet written successfully**.

This is the **partial completion** and **resume after failure** problem in the **Idempotent Retries** chapter.

Four separate questions must be answered:

- **Work scope:** which exact inputs must be processed? Can that scope change between two runs?
- **Committed state:** which processing units finished durably, and which existed only in memory?
- **Resume point:** where should the new run start reading from?
- **External effects:** did any operations such as sending emails, calling APIs, or writing files happen that an internal transaction cannot roll back?

**TaskRepository does not store record-level business progress.** It tracks a `TaskExecution` with start time, end time, exit code, and error details. Storing cursors, checkpoints, and partial outcomes must be designed at the **business layer** or managed by a dedicated mechanism like **Spring Batch**.

### Learning outcomes

After this lesson, you will be able to distinguish execution state from work state, design a durable **work key**, persist outcomes and checkpoints in the same transaction, resume with a stable cursor, apply idempotency/outbox for out-of-database side effects, and test failure windows before running in production.

## 2. TaskExecution and checkpoints operate at two different levels

Every launch of a Spring Cloud Task application can create a new execution record:

| Run | TASK_EXECUTION_ID | Work key | Outcome |
| --- | --- | --- | --- |
| First run | 501 | `tenant-A:2026-11-23:v1` | Failed after chunk 60 |
| Rerun | 502 | `tenant-A:2026-11-23:v1` | Resumed from checkpoint and completed |

**Task execution ID** identifies **one physical run**. **Work key** identifies **the business work to complete**, and must remain stable across retries sharing the same source scope.

| Storage | Contents | Can it be used to resume? |
| --- | --- | --- |
| `TaskRepository` / `TASK_EXECUTION` | Task name, run ID, timestamps, exit code, error message | Only enough for lifecycle; **does not** know which records committed |
| Business `work_progress` table | Work key, source version, checkpoint, status | **Yes**, if the checkpoint reflects committed data |
| Business results table | Processed data, unique outcome key | Verifies what actually completed |
| Outbox or external system | Events and delivery status by event ID | Verifies out-of-transaction effects |

Runs `501` and `502` need the **same work key** to share the checkpoint. If you key the progress record by `TASK_EXECUTION_ID`, a retry with a new ID will not find the previous resume point.

In logs, record both the **execution ID** and **work key**; avoid placing passwords, tokens, or personal data in persisted arguments or logs.

## 3. Checkpoint invariant

A **checkpoint** is a durably completed boundary. For example:

~~~text
work_key          = tenant-A:2026-11-23:v1
upper_source_id   = 10000
last_committed_id = 6000
state             = IN_PROGRESS
~~~

The exact meaning of `last_committed_id=6000` is that **every required unit within the frozen source scope whose key is less than or equal to 6000 has been completed and committed, or has an explicitly recorded skip decision**.

Here is the core invariant:

> Only advance the checkpoint to `C` after **all results for work units at or before `C` have been durably persisted**.

If you update the cursor to 7000 **before** writing results for 6001–7000, a crash will cause the next run to skip unprocessed records. If you write results first but update the checkpoint in a **separate transaction**, a crash can cause the next run to redo completed work.

When results and checkpoints reside in **the same transactional database**, write them in **one transaction**. A chunk then has only two durable states: **both results and checkpoint committed**, or **both rolled back**.

~~~mermaid
flowchart LR
    A["Read checkpoint by work key"] --> B["Fetch source chunk after cursor"]
    B --> C["BEGIN transaction"]
    C --> D["Write business results"]
    D --> E["Advance checkpoint"]
    E --> F{"COMMIT succeeded?"}
    F -->|Yes| G["Proceed to next chunk"]
    F -->|No| H["ROLLBACK both results and checkpoint"]
    H --> A
    G --> B
~~~

### Choosing the commit unit size

| Commit unit | Advantages | Trade-offs |
| --- | --- | --- |
| Per record | Very fine-grained resume, minimal rework | Many transactions, higher overhead |
| Chunk of 100–1,000 records | Balanced throughput, bounded rollback | Entire chunk is retried on failure before commit |
| All 10,000 records | Simple logic if work is tiny | Large transaction, long locks, expensive rollback |
| Per workflow step | Easy to observe finished steps | Needs dedicated state/compensation for side-effecting steps |

**There is no single optimal chunk size for every application.** Base it on execution duration, timeout limits, database resources, retry capability, and required atomicity.

## 4. Ensuring the source dataset does not shift during recovery

A cursor is safe only if the source set and processing order are **stable**.

Suppose processing reached `source_id=6000` before restarting:

~~~sql
SELECT source_id, amount
FROM payment_source
WHERE work_key = :workKey
  AND source_id > :lastCommittedId
  AND source_id <= :upperSourceId
ORDER BY source_id
LIMIT :chunkSize;
~~~

This is **keyset pagination**: reading **after** the checkpoint and sorting by a stable key. The `>` predicate excludes the already-committed boundary row.

Do not store `OFFSET=6000` on a table undergoing inserts/deletes, because row positions can shift. Likewise, merely storing `upper_source_id=10000` is insufficient if a slow concurrent transaction commits later and makes a row with an ID below 10000 appear.

Ways to **freeze the source set** include:

- Using an immutable source partition after period close.
- Creating a manifest table listing the exact `source_id`s to process.
- Using a `snapshot_id` or file version paired with a checksum.
- Embedding a business version in the work key, e.g., `tenant-A:2026-11-23:v1`.

**If the source can mutate while running, the following example is safe only when paired with a real snapshot/manifest mechanism.** A single "highest ID" number does not automatically make an actively written source immutable.

## 5. PostgreSQL example: persisting checkpoints yourself

This example targets a finite-running Spring Cloud Task application with a PostgreSQL business database. This is **application business schema**, not `TaskRepository` DDL. Assume `payment_source` is already frozen per work key.

### 5.1. Creating the three tables

~~~sql
-- Input frozen per work_key.
CREATE TABLE payment_source (
    work_key    VARCHAR(160) NOT NULL,
    source_id   BIGINT NOT NULL,
    amount      NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (work_key, source_id)
);

-- Results need a unique key to prevent duplicate writes.
CREATE TABLE payment_projection (
    work_key     VARCHAR(160) NOT NULL,
    source_id    BIGINT NOT NULL,
    amount       NUMERIC(18, 2) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (work_key, source_id)
);

-- Durable checkpoint, independent of TaskExecution.
CREATE TABLE reconciliation_progress (
    work_key          VARCHAR(160) PRIMARY KEY,
    upper_source_id   BIGINT NOT NULL,
    last_committed_id BIGINT NOT NULL DEFAULT 0,
    state             VARCHAR(20) NOT NULL DEFAULT 'READY',
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT valid_progress
      CHECK (last_committed_id >= 0
         AND upper_source_id >= 0
         AND last_committed_id <= upper_source_id),
    CONSTRAINT valid_state
      CHECK (state IN ('READY', 'IN_PROGRESS',
                      'COMPLETED', 'FAILED'))
);
~~~

Key columns:

| Column | Meaning |
| --- | --- |
| `work_key` | Keys the same unit of work across retries |
| `upper_source_id` | Upper bound of the **frozen** source set |
| `last_committed_id` | Key of the last committed source unit in processing order |
| `state` | Work state at the business layer |
| `updated_at` | Helps observe changes; not a lease or lock on its own |

To initialize for the first time, **after the source is frozen**:

~~~sql
INSERT INTO reconciliation_progress (work_key, upper_source_id)
SELECT 'tenant-A:2026-11-23:v1',
       COALESCE(MAX(source_id), 0)
FROM payment_source
WHERE work_key = 'tenant-A:2026-11-23:v1'
ON CONFLICT (work_key) DO NOTHING;
~~~

`ON CONFLICT DO NOTHING` lets initialization be called repeatedly **without resetting** an existing checkpoint. If you need to process a new source version, create a new work key/version or an explicit reprocessing workflow.

### 5.2. Each chunk is one transaction

Java 17+ and Spring JDBC example with one transaction manager governing **both outcomes and checkpoints**. The method is invoked through a Spring proxy from another bean:

~~~java
import java.math.BigDecimal;
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ReconciliationChunkService {

    private final JdbcTemplate jdbc;

    public ReconciliationChunkService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public boolean processNextChunk(String workKey, int chunkSize) {
        if (chunkSize < 1 || chunkSize > 1000) {
            throw new IllegalArgumentException("Invalid chunk size");
        }

        Cursor cursor = jdbc.queryForObject("""
            SELECT last_committed_id, upper_source_id, state
            FROM reconciliation_progress
            WHERE work_key = ?
            FOR UPDATE
            """,
            (rs, n) -> new Cursor(
                rs.getLong("last_committed_id"),
                rs.getLong("upper_source_id"),
                rs.getString("state")),
            workKey
        );

        if ("COMPLETED".equals(cursor.state())) {
            return false;
        }

        List<Payment> batch = jdbc.query("""
            SELECT source_id, amount
            FROM payment_source
            WHERE work_key = ?
              AND source_id > ?
              AND source_id <= ?
            ORDER BY source_id
            LIMIT ?
            """,
            (rs, n) -> new Payment(
                rs.getLong("source_id"),
                rs.getBigDecimal("amount")),
            workKey, cursor.lastId(), cursor.upperId(), chunkSize
        );

        if (batch.isEmpty()) {
            if (cursor.lastId() < cursor.upperId()) {
                throw new IllegalStateException(
                    "Frozen source has unexpectedly changed");
            }
            jdbc.update("""
                UPDATE reconciliation_progress
                SET state = 'COMPLETED', updated_at = now()
                WHERE work_key = ?
                """, workKey);
            return false;
        }

        for (Payment p : batch) {
            jdbc.update("""
                INSERT INTO payment_projection
                    (work_key, source_id, amount)
                VALUES (?, ?, ?)
                ON CONFLICT (work_key, source_id) DO NOTHING
                """, workKey, p.id(), p.amount());
        }

        long lastId = batch.get(batch.size() - 1).id();
        jdbc.update("""
            UPDATE reconciliation_progress
            SET last_committed_id = ?,
                state = CASE
                    WHEN ? = upper_source_id THEN 'COMPLETED'
                    ELSE 'IN_PROGRESS'
                END,
                updated_at = now()
            WHERE work_key = ?
            """, lastId, lastId, workKey);

        return true;
    }

    private record Cursor(long lastId, long upperId, String state) {}
    private record Payment(long id, BigDecimal amount) {}
}
~~~

**Protections in this example:**

1. `SELECT ... FOR UPDATE` locks **the work key's checkpoint row** during the active transaction. Two processes cannot read the same old checkpoint and concurrently commit updates to the same row when transactions/DB are configured properly.
2. `ORDER BY source_id` and `source_id > last_committed_id` form a monotonically advancing cursor without offsets.
3. `ON CONFLICT` prevents writing two results with the same key. It can also **mask errors if source data is altered**, which is why source immutability is mandatory; if the source gets a new version, design separate handling.
4. Updating `last_committed_id` happens **in the same transaction** as writing `payment_projection`. If any statement in the chunk throws before commit, the whole chunk rolls back.
5. `@Transactional` activates when called **through the Spring bean proxy**. Self-invoking `this.processNextChunk(...)` inside the same class may bypass Spring AOP transactions.
6. The example assumes the checkpoint row was initialized. Without a matching row, `queryForObject` throws; detect and initialize the work key before running.

**Limitation:** the row lock only synchronizes **per chunk**; two processes could alternate chunks of the same work key after each commit. If only one process may run a period end-to-end, add a work-key lock or scheduler policy.

### 5.3. Spring Cloud Task runner

~~~java
import java.util.List;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ReconciliationRunnerConfig {

    @Bean
    ApplicationRunner reconciliationRunner(
            ReconciliationChunkService service) {
        return args -> {
            List<String> values = args.getOptionValues("workKey");
            if (values == null || values.size() != 1) {
                throw new IllegalArgumentException(
                    "Required: --workKey=<stable-business-key>");
            }

            String workKey = values.get(0);
            while (service.processNextChunk(workKey, 100)) {
                // Each call runs in its own transaction.
            }
        };
    }
}
~~~

Command-line run example:

~~~bash
java -jar reconciliation-task.jar --workKey=tenant-A:2026-11-23:v1
~~~

If the runner throws an exception, Spring Cloud Task can record the failed run in `TaskRepository`. The next launch receiving the **same work key** reads the committed checkpoint; the new run's `TaskExecution` gets a **different execution ID**.

### 5.4. Verifying committed data

~~~sql
SELECT work_key, upper_source_id,
       last_committed_id, state, updated_at
FROM reconciliation_progress
WHERE work_key = 'tenant-A:2026-11-23:v1';
~~~

~~~sql
SELECT COUNT(*) AS committed_results
FROM payment_projection
WHERE work_key = 'tenant-A:2026-11-23:v1';
~~~

**Note:** `last_committed_id` is a **positional key**, not necessarily the count of processed rows. If IDs have gaps, `last_committed_id=6000` does not mean exactly 6,000 rows were processed.

## 6. Failure windows and how reruns behave

| When did the failure occur? | Checkpoint and results | Recovery rule |
| --- | --- | --- |
| Before chunk starts | No new chunk changes yet | Re-read current checkpoint |
| Mid-chunk before commit | Both results and checkpoint roll back | Re-execute chunk from prior boundary |
| After UPDATE checkpoint but before COMMIT | Neither is durable yet | Roll back and rerun from old checkpoint |
| After COMMIT but before "done" log | Results and checkpoint **are saved** | Resume after committed cursor |
| After sending HTTP/email but before saving state | External side effects may have occurred | Idempotency/outbox/external reconciliation |
| JVM killed before TaskRepository writes END_TIME | TaskExecution metadata may remain open | Check process and business checkpoint |

**Never update the checkpoint first and write data afterward.** Dangerous example:

~~~text
UPDATE progress SET last_committed_id = 7000;
COMMIT;
... records 6001-7000 not processed yet ...
CRASH
~~~

The new run trusts cursor 7000 and **skips** unfinished work.

Correct design in the same database:

~~~text
BEGIN TRANSACTION;
  WRITE results for 6001-7000;
  UPDATE checkpoint = 7000;
COMMIT;
~~~

If an operation fails, the transaction rolls back. If the commit succeeds and the final log is lost, the database remains the source of truth for progress.

## 7. When work has side effects outside the database

A JDBC transaction cannot roll back an email, object storage upload, or API call that already succeeded. Example:

1. Task calls a refund API with `refundId=R-123`.
2. The API executes the refund, then the connection drops before sending the response.
3. Task times out without saving a checkpoint.
4. Retry sends the same request again.

Without receiver-side protection, the same transaction can be refunded **twice**.

### 7.1. Stable idempotency key

Derive the key from the **business unit**, such as `refund:order-123:v1`, and pass that same key across every retry. If the target API supports idempotency properly, repeated requests return the prior outcome without creating a new side effect.

**Do not use `TASK_EXECUTION_ID` as an idempotency key**, because each rerun has a different ID. For APIs that lack idempotency support, query status by business key or build reconciliation/compensation workflows.

### 7.2. Transactional outbox

If you need to emit events after processing data, write **results, outbox records, and checkpoints in the same DB transaction**. An independent publisher delivers the outbox to external systems:

~~~mermaid
flowchart LR
    A["Chunk transaction"] --> B["DB results"]
    A --> C["Unique outbox event_id"]
    A --> D["Checkpoint"]
    C --> E["Publisher retry"]
    E --> F["Receiver checks event_id"]
~~~

Minimal DDL:

~~~sql
CREATE TABLE outbox_event (
    event_id    VARCHAR(180) PRIMARY KEY,
    work_key    VARCHAR(160) NOT NULL,
    event_type  VARCHAR(80) NOT NULL,
    payload     JSONB NOT NULL,
    sent_at     TIMESTAMPTZ
);
~~~

Event record with a stable ID and unique constraint:

~~~sql
INSERT INTO outbox_event (event_id, work_key, event_type, payload)
VALUES (
    'tenant-A:2026-11-23:v1:payment-601',
    'tenant-A:2026-11-23:v1',
    'PAYMENT_RECONCILED',
    '{"sourceId":601}'
)
ON CONFLICT (event_id) DO NOTHING;
~~~

The publisher can still send **more than once** if interrupted after the receiver processed the event but before marking `sent_at`. The downstream consumer/API must deduplicate by `event_id`. An outbox provides reliable **at-least-once** delivery when implemented properly; it does not automatically guarantee exactly-once across multiple systems.

If a workflow spans multiple non-rollbackable operations, you may need **per-step state** and **compensation**. A single cursor cannot represent states like "paid, but notification not yet sent."

## 8. Parallel execution or per-item failures

### 8.1. Two processes sharing the same work key

If two processes both read `last_committed_id=6000`, without locking both can process 6001–6100. `SELECT ... FOR UPDATE` in the example synchronizes at the chunk level, yet **does not** restrict active processes across the entire job.

You can add:

- Scheduler coordination so runs do not overlap.
- Spring Cloud Task single-instance locking by **task name**, where appropriate and sharing a lock store.
- A distributed lease by **work key** if different task names or workers can act on the same period.
- Unique constraints/idempotency on the outcome table as the final safety net.

An expired lease while the old process is still alive can cause **split-brain**. For critical effects, consider a **fencing token** validated by the target system before writing.

### 8.2. One item fails while a later item succeeds

A monotonically advancing cursor works only when **every item before the boundary is resolved**. If parallel processing leaves `source_id=602` failed while `603` succeeded, you **must not** advance the checkpoint to 603 and abandon 602.

When items have independent states, use a **per-item state table**:

| work_key | source_id | state | attempt_count |
| --- | --- | --- | --- |
| tenant-A:2026-11-23:v1 | 601 | COMPLETED | 1 |
| tenant-A:2026-11-23:v1 | 602 | RETRYABLE | 2 |
| tenant-A:2026-11-23:v1 | 603 | COMPLETED | 1 |

The overall job is marked `COMPLETED` only when every required item has finished, or has an explicitly recorded **skip** decision per business rules.

## 9. When should you choose Spring Batch?

**Spring Batch** is designed for batch data processing with **jobs/steps**, checkpoints, restarts, retries, and skips. Key concepts:

- `JobRepository` manages `JobExecution` and `StepExecution`.
- `ExecutionContext` holds recovery state; **Step ExecutionContext** is saved at chunk-step commit points.
- Restartable readers/writers can use `ExecutionContext` to remember position.
- `JobParameters` together with the job name determine the `JobInstance` and restart eligibility.

Meanwhile, **Spring Cloud Task `TaskRepository` only stores task application lifecycle**. If an application runs Spring Batch inside Spring Cloud Task, distinguish `TaskExecution` from `JobExecution` and inspect the right repository.

| Spring Cloud Task | Spring Batch |
| --- | --- |
| Tracks **one process run** | Tracks **jobs and steps/chunks** |
| Each launch gets its own TaskExecution | JobInstance restart follows dedicated rules |
| Does not provide item-level checkpoints itself | ExecutionContext supports commit-point restart |
| Can run scheduled or on demand | Suited for large data volumes, retry/skip, and granular restart |

If the problem is already a job reading and writing millions of records with scattered errors, **prefer Spring Batch's checkpoint mechanism** instead of reinventing a framework. For small business operations with a business key and results in a single database, a custom progress table may suffice.

**Note:** if Spring Cloud Task only launches a Batch job **asynchronously** and the runner returns, `TaskExecution` can finish before the job actually completes. Wait for the job outcome whenever task success is defined as Batch job success.

## 10. Hands-on fault injection and verification

Create a frozen source of 250 records, set chunk size = 100, and use the same work key.

### Scenario A: failure inside the second chunk

1. Commit chunk 1 covering records 1–100.
2. In chunk 2, intentionally throw `IllegalStateException` after writing a few rows, **before commit**.
3. Query `reconciliation_progress`: `last_committed_id` must still be `100`.
4. Count `payment_projection`: only 100 committed rows exist.
5. Rerun with the same work key and confirm the final count is 250 rows with no key duplicates.

### Scenario B: crash after commit, before final log

1. Commit chunk 1.
2. Simulate process termination immediately after transaction commit.
3. TaskRepository may lack an end timestamp; the "chunk done" log may be missing.
4. Restart with the same work key. Execution must resume from the **committed cursor** (`100`), not an estimate inferred from logs.

### Scenario C: external API succeeded but returned timeout

1. Send the same `event_id` on the initial request.
2. The target processes it, yet the client times out.
3. Retry with the **same idempotency key**.
4. The target returns or confirms the prior result without producing duplicate side effects.

### Scenario D: two processes sharing a work key

Launch two tasks concurrently against the same database. Observe row locks, transaction ordering, and unique constraints. In the example design, **two processes may alternate processing chunks**; the final result must still be accurate. If only a single process is permitted, add a lease/scheduler lock and test rejection/retry policy.

### Verification checklist

- [ ] Work key is stable across retries and tied to source scope/version.
- [ ] Source is frozen or backed by a reliable manifest/snapshot.
- [ ] Checkpoint reflects only **committed** progress.
- [ ] Results and checkpoint updates occur in the same transaction when sharing a database.
- [ ] Pre-commit failures never advance the cursor; post-commit failures never move it backward.
- [ ] Outcomes have unique keys or suitable idempotency protection.
- [ ] Failed/skipped item handling never loses unresolved items.
- [ ] Retry rules define bounded attempts, backoff, timeouts, and alerts.
- [ ] Out-of-database side effects use idempotency keys, outbox, or reconciliation.
- [ ] TaskExecution ID is logged, while recovery relies on work key/checkpoint.
- [ ] Procedures exist for dead processes, blank `END_TIME` metadata, and stale locks.

## 11. Runbook when a task partially completes

When a task fails or has not recorded completion time:

1. **Verify the actual process:** logs, pod, job, PID, timeout. `END_TIME IS NULL` in TaskRepository does not prove the JVM is still alive.
2. **Identify work key and source version:** obtain from non-sensitive arguments and request history.
3. **Read the committed checkpoint:** `upper_source_id`, `last_committed_id`, `state`, `updated_at`.
4. **Reconcile real outcomes:** business tables, outbox, files, target APIs; check for unconfirmed side effects.
5. **Check for contention:** is another process handling the same work key? Is any lease/lock still valid?
6. **Choose a recovery policy:** resume from checkpoint, retry failed items, compensate, or investigate if metadata and outcomes conflict.
7. **Rerun under control:** use the same source version's work key, creating a new TaskExecution, and monitor outcomes.
8. **Confirm completion:** expected row counts, zero duplicate keys, no outbox rows pending beyond SLA, accurate business totals.

Never manually set `last_committed_id=upper_source_id` to "clear an error," or reset the cursor to 0 and rerun without verifying idempotency.

## 12. Common design mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using taskExecutionId to key the checkpoint | Every rerun gets a new ID and cannot resume | Use a stable business work key |
| Advancing checkpoint before writing results | Data skipped after a crash | Commit results and checkpoint in the same transaction |
| Writing results and checkpoint in two transactions | Written items may be reprocessed | Add atomicity and idempotency |
| Using `OFFSET` on a mutating source | Pagination shifts, re-reading or skipping rows | Use snapshots and stable cursors |
| Advancing cursor past an unresolved item | Failed item gets lost | Track per-item state and explicit skips |
| Calling external APIs expecting DB rollback to undo them | Duplicate side effects or state drift | Idempotency keys, outbox, or reconciliation |
| Checking only `EXIT_CODE=0` | Runner might swallow errors or exit before async work finishes | Define success by verified business outcomes |
| Relying solely on single-instance lock for exactly-once | Sequential reruns can still duplicate | Unique keys/idempotency at the target system |
| Immediate unbounded retries | Load storms and cascading failures | Retries with backoff, limits, timeouts, and alerts |

## 13. Key takeaways

**TaskRepository answers "how did the Spring Cloud Task run go?"; a business checkpoint answers "how far has work durably completed and where should the next run resume?".** Both states connect via work key and execution ID, yet serve distinct roles.

To handle **partial completion** safely: **freeze the source**, **choose commit units**, **persist results and checkpoints atomically**, and **protect out-of-transaction side effects with idempotency, outboxes, and reconciliation**. When large-scale chunking, skipping, and restarts are needed, prefer **Spring Batch `ExecutionContext`** instead of rebuilding built-in capabilities.

### References

- [Spring Cloud Task Reference Guide — lifecycle and TaskRepository](https://docs.spring.io/spring-cloud-task/docs/current/reference/html/)
- [Spring Batch — Configuring a Job: Restartability](https://docs.spring.io/spring-batch/reference/job/configuring-job.html)
- [Spring Batch — ExecutionContext and restart](https://docs.spring.io/spring-batch/reference/domain.html)
- [Spring Batch — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring.html)
