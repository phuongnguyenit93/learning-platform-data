# Limiting Query Size, Row Counts, and Processing Time

## 1. Why Must Resources Be Bounded During Data Access?

A reactive API can handle many concurrent requests, but that does not mean every request should be allowed to issue unbounded queries, read millions of rows, or hold connections open indefinitely.

In a Spring WebFlux and Spring Data Relational R2DBC application, a single request can consume multiple kinds of resources:

- Memory to receive the request body, construct SQL, and hold results.
- CPU to parse search conditions, sort, convert, and serialize data.
- Connections from the R2DBC pool.
- Database processing time.
- Network bandwidth to read rows and return responses.
- Workers and queues when blocking or concurrent work is involved.
- Resources of downstream services if the request triggers side effects.

If a client can request huge page sizes, send an unbounded list of IDs, construct complex filters, or keep requests open too long, even a handful of requests can exhaust application and database resources.

This is both a security and an availability concern. An attacker does not need malicious payloads or SQL injection. Sending many valid yet excessively heavy requests can cause resource exhaustion or denial of service.

Therefore, limits must be enforced at multiple layers:

1. Request size and input dimensions.
2. Complexity of filters, sorting, and queries.
3. Number of rows read or written in one operation.
4. Response size.
5. Wait times for connections, SQL execution, and transactions.
6. Number of concurrent requests or tasks.
7. Request rate per user, tenant, or API key.

Limits must be enforced on the server. Never rely on client UI controls to bound page size or timeouts, because clients can be altered or bypassed completely.

## 2. Map of Required Limits

| Resource | Risk if unbounded | Protection mechanism |
|---|---|---|
| Request body | Excessive heap usage during decode or aggregation | Limit body and multipart sizes |
| Search keyword | Overly long filters, CPU-heavy searches | Limit length, normalize, and validate format |
| Number of filter conditions | Complex, unoptimizable queries | Filter allowlists and condition count limits |
| Sort field | Abuse of unindexed columns or SQL injection | Allowlist column names and sort directions |
| ID list | Excessive bind parameters and huge SQL | Cap element count, split into batches |
| Page size | Reading and serializing too many rows | Server-enforced max page size |
| Offset | Deep queries skip huge numbers of rows | Keyset/cursor pagination |
| Write batches | Long-held transactions and locks | Cap batch size |
| Query duration | Connections and DB workers tied up too long | Driver/database statement/query timeouts |
| Acquire wait | Requests waiting indefinitely on the pool | Pool acquire timeouts and pending limits |
| Transaction duration | Connections and locks held too long | Short transactions and timeouts |
| Concurrency | Too many simultaneous queries | Concurrency caps, bulkheads, and rate limits |
| Response size | Heap pressure and bandwidth exhaustion | Cap row counts, fields, and payload size |

No single limit protects the whole system. Combine layers so heavy requests are blocked before claiming excessive resources.

## 3. Limiting Request Body Size

### 3.1. Limit before parsing data

WebFlux can receive request bodies as streams. However, when the framework or application buffers data into memory to deserialize an object, large request bodies pressure the heap.

With Spring Boot, you can configure codec memory limits:

~~~yaml
spring:
  codec:
    max-in-memory-size: 1MB
~~~

This value is only an example. Choose according to your API contract, valid payload sizes, and how the application decodes bodies.

The codec limit is not always equivalent to a total request-body cap for every streaming pattern. For file uploads or multipart requests, configure dedicated limits for total request size, individual part size, part count, and temporary storage per your server/container and Spring Boot version.

### 3.2. Never aggregate large streams arbitrarily

Avoid calling **`collectList()`** or buffering all `DataBuffer`s in memory when payloads can be large.

For example, if an API accepts a very long list of IDs to update, deserializing the entire array into a `List` can allocate a huge object before any database query begins.

Consider:
- Limiting the element count in requests.
- Receiving data in small batches.
- Streaming when formats and business rules permit.
- Offloading large imports to asynchronous jobs rather than holding an HTTP request open.
- Checking file sizes before parsing content.

### 3.3. Limiting field counts and nesting depth

A payload that is small in bytes can still burn CPU if it contains deeply nested structures or huge element counts.

APIs should limit:
- Nesting depth of objects when payloads are tree-structured.
- Collection element counts.
- Filter and sort field counts.
- String lengths.
- Number of updatable fields.
- Elements per batch.

When requests use fixed DTOs, use Bean Validation to check fields right at the HTTP boundary.

## 4. Validating Size and Bounds on Search Parameters

Example order search DTO:

~~~java
public record OrderSearchRequest(
    @Size(max = 80)
    String keyword,

    @Min(0)
    @Max(1000)
    int page,

    @Min(1)
    @Max(100)
    int size,

    @NotNull
    OrderSortField sortBy,

    @NotNull
    Sort.Direction direction
) {
}
~~~

