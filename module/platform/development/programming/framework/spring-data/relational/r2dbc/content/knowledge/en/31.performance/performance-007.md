# Avoiding Collecting Large Flux Streams into Memory

In Spring Data Relational R2DBC, repositories, `R2dbcEntityTemplate`, and `DatabaseClient` commonly return `Flux<T>` for multi-row queries. `Flux` lets applications process data as a stream and propagate backpressure across layers. However, using `Flux` does not automatically guarantee bounded memory. A single operator such as `collectList()`, `sort()`, `cache()`, or an unbounded buffer can force the application to hold the entire result set in the heap.

On large tables, collecting all rows into a `List` causes heap usage to scale with row count, generates temporary objects, increases garbage collection overhead, and can eventually trigger `OutOfMemoryError`. The solution is to keep data streaming when appropriate, explicitly bound all buffers, process in finite batches, or push filtering and aggregation down to the database. When full data retrieval is needed, design paginated exports or background jobs instead of materializing an entire result set inside one request.

## 1. Flux Does Not Imply Unbounded Memory Safety

An R2DBC query can return `Flux<Customer>`:

```java
Flux<Customer> customers = customerRepository.findAll();
```

This publisher represents a stream of items. If downstream consumes items one by one and operators keep buffered state bounded, the application can process large datasets without holding all rows simultaneously.

However, the following materializes the entire result:

```java
Mono<List<Customer>> customers = customerRepository.findAll()
    .collectList();
```

`collectList()` must wait for the source to complete and store every element in a `List` before emitting it. If the query returns a million rows, the list and all corresponding `Customer` objects coexist on the heap.

Therefore, distinguish between:

- **Streaming:** items are processed as they arrive, with bounded in-flight data.
- **Materialization:** consuming the source and retaining results in a structure such as a `List`, `Map`, or array.
- **Buffering:** holding items awaiting processing; buffers can be bounded or unbounded.
- **Aggregation:** computing summary results. This can run in the database or in the application; where it runs heavily impacts memory.

## 2. Why Collecting Large Fluxes Creates Memory Pressure

Suppose each mapped row occupies a certain amount of memory across entities, strings, collections, and helper objects. Total memory exceeds raw database storage size: inside the JVM, each row becomes objects with headers, references, and internal structures.

Factors driving heap growth:

- Number of materialized rows.
- Row width and number of columns selected.
- Nested child objects, strings, and collections inside entities.
- Reactor, driver, and HTTP server buffers.
- Number of concurrent requests materializing data simultaneously.
- Intermediate copies created during mapping, sorting, grouping, or serialization.
- Reference lifetimes preventing the garbage collector from reclaiming objects.

For example, one request loading an entire table builds a `List<Customer>`. When multiple such requests run concurrently, heap usage multiplies by the total rows across all requests—not just one.

A useful estimation:

\[
\text{Retained heap} \approx
\text{Retained item count} \times
\text{Average object size}
\]

This is only an initial estimate. Actual footprint depends on JVM internals, object graphs, string encoding, collection capacities, buffers, and copies. Measure with a profiler or heap dump on representative data.

### 2.1. Concurrent Requests Amplify the Problem

If one request retains 100 MB and ten requests run simultaneously, the application may retain around 1 GB solely for materialized results, excluding baseline application heap. This creates GC pressure, raises latency, and degrades unrelated requests.

Do not judge memory safety by running a single request locally. Account for production data volumes and expected concurrency.

## 3. collectList() Is the Most Common Materialization Point

`collectList()` converts `Flux<T>` into `Mono<List<T>>`:

```java
Mono<List<Customer>> loadAllCustomers() {
    return customerRepository.findAll()
        .collectList();
}
```

The publisher emits the `List` only after the source completes. Throughout execution, the list grows and retains references to every received element.

### 3.1. Never Use collectList() on Unbounded Tables

Avoid:

```java
public Mono<List<Order>> findAllOrders() {
    return orderRepository.findAll()
        .collectList();
}
```

As the `orders` table grows over time without an API cap, memory usage grows right along with it. An endpoint that works fine at a few thousand rows can crash once data reaches millions of rows.

Return `Flux<Order>` if callers can process row by row:

