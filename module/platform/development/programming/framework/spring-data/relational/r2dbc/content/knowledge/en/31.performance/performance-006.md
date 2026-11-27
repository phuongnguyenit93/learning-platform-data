# Adjusting Fetch Size When Supported by the Driver

When an R2DBC query returns many rows, the application must balance memory usage, database round-trips, and consumption speed. Some drivers let the application provide a hint on how many rows to fetch per batch via `Statement.fetchSize(int)`. When the driver supports batched fetching, this setting helps control how much data the driver reads ahead and reduces memory pressure on large result sets.

`fetchSize` is a hint at the R2DBC statement layer—not a guarantee that the database sends exact row counts per network packet or that heap holds at most that many rows. Drivers may support it, interpret it differently, or ignore the hint altogether. Some drivers buffer entire results; others use cursors or custom streaming; others require an active transaction or extra connection options for batched fetching to work as expected.

Therefore, distinguish `fetchSize` from `LIMIT`, pagination, Reactive Streams backpressure, and write batching. `LIMIT` caps total rows returned by a query; `fetchSize` hints how the driver fetches the result set; backpressure regulates how many items a subscriber requests; write batching groups parameter sets or statements for execution. These mechanisms complement each other without replacing one another.

## 1. Why Tune Fetch Size?

Suppose a report must read several hundred thousand rows from an `event_log` table. If the driver loads and buffers the entire result set before emitting to the application, memory usage can spike sharply. When the driver supports batched fetching, the application can consume part of the result before the driver fetches more as needed.

Fetch size can influence:

- **Application memory:** how many rows/row buffers the driver holds ahead of emission.
- **Server round-trips:** small batches may increase fetch round-trips; larger batches reduce communication overhead.
- **Latency:** time until the first row arrives and delays between fetch batches.
- **Throughput:** rows processed per second when driver, network, and database leverage batched fetching.
- **Connection hold time:** streaming result sets may keep connections occupied longer while the application consumes data.

There is no single optimal fetch size for every query. Optimal values depend on row width, column count, network speed, database, driver, pool, downstream processing speed, and application concurrency.

### Example Scenarios

An endpoint displaying 25 recent customers does not need to read 100,000 rows and discard most of them. Use `ORDER BY` and `LIMIT` appropriately.

An export job traversing 500,000 events may not want to collect everything into a `List`. The job can stream a `Flux` and, if the driver supports it, configure fetch size to tune how the driver pulls rows from the server.

Both scenarios read data but solve different problems: `LIMIT` reduces total queried data; `fetchSize` tunes how result-set rows are retrieved.

## 2. `Statement.fetchSize(int)` in the R2DBC SPI

The R2DBC SPI defines `Statement.fetchSize(int rows)` as a hint to the driver regarding how many rows to retrieve per fetch when reading result sets. Call this method on the statement before `execute()`:

```java
Statement statement = connection.createStatement("""
        SELECT id, event_type, created_at
        FROM event_log
        WHERE tenant_id = ?
        ORDER BY id
        """);

statement.bind(0, tenantId);
statement.fetchSize(256);

Publisher<? extends Result> results = statement.execute();
```

`256` is an illustrative example, not a default or universal recommendation. A driver may use it as rows per fetch, treat it as a prefetch hint, or ignore it if unsupported.

### Fetch Size of 0

Per SPI semantics, `0` indicates no specific fetch size hint is set, leaving the driver to use its default. Do not interpret `0` as fetching zero rows or disallowing result sets. Negative values are invalid; check your SPI/driver documentation and validate inputs before building statements.

### It Is a Hint, Not a Hard Limit

Even after calling `fetchSize(256)`, do not assume:

- The database always transmits exactly 256 rows per network transfer.
- The driver never buffers more than 256 rows.
- Every downstream request for 256 elements triggers a database fetch of 256 rows.
- Application heap is capped at 256 objects.
- The query automatically uses a cursor or server-side streaming.

