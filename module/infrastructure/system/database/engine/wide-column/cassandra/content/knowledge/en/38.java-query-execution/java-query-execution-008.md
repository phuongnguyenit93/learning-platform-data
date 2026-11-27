# Per-Query Timeouts, Page Sizes, and Statement Attributes from Java in Apache Cassandra

## 1. Why does per-query configuration matter?

Apache Cassandra is a distributed **wide-column** database: data is distributed by **partition key**, replicated per replication factor (RF), and read/written through a coordinator at a consistency level (CL). In the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module, query-driven table design, CQL, replication, compaction, repair, and error handling all shape how long a request actually takes to finish.

A Java application typically handles several distinct workloads:

- An API looking up a single order by `order_id`, needing fast responses and one row.
- An API listing orders by `customer_id`, potentially spanning multiple pages.
- A worker updating status or recording events, requiring careful CL and idempotency choices.
- A reconciliation job reading partitions with a longer time budget, yet needing **bounded load**.

Using a single timeout, page size, and retry policy across every query pushes the system into two extremes: **timing out prematurely** on legitimate paginated queries, or **holding connections/requests too long** when a partition grows huge or the cluster is under heavy compaction.

This lesson focuses on **per-statement attributes in Java Driver 4.x**:

1. **Timeout**: request duration limit from the driver's perspective, distinct from business deadlines and Cassandra server timeouts.
2. **Page size**: the CQL protocol page size requested by the driver, not the size of an HTTP response.
3. **Per-query attributes**: consistency level, serial consistency for LWTs, idempotence, execution profiles, tracing, and related options.

**Expected outcome:** you will be able to configure controlled defaults, override individual statements via the right APIs, understand replica/CL effects, execute synchronously or asynchronously, handle timeouts without duplicate writes, and benchmark performance properly.

## 2. Business example and two query-driven tables

Assume the cluster has a real datacenter named `dc1` and keyspace `commerce` with RF=3 in that DC. Learning schema:

```sql
CREATE KEYSPACE IF NOT EXISTS commerce
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

-- Point lookup for one order by partition key.
CREATE TABLE IF NOT EXISTS commerce.orders_by_id (
  order_id uuid PRIMARY KEY,
  customer_id uuid,
  status text,
  updated_at timestamp
);

-- List a customer's orders in chronological order.
CREATE TABLE IF NOT EXISTS commerce.orders_by_customer (
  customer_id uuid,
  created_at timestamp,
  order_id uuid,
  status text,
  PRIMARY KEY ((customer_id), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
```

**Lab note:** RF and DC name must match your actual topology. A single-node cluster cannot satisfy `RF=3` with `LOCAL_QUORUM`; for single-node lab practice, choose an appropriate RF and document the difference from production.

Two queries:

```sql
-- Query a single partition and single row by order_id:
SELECT order_id, status, updated_at
FROM commerce.orders_by_id
WHERE order_id = ?;

-- Query a partition that may hold many rows by customer_id:
SELECT created_at, order_id, status
FROM commerce.orders_by_customer
WHERE customer_id = ?;
```

Setting `pageSize=100` does not make a query missing its partition key efficient. If a `customer_id` partition grows oversized or accumulates tombstones, fix the **data model, retention, and partition organization**, not just the timeout.

## 3. Three configuration layers: defaults, execution profiles, and statements

Java Driver 4.x exposes three levels of settings:

| Layer | Example | Purpose |
| --- | --- | --- |
| **Default config** | `basic.request.timeout`, `basic.request.page-size` | Sets the baseline for requests without overrides |
| **Execution profile** | Profile `order-list` with smaller page size or dedicated timeout | Groups policies for queries sharing an SLA |
| **Statement attributes** | `bound.setTimeout(...)`, `bound.setPageSize(...)` | Local override for one specific request |

Example Driver 4.x HOCON configuration in a Java project:

```hocon
datastax-java-driver {
  basic {
    request {
      timeout = 2 seconds
      page-size = 500
      consistency = LOCAL_QUORUM
    }
  }
  profiles {
    order-list {
      basic.request.timeout = 4 seconds
      basic.request.page-size = 100
      basic.request.consistency = LOCAL_ONE
    }
  }
}
```

This is an **illustrative template**, not a universal SLA/CL recommendation. If a list API cannot tolerate stale reads, **never** set `LOCAL_ONE` just to shave latency. Base CL on business contracts, RF, and how the application synchronizes data.

Selecting a profile and overriding timeout on the statement:

```java
BoundStatement query = prepared.bind(customerId)
    .setExecutionProfileName("order-list")
    .setTimeout(Duration.ofSeconds(3))
    .setPageSize(80);
```

