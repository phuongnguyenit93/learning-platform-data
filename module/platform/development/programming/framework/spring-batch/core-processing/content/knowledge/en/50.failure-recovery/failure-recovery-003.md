# Writer Failures in Spring Batch: Detection, Rollback, and Recovery

In a batch job, `ItemWriter` is where processed results are written to a database, file, message broker, or external API. A failure here is often more serious than failing to read an item: data may already have been written before the failure, part of a chunk may not have committed, or an external system may have received a side effect that Spring Batch cannot undo.

A **writer failure** is a situation where a write operation fails, produces an uncertain outcome, or cannot uphold the output contract. To recover properly, you must distinguish **the writer was invoked** from **the data was committed**, determine which resources genuinely participate in the transaction, choose among **retry**, **skip**, **fail-fast**, and **restart**, and protect the output against duplicate writes.

This article belongs to **Spring Batch Core Processing → Failure recovery**, focusing on chunk-oriented processing in Spring Batch 5.x and later with `ItemWriter.write(Chunk<? extends T>)`. Examples use Java 17+ and JDBC/PostgreSQL where concrete SQL is needed; the principles around transaction boundaries and replay apply to other writers once each resource's semantics are accounted for.

## 1. Where Does the Writer Sit in a Chunk's Lifecycle?

In a chunk-oriented step, the typical flow is:

~~~mermaid
flowchart TD
    A["Start chunk transaction"] --> B["ItemReader reads up to N items"]
    B --> C["ItemProcessor processes each item"]
    C --> D["ItemWriter.write(chunk)"]
    D -->|Write succeeds| E["Update checkpoint / required metadata"]
    E --> F["Commit transaction"]
    D -->|Writer throws exception| G["Roll back transaction"]
    E -->|Commit fails| G
    G --> H{"Error handling policy"}
    H -->|Transient error| I["Bounded retry"]
    H -->|Skip allowed| J["Isolate and skip bad item per policy"]
    H -->|Unrecoverable| K["Step FAILED"]
    I --> D
    J --> D
    F --> L["Start next chunk"]
~~~

The diagram illustrates the **conceptual flow**: internal details of a fault-tolerant step, retries, skips, item re-reading, and actual commits depend on the reader, writer, transaction manager, and configuration. What remains constant is that **each chunk is a common transaction boundary**, whereas the entire job does not by default run inside a single large transaction.

For example, with `chunkSize = 3`, the reader passes items A, B, and C to the writer. The writer issues write statements for A and B, and on C the database returns an error. If all three statements share **the same step transaction** and that transaction rolls back cleanly, A and B are **not committed**, even though the writer code ran over them.

Conversely, if the writer calls an HTTP API to create transactions A and B and the API fails on C, rolling back the step's JDBC transaction **does not remove** transactions A and B already accepted by the external API. In that case, you need idempotency, an outbox, or a dedicated cross-system recovery mechanism.

### The ItemWriter Contract

Spring Batch 5.x defines:

~~~java
public interface ItemWriter<T> {
    void write(Chunk<? extends T> chunk) throws Exception;
}
~~~

A writer can throw an exception to signal failure. The interface itself **does not create a transaction**; transaction boundaries are configured on the `Step`, while the target write resource determines whether operations commit or roll back with that transaction.

In Spring Batch 4.x, `ItemWriter.write` took `List<? extends T>`. When reading examples online, watch for API differences across versions.

## 2. Three Levels of "Written" That Must Not Be Confused

During a write operation, three distinct states can be observed:

| State | Example | What Can Be Concluded |
|---|---|---|
| **Writer was invoked** | `write(chunk)` begins executing. | Not yet proof of any persisted storage outcome. |
| **Statements ran or data flushed** | JDBC sent `INSERT`, JPA flushed. | Changes may still sit inside an uncommitted transaction. |
| **Transaction committed successfully** | Transaction manager confirms commit. | Changes belong to a confirmed durable transaction per resource guarantees. |

In particular, `ItemWriteListener.afterWrite(...)` is normally invoked after the writer finishes **but before the chunk transaction commits**. Consequently, emitting a `PAYMENT_PERSISTED` event or sending an email from `afterWrite` can report success prematurely. If the subsequent commit fails, recipients will have seen a notification for data that never committed.

If post-commit actions are needed, bind them appropriately to transaction commit or design a transactional outbox. For logging, you can log "writer call completed," but never infer "chunk committed" from `afterWrite`.

### Previously Committed Chunks Do Not Roll Back When a Later Chunk Fails

Suppose the input has eight items and `chunkSize = 3`:

| Chunk | Items | Outcome |
|---|---|---|
| 1 | 1, 2, 3 | Committed successfully. |
| 2 | 4, 5, 6 | Writer fails when writing item 6; chunk 2 transaction rolls back. |
| 3 | 7, 8 | Never runs if the step fails on chunk 2. |