Actual behavior depends on driver implementation, protocol, server, and downstream operators. Treat `fetchSize` as an advisory setting to verify via integration tests and measurements.

## 3. How Fetch Size Differs from Other Mechanisms

| Mechanism | Where It Acts | What It Controls |
| --- | --- | --- |
| `Statement.fetchSize(n)` | R2DBC driver/statement | Hint for rows fetched per batch from a result set |
| SQL `LIMIT n` | Database query | Caps total rows returned by the query |
| `OFFSET` / keyset pagination | Database query and access pattern | Splits results into discrete pages |
| Reactive Streams `request(n)` | Publisher/subscriber | Number of items downstream is ready to receive |
| Reactor `limitRate(n)` | Reactor pipeline | Adjusts upstream request batching/prefetch |
| `buffer(n)` | Application/Reactor pipeline | Groups up to n items into a collection before emitting the collection |
| `collectList()` | Application | Accumulates all items into a single `List` |
| `Statement.add()` | R2DBC statement | Adds multiple parameter sets to the same write SQL statement |

For instance, `LIMIT 1000` and `fetchSize(100)` can work together: the database returns at most 1,000 rows, and the driver may fetch them in batches of roughly 100 rows if supported. Without `LIMIT`, fetch size does not cap total rows.

### Fetch Size Is Not Write Batch Size

`Statement.add()` and multi-row `INSERT` control sending multiple value sets for writes. `fetchSize` applies to reading result sets. Never use `fetchSize` expecting to batch inserts or updates.

## 4. Fetch Size and Reactive Streams Backpressure

Reactive Streams defines demand: subscribers call `request(n)` to signal readiness for up to n more items. Reactor propagates demand upstream according to operator semantics.

Example:

```java
Flux<EventView> events = databaseClient.sql("""
            SELECT id, event_type, created_at
            FROM event_log
            ORDER BY id
            """)
        .map((row, metadata) -> new EventView(
                row.get("id", Long.class),
                row.get("event_type", String.class),
                row.get("created_at", LocalDateTime.class)
        ))
        .all();
```

Subscribers can request a specific number of elements. However, the driver may prefetch or buffer part of the result set before downstream requests all those items. Fetch size influences how the driver pulls rows; demand signals capacity between subscriber and publisher. The two layers interact without being identical.

### Calling `limitRate` Does Not Set Fetch Size

```java
events.limitRate(128);
```

`limitRate` tunes upstream Reactor demand batching/prefetch. It does not necessarily call `Statement.fetchSize(128)` or ensure the driver uses a 128-row cursor. To control both layers, configure them separately per driver capabilities.

### Backpressure Does Not Eliminate Full Buffering Operators

Operators like `collectList()` actively accumulate all elements:

```java
Mono<List<EventView>> allEvents = events.collectList();
```

Even if the source fetches in batches, the full list eventually sits in memory. For large exports, process row by row or chunk by chunk and stream to the destination instead of calling `collectList()` on the whole result set.

## 5. Drivers Implement Fetch Size Differently

The R2DBC SPI provides a common API, yet execution behavior resides in each driver. Depending on the driver, fetch size may:

- Translate into server-side cursor or result-set configuration.
- Adjust how much data the driver requests or prefetches from the server.
- Take effect only under specific transaction or connection modes.
- Be ignored if the driver lacks a corresponding mechanism.
- Be clamped or interpreted according to driver-specific rules.

Do not infer support simply because the code compiles. If `fetchSize` has a default no-op implementation in a given SPI/driver version, calling it may produce zero runtime effect.

### Questions to Verify in Driver Documentation

Before enabling fetch size, answer:

1. Does the driver support `Statement.fetchSize(int)`?
2. Does it apply to all statements or only SELECT/result sets?
3. Does the driver use server-side cursors, server-side fetches, or client-side buffering?
4. Does it require an open transaction or `autoCommit` disabled?
5. Are special connection URL/options needed to enable streaming or cursors?
6. How are `0` and maximum values interpreted?
7. Does fetch size affect generated values or multiple result sets?
8. What happens if a subscriber cancels or times out mid-fetch?
9. Are there restrictions on prepared statements, scrollability, or large data types?
10. Which driver versions support this behavior?