When an attribute is set explicitly on the statement, it takes precedence over the profile's value; for attributes not overridden, the driver reads from the chosen profile. When no profile is selected, the driver uses the base defaults. Verify **exact options supported by your driver version**; never assume every advanced setting has a statement-level setter.

### Do not alter global config for a single request

If only one endpoint needs 100-row pages, configure it on the **statement or profile** instead of forcing page size 100 across the whole application. This keeps point queries, list queries, and workers cleanly decoupled.

## 4. Timeouts: distinguishing four separate clocks

The word “timeout” spans multiple mechanisms. When a Java app sends a request, at least four clocks matter.

| Type | Where set | On expiration | What to know |
| --- | --- | --- | --- |
| **Business deadline** | HTTP/gRPC/worker/job | API may no longer wait or keep processing | May span multiple Cassandra queries, app logic, and network |
| **Driver request timeout** | `basic.request.timeout` or `Statement.setTimeout(Duration)` | Driver fails the request if no valid response arrives in time | Client-side timeout; **does not roll back CQL** already sent to servers |
| **Server-side read/write timeout** | Cassandra config by version, CL, replica state | Coordinator returns `ReadTimeout`/`WriteTimeout` when insufficient replicas respond in time | Can occur before the driver timeout |
| **Connection/initialization timeout** | Driver/network config | Fails to connect to a node, open a session, or complete handshake | Distinct from per-statement execution timeout |

Example timeline:

```text
HTTP request           Java Driver               Cassandra
   |                         |                        |
   |-- call service -------->|                        |
   |                         |--- send CQL ---------->|
   |                         |                        | coordinator/replicas processing
   |                         |<-- no response yet ----|
   |               [driver timeout]                   |
   |<-- 504/controlled err --|                        | data may already be written!
   |                         |                        | mutation may finish afterward
```

When a client-side timeout fires, **you cannot conclude the write failed**. A timeout means the client did not receive enough confirmations within its budget, not that the database rolled back a transaction.

### 4.1. Setting per-statement timeouts

```java
BoundStatement readOne = selectById.bind(orderId)
    .setTimeout(Duration.ofMillis(700));

BoundStatement readList = selectByCustomer.bind(customerId)
    .setTimeout(Duration.ofSeconds(3))
    .setPageSize(100);
```

Both durations above are **illustrative values**. Production services should pick timeouts from SLOs, measured latency distributions, cross-DC RTT, CL, retries/speculative execution, and external deadlines.

- Timeout too low: increases false failures, unnecessary retries, and cluster load.
- Timeout too high: holds resources longer, swells backlogs, and hides hot partitions/compaction issues.
- Never set unbounded timeouts on user-facing requests; enforce explicit bounds and cancellation/reconciliation.
- A multi-page query can issue **several separate CQL requests**; budget for the **entire operation**, not just a single page fetch.

### 4.2. Relationship to HTTP deadlines

Suppose an API targets a `1.5 s` response deadline and executes two sequential Cassandra queries. Giving each query a `2 s` timeout contradicts the deadline, because a single query can exhaust the whole API budget. Instead, track **remaining budget**:

```text
API deadline = start time + 1500 ms
Remaining budget before query 1 = 1300 ms
Remaining budget before query 2 = 500 ms
If remaining budget <= minimum threshold:
    Stop or return a controlled error; do not send more CQL
```

Never add timeouts mechanically: logging, serialization, network hops, and app logic consume time too. And if your framework supports cancellation, remember that **canceling a Java future/call does not guarantee stopping a mutation already sent to Cassandra**.

### 4.3. When timeouts signal overload

A partition with millions of rows, heavy tombstones, or a node bogged down in compaction can drive up `ReadTimeout`. Root remedies include:

- Redesigning partition keys/buckets for oversized time-series or list tables.
- Reducing Java fan-out and in-flight requests, balancing load, and adding backpressure.
- Checking replication/repair, disk I/O, GC, pending compactions, and token ownership.
- Tuning page size against real row sizes and data volumes.
- Inspecting driver and server metrics to pinpoint the bottleneck before altering timeouts.

**Raising timeouts never fixes a hot partition or missing replicas.**

## 5. Page size is neither LIMIT nor HTTP pagination

`Page size` in Driver 4.x is the **target number of rows per CQL protocol page fetch**. It splits a large result set into incremental fetches instead of pushing all rows through RAM and the network at once.

```java
BoundStatement statement = selectByCustomer.bind(customerId)
    .setPageSize(100);
```

Practical semantics:

- It is a **protocol/driver page size**, not a promise that every response contains exactly 100 rows.
- Cassandra may return **fewer** rows depending on execution state, byte-size limits, and server guardrails. Driver auto-paging also affects how many rows the app observes at once.
- `pageSize` does not cap the **total** rows read; it only chunks delivery into pages.
- CQL `LIMIT 100` caps total rows returned by the query, whereas `pageSize=100` chunks retrieval. Both can be combined when appropriate.
- Page size does not guarantee a lightweight request: tombstone scans, server-side filtering, or massive partitions can still consume heavy resources.
- Never treat `pageSize` as an HTTP API contract (“every HTTP page has 100 orders”) without application-level paging-state handling and boundaries.

### 5.1. Comparing `LIMIT`, page size, and business pages

| Mechanism | Controls | Caps total results? | Example |
| --- | --- | --- | --- |
| CQL `LIMIT 50` | Maximum total rows returned per CQL semantics | **Yes** (for that query) | Need only the 50 newest orders |
| Driver `setPageSize(50)` | Target rows per fetch page | **No** | Iterate many rows in chunks |
| HTTP `pageSize=50` | API pagination contract | Depends on implementation | Return up to 50 items and a continuation token |
| Backpressure / bulkhead | Concurrent requests, rows, or jobs | Indirectly | Max 16 in-flight Cassandra requests |

Small page sizes shrink per-fetch payloads yet increase network round trips; large page sizes cut round trips yet raise RAM, I/O, and single-page latency spikes. Benchmark with **real row byte sizes**, not just row counts.

### 5.2. Never use `ALLOW FILTERING` to “solve” paging

If a table only has partition key `order_id`, `WHERE customer_id = ?` does not fit the design. Adding `ALLOW FILTERING` or `setPageSize(100)` does not make it efficient. In Cassandra, build an `orders_by_customer` table for that access pattern, and evaluate bucketing if one customer can accumulate huge row counts.

## 6. Java Driver 4.x practice: per-query statement configuration

Examples use the `com.datastax.oss.driver.api.*` APIs from Driver 4.x. Choose Maven/Gradle coordinates and verify Cassandra/JDK compatibility for your target release; never assume all versions share identical packages or options.

### 6.1. Create the session once

```java
import java.net.InetSocketAddress;
import com.datastax.oss.driver.api.core.CqlSession;

CqlSession session = CqlSession.builder()
    .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
    .withLocalDatacenter("dc1")
    .build();
```

This lab omits authentication/TLS. **Production must enable TLS, least-privilege credentials/roles, and secure secrets management**, rather than relying on unauthenticated defaults.

In real apps, create `CqlSession` once at service startup and **reuse it**; never create a session per HTTP request. Close it cleanly at application shutdown.

### 6.2. Complete program: two queries, two policies

```java
import java.net.InetSocketAddress;
import java.time.Duration;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

public final class PerQueryOptionsDemo {

    public static void main(String[] args) {
        UUID orderId = UUID.fromString(
            "11111111-1111-1111-1111-111111111111");
        UUID customerId = UUID.fromString(
            "22222222-2222-2222-2222-222222222222");

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement getOrder = session.prepare(
                "SELECT order_id, status, updated_at " +
                "FROM commerce.orders_by_id WHERE order_id = ?");

            PreparedStatement listOrders = session.prepare(
                "SELECT created_at, order_id, status " +
                "FROM commerce.orders_by_customer WHERE customer_id = ?");

            BoundStatement singleRead = getOrder.bind(orderId)
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
                .setTimeout(Duration.ofMillis(800))
                .setPageSize(20)
                .setIdempotent(true);

            Row one = session.execute(singleRead).one();
            if (one == null) {
                System.out.println("Order not found");
            } else {
                System.out.println("status=" + one.getString("status"));
            }

            BoundStatement listRead = listOrders.bind(customerId)
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
                .setTimeout(Duration.ofSeconds(3))
                .setPageSize(100)
                .setIdempotent(true);

            ResultSet rs = session.execute(listRead);
            int printed = 0;
            for (Row row : rs) {
                // Process at most 10 rows in this demo.
                // With a synchronous ResultSet, the iterator MAY fetch new pages automatically.
                System.out.println(row.getUuid("order_id"));
                if (++printed >= 10) {
                    break;
                }
            }
        }
    }
}
```

**Conditions and caveats:**

- Tables must exist; `LOCAL_QUORUM` requires enough replicas per RF in `dc1`.
- `setTimeout` here is the **driver-side request timeout per execute/fetch request**, not the whole endpoint's SLA.
- `setPageSize(20)` on a single-row query does not speed it up; it is shown merely to illustrate the property.
- Looping `for (Row row : rs)` on a **synchronous `ResultSet`** can automatically fetch subsequent pages; never assume it reads only the first page.
- Breaking after 10 printed rows is **not** `LIMIT 10` and does not stop the server from returning/fetching more; if you only want at most 10 rows, put `LIMIT` in CQL.
- Production code needs proper logging, error handling, TLS, deadline checks, resource bounds, and HTTP mapping rather than `System.out.println` per row on hot paths.