When the step ends as `FAILED`, **chunk 1 typically remains in the database**. Restarting does not mean "starting over from an empty database." Spring Batch uses metadata and `ExecutionContext` to resume when the reader/step is properly configured for restart; the writer must also tolerate replay scenarios.

## 3. Classifying Writer Failures Before Choosing Recovery

Not every exception is suitable for retry. You must understand whether the error can resolve on its own or stems from data/configuration.

| Error Type | Example | Typical Recoverability |
|---|---|---|
| **Transient infrastructure error** | Deadlock, lock timeout, brief DB connection blip | Bounded retry with appropriate backoff, if the operation is safe to repeat. |
| **Data constraint violation** | Unique key, foreign key, not-null violation | Usually requires data handling, idempotency design, or policy-driven skip; blind retry rarely helps. |
| **Output type/format error** | Writer converts a value rejected by DB/target | Fix mapper/transform or reject item per business rules. |
| **Code/configuration bug** | Wrong SQL column, unmigrated schema, wrong transaction manager | Fail fast and fix; retry delays detection. |
| **Resource exhaustion** | Disk full, DB quota exceeded, unwritable file | Restore resources then restart; avoid aggressive retries. |
| **Explicit HTTP/broker error** | HTTP 429/503, broker temporarily unavailable | Retry with backoff if the endpoint and request support idempotency. |
| **Uncertain outcome** | Timeout after sending HTTP; connection lost right at commit | Never assume side effects did not occur; use idempotency keys, status lookup, or reconciliation. |
| **Isolated per-item error** | One record violates a documented output rule | Can be skipped or quarantined if business permits and the writer can isolate failures. |

This classification **guides policy**, rather than acting as a rigid law for every system. For instance, the same `DataIntegrityViolationException` might represent a benign duplicate to ignore or a critical bug showing broken business logic.

### Commit-Time Errors Differ from Errors Inside write()

Even when `write(chunk)` returns normally, the transaction can still fail during flush or commit. With JPA, SQL may be deferred until flush; with JDBC, a constraint or commit error can still surface after earlier statements.

Therefore:

1. Do not inspect only exceptions thrown directly inside `write(...)`.
2. Also inspect `StepExecution`, `JobExecution`, and rollback/commit metrics.
3. When the commit outcome is **unknown due to a connection failure**, do not claim definitively that all data rolled back or committed; have a query/reconciliation mechanism for final data.
4. Never trigger non-rollbackable side effects solely from a pre-commit callback.

## 4. Where Is the Writer's Transaction Configured?

For a JDBC writer, the chunk step configuration specifies the transaction manager:

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step importLedgerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<LedgerRow> ledgerReader,
        JdbcBatchItemWriter<LedgerRow> ledgerWriter) {

    return new StepBuilder("importLedgerStep", jobRepository)
        .<LedgerRow, LedgerRow>chunk(100, transactionManager)
        .reader(ledgerReader)
        .writer(ledgerWriter)
        .build();
}
~~~

A critical requirement is that `JdbcBatchItemWriter` and `transactionManager` must **participate in the same appropriate transactional resource**. If the step opens a transaction on database A while the writer opens a standalone connection with `autoCommit=true` to database B, a rollback on A cannot undo B.

Common design mistakes:

- The writer calls `DriverManager.getConnection(...)` to open and commit its own connection.
- The writer invokes a service with `REQUIRES_NEW` per item, committing before the chunk completes.
- The writer uses multiple delegates where one writes to a transactional database and another calls an HTTP API.
- The writer writes across multiple databases/queues without a corresponding transaction-coordination strategy.
- Code catches exceptions and only logs them, leading the step to believe the writer succeeded.

**Do not wrap `write(...)` in a new transaction "to be safer" if doing so detaches the writer from the chunk transaction.** Let the chunk step and actual resources coordinate on the designed commit boundary.

## 5. Example JDBC Writer and Idempotent Output

Suppose each valid payment event has a unique `eventId` and an `amount`. A PostgreSQL target table:

~~~sql
CREATE TABLE ledger_entry (
    event_id VARCHAR(80) PRIMARY KEY,
    amount NUMERIC(18, 2) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

The writer can use `INSERT ... ON CONFLICT` if the policy is **one record per event**:

~~~java
import java.math.BigDecimal;
import javax.sql.DataSource;

import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

record LedgerRow(String eventId, BigDecimal amount) {}

@Bean
JdbcBatchItemWriter<LedgerRow> ledgerWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<LedgerRow>()
        .dataSource(dataSource)
        .sql("""
            INSERT INTO ledger_entry (event_id, amount)
            VALUES (:eventId, :amount)
            ON CONFLICT (event_id) DO NOTHING
            """)
        .itemSqlParameterSourceProvider(row ->
            new MapSqlParameterSource()
                .addValue("eventId", row.eventId())
                .addValue("amount", row.amount()))
        .assertUpdates(false)
        .build();
}
~~~

