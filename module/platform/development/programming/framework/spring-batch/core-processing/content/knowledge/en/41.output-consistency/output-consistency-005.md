# Transactional writer in Spring Batch: ensuring output consistency

In a batch job, writing data does not automatically mean that the data has been **committed**. If part of a chunk is written successfully and a subsequent part fails, Spring Batch needs to know which changes to roll back, when to retry, and where to resume after restarting the job. That is why a **transactional writer** is a core component of *output consistency*.

This article focuses on **chunk-oriented processing**: an `ItemWriter` writes data to a transactional resource (typically a database) coordinated by the transaction manager configured on the `Step`. Examples use Spring Batch 5.x+ APIs with `ItemWriter.write(Chunk<? extends T>)`; in Spring Batch 4.x, the corresponding method accepts `List<? extends T>`.

## 1. What problem does a transactional writer solve?

Suppose a step reads 300 payment transactions, processes them, and writes them to the `ledger_entry` table with `chunkSize = 100`:

- Chunk 1 (records 1–100) writes successfully and commits.
- Chunk 2 (101–200) is writing when record 157 violates a data constraint.
- Chunk 3 (201–300) has not been processed yet.

If the writer participates in **the same transaction as the chunk**, all database changes made by chunk 2 are rolled back; there is no half-saved, half-unsaved chunk state. Chunk 1 remains because it was committed in a previous transaction. Depending on the error-handling configuration, the step can retry, skip the failing record, or fail and be restarted.

If the writer calls an HTTP API, sends an email, or writes to a resource that is not coordinated with the transaction, some side effects may have already occurred before Spring Batch rolls back. Therefore, the term *transactional writer* must be understood accurately:

> **A writer is transactional when its write operations genuinely participate in the transaction managed by the step, and the storage system is capable of committing/rolling back those operations.** Simply naming a class `TransactionalWriter` or adding `@Transactional` does not create this guarantee.

Three properties are frequently confused:

| Property | Meaning | Scope |
|---|---|---|
| **Atomicity** | Changes within the same transaction are either all committed or all rolled back. | Typically **per chunk**, not the entire job. |
| **Idempotency** | Writing the same event again produces no unintended additional effect. | Business rules and key/constraint design. |
| **Exactly-once effect** | An event causes only one final business effect, even across retries/crashes. | Requires coordinating transactions, checkpoints, idempotency keys, and sometimes the consumer side. |

Transactions are foundational, but **a transaction alone does not prove exactly-once across all systems**.

## 2. How does the chunk transaction wrap the writer?

In a typical chunk-oriented step, `PlatformTransactionManager` manages the transaction for the read, process, and write cycle of each chunk:

~~~mermaid
flowchart TD
    A["Start chunk transaction"] --> B["Read and process up to N items"]
    B --> C["ItemWriter.write(chunk)"]
    C -->|No error| D["Update checkpoint state"]
    D --> E["Commit transaction"]
    C -->|Exception| F["Rollback transaction"]
    D -->|Commit failed| F
    F --> G["Retry / skip / fail step"]
    E --> H{"More data?"}
    H -->|Yes| A
    H -->|No| I["Step completed"]
~~~

The sequence above is a conceptual model. Reading from a specific resource may follow its own buffering and restart rules; writing `ExecutionContext`/checkpoint state also depends on the `JobRepository` configuration. However, **the commit boundary of a database writer is the chunk transaction boundary**.

In Spring Batch 5+, the writer contract is:

~~~java
public interface ItemWriter<T> {
    void write(Chunk<? extends T> chunk) throws Exception;
}
~~~

`write` is called with a group of items and can throw an exception. This interface does **not** itself define commit/rollback mechanics. Those mechanics come from the target data resource and the transaction manager:

