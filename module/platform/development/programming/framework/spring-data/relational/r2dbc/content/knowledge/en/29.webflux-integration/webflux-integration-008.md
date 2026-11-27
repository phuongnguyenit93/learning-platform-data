# Risk of Holding Connections Open When Consumers Read Slowly

In an application using Spring Data Relational R2DBC with Spring WebFlux, a query can return a `Flux<T>` and stream directly into an HTTP response. This model enables streaming data processing without blocking threads waiting for every row. However, if the consumer reads the response slowly, the pipeline can experience backpressure. While the database result is still being consumed, the connection used for the query can remain checked out from the connection pool.

This is a critical distinction: **non-blocking does not mean resource-free**. Request-handling threads may not be blocked, yet database connections, transactions, buffers, and memory still have lifetimes. A handful of long-lived response streams can tie up many connections for extended periods; once the pool is exhausted, new requests must wait or time out.

This lesson explains why downstream consumption speed affects connection hold times, how backpressure propagates through WebFlux and R2DBC, which operators tend to introduce buffering, the impact of transactions, how to monitor the pool, and mitigation strategies such as keyset pagination, bounded batches, and asynchronous exports.

## 1. From Database Result to HTTP Response

An endpoint can return `Flux<CustomerView>` directly:

```java
@GetMapping(value = "/customers/stream",
            produces = MediaType.APPLICATION_NDJSON_VALUE)
public Flux<CustomerView> streamCustomers() {
    return customerService.streamCustomers();
}
```

The service uses `DatabaseClient`:

```java
public Flux<CustomerView> streamCustomers() {
    return databaseClient.sql("""
            SELECT id, name, email
            FROM customer
            ORDER BY id
            """)
        .map((row, metadata) -> new CustomerView(
            row.get("id", Long.class),
            row.get("name", String.class),
            row.get("email", String.class)
        ))
        .all();
}
```

When WebFlux writes the response, the framework subscribes to the publisher and requests data according to the encoder/network demand. With streaming media types like NDJSON or Server-Sent Events, the response may be written item by item or event by event. Exact flushing and buffering behavior also depends on the codec, media type, server connector, and upstream proxies.

High-level processing flow:

```text
PostgreSQL
    |
    v
R2DBC driver / Result
    |
    v
DatabaseClient Flux<CustomerView>
    |
    v
WebFlux encoder
    |
    v
HTTP server / network buffers
    |
    v
Proxy / client
```

If the client reads quickly, demand is satisfied promptly and the query can finish early. If the client reads slowly or pauses reading, downstream reduces demand. As long as the pipeline is still consuming the same database result, the connection can remain held until the result completes, errors, or is cancelled and cleanup finishes.

## 2. Why Are Connections Held Open for Long Periods?

For a reactive query, a connection is typically acquired when the publisher is subscribed to. The driver executes the statement and supplies the result. Spring Data/`DatabaseClient` must keep the connection while the result is being consumed, releasing or returning it to the pool afterward.

A response stream can drag out because:

- The query returns hundreds of thousands or millions of rows.
- The client downloads data over a slow network.
- A proxy or gateway throttles transmission speed.
- The client spends significant time processing each item.
- Downstream calls additional services or runs computations before requesting the next item.
- A buffering or prefetch operator alters consumption rates between layers.
- A transaction wraps the entire stream and closes only when the stream finishes.

For instance, a query that takes a few hundred milliseconds when drained rapidly can hold a connection for many seconds or longer when streamed to a slow client. SQL execution duration and connection occupation duration are not necessarily equal.

### 2.1. Connection Hold Time Differs from SQL Execution Time

Several intervals can be distinguished:

| Interval | Meaning |
|---|---|
| Connection acquire | Waiting to obtain a connection from the pool |
| Statement execution | Driver sends the statement and database processes it |
| Result consumption | Application/driver reads result rows |
| Downstream processing | Mapping, encoding, business work, and sending response |
| Cleanup/release | Closing result/statement and returning connection to the pool |

For a streaming result, these stages overlap. If downstream only asks for more data after finishing writing the previous chunk, result consumption stretches to match HTTP write speed. Therefore, measuring query latency alone is insufficient to detect long connection holds.

### 2.2. Non-Blocking Still Occupies Connections

R2DBC uses asynchronous I/O to avoid blocking threads while waiting on the database. Nevertheless, connections are finite resources. A connection actively serving a result stream cannot concurrently be handed to another request under normal connection pooling.

Consequently, an application can use very few threads and still exhaust its pool. This is a classic reason reactive systems experience rising latency despite low CPU utilization.

## 3. How Backpressure Propagates from WebFlux to R2DBC

