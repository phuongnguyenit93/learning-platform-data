# Ensuring data is not duplicated

In Spring Batch, an item can be re-read or reprocessed when a chunk rolls back, when a Job restarts, when an operation retries, or when a partition re-runs. Therefore, the application must design the Reader, Processor, Writer, and external operations so that repeated processing does not create duplicate records or unintended repeated side effects.

The practical goal is usually **idempotency**: whether the same business request executes once or multiple times, the system reaches the exact same final data state. Spring Batch provides transactions, checkpoints, retry, and restart, yet does not by itself guarantee every business operation executes only once. Data uniqueness must be protected at the application and database layers.

## 1. Why can data be duplicated?

A Job does not always process every item strictly once in an absolute sense. Many valid situations cause the same item to pass through the pipeline multiple times:

- A chunk wrote partially and the transaction rolled back; the next attempt must reprocess the chunk.
- The Job failed and restarted from the most recently committed checkpoint.
- A retry policy re-invoked the Processor or Writer after a transient error.
- A worker or partition re-ran after a process stop or connection loss.
- A scheduler sent the same launch request multiple times.
- An external system received a request, yet the application never received the response and retried sending it.
- An operator intentionally created a new `JobInstance` to reprocess the same source data.

For example, the Writer inserts an order into the target table via an `INSERT` statement. The chunk writes successfully, but the application loses connectivity before receiving commit confirmation. On retry, the same order is inserted again. Without a unique constraint on the source order code in the target table, two rows can coexist.

```text
Chunk attempt 1
  Read order ORD-100
  INSERT ORD-100
  Connection lost / transaction outcome uncertain
        |
        v
Chunk attempt 2
  Read order ORD-100 again
  INSERT ORD-100 again
        |
        v
Two rows representing the same business order
```

This is why uniqueness must be enforced right where data is written, rather than relying solely on the Reader never returning the same item again.

## 2. Understanding idempotency and exactly-once

An operation is idempotent if executing it multiple times with the same identifier and business semantics produces no further change to the final result after the first execution.

Examples:

- `UPDATE account SET status = 'ACTIVE' WHERE account_id = ?` can be idempotent if the goal is setting status to ACTIVE.
- `INSERT INTO payment ...` is normally non-idempotent if each invocation creates a new row.
- `balance = balance + 100` is non-idempotent if the same request is applied twice.
- `UPSERT` by business key can be idempotent if the updated values are deterministic and not unintentionally cumulative.

| Concept | Meaning |
|---|---|
| At-most-once | An operation is attempted at most once; risks losing results if an error occurs before completion. |
| At-least-once | The system keeps trying until an outcome is obtained or the policy is exhausted; the same operation may appear multiple times. |
| Idempotent processing | Allows repeated execution without duplicating business outcomes. |
| Exactly-once effect | The business effect appears only once; typically achieved via transactions, unique keys, idempotency keys, or proper coordination protocols. |

In real batch systems, at-least-once delivery combined with idempotent operations is usually easier to implement and more reliable than trying to guarantee each call happens strictly once across multiple independent systems.

## 3. Choosing a stable business key for each item

To recognize whether an item has already been processed, you need a stable business key. This key must represent the exact same entity or request across reads, retries, and restarts.

Examples:

| Data type | Candidate business key |
|---|---|
| Order from a source system | `source_system + source_order_id` |
| Payment transaction | Source `payment_reference` or `transaction_id` |
| Customer record per source | `source_system + source_customer_id` |
| File import | `source_file_id` or checksum combined with data period |
| Message broker event | `event_id` |
| Per-period and per-tenant record | `tenant_id + business_period + record_key` |

Do not use the Reader's sequential read number as a business key if source ordering can change. Also do not use the current timestamp or a fresh UUID on every retry, because the same item would receive a different key and be recorded as a new entry.

The target table's technical primary key and business key may differ. For instance, a table can use an auto-incrementing `id` as its primary key while still needing a unique constraint on `(source_system, source_order_id)` to prevent two rows from representing the same source order.

## 4. Protecting uniqueness with database constraints

The most important safeguard against duplicate inserts is placing a unique constraint or unique index on the business key. Checking for duplicates with a `SELECT` before an `INSERT` is not safe enough when multiple workers run concurrently: two transactions can both see no existing row and both insert.

Schema example:

```sql
CREATE TABLE imported_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    source_system VARCHAR(40) NOT NULL,
    source_order_id VARCHAR(100) NOT NULL,
    customer_id VARCHAR(100) NOT NULL,
    amount DECIMAL(18, 2) NOT NULL,
    imported_at TIMESTAMP NOT NULL,
    CONSTRAINT uk_imported_order_source
        UNIQUE (source_system, source_order_id)
);
```

When two workers or two retries write the same order, the unique constraint allows only one row with that business key. The application must handle conflicts per policy: skip if the content matches, update if edits are allowed, or flag an error if the same key carries a different payload.

Database constraints are the final line of defense because they enforce uniqueness even across multiple threads, multiple application instances, or external processes writing simultaneously.

## 5. Using database-specific INSERT ... ON CONFLICT or MERGE

Many databases support insert-or-update (upsert) statements. Syntax varies by database engine.

PostgreSQL example:

```sql
INSERT INTO imported_order (
    source_system,
    source_order_id,
    customer_id,
    amount,
    imported_at
)
VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
ON CONFLICT (source_system, source_order_id)
DO UPDATE SET
    customer_id = EXCLUDED.customer_id,
    amount = EXCLUDED.amount;
```

With this approach, the same business key does not create an extra row. If source data changes, the statement updates fields according to defined rules.

However, upsert does not automatically make every business operation idempotent. If the statement uses cumulative arithmetic like `amount = imported_order.amount + EXCLUDED.amount`, re-running will keep adding to it. Set fields to deterministic source values, or store a version/event ID so only newer changes apply.

For databases supporting `MERGE`, you can use `MERGE` to match source keys and decide insert/update. Check semantics, isolation levels, and concurrent merge behavior for the same key in your database documentation.

## 6. Using a processed-items table

A common pattern is recording a trace of every processed business key. Before performing side effects, the application checks or records the processing key in a table with a unique constraint.

Example:

```sql
CREATE TABLE processed_item (
    idempotency_key VARCHAR(160) PRIMARY KEY,
    job_name VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    result_reference VARCHAR(160)
);
```

Within the same transaction as the business data, the application attempts to insert `idempotency_key`. If the insert succeeds, the transaction proceeds to update business data. If the key already exists, the item was already processed or another transaction is processing the same key; the application reads the status and decides to skip, wait, or reprocess per rules.

Crucially, inserting the processed key and modifying business data must occur in the same transaction. If the key is committed in a separate transaction first and the business transaction fails, the next run may skip the item even though target data was never updated. Conversely, if business data commits without recording the processed key, the next run may re-execute it.

A conceptual transaction flow:

```text
BEGIN TRANSACTION
   |
   +--> INSERT processed_item(idempotency_key)
   |
   +--> If key is new:
   |       update business data
   |       save result/reference
   |
   +--> If key already exists:
           check status and apply policy
   |
COMMIT
```

Under concurrency, never rely on a prior `SELECT` followed by `INSERT` without a constraint. Use unique keys and handle insert/duplicate outcomes safely.

## 7. Designing an idempotent ItemWriter

The Writer is where duplicate data is commonly produced because it persists business outputs. A safe Writer should derive a key for each item and write in a repeatable way.

Example Writer using JDBC upsert by business key:

```java
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.List;

import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriter;
import org.springframework.jdbc.core.BatchPreparedStatementSetter;
import org.springframework.jdbc.core.JdbcTemplate;

public class IdempotentOrderWriter implements ItemWriter<ProcessedOrder> {

    private final JdbcTemplate jdbcTemplate;

    public IdempotentOrderWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void write(Chunk<? extends ProcessedOrder> chunk) {
        List<? extends ProcessedOrder> items = chunk.getItems();

        jdbcTemplate.batchUpdate(
                """
                INSERT INTO imported_order
                    (source_system, source_order_id, customer_id, amount, imported_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT (source_system, source_order_id)
                DO UPDATE SET
                    customer_id = EXCLUDED.customer_id,
                    amount = EXCLUDED.amount
                """,
                new BatchPreparedStatementSetter() {
                    @Override
                    public void setValues(PreparedStatement ps, int i)
                            throws SQLException {
                        ProcessedOrder item = items.get(i);
                        ps.setString(1, item.sourceSystem());
                        ps.setString(2, item.sourceOrderId());
                        ps.setString(3, item.customerId());
                        ps.setBigDecimal(4, item.amount());
                    }

                    @Override
                    public int getBatchSize() {
                        return items.size();
                    }
                });
    }
}
```

This example uses PostgreSQL syntax and Spring Batch 5. `ProcessedOrder` is an application domain type. `JdbcTemplate` must use the `DataSource` participating in the Step's transaction so write statements commit/roll back with the chunk.