Enum restricting sortable columns:

~~~java
public enum OrderSortField {
    CREATED_AT,
    ID,
    STATUS
}
~~~

Controller enabling validation:

~~~java
@PostMapping("/search")
public Flux<OrderSummary> search(
        @Valid @RequestBody OrderSearchRequest request) {

    return orderService.search(request);
}
~~~

Depending on your Spring Boot and WebFlux versions, include the validation starter and corresponding method/bean validation setup. Ensure validation failures map to `400` responses per the API contract.

### 4.1. Never validate solely on the client

Clients can send `size=1000000` even if the UI displays only 20, 50, or 100 items. The server must enforce its own cap.

Out-of-bounds requests can be rejected with `400` or `422`. Some APIs clamp page size down to the maximum, though that behavior must be documented explicitly. Rejecting usually makes API misuse obvious instead of silently returning fewer rows than expected.

### 4.2. Never use arbitrary strings as column names or sort directions

Bind parameters protect values only. They cannot replace column names or SQL keywords.

Do not write:

~~~java
String sql = "SELECT * FROM orders ORDER BY " + request.sortBy();
~~~

If `sortBy` comes from the client, it can alter the SQL statement structure.

Map the enum to identifiers defined in code:

~~~java
private String sortColumn(OrderSortField field) {
    return switch (field) {
        case CREATED_AT -> "created_at";
        case ID -> "id";
        case STATUS -> "status";
    };
}
~~~

Sort direction must also be constrained to `ASC` or `DESC`. Never concatenate an arbitrary request string into SQL.

With `R2dbcEntityTemplate`, build `Sort` from controlled enums rather than passing arbitrary column names.

### 4.3. Limiting the number of filters

A search API may support multiple filters. Without limits on filter counts or `AND`/`OR` expression complexity, the server can generate huge, hard-to-optimize queries.

Specify:
- Maximum number of filters.
- Allowed filterable fields.
- Allowed operators per field.
- Maximum elements per `IN` condition.
- No client-supplied raw SQL expressions or arbitrary query criteria.
- Maximum length for keywords and wildcard patterns.

Represent search rules with structured DTOs, then let the service translate them into controlled `Criteria`/SQL.

## 5. Limiting SQL Length and Bind Parameter Counts

### 5.1. Never accept raw SQL from clients

A business API should never accept SQL strings from clients for server execution. Even with character-length caps, raw SQL opens up out-of-scope data access, expensive queries, and unauthorized operations.

Accept business parameters instead—such as status, date ranges, keywords, page size, and sort enums. The server builds SQL from allowlisted components.

### 5.2. Bind parameters for values

Safer example:

~~~java
return databaseClient.sql("""
        SELECT id, status, created_at
        FROM orders
        WHERE status = :status
          AND created_at >= :from
        ORDER BY created_at DESC, id DESC
        LIMIT :limit
        """)
    .bind("status", status)
    .bind("from", from)
    .bind("limit", limit)
    .map((row, metadata) -> new OrderSummary(
        row.get("id", Long.class),
        row.get("status", String.class),
        row.get("created_at", LocalDateTime.class)
    ))
    .all();
~~~

Bind parameters separate data values from SQL structure. They do not make table names, column names, operators, or `ORDER BY` keywords bindable.

### 5.3. Limiting `IN` lists

A request sending tens of thousands of IDs can generate a SQL statement with a massive number of bind parameters.

Example:

~~~sql
SELECT id, status
FROM orders
WHERE id IN (:id1, :id2, :id3, ...);
~~~

Maximum bind parameters depend on the database and driver. Even when supported, a huge list increases SQL size, parse time, and planning cost.

Protections:

- Cap the number of IDs per request.
- Reject empty or oversized lists per the API contract.
- Split internal workloads into fixed-size batches.
- Use array/table-valued parameters or temporary tables if supported by the database and truly needed for large lists.
- Never generate thousands of placeholders just because a client passed many items.

Example check:

~~~java
private static final int MAX_IDS_PER_REQUEST = 500;

public Flux<Order> findByIds(List<Long> ids) {
    if (ids == null || ids.isEmpty()) {
        return Flux.empty();
    }

    if (ids.size() > MAX_IDS_PER_REQUEST) {
        return Flux.error(
            new TooManyIdsException(MAX_IDS_PER_REQUEST)
        );
    }

    return orderRepository.findAllById(ids);
}
~~~

`500` is just an example. Choose a limit based on database constraints, request sizes, and measured performance.

### 5.4. Batching does not mean an unbounded transaction

If 50,000 IDs must be processed, splitting into batches shrinks each query. However, do not hold one single transaction across all 50,000 items by default.

A huge transaction can:
- Hold connections open too long.
- Hold locks too long.
- Generate heavy undo/WAL volume.
- Make rollbacks expensive.
- Increase timeout risk.

