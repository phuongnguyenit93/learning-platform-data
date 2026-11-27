# Batch Data Import with Concurrency Limits and Error Policies

A large data import flow often has to read thousands or millions of records, validate them, convert them into entities, and write them to a database via Spring Data Relational R2DBC. Processing sequentially can take far too long. Issuing too many concurrent operations can exhaust the connection pool, increase lock contention, or overload the database.

The solution is splitting the stream into bounded-size batches, capping how many batches or records execute concurrently, and defining clearly which errors are skipped, which are retried, and which halt the import. Reactive Streams and Reactor provide operators such as `buffer`, `bufferTimeout`, `flatMap`, `concatMap`, and `retryWhen` to build controlled pipelines.

Batch size, concurrency, transaction boundaries, and error policy are four separate decisions. A batch might hold 500 rows while allowing only 3 batches to write concurrently. A validation error might reject a single row, whereas a lost connection might require stopping the entire job. If a batch-level transaction fails, other rows in that same batch may also roll back.

This lesson explains how to design an import pipeline with `Flux`, group items into bounded batches, tune concurrency to database capacity, choose per-row vs. per-batch transactions, classify errors, retry safely, ensure idempotency, persist progress, and test against a real database.

## 1. Big picture of an import pipeline

An import pipeline typically includes these stages:

1. Reading records from a file, message stream, or HTTP source.
2. Assigning row numbers or source keys for traceability.
3. Parsing and normalizing data.
4. Validating records against business rules.
5. Grouping records into bounded batches.
6. Writing to the database with bounded concurrency.
7. Classifying successes, data errors, and infrastructure failures.
8. Persisting outcomes, progress, and checkpoints.
9. Producing an import report.

~~~text
Data source
   |
   v
Flux<ImportRow>
   |
   v
Assign row number / source key
   |
   v
Parse + normalize + validate
   |
   v
Buffer into bounded batches
   |
   v
flatMap with bounded concurrency
   |
   +-------------------------------+
   |                               |
   v                               v
Per-row transaction         Per-batch transaction
   |                               |
   v                               v
R2DBC repository / DatabaseClient
   |                               |
   +---------------+---------------+
                   |
                   v
       Outcomes + errors + checkpoint
                   |
                   v
             Import report
~~~

You do not have to implement every step in a single class. Separate the parser, validator, writer, error classifier, and job coordinator so each can be tested independently.

## 2. Why batching is needed

A large data source should never be loaded completely into memory before writing.

Example of a problematic approach:

~~~java
List<ImportRow> rows = Files.readAllLines(path)
        .stream()
        .map(this::parse)
        .toList();

return Flux.fromIterable(rows)
        .flatMap(repository::save);
~~~

This approach can:

- Load the entire file onto the heap.
- Allocate extra objects for every row upfront.
- Fire too many concurrent write operations at once.
- Leave the number of active transactions unbounded.
- Make resuming from a checkpoint hard if the process stops mid-run.

Instead, stream records and hold only a bounded slice in memory:

~~~java
Flux<ImportRow> rows = importFileReader.read(path);

return rows
        .buffer(250)
        .concatMap(this::writeBatch);
~~~

`buffer(250)` collects up to 250 items into a `List` and emits that `List`. `concatMap` waits for the current batch to finish before starting the next one, so only one batch is active at a time in this pipeline.

This design is simple, predictable, and ordered. If higher throughput is needed, allow multiple batches to run concurrently using `flatMap` with bounded concurrency.

## 3. Distinguishing batch size and concurrency

These two parameters are not the same:

- **Batch size:** number of records in a single group.
- **Concurrency:** number of groups or operations allowed to execute simultaneously.

For example, a batch size of 200 and chunk concurrency of 4 can keep roughly 800 records in active batches, excluding upstream buffers/prefetch and auxiliary results.

| Batch size | Chunk concurrency | Meaning |
|---:|---:|---|
| 100 | 1 | One batch of 100 rows at a time |
| 100 | 4 | Up to 4 batches processed concurrently |
| 500 | 2 | Up to ~1,000 rows in active batches |
| 1,000 | 8 | Can place heavy pressure on memory and the database |

No single pair of numbers fits every system. Measure with production-like data and database resources.

### 3.1. Small batches

Pros:

- Shorter transactions when each batch is one transaction.
- Lower memory footprint.
- A failure in one batch affects fewer rows.
- More frequent checkpoints.

Cons:

- More database round-trips.
- Higher transaction open/commit overhead when each batch starts a transaction.
- Lower efficiency if individual writes are very small.

### 3.2. Large batches

Pros:

- Can reduce round-trips or transaction count.
- Can leverage bulk inserts if the driver and database support them.
- Higher throughput when per-write overhead is high.

Cons:

- Holds more objects in memory.
- Longer transactions and longer lock durations.
- Rollbacks discard more completed work.
- One error can affect many rows.
- Can hit database parameter or statement limits.

Choose batch size alongside your transaction policy and how the driver executes batches.

## 4. Streaming data instead of loading entire files

For large files, the parser should emit records incrementally rather than returning a `List` of the whole file.

~~~java
public interface ImportFileReader {
    Flux<ImportRow> read(Path path);
}
~~~

The parser can use a streaming CSV library or read line by line using an appropriate API. If using blocking file APIs, isolate file reads on a dedicated scheduler or use a non-blocking library. Non-blocking R2DBC does not automatically make a blocking file parser non-blocking.

Assign row numbers as records arrive:

~~~java
Flux<IndexedImportRow> indexedRows =
        reader.read(path)
                .index()
                .map(tuple ->
                        new IndexedImportRow(
                                tuple.getT1() + 1,
                                tuple.getT2()));
~~~

`index()` emits zero-based indices; add 1 for 1-based display row numbers. If the file has a header, the parser must track the actual source line number or store a separate source offset.