Reactive Streams uses demand: a subscriber requests a count of elements via `request(n)`. A publisher emits at most the requested count per contract. When downstream consumes slowly, it can slow its request rate, propagating backpressure up the pipeline where components support it.

Conceptual example:

```text
Client reads slowly
      |
      v
HTTP response writer lowers demand
      |
      v
WebFlux encoder emits more slowly
      |
      v
Reactor pipeline requests fewer items
      |
      v
R2DBC result is consumed more slowly
      |
      v
Connection may be held open longer
```

Backpressure prevents an unconstrained producer from flooding a slower consumer. It does not automatically release connections early. In a streaming query, slowing consumption usually means the result—and thus the connection—lives longer.

### 3.1. Backpressure Does Not Guarantee the Database Sends One Row at a Time

Between the subscriber and the driver there may be several buffering layers:

- Reactor operator prefetch.
- Buffers inside the R2DBC driver.
- Database protocol and socket buffers.
- HTTP server and network stack buffers.
- Buffers in reverse proxies or clients.

Thus, subscriber demand does not mean every `request(1)` causes one network round trip to the database. The driver may prefetch rows or use its own cursor/fetch strategy. Behavior depends on the driver and configuration.

If the driver supports fetch size or cursor-based fetching, configure it per driver documentation. R2DBC SPI offers APIs such as `Statement.fetchSize(int)` in supported versions, though drivers may ignore it or apply custom semantics. Do not assume `fetchSize` behaves identically across all databases.

### 3.2. Backpressure Helps Only If the Pipeline Does Not Break It

Certain operators ask upstream to emit faster and store items in buffers. For example:

- `onBackpressureBuffer()` can queue items waiting for downstream.
- `publishOn` uses a prefetch queue to pass signals across schedulers.
- `collectList()` drains the entire source and holds all elements in memory.
- `buffer(n)` collects elements into batches before emitting.
- `flatMap` can run multiple inner publishers and buffer pending outputs.

These operators are not inherently wrong, yet they shift where and how much data is buffered. If buffers are unbounded, a slow downstream can rapidly inflate heap usage.

## 4. HTTP Streaming Can Prolong Query Lifetimes

Example row-streaming endpoint:

```java
@GetMapping(value = "/events", produces = MediaType.APPLICATION_NDJSON_VALUE)
public Flux<EventView> events() {
    return eventService.findAllEvents();
}
```

As the client reads NDJSON line by line, WebFlux can request more items as writing progresses. If the client receives data over a sluggish mobile network, the response writer experiences backpressure and the pipeline can keep the database result open.

This works well for bounded streams with small consumer counts. It becomes problematic if the endpoint streams millions of records, clients keep connections open for a long time, or many users download simultaneously.

### 4.1. Media Type Affects How Responses Are Encoded

Common response types:

| Media Type | Characteristics |
|---|---|
| `application/x-ndjson` | Each JSON object is newline-delimited; suited for per-record transmission |
| `text/event-stream` | Server-Sent Events; each event has its own framing |
| `application/json` | JSON document/array; encoding, flushing, and buffering depend on codec and server |

When clients must process each record upon arrival, NDJSON or SSE expresses streaming semantics more clearly than a standard JSON array. Yet changing media type alone does not fix long connection holds if the publisher remains tied to a long query.

### 4.2. Proxies Can Buffer Responses

Reverse proxies, ingress controllers, API gateways, or CDNs may buffer responses before forwarding to clients. This can dampen direct client-to-application backpressure or alter response write timing. Conversely, proxies may hold upstream connections open while a slow downstream reads.

Inspect streaming/buffering configurations in your real infrastructure. Do not infer production behavior solely from tests hitting a WebFlux server directly on localhost.

## 5. Impact of Transactions on Connection Hold Duration

Reactive transactions are normally tied to the subscription and connection managed by the transaction manager. If a `@Transactional` method returns a long `Flux`, the transaction can stay active until the `Flux` finishes or is cancelled.

Example:

```java
@Transactional(readOnly = true)
public Flux<CustomerView> streamCustomers() {
    return customerRepository.findAll()
        .map(this::toView);
}
```

If this publisher directly backs an HTTP response and the client consumes slowly, the transaction-bound connection can be held for the entire stream duration. `readOnly = true` does not mean the connection returns to the pool immediately once the query starts.

Long-running transactions can also:

- Hold read snapshots longer depending on isolation level and database.
- Increase lock contention if the transaction performs writes or acquires read locks.
- Prolong connection pool checkout times.
- Exceed transaction timeouts or application deadlines.
- Impact vacuum/cleanup or replication depending on database and isolation semantics.

