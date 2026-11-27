# Comparing Single-Row Writes, Batched Writes, and Multi-Row SQL

When a Spring Data Relational R2DBC application must persist many records, how writes are structured affects throughput, latency, memory, transactions, and error handling. Calling `save` per entity is straightforward and suits many business flows. However, when writing thousands or millions of rows, statement creation, parameter binding, and database round-trip overhead can become bottlenecks.

Several write strategies exist:

- **Single-row writes:** each entity is persisted via its own insert/update operation.
- **Application-level chunking:** grouping entities into chunks processed sequentially or with bounded concurrency.
- **Batch statements:** reusing one SQL statement with multiple parameter binding sets via R2DBC APIs such as `Statement.add()`, if supported by the driver.
- **Multi-row SQL:** a single `INSERT` statement containing multiple `VALUES` tuples.
- **Database-native bulk loading:** specialized high-throughput bulk ingestion mechanisms provided by the database when volumes justify them.

These approaches are not equivalent. In particular, the method name `saveAll` does not guarantee Spring Data generates a multi-row `INSERT` or a driver-level batch. Understand your Spring Data implementation, driver, and database before choosing a strategy.

This lesson compares the performance and semantics of each approach, illustrating reactive flow organization, chunking, transactions, backpressure, error handling, bind-parameter limits, generated IDs, and benchmarking on real databases.

## 1. Concepts to Distinguish

Before comparing, separate concepts often loosely lumped together as “batching”.

| Concept | Meaning | Example |
| --- | --- | --- |
| Application-level grouping | Collecting entities into a collection to process together. | `buffer(500)` then processing each chunk. |
| Batch statement | Sending one SQL statement with multiple parameter sets. | R2DBC `Statement.bind(...).add()...execute()`. |
| Multi-row SQL | One `INSERT` containing multiple `VALUES` tuples. | `INSERT INTO t(a,b) VALUES (...), (...)`. |
| Bulk loading | Database-specific optimized ingestion API. | `COPY` in PostgreSQL or equivalent bulk loaders. |

Collecting entities into a `List` does not automatically create a batch statement. Calling `repository.saveAll(list)` does not guarantee the driver receives a single bulk command either. Conversely, a multi-row `INSERT` is a single SQL statement even though the application builds it from a collection.

### Layers in the Write Path

~~~mermaid
flowchart TD
    A[Publisher of entities] --> B[Application grouping]
    B --> C{Write strategy}
    C --> D[Save each entity]
    C --> E[Repeated statement batch]
    C --> F[Multi-row INSERT]
    C --> G[Database bulk loader]
    D --> H[R2DBC driver]
    E --> H
    F --> H
    G --> I[Database bulk protocol]
    H --> J[(Database)]
    I --> J
~~~

Each strategy has distinct strengths and limits. Never compare merely by lines of code; evaluate executions, round trips, transaction scope, payload sizes, and error semantics.

## 2. Single-Row Writes with `repository.save`

This is the most direct approach: for each entity, call `repository.save` and chain the publisher into the reactive flow.

~~~java
public Flux<Person> saveOneByOne(Flux<Person> people) {
    return people.concatMap(repository::save);
}
~~~

`concatMap` processes elements in order: awaiting the current entity's save before starting the next. This makes concurrency and ordering easy to control.

When data comes from a small collection:

~~~java
return Flux.fromIterable(people)
    .concatMap(repository::save);
~~~

### Advantages

- Simple, readable, easy-to-debug code.
- Each entity uses standard repository mapping and persistence lifecycles.
- Easy to retrieve saved entities, including generated IDs or updated versions.
- Easy to attach per-entity business logic.
- Easy to identify which record failed during sequential processing.
- Easy to enforce domain checks before or after each write.

### Limitations

- Usually generates one SQL operation per entity.
- Can produce many executions and database round trips.
- Network, statement preparation, and transaction coordination overhead can become heavy.
- Throughput can suffer when latency between application and database is high.