Do not rely solely on an in-memory index if you need to resume after a restart. For resumable imports, persist the source row number or a stable source key in a checkpoint.

## 5. Batching with buffer

Reactor offers several operators for grouping items.

### 5.1. buffer(size)

~~~java
source.buffer(200)
~~~

Collects up to 200 elements into a `List`. When upstream completes, the final batch may hold fewer than 200 items.

### 5.2. bufferTimeout(size, duration)

~~~java
source.bufferTimeout(
        200,
        Duration.ofMillis(300))
~~~

Emits a batch when 200 elements arrive or when 300 ms elapses. This helps continuous streams where waiting for a full batch might stall too long.

### 5.3. bufferUntil and bufferWhile

These operators group by data conditions, such as grouping by tenant or record type. They do not replace a maximum batch size if a group can grow without bound. Enforce a size cap when grouping by key.

### 5.4. Never create unbounded buffers

Avoid collecting every record into a collection and writing only after the source completes. If the source never completes, the import writes nothing while memory grows endlessly.

A streaming pipeline should enforce clear bounds on:

- Records per batch.
- Active batches in flight.
- Prefetched items.
- Outcomes/errors retained in memory.
- Open transactions.

## 6. Limiting concurrency with flatMap

Example allowing at most 4 concurrent batches:

~~~java
return source
        .buffer(200)
        .flatMap(
                this::writeBatch,
                4,
                1);
~~~

Parameters of `flatMap(mapper, concurrency, prefetch)`:

- `mapper`: turns each batch into a `Publisher`.
- `concurrency`: maximum inner `Publisher`s subscribed concurrently.
- `prefetch`: number of items requested ahead from each inner publisher.

Here, up to 4 batches run concurrently with a prefetch of 1 per inner publisher. Choose prefetch to fit the operator and driver rather than treating it as a batch size.

### 6.1. flatMap does not preserve output order

Batches can finish in a different order than the source stream. If batch 2 finishes faster than batch 1, batch 2's outcomes emit first.

To run concurrently while emitting results in source order:

~~~java
return source
        .buffer(200)
        .flatMapSequential(
                this::writeBatch,
                4,
                1);
~~~

`flatMapSequential` buffers results from batches that finish early while waiting for earlier batches. Preserving order can therefore raise memory usage and output latency.

If both execution and output must be strictly sequential, use:

~~~java
return source
        .buffer(200)
        .concatMap(this::writeBatch);
~~~

### 6.2. flatMap with per-row concurrency

You do not always need to buffer into batches when each record runs in its own transaction:

~~~java
return source.flatMap(
        this::importOne,
        8,
        1);
~~~

Here, at most 8 records are processed concurrently. This fits scenarios needing per-row partial success where every row has its own transaction.

### 6.3. Concurrency does not mean spawning threads

R2DBC drivers typically perform asynchronous I/O. `flatMap` controls how many publishers are subscribed concurrently; it does not spawn a separate thread per record.

Do not use `parallel()` or inflate scheduler thread counts just to issue more queries. Tune concurrency, pool limits, and database capacity first.

## 7. Sizing concurrency to connection pool and database capacity

If an R2DBC pool has max size 20, do not let an import job consume all 20 connections by default. API traffic, health checks, background jobs, and other tasks also need connections.

Example budget:

- Pool max size: 20.
- Reserved for API traffic: 8.
- Reserved for other jobs/maintenance: 2.
- Maximum budget for import: roughly 10 connections.

This is only an illustrative calculation. If each batch opens one transaction/connection, chunk concurrency should stay within that budget. If a batch issues parallel queries, actual connection/operation demand differs.

Reference formula:

\[
C_{\text{import}}
\leq
P_{\text{pool}}
-
R_{\text{API}}
-
R_{\text{other}}
\]

In multi-replica deployments, account for total pool connections across all instances:

\[
P_{\text{total}}
=
P_{\text{per instance}}
\times
N_{\text{instances}}
\]

Databases have limits on sessions, CPU, IOPS, locks, and transaction logs. Raising concurrency can actually lower throughput once the database saturates.

### 7.1. Start low and scale up gradually

A practical approach:

1. Start with concurrency 1 or 2.
2. Measure import duration, query latency, and pool pending acquires.
3. Increase step by step.
4. Watch for timeouts, deadlocks, lock waits, and database CPU.
5. Stop increasing when throughput plateaus or tail latency spikes.

Measure with dataset sizes and distributions resembling production. A test with a few dozen rows cannot guide concurrency for millions of rows.

## 8. Two primary transaction strategies

Batch processing requires deciding where transaction boundaries sit.

| Strategy | Transaction covers | When appropriate |
|---|---|---|
| One transaction per file | Entire import | Small files, strict all-or-nothing requirement, short duration |
| One transaction per batch | All records in a batch | Group commits acceptable, batch-wide rollback acceptable |
| One transaction per record | A single record | Partial success required so one row's error does not affect others |

No strategy is universally right. Choose based on business requirements, database behavior, and resume needs.

### 8.1. One transaction per file

Pro: if anything fails before commit, all changes roll back cleanly.

Cons:

- Transactions can run far too long.
- Connections stay pinned for the entire import.
- Lock footprints and transaction/undo logs grow large.
- Hard to retry partially.
- One error near the end can roll back all completed work.

Avoid wrapping a multi-million-row file in a single transaction just for "safety".

### 8.2. One transaction per batch

Each batch commits or rolls back independently. This is often a balanced choice for large imports.

If batch 4 fails, batches 1–3 may already be committed. The job needs checkpoints to resume from the right position and idempotency to rerun safely.

If one record hits a database error inside a batch transaction, many engines such as PostgreSQL mark the entire transaction as aborted. You cannot catch a constraint error and keep inserting later rows in the same transaction as if nothing happened. Roll back the batch transaction, or use savepoints if supported and tested by your driver and database.