Do not open a transaction just to wrap a large response stream unless business rules strictly require a single transaction across the entire stream. If snapshot consistency is needed, weigh snapshot benefits against connection resource costs.

### 5.1. Do Not Hold Transactions While Waiting on Slow Network Work

Avoid keeping a database transaction open while calling HTTP services, waiting on clients, or doing heavy CPU work unnecessarily:

```java
@Transactional(readOnly = true)
public Flux<CustomerView> streamCustomers() {
    return customerRepository.findAll()
        .flatMap(customer -> profileClient.fetch(customer.getId())
            .map(profile -> toView(customer, profile)));
}
```

Each element waits on an HTTP call. While the database query and transaction stay open during slow inner publishers, the connection can remain held far longer than SQL execution requires.

If external enrichment is needed, consider fetching data in finite batches, completing the query before calling external services, or using a dedicated workflow with bounded concurrency and timeouts.

### 5.2. Transactions Do Not Automatically Span Paginated Requests

If each page is a separate query using its own connection/transaction, pages may observe data at different points in time. Conversely, holding a single snapshot transaction across an entire export can tie up a connection for a long time.

Decide whether the use case needs:

- Latest data per page, accepting changes during reading.
- A stable dataset defined by a point-in-time/cutoff.
- A consistent database snapshot across the whole process.

Consistency requirements dictate pagination, watermark, snapshot, and connection-lifetime strategies.

## 6. Connection Pools Can Exhaust Despite Low CPU

A connection pool has a maximum capacity. When long streams hold connections, incoming requests must wait for free connections. If wait times exceed the acquire timeout, requests fail even when database CPU is nowhere near saturated.

An intuitive estimate based on Little's Law:

\[
\text{Average busy connections}
\approx
\text{DB request rate}
\times
\text{Average connection hold time}
\]

Qualitatively: if the rate of requests starting queries stays constant while connection hold time multiplies due to slow clients, average busy connections rise proportionally. Once approaching `maxSize`, acquire queues begin to grow.

Do not solve this merely by increasing pool size. Larger pools allow more concurrent connections against the database and add load, while the root cause remains each stream holding a connection for too long.

## 7. Monitoring the Connection Pool and Hold Durations

Useful metrics include:

| Metric | Meaning |
|---|---|
| Allocated connections | Number of connections created by the pool |
| Acquired/active connections | Connections currently checked out by the application |
| Idle connections | Free connections available for lease |
| Pending acquire | Requests waiting for a connection |
| Acquire duration | Time spent waiting to obtain a connection |
| Acquire timeout count | Failures to acquire a connection before timeout |
| Connection hold duration | Time from checkout to return, if instrumented |
| Query/statement duration | Statement execution or result duration per instrumentation |
| Cancellation count | Subscriptions cancelled while in flight |

Exact metric names depend on the R2DBC pool, Micrometer, Spring Boot, and library versions. Verify actual metric names in your runtime environment instead of hardcoding names from another version.

### 7.1. Signs That Slow Streams Are Starving the Pool

Warning signs include:

- Active connections climb while idle connections drop near 0.
- Pending acquires grow even though application CPU stays low.
- Acquire latency correlates with the number of concurrent streaming clients.
- Streaming endpoints show abnormally long response durations.
- Query execution time does not grow proportionally with connection hold duration.
- After clients disconnect, active connections drop slowly or cancellation/cleanup lags.

Combine pool metrics, HTTP response durations, query timings, and traces to distinguish slow queries from slow downstream consumers.

### 7.2. Timing at Boundaries

You can record timestamps when the publisher starts, on the first element, and when the pipeline ends:

```java
public Flux<CustomerView> streamCustomers() {
    return customerRepository.findAll()
        .doOnSubscribe(subscription -> log.debug("Customer stream subscribed"))
        .doOnNext(customer -> recordFirstOrNextRow(customer.getId()))
        .doFinally(signal -> recordStreamFinished(signal));
}
```

In production code, avoid logging IDs or personal data unless necessary. Use timers/metrics instead of per-row logs to avoid excessive log volume. `doFinally` observes complete, error, or cancel signals; it does not replace pool-level connection hold duration metrics.

## 8. Operators That Increase Buffering or Prolong Source Retention

### 8.1. collectList()

```java
return customerRepository.findAll()
    .collectList()
    .flatMapMany(Flux::fromIterable);
```

`collectList()` drains the entire source before emitting the list. The upside is that the query finishes and returns the connection to the pool before the list is streamed out to the HTTP client. The downsides are:

- All results live on the heap.
- Clients receive no items until the query completes.
- Latency and memory scale with row count.
- Large datasets can trigger `OutOfMemoryError`.