Single-row writes remain effective for small volumes, heterogeneous updates, or complex per-entity logic. Do not optimize into batches until measurements show writes are a bottleneck.

### Transaction Considerations

Without a transaction spanning the whole publisher, individual statements may commit under autocommit or driver/database-managed transactions. If row 50 fails, the prior 49 rows may already be committed.

Wrapping the entire publisher in one reactive transaction lets all statements join that transaction. When an error escapes the transaction boundary, the entire transaction can roll back, altering both error semantics and lock hold times.

## 3. `saveAll` Does Not Mean a Single Bulk Insert

`ReactiveCrudRepository` exposes `saveAll` to persist multiple entities:

~~~java
Flux<Person> saveAll(Iterable<Person> entities);

Flux<Person> saveAll(Publisher<Person> entities);
~~~

This API expresses the business intent of saving multiple entities. It is not a guarantee that the implementation builds a multi-row `INSERT` or uses R2DBC `Statement.add()`.

In many Spring Data R2DBC implementations, `saveAll` processes entities by invoking save logic per item, often sequentially. Exact mechanics can vary by Spring Data version and repository implementation. Inspect your version's source/behavior when this path is performance-critical.

Example:

~~~java
return repository.saveAll(people);
~~~

The call looks concise yet reveals nothing about SQL statement counts or round trips. Never assume 1,000 entities become a single `INSERT` with 1,000 `VALUES`.

### When Is `saveAll` Appropriate?

- Moderate datasets.
- Standard Spring Data mapping and lifecycle callbacks are desired.
- You need each saved entity emitted back.
- Database round trips are not a proven bottleneck.
- Current repository throughput meets requirements.

### When Are Alternatives Needed?

- Importing tens of thousands or millions of rows.
- Measurements show database/network wait dominates runtime.
- Explicit chunk size control is required.
- Execution counts must be reduced.
- Vendor-specific SQL is acceptable.
- Import flows require checkpoints, retries, and idempotency.

Do not replace `saveAll` with bulk SQL based purely on assumptions. Measure a baseline first and verify which features—auditing, callbacks, generated IDs, optimistic locking, converters—must be preserved.

## 4. Application-Level Chunking

Application chunking groups a stream into bounded chunks. Each chunk can then be persisted using repositories, batch statements, or multi-row SQL.

Example grouping 500 entities at a time:

~~~java
public Flux<Person> saveInChunks(Flux<Person> source) {
    return source
        .buffer(500)
        .concatMap(chunk ->
            repository.saveAll(chunk)
        );
}
~~~

This caps how many entities enter each chunk before calling `saveAll`. It **does not automatically turn `saveAll` into a SQL batch**. If `saveAll` saves entity by entity, each chunk still issues multiple saves.

### Why Chunk?

- Bounds memory on large or unbounded sources.
- Establishes trackable units of work.
- Allows committing per chunk.
- Simplifies writing checkpoints after each chunk.
- Reduces risk of overly long transactions.
- Creates clear retry boundaries for idempotent imports.

### Choosing Chunk Size

Too small increases orchestration overhead and underutilizes batching. Too large inflates memory, statement size, transaction duration, and retry scope on failure.

There is no universal optimal chunk size. Start testing values such as 100, 250, 500, or 1,000 rows and benchmark on realistic workloads.

Factors to weigh:

- Column count and row width.
- Database/driver bind parameter limits.
- Packet or statement size limits.
- Network latency.
- Heap memory and backpressure.
- Chunk commit duration.
- Lock contention with concurrent workloads.

### Per-Chunk Transactions

When each chunk must be atomic on its own, wrap the chunk publisher with `TransactionalOperator`:

~~~java
public Flux<Person> saveChunked(
        Flux<Person> source,
        TransactionalOperator transaction) {

    return source
        .buffer(500)
        .concatMap(chunk ->
            transaction.transactional(
                repository.saveAll(chunk)
            )
        );
}
~~~

