# Regulating Data Demand (Backpressure) and Database-Layer Limits

In Spring Data Relational R2DBC, applications query the database using reactive types such as `Mono<T>` and `Flux<T>`. These types allow data to be emitted according to subscriber demand, letting the application process result streams without blocking a thread to wait for each I/O operation.

However, backpressure at the Reactive Streams layer is only one part of load control. A query can still read too many rows, scan a huge table, hold a connection open for too long, or subject the database to too many concurrent queries. To control resources end to end, reactive demand must work together with SQL query limits, pagination strategies, driver configuration, connection pools, and limits provided by the database management system.

## 1. Why Does Data Volume Need Control?

Suppose an API calls `repository.findAll()` to read millions of records and return them to the client. Even though the API returns `Flux<Customer>`, the application can still encounter these problems:

- A slow-reading client keeps the result stream alive for a long time. The connection or transaction used by the query can be held open for an extended duration.
- An operator that collects all results, such as `collectList()`, forces all data into application memory.
- The driver may prefetch or buffer a batch of rows. Thus, the number of items the subscriber has received does not necessarily equal the number of rows the database has processed or sent over the network.
- Many concurrent requests can exhaust connections in the pool, forcing new requests to wait or time out waiting for a connection.
- A SQL statement lacking an appropriate filter or index can still scan, sort, or join a massive volume of data, even when the application only needs part of the result.

Therefore, three separate questions must be answered: how many items does the subscriber currently need, how many rows is the SQL query allowed to return, and how many resources is the database allowed to spend producing those rows.

## 2. Backpressure in Reactive Streams

Reactive Streams defines a demand-exchange mechanism between subscriber and publisher. In Reactor, `Flux` and `Mono` are the publisher types commonly encountered in Spring Data R2DBC.

A subscriber does not have to receive all data immediately. It can ask the publisher to emit a specific number of items via `request(n)`. The publisher emits at most the requested number of items, aside from completion or error signals. The subscriber can also cancel the subscription via `cancel()` when it no longer needs data.

Example illustrating what demand means:

1. A subscriber subscribes to a `Flux` without initially requesting any items.
2. The subscriber calls `request(1)` to indicate it can currently accept one item.
3. The publisher emits one item via `onNext`.
4. After finishing processing, the subscriber can request additional items.
5. When the subscriber cancels the subscription, the cancel signal propagates up the publisher chain to the extent supported by its components.

In a typical R2DBC flow, demand may pass through the layers as follows:

```text
HTTP client
    |
    v
Spring WebFlux handler / subscriber
    |
    v
Service: Flux<Customer>
    |
    v
Spring Data R2DBC repository / DatabaseClient
    |
    v
R2DBC driver
    |
    v
Database server
```

Backpressure enables reactive publishers to coordinate the rate at which data is pushed downstream. When downstream processes slowly, demand drops and slows further emissions from upstream. When a subscriber cancels, upstream layers get a chance to abort in-flight work.

**Backpressure is not synonymous with limiting a query's row count.** A subscriber may consume data in small chunks yet ultimately read all millions of records. Demand also does not guarantee the database stops executing immediately: how quickly reading halts, cursors close, and resources are released depends on the driver, protocol, and database engine.

## 3. Distinguishing Different Kinds of Limits

The following mechanisms solve different problems and cannot fully substitute for one another.

| Mechanism | What Does It Control? | Limits Total Rows Returned? |
|---|---|---|
| Reactive Streams demand | Number of items a subscriber requests at a time | No |
| Reactor `limitRate(n)` | How Reactor splits and throttles upstream requests | No |
| SQL `LIMIT` or equivalent syntax | Maximum rows a query returns | Yes |
| Keyset pagination | Batch size and range for the next read | Yes, per query |
| Driver fetch size | Hint for how many rows the driver fetches in one round trip or read batch | No |
| Connection pool `maxSize` | Number of connections granted concurrently from the pool | No |
| Database-level limits | Query duration, connections, locks, memory, or other resources depending on the DBMS | Not necessarily |

Good designs use multiple layers: SQL limits results, subscribers consume by demand, drivers read in appropriate batches, pools cap concurrent queries, and the database enforces resource guardrails.