### 6.3. Immutable / copy-on-write statement behavior

Setters such as `setTimeout`, `setPageSize`, and `setConsistencyLevel` in Driver 4.x return a **new or updated statement instance** instead of mutating the existing statement in place. Always **capture the return value**:

```java
BoundStatement original = getOrder.bind(orderId);

// CORRECT: capture the new instance returned by the setter.
BoundStatement configured = original
    .setTimeout(Duration.ofSeconds(1))
    .setPageSize(100);

// WRONG expectation: calling setter and discarding the return value.
// original.setTimeout(Duration.ofSeconds(1));
// session.execute(original); // still uses the old timeout
```

This matters especially when writing statement-builder utilities or sharing `PreparedStatement` objects. **`PreparedStatement` is reusable**; construct a distinct `BoundStatement` per value set and request, never mixing attributes across two unrelated requests.

## 7. Understanding synchronous paging: `ResultSet` auto-fetches during iteration

Example:

```java
ResultSet rs = session.execute(
    selectByCustomer.bind(customerId).setPageSize(100));

for (Row row : rs) {
    process(row);
}
```

As the iterator consumes buffered rows, the driver fetches subsequent pages behind the scenes. If `process(row)` is slow or collects all rows into an unbounded `List`, memory and latency can grow out of control.

In synchronous code:

- Avoid `rs.all()` on unbounded result sets; it materializes every row across pages into memory.
- `rs.getAvailableWithoutFetching()` only reports rows currently buffered **without a network fetch**, not the query's total row count.
- `rs.isFullyFetched()` tells whether the driver has fetched all pages, **not** that Cassandra data cannot mutate afterward.
- Total **loop duration** can exceed the statement timeout because multiple fetches and app processing span multiple stages.

When an API wants a single page, use **explicit pagination and a continuation token**, rather than iterating unboundedly and slicing Afterward.

## 8. Asynchronous paging: `AsyncResultSet` does not auto-fetch all pages

Java Driver 4.x provides `session.executeAsync(...)`, returning a `CompletionStage<AsyncResultSet>`.

`AsyncResultSet.currentPage()` covers **only the current page**. When `hasMorePages()` is `true`, you must call `fetchNextPage()` explicitly to continue.

Example helper capped at three pages, counting rows only to avoid heavy I/O inside callbacks:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

public final class AsyncPageCounter {

    public static CompletionStage<Long> countAtMostPages(
            AsyncResultSet page, int remainingPages, long count) {

        long nextCount = count;
        for (Row ignored : page.currentPage()) {
            nextCount++;
        }

        if (remainingPages <= 1 || !page.hasMorePages()) {
            return CompletableFuture.completedFuture(nextCount);
        }

        final long accumulated = nextCount;
        return page.fetchNextPage()
            .thenCompose(nextPage ->
                countAtMostPages(nextPage, remainingPages - 1, accumulated));
    }

    // Usage after creating session and statement:
    // CompletionStage<Long> stage = session.executeAsync(statement)
    //     .thenCompose(page -> countAtMostPages(page, 3, 0));
}
```

This is **demand-driven**, fetching the next page only after finishing the current one. It is not a full-table `COUNT(*)`; the helper merely counts rows across at most three pages.

Notes:

- `CompletionStage` callbacks may execute on driver I/O threads; never run slow I/O, blocking calls, heavy JSON work, or `join()` inside them.
- Offload heavy processing to a dedicated executor with bounded queues instead of crowding driver I/O threads.
- Bound page counts and in-flight requests to fit RAM, deadlines, and workload SLOs.
- **A failure in `fetchNextPage()` does not mean earlier pages were never read**; design continuation/reconciliation if pagination aborts mid-stream.

## 9. HTTP pagination and paging state: not the same as page size

For `GET /customers/{id}/orders?pageSize=50`, clients expect **up to 50 items** plus a `nextPageToken`. CQL driver page size helps fetch chunks; the API must also manage **continuation state**.

Conceptually:

```mermaid
flowchart LR
    A[HTTP page request] --> B[BoundStatement + paging state]
    B --> C[Cassandra returns CQL page]
    C --> D[Application selects items per contract]
    D --> E[items + nextPageToken]
    E --> F[Next HTTP request]