Notes:

- `event_id` is a durable business key. If an item is replayed after rollback/restart, no extra row is created for the same ID.
- `ON CONFLICT ... DO NOTHING` is PostgreSQL syntax; other databases require equivalent SQL.
- `assertUpdates(false)` fits this example because an `INSERT` hitting an existing key can affect **0 new rows**. Leaving `assertUpdates(true)` would cause the writer to treat 0 updated rows as an error.
- `DO NOTHING` does not verify that two payloads sharing an ID have identical content. If the same `event_id` with a different `amount` is a business error, validate stored data or use a conditional UPSERT/checksum check.
- Writing successfully to a database does not guarantee exactly-once behavior for out-of-transaction APIs, files, or brokers.

If the business logic adds to a balance, the following write is **not inherently idempotent**:

~~~sql
UPDATE account
SET balance = balance + :amount
WHERE account_id = :accountId;
~~~

Replaying the same event would add the amount a second time. To prevent that, record the processed event ID in the same transaction as the balance update, enforce a unique constraint, and apply the balance update only when the new event is actually accepted.

## 6. Retrying Writer Failures: When Errors Can Self-Recover

Spring Batch supports fault tolerance on the step:

~~~java
import org.springframework.dao.TransientDataAccessException;

@Bean
Step resilientLedgerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<LedgerRow> reader,
        JdbcBatchItemWriter<LedgerRow> writer) {

    return new StepBuilder("resilientLedgerStep", jobRepository)
        .<LedgerRow, LedgerRow>chunk(100, transactionManager)
        .reader(reader)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
}
~~~

Meaning:

1. `.faultTolerant()` enables error-handling policies on the step.
2. `.retry(TransientDataAccessException.class)` permits retrying transient data-access errors of the selected type.
3. `.retryLimit(3)` caps retry attempts under the retry policy; this is **not three full restarts of the entire job**.
4. When the writer throws a matching exception, Spring Batch can roll back the chunk and retry via fault tolerance. The writer may be invoked multiple times with items from the prior attempt.
5. When attempts exceed the limit or the error is non-retryable, the step can fail unless an appropriate skip policy applies.

**Retry is only safe when the write operation can be repeated per the business contract.** With JDBC sharing the transaction, rollback usually discards uncommitted chunk changes. However, if the writer calls an HTTP API or commits an independent transaction, the prior attempt may already have produced side effects; retrying then requires an idempotency key or a mechanism to determine the receiver's state.

### Should You Retry All Exceptions?

No:

~~~java
// Anti-pattern: bypasses error classification, retries even schema and data errors.
.retry(Exception.class)
~~~

Bad SQL columns, invalid data, or programming bugs will not vanish across retries. Indiscriminate retries prolong incidents, increase database load, and multiply external API calls.

### Backoff and Time Limits

For network errors, overloaded databases, or HTTP `429`, immediate retries can make things worse. Configure backoff when fault tolerance allows it:

~~~java
import org.springframework.retry.backoff.FixedBackOffPolicy;

FixedBackOffPolicy backOff = new FixedBackOffPolicy();
backOff.setBackOffPeriod(1000L); // Wait 1 second between retries.

// Attach to fault-tolerant step builder:
// .backOffPolicy(backOff)
~~~

Availability and exact packages for backoff policies must match your project's libraries and version; in Spring Batch 5.x, step-builder retry/backoff APIs are typically backed by Spring Retry. The example highlights the need for **waiting periods and limits**, not that 1 second suits every environment.

If writing over HTTP, also enforce overall time budgets, connect/read timeouts, concurrency limits, and `Retry-After` handling if provided by the API. Do not build an infinite retry loop inside the writer that hides failures from Spring Batch.

## 7. Skipping Writer Failures: Only When Dropping Bad Items Is Allowed

**Skip** is a business decision allowing an unprocessable item to be bypassed so remaining items can proceed. It differs from **retry**, which expects the error to clear on subsequent attempts.

Example policy allowing up to two output records with clearly defined errors to be skipped:

~~~java
.faultTolerant()
.skip(RejectedOutputRecordException.class)
.skipLimit(2)
~~~

`RejectedOutputRecordException` here is an application-defined exception for cases where the writer can identify **a specific record allowed to be dropped**. In real code, define the class and ensure the writer/processor actually throws it only for that error category.

When a writer processes multiple items in a chunk, a failure on the third write does not automatically pinpoint which item is safe to skip. Spring Batch may have to roll back and re-invoke the writer with smaller subsets to **isolate the failing item** under the fault-tolerance algorithm. As a result, the writer can see the same item multiple times even when the step ultimately completes with skips.

Before enabling writer skips, verify:

- Does the error truly belong to **an individual item**, rather than the whole batch, schema, or external resource?
- Can every failed chunk attempt be rolled back cleanly?
- Can the writer rewrite valid items without creating duplicate effects?
- Is skipping legal under business rules? For instance, total-amount reports may become inaccurate if transactions are dropped.
- Must rejected records be saved in an access-controlled quarantine and audit store?
- When `skipLimit` is exceeded, the step must fail—what is the operational next step?

**Do not configure a blanket skip for all `DataIntegrityViolationException` just to make a job "turn green."** That exception can stem from foreign keys, duplicate keys, null values, or systemic data bugs. An overly broad skip can mask incidents that should halt the job.

### Read Skip, Process Skip, and Write Skip

| Skip Type | Where Failure Occurs | Example | Consequence |
|---|---|---|---|
| `readSkipCount` | Reader or parser | Malformed CSV structure. | Item is not converted into a valid object. |
| `processSkipCount` | Processor | Fails validation rule. | Item was read but produced no valid output. |
| `writeSkipCount` | Writer | An output record is rejected by the writer. | Writes must be rolled back/isolated before continuing. |

A step can finish `COMPLETED` even with skips when policy allows, yet the output is an intentional subset. Monitoring must surface skip counts and reasons rather than equating `COMPLETED` with "all inputs were written."

## 8. Do Not Swallow Exceptions in the Writer

A dangerous anti-pattern:

~~~java
@Override
public void write(Chunk<? extends LedgerRow> items) {
    for (LedgerRow item : items) {
        try {
            save(item);
        } catch (Exception error) {
            log.warn("Save failed, continue");
        }
    }
}
~~~

The writer ignored the error and returned normally. Spring Batch can assume the chunk succeeded and commit/checkpoint even though some items were never written. This causes:

- `writeCount` and step status to misrepresent how many items were actually persisted.
- Step-level retry/skip policies to never get a chance to decide.
- Restarts to skip missing items because the checkpoint advanced.
- Business failures to be hidden from monitoring and audits.

If items must be excluded per policy, validate/filter at the appropriate layer or configure bounded fault-tolerance/skip. If catching an error to add context, **rethrow an appropriate exception** (and avoid embedding sensitive payloads in exception messages):

~~~java
try {
    saveChunk(items);
} catch (TransientDataAccessException error) {
    throw error; // Let step decide rollback/retry.
}
~~~

Do not collapse every error into one generic exception if doing so destroys the distinction between transient and non-retryable failures. When wrapping is mandatory, preserve the cause for controlled diagnostics and configure policies to recognize the right error type.

## 9. Multi-Resource Writers: Rollback Has Limits

A single writer might write simultaneously to:

- Both `orders` and `order_audit` tables in one database.
- A database and a CSV file.
- A database and an HTTP API.
- A database and Kafka/message broker.
- Two independent databases.

### Multiple Tables in One Database Transaction

If two delegates share the same `DataSource`/transaction manager and do not self-commit, their operations can share the chunk transaction. For example, `CompositeItemWriter` simply calls multiple writers in order:

~~~java
CompositeItemWriter<LedgerRow> composite = new CompositeItemWriter<>();
composite.setDelegates(List.of(ledgerWriter, auditWriter));
~~~

**Composite does not create a distributed transaction.** If `ledgerWriter` writes via transactional JDBC while `auditWriter` calls an external API, an API failure may roll back JDBC data without undoing other API effects.

### HTTP API: Timeouts Leave Outcomes Uncertain

Suppose a writer calls an API:

~~~text
Writer  --- POST /payments --->  Remote API
Writer  <--- timeout ----------  (API may have committed)
~~~

At least two possibilities exist:

1. The request was never processed by the API.
2. The API processed and committed successfully, but the response was lost in transit.

If the writer retries without an idempotency key, the second case can create duplicate transactions. Therefore, when designing HTTP writers:

- Attach a **stable eventId/idempotency key** per business action.
- Require the API to recognize and return consistent responses for duplicate requests, if the contract supports it.
- Query status by business key when a call outcome is ambiguous.
- Cap retries and separate timeouts from permanent data errors.
- Never assume Spring Batch's database transaction rolls back HTTP calls.

### Transactional Outbox

When you need to update a database and emit events, a common pattern is saving both business data and **the intent to publish an event** in the same transaction:

~~~sql
-- The following statements must run in the same chunk transaction;
-- do not manually BEGIN/COMMIT inside ItemWriter.

INSERT INTO ledger_entry (event_id, amount)
VALUES (:eventId, :amount)
ON CONFLICT (event_id) DO NOTHING;

INSERT INTO outbox_event (event_id, event_type, payload)
VALUES (:eventId, 'LEDGER_CREATED', :payload)
ON CONFLICT (event_id) DO NOTHING;
~~~