Decide whether the entire batch must be atomic or whether batches can commit independently with checkpoints and resume support. That is a business decision, not just a technical optimization.

## 6. Limiting Returned Row Counts

### 6.1. Never allow unbounded queries on search endpoints

A search endpoint should define both a default page size and a maximum page size.

Example:

~~~java
private static final int DEFAULT_PAGE_SIZE = 20;
private static final int MAX_PAGE_SIZE = 100;

private int normalizePageSize(Integer requestedSize) {
    if (requestedSize == null) {
        return DEFAULT_PAGE_SIZE;
    }

    if (requestedSize < 1 || requestedSize > MAX_PAGE_SIZE) {
        throw new InvalidPageSizeException(MAX_PAGE_SIZE);
    }

    return requestedSize;
}
~~~

Never use a request's page size without validation. Negative values, zero, or oversized values must be handled per API contract.

### 6.2. Enforce `LIMIT` in the database

Row limits should be enforced inside the query itself rather than calling `take()` in application code after the database has read everything.

`DatabaseClient` example:

~~~java
return databaseClient.sql("""
        SELECT id, status, created_at
        FROM orders
        WHERE status = :status
        ORDER BY created_at DESC, id DESC
        LIMIT :limit
        OFFSET :offset
        """)
    .bind("status", status)
    .bind("limit", pageSize)
    .bind("offset", offset)
    .map((row, metadata) -> mapOrder(row))
    .all();
~~~

`LIMIT`/`OFFSET` syntax varies across database engines. Use syntax supported by your target database and driver.

With `R2dbcEntityTemplate`, set limits on `Query`:

~~~java
Query query = Query.query(
        Criteria.where("status").is(status)
    )
    .limit(pageSize)
    .offset(offset);

return template.select(query, Order.class).all();
~~~

Exact API signatures can vary across Spring Data Relational versions. Check the signatures in your project's version.

### 6.3. Never load everything first and limit afterward

Inappropriate:

~~~java
return orderRepository.findAll()
    .collectList()
    .map(all -> all.stream()
        .limit(100)
        .toList()
    );
~~~

The database may have already transmitted every row and the application buffered them all in memory before the limit is applied.

Apply the limit in the database query, then process only the bounded result set.

### 6.4. Limit both row count and per-row size

A query returning 100 rows can still be very heavy if every row contains a large `TEXT`/`BLOB` column.

Consider:
- Selecting only the columns needed for the response.
- Omitting large files/blobs from list endpoints.
- Moving large content to a separate authorized download endpoint.
- Capping lengths on user-entered fields.
- Capping JSON response sizes for heavy APIs.

Row count alone does not capture full response cost.

## 7. Pagination: Offset and Keyset

### 7.1. Offset pagination

Offset pagination suits small lists or cases where clients need to jump to arbitrary pages:

~~~sql
SELECT id, status, created_at
FROM orders
ORDER BY created_at DESC, id DESC
LIMIT :pageSize
OFFSET :offset;
~~~

Limit both `page` and `pageSize`. Compute `offset` using a wide enough integer type and check for overflow before binding:

~~~java
long offset = Math.multiplyExact((long) page, pageSize);
~~~

If the API allows huge page numbers, the database may scan and discard many rows before returning the requested page. Deep offset queries grow increasingly expensive.

### 7.2. Sorting must be deterministic

Pagination requires a deterministic order. Sorting only by `created_at` when multiple rows share timestamps causes pages to repeat or skip rows as data changes.

Add a unique column as a tie-breaker:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

Both sort fields and directions must still come from an allowlist.

### 7.3. Keyset pagination

For large datasets or continuous next-page navigation, keyset pagination is usually far more efficient than deep offsets.

Fetching the first page:

~~~sql
SELECT id, status, created_at
FROM orders
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT :limit;
~~~

Subsequent pages use the last row values from the previous page:

~~~sql
SELECT id, status, created_at
FROM orders
WHERE status = :status
  AND (
      created_at < :lastCreatedAt
      OR (
          created_at = :lastCreatedAt
          AND id < :lastId
      )
  )
ORDER BY created_at DESC, id DESC
LIMIT :limit;
~~~

The cursor holds the last sort values and can be signed or encoded if clients should not tamper with it. Even with a signed cursor, the service must still check page size, filters, and access rights.

Keyset pagination does not automatically create a snapshot-consistent view across concurrent edits. It resumes from the last position without deep-offset costs; behavior under concurrent data changes still needs to be defined.

### 7.4. Cursors are not access control

Never treat possessing a cursor as proof the client is allowed to read subsequent rows. Every page query must enforce the same tenant/user authorization and data filters as the first page.

If a cursor encodes sensitive IDs or timestamps, avoid exposing unnecessary details. Sign/encode cursors and set expirations where appropriate for the API.