```

Rules:

1. Paging state is tied to the **exact CQL statement, bind values, keyspace, and query context**. Never reuse `customer A`'s paging state for `customer B` or change filters/sorts mid-pagination.
2. **Never trust client-forged tokens.** If exposing paging state over HTTP, sign/verify or encrypt it per policy, binding principal/tenant, query fingerprint, and expiration. Never treat paging state as authorization proof.
3. Subsequent page requests must still enforce **authentication/authorization** and row caps; paging state never replaces app-level access checks.
4. Cassandra paging **is not a transactional snapshot**: concurrent inserts, updates, deletes, or TTL expirations between pages can alter results. For “consistent report as of time T”, use a separate snapshot or reconciliation strategy.
5. Follow your driver version's `PagingState` / execution-info APIs rather than hardcoding or manually editing raw paging-state bytes.
6. Never treat paging state as a permanent token **surviving arbitrary schema, driver/native-protocol, or query changes**; define versioning, expiry, and invalid-token handling.

When stable **keyset pagination** along clustering columns is needed, design continuation predicates matching the table's key and clustering order, accounting for concurrent writes, TTLs, tombstones, and partition limits.

## 10. Other important per-query attributes

Beyond timeouts and page size, Java Driver 4.x supports several statement-level attributes:

| Attribute | Typical API | Purpose | Warning |
| --- | --- | --- | --- |
| **Consistency level** | `setConsistencyLevel(...)` | Controls replica responses per CL | Does not create cross-table business atomicity |
| **Serial consistency** | `setSerialConsistencyLevel(...)` | Used for LWT/CAS with `IF` | Meaningful only for conditional operations |
| **Idempotence** | `setIdempotent(true/false)` | Tells the driver whether retry/speculative execution is safe under configured policies | Setting true wrongly can duplicate side effects |
| **Execution profile** | `setExecutionProfileName("...")` | Selects a named bundle of request settings | Explicit statement overrides still take precedence |
| **Tracing** | `setTracing(true)` | Requests server-side query tracing for diagnostics | Adds overhead; never enable globally |
| **Page size** | `setPageSize(n)` | Sets target row count per protocol page | Not equivalent to `LIMIT` |
| **Request timeout** | `setTimeout(Duration)` | Driver-side deadline for the request | Neither a transaction rollback nor an API SLA |
| **Paging state** | `setPagingState(...)` (where supported) | Resumes paginated query in the same context | Only pass valid state for matching query/bind values |

### 10.1. Example configuring a read query

```java
BoundStatement read = selectById.bind(orderId)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setTimeout(Duration.ofMillis(900))
    .setPageSize(200)
    .setIdempotent(true)
    .setTracing(false);
```

Pure `SELECT` queries can usually be marked idempotent **if** they cause no external side effects and business semantics tolerate read retries. `setTracing(false)` shows tracing disabled by default; in production, enable tracing only selectively alongside metrics.

### 10.2. LWT and serial consistency

A typical conditional update:

```sql
UPDATE commerce.orders_by_id
SET status = 'PAID'
WHERE order_id = ?
IF status = 'CREATED';
```

With Driver 4.x:

```java
BoundStatement conditional = updateStatusIfCreated.bind(orderId)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL)
    .setTimeout(Duration.ofSeconds(3))
    .setIdempotent(false);
