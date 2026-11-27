# Executing Aggregations, `bulkWrite`, and Reading Results in Batches

In Java applications using MongoDB, many problems go beyond `findOne()` or `insertOne()`. A real-world system often needs to:

- Filter, group, summarize, and sort millions of documents using an **aggregation pipeline**.
- Update or insert multiple documents in a single round via **`bulkWrite()`**.
- Read a large result set without loading it all into the JVM using **cursors and batching**.
- Transform data from a source collection to a target collection—reading and writing concurrently—while remaining safely restartable when a job fails.
- Track latency, per-operation errors, processed record counts, connection wait times, and recovery capability.

These three techniques work closely together: **aggregation produces the data**, **cursors stream it incrementally**, and **`bulkWrite` persists changes more efficiently than many individual round trips**. However, they neither replace one another nor automatically guarantee correctness, safe retries, or data consistency.

This lesson, **"Executing Aggregations, `bulkWrite`, and Reading Results in Batches"**, in the **Java Driver** chapter explains how to use the **MongoDB Java Sync Driver** with Java examples, BSON builders, resource management, performance tuning, error handling, and an operationally sound data-transfer workflow.

> **Three takeaways to remember upfront:** `aggregate()` returns a result iterable evaluated when consumed; `batchSize()` is a hint for how many documents the server sends per fetch, not a limit on total results; and `bulkWrite()` is a batch of write operations, **not an atomic transaction over the whole batch by default**.

---

## 1. Big Picture

A Java data-processing pipeline might look like this:

```text
MongoDB collection: orders
          │
          ▼
Java Sync Driver
          │
          ▼
aggregate(pipeline)
          │
          ▼
AggregateIterable<Document>
          │
          ▼
MongoCursor<Document>
  ├── batch from server #1
  ├── getMore / batch #2
  ├── getMore / batch #3
  └── ...
          │
          ▼
Java transformation / validation
          │
          ▼
List<WriteModel<Document>>
          │
          ├── Reached 500 ops → bulkWrite(...)
          ├── Reached 500 ops → bulkWrite(...)
          └── Remaining 147 ops → bulkWrite(...)
          │
          ▼
MongoDB collection: orderSummaries
```

There are **two distinct kinds of batches** here:

1. **Read batch**: controlled by the MongoDB server and cursor protocol, influenced by `batchSize()` and response size limits.
2. **Write batch**: assembled by the application as `WriteModel` items and passed to `bulkWrite()`, which the driver may split into underlying protocol commands to respect server limits.

There is no requirement that read batch size and write batch size be equal.

## 2. Choosing the Right API

| Need | Java Sync Driver API | Characteristics |
|---|---|---|
| Find one document | `find(...).first()` | Simple; returns one document or `null` |
| Read multiple documents | `find(...)` + `MongoCursor` | Incremental cursor iteration |
| Aggregate data | `aggregate(pipeline)` | Filter, group, compute, join, transform |
| Consume aggregation results | `AggregateIterable<T>` | Iterate, limit, batch, timeout |
| Simple multi-document insert | `insertMany()` | Inserts homogeneous documents |
| Mixed write types in one batch | `bulkWrite(models, options)` | Insert/update/replace/delete |
| Update one document | `updateOne()` | Easy per-operation result handling |
| Server-side write from aggregation | `$merge` / `$out` | Final aggregation stage that writes |
| Continuous change tracking | `watch()` / change streams | Event stream; differs from batch scans |
| Multi-document transactions | `ClientSession` / transaction API | Atomicity where supported |

Picking an API is not just "which is fastest?"—it also depends on **where transformations run, how many round trips occur, what consistency guarantees are needed, and how recovery works on failure**.

## 3. Setting Up the Java Environment

Examples use the **MongoDB Java Sync Driver**. Choose a driver release officially supported for your running MongoDB Server; the APIs below follow the 5.x driver style.

### 3.1. Maven

```xml
<dependency>
    <groupId>org.mongodb</groupId>
    <artifactId>mongodb-driver-sync</artifactId>
    <version>${mongodb.driver.version}</version>
</dependency>
```

`mongodb.driver.version` is a project property that must resolve to a specific compatibility-verified version. Never pick an arbitrary version simply because examples use 5.x.

### 3.2. Gradle

```groovy
dependencies {
    implementation "org.mongodb:mongodb-driver-sync:${mongoDriverVersion}"
}
```

`mongoDriverVersion` is a build variable. This snippet only illustrates the dependency; you do not need to run Gradle to follow the lesson.

### 3.3. Connection String

Configure the connection string in a secret manager or environment variable:

```text
MONGODB_URI=mongodb+srv://<user>:<password>@<cluster-host>/
```

This is an illustrative template, not a live URI. Production requires TLS, network access controls, RBAC, and least-privilege database users.

Do not:

- Hardcode passwords in source code;
- Commit `.env` files containing secrets;
- Log full URIs;
- Disable certificate or hostname verification to "fix" TLS errors.

### 3.4. Initializing the Client

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;

import org.bson.Document;

public class MongoSetup {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is not configured");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("demo_orders");
            MongoCollection<Document> orders =
                db.getCollection("orders");

            System.out.println(
                "Connected collection: " + orders.getNamespace()
            );
        }
    }
}
```

In a web service, use **one shared `MongoClient` scoped to the application lifecycle** rather than creating and closing a client per HTTP request. `MongoClient` manages connection pools, monitoring, and topology discovery.

## 4. Sample Data and Problem Statement

Collection `demo_orders.orders` contains:

```javascript
{
  _id: "ORD-1001",
  tenantId: "T-01",
  customerId: "C-105",
  status: "PAID",
  amountCents: NumberLong("249900"),
  createdAt: ISODate("2026-11-10T08:30:00Z"),
  updatedAt: ISODate("2026-11-10T08:31:00Z"),
  channel: "WEB",
  tags: ["priority", "gift"]
}
```

Additional documents:

```javascript
{
  _id: "ORD-1002",
  tenantId: "T-01",
  customerId: "C-105",
  status: "PAID",
  amountCents: NumberLong("100000"),
  createdAt: ISODate("2026-11-11T09:00:00Z"),
  channel: "APP"
}
```

```javascript
{
  _id: "ORD-1003",
  tenantId: "T-02",
  customerId: "C-205",
  status: "CANCELLED",
  amountCents: NumberLong("350000"),
  createdAt: ISODate("2026-11-11T10:00:00Z"),
  channel: "WEB"
}
```

The problem has three parts:

1. Compute **total paid revenue per customer** within a date range.
2. Read the results in a **memory-bounded** way.
3. Insert or update the `customerRevenue` collection per group via **bulk upsert**.

Examples use integer minor units (`amountCents`) to avoid `double` rounding drift. Real financial systems may use `Decimal128`, `BigDecimal`, and stricter monetary rules.

### 4.1. Candidate Index

An index to support filtering:

```javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: 1,
  customerId: 1
});
```

This is only a **candidate**: inspect query shapes, `explain("executionStats")`, cardinality, and read/write overhead. Never create an index in production simply because it appeared in an example.

## 5. What Is an Aggregation Pipeline?

An aggregation pipeline is an ordered list of **stages** executed sequentially over a stream of documents. Each stage receives an input stream, transforms it, and passes output to the next stage.

```text
orders
  │
  ▼
$match      filter tenant/status/date
  │
  ▼
$group      group by customerId
  │
  ▼
$project    shape output fields
  │
  ▼
$sort       sort by total revenue
  │
  ▼
$limit      take top N customers
  │
  ▼
aggregation result
```

Common stages:

| Stage | Purpose |
|---|---|
| `$match` | Filter documents |
| `$project` | Select/transform fields |
| `$group` | Group and compute aggregates |
| `$sort` | Sort results |
| `$limit` | Cap output count |
| `$skip` | Skip leading results |
| `$unwind` | Deconstruct array elements into documents |
| `$lookup` | Join data from another collection |
| `$set` / `$addFields` | Add/modify fields |
| `$facet` | Run parallel sub-pipelines |
| `$count` | Count documents |
| `$merge` | Write results into a target collection |
| `$out` | Write results out to a collection per stage semantics |

Some stages have position and version constraints and cannot be reordered arbitrarily.

## 6. Writing Pipelines Directly with `Document`

The Java Driver accepts `Bson` stages. `org.bson.Document` closely mirrors MongoDB shell syntax:

```java
import java.util.Arrays;
import java.util.Date;
import java.util.List;

import org.bson.Document;
import org.bson.conversions.Bson;

Date from = new Date(1761955200000L);
Date to = new Date(1764547200000L);

List<Bson> pipeline = Arrays.asList(
    new Document("$match",
        new Document("tenantId", "T-01")
            .append("status", "PAID")
            .append("createdAt",
                new Document("$gte", from).append("$lt", to))
    ),

    new Document("$group",
        new Document("_id", "$customerId")
            .append("grossCents",
                new Document("$sum", "$amountCents"))
            .append("orderCount",
                new Document("$sum", 1))
    ),

    new Document("$sort",
        new Document("grossCents", -1)
    ),

    new Document("$limit", 50)
);
```

Here the date bounds illustrate Unix millisecond timestamps. In real applications, use `Instant`/`Date.from(instant)` with explicit timezones; `to` is typically **exclusive** to prevent double-counting boundaries.

### 6.1. Role of Each Stage

1. `$match`: keeps only paid orders for tenant `T-01` within the date range.
2. `$group`: groups by customer, summing cents and counting orders.
3. `$sort`: sorts descending by gross revenue.
4. `$limit`: returns at most 50 customers.

Sample output:

```javascript
{
  _id: "C-105",
  grossCents: NumberLong("349900"),
  orderCount: 2
}
```

The type of `grossCents` depends on input types and accumulator rules. Never assume every sum across every collection is always Java `Long`; if `Decimal128`, floating-point, or overflow occurs, handle the actual BSON type properly.

### 6.2. `Document` Is Flexible but Error-Prone for Field/Operator Names

Drawbacks:

- Stage and field names are raw strings, prone to typos;
- Deeply nested `Document`s are hard to read;
- No compile-time type safety on BSON structure;
- Easy to accidentally mix in unvalidated inputs.

For common stages, the MongoDB Java Driver offers **builder APIs** that express intent more cleanly.

## 7. Using `Aggregates`, `Filters`, and `Accumulators` Builders

The Java Driver provides factory methods:

- `Filters.eq`, `gte`, `lt`, `and`;
- `Aggregates.match`, `group`, `project`, `sort`, `limit`;
- `Accumulators.sum`, `avg`, `max`, `min`;
- `Sorts.ascending`, `descending`;
- `Projections.include`, `excludeId`, `fields`.

Example:

```java
import java.util.Arrays;
import java.util.Date;
import java.util.List;

import com.mongodb.client.model.Accumulators;
import com.mongodb.client.model.Aggregates;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;

import org.bson.conversions.Bson;

Date from = new Date(1761955200000L);
Date to = new Date(1764547200000L);

List<Bson> pipeline = Arrays.asList(
    Aggregates.match(
        Filters.and(
            Filters.eq("tenantId", "T-01"),
            Filters.eq("status", "PAID"),
            Filters.gte("createdAt", from),
            Filters.lt("createdAt", to)
        )
    ),

    Aggregates.group(
        "$customerId",
        Accumulators.sum("grossCents", "$amountCents"),
        Accumulators.sum("orderCount", 1)
    ),

    Aggregates.sort(
        Sorts.descending("grossCents")
    ),

    Aggregates.limit(50)
);
```

Builders produce identical BSON stages without changing MongoDB execution semantics.

### 7.1. When to Use Builders vs. `Document`?

| Scenario | Choice |
|---|---|
| Common, well-supported stages | Builders |
| Newer stages lacking convenient driver builders | `Document` or `BsonDocument` |
| Dynamically assembled internal query plans | Builders composing `Bson` |
| Queries driven by user inputs | Validate and allowlist; never pass raw BSON |
| Long/multi-branch pipelines | Extract helper methods building stages |

Never accept `request.body` as an unrestricted pipeline unless clients are explicitly permitted to run arbitrary MongoDB operators.

## 8. Calling `aggregate()` in Java

Given a collection:

```java
MongoCollection<Document> orders =
    client.getDatabase("demo_orders")
          .getCollection("orders");