## 8. Limiting Count and Aggregation Queries

### 8.1. `COUNT(*)` can be expensive

An API returning total counts on every search forces the database to process a large dataset solely to compute the total.

On large tables with complex filters, `COUNT(*)` can cost more I/O or CPU than fetching the page itself.

Consider:
- Returning only whether a next page exists.
- Bounding date ranges or scoping by tenant.
- Caching count results if semantics allow.
- Using approximate estimates when acceptable to the business.
- Running counts only when the client explicitly requests them.
- Setting separate timeouts and monitoring on aggregate queries.

### 8.2. Limiting `GROUP BY` and date ranges

Reporting queries can produce small outputs while scanning huge datasets. Capping returned rows does not bound internal database work.

For reports, limit:
- Maximum date ranges.
- Number of groups or grouping dimensions.
- Number of sort/group fields.
- Permitted filters.
- Aggregation depth.
- Database execution time.

Heavy reports should run asynchronously, store results, or query dedicated read models instead of tying up HTTP requests and connection pools.

## 9. Limiting Write Row Counts and Batch Sizes

### 9.1. Bulk insert/update

Bulk write APIs must limit items per request. One request can hold 100,000 items even if each item is tiny.

Define:
- Maximum items per request.
- Batch size.
- Bind parameters per statement.
- Total duration budget for a batch run.
- Maximum concurrent batches.
- Error recovery behavior between batches.

Example splitting a list into batches:

~~~java
Flux.fromIterable(items)
    .buffer(200)
    .concatMap(batch -> saveBatch(batch));
~~~

`concatMap` processes batches sequentially, bounding concurrent batches. `200` is just an example; tune based on parameter limits, row sizes, and the database.

### 9.2. Choosing appropriate atomicity

Two distinct business patterns exist:

- The entire import must succeed or fail together: requires a larger transaction or an appropriate staging/swap strategy, weighing locks and transaction logs carefully.
- Each batch can complete independently: use short per-batch transactions, record checkpoints, and support resumption.

Never split an all-or-nothing transaction into smaller transactions without recovery rules. Conversely, never wrap tens of thousands of operations in a single transaction unless business rules truly demand it.

### 9.3. Limiting batch concurrency

Do not run hundreds of batches concurrently just because reactive APIs make it easy:

~~~java
Flux.fromIterable(batches)
    .flatMap(this::saveBatch, 4);
~~~

The parameter `4` caps concurrent batch subscriptions. Size it based on pool size, database capacity, lock contention, and traffic from other requests.

If all batches share a single transaction connection, parallel execution may not be supported by the driver. When sharing one transaction, prefer sequential execution and verify connection semantics.

## 10. Limiting Time at Every Layer

A request accessing a database moves through multiple stages. Each stage needs its own timeout.

| Layer | What the timeout protects |
|---|---|
| Gateway/client | Total time the client waits for a response |
| Web server/request | Maximum lifetime allowed for an HTTP request |
| Rate limiter/bulkhead | Queue wait time or queue depth before processing |
| R2DBC pool acquire | Time spent waiting for a connection |
| Connection creation | Time to establish a new connection |
| SQL statement/database | Time the database is allowed to execute a query |
| Transaction | Maximum duration a transaction may remain open |
| Downstream client | Time waiting on external services |
| Reactor timeout | Publisher deadline at the point applied |

No single global timeout replaces all of these. If acquire timeout is 3 seconds while client timeout is 2 seconds, the client may abort before the pool times out. If transaction timeout is too long, connections stay tied up after the API response is no longer useful.

### 10.1. Acquire timeout

R2DBC Pool can cap connection wait times:

~~~java
ConnectionPoolConfiguration configuration =
    ConnectionPoolConfiguration.builder(connectionFactory)
        .maxSize(20)
        .maxPendingAcquire(100)
        .maxAcquireTime(Duration.ofSeconds(2))
        .build();
~~~

Exact builder methods and defaults depend on the R2DBC Pool version. Check your application's actual configuration.

Acquire timeout protects pool wait time. It does not limit how long a SQL statement runs once a connection is acquired.

### 10.2. Query or statement timeout

Databases and drivers provide ways to cap SQL execution time. Mechanisms differ across database engines and driver versions.

For example, PostgreSQL supports `statement_timeout` at session or transaction scope, such as `SET LOCAL statement_timeout` inside a transaction. Apply the right connection/transaction scope and prevent session state from leaking into subsequent requests on pooled connections.

Do not assume a single generic R2DBC property behaves identically on every driver. Check your target driver and database, and verify queries actually terminate when timed out.

### 10.3. Transaction timeout

You can set a timeout on service transactions:

~~~java
@Transactional(
    transactionManager = "r2dbcTransactionManager",
    timeout = 5
)
public Mono<Order> confirm(Long orderId) {
    return performConfirmation(orderId);
}
~~~