```java
public Flux<Order> streamOrders() {
    return orderRepository.findAll();
}
```

Or provide a paginated API with a strict maximum page size if callers require a bounded result set.

### 3.2. collectList() Still Fits Small Bounded Datasets

You do not need to ban `collectList()` completely. It remains suitable when:

- Results are bounded by `LIMIT` or page size.
- Dataset size is small and enforced by the API contract.
- An algorithm genuinely needs all elements of a small group at once.
- A transaction/query completes before the list passes to the next layer.

Example:

```java
public Mono<List<CustomerSummary>> findCustomerPage(int pageSize) {
    int boundedSize = Math.min(Math.max(pageSize, 1), 100);

    return databaseClient.sql("""
            SELECT id, name
            FROM customer
            ORDER BY id
            LIMIT :pageSize
            """)
        .bind("pageSize", boundedSize)
        .map((row, metadata) -> new CustomerSummary(
            row.get("id", Long.class),
            row.get("name", String.class)
        ))
        .all()
        .collectList();
}
```

Here the list is capped at 100 elements. Set the cap based on DTO size and realistic response budgets.

### 3.3. Do Not Limit Only at the Flux Layer If SQL Still Reads Too Much

Example:

```java
return customerRepository.findAll()
    .take(100);
```

`take(100)` cancels upstream after 100 items, yet the driver may have already prefetched more data depending on implementation. The database may also execute an unbounded query. When a use case needs at most 100 rows, push the limit into SQL:

```sql
SELECT id, name
FROM customer
ORDER BY id
LIMIT 100;
```

You can keep `take(100)` as an extra safeguard, but `LIMIT` communicates intent directly to the database and minimizes work generated and read.

## 4. Other Operators That Can Retain Full Datasets

`collectList()` is not the only culprit. Understand the memory semantics of pipeline operators.

| Operator | Memory Behavior | Notes |
|---|---|---|
| `collectList()` | Retains all items in a `List` | Do not use on large unbounded sources |
| `collectMap()` | Retains all entries in a `Map` | Key count can scale with rows |
| `collectMultimap()` | Retains all values per key | Can hold even more objects than `collectMap()` |
| `sort()` | Collects all items before sorting | Use SQL `ORDER BY` in the database whenever possible |
| `cache()` | Caches emitted signals for future subscribers | Caching large Fluxes retains data long-term |
| `replay()` | Stores signals for replay per configuration | Bound size or time if used |
| `distinct()` | Maintains a set of seen keys | Set can grow unboundedly |
| `buffer()` | Groups items into collections | Must bound by count or duration |
| `groupBy()` | Creates groups holding state/queues | High cardinality can exhaust memory |
| `window()` | Creates inner Flux windows per boundary | Must consume windows properly; avoid unbounded windows |
| `reduce()` | Holds an accumulator | Memory stays small only if accumulator size is fixed |

### 4.1. sort() Usually Needs the Entire Source

Avoid:

```java
return customerRepository.findAll()
    .sort(Comparator.comparing(Customer::getName));
```

To sort all rows, Reactor must buffer all items before emitting in order. When the database can sort, use `ORDER BY` with a matching index:

```sql
SELECT id, name
FROM customer
ORDER BY name, id
LIMIT :pageSize;
```

The database can leverage indexes or external sorting algorithms. Even when the database expends resources sorting, the application avoids holding all Java objects on the heap.

### 4.2. cache() Can Retain Data Past Request Completion

By default, `Flux.cache()` can retain emitted signals for subsequent subscribers. If the source is an entire table, the cache can pin the full result in memory for the lifetime of the publisher.

Avoid:

```java
private final Flux<Customer> allCustomers = customerRepository.findAll()
    .cache();
```

When caching is needed, bound the dataset, use a cache with explicit TTL/size limits, or choose a dedicated cache with an eviction policy. Define invalidation for database mutations.

### 4.3. distinct() Grows State with Distinct Value Count

```java
return eventRepository.findAll()
    .distinct(Event::getExternalId);
```

`distinct` tracks seen keys to filter duplicates. If the source is huge and nearly all keys are unique, retained state scales with row count. If the database can deduplicate:

```sql
SELECT DISTINCT external_id
FROM event
ORDER BY external_id;
```