Each chunk executes in its own transaction per the transaction manager. If chunk 3 fails, chunks 1 and 2 may already be committed; chunk 3 rolls back; subsequent chunks do not run if the error propagates.

Wrapping the transaction outside the entire publisher:

~~~java
return transaction.transactional(
    source.buffer(500)
        .concatMap(repository::saveAll)
);
~~~

places all chunks in one giant transaction. This provides all-or-nothing atomicity at the cost of longer transactions, longer connection holds, and longer locks. Choose based on business rules, not throughput alone.

## 5. `concatMap`, `flatMap`, and Concurrency

Reactive operators govern how many write operations run concurrently.

### `concatMap`: Sequential

~~~java
return source.concatMap(repository::save);
~~~

- Runs one downstream save at a time.
- Preserves source emission order.
- Predictable ordering and failure boundaries.
- Throughput can be bounded by per-operation round-trip latency.

### `flatMap`: Concurrent

~~~java
return source.flatMap(repository::save, 8);
~~~

- Allows up to the configured concurrency of active inner publishers.
- Emissions may arrive out of source order.
- Can increase throughput when database and pool have spare capacity.
- Can cause connection, lock, and resource contention.
- Does not create a single SQL batch.

`flatMap` with concurrency 8 still performs separate save operations. It increases parallelism, not SQL batching.

### `flatMapSequential`

~~~java
return source.flatMapSequential(repository::save, 8);
~~~

Runs inner publishers concurrently while emitting results in source order. Emitting results in order does not mean the database executed or committed them in that exact order.

### Choosing Concurrency

Start with low concurrency and ramp up during benchmarks. Never crank concurrency way up trying to “force” the database faster. If a pool has 10 connections and the app launches thousands of concurrent saves, most tasks simply queue and add memory pressure.

When multiple statements share a single transaction connection, drivers or databases may not support parallel execution on that connection. Inside transactions, stick to `concatMap` or sequential commands unless driver support is verified.

## 6. Batch Statements with R2DBC `Statement.add()`

The R2DBC SPI defines `Statement.add()` to append another parameter set to the same statement. You create the SQL once, bind the first parameter set, call `add()`, and bind the next set before executing.

R2DBC SPI example using PostgreSQL positional bind markers:

~~~java
Statement statement = connection.createStatement(
    "INSERT INTO people (first_name, email) VALUES ($1, $2)"
);

statement
    .bind(0, "Ada Lovelace")
    .bind(1, "ada@example.test")
    .add();

statement
    .bind(0, "Grace Hopper")
    .bind(1, "grace@example.test");

Publisher<? extends Result> results = statement.execute();
~~~

The example uses PostgreSQL positional markers; other drivers use different markers. Check `Statement.add()` and batch execution behavior for your specific R2DBC driver.

### What Does `add()` Do?

- Keeps the SQL statement fixed.
- Adds the current bindings to the batch.
- Prepares the next parameter binding slot.
- Executes the statement across accumulated binding sets.

Batch statements differ from multi-row SQL. A batch executes the same `INSERT` across multiple parameter sets; multi-row SQL is a single `INSERT` containing multiple `VALUES` tuples.

### Not Every Driver Optimizes Identically

The R2DBC SPI defines the abstraction, while wire-level batch transmission depends on the driver implementation. Some drivers pipeline batches efficiently; others have limitations by statement type; behavior around generated values and `rowsUpdated` can also vary.

Never assume `Statement.add()` always takes one network round trip or always beats multi-row `INSERT`. Check driver documentation and benchmark on your setup.

### Integrating with Spring Transactions

When using `Connection` and `Statement` directly, manage connection lifecycles carefully. Inside a Spring-managed transaction, do not open a separate connection and expect statements to join the active transaction. Obtain the transaction-managed connection or integrate via a custom repository implementation wired into transaction binding/context.

When direct `Statement.add()` control is not needed, prefer supported Spring Data APIs and drop down to custom persistence code only when benchmarks justify it.