### 8.3. One transaction per record

Each record gets its own transaction. When one record violates a unique constraint, that record's transaction rolls back while other records proceed.

Pros:

- Easy per-row error reporting.
- Natural partial success.
- Independent per-record retries.
- One constraint failure does not poison the next record's transaction.

Cons:

- Many more transactions.
- Higher transaction/round-trip overhead.
- Requires concurrency caps to avoid opening too many simultaneous transactions.

## 9. Configuring TransactionalOperator for R2DBC

When explicit transactions are needed, use a reactive transaction manager and `TransactionalOperator`.

Example configuration:

~~~java
@Configuration
public class R2dbcTransactionConfiguration {

    @Bean
    TransactionalOperator transactionalOperator(
            ReactiveTransactionManager transactionManager) {
        return TransactionalOperator.create(transactionManager);
    }
}
~~~

Spring Boot may already auto-configure a reactive transaction manager for your `ConnectionFactory`. Inspect the application context before declaring duplicate beans.

All repository and database operations within a transaction must share the same reactive transaction context and `ConnectionFactory`. Never construct a standalone `ConnectionFactory` inside one repository and expect the active transaction manager to govern it.

### 9.1. Per-record transaction

~~~java
private Mono<ImportedCustomer> saveOne(ImportRow row) {
    Mono<ImportedCustomer> write =
            customerRepository.save(toEntity(row));

    return transactionalOperator.transactional(write);
}
~~~

If the pipeline re-subscribes to the transactional publisher, a new transaction is created for that subscription. When retrying, place `retryWhen` outside the transaction-wrapped publisher so each attempt gets a fresh transaction.

### 9.2. Per-batch transaction

~~~java
private Mono<List<ImportedCustomer>> saveBatch(
        List<ImportRow> batch) {

    Mono<List<ImportedCustomer>> work =
            Flux.fromIterable(batch)
                    .concatMap(row ->
                            customerRepository.save(toEntity(row)))
                    .collectList();

    return transactionalOperator.transactional(work);
}
~~~

Operations inside a batch run sequentially via `concatMap` within the same transaction. If any operation fails, the transaction rolls back the entire batch.

Never casually swap `concatMap` for `flatMap` inside the same transaction. A reactive transaction usually binds to a single connection; drivers may not support concurrent statements on the same connection or transaction. Verify driver and transaction manager capabilities before running parallel queries inside a transaction.

## 10. Error policies must be defined upfront

Not every error deserves the same response. Classify failure modes before writing operators.

| Error category | Example | Typical policy |
|---|---|---|
| Format/validation error | Missing email, invalid date | Reject row and continue |
| Business rule error | Disallowed status, missing customer | Reject or route to review list |
| Duplicate/conflict | Unique constraint, import key already exists | Skip, reject, or upsert per contract |
| Transient database error | Temporary connection drop, retryable deadlock | Bounded retry |
| Configuration/schema error | Wrong column name, missing table, SQL grammar | Stop job |
| Persistent infrastructure outage | Database unavailable, sustained pool timeouts | Stop job and resume later |
| Unknown error | Unclassified exception | Fail job and store safe diagnostics |

An explicit policy must answer:

- Does a bad record halt the whole file?
- Should processing continue after duplicates?
- How many retries are allowed?
- Do infrastructure failures move the job to `FAILED` or `PAUSED`?
- Can committed batches be re-run safely?
- Which row numbers and error codes belong in the error report?
- Is there a cap on stored error details?

Never let default operator behavior dictate business semantics in place of explicit design.

## 11. Per-row import outcome model

Instead of failing the entire stream on every data error, model each record's result:

~~~java
public record ImportOutcome(
        long rowNumber,
        ImportStatus status,
        Long generatedId,
        String errorCode,
        String safeMessage) {

    public static ImportOutcome success(
            long rowNumber,
            Long id) {
        return new ImportOutcome(
                rowNumber, ImportStatus.SUCCESS, id, null, null);
    }

    public static ImportOutcome rejected(
            long rowNumber,
            String code,
            String message) {
        return new ImportOutcome(
                rowNumber, ImportStatus.REJECTED, null, code, message);
    }
}
~~~

Enum:

~~~java
public enum ImportStatus {
    SUCCESS,
    REJECTED,
    SKIPPED,
    FAILED
}
~~~

Use stable error codes like `EMAIL_REQUIRED`, `DUPLICATE_EXTERNAL_ID`, or `UNKNOWN_CUSTOMER`. Never expose raw SQL, stack traces, passwords, or personal data in user-facing reports.

For very large files, do not hold every `ImportOutcome` in a `List`. Persist errors to an `import_error`/`import_row_status` table or stream reports out to a file.

## 12. Per-record transaction pattern with bounded concurrency

This strategy fits imports that must continue past row-level data errors.

~~~java
@Service
public class CustomerImportService {

    private final CustomerRepository repository;
    private final TransactionalOperator transactionalOperator;

    public CustomerImportService(
            CustomerRepository repository,
            TransactionalOperator transactionalOperator) {
        this.repository = repository;
        this.transactionalOperator = transactionalOperator;
    }

    public Flux<ImportOutcome> importRows(
            Flux<IndexedImportRow> rows) {

        return rows.flatMap(
                this::importOne,
                8,
                1);
    }

    private Mono<ImportOutcome> importOne(IndexedImportRow item) {
        Mono<Customer> write = Mono.defer(() -> {
            validate(item.row());

            return repository.save(toEntity(item.row()));
        });

        return transactionalOperator.transactional(write)
                .map(saved ->
                        ImportOutcome.success(
                                item.rowNumber(),
                                saved.getId()))
                .onErrorResume(
                        InvalidImportRowException.class,
                        error -> Mono.just(
                                ImportOutcome.rejected(
                                        item.rowNumber(),
                                        error.code(),
                                        error.safeMessage())))
                .onErrorResume(
                        DataIntegrityViolationException.class,
                        error -> Mono.just(
                                ImportOutcome.rejected(
                                        item.rowNumber(),
                                        "DATA_CONFLICT",
                                        "Record conflicts with stored data")));
    }
}
~~~

