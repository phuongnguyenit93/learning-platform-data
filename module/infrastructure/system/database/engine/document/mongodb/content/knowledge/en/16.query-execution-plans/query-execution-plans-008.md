# Distinguishing Explain Execution Time from Application Latency

## 1. A Query Can Be "Fast in Explain" While the API Remains Slow

When optimizing MongoDB queries, you often see two measurements that do not match:

- In `explain("executionStats")`, `executionStats.executionTimeMillis` reports **8 ms**.
- In Java logs or the API dashboard, the request running that query takes **250 ms**.

These two numbers **do not necessarily contradict each other**. They are measured at **two different boundaries** and may be observing **two different executions**.

`explain()` shows how MongoDB **plans and executes the query on the database side**. Application response time spans many more steps: waiting for a connection, sending the command over the network, running on the server, transferring results, reading cursor batches, decoding BSON, transforming data, running business logic, and sending the HTTP response.

> **Principle:** `executionTimeMillis` in `explain` signals MongoDB's query work—it is **not** an end-to-end latency measurement experienced by application users.

The goal of this lesson is to understand **what each metric measures, what it omits, how to measure consistently, and how to investigate discrepancies**. This is a core skill in the *Query Execution Plans* chapter, because reading an execution plan accurately only helps when tied to real application symptoms.

### 1.1. Four Distinct Questions

| Question | Appropriate Tool / Perspective |
| --- | --- |
| Did MongoDB choose `COLLSCAN`, `IXSCAN`, `FETCH`, or `SORT`? | `explain("queryPlanner")` or `explain("executionStats")`. |
| How many keys/documents did a server-recorded execution scan, and how long did it take? | `explain("executionStats")`, profiler/server logs/metrics depending on the case. |
| How long did a `find` or `getMore` command take from the driver's perspective? | Command monitoring, driver metrics, tracing. |
| How long did the API take from receiving the request to sending the response? | Service timers, distributed tracing, HTTP server/gateway metrics. |

Do not swap a tool in one row for a tool in another row and assume the numbers mean the same thing.

---

## 2. Three Time Layers to Separate

### 2.1. Layer A — Time Inside `explain`

Common invocation:

```javascript
db.orders.find({
  customerId: "C01"
}).explain("executionStats");
```

In the output, a section might look like:

```javascript
{
  executionStats: {
    executionSuccess: true,
    nReturned: 20,
    executionTimeMillis: 7,
    totalKeysExamined: 20,
    totalDocsExamined: 20
  }
}
```

This is a **hypothetical partial output example**, not guaranteed output across every version. The `7` represents the time MongoDB reported for selecting/executing the plan during the `explain` operation as measured by the server. It does **not** include the application's full HTTP request lifecycle.

### 2.2. Layer B — Command Execution Time via Driver

In a Java application, a command like `find` passes through the driver, network connection, and server before receiving a response. Command monitoring records a command's duration from the driver's viewpoint, reflecting round-trip and server processing time for that command.

If the query returns multiple batches, there may be:

```text
find
getMore
getMore
...
```

Thus, **a single `find` command does not necessarily represent total result loading time**. To measure full cursor consumption, sum/observe all batches and client-side work, not just the initial command duration.

### 2.3. Layer C — End-to-End Application Time

An endpoint may go through:

```text
HTTP request arrives at service
    |
    +--> Authentication, parameter validation, routing
    |
    +--> Server selection / connection pool wait
    |
    +--> MongoDB find, server processing, network round trip
    |
    +--> getMore if cursor has remaining data
    |
    +--> BSON decoding and DTO mapping
    |
    +--> Business logic / external service calls
    |
    +--> JSON serialization, compression, HTTP response
    v
Client receives response
```

When measured from **HTTP ingress until the service finishes sending the response**, every step in the endpoint contributes. When measured from **a browser**, user network, gateway, TLS, asset loading, and rendering time also enter the picture. Therefore, even "application latency" must be clearly defined.

### 2.4. Three Clocks Diagram

```text
                          Timeline (illustrative)
HTTP ingress ------------------------------------------------ HTTP response
       |                                                        |
       |  app logic | pool | find | decode | getMore | JSON ...  |
       |            |      |      |        |         |          |
       +------------+------+------+--------+---------+----------+
       <---------------- API latency -------------------------->

                           <find round trip>
                                   <server work>

                        explain("executionStats")
                              <explain server work>
```

`explain` is normally **a separate operation**, not a sub-span recorded inside that same HTTP request. You cannot simply compute `API latency - explain.executionTimeMillis` and claim the difference equals network time.

---

## 3. What Work Does `explain()` Perform?

MongoDB lets you run explain at different verbosity levels:

| Verbosity | What You Want to Know | Includes Execution Stats? |
| --- | --- | --- |
| `queryPlanner` | Planning details, winning plan, and related candidates. | Does not provide full execution metrics like `executionStats`. |
| `executionStats` | Executes the chosen plan to capture results/cost. | Includes `nReturned`, `executionTimeMillis`, `totalKeysExamined`, `totalDocsExamined`. |
| `allPlansExecution` | Adds candidate plan info from the plan selection process. | Includes execution stats plus partial trial stats for candidates during plan selection. |

Example:

```javascript
// Inspect plan without focusing on runtime metrics.
db.orders.find({ customerId: "C01" })
  .explain("queryPlanner");

// Inspect executed plan and execution cost metrics.
db.orders.find({ customerId: "C01" })
  .explain("executionStats");

// Also study competition among candidate plans.
db.orders.find({ customerId: "C01" })
  .explain("allPlansExecution");
```

Do not use `allPlansExecution` for every inspection when basic metrics suffice: output is larger and more complex, without automatically making diagnosis more accurate.

### 3.1. What Is `executionStats.executionTimeMillis`?

This is the number of milliseconds MongoDB records for **selecting and executing the query plan during the explain operation**. Exact calculation and detail depend on engine, version, and operation type.

What it is **not**:

- Not endpoint HTTP latency.
- Not total application time to fetch and process all documents through a cursor.
- Not network latency between the service and MongoDB.
- Not driver connection pool wait time.
- Not guaranteed to match a regular `find()`, as `explain` has its own planning semantics.
- Not a guarantee for production p95/p99 latency.

### 3.2. `executionTimeMillisEstimate` Per Stage

Some `executionStages` trees include values like:

```javascript
{
  stage: "FETCH",
  nReturned: 20,
  executionTimeMillisEstimate: 4,
  inputStage: {
    stage: "IXSCAN",
    nReturned: 20,
    executionTimeMillisEstimate: 2
  }
}
```

This is a trimmed illustration. Stage-level `executionTimeMillisEstimate` is an estimate with its own semantics, **not independent stopwatches you can simply add up**. A parent stage encompasses its child stage's work; adding 4 + 2 and treating it as total query time **double-counts** work.

With newer engines, stage trees and stat fields can differ from the classic structure. Read execution plans according to your server version.

### 3.3. `totalKeysExamined`, `totalDocsExamined`, `nReturned`

These three numbers usually matter far more than a few milliseconds difference on one run:

- `totalKeysExamined`: index entries examined.
- `totalDocsExamined`: documents examined.
- `nReturned`: documents returned by query execution during explain.

Hypothetical examples:

| Query | Keys Examined | Docs Examined | Returned | Signal |
| --- | ---: | ---: | ---: | --- |
| Equality on unique key | 1 | 1 | 1 | Highly selective lookup path. |
| Well-matched compound index | 25 | 25 | 20 | Relatively little work. |
| Poorly selective index | 250,000 | 120,000 | 20 | Heavy scanning and filtering. |
| Covered query | 20 | 0 | 20 | Can avoid document `FETCH`. |
| Collection scan | 0 | 1,000,000 | 20 | Broad scan. |

These numbers are **illustrative scenarios**, not MongoDB benchmarks.

If explain reports `executionTimeMillis: 0` on a small dataset, that reflects timer reporting resolution or a very fast operation; **it does not mean the database used zero CPU or I/O**.

---

## 4. Crucial Detail: Explain Does Not Behave Identically to Normal Queries

MongoDB treats explain as **a standalone query** and does not read or update the plan cache the way normal queries do. Consequently, the winning plan or planning cost in explain can differ from the path a live request takes.

Example:

```javascript
db.orders.find({
  customerId: "C01",
  status: "PAID"
}).sort({ createdAt: -1 }).explain("executionStats");
```

Never conclude:

> "The API definitely uses the exact winning plan shown by this explain command."

A live command is influenced by the plan cache, execution history, index changes, metadata, and workload state. Explain is great for **investigating plan choices**, whereas to see **actual application execution**, combine command monitoring, profiler/logs, and tracing.

### 4.1. Explain Also Consumes Resources

`explain("executionStats")` executes actual work to gather metrics. On heavy queries, this can impose significant load; never run expensive explains repeatedly in production just to grab a number.

### 4.2. Instrumentation Overhead Can Skew Measurements

Measurement itself adds overhead. An explain run right after caches warm up may look faster than the first run, while an explain run under server load looks slower. Statistics are informative, not a sterile benchmark of every live request.

### 4.3. Never Subtract Two Separate Requests Directly

Suppose:

```text
10:00:00 explain.executionTimeMillis = 7 ms
10:05:00 API request duration       = 180 ms
```

In five minutes, any of these can differ:

- Different cached pages.
- Different concurrency.
- Different replica serving the query.
- Query parameters or results with different selectivity.
- Different plan cache / plan selection.
- Different returned payload size and batch count.
- Network variance.
- Extra post-query work in the application.

Hence `180 - 7 = 173 ms network` is **baseless**.

---

## 5. Which Phases Make Up a Real Endpoint?

To analyze discrepancies, break a request into observable segments:

| Phase | Example Work | Included in Explain? |
| --- | --- | --- |
| Ingress / gateway | HTTP routing, TLS, reverse proxy. | No. |
| Pre-MongoDB app logic | Authentication, validation, building filter. | No. |
| Server selection | Picking a node per read preference and topology. | No. |
| Pool wait | Waiting to check out a connection. | No. |
| Driver command | Encoding command, network send, receiving response. | Partially; explain only reflects server work of the standalone explain op. |
| Server-side query | Selecting/running plan, reading index/docs, sorting. | Core focus of explain. |
| Cursor / `getMore` | Fetching remaining batches. | Explain does not directly model the client's `getMore` chain. |
| BSON -> objects | Decoding BSON, mapping DTOs/POJOs. | No. |
| Business logic | Application-side joins, calling other services. | No. |
| HTTP response | JSON serialization, compression, network write. | No. |

This table separates boundaries rather than summing exact times: some steps overlap, and **tools at different layers have different timing boundaries**.

### 5.1. Pool Wait and Server Selection

Suppose the connection pool runs out of idle connections and a request waits 120 ms to acquire one. Immediately after, MongoDB runs the command in 6 ms. `explain` reports 6 ms or similar, yet the application already lost over 120 ms before the query even started.

This requires checking **connection pool metrics and server selection metrics**, and cannot be fixed simply by adding an index.

### 5.2. Network and Payload

A server-side query can execute fast yet return tens of thousands of large documents, causing:

- Heavy network response transfer.
- Heavy client-side BSON decoding.
- Huge DTO/JSON allocation in the app.
- Heavy payload delivery to the gateway/client.

Fixes usually involve `limit`, projection, pagination, or API contract changes; indexes only address part of the access path.

### 5.3. Post-Query Time

A service may load 20 orders in 8 ms and then call three external services taking tens of milliseconds each before building a JSON response. Overall API latency is not a slow MongoDB measurement.

Never "tune indexes until explain hits 0 ms" when the largest chunk of time lives in application logic.

---

## 6. Setting Up a MongoDB Example

Suppose a test `orders` collection has the schema:

```javascript
{
  _id: "O1001",
  customerId: "C01",
  status: "PAID",
  createdAt: ISODate("2026-11-14T08:00:00Z"),
  totalMinor: NumberLong("520000"),
  items: [
    { sku: "P10", quantity: 2 },
    { sku: "P11", quantity: 1 }
  ]
}
```

An endpoint requirement:

> "Fetch the 20 newest PAID orders for customer C01, returning only order ID, date, and total amount."

Query:

```javascript
db.orders.find(
  {
    customerId: "C01",
    status: "PAID"
  },
  {
    _id: 1,
    createdAt: 1,
    totalMinor: 1
  }
).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
```

To support filtering and deterministic ordering, you can test an index:

```javascript
db.orders.createIndex(
  {
    customerId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  {
    name: "idx_customer_status_recent"
  }
);
```