```

Execute:

```java
import com.mongodb.client.AggregateIterable;

AggregateIterable<Document> result =
    orders.aggregate(pipeline);

for (Document row : result) {
    String customerId = row.getString("_id");
    Object grossCents = row.get("grossCents");
    Number count = (Number) row.get("orderCount");

    System.out.printf(
        "Customer=%s gross=%s count=%d%n",
        customerId,
        grossCents,
        count.longValue()
    );
}
```

If data is large or sensitive, **never print every document into production logs**. The example uses synthetic revenue data.

### 8.1. What Is `AggregateIterable`?

`aggregate()` returns an `AggregateIterable<TResult>`—an object representing the aggregation query and supporting options such as:

```java
orders.aggregate(pipeline)
    .allowDiskUse(true)
    .batchSize(200)
    .maxTime(30, java.util.concurrent.TimeUnit.SECONDS);
```

Server execution happens when **consuming the iterable** (via `iterator()`, a `for` loop, `first()`, or `into()`), not simply when assigning `result`.

This is especially critical for pipelines ending in `$merge` or `$out`: constructing `AggregateIterable` without consuming it leaves the pipeline unexecuted.

### 8.2. Do Not Confuse the Iterable with Materialized Data

`AggregateIterable<Document>` is **not** a `List<Document>` already residing in RAM. The driver uses a cursor to fetch batches from the server as the application iterates.

To collect everything, `into()` exists, but always watch result size.

## 9. `first()`, `into()`, `forEach()`, and `iterator()`

Ways to consume results:

### 9.1. Taking the First Result

```java
Document first = orders.aggregate(pipeline).first();

if (first == null) {
    System.out.println("No aggregation result");
}
```

Useful when at most one summary document is expected. If only one item is needed from a multi-row pipeline, add `$limit: 1` explicitly.

### 9.2. Collecting Everything into a `List`

```java
import java.util.ArrayList;
import java.util.List;
import org.bson.Document;

List<Document> all = orders.aggregate(pipeline)
    .into(new ArrayList<>());
```

Convenient in JVM code, but if the pipeline yields millions of rows, this `List` consumes huge RAM or triggers `OutOfMemoryError`.

### 9.3. Using a `for` Loop

```java
for (Document row : orders.aggregate(pipeline)) {
    process(row);
}
```

Concise syntax, though when you need explicit cursor closure or complex lifecycle handling, prefer `MongoCursor`.

### 9.4. Using an Explicit Cursor

```java
import com.mongodb.client.MongoCursor;

try (MongoCursor<Document> cursor =
         orders.aggregate(pipeline).iterator()) {

    while (cursor.hasNext()) {
        Document row = cursor.next();
        process(row);
    }
}
```

`MongoCursor` implements `close()`; `try-with-resources` ensures closure even if processing throws an exception.

**For large result sets, explicit cursor management controls memory far better than `into(new ArrayList<>())`.**

## 10. Lazy Execution vs. Synchronous Blocking

The **MongoDB Java Sync Driver** is synchronous. Even though `AggregateIterable` executes lazily and fetches in batches, the thread calling `hasNext()`, `next()`, or `bulkWrite()` still **blocks waiting on I/O**.

```text
AggregateIterable created
        │
        ▼
cursor = iterable.iterator()
        │
        ▼
send aggregate command
        │
        ▼
fetch first batch
        │
        ▼
cursor.next() ...
        │
        ▼
need more docs?
        │
        └── getMore network round trip
```

Lazy does not mean non-blocking or reactive. If a service runs on an event loop forbidding blocking calls, use the Reactive Streams Driver or offload to a proper async execution model.

### 10.1. Never Call `parallelStream()` Directly on a Cursor

`MongoCursor` is not a concurrent random-access collection. Never share one cursor across multiple threads without explicit coordination. To process in parallel:

- One thread reads from the cursor;
- Feeds items into a bounded queue;
- Workers process independently;
- Enforce backpressure and cancellation;
- Define ordering and idempotency rules.

Unbounded concurrency risks OOM or exhausting connection pools.

## 11. What Does `batchSize()` Actually Control?

Example:

```java
AggregateIterable<Document> iterable =
    orders.aggregate(pipeline)
          .batchSize(250);
```

`batchSize(250)` hints to the server to send **around or up to that target document count per batch**, still bounded by response byte limits, server timers, and cursor/stage semantics.

It **does not**:

- Cap total returned documents at 250;
- Guarantee every batch contains exactly 250 documents;
- Guarantee a single network request;
- Alter how MongoDB computes `$group` or logical results;
- Define how many write models the app passes to `bulkWrite`;
- Create an automatic checkpoint if the JVM crashes;
- Guarantee strictly constant memory usage regardless of document size.

### 11.1. `batchSize` vs. `$limit`

| Option | Effect |
|---|---|
| `$limit: 1000` | Pipeline returns at most 1,000 results at that stage |
| `.batchSize(100)` | Results arrive across multiple network batches of ~100 |
| `find().limit(1000)` | Cursor returns at most 1,000 documents |
| `find().batchSize(100)` | Adjusts `find` cursor batch size |
| Application buffer 500 | Accumulates 500 records in JVM before processing/writing |
| Bulk write list 500 | Single `bulkWrite` invocation carrying 500 write models |

### 11.2. Approximate Batch Calculation

Suppose an aggregation yields 1,250 documents:

```text
batchSize = 250

Batch 1 → ~250 docs
Batch 2 → ~250 docs
Batch 3 → ~250 docs
Batch 4 → ~250 docs
Batch 5 → ~250 docs
```

Actual batch counts vary due to server message size caps and execution conditions. Treat this as a conceptual diagram—never build business logic assuming every batch has exactly 250 records.

### 11.3. Trade-Offs of Small vs. Large Batches

| Small Batch | Large Batch |
|---|---|
| Fewer docs buffered client-side per fetch | Fewer network round trips |
| Easier memory control for large docs | Higher memory pressure |
| More `getMore` overhead | Can impact cross-client latency/fairness |
| Fits slow downstream processing | Fits fast consumers and high network RTT |
| Does not fix query plans | Does not fix query plans |

There is no universally optimal `batchSize`. Start with a reasonable value and measure network traffic, heap, end-to-end duration, and `getMore` counts.

## 12. `getMore` and Cursor Lifecycle

A cursor does not necessarily hold every result upfront. Once the application drains the current batch, the driver sends **`getMore`** to fetch the next batch.

```text
aggregate command
    │
    ▼
firstBatch
    │
    ▼
Java consumes documents
    │
    ▼
getMore → nextBatch
    │
    ▼
Java consumes documents
    │
    ▼
getMore → nextBatch
    │
    ▼
cursor exhausted / closed
```

### 12.1. Why Close Cursors?

Cursors hold server-side state and resources. When stopping early:

```java
try (MongoCursor<Document> cursor =
         orders.aggregate(pipeline).iterator()) {

    for (int i = 0; i < 10 && cursor.hasNext(); i++) {
        process(cursor.next());
    }
}
```

Closing the cursor tells the driver to clean up associated resources. Never rely solely on server timeouts or the garbage collector to clean up abandoned cursors.

### 12.2. Cursors Can Time Out

A cursor left idle too long or hitting session/network drops can be closed by server/client/session timeout policies. Applications must treat cursors as **fallible streams during iteration**.

Never assume that because `aggregate()` returned an iterable, all 1 million documents are safely sitting in the JVM.

### 12.3. Batches Are Not a Transaction Boundary

Documents in batch 1 and batch 2 **do not automatically belong to a single point-in-time snapshot** merely because they share a cursor. If underlying data mutates concurrently, use appropriate read concerns, snapshots, transactions, or reconciliation per business requirements.

## 13. Memory-Safe Processing for Large Results

Dangerous for millions of rows:

```java
List<Document> allRows = orders.aggregate(pipeline)
    .into(new ArrayList<>());

for (Document row : allRows) {
    heavyTransform(row);
}
```

If each document averages a few KB, the list swells to multiple gigabytes plus `Document`, nested object, and JVM heap overhead.

Usually far better:

```java
long processed = 0;

try (MongoCursor<Document> cursor =
         orders.aggregate(pipeline)
               .batchSize(300)
               .iterator()) {

    while (cursor.hasNext()) {
        Document row = cursor.next();
        lightweightTransform(row);
        processed++;
    }
}

System.out.println("Processed rows: " + processed);
```

### 13.1. Use Projections to Shrink Payloads

If only `_id`, `customerId`, and `amountCents` are needed:

```java
import static com.mongodb.client.model.Aggregates.*;
import static com.mongodb.client.model.Projections.*;

List<Bson> pipeline = Arrays.asList(
    match(Filters.eq("tenantId", "T-01")),
    project(fields(include("_id", "customerId", "amountCents")))
);
```

Do not fetch `shippingAddress`, `paymentDetails`, or `items` when unused. This cuts network bandwidth, BSON decoding, heap allocation, and PII exposure.

### 13.2. Document Size Affects Effective Batching

300 documents of 200 bytes behave completely differently from 300 documents of 2 MB. MongoDB enforces BSON document and wire message size limits, so track **bytes**, not just record counts.

### 13.3. Stopping Cleanly

When a job is canceled or its thread interrupted:

- Stop reading the cursor;
- Close the cursor;
- Do not let workers hold unbounded queues or pending writes;
- Persist checkpoints only for committed data;
- Report job status and errors;
- Resume only via a verified checkpoint mechanism.

## 14. What Does `allowDiskUse()` Do?

Certain aggregation stages like `$group` and `$sort` buffer substantial intermediate data before emitting results.

```java
AggregateIterable<Document> iterable =
    orders.aggregate(pipeline)
          .allowDiskUse(true);
```

`allowDiskUse(true)` allows supported stages to spill temporary data to disk when needed, subject to server version, configuration, and stage limits.

It does **not** mean:

- Disk is always used;
- Resource limits disappear;
- Sorts are infinitely scalable for free;
- The query becomes fast;
- The JVM cannot OOM;
- Indexes are unnecessary;
- Every stage supports spilling.

Recent MongoDB Server versions may configure `allowDiskUseByDefault`; verify default server behavior in your environment.

### 14.1. Risks of Disk Spills

- Increased disk I/O;
- Temporary disk consumption;
- Degraded p95/p99 latency;
- Multiple concurrent spilling jobs causing storage saturation;
- Failures if disk fills or stage-specific limits are hit.

In production, monitor aggregation and disk metrics rather than treating `allowDiskUse(true)` as a cure-all for slow pipelines.

### 14.2. Optimize Stage Ordering

A well-ordered pipeline often follows:

```text
$match using indexed predicates
        ↓
$project keeping only needed fields
        ↓
$group
        ↓
$sort
        ↓
$limit
```

Never reorder stages without preserving semantics. For instance, `$match` after `$group` filters grouped outputs, which is not equivalent to filtering raw documents beforehand. Always verify query plans.

## 15. Timeouts for Aggregations

Example:

```java
import java.util.concurrent.TimeUnit;