This illustrative example needs retries and job-level failure handling for production. Key points:

- `flatMap(..., 8, 1)` bounds active records to at most 8.
- Each record runs in its own transaction.
- Validation and constraint errors convert into outcomes after the record's transaction finishes and rolls back.
- Unclassified infrastructure errors propagate outward and can halt the pipeline.
- Outcome order is not preserved because `flatMap` lets faster records finish ahead of earlier ones.

Never catch every `Throwable` and convert it into `REJECTED`. If the database loses connectivity, reporting a million rejected rows hides an infrastructure outage.

### 12.1. Adding bounded retries

Build the transactional publisher per attempt and wrap the retry outside it:

~~~java
private Mono<ImportOutcome> importOne(IndexedImportRow item) {
    Mono<Customer> oneAttempt = Mono.defer(() -> {
        validate(item.row());

        Mono<Customer> write =
                repository.save(toEntity(item.row()));

        return transactionalOperator.transactional(write);
    });

    return oneAttempt
            .retryWhen(
                    Retry.backoff(3, Duration.ofMillis(100))
                            .maxBackoff(Duration.ofSeconds(2))
                            .jitter(0.5)
                            .filter(this::isTransientDatabaseFailure)
                            .onRetryExhaustedThrow(
                                    (spec, signal) -> signal.failure()))
            .map(saved ->
                    ImportOutcome.success(
                            item.rowNumber(),
                            saved.getId()))
            .onErrorResume(
                    InvalidImportRowException.class,
                    error -> Mono.just(
                            ImportOutcome.rejected(
                                    item.rowNumber(),
                                    error.code(),
                                    error.safeMessage())))
            .onErrorResume(
                    DataIntegrityViolationException.class,
                    error -> Mono.just(
                            ImportOutcome.rejected(
                                    item.rowNumber(),
                                    "DATA_CONFLICT",
                                    "Record conflicts with stored data")));
}
~~~

`Mono.defer` ensures each subscription/retry recreates the write and transaction publisher. Retries apply only to errors matched by `isTransientDatabaseFailure`. Never retry validation failures or unique conflicts.

A predicate can walk the cause chain:

~~~java
private boolean isTransientDatabaseFailure(Throwable error) {
    for (Throwable cause = error;
            cause != null;
            cause = cause.getCause()) {

        if (cause instanceof R2dbcTransientException
                || cause instanceof TransientDataAccessException) {
            return true;
        }
    }

    return false;
}
~~~

Drivers classify exceptions differently. Inspect the real exceptions emitted by your driver and retry only failures verified as transient. Deadlocks and serialization conflicts can be retried in certain cases, provided the entire transaction reruns and operations are safely repeatable.

## 13. Per-batch transaction pattern with bounded concurrency

When each batch must be atomic, multiple independent batches can run concurrently:

~~~java
public Flux<BatchOutcome> importInBatches(
        Flux<IndexedImportRow> source) {

    return source
            .buffer(200)
            .flatMap(
                    this::writeBatchAtomically,
                    3,
                    1);
}

private Mono<BatchOutcome> writeBatchAtomically(
        List<IndexedImportRow> batch) {

    Mono<List<Customer>> work =
            Flux.fromIterable(batch)
                    .concatMap(item ->
                            Mono.fromRunnable(() ->
                                            validate(item.row()))
                                    .then(Mono.defer(() ->
                                            repository.save(
                                                    toEntity(item.row())))))
                    .collectList();

    return transactionalOperator.transactional(work)
            .map(saved ->
                    BatchOutcome.success(
                            batch.size(),
                            saved.size()));
}
~~~

In this example:

- Each batch contains up to 200 rows.
- Up to 3 batches run concurrently.
- Within each batch, records are written sequentially.
- Each batch owns its own transaction.
- If any row fails during write, the entire batch transaction rolls back.

These are batch-level all-or-nothing semantics. Do not use this pattern if business rules require valid rows in the same batch to survive when one row fails.

### 13.1. Reporting batch failures after rollback

To let the pipeline continue with subsequent batches, handle errors outside the transaction:

~~~java
private Mono<BatchOutcome> writeBatchAtomically(
        List<IndexedImportRow> batch) {

    Mono<List<Customer>> work =
            Flux.fromIterable(batch)
                    .concatMap(item ->
                            Mono.fromRunnable(() ->
                                            validate(item.row()))
                                    .then(Mono.defer(() ->
                                            repository.save(
                                                    toEntity(item.row())))))
                    .collectList();

    return transactionalOperator.transactional(work)
            .map(saved -> BatchOutcome.success(batch, saved))
            .onErrorResume(error -> {
                if (isFatalInfrastructureFailure(error)) {
                    return Mono.error(error);
                }

                return Mono.just(
                        BatchOutcome.rolledBack(
                                batch,
                                classifyBatchFailure(error)));
            });
}
~~~

Here `onErrorResume` sits outside the transaction publisher. When it executes, the transaction has already terminated along the error path and rolled back if the database/transaction manager supports rollback for that failure.

If the connection drops right at commit time, the commit outcome may be ambiguous. Never claim a batch rolled back without evidence; use idempotency keys and checkpoints to reconcile state.

### 13.2. Pre-transaction validation to reduce unnecessary rollbacks

If validation depends solely on the record's fields without database queries, classify validation failures before opening a transaction. Keep the row number and rejection reason so the report remains complete.

Database-dependent checks such as reference lookups still face race conditions; database constraints remain the final guardrail.

## 14. Never continue writing inside an aborted transaction

This is a common design mistake when pursuing partial success.