consider pushing deduplication to the database and verifying the execution plan and indexes.

## 5. Buffers Must Be Bounded

Buffering is useful for grouping items into batches, provided element counts or time windows are bounded.

### 5.1. buffer(n)

```java
return customerRepository.findAll()
    .buffer(200)
    .concatMap(customerBatch -> processBatch(customerBatch));
```

Each list holds at most 200 items. `concatMap` processes batches sequentially, bounding concurrent in-flight batches in this branch. Still account for operator prefetch and upstream/driver buffers.

### 5.2. bufferTimeout(maxSize, maxTime)

When batches should emit upon hitting a count or a timeout:

```java
return source.bufferTimeout(
        200,
        Duration.ofSeconds(1)
    )
    .concatMap(this::processBatch);
```

Batches emit at 200 items or after one second per operator semantics. This avoids holding partial batches indefinitely when the source emits slowly.

### 5.3. Avoid Unbounded Buffers

Avoid:

```java
return source.onBackpressureBuffer();
```

If the producer outpaces the consumer over time, an unbounded buffer grows until heap exhaustion. Prefer letting backpressure propagate upstream. When buffering is truly required, set a fixed capacity and specify overflow behavior: fail, drop, or handle explicitly.

Never silently drop records in database write paths, payments, or events requiring guaranteed delivery. Overflow policies must match data semantics.

## 6. Preserving Backpressure Throughout the Pipeline

Reactive Streams allows downstream to request items according to capacity. When consumers slow down, upstream can throttle emission if every stage honors backpressure.

Sequential processing example:

```java
return customerRepository.findAll()
    .concatMap(customer -> processCustomer(customer));
```

`concatMap` completes the active inner publisher before moving to the next element. This caps concurrent active tasks, though operator prefetch may still queue a small number of pending items.

With `flatMap`, set a finite concurrency limit:

```java
return customerRepository.findAll()
    .flatMap(customer -> processCustomer(customer), 8);
```

The limit `8` caps active inner publishers for that overload. It does not mean total memory holds only eight rows: inner publishers, prefetch queues, drivers, and downstream may hold separate buffers.

### 6.1. flatMapSequential Can Also Buffer Pending Results

`flatMapSequential` runs inner publishers concurrently while emitting results in source order. If the first inner publisher stalls while subsequent ones finish fast, later results queue up waiting to emit. Tune concurrency and prefetch carefully, or switch to `concatMap` if strict sequentiality outweighs parallelism.

### 6.2. publishOn Uses a Prefetch Queue

`publishOn` switches downstream execution to another scheduler and maintains a prefetch queue:

```java
return customerRepository.findAll()
    .publishOn(Schedulers.parallel(), 32)
    .map(this::calculateView);
```

The queue decouples pacing across schedulers while holding items in memory. Size prefetch according to object size and throughput; never raise prefetch simply to mask a slow consumer.

### 6.3. Backpressure Does Not Eliminate Driver Buffering

R2DBC drivers and database protocols may prefetch or buffer rows. A subscriber requesting one element does not map 1:1 to a network round trip or a single row transmitted by the database. Check driver fetch/cursor behavior and configure `fetchSize` if supported.

`Statement.fetchSize(int)` in the R2DBC SPI is an advisory hint to the driver; drivers may ignore or interpret it differently. It neither replaces query limits/pagination nor bounds application memory if downstream operators materialize the whole stream.

## 7. Using reduce() When the Accumulator Has Fixed Size

When only an aggregated result is needed, avoid collecting rows just to reduce in Java.

Avoid:

```java
return orderRepository.findAll()
    .collectList()
    .map(orders -> orders.stream()
        .map(Order::getTotal)
        .reduce(BigDecimal.ZERO, BigDecimal::add));
```

This retains every `Order` on the heap even though the final answer is a single total.

Use `reduce` with a fixed-size accumulator:

```java
return orderRepository.findAll()
    .map(Order::getTotal)
    .reduce(BigDecimal.ZERO, BigDecimal::add);
```

Here the accumulator holds only a single `BigDecimal` at a time. Better yet, when aggregation can run in the database, push it into SQL:

```sql
SELECT COALESCE(SUM(total), 0) AS total_amount
FROM orders
WHERE status = :status;
```