This is a **candidate** based on filter/sort, not guaranteed optimal for every workload. Because projection needs `totalMinor` outside the index, the query may still need `FETCH`.

### 6.1. Running Explain

```javascript
db.orders.find(
  { customerId: "C01", status: "PAID" },
  { _id: 1, createdAt: 1, totalMinor: 1 }
).sort({ createdAt: -1, _id: -1 })
 .limit(20)
 .explain("executionStats");
```

If the query planner selects the index, output may show `IXSCAN`, `FETCH`, low keys/docs examined, and no separate `SORT` step. The duration in explain is **the server metric for that explain run**.

### 6.2. Timing Real Reads in `mongosh`

```javascript
const start = Date.now();

const results = db.orders.find(
  { customerId: "C01", status: "PAID" },
  { _id: 1, createdAt: 1, totalMinor: 1 }
).sort({ createdAt: -1, _id: -1 })
 .limit(20)
 .toArray();

const elapsedMs = Date.now() - start;

printjson({
  returned: results.length,
  clientElapsedMs: elapsedMs
});
```

Here `clientElapsedMs` measures **the time `mongosh` took to execute the operation and materialize all returned results** into an array inside the shell process, including shell/driver work and network. It is **not** Java HTTP service latency, and `Date.now()`'s millisecond resolution is coarse for very short operations.

In particular, this measurement still omits JSON serialization and sending an HTTP response in a real app.

### 6.3. Do Not Measure Two Different Queries

These two commands can take vastly different times:

```javascript
// Query A: 20 newest orders.
db.orders.find({ customerId: "C01" })
  .sort({ createdAt: -1 })
  .limit(20);

// Query B: entire history.
db.orders.find({ customerId: "C01" })
  .sort({ createdAt: -1 });
```

If the live API fetches every document in Query B while explain runs Query A, the time gap has **zero diagnostic value**.

---

## 7. Cursors and Lazy Execution: Why Java Timing Is Easily Wrong

The MongoDB Java Sync Driver relies on APIs returning `FindIterable` or cursors. **Building a `FindIterable` does not mean the query executed or fetched any results.**

Common mistake:

```java
long start = System.nanoTime();

FindIterable<Document> iterable = collection.find(
    Filters.eq("customerId", "C01")
);

long elapsedMs =
    TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - start);

System.out.println("MongoDB query took " + elapsedMs + " ms");
```

This mainly times **constructing the query descriptor object**, likely without even sending `find` to the server. Concluding "MongoDB took 0 ms" from this snippet is completely wrong.

### 7.1. Time Until Results Are Actually Exhausted

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

import java.util.concurrent.TimeUnit;

public class MongoReadTimer {

    public static long readTwentyOrders(
            MongoCollection<Document> orders,
            String customerId
    ) {
        long started = System.nanoTime();
        long count = 0;

        try (MongoCursor<Document> cursor = orders.find(
                    Filters.and(
                        Filters.eq("customerId", customerId),
                        Filters.eq("status", "PAID")
                    )
                )
                .projection(
                    Projections.include(
                        "_id", "createdAt", "totalMinor"
                    )
                )
                .sort(
                    Sorts.orderBy(
                        Sorts.descending("createdAt"),
                        Sorts.descending("_id")
                    )
                )
                .limit(20)
                .iterator()) {

            while (cursor.hasNext()) {
                Document order = cursor.next();
                count++;

                // Illustrates consuming documents only.
                // Time DTO mapping separately if needed.
            }
        }

        long elapsedNanos = System.nanoTime() - started;
        long elapsedMs = TimeUnit.NANOSECONDS.toMillis(elapsedNanos);

        System.out.printf(
            "loaded=%d; cursorElapsedMs=%d%n",
            count,
            elapsedMs
        );
        return elapsedMs;
    }
}
```

The timer starts before opening the cursor and ends after the cursor is drained/closed. This is closer to **total driver-side read duration**, including connection wait, network, server work, decoding, and client iteration. Still:

- It is not yet the full HTTP request.
- If heavy business logic runs inside the loop, the timer includes that work too.
- Never `println` every document when isolating MongoDB read time: console I/O skews latency.
- `System.nanoTime()` measures elapsed time within one JVM process, not wall-clock timestamps comparable across hosts.
- Counting documents does not measure DTO mapping or JSON serialization; give those separate spans.

### 7.2. Timing "First Result" Differs from Timing "All Results"

Calling:

```java
Document first = collection.find(
    Filters.eq("customerId", "C01")
).first();
```

times fetching the first document, **not** draining every result of an unbounded query.

If the real API executes:

```java
List<Document> all = collection.find(
    Filters.eq("customerId", "C01")
).into(new ArrayList<>());
```

it may pull many batches, allocate heavy RAM, and take much longer. Never compare `first()` directly against an endpoint materializing 100,000 documents.

### 7.3. `batchSize` and `getMore`

MongoDB streams cursor results in batches. The driver sends `find` for the first batch, then issues `getMore` as needed.

```text
Service invokes query
      |
      v
   find command --------> batch 1
      |
      v
   getMore -------------> batch 2
      |
      v
   getMore -------------> batch 3
      |
      v
   Cursor completes
```

`batchSize` affects batch count, round-trip overhead, and memory per batch, though bigger is not always better. Tiny batches inflate network round trips; huge batches raise memory usage and time-to-first-response. MongoDB also enforces protocol-level message and batch size limits.

A `limit(20)` query normally finishes in one batch; a query returning hundreds of thousands of documents issues many `getMore` calls.

### 7.4. Time to First Result vs. Time to Drain Cursor

Separate two metrics:

- **Time to first result:** from request start until the first document arrives.
- **Time to drain cursor:** from request start until all required documents are consumed.

A streaming API may start sending bytes early yet take seconds to finish streaming. An API materializing all documents before writing JSON has high time-to-first-byte. A single `executionTimeMillis` field in explain cannot distinguish these latency profiles.

---

## 8. What Does Command Monitoring Measure?

The Java Driver supports command monitoring via `CommandListener`. You can record timings for commands like `find`, `getMore`, and `aggregate` **from the driver's viewpoint** to see which commands and batches spend time.

Compact example:

```java
import com.mongodb.MongoClientSettings;
import com.mongodb.event.CommandListener;
import com.mongodb.event.CommandStartedEvent;
import com.mongodb.event.CommandSucceededEvent;
import com.mongodb.event.CommandFailedEvent;