- `JdbcBatchItemWriter` uses JDBC to write data; its statements participate in the current JDBC transaction when the `DataSource` and transaction manager are configured properly.
- A JPA writer requires an `EntityManager` managed within the corresponding transaction; SQL may only be sent/fully checked upon flush or commit.
- A writer calling a REST API, sending email, or pushing data to another system is usually **not** rolled back simply because the database transaction rolls back.
- A writer composing multiple delegates via `CompositeItemWriter` is only atomic across delegates that **participate in the same compatible transaction**. One delegate writing to a database and another calling an HTTP API do not automatically become a distributed transaction.

Another important point: if a job consists of 20 chunks and chunk 20 fails, the 19 already-committed chunks **do not automatically roll back**. If business requirements demand that the entire job appear all at once, additional design is needed, such as writing to a staging table and publishing by batch ID, or a controlled publish/swap step.

## 3. Implementing a JDBC writer that participates in the step transaction

Consider the requirement to write normalized financial events into PostgreSQL. Each event has a unique `eventId` and an `amount`. Designing a stable business key makes re-writing the same event safer when a job restarts or is re-run.

### 3.1. Output schema

~~~sql
CREATE TABLE ledger_entry (
    event_id BIGINT PRIMARY KEY,
    amount   NUMERIC(18, 2) NOT NULL
);
~~~

The `event_id` primary key enforces uniqueness at the **database layer**. A "SELECT to check existence then INSERT" check is insufficient in concurrent environments because two workers may both observe that the record does not yet exist.

### 3.2. Writer and step

The following example assumes the application already has an `ItemReader<LedgerItem>`, `DataSource`, and `PlatformTransactionManager` pointing to the appropriate business resource. This is a Java configuration for Spring Batch 5.x, using Java 17+:

~~~java
import java.math.BigDecimal;
import javax.sql.DataSource;

import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
class LedgerBatchConfig {

    @Bean
    JdbcBatchItemWriter<LedgerItem> ledgerWriter(DataSource dataSource) {
        return new JdbcBatchItemWriterBuilder<LedgerItem>()
            .dataSource(dataSource)
            .sql("""
                INSERT INTO ledger_entry (event_id, amount)
                VALUES (:eventId, :amount)
                ON CONFLICT (event_id)
                DO UPDATE SET amount = EXCLUDED.amount
                """)
            .itemSqlParameterSourceProvider(item ->
                new MapSqlParameterSource()
                    .addValue("eventId", item.eventId())
                    .addValue("amount", item.amount()))
            .assertUpdates(true)
            .build();
    }

    @Bean
    Step ledgerStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<LedgerItem> reader,
            JdbcBatchItemWriter<LedgerItem> ledgerWriter) {

        return new StepBuilder("ledgerStep", jobRepository)
            .<LedgerItem, LedgerItem>chunk(100, transactionManager)
            .reader(reader)
            .writer(ledgerWriter)
            .build();
    }
}

record LedgerItem(long eventId, BigDecimal amount) {}
~~~

Details that determine consistency:

1. `chunk(100, transactionManager)` specifies that up to 100 items are processed in one step transaction. The final chunk may contain fewer than 100 items.
2. `JdbcBatchItemWriter` obtains its JDBC connection through Spring's data access infrastructure. When the writer and `transactionManager` use the same `DataSource`, write operations participate in the active transaction; the step manages commit/rollback.
3. The SQL `ON CONFLICT ... DO UPDATE` is **PostgreSQL** syntax. For other database engines, choose the appropriate UPSERT/MERGE mechanism. Re-running the same `event_id` with the same `amount` produces the same final state.
4. `assertUpdates(true)` requires each batch statement to update at least one row, which helps catch certain cases where the writer appears to have written but actually affected no rows. With statements or drivers that intentionally return an update count of 0, this setting must be considered carefully.
5. The code does not open its own transaction inside `write`. The writer lets the **chunk step own the transaction**.

The example above is idempotent in the sense of **assigning the same absolute value for the same event key**. Do not generalize that to all SQL. For example, this statement:

~~~sql
UPDATE account
SET balance = balance + :delta
WHERE account_id = :accountId;
~~~

