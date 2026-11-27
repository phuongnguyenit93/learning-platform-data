# Choosing Transactions for the Whole Dataset or Per Group

When writing multiple records with Spring Data R2DBC, you must decide on the transaction scope: whether the entire import is one atomic unit, or whether each group of records commits independently. This choice affects consistency, connection hold times, locking, failure recovery, and how an interrupted import resumes.

A single transaction for the whole dataset ensures all changes in the import either commit together or roll back together. Per-group (per-batch) transactions shorten each transaction and preserve committed groups when a later group fails, though the overall dataset can end up partially complete. Neither option is universally right; transaction scope must reflect business rules.

## 1. Distinguishing write batching from transaction scope

Batching and transactions are two separate concepts:

- **Batching** defines how many records are grouped together to process in one unit. For example, `buffer(500)` creates chunks of up to 500 elements.
- **Transactions** define commit/rollback boundaries. Multiple batches can sit inside one transaction, or each batch can run in its own transaction.

For instance, a 10,000-row file can be split into 20 chunks of 500 rows each. There are two ways to structure this:

1. Open one transaction outside the entire pipeline, process all 20 chunks sequentially, and then commit. If chunk 20 fails, changes from all 20 chunks roll back.
2. Open a separate transaction for each chunk. If chunks 1 through 10 commit and chunk 11 fails, data from the first 10 chunks stays in the database.

`buffer(500)` only controls how many elements are grouped in memory. It neither creates a transaction nor commits data on its own. Transaction scope is determined by where `TransactionalOperator` or `@Transactional` boundaries are placed.

## 2. When to use one transaction for the whole dataset?

Choose a whole-dataset transaction when business rules require all records to appear together or none at all. Examples:

- Loading a small reference dataset where dependent tables must stay synchronized simultaneously.
- Updating a set of records that together form a single business state.
- Writing multiple rows whose invariants hold only when the entire change set commits together.
- Replacing a data snapshot where readers must never observe a partially updated new state.

The main advantage is atomicity: when any operation in the transaction fails, changes already made within that transaction can roll back. Other readers observe data under database isolation rules rather than seeing individual batches commit one by one.

The trade-off is that the transaction may remain open throughout reading, transforming, and writing the entire dataset. Connections stay held longer; locks and older row versions remain active longer; transaction logs/WAL or undo space can grow; rolling back after processing many rows can be slow. If the pipeline reads from files, networks, or external services, waiting on the data source can further prolong the transaction.

For very large datasets, whole-dataset transactions can strain the database and degrade sibling workloads. Do not choose this solely out of a vague sense of "being safer"; weigh operational cost against genuine atomicity requirements.

## 3. When to commit per group?

Per-batch transactions fit when each chunk can be treated as an independent unit of completion. Examples:

- Large imports that can resume from the last committed chunk.
- Catalog or history syncs where records do not need to appear at the exact same instant.
- Background jobs that record progress after each chunk.
- Deleting or updating old records in chunks to reduce lock duration and work per transaction.

Each batch commits independently, releasing connections and transactions sooner. If a later batch fails, previously committed batches are not rolled back. You can record checkpoints, track progress, or retry just the failing batch.

The downside is that partial completion becomes part of the design. If users or other services read data mid-import, they may observe part of the new data. If rows across batches have cross-batch business constraints, per-batch commits can leave an invalid state when interrupted midway.

To use per-batch transactions safely, define how to detect incomplete runs, how to resume, how to prevent duplicates on retry, and how to prevent users from consuming unpublished data.

## 4. Comparing the two strategies

| Criterion | One transaction for the whole dataset | One transaction per batch |
|---|---|---|
| Atomicity | Entire write commits or rolls back together | Only each batch is atomic |
| When the last batch fails | Rolls back all changes from the import | Keeps committed batches; failing batch rolls back alone |
| Transaction duration | Can be very long | Shorter, bounded by single-batch processing time |
| Connections | May hold a connection for the entire import | Releases connection after each batch |
| Locks and transaction logs | Can grow with the entire dataset | Usually bounded per batch |
| Resumability | Typically must rerun from scratch or use staging | Can resume from committed checkpoints |
| Partial data state | Uncommitted changes hidden under normal isolation | Committed batches may be visible before import finishes |
| Best suited for | Small/medium change sets requiring all-or-nothing | Large imports, background processing, independent chunks |