AggregateIterable<Document> iterable =
    orders.aggregate(pipeline)
          .batchSize(300)
          .maxTime(30, TimeUnit.SECONDS);
```

`maxTime` bounds server-side command execution per MongoDB semantics. It is not an **absolute deadline for the entire Java job**, especially when the job also transforms data, writes outputs, waits on connection pools, traverses the network, and issues multiple `getMore` rounds.

Other timeouts:

| Timeout | Role |
|---|---|
| Server selection | Waiting to find an eligible server |
| Connection checkout | Waiting for a connection from the pool |
| Connect timeout | Establishing TCP/TLS connection |
| Read/socket timeout | Waiting for socket I/O per driver config |
| `maxTime` / `maxTimeMS` | Bounding MongoDB operation runtime |
| Application deadline | Overall workflow time limit |
| Batch job timeout | Scheduler / single run time limit |

Never set all timeouts to "infinite" just to avoid exceptions. Genuinely slow operations require investigating query plans, cache pressure, contention, or data models.

## 16. Inspecting Aggregations with `explain`

When supported by your driver version, run `explain`:

```java
Document plan = orders.aggregate(pipeline)
    .explain();

System.out.println(
    plan.get("queryPlanner") != null
        ? "Plan available"
        : "Inspect explain output structure for this server"
);
```

Output structure varies by MongoDB Server version, aggregation stages, and query engine. Do not assume `queryPlanner` is always a top-level field.

Check:

- Whether `$match` uses an indexed plan;
- `COLLSCAN` vs. `IXSCAN`;
- Blocking sorts;
- Group spills;
- Query execution time;
- Documents passing through each stage;
- Network and result sizes.

`explain()` is an analysis tool—it does not replace measuring full API p95/p99 under realistic load.

## 17. Aggregations Can Shrink Results Dramatically

Suppose:

```text
Orders input: 5,000,000 documents
Unique customers: 100,000
```

A `$group` pipeline by customer emits ~100,000 rows even though MongoDB processed most of the 5 million orders.

`batchSize(500)` controls **output rows per network batch**, not how many input documents `$group` must scan.

Optimization takeaways:

- `$match` shrinks the input set;
- Indexes accelerate initial filtering;
- `$group` consumes memory/disk proportional to group cardinality;
- Streaming outputs only eases **reading results**, not server-side work.

A pipeline returning very few rows can still be very expensive.

## 18. `$lookup` and Multi-Collection Data

To combine revenue with customer metadata, `$lookup` can join collections where supported and indexed:

```javascript
{
  $lookup: {
    from: "customers",
    localField: "_id",
    foreignField: "_id",
    as: "customer"
  }
}
```

In Java, use `Aggregates.lookup()` or `Document`.

### 18.1. Do Not Turn `$lookup` into N+1 Queries in Java

Inefficient pattern:

```text
Read 100,000 group results
        │
        └── For each result call customers.findOne(...)
                   → 100,000 round trips