After the transaction commits, a separate process reads the outbox and publishes events. If that publisher crashes after the broker accepts the event but before saving progress, the event may be re-sent. Consumers therefore still need deduplication by event ID. Outbox coordinates **writing data and recording publish intent** in the same database; it does not magically create system-wide exactly-once delivery.

### File Writers

Filesystems generally lack database-style ACID rollbacks. Some Spring Batch writers, such as `FlatFileItemWriter`, support buffering, state synchronization, and restarts, yet you cannot assume every file write is cleanly undone after a crash or power loss.

For critical output files, write to a temporary file, close and verify the result, and publish via rename/move when the filesystem guarantees the desired semantics. Define paths per `JobInstance`/version, overwrite rules, and cleanup of leftover temp files after failures.

## 10. Writer Failures and Job Restarts

Spring Batch stores metadata in `JobRepository` and uses `ExecutionContext` to support restarts for stateful readers/writers. For the same `JobInstance`, a new `JobExecution` can resume after a `FAILED`/`STOPPED` execution depending on configuration.

~~~text
JobInstance: importLedgerJob(businessDate=2026-11-15)
    |
    +-- JobExecution 101: FAILED
    |      chunk 1: COMMITTED
    |      chunk 2: ROLLED BACK
    |
    +-- JobExecution 102: COMPLETED
           restart same JobInstance
~~~

In this example:

- Chunk 1 committed and normally remains persisted.
- Failed chunk 2 is retried/replayed or resumed on restart from the appropriate checkpoint.
- The writer must tolerate an item reappearing during recovery.
- If out-of-transaction side effects occurred, reconcile whether those actions already completed on the external target.

**Never create a new JobInstance using a timestamp or random `run.id` just to bypass an existing failed instance**, if the goal is checkpoint-based recovery. Doing so can reprocess the entire input and double committed effects. To restart, preserve exact identifying `JobParameters` and metadata.

### What If Commit Success or Failure Is Ambiguous?

A tricky scenario is losing connection right during transaction commit:

~~~text
DB receives COMMIT
   |
   +-- Committed, but response lost?
   |
   +-- Not committed, and transaction rolled back?
~~~

Inspecting only the application-side exception cannot reliably distinguish which case happened. If `JobRepository` metadata and output are stored in two separate transactions/resources, checkpoints and business data can also drift out of sync.

Consequently, beyond transactions, design **idempotent outputs** and **reconciliation** procedures by business key. On restart or rerun, the system should check final state rather than blindly accumulating effects.

### Step Metadata Does Not Replace Business Output Verification

`BatchStatus.FAILED` means the execution did not finish successfully; it does not mean the target database is empty. `writeCount` reflects Spring Batch processing statistics; it cannot prove how many requests an external API committed during timeouts. For critical outputs, reconcile counts, keys, amounts, or checksums between source and target per business policy.

## 11. Listeners Help Observe Writer Errors Without Weighing Down Recovery

Spring Batch lets you register `ItemWriteListener`, `SkipListener`, and `StepExecutionListener` to observe error stages. Listeners should **record metadata safely** and avoid side effects that are hard to roll back.

Example `ItemWriteListener`:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriteListener;

public class SafeWriterListener implements ItemWriteListener<LedgerRow> {

    private static final Logger log =
        LoggerFactory.getLogger(SafeWriterListener.class);

    @Override
    public void onWriteError(
            Exception error,
            Chunk<? extends LedgerRow> items) {
        log.warn(
            "batch.writer.failed category={} attemptedItems={}",
            classify(error),
            items.size()
        );
    }

    private String classify(Throwable error) {
        if (error instanceof
                org.springframework.dao.TransientDataAccessException) {
            return "DATABASE_TRANSIENT";
        }
        if (error instanceof
                org.springframework.dao.DataIntegrityViolationException) {
            return "DATA_CONSTRAINT";
        }
        return "WRITER_FAILURE";
    }
}
~~~

The listener does not log `items` or `error.getMessage()`. The log line reports the number of items **attempted**, not committed. During retries, the error callback can fire multiple times; do not equate error log counts with lost items.

Example listener for write skips:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;

public class WriterSkipListener implements SkipListener<LedgerRow, LedgerRow> {

    private static final Logger log =
        LoggerFactory.getLogger(WriterSkipListener.class);

    @Override
    public void onSkipInWrite(LedgerRow item, Throwable error) {
        // Do not print the entire item or raw exception.
        log.warn("batch.item.skipped stage=WRITE category=REJECTED_OUTPUT");
    }
}
~~~

If business rules require persisting rejected items, use a quarantine store with proper access controls and clear transaction boundaries. Do not log sensitive data or invoke non-idempotent APIs directly from callbacks triggered during retry/rollback flows.

### Useful Metrics

From `StepExecution`, observe:

| Metric | What It Shows |
|---|---|
| `readCount` | Items read per step definition. |
| `writeCount` | Items recorded by the step as successfully processed by the writer. |
| `writeSkipCount` | Items skipped at the writer stage. |
| `processSkipCount` and `readSkipCount` | Items dropped at other stages. |
| `rollbackCount` | Rollbacks recorded by the step. |
| `commitCount` | Commits recorded by the step. |
| `BatchStatus` / `ExitStatus` | Execution status and exit result. |
| `jobExecutionId` / `stepExecutionId` | Correlation link to logs/tracing and repository history. |

Never equate `writeCount` with "external API requests processed exactly once." Spring Batch's internal counters cannot replace reconciliation against a resource with independent semantics.

## 12. A Recovery Strategy by Failure Type

Decisions can follow this flow:

~~~mermaid
flowchart TD
    A["Writer failure"] --> B{"Does the write resource join\nthe chunk transaction?"}
    B -->|Yes| C{"Is the error transient?"}
    B -->|No / uncertain| D["Verify target side effects\nand idempotency key"]
    C -->|Yes| E["Bounded retry\nwith backoff"]
    C -->|No| F{"Can the bad item be isolated\nand does business allow skip?"}
    F -->|Yes| G["Bounded skip\nand quarantine / audit"]
    F -->|No| H["Fail step, preserve metadata\nto fix and restart"]
    D --> I{"Did target effect happen?"}
    I -->|Yes or unknown| J["Check status / reconcile\navoid duplicate effects"]
    I -->|No and guaranteed| K["Retry per API contract"]
    E --> L["Verify final output"]
    G --> L
    H --> L
    J --> L
    K --> L
~~~

In practice, decisions depend on business objectives. For example, a reconciliation job requiring 100% of transactions cannot skip any item; whereas a reference-data import might tolerate a few invalid records if a reject report is written and counts are clearly reported.

### Suggested Policy Matrix

| Failure | Initial Policy | Prerequisite Before Continuing |
|---|---|---|
| Transient DB deadlock | Bounded retry. | Writer is transactional and safe on replay. |
| SQL schema mismatch | Fail-fast. | Migration/config fixed, then restart. |
| Unique constraint violation | Classify: benign duplicate vs. bad data. | Business key/idempotency rules and explicit ignore policy. |
| Disk/file space exhausted | Fail; restore resources. | Can safely resume/rewrite without corrupting or duplicating the file. |
| API 503 | Retry with backoff. | Endpoint supports idempotency or status lookup. |
| API timeout after request | Uncertain outcome. | Look up by idempotency key before repeating the action. |
| Single item un-exportable | Skip if business allows, otherwise fail. | Writer can isolate errors, count, and record rejects accurately. |
| Process crash between chunks | Restart from metadata. | Reliable checkpoints, idempotent/reconciled output. |

## 13. Designing Writer Failure Tests

A happy-path test is insufficient. Intentionally inject faults at predictable points and inspect **final output state** and metadata.

### 13.1. Testing JDBC Chunk Rollback

Assume `ledger_entry` is empty and input contains A, B, C in **one chunk of size 3**. The writer executes JDBC inserts within the step transaction and deliberately throws on C:

~~~java
import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriter;
import org.springframework.jdbc.core.JdbcTemplate;

class FailingLedgerWriter implements ItemWriter<LedgerRow> {

    private final JdbcTemplate jdbc;

    FailingLedgerWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public void write(Chunk<? extends LedgerRow> chunk) {
        for (LedgerRow row : chunk) {
            jdbc.update(
                "INSERT INTO ledger_entry(event_id, amount) VALUES (?, ?)",
                row.eventId(),
                row.amount()
            );
            if ("C".equals(row.eventId())) {
                throw new IllegalStateException("DELIBERATE_WRITER_FAILURE");
            }
        }
    }
}
~~~

This snippet is a **fault-injecting writer for integration tests**, not a production implementation. If `JdbcTemplate` shares the transaction configured for the step, when C throws:

- A and B ran their `INSERT` statements but remain in an uncommitted transaction.
- The chunk transaction rolls back, so none of A, B, or C remain after a clean rollback.
- Without a matching skip/retry policy, the step ends as `FAILED`.

In the test, after `JobExecution` finishes, query the table and assert none of A/B/C exist; also assert `BatchStatus.FAILED`. This check is far more reliable than merely asserting the writer threw an exception.

### 13.2. Testing Earlier Chunk Committed, Later Chunk Fails

Given inputs A, B, C and `chunkSize = 2`. If chunk 1 (A/B) commits and chunk 2 (C) throws, verify:

- A and B **remain persisted**.
- C is absent from output if the transaction containing C rolls back.
- Step is `FAILED`.
- Restarting with **the same identifying JobParameters** processes the unfinished work without inserting duplicates of A/B.

A small three-item fixture suffices to prove chunk boundaries; thousands of records are unnecessary.

### 13.3. Testing Transient Error Retry