The deciding factor is not raw record count alone, but business coupling between records, database load, and how the system handles interrupted state.

## 5. Using Reactive TransactionalOperator

In reactive applications, `TransactionalOperator` lets you define explicit transaction scopes around a `Mono` or `Flux`. Spring requires a `ReactiveTransactionManager` matching your `ConnectionFactory`.

Example manual configuration of the operator:

```java
@Bean
TransactionalOperator transactionalOperator(
        ReactiveTransactionManager transactionManager) {
    return TransactionalOperator.create(transactionManager);
}
```

If Spring Boot already provides a transaction manager and no customization is needed, inject the existing bean rather than creating a duplicate transaction manager. Bean names and configuration must fit single- or multi-`ConnectionFactory` setups.

`TransactionalOperator.transactional(publisher)` starts a transaction when the reactive chain is subscribed to, propagates the transaction context through the pipeline, and commits on successful completion or rolls back on error/cancellation per the transaction manager and driver's semantics.

## 6. One transaction wrapping the whole dataset

Suppose the input source is `Flux<ImportRow>`, with each row written via a repository. You can chunk for memory control while placing the transaction outside the entire pipeline:

```java
public Mono<Void> importAtomically(Flux<ImportRow> source) {
    return transactionalOperator.transactional(
        source
            .buffer(500)
            .concatMap(batch ->
                Flux.fromIterable(batch)
                    .concatMap(importRepository::save)
            )
            .then()
    );
}
```

Here:

- `buffer(500)` splits the source into groups of up to 500 rows.
- `concatMap` processes each group and each row sequentially, keeping order controlled and avoiding excessive concurrent writes.
- `transactionalOperator.transactional(...)` wraps the whole pipeline, so all `save` calls in the chain join the same reactive transaction when the repository uses the managed connection infrastructure.
- `.then()` converts the output to `Mono<Void>` because the service only cares about completion or error.

Even though data is processed in groups of 500, all groups sit in one transaction. If any `save` signals an error, the publisher errors and the transaction rolls back. `buffer` does not commit after each group.

Never call `subscribe()` inside the service to fire off the pipeline manually. Return the publisher so the framework or caller subscribes; subscribing internally can cause the transaction to finish before writes complete or prevent errors from reaching the caller.

## 7. One transaction per batch

If each group is allowed to commit independently, place `TransactionalOperator` inside `concatMap`:

```java
public Mono<Void> importPerBatch(Flux<ImportRow> source) {
    return source
        .buffer(500)
        .concatMap(batch -> transactionalOperator.transactional(
            Flux.fromIterable(batch)
                .concatMap(importRepository::save)
                .then()
        ))
        .then();
}
```

In this structure, each `concatMap` batch subscribes inside its own transaction. A batch is complete only when all save operations in that batch finish and its transaction commits. `concatMap` waits for the current batch to finish before starting the next.

If batch 8 fails, batch 8's transaction rolls back. Batches 1 through 7 remain committed. By default, the outer publisher emits an error and stops; subsequent batches do not run automatically. The service must decide whether to fail fast, record the failure and continue, or route failed batches to a separate queue.

To track progress, you can persist an import job record or checkpoint in the same transaction as the batch's data:

```java
private Mono<Void> persistBatch(UUID jobId, int batchNumber,
                                List<ImportRow> batch) {
    return transactionalOperator.transactional(
        Flux.fromIterable(batch)
            .concatMap(importRepository::save)
            .then(importJobRepository.markBatchCompleted(jobId, batchNumber))
            .then()
    );
}
```

The checkpoint must commit together with the batch data. If the checkpoint is written in a separate transaction, data could commit without updating the checkpoint, or vice versa. On retry, design writes to detect and reprocess safely.

## 8. Using @Transactional on reactive methods

Spring also supports declaring transactions with `@Transactional` on methods returning reactive publishers. The selected transaction manager must be the reactive transaction manager corresponding to R2DBC.

```java
@Transactional
public Mono<Void> importAtomically(Flux<ImportRow> source) {
    return source
        .buffer(500)
        .concatMap(batch ->
            Flux.fromIterable(batch)
                .concatMap(importRepository::save)
        )
        .then();
}
```

For reactive methods, Spring attaches the transaction to the reactive context of the returned publisher. Never make the method `void` and call `subscribe()` internally; doing so prevents the transaction proxy from managing the publisher lifecycle as expected.