is an additive operation: running it twice adds the money twice. If accumulation is required, you must record the processed `event_id` with a unique constraint and update the balance only when the event is genuinely received for the first time, within **the same database transaction**.

> **When multiple DataSources/transaction managers exist:** explicitly specify the right bean (for example, via `@Qualifier`). If the `Step` opens a transaction on database A while the writer writes to database B via an auto-commit connection, rolling back A cannot undo data in B.

## 4. What happens when the writer fails?

Suppose the current chunk contains items `[A, B, C]` and the writer uses a JDBC transaction:

1. The writer writes A and B within the open transaction.
2. When writing C, the database returns a constraint violation error.
3. The writer throws an exception to the step.
4. Spring Batch rolls back the chunk transaction. Result: neither A, B, nor C **is committed in this chunk**.
5. The fault-tolerance configuration determines whether to retry, skip the failing item, or end the step with `FAILED` status.

Different critical scenarios:

| Failure timing | Output of same-transaction JDBC writer | Consequences to consider |
|---|---|---|
| Processor fails before writer is called | No output written for the current chunk yet. | Step rolls back or handles via retry/skip. |
| Writer writes partially then throws exception | Uncommitted changes of the **entire chunk** are rolled back. | Retry may invoke the writer again with previously seen items. |
| Chunk commits successfully, later chunk fails | Committed chunks remain persisted. | Restart needs to resume from the exact checkpoint. |
| Application loses connection during commit | Commit outcome sometimes cannot be confirmed solely from a client-side exception. | Do not assume rollback occurred with certainty; use business keys/idempotency to tolerate re-runs. |
| HTTP call succeeds then JDBC transaction rolls back | HTTP side effect is not rolled back by the JDBC transaction. | Risk of duplicate send or write on retry. |
| Crash after data committed before checkpoint is durably saved | Divergence between job progress and output can occur if the two stores are not transactionally coordinated. | Share the same transaction boundary if feasible and protect writes with idempotency. |

### Rollback does not mean "the writer was never called"

Especially when retry or skip is enabled, the same item can pass through writer logic more than once. If the writer mutates in-memory state variables, generates sequence numbers outside the transaction, logs business events, or calls non-idempotent APIs, those effects can repeat even though JDBC data was rolled back.

Therefore, prefer to:

- Isolate rollbackable effects into the same transactional storage system.
- Use stable business keys and unique constraints instead of generating new keys on each attempt.
- Avoid irreversible side effects directly inside the processor/writer when possible.
- Ensure item-processing logic can tolerate replay without changing outcomes unexpectedly.

## 5. Retry, skip, and transactions must be designed together

In Spring Batch, **retry** handles transient errors by trying again; **skip** accepts omitting a bad item within a configured limit; **rollback** undoes changes of the current transaction. These are three distinct concepts.

For example, a DB lock contention error can be retried:

~~~java
return new StepBuilder("ledgerStep", jobRepository)
    .<LedgerItem, LedgerItem>chunk(100, transactionManager)
    .reader(reader)
    .writer(ledgerWriter)
    .faultTolerant()
    .retry(org.springframework.dao.CannotAcquireLockException.class)
    .retryLimit(3)
    .build();
~~~

This is a **configuration example** for a potentially transient error, not an instruction to retry every exception. Wrong schema errors, invalid data, or unique constraint violations will likely still fail after multiple attempts; blind retrying only increases load.

When skipping writer errors, Spring Batch may have to isolate the bad item from a group of written items, leading to multiple writer calls and rollbacks before the chunk can complete. Consequently:

- **Same-transaction JDBC writer:** can roll back failed attempts, then re-write valid items.
- **Non-transactional writer:** failed attempts may already have produced side effects, even if the step later decides to skip the item.
- **Writer depending on external state:** "which items were processed" logic must be durable, keyed/idempotent, and participate in the corresponding transaction where possible.