## 4. Reading Data with Spring Data R2DBC

Reactive repositories typically return `Mono<T>` for a single result or `Flux<T>` for multiple results:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByActiveTrue();
}
```

`findByActiveTrue()` returns a `Flux<Customer>`. Subscribers can consume items one by one by demand, yet this method can still return every active customer. If business logic needs only a bounded amount, put the limit into the query.

Example using `@Query` with PostgreSQL or MySQL `LIMIT` syntax:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    @Query("""
        SELECT id, name, created_at
        FROM customer
        WHERE active = true
          AND id > :afterId
        ORDER BY id
        LIMIT :batchSize
        """)
    Flux<Customer> findNextBatch(
            @Param("afterId") Long afterId,
            @Param("batchSize") int batchSize);
}
```

Here:

- `id > :afterId` marks the starting point of the next batch.
- `ORDER BY id` establishes a stable order to define the cursor.
- `LIMIT :batchSize` limits the number of rows returned by the database in a single query.
- `Flux<Customer>` allows the consumer to process rows reactively.

`LIMIT` syntax is dialect-dependent. SQL Server, Oracle, and other database systems may use different row-limiting syntax. Check the SQL supported by your database and dialect. When using `DatabaseClient`, the same principle applies: put the limit directly in SQL and call `fetch().all()` to obtain a `Flux`.

```java
Flux<Customer> customers = databaseClient.sql("""
        SELECT id, name
        FROM customer
        WHERE active = :active
        ORDER BY id
        LIMIT :maxRows
        """)
    .bind("active", true)
    .bind("maxRows", 200)
    .map((row, metadata) -> new Customer(
        row.get("id", Long.class),
        row.get("name", String.class)))
    .all();
```

In real applications, do not let clients send an arbitrarily huge `batchSize`. Validate and enforce a maximum cap at the service or API layer:

```java
public Flux<Customer> findNextBatch(long afterId, int requestedSize) {
    int batchSize = Math.max(1, Math.min(requestedSize, 500));
    return customerRepository.findNextBatch(afterId, batchSize);
}
```

The value `500` is only an example; a suitable limit must be chosen based on record size, latency, database load, and system measurements.

## 5. Limiting Results with SQL and Pagination

### 5.1. LIMIT and OFFSET

Offset pagination fits screens where users jump directly to a specific page:

```sql
SELECT id, name, created_at
FROM customer
WHERE active = true
ORDER BY created_at DESC, id DESC
LIMIT 50 OFFSET 100;
```

`LIMIT 50` caps the rows returned for the current page. `OFFSET 100` skips the previous 100 rows. A stable `ORDER BY` is required; otherwise, the same offset can return different sets of rows across runs.

With large offsets, the database typically has to walk through many rows before returning the desired page. This becomes expensive as users navigate to deep pages. When reading continuously through a large dataset, keyset pagination is usually a better fit.

### 5.2. Keyset Pagination

Keyset pagination uses the values of the last row in the previous batch as a cursor. For example, if `id` is monotonically increasing and unique:

```sql
SELECT id, name, created_at
FROM customer
WHERE id > :lastSeenId
ORDER BY id
LIMIT :batchSize;
```

After processing the current batch, take the `id` of the last row as `lastSeenId` for the next query. The database does not need to skip large numbers of rows via `OFFSET`.

For this approach to be reliable:

- The sort order must be deterministic and should end with a unique key.
- The cursor predicate must match the sort order. If sorting by multiple columns, the cursor must include all values needed to pinpoint the next position.
- Columns used in filter conditions and sorting should have appropriate indexes.
- Define business behavior for records inserted or updated while reading is in progress.

If sorting by `created_at` where multiple rows can share the same timestamp, using only `created_at > :lastSeenTime` can skip rows. Include a unique key as a tiebreaker:

```sql
SELECT id, name, created_at
FROM customer
WHERE created_at > :lastSeenTime
   OR (created_at = :lastSeenTime AND id > :lastSeenId)
ORDER BY created_at, id
LIMIT :batchSize;
```

### 5.3. Select Only Needed Columns

Limiting row count is not enough if each row contains several large columns. `SELECT` only the columns required for business logic, especially when tables contain JSON, long text, or binary data. Projections reduce network transfer from the database, data buffered by the driver, and object conversion costs.