Use `collectList()` only when size is strictly bounded, such as a page of a few dozen or hundred records per system SLAs. Never use it on entire large tables.

### 8.2. buffer(n)

```java
return customerRepository.findAll()
    .buffer(100)
    .concatMap(this::processBatch);
```

`buffer(100)` groups up to 100 items into a list before emitting. It bounds each batch size but does not split the query across separate connections or guarantee connection release between batches. If upstream is a single result stream, the connection can still be held until the entire source finishes.

To release connections between pages, execute separate bounded queries, consume each query to completion, emit the page, and only then start the next query.

### 8.3. onBackpressureBuffer()

```java
return customerRepository.findAll()
    .onBackpressureBuffer();
```

Unbounded buffers convert downstream pressure into heap pressure. When consumers slow down, the application accumulates rows instead of slowing the producer. With large database results, this poses a severe risk.

If buffering is genuinely needed, set bounds and an overflow policy:

```java
return source.onBackpressureBuffer(
    500,
    dropped -> metrics.counter("stream.buffer.overflow").increment()
);
```

Exact overload signatures and behavior depend on the Reactor version. Overflow policies must match business needs; never arbitrarily drop database rows just to keep a pipeline running.

### 8.4. publishOn()

`publishOn` moves downstream processing to another scheduler and typically maintains a prefetch queue. It helps offload CPU work from upstream execution threads, but its queue buffers elements in memory and does not release the connection early.

```java
return customerRepository.findAll()
    .publishOn(Schedulers.parallel(), 64)
    .map(this::expensiveMapping);
```

Smaller prefetch values limit queued items, though they do not replace pagination or fetch-size tuning. Do not add schedulers just hoping to "make reactive faster"; measure first and isolate genuine CPU/blocking work.

### 8.5. flatMap()

```java
return customerRepository.findAll()
    .flatMap(customer -> profileClient.fetch(customer.getId()));
```

`flatMap` can keep many inner publishers active and buffer results waiting for downstream. If inner publishers are slow, in-flight connections/HTTP calls or buffers can grow. Specify bounded concurrency:

```java
return customerRepository.findAll()
    .flatMap(customer -> profileClient.fetch(customer.getId()), 8);
```

Limiting concurrency caps concurrent secondary work, yet if `findAll()` remains one continuous result stream, the source connection may still stay open until the source completes.

## 9. Subscription Cancellation on Client Disconnect

When a client closes the connection before the response completes, WebFlux can cancel the response publisher's subscription. Cancellation propagates through Reactor to the R2DBC driver, stopping result consumption and triggering connection cleanup.

However:

- Cancellation does not guarantee the database stops the statement instantaneously.
- The driver may take time to send a cancel request or drain/close protocol state.
- Some operations may have already completed on the database before cancellation arrives.
- Proxies may keep upstream requests alive briefly after clients close.
- Open transactions may need rollback/cleanup before the connection returns to the pool.

Never rely solely on cancellation to cap resources. Combine query limits, timeouts, page sizes, transaction boundaries, and concurrent stream caps.

### 9.1. take(n) and Row Limits

If an API needs at most N rows, enforce the limit directly in SQL:

```sql
SELECT id, name
FROM customer
ORDER BY id
LIMIT :limit;
```

Or apply `.take(n)` as a pipeline cap:

```java
return customerRepository.findAll()
    .take(100);
```

`take(100)` cancels upstream after 100 items, yet the database/driver may have already prefetched more rows. Placing `LIMIT` in SQL is clearer and avoids generating large results on the database. Both can be layered defensively, provided their semantics are understood.

## 10. Multi-Layer Timeouts

A streaming endpoint should have appropriate time budgets and resource caps. Different timeouts protect different phases:

| Timeout | Protects |
|---|---|
| Pool acquire timeout | Waiting time for a free connection |
| Connection creation timeout | Establishing a new physical connection |
| Statement/query timeout | Statement execution duration per driver/database support |
| Reactor `timeout` | Duration a publisher emits no signal per operator config |
| Transaction timeout | Transaction lifetime per transaction manager |
| HTTP response timeout | Allowed response lifetime at server/gateway/client |
| Idle timeout | Period of inactivity before closing the connection |

Example using Reactor timeout:

```java
return customerService.streamCustomers()
    .timeout(Duration.ofMinutes(2));
```

`timeout` cancels upstream upon expiration and emits `TimeoutException` or switches to a fallback. It does not replace a database query timeout, and it does not guarantee every driver cancels statements immediately.

For streams that legitimately run long while steadily emitting items, overall timeouts and idle timeouts serve different roles. A steadily flowing stream may exceed a total deadline without going idle; conversely, a stalled stream emitting nothing needs an idle timeout.