If driver documentation does not guarantee support, leave the default or validate with real integration tests before enabling in production.

## 6. Setting Fetch Size at the R2DBC SPI Layer

When direct statement control is needed, call `fetchSize` prior to `execute()`:

```java
Statement statement = connection.createStatement("""
        SELECT id, name
        FROM customer
        WHERE status = ?
        ORDER BY id
        """);

statement.bind(0, "ACTIVE");
statement.fetchSize(200);

Flux<CustomerView> rows = Flux.from(statement.execute())
        .concatMap(result -> Flux.from(result.map((row, metadata) ->
                new CustomerView(
                        row.get("id", Long.class),
                        row.get("name", String.class)
                )
        )));
```

The example uses `?` placeholders illustrating positional bind markers; actual markers depend on the SQL dialect. `fetchSize(200)` must be invoked before `execute()`. Mapping row by row into a DTO allows downstream processing per item without building an in-memory `List` of the whole result set.

### Managing Connections When Using the SPI Directly

In Spring applications, do not call `ConnectionFactory.create()` arbitrarily when operations must join an active reactive transaction. Use `ConnectionFactoryUtils.getConnection(...)` to obtain the transaction-bound connection and release it via the matching helper:

```java
public Flux<CustomerView> streamActiveCustomers(int fetchSize) {
    if (fetchSize < 0) {
        return Flux.error(new IllegalArgumentException(
                "fetchSize must not be negative"
        ));
    }

    return Flux.usingWhen(
            ConnectionFactoryUtils.getConnection(connectionFactory),
            connection -> {
                Statement statement = connection.createStatement("""
                        SELECT id, name
                        FROM customer
                        WHERE status = ?
                        ORDER BY id
                        """);

                statement.bind(0, "ACTIVE");
                if (fetchSize > 0) {
                    statement.fetchSize(fetchSize);
                }

                return Flux.from(statement.execute())
                        .concatMap(result -> Flux.from(result.map(
                                (row, metadata) -> new CustomerView(
                                        row.get("id", Long.class),
                                        row.get("name", String.class)
                                )
                        )));
            },
            connection -> ConnectionFactoryUtils.releaseConnection(
                    connection, connectionFactory
            ),
            (connection, error) -> ConnectionFactoryUtils.releaseConnection(
                    connection, connectionFactory
            ),
            connection -> ConnectionFactoryUtils.releaseConnection(
                    connection, connectionFactory
            )
    );
}
```

This is a skeleton SPI example; declare `connectionFactory`, DTOs, and imports accordingly. When `fetchSize` is 0, the example skips calling the method so the driver uses its default. `usingWhen` handles release on completion, error, and cancellation. When the connection belongs to a Spring-managed transaction, `ConnectionFactoryUtils.releaseConnection` preserves transaction-manager ownership; outside a transaction, the helper releases the acquired connection.

When direct SPI control is unnecessary, prefer `DatabaseClient` or repositories to stay within Spring Data abstractions.

## 7. Configuring via `DatabaseClient` When Spring Supports Filters

Some Spring Framework versions offer `StatementFilterFunction` on `DatabaseClient.Builder`. A filter can customize statements before execution:

```java
DatabaseClient client = DatabaseClient.builder()
        .connectionFactory(connectionFactory)
        .filter((statement, next) -> {
            statement.fetchSize(200);
            return next.execute(statement);
        })
        .build();
```

Filter APIs and setup can differ across Spring Framework versions. Check the Javadoc for `DatabaseClient.Builder` and `StatementFilterFunction` in your project's version before using it. This filter applies only to statements executed through that configured client; it does not apply to another `DatabaseClient` constructed by separate infrastructure.