## 7. Multi-Row SQL with `INSERT ... VALUES`

Multi-row SQL writes multiple tuples in one `INSERT` statement:

~~~sql
INSERT INTO people (first_name, email)
VALUES
    ('Ada Lovelace', 'ada@example.test'),
    ('Grace Hopper', 'grace@example.test'),
    ('Katherine Johnson', 'katherine@example.test');
~~~

This reduces executions compared to sending one `INSERT` per row. The database parses and executes a single multi-row statement.

With bind parameters, for example two rows:

~~~java
databaseClient.sql("""
    INSERT INTO people (first_name, email)
    VALUES
        (:name0, :email0),
        (:name1, :email1)
    """)
    .bind("name0", "Ada Lovelace")
    .bind("email0", "ada@example.test")
    .bind("name1", "Grace Hopper")
    .bind("email1", "grace@example.test")
    .fetch()
    .rowsUpdated();
~~~

Spring `DatabaseClient` supports named parameters and translates them to driver-specific bind markers. This example uses fixed SQL for two rows; for dynamic row counts, construct placeholders matching the batch count and bind every parameter accordingly.

### Generate Only Structural Placeholders from Counts

When building dynamic SQL, concatenate only generated placeholders and allow-listed identifiers. Never concatenate client values directly into SQL.

Conceptual placeholder generation:

~~~java
String values = IntStream.range(0, rows.size())
    .mapToObj(i -> "(:name" + i + ", :email" + i + ")")
    .collect(Collectors.joining(", "));

String sql = """
    INSERT INTO people (first_name, email)
    VALUES %s
    """.formatted(values);
~~~

Then bind each name/email via the `DatabaseClient` API. Table and column names must remain static or come from strict allow-lists. Data values must always be bound, never interpolated into SQL text.

### Bind Parameter Limits

If each row binds C columns and the database caps total parameters at P, maximum rows per statement cannot exceed:

\[
N \leq \left\lfloor \frac{P}{C} \right\rfloor
\]

This is only a theoretical parameter-count ceiling. Leave room for extra parameters and respect practical database, driver, statement-length, and packet-size limits.

An `INSERT` with 500 rows and 8 columns requires roughly 4,000 bind parameters. At 5,000 rows, bindings reach 40,000. Databases or drivers may reject oversized statements well before hitting other theoretical bounds.

### Generated IDs and `RETURNING`

Some databases support `RETURNING` to return generated IDs or columns:

~~~sql
INSERT INTO people (first_name, email)
VALUES
    ('Ada Lovelace', 'ada@example.test'),
    ('Grace Hopper', 'grace@example.test')
RETURNING id, first_name, email;
~~~

`RETURNING` support and how R2DBC drivers expose rows vary by database. If mapping returned rows back to inputs, do not assume output row order always matches input order unless the database documentation guarantees it. Prefer stable business keys or a queryable correlation token.

## 8. Database-Native Bulk Loading

For massive volumes, databases typically offer specialized ingestion mechanisms with much higher throughput than standard inserts.

Examples:

- PostgreSQL `COPY` command/protocol.
- Vendor-specific bulk insert, load data, or import utilities.
- Cloud database ingestion from object storage files.

Bulk loaders cut statement parsing and per-row binding overhead drastically. However, they carry specialized semantics, APIs, and formatting rules.

Considerations:

- Does the bulk loader bypass or handle triggers, constraints, defaults, and indexes differently?
- Are errors reported per row or for the whole file?
- Are transactions and rollbacks supported?
- Can data stream from the source without loading entire files into the heap?
- Can jobs resume from checkpoints?
- Does it require elevated database privileges or server-side file access?

Bulk loading suits large imports, ETL, and background ingestion. It is not the default choice for HTTP requests persisting a handful of entities.

## 9. Performance Comparison

The table below outlines typical tendencies, not guaranteed round-trip counts for every driver:

| Strategy | App-Level Executions | Round-Trip Reduction Potential | Complexity | Best Fit |
| --- | --- | --- | --- | --- |
| Save each row | Usually one execute per row. | Low. | Low. | Few records, per-entity logic. |
| `saveAll` | Implementation-dependent; may still save row by row. | Not guaranteed. | Low. | Standard repository API, moderate sets. |
| Chunk + `saveAll` | Multiple saves inside each chunk. | Not reduced automatically if implementation saves per row. | Medium. | Controlling memory and transaction scope. |
| `flatMap` concurrency | Many concurrent saves. | Improves throughput by overlapping latency, not batching. | Medium. | Independent I/O when DB and pool have headroom. |
| `Statement.add` batch | One statement with multiple binding sets. | Can reduce executions/round trips. | Higher. | Repeating identical SQL when driver supports batching. |
| Multi-row `INSERT` | One SQL statement with multiple `VALUES`. | Typically reduces executions and round trips. | Medium/high. | Inserting homogeneous rows. |
| Bulk loader | Specialized ingestion API/protocol. | Highest potential on massive workloads. | High. | Huge imports/ETL where supported by DB. |

No single method always wins. For tiny batches, dynamic SQL overhead or custom code can outweigh gains. For gigantic batches, a massive SQL statement can breach packet/parameter limits and spike memory.

### Influencing Factors

1. **Network latency:** the farther the database, the larger the gain from cutting round trips.
2. **Statement preparation:** repeated SQL benefits from prepared statement or driver caches.
3. **Mapping:** reflection, conversion, and callbacks can consume application CPU.
4. **Indexes and constraints:** every row still updates indexes and checks constraints.
5. **Transaction logs:** heavy writes generate substantial WAL/redo log traffic.
6. **Lock contention:** large transactions hold locks longer and block concurrent workloads.
7. **Connection pool:** excessive concurrency starves the pool.
8. **Payload size:** rows with large JSON/BLOBs inflate packets and heap.
9. **Database load:** CPU, I/O, and replication lag can become the bottleneck.

## 10. Backpressure and Memory When Processing Large Data

Reactive does not mean holding unlimited data in memory. `buffer` allocates a collection per chunk; if the producer outpaces writes, memory held in flight must be bounded.

Example:

~~~java
return source
    .buffer(500)
    .concatMap(this::writeChunk);
~~~

`concatMap` waits for the current chunk to finish before processing the next, bounding active downstream chunks.

If using:

~~~java
return source
    .buffer(500)
    .flatMap(this::writeChunk, 4);
~~~

up to four chunks may be active simultaneously according to concurrency. Minimum chunk memory approximates concurrency times chunk size, excluding internal buffers, in-flight items, and object overhead.

### Never `collectList` an Entire Large Source

Avoid:

~~~java
return source.collectList()
    .flatMapMany(repository::saveAll);
~~~

If the source contains millions of entities, `collectList` retains them all on the heap before saving begins. Use `buffer(chunkSize)` to bound grouped data.

### Bound the Data Source Itself

If reading from files, message streams, or cursors, ensure the source also reads incrementally. If an entire file was loaded into a `List` beforehand, downstream `buffer` cannot undo the memory already consumed.

Maintain backpressure end-to-end from reader to writer. Avoid detaching independent subscriptions or inserting unbounded queues between producers and writers.

## 11. Transactions and Atomicity

Write performance must always be evaluated alongside transaction semantics.

### No Outer Transaction

Writes complete independently. If one row fails after earlier successes, prior rows remain persisted.

Appropriate when:

- Rows are independent.
- Partial success is acceptable.
- Row/chunk retries or checkpoints exist.
- Large imports need steady incremental progress.

### One Transaction for the Entire Import

~~~java
return transaction.transactional(
    source.concatMap(repository::save)
);
~~~

If an error escapes the transaction boundary, all work rolls back. On the downside, transactions stay open long, holding connections and locks, inflating logs, and impacting other workloads.