Do not apply overly aggressive timeouts uniformly across every endpoint. Tune per SLA, result size, network speed, and client type.

## 11. Strategy 1: Bounding Results Directly in SQL

If the use case only needs a finite subset, use `LIMIT`/`FETCH FIRST` or database-appropriate pagination APIs.

```java
Flux<CustomerView> findRecentCustomers(int limit) {
    return databaseClient.sql("""
            SELECT id, name, email
            FROM customer
            ORDER BY created_at DESC, id DESC
            LIMIT :limit
            """)
        .bind("limit", limit)
        .map((row, metadata) -> new CustomerView(
            row.get("id", Long.class),
            row.get("name", String.class),
            row.get("email", String.class)
        ))
        .all();
}
```

Validate `limit` within safe bounds before binding. Never allow clients to request millions of records simply by passing a huge query parameter.

SQL limits reduce rows read and typically shorten connection hold times. They are the best option when business logic does not truly need the entire dataset.

## 12. Strategy 2: Paginating to Release Connections Between Pages

When scanning a large dataset, run multiple small page queries. Once each query completes, the connection is released; the application then sends the page downstream and starts the next query only when needed.

### 12.1. Keyset Pagination

Keyset pagination uses the last item's key from the previous page as a cursor:

```sql
SELECT id, name, email
FROM customer
WHERE id > :afterId
ORDER BY id
LIMIT :pageSize;
```

Assume `id` is a unique key with stable ascending order. The first page uses an initial cursor matching the ID domain; subsequent pages use the last ID from the previous page.

Compared to `OFFSET`, keyset pagination avoids skipping vast numbers of rows deep into a dataset. It is also less prone to row shifting when new rows are inserted before the cursor. However, it requires choosing a cursor based on a stable, unique ordering.

### 12.2. Example Fetching a Page and Finishing the Query Before Emitting

```java
private Mono<List<CustomerView>> fetchPage(long afterId, int pageSize) {
    return databaseClient.sql("""
            SELECT id, name, email
            FROM customer
            WHERE id > :afterId
            ORDER BY id
            LIMIT :pageSize
            """)
        .bind("afterId", afterId)
        .bind("pageSize", pageSize)
        .map((row, metadata) -> new CustomerView(
            row.get("id", Long.class),
            row.get("name", String.class),
            row.get("email", String.class)
        ))
        .all()
        .collectList();
}
```

Here, `collectList()` collects only a single page bounded by `pageSize`. Once `.all()` completes, the page's result is drained and the query's connection can return to the pool before the page is incrementally transmitted to the HTTP client.

### 12.3. Chaining Pages Sequentially