The database returns one row instead of transferring every order over the network and allocating Java objects.

### 7.1. reduce() Can Still Grow Memory

Accumulators are not automatically small. For example:

```java
return source.reduce(
    new ArrayList<Customer>(),
    (list, customer) -> {
        list.add(customer);
        return list;
    }
);
```

This still collects the entire stream into a list. Evaluate the accumulator's growth, not merely the operator's name.

### 7.2. Choosing Database Aggregates

Operations well suited for SQL:

| Need | SQL |
|---|---|
| Row count | `COUNT(*)` |
| Sum | `SUM(amount)` |
| Average | `AVG(amount)` |
| Min/max | `MIN(value)`, `MAX(value)` |
| Grouping by status | `GROUP BY status` |
| Deduplication | `DISTINCT` |
| Existence check | `EXISTS (...)` |
| Top N | `ORDER BY ... LIMIT N` |

Example with `DatabaseClient`:

```java
Mono<Long> countPendingOrders() {
    return databaseClient.sql("""
            SELECT COUNT(*) AS total
            FROM orders
            WHERE status = :status
            """)
        .bind("status", "PENDING")
        .map((row, metadata) -> row.get("total", Long.class))
        .one();
}
```

The database still uses resources to compute the aggregate, yet the application receives only a compact result. Inspect execution plans and indexes when aggregating large tables.

## 8. Using Projections Instead of Loading Full Entities

When only a few columns are needed, avoid reading every column of a wide entity.

Unnecessary:

```java
return customerRepository.findAll()
    .map(customer -> customer.getEmail());
```

If the entity has many columns, large JSON, or LOBs, mapping the full entity wastes network bandwidth and object allocations even though only `email` is kept.

Use a query projection:

```java
Flux<String> findAllEmails() {
    return databaseClient.sql("SELECT email FROM customer ORDER BY id")
        .map((row, metadata) -> row.get("email", String.class))
        .all();
}
```

Or a small DTO:

```java
Flux<CustomerSummary> findSummaries() {
    return databaseClient.sql("""
            SELECT id, name
            FROM customer
            ORDER BY id
            """)
        .map((row, metadata) -> new CustomerSummary(
            row.get("id", Long.class),
            row.get("name", String.class)
        ))
        .all();
}
```

Projections shrink per-item size, network payload, and mapping cost. They do not bound row count; streaming or pagination is still needed for large result sets.

## 9. Paginating to Keep Each Query Finite

When callers must traverse an entire dataset, pagination keeps each query bounded. Two common approaches are offset pagination and keyset pagination.

### 9.1. Offset Pagination

```sql
SELECT id, name
FROM customer
ORDER BY id
LIMIT :pageSize OFFSET :offset;
```

Offset is simple and suits UIs requiring arbitrary page jumps. However, large offsets force the database to read/skip many rows before returning a page, and rows can shift across pages during concurrent INSERTs/DELETEs.

### 9.2. Keyset Pagination

```sql
SELECT id, name
FROM customer
WHERE id > :afterId
ORDER BY id
LIMIT :pageSize;
```

Keyset uses the last key of the previous page as a cursor. It is usually far more efficient when scanning deep into large datasets and resists row shifts from inserts prior to the cursor.

Cursors require deterministic ordering. If sorting by `created_at`, add `id` as a tie-breaker:

```sql
SELECT id, created_at, name
FROM customer
WHERE (created_at, id) > (:afterCreatedAt, :afterId)
ORDER BY created_at, id
LIMIT :pageSize;
```

Row-value comparison syntax works in PostgreSQL and several other DBMSs; verify dialect compatibility when switching databases.

### 9.3. Collecting One Small Page and Processing

```java
private Mono<List<CustomerSummary>> fetchPage(long afterId, int size) {
    return databaseClient.sql("""
            SELECT id, name
            FROM customer
            WHERE id > :afterId
            ORDER BY id
            LIMIT :pageSize
            """)
        .bind("afterId", afterId)
        .bind("pageSize", size)
        .map((row, metadata) -> new CustomerSummary(
            row.get("id", Long.class),
            row.get("name", String.class)
        ))
        .all()
        .collectList();
}
```

`collectList()` is safer here because `size` is bounded. The page query finishes before the list moves downstream; peak page memory can be estimated from page size and DTO size.

