# Recovering When a Chunk Fails and Designing Safe Retries

## Objectives

Batch processing often splits data into many small chunks to bound memory, transaction duration, and SQL batch size. A chunk can fail due to invalid data, constraint violations, concurrency conflicts, deadlocks, timeouts, or connection failures. The application needs to know which parts committed, which rolled back, and how to re-run without creating duplicate data or applying business logic twice.

After this lesson, you will be able to:

- Distinguish a single transaction's rollback from overall batch job progress.
- Design chunked transaction boundaries and flush intentionally to surface errors.
- Classify retryable errors versus errors requiring data remediation.
- Retry a chunk in a fresh transaction with bounded attempts and backoff.
- Store checkpoints to resume a job after process interruption.
- Design idempotent operations using business keys, idempotency keys, and unique constraints.
- Safely handle cases where it is uncertain whether a transaction committed.
- Protect external side effects outside the database using the transactional outbox and idempotent consumers.

## 1. Identifying the exact failure scope

Suppose a job imports 10,000 rows split into 100 chunks of 100 rows each. If each chunk runs in its own transaction, progress may look like:

| Chunk | Result | Data state |
|---|---|---|
| 1–35 | Committed | Persisted durably |
| 36 | Failed | Changes in chunk 36's transaction rolled back |
| 37–100 | Not yet run | Unprocessed |

In this design, a failure in chunk 36 does not automatically roll back the 35 previously committed chunks. Upon restart, the job can resume from chunk 36 if checkpoints and input data allow.

If all 10,000 rows sit inside one single transaction, an error rolling back the transaction cancels all changes in that transaction. This fits when business logic requires all-or-nothing semantics, though a large transaction can hold many entities in the persistence context, hold locks for a long time, and pressure transaction logs.

Three concepts must be distinguished:

- **Batch job:** the entire data import or update task.
- **Chunk:** a group of records processed as one unit of progress.
- **Transaction:** the commit or rollback boundary for database operations.

One chunk can correspond to one transaction, though that is a design decision. Before writing retry logic, clearly define which unit must succeed atomically together.

## 2. Flush, rollback, and persistence context state

JPA can defer SQL until flush or commit time. Therefore, a `save()` call returning normally does not prove data was successfully written to the database.

Example:

~~~java
@Transactional
public void importChunk(List<Product> products) {
    productRepository.saveAll(products);
    productRepository.flush();
}
~~~

`saveAll()` requests saving the entities; `flush()` instructs the persistence context to synchronize changes to the database. Flushing surfaces some SQL errors early, such as unique constraint violations or update errors. However, flush **does not commit the transaction**. The transaction can still fail on a subsequent statement or at commit time.

When a persistence error occurs, the transaction may be marked rollback-only. Do not catch a `PersistenceException` and continue processing entities in the same transaction as if nothing happened. Let the error escape the transaction boundary so the transaction rolls back, then decide on retry or error recording outside.

For large chunks, you can flush and clear the persistence context in sub-groups:

~~~java
@Transactional
public void importChunk(List<Product> products) {
    int count = 0;

    for (Product product : products) {
        entityManager.persist(product);
        count++;

        if (count % 50 == 0) {
            entityManager.flush();
            entityManager.clear();
        }
    }

    entityManager.flush();
    entityManager.clear();
}
~~~

`flush()` sends pending changes to the database; `clear()` detaches all entities from the persistence context to reduce memory. After `clear()`, the old Java objects are no longer managed. If you still need to modify an entity, reload or re-manage it according to its lifecycle.

The code above only illustrates persistence context management within one transaction. If the transaction fails at the end, operations already flushed in that transaction still roll back together. Flushing every 50 entities does not mean committing every 50 entities.

## 3. Choosing transaction boundaries per chunk

For jobs that must resume from completed progress, use a separate transaction per chunk. A dedicated service performs the write:

~~~java
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ChunkWriter {

    private final ProductRepository productRepository;

    public ChunkWriter(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void write(List<Product> products) {
        productRepository.saveAll(products);
        productRepository.flush();
    }
}
~~~

`REQUIRES_NEW` instructs Spring to open an independent transaction for this call. When the method is called through the Spring proxy and returns normally, the chunk's transaction finishes committing; when an error escapes, that transaction rolls back.

The coordinator invokes the service chunk by chunk:

~~~java
@Service
public class BatchRunner {

    private final ChunkWriter chunkWriter;

    public BatchRunner(ChunkWriter chunkWriter) {
        this.chunkWriter = chunkWriter;
    }

    public void run(List<List<Product>> chunks) {
        for (List<Product> chunk : chunks) {
            chunkWriter.write(chunk);
        }
    }
}
~~~

In the example, `BatchRunner` does not open an enclosing transaction spanning the entire job. Each `chunkWriter.write()` call passes through another bean's proxy, so the `REQUIRES_NEW` boundary is applied.

An important note: calling another `@Transactional` method via `this.write(...)` inside the same bean is self-invocation. That internal call does not pass through Spring's default proxy, so propagation may not be applied as expected. Put the transactional worker in a separate bean or use explicit transaction management such as `TransactionTemplate`.

Choose `REQUIRES_NEW` when each chunk must commit independently even if an outer transaction exists. When there is no outer transaction, `REQUIRED` on a worker bean can also create a separate transaction per call. The key is that the coordinator does not inadvertently group all chunks into one transaction.

## 4. Classifying errors before retrying

Not every error can be solved by re-running the same data.

| Error category | Examples | Typically appropriate handling |
|---|---|---|
| Transient | Deadlock, lock timeout, certain connection or temporary resource errors | Bounded retry with backoff and a fresh transaction |
| Data conflict | Optimistic locking failure because the entity was updated | Reload data, recompute business logic, then retry |
| Invalid data | Missing required field, invalid format, out-of-range value | Flag invalid record, fix data, or route to quarantine |
| Rule violation | Unique constraint, foreign key, check constraint | Determine if valid duplicate or business error; do not retry blindly |
| Programming or configuration error | Wrong mapping, invalid JPQL, missing schema column | Fix code or config; retrying will not resolve the root cause |

Spring provides exception hierarchies such as `TransientDataAccessException`, `DataIntegrityViolationException`, and `OptimisticLockingFailureException`. Exact exception translation depends on Spring, JPA provider, driver, and database engine. Classify based on actual root causes and application configuration.

For optimistic locking, retrying the same stale entity usually fails again. Reload the entity in a new transaction and recompute changes from the fresh state. For deadlocks or temporary resource errors, you can retry the entire chunk if chunk operations are designed to be safe when re-run.

## 5. Retrying with a fresh transaction and bounded attempts

A safe retry needs:

1. A maximum attempt limit.
2. Increasing wait intervals (backoff), optionally with jitter to avoid multiple workers retrying simultaneously.
3. A fresh transaction for each attempt.
4. Retrying only errors identified as transient.
5. Logging or metrics for attempt counts, chunk, cause, and final outcome.
6. Stopping and routing to failure handling when attempts are exhausted.

Example chunk retry coordinator:

~~~java
import java.util.List;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.stereotype.Service;

@Service
public class RetryingBatchRunner {

    private final ChunkWriter chunkWriter;

    public RetryingBatchRunner(ChunkWriter chunkWriter) {
        this.chunkWriter = chunkWriter;
    }

    public void writeWithRetry(List<Product> chunk) {
        int maxAttempts = 3;

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                chunkWriter.write(chunk);
                return;
            } catch (TransientDataAccessException ex) {
                if (attempt == maxAttempts) {
                    throw ex;
                }

                try {
                    Thread.sleep(100L * attempt);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(
                        "Retry was interrupted", interrupted);
                }
            }
        }
    }
}
~~~

In the example, each call to `chunkWriter.write()` passes through the proxy and opens a new transaction. Exceptions are caught only after the worker call returns and the transaction has rolled back. Do not catch errors inside the worker and continue using a broken transaction.