Values are in seconds in Spring's `@Transactional` configuration. Actual enforcement depends on the transaction manager, driver, and resource.

Transaction timeout is not query timeout. A single transaction may span multiple statements and waits; enforce bounds at both layers.

### 10.4. Reactor timeout

You can bound a publisher's execution time:

~~~java
public Mono<OrderSummary> loadSummary(Long orderId) {
    return orderRepository.findById(orderId)
        .map(OrderSummary::from)
        .timeout(Duration.ofSeconds(3));
}
~~~

`timeout` emits an error if the publisher produces no signal within the duration. Cancellation propagates upstream, though whether the underlying database statement stops immediately depends on the driver and database.

Never treat a Reactor `timeout` as proof that the server canceled the query. For expensive queries, also configure database-side statement timeouts and observe queries/sessions after timeouts.

### 10.5. Using an end-to-end deadline budget

Suppose an API has a 4-second deadline. The budget might be allocated as:

~~~text
Total API deadline: 4 seconds
  |
  +-- waiting for connection: max 0.5 seconds
  |
  +-- query and transaction: ~2 seconds
  |
  +-- response processing/serialization: ~0.5 seconds
  |
  +-- network and scheduling buffer: ~1 second
~~~

This is only an illustrative allocation. Layer timeouts must align with the overall deadline. If every stage has a 10-second timeout, a request can outlive what clients or gateways tolerate.

## 11. Timeouts, Cancellation, and Resource Cleanup

When a Reactor timeout fires or a client disconnects, cancellation travels upstream through the reactive chain. However, cancellation does not always halt underlying work instantaneously.

Distinguish between:

- Publisher canceled.
- Driver canceled the statement.
- Database server stopped the query.
- Transaction rolled back.
- Connection released back to the pool.

These events do not necessarily happen simultaneously. A blocking library or a driver with limited cancellation support can hold resources even after downstream stops listening.

To protect the system:
- Configure timeouts at client, driver, and database layers where supported.
- Keep transactions short.
- Never run blocking calls on event-loop threads.
- Ensure connection cleanup on complete, error, and cancel signals.
- Monitor acquired connection counts after timeouts.
- Avoid blindly retrying side effects whose completion state is uncertain.

If a timeout happens after the database committed but before the client received the response, a client retry can duplicate the action. For write APIs, use idempotency keys where business semantics require them.

## 12. Limiting Concurrency and Rates

### 12.1. Concurrency in Reactor

`flatMap` lets you cap the number of active inner publishers:

~~~java
return Flux.fromIterable(orderIds)
    .flatMap(
        id -> orderRepository.findById(id),
        8
    );
~~~

`8` is a per-pipeline concurrency limit in this example. It is not a system-wide limit: each request creates its own pipeline, so total concurrency still scales with concurrent requests.

If each request runs at concurrency 8 and 100 requests arrive together, total inner operations can reach roughly 800.

### 12.2. Rate limiting per user or tenant

A client can flood the system with many small requests that add up to heavy load. Rate limit by:
- Authenticated user.
- Tenant.
- API key/client.
- Endpoint or operation group.
- IP address where appropriate, though never as the sole identity.

Rate limits can sit at the API gateway or inside the application. With distributed rate limiters, ensure instances share state appropriately.

### 12.3. Bulkheads

Bulkheads cap how many concurrent tasks can consume a resource pool. For example, heavy reporting queries can have their own concurrency limit so they cannot starve order-write connections.

You can isolate pools, schedulers, or semaphores per workload, while keeping total connections within database capacity. Adding multiple pools does not increase the database's total capacity.

### 12.4. Backpressure does not replace all limits

Reactive Streams backpressure lets consumers regulate item emission rate inside a pipeline. It does not automatically bound:
- Aggregated request body sizes.
- Concurrent HTTP requests.
- Connection pool size.
- Array lengths sent in JSON requests.
- SQL query complexity.
- Query execution time.
- Request rates per tenant.

Enforce explicit limits at each resource boundary.

## 13. Designing a Bounded Search API

Example service accepting a validated DTO:

~~~java
public Flux<OrderSummary> search(OrderSearchRequest request) {
    int limit = normalizePageSize(request.size());
    long offset = Math.multiplyExact((long) request.page(), limit);

    String column = sortColumn(request.sortBy());
    String direction = request.direction() == Sort.Direction.ASC
        ? "ASC"
        : "DESC";

    String sql = """
        SELECT id, status, created_at
        FROM orders
        WHERE status = :status
        ORDER BY %s %s, id DESC
        LIMIT :limit
        OFFSET :offset
        """.formatted(column, direction);

    return databaseClient.sql(sql)
        .bind("status", request.status())
        .bind("limit", limit)
        .bind("offset", offset)
        .map((row, metadata) -> mapSummary(row))
        .all()
        .timeout(Duration.ofSeconds(2));
}
~~~