import java.util.concurrent.TimeUnit;

public final class MongoCommandTiming implements CommandListener {

    @Override
    public void commandStarted(CommandStartedEvent event) {
        String name = event.getCommandName();
        if ("find".equals(name) || "getMore".equals(name)) {
            System.out.printf(
                "Mongo command started: %s requestId=%d%n",
                name,
                event.getRequestId()
            );
        }
    }

    @Override
    public void commandSucceeded(CommandSucceededEvent event) {
        String name = event.getCommandName();
        if ("find".equals(name) || "getMore".equals(name)) {
            System.out.printf(
                "Mongo command succeeded: %s elapsedMs=%d%n",
                name,
                event.getElapsedTime(TimeUnit.MILLISECONDS)
            );
        }
    }

    @Override
    public void commandFailed(CommandFailedEvent event) {
        System.err.printf(
            "Mongo command failed: %s%n",
            event.getCommandName()
        );
    }

    public static MongoClientSettings.Builder configure(
            MongoClientSettings.Builder builder
    ) {
        return builder.addCommandListener(
            new MongoCommandTiming()
        );
    }
}
```

This illustrates the MongoDB Java Sync Driver's event API. Register the listener **before creating `MongoClient`**; merely defining the class does nothing.

**Command duration is neither HTTP latency nor pure server CPU time.** It observes the command at the driver layer, covering server interaction and network within the driver's event boundary; pre-connection steps, post-response app logic, and HTTP serialization sit outside a single command's duration.

### 8.1. Things to Avoid When Logging Commands

- Never log raw payloads, credentials, or PII unnecessarily.
- Never print synchronously to stdout thousands of times per second under heavy load; logging adds overhead.
- Never log only `find` while ignoring `getMore`, hiding multi-batch transfer times.
- Never assume one command equals one HTTP request; an endpoint may issue multiple queries, and one query may emit multiple commands.
- Never treat MongoDB's command `requestId` as an end-to-end HTTP trace ID without explicit correlation.

### 8.2. Distributed Tracing and Request Correlation

A system using OpenTelemetry/tracing might break down a trace as:

```text
HTTP GET /customers/C01/orders                    220 ms
    ├─ auth + validate                             15 ms
    ├─ Mongo pool/server-selection                  55 ms
    ├─ Mongo find command                           12 ms
    ├─ Mongo getMore commands                       20 ms
    ├─ DTO mapping                                  35 ms
    ├─ Call external pricing service                60 ms
    └─ JSON serialization/other                     23 ms
```

These numbers are **hypothetical non-overlapping spans** for illustration. In real traces, spans nest or run concurrently, so **you cannot always add every span's duration to get the total**. Analyze the critical path, wait times, and uninstrumented gaps.

---

## 9. How Does `explain` Differ from Server Profiler / Logs?

`explain` is an **active operation**, running the requested query to report its plan and statistics.

The profiler or slow-query log records **actual operations occurring on the server**, per collection settings. These sources capture command duration, keys/docs examined, index used, and cursor-related info.

Key differences:

| Source | Strength | Limitation |
| --- | --- | --- |
| `explain("queryPlanner")` | Shows plan and index structure without full execution metrics. | Not a runtime measurement. |
| `explain("executionStats")` | Provides counters and duration for one explain run. | Interacts differently with plan cache; does not represent all requests. |
| Profiler / slow log | Captures real server operations in runtime context. | Covers only server-visible work; collection adds overhead and may be sampled. |
| Driver command monitoring | Captures real commands, round trips, and `getMore`. | Excludes full HTTP/business logic duration. |
| End-to-end tracing | Shows request flow across all components. | Only as detailed as your instrumentation/spans. |

Some `getMore` metrics are logged separately from `find`. To understand full cursor loading time in the app, inspect the **command sequence**, not just the initial entry.

### 9.1. Do Server Log Timings Always Match `executionTimeMillis`?

Not necessarily. They have different measurement boundaries, collection conditions, workloads, and contexts—and both differ from user-perceived time.

If a slow-query log reports 120 ms while an equivalent explain reports 15 ms, check:

- Did filter, sort, limit, projection, and indexes match?
- Was it the same node, plan, and load window?
- Did the live operation hit server waits that explain did not reproduce?
- Was the cache already warm when explain ran?
- Did the live query return more data or iterate over multiple batches?

Never dismiss the discrepancy as a "profiler bug."

---

## 10. The Plan Cache Can Make Two Runs Differ

The MongoDB query planner evaluates multiple plans to pick a good path for a query shape. For regular queries, the plan cache reuses selected plans under eligible conditions.

`explain()` **does not use the plan cache like normal queries, nor does it insert cache entries from explain runs**. Thus, planning time and winning plan in explain may not match an application request using a cached plan.

Example:

```javascript
db.orders.find({
  customerId: "C01",
  status: "PAID"
}).sort({ createdAt: -1 }).explain("executionStats");
```

If live queries occasionally pick a different plan, do not immediately slap `hint()` on it. Determine:

1. Are multiple candidate indexes present?
2. Is customer distribution skewed (one customer with millions of orders, others with a few)?
3. Are query shapes/parameters identical?
4. Do server version, collation, or read preference differ?
5. What do plan stats from the actual slow operation show?

You can use `hint()` in a test environment to compare candidate indexes:

```javascript
db.orders.find({
  customerId: "C01",
  status: "PAID"
}).sort({ createdAt: -1 })
  .hint({
    customerId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  })
  .explain("executionStats");
```

This assumes the corresponding index exists. **Forcing a plan is not automatically optimal**: an index great for one parameter set can perform poorly for another.

---

## 11. Cache Warmth and Concurrent Load

Two runs of the same query can still yield different latencies even when the execution plan is identical.

### 11.1. Cold Cache vs. Warm Cache

On the first run, MongoDB may read index/document pages from disk storage; on subsequent runs, those pages may already sit in the WiredTiger cache or OS filesystem cache.

```text
First run:
    index page -> storage
    data page  -> storage
    query work -> results

Next run:
    index page -> cache
    data page  -> cache
    query work -> results