### Filter Scope

A builder-level filter can affect all statements issued by that client, including non-read statements. If you only want fetch size on SELECTs, identify matching statements reliably per your API version and project SQL conventions. Do not blindly enforce a global fetch size on inserts or updates.

If the client backs `R2dbcEntityTemplate` or repositories, ensure those components actually use the configured client. Registering an extra `DatabaseClient` bean does not mean Spring Data repositories automatically adopt it.

### When No Suitable Filter API Exists

If your Spring version lacks the needed filter mechanism, options include:

- Using R2DBC SPI directly for queries requiring fetch size, with proper connection management.
- Using driver-level connection configuration if provided by the driver.
- Encapsulating statement handling behind a dedicated query/adapter abstraction.
- Upgrading Spring Framework or the driver after compatibility testing.

Avoid using reflection to reach `DatabaseClient` internals or mutate statement state after execution.

## 8. Choosing a Fetch Size Value

Small and large fetch sizes present different trade-offs.

| Fetch Size | Potential Benefits | Potential Costs / Risks |
| --- | --- | --- |
| Small | Less prefetched data; lower buffer and memory pressure | More fetch round-trips and communication overhead |
| Medium | Balances memory and fetch count | Requires measuring against row width and workload |
| Large | Fewer exchanges and higher throughput | Larger buffers, higher memory, data fetched ahead of demand |
| 0 / default | Uses driver's default strategy | No explicit control from application code |

Do not pick fetch size based solely on row count. A row with a few small integers differs drastically from one holding large JSON, long text, or binary payloads. Factor in average row byte size and concurrent result sets.

### Finding a Starting Point

Start benchmarking with a few well-spaced values such as 32, 128, 512, and the driver default. These are test starting points, not universal standards. For each value, measure:

- Time to first row.
- Total duration to read the entire result set.
- Row throughput per second.
- Heap usage and allocation rate.
- Fetch/round-trip counts if exposed by driver metrics or logs.
- Connection hold time and pool pending acquires.
- Application and database CPU.

Pick the value based on realistic workloads and latency/memory constraints—not a single test run.

## 9. Row Width and Real Memory Footprint

Suppose each decoded and mapped row averages roughly 2 KB on the heap; 500 prefetched rows represent around 1 MB of object payload, before counting object headers, byte buffers, metadata, queues, and other publishers. If each row carries a 100 KB JSON document, the same fetch size of 500 creates far greater memory pressure.

Fetch size alone does not bound total application memory. Account for:

- Network/protocol buffers.
- Driver internal buffers.
- `Row`/metadata and mapped domain objects.
- Reactor operator prefetch queues.
- Queues from `flatMap` concurrency.
- Collections from `buffer`, `collectList`, or caching.
- Number of concurrent queries running simultaneously.

For example, if 20 concurrent requests each stream 10,000 rows while the driver prefetches 500 rows per request, retained memory can become substantial. Actual memory footprint must be measured with the real driver and a heap profiler; multiplying row counts is only an initial rough estimate.

### Select Only Needed Columns

Avoid `SELECT *` on large streaming queries when downstream only needs a few columns:

```sql
SELECT id, event_type, created_at
FROM event_log
WHERE tenant_id = :tenantId
ORDER BY id;
```

Shrinking row payloads lowers network traffic, decode cost, and heap allocations. If a query needs a large JSON/binary column, fetch it only when the consumer truly requires it.

## 10. Streaming Result Sets Do Not Mean Zero Memory Usage

Even when a driver streams results, downstream operators can still accumulate data:

```java
// Still holds the entire result in a List.
return repository.findAll()
        .collectList();
```

Or build large queues via high concurrency or prefetch:

```java
return repository.findAll()
        .flatMap(this::enrich, 64);
```

`flatMap` can maintain many active inner publishers and operator prefetch buffers. If `enrich` is slow, pending queues and in-flight results grow. Tune concurrency and prefetch separately alongside driver fetch size.