```java
public Flux<CustomerView> streamByPages(int pageSize) {
    return fetchPages(0L, pageSize);
}

private Flux<CustomerView> fetchPages(long afterId, int pageSize) {
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

This example assumes positive ascending IDs and a `CustomerView` accessor `id()`. In production code, enforce a maximum `pageSize` and pick an appropriate starting cursor. `Flux.defer` postpones querying the next page until its branch is subscribed to; `concatWith` advances to the next page only after the current page's items are consumed.

Unlike `findAll().buffer(pageSize)`, each page here executes as its own SQL statement. The current query completes before page items travel downstream; the connection is not held across the entire dataset.

### 12.4. Cursors Need a Deterministic Unique Order

When sorting by `created_at`, multiple rows can share the same timestamp. Using timestamp alone as a cursor can skip or duplicate rows. Include a unique key as a tie-breaker:

```sql
SELECT id, created_at, name
FROM customer
WHERE (created_at, id) > (:afterCreatedAt, :afterId)
ORDER BY created_at, id
LIMIT :pageSize;
```

Row-value comparisons like this work well in PostgreSQL and several databases; syntax varies by dialect. With multi-column cursors, use the exact same column order in both the predicate and `ORDER BY`.

## 13. Pagination Changes Data Consistency Semantics

Each page is a separate statement, so data can change between reads:

- New rows are inserted after the previous page finished.
- Rows are deleted before the next page is read.
- Cursor or sort columns are updated.
- Rows move from behind the cursor ahead of it or vice versa.

Keyset pagination avoids many `OFFSET` issues, yet it does not automatically provide a consistent snapshot for an entire export.

If in-flight mutations are acceptable, document these semantics clearly for callers. If a stable dataset is required, you can:

- Choose a business cutoff/version and apply a fixed filter predicate across all pages.
- Use an appropriate database snapshot if supported by the DBMS/isolation level, accepting longer connection/transaction retention.
- Build an export job using a snapshot or pre-materialized key list per design.
- Use a staging/export snapshot table to decouple data preparation from download.

Do not wrap pagination in a long-running transaction just for consistency without evaluating pool and database impact.

## 14. Strategy 3: Reading Quickly into Bounded Memory Before Responding

For small, explicitly bounded datasets, read everything before starting to write the response:

```java
public Mono<List<CustomerView>> loadCustomerPage(int pageSize) {
    return databaseClient.sql("""
            SELECT id, name, email
            FROM customer
            ORDER BY id
            LIMIT :pageSize
            """)
        .bind("pageSize", pageSize)
        .map((row, metadata) -> new CustomerView(
            row.get("id", Long.class),
            row.get("name", String.class),
            row.get("email", String.class)
        ))
        .all()
        .collectList();
}
```

Once the database publisher completes, the connection can be released. WebFlux then serializes the in-memory list. Slow clients no longer extend database result reading time.

Trade-offs:

- Memory scales with row count and object size.
- Clients wait until the query finishes before receiving the first byte.
- Unsuitable for unbounded exports.
- Under high concurrency, aggregate memory usage can grow substantially.

This strategy fits small pages, bounded responses, or limited aggregate payloads. It is not a safe substitute for streaming entire tables.

## 15. Strategy 4: Asynchronous Exports for Very Large Datasets

If users need to download millions of rows, keeping one HTTP request and one database connection alive for the entire download is rarely a good design.

Convert it into an export job:

1. API accepts the export request and creates a job record.
2. Worker reads data via keyset pages with a finite batch size.
3. Worker writes output to file/object storage in a memory-bounded stream.
4. Each page query completes and releases its connection before further processing if designed that way.
5. Worker updates job progress and status.
6. API returns a job ID; the client polls status or receives a completion notification.
7. Once ready, the client downloads the file from a dedicated endpoint/download service.

Benefits:

- Avoids holding HTTP requests open for long periods.
- Uses connections per page rather than for the client's entire download time.
- Supports retries/resumption and progress tracking.
- Enforces quotas and limits concurrent exports.
- Decouples database read speed from client download speed.

Workers still need concurrency caps, timeouts, checkpoints, and file-retention policies. If exports require consistent snapshots, design explicit snapshot/cutoff boundaries.

## 16. Never Hold Connections During Slow Data Processing

A pipeline may perform mapping or enrichment after reading rows. If post-database work is slow, the source connection can stay open while downstream processes.

Example:

```java
return customerRepository.findAll()
    .flatMap(customer -> slowExternalService.enrich(customer)
        .map(this::toView), 4);
```

`flatMap` with concurrency `4` bounds active enrichments. Yet `findAll()` remains an open database stream; if downstream does not drain it, the result connection can stay occupied.

Whenever possible, split into two phases:

1. Read a bounded page and finish the query.
2. After releasing the connection, process the page against the external service with bounded concurrency.
3. Only after the page completes, fetch the next page.

Structural example:

```java
private Mono<List<Customer>> fetchCustomerPage(long afterId, int size) {
    return customerRepository.findPageAfter(afterId, size)
        .collectList();
}