Do not use configurations like `noRollback(...)` to "keep rows already written" just to work around errors, because it can break the atomicity the business expects. Any rollback exception must be evaluated against the target resource and actual consistency requirements.

## 6. Writers targeting multiple tables or multiple destinations

### 6.1. Two tables in the same database transaction

Suppose each item must be written to `ledger_entry` and `audit_entry`. Two JDBC writers can be called sequentially by `CompositeItemWriter`. If both use the step's same `DataSource` and transaction manager, a failure when writing the second table rolls back changes to the first table **within the current chunk**.

~~~java
CompositeItemWriter<LedgerItem> composite = new CompositeItemWriter<>();
composite.setDelegates(List.of(ledgerWriter, auditWriter));
~~~

The condition lies in **both delegates genuinely participating in the same transaction**, not in the composite class itself. If one delegate creates its own connection with `autoCommit=true` or starts its own transaction and commits early, the guarantee disappears.

### 6.2. Database + HTTP/Kafka/email: cross-system consistency design required

Do not assume a JDBC transaction automatically protects network operations. There are three common approaches:

| Approach | Advantages | Limitations |
|---|---|---|
| Call API directly from writer | Easy to implement. | API succeeds but chunk rollback can cause duplicates; conversely, network failures leave API outcome unknown. |
| Use distributed/XA transactions when all infrastructure supports it | Can coordinate certain transactional resources. | Operational cost, support limits, and complexity on failure; ordinary HTTP does not participate in XA. |
| **Transactional outbox** | Commits business data and event-publishing intent together in one database transaction. | Post-commit relay typically delivers with *at-least-once* semantics; receivers still need idempotency. |

For systems using a database and a message broker, **transactional outbox** is usually easier to operate than calling the broker directly from a chunk writer:

~~~sql
BEGIN;

INSERT INTO ledger_entry (event_id, amount)
VALUES (:eventId, :amount)
ON CONFLICT (event_id)
DO UPDATE SET amount = EXCLUDED.amount;

INSERT INTO outbox_event (event_id, event_type, payload)
VALUES (:eventId, 'LedgerUpdated', :payload)
ON CONFLICT (event_id) DO NOTHING;

COMMIT;
~~~

The two statements above are illustrative only: they must be executed by writers/repositories **within the same transaction managed by the step**, without manually calling `BEGIN`/`COMMIT` inside `ItemWriter`. A separate event-publishing process reads committed outbox rows, sends them to the broker, and marks progress. If the publisher crashes after sending but before marking, it may resend; consumers must detect duplicate `event_id` values.

### 6.3. File writers are a special case

Ordinary filesystems do not have ACID transactions like databases. Some Spring Batch writers, such as `FlatFileItemWriter`, provide buffering and state management to align writes closely with chunk boundaries and restarts; however, **you should not equate that with the ability to roll back a physical file like a database transaction** across all crash scenarios.

For high-consistency file export requirements, you can write to a temporary file, close and validate the output, and then publish using a rename/move operation suited to the filesystem; note that atomic rename behavior depends on the filesystem and source/target locations. Combine a filename tied to the `JobInstance`/batch ID, clear overwrite rules, and publication metadata to prevent consumers from reading incomplete files.

## 7. Restart and checkpoint: consistency of both data and progress

Spring Batch uses `JobRepository` to store job/step state and `ExecutionContext` to persist state required for restarting stateful readers/writers. When a chunk commits successfully, confirmed progress must correspond to stored output. If these two parts belong to two independent transactional resources, the following can happen:

1. Chunk business data commits.
2. The application crashes before checkpoint state is fully recorded.
3. Restart re-runs part of the input.

That is one reason an **idempotent writer** is needed, even when the writer uses a JDBC transaction. In a suitable architecture, configuring `JobRepository` and business output on the same database/transaction manager can coordinate checkpoints and data writes more tightly; if separate resources are used, consistency and recovery scenarios must be explicitly evaluated.