A pipeline can maintain lower memory by processing sequentially or with tightly bounded concurrency:

```java
return repository.findAll()
        .concatMap(this::processOne);
```

When parallelism is needed, choose modest concurrency and measure queues/heap. Fetch size does not substitute for concurrency control.

## 11. Fetch Size and LIMIT / Pagination

When users ask for a single page of data, limit rows directly in SQL:

```sql
SELECT id, name
FROM customer
WHERE status = :status
ORDER BY id
LIMIT :pageSize OFFSET :offset;
```

There is no reason to raise fetch size to thousands if the query returns 20 rows. A fetch size larger than the total row count yields no extra rows; it only affects driver behavior if supported.

### Traversing Large Datasets via Keyset Pagination

For jobs scanning an entire table, keyset pagination avoids deep offsets:

```sql
SELECT id, event_type, created_at
FROM event_log
WHERE id > :lastId
ORDER BY id
LIMIT :chunkSize;
```

After each chunk, save the last row's `lastId` and issue the next query. Primary-key indexing enables fast ID seeking. This caps rows per query and can release connections between chunks, depending on pipeline design.

Fetch size may still help inside each chunk query if supported by the driver, though when `LIMIT` is already small, gains may be minor. Choose between one long-lived streaming cursor and multiple short chunk queries based on snapshot consistency requirements, connection hold times, and job resumability.

## 12. Fetch Size and Transactions

Some drivers only activate cursor-based fetching when the connection is inside a transaction or when auto-commit is disabled. This is driver-specific; there is no single universal rule across all R2DBC databases.

If a driver requires a transaction:

- Ensure the query executes within an appropriate reactive transaction.
- Never call `subscribe()` manually and detach the query from transaction context.
- Keep transactions no longer than necessary.
- Consume the result set completely or cancel the publisher properly so cursors/resources are freed.
- Check isolation and snapshot semantics if data changes while streaming.

Long transactions hold connections, locks, or snapshots longer; on MVCC databases, prolonged old snapshots increase maintenance overhead. If per-row processing is slow, holding a cursor/transaction open for a long time impacts both the pool and the database.

### Long Reads with Slow Processing

Example pipeline:

```java
return databaseClient.sql("SELECT id, payload FROM event_log ORDER BY id")
        .map((row, metadata) -> mapEvent(row))
        .all()
        .concatMap(event -> callSlowExternalService(event));
```

If each event invokes a slow external service, the cursor and connection can remain pinned throughout consumption. Consider reading in chunks, recording checkpoints, and closing the query before performing slow external work. Never hold a database transaction open while waiting on external HTTP calls unless strict consistency requires it.

## 13. Cancellation and Resource Cleanup

Subscribers may cancel streams due to timeouts, client disconnects, or partial reads. Drivers must observe cancellation to close cursors or release protocol resources as supported.

Example taking only the first 10 rows:

```java
return databaseClient.sql("SELECT id, payload FROM event_log ORDER BY id")
        .map((row, metadata) -> mapEvent(row))
        .all()
        .take(10);
```

`take(10)` cancels upstream once 10 items arrive. Whether the server halts immediately or the driver already prefetched extra rows depends on the driver. A smaller `fetchSize` can shrink prefetched excess in some drivers, yet it does not replace proper cancellation.

When using R2DBC SPI directly, handle connection cleanup across all three terminal paths: complete, error, and cancel. `usingWhen` declares asynchronous cleanup cleanly. With Spring `DatabaseClient`/repositories, the framework manages resources along the publisher lifecycle; never manually close connections owned by the framework.

## 14. Fetch Size and Connection Pools

A streaming result set usually occupies a connection for as long as the publisher stays active. If subscribers hold connections for extended periods, the pool can exhaust even without query errors.

Monitor:

- Acquired connections.
- Idle connections.
- Pending acquire requests.
- Connection acquire duration.
- Time from `execute` to complete/cancel.
- Concurrent open streams.
- Downstream processing time per row/chunk.