### 9.4. Processing Pages Sequentially

```java
private Flux<CustomerSummary> fetchPages(long afterId, int pageSize) {
    return Flux.defer(() -> fetchPage(afterId, pageSize))
        .flatMapMany(page -> {
            if (page.isEmpty()) {
                return Flux.empty();
            }

            long nextAfterId = page.get(page.size() - 1).id();

            return Flux.fromIterable(page)
                .concatWith(Flux.defer(() ->
                    fetchPages(nextAfterId, pageSize)
                ));
        });
}
```

This assumes `CustomerSummary` exposes `id()` and IDs form an ordered increasing key. `Flux.defer` delays the next page query until needed; `concatWith` maintains ordering and advances only after the current page finishes.

Each page runs as a separate query. Once `.all().collectList()` finishes, that query's result is consumed and the connection can return to the pool before starting the next page. This differs from `findAll().buffer(pageSize)`, which only chunks a single result stream and does not necessarily release the connection between chunks.

### 9.5. Pagination Does Not Automatically Create a Consistent Snapshot

Data can change between pages. If a consistent dataset is required, define an explicit cutoff/version or snapshot design. Holding one open snapshot transaction across an entire export pins connections for a long time; weigh the trade-offs carefully.

## 10. Batch Processing with Bounded Memory

For update or import jobs, read and process in batches:

```java
public Mono<Void> processAllCustomers() {
    return customerRepository.findAll()
        .buffer(200)
        .concatMap(batch -> customerService.processBatch(batch))
        .then();
}
```

Each batch holds at most 200 customers. `concatMap` processes sequentially so multiple batches are not in flight simultaneously. However, if the source is a single `findAll()` query, the underlying result connection may remain held until the whole source completes. `buffer` bounds heap batches without releasing connections between batches.

If you need both bounded memory and periodic connection release, execute separate page queries as shown earlier, finishing one page before fetching the next.

### 10.1. Choosing Batch Size

Overly small batches raise round-trips and coordination overhead. Overly large batches inflate memory, processing duration, and rollback scope if each batch runs in its own transaction.

Base batch size on:

- Average object size.
- Columns and LOBs read.
- Write operations per batch.
- Connection pool and database capacity.
- Latency and transaction duration.
- Concurrent workers or batches.

A batch of 500 entities holding large JSON documents consumes far more memory than 500 small DTOs. Measure on realistic data.

### 10.2. Bounding Concurrent Batches

When batches are independent and parallelism is needed:

```java
return pageSource
    .flatMap(this::processBatch, 4)
    .then();
```

Concurrency 4 permits up to four batch inner publishers in flight under this operator. Total memory must account for active batches, prefetched batches, queues, and per-publisher state.

For database writes, high concurrency can also cause pool and lock contention. Start small, measure throughput and pool metrics, then tune.

## 11. groupBy() and High Cardinality

`groupBy` creates a `GroupedFlux` per key:

```java
return eventRepository.findAll()
    .groupBy(Event::getTenantId)
    .flatMap(group -> group.count());
```

If tenant count is small and bounded, this can work. If millions of rows produce millions of distinct keys, group count and state blow up. Moreover, every group must be consumed; an unsubscribed or unconsumed group can stall upstream.

When you only need per-tenant counts, the database is usually far better:

```sql
SELECT tenant_id, COUNT(*) AS total
FROM event
GROUP BY tenant_id;
```

This returns one row per tenant instead of streaming every event into the JVM. If tenant count itself is massive, still paginate or stream aggregate results in bounded fashion.

## 12. distinct() and Deduplication

`distinct()` stores seen values in memory. On large sources, state grows with distinct key count:

```java
return eventRepository.findAll()
    .distinct(Event::getExternalId);
```

When retrieving unique external IDs, consider:

```sql
SELECT DISTINCT external_id
FROM event
ORDER BY external_id;
```

The database can use sort/hash aggregation and matching indexes. It still consumes server resources, yet the application avoids holding every key in a Java `Set`.

When deduplication relies on complex logic that cannot be pushed into SQL, process by partition/batch or use a bounded state store with eviction. Never assume `distinct()` on an unbounded `Flux` keeps memory flat.