private Flux<CustomerView> processPages(long afterId, int size) {
    return Flux.defer(() -> fetchCustomerPage(afterId, size))
        .flatMapMany(page -> {
            if (page.isEmpty()) {
                return Flux.empty();
            }

            long next = page.get(page.size() - 1).getId();

            return Flux.fromIterable(page)
                .flatMap(this::enrichCustomer, 4)
                .concatWith(Flux.defer(() -> processPages(next, size)));
        });
}
```

This illustrates completing the page query before invoking external services. If output ordering must be preserved, replace `flatMap` with `concatMap` or re-sort by key. Verify the repository page query uses a deterministic sort order.

## 17. Using Fetch Size/Cursors When Supported by the Driver

For large datasets, some database drivers support cursors or fetch sizes to retrieve results incrementally rather than pulling the whole result set to the client at once. R2DBC SPI includes `Statement.fetchSize(int)` in supported versions, though it is a driver hint; availability and semantics depend on the implementation.

Questions to verify per driver:

- Is `fetchSize` honored or ignored?
- Is an open transaction required while the cursor is consumed?
- Does the driver use server-side cursors, portals, or prefetching?
- When the subscriber reduces demand, does the driver pause fetching?
- On cancellation, how are cursors/portals closed and connections returned?
- Are there batch-size or buffered-row limits?

Do not set `fetchSize` excessively high just to reduce round trips; it can inflate memory. Too small a `fetchSize` increases round trips and lowers throughput. Benchmark based on row size, network latency, and consumer speed.

### 17.1. fetchSize Does Not Solve Connection Retention

Fetch size can cap how many rows the driver pulls per round trip, but if the entire result is still streamed to a slow client, the connection can still stay checked out until the cursor ends. Fetch size primarily tunes buffering/fetch behavior; pagination establishes completed query boundaries between pages.

## 18. Limiting Concurrent Streams and In-Flight Work

Not every streaming endpoint needs to serve unlimited concurrent clients. Apply quotas or concurrency caps at the application layer:

- Cap concurrent exports/streams per tenant or user.
- Cap row counts, duration, and read rates.
- Use rate limiters or bulkheads on connection-heavy endpoints.
- Dedicate separate pools for reporting workloads if architecture and database capacity allow.
- Prioritize short page queries for interactive requests.
- Use queues for long exports and heavy batches.

Separate pools do not create infinite database capacity. Total connections across all pools and applications must fit within the server's budget.

### 18.1. Bulkheads for Streaming Endpoints

A bulkhead can limit concurrent streaming tasks so one group of clients cannot consume all API resources. When exceeded, return a retryable overload error or enqueue the request.

Do not rely on semaphores holding permits without timeouts or cleanup. Permits must be released on complete, error, or cancel; use abstractions that integrate with the reactive lifecycle.

## 19. Common Mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Returning an unbounded query `Flux` straight to slow clients | Results and connections can stay open long | Bound results or use page queries |
| Thinking non-blocking means zero resource consumption | Pool can exhaust despite low CPU | Monitor connection hold time and active/pending pool metrics |
| Wrapping an entire stream in `@Transactional` | Transaction/connection lives for the whole response | Use long transactions only when snapshot/atomicity is explicitly required |
| Using `collectList()` on an entire table | Heap grows with total rows and high time-to-first-byte | Collect only small, bounded pages |
| Thinking `buffer(n)` releases connections per batch | A single result stream may keep the same connection | Execute separate queries per page |
| Using unbounded `onBackpressureBuffer()` | Buffers grow and can cause OOM | Keep backpressure or use bounded buffers with overflow policies |
| Using `publishOn` hoping the query finishes earlier | Queue adds buffering while connection can stay open | Decouple query from downstream via pages/bounded materialization |
| Unbounded `flatMap` calling external services | Too many concurrent requests and buffered outputs | Set finite concurrency |
| Enriching each row via HTTP inside a transaction | Connection held during network waits | Finish query per page, then enrich outside transactions |
| Using only `take(n)` while SQL stays unbounded | Driver may prefetch more and query plan lacks target | Put `LIMIT` in SQL |
| Ignoring cancellation | Resources/queries may linger after client leaves | Measure cancellation/cleanup and test with real driver |
| Only increasing pool size | Increases DB connection pressure without reducing hold time | Shorten connection hold time and cap streams |
| Using deep `OFFSET` for large exports | Database skips many rows and performance degrades | Use keyset pagination with stable cursors |
| Cursor lacks a unique tie-breaker | Rows can duplicate or skip across pages | Include a unique key in `ORDER BY` and cursor |
| Paginating while assuming a consistent snapshot | Data mutates between pages | Use cutoffs/versions/snapshots as needed |
| Relying on `fetchSize` to release connections | Cursors can still hold connections until result ends | Use page queries when releasing between parts is required |
| Not capping concurrent exports | A small group of requests can starve the pool | Quotas, bulkheads, and export jobs |

## 20. Workflow for Investigating Long Connection Holds

When incoming requests start queuing for connections or the pool frequently hits capacity, investigate in this order:

1. **Inspect pool metrics:** active/acquired, idle, pending acquire, acquire duration, and timeouts.
2. **Inspect query metrics:** compare statement execution/result time against connection hold duration.
3. **Locate long streams:** find endpoints returning `Flux`, NDJSON, SSE, or large exports.
4. **Inspect downstream:** client speed, proxy buffering, response durations, and disconnects.
5. **Inspect transactions:** check whether transactions wrap an entire `Flux` or include slow HTTP/CPU work.
6. **Inspect operators:** look for `collectList`, unbounded buffers, large prefetch, high `flatMap` concurrency, or `publishOn` queues.
7. **Inspect driver behavior:** verify fetch size, cursors, buffering, and cancellation semantics.
8. **Reproduce with a slow client:** simulate low read rates and mid-stream disconnects.
9. **Test a paged approach:** measure per-page connection hold times and memory usage.
10. **Enforce limits:** page size, query timeout, response timeout, concurrency, and active stream caps.

Do not conclude a connection leak solely because active connections rise while a stream is running. Connections may be legitimately in use. Suspect a leak when subscriptions have completed, errored, or cancelled yet connections fail to return within expected deadlines, or held connections climb steadily without dropping.

## 21. Testing with Slow Downstream Consumers and Cancellation

Ordinary tests that drain a `Flux` immediately rarely uncover connection-retention bugs. Test slow-consumption scenarios explicitly:

### 21.1. Simulating a Slow Consumer

```java
Flux<CustomerView> slowConsumer = customerService.streamCustomers()
    .delayElements(Duration.ofMillis(100));