Large fetch sizes reduce fetch round-trips while raising prefetch buffering; small fetch sizes trim buffers while prolonging queries due to more fetches. Both affect connection hold times depending on driver and downstream speed.

Do not raise pool `maxSize` solely to mask long-lived streams holding connections. First inspect hold times, concurrency, query latency, and consumption speed. For massive exports, move jobs out of HTTP request/response cycles into concurrency-bounded workers.

## 15. Combining Fetch Size with `DatabaseClient`

`DatabaseClient` provides a reactive API for reading results as a `Flux`. Typical example:

```java
Flux<EventView> streamEvents(UUID tenantId) {
    return databaseClient.sql("""
                SELECT id, event_type, created_at
                FROM event_log
                WHERE tenant_id = :tenantId
                ORDER BY id
                """)
            .bind("tenantId", tenantId)
            .map((row, metadata) -> new EventView(
                    row.get("id", Long.class),
                    row.get("event_type", String.class),
                    row.get("created_at", LocalDateTime.class)
            ))
            .all();
}
```

`.all()` returns a `Flux` for multi-row consumption. This API by itself implies no specific fetch size. When the driver supports fetch size, configure statements through the API provided by your Spring version or via direct SPI.

### Statement Filters on DatabaseClient

In Spring Framework versions offering `DatabaseClient.Builder.filter(StatementFilterFunction)`, configure:

```java
DatabaseClient client = DatabaseClient.builder()
        .connectionFactory(connectionFactory)
        .filter((statement, next) -> {
            statement.fetchSize(256);
            return next.execute(statement);
        })
        .build();
```

This applies to statements executed by the built client. Verify the API exists in your Spring Framework version and that the controlled component actually uses that client. Passing this client into `R2dbcEntityTemplate` lets the template apply the filter; repository factories must be configured with the same infrastructure for repositories to inherit it.

Do not assume `@Query` offers a portable `fetchSize` attribute across all Spring Data R2DBC versions. Check your version's API; if absent, use a `DatabaseClient` filter or SPI inside an appropriate adapter.

## 16. Combining Fetch Size with Repositories

Repository methods can return `Flux<T>`:

```java
public interface EventRepository
        extends ReactiveCrudRepository<Event, Long> {

    Flux<Event> findByTenantIdOrderById(UUID tenantId);
}
```

Repository APIs focus on queries and mapping and do not always expose fetch size directly in method signatures. When a specific large query needs custom fetch size:

- Check whether your Spring Data R2DBC version provides statement customization hooks.
- Use a dedicated `DatabaseClient` configured with a filter for export queries.
- Use R2DBC SPI inside a specialized adapter for fine statement control.
- Keep repositories for standard CRUD/queries instead of applying a large global fetch size if only a few queries need it.

Example dedicated adapter interface:

```java
public interface EventExportReader {
    Flux<EventView> streamEvents(UUID tenantId, int fetchSize);
}
```

Services depend on `EventExportReader` without knowing about driver or connection details. The adapter implements it via a `DatabaseClient` filter or SPI per driver capabilities, keeping business logic decoupled from driver-specific APIs.

## 17. Fetch Size with Multiple Result Sets

A statement can produce one or more `Result` objects depending on the SQL and driver. Distinguish between:

- Rows within a single result set.
- `Result` instances emitted by `Statement.execute()`.
- Whether fetch size applies per result set or via driver-specific rules.

Do not assume `fetchSize(n)` caps total rows across an entire statement if it returns multiple result sets. Read driver documentation and consume `Result` objects using the proper API.

Normal SELECT queries typically yield one result set. Stored procedures or multi-statement batches can have subtler semantics. Test streaming large outputs from stored procedures separately rather than extrapolating from simple SELECTs.

## 18. Fetch Size and Large Payloads (BLOB/CLOB/JSON)

When rows carry heavy payloads, row count per fetch batch understates buffer footprint. Fetching 100 tiny metadata rows differs drastically from fetching 100 multi-megabyte images or JSON documents.