## 13. Caching Large Data in a Controlled Manner

Caching cuts repeated queries, yet caching an entire large `Flux` creates a long-lived heap copy:

```java
Flux<Product> products = productRepository.findAll().cache();
```

A cached publisher retains emitted elements to replay to future subscribers. As product count grows, cache heap grows too.

Safer alternatives:

- Cache small pages or bounded queries.
- Cache compact summary values rather than full entities.
- Use off-heap or remote caches with max size and TTLs.
- Design invalidation for data mutations.
- Never cache unbounded streams or rapidly mutating tables without eviction.

With Caffeine or similar caches, configure explicit maximum size/weight and expiry. Size limits by object weight/byte footprint, not entry count alone.

## 14. Avoiding Extra Data Copies During Mapping

Even without `collectList()`, mapping can allocate large intermediate objects:

```java
return customerRepository.findAll()
    .map(customer -> objectMapper.convertValue(
        customer,
        CustomerDto.class
    ));
```

Conversion can build heavy object graphs, duplicate strings, or copy collections. When only a few fields are needed, direct SQL projection is usually leaner.

Do not serialize each entity into a JSON string and collect them into a list when WebFlux can encode DTOs item by item. When writing files, write in chunks using bounded buffers and honor backpressure.

### 14.1. Watch Out for LOBs and Wide Fields

`TEXT`, `BYTEA`, large JSONB, or LOB columns can dominate heap usage. If only metadata is needed, omit payload columns from `SELECT`. For large file transfers, use proper streaming APIs and verify driver/codec decoding behavior instead of materializing huge `byte[]` arrays per request.

## 15. HTTP Streaming Is Not Always a Complete Solution

WebFlux can stream `Flux<T>` item by item using media types like NDJSON or SSE. This avoids materializing the full response in application memory, yet the query result and connection may remain occupied as long as the client takes to read.

Example:

```java
@GetMapping(value = "/customers/stream",
            produces = MediaType.APPLICATION_NDJSON_VALUE)
public Flux<CustomerSummary> streamCustomers() {
    return customerService.streamSummaries();
}
```

Streaming works well when:

- The dataset is practically bounded or stream duration is controlled.
- Clients consume streams reliably.
- Concurrent open streams are capped.
- Connection and transaction hold times remain acceptable.

For huge exports or slow clients taking minutes to download, paginated queries or export jobs are usually better. Streaming avoids heap growth across the full result, at the cost of holding connections longer.

## 16. Exporting Large Datasets via Background Jobs and Files

When millions of rows must be downloaded, decouple file generation from HTTP requests:

1. API creates an export job and returns a job ID.
2. Worker reads bounded keyset pages.
3. Each page finishes and releases its connection.
4. Worker serializes rows or batches to a file or object storage.
5. Worker records checkpoints and progress.
6. Upon completion, the API provides a download link or endpoint.
7. Files expire per TTL/retention policies.

Workers need backpressure, concurrency bounds, maximum file limits, timeouts, and resume support. If point-in-time consistency is required, use an explicit cutoff/version or snapshot design.

Never call `collectList()` and serialize the whole file in memory. Use a streaming writer with bounded buffers, verifying the writer does not buffer the entire output before flushing.

## 17. Capping Request Sizes and Page Sizes

Never let clients dictate unbounded page sizes or batch sizes. Validate inputs:

```java
int normalizePageSize(Integer requested) {
    if (requested == null) {
        return 50;
    }

    return Math.min(Math.max(requested, 1), 200);
}
```

Choose upper bounds based on response weight, heap budget, and SLAs. If DTOs carry large JSON payloads, even 200 may be too high.

For export APIs, enforce per-user/tenant quotas and cap concurrent jobs. Prevent a single client from firing multiple large requests that exhaust memory or the connection pool.

## 18. Estimating Memory for Batches and Concurrency

For batch processing, use a simple model:

\[
\text{Heap for batch data} \approx
\text{Batch size} \times
\text{Average item size} \times
\text{Concurrent batches}
\]

For example, assuming each DTO averages 4 KB, batch size is 200, and concurrency is 4:

\[
200 \times 4\text{ KB} \times 4
= 3.2\text{ MB}
\]