```

Better options depending on workload:

- Properly indexed `$lookup`;
- Batched lookups using bounded `$in` queries;
- Pre-joined/materialized views;
- Controlled denormalization.

### 18.2. Security During Joins

In multi-tenant systems, ensure joins never leak records from another tenant. If `customerId` is only unique within a tenant, joining on `_id` carelessly can expose cross-tenant data. Enforce **tenant scoping on both source and joined collections**.

## 19. Aggregations That Write Directly via `$merge` or `$out`

Not every aggregation must stream rows into the JVM just to call `bulkWrite()`.

A pipeline can write directly inside MongoDB:

```javascript
db.orders.aggregate([
  { $match: { tenantId: "T-01", status: "PAID" } },
  {
    $group: {
      _id: "$customerId",
      totalCents: { $sum: "$amountCents" }
    }
  },
  {
    $merge: {
      into: "customerRevenue",
      on: "_id",
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
]);
```

This is a **conceptual example**. If multiple tenants share customer IDs, the output `_id` must include `tenantId` to avoid mixing tenant totals. Output schemas and unique keys must match multi-tenant boundaries.

### 19.1. Java: Pipeline with `$merge`

```java
List<Bson> pipeline = Arrays.asList(
    Aggregates.match(Filters.eq("tenantId", "T-01")),
    Aggregates.group(
        new Document("tenantId", "$tenantId")
            .append("customerId", "$customerId"),
        Accumulators.sum("totalCents", "$amountCents")
    ),
    new Document("$merge",
        new Document("into", "customerRevenue")
            .append("on", "_id")
            .append("whenMatched", "replace")
            .append("whenNotMatched", "insert")
    )
);
```

**Important:** creating `AggregateIterable` does not run the pipeline. You must consume it:

```java
try (MongoCursor<Document> cursor =
         orders.aggregate(pipeline).iterator()) {

    while (cursor.hasNext()) {
        cursor.next();
    }
}
```

`$merge` normally returns no business result documents, yet iterating the cursor triggers server execution. Never just call `orders.aggregate(pipeline);` and assume materialization ran.

### 19.2. When to Pick `$merge` Over `bulkWrite`?

`$merge` fits well when:

- All transformations express cleanly as aggregation stages;
- Processing near the data saves JVM/network transfer;
- The target collection is authorized;
- Merge semantics fit business rules;
- Idempotency, indexes, and permissions are planned.

Java `bulkWrite` fits better when:

- Complex business logic must run in Java;
- External APIs or non-MongoDB validations are involved;
- Mixed write models (`insert`/`update`/`delete`) are needed;
- Transformed records must also be routed/returned;
- Custom checkpointing or migration logic is required.

`$merge` is likewise not an atomic transaction across all output documents. Understand failure/retry semantics and design idempotency.

## 20. What Is `bulkWrite()`?

`MongoCollection.bulkWrite()` batches **multiple write operations** on one collection into a single API call:

- `InsertOneModel<T>`;
- `UpdateOneModel<T>`;
- `UpdateManyModel<T>`;
- `ReplaceOneModel<T>`;
- `DeleteOneModel<T>`;
- `DeleteManyModel<T>`.

Example:

```text
BulkWrite:
  1. Insert order A
  2. Update order B
  3. Delete stale order C
  4. Replace order D
  5. Update status of order E
```

The MongoDB Driver accepts `List<WriteModel<T>>` and dispatches write commands within server/driver protocol limits.

### 20.1. Why Is It Usually Faster Than Single-Operation Loops?

Compare:

```java
for (Document d : documents) {
    collection.insertOne(d);
}
```

with:

```java
List<WriteModel<Document>> operations = ...;
collection.bulkWrite(operations);
```

Bulk writes cut network round trips and coordination overhead, though real speedups depend on batch size, topology, network RTT, indexes, validation, and operation mix.

Do not assume `bulkWrite` always beats `insertMany` or server-side `$merge`; benchmark your actual workload.

## 21. `bulkWrite` Example with Mixed Operation Types

```java
import java.util.ArrayList;
import java.util.List;

import com.mongodb.client.model.BulkWriteOptions;
import com.mongodb.client.model.DeleteOneModel;
import com.mongodb.client.model.InsertOneModel;
import com.mongodb.client.model.UpdateOneModel;
import com.mongodb.client.model.UpdateOptions;
import com.mongodb.client.model.Updates;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.WriteModel;
import com.mongodb.bulk.BulkWriteResult;

import org.bson.Document;

List<WriteModel<Document>> writes = new ArrayList<>();

writes.add(
    new InsertOneModel<>(
        new Document("_id", "ORD-2001")
            .append("tenantId", "T-01")
            .append("status", "NEW")
            .append("amountCents", 149900L)
    )
);

writes.add(
    new UpdateOneModel<>(
        Filters.and(
            Filters.eq("_id", "ORD-1001"),
            Filters.eq("tenantId", "T-01")
        ),
        Updates.combine(
            Updates.set("status", "SHIPPED"),
            Updates.currentDate("updatedAt")
        ),
        new UpdateOptions().upsert(false)
    )
);

writes.add(
    new DeleteOneModel<>(
        Filters.and(
            Filters.eq("_id", "TEMP-01"),
            Filters.eq("tenantId", "T-01")
        )
    )
);

BulkWriteResult result = orders.bulkWrite(
    writes,
    new BulkWriteOptions().ordered(true)
);

if (result.wasAcknowledged()) {
    System.out.println("Inserted: " + result.getInsertedCount());
    System.out.println("Matched: " + result.getMatchedCount());
    System.out.println("Modified: " + result.getModifiedCount());
    System.out.println("Deleted: " + result.getDeletedCount());
}
```

**Never run this example literally against production data.** It illustrates operations on a test collection with synthetic IDs.

### 21.1. Why Use `WriteModel<Document>`?

All operations in a collection-scoped bulk must match the collection's document type. `WriteModel<TDocument>` expresses diverse write operations cleanly in a type-safe list.

### 21.2. What Does `ordered(true)` Mean?

Writes execute in sequence: when a write error occurs in an ordered bulk, remaining writes are normally halted per bulk-write rules.

`ordered(true)` **does not make the batch atomic** and does not roll back earlier operations that already succeeded before the error.

## 22. `ordered` vs. `unordered`: Choosing a Strategy

Compare:

```java
new BulkWriteOptions().ordered(true);
```

versus:

```java
new BulkWriteOptions().ordered(false);
```

### 22.1. Ordered Bulk

Behavior:

```text
Write 1 → success
Write 2 → success
Write 3 → duplicate key error
Write 4 → not executed
Write 5 → not executed
```

Best when:

- Some operations depend on prior order;
- You want to fail fast on error;
- Sequential execution order matters at the API level;
- Subsequent writes must not run if an earlier write failed.

Still, ordered bulk **is not a transaction over the whole list**.

### 22.2. Unordered Bulk

Example:

```java
new BulkWriteOptions().ordered(false);
```

MongoDB can execute writes out of source order and continue remaining writes after individual write errors.

Behavior:

```text
Write 1 → success
Write 2 → duplicate key
Write 3 → success
Write 4 → success
Write 5 → validation error
```

Best when:

- Operations are independent;
- Maximizing throughput matters;
- Valid records should persist even if some records fail.

**Never guarantee every operation runs if a connection, server, or command-level failure occurs.** A severe failure can abort remaining operations.

### 22.3. Unordered Does Not Preserve Update Order on the Same Record

Never use unordered for sequential state changes on the same document:

```text
Update status = PAID
Update status = SHIPPED
Update status = DELIVERED
```

if all three target the same document and final state depends on order.

Instead:

- Merge into one final state update if valid;
- Use ordered execution;
- Enforce optimistic concurrency/version guards;
- Or use a transaction when multi-document atomicity is required.

### 22.4. Comparison

| Criterion | `ordered(true)` | `ordered(false)` |
|---|---|---|
| Execution order | Follows input sequence | Not guaranteed |
| Write error mid-batch | Stops subsequent writes | Continues independent writes |
| Independent operations | Supported | Usually better fit |
| Order-dependent updates | Better fit | Avoid |
| Atomic whole batch | **No** | **No** |
| Partial success | Possible | Possible |
| Retry handling | Required | Required |

## 23. Common Write Model Patterns

### 23.1. Insert

```java
new InsertOneModel<>(
    new Document("_id", "ORD-3001")
        .append("tenantId", "T-01")
);
```

If `_id` collides, MongoDB raises a duplicate key error.

### 23.2. Update One Record

```java
new UpdateOneModel<>(
    Filters.eq("_id", "ORD-3001"),
    Updates.set("status", "PAID")
);
```

### 23.3. Update Many Records

```java
new com.mongodb.client.model.UpdateManyModel<>(
    Filters.and(
        Filters.eq("tenantId", "T-01"),
        Filters.eq("status", "PENDING")
    ),
    Updates.set("needsReview", true)
);
```

`updateMany` can touch huge numbers of documents; validate filters carefully before running.

### 23.4. Replace

```java
new com.mongodb.client.model.ReplaceOneModel<>(
    Filters.eq("_id", "ORD-3001"),
    new Document("_id", "ORD-3001")
        .append("tenantId", "T-01")
        .append("status", "PAID")
        .append("amountCents", 100000L)
);
```

`replaceOne` overwrites the whole document per replace semantics rather than `$set`ting individual fields. Fields omitted from the replacement document are deleted.

### 23.5. Delete Many

```java
new com.mongodb.client.model.DeleteManyModel<>(
    Filters.and(
        Filters.eq("tenantId", "T-01"),
        Filters.eq("archived", true)
    )
);
```

Never run an empty delete filter in production unless explicitly approved and controlled.

## 24. `upsert(true)` and Idempotency

An upsert acts as:

- Matching document exists → update/replace;
- No matching document → insert per operation semantics.

Example:

```java
import com.mongodb.client.model.UpdateOneModel;
import com.mongodb.client.model.UpdateOptions;

WriteModel<Document> operation =
    new UpdateOneModel<>(
        Filters.eq("_id", "T-01:C-105"),
        Updates.combine(
            Updates.set("tenantId", "T-01"),
            Updates.set("customerId", "C-105"),
            Updates.set("grossCents", 349900L)
        ),
        new UpdateOptions().upsert(true)
    );
```

Re-running with identical values converges to the exact same final state. This is an **idempotent update** when business semantics and inputs stay constant.

### 24.1. `$inc` Is Not Idempotent Under Manual Retries

Do not blindly retry:

```java
new UpdateOneModel<>(
    Filters.eq("_id", "COUNTER-1"),
    Updates.inc("count", 1)
);
```

If the write succeeded on the server yet the client timed out before receiving the ACK, re-sending it as a new job attempt increments `count` a second time.

The driver supports retryable writes for eligible single-document operations using session/transaction identifiers within protocol rules. **Application-level retries outside that mechanism do not preserve the same write identity**, and multi-update operations also have different rules.

### 24.2. Designing Unique Keys for Summary Records

When materializing `customerRevenue`, you might build:

```text
_id = tenantId + ":" + customerId + ":" + period
```

If components might contain delimiters, use a structured compound key or unambiguous encoding:

```java
Document id = new Document("tenantId", "T-01")
    .append("customerId", "C-105")
    .append("period", "2026-11");
```

MongoDB allows `_id` to be a BSON document, provided field order and serialization stay consistent. Upsert keys must encode full business identity so tenants never collide.

## 25. Interpreting `BulkWriteResult`

After a successful `bulkWrite()`:

```java
BulkWriteResult result = collection.bulkWrite(
    writes,
    new BulkWriteOptions().ordered(false)
);
```

Key accessors:

| API | Meaning |
|---|---|
| `wasAcknowledged()` | Whether write concern required acknowledgment |
| `getInsertedCount()` | Documents inserted via insert models |
| `getMatchedCount()` | Documents matched by updates/replacements |
| `getModifiedCount()` | Documents actually modified (when supported) |
| `getDeletedCount()` | Documents deleted |
| `getUpserts()` | List of upsert insertions |

### 25.1. Matched Differs from Modified

Suppose:

```text
Current document status = "PAID"
UpdateOne: set status = "PAID"
```

Result:

```text
matchedCount = 1
modifiedCount = 0
```

This is normal—the document already held the target value.

### 25.2. Upsert Count Differs from `getInsertedCount()`

An `UpdateOneModel` with `upsert(true)` can insert a new document. That insertion appears in `getUpserts()`, not necessarily in `getInsertedCount()`, which counts insert models.

### 25.3. Unacknowledged Writes

With unacknowledged write concerns, several counters are unavailable or meaningless. For critical ETL, use an appropriate write concern—never disable acknowledgment just to inflate benchmark throughput.

## 26. Handling `MongoBulkWriteException`

A bulk call can **partially succeed** before throwing an exception.

```java
import com.mongodb.MongoBulkWriteException;
import com.mongodb.bulk.BulkWriteError;
import com.mongodb.bulk.BulkWriteResult;

try {
    BulkWriteResult result = collection.bulkWrite(
        writes,
        new BulkWriteOptions().ordered(false)
    );

    recordSuccess(result);

} catch (MongoBulkWriteException ex) {
    BulkWriteResult partial = ex.getWriteResult();

    if (partial != null && partial.wasAcknowledged()) {
        recordPartialCounts(partial);
    }

    for (BulkWriteError error : ex.getWriteErrors()) {
        int requestIndex = error.getIndex();
        int errorCode = error.getCode();

        // Log only approved metadata.
        recordFailure(requestIndex, errorCode);
    }

    if (ex.getWriteConcernError() != null) {
        recordWriteConcernProblem(
            ex.getWriteConcernError().getCode()
        );
    }

    throw ex; // Let the job framework decide retry/reconciliation.
}
```

`recordSuccess`, `recordPartialCounts`, `recordFailure`, and `recordWriteConcernProblem` are application hooks you implement; the snippet illustrates error-handling structure.

### 26.1. Which Operation Does an Error Index Refer To?

`BulkWriteError.getIndex()` identifies the operation's position in the submitted write list per driver semantics. To retry a subset, preserve a parallel mapping from index to business/job ID when assembling the batch.

Never just log `"bulk error 11000"` without tracking which record failed, especially in large ETL jobs.

### 26.2. Partial Success Is Normal in Unordered Bulks

An unordered bulk might produce:

```text
Requested: 500
Succeeded: 490
Failed due duplicate key: 8
Failed due schema validation: 2
```

If the job blindly retries all 500 operations, safety depends on idempotency. `InsertOneModel` items whose `_id` already succeeded will fail with duplicate key errors; `$inc` items would apply twice.

### 26.3. `writeConcernError` Differs from Write Errors

- **Write error:** a specific write model was rejected (e.g., duplicate key or schema validation).
- **Write concern error:** writes did not satisfy the requested replication/acknowledgment policy, even though changes may already have been applied.

On write concern or network timeouts, **never assume nothing was written**. Inspect target state by business key or reconcile idempotently.

### 26.4. Never Swallow Exceptions and Report Success

Wrong:

```java
try {
    collection.bulkWrite(writes);
} catch (Exception ignored) {
    // Job continues and reports completed.
}
```

Such a job silently drops thousands of records. Categorize errors, store failed IDs/retry metadata, and exit with an accurate status.

## 27. Size Limits on Bulk Operations

An oversized `List<WriteModel>` can:

- Consume excessive heap before sending;
- Slow down batch construction;
- Increase the blast radius of a large failure;
- Make retry/reconciliation costly;
- Hit server BSON, wire message, or write batch size limits.

The MongoDB driver automatically splits operations into protocol batches respecting `maxWriteBatchSize`, `maxBsonObjectSize`, and `maxMessageSizeBytes` where supported. **Never assume passing 1 million operations to `bulkWrite()` sends a single network command.**

### 27.1. Bounding Batches in the Application

Example starting parameters:

```text
Read cursor batchSize: 250
Write operation buffer: 400
Maximum buffer memory: monitored
```

There is no magic rule for 400. Use smaller batches for large documents; for tiny documents over high-RTT networks, test larger batches carefully.

### 27.2. Batch Size Impacts Tail Latency

Very large batches cut round trips but increase:

- Latency until a batch is acknowledged;
- Records needing reconciliation on failure;
- Peak heap;
- Lock/write contention;
- Worker hold time.

Optimize for both throughput **and** p95/p99 latency, not records/sec alone.

## 28. Example: Chunked `bulkWrite` in Batches of 400 Operations

A basic helper:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.BulkWriteOptions;
import com.mongodb.client.model.WriteModel;
import org.bson.Document;

import java.util.ArrayList;
import java.util.List;

public final class BulkBuffer {
    private final MongoCollection<Document> collection;
    private final int maxOperations;
    private final List<WriteModel<Document>> pending =
        new ArrayList<>();

    public BulkBuffer(
        MongoCollection<Document> collection,
        int maxOperations
    ) {
        if (maxOperations <= 0) {
            throw new IllegalArgumentException("maxOperations must be positive");
        }
        this.collection = collection;
        this.maxOperations = maxOperations;
    }

    public void add(WriteModel<Document> operation) {
        pending.add(operation);

        if (pending.size() >= maxOperations) {
            flush();
        }
    }

    public void flush() {
        if (pending.isEmpty()) {
            return;
        }

        collection.bulkWrite(
            pending,
            new BulkWriteOptions().ordered(false)
        );

        // Clear only after receiving write-concern acknowledgement.
        pending.clear();
    }
}
```

In production, add:

- Business ID tracking per write model;
- Partial write failure handling;
- Retry/reconciliation logic;
- Metrics;
- Error classification;
- Backoff/cancellation;
- Thread confinement or synchronization (never share this unsynchronized buffer across threads);
- Byte-size caps in addition to operation counts.

### 28.1. Why Clear Only After Success?

Clearing before `bulkWrite` loses the entire pending list if the call fails. Yet on **partial success**, blindly keeping and retrying the whole list is also insufficient—track per-operation status and enforce idempotency.

### 28.2. Final `flush()` at Job End Is Mandatory

If 1,050 operations arrive with max batch 400:

```text
Batch 1: 400
Batch 2: 400
Final buffer: 250
```

Forgetting `flush()` at the end **silently drops the remaining 250 operations**.

## 29. Combining Aggregation, Cursors, and `bulkWrite`

Combined task: read orders for a tenant and date range, reshape them in Java, and upsert them into `orderExports`.

To keep things clear, the example maps **independent** source documents without `$group` so each source record produces one target write.

### 29.1. Target Design

Source record:

```javascript
{
  _id: "ORD-1001",
  tenantId: "T-01",
  customerId: "C-105",
  status: "PAID",
  amountCents: NumberLong("249900")
}
```

Target `orderExports`:

```javascript
{
  _id: {
    tenantId: "T-01",
    orderId: "ORD-1001"
  },
  customerId: "C-105",
  status: "PAID",
  amountCents: NumberLong("249900")
}
```

Using a composite `_id` of `tenantId + orderId` prevents colliding business IDs across tenants.

### 29.2. Pipeline Fetching Only Required Fields

```java
import static com.mongodb.client.model.Aggregates.*;
import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Projections.*;

List<Bson> pipeline = Arrays.asList(
    match(and(
        eq("tenantId", "T-01"),
        eq("status", "PAID")
    )),
    project(fields(
        include("_id", "tenantId", "customerId",
                "status", "amountCents")
    ))
);
```

Avoid `into(new ArrayList<>())` when source collections are large.

### 29.3. Mapping a Source Document to a Write Model

```java
import com.mongodb.client.model.ReplaceOneModel;
import com.mongodb.client.model.ReplaceOptions;
import com.mongodb.client.model.WriteModel;
import com.mongodb.client.model.Filters;

import org.bson.Document;

static WriteModel<Document> toExportWrite(Document src) {
    String orderId = src.getString("_id");
    String tenantId = src.getString("tenantId");

    Document targetId = new Document("tenantId", tenantId)
        .append("orderId", orderId);

    Document replacement = new Document("_id", targetId)
        .append("customerId", src.getString("customerId"))
        .append("status", src.getString("status"))
        .append("amountCents", src.get("amountCents"));

    return new ReplaceOneModel<>(
        Filters.eq("_id", targetId),
        replacement,
        new ReplaceOptions().upsert(true)
    );
}
```

Advantage: given the same source record, re-running produces the **same target state**, unlike `$inc`.

However, if the source record updates mid-job, an older scan read could **overwrite newer data** in the target. That is the source-revision problem addressed next.

### 29.4. Complete Job at the API Level

```java
import com.mongodb.client.AggregateIterable;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;

import com.mongodb.client.model.BulkWriteOptions;
import com.mongodb.client.model.WriteModel;

import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

static long exportOrders(
    MongoCollection<Document> source,
    MongoCollection<Document> target,
    List<Bson> pipeline
) {
    final int readBatchSize = 250;
    final int writeBatchSize = 400;

    long processed = 0;
    List<WriteModel<Document>> pending =
        new ArrayList<>(writeBatchSize);

    AggregateIterable<Document> iterable = source.aggregate(pipeline)
        .batchSize(readBatchSize)
        .maxTime(60, TimeUnit.SECONDS);

    try (MongoCursor<Document> cursor = iterable.iterator()) {
        while (cursor.hasNext()) {
            Document src = cursor.next();

            pending.add(toExportWrite(src));
            processed++;

            if (pending.size() >= writeBatchSize) {
                target.bulkWrite(
                    pending,
                    new BulkWriteOptions().ordered(false)
                );
                pending.clear();
            }
        }
    }

    if (!pending.isEmpty()) {
        target.bulkWrite(
            pending,
            new BulkWriteOptions().ordered(false)
        );
        pending.clear();
    }

    return processed;
}
```

This function demonstrates **streaming reads + batched writes**. It does not yet provide job-wide transactions, durable checkpoints, partial-failure recovery, or change capture—all essential for reliably resumable production ETL.

### 29.5. Why Not Call `bulkWrite` for Every Single Record?

Wrapping one element in a `List` and calling `bulkWrite` inside every loop iteration forfeits batching efficiency. Keep buffers sized to your workload without letting them grow unboundedly.

### 29.6. Do You Need Two `MongoClient` Instances?

Usually you can share **one `MongoClient`** if source and target live in the same deployment and security context. Separate deployments require separate clients and connection strings. Never create a new client per batch.

## 30. Consistency Pitfall: Reading While Source Data Mutates

Suppose an ETL runs:

```text
T1: Cursor reads ORD-1001, sourceRevision=7
T2: User updates ORD-1001 to revision=8
T3: Another worker exports revision=8 to target
T4: Stale ETL bulk-replaces revision=7 into target
```

The target ends up overwritten with stale data.

### 30.1. Simple Approach: Dataset Snapshot

If business rules allow, run ETL against a consistent snapshot or a source dataset frozen during processing.

Pros: simpler semantics. Cons: requires appropriate snapshot storage, timing, and mechanisms.

Never assume simply passing `readConcern("majority")` across multiple read calls creates a job-wide snapshot.

### 30.2. Alternative: Source Revisions and Guarded Writes

Persist:

```javascript
{
  _id: "ORD-1001",
  sourceRevision: 8
}
```

Store the revision on the target as well so stale jobs never overwrite newer target revisions.

Logic:

```text
If target revision < source revision:
    allow update
Else:
    skip as stale or duplicate
```

A guarded update must **embed the condition inside the atomic write operation** and handle upserts/unique keys properly—never read target revision in Java and decide afterward, as another worker can write in between.

### 30.3. Concurrent Upsert Challenges

If the target document does not yet exist, two workers can race to upsert simultaneously. Enforce stable unique keys and duplicate-key reconciliation. Poorly designed version-conditional filters can trigger duplicate-key errors or conflicts.

For complex pipelines, consider transactional outboxes, versioned staging collections, `$merge` with appropriate semantics, or change streams for catch-up.

### 30.4. Deletes Must Also Propagate

A batch scan only sees existing documents; if a source document is deleted mid-job or post-export, the target does not delete itself automatically.

You need:

- Tombstones;
- Change stream delete events;
- Full key-set reconciliation;
- Aligned TTL/retention policies.

Never declare a target an exact mirror simply because all visible source documents were upserted.

## 31. Cursors and Checkpoints: `batchSize` Does Not Enable Resume

A job processing 2 million records can crash at 1.2 million:

```text
Processed: 1,200,000
JVM crash
Cursor lost
```

Upon restart, the old `MongoCursor` is gone and is not a durable checkpoint. Persist:

- Job ID;
- Source range/watermark;
- Last **committed** target identifier;
- Pipeline/transform version;
- Retry count;
- Error records;
- Snapshot/revision context;
- Start/end timestamps.

### 31.1. Keyset Pagination for Stable Scans

Scanning ordered by `_id`:

```javascript
db.orders.find({
  tenantId: "T-01",
  _id: { $gt: lastCommittedId }
})
.sort({ _id: 1 })
.limit(500);
```

Requires a supporting index, such as (depending on workload):

```javascript
db.orders.createIndex({
  tenantId: 1,
  _id: 1
});
```

This is not a full snapshot. Newly inserted documents with `_id` below the watermark or concurrent updates/deletes during the scan may be missed without a catch-up mechanism.

### 31.2. Java `find` with Keyset

```java
import com.mongodb.client.FindIterable;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;

String tenantId = "T-01";
String lastCommittedId = "ORD-1000";

FindIterable<Document> page = orders.find(
    Filters.and(
        Filters.eq("tenantId", tenantId),
        Filters.gt("_id", lastCommittedId)
    )
)
.sort(Sorts.ascending("_id"))
.limit(500)
.batchSize(100);
```

`limit(500)` defines the **logical page**; `batchSize(100)` tunes network fetching within that page.

### 31.3. When Should You Record a Checkpoint?

**Only after confirming** the corresponding writes succeeded per write concern and reconciliation logic. Advancing the watermark beforehand causes lost records if `bulkWrite` fails.

On partial batch success, never advance the checkpoint past failed items without tracking failed IDs.

### 31.4. Never Use Offset `skip` as a Checkpoint on Mutable Datasets

If records are inserted or deleted while paginating:

```text
Page 1: skip 0, limit 500
Page 2: skip 500, limit 500
```

items will be duplicated or skipped. Keyset pagination and change capture fit large jobs better, while still requiring consistency design.

## 32. `aggregate` + `bulkWrite`: Group Results Then Persist

Another pattern is **aggregating totals per customer** and materializing `customerRevenue`.

Pipeline:

```java
List<Bson> pipeline = Arrays.asList(
    Aggregates.match(
        Filters.and(
            Filters.eq("tenantId", "T-01"),
            Filters.eq("status", "PAID")
        )
    ),

    Aggregates.group(
        "$customerId",
        Accumulators.sum("grossCents", "$amountCents"),
        Accumulators.sum("orderCount", 1)
    )
);
```

Sample group output:

```javascript
{
  _id: "C-105",
  grossCents: NumberLong("349900"),
  orderCount: 2
}
```

Convert to `UpdateOneModel`:

```java
static WriteModel<Document> toRevenueWrite(
    String tenantId,
    Document grouped
) {
    String customerId = grouped.getString("_id");

    Document targetId = new Document("tenantId", tenantId)
        .append("customerId", customerId);

    return new UpdateOneModel<>(
        Filters.eq("_id", targetId),
        Updates.combine(
            Updates.set("tenantId", tenantId),
            Updates.set("customerId", customerId),
            Updates.set("grossCents", grouped.get("grossCents")),
            Updates.set("orderCount", grouped.get("orderCount")),
            Updates.currentDate("computedAt")
        ),
        new UpdateOptions().upsert(true)
    );
}
```

This **overwrites the full group total**, rather than adding deltas. Given unchanged inputs/snapshots and logic, re-running converges to the same state.

### 32.1. Source Updates Between Runs

If source documents change after the aggregation reads them, the target becomes temporarily stale. Compute groups against a `snapshotTime` or track `computedAt`/`sourceWatermark` followed by catch-up runs.

### 32.2. Completely Disappearing Groups

If a customer no longer has any `PAID` orders, the new pipeline **emits no group row**, leaving the old summary stale in the target. Reconcile and remove stale keys or use tombstones.

This is a classic materialized-view bug that `upsert(true)` alone cannot solve.

### 32.3. Using `$merge` Instead

If all computation happens inside MongoDB without Java transformations, `$merge` reduces network and JVM overhead. You still must handle missing groups, consistency, permissions, and failure semantics.

## 33. Bulk Operations Are Not Transactions

An ordered bulk:

```text
Update A → committed
Update B → committed
Update C → failed
Update D → never executed
```

There is no automatic rollback of A or B when C fails.

### 33.1. Single-Document Atomicity

MongoDB guarantees atomicity for writes on **a single document** per supported semantics, not across multiple `WriteModel` operations spanning different documents.

When A, B, and C must all succeed or all roll back together, use a **multi-document transaction** where supported by your deployment.

### 33.2. Transactions Are Not Free

Transactions carry overhead:

- Holding snapshots and locks/resources;
- Coordination overhead;
- Retries on transient errors;
- Timeouts;
- Write conflicts;
- Version/config size and duration caps.

Never wrap a 50-million-record migration in **one giant transaction** just for simple atomicity reasoning.

### 33.3. Session + Bulk Example

```java
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;

try (ClientSession session = client.startSession()) {
    session.startTransaction();

    try {
        collection.bulkWrite(
            session,
            writes,
            new BulkWriteOptions().ordered(true)
        );

        session.commitTransaction();
    } catch (Exception ex) {
        session.abortTransaction();
        throw ex;
    }
}
```

This is an **illustrative skeleton**, omitting retry handling for transaction commit errors and transient error labels. Standard helpers like `withTransaction` or driver transaction callbacks are normally preferable when implemented properly.

Verify topology support, session lifecycle, and write concerns. Transactions never make external API calls atomic with the database.

## 34. Read Concern and Write Concern

Two frequently confused concepts:

- **Write concern:** acknowledgment/durability guarantees required from the server/replica set.
- **Read concern:** isolation/consistency guarantees for reads where supported.

Setting `majority` write concern on a collection:

```java
import com.mongodb.WriteConcern;

MongoCollection<Document> durableWrites =
    collection.withWriteConcern(WriteConcern.MAJORITY);
```

### 34.1. `MAJORITY` Is Not Idempotency

If a client submits the same `$inc` twice as independent requests and both satisfy `majority`, the counter increments twice. Majority governs durability acknowledgment, not business retry deduplication.

### 34.2. `readConcern("majority")` Is Not a Job-Wide Snapshot

Reading 1 million rows across multiple calls/phases while source data mutates does not yield a single point-in-time snapshot. True snapshot consistency requires snapshot read concern/transactions or snapshot backups compatible with your MongoDB version, topology, and runtime duration.

### 34.3. Lowering Write Concern Is Not a Safe Throughput Fix

Weakening write concern can reduce wait time at the expense of durability guarantees. Choose write concerns based on RPO and business requirements, never to inflate benchmark scores.

## 35. Retryable Writes and Ambiguous Outcomes

Consider this failure mode:

```text
T1: Client sends bulk update
T2: Server applies write
T3: Network drops before ACK reaches client
T4: Client times out
```

The client **cannot tell** whether the write succeeded.

### 35.1. Do Not Equate Driver Retryable Writes with Manual Retries

Driver retryable writes apply only to **eligible operations** under specific server, session, and transaction conditions. Bulks containing multi-document operations like `updateMany` or `deleteMany` have different retryability rules. Never assume "`retryWrites=true` makes every bulk safe to retry."

Manual application retry loops generate new request identities and can duplicate side effects even when initial protocol-level driver retries were safe.

### 35.2. Mitigating Risk

- Use stable operation IDs and business keys.
- Upsert by unique key where appropriate.
- Prefer `$set`/replace to final state over non-idempotent `$inc` on replay.
- Use optimistic version guards.
- Reconcile target state by `_id` after timeouts.
- Never retry validation or authorization errors infinitely.
- Enforce retry budgets and exponential backoff with jitter.
- Log job ID, batch ID, model indexes, errors, and commit checkpoints.

### 35.3. Errors That Should Not Be Retried Infinitely

| Category | Handling |
|---|---|
| Business duplicate key | Validate, skip, or resolve conflict |
| Schema validation error | Fix input data or mapping |
| Unauthorized | Fix roles/credentials |
| Invalid BSON / type / dimension | Fix input |
| Rate limit / transient network | Bounded retry |
| Write concern timeout | Verify target state before retrying |
| Primary stepdown | Driver retries/resumes where eligible |
| Disk full | Halt job, fix capacity |
| Wrong collection/tenant | Stop immediately and investigate security |

## 36. Bulks and Uniqueness Constraints

Upserting by business key requires a supporting unique index where appropriate.

Example revenue collection:

```javascript
{
  _id: {
    tenantId: "T-01",
    customerId: "C-105"
  },
  grossCents: NumberLong("349900")
}
```

MongoDB enforces uniqueness on `_id` within the collection. If stored as separate fields instead:

```javascript
{
  tenantId: "T-01",
  customerId: "C-105"
}
```

add a unique compound index:

```javascript
db.customerRevenue.createIndex(
  { tenantId: 1, customerId: 1 },
  { unique: true }
);
```

Under concurrent upserts, two workers seeing no existing record can collide with a duplicate key error. Do not assume duplicate key always means lost data; re-read and resolve using idempotent semantics.

### 36.1. Avoid Unordered Bulks That Delete and Upsert the Same Key

If a bulk deletes and upserts the same document and depends on sequence, unordered execution produces nondeterministic results. Split into phases or use ordered/transactional logic with clear semantics.

### 36.2. Multiple Operations Targeting the Same `_id` in One Batch

Avoid emitting duplicate operations for the same target key unintentionally. Deduplicate in Java by business key before building the bulk, or merge changes into one update.

## 37. Security and Tenant Isolation in Aggregations and Bulks

In a multi-tenant system, this query:

```java
orders.aggregate(
    Arrays.asList(
        Aggregates.match(
            Filters.eq("status", "PAID")
        )
    )
);
```

reads orders across **all tenants** in a shared collection—a severe security vulnerability if the caller is scoped to one tenant.

### 37.1. Source Tenant Identity from Trusted Context

```java
String tenantId = trustedAuthContext.getTenantId();
```

`trustedAuthContext` is provided by backend auth/authz middleware, never taken blindly from frontend inputs.

Pipeline:

```java
Aggregates.match(
    Filters.and(
        Filters.eq("tenantId", tenantId),
        Filters.eq("status", "PAID")
    )
);
```

### 37.2. Bulk Updates Need Tenant Scope Too

Avoid:

```java
Filters.eq("_id", orderId)
```

when `_id` alone does not guarantee tenant isolation in your data model/authz rules. In shared collections:

```java
Filters.and(
    Filters.eq("_id", orderId),
    Filters.eq("tenantId", tenantId)
)
```

For upserts, validate that both the business key and inserted fields bind the verified `tenantId`, preventing callers from writing into another tenant.

### 37.3. Never Log Raw Documents

Pipeline or bulk errors may contain sensitive field names, values, or command payloads. Log only:

```text
traceId
jobId
tenant scope (per policy)
operationType
requestIndex
errorCode
batchSize
duration
```

Never log passwords, MongoDB URIs, document bodies/PII, raw query vectors, or tokens unless explicitly authorized by policy.

## 38. Observability for Aggregations and Bulks

An ETL/batch job should emit metrics across three layers:

### 38.1. Read Path

- Aggregation duration;
- Rows yielded;
- `getMore` frequency;
- Read batch counts/latency;
- Server operation latency;
- Query plan/scan efficiency;
- Disk spills;
- Cursor errors;
- Heap usage and GC pauses;
- Source lag.

### 38.2. Write Path

- Bulk calls;
- Models attempted;
- Inserted/matched/modified/deleted/upsert counts;
- Partial failures;
- Duplicate key counts;
- Write concern errors;
- Retry counts;
- Write p95/p99 latency;
- Batch bytes/operations;
- Target storage/replication lag.

### 38.3. Business and Completeness

- Eligible source documents;
- Processed documents;
- Last committed watermark;
- Target documents/current revisions;
- Failed/rejected records;
- Reconciliation delta;
- Last successful job run;
- RPO/freshness targets.

### 38.4. Distinguish "Processed" from "Committed"

If the cursor read 10,000 rows while `bulkWrite` committed 9,600, dashboards must report:

```text
rowsRead = 10000
rowsAttemptedToWrite = 10000
rowsAcknowledgedOrReconciled = 9600
rowsPendingOrFailed = 400
```

Never use a single `processed` counter as proof that all data was persisted.

## 39. Memory and Throughput Tuning

Several parameters must be tuned together:

```text
readBatchSize
writeBatchSize
maxBufferedBytes
workerConcurrency
MongoClient maxPoolSize
serverSelectionTimeout
maxTimeMS / application deadline
writeConcern
```

### 39.1. Small Batches

Pros:

- Low memory footprint;
- Simpler partial retry;
- Smaller blast radius on errors.

Cons:

- More network round trips;
- Higher per-bulk overhead;
- Lower throughput under high network latency.

### 39.2. Large Batches

Pros:

- Fewer network round trips;
- Higher throughput for small documents when server has headroom.

Cons:

- High peak heap;
- Complex partial failure recovery;
- Higher per-batch latency;
- Bursty server load;
- Potential GC pauses.

### 39.3. Concurrency

Running 20 parallel workers each buffering 1,000 docs means:

```text
Up to 20,000 pending write models
+ Current read batches
+ Decoded BSON objects
+ Network buffers
+ Driver pools
```

Bound total memory and concurrent writes across all workers—not just per worker.

### 39.4. Little's Law and Concurrent Operations

General relationship:

\[
L \approx \lambda W
\]

In steady state:

- \(L\): average operations in flight/waiting;
- \(\lambda\): throughput (operations/second);
- \(W\): average time in the system (seconds).

At 200 write ops/s averaging 0.05 s each, average concurrency is ~10. This is not an exact `maxPoolSize` formula—account for bursts, batching, server selection, query mix, and tail latency.

## 40. Performance Benchmarking Scenarios

Build a representative staging dataset; never benchmark unapproved against production.

### 40.1. Trial Matrix

| Trial | Read Batch | Write Batch | Workers |
|---|---:|---:|---:|
| A | 100 | 100 | 1 |
| B | 250 | 400 | 1 |
| C | 500 | 1000 | 1 |
| D | 250 | 400 | 4 |
| E | 500 | 1000 | 8 |

### 40.2. Metrics to Capture

- Total job duration;
- Documents/second;
- Read/network bytes;
- Bulk p95/p99;
- Peak heap;
- GC pauses;
- CPU/disk/cache;
- Connection pool waits;
- Replication lag;
- Errors/retries;
- Target data integrity.

### 40.3. Do Not Pick Purely on Peak Throughput

If Trial D hits 30,000 docs/s and Trial E hits 32,000 docs/s while quadrupling heap usage and degrading production API p99, D is the safer choice.

### 40.4. Applying Backpressure

Pipeline architecture:

```text
Cursor reader (1 thread)
       │
       ▼
Bounded queue (max 1000 records)
       │
       ▼
Transform workers (limited)
       │
       ▼
Bounded write buffers
       │
       ▼
bulkWrite
```

When the queue fills, the reader **slows down** rather than pulling unbounded records until OOM. Handle cancellation and shutdown cleanly so records are never dropped while reporting job completion.

## 41. Reading in Batches with `find()` Instead of Aggregation

When no server-side grouping or reshaping is needed, `find()` is simpler:

```java
import com.mongodb.client.FindIterable;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;

FindIterable<Document> iterable = orders.find(
    Filters.eq("tenantId", "T-01")
)
.projection(
    Projections.include("_id", "customerId", "amountCents")
)
.sort(Sorts.ascending("_id"))
.batchSize(300);

try (MongoCursor<Document> cursor = iterable.iterator()) {
    while (cursor.hasNext()) {
        Document order = cursor.next();
        process(order);
    }
}
```

### 41.1. Similarities Between `FindIterable` and `AggregateIterable`

Both support cursor iteration and `batchSize`, avoiding materializing entire result sets in the JVM.

### 41.2. Differences

- `find()` focuses on document retrieval with filters, projections, and sorts.
- `aggregate()` supports transformations, grouping, joins, facets, and multi-stage pipelines.
- Available options differ.
- Server cost varies by query/pipeline shape.

Never force a complex aggregation when `find()` suffices, and never pull huge datasets into Java just to group what MongoDB can aggregate efficiently in a pipeline.

## 42. Is a Cursor Loop the Same as API Pagination?

Not quite.

An API may expose:

```text
GET /orders?pageSize=20&cursor=...
```

A Java MongoDB cursor is a short-lived server/client resource for sequential reading. Never expose internal `MongoCursor` state directly as a frontend pagination token.

### 42.1. Stable API Pagination

Include:

- Stable sort keys;
- A unique tie-breaker like `_id`;
- Bounded page limits;
- Backend-issued cursor tokens;
- Tenant/auth scope validation;
- Token signing/integrity checks if needed;
- Handling for concurrent mutations between pages.

### 42.2. Large `skip()` Offsets Are Costly

Example:

```java
orders.find(Filters.eq("tenantId", "T-01"))
    .sort(Sorts.ascending("_id"))
    .skip(500_000)
    .limit(20);
```

The server must traverse and discard 500,000 entries before returning the page. Keyset pagination scales far better for large collections.

### 42.3. Never Treat `batchSize()` as Public `pageSize`

Setting `batchSize(500)` on a 2-million-row cursor does not mean a client receives 500 items and keeps the cursor alive across HTTP requests. Design API pagination with explicit stateless cursors, lifetimes, and security bounds.

## 43. Watch-Outs When Using Java POJOs Instead of `Document`

You can define:

```java
public class Order {
    private String id;
    private String tenantId;
    private String customerId;
    private long amountCents;

    // Public no-arg constructor, getters/setters,
    // mapping annotations or codec conventions per configuration.
}
```

And use `MongoCollection<Order>` once codecs/registries are configured.

### 43.1. Aggregation Output Differs from Source Entity Type

Source `Order` holds order fields, whereas `$group` outputs:

```javascript
{
  _id: "C-105",
  grossCents: NumberLong("349900"),
  orderCount: 2
}
```

You cannot decode `$group` output into `Order` because the shapes differ.

Options:

```java
AggregateIterable<Document> rows =
    orders.aggregate(pipeline, Document.class);
```

or a dedicated output DTO with matching codecs/mappings.

### 43.2. Semantic Output DTOs

```java
public class RevenueRow {
    private String id;
    private long grossCents;
    private long orderCount;

    // Constructors/getters/setters per codec.
}
```

Verify `_id` mapping and accumulator output types. For `Decimal128`, use a matching decimal type rather than casting to `long`.

### 43.3. Never Cast Monetary Types Blindly

If source amounts use `NumberDecimal`, `$sum` outputs `Decimal128`. Calling:

```java
Long gross = row.getLong("grossCents");
```

fails with a type mismatch. Read via `get()` with controlled conversion or use proper codecs/DTOs.

## 44. Aggregations with `$facet`: Memory Considerations

`$facet` runs multiple sub-pipelines over the same input stream:

```javascript
db.orders.aggregate([
  { $match: { tenantId: "T-01" } },
  {
    $facet: {
      byStatus: [
        { $group: { _id: "$status", count: { $sum: 1 } } }
      ],
      recent: [
        { $sort: { createdAt: -1 } },
        { $limit: 10 }
      ]
    }
  }
]);
```

Output is typically a single document containing multiple array branches. It is subject to MongoDB version/stage memory and BSON size limits; setting `batchSize(100)` cannot shrink an oversized single `$facet` output document.

### 44.1. Batch Size Cannot Split a Single Oversized BSON Document

If one output document exceeds the BSON document limit, lowering `batchSize` changes nothing. Redesign the pipeline to emit smaller per-record outputs or separate queries.

### 44.2. When to Split into Separate Queries?

When branches need different indexes or cause memory bottlenecks, running two targeted queries is often faster and safer than one `$facet`. Benchmark against realistic data.

## 45. `$sort`, `$group`, `$limit`, and Pipeline Ordering

Compare two pipelines:

```text
A: $match → $sort → $limit → $group
B: $match → $group → $sort → $limit
```

They are **not equivalent**.

A groups a truncated subset. B groups all documents matching `$match`, then picks the top groups.

For "top customers by revenue," you normally need B (or an equivalent semantic variant). Never move `$limit` earlier purely for speed if it breaks business logic.

### 45.1. Push `$match` as Early as Semantics Permit

Early filtering shrinks input to `$group`/`$sort` and enables index usage.

### 45.2. Never Project Away Fields Needed by Later Stages

If `$project` drops `amountCents` before `$group`, totals become zero/incorrect. Trim fields only **after auditing downstream stage dependencies**.

### 45.3. Sorting Before Grouping Differs from Sorting After Grouping

Sorting by `createdAt` before `$group` does not keep group outputs sorted by revenue. Each stage reshapes the stream.

## 46. Handling Exceptions While Iterating a Cursor

A cursor can fail during `hasNext()` or `next()`:

```java
try (MongoCursor<Document> cursor =
         orders.aggregate(pipeline).iterator()) {

    while (cursor.hasNext()) {
        Document row = cursor.next();
        process(row);
    }

} catch (com.mongodb.MongoException ex) {
    // Record errorCode/category, traceId, jobId.
    // Decide retry/resume based on checkpoint and idempotency.
    throw ex;
}
```

Possible failures:

- Server selection or connection loss;
- Network timeouts;
- Cursor killed or expired;
- Operation exceeded time limit (`maxTimeMS`);
- Primary failover;
- Authorization errors;
- Decoding/codec exceptions.

### 46.1. Failing Mid-Stream Is Not "Nothing Happened"

If 10,000 rows were processed before the cursor failed, the app may already have written corresponding outputs. Never retry the entire job without idempotency.

### 46.2. Never Hold a Cursor Open Across User Think Time

Never open a cursor in an HTTP request and try to keep it alive for hours until the user clicks "Next." Use stateless API pagination tokens and keyset queries.

## 47. `getMore` and Operational Metrics

With small batch sizes or large result sets, the driver issues more `getMore` commands.

Monitor:

```text
aggregate command duration
getMore command count
getMore duration
total cursor lifetime
rows returned
rows/sec
bytes received
```

The Java Driver's `CommandListener` observes commands by name (e.g., `aggregate`, `getMore`; `bulkWrite` appears as the underlying write commands depending on driver/server). Never assume every bulk executes under a literal command named `"bulkWrite"` across all versions.

### 47.1. Are Many `getMore` Calls an Error?

No. They are normal cursor protocol behavior. Optimize only when round-trip overhead, RTT, or latency hurts throughput.

### 47.2. Never Print Raw Command Bodies

Command payloads may contain PII, tenant data, or update values. Restrict logging/tracing to safe metadata.

## 48. Java Command Monitoring

A lightweight listener:

```java
import com.mongodb.event.CommandListener;
import com.mongodb.event.CommandSucceededEvent;
import com.mongodb.event.CommandFailedEvent;
import com.mongodb.event.CommandStartedEvent;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.LongAdder;

public final class SafeCommandMetrics
        implements CommandListener {

    private final LongAdder successes = new LongAdder();
    private final LongAdder failures = new LongAdder();
    private final LongAdder totalMicros = new LongAdder();

    @Override
    public void commandStarted(CommandStartedEvent event) {
        // Never log event.getCommand(), as it may contain sensitive data.
    }

    @Override
    public void commandSucceeded(CommandSucceededEvent event) {
        successes.increment();
        totalMicros.add(
            event.getElapsedTime(TimeUnit.MICROSECONDS)
        );
    }

    @Override
    public void commandFailed(CommandFailedEvent event) {
        failures.increment();
        totalMicros.add(
            event.getElapsedTime(TimeUnit.MICROSECONDS)
        );
    }

    public long getSuccesses() {
        return successes.sum();
    }

    public long getFailures() {
        return failures.sum();
    }
}
```

Register with `MongoClientSettings`:

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

String uri = System.getenv("MONGODB_URI");

SafeCommandMetrics metrics = new SafeCommandMetrics();

MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .addCommandListener(metrics)
    .build();

MongoClient client = MongoClients.create(settings);
```

In production, export histograms to a metrics backend rather than summing everything into one counter, and break down `aggregate`, `getMore`, writes, and command failures.

## 49. Connection Pools and Concurrency

The MongoDB Java Sync Driver manages connection pools per server/topology.

If a batch job opens dozens of cursors and runs many parallel bulks:

- Pool checkout wait rises;
- Active connections rise;
- Server CPU/I/O rises;
- App heap and thread counts rise;
- Live API traffic can degrade.

### 49.1. One Shared `MongoClient`

Never instantiate a `MongoClient` per 400 writes; that causes connection/TLS/auth overhead and pool churn.

### 49.2. Bound Worker Concurrency

Architecture option:

```text
One shared MongoClient
    │
    ├── ETL worker A
    ├── ETL worker B
    ├── ETL worker C
    └── Web API (isolate priority workloads if needed)
```

If ETL shares a cluster with critical user APIs, enforce throttling or maintenance windows to protect user-facing latency.

### 49.3. Never Raise `maxPoolSize` Indefinitely

A larger pool may lower JVM checkout waits briefly while pushing excessive concurrent load into MongoDB, worsening server saturation. Balance with load tests and metrics.

## 50. Persisting Aggregation Results: Java Bulk vs. `$merge`?

| Criterion | Cursor + Java `bulkWrite` | Server-Side `$merge` |
|---|---|---|
| Custom Java logic | Flexible | Limited to aggregation expressions |
| Server-to-app network traffic | Proportional to output | Typically much lower |
| JVM memory | Needs buffers and transforms | No result buffering in Java |
| Per-write-model control | Explicit | Governed by `$merge` options |
| Idempotency | Application-designed | Key and merge-semantics designed |
| External service calls | Easy to integrate | Not directly supported |
| Error/retry orchestration | Application-handled | Aggregation/write semantics |
| Writing multiple collections | Can target separate collections | `$merge` targets one collection per pipeline |
| Whole-job transaction | Not automatic | Not automatic |
| Checkpoint/restart | Built by application | Requires rerun/reconciliation strategy |

Do not assume `$merge` and `bulkWrite` are always interchangeable—they behave differently under concurrent source mutations and pre-existing target records.

## 51. Managing the Full Job as a State Machine

A production ETL job needs explicit states:

```text
PENDING
   │
   ▼
RUNNING
   │
   ├── source cursor
   ├── transform
   ├── bulk write
   └── checkpoint
   │
   ├── success → COMPLETED
   ├── transient error → RETRYING
   ├── permanent error → FAILED
   └── cancellation → CANCELLED
```

Example job metadata:

```javascript
{
  _id: "JOB-20261114-001",
  pipelineVersion: "v3",
  tenantId: "T-01",
  sourceCollection: "orders",
  targetCollection: "orderExports",
  state: "RUNNING",
  lastCommittedId: "ORD-4500",
  rowsRead: NumberLong("4500"),
  rowsAcknowledged: NumberLong("4400"),
  failures: 0,
  startedAt: ISODate("2026-11-14T03:00:00Z")
}
```

This is a structural model, not an automatic exactly-once guarantee.

### 51.1. Leases and Preventing Duplicate Runs

With multiple scheduler instances, two jobs could scan and write the target concurrently. Use job leases/ownership or strictly idempotent, concurrency-safe designs. Custom distributed locks must support expiration and renewal; never treat `status: RUNNING` alone as a safe lock.

### 51.2. Pipeline Versioning

If transformation logic changes, a checkpoint from pipeline `v1` may be incompatible with `v2`. Persist `pipelineVersion` to decide whether to resume or rebuild.

### 51.3. Source Mutates After Job Completion

If the source continues receiving writes, completing a historical scan does not keep the target up to date. Pair with change streams, CDC/outbox, or periodic reconciliation.

## 52. Common Mistakes

| Mistake | Consequence | Right Approach |
|---|---|---|
| Creating `aggregate()` iterable without iterating | Pipeline never executes | Consume the iterable |
| `into(new ArrayList<>())` on millions of rows | OOM / heavy JVM GC | Stream with cursor |
| Treating `batchSize` like `limit` | Returns far more data than expected | Use `$limit` or `limit()` |
| Assuming every batch has exact size N | Broken processing logic | Process record-by-record |
| Failing to close cursors | Leaks server/client resources | `try-with-resources` |
| Treating Sync Driver as non-blocking | Blocks caller threads on I/O | Size threads or use Reactive where appropriate |
| Treating `allowDiskUse(true)` as free optimization | Disk spills remain costly | Review indexes, query plans, resources |
| Placing `$limit` before `$group` for top revenue | Wrong business results | Preserve pipeline semantics |
| Passing millions of write models into one bulk | OOM, painful retries | Chunk into bounded batches |
| Forgetting final buffer `flush()` | Drops trailing records | Flush after loop |
| Clearing buffer before `bulkWrite` | Data loss on error | Clear only after success |
| Assuming `bulkWrite` is atomic across the batch | Unexpected partial writes | Use transactions or idempotency |
| Using unordered bulk for order-dependent writes | Nondeterministic state | Use ordered or redesign |
| Retrying `$inc` blindly after timeout | Double increment | Reconcile / enforce idempotency |
| Assuming errors mean "nothing was written" | Corrupt state | Inspect partial results / verify |
| Checking only `getInsertedCount` | Misses upserts and matched updates | Inspect all relevant counters |
| Using unacknowledged writes for ETL | No write result visibility | Use appropriate write concern |
| Target key missing tenant ID | Cross-tenant corruption | Compound business keys |
| Checkpointing before commit | Skipped records on crash | Checkpoint after verification |
| Scanning changing data with `skip` | Duplicates / skipped records | Keyset + CDC/reconciliation |
| Treating `majority` read concern as a job snapshot | Non-point-in-time reads | Use snapshot/capture design |
| Upserting without handling deletes | Stale target records | Tombstones / reconciliation |
| Materialized view leaving stale deleted groups | Outdated summaries | Full key reconciliation |
| Tracking only read rows, not committed writes | False job success | Track both sides |
| Creating `MongoClient` per batch | Connection churn | Shared client |
| Logging raw queries/URIs | Leaks secrets/PII | Redact logs |
| Unbounded worker concurrency | Overloads DB and pools | Enforce backpressure |
| Testing only with 100 records | Hides memory/perf bottlenecks | Load-test realistically |
| Decoding `$group` output with source POJO | Mapping failures | Use matching DTO or `Document` |

## 53. Practice Exercises

### Exercise 1 — Aggregation Builders

From `orders`, write a Java pipeline using `Aggregates` and `Filters`:

- Filter `tenantId = T-01`;
- Status `PAID` only;
- Date within November 2026;
- Group by `customerId`;
- Sum `amountCents` and count orders;
- Sort descending by total;
- Return top 20.

Explain the ordering of `$match`, `$group`, `$sort`, and `$limit`.

### Exercise 2 — `Document` vs. Builders

Write the same pipeline in both styles. Compare:

1. Readability;
2. Support for brand-new stages;
3. Reusability;
4. Risk of field-name typos;
5. Validating user inputs.

### Exercise 3 — `batchSize` vs. `limit`

A pipeline yields 10,000 documents with `.batchSize(200)`.

1. Does it return only 200 documents?
2. Approximate number of batches?
3. Why might actual batch sizes not equal 200?
4. What must be added if you only want 200 total results?
5. If a single document exceeds the BSON size limit, does shrinking `batchSize` help?

### Exercise 4 — Cursor Lifecycle

Write Java code that:

- Uses `MongoCursor<Document>`;
- Reads at most 1,000 records;
- Stops early on a business condition;
- Closes the cursor;
- Catches `MongoException`;
- Records metrics safely.

### Exercise 5 — Memory

An aggregation returns 2 million rows averaging 2 KiB each.

1. Why can `into(ArrayList)` cause OOM?
2. Roughly how large is the logical payload?
3. How does Java object overhead increase actual heap usage?
4. How do you choose a read batch size?
5. How do projections shrink network and heap overhead?

### Exercise 6 — Ordered vs. Unordered

A bulk has five operations, and the third violates a unique index.

1. What happens under `ordered(true)`?
2. What can happen under `ordered(false)`?
3. Is the batch atomic?
4. When must `ordered(false)` never be used?
5. Can you safely retry the entire list blindly?

### Exercise 7 — `BulkWriteResult`

A bulk returns:

```text
insertedCount = 100
matchedCount = 200
modifiedCount = 170
deletedCount = 20
upserts = 15
```

1. Why does `matched` differ from `modified`?
2. Are `upserts` counted inside `insertedCount`?
3. Under unacknowledged writes, which metrics become unreliable?
4. Which metrics should be logged after a partial failure?

### Exercise 8 — Retrying `$inc`

An update incrementing `totalRevenue` by 100,000 cents times out after the server may already have committed.

1. What is the risk of manual retry?
2. Why can `$set` to a final state be safer?
3. What business idempotency key is needed?
4. Does `majority` write concern solve this by itself?
5. Outline a reconciliation approach.

### Exercise 9 — Full Batch Flush

Using a write buffer of 400 and 1,050 input records:

1. How many full batches execute?
2. How many trailing records remain?
3. When is `flush()` called?
4. If the final batch fails, what should the checkpoint reflect?
5. If the job crashes right after ACK before saving the checkpoint, how do you resume safely?

### Exercise 10 — `MongoBulkWriteException`

Design a handler that:

- Reads `getWriteErrors`;
- Maps `getIndex` back to business IDs;
- Categorizes duplicate key vs. validation vs. transient errors;
- Captures partial results;
- Handles `WriteConcernError`;
- Writes failed items to dead-letter storage;
- Never logs raw PII.

### Exercise 11 — ETL and Source Mutations

One worker reads source revision 7, while another worker writes target revision 8 before the first finishes.

1. What is the stale-overwrite risk?
2. Is check-then-update in Java atomic?
3. Design a version guard.
4. What unique key is needed?
5. If the source is deleted, how should the target handle it?

### Exercise 12 — Checkpoints

A job scans 100,000 records in bulks of 500.

1. When should `lastCommittedId` be checkpointed?
2. What if a batch partially succeeds?
3. Why does a cursor not automatically persist a resume position?
4. Compare offset vs. keyset pagination.
5. What if a new record is inserted with an `_id` smaller than the watermark?

### Exercise 13 — `$merge` vs. Java Bulk

For computing revenue per customer:

1. When should you pick `$merge`?
2. When is Java logic required?
3. Which minimizes network transfer?
4. How do you handle groups that disappear?
5. Is either approach atomic across all output documents?

### Exercise 14 — Transactions

Two writes must succeed together: updating an order and inserting a payment record.

1. Is `bulkWrite` enough?
2. When do you need a multi-document transaction?
3. How is `ClientSession` lifecycle managed?
4. How are commit retries handled?
5. Why shouldn't you put 5 million operations inside one transaction?

### Exercise 15 — Performance Benchmark

Compare 3 configurations:

```text
A: readBatchSize=100, writeBatchSize=100, workers=1
B: readBatchSize=250, writeBatchSize=400, workers=2
C: readBatchSize=500, writeBatchSize=1000, workers=8
```

Measure:

- Throughput;
- Heap/GC;
- Command/`getMore` counts;
- Bulk p95;
- Server CPU/disk/replication lag;
- Retries/errors;
- Impact on live API p99.

Pick the best config against SLOs rather than raw rows/sec.

### Exercise 16 — Multi-Tenant Security

An API exports orders for tenant A.

1. Where must the tenant predicate sit in the pipeline?
2. How should bulk target keys be structured?
3. Should users be allowed to pass an arbitrary `tenantId`?
4. Which fields belong in logs?
5. If `$lookup` joins `customers`, what access checks are required?

### Exercise 17 — POJO/DTO

Source `Order` stores `Decimal128` for `amount`, and an aggregation computes `$sum`.

1. Why might `getLong()` fail?
2. What DTO shape is needed?
3. How should codecs be configured?
4. How do you test round-trips and overflow?
5. Why doesn't aggregation output necessarily match the source schema?

### Exercise 18 — Incident Analysis

An ETL job's batch size was raised from 400 to 10,000 and workers from 2 to 32, followed by:

```text
Heap jumped 5x
Long GC pauses
Pool checkout timeouts
Rising replica lag
Bulk partial failures
```

You should:

1. Identify likely bottlenecks;
2. List metrics, logs, and traces to inspect;
3. Propose controlled load-shedding/throttling steps;
4. Design a config rollback;
5. Verify data completeness after the incident.

## 54. Production Checklist

### Aggregation

- [ ] Pipeline enforces business filters and tenant scope.
- [ ] `$match` pushed early wherever semantics allow.
- [ ] Indexes and query plans verified on representative data.
- [ ] No unexpected `COLLSCAN` on hot paths.
- [ ] `$group`, `$sort`, `$lookup`, and `$facet` memory/disk evaluated.
- [ ] `allowDiskUse` enabled only with understanding of spill costs.
- [ ] `maxTime` and deadlines configured.
- [ ] Sensitive raw data never logged.
- [ ] Result BSON types handled cleanly.
- [ ] Consistency strategy defined for mutating source data.

### Cursors and Batch Reading

- [ ] Cursor streaming used for large results.
- [ ] `into(List)` avoided on unbounded datasets.
- [ ] `batchSize` clearly distinguished from `limit`.
- [ ] `getMore` round trips accounted for.
- [ ] Cursors closed on completion and error.
- [ ] Backpressure/bounded queues enforced for parallel processing.
- [ ] Durable checkpoints persisted if job must resume.
- [ ] Checkpoints advanced only after write verification.
- [ ] Concurrent inserts/updates/deletes during scans handled.

### BulkWrite

- [ ] `ordered` chosen based on actual dependencies.
- [ ] Every batch bounded by operation count and memory.
- [ ] Trailing buffer flushed at job end.
- [ ] Partial write successes and errors handled.
- [ ] `BulkWriteResult` interpreted per write concern semantics.
- [ ] Upserts distinguished from matched/modified counts.
- [ ] Non-idempotent writes never retried blindly.
- [ ] Appropriate business keys and unique constraints in place.
- [ ] Retry budgets, dead-letter handling, and reconciliation implemented.
- [ ] `bulkWrite` never mistaken for an atomic transaction.
- [ ] Write concerns and timeouts match business requirements.
- [ ] Stale source reads never overwrite newer target revisions.

### Operations

- [ ] `MongoClient` shared across application lifecycle.
- [ ] Driver command and pool monitoring active.
- [ ] Read/write throughput, p95/p99, and error metrics tracked.
- [ ] Heap, GC, CPU, disk, and replication lag monitored.
- [ ] Load-tested with representative datasets and concurrency.
- [ ] Runbooks exist for stopping, resuming, and retrying jobs.
- [ ] Data completeness can be verified and reconciled.
- [ ] No passwords or PII in logs or public batch metadata.
- [ ] Clear owners, alerts, and incident response plans defined.

## 55. References

Always consult documentation for your **exact MongoDB Java Sync Driver and MongoDB Server versions**:

- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/)
- [Java Driver Aggregation](https://www.mongodb.com/docs/drivers/java/sync/current/aggregation/)
- [Java Driver Bulk Write Operations](https://www.mongodb.com/docs/drivers/java/sync/current/crud/bulk/)
- [Java Driver Read Operations](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/)
- [Java Driver Update Operations](https://www.mongodb.com/docs/drivers/java/sync/current/crud/update-documents/)
- [MongoDB Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/)
- [MongoDB Aggregation Stages](https://www.mongodb.com/docs/manual/reference/operator/aggregation/)
- [MongoDB `aggregate` Command](https://www.mongodb.com/docs/manual/reference/command/aggregate/)
- [MongoDB `getMore` Command](https://www.mongodb.com/docs/manual/reference/command/getMore/)
- [MongoDB `bulkWrite` Command](https://www.mongodb.com/docs/manual/reference/command/bulkWrite/)
- [MongoDB Bulk Write Operations](https://www.mongodb.com/docs/manual/core/bulk-write-operations/)
- [MongoDB Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/)
- [MongoDB Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [MongoDB Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Cursor Lifecycle](https://www.mongodb.com/docs/manual/core/cursors/)
- [MongoDB Java Driver Monitoring](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/monitoring/)
- [MongoDB Java Driver Connection Pools](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/connection-pools/)
- [MongoDB Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)

## Conclusion

In the MongoDB Java Sync Driver, **aggregation**, **cursors/batching**, and **`bulkWrite`** work together to process large data volumes while keeping resource usage and correctness under control.

**Aggregation** pushes filtering, grouping, computation, and joins close to the MongoDB server. Design pipelines around exact semantics, leverage indexes, and measure memory/disk costs. **`AggregateIterable`** executes only when consumed; for pipelines using `$merge` or `$out`, never instantiate the iterable without iterating it and assume writes happened.

**Cursors and `batchSize`** fetch results incrementally over the network instead of loading everything into the JVM heap. Yet `batchSize` neither limits total output nor guarantees exact batch sizes, checkpoints, or snapshot isolation. For large results, use `MongoCursor` inside `try-with-resources`, projections, timeouts, and bounded processing.

**`bulkWrite`** cuts round-trip overhead by batching write models with ordered or unordered semantics. However, **partial success is possible**, result counters distinguish inserts, matches, modifications, and upserts, and the batch is not a multi-document transaction. Safe retries demand unique business keys, idempotency, proper write concerns, partial error handling, and reconciliation—never re-run `$inc` blindly after an unverified timeout.

When combining all three into an ETL pipeline, success is measured by **verified data accuracy, safe resumability, tenant isolation, sustainable throughput, and p95/p99 latencies that preserve system SLOs**—not merely a fast read loop or a clean-looking bulk call.

**The sustainable engineering pattern is: filter early on the server, stream conservatively with cursors, write in bounded batches, and design failure handling and safe restarts before ever running in production.**