In this example:

- `status` is bound as a value.
- Sort field is mapped from an allowlisted enum.
- Direction can only be `ASC` or `DESC`.
- Page size is validated and bounded.
- Offset uses `long` arithmetic to reduce overflow risk.
- SQL enforces `LIMIT`.
- The publisher has a timeout.

The 2-second timeout is illustrative and should align with acquire timeout, database statement timeout, transaction deadline, and HTTP deadline.

If the API supports multiple filters, construct queries from controlled predicates. Never concatenate raw fragments from clients into SQL.

## 14. Limiting Responses and Result Processing

### 14.1. Return small DTOs instead of full entities

List endpoints typically need only a few fields. There is no need to return entire entities carrying blobs, large metadata, or unused relationships.

Example:

~~~java
public record OrderSummary(
    Long id,
    String status,
    Instant createdAt
) {
}
~~~

Selecting only required columns reduces:
- Data transferred from database over the network.
- Mapping overhead.
- Application heap usage.
- JSON response size.
- Accidental exposure of sensitive fields.

### 14.2. Never call `collectList` on unbounded datasets

`collectList` gathers every emitted element into a `List`. It is fine when element counts are strictly bounded, but dangerous on an unbounded `Flux`.

Avoid:

~~~java
return repository.findAll()
    .collectList()
    .map(this::buildResponse);
~~~

if `findAll` can return hundreds of thousands of rows.

Instead:
- Put `LIMIT` inside the query.
- Return a `Flux` when the API supports streaming.
- Paginate results.
- Use asynchronous export jobs for very large datasets.
- Cap total response bytes if rows contain large fields.

### 14.3. Streaming also requires limits

Streaming does not mean resources are free. A long-lived stream holds connections, request contexts, and network buffers.

Set:
- Maximum rows per stream.
- Maximum duration or lifetime deadline.
- Rate and concurrency limits.
- Cancellation and cleanup rules.
- Resume/cursor support if clients need continuation.

For large exports, generate a file via a background job, store the result, and let authorized clients download it instead of holding a database connection open for the entire download.

## 15. Scoping Queries by Access Control and Tenant

Row limits do not replace authorization.

A query with `LIMIT 20` can still read another tenant's data if partitioning predicates are omitted.

Every query must enforce the proper access scope:
- Tenant ID comes from the authenticated security context; never trust client-declared tenant IDs.
- Users read only resources they are authorized to access.
- Filters and sorts cannot expose out-of-scope internal columns.
- Cursors are never proof of authorization.
- Count queries must carry the same tenant and access predicates as data queries.

Example:

~~~sql
SELECT id, status, created_at
FROM orders
WHERE tenant_id = :authenticatedTenantId
  AND status = :status
ORDER BY created_at DESC, id DESC
LIMIT :limit;
~~~

`authenticatedTenantId` must come from the verified principal/security context. Never merely bind a `tenantId` straight from a request body without permission verification.

## 16. Observing and Alerting on Limits

Even well-designed limits need metrics to confirm they are sized properly.

Metrics worth tracking:

| Metric/measurement | What to observe |
|---|---|
| Request body rejected | How many requests exceed size limits |
| Validation failure | Clients sending invalid page sizes/filters |
| Query duration | Whether queries exceed time budgets |
| Rows returned | How many rows each request reads |
| Response bytes | Whether responses grow too large |
| Acquire latency/timeout | Whether requests wait on connections |
| Pool acquired/idle/pending | Pool headroom vs. saturation |
| Transaction duration | Whether transactions hold connections too long |
| Rate limit rejected | Which clients/tenants exceed quotas |
| Batch size and duration | Whether batches are oversized or slow |
| Cancellation/timeout count | Canceled requests or expired deadlines |

Never put user IDs, emails, SQL parameters, or cursors into metric labels if doing so creates high cardinality or leaks data. Use controlled, masked traces/logs when per-request investigation is needed.

### 16.1. Recording rejection reasons

Distinguish error causes:
- Request body too large.
- Page size exceeds limit.
- Too many IDs or filters.
- Acquire timeout.
- Query timeout.
- Transaction timeout.
- Rate limit exceeded.
- Client cancellation.

If all of these return a generic "database error", operators cannot tell which limit was hit.

Never expose SQL, internal table names, stack traces, or connection details in public responses. Log details internally with sensitive data masked.

### 16.2. Impact-based alerting

Examples:
- Rising acquire timeout rate.
- Query p95/p99 crossing thresholds.
- Abnormal increases in transaction duration.
- Spikes in rate-limited or size-rejected requests.
- Response sizes exceeding baseline.
- Persistent pool pending queues.