### 5.4. Counting Total Rows

To display total page counts, applications often run an extra `COUNT(*)` query. Count queries have their own resource cost and should not be run automatically for every large stream if the business flow does not need them. Decide explicitly whether an API requires an exact total, an estimate, or only a cursor to fetch the next page.

## 6. Regulating Demand with Reactor Operators

Reactor operators adjust how data flows through a pipeline. Know which operators regulate demand, which limit total items, and which can create buffers.

### 6.1. `limitRate`

```java
customerRepository.findByActiveTrue()
    .limitRate(128)
    .subscribe(this::processCustomer);
```

`limitRate(128)` regulates how Reactor requests data from upstream in batches of requests. It helps prevent downstream from requesting a massive amount all at once. It does **not** mean the query returns only 128 rows; as the subscriber continues requesting, the stream can still emit all results.

### 6.2. `take`

```java
customerRepository.findByActiveTrue()
    .take(100);
```

`take(100)` caps the number of items the pipeline forwards downstream and then cancels the subscription. This is a reactive-layer limit. Depending on the driver and database, some extra data may already have been prefetched or buffered. If business logic requires the database to return at most 100 rows, put `LIMIT 100` in SQL.

### 6.3. Bounding `flatMap` Concurrency

When each row triggers another service call or asynchronous operation, `flatMap` can launch many concurrent tasks:

```java
customerRepository.findByActiveTrue()
    .flatMap(this::enrichCustomer, 8, 1);
```

The `8` parameter limits how many inner publishers run concurrently; `1` sets prefetch per inner publisher. Bounding concurrency avoids launching too much work at once. If the inner operation also accesses the database, align concurrency with connection pool size and database capacity.

When sequential processing is needed, `concatMap` is easier to control:

```java
customerRepository.findByActiveTrue()
    .concatMap(this::processCustomer);
```

In trade-off, sequential processing can lower throughput. Choose based on ordering requirements and resource limits.

### 6.4. Buffer and Backpressure Operators

Some upstream sources cannot slow down their emission rate in response to demand. For those situations, Reactor provides strategies such as `onBackpressureBuffer`, `onBackpressureDrop`, and `onBackpressureLatest`.

- `onBackpressureBuffer` holds items in a buffer when downstream is slow. Buffers need a capacity limit and an overflow policy; unbounded buffers can exhaust memory.
- `onBackpressureDrop` discards items that cannot be accepted. This is appropriate only when losing data is acceptable to business logic.
- `onBackpressureLatest` retains only the newest item and discards older ones under overload. It suits certain continuously updating status streams, but is usually inappropriate for queries requiring every row to be processed.

R2DBC publishers follow the reactive demand model. Therefore, do not mechanically slap buffers or drop strategies onto repository queries. First determine which upstream does not support backpressure and whether data loss is permissible.

### 6.5. Watch Out for Memory-Growing Operators

Operators such as `collectList()`, `collectMap()`, `sort()`, or `buffer()` can hold large amounts of data in memory before emitting onward. Example:

```java
// May hold all results in memory.
customerRepository.findAll()
    .collectList();
```

If results are unbounded, collecting everything into a `List` can create memory pressure or `OutOfMemoryError`. Prefer processing item by item or in bounded batches. Only collect into a collection when size is bounded and the maximum data volume is well understood.

## 7. Fetch Size and How Drivers Read Data

Fetch size indicates how many rows the driver is hinted to retrieve in one read batch. In the R2DBC SPI, `Statement.fetchSize(int)` is a hint to the driver regarding fetch chunk size. It is not a limit on the total rows returned by the query.

Illustration at the R2DBC SPI level:

```java
connection.createStatement("SELECT id, name FROM customer ORDER BY id")
    .fetchSize(100)
    .execute();
```

Actual behavior depends on the driver and database. Some drivers may use cursors or chunked reading; others may ignore the hint or buffer data in their own way. Also check transaction and configuration requirements that a driver may impose for cursor usage.

In Spring Data R2DBC, high-level repository methods do not necessarily expose a uniform place to configure fetch size for every driver. If statement-level control is needed, check your driver's API and statement integration in your Spring Data version. Do not assume setting fetch size limits row counts or guarantees memory stays bounded at a fixed number.

