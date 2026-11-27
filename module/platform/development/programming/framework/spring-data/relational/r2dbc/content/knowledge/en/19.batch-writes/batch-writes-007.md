# Retrieving Generated Identifiers and Handling Per-Group Errors

When writing multiple records to a database with Spring Data R2DBC, an application often needs to retrieve database-generated identifiers and know which data groups succeeded and which failed. These are two related yet distinct requirements: generated IDs link newly created rows back to input records, while an error-handling strategy defines rollback scope, how failing records are isolated, and whether remaining groups can continue.

Do not assume all multi-record write approaches behave the same way. Repository `saveAll`, a multi-row SQL insert, and a batch `Statement` using `add()` are distinct execution strategies. Support for returning generated values and how drivers report errors also depend on the database engine, R2DBC driver, and version in use.

A sound design clearly defines the unit of success: per record, per batch, or the entire job. From that choice follow the ID retrieval mechanism, transaction boundaries, retry strategy, and result structure so callers know precisely what happened.

## 1. Three common ways to write multiple records

In Spring Data R2DBC, multiple entities can be written in several ways:

| Write approach | Mechanism | Key considerations |
|---|---|---|
| `repository.saveAll(...)` | Passes a publisher or iterable of entities through the Repository | Convenient API; do not assume it always emits a driver-level batch SQL statement |
| Multiple `save`/`insert` calls | Each entity is saved via a separate reactive operation | Easy to identify which entity failed; can incur many round-trips if not grouped thoughtfully |
| Single `INSERT ... VALUES (...), (...)` | One statement containing multiple value tuples | Can return multiple IDs via `RETURNING` on supported databases; constraint errors usually fail the whole statement |
| R2DBC SPI `Statement.add()` | One statement executed with multiple binding sets | Driver-level batching; generated values support and error behavior depend on the driver |

`saveAll` is a repository-level API, not a promise of a single network round-trip or one batch statement. Exact execution details depend on the Spring Data release train. When batch performance matters, inspect actual SQL/driver behavior or use a driver-appropriate batching mechanism.

## 2. Identifying which identifiers need to be returned

Before writing a batch, distinguish between types of identifiers:

- **Generated ID:** primary key assigned by the database, such as an identity or sequence.
- **Business key:** domain code such as `order_no`, SKU, or employee ID.
- **Correlation key:** key used to match returned results back to the exact input element in the batch.
- **Idempotency key:** key identifying whether a write request was already processed, preventing duplicate records on retry.

These keys may map to the same column if the domain model fits, though they typically serve different roles. Generated IDs may be unknown before inserting. Correlation keys must exist before sending the batch so the application can match results reliably.

Input example:

```java
public record PersonInput(
    String requestKey,
    String name,
    String email
) {}
```

Post-write result:

```java
public record PersonCreated(
    String requestKey,
    Long id
) {}
```

`requestKey` can be an application-generated UUID per item. When the database returns both `id` and `request_key`, the application matches the new ID to the exact input without guessing based on return order.

## 3. Why you should not pair IDs by list position

An error-prone approach is assuming IDs come back in exact input order and zipping two lists by index:

```java
// Do not assume this unless the driver/database guarantees ordering.
for (int i = 0; i < inputs.size(); i++) {
    result.put(inputs.get(i), generatedIds.get(i));
}
```

The order of rows returned by a database is not always guaranteed solely by insert order. With batch statements, how a driver represents each `Result` can also vary. One driver may emit results per execution, while another has limits on generated values or lacks batch key return support altogether.

A safer solution is storing a correlation key in the written data and having the database return that key alongside the generated ID. With PostgreSQL, you can use `RETURNING`:

```sql
INSERT INTO person (request_key, name, email)
VALUES
    (:key0, :name0, :email0),
    (:key1, :name1, :email1),
    (:key2, :name2, :email2)
RETURNING id, request_key;
```

Then map by `request_key`:

```java
public record PersonCreated(String requestKey, Long id) {}

public Flux<PersonCreated> insertPeople(List<PersonInput> inputs) {
    return databaseClient.sql("""
            INSERT INTO person (request_key, name, email)
            VALUES
                (:key0, :name0, :email0),
                (:key1, :name1, :email1),
                (:key2, :name2, :email2)
            RETURNING id, request_key
            """)
        .bind("key0", inputs.get(0).requestKey())
        .bind("name0", inputs.get(0).name())
        .bind("email0", inputs.get(0).email())
        .bind("key1", inputs.get(1).requestKey())
        .bind("name1", inputs.get(1).name())
        .bind("email1", inputs.get(1).email())
        .bind("key2", inputs.get(2).requestKey())
        .bind("name2", inputs.get(2).name())
        .bind("email2", inputs.get(2).email())
        .map((row, metadata) -> new PersonCreated(
            row.get("request_key", String.class),
            row.get("id", Long.class)
        ))
        .all();
}
```

This SQL example demonstrates a fixed three-item batch using PostgreSQL `RETURNING` syntax. When item count varies, the data-access layer can generate the corresponding number of placeholder tuples from the item count, with placeholder names generated in code by index; all values must still be bound. Never concatenate user data directly into SQL.

If storing a correlation key in the table is not possible, consider a staging table or an existing unique business key. Pair by order only when database/driver documentation explicitly guarantees that ordering and integration tests confirm it on your deployed version.

## 4. Receiving IDs when using ReactiveCrudRepository.saveAll

For standard CRUD, `ReactiveCrudRepository` offers `saveAll` accepting an `Iterable` or `Publisher` depending on the overload. The resulting publisher emits saved entities; when IDs are database-generated and driver-supported, each returned entity can carry its new ID.

```java
@Table("person")
public record Person(
    @Id Long id,
    String requestKey,
    String name,
    String email
) {}

public interface PersonRepository
        extends ReactiveCrudRepository<Person, Long> {
}
```

```java
public Flux<PersonCreated> createAll(List<PersonInput> inputs) {
    List<Person> entities = inputs.stream()
        .map(input -> new Person(
            null,
            input.requestKey(),
            input.name(),
            input.email()
        ))
        .toList();

    return personRepository.saveAll(entities)
        .map(saved -> new PersonCreated(saved.requestKey(), saved.id()));
}
```

With this approach, each returned entity carries both the correlation key and the ID. There is no need to query `MAX(id)` or compute next IDs manually. However, check how `saveAll` executes in your Spring Data version; this API does not guarantee a single multi-row SQL insert or a single driver batch.

If per-item error capture is required, `saveAll` as a publisher can signal an error and terminate the chain when one operation fails. Do not assume the publisher automatically skips failing rows and continues. Choose transaction boundaries and error handling suited to per-record or per-group needs.

## 5. Writing per entity and preserving success/failure outcomes

If error isolation at the record level is required, process each entity with `concatMap` and map outcomes into an outcome type:

```java
public sealed interface RowOutcome {
    record Success(String requestKey, Long generatedId) implements RowOutcome {}
    record Failure(String requestKey, String errorCode) implements RowOutcome {}
}
```

```java
public Flux<RowOutcome> createIndividually(List<PersonInput> inputs) {
    return Flux.fromIterable(inputs)
        .concatMap(input -> {
            Person person = new Person(
                null,
                input.requestKey(),
                input.name(),
                input.email()
            );

            return personRepository.save(person)
                .map(saved -> (RowOutcome) new RowOutcome.Success(
                    input.requestKey(), saved.id()))
                .onErrorResume(error -> Mono.just(
                    new RowOutcome.Failure(
                        input.requestKey(),
                        classify(error)
                    )
                ));
        });
}
```

`concatMap` processes items one by one, bounding concurrency and keeping outcome emission in input order. This makes it straightforward to know which item succeeded or failed, though it typically issues more database operations than a true batch.

If each item needs its own transaction, wrap each item's operation in `TransactionalOperator` and catch errors outside that transaction. When an insert fails, that item's transaction rolls back before the sequence proceeds to the next item.