This is a minimal example with linear backoff. Production systems should use bounded backoff with jitter, reasonable timeouts, metrics, and avoid holding resources while waiting. Do not retry indefinitely because a failing dependency can cause queues to grow unboundedly.

`TransientDataAccessException` is a broad category. In production, narrow the retryable errors according to your database engine and application policy. Do not include `DataIntegrityViolationException` in a default retry list. If retrying a chunk containing updates to versioned entities, the worker must reload fresh data inside each transaction rather than holding stale entities from before the loop.

The `ChunkWriter` example above takes a list of entities to illustrate the transaction boundary. For jobs updating existing records, pass immutable input DTOs or IDs, then reload entities inside each worker call. Do not reuse entities detached after a rollback or carrying stale versions.

## 6. Checkpoints and job resumability

Checkpoints record completed progress so a job can resume after process termination or server restarts.

A job state table can store:

| Field | Meaning |
|---|---|
| job_id | Identifier of one logical job run |
| chunk_no | Chunk sequence number |
| status | PENDING, RUNNING, COMPLETED, or FAILED |
| attempt_count | Number of attempts |
| started_at, completed_at | Start and completion timestamps |
| error_code, error_message | Error details useful for investigation |

**Checkpoints must reflect committed data.** If COMPLETED status is written before chunk data commits, the process might crash after updating the checkpoint but before committing data. Upon restart, the job skips the chunk and data is missing.

There are two common organization patterns:

- **Same transaction:** write chunk data and mark the chunk COMPLETED within the same transaction. If the transaction rolls back, both data and checkpoint roll back; if it commits, both are durable together.
- **Post-commit checkpoint:** the worker commits data first, then another transaction updates the checkpoint. If the process stops between the two steps, the chunk may be re-run. This requires idempotent operations or a chunk-completion record with a unique key so the re-run detects work is already done.

You cannot rely solely on chunk sequence numbers if the source dataset can change while the job runs. Fix the input scope using a snapshot, job creation timestamp, file version, or persisted list of IDs. When resuming, use the same job_id and input set so chunks do not drift.

For paginated data, use a stable ordering, such as ascending ID, and store the last processed key. Avoid offset-based pagination on constantly changing datasets because inserted or deleted rows can shift page positions.

## 7. Idempotency: re-running without duplicating results

An operation is **idempotent** if executing it once or multiple times with the same identifier and data leads to the same business state.

Examples:

- Setting an order's status to **PAID** can be idempotent if state transitions are guarded and no duplicate side effects occur.
- Deducting 100 units from a balance on each call is not idempotent: calling twice deducts 200.
- Recording a stock receipt transaction by a unique reference code can be idempotent if the database prevents that code from being applied twice.

A `save()` statement does not make business logic idempotent on its own. If the same request is resent after a timeout, the application must recognize it as the same logical request.

### 7.1. Using an idempotency key

Each request or input item needs a stable key, for example:

- **client-request-id** generated by the caller.
- Transaction code from the source system.
- The pair **(job_id, source_record_id)** for an import row.
- The pair **(job_id, chunk_no)** for a chunk.

The key must remain identical across retries. Do not generate a new UUID on every attempt, as the database will treat each attempt as a new operation.

Store a payload hash or version alongside it. If the same idempotency key arrives with a different payload, return a conflict error rather than silently treating the new request as a duplicate of the old one.

### 7.2. Protecting the key with a unique constraint

One implementation is storing each processed command in a table whose primary key is the idempotency key:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "processed_command")
public class ProcessedCommand {

    @Id
    @Column(name = "idempotency_key", nullable = false, updatable = false)
    private String idempotencyKey;

    @Column(name = "payload_hash", nullable = false, updatable = false)
    private String payloadHash;

    protected ProcessedCommand() {
    }

    public ProcessedCommand(String idempotencyKey, String payloadHash) {
        this.idempotencyKey = idempotencyKey;
        this.payloadHash = payloadHash;
    }