Create a test writer that counts calls, throws an exception **configured for retry** on the first attempt, and succeeds afterward. Verify:

1. At least one rollback/retry occurs per configuration.
2. The job ends as `COMPLETED` once the error clears within the limit.
3. Each business key has only one final result at the target.
4. If the error persists beyond the limit, the job is `FAILED` with matching metadata.

Do not hardcode assertions on the exact number of `write` invocations if the fault-tolerance algorithm splits chunks or invokes the writer differently across versions. Assert final data invariants and step status, checking attempt counts only when that is the specific test goal.

### 13.4. Testing Writer Skip

Create three items, deliberately rejecting one item with an exception listed in `skip(...)`. Verify the two valid items are written once, the bad item is not written, `writeSkipCount` matches policy, and the job reaches the expected status.

Write a second test where failing items exceed `skipLimit` to confirm the step actually fails rather than silently skipping everything.

### 13.5. Testing Out-of-Transaction Side Effects

Use a fake HTTP server capable of:

- Receiving a request and delaying the response until timeout.
- Receiving the same idempotency key twice.
- Returning 503 followed by 200.
- Returning a permanent validation error.

After each scenario, verify **the final count of business effects on the server** rather than just counting requests sent. A retry may send two valid requests while the server creates only one transaction thanks to idempotency.

### Comprehensive Test Matrix

| Scenario | Small Dataset | Expected Result |
|---|---|---|
| Writer fails mid-JDBC chunk | 3 items, fail on 3rd, chunk 3 | Entire chunk rolls back. |
| Failure after a committed chunk | 3 items, chunk 2, fail on 3rd | First two items remain; 3rd uncommitted. |
| Transient retry then success | 1–2 items, fail on first call | Single correct final result, job succeeds within limit. |
| Retries exhausted | Persistent error | `FAILED`, no inconsistent output. |
| Skip exactly one item | 3 items, 1 rejected | Valid items complete; skip counter and audit match. |
| Skip limit exceeded | 3 items, multiple rejected | Step `FAILED`. |
| Duplicate event after restart | Repeated event ID | No duplicate business rows. |
| HTTP timeout after server processed | 1 event with idempotency key | No second business effect created. |
| Connection lost on commit | Fault injection/simulation | Outcome verified by query/reconciliation, not rollback assumptions. |
| File writer crash before publish | Temp/target file | Unfinished output file is not published per policy. |

## 14. Logging and Monitoring Writer Failures

A useful writer-failure log correlates the failure to an execution and root-cause category without dumping the whole chunk or sensitive data:

~~~json
{
  "event": "batch.writer.failed",
  "jobName": "importLedgerJob",
  "jobExecutionId": 8102,
  "stepName": "writeLedgerStep",
  "stepExecutionId": 9205,
  "correlationId": "req-301",
  "errorCode": "DATABASE_TRANSIENT",
  "attemptedItemCount": 100
}
~~~

This is an **application-defined schema**, not default JSON emitted by Spring Batch. `attemptedItemCount` is only the number of items in the failed writer call, not proof that 100 items committed.

Avoid logging:

~~~java
log.error("writer failed chunk={}", chunk);
log.error("writer failed item={}", item);
log.error("SQL failed with params={}", fullParameters);
~~~

When items contain PII, account numbers, tokens, or partner payloads, such logs can leak data to stdout, collectors, and dashboards. Exceptions from parsers/JDBC/HTTP can also embed sensitive values in messages or cause chains; normalize `errorCode` and send stack traces only to controlled diagnostic channels after review.

Useful operational metrics include:

- `FAILED` `JobExecution`/`StepExecution` counts by job and step.
- `writeSkipCount`, `rollbackCount`, `commitCount`, `writeCount`.
- Per-chunk processing duration and retry/backoff duration.
- Classified error codes: transient, data constraint, timeout, schema/configuration.
- Unpublished outbox event count or pending rejects awaiting remediation, if applicable.
- Discrepancy between source and output counts after reconciliation.

**Do not use `jobExecutionId`, `eventId`, or per-request correlation IDs as standard metric tags**, as cardinality will explode. Keep those IDs in logs/tracing/audits for granular investigation; metrics should use bounded labels such as `jobName`, `stepName`, `errorCode`, and `status`.

## 15. Operational Incident Procedure for Writer Failures

When a batch step fails at the writer, follow this procedure:

1. **Identify the execution and failure point.** Look up `jobExecutionId`, `stepExecutionId`, `JobRepository`, step status, and error code.
2. **Identify writer resources.** Transactional JDBC sharing the step transaction, file, HTTP, broker, or multiple targets? Does any resource commit independently?
3. **Classify the failure.** Transient, permanent data issue, schema, exhausted resource, ambiguous commit outcome, or cross-system side effect.
4. **Verify committed results.** Reconcile by business key; separate previously committed chunks from the failing chunk. For external APIs, query idempotency/event IDs.
5. **Select a recovery path.** Retry with backoff, fix data then restart, skip/quarantine per policy, or restore resources.
6. **Preserve the JobInstance on restart.** Use the same identifying parameters and checkpoint; never delete metadata just to bypass state.
7. **Track to final outcome.** Verify output records, skip/retry counts, missing/duplicate rows, and alerts rather than watching `BatchStatus.COMPLETED` alone.