If per-batch transactions are needed, delegate to a separate Spring bean with a transactional per-batch method, or wrap each batch publisher with `TransactionalOperator`. Watch out for Spring proxy behavior: self-invocation (one method directly calling another method on the same object) generally bypasses the proxy and may not activate the annotation as expected.

## 9. Choosing concurrency: concatMap or flatMap?

In reactive flows, `concatMap` runs sequentially and moves to the next item only after the inner publisher completes. `flatMap` can run multiple inner publishers concurrently.

With a single transaction wrapping the whole import, start with `concatMap` so writes run sequentially on the transaction context. Never assume every driver or connection supports multiple concurrent statements on the same connection. If parallel optimization is needed, verify driver, transaction manager, and database capabilities, and measure pool and lock effects.

With per-batch transactions, you can use `flatMap(batch -> transactionalOperator.transactional(...), concurrency)` when batches are independent and the database has capacity for concurrent work. As concurrency rises, each batch may require its own connection. Match concurrency to pool size, database connection limits, and load from other services.

Example running up to three batches concurrently:

```java
return source
    .buffer(500)
    .flatMap(batch -> transactionalOperator.transactional(
        Flux.fromIterable(batch)
            .concatMap(importRepository::save)
            .then()
    ), 3)
    .then();
```

Commit order may differ from input batch order when running concurrently. If ordering is a business requirement, use `concatMap` or design explicit sequence/checkpointing. Do not raise concurrency solely to speed up an import if the database is already saturated or pool pending acquires are climbing.

## 10. Batch size and transaction duration

Batch size balances overhead against resource consumption:

- **Too-small batches:** increase transaction open/commit count, round-trips, and progress-tracking overhead.
- **Too-large batches:** increase temporary memory, per-transaction duration, lock scope, and rollback cost.
- **Well-sized batches:** bound row counts and processing times within what the database comfortably handles without spawning excessive tiny transactions.

There is no default number right for every database. Start with a moderate size and measure per-batch duration, active connections, pending acquires, lock waits, transaction logs, and error rates. Then adjust for row width, indexes, constraints, network latency, and concurrent load.

`buffer(500)` can also emit a final batch smaller than 500 when the source completes. For unbounded sources, add time-based flushing or another boundary; count-only `buffer(size)` can leave a partial batch waiting indefinitely. For finite file imports, the trailing batch emits when the publisher completes.

## 11. Mid-flight errors and continuation policies

With a whole-import transaction, an error at any step usually rolls back the entire publisher. Recovery means fixing the root cause and rerunning from scratch, or using staging/snapshots to swap data in a controlled manner.

With per-batch transactions, an error in one batch rolls back only that batch; prior batches remain intact. Choose one of the following policies:

1. **Fail-fast:** stop immediately when a batch fails, mark the job failed, and require operational intervention.
2. **Bounded retries:** retry the failed batch if the error is transient and the operation is idempotent.
3. **Record failed batch and continue:** appropriate only when batches are independent and business rules permit partial results; must produce a report of failed rows.
4. **Send failed records to a dead-letter/reject store:** persist payload and reason for later handling rather than silently dropping them.

Avoid blanket `onErrorResume(error -> Mono.empty())` around the entire pipeline. It can mask database failures as false successes and lose track of unwritten batches.

## 12. Retries and idempotency

Retries can resend the same batch after a network glitch or timeout. Applications must handle uncertainty about whether the server committed. If the first attempt committed while the client lost the response, retrying a plain insert can create duplicates or fail with unique constraint errors.

Techniques supporting safe retries include:

- Using business keys or stable source IDs to identify records.
- Adding unique constraints so the database blocks duplicate inserts.
- Using upserts or insert/update operations with database-clear semantics.
- Writing checkpoints in the same transaction as batch data.
- Retrying only errors classified as transient; never retrying validation or constraint errors indefinitely.

Example retrying around each batch's transaction:

```java
return transactionalOperator.transactional(saveBatch(batch))
    .retryWhen(Retry.backoff(3, Duration.ofMillis(200))
        .filter(this::isTransientDatabaseFailure));
```

On retry, the publisher is re-subscribed; a fresh transaction must be created for the new attempt. Placing retry outside the transaction publisher ensures each attempt runs through a new transaction lifecycle. Verify error classification and idempotency before enabling retries.

## 13. Constraints spanning multiple batches