    public String getPayloadHash() {
        return payloadHash;
    }
}
~~~

Repository:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProcessedCommandRepository
        extends JpaRepository<ProcessedCommand, String> {
}
~~~

Service processing the command and modifying business data in the same transaction:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CommandProcessor {

    private final ProcessedCommandRepository processedCommands;
    private final AccountRepository accountRepository;

    public CommandProcessor(
            ProcessedCommandRepository processedCommands,
            AccountRepository accountRepository) {
        this.processedCommands = processedCommands;
        this.accountRepository = accountRepository;
    }

    @Transactional
    public void apply(
            String key,
            String payloadHash,
            Long accountId,
            long amount) {

        processedCommands.saveAndFlush(
            new ProcessedCommand(key, payloadHash));

        Account account = accountRepository.findById(accountId)
            .orElseThrow(() ->
                new IllegalArgumentException("Account not found"));

        account.debit(amount);
    }
}
~~~

The example assumes **Account** has a **debit(long)** method enforcing balance rules and **AccountRepository** is a Spring Data repository. **saveAndFlush()** forces duplicate-key checking early. The processed command record and Account modification sit in the same transaction: if updating Account fails, the idempotency record rolls back too; if it commits, both are persisted together.

If two requests with the same key run concurrently, the database unique constraint is the final barrier. One transaction may wait for the other; after the first commits, the other cannot insert the same key. Do not rely on a **findById()** followed by **save()** pattern as a locking mechanism, because two requests can both see the key as absent before either writes.

### 7.3. Handling duplicate requests outside the transaction

When **saveAndFlush()** detects an existing key, the current transaction must roll back. Catch the error in a caller layer outside **CommandProcessor**'s transaction, then read the committed record:

~~~java
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;

@Service
public class IdempotentCommandFacade {

    private final CommandProcessor processor;
    private final ProcessedCommandRepository processedCommands;

    public IdempotentCommandFacade(
            CommandProcessor processor,
            ProcessedCommandRepository processedCommands) {
        this.processor = processor;
        this.processedCommands = processedCommands;
    }

    public void execute(
            String key,
            String payloadHash,
            Long accountId,
            long amount) {

        try {
            processor.apply(key, payloadHash, accountId, amount);
        } catch (DataIntegrityViolationException ex) {
            ProcessedCommand existing =
                processedCommands.findById(key).orElse(null);

            if (existing == null) {
                throw ex;
            }

            if (!existing.getPayloadHash().equals(payloadHash)) {
                throw new IllegalArgumentException(
                    "Idempotency key was reused with a different payload", ex);
            }

            // Same key and same payload: the request was already applied.
        }
    }
}
~~~

The facade has no **@Transactional**, so the exception leaves **CommandProcessor**'s proxy after the transaction fails. The **findById()** read runs afterward in the repository's read transaction. If the constraint error came from a different cause and no matching committed command exists, the facade rethrows the original exception.

In real applications, narrow duplicate detection to the specific idempotency key constraint. You can inspect the constraint name or database-specific error code. The example above also checks the record and payload hash to avoid swallowing an unrelated data integrity error.

Do not use this mechanism if the command also performs external side effects outside the database before commit. Emails, HTTP calls, or actions on external systems do not automatically roll back with a JPA transaction.

## 8. Handling side effects with the transactional outbox

Suppose a command updates an order and needs to send an **OrderPaid** event to a message broker. If the application commits the order and sending the message fails, downstream systems miss the event. If it sends the message first and the database transaction rolls back, downstream systems receive an event for a change that does not exist.

The transactional outbox bridges this gap:

1. In the same JPA transaction, update business data and insert an outbox record.
2. Commit the transaction. Business data and the pending event exist together or roll back together.
3. A worker reads unsent outbox records and publishes them to the broker.
4. After publishing succeeds, the worker marks the record as sent or records delivery state.
5. If the worker stops after publishing but before marking, the message may be sent again.