This estimates only batch payload data—excluding object graph overhead, prefetch queues, driver buffers, serialization buffers, thread stacks, and baseline heap. Measure true object sizes with a profiler or heap dump.

Leave ample headroom for concurrent requests and GC. Never size batches and concurrency to consume 100% of theoretical heap.

## 19. Monitoring Memory and Detecting Unintended Materialization

Metrics to monitor:

- Heap used and heap after GC.
- Allocation rate and allocations per endpoint/job.
- GC pause duration and frequency.
- Concurrent materializing or exporting requests.
- Items queued in batches/buffers if instrumented.
- Response sizes and row counts returned.
- Query execution and downstream processing times.
- OOM counts, container memory, and process RSS.
- Cache entry counts/weights and eviction counts.

Exact metric names depend on Micrometer, the JVM, and the deployment platform. Use JFR, heap dumps, or profilers to identify which object types retain heap when metrics climb abnormally.

### 19.1. Signs That collectList or Caching Is Retaining Data

- Heap grows proportionally with a single request's row count.
- Memory fails to drop after queries finish because caches or static references hold lists.
- Frequent GC cycles leave post-GC heap elevated.
- Endpoints emit their first item only after the whole query finishes.
- Concurrent export requests trigger sharp heap spikes.
- Heap dumps show `ArrayList`, `HashMap`, Reactor cache state, or DTO objects dominating heap.

Do not diagnose a leak solely from temporary heap growth during active processing. A list can legitimately stay alive until a request finishes; check whether objects remain reachable after the workflow ends.

## 20. Testing to Catch Oversized Materialization

Unit tests can verify a service does not await full source completion before emitting its first item:

```java
@Test
void streamsItemsWithoutWaitingForSourceCompletion() {
    TestPublisher<Integer> source = TestPublisher.create();

    Flux<Integer> result = source.flux()
        .map(value -> value * 2);

    StepVerifier.create(result)
        .then(() -> source.next(1))
        .expectNext(2)
        .thenCancel()
        .verify(Duration.ofSeconds(2));
}
```

This test confirms mapping emits items before the source completes. If a `collectList()` sat in the pipeline, no item would emit until source completion.

### 20.1. Testing Bounded Batch Sizes

```java
@Test
void emitsBatchesWithConfiguredMaximumSize() {
    StepVerifier.create(
            Flux.range(1, 10).buffer(3)
        )
        .expectNext(List.of(1, 2, 3))
        .expectNext(List.of(4, 5, 6))
        .expectNext(List.of(7, 8, 9))
        .expectNext(List.of(10))
        .verifyComplete();
}
```

This illustrates `buffer(3)` semantics. For production pipelines, test actual batch sizes, concurrency, and query counts.

### 20.2. Testing Against collectList on Unbounded Sources

You can use `Flux.never()` or `Flux.interval()` to verify pipelines emit on demand without awaiting completion. Bound test timeouts and cancel subscriptions cleanly so sources do not linger in the background.

### 20.3. Integration Tests with Larger Datasets

Against a real database:

- Seed enough data with production-like row widths.
- Run streaming queries or paginated queries.
- Measure heap/allocations and time to first item.
- Run concurrent requests at target load.
- Compare streaming, page materialization, and bounded `collectList()`.
- Verify connections return to the pool after each query/page.
- Test cancellation and cleanup.

You do not need millions of rows in every CI test. Run moderate integration tests in CI alongside dedicated performance/load tests on larger datasets.