Appropriate when the entire dataset must succeed or fail together and total size is bounded.

### One Transaction per Chunk

~~~java
return source
    .buffer(500)
    .concatMap(chunk ->
        transaction.transactional(
            repository.saveAll(chunk)
        )
    );
~~~

Each chunk is an atomic commit unit. This often strikes a practical balance between atomicity and throughput for large imports, provided checkpoints track committed chunks.

If chunk 8 fails, chunks 1–7 are already committed. Retries must recognize already-processed chunks to avoid duplicates.

### Transactions Do Not Turn Saves into Batches

`@Transactional` or `TransactionalOperator` defines only transaction boundaries—not SQL statement counts. One transaction running 1,000 `repository.save` calls can still execute 1,000 individual `INSERT`s.

## 12. Error Handling and Partial Success

Different write strategies have different failure semantics:

| Strategy | When One Row Fails | State of Other Rows |
| --- | --- | --- |
| Row-by-row, no outer transaction | Sequential publisher usually stops at first error. | Prior rows may already be committed. |
| Row-by-row inside one large transaction | Error escaping boundary rolls back everything. | Prior rows roll back with the transaction. |
| Chunked, per-chunk transaction | Failing chunk rolls back; flow may halt. | Earlier chunks committed; later chunks untouched. |
| Statement batch | Driver/database determines batch error reporting. | Partial execution varies by driver/DB; test explicitly. |
| Multi-row `INSERT` | Statement failure usually fails the whole statement per DB semantics. | Rows in that statement share statement outcome; outer transaction governs commit. |
| Bulk loader | Depends on database API, error mode, and transaction settings. | May abort batch or report per-row errors. |

Do not assume “if a batch fails, zero rows were written” without confirming driver, database, and transaction behavior. Inspect `rowsUpdated`, SQLSTATE, transaction status, and stored rows after failures.

### Do Not Silently Swallow Errors

Dangerous pattern:

~~~java
return source.flatMap(repository::save)
    .onErrorResume(error -> Mono.empty());
~~~

This turns write failures into normal completion, fooling callers into thinking everything saved. When partial success is desired, model outcomes explicitly:

~~~java
record RowWriteResult(
    int inputIndex,
    boolean saved,
    String errorCode
) {}
~~~

Each row or chunk reports a success/failure result recording its index or business key so operators can pinpoint failed records.

## 13. Retries and Idempotency for Imports

Retries help handle transient failures such as deadlocks or dropped connections. However, a timeout can happen after the database committed an insert yet before the application received the response. Blind retries then produce duplicates.

Imports should design for:

- Stable business keys or idempotency keys.
- Database unique constraints.
- Checkpoints per chunk or source offset.
- Persistent import job status and processed row counts.
- Explicit duplicate-handling rules.
- Bounded retries with backoff.
- Safe resumption from uncommitted chunks.

Upserts can make replays safe, though syntax and semantics vary across databases. Clarify whether key collisions should skip, update, or raise conflicts. Avoid blind upserts if they could silently overwrite newer data.

### Retry Whole Chunks or Individual Rows?

- If a chunk runs inside a single transaction that rolls back cleanly, retrying the chunk works well.
- If partial commits are possible, retry per row or enforce idempotency keys.
- If a bulk API provides native checkpointing, use the database's resume mechanism.
- Never retry SQL syntax errors, mapping bugs, or data constraint violations as transient errors.

## 14. Generated IDs, Auditing, and Lifecycle Behavior

Repository `save` applies Spring Data mapping and entity callbacks. Switching to custom batch SQL requires explicitly restoring or verifying needed behaviors.

Questions to check:

- Are database-generated IDs returned for every row?
- Is `@Version` incremented and optimistic locking enforced?
- Do `BeforeConvert`/`BeforeSave`/`AfterSave` callbacks run?
- Are auditing fields populated?
- Are custom converters applied to every bind parameter?
- Do returned entities reflect database defaults or triggers?
- Is `RETURNING` needed to retrieve generated columns?