```

The gap can be huge when the working set is large. A production system rarely keeps every page warm like a benchmark repeating one query; production serves diverse keys and query patterns.

### 11.2. Contention, CPU, and I/O

The exact same query slows down when:

- The server handles heavy concurrent traffic.
- CPU is saturated by heavy aggregations.
- Storage IOPS or disk latency spikes.
- Other data/indexes compete for cache space.
- Heavy writes pressure cache eviction and maintenance.
- Replication/topology routes queries to different nodes.

A single explain run on an idle box tells you nothing about p99 query latency during peak traffic.

### 11.3. Same Plan Does Not Mean Same Duration

An `IXSCAN -> FETCH` plan may scan exactly 20 keys on two runs yet take vastly different times depending on whether pages live in RAM or on disk, or on concurrent load. **Execution counters explain logical work; latency reflects both resources and execution context.**

---

## 12. `limit`, Projection, `skip`, Sort, and Result Size

To compare explain against a live request, every query attribute must match:

| Attribute | Why Does It Matter? |
| --- | --- |
| Filter | Determines selectivity and candidate plans. |
| Sort | May require an ordered index or a `SORT` step. |
| Projection | Determines covered query eligibility and payload size. |
| Limit | Caps returned results; allows early stop on aligned paths. |
| Skip | Deep offsets force the engine to traverse many keys. |
| Collation | Affects string comparison and index eligibility. |
| Batch size | Affects response/`getMore` counts on real clients. |
| Read preference | Can route commands to a different node. |
| Read concern | Can alter read semantics and cost. |
| Hint | Forces an index, overriding default planner selection. |
| Aggregation stages | Can alter index usage and processed document counts. |

### 12.1. The `skip` Trap

```javascript
db.orders.find({
  customerId: "C01"
}).sort({ createdAt: -1 })
  .skip(200000)
  .limit(20);
```

Even with an index, the engine may have to walk through 200,000 keys just to discard them. Running explain on page one with `limit(20)` hides the cost of deep pages using `skip`.

**Keyset pagination** is typically far more efficient when a stable sort order exists:

```javascript
db.orders.createIndex({
  customerId: 1,
  createdAt: -1,
  _id: -1
});

const lastCreatedAt = ISODate("2026-11-02T09:30:00Z");
const lastId = "O1002";