Some rejections due to limits are expected behavior. Alerts should distinguish client misuse or bot traffic from system issues rejecting legitimate requests.

## 17. Testing Limits

### 17.1. Testing validation at the HTTP boundary

Verify:
- Bodies at the exact limit are accepted.
- Bodies above the limit are rejected.
- Oversized keywords are rejected.
- Negative, zero, or oversized page sizes are rejected.
- Out-of-range page numbers are rejected.
- Sort fields outside the enum are rejected.
- Oversized ID lists are rejected.
- Excessive or overly deep filters are rejected.

Tests must confirm services and repositories are not invoked when requests fail at the validation layer.

### 17.2. Testing query limits

Seed more rows than the maximum page size, invoke the service, and confirm:
- Returned rows never exceed the limit.
- The query itself enforces the limit in the database.
- No intermediate step collects all rows before slicing.
- Sorting is deterministic with a tie-breaker key.
- Subsequent-page cursors never duplicate rows.

### 17.3. Testing timeouts

Controlled publishers can verify timeout behavior in tests:

~~~java
StepVerifier.withVirtualTime(() ->
        service.loadSlowData()
            .timeout(Duration.ofSeconds(2))
    )
    .thenAwait(Duration.ofSeconds(2))
    .expectError(TimeoutException.class)
    .verify();
~~~

Virtual time works with publishers using schedulers that support virtual time. It does not prove the database server or R2DBC driver canceled a real query. Write separate integration tests for statement timeouts and connection cleanup.

### 17.4. Testing acquire timeouts and pool exhaustion

Use a small test pool `maxSize`, hold connections with controlled test publishers, and submit additional requests. Verify:
- Pending acquisitions grow up to the configured cap.
- Acquire timeouts emit errors when wait time expires.
- Connections are released on complete, error, and cancel.
- Subsequent requests can acquire connections again.
- No connections leak.

Never use `Thread.sleep` to manufacture contention. Use barriers or controlled publishers to govern release timing.

### 17.5. Load testing and end-to-end limits

Load tests should simulate:
- Many concurrent users.
- Valid requests at maximum page size.
- Expensive filters.
- Burst traffic.
- Slow database responses.
- Slow downstreams.
- Mid-flight client cancellations.
- Multi-tenant concurrency.

Observe p95/p99 latency, error rates, acquired/idle/pending connections, query durations, and database sessions. Limits must protect the system while meeting SLOs for valid requests.

## 18. Common Mistakes

| Mistake or misconception | Consequence | Remedy |
|---|---|---|
| Capping page size only in UI | Clients send huge sizes directly | Validate on the server |
| Limiting after `collectList` | Database and app already read/buffered all rows | Enforce `LIMIT` in the query |
| Accepting raw SQL from clients | Loss of structural and cost control | Use allowlisted filter DTOs |
| Concatenating request sort fields into SQL | Can alter SQL structure | Map enums to fixed identifiers |
| Thinking value binding secures identifiers | Bind parameters cannot bind column names | Allowlist tables/columns/operators |
| Allowing unbounded `IN` lists | Long SQL, excessive bind parameters, heavy load | Limit element counts or batch |
| Unbounded offsets | Deep page queries become very slow | Cap page number or use keyset pagination |
| Unstable sorting | Pages repeat or skip rows | Add a unique tie-breaker |
| Counting on every query | Heavy database CPU/I/O | Count only when needed with bounded scope |
| Returning full entities in lists | Large responses and potential field leaks | Use projections/DTOs with needed columns |
| Calling `collectList` on unbounded `Flux` | Heap spikes sharply | Limit, paginate, or stream safely |
| Setting only Reactor timeouts | Driver/database may not stop queries | Add statement timeouts and test cleanup |
| One timeout for every layer | Requests wait too long or cut off in the wrong place | Budget deadlines per layer |
| Holding transactions across external HTTP calls | Connections stay tied up; HTTP side effects do not roll back | Separate transactions and use outbox/saga |
| Unbounded `flatMap` | Too many concurrent queries | Cap concurrency |
| Increasing pool size instead of bounding workload | Database becomes even more overloaded | Investigate queries, hold times, and total connections |
| Relying solely on backpressure | Does not bound body size, query complexity, or rate | Add explicit limits at each boundary |
| Treating cursors as authorization | Users probe cursors from other resources | Enforce authorization on every query |

## 19. Workflow for Establishing Safe Limits

When building or reviewing an R2DBC endpoint, proceed in order:

1. Identify every resource a request can consume: body, filters, queries, rows, response, connections, and time.
2. Cap request body and multipart sizes on the server.
3. Use validated DTOs for keywords, page, page size, filters, sorting, and collections.
4. Permit only allowlisted fields and operators.
5. Bind every SQL value; never accept raw SQL from clients.
6. Cap bind parameter counts, ID counts, and filter counts.
7. Put `LIMIT` in queries with deterministic sorting.
8. Use keyset pagination for large datasets or deep pages.
9. Select only needed columns and bound response size.
10. Batch writes and cap concurrency.
11. Configure pool acquire timeouts and pending limits.
12. Configure driver/database statement timeouts and appropriate transaction timeouts.
13. Set overall request deadlines and downstream timeouts.
14. Ensure cancellation and cleanup never leak connections.
15. Enforce authorization and tenant filters on every query, including counts and next pages.
16. Monitor rows returned, response bytes, query duration, pool wait, and transaction duration.
17. Write integration tests for boundary values, timeouts, cancellation, and pool exhaustion.
18. Run load tests to verify limits protect the database while meeting SLOs.

## 20. Self-Check Exercises

### Exercise 1: Page size

An API lets clients pass `pageSize`. The UI displays at most 100 items, yet a client sends 500,000. What should the server do?

Hint: Validate on the server and reject or enforce the contract maximum. Put `LIMIT` directly in the query.

### Exercise 2: Raw SQL

An endpoint takes `sortBy` and concatenates it directly into `ORDER BY`. Why doesn't parameter binding fix this?

Hint: Bind parameters represent values only, not SQL identifiers or keywords. Map an enum to allowlisted column names.

### Exercise 3: `IN` list

A request contains 20,000 IDs. Which limits need review?

Hint: Body size, element count, database/driver bind parameter limits, query size, batch size, and processing time.

### Exercise 4: `LIMIT`

Why is `repository.findAll().collectList().map(list -> list.subList(0, 100))` not a safe query limit?

Hint: All rows are read and buffered on the heap before slicing. Enforce `LIMIT` inside the SQL or `Query`.

### Exercise 5: Offset pagination

Why can very large offsets be slow?

Hint: The database may scan and discard many rows before reaching the requested page. Consider keyset pagination with deterministic ordering.

### Exercise 6: Acquire timeout

If a request hits an acquire timeout, does that mean SQL ran too long?

Hint: No. The request never acquired a connection, so the SQL statement may not even have started.

### Exercise 7: Reactor timeout

A publisher times out after 2 seconds. Can we conclude the database query stopped immediately?

Hint: No. Cancellation goes upstream, but whether the statement halts depends on the driver and database. Add statement timeouts and verify cleanup.

### Exercise 8: Transaction duration

A service opens a transaction, calls an 8-second HTTP service, and then updates an order. What impacts can occur?

Hint: Connections and transactions remain held during the wait; HTTP side effects do not roll back with R2DBC. Move external calls outside the transaction.

### Exercise 9: Concurrency

A request uses `flatMap` concurrency 10 and 100 requests arrive concurrently. Roughly how many inner operations can be active?

Hint: Roughly 1,000 if all requests hit maximum concurrency. Limit total load at the gateway, service, and database.

### Exercise 10: Response size

A page has only 50 rows, but each row contains a 5 MB `BLOB` field. Is a page size of 50 enough to protect responses?

Hint: No. Limit per-record size and response bytes too; serve large payloads from a separate endpoint.

## 21. Takeaways

- Limiting query size, row counts, and processing time is part of security and availability.
- Always validate on the server; never rely on UI/client-side limits.
- Bound request bodies, string lengths, filter counts, collection sizes, and nesting depth.
- Never accept raw SQL from clients.
- Bind parameters for values; allowlist identifiers, sort fields, and operators.
- Limit `IN` list elements and bind parameters; batch large jobs.
- Enforce `LIMIT` inside SQL or `Query` rather than reading everything and slicing later.
- Cap row counts, per-row size, and total response bytes.
- Use deterministic sorting; keyset pagination fits large datasets and deep pages.
- `COUNT` and `GROUP BY` can still be expensive even when returning few rows.
- Limit batch size and concurrency; avoid spawning too many simultaneous queries.
- Acquire timeouts, statement timeouts, transaction timeouts, downstream timeouts, and request deadlines protect different layers.
- Reactor timeouts send cancellation but do not guarantee immediate query termination on the database.
- Short transactions reduce connection and lock hold times.
- Backpressure does not replace bounds on request bodies, query complexity, rates, or connection pools.
- Apply authorization and tenant filters to every query, including counts and subsequent pages.
- Monitor query duration, rows returned, response bytes, acquire wait, pending count, and transaction duration.
- Test boundary values, timeouts, cancellation, pool exhaustion, and load against the target database and driver.

A secure R2DBC API must bound how much work each request can demand, how many resources can be consumed concurrently, and how long those resources can be held. Apply bounds from request bodies down to SQL, row counts, responses, connection pools, and transactions, while enforcing access controls and measuring real behavior. When each layer has a clear budget, an oversized or overly slow request is contained before it impacts the entire application.