Considerations:

- Select payload columns only when actually needed.
- If the driver supports streaming LOB reads, learn the exact LOB API and lifecycle; do not assume every codec streams payloads.
- Avoid materializing large payloads into full objects or `byte[]` arrays unless downstream truly needs the entire payload at once.
- Cap concurrent streams.
- Measure peak heap and direct memory, not just post-GC heap.
- Enforce timeouts and cleanup when clients cancel mid-payload.

Smaller fetch sizes trim prefetched row counts, yet a single huge row can still consume substantial memory. Control both payload size and driver decoding behavior.

## 19. Benchmarking to Select Fetch Size

Never choose fetch size using mock benchmarks like `Flux.just(...)`; measure against the real database and driver. Benchmark plan:

1. Seed data with production-like row counts and column widths.
2. Execute the exact same query, ordering, and indexes across candidate fetch sizes.
3. Keep downstream pipelines identical—do not compare `collectList()` in one run against row-by-row streaming in another.
4. Measure time to first row and total completion time.
5. Measure row throughput, heap, direct memory, allocation rates, CPU, and GC.
6. Observe connection pool metrics, query duration, and database load.
7. Repeat multiple runs, including warm-up and concurrent workloads.
8. Include the driver default as a baseline.
9. Confirm the driver actually honors fetch size rather than silently ignoring the API call.
10. Pick a value satisfying latency and memory goals, then test under production-like concurrency.

### Metrics to Compare

| Metric | Why It Matters |
| --- | --- |
| Time to first row | Impacts initial responsiveness and start of processing |
| Total query/stream duration | Measures time to finish all work |
| Rows per second | Measures read throughput |
| Peak heap/direct memory | Exposes oversized buffers or payloads |
| GC pauses/allocation rate | Reveals object creation cost and GC pressure |
| Fetch/round-trip count | Evaluates network chatter when exposed by driver |
| Connection hold time | Evaluates pool impact |
| Pool pending acquire | Catches connection starvation during long streams |
| Database CPU/I/O | Prevents client optimizations from overloading the server |

## 20. Testing Fetch Size

`TestPublisher` verifies downstream demand and cancellation logic, yet it proves nothing about real batched fetching by the driver. Fetch size is an R2DBC statement/driver behavior requiring integration tests against the target database.

### Verifying Statement Configuration

If using a custom wrapper or adapter managing statements, unit test it with a mocked `Statement` to confirm `fetchSize(n)` is invoked before `execute()`. This verifies the API call only—not driver batching behavior.

Conceptual example:

```java
verify(statement).fetchSize(256);
verify(statement).execute();
```

Do not mock the entire driver and claim memory is bounded. Buffering and cursor behavior can only be verified with the real driver.

### Integration Tests with the Real Driver

Verify:

- Queries return all rows when fetch size is smaller than total row count.
- Row mapping and ordering remain intact.
- Publishers consume the entire result set cleanly.
- Cancellation releases cursors/connections as supported by the driver.
- Transaction boundaries behave properly if the driver requires a transaction for cursors.
- Connection pools do not leak connections after complete, error, or cancel.
- Driver logs/metrics or server observations confirm expected fetching when observability tools exist.

Not every driver exposes fetch-batch counts. When direct observation is unavailable, combine driver documentation, load tests, and memory profiling while noting the limits of available evidence.