Suppose a batch runs inside a PostgreSQL transaction and one `INSERT` violates a unique constraint. PostgreSQL marks the transaction as aborted; every subsequent statement in that transaction fails until rollback.

Logic like:

~~~java
Flux.fromIterable(batch)
        .concatMap(row ->
                repository.save(toEntity(row))
                        .onErrorResume(
                                DataIntegrityViolationException.class,
                                error -> Mono.empty()))
~~~

may swallow the error at the publisher level, but it does not heal the database transaction state. Subsequent inserts will still fail because the transaction is already aborted.

Safer alternatives:

- Use a separate transaction per row when processing must continue past per-row constraint errors.
- Use a batch transaction and roll back the entire batch on error.
- Use savepoints if supported and tested on your driver, database, and transaction manager.
- Validate and deduplicate before entering the transaction, while still handling database constraint races.

Never assume `onErrorResume` replacing an error signal leaves the database transaction usable.

## 15. Using savepoints when batch partial success is truly required

Savepoints allow rolling back part of a transaction in some databases. However, R2DBC savepoint support and how transaction managers expose it vary by driver, database, and version.

Before relying on savepoints, verify:

- The driver supports creating, rolling back, and releasing savepoints.
- The transaction manager exposes and supports those operations.
- The database permits continuing the transaction after rolling back to a savepoint.
- Constraint violations recover cleanly under the database's semantics.
- Savepoints work reliably with connection pooling and reactive transaction contexts.

When portability matters, per-row transactions are easier to reason about. Savepoints can cut transaction overhead, at the cost of extra complexity and database coupling.

## 16. Distinguishing fail-fast, continue-on-error, and delay-error

### 16.1. Fail-fast

By default, combining operators such as `flatMap` terminate when an inner publisher emits an error, canceling remaining subscriptions per operator semantics. This fits failures indicating the job cannot continue.

Note that operations already sent to the database may have executed or committed before cancellation arrives. Fail-fast does not roll back previously committed independent transactions.

### 16.2. Per-record continue-on-error

Use `onErrorResume` inside a single record's publisher, converting only well-defined data errors into outcomes. Infrastructure and fatal errors must still escape.

This pattern suits imports that allow partial success.

### 16.3. Delay error

Reactor offers delay-error operators like `flatMapDelayError` that wait for other inner publishers to finish before emitting a composite error. This helps in pipelines needing to collect partial results before failing.

However, delay-error does not classify business errors, does not roll back committed transactions, and does not generate per-row error reports. Use it intentionally, not as a substitute for an error policy.

### 16.4. Avoid onErrorContinue for critical imports

`onErrorContinue` has operator- and position-dependent semantics that make control flow unpredictable. It can skip an element without guaranteeing the database transaction recovered.

Prefer `onErrorResume` at the clear boundary of a single record or batch, where you know exactly which record failed and which transaction ended.

## 17. Retries: when allowed and when forbidden?

Retries help for transient failures:

- Temporary connection drops.
- Deadlocks resolvable by rerunning the transaction.
- Serialization conflicts under database isolation.
- Dependent services returning transient errors.

Never blindly retry:

- Malformed data.
- Unique or business constraint violations without a resolution strategy.
- Invalid SQL grammar.
- Missing tables or columns.
- Mapping or conversion bugs.
- Permission denials.

### 17.1. Retries must be bounded

~~~java
Retry.backoff(3, Duration.ofMillis(100))
        .maxBackoff(Duration.ofSeconds(2))
        .jitter(0.5)
        .filter(this::isTransientDatabaseFailure);
~~~

Backoff avoids hammering an overloaded database. Jitter prevents workers from retrying in lockstep.

Bound total job duration and record retry counts. Unbounded retries pin resources and let backlogs grow indefinitely.

### 17.2. Retry the whole transaction unit

If a batch performs several inserts and one fails transiently, retry the entire batch transaction after rollback rather than retrying only the last statement inside an aborted transaction.

With per-row transactions, retry that row. With per-batch transactions, retry that batch. Place retries outside the transactional publisher so each attempt opens a fresh transaction.

### 17.3. Idempotency is essential

If a request times out or drops after the database commits but before the app receives the acknowledgment, the app does not know whether the record persisted. Retrying without idempotency creates duplicates.

An idempotency key can combine:

- Import job ID.
- Source row number or source record key.
- Tenant/business key where appropriate.

Enforce a unique constraint on this key or an import ledger table. On rerun, the application detects already-processed records and produces matching outcomes.

Never use an auto-generated sequence ID as an idempotency key. Sequences advance even when transactions roll back.

## 18. Duplicates, upserts, and pre-existing data

During imports, duplicates can mean several things:

- Record already imported earlier in the same job.
- Record already exists from a previous job.
- Business key is already taken.
- Duplicate rows appear within the same input file.

Possible policies:

| Policy | Behavior |
|---|---|
| Reject | Record a duplicate error |
| Skip | Leave existing record untouched |
| Update | Update existing record by business key |
| Upsert | Insert if absent, update if present |
| Merge | Update selected fields per domain rules |

Upsert syntax and semantics are database-specific. Spring Data R2DBC does not generate one portable upsert across all dialects. You may need custom SQL and integration tests against the target database.

If an input file contains multiple rows with the same business key, decide which wins: first row, last row, or reject all. Deduplicate prior to writing if required by policy.

Never rely on a `SELECT` existence check followed by `INSERT` to guarantee uniqueness under concurrency. Two workers can both see "not found". Only a database unique constraint or atomic upsert resolves the race condition.

## 19. Checkpoints and resumability

Large imports can be interrupted by deployments, network drops, timeouts, or process crashes. Without checkpoints, the job must restart from line one.

A job table can track:

- Job ID.
- File/source identity and checksum.
- Status: `PENDING`, `RUNNING`, `PAUSED`, `COMPLETED`, `FAILED`.
- Total record count if known.
- Succeeded, rejected, and skipped counts.
- Last processed position or row number.
- Start, update, and completion timestamps.
- Overall error code.

A detail table can store per-source-key or per-batch statuses.

### 19.1. Checkpoints must stay consistent with commits

If data writes commit but the checkpoint is not updated, a restart will reprocess records. If the checkpoint advances before data commits, a restart will skip unsaved records.

The safest pattern updates business rows and the import ledger/checkpoint in the same transaction when stored in the same database:

~~~text
BEGIN
  INSERT/UPDATE business row
  INSERT import_row_ledger
  UPDATE import_job progress
COMMIT
~~~

If data and checkpoints live in separate systems, atomicity is not automatic; design reconciliation and idempotency accordingly.

### 19.2. Do not checkpoint solely by row number if the source can change

If a file is replaced or edited, row 1000 in the new file may differ from row 1000 in the old file. Store a checksum, version, or source identity to confirm resumes match the original input.

For message streams, use message offsets/partitions or source event IDs per broker semantics.

## 20. Cancellation and import job lifecycle

If an HTTP request uploads a large file and the client disconnects, the publisher may be canceled. Cancellation stops further pipeline execution, yet already-committed transactions remain persisted. In-flight writes already sent to the database may also finish before cancellation takes effect.

Decide whether the import belongs to the HTTP request lifecycle or runs as an independent job.

### 20.1. Synchronous request-scoped import

Suitable for small files and short durations. The client waits for completion. If the client cancels the request, the pipeline cancels.

### 20.2. Asynchronous import job

For large files, usually:

1. Upload and store the file in durable storage.
2. Create an import job record.
3. Return HTTP `202 Accepted` with the job ID.
4. Have a worker/job coordinator manage the import publisher.
5. Persist progress and outcomes.
6. Let clients poll job status.

Never fire-and-forget `subscribe()` inside a controller to "run in the background". Background execution needs a job coordinator managing subscriptions, errors, shutdowns, retries, and checkpoints, or a durable queue.

If the process restarts, the job must be able to resume from saved state.

## 21. Storing error reports without growing memory

For small imports, collecting outcomes can work:

~~~java
return importRows(rows)
        .collectList()
        .map(ImportReport::from);
~~~

However, `collectList()` retains every outcome on the heap. For large files, choose one of these patterns:

- Persist errors to an `import_error` table per record.
- Stream rejected rows out to a CSV error file.
- Track totals with counters for success/rejected/skipped.
- Keep a bounded sample of errors plus counts grouped by error code.
- Paginate error results when clients download reports.

Never retain full exception objects. Store row numbers, error codes, safe messages, and source keys sufficient for users to locate the row.

## 22. Bulk inserts and Statement.add()

Application-level batching does not automatically mean the driver executes a single bulk SQL insert.

Writes can use `repository.save`, `saveAll`, multi-row `INSERT` SQL, or R2DBC SPI `Statement.add()` batch binding. These differ in throughput and support for returning generated keys.

R2DBC SPI defines `Statement.add()` to append another parameter binding set on supporting drivers. Yet batching behavior, row counts, generated values, and parameter limits vary across drivers and databases.

Before adopting bulk statements, check:

- Does the driver support `Statement.add()` for that SQL statement?
- Must every parameter be rebound per row?
- Does the result emit a single count or one count per binding?
- Are generated IDs returned for every row?
- How does an error mid-batch affect other bindings?
- What are the database's batch size and parameter count limits?

Never assume `repository.saveAll(Publisher)` always compiles down to a single bulk SQL statement. It is a reactive API for saving multiple entities; actual execution depends on Spring Data version, dialect, and driver.

### 22.1. Bulk SQL and parameter limits

When constructing a multi-row `INSERT`, bind parameter count scales as:

\[
N_{\text{parameters}}
=
N_{\text{rows}}
\times
N_{\text{columns per row}}
\]

Databases cap parameter counts, statement lengths, and packet sizes. Size batches to stay safely inside real driver and database limits.

### 22.2. Separate batching APIs from transaction policies

A batched statement executes multiple bindings, but does not automatically make an entire import atomic. If atomicity is needed, still wrap it in a transaction. If a driver reports partial failures, determine which bindings were executed.

Test on the target driver before shipping bulk paths to production.

## 23. Validation, normalization, and staging tables

Imports often parse many formats: dates, money, country codes, enums, emails, or foreign keys.

Separate these stages:

- Parse: convert raw strings into structured types.
- Normalize: trim, normalize casing, formats, and timezones per rules.
- Validate: check required fields, ranges, formats, and domain rules.
- Resolve: look up database references if needed.
- Persist: write to target tables.

For huge files or complex rules, staging tables can help:

1. Load raw rows into staging tagged by job ID and row number.
2. Validate using SQL or services.
3. Copy failed rows into a rejection table.
4. Merge valid rows into target tables.
5. Mark the job completed.

Staging simplifies resumes and auditing, but requires managing cleanup, indexes, partitioning, and access control. Never retain raw sensitive data longer than necessary.

## 24. Processing order and consistency

When multiple batches run concurrently, commit order can diverge from source order. This matters when:

- One record depends on an earlier record.
- Two records update the same aggregate.
- A file carries a business sequence number.
- The import must apply the latest version.

Options:

- `concatMap` for strictly sequential processing.
- `flatMapSequential` for concurrent execution with source-ordered output.
- Partition by business key so records with the same key run sequentially while different keys run in parallel.
- Design upserts/version checks to resolve conflicts.
- Split dependencies into phases: import master data first, details second.

Preserving output order does not mean preserving commit order. `flatMapSequential` still runs inner publishers concurrently; it only reorders emissions downstream.

## 25. Controlling concurrency by tenant or partition

In multi-tenant imports, you can cap overall job concurrency while keeping per-tenant order:

~~~text
Record source
   |
   +--> tenant A --> sequential concatMap
   |
   +--> tenant B --> sequential concatMap
   |
   +--> tenant C --> sequential concatMap
             |
             v
     limit active tenants
~~~

Reactor offers `groupBy` to process each group, though `groupBy` can retain groups and buffer if downstream consumption stalls. Never use it over unbounded key cardinality without analyzing memory and group lifecycles.

Another approach partitions by source key or dispatches records into per-tenant queues. The goal is preventing concurrent updates to the same aggregate while exploiting parallelism across independent aggregates.

## 26. Observability for import jobs

Import jobs should emit metrics with bounded tag cardinality:

- `import.records.read`
- `import.records.succeeded`
- `import.records.rejected`
- `import.records.skipped`
- `import.records.retried`
- `import.batch.duration`
- `import.batch.size`
- `import.job.duration`
- `import.database.errors`

Suitable tags include `sourceType`, `outcome`, `errorCategory`, or `operation` with bounded value sets.

Never use `importJobId`, file name, customer ID, or row number as metric tags. Those belong in protected logs, traces, or job tables, not high-cardinality metric dimensions.

Also monitor the R2DBC pool:

- Acquired/allocated/idle connections.
- Pending acquires.
- Acquire timeouts.
- Query latency.
- Database error rates.

If raising concurrency fails to boost throughput, pool pending acquires and query durations will point straight to the bottleneck.

## 27. Testing the import pipeline

Unit tests verify parsers, validators, error classifiers, and outcome mapping. Integration tests must run against a real database to validate transactions, constraints, retries, and driver behavior.

### 27.1. Testing concurrency limits

You can use a synthetic publisher tracking active subscriptions:

~~~java
AtomicInteger active = new AtomicInteger();
AtomicInteger maximum = new AtomicInteger();

Flux<Integer> work =
        Flux.range(1, 100)
                .flatMap(value ->
                                Mono.defer(() -> {
                                    int current =
                                            active.incrementAndGet();

                                    maximum.accumulateAndGet(
                                            current,
                                            Math::max);

                                    return Mono.delay(
                                                    Duration.ofMillis(20))
                                            .thenReturn(value)
                                            .doFinally(signal ->
                                                    active.decrementAndGet());
                                }),
                        4,
                        1);
~~~

After verifying completion, assert `maximum` never exceeds 4. This tests operator concurrency; integration tests are still required for real pools and databases.

### 27.2. Testing per-record partial success

Prepare three rows:

- Row 1 is valid.
- Row 2 fails validation or violates a unique constraint.
- Row 3 is valid.

Expectations:

- Row 1 commits.
- Row 2 produces `REJECTED`.
- Row 3 still commits.
- The report contains all three row numbers.
- No database error is misclassified as a validation error.

With per-row transactions, these semantics are straightforward to verify.

### 27.3. Testing batch atomicity

Create a batch containing one row that violates a constraint. Verify:

- The batch transaction rolls back.
- No business rows from that batch commit.
- Other batches can still complete if policy permits.
- Outcomes report the whole batch rolled back rather than reporting success for earlier rows in that batch.

### 27.4. Testing retries and idempotency

Inject or trigger a controlled transient failure. Verify retries stay within the configured cap and each attempt runs in a fresh transaction.

Rerun the same job/source key after partial commits. Verify the unique import ledger or upsert prevents duplicates.

### 27.5. Testing cancellation and restart

Cancel the subscription mid-import and verify:

- Uncommitted transactions roll back when cancellation arrives in time.
- Already-committed transactions remain persisted.
- Job state records paused/canceled/failed as designed.
- Restarting resumes cleanly without duplicating rows.

Never assume cancellation leaves zero persisted rows.

### 27.6. Testing with a real database

Use Testcontainers or a dedicated test database matching your production engine and version. H2 does not replicate target database semantics for transaction aborts, savepoints, upserts, locking, or batch execution.

## 28. Complete example: batched/concurrent import with per-record transactions

This example illustrates streaming, row numbering, bounded concurrency, per-row transactions, transient retries, and continuing past classified data errors.

~~~java
@Service
public class CustomerImportService {

    private static final int ROW_CONCURRENCY = 8;

    private final CustomerRepository repository;
    private final TransactionalOperator tx;

    public CustomerImportService(
            CustomerRepository repository,
            TransactionalOperator tx) {
        this.repository = repository;
        this.tx = tx;
    }

    public Flux<ImportOutcome> importRows(Flux<ImportRow> source) {
        return source
                .index()
                .map(tuple ->
                        new IndexedImportRow(
                                tuple.getT1() + 1,
                                tuple.getT2()))
                .flatMap(
                        this::importOne,
                        ROW_CONCURRENCY,
                        1);
    }

    private Mono<ImportOutcome> importOne(
            IndexedImportRow item) {

        Mono<Customer> oneAttempt = Mono.defer(() -> {
            validate(item.row());

            return tx.transactional(
                    repository.save(toEntity(item.row())));
        });

        return oneAttempt
                .retryWhen(
                        Retry.backoff(
                                        3,
                                        Duration.ofMillis(100))
                                .maxBackoff(Duration.ofSeconds(2))
                                .jitter(0.5)
                                .filter(this::isTransientDatabaseFailure)
                                .onRetryExhaustedThrow(
                                        (spec, signal) ->
                                                signal.failure()))
                .map(saved ->
                        ImportOutcome.success(
                                item.rowNumber(),
                                saved.getId()))
                .onErrorResume(
                        InvalidImportRowException.class,
                        error -> Mono.just(
                                ImportOutcome.rejected(
                                        item.rowNumber(),
                                        error.code(),
                                        error.safeMessage())))
                .onErrorResume(
                        DataIntegrityViolationException.class,
                        error -> Mono.just(
                                ImportOutcome.rejected(
                                        item.rowNumber(),
                                        "DATA_CONFLICT",
                                        "Record conflicts with stored data")));
    }