```java
public Flux<RowOutcome> createIndividually(List<PersonInput> inputs) {
    return Flux.fromIterable(inputs)
        .concatMap(input -> {
            Mono<Person> insert = personRepository.save(new Person(
                null,
                input.requestKey(),
                input.name(),
                input.email()
            ));

            return transactionalOperator.transactional(insert)
                .map(saved -> (RowOutcome) new RowOutcome.Success(
                    input.requestKey(), saved.id()))
                .onErrorResume(error -> Mono.just(
                    new RowOutcome.Failure(input.requestKey(), classify(error))
                ));
        });
}
```

Never place `onErrorResume` inside a shared transaction expecting the database to continue after a constraint violation. Some databases, such as PostgreSQL, mark the transaction aborted after a failed statement; subsequent statements fail until rollback. Catching errors outside the transaction boundary ensures rollback completes before moving to the next item.

## 6. Splitting data into bounded-size batches

Never pass an unbounded list into a single statement or transaction. Splitting inputs into small groups helps control:

- Bind parameter counts and database/driver limits.
- Network packet payload sizes.
- Memory used to hold inputs and generated ID results.
- Connection and lock hold durations.
- Rollback scope when a group fails.

Example splitting into groups of 200 items:

```java
Flux<List<PersonInput>> batches = Flux.fromIterable(inputs)
    .buffer(200);
```

The size 200 is only an example. The right number depends on columns per row, parameter limits, latency, database load, and driver. Measure with realistic data.

To process each batch sequentially:

```java
return Flux.fromIterable(inputs)
    .buffer(200)
    .concatMap(batch -> insertBatch(batch));
```

`concatMap` starts the next batch only after the current batch finishes. If the database has capacity and business logic permits, `flatMap` with bounded concurrency can be used, taking connections, locks, and result ordering into account.

## 7. Receiving generated values with R2DBC SPI Statement.add

The R2DBC SPI allows creating a `Statement`, binding multiple value sets, and calling `add()` to enqueue binding sets into the batch. `Statement.returnGeneratedValues(...)` can ask the driver to return database-generated values.

Skeleton example operating directly on the SPI:

```java
public Mono<List<Long>> insertBatchIds(List<PersonInput> batch) {
    if (batch.isEmpty()) {
        return Mono.just(List.of());
    }

    return Mono.usingWhen(
        Mono.from(connectionFactory.create()),
        connection -> {
            Statement statement = connection.createStatement("""
                INSERT INTO person (request_key, name, email)
                VALUES ($1, $2, $3)
                """);

            statement.returnGeneratedValues("id");

            for (int i = 0; i < batch.size(); i++) {
                PersonInput item = batch.get(i);
                statement.bind(0, item.requestKey())
                    .bind(1, item.name())
                    .bind(2, item.email());

                if (i < batch.size() - 1) {
                    statement.add();
                }
            }

            return Flux.from(statement.execute())
                .concatMap(result -> Flux.from(
                    result.map((row, metadata) -> row.get("id", Long.class))
                ))
                .collectList();
        },
        connection -> Mono.from(connection.close()),
        (connection, error) -> Mono.from(connection.close()),
        connection -> Mono.from(connection.close())
    );
}
```

This example shows SPI-level batch structure: each binding set is added via `add()` before binding the next set; the last set remains the active binding set when `execute()` is called. Bind indices in SPI start at 0. The snippet requests the `id` column back, so the result is a list of IDs.

**Important:** generated values support for batches, how many `Result` items emit, how returned rows are grouped, and whether IDs can be mapped accurately back to inputs depend on the driver/database. Do not assume this snippet runs identically across all R2DBC drivers. Check your driver's documentation and run integration tests on the specific version. For a more portable way to pair IDs with inputs, return a correlation key alongside the ID using database-supported `RETURNING`/`OUTPUT` SQL.

This example creates a connection directly from `ConnectionFactory` and closes it afterward. If participating in a Spring-managed reactive transaction is required, do not acquire an independent connection like this and expect it to join the transaction context automatically. Use Spring-managed connection retrieval or manage SPI transactions directly on the connection; for typical operations, `DatabaseClient` and `TransactionalOperator` integrate much more easily.

## 8. A multi-row INSERT statement with RETURNING

Another option is building an insert statement with multiple value sets. With PostgreSQL:

```sql
INSERT INTO person (request_key, name, email)
VALUES
    ('req-a', 'An', 'an@example.test'),
    ('req-b', 'Binh', 'binh@example.test')
RETURNING id, request_key;
```