```

This is a simple way to slow consumption in tests. It does not fully replicate HTTP network backpressure, yet it reveals publisher completion times and connection hold durations.

### 21.2. Testing Slow-Reading HTTP Clients

In WebFlux integration tests:

- Call streaming endpoints using a client that throttles demand or reads body chunks incrementally.
- Keep the client reading slowly while observing active pool connections.
- Verify the connection is released once the response finishes.
- Cancel the request mid-stream and verify cleanup/cancellation.
- Call another endpoint concurrently to verify the pool retains capacity.

### 21.3. Testing Page Queries Releasing Connections

Compare two approaches:

- A single `Flux` result consumed slowly to completion.
- Multiple small page queries, each collected via `collectList()` and sent incrementally.

Observe active connections and hold durations while the client reads pages. With paging, connections go idle between pages while memory holds only the current page.

### 21.4. Testing Transactions

If a method uses `@Transactional` or `TransactionalOperator`, verify the transaction ends when the publisher completes or cancels. Verify the connection returns to the pool after complete, error, and cancel. Against the target driver/database, verify cancellation leaves no stray open transactions or cursors.

## 22. Choosing a Strategy by Use Case

| Use Case | Strategy to Consider | Reason |
|---|---|---|
| Interactive list view | SQL `LIMIT` + small pages | Fast response, brief connection usage |
| Client needs to stream a few hundred records | Bounded `Flux` streaming | May hold connection during stream, but scope is controlled |
| Downloading millions of records | Export job + keyset pages + file/object storage | Decouples client speed from DB connections |
| Dashboard needing small data | `collectList()` or bounded aggregates | Releases query before response finishes |
| Enriching each record via HTTP | Page query then bounded-concurrency enrichment | Avoids holding connections during network waits |
| Reads requiring consistent snapshot | Explicitly designed snapshot/cutoff | Trades off consistency vs. transaction hold time |
| Continuous SSE/event streams | Avoid holding R2DBC queries indefinitely | Use a proper broker/event source instead of long DB cursors |

## 23. Principles to Remember

- Non-blocking keeps threads unblocked, yet connections, transactions, and buffers remain occupied.
- For result streams, connections are usually held until the result completes, errors, or cancels and finishes cleanup.
- Slow downstream consumption can propagate backpressure to R2DBC and prolong connection holds.
- Backpressure does not mean the driver avoids prefetching or buffering; inspect driver fetch behavior.
- Streaming media types like NDJSON/SSE express item-by-item responses, yet codecs/proxies still influence buffering.
- Transactions wrapping a `Flux` can stay open until the stream ends; `readOnly` does not release connections early.
- `collectList()` frees the query before sending the response, at the cost of heap retention and higher time-to-first-byte.
- `buffer(n)` does not issue new page queries or guarantee releasing connections between batches.
- Unbounded buffers, prefetch, and high `flatMap` concurrency can inflate memory or pending work.
- Limit data directly in SQL via `LIMIT` when the business case does not need the entire set.
- Use keyset pagination with stable cursors and unique tie-breakers for large datasets.
- Completing each page query returns connections to the pool before sending slow pages to clients.
- Pagination does not automatically guarantee consistent snapshots across pages; pick cutoffs/versions/snapshots per requirements.
- Use fetch size/cursors only when driver-supported, understanding they do not automatically release connections mid-result.
- Separate queries from slow HTTP/CPU/external-service work using pages or bounded materialization.
- For large exports, favor asynchronous jobs and files over holding single HTTP responses/connections open.
- Monitor active/idle/pending pool metrics, acquire latency, connection hold duration, query duration, and HTTP response duration.
- Test slow clients, cancellation, timeouts, and cleanup on a real WebFlux server and R2DBC driver.

The risk of holding connections open arises whenever database result lifetimes are coupled directly to downstream consumption speed. Backpressure paces data flow, yet it does not return connections to the pool while results remain open. For small, bounded streams, holding a connection during delivery may be acceptable. For large datasets or slow clients, shorten individual queries with finite pages, release connections between pages, bound buffers/concurrency, and move long exports out of HTTP request lifecycles. Combining pool metrics with response timings and cancellation tests catches pool starvation early even in fully non-blocking applications.