```

**Distinctions:**

- Normal consistency (`LOCAL_QUORUM`) and serial consistency (`LOCAL_SERIAL`) govern different LWT phases per Cassandra design.
- LWTs have higher cost and latency than regular writes. Never raise timeouts arbitrarily without monitoring contention and replica health.
- On client timeout, **CAS may or may not have committed**; check state, idempotency, and business rules rather than retrying unconditionally.
- `setIdempotent(false)` here is a conservative choice absent proof that retries are safe. Specific workflows using conditional versions and deduplication may adopt a tested custom policy.

**Important:** `status` is business state; when two workers compete, looking only at timeouts is insufficient. Use LWT or explicit versioning/synchronization by design to avoid lost updates.

### 10.3. Enable tracing only during targeted investigations

`setTracing(true)` helps inspect coordinator/replica execution, yet tracing adds runtime overhead and writes trace metadata. Never enable it on all production traffic, especially at high QPS. Enforce proper authorization and short retention windows when collecting traces.

## 11. Idempotence, retries, and speculative execution

From the client's view, a Cassandra query ends in one of three outcomes:

1. **Clear success:** valid response received.
2. **Clear failure:** deterministic server error or inability to reach enough nodes.
3. **Unknown outcome:** timeout or network drop before response; the mutation may have applied.

`Idempotent` means repeating the operation does not corrupt the defined business outcome. It is an **inherent property of the operation**, not a “speed trick”.

| Operation | Safe to mark idempotent? | Must check |
| --- | --- | --- |
| `SELECT` by partition key | Usually yes | No external side effects; business logic tolerates read retries |
| `INSERT`/`UPDATE` setting fixed values | Depends | Timestamps, TTLs, external triggers/events, side effects, concurrent writes |
| `UPDATE counter = counter + 1` | **No** by default | Retries can increment multiple times |
| Writes with relative `TTL` | Not by default | Retries can shift expiration time |
| LWT `IF` | Do not assume yes | CAS result, contention, business decisions, and retry behavior |
| Multi-mutation batch | Analyze every mutation | Logged batches do not isolate multi-partition application transactions |

`setIdempotent(true)` does not force the driver to retry every exception. **Retry policies** and **speculative execution policies** decide when to retry/speculate, while idempotence restricts which requests may safely be retried. Aggressive retries during cluster overload usually worsen incidents.

Counter-example:

```sql
-- Never auto-retry on timeout without idempotency:
UPDATE commerce.order_counters
SET total = total + 1
WHERE customer_id = ?;
```

This illustrates the counter hazard; an actual counter table must declare `counter` columns and matching keys. A blind retry after an uncertain timeout can double-increment `total`.

**Never treat Java request cancellation as transaction compensation.** Critical workflows need deterministic event IDs, conditional versions, outboxes, or authoritative reconciliation.

## 12. Timeouts and page sizes on multi-page queries

Suppose a customer has 12,000 orders and the app uses page size 100. Traversing all rows takes many separate page fetches. If each request has a `2 s` timeout:

- It does **not** mean reading all 12,000 rows **must complete within 2 s**.
- Each fetch and app processing step consumes time, so total duration can breach the HTTP deadline even while every individual fetch succeeds.
- When streaming/serializing rows across fetches, enforce an **overall job/request timeout** and check remaining budget after every page.
- Retries or hot partitions push fetch counts and elapsed time higher.

### Designing three budgets

Example for a list endpoint:

| Budget | Illustrative value | How enforced |
| --- | ---: | --- |
| HTTP deadline | 1500 ms | Total wall-clock budget the service may spend |
| Driver timeout per fetch | 700 ms | Prevents one slow fetch from burning the entire budget |
| Pages/rows per response | 1–2 pages, max 100 items | Bounds RAM and response payload |

These numbers are **illustrative only**, not universal defaults. Benchmark real row sizes, network RTT, RF/CL, startup costs, p95/p99, and SLOs. Returning **exactly 100 items** over HTTP may require handling short CQL pages, application filters, and continuation tokens; never assume one CQL page equals one HTTP page.

### Never trade away correctness for latency

If an app requires reading the latest writes within a DC, switching CL from `LOCAL_QUORUM` to `LOCAL_ONE` just to dodge timeouts violates the consistency contract. First diagnose slow replicas, oversized partitions, timeout budgets, or flaws in the query/data model.

## 13. Distinguishing errors and handling them safely in Java

Key error classes from the Java Driver perspective:

| Symptom | Where it occurs | Chance mutation was written | Action |
| --- | --- | --- | --- |
| Driver-side request timeout | Client budget expired | **Possible** | Log request ID/context; do not retry non-idempotent writes; reconcile |
| `ReadTimeoutException` | Coordinator waited too long for replicas | N/A for SELECT | Inspect CL, partition, I/O, tombstones, replicas, and controlled retries |
| `WriteTimeoutException` | Coordinator lacked enough write ACKs in time | **Possible** on some or enough replicas | Use idempotency/reconciliation; inspect write type and replicas |
| `UnavailableException` | Coordinator sees insufficient live replicas for CL | Request normally failed preconditions | Check RF/DC/node state; never downgrade CL automatically |
| Connection / node-lost error | Network / transport | Unknown if already sent | Inspect driver logs, retry policy, and idempotence |
| `InvalidQueryException` | CQL / schema | Query rejected for syntax/validity | Fix CQL/schema; raising timeouts does nothing |
| Auth / permission error | RBAC or TLS/auth | Query denied | Grant least privilege or fix credentials |

Exact exception classes vary slightly across driver versions; this table highlights **error categories and responses**, not a strict class hierarchy. Never catch `Exception` and retry everything in a loop.

### Async error-handling pattern

```java
CompletionStage<AsyncResultSet> future = session.executeAsync(statement);

future.whenComplete((page, error) -> {
    if (error != null) {
        // Log query kind, logical request ID, deadline, and error;
        // NEVER log passwords or sensitive data values.
        // Never auto-retry mutations unless proven idempotent.
        recordFailure(error);
        return;
    }
    recordSuccess(page);
});
```

`recordFailure` and `recordSuccess` are application methods **not declared in the snippet**, illustrating only the handling boundary. Callbacks must stay lightweight; offload slow I/O to an executor. In production, propagate failures and map HTTP responses accurately rather than logging and treating the request as successful.

## 14. Execution profiles: grouping configuration by workload

When multiple endpoints share a policy, profiles eliminate repetition and simplify review.

Example `order-point-read` and `order-list` profiles:

```hocon
datastax-java-driver {
  profiles {
    order-point-read {
      basic.request.timeout = 700 milliseconds
      basic.request.consistency = LOCAL_QUORUM
      basic.request.page-size = 100
    }
    order-list {
      basic.request.timeout = 2500 milliseconds
      basic.request.consistency = LOCAL_QUORUM
      basic.request.page-size = 150
    }
  }
}
```

In Java:

```java
BoundStatement getOrder = selectById.bind(orderId)
    .setExecutionProfileName("order-point-read");

