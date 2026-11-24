# Database Connection Loss — Failure Recovery in Spring Batch

## 1. Scenario: The Database Becomes Unreachable Mid-Batch

An order-import job runs at 01:00, reading data from a CSV file, normalizing it in an `ItemProcessor`, and writing to PostgreSQL with `JdbcBatchItemWriter`. After 80,000 records, the database switches primary during a failover. The active connection closes; the writer throws an exception. The job must determine what committed, what must be reprocessed, and how to resume once PostgreSQL is ready.

In another system, the business database stays healthy while the database storing Spring Batch metadata loses connectivity. The job can process data yet fails to update `StepExecution`, `JobExecution`, or `ExecutionContext`. This is a crucial distinction: **in-memory success of a business operation does not mean the checkpoint was persisted**.

When a database disconnects, three operational decisions must be separated:

1. **Detection and classification:** did the failure happen in the reader, processor, writer, commit, or `JobRepository`? Is it a transient connection error, a permanent SQL bug, or an ambiguous commit outcome?
2. **Recovery:** can it retry within the same step/transaction, must it roll back and restart the `JobInstance`, or does it need investigation and reconciliation before rerunning?
3. **Data integrity:** committed items must not be lost; uncommitted items must be reprocessed properly; side effects must not duplicate outside the business contract.

This lesson belongs to **Failure recovery** in **Spring Batch Core Processing**, focusing on transactions, retries, checkpoints, restarts, JDBC connection pools, metadata, and observability during database outages.

Examples use Java 17+, Spring Boot 3.x, Spring Batch 5.x, Spring JDBC, HikariCP, and JUnit 5. Some APIs changed in Spring Batch 6.x; always verify against your target framework version before using code.

---

## 2. Two Database Roles and Two Connection-Loss Modes

### 2.1. Business Database

The business database is where the reader queries or the writer saves customer/order/invoice rows. If connectivity drops during SQL execution:

- The reader may fail to fetch the next item.
- The writer may fail when sending batch inserts/updates.
- The transaction may roll back.
- The step may become `FAILED` if retries fail or exhaust their budget.
- An appropriate restart can use the checkpoint in `ExecutionContext` to resume.

### 2.2. Spring Batch Metadata Database

`JobRepository` stores metadata such as:

- `JobInstance`: a logical run tied to a job name and identifying `JobParameters`.
- `JobExecution`: each execution attempt of a job; status `STARTED`, `FAILED`, `COMPLETED`, etc.
- `StepExecution`: step status and read/write/skip/rollback/commit counts.
- `ExecutionContext`: state needed for restart, such as offset, cursor position, or reader/writer checkpoints.

A JDBC implementation typically uses tables `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION`, `BATCH_JOB_EXECUTION_CONTEXT`, and `BATCH_STEP_EXECUTION_CONTEXT`.

If the metadata database is unavailable, Spring Batch may fail to create an execution **before business work even begins**, or fail to persist checkpoints/statuses while the step runs. If the process dies abruptly, metadata can remain `STARTED` even when no worker is actually processing.

### 2.3. Failure Scope Diagram

```text
             Scheduler / REST / Operator
                        |
                        v
                   JobLauncher
                        |
                        v
           +---------------------------+
           | JobRepository             |
           | JobExecution              |
           | StepExecution             |
           | ExecutionContext          |
           +-------------+-------------+
                         |
                         v
                METADATA DATABASE
                  BATCH_* tables
                         ^
                         |
              connection lost here
              => may fail to persist
                 execution status

      +-----------------------+
      | Chunk Step            |
      | read -> process       |
      |          -> write     |
      +-----------+-----------+
                  |
                  v
             BUSINESS DATABASE
              business tables
                  ^
                  |
           connection lost here
           => read/write/commit failure
```

The two databases may physically be the same database/schema and share a `DataSource`, or be completely separate. Recovery mechanics depend on how **`DataSource` and `PlatformTransactionManager`** are wired, not just bean names.

| Situation | Spring Batch Metadata | Business Data | Investigation Direction |
| --- | --- | --- | --- |
| Business DB down, metadata DB up | Can record `FAILED` and committed checkpoints | Running SQL fails | Bounded retry, rollback, restart |
| Metadata DB down before launch | May fail to create `JobExecution` | Likely untouched | Fix metadata DB, inspect instance before relaunching |
| Metadata DB down mid-step | May retain old status or miss final updates | Some chunks may have committed | Reconcile both sides before restarting |
| Both down together | Both job/step metadata and business transactions affected | Outcome may be unclear | Restore infrastructure, reconcile checkpoints/commits |
| DB times out at commit | Metadata may lead or lag depending on ordering | **Uncertain whether commit succeeded or failed** | Query actual state; idempotency |

**Never assume sharing one physical database automatically places all metadata and business updates inside one single transaction.** Transaction managers, datasources, propagation, and write ordering determine atomicity for each piece.

---

## 3. At Which Stage Can Failures Occur?

### 3.1. Before the Job Launches

The application cannot reach the metadata DB during `JobLauncher.run(...)`. The framework may fail to create `JobInstance`/`JobExecution`, or partially create metadata before the caller receives an error.

What to do: **query the repository after connectivity recovers**, using job name and identifying parameters to check whether an execution was created before deciding to launch again. If the client timed out after the request reached the server, retrying with random parameters can kick off a duplicate run.

### 3.2. Inside `ItemReader.read()`

Suppose `JdbcCursorItemReader` holds a JDBC cursor. When the connection breaks:

- The JDBC driver throws `SQLException`, or Spring JDBC wraps it as `DataAccessException`.
- The cursor/result set is usually invalid.
- Retrying `read()` directly on the same reader object may **fail to restore the old connection/cursor**.
- A step restart reopening the reader from the saved checkpoint may be safer.

With `JdbcPagingItemReader`, each page fetch issues a separate query; once the datasource recovers, new queries can succeed. Still, ensure a unique/stable sort key, persisted state, and that source data does not shift in ways that drop or duplicate items across pages.

### 3.3. Inside `ItemProcessor.process()`

A processor may be pure Java logic or query repositories/JDBC/HTTP. If the processor queries a database for lookups and the connection drops, distinguish:

- Transient connection errors, retryable within the chunk if the operation and resource remain valid.
- Permanent SQL bugs such as missing columns, bad mappings, or constraint violations.
- Non-database business errors, such as invalid input data.

A processor performing DB reads can be retried, yet processor side effects are not necessarily transactional. If the processor emits an event/email before failing, retries can duplicate that action.

### 3.4. Inside `ItemWriter.write(Chunk)`

A writer can write multiple items in one transaction. When JDBC loses connectivity:

- Batch SQL may have executed only partially on the database.
- The transaction may roll back or the connection may die before the outcome is known.
- Re-invoking the writer on the same chunk during retry may hit duplicate keys if partial side effects existed outside the transaction.
- You cannot infer from `write()` throwing an exception that **zero effects reached the target system**.

Especially with remote APIs, message brokers, or databases under another transaction manager, operations that succeeded before the error may not roll back with the chunk.

### 3.5. During Transaction Commit

`write()` can return cleanly yet `PlatformTransactionManager.commit(...)` fails from a dropped connection or timeout.

```text
Writer sends INSERT successfully
           |
           v
Database receives COMMIT
           |
           X  network drops while returning response
           |
     Client does not know outcome
```

The server may have committed before the response dropped, or failed to commit and rolled back. This is an **ambiguous commit outcome**. Blindly rerunning with a new ID or inserting another copy is dangerous.

Use unique business keys, idempotency, post-recovery DB state verification queries, and outcome reconciliation before retrying or restarting.

### 3.6. During `JobRepository` and Checkpoint Updates

A business transaction might commit while the repository fails to persist `ExecutionContext`/`StepExecution` due to a broken metadata connection. Restarting can then start from an old checkpoint and reprocess already written data.

When metadata and business data share the same transaction manager and transactional resource, atomicity boundaries are cleaner. With separate datasources, design for **the lack of automatic atomic commits across two sources**. Never treat an in-memory `ExecutionContext` as proof the checkpoint persisted.

---

## 4. Connections, Transactions, Chunks, and Checkpoints

In chunk-oriented processing, Spring Batch typically reads and processes a group of items before writing and committing. Example with chunk size 100:

```text
Chunk 1: records 1..100   -> write -> COMMIT
Chunk 2: records 101..200 -> write -> COMMIT
Chunk 3: records 201..300 -> failure before COMMIT
                            |
                            v
                       ROLLBACK
```

If metadata/checkpoint 200 persisted consistently, restart should resume from the last committed state rather than item 300 read in memory.

### 4.1. "Read" State Differs from "Committed" State

The reader may have returned 280 items while the last transaction only committed through 200. Items 201–280 must be eligible for reprocessing. This requires the reader to save state per the `ItemStream` contract and the writer to handle replayed items idempotently after rollback/restart.

### 4.2. `ItemStream` and `ExecutionContext`

Stateful readers/writers typically implement `ItemStream`:

```java
public interface ItemStream {
    void open(ExecutionContext executionContext)
            throws ItemStreamException;

    void update(ExecutionContext executionContext)
            throws ItemStreamException;

    void close() throws ItemStreamException;
}
```

- `open` receives the restored context when the step starts, including restarts.
- `update` writes updated state to the context at checkpoint boundaries.
- `close` releases resources.

If a delegate is wrapped inside another component, the step must recognize/register the `ItemStream` appropriately. Missing lifecycle callbacks can let a step run fine until an outage forces a restart—and then restart from the beginning.

Example flow:

```text
Execution #1:
  open(context offset=0)
  commit chunk 1 -> context offset=100
  commit chunk 2 -> context offset=200
  chunk 3 error -> rollback, step FAILED

Repository: last persisted offset=200

Execution #2 (restart same JobInstance):
  open(context offset=200)
  continue processing uncommitted items
```

Offset numbers are illustrative. With real paging/cursor readers, verify checkpoint semantics and rollback/restart behavior for that specific reader type.

### 4.3. When Retries and Rollbacks Occur

A Spring Batch fault-tolerant step can retry `read`, `process`, or `write` calls depending on policy. Some invocations repeat after rollbacks; total method invocations do not necessarily equal `readCount`/`writeCount`.

For diagnostics, collect `commitCount`, `rollbackCount`, retry attempts, exception types, and output item counts. Never deduce from seeing an exception once in logs that the DB broke exactly one transaction.

---

## 5. Exception Classification: Recoverable vs. Permanent Failures

### 5.1. Common Exceptions

In Spring JDBC, exceptions are normally translated into `DataAccessException`. Key categories to distinguish:

| Exception / Category | Typical Meaning | Handling Direction |
| --- | --- | --- |
| `CannotGetJdbcConnectionException` | Cannot obtain a JDBC connection | Check DB/pool/network; bounded retry if infrastructure is expected to recover |
| `DataAccessResourceFailureException` | Data access resource unavailable | Likely DB/network outage; usually requires infrastructure recovery |
| `TransientDataAccessException` | Category documented as potentially succeeding on retry | Bounded retry if operation is safe |
| `TransientDataAccessResourceException` | Resource temporarily unavailable | Retry/backoff after confirming retryability |
| `DeadlockLoserDataAccessException` / transient locking errors | Transaction contention or deadlock | Retry entire transaction with backoff when appropriate |
| `QueryTimeoutException` | Query exceeded timeout | Inspect load/SQL; timeout alone does not prove commit failed |
| `DuplicateKeyException` / constraint violation | Data constraint violated | Usually not an outage; handle idempotency or business error |
| `BadSqlGrammarException` | SQL/schema mismatch | Do not retry repeatedly; fix code/schema |
| `SQLTransientConnectionException` (JDBC) | Driver marks connection failure as transient | Classify by driver and root cause |
| `SQLRecoverableException` (JDBC) | May require opening a fresh connection and repeating transaction | Do not reuse the dead connection |

**Note on exception hierarchy:** real connection failures do not always sit under `TransientDataAccessException`. For example, `CannotGetJdbcConnectionException` can appear under another resource-failure branch depending on Spring JDBC/driver and version. Retrying on too narrow a superclass can miss outages, while retrying every `DataAccessException` uselessly loops on permanent SQL bugs.

### 5.2. SQLState and Vendor Error Codes