In an application, values must be bound rather than written as input literals:

```java
public Flux<PersonCreated> insertTwo(
        PersonInput first,
        PersonInput second) {

    return databaseClient.sql("""
            INSERT INTO person (request_key, name, email)
            VALUES (:key0, :name0, :email0),
                   (:key1, :name1, :email1)
            RETURNING id, request_key
            """)
        .bind("key0", first.requestKey())
        .bind("name0", first.name())
        .bind("email0", first.email())
        .bind("key1", second.requestKey())
        .bind("name1", second.name())
        .bind("email1", second.email())
        .map((row, metadata) -> new PersonCreated(
            row.get("request_key", String.class),
            row.get("id", Long.class)
        ))
        .all();
}
```

Results are matched by `request_key`, not by return order. Because this is a single SQL statement, on PostgreSQL a constraint violation in one row usually fails the entire statement; there is no partial list of successfully inserted rows from that same statement.

For other databases, retrieving IDs may use `OUTPUT`, `RETURNING`, or another mechanism. Separate SQL per dialect or use SPI generated values when supported by the driver.

## 9. Distinguishing errors at record, batch, and job levels

Before implementing error handling, decide what scope the system considers the unit of success:

| Scope | Meaning | Behavior when one element fails |
|---|---|---|
| Per record | Each input is independent | Roll back only that record and continue others if transactions are separate |
| Per batch | Inputs in one group form a unit | Roll back the entire batch if one operation in the group fails |
| Whole job | All batches must succeed together | A single error can roll back the entire job if all operations share one transaction |

No single choice fits every scenario. Independent data imports often record per-record or per-batch failures and continue. Money transfers or writing a single aggregate typically require all-or-nothing. Large migrations may need large transactions or segmented checkpoints depending on scale.

## 10. Classifying errors before deciding on retries

Not every error should be retried. Errors can be grouped as follows:

| Error category | Examples | Handling approach |
|---|---|---|
| Invalid data | Missing required field, bad format, out-of-range value | Validate before hitting database; flag invalid input |
| Constraint violation | Unique, foreign key, NOT NULL, CHECK | Do not retry as-is; fix data or record conflict |
| Transient error | Deadlock, serialization failure, brief connection drop | May retry with bounds if operation is safe and transaction rolled back |
| Overload or timeout | Pool exhausted, overloaded database, query timeout | Apply backoff, cap concurrency, and inspect load before retrying |
| Config/programming bug | Invalid SQL, missing column, wrong bind type, missing permissions | Fix code/config; retries will not help |
| Ambiguous outcome | Connection dropped after server may have committed | Look up by idempotency key before resending |

With R2DBC, errors may surface as driver exceptions or Spring-translated exceptions. Depending on the driver, inspect SQL state or error codes to classify. Avoid relying solely on error message text since wording can change across drivers and versions.

Common PostgreSQL SQLSTATE codes:

| SQLSTATE | Meaning |
|---|---|
| `23505` | Unique violation |
| `23503` | Foreign key violation |
| `23502` | Not-null violation |
| `23514` | Check constraint violation |
| `40001` | Serialization failure |
| `40P01` | Deadlock detected |

These codes are PostgreSQL examples; other database engines have their own codes and classifications. In Spring, constraint errors typically translate into the `DataIntegrityViolationException` hierarchy, while transient errors may translate into `TransientDataAccessException`, though you should verify the exact exceptions raised by your driver and translator.

## 11. Per-batch transactions

A common strategy is giving each batch its own transaction. If a batch fails, that batch rolls back; prior committed batches stay and subsequent batches can still be processed.

```java
public record BatchOutcome(
    long batchNumber,
    int attempted,
    List<PersonCreated> inserted,
    String errorCode
) {}
```

```java
public Flux<BatchOutcome> importInBatches(
        Flux<PersonInput> source,
        int batchSize) {

    return source
        .buffer(batchSize)
        .index()
        .concatMap(indexed -> {
            long batchNumber = indexed.getT1();
            List<PersonInput> batch = indexed.getT2();

            return transactionalOperator.transactional(
                    insertBatch(batch)
                )
                .map(inserted -> new BatchOutcome(
                    batchNumber,
                    batch.size(),
                    inserted,
                    null
                ))
                .onErrorResume(error -> Mono.just(new BatchOutcome(
                    batchNumber,
                    batch.size(),
                    List.of(),
                    classify(error)
                )));
        });
}
```