If an execution remains marked `STARTED` after a node actually died, verify the process and side effects before altering metadata. Do not arbitrarily edit `BATCH_JOB_EXECUTION` or wipe `BATCH_*` tables to "unlock" the job: that destroys checkpoints and risks reprocessing already committed data.

### When Should You Not Auto-Restart?

Do not restart immediately when:

- You do not know how many external API effects occurred in the prior run.
- The writer performs non-idempotent accumulation and checkpoints are untrustworthy.
- An output file was partially published and consumers may have read it.
- The business database and metadata repository are out of sync and unreconciled.
- The error stems from an unfixed schema/logic bug certain to recur.
- The previous execution might still be running on another node.

These cases require recovery decisions backed by verified data. Automated retry or restart is appropriate only when safe writer behavior has been explicitly designed and tested.

## 16. Common Mistakes

**"The writer called INSERT, so the row is saved."** Not necessarily; if the transaction has not committed and later rolls back, the row does not exist. Distinguish SQL execution/flush from transaction commit.

**"Step FAILED means all job output rolled back."** False in standard chunk-oriented processing: previously committed chunks normally persist. Check output state before restarting.

**"Since retry exists, retry every exception."** Schema bugs, invalid data, and logic errors do not self-heal. Over-broad retries delay failure detection and can multiply non-transactional side effects.

**"Catch the exception and continue so the job won't fail."** If the writer swallows errors, Spring Batch can commit and checkpoint despite missing data. Use explicit retry/skip policies or fail.

**"Using CompositeItemWriter means all delegates roll back together."** Composite merely invokes delegates; actual transaction behavior depends on each delegate's datasource, transaction manager, and resource.

**"HTTP timeout means the API never processed it."** The API may have committed while the response was lost. Safe retry requires idempotency or status lookup.

**"Enabling skip for DataIntegrityViolationException solves everything."** It can drop mandatory transactions or mask systemic data bugs. Distinguish benign duplicates, constraint violations, and chunk-wide failures.

**"ItemWriteListener.afterWrite means data is committed."** That callback typically runs before chunk commit, not as a final commit confirmation event.

**"Restarting with a new run.id resumes the old job."** When `run.id` is identifying and changes, that creates a new JobInstance and risks reprocessing all input. True restarts preserve the old instance and metadata.

**"Checking `writeCount` alone proves the external API has no duplicates."** Internal counters cannot reliably measure out-of-transaction external side effects, especially across timeouts. Reconcile against the target system.

## 17. Principles for Designing a Recoverable Writer

A reliable writer in Spring Batch generally follows these principles:

1. **Respect the chunk transaction boundary.** Write to transactional resources matching the step's transaction manager; avoid independent commits unless deliberately architected.
2. **Throw exceptions when write outcomes are unguaranteed.** Let Spring Batch decide rollback, retry, skip, or fail according to policy.
3. **Classify errors before retrying.** Pick specific transient exceptions, limit attempts, use backoff, and avoid infinite retries.
4. **Skip only under a business contract.** The writer must isolate failing items and guarantee valid items are not duplicated.
5. **Design idempotent outputs.** Use business/event keys, unique constraints, controlled UPSERTs, or equivalent API mechanisms.
6. **Coordinate out-of-transaction side effects.** Use outbox, idempotency keys, status queries, or compensation as required.
7. **Preserve metadata for restarts.** Never delete checkpoints/history casually; verify committed chunks and items needing replay.
8. **Observe metadata safely.** Log job/step IDs, error codes, counters, and status; never dump sensitive items or full chunks.
9. **Test real failures.** Inject errors mid-chunk, after a commit, timeouts with uncertain outcomes, exceeded retry/skip limits, and restarts after crashes.

## Conclusion

**Writer failure** is not merely an exception to catch; it is a question of **written data state, commit boundaries, and safe replay**. With a JDBC writer sharing the chunk transaction, errors typically roll back uncommitted changes in that chunk while prior chunks persist. Spring Batch can retry, skip, or restart per configuration, but those mechanisms may re-invoke the writer and cannot automatically undo HTTP calls, files, or brokers outside the transaction.

Design recovery from the start: classify errors, use transactions properly, generate stable business keys, protect writers with idempotency, persist reliable checkpoints, reconcile when commit outcomes are ambiguous, and verify final outputs. Then a writer failure becomes detectable, explainable, and recoverable without losing or duplicating business data.