When data has cross-batch invariants, per-batch transactions may be insufficient. For instance, importing accounts and balances may require total balances to reconcile against total transactions once all batches finish. Individual batches might each look valid while an incomplete dataset remains inconsistent.

Strategies:

- **Staging tables:** write batches into staging tables, validate the full dataset, and promote to main tables in an appropriate commit step.
- **Import job status:** tag data with `job_id` and expose it only once the job transitions to `COMPLETED`.
- **Snapshots/versions:** write new versioned records, then flip the active version pointer once all data is ready.
- **Pre-publication validation:** verify counts, checksums, duplicate keys, aggregates, and referential integrity before publishing data.

These patterns let you write in batches to avoid long transactions while still controlling when data becomes visible as a complete set. The final state flip typically requires only a short, conditional transaction.

## 14. Impact of transactions on data sources and external side effects

An R2DBC transaction manages only the participating database resources. It does not roll back file reads, HTTP calls, sent emails, or messages published to external brokers.

Avoid holding transactions open while waiting for external services to respond. Read and validate data first, then open transactions strictly for the write phase. For large batched imports, reading a chunk from the source and opening a transaction for that chunk bounds connection hold time.

If events must emit after each batch commits, do not publish before commit succeeds. To ensure events are not lost between commit and publish, use a transactional outbox: write domain data and an outbox row in the same transaction, then have a separate publisher dispatch events and mark them processed.

## 15. Example service with per-batch checkpoints

A service can process batches sequentially and record progress in the same transaction:

```java
public Mono<Void> importWithCheckpoint(
        UUID jobId, Flux<ImportRow> source) {

    AtomicInteger batchNumber = new AtomicInteger(0);

    return source
        .buffer(500)
        .concatMap(batch -> {
            int currentBatch = batchNumber.incrementAndGet();

            return transactionalOperator.transactional(
                Flux.fromIterable(batch)
                    .concatMap(importRepository::save)
                    .then(importJobRepository.markBatchCompleted(
                        jobId, currentBatch, batch.size()))
                    .then()
            );
        })
        .then();
}
```

This illustrates updating a checkpoint inside the same transaction. In production applications, batch numbers should be derived deterministically from the source or persisted in the database so runs can resume after restarts. An in-memory `AtomicInteger` counts only within one process run; it is not a durable checkpoint. When restarting a job, read completed batches from the database and identify the next batch using a stable key.

If multiple workers can process the same job, add a claim/lease mechanism so only one worker handles a batch at a time, or enforce uniqueness/optimistic locking on checkpoints. Otherwise two workers could write the same batch simultaneously.

## 16. Monitoring and operations

To pick the right transaction scope, observe both application and database metrics:

| Metric | What to watch |
|---|---|
| Transaction duration | Unusually long transactions hold connections and locks too long. |
| Per-batch duration | Guides batch sizing and flags abnormal data batches. |
| Committed/rolled-back rows | Tracks actual progress and failure levels. |
| Active/pending connections | Detects pool exhaustion when batches run in parallel. |
| Lock waits/deadlocks | Reveals batches contending on the same rows or indexes. |
| Transaction log/WAL/undo | Highlights pressure from large transactions or heavy write rates. |
| Checkpoints and job state | Shows where to resume after a restart. |
| Retry count and rejected rows | Tracks transient faults and invalid data. |

When an import is slow, do not reflexively increase batch size or concurrency. Check query plans, indexes, constraints, row width, locks, and connection wait times first. Larger transactions can actually lower throughput if the database has to retain extensive resources for long periods.

## 17. Process for choosing transaction scope

Before implementing multi-record writes, answer:

1. Must all records appear together or disappear together?
2. Can readers tolerate seeing partially committed data?
3. If batch N fails, can prior batches stay committed and processing resume?
4. Are there cross-batch business invariants to check before publishing?
5. Would a whole-dataset transaction hold connections/locks too long or bloat logs?
6. Are batches idempotent with durable checkpoints for safe retries?
7. Does batch concurrency fit the connection pool and database capacity?
8. Do external side effects need an outbox or post-commit dispatch?

Choose a whole-dataset transaction when atomicity applies to the entire dataset and long-transaction costs are acceptable. Choose per-batch transactions when each group can commit independently, progress is tracked, and partial state can be handled cleanly. In both cases, use the reactive transaction manager matching your `ConnectionFactory`, keep database operations inside the reactive chain, and measure real workloads to tune batch size and concurrency.