JDBC drivers expose `SQLState` and vendor error codes. For instance, many drivers use `08xxx` SQLStates for connection exceptions; PostgreSQL emits codes like `08006` and `08001` in certain scenarios. Still:

- Specific codes vary by driver and failure phase.
- Frameworks may wrap an exception across multiple layers.
- Connection timeouts can also surface as pool timeouts or network exceptions lacking an SQLState.
- SQLState is one signal, not a replacement for operation/transaction context.

A classifier can inspect the `DataAccessException` subtype, cause chain, SQLState, and operation to decide **retry, fail fast, or require reconciliation**. Never mark every `SQLException` unconditionally "retryable."

### 5.3. Classifying by Operation Matters More Than a Single Exception Name

The exact same socket timeout carries different meanings:

- An idempotent `SELECT` that has not returned rows: usually safe to acquire a new connection and re-query.
- An `UPDATE` inside a confirmed rolled-back transaction: transaction can be retried.
- A `COMMIT` with no response: outcome must be verified; blind retry can duplicate.
- A payment API call outside the transaction: must check idempotency key on the target system.

Classification should combine context: **operation + transaction boundary + idempotency + available checkpoint**.

---

## 6. In-Place Retry or Job Restart?

### 6.1. Retry Within a `StepExecution`

Retry helps with brief disruptions such as:

- Connection pool momentarily exhausted, recovering within seconds.
- Deadlocks or serialization conflicts where the transaction can rerun.
- Brief network hiccups on idempotent operations.
- Very short database failovers where a fresh connection works.

Retries require:

- Bounded attempts.
- Backoff to prevent retry storms.
- Reasonable timeouts to avoid unbounded stalls.
- Classified exceptions.
- Ability to recreate transactions/resources and preserve semantics on retry.

Retry **does not guarantee** a broken JDBC cursor can continue inside the same reader. If connectivity has not recovered or state is invalid, letting the step end `FAILED` and restarting from a checkpoint can be safer.

### 6.2. Restart Creates a New `JobExecution`

Once a Step has `FAILED` and the infrastructure root cause is fixed, restarting creates a new execution for **the same `JobInstance`**:

```text
JobInstance: importOrdersJob + businessDate=2026-11-16
    |
    +-- JobExecution #3001 FAILED
    |     reader checkpoint = 200
    |
    +-- JobExecution #3002 COMPLETED
          reader resumes from persisted checkpoint
```

In Spring Batch 5.x:

```java
Long restartedExecutionId = jobOperator.restart(3001L);
```

`restart` takes the **old JobExecution ID**, not the JobInstance ID. Preconditions: execution and job allow restarting, the job definition exists, the metadata repository is reachable, no other execution is running, and the instance is not already completed.

### 6.3. Decisions by Scenario

| Situation | Preference | Explanation |
| --- | --- | --- |
| Brief reader query timeout, connection still valid | Bounded retry if driver/reader is safe | Avoids creating a new execution for a brief glitch |
| JDBC cursor closed after network reset | Fail step then restart from checkpoint | Do not assume the old cursor heals itself |
| Writer hits deadlock with confirmed rollback | Retry transaction/chunk with backoff | Avoid retrying isolated statements individually |
| Extended metadata DB outage, job cannot persist | Restore metadata first; reconcile | Cannot guarantee checkpoints/restarts while repository is down |
| Connection lost right at `COMMIT`, outcome unsure | Reconcile output and metadata before replay | Prevents duplicate or dropped writes |
| Bad SQL syntax or missing table | Fail fast and fix config/schema | Retries only add load |
| Static business input fails validation | Skip/quarantine per business contract | Not a transient infrastructure error |
| Job `COMPLETED` and another date needs processing | Launch a new instance with new parameters | Restart is not for completed jobs |
| Old job execution stuck `STARTED` after crash | Verify live worker and follow recovery procedure | Never force restart before confirming old process stopped |

---

## 7. Configuring Fault-Tolerant Chunk Retry in Spring Batch 5

### 7.1. `StepBuilder` Example

A chunk step writing orders can configure retry for **an explicitly chosen exception set**. This example assumes reader/processor/writer beans and transaction manager are already defined in the application:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.transaction.PlatformTransactionManager;