Beyond restarting **the same JobInstance**, consider the case where an operator launches a new job using different `JobParameters` on the same source data. Spring Batch may treat that as another valid run; relying solely on "which line was read up to" cannot prevent business-level duplicate writes. Event keys, batch ID controls, and idempotency must be designed independently of whether a job restarts.

## 8. Common implementation mistakes

**1. Writer self-committing outside the step transaction.** Using `DriverManager.getConnection(...)` with `autoCommit=true`, calling a non-transactional SDK, or opening `REQUIRES_NEW` per item can commit data before the entire chunk completes. As a result, a step rollback can no longer undo those changes.

**2. Confusing the `@Transactional` annotation with consistency guarantees.** For a chunk step, the step's transaction manager must be the primary coordinator. The annotation itself does not join two databases, an HTTP API, or a queue into a single transaction; how Spring proxies apply transactions also depends on the actual invocation path.

**3. Assuming the writer runs only once.** Retry, skip, unknown-outcome commit errors, and restarts can repeat write effects. An `INSERT` generating a new ID each time, balance accumulation, or direct email sending all require additional safeguards.

**4. Catching errors and returning normally.** If a writer silently swallows SQL errors, Spring Batch may continue committing and mark the chunk successful even though part of the output is missing. Only treat an error as a valid outcome when the business has an explicit policy and consistency is guaranteed.

**5. Treating chunk size as the entire job's boundary.** `chunkSize=100` does not make 10,000 items a single transaction. Each chunk commits independently; choosing chunk size also affects lock hold duration, memory usage, round trips, and the amount of rework on rollback.

**6. Failing to distinguish data defects from infrastructure errors.** Business validation violations usually suit controlled routing/skipping; deadlocks or transient connection failures can be retried; data loss or ambiguous commits require different recovery measures. Do not configure retry on every exception.

## 9. Practical scenarios to verify behavior yourself

| Scenario | What to observe |
|---|---|
| In a chunk of 3 items, the third item makes the writer throw an exception after the first two items wrote via JDBC. | No rows of the **failed chunk** are committed if all statements share the same transaction. |
| Chunk 1 commits; chunk 2 fails; then the job restarts. | Chunk 1 data remains; restart progress and business keys prevent duplicate or missing results. |
| Send the same `eventId` twice with an idempotent UPSERT statement. | The output table still represents a single correct state for that event. |
| Replace UPSERT with `balance = balance + delta` and replay the item. | Clearly demonstrates double-crediting risk without an idempotency key. |
| One delegate writes JDBC, another simulates an API that already accepted the request then throws an exception. | JDBC rollback cannot undo the side effect that already occurred on the API. |
| Use outbox and intentionally replay the same `event_id`. | The consumer is able to discard duplicate events by stable key. |

These scenarios test **system behavior under failure**, not just the happy path of a single successful run. In particular, verifying the same business outcome after retry/restart is a more practical perspective than merely counting how many times `write` was called.

## 10. Design principles to remember

When building a transactional writer for Spring Batch:

1. **Define the unit of atomicity:** typically one chunk; if atomicity across the entire job is required, add dedicated design mechanisms.
2. **Let the step manage the transaction:** the writer writes through the right `DataSource`/transaction manager and does not commit on its own.
3. **Protect against replay:** use business keys, unique constraints, and idempotent operations, especially under retry, skip, or restart.
4. **Understand each resource's limits:** databases have ACID rollback; HTTP, email, files, and message brokers do not automatically roll back with a database.
5. **Coordinate progress and output:** examine the relationship between `JobRepository`, checkpoints, business databases, and external sources/destinations.
6. **Use outbox or compensation when needed:** if output spans multiple systems, explicitly design how replay and deduplication work.

**Conclusion:** In Spring Batch, a transactional writer is the combination of an `ItemWriter` writing through a transactional resource and the **chunk step's transaction boundary**. This mechanism prevents half-committed JDBC output within a chunk. Achieving *output consistency* across retries, restarts, and multiple participating systems also requires intentional design of idempotency, checkpoints, and data publication.