## 21. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| `findAll().collectList()` on large tables | Retains all entities in heap | Return `Flux`, paginate, or aggregate in DB |
| `collectMap()`/`collectMultimap()` on large sources | Maps grow with key/value count | Group/aggregate in SQL or process page by page |
| `sort()` over an entire Flux | Materializes all items to sort | Use SQL `ORDER BY` with matching indexes |
| `cache()` on a whole-table Flux | Pins full dataset in publisher cache | Cache small pages/results with TTL and max size |
| `distinct()` with high cardinality | Seen-key set grows unboundedly | Use SQL `DISTINCT` or partitioned deduplication |
| Unbounded `onBackpressureBuffer()` | Heap grows when consumers slow down | Propagate backpressure or use bounded buffers |
| Assuming `buffer(n)` releases connections per batch | Underlying result stream may still pin connection | Issue separate page queries if releasing between batches |
| Unbounded `flatMap()` | Many concurrent inner publishers and queued results | Set finite concurrency |
| `flatMapSequential()` with a slow leading item | Subsequent results queue waiting for order | Lower concurrency/prefetch or use `concatMap` |
| `groupBy()` with many keys | Many groups and queues/state | Group/aggregate in DB or partition into bounded keys |
| `reduce()` with a List accumulator | Still collects the entire source | Use fixed-size accumulators or SQL aggregates |
| Using only `.take(n)` after an unbounded query | Driver/DB may still prefetch or scan excessively | Put `LIMIT` in SQL |
| Selecting full entities when few fields are needed | Heavy network traffic and object allocations | Small projections/DTOs |
| `collectList()` for a full export before serializing | Heap scales with entire export file | Background export jobs with pages and streaming writers |
| Client-controlled arbitrary page size/concurrency | Single request can exhaust heap | Enforce max page sizes and quotas |
| Measuring heap without checking post-GC retention | Confuses transient allocations with retained leaks | Use JFR, heap dumps, or profilers |

## 22. Process for Designing a Bounded-Memory Pipeline

When processing large datasets, follow these steps:

1. **Size the workload:** estimate row counts, row/DTO widths, and concurrent requests.
2. **Choose projections:** SELECT only needed columns; omit large LOBs/JSON when unused.
3. **Push computation to the database:** use `COUNT`, `SUM`, `GROUP BY`, `DISTINCT`, `EXISTS`, and `ORDER BY` where appropriate.
4. **Limit results:** enforce SQL `LIMIT` and validate page sizes.
5. **Choose streaming vs. pagination:** stream for fast consumers and controlled sets; paginate large datasets to release queries between chunks.
6. **Bound all buffers:** use `buffer(n)` or `bufferTimeout` with explicit capacities; ban unbounded buffers.
7. **Bound concurrency:** size max concurrency and prefetch within heap and pool budgets.
8. **Audit stateful operators:** avoid `collectList`, `sort`, `cache`, `distinct`, or `groupBy` on large unbounded sources.
9. **Isolate slow work:** complete page queries before external calls or file writes whenever possible.
10. **Measure and test:** use profilers, heap dumps, load tests, and real-driver integration tests.

## 23. Principles to Remember

- `Flux` does not automatically bound memory; downstream operators determine how much data stays in memory.
- `collectList`, `collectMap`, `collectMultimap`, `sort`, `cache`, and `replay` can retain all or most of a stream.
- `distinct` and `groupBy` maintain state proportional to key cardinality; high-cardinality sources inflate heap.
- `reduce` saves memory only when the accumulator has fixed size.
- Use `buffer(n)` or `bufferTimeout(maxSize, maxTime)` with explicit limits.
- Avoid unbounded `onBackpressureBuffer()`; prefer backpressure and business-aligned overflow policies.
- Set finite concurrency and prefetch on `flatMap`, `flatMapSequential`, and `publishOn`.
- Push filtering, sorting, aggregation, and distinctness down to the database when appropriate.
- Use projections to shrink per-row size; read only required columns.
- Use SQL `LIMIT` rather than relying solely on `.take(n)` over an unbounded query.
- Use keyset pagination with stable cursors for large datasets.
- `buffer(n)` splits a result stream into batches without issuing separate queries or releasing connections between batches.
- Collecting a small page with `collectList()` is safe when page size is strictly bounded.
- For large exports, favor background jobs, page queries, and streaming writers.
- Caches require size/weight bounds, TTLs, and invalidation; never cache large Fluxes indefinitely.
- Estimate memory from batch size, object size, and concurrency, then verify with a profiler.
- Test slow downstream consumers, large datasets, and high concurrency.

Avoiding collecting large `Flux` streams into memory is a pipeline-wide design discipline—not merely deleting a `collectList()` call. Bound every point where items can accumulate, preserve backpressure, push projections and aggregates down to the database, and split large datasets into finite pages or batches. When full datasets must be downloaded, background export jobs and streaming writers decouple database speed from client speed. Combining page/concurrency caps with heap profiling and load testing lets R2DBC applications process large datasets without memory scaling linearly with total results.