BoundStatement listOrders = selectByCustomer.bind(customerId)
    .setExecutionProfileName("order-list")
    .setPageSize(80); // Explicit override for this case.
```

**Benefit:** business code picks a meaningful profile name while numeric thresholds live in reviewed configuration. Still, avoid creating hundreds of near-identical profiles differing by a few milliseconds; every profile needs an owner, SLO target, and tests.

Keep **driver configuration** distinct from **Cassandra table options** like `compaction`, `compression`, and `default_time_to_live`. Changing a profile timeout does not change SSTables, TTLs, replication, or server-side data.

## 15. Runbook: tuning timeout and page size for a slow endpoint

Context: `GET /customers/{customerId}/orders` suffers high p99 and `ReadTimeout` at peak traffic.

### Phase A — Establish a baseline before changing anything

1. **Verify query and data model:** `WHERE customer_id = ?` targets `orders_by_customer`; measure rows/partition, row byte size, TTLs, and tombstones.
2. **Check cluster health:** nodes `UP`, RF/CL, compaction backlog, disk I/O, GC, repair, and network.
3. **Inspect Java Driver:** request timeout, page size, execution profile, in-flight count, pools/connections, retries/speculative attempts.
4. **Measure real load:** p50/p95/p99 per page and per full API call, pages fetched, rows/bytes, timeout rates, retries, and HTTP deadlines.
5. **Define targets:** lower p99 without increasing stale data, errors, or cluster overload.

### Phase B — Controlled experimentation

- In staging, test `pageSize` 50, 100, and 200 on representative data; compare per-page latency, round trips, heap usage, and throughput.
- Test SLO-aligned timeouts (e.g., `700 ms` vs `1 s`), tracking false-timeout rates alongside actual completed requests.
- Cap concurrent async requests instead of raising concurrency unchecked.
- Change one parameter group at a time so cause and effect stay clear.
- Hold consistency level constant unless changing CL is an explicitly approved business decision.

### Phase C — Rollout and observation

```text
SLO & baseline
   -> check partition/data model
   -> test timeout/page size
   -> verify backpressure/retry/idempotency
   -> canary small traffic slice
   -> compare p99, errors, requests/page, and cluster health
   -> expand rollout or revert config