## 21. Common Pitfalls

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| Calling `fetchSize` yet heap still grows | Driver ignores hint, buffers elsewhere, or downstream accumulates data | Verify driver behavior and remove `collectList`/large queues |
| Entire result still loads upfront | Driver does not use cursors/streaming or lacks required options | Check driver documentation and connection options |
| Small fetch size slows queries | Too many fetch round-trips | Benchmark larger values and measure network latency |
| Large fetch size causes memory pressure | Too many rows/payloads prefetched | Lower fetch size, concurrency, or selected columns |
| Cursors fail to activate | Driver requires an active transaction or connection option | Review driver cursor prerequisites |
| Connection pool drains | Long streams hold connections while downstream is slow | Shorten streams, split into chunks, or cap concurrency |
| Mid-stream timeouts | Slow query/fetch or overly tight deadline | Tune timeouts and handle cancellation |
| Resources remain held after cancel | Broken driver/adapter cleanup or missing `usingWhen` in raw SPI | Inspect driver and ensure cleanup on complete/error/cancel |
| `limitRate` fails to alter fetch behavior | Reactor demand differs from statement fetch size | Configure driver statement separately |
| High `LIMIT` still consumes lots of memory | Total returned rows remain large | Reduce LIMIT, paginate, or stream/chunk |
| `collectList()` still triggers OOM | Full result set retained in heap | Process row by row or chunk by chunk instead of collecting all |
| Repository lacks a fetch-size property | Abstraction does not expose statement hints in that API | Use `DatabaseClient` filter or SPI adapter per version |
| Filter API fails to compile | Spring Framework version lacks the API or uses a different signature | Check Javadoc for exact version; use SPI/driver config |

## 22. Fetch Size Tuning Workflow

1. Determine whether the query has a large result set requiring streaming or only needs a small page.
2. Use SQL `LIMIT`/keyset pagination if the use case does not need the entire result set at once.
3. Check whether the R2DBC driver supports `Statement.fetchSize(int)` or another fetch mechanism.
4. Review driver prerequisites regarding transactions, cursors, auto-commit, and connection options.
5. Choose where to configure it: direct SPI, `DatabaseClient` statement filter if supported by Spring, or driver-specific API.
6. Avoid accumulating full results via `collectList()` on large datasets.
7. Bound downstream concurrency/prefetch and concurrent open streams.
8. Measure small, medium, large, and driver-default fetch sizes on realistic data.
9. Inspect time-to-first-row, throughput, memory, round-trips, and connection hold time.
10. Integration-test complete, error, and cancel paths to confirm cleanup.
11. Record driver/server versions alongside chosen values for reproducibility.

## 23. Key Takeaways

- `Statement.fetchSize(int)` is an R2DBC SPI hint for rows fetched per batch; drivers may honor or ignore it.
- Fetch size does not cap total rows; SQL `LIMIT` caps result set size.
- Fetch size differs from Reactive Streams demand, `limitRate`, `buffer`, `collectList`, and write batching.
- Never assume `fetchSize(256)` means the database sends 256 rows per packet or heap only holds 256 rows.
- Cursor/streaming behavior, transaction prerequisites, and connection options depend on the driver, database, and version.
- Small fetch sizes can shrink prefetch at the cost of more round-trips; large fetch sizes can boost throughput while increasing buffering.
- Row width and JSON/BLOB/CLOB payloads matter just as much as row counts.
- `collectList()` still materializes the full result even when the driver fetches in batches.
- `limitRate` adjusts Reactor demand, not `Statement.fetchSize`.
- In Spring `DatabaseClient`, use `StatementFilterFunction` only when supported by your Spring version and ensure the configured client backs the target component.
- When using R2DBC SPI directly in Spring, obtain connections via `ConnectionFactoryUtils` and release them across complete, error, and cancel.
- Streaming result sets can pin connections longer; monitor pool metrics, transaction duration, and downstream speed.
- Use integration tests with the real driver and database to verify fetch behavior; `TestPublisher` only checks reactive pipeline signals.
- Benchmark on production-like data, measuring time-to-first-row, throughput, heap, GC, round-trips, and connection hold times before finalizing values.

Tuning fetch size is only effective when the driver actually supports batched result-set fetching. Start from query requirements, verify driver capabilities, configure at the proper statement layer, and keep downstream pipelines from accumulating unnecessary data. Finally, measure against your production-equivalent database and driver to pick a value balancing memory, round-trips, throughput, and connection hold times.