If the same business key arrives with a changed payload, such as a different amount, the upsert in this example overwrites it. If business rules forbid modifying an already-imported order, replace `DO UPDATE` with an ignore policy or report a conflict. Idempotency must reflect business rules, not merely serve as a trick to avoid unique constraint errors.

## 8. Ensuring idempotency during retry and rollback

In chunk processing, an exception can roll back the entire chunk transaction. Spring Batch may retry the item or chunk per configuration. If the Writer called an external service or wrote to a non-transactional resource, that action may have completed even though the database rolled back.

Example:

```text
Chunk transaction
   |
   +--> UPDATE order in database
   |
   +--> POST payment to external API (success)
   |
   +--> Error on next item
   |
   +--> ROLLBACK database transaction
          |
          +--> Payment API still received the request
```

On retry, the same payment request may be sent again. The solution is generating a stable idempotency key, such as `payment:<sourceTransactionId>`, and sending the exact same key on every attempt:

```http
POST /payments
Idempotency-Key: payment:TX-2026-000123
Content-Type: application/json
```

The receiving system must persist the key and processed outcome. If the same key arrives again, the system returns the prior result or confirms it was already processed without creating a second payment.

If the external system does not support idempotency keys, use an outbox table or a state-lookup mechanism before resending. Catching exceptions on the client side cannot guarantee no duplicates, because a timeout does not indicate whether the server executed the request.

## 9. Transactional outbox for messages and non-database side effects

When a chunk both updates the database and needs to publish messages, send emails, or call external systems, do not assume both operations roll back together. A transactional outbox solves this by writing business data and an outbound event in the same database transaction.

```text
Chunk transaction
   |
   +--> UPDATE imported_order
   |
   +--> INSERT outbox_event(event_id, payload, status='NEW')
   |
COMMIT
   |
   v
Outbox dispatcher
   |
   +--> Send event to message broker / API
   |
   +--> Mark event as sent
```

If the chunk rolls back, both the business change and the outbox event roll back. If the chunk commits, the event exists durably and the dispatcher can deliver it afterward. The dispatcher can still send duplicates if it stops after the broker receives the message but before marking it sent. Therefore, consumers should also deduplicate by `event_id` or use idempotency keys.

An outbox does not give the entire system exactly-once delivery on its own. It ensures events are not lost between database commit and dispatch, while duplicate deliveries still require idempotent handling.

## 10. Using staging tables and a promote step

For large file imports, data can be loaded into a staging table first, followed by another Step that merges data into the main table. Staging separates raw data from accepted data and enables deduplication before promotion.

Example flow:

```text
read source file
      |
      v
load staging table
      |
      v
validate and deduplicate
      |
      v
merge into target table by business key
      |
      v
mark batch completed
```

The staging table can enforce `(batch_id, source_record_key)` to prevent the same file line from being loaded multiple times in the same batch. The promote Step uses `MERGE` or upsert by the target table's business key.

This design is useful when you need to validate record counts, detect duplicates within the source file, handle line-level errors, and re-run a promote step without re-reading the file. Still, define a policy for when the same source key appears with differing payloads.

## 11. Preventing duplicates when a scheduler launches a Job multiple times

Duplicates do not occur only inside the Writer. A scheduler, API, or operator can submit the same launch request multiple times. Spring Batch identifies a `JobInstance` by Job name and identifying `JobParameters`:

- Same Job name and same identifying parameters: same `JobInstance`.
- `JobInstance` currently running: duplicate launch is normally rejected.
- `JobInstance` already `COMPLETED`: relaunching with the same identity is normally rejected.
- `JobInstance` `FAILED` or `STOPPED`: can be restarted if the Job allows restarts.
- Different identifying parameters: creates a new `JobInstance`.

For example, a file-processing Job should use `sourceFileId` or `businessDate + sourceFileId` as identifying parameters. Do not add a fresh timestamp or UUID to identifying parameters every time the scheduler resends the same request, because each call would create a new `JobInstance` and potentially re-import data.

If the application accepts requests from an API, store `request_id` with a unique constraint in a `batch_request` table. The API creates only one request per idempotency key; a dispatcher launches the Job based on that durable request. This provides an orchestration-level deduplication layer.

## 12. Partitioning and concurrency also require duplicate protection

With partitioning or multi-threaded Steps, multiple workers can write data concurrently. Ensure partitions do not overlap and the Writer is safe when multiple workers process simultaneously.

Principles:

- Partition sources along non-overlapping boundaries, such as ID ranges, tenants, or files.
- If partitioning uses hashing, every restart must use the same hash function and partition count for consistent distribution, or persist the partition plan upfront.
- Place unique constraints on business keys in target tables, because partitioning bugs can still occur.
- Never rely on an in-memory `Set` inside one worker to deduplicate across the entire Job; other workers do not share that state and restarts erase in-memory data.
- Use upserts, processed-item tables, or idempotency keys in durable storage.

If two partitions can contain the same business key, the unique constraint prevents duplicate inserts yet may cause one worker to receive a duplicate-key exception. The Writer must handle the exception per policy, or the partitioner must be fixed so data does not overlap.

## 13. Cases requiring explicit policies

| Situation | Question to answer |
|---|---|
| Same key, same payload | Ignore, return prior result, or update timestamp? |
| Same key, different payload | Should newer source overwrite? Based on which version? |
| Same file submitted twice | Treat as the same batch or two separate imports? |
| Job restarts after external API succeeded | Does the API support idempotency keys or status lookup? |
| Two partitions write the same key | Is partitioning overlapping or does source data contain duplicates? |
| An item was processed before the Job saved its checkpoint | Can the Writer run again without creating a second effect? |
| User requests reprocessing | Create a new version/correction ID or update the old result? |

No single upsert statement solves every case. Duplicate rules must be defined by business semantics and leave enough audit trail to explain why an item was ignored, updated, or reprocessed.

## 14. Testing duplicate prevention

Testing should not consist only of running the Job successfully once. Create retry, restart, and concurrency scenarios to confirm final data is not duplicated.

Useful scenarios:

1. **Launch identical JobParameters twice:** verify Spring Batch recognizes the same `JobInstance` and acts according to prior state.
2. **Restart after a mid-chunk failure:** have the Writer write partially then throw an exception; restart the Job and verify only one row exists per business key in the target table.
3. **Retry transient errors:** have a service or Writer fail on the first attempt and succeed on the next; verify side effects produce only one business outcome.
4. **Submit the same idempotency key multiple times:** verify the API or consumer returns the prior result instead of creating a new record.
5. **Run two workers with the same business key:** verify the unique constraint blocks duplicate data and the application handles the conflict per policy.
6. **Reprocess an already-imported file:** verify the batch request or file key prevents unintended re-imports.
7. **Outbox dispatcher stops between sending and marking:** verify the consumer deduplicates events by ID.

Example assertion after the Job completes:

```java
Integer count = jdbcTemplate.queryForObject(
        "select count(*) from imported_order "
                + "where source_system = ? and source_order_id = ?",
        Integer.class,
        "ERP",
        "ORD-100");

assertEquals(1, count);
```

For restart tests, use identical identifying `JobParameters` for the initial run and the restart to test the exact `JobInstance`. After restarting, inspect both `JobExecution` history and target data. Do not only assert `COMPLETED` status, because a Job can complete while still producing duplicate data.

## 15. Common mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Using plain `INSERT` in a Writer with retry/restart | The same item can create multiple rows. | Unique constraints and upsert by business key. |
| Only running `SELECT` to check before inserting | Race condition when multiple workers check concurrently. | Let database unique constraints enforce uniqueness. |
| Generating a new UUID on every retry | The system fails to recognize the same request. | Derive stable idempotency keys from business keys. |
| Writing the processed key in a separate transaction before main data | May mark as processed even though main data never committed. | Write marker and business data in the same transaction. |
| Calling APIs in the Writer without idempotency | Retries can trigger external side effects multiple times. | Use API idempotency keys or a transactional outbox. |
| Using in-memory collections to deduplicate | State is lost on restart and unshared across workers. | Use a database or durable state store. |
| Partitions without stable boundaries | Two workers may process the same record. | Persist the partition plan or create non-overlapping ranges. |
| Assuming checkpoints prevent all duplicates | Non-transactional side effects may occur before rollback. | Combine checkpoints with idempotent Writers and external keys. |

## Conclusion

Ensuring data is not duplicated in Spring Batch requires combining checkpoints/restarts with idempotent design at write boundaries. Choose stable business keys, enforce them with unique constraints, use upserts or processed-item tables in the same transaction as business data, and apply idempotency keys or transactional outboxes for external side effects. Under retries, rollbacks, duplicate scheduler launches, or concurrent partitions, the same item can still appear multiple times; the system must recognize and handle repeated execution safely. Testing restarts and concurrency by inspecting actual target data is the most important verification.