`insertBatch(batch)` represents a batch operation returning a list of results with IDs. `TransactionalOperator` wraps the batch publisher; `onErrorResume` sits outside the transaction boundary so errors reach the transaction manager and trigger rollback before being mapped into a failed `BatchOutcome`.

When `onErrorResume` catches the error after the transaction, the current batch is recorded as failed and `concatMap` can proceed to the next batch. This produces partial results across batches: earlier batches may have committed, the failing batch rolls back, and later batches continue. This behavior must be explicitly accepted in the import contract.

Never put `onErrorResume` inside `transactionalOperator.transactional(...)` if the goal is to roll back the entire batch on error. Swallowing the error before the transaction manager sees it can leave the transaction committing in an unintended state or with the database transaction already aborted.

## 12. Per-record transactions

If valid records must still be persisted even when other records in the same input list fail, each record can have its own transaction:

```java
public Flux<RowOutcome> importRowsIndependently(
        Flux<PersonInput> source) {

    return source.concatMap(input -> {
        Mono<Person> write = personRepository.save(new Person(
            null,
            input.requestKey(),
            input.name(),
            input.email()
        ));

        return transactionalOperator.transactional(write)
            .map(saved -> (RowOutcome) new RowOutcome.Success(
                input.requestKey(), saved.id()))
            .onErrorResume(error -> Mono.just(
                new RowOutcome.Failure(input.requestKey(), classify(error))
            ));
    });
}
```

The benefit is knowing precisely which item failed and which succeeded. The downside is more transactions and more round-trips. For large datasets, process in small batches or use a staging mechanism to balance throughput and error isolation.

## 13. Why you should not use onErrorContinue to skip batch errors

`onErrorContinue` can look appealing when you want to skip a failing item and keep the stream going. However, for database operations, it does not automatically guarantee that:

- The failing statement rolled back.
- The transaction remains in a usable state.
- The driver cleared or reset connection state.
- Earlier elements in the same batch committed independently.
- Generated IDs match remaining inputs accurately.

A constraint error inside a PostgreSQL transaction can put the entire transaction into an aborted state. Sending more statements on that same transaction will fail until rollback. Therefore, use per-batch or per-record transactions, let errors escape the transaction boundary so rollback finishes cleanly, and only then continue.

`onErrorResume` also does not create a transaction boundary by itself. Operator placement matters: catch errors after the transaction so the transaction manager observes the error and rolls back first.

## 14. Isolating failing records in a failed batch

If a 500-record batch has one record violating a unique constraint, the batch transaction may roll back all 500. Several strategies can pinpoint the offending item:

**Pre-write validation:** validate format, required fields, and rules checkable at the application layer. This does not replace database constraints since concurrent writes can change data.

**Batch bisection:** after a batch fails due to a data error, split the group in half and retry each half in an independent transaction. Continue splitting until the failing item or small group is found. This uses fewer attempts than writing row-by-row from the start, though it only works when retries are safe and errors are deterministic.

**Per-record fallback:** if a batch fails, roll back and retry each input in its own transaction to pinpoint exact errors. This is simple but can be slow for large batches.

**Savepoints:** within a transaction, you can create a savepoint before a small sub-group and roll back to the savepoint when it fails, if supported by the database and driver. Savepoint support and connection state must be verified per driver; do not assume all R2DBC drivers behave identically.

Do not use bisection or fallback retries for widespread connectivity outages, persistent deadlocks, or configuration errors. When failures are systemic, shrinking batches only adds load without fixing the root cause.

## 15. Safe retries and idempotency keys

A timeout or dropped connection can occur after the database executed the insert but before the application received the response. At that point, the application does not know whether data committed. Resending the same inputs can create duplicates without an idempotency mechanism.

A common approach is storing a unique `request_key`:

```sql
CREATE TABLE person (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    request_key UUID NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    email VARCHAR(320) NOT NULL
);
```

On retry, the application can look up by `request_key` first or use a database-appropriate upsert. With PostgreSQL:

```sql
INSERT INTO person (request_key, name, email)
VALUES (:requestKey, :name, :email)
ON CONFLICT (request_key)
DO UPDATE SET name = EXCLUDED.name,
              email = EXCLUDED.email
RETURNING id, request_key;
```

This example uses PostgreSQL `ON CONFLICT`. If the request key already exists, the statement updates the existing row and returns its ID; depending on business rules, you could choose `DO NOTHING` and re-query. Decide explicitly whether retrying the same key with a different payload should update or report a conflict.

Retry only errors classified as transient, using bounded attempt counts, exponential backoff, and jitter. Do not retry data errors like unique violations if the input has not changed. For deadlocks or serialization failures, you can retry the entire transaction if business rules and operations are idempotent.

## 16. Sequences and identities can leave ID gaps

Do not assume generated IDs are contiguous or that rollbacks return allocated numbers. Many databases consume sequence/identity values even when a transaction rolls back. Thus gaps can appear in the ID sequence after a failed batch.

For example, a batch acquires IDs 101, 102, 103 and rolls back; the next batch may receive 104, 105. This is normal and does not indicate missing data or a bug.

Never use `MAX(id) + 1`, never infer each input's ID from the first ID, and never use the gap between two IDs as a count of succeeded records. Always read IDs returned by the database and match them via correlation keys.

## 17. Choosing a multi-row statement or driver batching?

These two approaches differ in failure scope and result retrieval:

| Criterion | Multi-row INSERT | R2DBC SPI Statement batch |
|---|---|---|
| SQL statements | One query containing multiple VALUES tuples | One statement with multiple binding sets via `add()` |
| Generated IDs | Databases like PostgreSQL can return multiple rows via `RETURNING` | `returnGeneratedValues` depends on driver support and how results emit |
| Pairing IDs to inputs | Easy when `RETURNING` includes the correlation key | Verify driver behavior; do not assume order or one Result per input |
| Constraint errors | Usually the entire statement fails as one unit | Behavior when one item fails depends on driver and transaction |
| SQL size | SQL text and bindings grow with row count | Fixed SQL, multiple SPI binding sets |
| Portability | Multi-row syntax is common, though `RETURNING` varies by database | Batch API is more uniform, though generated keys remain driver-dependent |

Choose based on database/driver capabilities, batch size, and result requirements. If accurate ID mapping is needed and the database supports `RETURNING`, a multi-row insert with a correlation key is usually straightforward. If using SPI batching to cut overhead, thoroughly verify driver behavior for generated values and errors.

## 18. Handling batch success and failure outcomes

Do not return only a total count of succeeded rows if the system needs diagnostics and retries. An import result should capture:

- Batch number or import job ID.
- Attempted item count.
- Succeeded item count.
- List of succeeded correlation keys and generated IDs.
- List of failed correlation keys with actionable error codes.
- Whether the batch was retried and retry count.
- Start/end timestamps and duration.

Example result model:

```java
public record ImportReport(
    String jobId,
    int attempted,
    int succeeded,
    int failed,
    List<PersonCreated> created,
    List<RowFailure> failures
) {}

public record RowFailure(
    String requestKey,
    String errorCode,
    boolean retryable
) {}
```

Do not include sensitive payloads or connection details in error reports. Use correlation keys to cross-reference logs and source data. If failure counts are large, persist details to an error table or output file instead of holding the full list in memory.

## 19. Limiting concurrency across multiple batches

`concatMap` runs sequentially, is predictable, and helps preserve ordering. `flatMap` can execute multiple batches concurrently, though concurrency should be capped:

```java
Flux.fromIterable(inputs)
    .buffer(200)
    .flatMap(this::insertBatch, 4);
```

A concurrency of 4 is only an example. Increasing concurrency can boost throughput when the database has spare resources, while also increasing active connections, lock contention, memory, and deadlock risk. If each batch opens its own transaction, each transaction may require a connection.

Do not use `parallel()` or unbounded `flatMap` for database writes just because the API is reactive. Measure pool utilization, acquire latency, query latency, and errors before increasing concurrency.