Custom SQL via `DatabaseClient` bypasses repository entity lifecycle hooks. When moving to batch SQL for throughput, list required behaviors and implement any missing pieces explicitly in the application or persistence layer.

For multi-row generated IDs, never match returned IDs to input items solely by position unless the database and driver explicitly guarantee ordering. Use a stable correlation key when mapping results back.

## 15. Batch and SQL Size Limits

Batches must stay within constraints across multiple layers:

- Database bind-parameter limits.
- Maximum SQL statement length or network packet size.
- Driver message/frame limits.
- Heap memory for building SQL strings and retaining bind values.
- Parse/plan/execute duration.
- Transaction timeouts.
- Bulk API row or payload caps.

If each row binds C columns and a chunk holds N rows, total bind parameters are roughly N × C plus any extra parameters. Pick N safely below real limits with margin.

Oversized multi-row SQL inflates parse times and memory. Repeated statement batches reuse SQL text while still holding binding sets. Bulk loaders often fit best when volumes grow very large.

Never hardcode one chunk size for all entities. A 5-column narrow row behaves completely differently from a 40-column row with large JSON or binary payloads.

## 16. Choosing Which Strategy to Use

Use this decision table as a starting point:

| Situation | Starting Choice |
| --- | --- |
| Saving a few entities in a request | `repository.save` |
| Moderate counts needing standard mapping | `repository.saveAll`, after verifying implementation |
| Streaming many entities needing bounded memory | `buffer(chunkSize) + concatMap` |
| Independent operations benefiting from concurrency | `flatMap` with low, measured concurrency |
| Repeating identical INSERT many times with batch-capable driver | R2DBC `Statement.add()` |
| Many homogeneous rows needing fewer executions | Multi-row `INSERT` |
| Massive data imports with DB bulk protocol | Specialized bulk loading |
| Partial success and resumability required | Chunk transactions + checkpoints + idempotency |
| Entire dataset must be atomic | One transaction if size and duration remain bounded |

Start with business semantics, then optimize SQL delivery. For example, if each row needs independent confirmation and per-row retries, a single bulk statement may not fit even if raw throughput is higher.

## 17. Measuring Performance Properly

Do not evaluate strategies from a single laptop run. Benchmarks should reflect realistic data sizes, network latency, and concurrency.

Metrics to collect:

- Rows per second.
- Total import duration.
- p50/p95/p99 latency per chunk.
- Statement execution and round-trip counts where observable.
- Connection pool acquisition time and active connections.
- Application CPU and memory.
- Database CPU, I/O, lock waits, and transaction log activity.
- Error rates, retry counts, and partial success counts.
- Replication lag if replicas exist.

### Fair Comparisons

When comparing row-by-row, `saveAll`, `Statement.add`, and multi-row SQL:

1. Use the exact same database version, driver, and schema.
2. Use identical row counts and row widths.
3. Keep identical indexes, constraints, and triggers.
4. Keep identical transaction semantics.
5. Warm up connection pools and prepared statements as needed.
6. Run multiple iterations and verify stability.
7. Verify persisted data correctness, not just timing.
8. Test under production-like concurrency.
9. Measure both latency and resource consumption.
10. Test multiple chunk sizes.

If one strategy wins solely because it skipped auditing, constraints, or transactions, the comparison is invalid.

## 18. Testing Each Strategy

Repository tests with `@DataR2dbcTest` fit `save`/`saveAll` and mapping. Custom batches or multi-row SQL need integration tests against the target driver and database.

Cases to verify:

- Exact inserted row count.
- Generated IDs returned or queryable.
- Duplicate keys and constraint errors behave as expected.
- Mid-chunk failures trigger partial success or rollback as designed.
- Retrying the same chunk produces zero duplicates.
- Driver genuinely supports batch statements.
- Multi-row SQL stays within bind-parameter and packet limits.
- Transactions roll back properly when publishers error.
- Re-read data maps cleanly.
- Callbacks/auditing execute or are handled explicitly.