    private void validate(ImportRow row) {
        if (row.email() == null || row.email().isBlank()) {
            throw new InvalidImportRowException(
                    "EMAIL_REQUIRED",
                    "Email is required");
        }
    }

    private Customer toEntity(ImportRow row) {
        return new Customer(row.email(), row.fullName());
    }

    private boolean isTransientDatabaseFailure(Throwable error) {
        for (Throwable cause = error;
                cause != null;
                cause = cause.getCause()) {

            if (cause instanceof R2dbcTransientException
                    || cause instanceof TransientDataAccessException) {
                return true;
            }
        }

        return false;
    }
}
~~~

This is an illustrative skeleton; production code should add an import ledger/idempotency check, job state tracking, metrics, and driver-accurate exception classification. `flatMap` can emit outcomes out of row-number order. If source order is required, weigh `flatMapSequential` and its buffering cost.

For very large files, never call `collectList()` on the entire outcome stream. Stream outcomes out or aggregate with bounded counters.

## 29. Common pitfalls in batch data imports

| Mistake | Consequence | Fix |
|---|---|---|
| Reading entire file into a List | Exhausts heap, fails on large files | Use a streaming parser and Flux |
| Unbounded buffering | Uncontrolled memory growth | Use buffer(size) or size-bounded bufferTimeout |
| flatMap without explicit concurrency | Can launch too many simultaneous operations | Specify concurrency and prefetch explicitly |
| Setting concurrency equal to pool max size | Starves API traffic of connections | Reserve capacity and sum across replicas |
| Raising batch size and concurrency together | Cannot tell which caused overload | Tune one parameter at a time and measure |
| Using flatMap while assuming ordering | Outcomes or commits arrive out of order | Use concatMap or flatMapSequential when needed |
| Swallowing errors inside an aborted transaction | Subsequent statements still fail | Roll back the batch or use per-row transactions |
| Wrapping an entire file in one long transaction | Holds connections/locks too long, huge rollbacks | Use per-batch or per-row transactions |
| Retrying every exception | Repeats unfixable data and SQL errors | Retry only transient failures, with bounds |
| Retrying a statement inside an aborted transaction | Transaction stays broken | Retry the entire transaction unit |
| No idempotency | Retries or restarts create duplicates | Enforce a unique import key or ledger |
| Advancing checkpoints before data commits | Resumes can skip unpersisted rows | Update checkpoints in the same transaction |
| Checkpointing after commit without idempotency | Restarts can reprocess rows | Reconcile using source keys |
| Calling subscribe() in controller for background work | Loses error handling and lifecycle control | Use a job coordinator or durable queue |
| Collecting all errors in memory | Exhausts heap on large files | Stream error reports or persist to DB |
| Using onErrorContinue | Unpredictable semantics, no transaction recovery guarantee | Use onErrorResume at record/batch boundaries |
| Assuming saveAll is always bulk SQL | Throughput and generated keys behave unexpectedly | Check implementation/driver and benchmark |
| Not testing against the production database engine | Missed transaction/batch/upsert differences | Run integration tests on the target engine |
| Ignoring pool pending acquires | Import stalls with no visible root cause | Monitor pool, query duration, and retry metrics |

## 30. Practical implementation sequence

A controlled implementation sequence:

1. Identify the data source and streaming reader.
2. Assign stable source keys or row numbers.
3. Define validation, normalization, and error codes.
4. Pick batch size based on memory, transaction, and database limits.
5. Choose per-row or per-batch transactions based on partial-success rules.
6. Size concurrency to connection pool budgets and database capacity.
7. Cap prefetch and eliminate unbounded buffers.
8. Define fail-fast, reject-row, skip, upsert, and retry policies.
9. Retry only transient failures, always retrying the entire transaction unit.
10. Design idempotency keys and checkpoints for safe resumption.
11. Stream outcomes instead of collecting the entire file in memory.
12. Define cancellation handling and job lifecycle management.
13. Add metrics for throughput, errors, retries, batch duration, and pools.
14. Test concurrency, rollbacks, partial success, retries, resumption, and cancellation.
15. Load test against production-like database, driver, and versions.

## 31. Key takeaways

- Batch size is records per group; concurrency is groups or records processed simultaneously.
- Use `Flux` streaming and bounded buffers to avoid loading whole files onto the heap.
- `flatMap` bounds concurrency; `concatMap` runs sequentially; `flatMapSequential` preserves output order at the cost of buffering.
- Size concurrency around connection pools, API traffic, replica counts, and database capacity.
- Pick whole-file, per-batch, or per-record transactions according to atomicity and partial-success requirements.
- In batch transactions, one database error can abort the transaction; never keep writing merely by swallowing the error signal.
- Per-row transactions suit imports that must continue after per-row constraint failures.
- Classify validation/business errors, conflicts, transient infrastructure errors, and fatal configuration errors separately.
- Convert only defined data errors into outcomes; let fatal/infrastructure failures propagate to the job coordinator.
- Bound retries with backoff and jitter; place retries outside the transaction so each attempt uses a fresh transaction.
- Safe retries and restarts require idempotency keys or a unique import ledger.
- Keep checkpoints consistent with data commits; never assume cancellation rolls back already-committed transactions.
- R2DBC `Statement.add()` and bulk inserts depend on driver and database; `saveAll` is not automatically bulk SQL.
- Avoid `onErrorContinue` as a general partial-success mechanism.
- Never call `subscribe()` ad-hoc for background jobs; manage lifecycles via a job coordinator or durable queue.
- For large imports, stream outcomes and errors rather than calling `collectList()` over the entire job.
- Test concurrency, transaction aborts, retries, duplicates, restarts, and cancellation against a real database.