db.orders.find({
  customerId: "C01",
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    {
      createdAt: lastCreatedAt,
      _id: { $lt: lastId }
    }
  ]
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
```

This example assumes `_id` is a string compared in stored order; keep types and collations consistent.

### 12.2. Projection and Payload

```javascript
// Returns entire large documents:
db.orders.find({ customerId: "C01" });

// Returns only required fields:
db.orders.find(
  { customerId: "C01" },
  { _id: 1, createdAt: 1, status: 1 }
);
```

Projection reduces bytes transferred and decoded, yet does not automatically make a query covered. Even when MongoDB still FETCHes documents, smaller responses improve application latency. Conversely, a covered query returning hundreds of thousands of keys can still produce a huge payload.

---

## 13. Aggregation Queries: Stage Stats Are Not API Latency

Dashboard example calculating revenue per customer:

```javascript
db.orders.aggregate([
  {
    $match: {
      status: "PAID",
      createdAt: {
        $gte: ISODate("2026-11-01T00:00:00Z"),
        $lt: ISODate("2026-12-01T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: "$customerId",
      orderCount: { $sum: 1 },
      totalRevenueMinor: { $sum: "$totalMinor" }
    }
  },
  { $sort: { totalRevenueMinor: -1 } },
  { $limit: 10 }
]);
```

Explain:

```javascript
db.orders.explain("executionStats").aggregate([
  {
    $match: {
      status: "PAID",
      createdAt: {
        $gte: ISODate("2026-11-01T00:00:00Z"),
        $lt: ISODate("2026-12-01T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: "$customerId",
      totalRevenueMinor: { $sum: "$totalMinor" }
    }
  },
  { $sort: { totalRevenueMinor: -1 } },
  { $limit: 10 }
]);
```

An aggregation may read millions of orders to produce ten summary rows. Final `nReturned = 10` does not mean only ten source documents were processed. Inspect input/output counts per stage alongside documents/keys examined.

### 13.1. Blocking Stages and Time to First Result

`$sort` and `$group` may accumulate large volumes of data before emitting a single document. Thus, time-to-first-document differs sharply from an indexed `limit(10)` query streaming results directly.

### 13.2. Never Sum Stage Estimates

If explain reports estimated times across multiple stages, do not add them together to claim total latency. Parent and child stages overlap in work, some stages use distinct sampling/estimation, and output formats differ across engines.

### 13.3. When Indexes Are Not Enough

Indexes help `$match` and sometimes `$sort`, yet cannot eliminate the cost of aggregating massive datasets on the fly. If a dashboard recomputes the exact same summaries constantly, consider **computed summaries** or pre-aggregation with clear update/reconciliation policies.

---

## 14. Sharded Clusters and Read Preference

In a sharded setup, a query passes through `mongos` to one or more shards. Explain output can contain separate per-shard plans and statistics.

```text
Java application
       |
       v
     mongos
     /   \
    v     v
 Shard A Shard B
```

End-to-end latency can be affected by:

- Number of shards targeted.
- Coordination and result-merging overhead at the router.
- Speed of the slowest shard.
- Network between `mongos` and shards.
- Data return path from `mongos` to the app.

**Do not sum `executionTimeMillis` across shards and equate it to HTTP latency.** Shards can run in parallel; metrics at each tier have different scopes and measurement boundaries. Read the sharded plan alongside live request traces.

Read preference matters too: the API might read from a secondary while explain ran against the primary in a shell. If nodes differ in load, cache, or network latency, numbers are not directly comparable.

---

## 15. Four Classic Discrepancy Investigation Cases

### Case A — Fast Explain, Slow API Due to Connection Pool

**Illustrative scenario:**

```text
explain.executionTimeMillis:    6 ms
Mongo find command round trip:  9 ms
Connection pool wait:         140 ms
API request latency:          185 ms
```

Most of the delay likely sits in waiting for a connection or pre/post-query work. Actions:

1. Check pool size, checked-out connections, pending checkouts, and wait times.
2. Check concurrent requests and how long cursors/connections are held open.
3. Check whether long-running queries/cursors are starving the pool.
4. Tune concurrency, timeouts, or pool sizing to the workload **after measuring**, rather than blindly raising pool size indefinitely.

Adding an index does not directly eliminate pool wait times in every case, though faster queries can indirectly free connections sooner.

### Case B — Fast Explain, Slow API Due to Many `getMore` Calls

```text
explain:                       12 ms
find command:                   9 ms
getMore commands:           8 × 20 ms
DTO mapping + JSON:            80 ms
HTTP total:                   290 ms
```

Numbers are illustrative. The query likely returns tens of thousands of documents across multiple batches. Actions:

- Count actual returned documents.
- Count `getMore` calls and total bytes transferred.
- Ask whether the API truly needs the entire dataset.
- Apply projection, limit, keyset pagination, or appropriate streaming.
- Measure cursor drain separately from JSON serialization.

Stopping at explain and concluding "MongoDB isn't slow so nothing needs fixing" overlooks the cost of hauling huge data out of MongoDB.

### Case C — Slow Explain Due to Heavy Scanning, Slow API Too

```text
explain:
  executionTimeMillis:       480
  totalKeysExamined:      450000
  totalDocsExamined:      280000
  nReturned:                  20

API p95 latency:             650 ms
```

This clearly points to **query plan and index** issues. Inspect filter, sort, and compound indexes—especially if an index exists yet still scans hundreds of thousands of keys. Test index candidates aligned with access patterns, measure before/after, and monitor write costs of new indexes.

### Case D — Fast Explain After Cache Warm-Up, High Production p99

Someone repeatedly runs explain for customer `C01`, whereas production randomly queries millions of customers. Pages for `C01` warm up in cache, making explain look fast, while p99 hits cold pages or I/O spikes.

Actions:

- Test across a representative parameter distribution rather than one fixed customer.
- Benchmark both warm and cold workloads where relevant.
- Analyze storage latency, cache hit/miss rates, and working set size.
- Observe p95/p99 under realistic concurrency.

### Case E — Explain and Live API Actually Run Different Queries

Suppose explain runs only:

```javascript
db.orders.find({
  customerId: "C01"
}).limit(20).explain("executionStats");
```

While the real API runs:

```javascript
db.orders.find({
  customerId: "C01"
}).sort({ createdAt: -1 })
  .skip(50000)
  .limit(100);
```

Different sort, skip, and limit change both query cost and transferred data volume. Before blaming the network, **reproduce the exact query shape**, projection, sort, skip, collation, and predicates used by the API.

### Case F — Fast MongoDB Command, Slow HTTP Due to Other Services

```text
MongoDB command total:      15 ms
Call pricing API:          110 ms
Business rules:             25 ms
JSON serialization:         20 ms
HTTP total:                190 ms
```

MongoDB tuning here has a very low ceiling of benefit. Optimize the application critical path or external service dependencies instead of adding more indexes.

---

## 16. Comprehensive Measurement Example in Java

Time the endpoint while separating MongoDB cursor reading from mapping:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class OrderService {

    private final MongoCollection<Document> orders;

    public OrderService(MongoCollection<Document> orders) {
        this.orders = orders;
    }

    public List<Document> listRecentPaid(String customerId) {
        long requestStart = System.nanoTime();

        List<Document> loaded = new ArrayList<>();
        long mongoStart = System.nanoTime();

        try (MongoCursor<Document> cursor = orders.find(
                    Filters.and(
                        Filters.eq("customerId", customerId),
                        Filters.eq("status", "PAID")
                    )
                )
                .projection(Projections.fields(
                    Projections.include("createdAt", "totalMinor")
                ))
                .sort(Sorts.orderBy(
                    Sorts.descending("createdAt"),
                    Sorts.descending("_id")
                ))
                .limit(20)
                .iterator()) {

            while (cursor.hasNext()) {
                loaded.add(cursor.next());
            }
        }

        long mongoEnd = System.nanoTime();

        // In a real app, DTO mapping logic may sit here.
        List<Document> response = loaded;

        long methodEnd = System.nanoTime();

        System.out.printf(
            "dbCursorMs=%d serviceMethodMs=%d count=%d%n",
            TimeUnit.NANOSECONDS.toMillis(
                mongoEnd - mongoStart
            ),
            TimeUnit.NANOSECONDS.toMillis(
                methodEnd - requestStart
            ),
            response.size()
        );

        return response;
    }
}
```

This illustrates **service-method instrumentation**, not full HTTP end-to-end timing. It starts after authentication/routing and ends before the framework serializes and flushes the HTTP response. To capture the full request, add timers in HTTP middleware or distributed tracing covering handler and response.

To break down pool wait, command round trips, and deserialization further, use driver monitoring and dedicated spans rather than guessing everything from one cursor timer.

### 16.1. Different Metrics Can Nest Inside Each Other

Example:

```text
serviceMethodMs = 85
dbCursorMs      = 62
findCommandMs   = 20
getMoreMs       = 10
```

Do not add `85 + 62 + 20 + 10`. `dbCursorMs` sits inside `serviceMethodMs`, and `find`/`getMore` sit inside cursor execution. Summing nested spans **double-counts time**.

---

## 17. Metrics Worth Capturing on a Dashboard

A helpful observability set by endpoint and query shape:

| Group | Metrics | Purpose |
| --- | --- | --- |
| API | Request count, p50/p95/p99 latency, error rate | Shows actual user-facing latency. |
| Driver | Command duration by `find`/`getMore`/`aggregate` | Shows MongoDB command time at the driver. |
| Cursor | Documents returned, batches, cursor drain time | Spots oversized result transfers. |
| Pool | Checked-out, pending checkout, wait time, timeouts | Spots connection contention. |
| Server query | Keys/docs examined, plan, sort stage, duration | Spots broad scans and missing indexes. |
| Server resources | CPU, memory/cache, disk latency/IOPS | Separates query logic from infrastructure load. |
| Database topology | Node, read preference, replication/lag | Spots per-node skew or server selection issues. |
| Payload | BSON/HTTP bytes, JSON serialization duration | Spots transfer and encoding costs. |

You do not need to log raw input documents to collect these metrics. When logging query shapes or filters, **mask or strip sensitive values**.

### 17.1. Use Percentiles Instead of a Single Sample

If an endpoint shows:

```text
p50 = 35 ms
p95 = 140 ms
p99 = 850 ms
```

a single 10 ms explain may represent the fast path yet says little about long-tail requests. Inspect slow samples in context: pool wait, concurrency, abnormally large result sets, I/O, and target node.

Never equate average latency with p95/p99. Averages can look low while a subset of users endures terrible tail latency.

### 17.2. Measure by Query Shape and Parameter Tier

One endpoint may serve small customers (10 orders) and huge customers (millions of orders). Same query shape, vastly different matching counts. Sample both tiers and measure against realistic distributions.

---

## 18. Practical Workflow for Investigating Latency Discrepancies

### Step 1 — Define the Exact Measurement Question

Clarify:

- Does "application latency" mean server-side handler, gateway, or browser?
- Is the number average, p95, p99, or a single request?
- Which node ran explain, and when?
- Does the app drain the full cursor?

Without answering these, comparing two millisecond figures usually leads to wrong conclusions.

### Step 2 — Capture a Trace of a Slow Request

A solid trace breaks down each segment:

```text
HTTP request
  -> auth/validation
  -> pool checkout
  -> MongoDB command(s)
  -> cursor consumption
  -> mapping
  -> external calls
  -> serialization
  -> response
```

If spans are missing, add instrumentation before changing indexes. Never blame unmeasured gaps on the network or database by guesswork.

### Step 3 — Recover the Exact Query

Collect a **PII-free query shape** and relevant parameters:

```text
collection = orders
filter     = customerId + status
sort       = createdAt DESC, _id DESC
limit      = 20
projection = _id, createdAt, totalMinor
readPreference = primary
```

Separate it from queries that merely share an endpoint name while differing in `skip`, ranges, batch size, or collation.

### Step 4 — Read the Execution Plan

Run explain carefully and inspect:

- `COLLSCAN` or `IXSCAN`?
- `FETCH` or covered?
- Costly `SORT`?
- Keys/docs examined relative to `nReturned`?
- Which index was chosen? Is there an index matching filter + sort?
- Are multiple candidate plans competing?
- In a sharded cluster, how is work spread across shards?

### Step 5 — Correlate with Live Commands

Inspect command monitoring / profiler data for the actual request:

- How long did `find`/`aggregate` take?
- Were there `getMore` calls, and how many?
- Was there significant pool wait or server selection time?
- Were there timeouts or retries?
- How many bytes and documents were transferred?

Only now can you distinguish a **server query bottleneck**, a **driver/network bottleneck**, and an **application bottleneck**.

### Step 6 — Propose Fixes Aligned with the Root Cause

| Observed Cause | Remediation Direction |
| --- | --- |
| `COLLSCAN` or huge keys/docs examined | Review filters, compound indexes, selectivity, query rewrites. |
| Expensive `SORT` | Index supporting filter + sort, result limits. |
| Returning too many documents | Projection, limit, keyset pagination, streaming. |
| Excessive `getMore` / network traffic | Check batch size, payload, and actual data requirements. |
| Long pool checkout wait | Check concurrency, pool settings, long-lived cursors holding connections. |
| Hot cache / I/O contention | Check working set, index/data sizes, concurrent load. |
| Heavy DTO / JSON overhead | Optimize mapping, response contracts, serialization. |
| Slow external service | Optimize downstream dependencies and app critical path. |

### Step 7 — Re-Measure End-to-End

After a change, do not merely report "explain dropped from 400 to 10 ms." Verify:

- Did API p95/p99 actually drop?
- Did throughput improve?
- Did error/timeout rates change?
- Are MongoDB CPU, I/O, and cache stable?
- How much did the new index slow inserts/updates/deletes?
- Were other queries negatively impacted?

**Optimization is complete when user-facing behavior improves**, not when one number in explain looks prettier.

---

## 19. Benchmarking Properly Without Creating Fake Results

### 19.1. Keep Query Shape Identical

Do not compare `findOne` against `find` + `toArray`, do not compare `limit(20)` against unbounded queries, and do not omit `sort` in explain if the live API sorts. Keep projection, collation, read concern, and target node equivalent whenever possible.

### 19.2. Run Multiple Times Across Varied Parameters

One run can benefit from a warm cache or suffer random contention. Use representative input distributions and report p50/p95/p99, never a single best-case reading.

### 19.3. Separate Sequential Load from Concurrent Load

A query running sequentially on an idle server behaves differently from 500 concurrent requests fighting over CPU, cache, and connections. To forecast production latency, test at realistic concurrency.

### 19.4. Do Not Benchmark with Excessive Logging

Printing JSON for every document or writing synchronous logs inside a tight loop severely slows the client. Measure individual steps cleanly with lightweight instrumentation and appropriate sampling.

### 19.5. Do Not Subtract Clocks Across Different Hosts

`System.nanoTime()` measures **elapsed time within one process**. Wall clocks on app servers and database nodes can drift. Distributed tracing requires correlation and proper clock handling; never subtract timestamps from two different machines to measure network latency without accounting for clock skew.

### 19.6. Evaluate the Cost of New Indexes

A compound index that speeds up reads can introduce write amplification. Measure writes, index build cost, disk footprint, and update workloads—not just `executionTimeMillis` on one read endpoint.

---

## 20. Misconceptions to Avoid

| Misconception | Accurate Understanding |
| --- | --- |
| "`executionTimeMillis` is HTTP request duration." | It is server-reported duration for the explain op, omitting the rest of the app. |
| "Explain 5 ms, API 200 ms means 195 ms network." | Unsupported; could be pool wait, `getMore`, serialization, app logic, load, or a different query. |
| "Explain always runs the app's exact cached plan." | Explain interacts separately with the plan cache and can pick a different plan. |
| "Calling `find()` in Java downloads all results immediately." | `FindIterable` is lazy; you must drain the cursor to measure real execution. |
| "`first()` measures the same thing as `toArray()`." | Fetching one document differs from materializing the full result set. |
| "One `find` command equals the entire cursor." | Multiple `getMore` commands may follow. |
| "`limit(20)` guarantees reading only 20 documents." | Filters, sorts, and `skip` can force examining far more. |
| "`nReturned = 20` means only 20 source docs were processed." | Aggregation/sort/filter may process huge inputs to return 20 results. |
| "Stage-level `executionTimeMillisEstimate` values can be summed." | Stages nest; estimates are not independent timers. |
| "`executionTimeMillis: 0` means the query cost nothing." | Timer resolution and fast operations can report 0 ms. |
| "A query with `IXSCAN` is guaranteed fast." | It can still scan millions of keys and `FETCH` many docs. |
| "One fast explain proves p99 will be fast." | p99 is shaped by cache misses, concurrency, data skew, and more. |
| "Profiler metrics equal HTTP latency." | The profiler tracks server ops, excluding app/client network time. |
| "Command duration is pure MongoDB CPU time." | It is driver-observed command time including network round trips. |
| "All span durations can be summed." | Spans nest or run in parallel; summing double-counts time. |
| "New indexes always improve API latency." | They might go unused, or the real bottleneck sits outside the query. |
| "Adding indexes has zero write cost." | Inserts/updates/deletes must maintain indexes; always measure impact. |

---

## 21. Scenario Exercises

### Exercise 1 — Faulty Measurement in Java

Code snippet:

```java
long start = System.nanoTime();
FindIterable<Document> result =
    collection.find(Filters.eq("status", "PAID"));
long duration = System.nanoTime() - start;
```

**Question:** Why does this tiny reading not prove MongoDB returned millions of documents in nanoseconds?

**Hint:** `FindIterable` merely describes the query; the snippet never consumed the cursor. Open the cursor and read results up to what the real endpoint consumes.

### Exercise 2 — Fast Explain, Slow Service

```text
explain.executionTimeMillis = 8 ms
findCommandDuration        = 11 ms
poolCheckoutWait           = 130 ms
HTTP p95                   = 190 ms
```

**Question:** Should you immediately create a new compound index, or what should you investigate?

**Hint:** Pool wait time dominates. Check connection pool sizing, concurrency, open cursors, and connection hold times before blaming indexes.

### Exercise 3 — Multiple Batches

An API loads 50,000 documents; the driver logs one `find` and 30 `getMore` commands. Explain reports only 15 ms.

**Question:** Why might the API take over a second?

**Hint:** Multiple network round trips, large payload transfer, and BSON/JSON mapping are excluded from explain timing; measure cursor drain and bytes transferred.

### Exercise 4 — Reading the Query Plan Before Explaining Latency

Hypothetical explain:

```text
nReturned             = 15
totalKeysExamined     = 400000
totalDocsExamined     = 220000
executionTimeMillis   = 650
```

**Question:** Which issue should you investigate first?

**Hint:** Weakly selective or mismatched filter/index; inspect `IXSCAN`, `FETCH`, sorting, compound indexes, and query shape.

### Exercise 5 — Warm Cache

Running explain 20 times in a row for customer `C01` looks fast, while production p99 across diverse customers is high.

**Question:** Why can you not treat the fastest reading as your SLA?

**Hint:** Repeating one parameter warms its working set; test across realistic parameter distributions and production-like concurrency.

### Exercise 6 — Differing Result Limits

Explain uses `limit(20)`, while the real API uses `skip(100000).limit(20)`.

**Question:** Can those two timings be compared directly?

**Hint:** No; the engine may traverse many keys to skip deep offsets. Consider keyset pagination and an index supporting deterministic sorting.

### Exercise 7 — Nested Span Sums

A trace shows:

```text
HTTP handler   250 ms
Mongo cursor    70 ms
find command    25 ms
getMore         20 ms
```

**Question:** Can you sum them to 365 ms?

**Hint:** No; Mongo cursor sits inside the HTTP handler, and commands sit inside the cursor. Inspect parent-child nesting and the critical path.

### Exercise 8 — Optimizing Reads While Hurting Writes

Adding a compound index drops explain from 350 ms to 30 ms, yet insert throughput falls by 25%.

**Question:** Should you definitely keep the index?

**Hint:** Evaluate query frequency, SLA, latency savings, and write workload impact. Consider partial indexes, query adjustments, or pre-aggregation.

---

## 22. Mental Checklist When Reconciling Metrics

Before claiming "explain and the application don't match," verify:

1. **Is it the exact same query?** Filter, sort, projection, skip, limit, collation, batch size.
2. **Is it the same node and conditions?** Read preference, sharding, workload, cache, version.
3. **Are you comparing two different executions?** Explain does not follow the cached query path.
4. **Did you drain the full cursor?** `find`, `getMore`, iteration time, document count.
5. **What did the app wait on before MongoDB?** Pool checkout, server selection, auth.
6. **What did the app do after MongoDB?** DTO mapping, business logic, HTTP serialization, external calls.
7. **Does the plan itself have a logic/index issue?** High docs/keys examined, `SORT`, `COLLSCAN`, ill-fitting index.
8. **Is it a single run or a percentile?** p50/p95/p99 under load.
9. **Are you double-counting nested spans?** Parent/child nesting and async overlap.
10. **Does the proposed optimization truly help the SLA?** Re-measure end-to-end, including write impact.

## 23. Official MongoDB References

- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/): explain fields, runtime stats, and plan representation.
- [Explain Command](https://www.mongodb.com/docs/manual/reference/command/explain/): verbosity levels and explain behavior.
- [Query Plans](https://www.mongodb.com/docs/manual/core/query-plans/): query planner, plan selection, and plan cache.
- [Query Optimization](https://www.mongodb.com/docs/manual/core/query-optimization/): indexes, sorting, covered queries.
- [Cursors](https://www.mongodb.com/docs/manual/core/cursors/): cursors and result batching.
- [MongoDB Java Sync Driver — Query Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/): `find`, filters, sorts, projections, cursors.
- [MongoDB Java Sync Driver — Monitor Application Events](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/monitoring/): command monitoring and driver observability.
- [Database Profiler](https://www.mongodb.com/docs/manual/tutorial/manage-the-database-profiler/): capturing server-side execution details.

When consulting documentation, match your exact MongoDB server and driver versions, as explain output, execution engines, monitoring APIs, and plan cache details evolve across releases.

## 24. Conclusion

**`explain("executionStats")` answers "Which plan did MongoDB choose and run, and how much work did that explain execution perform?"** It does not fully answer "How long did a user wait on the API?"

**Application latency** spans many parts: acquiring/waiting for a connection, sending commands, server execution, fetching batches, decoding BSON, mapping, calling external services, serializing, and sending responses. Even a MongoDB driver command is just one segment along that path.

Effective investigation **combines** execution plans and counters from explain with command monitoring, cursor metrics, profiler/server logs, and distributed tracing. Never extrapolate one layer's milliseconds to represent all remaining layers; measure boundaries cleanly, match the real workload, and optimize where the actual bottleneck lives.