public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager businessTransactionManager,
        ItemReader<OrderRow> reader,
        ItemProcessor<OrderRow, OrderRow> processor,
        ItemWriter<OrderRow> writer) {

    ExponentialBackOffPolicy backOff = new ExponentialBackOffPolicy();
    backOff.setInitialInterval(500L);
    backOff.setMultiplier(2.0);
    backOff.setMaxInterval(4_000L);

    return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderRow, OrderRow>chunk(
            100, businessTransactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .backOffPolicy(backOff)
        .build();
}
```

`OrderRow` is an illustrative domain data type. This setup creates a fault-tolerant step for exceptions under `TransientDataAccessException`, capped by `retryLimit(3)` total attempt rules and exponential backoff. On its own, this configuration **does not cover every database connection loss**; adjust your classifier for the actual JDBC driver exceptions, Spring exception translation, and operation involved.

### 7.2. Why Avoid `retry(Exception.class)`?

Retrying every exception can:

- Retry mapping/validation bugs that never self-resolve.
- Flood a downed database with unnecessary queries or writes during a prolonged outage.
- Mask configuration errors, delaying `FAILED` detection.
- Replay non-transactional side effects.
- Trigger a "retry storm" when multiple workers lose DB connectivity together.

Favor an allowlist of recoverable errors with **well-understood semantics**, while failing fast and alerting on permanent failures.

### 7.3. Why Avoid Manual `Thread.sleep` Inside Reader/Writer?

Writing an unbounded loop inside `ItemWriter.write` forfeits retry budget tracking, rollbacks, and stop-signal responsiveness. Use Spring Batch/Retry mechanisms when backoff is needed, and monitor duration and attempt counts. For long outages, failing the step cleanly so an orchestrator/`JobOperator` can restart once the DB recovers is far better.

### 7.4. Caution with Writer Retries

A chunk can be re-invoked after rollback. If the writer uses JDBC in the same transaction, uncommitted SQL normally rolls back with the transaction. Yet if the writer calls an external non-transactional resource or commits with an ambiguous result, retries can issue duplicate commands.

Therefore, before enabling writer retries, check:

- Which transactional resource actually rolls back?
- Is batch SQL atomic in the transaction, or auto-committed per statement?
- Do remote side effects carry idempotency keys?
- Can results be verified via query after a timeout?
- When is the checkpoint updated?

### 7.5. Skip Is Not a Remedy for Database Outages

`skip(FlatFileParseException.class)` makes sense for isolating a malformed line in a file. However, when the DB is unreachable, `skip(DataAccessException.class)` can drop thousands of items and report the job `COMPLETED` with missing output.

An outage is an **infrastructure failure** affecting the whole pipeline; prefer bounded retry followed by fail/restart. Skip only when business rules explicitly define an unprocessable single record and route it to an error/quarantine store—never use skip to paper over DB outages.

---

## 8. HikariCP Connection Pools After a Database Outage

Spring Boot 3.x commonly uses HikariCP for JDBC datasources. HikariCP manages pooled connections; when a connection breaks, the pool can evict it and open fresh ones once the database returns. However, **a dead physical connection cannot be "healed" mid-transaction**.

### 8.1. Timeouts to Distinguish

| Setting / Concept | What It Controls | What It Does Not Solve |
| --- | --- | --- |
| `spring.datasource.hikari.connection-timeout` | Max wait to borrow a connection from the pool | Does not bound already running queries |
| `validation-timeout` | Max time allowed for connection validation | Not a transaction timeout |
| `idle-timeout` | Eviction threshold for idle connections, subject to pool bounds | Does not repair a broken transaction |
| `max-lifetime` | Max connection age before Hikari retires it | Does not guarantee DB availability |
| JDBC driver connect timeout | Time to establish the network socket | Not a retry budget |
| JDBC driver socket/read timeout | Waiting for database responses | Can leave commit outcomes ambiguous |
| Statement/query timeout | Caps SQL execution duration | Does not replace rollback/reconciliation |
| Batch retry backoff | Pause between retry attempts | Does not automatically fix metadata/checkpoints |

Tune values to match SLAs, expected failover durations, load, and downstream limits.

### 8.2. Example Bounded Wait Configuration

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 10
      connection-timeout: 5000
      validation-timeout: 2000
      max-lifetime: 1800000
```

This example waits 5 seconds for a connection; it does **not** mean "after 5 seconds Spring Batch restarts the job." If PostgreSQL failover takes 60 seconds, several short retries may all fail and transition the job to `FAILED`. An orchestrator must inspect health/recovery signals before restarting later.

### 8.3. Hikari Pool Does Not Replace Observability

When the database goes down:

```text
Worker threads -> request JDBC connection
      |
      v
Hikari pool
  active  = 10
  idle    = 0
  pending = 30
      |
      v
Database unreachable
```

Looking only at writer errors makes it easy to blame writer code while the pool is actually stalled waiting on an unresponsive DB. Watch active/idle/pending counts, connection acquisition times, DB health, and network telemetry. Once the DB recovers, the pool can open new connections, yet tasks using failed connections still require proper rollback/restart.

### 8.4. Be Careful with Long-Lived Cursor Connections

`JdbcCursorItemReader` can hold a single connection/cursor across many reads. Dropping the connection mid-stream destroys the cursor; even after the pool recovers, that reader instance does not automatically rebuild the cursor at a safe offset. Persisted `ExecutionContext` checkpoints for restart matter far more than hoping a new connection revives an old cursor.

---

## 9. Choosing Readers Compatible with Recovery

### 9.1. Cursor Readers

`JdbcCursorItemReader` streams a result set with lower memory overhead than loading everything at once. However:

- It can rely on long-lived connections.
- Connection loss invalidates the cursor.
- Source data may mutate between initial execution and restart.
- Requires `saveState`, stable reader names, and accurate checkpoints.

For safe restarts, never casually rename a reader/key after deployment, or persisted `ExecutionContext` entries may fail to match.

### 9.2. Paging Readers

`JdbcPagingItemReader` reads page by page, issuing a dedicated query per page, which avoids holding long-lived cursors. Still:

- Sort keys must be **unique and stable**.
- Inserts/deletes/updates during execution can shift the item set.
- Page size differs from chunk size and has its own memory/network impact.
- Restart position depends on reader contracts and source data stability.

When source data mutates continuously, consider snapshots, cutoff timestamps, deterministic ordering, or key-range partitioning to avoid missing rows.

### 9.3. File Reader with Database Writer

This is the easiest recovery case to reason about: input files are usually immutable, reader checkpoints save the read position, and the writer persists to the DB. After a DB outage and restart, the reader resumes from the last committed offset. Even so, the writer must stay idempotent because a commit-time disconnect may have persisted output even if metadata lagged.

### 9.4. Never Persist a "Read" Offset Independently as a Commit

A reader incrementing an `offset` per item has `update` called by the framework at checkpoints, but if custom code commits that offset to a separate database before the writer finishes, the offset can advance ahead of business data. Restarting would then skip unwritten items.

Let checkpoints follow Spring Batch's `ItemStream` lifecycle and understand transaction boundaries. If an external watermark is maintained outside Spring Batch, manage it alongside output state or enforce explicit reconciliation.

---

## 10. Idempotent Writers to Survive Ambiguous Commits

### 10.1. Why Idempotency Matters

Suppose a chunk contains order IDs 201–300. The client sends SQL, the database commits the chunk, and the `commit` response is lost. `JobRepository` cannot confirm the checkpoint persisted. On restart, those orders may be passed to the writer again.

If every write is a plain insert without unique constraints, the database can end up with two copies of the same order. A robust design defines a **business key** so replaying an item yields a valid outcome.

### 10.2. Unique Constraints

PostgreSQL example:

```sql
CREATE TABLE imported_orders (
    source_system VARCHAR(40) NOT NULL,
    external_order_id VARCHAR(120) NOT NULL,
    business_date DATE NOT NULL,
    amount NUMERIC(18, 2) NOT NULL,
    imported_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uq_imported_order
        UNIQUE (source_system, external_order_id)
);
```

The unique key enforces that an order from a given source appears once. Pick keys matching domain rules; you may need to include version or business date if external IDs are reused across periods.

### 10.3. UPSERT with Clear Semantics

PostgreSQL supports:

```sql
INSERT INTO imported_orders (
    source_system,
    external_order_id,
    business_date,
    amount,
    imported_at
)
VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
ON CONFLICT (source_system, external_order_id)
DO UPDATE SET
    business_date = EXCLUDED.business_date,
    amount = EXCLUDED.amount;
```

If the job restarts and rewrites the same order, the statement updates existing state rather than creating a second row. Still, UPSERT is not a silver bullet:

- If the order legitimately changed after the prior import, overwriting with older data can be wrong.
- If triggers or downstream events fire on UPDATE, repeated upserts still produce side effects.
- Append-only accounting may require idempotent ledger events instead of updates.
- If the writer sends emails or payments, local database unique constraints do not protect external systems unless an idempotency key is passed downstream.

An idempotent writer needs a **business contract**, not just SQL that ignores duplicate keys.

### 10.4. Transactional Outbox for Out-of-DB Side Effects

When Batch writes order state and must emit events, save an outbox record in the same database transaction:

```text
Chunk transaction
   |
   +-- UPSERT imported_orders
   |
   +-- INSERT outbox_event (unique event_key)
   |
   +-- COMMIT
            |
            v
Outbox publisher reads unsent events
            |
            v
Message broker / API
```

Outbox closes the gap between "DB committed" and "event emitted," though consumers/publishers must still be idempotent since redeliveries can occur. When business DB and metadata DB are separate, outbox **does not create an atomic transaction with Spring Batch JobRepository**; restarts must still handle business writes racing ahead of checkpoints.

---

## 11. How Single vs. Dual Datasources Affect Recovery

### 11.1. Single Datasource

An application may share one `DataSource` between `JobRepository` and JDBC writers. When the step uses a matching JDBC transaction manager, chunk updates and metadata updates can participate in consistently managed transactions per configuration.

Always verify the **actual** Spring Batch wiring, transaction propagation, connection handling, step type, and repository behavior. Never assume every metadata write shares one physical transaction with business SQL merely because the URLs match.

### 11.2. Two Separate Datasources

```text
Spring Batch JobRepository
    |
    v
metadataDataSource -> DB A (BATCH_*)

JdbcBatchItemWriter
    |
    v
businessDataSource -> DB B (orders)
```

If the chunk writer commits on DB B while the metadata checkpoint fails on DB A, states diverge. Two local transaction managers do not automatically form a distributed atomic commit.

Safe strategies:

- Stateful readers with persisted checkpoints whenever possible.
- Idempotent writers to handle chunk replays.
- Reconciliation between metadata and business output.
- Transactional outbox for suitable side effects.
- For ultra-strict multi-resource atomicity, evaluate distributed/XA transactions only if the infrastructure genuinely supports them and operational costs are acceptable; never treat XA as the default for all batches.

### 11.3. The Metadata Database Must Be Durable

For jobs needing restarts after process death, back JDBC `JobRepository` with a durable database surviving restarts. In-memory H2 is only suited for single-JVM restart tests while the DB instance stays alive; history vanishes once the JVM exits.

If the metadata database is permanently lost while business output remains, launching a new job with a random `run.id` will not automatically reconstruct unfinished obligations. Plan backup/restore or state rebuilds reconciled from business tables.

---

## 12. Recovering Jobs with `JobOperator`

### 12.1. Restart Preconditions

A `FAILED` or `STOPPED` `JobExecution` can be restarted when:

- The metadata repository is reachable and holds execution/context history.
- The current job definition is compatible and registered so the operator can locate it.
- The job permits restarting; `preventRestart()` is not configured.
- The JobInstance has no `COMPLETED` execution and no other running execution.
- Steps have not exceeded `startLimit`, and data/checkpoints remain valid.
- The database outage is resolved and side effects are reconciled enough to proceed.

In Spring Batch 5.x:

```java
Long nextId = jobOperator.restart(failedExecutionId);
```

The method takes the **old JobExecution ID** and returns the new execution ID. Depending on synchronous/asynchronous launchers, receiving an ID does not mean the job has `COMPLETED`.

### 12.2. Inspecting Metadata Before Triggering Restart

```java
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.launch.JobOperator;

public class DatabaseFailureRecovery {

    private final JobExplorer explorer;
    private final JobOperator operator;

    public DatabaseFailureRecovery(
            JobExplorer explorer,
            JobOperator operator) {
        this.explorer = explorer;
        this.operator = operator;
    }

    public long restartAfterDatabaseRecovered(long executionId)
            throws Exception {

        JobExecution previous =
            explorer.getJobExecution(executionId);

        if (previous == null) {
            throw new IllegalArgumentException(
                "Unknown JobExecution: " + executionId);
        }

        BatchStatus status = previous.getStatus();

        if (status != BatchStatus.FAILED &&
            status != BatchStatus.STOPPED) {
            throw new IllegalStateException(
                "Execution status does not permit restart: "
                    + status);
        }

        // Other critical safety checks are performed
        // at the operations layer before calling this method:
        // DB health, actual running workers, side effects,
        // job definition compatibility, newer executions.
        return operator.restart(executionId);
    }
}
```

This precheck gives clearer errors but does not prevent races: after reading `FAILED`, another node could restart the same JobInstance. `JobOperator`/`JobRepository` still enforce runtime checks. Never catch exceptions and tack on a new identifying timestamp to bypass an already-running instance.

### 12.3. Handling Executions Stuck in `STARTED`

If the JVM dies suddenly before updating status, the repository may still show `STARTED` even though the worker is gone:

```text
Metadata DB:
  JobExecution #901 = STARTED
Runtime:
  Old pod is dead; no worker processing
```

This requires **operational state recovery**, not an ordinary `FAILED` restart. Procedure:

1. Confirm no other process/worker is still running the job.
2. Inspect committed transactions and remaining business data.
3. Follow metadata recovery procedures fitting **your Spring Batch version and operational policy** to bring the instance into a restartable state.
4. Once metadata is valid, restart and monitor the new execution.

Never run manual `UPDATE BATCH_JOB_EXECUTION SET STATUS='FAILED'` as a generic fix: consider versions, counters, contexts, open transactions, whether the old process is still alive, and JobRepository consistency.

**Version note:** Spring Batch 6.x adds operator recovery APIs such as `recover` for executions stuck after crashes; examples here target Spring Batch 5.x and do not assume 6.x APIs exist in 5.x.

---

## 13. Disconnects Right Before and Right After Commit: Analyzing Three Scenarios

### Scenario A — Confirmed Rollback

```text
Order 1..100  -> COMMIT
Order 101..200 -> COMMIT
Order 201..300 -> writer exception
confirmed transaction rollback
JobExecution -> FAILED
```

When the DB returns, restart from checkpoint 200; items 201..300 are reprocessed. When the JDBC writer shares the transaction with no external side effects, this case is fairly straightforward.

### Scenario B — Ambiguous Commit Outcome

```text
Order 201..300 -> DB receives COMMIT
Network drops right when server responds
Client receives connection error
```

Records 201..300 may or may not be in the database. Query by business key to reconcile; an idempotent writer keeps chunk replays safe. Reading a "connection reset" message alone cannot tell whether commit succeeded.

### Scenario C — Business DB Commits Then Metadata DB Drops

```text
DB B: orders 201..300 COMMITTED
DB A: checkpoint still offset=200
Process dies
```

On restart, Batch may re-read 201..300. With unique constraints/idempotent upserts, final data remains accurate. If the writer blindly appends without business keys or fires non-transactional side effects, duplicates occur.

**Lesson:** Never treat Spring Batch's restart support as proof of universal exactly-once behavior across external systems. Correctness depends on transaction boundaries, metadata persistence, and idempotent output design.

---

## 14. Handling Outages Longer Than the Retry Budget

Suppose a cluster runs 50 concurrent jobs and a database failover takes 3 minutes. If every item retries aggressively without backoff, 50 jobs can fire thousands of connection attempts per second right as the DB tries to recover.

Design in layers:

```text
Short transient error
    |
    v
Bounded retry + exponential backoff
    |
    +-- Succeeded -> continue chunk
    |
    +-- Budget exhausted -> step FAILED
                           |
                           v
                  Orchestrator records
                           |
                           v
                 DB health + cooldown
                           |
                           v
                    Operator restart
                           |
                           v
                    Reconcile output
```

### 14.1. Why Exponential Backoff?

Suppose three attempts pause 0.5 seconds then 1 second (for example). Instead of hammering continuously, backoff relieves pressure on a recovering database.

In multi-node clusters, consider **jitter** so all jobs do not retry at the exact same instant. If a default backoff lacks jitter, configure an alternative policy or spread retries in the orchestration layer.

### 14.2. Does a Circuit Breaker Replace Restart?

A client-side circuit breaker stops sending requests to a broken DB/service for a cooldown period. Yet it does not automatically flip a `FAILED` `JobExecution` to completed, restore reader checkpoints, or guarantee written items are duplicate-free.

A circuit breaker can support **admission control** or transient I/O protection; Batch recovery still requires repositories, checkpoints, and orchestration.

### 14.3. Schedulers Must Prevent Uncontrolled Backlogs

If daily/hourly jobs keep launching while the DB is down, piles of executions become `FAILED` and need restarts. Schedulers should defer/queue new slots or throttle active jobs based on DB health. Once the DB recovers, catch up under quotas and actual state rather than launching every missed slot simultaneously.

---

## 15. Observability During Database Disconnections

### 15.1. Metrics and Signals to Watch

| Source | Signal / Metric | Meaning |
| --- | --- | --- |
| Spring Batch | `BatchStatus`, `ExitStatus` | Whether job/step finished or is still running |
| Spring Batch | `readCount`, `writeCount`, `commitCount`, `rollbackCount` | How much processed or rolled back |
| Spring Batch | `ExecutionContext` checkpoint read via `JobExplorer` | Persisted restart position |
| HikariCP | active/idle/pending connections | Whether the pool is congested or exhausted |
| JDBC driver | connect timeout, socket timeout, SQLState, query failures | Distinguishes network vs. query errors |
| Database | availability, failover, replication lag, locks, active sessions | Infrastructure root cause |
| Application | retry attempts, backoff duration, failure count | Whether a retry storm is happening |
| Business output | unique business keys, checksums, reconciliation gaps | Whether all expected records wrote without duplicates |

Common Hikari/Micrometer metrics are exposed via Micrometer, though exact names and tags vary by version and registry. Inspect your actual metrics/Prometheus endpoint before configuring alerts.

### 15.2. Contextual Logs Without Sensitive Data

An outage log should include:

```text
event=database_connection_lost
jobName=importOrdersJob
jobExecutionId=3001
stepName=importOrdersStep
batchStatus=FAILED
errorClass=CannotGetJdbcConnectionException
sqlState=08006
retryAttempt=3
metadataCheckpoint=200
databaseRole=business
correlationId=batch-3001
```

Never log usernames/passwords, raw connection strings with secrets, payment card data, or full `ExecutionContext` dumps if sensitive fields exist. SQLState/errorClass above are illustrative; capture them from actual exceptions.

### 15.3. Business-Impact Alerting

Instead of counting exceptions alone, alert on:

- Critical jobs missing completion deadlines.
- Database-caused `FAILED` executions exceeding thresholds.
- Continuously climbing Hikari pending connections.
- Database unreachable with excessive time since the last commit/checkpoint.
- Queue/backfill lag exceeding SLAs.
- Gaps between due source records and completed output business keys.

A single successful retry may not warrant paging on-call; a day missing a report even with zero `FAILED` executions is a genuine business incident.

---

## 16. Integration Testing: Simulating Transient Writer Failures

The first testing layer can use a writer test double throwing `TransientDataAccessResourceException` on the first few attempts before succeeding. This verifies retry wiring and Batch outcomes, **not yet real JDBC connection loss**.

### 16.1. Fault-Injecting Writer

```java
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriter;
import org.springframework.dao.TransientDataAccessResourceException;

public class FlakyWriter implements ItemWriter<Integer> {

    private final AtomicInteger attempts = new AtomicInteger();

    @Override
    public void write(Chunk<? extends Integer> chunk) {
        int attempt = attempts.incrementAndGet();

        if (attempt <= 2) {
            throw new TransientDataAccessResourceException(
                "Simulated temporary database outage");
        }

        // Fixture: record items if the test needs to assert output.
    }

    public int attempts() {
        return attempts.get();
    }
}
```

This writer touches no database, so it only tests **retry wiring**. Every call must leave chunk input replayable; to verify real rollbacks, use JDBC transactions and a test datasource.

### 16.2. Expected Test Behavior

Suppose a step has:

- A reader producing one chunk of items.
- `FlakyWriter` as the writer.
- Fault-tolerant config retrying `TransientDataAccessException` with limit 3.
- Short backoff in tests.
- Working test `JobRepository`.

Upon launch:

```java
JobExecution execution =
    jobLauncherTestUtils.launchJob(parameters);

assertEquals(BatchStatus.COMPLETED, execution.getStatus());
assertEquals(3, flakyWriter.attempts());
```

These two assertions are meaningful only when fixtures are reset, there is a single logical writer invocation, and tests do not share the fixture concurrently. Add output assertions confirming the writer succeeded exactly once per business contract.

### 16.3. Testing Exhausted Retry Budgets

Change the writer to throw unconditionally, then assert `JobExecution`/`StepExecution` transitions to `FAILED` once retries exhaust. If the metadata database also drops, `JobRepository` may fail to save `FAILED`; that is a separate integration scenario that cannot be simulated solely by having the writer throw.

### 16.4. Unit Testing Classification

Extract exception classification into its own component and test:

- `TransientDataAccessResourceException` is treated as transient.
- `BadSqlGrammarException` is not retried.
- Ambiguous commit errors yield `RECONCILE_REQUIRED` rather than blind retries.
- Errors exhausting the retry budget route to restart/orchestration instead of infinite loops.

If using driver/vendor error codes in practice, construct `SQLException` cause chains with matching SQLStates to test the classifier under realistic conditions.

---

## 17. Integration Testing Real Disconnections with Testcontainers

### 17.1. Why H2 Is Not Enough

In-memory H2 works well for metadata tests and basic transaction semantics. Yet it does not faithfully reproduce mid-query TCP resets or PostgreSQL/Oracle failovers:

- Different network drivers, socket timeouts, and pool behaviors.
- Different locking/isolation characteristics from production.
- No primary failover, connection termination, or proxy latency.
- Driver exception types and cause chains can differ.

For production PostgreSQL, use Testcontainers PostgreSQL; when controlled network cuts are required, pair it with Toxiproxy or equivalent fault-injection tools.

### 17.2. Designing an Outage Test

A trustworthy fixture separates the metadata database from the business database so you can **deliberately disconnect the business DB while `JobRepository` still records failed status**:

```text
Spring Batch metadata  -> stable test DB A
Spring Batch writer    -> PostgreSQL Testcontainer B
                              |
                              v
                       network fault proxy
```

Procedure:

1. Provision schema, unique constraints, and fixed input data.
2. Run a job with chunk size 20; ensure at least two chunks commit.
3. At a deterministic point, sever business DB connectivity via the proxy or terminate the backend connection.
4. Wait for the job to reach a terminal state with an explicit timeout; inspect the actual exception.
5. Via `JobExplorer`, re-read persisted `StepExecution` and `ExecutionContext`.
6. Restore the network and verify the datasource can open new connections.
7. If `JobExecution` is `FAILED` and restart is valid, restart with **the same identifying `JobParameters` / `JobInstance`**.
8. Assert the final execution is `COMPLETED` and business keys are complete with no missing/duplicate rows.
9. When deliberately severing right at commit, verify both commit-succeeded and commit-rolled-back paths via reconciliation rather than assuming one outcome.

This is a **test design**, not a standalone Testcontainers snippet that configures a fault proxy automatically. Network fault injection, container port mapping, and cutoff triggers must be implemented for your project's Testcontainers/datasource setup.

### 17.3. Testing Isolated Metadata DB Loss

In a second scenario, keep the business DB healthy while cutting the metadata JDBC DB:

- The test should observe execution/checkpoint creation or updates failing.
- After recovery, query real metadata records rather than trusting old in-JVM statuses.
- Reconcile committed business data against persisted checkpoints.
- Follow version/framework procedures to handle stale `STARTED` states.
- Only then restart, ensuring the writer handles already-persisted items idempotently.

This scenario catches dual-datasource design flaws much faster than tests that merely make a writer throw exceptions.

### 17.4. Avoid Uncontrolled `Thread.sleep` in Tests

If you sever the database "after 2 seconds" while CI runs slower or faster than a laptop, the fault may strike before the first chunk or after the job finishes. Instead, have the fixture signal after N committed chunks, then trigger the network fault. Use latches/events and timeouts rather than wall-clock sleeps.

---

## 18. Sample Runbook for Database Connection Loss

### Initial State

```text
Job:          dailyOrderImport
JobInstance:  #87
JobExecution: #4100
Step:         importOrdersStep
Business DB:  PostgreSQL (unavailable)
Metadata DB:  JDBC repository (available)
Step status:  FAILED
Checkpoint:   last committed page/key = 5000
```

### 18.1. Determine Scope

1. Confirm which database role failed: business DB, metadata DB, or both.
2. Test fresh connections from application nodes using real health checks, not just host pings.
3. Inspect actual `JobExecution`/`StepExecution` records via `JobExplorer`.
4. Capture exception class, SQLState, transaction outcome, and failure timestamp.
5. Check whether other jobs sharing the datasource failed en masse.

### 18.2. Restore Infrastructure and Assess Impact

1. Restore database, permissions, network, and connection pools.
2. Confirm replication lag or failover has stabilized for required operations.
3. Identify the **persisted** checkpoint in the repository.
4. Reconcile business output against the checkpoint, especially chunks near the disconnect timestamp.
5. Check unique business keys and external side effects.
6. Confirm no new execution is already running before issuing a restart.

### 18.3. Restart the Exact Instance

If execution `4100` is `FAILED`, restartable, and reconciled:

```java
Long newId = jobOperator.restart(4100L);
```

Record `newId` and monitor `BatchStatus` until terminal. With an async launcher, receiving an ID does not prove job completion.

If the execution remains `STARTED` from a crash, resolve status via the recovery procedure first; never hack SQL to force an immediate restart. If the `JobInstance` is already `COMPLETED`, do not restart the old run; investigate whether only a dashboard/ledger update lagged or new work arrived.

### 18.4. Verify Completion

- New `JobExecution` belongs to the same `JobInstance`.
- Terminal status is `COMPLETED`.
- Previously completed steps did not rerun outside intentional policy.
- Failed step resumed from the proper checkpoint.
- Zero duplicate business keys; total records/amounts/checksums match source.
- External event/API side effects reconciled.
- Scheduler/queue no longer fires duplicate runs for the same business date.
- Incidents/alerts closed only after business output is verified accurate.

---

## 19. Common Mistakes

| Mistake | Why It Is Dangerous | Better Practice |
| --- | --- | --- |
| Retrying every `Exception` endlessly | DB downtime causes retry storms; permanent SQL bugs never heal | Classify errors, bound attempts, and add backoff |
| Using `skip(DataAccessException.class)` for outages | Job can finish `COMPLETED` while dropping many items | Fail/restart outages; reserve skip for permitted bad records |
| Seeing `COMMIT` timeout and assuming rollback | Server may have committed before response dropped | Reconcile business state, use idempotent writers |
| Adding a new identifying UUID on each retry | Creates new `JobInstance`, loses checkpoints, causes duplicates | Keep stable job parameters; restart old instance |
| Trusting in-memory `ExecutionContext` persisted | Repository update may have failed | Re-read via `JobExplorer` |
| Assuming Hikari reconnect revives cursor readers | Old cursors can be invalid | Restart reader from checkpoint |
| Manually editing `BATCH_JOB_EXECUTION.STATUS` on stuck `STARTED` | Metadata/process can diverge | Verify workers and follow controlled recovery procedure |
| Assuming business DB and metadata DB are always atomic | Two transactional resources can commit out of sync | Idempotency + reconciliation; clear transaction design |
| Testing only with fake writer exceptions | Misses socket resets and ambiguous commits | Add fault-injection integration tests |
| Ignoring connection pool metrics | Cannot tell pool exhaustion from DB outage | Monitor Hikari active/idle/pending and DB metrics |
| Restarting the instant DB responds to ping | Primary failover/replication may still be settling | Verify operation-level readiness and SLAs |
| Asserting only `BatchStatus.COMPLETED` | Business output may have gaps or duplicates | Assert business output + checkpoints |

---

## 20. Practice Exercises

### Exercise 1 — Classifying Failures

A job has a PostgreSQL reader, pure Java processor, and PostgreSQL writer. Successive runs encounter:

1. `CannotGetJdbcConnectionException` when starting to read.
2. `BadSqlGrammarException` after deploying without a migration.
3. `DuplicateKeyException` for an existing order ID.
4. Socket timeout while the transaction is committing.

Explain which cases are retryable, which must fail fast, which require reconciliation, and why one retry rule cannot cover all four.

### Exercise 2 — Configuring a Fault-Tolerant Step

Create a step with chunk size 25 and a `FlakyWriter` that fails the first two attempts with `TransientDataAccessResourceException` before succeeding. Configure retry limit 3 and a small backoff.

Verify `JobExecution COMPLETED`, writer call count, and that business items write exactly once per fixture. Then make the writer fail unconditionally and verify the step becomes `FAILED` once budget runs out.

### Exercise 3 — Connection Loss After Two Chunks

Build a job importing 100 items with chunk size 20; after 40 items commit, trigger an outage on the next chunk. Use `JobExplorer` to read the last persisted checkpoint. Restart and verify all 100 output items exist without duplicates.

Extension: deliberately trigger a timeout near COMMIT, evaluate both commit-succeeded and commit-failed possibilities, and build an idempotent writer so both converge to correct results.

### Exercise 4 — Separate Datasources

Set up metadata DB A and business DB B. When writing to DB B succeeds yet DB A drops before checkpointing, simulate JVM termination.

Task: explain how the job could reprocess committed items, design unique keys and reconciliation to prevent duplicates, and safely recover the execution.

### Exercise 5 — Cursor vs. Paging

Build both `JdbcCursorItemReader` and `JdbcPagingItemReader` over the same dataset with a stable sort key. Sever the connection mid-read, observe the exceptions, and check recovery in a new execution.

Task: explain the limits of retrying over a closed cursor and the role of `ItemStream`/`ExecutionContext`.

### Exercise 6 — Production Runbook

Scenario: a financial reconciliation job has written 70% of results, PostgreSQL fails over primary, and `JobRepository` remains `STARTED` after the container was killed. Write a procedure to verify the old worker stopped, restore the DB, reconcile committed transactions, resolve metadata status per version, and restart the exact instance.

Include necessary metrics/alerts and how to protect out-of-transaction APIs or events.

---

## 21. Core Principles

Database connection loss in Spring Batch is more than an `SQLException`. It can simultaneously affect **business transactions**, **checkpoints**, **JobRepository metadata**, and **restart workflows**. Safe retries depend on resource recoverability and operation idempotency. Safe restarts depend on persisted metadata and reconciling real data.

Keep these three distinctions clear:

- **Retry**: handles transient failures within the same execution logic using bounded attempts and backoff.
- **Restart**: creates a new `JobExecution` for **the same `JobInstance`** from saved state after resolving the failure.
- **Reconciliation**: compares metadata against business data whenever commit/connection outcomes are uncertain before deciding to reprocess.

Sound design not only lets jobs run again, it guarantees **zero lost data and zero duplicate side effects** when the database drops at the worst possible moment.

## 22. References

- [Spring Batch — Configuring a Step / Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): chunks and transaction boundaries.
- [Spring Batch — Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html): fault-tolerant retry and recovery.
- [Spring Batch — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): `open/update/close` and checkpoints.
- [Spring Batch — Job Restart](https://docs.spring.io/spring-batch/reference/job/configuring.html): `JobInstance`, `JobExecution`, and restartability.
- [Spring Batch — Advanced Metadata Usage](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html): `JobExplorer` and `JobOperator`.
- [Spring Batch — Batch Metadata Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): `BATCH_*` tables.
- [Spring Framework — Data Access Exception Hierarchy](https://docs.spring.io/spring-framework/reference/data-access/dao.html): Spring JDBC exception translation.
- [Spring Boot — Data Access / SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): JDBC datasource configuration.
- [HikariCP README](https://github.com/brettwooldridge/HikariCP): connection pool configuration and timeout semantics.
- [Testcontainers — Databases](https://java.testcontainers.org/modules/databases/): integration testing with production-like databases.