## 8. Limiting Concurrent Queries with a Connection Pool

A connection pool controls how many connections are leased concurrently. With R2DBC Pool, maximum size and acquisition timeout can be configured:

```java
ConnectionPoolConfiguration configuration =
    ConnectionPoolConfiguration.builder(connectionFactory)
        .initialSize(2)
        .maxSize(20)
        .maxAcquireTime(Duration.ofSeconds(5))
        .maxIdleTime(Duration.ofMinutes(10))
        .build();

ConnectionPool pool = new ConnectionPool(configuration);
```

This snippet illustrates pool configuration; exact imports and `ConnectionFactory` setup depend on application configuration. `maxSize(20)` caps concurrent connections the pool can hand out. Once connections are exhausted, new requests must wait for a connection to be returned or hit `maxAcquireTime`.

Connection pools limit how many sessions the application opens to the database, not how many rows each query fetches. A single query can still read a huge amount of data. Conversely, too many tiny concurrent queries can still overload the server even if each fetches only a few rows.

When choosing `maxSize`, account for the database's connection limit, application instance count, other services, and administrative connections. Do not inflate the pool merely to reduce wait times if the database is already near capacity. Monitor active connections, idle connections, waiting requests, and acquisition time.

## 9. Transactions and Connection Hold Time

With reactive transaction management, a transaction is tied to subscribing and executing the reactive publisher. If a `@Transactional` method returns a long-lived `Flux`, the transaction can stay open for as long as the stream remains active. The connection used by the transaction can therefore be held for a long time.

For instance, if an API streams results to a slow-network client, slow consumption can prolong both reading and connection hold time. If a stream is abandoned or fails to terminate properly, resources can remain occupied longer than expected.

Ways to reduce risk:

- Limit row counts per query and split work into bounded batches.
- Avoid keeping a transaction open while waiting on external tasks or slow-reading clients.
- In background processing, read a batch, process it, save an appropriate checkpoint, and only then read the next batch.
- Ensure subscriptions terminate or are canceled when work is no longer needed.
- Verify how the transaction manager and driver release connections when a publisher completes, errors, or is canceled.

Transactions may be necessary to preserve business consistency. Keep transactions to the smallest scope that satisfies consistency requirements, while avoiding splitting transactions arbitrarily if doing so compromises business correctness.

## 10. Database-Layer Guardrails

Database-layer limits protect the system when queries run too long or consume excessive resources. Specific capabilities depend on the DBMS and version.

Common guardrail categories include:

- **Statement/query timeout:** limits how long a statement is allowed to execute.
- **Lock timeout:** limits lock wait duration, preventing a query from waiting indefinitely on a lock.
- **Connection limit:** caps total sessions or connections.
- **Resource governance:** limits or allocates CPU, memory, I/O, or concurrency per workload, user, or query group if supported by the database.
- **Access privileges:** run the application account with least privilege, restricting permitted operations and accessible schemas.

For example, PostgreSQL provides settings such as `statement_timeout` and `lock_timeout`; other database engines have their own mechanisms and syntax. Apply settings at the appropriate scope (session, role, database, or system) according to operational policy. Do not copy configuration verbatim from one DBMS to another.

Timeouts protect the system from runaway queries, though they do not replace query optimization. When a timeout triggers, the application should handle the error and verify whether the driver canceled the statement, rolled back the transaction, and returned the connection to the pool.

A SQL query with `LIMIT 20` can still consume heavy resources if it has to scan millions of rows or sort a huge dataset before finding 20 matching rows. Inspect execution plans and create indexes aligned with `WHERE` predicates, `ORDER BY` ordering, and joins. With PostgreSQL, `EXPLAIN` or `EXPLAIN (ANALYZE, BUFFERS)` can be used in an appropriate test environment; other database engines offer equivalent execution plan tools.

## 11. Combining Layers in a Processing Flow

A large-data reading flow can be structured across these steps:

1. The API receives a cursor and batch size, then validates the batch size within configured limits.
2. The repository runs a SQL query with a cursor predicate, stable `ORDER BY`, and `LIMIT`.
3. The driver reads results according to its capabilities; fetch size is treated only as a hint if supported.
4. The service processes each item or uses `flatMap` with bounded concurrency.
5. The connection pool limits how many queries can hold connections simultaneously.
6. The database enforces timeouts, connection limits, and appropriate guardrails.
7. The client uses the last row's cursor to request the next batch.

Flow diagram:

```text
Client sends cursor + batchSize
            |
            v
Service validates batchSize
            |
            v
Repository runs WHERE cursor + ORDER BY + LIMIT
            |
            v
R2DBC driver reads results as supported
            |
            v
Flux emits according to subscriber demand
            |
            v
Process with bounded concurrency
            |
            v
Return next cursor to client
```

The key takeaway is that each layer enforces a different kind of limit. `LIMIT` controls a query's result size; demand controls consumption rate; concurrency bounds active work; the pool bounds connections; database guardrails bound server-side execution time and resources.

## 12. Testing and Observability

Demand behavior at the Reactor layer can be tested with `StepVerifier`:

```java
StepVerifier.create(customerRepository.findByActiveTrue(), 0)
    .thenRequest(1)
    .expectNextCount(1)
    .thenCancel()
    .verify();
```

This example creates a subscriber requesting zero items initially, then requests one item and cancels the subscription. It verifies how the publisher responds to demand and cancellation at the reactive layer. It **does not prove** the database read strictly one row: the driver may have prefetched or buffered data. To inspect that, observe driver, cursor, query, and database behavior with appropriate tooling.

In operations, monitor:

- Rows returned, rows processed, and actual batch sizes.
- Query latency, connection wait time, and timeout counts.
- Active/idle connection counts, acquisition wait queues, and connection hold durations.
- Heap memory, GC activity, buffer sizes, and downstream latency.
- Database CPU, I/O, session count, lock waits, and execution plans.
- Canceled subscriptions and how the driver releases resources after cancellation.

Test with realistic data volumes and simulate slow downstream consumers. A query that finishes quickly over a few hundred rows in development does not prove it is safe against millions of rows in production.

## 13. Common Design Mistakes

| Practice | Consequence | Fix |
|---|---|---|
| Assuming `Flux` automatically limits total rows | Query can still scan/read the entire table | Add filter predicates and SQL limits |
| Using `limitRate(100)` as a result limit | Stream keeps emitting as new demand arrives | Use `LIMIT` or pagination when capping total rows |
| Using `take(n)` instead of SQL limits | Driver may already prefetch extra data | Push limits down into the SQL query |
| Calling `collectList()` on large queries | All results may land in the heap | Process row by row or in bounded batches |
| Using unbounded buffers | Memory grows when downstream slows down | Use natural backpressure or bounded buffers with overflow policies |
| Unbounded `flatMap` on large sources | Too many concurrent tasks and queries | Set appropriate concurrency and prefetch |
| Increasing pool size without measuring database load | Database can overload from too many sessions | Size pools within the overall connection budget |
| Using huge offsets for sequential scans | Row-skipping cost grows with page depth | Use keyset pagination where appropriate |
| Adding `LIMIT` without checking execution plans | Database may still scan or sort massive datasets | Optimize indexes, filters, and sort order |

## 14. Selection Principles

- Need to cap **total rows** of a query: use `LIMIT` or equivalent SQL syntax.
- Need to read a large dataset across multiple trips: prefer keyset pagination with a stable cursor.
- Need to throttle **consumption rate** in the pipeline: use Reactive Streams natural demand and consider `limitRate`.
- Need to cap concurrent asynchronous tasks: configure `flatMap` concurrency or use `concatMap` when sequential execution is required.
- Need to control **connection count**: configure the connection pool and monitor acquisition time.
- Need to prevent runaway queries or lock waits: configure database timeouts or equivalent DBMS controls.
- Need to cut data transfer and conversion overhead: select only needed columns and add appropriate indexes.
- Need to keep memory predictable: avoid collecting unbounded results and keep every buffer bounded.

Backpressure helps Spring Data R2DBC process data streams at the pace downstream can handle. SQL limits and database guardrails protect the system at the query and server levels. When these layers work together, applications can handle large datasets in a controlled manner while reducing the risks of memory exhaustion, connection starvation, and excessive database load.