Example multi-row insert test with `DatabaseClient`:

~~~java
@Test
void insertsMultiplePeopleWithOneStatement() {
    String suffix = UUID.randomUUID().toString();

    StepVerifier.create(
        databaseClient.sql("""
            INSERT INTO people (first_name, email)
            VALUES (:name0, :email0), (:name1, :email1)
            """)
            .bind("name0", "Ada")
            .bind("email0", "ada-" + suffix + "@example.test")
            .bind("name1", "Grace")
            .bind("email1", "grace-" + suffix + "@example.test")
            .fetch()
            .rowsUpdated()
    )
    .expectNext(2L)
    .verifyComplete();
}
~~~

This assumes the driver returns `rowsUpdated` as `Long` and no trigger alters the reported count. Adjust assertion types to match your driver and API.

## 19. Common Mistakes

| Mistake | Cause | Fix |
| --- | --- | --- |
| Assuming `saveAll` runs one multi-row INSERT | Confusing multi-entity API with bulk SQL. | Inspect implementation and count statements. |
| Calling `buffer` then `saveAll` yet staying slow | Grouping in app memory only; `saveAll` may still save one by one. | Switch to batch/multi-row SQL when warranted. |
| Raising `flatMap` concurrency too high | Overloads pool and database. | Bound concurrency and benchmark. |
| `flatMap` scrambles output order | Inner publishers complete out of source order. | Use `concatMap` when ordering is required. |
| Oversized chunks | Exceeds bind/packet limits or bloats heap. | Shrink chunk size and measure. |
| One massive transaction for whole import | Holds connections/locks and bloats logs. | Use per-chunk transactions if business rules allow. |
| Batch fails without identifying bad row | Batch API returns aggregate error or driver omits row details. | Track business keys, use smaller chunks, emit failure reports. |
| Retries create duplicate rows | Timeouts happen after commit succeeds. | Enforce idempotency keys and unique constraints. |
| Mismatched generated IDs | Assuming `RETURNING` order always matches input order. | Use correlation keys and verify driver semantics. |
| Custom SQL skips callbacks/auditing | Raw SQL bypasses entity lifecycle hooks. | Set required metadata explicitly and test. |
| Data lost on process restart | Missing durable checkpoints or import state. | Persist per-chunk progress for safe resumption. |

## 20. Process for Selecting and Implementing a Write Strategy

When accelerating multi-row R2DBC writes, follow this sequence:

1. **Clarify business rules:** must the entire batch be atomic or is partial success allowed?
2. **Measure baseline:** benchmark current single-row or `saveAll` throughput and latency.
3. **Inspect implementation:** verify how `saveAll` executes in your Spring Data version.
4. **Bound the source:** use `buffer` so full datasets never sit in memory.
5. **Choose execution style:** single-row, bounded concurrency, `Statement.add`, multi-row `INSERT`, or bulk loader.
6. **Choose transaction scope:** whole import vs. per chunk.
7. **Calculate limits:** bind parameters, packet size, statement length, memory, and timeouts.
8. **Design errors and retries:** idempotency, checkpoints, partial success, and failure reporting.
9. **Preserve required behaviors:** generated IDs, converters, callbacks, auditing, and optimistic locking.
10. **Integration test:** run against the real database/driver and verify persisted data.
11. **Benchmark:** vary one parameter at a time while measuring throughput and resources.
12. **Monitor production:** track pool metrics, query latency, locks, error rates, and import progress.

Single-row writes are clear and fit small workloads or per-entity business rules. Application chunking bounds memory and structures transactions, though grouping alone does not cut SQL statement counts. `Statement.add` and multi-row SQL reduce executions and round trips when supported by the driver and database; bulk loaders serve massive ingestion. Pick strategies around atomicity semantics, retryability, and required persistence behavior, then benchmark on the real driver and database rather than assuming any API named “batch” automatically yields an optimal write path.