Because the final step can still repeat, consumers must be idempotent. For example, the consumer stores **event_id** with a unique constraint and applies business changes only when event_id has not been processed. This design typically achieves at-least-once delivery with safe deduplication; do not claim end-to-end exactly-once semantics solely from using an outbox.

Outbox fits events that need to be emitted after commit, such as order notifications, data synchronization, or updating other systems. For emails or external APIs, also use a durable job queue and provider idempotency keys where available.

## 9. Handling failed records and dead-letter queues

A batch job must distinguish single-record errors from errors that break an entire chunk.

If a row has malformed data, you can record the error details and continue processing other rows when business rules allow. If the error is a deadlock or lost connection, roll back the chunk and retry the entire transaction unit. Do not continue after a persistence error inside a transaction already marked rollback-only.

A useful operational state model:

- **PENDING:** not yet processed.
- **PROCESSING:** claimed by a worker; needs a lease or timeout to recover if the worker dies.
- **COMPLETED:** result committed.
- **RETRY_WAIT:** transient error, waiting for retry time.
- **FAILED_PERMANENT:** error that cannot be resolved by automatic retry.
- **DEAD_LETTER:** exceeded retry attempts or requires operator inspection.

Record error codes, sanitized messages, source record ID, job ID, chunk number, attempt count, and timestamps. Avoid writing secrets or sensitive payloads into unprotected logs.

A dead-letter record needs enough information to repair and replay intentionally. When replaying, keep the same business key or idempotency key if it remains the same logical operation. If an operator edited the payload and it constitutes a new operation, create a new version or identifier per business rules while preserving a link to the prior attempt for traceability.

## 10. Testing recovery and idempotency

Do not test only happy-path batch runs. Test failure points and stops that can happen:

1. **Mid-chunk failure:** craft data causing one statement in a chunk to violate a constraint; confirm the entire chunk rolls back.
2. **Failure after commit but before checkpoint:** simulate process stop after a chunk commits; re-run and confirm no duplicate data or duplicate side effects are created.
3. **Deadlock or timeout retry:** simulate transient errors; confirm each attempt uses a fresh transaction and attempts do not exceed the limit.
4. **Permanent data error:** confirm the record is marked FAILED_PERMANENT or moved to dead-letter without endless retries.
5. **Two requests with the same idempotency key:** run concurrently; confirm the business change applies only once.
6. **Same key, different payload:** confirm the second request is rejected as a conflict.
7. **Outbox duplicate delivery:** publish the same event multiple times; confirm the consumer applies the business effect only once.
8. **Job resume:** stop after several committed chunks, restart with the same job_id, and confirm completed chunks are not applied again.

Use independent transactions and threads in integration tests to reproduce real contention. Verify final state using a new transaction rather than inspecting entities still sitting in the test's persistence context. Run lock, deadlock, and batch tests against the same database engine the application deploys to.

## 11. Design checklist before deployment

- Determine whether the whole job must be atomic or only individual chunks must be atomic.
- Choose chunk size based on memory, transaction duration, SQL batching, and recoverability.
- Flush intentionally to surface errors; clear when needed to reduce persistence context size.
- Use a separate transaction per chunk when independent progress commits are needed.
- Retry only transient errors; set limits, backoff, and jitter.
- Reload entities and recompute business logic after optimistic locking conflicts.
- Persist checkpoints in the same transaction as data whenever possible; if separated, ensure safe replay.
- Use stable idempotency keys and database unique constraints.
- Check payload hashes to detect same-key different-content conflicts.
- Place external side effects in a transactional outbox and make consumers idempotent.
- Store error state, attempt counts, and enough context for investigation or replay.
- Test rollback, retry, crash between commit and checkpoint, duplicate requests, and job resume.

A reliable batch job must answer three questions: what data committed, what data needs reprocessing, and how to guarantee a re-run does not apply business logic a second time. Transaction boundaries, checkpoints, and idempotency must be designed together so recovery always yields deterministic outcomes.