```

Stop conditions: p99 breaches threshold, `Unavailable`/`ReadTimeout` rises, in-flight/backlogs grow, or extra page requests add load. If shrinking page size spikes round trips excessively, optimize the schema and cap HTTP row counts instead of shrinking pages endlessly.

### Phase D — Update the operational contract

Document:

- Exact profile and statement attributes changed, code/config versions, and deployment date.
- Effective HTTP deadline, CQL timeout, max fetches, and response row sizes.
- Retry/idempotency rules per operation type.
- Revert triggers and responsible owner.
- Load-test results under production-equivalent RF/CL, topology, and dataset.

## 16. Common configuration mistakes table

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Setting `setTimeout(10s)` inside a 1s API deadline | Requests outlive the API budget | Compute remaining budget and bound driver timeout |
| Assuming timeout means the write failed | Retries duplicate mutations, especially counters/LWTs | Enforce idempotency, request IDs, and reconciliation |
| `setPageSize(100)` followed by `ResultSet.all()` | Loads the entire result set into RAM | Iterate on demand and bound rows/pages |
| Treating CQL page size as HTTP page size | API returns too many/few items or wrong tokens | Build dedicated API pagination logic |
| Adding `ALLOW FILTERING` because paging is enabled | Full scans and overload | Design query-first tables and partition keys |
| Reading one async page and stopping | Misses all subsequent pages | Use `hasMorePages()` and `fetchNextPage()` |
| Discarding return values from `setTimeout`/`setPageSize` | Statement keeps old settings | Capture the returned `BoundStatement` |
| Marking counter updates idempotent | Retries increment counters repeatedly | Mark non-idempotent and use reconciliation design |
| Lowering CL to reduce timeouts without review | Serves stale data and breaks consistency contracts | Investigate replicas/performance and approve CL explicitly |
| Enabling tracing on every request | Adds heavy overhead to cluster | Enable selectively during investigations |
| Running blocking I/O in async callbacks | Blocks driver threads and hurts whole-service latency | Offload to a bounded executor with backpressure |
| Raising timeouts to mask a hot partition | Accumulates in-flight requests and resource pressure | Fix schema/bucketing, compaction/tombstones, and rate limits |

## 17. Exercise: designing per-query policies for three endpoints

A Java service handles three workloads:

- **A — `GET /orders/{id}`:** reads one row by `order_id`, 800 ms API SLA, requires `LOCAL_QUORUM` in an RF=3 DC.
- **B — `GET /customers/{id}/orders`:** returns up to 50 items plus a next-page token; one partition may hold tens of thousands of orders.
- **C — `POST /orders/{id}/paid`:** conditional status update with `IF status = 'CREATED'`, may time out and be retried by clients.

**Questions:**

1. For A, does setting page size 5000 make it faster? Pick a timeout leaving headroom for serialization and network.
2. For B, is `pageSize=50` enough to guarantee HTTP returns exactly 50 items? Why or why not?
3. Write the `BoundStatement` for A with `LOCAL_QUORUM`, 600 ms timeout, and `setIdempotent(true)`.
4. Write the `BoundStatement` for B with page size 100 and profile `order-list`; describe safe continuation-token handling.
5. For C, why must you not automatically retry every timeout? What must you establish about the LWT outcome after a timeout?
6. Distinguish `DriverTimeout`, `WriteTimeout`, and `Unavailable` using concrete scenarios.
7. For B with 10,000 rows, why is `ResultSet.all()` risky? Sketch sequential fetching capped at two pages.
8. Which metrics prove page size 100 genuinely outperforms 200 without overloading the cluster?

**Solution hints:**

```java
// A — single-row lookup:
BoundStatement a = selectById.bind(orderId)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setTimeout(Duration.ofMillis(600))
    .setIdempotent(true);

// B — profile + statement-level override:
BoundStatement b = selectByCustomer.bind(customerId)
    .setExecutionProfileName("order-list")
    .setPageSize(100)
    .setIdempotent(true);

// C — LWT: timeout can leave an unknown outcome at the client.
BoundStatement c = conditionalPaid.bind(orderId)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL)
    .setIdempotent(false);
```

- A needs measured p99 and remaining budget for logic/response; a single-row lookup gains nothing from a massive page size.
- B needs an HTTP coordinator validating paging state against the exact query/bind values, capping rows, and authenticating tokens. Page size is only the target CQL page row count.
- C must verify whether the mutation applied via idempotency/versioning or reading back business state; timeouts are not rollbacks.
- Compare **total** API latency, fetch counts, bytes/row, in-flight requests, timeouts/errors, p95/p99, and server CPU/GC/I/O before and after.

## 18. Production checklist

- [ ] Distinguished API deadlines, driver request timeouts, server-side timeouts, and connect timeouts.
- [ ] Tuned `setTimeout` to SLOs and the total fetches/operations within a request.
- [ ] Defined reviewed defaults/profiles, overriding on statements only when justified.
- [ ] Used `setPageSize` strictly for CQL protocol paging without assuming it caps total rows or HTTP responses.
- [ ] Queries target partition keys and monitor hot partitions/tombstones rather than masking bad models with page size.
- [ ] Avoided `ResultSet.all()` on unbounded results; enforced max rows/pages and backpressure.
- [ ] Async paging handles `currentPage`, `hasMorePages`, and `fetchNextPage` properly without blocking callbacks.
- [ ] HTTP next-page tokens are authenticated/expiring and bound to principal, query, and bind values without leaking raw state.
- [ ] Verified per-statement CL and LWT serial CL against real RF and DC topology.
- [ ] Classified idempotent vs non-idempotent statements; never blindly retry counters/LWTs/mutations after timeouts.
- [ ] Disabled blanket tracing; configured metrics, safe logging, and driver/server timeout separation.
- [ ] Enforced in-flight caps, retry/speculation budgets, and deadline propagation.
- [ ] Load-tested across varied row sizes, multi-page results, CLs, and failure scenarios.
- [ ] Prepared a configuration rollback plan if p99, timeouts, or I/O degrade.

**Conclusion:** In the Cassandra Java Driver, **timeouts bound client-side request budgets without rolling back writes**, and **page sizes regulate chunked result delivery without replacing `LIMIT` or fixing partition design**. Each `BoundStatement` can inherit a profile and override timeout, page size, CL, serial CL, idempotence, and tracing to fit its workload. Sound design weighs **partition keys, RF/CL, application SLOs, backpressure, and safe retry semantics** together; driver attributes are control knobs, not substitutes for data modeling and cluster operations.