## 20. Writing checkpoints to resume imports after failures

For large import jobs, store per-batch state:

| Field | Meaning |
|---|---|
| `job_id` | Import run identifier |
| `batch_no` | Group sequence number |
| `status` | `PENDING`, `PROCESSING`, `SUCCEEDED`, `FAILED` |
| `attempted_count` | Items in the batch |
| `success_count` | Succeeded items |
| `failure_count` | Failed items |
| `started_at`, `completed_at` | Processing timestamps |
| `error_code` | Error category if failed |

Checkpoints allow resuming from incomplete batches instead of resending all data. However, checkpoint updates and data writes need a consistency strategy. You can record `PROCESSING` first, then commit data together with `SUCCEEDED` in the same transaction when checkpoints live in the same database. If the job crashes after committing data but before marking completion, idempotency keys let the rerun recognize already-existing records.

For very large datasets, avoid holding all generated IDs in memory. Persist the `request_key -> generated_id` mapping into an import results table per batch.

## 21. Testing generated IDs and batch errors

Integration tests should cover both success and failure scenarios:

1. Write a valid batch and verify every input receives a generated ID.
2. Verify IDs are paired to the exact `requestKey`, not relying on incidental order.
3. Write a batch with one item violating a unique constraint and verify rollback scope matches the design.
4. Verify whether subsequent batches continue when an earlier batch fails.
5. Check error behavior and emission order of `saveAll` in your Spring Data version.
6. Verify driver support for `Statement.add()` and `returnGeneratedValues` for your batch shape.
7. Test multi-row `RETURNING`/`OUTPUT` on the target database.
8. Verify IDs can have gaps after rollbacks and the application does not rely on contiguous IDs.
9. Simulate a connection failure after the server may have committed; verify idempotency-key retries create no duplicates.
10. Test concurrency, transaction timeouts, rollbacks, and connection release.

Testcontainers or a test database matching production engine type is appropriate. H2 can differ from PostgreSQL, SQL Server, or Oracle on generated values, batch execution, transaction error states, and returning syntax.

## 22. Workflow for implementing multi-record writes

A practical workflow for imports or bulk creation:

**Step 1 — Normalize inputs.** Validate data and create correlation keys and idempotency keys if retries are needed.

**Step 2 — Choose write mechanism.** Use `saveAll` for convenient CRUD, multi-row inserts when the database returns suitable results, or `Statement.add()` when SPI-level batching is needed.

**Step 3 — Choose ID retrieval.** Use returned entities from a Repository, `RETURNING`/`OUTPUT`, or `Statement.returnGeneratedValues`; always verify driver support.

**Step 4 — Pair results.** Prefer returning correlation keys alongside generated IDs. Never infer IDs via `MAX(id)` or assume contiguous IDs.

**Step 5 — Chunk inputs.** Pick batch size based on parameter limits, payloads, latency, and transaction duration.

**Step 6 — Define rollback units.** Choose per-record, per-batch, or whole-job transactions based on business requirements.

**Step 7 — Classify errors.** Separate data, constraint, transient, timeout, and configuration errors; retry only suitable categories.

**Step 8 — Record per-group outcomes.** Persist counts, generated IDs, correlation keys, errors, and required checkpoints.

**Step 9 — Test on real databases.** Verify generated values, batch errors, rollbacks, and idempotency with the exact driver.

## 23. Conclusion

Writing multiple records in Spring Data R2DBC requires a clear strategy for both generated IDs and error handling. `saveAll` is convenient for CRUD without guaranteeing a single SQL batch; multi-row inserts can return multiple IDs via `RETURNING`/`OUTPUT`; R2DBC SPI `Statement.add()` provides batch binding while generated values and error behavior depend on the driver.

To pair IDs accurately, return a correlation key alongside generated IDs instead of relying on ordering or contiguous sequences. For error handling, define the rollback unit as record, batch, or job; catch errors outside transaction boundaries; retry only transient errors on idempotent operations; and record per-group outcomes. Integration testing against the target database and driver is the reliable way to confirm assumptions about batching, generated values, and transactions before going to production.
