# MongoCursor, Resource Release, and Processing Large Datasets in MongoDB Java Driver

## 1. Why Is MongoCursor Needed?

A Java service needs to read 10 million documents from the `orders` collection to export CSV, transform data, or sync to another system. A first approach might be:

```java
List<Document> all = collection.find()
    .into(new ArrayList<>());

for (Document document : all) {
    process(document);
}
```

This code **collects the entire result set into the Java heap**. It may work if the query only returns a few dozen or a few hundred records, but it is very dangerous when the count is unbounded:

- `OutOfMemoryError` when total objects exceed heap capacity.
- The garbage collector must track a huge number of long-lived objects.
- Long wait time for the entire query to finish before processing the first items.
- Hard to stop early or cancel a long-running task.
- Hard to handle errors when data changes or the connection drops mid-way.

**`MongoCursor<TResult>`** enables sequential iteration over results while the driver holds only **a portion** of the data in memory at any given time. Results are received from MongoDB in **batches**, and the application processes one document at a time.

```text
MongoDB: 10,000,000 documents
                |
           find/aggregate
                |
                v
      Server-side cursor
                |
      firstBatch (e.g. 101)
                |
                v
        Java MongoCursor
                |
       hasNext() / next()
                |
           batch ended?
                |
       getMore next batch
                |
             ...
                |
     exhausted or close()
```

However, a cursor **does not automatically make every program memory-safe**: code can still accumulate documents in a `List`, maintain an unbounded `Map`, or push documents into an unbounded queue. You need to combine cursors, bounded processing structures, and resource release policies.

> **Core principle:** the larger the dataset, the more you must control **cursor lifecycle, batch size, processing rate, and recovery from checkpoints**. Using `cursor()` alone is not enough.

---

## 2. What Is MongoCursor in the Java Sync Driver?

In the MongoDB Java Sync Driver, the interface resides at:

```java
com.mongodb.client.MongoCursor<TResult>
```

`TResult` is the output type returned by the driver: typically `Document`, a codec-mapped POJO, or an appropriate BSON type.

According to the modern driver API:

- `MongoCursor<TResult>` extends `Iterator<TResult>` and `Closeable` / `AutoCloseable`.
- `hasNext()` indicates whether a next element exists.
- `next()` retrieves the next element.
- `tryNext()` retrieves an element if available or returns `null` according to cursor semantics.
- `available()` returns the number of documents **locally available without blocking**, not the total document count.
- `close()` terminates the cursor and requests resource release.
- `getServerCursor()` can provide server-side cursor metadata if a handle is still active.
- The interface is marked **NotThreadSafe**, except that `close()` may be called concurrently with other methods to cancel a blocked cursor per the API contract.

### 2.1. MongoCursor Is Not a Collection

`MongoCollection<Document>` represents the collection and provides query operations. `MongoCursor<Document>` represents **one traversal of the results** of a query.

### 2.2. MongoCursor Is Not a Durable Iterator

An open cursor depends on the connection session, server-side cursor state, session, and topology. Never persist a cursor ID to a database and treat it as a checkpoint that can resume after a process restart or primary failover.

### 2.3. The Java Sync Driver Is Blocking

`hasNext()` may wait for `getMore` over the network; `next()` and codecs can consume CPU. Iterating with a cursor bounds memory, **but does not make calls non-blocking**. For non-blocking execution, use the Reactive Streams driver/API instead.

---

## 3. Preparing Java Examples

The code snippets use the Java MongoDB Sync Driver and assume a `MongoCollection<Document>` is initialized:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

String uri = System.getenv("MONGODB_URI");

try (MongoClient client = MongoClients.create(uri)) {
    MongoDatabase database = client.getDatabase("sales");
    MongoCollection<Document> orders =
        database.getCollection("orders");

    // Invoke processing examples here.
}
```

In real web applications or background workers, `MongoClient` is usually created **once for the application lifecycle** to leverage its connection pool, rather than opened and closed per request or per document.

**Lifecycle distinctions:**

| Object | Typical lifecycle |
| --- | --- |
| `MongoClient` | Long-lived, scoped to process/service |
| `MongoDatabase` / `MongoCollection` handle | Reusable |
| `FindIterable` / `AggregateIterable` | Configuration for a single query |
| `MongoCursor` | Single traversal, must be closed |
| `ClientSession` | Explicit operation/session scope |
| `BufferedWriter` / `OutputStream` | Single export file or HTTP response |

If using POJOs instead of `Document`, ensure the codec registry and data mapping are compatible; cursor cleanup rules remain unchanged.

---

## 4. How FindIterable Differs from MongoCursor

```java
import com.mongodb.client.FindIterable;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import org.bson.Document;

FindIterable<Document> iterable =
    orders.find(Filters.eq("status", "PAID"))
        .batchSize(500)
        .limit(10_000);

// Terminal operation creates the cursor and initiates the query.
try (MongoCursor<Document> cursor = iterable.cursor()) {
    while (cursor.hasNext()) {
        Document order = cursor.next();
        process(order);
    }
}
```

`FindIterable` allows configuring:

- `filter` via `find(...)`.
- `sort(...)`, `projection(...)`.
- `limit(...)` and `skip(...)`.
- `batchSize(...)`.
- `maxTime(...)`, `noCursorTimeout(...)`.
- Other options depending on API/driver version.

Calling `find(...)` and chaining options builds a query descriptor object; **terminal** operations such as `first()`, `into(...)`, `cursor()`/`iterator()`, or beginning iteration actually execute the query accordingly.

### 4.1. `cursor()` and `iterator()` Methods

Both appear in Java driver documentation to start iteration. When you want a resource with clear ownership that works cleanly with `try-with-resources`, be consistent and use `cursor()`:

```java
try (MongoCursor<Document> cursor =
         orders.find().cursor()) {
    // ...
}
```

### 4.2. Do Not Initialize Cursors Too Early

If you create a cursor and then wait for a user file upload or a slow external API call, the server-side state may time out. Initialize the cursor only right before you are ready to start consuming it.

---

## 5. Standard Pattern: try-with-resources

This is the recommended pattern for queries returning multiple documents:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import org.bson.Document;

public final class OrderReader {

    public static void consume(
            MongoCollection<Document> orders
    ) {
        try (MongoCursor<Document> cursor =
                 orders.find(
                     Filters.eq("status", "READY")
                 ).cursor()) {

            while (cursor.hasNext()) {
                Document order = cursor.next();
                process(order);
            }
        }
    }

    private static void process(Document order) {
        System.out.println(order.get("_id"));
    }
}
```

### 5.1. Why Must You Close It?

An unfinished cursor can retain server-side state, session bindings, network buffers, and associated driver resources. Calling `close()` explicitly requests resource release instead of waiting for timeouts.

### 5.2. When Does Java Automatically Call `close()`?

With `try-with-resources`, Java closes the cursor upon leaving the block scope, even when:

- The loop reads all documents.
- A `break` is hit.
- A `return` executes inside the block.
- `process()` throws an exception.
- `hasNext()` or `next()` throws an exception.
- Internal logic cancels according to designed control flow.

### 5.3. Does an Exhausted Cursor Close Automatically?

MongoDB releases the server-side cursor once exhausted. However, real-world code may stop early, so `try-with-resources` remains the safest choice.

### 5.4. Do Not Ignore Errors

Closing a cursor does not mean the task succeeded. If CSV export fails at the 500,000th document, mark the job failed or partial rather than returning `COMPLETED`.

---

## 6. Why Enhanced for-each Is Risky

Java allows:

```java
for (Document order : orders.find()) {
    process(order);
}
```

This is concise, but driver documentation warns: if an exception occurs or the loop exits early, the cursor **may not be closed proactively**.

Example:

```java
for (Document order : orders.find()) {
    if (isTarget(order)) {
        break;
    }
}
```

There is no cursor variable available to call `close()` inside `finally`.

### 6.1. Rewriting It Safely

```java
try (MongoCursor<Document> cursor =
         orders.find().cursor()) {
    while (cursor.hasNext()) {
        Document order = cursor.next();
        if (isTarget(order)) {
            break;
        }
    }
}
```

### 6.2. Can You Use the Iterable's `forEach`?

Yes:

```java
orders.find().forEach(order -> process(order));
```

However, when you need early termination, cancellation, checkpointing, output streams, or fine-grained exception handling, an explicit `MongoCursor` gives clearer lifecycle management.

---

## 7. Closing Cursors on Early `return`

Example finding the first document violating a rule:

```java
public Document findFirstInvalid(
        MongoCollection<Document> orders
) {
    try (MongoCursor<Document> cursor =
             orders.find().cursor()) {

        while (cursor.hasNext()) {
            Document order = cursor.next();

            if (isInvalid(order)) {
                return order;
            }
        }
        return null;
    }
}
```

Even though `return` is inside `try`, Java still closes the resource before the method returns.

### 7.1. Should You Use `first()`?

If your condition only requires querying for a single record, `first()` is usually cleaner:

```java
Document order = orders.find(
    Filters.eq("_id", orderId)
).first();
```

Use an explicit cursor when you genuinely need to inspect multiple documents or process them as a stream.

---

## 8. The `firstBatch` and `getMore` Mechanism

MongoDB does not send millions of result documents in a single network response.

```text
Java find()
    |
    v
Server executes find
    |
    v
First batch + cursor ID
    |
    v
Java consumes documents in first batch
    |
    v
Has more server-side results?
   | yes
   v
getMore(cursor ID)
    |
    v
Next batch
    |
    v
Repeat until exhausted/close
```

### 8.1. Batch Limits per MongoDB Documentation

For standard `find` commands:

- The default first batch is up to **101 documents or about 16 MiB**, whichever limit is reached first.
- Subsequent batches are fetched via `getMore`.
- When no batch size is specified, subsequent batches are capped at roughly **16 MiB**.
- When a batch size is set, the server may return fewer documents than requested due to byte limits or reaching the final batch.
- An individual BSON document still obeys the 16 MiB limit independently.

### 8.2. Cursor ID Is a Temporary Server Resource

If a query is not yet exhausted, the server may return a non-zero cursor ID. If all results fit in one batch, the server may not need to keep a cursor open.

Do not use a cursor ID as a document ID, version, public pagination token, or post-restart checkpoint.

### 8.3. Batching Does Not Create an Immutable Snapshot

Multiple `getMore` calls can occur while other writers insert, update, or delete documents. An ordinary cursor does not implicitly guarantee that all batches reflect the database state at a single point in time.

---

## 9. Tuning `batchSize`

```java
try (MongoCursor<Document> cursor =
         orders.find(
             Filters.eq("status", "READY")
         )
         .batchSize(500)
         .cursor()) {

    while (cursor.hasNext()) {
        process(cursor.next());
    }
}
```

`batchSize(500)` requests **up to roughly 500 documents per batch**, still subject to byte limits and server conditions.

**It does not mean the query only returns 500 documents total.** To cap the total at 500:

```java
orders.find(filter)
    .limit(500);
```

### 9.1. Small Batches

May be suitable when:

- Documents are large, with many arrays or strings.
- Processing each record is slow.
- Many cursors run concurrently.
- Fast initial client response is needed.
- You want to avoid holding a large local batch buffer.

The trade-off is potentially more `getMore` calls and network round trips.

### 9.2. Large Batches

Can help reduce network round trips when:

- Documents are small.
- The processing pipeline is fast.
- Network latency is high.
- Memory headroom is available.
- High throughput is required.

However, it can increase batch buffer/GC pressure and extend processing duration before the next `getMore`.

### 9.3. No Single Optimal Batch Size for All Workloads

Test meaningful sizes like 100, 250, 500, and 1000 while measuring document throughput, heap usage, GC behavior, `getMore` latency, and impact on concurrent queries.

---

## 10. Distinguishing `limit`, `batchSize`, `skip`, and `into`

| Operation | Purpose |
| --- | --- |
| `limit(100)` | Caps the **total** number of result documents |
| `batchSize(100)` | Adjusts **documents per batch** |
| `skip(100)` | Skips the first 100 matching documents |
| `first()` | Retrieves the first document or null |
| `into(list)` | Collects all results into the target collection |
| `countDocuments(filter)` | Counts documents matching the filter |
| `cursor()` | Obtains a `MongoCursor` for manual iteration |

OOM-prone example:

```java
List<Document> all = orders.find()
    .batchSize(100)
    .into(new ArrayList<>());
```

Even though fetched in batches of 100, all documents eventually end up inside `all`.

If you only need 100 records:

```java
List<Document> page = orders.find()
    .sort(Sorts.ascending("_id"))
    .limit(100)
    .into(new ArrayList<>());
```

For 100 results, using `into` can be reasonable. The danger is an **unbounded result set**, not `into()` itself being inherently wrong.

---

## 11. `available()` Is Local Buffer Count, Not Total Count

```java
try (MongoCursor<Document> cursor =
         orders.find().cursor()) {
    int immediatelyAvailable = cursor.available();
    System.out.println(immediatelyAvailable);
}
```

`available()` reports how many documents are currently buffered on the client **without waiting to read more from the server**.

It is NOT:

- Total documents matching the filter.
- Total documents in the collection.
- Documents guaranteed to remain on the server.
- A reliable indicator that the server cursor has been closed.

When a cursor is exhausted, `available()` is typically 0. Some implementations may still report locally buffered documents after early closure per API semantics; do not use `available()` to check closed state.

### 11.1. Common Mistake

```java
int total = orders.find().cursor().available();
```

Wrong semantically, and it also leaks an unclosed cursor.

### 11.2. When You Need a Count

```java
long total = orders.countDocuments(
    Filters.eq("status", "READY")
);
```

Keep in mind counting carries execution cost. A paginated API does not necessarily have to run an exact count on every request.

### 11.3. Do Not Use `available()` as the Loop Condition

Wrong:

```java
while (cursor.available() > 0) {
    process(cursor.next());
}
```

This can stop once the local batch finishes even if more data exists on the server. Use:

```java
while (cursor.hasNext()) {
    process(cursor.next());
}
```

---

## 12. `hasNext()`, `next()`, and `tryNext()`

### 12.1. hasNext()

```java
boolean has = cursor.hasNext();
```

Checks whether a next document exists. **May block** when requesting the next batch over the network.

### 12.2. next()

```java
Document next = cursor.next();
```

Returns the next document. If exhausted, calling it again throws `NoSuchElementException` per the iterator contract.

### 12.3. tryNext()

```java
Document maybe = cursor.tryNext();
```

A specialized method that can return `null` when no element is currently ready. Most useful when designing tailable cursors or change streams where "no new events yet" is an expected state.

### 12.4. Do Not Assume `null` Means Data Has Ended Forever

With tailable cursors or change streams, `tryNext() == null` does not necessarily mean the stream has terminated. Distinguish finite standard cursors from event-waiting cursors.

---

## 13. Large Datasets and Java Memory

Suppose an average decoded Java `Document` takes 12 KiB.

```text
1 document:          12 KiB
500 documents:     5.9 MiB
1 million docs:   11.4 GiB
10 million docs:   114 GiB
```

This is an illustrative calculation, not a fixed size for every document. Object overhead, strings, arrays, codec buffers, metadata, and garbage collection all change real memory usage.

### 13.1. Bounded Processing Model

```text
MongoCursor
    |
    v
Read one
    |
    v
Transform
    |
    v
Write to bounded sink
    |
    v
Discard reference
    |
    v
Read next
```

### 13.2. Unbounded Processing Model

```text
MongoCursor
    |
    v
Keep appending to ArrayList/HashMap
    |
    v
Millions of live objects
    |
    v
GC pressure / OOM
```

Using a cursor and then calling `buffer.add(cursor.next())` without bounds **does not protect the heap**.

---

## 14. Streaming Read Example with Filter, Sort, and Projection

Given a collection schema:

```javascript
{
  _id: ObjectId("691800000000000000000001"),
  tenantId: "T100",
  status: "PAID",
  customerId: "C100",
  totalMinor: 199000,
  createdAt: ISODate("2026-11-14T08:00:00Z")
}
```

Java:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

public final class OrderScan {

    public static void scan(
            MongoCollection<Document> orders,
            String tenantId
    ) {
        try (MongoCursor<Document> cursor =
                 orders.find(
                     Filters.eq("tenantId", tenantId)
                 )
                 .sort(Sorts.ascending("_id"))
                 .projection(
                     Projections.fields(
                         Projections.include(
                             "customerId",
                             "status",
                             "totalMinor",
                             "createdAt"
                         )
                     )
                 )
                 .batchSize(500)
                 .cursor()) {

            while (cursor.hasNext()) {
                Document order = cursor.next();
                process(order);
            }
        }
    }
}
```

**Why this helps:**

- `Filters.eq("tenantId", ...)` scopes strictly to the tenant.
- Sorting by `_id` gives deterministic ordering.
- Projection reduces fields transmitted to the client.
- Batch size 500 bounds expected documents per fetch.
- Cursor closes even if `process` fails.

Projection lowers network and decoding cost, though it does not automatically reduce physical disk reads proportionally on the server. To reduce document page reads, you need queries/indexes supporting covered queries or matching access patterns.

---

## 15. Queries and Indexes Remain Fundamental

Cursors reduce application memory but do not fix poor queries.

Example:

```java
collection.find(
    Filters.eq("status", "PENDING")
).sort(
    Sorts.descending("createdAt")
);
```

If the collection is large and lacks a suitable index, the server may read many pages and perform a blocking sort before returning the first batch.

A reference index:

```javascript
db.orders.createIndex({
  status: 1,
  createdAt: -1
});
```

If queries also filter by tenant:

```javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
```

Choose indexes based on query shapes, cardinality, and `explain`, rather than adding indexes indiscriminately.

### 15.1. Time to First Result

A cursor may open yet take seconds or minutes before returning the first document if the server performs heavy scans, sorts, or aggregations. `batchSize` does not turn an unindexed blocking sort into streaming execution.

### 15.2. Measuring with Explain

```javascript
db.orders.find({
  tenantId: "T100",
  status: "PAID"
}).sort({
  createdAt: -1
}).explain("executionStats");
```

Inspect `totalKeysExamined`, `totalDocsExamined`, `nReturned`, `IXSCAN`, `COLLSCAN`, `FETCH`, `SORT`, and version-specific execution stats.

---

## 16. Exporting 1 Million Records to CSV Without Collecting into a List

Example simple CSV exporter class:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.types.ObjectId;

import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Date;

public final class OrdersCsvExport {

    public static long export(
            MongoCollection<Document> orders,
            String tenantId,
            Path path
    ) throws IOException {

        long count = 0;

        try (BufferedWriter writer =
                 Files.newBufferedWriter(
                     path, StandardCharsets.UTF_8
                 );
             MongoCursor<Document> cursor =
                 orders.find(
                     Filters.eq("tenantId", tenantId)
                 )
                 .sort(Sorts.ascending("_id"))
                 .batchSize(500)
                 .cursor()) {

            writer.write(
                "id,customerId,status,totalMinor,createdAt"
            );
            writer.newLine();

            while (cursor.hasNext()) {
                Document d = cursor.next();

                ObjectId id = d.getObjectId("_id");
                String customer = d.getString("customerId");
                String status = d.getString("status");
                Object total = d.get("totalMinor");
                Date date = d.getDate("createdAt");

                writer.write(csv(id.toHexString()));
                writer.write(",");
                writer.write(csv(customer));
                writer.write(",");
                writer.write(csv(status));
                writer.write(",");
                writer.write(csv(
                    total == null ? "" : total.toString()
                ));
                writer.write(",");
                writer.write(csv(
                    date == null
                        ? ""
                        : date.toInstant().toString()
                ));
                writer.newLine();

                count++;

                if (count % 1000 == 0) {
                    writer.flush();
                }
            }
        }

        return count;
    }

    private static String csv(String value) {
        if (value == null) {
            return "";
        }
        return "\"" + value.replace("\"", "\"\"")
            + "\"";
    }
}
```

### 16.1. Application Memory

Memory is only needed for one driver batch, the writer buffer, and per-row logic—not for holding 1 million documents simultaneously.

### 16.2. Export Files Can Be Incomplete

If `getMore` fails at the 200,000th record, the output file already contains partial data. `try-with-resources` only guarantees closing resources—it does **not** mark the file complete.

A production workflow should:

1. Write to a temporary file.
2. Mark `COMPLETED` only after all records are exported.
3. Verify checksum/count when needed.
4. Perform an atomic rename/move when supported by the filesystem.
5. Clean up temp files on failure.
6. Enforce access controls and retention policies.

### 16.3. CSV Formula Injection

When opened in spreadsheet software, user-supplied strings starting with `=`, `+`, `-`, or `@` may be evaluated as formulas in some environments. CSV quoting alone does not prevent formula injection. Apply sanitization policies suited to output consumers, especially when exporting externally supplied data.

---

## 17. When the Output Is Slower Than MongoDB

Suppose MongoDB can fetch 40,000 documents/second while a downstream API only accepts 200 documents/second.

In a synchronous loop:

```java
while (cursor.hasNext()) {
    Document d = cursor.next();
    externalApi.send(d);
}
```

The thread waits for `externalApi.send` before calling `next` again. This provides control-flow backpressure, **but can keep the cursor open far too long**.

### 17.1. Risks

- A single batch takes tens of minutes to finish.
- Session idle timeout.
- External call hangs.
- Export cancellation fails to close the cursor if ownership is mishandled.
- Multiple jobs holding resources put pressure on connection pools or server state.

### 17.2. Better Design

- Moderate batch sizes.
- Downstream timeouts.
- Concurrency caps on running jobs.
- Bounded work queues.
- Splitting jobs into pages with checkpoints.
- Holding a cursor only within a short unit-of-work scope.
- Proper cancellation and cleanup.

---

## 18. Session and Cursor Timeouts

MongoDB enforces multiple lifetime layers:

| Mechanism | Role |
| --- | --- |
| `cursorTimeoutMillis` | Idle timeout for applicable server cursors, defaulting to around 10 minutes |
| `localLogicalSessionTimeoutMinutes` | Logical session idle timeout, defaulting to around 30 minutes |
| `noCursorTimeout(true)` | Requests bypassing standard cursor idle timeout |
| Driver/network timeouts | Controls I/O and server selection |
| `maxTime(...)` | Server-side execution time cap per API |
| Client-side operation timeout / CSOT | Client-enforced operation limit when configured and supported |
| Business deadline | Overall SLA for the export/backfill |

### 18.1. Session Idle Timeout Can Override `noCursorTimeout`

Drivers associate most operations with implicit or explicit sessions. MongoDB documentation notes that the server can expire an inactive session after **30 minutes by default**, closing associated cursors even if `noCursorTimeout` is set.

Example:

```text
10:00:  firstBatch received
10:01:  Java starts processing 500 documents
10:32:  session may have expired
10:35:  Java calls getMore
        -> cursor not found / session-related error
```

### 18.2. Do Not Enable `noCursorTimeout` for All Queries

```java
try (MongoCursor<Document> cursor =
         collection.find(filter)
             .noCursorTimeout(true)
             .batchSize(100)
             .cursor()) {

    while (cursor.hasNext()) {
        process(cursor.next());
    }
}
```

This option **does NOT**:

- Prevent restarts or primary elections.
- Prevent session timeouts.
- Prevent network failures.
- Replace calling `close()`.
- Provide resumability.
- Guarantee a long job will finish.

Use it only when specifically required and you understand resource leak risks.

---

## 19. Why Slow Batch Processing Causes Cursor Not Found

Suppose:

```text
batchSize = 500
Each document calls an external API taking 5 seconds

Batch processing time:
  500 × 5s = 2500s ≈ 41 minutes 40 seconds
```

The default session idle timeout may expire before Java requests the next batch.

Mitigations:

1. Reduce batch size.
2. Avoid performing very slow work inside the same cursor loop.
3. Use checkpoints to open a fresh query per page.
4. Consider explicit sessions/refresh only when truly necessary and permitted.
5. Monitor timeouts across both data source and downstream services.
6. Do not assume every cursor-not-found error is a driver bug.

### 19.1. Explicit Session Refresh

MongoDB documentation describes using an explicit session and calling `refreshSessions` periodically if a cursor may sit idle beyond limits. This is an advanced workflow requiring appropriate privileges and strict adherence to driver/session APIs—not a reason to design infinitely lived cursors.

For most background jobs, **reading a page, processing, checkpointing, and closing the cursor** recovers much more cleanly.

---

## 20. Sessions and Resource Closing Order

A cursor can be created within a `ClientSession`:

```java
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

public final class SessionRead {

    public static void run(
            MongoClient client,
            MongoCollection<Document> collection
    ) {
        try (ClientSession session = client.startSession();
             MongoCursor<Document> cursor =
                 collection.find(
                     session,
                     new Document()
                 ).cursor()) {

            while (cursor.hasNext()) {
                process(cursor.next());
            }
        }
    }
}
```

Java closes `try-with-resources` declarations in **reverse order**:

1. Cursor is closed.
2. Session is closed.

This is the right order because the cursor is bound to the session.

### 20.1. Do Not Share a Session Across Threads

`ClientSession` must not be shared concurrently across threads arbitrarily. Queries and sessions must belong to the same `MongoClient`; follow the driver contract.

### 20.2. Do Not Hold Transactions Open for Hours to Export Data

A long-running transaction retains snapshot/resource state, faces transaction lifetime limits, impacts concurrency, and may fail. If you need a consistent view of a large dataset, consider snapshot/backup mechanisms or compatible read concerns rather than opening multi-hour transactions by default.

---

## 21. Server `maxTime` and Client-Side Timeouts

Example:

```java
try (MongoCursor<Document> cursor =
         collection.find(filter)
             .maxTime(
                 30,
                 java.util.concurrent.TimeUnit.SECONDS
             )
             .cursor()) {
    while (cursor.hasNext()) {
        process(cursor.next());
    }
}
```

`maxTime` caps server-side execution time per MongoDB/driver version semantics. It **does not** abort a blocking `process()` method in Java or a third-party HTTP call.

### 21.1. CSOT and New Timeout Modes

Modern Java Sync Drivers support **Client-Side Operation Timeout (CSOT)**. When supported and configured with timeouts on the client/database/collection, available modes include:

- `TimeoutMode.CURSOR_LIFETIME`: a single deadline covering the entire lifetime from creation through exhaustion.
- `TimeoutMode.ITERATION`: a deadline per `hasNext`, `next`, or `tryNext` call, resetting on each iteration step.
- Tailable/Change Stream cursors use defaults suited to iteration mode.

Example strictly for driver versions exposing this API:

```java
import com.mongodb.TimeoutMode;

// Assumes CSOT is configured on client/collection.
try (MongoCursor<Document> cursor =
         collection.find()
             .timeoutMode(TimeoutMode.ITERATION)
             .cursor()) {

    while (cursor.hasNext()) {
        process(cursor.next());
    }
}
```

Do not call `timeoutMode` on older drivers or without understanding effective CSOT settings. Consult the Javadocs of your active dependency version.

### 21.2. Timeouts Do Not Automatically Make Retries Safe

If you already wrote part of a CSV or called an external API before timing out, retrying the entire job can produce duplicates. You still need checkpoints and idempotency.

---

## 22. Data Can Change While a Cursor Is Reading

Suppose a job starts reading at 10:00:

```text
10:00  cursor starts
10:01  fetch batch 1
10:02  users update or delete documents
10:03  fetch batch 2
10:04  writers insert new documents
10:05  fetch batch 3
```

Never assume all documents across batches represent a strict **point-in-time snapshot at 10:00**.

Depending on read concern, sort, index, and filter, concurrent writes can alter returned results or affect expected consistency.

### 22.1. Sorting Is Not a Snapshot

```java
collection.find()
    .sort(Sorts.ascending("_id"))
    .cursor();
```

Sorting orders iteration by key; it **does not** freeze the collection.

### 22.2. Need a Consistent Snapshot?

Consider:

- System-level snapshots or backups.
- Read concern and sessions with supported semantics.
- Immutable or append-only datasets.
- High-water mark with checkpoints.
- Change Streams to synchronize subsequent modifications.
- Quiescing writes or scheduling maintenance windows when business rules allow.

Do not open multi-hour transactions solely to achieve an "unchanging" export without evaluating resource limits.

---

## 23. Cursor ID Is Not a Durable Checkpoint

Never store:

```text
jobId=export-100
serverCursorId=12345678901234
```

expecting a process restart to resume from that cursor ID.

Because cursor IDs depend on server/session state, they can vanish on:

- Process restarts.
- Cursor idle timeouts.
- Session expiration.
- Primary elections.
- Network or topology changes.
- Server `killCursors`.
- Query exhaustion.

To resume large tasks, store a **logical checkpoint**, such as the last `_id` processed and confirmed successfully.

---

## 24. Keyset Pagination for Large Jobs

If documents have an `_id` key with stable ordering:

```text
Page 1:
  find _id > (none), sort _id asc, limit 500
  checkpoint lastId=A

Page 2:
  find _id > A, sort _id asc, limit 500
  checkpoint lastId=B

Page 3:
  find _id > B, ...
```

Each page uses a short-lived cursor that is closed promptly.

### 24.1. Java Example

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;
import org.bson.types.ObjectId;

public final class KeysetScanner {

    private static final int PAGE_SIZE = 500;

    public static ObjectId scanPage(
            MongoCollection<Document> collection,
            ObjectId lastProcessedId
    ) {
        Bson filter = lastProcessedId == null
            ? new Document()
            : Filters.gt("_id", lastProcessedId);

        ObjectId lastSuccessful = lastProcessedId;

        try (MongoCursor<Document> cursor =
                 collection.find(filter)
                     .sort(Sorts.ascending("_id"))
                     .limit(PAGE_SIZE)
                     .batchSize(100)
                     .cursor()) {

            while (cursor.hasNext()) {
                Document document = cursor.next();

                processIdempotently(document);

                lastSuccessful =
                    document.getObjectId("_id");
            }
        }

        return lastSuccessful;
    }

    private static void processIdempotently(
            Document document
    ) {
        // Persist result using an appropriate idempotency key.
    }
}
```

The caller saves the checkpoint once the page succeeds according to the sink's transaction/acknowledgement policy.

### 24.2. Not Automatically Exactly-Once

If the job processes document A successfully but crashes before persisting checkpoint A, the next run may reprocess A. **Downstream sinks must be idempotent**, or use transactions/outbox patterns if business logic requires exactly-once semantics.

### 24.3. `ObjectId` Is Not a Commit Timestamp

An `ObjectId` embeds a second-granularity timestamp and can be generated client-side. It does not strictly guarantee global commit order across clients or hosts. Keyset pagination over `_id` provides **key order**, not an exact global transaction log.

---

## 25. Why Large `skip` Values Can Be Slow

An easy pagination pattern to write:

```java
collection.find()
    .sort(Sorts.ascending("_id"))
    .skip(1_000_000)
    .limit(100)
    .into(new ArrayList<>());
```

At high offsets, the server still has to walk through many index entries or documents to reach the target position. Cost grows with offset across many query plans.

### 25.1. Comparison

| Approach | Strengths | Weaknesses |
| --- | --- | --- |
| `skip + limit` | Easy to jump to page N | Large offsets are expensive; concurrent writes cause drift |
| Keyset `_id > lastId` | Well suited for scanning and resuming | Cannot jump arbitrarily to page N |
| Single long-lived cursor | Simple code, high throughput when stable | Hard to resume after failures |
| Pages + durable checkpoint | Easy retries, bounded cursor lifetime | Requires application state |
| Partitioned scan | Parallel execution | Must split without gaps or overlaps |

### 25.2. Choosing by Use Case

- First 10–20 UI pages: offset pagination may suffice.
- Migrating millions of records: keyset + checkpointing is usually better.
- Consistent exports: may require complementary snapshot strategies.
- Event sync: Change Streams are often better than periodic scans when appropriate.

---

## 26. Keyset Pagination by `createdAt` and `_id`

When sorting only by `createdAt`, multiple documents can share the same timestamp; a deterministic tie-breaker is needed.

Suggested index:

```javascript
db.orders.createIndex({
  createdAt: 1,
  _id: 1
});
```

Next-page query:

```javascript
{
  $or: [
    { createdAt: { $gt: lastCreatedAt } },
    {
      createdAt: lastCreatedAt,
      _id: { $gt: lastId }
    }
  ]
}
```

Java:

```java
Bson nextPageFilter = Filters.or(
    Filters.gt("createdAt", lastCreatedAt),
    Filters.and(
        Filters.eq("createdAt", lastCreatedAt),
        Filters.gt("_id", lastId)
    )
);

try (MongoCursor<Document> cursor =
         orders.find(nextPageFilter)
             .sort(Sorts.ascending("createdAt", "_id"))
             .limit(500)
             .batchSize(100)
             .cursor()) {

    while (cursor.hasNext()) {
        process(cursor.next());
    }
}
```

**Important:** fields used for checkpointing should be immutable or follow strict mutation rules. If `createdAt` or the sort key is modified mid-scan, documents can be skipped or processed twice.

---

## 27. Retrying After Failure: Open a New Query from Checkpoint

Possible failures:

- Primary election.
- Connection reset.
- Server selection timeout.
- Cursor killed by session timeout.
- Downstream API returning 429 or 503.
- Schema error on a document.
- Java process restart.

Do not endlessly call `next()` on a broken cursor or try to reuse a server cursor ID.

### 27.1. Resilient Workflow

```text
START JOB
    |
    v
Load durable checkpoint
    |
    v
Open bounded page query
    |
    v
Read + apply idempotent effects
    |
    v
Persist checkpoint after acknowledgement
    |
    v
Close cursor
    |
    +--> More? next page
    |
    +--> Error? backoff and retry from checkpoint
    |
    v
COMPLETE
```

### 27.2. Never Checkpoint Before Downstream Writes Succeed

Wrong:

```text
Read 500 docs
Save lastId
Call external API
API failed
Restart skips those docs
```

Better:

```text
Read 500 docs
Apply operations with idempotency keys
Confirm successful outcome
Save lastId
```

A narrow window still exists between effect confirmation and checkpoint persistence, so **idempotency** protects against replaying partially completed work on retry.

---

## 28. Bounded-Memory Bulk Processing

To copy/transform many documents into another collection, batch writes with `bulkWrite`:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.ReplaceOneModel;
import com.mongodb.client.model.ReplaceOptions;
import com.mongodb.client.model.WriteModel;
import org.bson.Document;

import java.util.ArrayList;
import java.util.List;

public final class BulkMigration {

    public static long run(
            MongoCollection<Document> source,
            MongoCollection<Document> destination
    ) {
        final int WRITE_BATCH = 500;
        List<WriteModel<Document>> pending =
            new ArrayList<>(WRITE_BATCH);
        long processed = 0;

        try (MongoCursor<Document> cursor =
                 source.find()
                     .batchSize(500)
                     .cursor()) {

            while (cursor.hasNext()) {
                Document input = cursor.next();
                Document output = transform(input);

                pending.add(
                    new ReplaceOneModel<>(
                        Filters.eq("_id", output.get("_id")),
                        output,
                        new ReplaceOptions().upsert(true)
                    )
                );

                if (pending.size() >= WRITE_BATCH) {
                    destination.bulkWrite(pending);
                    processed += pending.size();
                    pending.clear();
                }
            }

            if (!pending.isEmpty()) {
                destination.bulkWrite(pending);
                processed += pending.size();
                pending.clear();
            }
        }

        return processed;
    }

    private static Document transform(Document src) {
        Document copy = new Document(src);
        copy.put("migrated", true);
        return copy;
    }
}
```

### 28.1. Why Upsert by `_id`?

If the same input is reprocessed, replacing/upserting by key prevents duplicate records as long as the transformation is **deterministic** and free of conflicting concurrent writes.

### 28.2. Do Not Assume Bulk Failures Roll Back Everything

A bulk batch can partially succeed before hitting an error. Depending on `ordered`/`unordered` behavior, the server stops or continues remaining operations. Inspect write errors and record checkpoints only for confirmed results.

### 28.3. Avoid Mutating the Filter Field on the Source While Scanning

If you scan `state: "PENDING"` and mutate `state` directly on the source during the scan, index traversal and query results can shift. Prefer immutable keys, paged queries, idempotent updates, or writing to a new destination collection per migration runbooks.

---

## 29. Parallel Processing: Never Share One Cursor Across Threads

`MongoCursor` is **not thread-safe**.

Wrong:

```java
executor.submit(() -> process(cursor.next()));
executor.submit(() -> process(cursor.next()));
```

Two workers calling `next()` on the same cursor simultaneously can trigger race conditions or violate the driver contract.

### 29.1. Producer–Consumer Pattern

```text
         MongoCursor
             |
    1 producer thread
             |
             v
       Bounded Queue
       capacity = 1000
             |
       +-----+-----+
       |     |     |
       v     v     v
      W1    W2    W3
       |     |     |
       +-----+-----+
             |
             v
     Downstream results
```

Only one thread reads the cursor; multiple worker threads process queued tasks.

### 29.2. Backpressure

When the bounded queue is full, the producer blocks or throttles. Never instantiate an unbounded `new LinkedBlockingQueue<>()` if input reaches millions of documents and downstream processing is slow.

### 29.3. Checkpointing with Parallel Workers

Never store the **highest `_id` finished** if lower `_id` items are still in flight. A restart would skip those unfinished lower items.

Instead:

- Track the contiguous committed prefix.
- Or checkpoint separately per partition.
- Or push tasks onto a durable queue with ack semantics.
- Maintain idempotency on retry.

---

## 30. Calling `close()` from Another Thread to Cancel a Cursor

The `MongoCursor` API makes one exception to `NotThreadSafe`: **`close()` may be called concurrently with other methods**, including to abort a blocking `hasNext()`/`next()` call.

Example:

```text
Worker:
  cursor.hasNext() waiting on getMore

Cancellation controller:
  cursor.close()

Worker:
  unblocks / receives exception / stops
```

### 30.1. Cancellation Design

- A single owner reads the cursor.
- The cancellation controller holds access to the active cursor to invoke `close()`.
- Never call `next()` from the cancelling thread.
- Workers and queues also shut down cleanly.
- Temporary outputs are closed and cleaned up.
- Mark the job `CANCELLED` instead of `COMPLETED`.

### 30.2. Do Not Rely on the Garbage Collector

GC has no deadline for releasing server resources. Use `try-with-resources` or explicit cleanup.

---

## 31. Tailable Cursors and `tryNext()`

**Tailable cursors** stream new documents appended to a **capped collection**. They differ from normal queries that read a finite result set.

```java
import com.mongodb.CursorType;
import com.mongodb.client.MongoCursor;
import java.util.concurrent.TimeUnit;

try (MongoCursor<Document> cursor =
         cappedCollection.find()
             .cursorType(CursorType.TailableAwait)
             .maxAwaitTime(2, TimeUnit.SECONDS)
             .cursor()) {

    while (!Thread.currentThread().isInterrupted()) {
        Document event = cursor.tryNext();

        if (event == null) {
            // Possibly no new document available on this poll attempt.
            continue;
        }

        process(event);
    }
}
```

### 31.1. How It Differs from an Ordinary Cursor

- The cursor waits for newly arriving documents.
- `null` from `tryNext` may simply mean no event has arrived yet.
- The cursor can lose its position if the capped collection wraps and overwrites old data.
- Application-level retry/resume loops may be needed.
- Requires explicit cancellation and sensible timeouts.
- Do not use on regular non-capped collections when capped semantics are required.

### 31.2. Watch Out for Busy-Spinning

If `tryNext()` returns `null` immediately without waiting under your configuration/mode, add backoff to avoid pegging CPU. Check your driver version for exact `awaitData`/`maxAwaitTime` behavior.

### 31.3. When to Use Change Streams Instead

If you need to react to inserts, updates, or deletes on regular collections or databases, **Change Streams** are usually a better fit. They expose resume tokens and rely on oplog retention; never substitute a cursor ID for a resume token.

---

## 32. Sessions and Cursors with Change Streams

Change Streams rely on long-lived cursors, typically returning `MongoChangeStreamCursor<TResult>` or the equivalent API.

Operational guidelines:

- Close the stream on service shutdown.
- Handle `tryNext()` returning no event cleanly.
- Monitor server errors and track resume tokens.
- Persist checkpoints/resume tokens **only after** downstream acknowledgement.
- Configure reasonable network/processing timeouts.
- Account for oplog retention windows and resume-point expiration.
- Never share the same cursor across multiple threads beyond API-permitted cancellation.

Keeping a Change Stream open for hours is normal; if an ordinary export cursor stays open for hours, consider splitting it into pages.

---

## 33. Sorting, Indexes, and Pagination Consistency

To traverse large datasets cleanly, ordering must be deterministic:

```java
collection.find(
    Filters.eq("tenantId", tenantId)
)
.sort(Sorts.ascending("createdAt", "_id"))
.batchSize(500);
```

Why add `_id` as a tie-breaker?

Two orders can share the exact same `createdAt`. Without a unique, stable trailing sort key, page boundaries can become inconsistent.

### 33.1. Sorting Alone Does Not Guard Against Concurrent Updates

If a sort field is modified during a scan, a document can shift position in the ordering. For multi-hour batch jobs, use immutable sort keys or snapshot/reconciliation mechanisms.

### 33.2. Indexes for Filter + Sort

```javascript
db.orders.createIndex({
  tenantId: 1,
  createdAt: 1,
  _id: 1
});
```

This is a query-shape illustration, not universal indexing advice for all systems.

---

## 34. Aggregations Must Also Close Cursors

```java
import com.mongodb.client.AggregateIterable;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Aggregates;
import com.mongodb.client.model.Accumulators;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.conversions.Bson;

List<Bson> pipeline = List.of(
    Aggregates.match(
        Filters.eq("tenantId", tenantId)
    ),
    Aggregates.group(
        "$status",
        Accumulators.sum("count", 1)
    )
);

AggregateIterable<Document> iterable =
    orders.aggregate(pipeline);

try (MongoCursor<Document> cursor =
         iterable.batchSize(100).cursor()) {
    while (cursor.hasNext()) {
        System.out.println(cursor.next().toJson());
    }
}
```

### 34.1. Batch Size Does Not Eliminate Aggregation Memory Usage

Stages like `$sort`, `$group`, and `$setWindowFields` may require intermediate memory or disk spills before emitting results. A cursor prevents the client from buffering the full output, **but does not turn blocking server stages into streaming ones**.

### 34.2. `allowDiskUse` Does Not Automatically Make Queries Faster

Where supported, `allowDiskUse` lets certain stages spill to disk to finish rather than failing on memory limits, which can actually slow down execution. Optimize `$match`, indexes, cardinality, and the execution plan first.

---

## 35. HTTP Streaming and Cursor Lifecycle

A large export endpoint may stream data directly:

```text
GET /api/exports/orders?tenantId=T100

HTTP response OutputStream
           ^
           |
       CSV writer
           ^
           |
      MongoCursor
           ^
           |
        MongoDB
```

### 35.1. When the Client Disconnects

`OutputStream.write` may throw an `IOException`. If both writer and cursor live inside `try-with-resources`, both resources close when exiting scope.

### 35.2. Once an HTTP Response Is Committed

After sending several megabytes of CSV, the server cannot replace already-transmitted payload bytes with a clean JSON error response. Define partial-download handling: abort the stream/connection, log the failure, and specify retry behavior per API contract.

### 35.3. Very Large Exports Should Be Background Jobs

Instead of holding an HTTP connection open for hours:

1. Accept the export request and generate a job ID.
2. Execute a checkpointed job in bounded workers.
3. Write output to temporary storage or object storage.
4. Verify completion and publish an authorized download URL.
5. Clean up expired files per retention policy.
6. On failure, transition the job to `FAILED` with retry support.

HTTP streaming makes sense for moderate outputs; not every scenario requires async job orchestration.

---

## 36. Monitoring Open Cursors on MongoDB Server

In environments with appropriate privileges:

```javascript
const cursorMetrics =
    db.serverStatus().metrics.cursor;

printjson(cursorMetrics);
```

Commonly exposed groups/counters depending on version:

- `open.total`.
- `open.noTimeout`.
- `open.pinned`.
- `timedOut`.
- `lifespan` histograms or related statistics.

**Field names and schemas can vary across MongoDB Server versions.**

### 36.1. Signals Worth Investigating

- Open cursor count climbing steadily even after requests finish.
- Rising `noTimeout` cursors without clear ownership.
- `timedOut` climbing alongside export failures.
- Cursor lifespans exceeding SLAs.
- High `getMore` latency.
- Simultaneous growth in heap, connection pool usage, or threads.

### 36.2. High Cursor Counts Do Not Always Indicate Leaks

A service maintaining multiple long-lived Change Streams legitimately keeps cursors open. Compare against **expected design counts** and ownership before blindly killing cursors.

---

## 37. `currentOp` and `killCursors`

When investigating long-running queries or `getMore` calls:

```javascript
db.currentOp();
```

Or:

```javascript
db.adminCommand({
  currentOp: 1
});
```

MongoDB provides the administrative `killCursors` command to terminate server cursors given their IDs and namespace.

```javascript
// Syntax illustration only; DO NOT run casually in production.
db.runCommand({
  killCursors: "orders",
  cursors: [NumberLong("123456789")]
});
```

### 37.1. Prefer Closing from the Application

If the application owns a `MongoCursor`, **call `close()`**. Reserve manual kills for approved administrative interventions after verifying the cursor/collection and accepting that active valid jobs may fail.

### 37.2. Closing a Cursor Is Different from Closing the Client

Closing a cursor does not tear down the `MongoClient` connection pool. Never call `client.close()` after every document just to "free resources".

---

## 38. How Many Connections Does Each Cursor Use?

A common misconception:

> 100 cursors always equate to 100 TCP connections pinned for their entire lifetime.

Not every query pins a connection. The driver manages connection pools; pinning behavior differs for transactions, load-balanced deployments, Change Streams, or specialized operations.

Measure each metric independently:

- `metrics.cursor.open`.
- Connection pool active and checked-out counts.
- Pool wait time.
- Driver thread counts.
- `getMore` latency.
- Pinned connections/cursors where topology exposes metrics.
- Server selection timeouts.

Do not enlarge the connection pool merely because cursor counts are high if the true bottleneck is downstream throughput or JVM heap.

---

## 39. Retryable Writes Do Not Make External APIs Idempotent

Consider a worker flow:

```text
Read order O100 from cursor
    |
    v
Charge payment gateway
    |
    v
Save processed checkpoint
```

If payment succeeds but saving the checkpoint times out, retrying may charge the customer twice.

**Solution:** attach a stable idempotency key per business operation, persist state, and reconcile with the gateway. MongoDB retryable writes do not protect external HTTP calls.

### 39.1. Do Not Treat Cursor Position as a Transaction Boundary

Distinguish clearly between:

- Read position.
- Side effect acknowledged.
- Checkpoint persisted.
- Business operation completed.

A cursor only tracks read ordering; it never proves side effects committed cleanly.

---

## 40. Partitioning Large Processing Jobs

For massive workloads, divide key ranges across partitions:

```text
Worker A: _id in [min, boundary1)
Worker B: _id in [boundary1, boundary2)
Worker C: _id in [boundary2, max]
```

Each worker maintains:

- Its own cursor.
- Non-overlapping range filters.
- Its own batch size.
- Its own checkpoint.
- A retry policy.
- Ownership/lease and heartbeat.
- Throughput and error metrics.

### 40.1. Do Not Partition by Assuming Uniform ObjectId Distribution

`ObjectId` values are not necessarily distributed uniformly numerically; one range may be packed densely while another is nearly empty.

### 40.2. Cap Parallelism

Too many concurrent workers can saturate:

- Disk IOPS and index reads.
- Network bandwidth.
- MongoDB CPU.
- Connection pools.
- Downstream APIs.
- Java heap.

Adding more workers does not always improve throughput.

---

## 41. Designing Background Job State

An example schema:

```javascript
{
  _id: "export-orders-T100-20261114",
  state: "RUNNING",
  tenantId: "T100",
  startedAt: ISODate("2026-11-14T08:00:00Z"),
  updatedAt: ISODate("2026-11-14T08:30:00Z"),
  lastProcessedId: ObjectId("691800000000000000000111"),
  processedCount: NumberLong("250000"),
  failedCount: NumberLong("3"),
  attempt: 2,
  workerId: "worker-01",
  schemaVersion: 1
}
```

Fields to capture:

- `state`: CREATED, RUNNING, RETRY_WAIT, FAILED, COMPLETED, CANCELLED.
- `lease`/owner to prevent two workers from claiming the same partition.
- Durable checkpoint.
- Attempt count.
- Processed/failed counts.
- Heartbeat timestamp.
- Query filter/version.
- Output ID or temp file path.
- Data retention and access control settings.

Never store a server cursor ID as a progress checkpoint.

---

## 42. Common Errors and How to Diagnose Them

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| `MongoCursorNotFoundException` | Cursor or server session expired | Page queries, check timeouts, resume from checkpoint |
| Network reset during `getMore` | Server election or network issue | Retry job from checkpoint |
| `OutOfMemoryError` | `into(List)`, unbounded buffer | Use cursor with bounded processing |
| Stops at exactly 100 documents | Loop condition relies on `available()` | Use `hasNext()` |
| Batch size 500 returns only 120 | Byte limit or final batch | Normal behavior |
| `hasNext()` is slow | Slow server `getMore`, disk, or network | Check query metrics, indexes, timeouts |
| `first()` returns an "unexpected" record | Missing sort clause | Sort explicitly per business rules |
| Many idle cursors | Forgot `close()`, request leaks | `try-with-resources`, lifecycle monitoring |
| `noCursorTimeout` still gets killed | Session idle timeout or topology event | Do not rely solely on `noCursorTimeout` |
| Duplicate rows in export | Non-idempotent retry | Keyset + checkpoint + idempotency |
| Missing records in export | Mutable sort key or bad checkpoint | Stable sort key, data consistency |
| Partial bulk success | Ordered/unordered bulk semantics | Handle write errors and acknowledgements |
| Parallel cursor errors | Multiple threads calling `next` | Single producer + bounded queue |
| Truncated HTTP export | Client disconnect or cursor failure | Define partial-response policy |
| Secondary replication lag | Heavy reporting scans | Throttle workload or capacity |
| Query slow from the very first record | Blocking sort or full scan | `explain`, proper indexes |
| Connection pool timeout | Excessive concurrent waits | Inspect pool metrics and concurrency |
| `maxTime` does not stop HTTP call | Server timeout does not wrap Java app work | Enforce layered deadlines |

---

## 43. Anti-Patterns to Avoid

### 43.1. Storing a Cursor as a Singleton Service Field

```java
// Avoid inside a Spring singleton:
private MongoCursor<Document> cursor;
```

A cursor belongs to **one processing execution**, not shared global state.

### 43.2. Returning an Open Cursor Without Documenting Ownership

```java
public MongoCursor<Document> openOrders() {
    return collection.find().cursor();
}
```

If such a method is unavoidable, clearly specify **caller owns and closes** in Javadoc and audit callers; usually it is safer to accept a callback/consumer and close the cursor internally.

### 43.3. Forcing Java Parallel Streams Directly Over a Cursor

`MongoCursor` is not thread-safe. For parallel processing, have one producer read sequentially and feed a bounded queue.

### 43.4. Increasing `batchSize` Indefinitely

Oversized batches raise heap/GC overhead without fixing slow downstream APIs or server-side blocking sorts.

### 43.5. Collecting All Results into a `HashMap` "to Process Later"

Memory still scales linearly with total results, negating streaming benefits.

### 43.6. Enabling `noCursorTimeout` Globally

Easily leaves long-lived idle server cursors behind and still cannot bypass session idle timeouts.

### 43.7. Exposing Cursor IDs as Public Pagination Tokens

Cursor IDs are non-durable, carry no tenant authorization context, and are not safe API contracts.

### 43.8. Holding a Transaction Open Across an Entire Migration

Risks hitting transaction lifetime limits and straining resources without substituting for durable checkpoints.

### 43.9. Ignoring Partial Outputs on Error

Target CSVs/files may be incomplete even when the cursor itself closed cleanly.

---

## 44. Scenario: MongoCursor Fails After 35 Minutes

**Symptom:** the job reads the first 500 documents, then throws on `getMore` after a long processing phase.

**Analysis:**

```text
Batch size: 500
Processing per document: 5 seconds
Elapsed per batch: ~41 minutes
Session idle timeout default: ~30 minutes
```

**Solution:**

1. Reduce batch size.
2. Bound external API latency.
3. Switch to short paged queries.
4. Persist checkpoints after processed output succeeds.
5. Check KMS, network, or primary elections if logs suggest other causes.
6. Never assume `noCursorTimeout(true)` alone solves this.

---

## 45. Scenario: OOM Despite Using `batchSize(100)`

**Code:**

```java
List<Document> documents = collection.find()
    .batchSize(100)
    .into(new ArrayList<>());
```

**Problem:** `into` still loads all 8 million results into the list.

**Fix:**

```java
try (MongoCursor<Document> cursor =
         collection.find()
             .batchSize(100)
             .cursor()) {

    while (cursor.hasNext()) {
        process(cursor.next());
    }
}
```

Ensure `process` does not retain unbounded references either.

---

## 46. Scenario: Slow Export Due to Unindexed Sort

**Symptom:**

```text
Time to first document: 80 seconds
Batch size: 100
Server execution stats: blocking sort
Disk reads: high
```

**Remediation:**

- Run `explain`.
- Align filter and sort with an index.
- Narrow the query window.
- Use keyset pagination with a stable key.
- Consider pre-computed outputs.
- Do not merely raise `batchSize`.

---

## 47. Scenario: Migration Drops Records After Restart

**Broken flow:**

```text
Read document D100
Save checkpoint D100
Write D100 to destination -> failed
Restart: query D > D100
D100 is skipped
```

**Fix:**

```text
Read D100
Apply idempotent write successfully
Save checkpoint D100
Restart may replay if checkpoint save fails
Idempotency prevents duplicate harmful effects
```

With multiple workers, checkpoints must track **contiguous completed work**, not just the highest completed ID.

---

## 48. Scenario: Export API Overloads Production

A user requests a 5-year order export using an unindexed query across 50 concurrent requests.

**Risks:**

- High disk I/O.
- Spiking cursor counts.
- Memory and bandwidth pressure.
- Degraded latency for normal API traffic.
- Sensitive data exposure in exports.
- Requests hitting proxy timeouts.

**Resolution:**

1. Enforce RBAC and tenant authorization.
2. Apply row/byte quotas and concurrency caps on exports.
3. Move to checkpointed async jobs.
4. Require indexed time-window filters.
5. Route to a reporting secondary or dedicated cluster if consistency permits.
6. Secure outputs, enforce retention, and log audits.
7. Monitor p95/p99 latency of critical workloads.

---

## 49. Security Checklist for Large Dataset Processing

- Never trust a client-supplied tenant ID alone for authorization.
- Derive tenant filters from authenticated context.
- Exclude sensitive fields unless explicitly authorized.
- Enforce record and byte limits.
- Configure timeouts and rate limits on export APIs.
- Never log raw documents or credentials.
- Never write production CSVs to world-readable directories.
- Clean up temp files after `FAILED` or `CANCELLED` runs.
- Never expose cursor IDs as capability tokens.
- Use TLS, authentication, and least-privilege DB roles.
- Emit audit events for exports and downloads.
- Separate dataset read privileges from MongoDB admin privileges.
- When writing exports to object storage, enforce encryption and access policies.

---

## 50. MongoCursor Code Review Checklist

- [ ] Do you know roughly how many documents the query can return?
- [ ] Avoided `into(List)` on unbounded results?
- [ ] Distinguished `batchSize` from `limit`?
- [ ] Does every explicit cursor have a clear owner?
- [ ] Protected with `try-with-resources` or `finally` close?
- [ ] Do `break`, `return`, and exceptions all clean up the cursor?
- [ ] Avoided using `available()` as total count?
- [ ] Avoided using `available()` as the loop termination condition?
- [ ] Appropriate filters, sorts, projections, and indexes in place?
- [ ] Measured time-to-first-document?
- [ ] Batch size tuned appropriately for document size?
- [ ] Avoided accumulating records unboundedly in queues/maps?
- [ ] Handled errors occurring mid-`getMore`?
- [ ] Timeouts enforced across server, client, and downstream calls?
- [ ] Avoided blanket `noCursorTimeout`?
- [ ] Accounted for session idle timeouts during slow processing?
- [ ] Implemented checkpoints for long jobs?
- [ ] Persisted checkpoints only after effects are acknowledged?
- [ ] Ensured idempotency across retries?
- [ ] Avoided sharing cursors across multiple threads?
- [ ] If parallelized, used a bounded queue and ordered checkpointing?
- [ ] Cancellation triggers `close()` and cleanup?
- [ ] Avoided arbitrary multi-hour transactions?
- [ ] Not treating a cursor as an immutable snapshot?
- [ ] Protected output files against partial failures?
- [ ] Monitoring open cursors, heap, and `getMore` metrics?
- [ ] Never closing the global `MongoClient` per cursor?
- [ ] Tested resilience against primary elections and network drops?
- [ ] Verified tenant authorization and sensitive-field filtering?
- [ ] Strategy defined for records changing mid-scan?

---

## 51. Practice Exercises with Answers

### Exercise 1 — Total Document Count

```java
int n = collection.find().cursor().available();
```

**Question:** Is `n` the total number of documents?

**Answer:** No. It is only the number of documents buffered locally; this also leaks an unclosed cursor.

### Exercise 2 — Batch Size vs. Limit

A query matches 1,000,000 documents and sets `.batchSize(100)`.

**Question:** Can more than 100 documents be read?

**Answer:** Yes. `batchSize` only controls documents per batch.

### Exercise 3 — Early Break

```java
for (Document d : collection.find()) {
    if (isTarget(d)) break;
}
```

**Question:** What needs to be fixed?

**Answer:** Use an explicit `MongoCursor` inside `try-with-resources` so it closes upon breaking.

### Exercise 4 — Exceptions

`process()` throws on the 300th document while the cursor is inside `try-with-resources`.

**Answer:** Java still invokes `close()`.

### Exercise 5 — Memory

Each decoded Java document averages 8 KiB, `batchSize` is 2000, and 30 cursors run concurrently.

**Answer:** Estimate 8 × 2000 × 30 KiB = 468,750 KiB ≈ 468.75 MiB, before counting JVM/codec overhead.

### Exercise 6 — Session Timeout

A batch takes 45 minutes to process, and the next `getMore` throws cursor not found.

**Answer:** Likely caused by session idle timeout; shorten cursor/page lifetimes rather than relying solely on `noCursorTimeout`.

### Exercise 7 — `available()` Equals Zero

Can `hasNext()` still return `true` when `available() == 0`?

**Answer:** Yes; the local client buffer is empty while the server still has remaining documents.

### Exercise 8 — Large Skip

Page 10,000 uses `skip(1_000_000)`.

**Answer:** Expensive because the server walks through many entries; keyset pagination is better for sequential scans.

### Exercise 9 — Checkpointing

A job saves its checkpoint before calling an external API, and the API call fails.

**Answer:** Records can be skipped after restart; persist checkpoints only after effects are acknowledged.

### Exercise 10 — Duplicate Effects

A job charges a payment gateway and crashes before saving the checkpoint.

**Answer:** Use idempotency keys to avoid double-charging on retry.

### Exercise 11 — Parallel Cursor Reads

Three threads call `cursor.next()` on the same cursor instance.

**Answer:** Not thread-safe; use one producer thread feeding a bounded queue.

### Exercise 12 — Cancellation

One thread is blocked in `hasNext()` while another thread needs to cancel it.

**Answer:** The interface permits concurrent `close()` calls, though not arbitrary concurrent reads.

### Exercise 13 — Tailable Cursors

`tryNext()` returns `null` on a Change Stream or tailable cursor.

**Answer:** Simply indicates no event is ready yet, not that the stream has ended.

### Exercise 14 — Snapshots

Does sorting ascending by `_id` guarantee every returned document reflects the state at 10:00?

**Answer:** No; concurrent writes and read concern/snapshot policies must be considered.

### Exercise 15 — Mid-Export Failure Over HTTP

HTTP has already streamed 5 MiB of CSV when the database fails.

**Answer:** Previously sent bytes cannot be replaced with a clean HTTP 500 JSON payload; define a partial/failure policy.

### Exercise 16 — Cursor ID

Can a server cursor ID be saved to resume after a restart?

**Answer:** No. Use logical checkpoints/keysets or Change Stream resume tokens as appropriate.

### Exercise 17 — MongoClient Lifecycle

Should you call `client.close()` after every cursor?

**Answer:** No, when the client is a long-lived singleton pool; scope cursor closing to tasks and client closing to app shutdown.

### Exercise 18 — Batch Size Zero

`batchSize: 0` on the server can create a cursor with an empty first batch. Does that mean "no results"?

**Answer:** No; results can arrive in subsequent `getMore` calls. Do not interpret an empty first batch as zero matches.

### Exercise 19 — Projection

Only returning two fields—does disk I/O necessarily drop by 90%?

**Answer:** No. Projection shrinks result payload size; physical reads still depend on execution plans and covered queries.

### Exercise 20 — Aggregation

Aggregating `$group` over 100 million events while Java sets `batchSize(100)`.

**Answer:** The server may still consume substantial intermediate memory/disk; client `batchSize` does not solve that.

### Exercise 21 — Partial Bulk Success

`bulkWrite` throws an exception after partially applying writes.

**Answer:** Do not assume full rollback; inspect results/errors, apply idempotency, and checkpoint accurately.

### Exercise 22 — Timestamp Keysets

Two documents share the exact same `createdAt`.

**Answer:** Add `_id` as a tie-breaker, sort by `(createdAt, _id)`, and use a matching lexicographic filter.

### Exercise 23 — Mutable Sort Keys

A document's `createdAt` changes mid-scan.

**Answer:** It may be read twice or skipped. Use immutable keys or snapshot/reconciliation workflows.

### Exercise 24 — Slow Downstream Sink

MongoDB reads 20,000 docs/s while the sink writes 200 docs/s.

**Answer:** The sink caps overall throughput; increasing `batchSize` won't help and increases memory and cursor lifetime.

### Exercise 25 — Progress Counts

Running `countDocuments` is too costly on huge datasets.

**Answer:** Report processed count, high-water marks, or partition progress instead; exact totals are not mandatory.

### Exercise 26 — Retrying Entire Requests

An exception in `next()` retries the entire HTTP request, including sending emails.

**Answer:** Protect external side effects with idempotency and resume from checkpoints.

### Exercise 27 — Concurrent Load

50 large exports run simultaneously and API p99 latency spikes.

**Answer:** Cap concurrency/quotas, optimize indexes, isolate reporting workloads, or offload to async jobs.

### Exercise 28 — CSOT

Does query `maxTime` bound 1 hour of CSV formatting work in Java?

**Answer:** No. Enforce end-to-end deadlines and appropriate CSOT/timeout modes.

### Exercise 29 — Server Metrics

`metrics.cursor.open.total` keeps growing without dropping after jobs stop.

**Answer:** Investigate cursor ownership/leaks versus expected long-lived streams; avoid killing cursors blindly.

### Exercise 30 — Recommended Architecture

Need to migrate 30 million documents over several hours while tolerating process restarts at any time.

**Answer:** Split into pages/partitions with short cursor scopes, durable checkpoints, idempotent writes, bounded memory, retry with backoff, monitoring, and reconciliation.

---

## 52. Official MongoDB Documentation

- [Access Data From a Cursor — Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/cursor/): using `FindIterable`, `MongoCursor`, `first`, `into`, `available`, close, and `try-with-resources`.
- [MongoCursor API — Java Sync Driver](https://mongodb.github.io/mongo-java-driver/5.7/apidocs/driver-sync/com/mongodb/client/MongoCursor.html): `hasNext`, `next`, `tryNext`, `available`, `close`, and thread safety.
- [Cursors — MongoDB Manual](https://www.mongodb.com/docs/manual/core/cursors/): server cursor ID, `getMore`, and lifecycle.
- [getMore Command — MongoDB Manual](https://www.mongodb.com/docs/manual/reference/command/getMore/): subsequent batches, `batchSize`, and timeouts.
- [cursor.batchSize — MongoDB Manual](https://www.mongodb.com/docs/manual/reference/method/cursor.batchSize/): 101-document/16 MiB first batch behavior and trade-offs.
- [cursor.noCursorTimeout — MongoDB Manual](https://www.mongodb.com/docs/manual/reference/method/cursor.noCursorTimeout/): idle cursor and session timeouts.
- [MongoDB Limits and Thresholds](https://www.mongodb.com/docs/manual/reference/limits/): BSON document limits and session idle timeout.
- [Limit Server Execution Time — Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/csot/): CSOT and cursor lifetime/iteration timeouts.
- [Query Documents — Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/): filter, sort, projection, limit.
- [Limit Returned Results — Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/limit/): limit/skip.
- [Bulk Write Operations — Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/crud/bulk/): ordered/unordered execution, errors, and batched writes.
- [Transactions — Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/): `ClientSession` and transaction semantics.
- [Change Streams — Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/change-streams/): event cursors and resume tokens.
- [Database Profiler](https://www.mongodb.com/docs/manual/tutorial/manage-the-database-profiler/): query diagnostics and profiler overhead.
- [serverStatus — MongoDB Manual](https://www.mongodb.com/docs/manual/reference/command/serverStatus/): `metrics.cursor` and other server metrics.
- [Java Sync Driver Compatibility](https://www.mongodb.com/docs/drivers/java/sync/current/compatibility/): Java/driver/server compatibility.
- [Java Reactive Streams Driver](https://www.mongodb.com/docs/languages/java/reactive-streams-driver/current/): non-blocking APIs and reactive backpressure.

**Version note:** APIs such as `timeoutMode()` and CSOT, tailable/Change Stream `getMore` semantics, `metrics.cursor`, and server timeouts can vary across Java Driver, MongoDB Server, and deployment topology versions. Verify against your active versions before deploying to production.

---

## 53. Summary

**MongoCursor** is the primary mechanism for Java applications to process large MongoDB result sets without loading everything onto the heap:

1. `FindIterable` configures the query; `MongoCursor` iterates the results.
2. MongoDB streams results in **batches**, while Java issues `getMore` transparently as needed.
3. `batchSize` tunes documents per fetch, **not** total results; `limit` caps the total.
4. `available()` reports only locally buffered documents, not total count.
5. Use `try-with-resources` so `close()` always runs on exhaustion, early exit, or errors.
6. `noCursorTimeout` does not disable session timeouts, failovers, or network interruptions.
7. `MongoCursor` is **not thread-safe**; for concurrent processing, use a single producer thread and a bounded queue.
8. Large jobs require **checkpoints + idempotency + retries from a fresh query**, never reusing server cursor IDs as resume tokens.
9. Filters, indexes, sorts, projections, and aggregations must still be tuned to minimize server reads.
10. Large HTTP exports must manage partial outputs, quotas, cancellation, and security.

Core pattern:

```java
try (MongoCursor<Document> cursor =
         collection.find(filter)
             .sort(sort)
             .projection(projection)
             .batchSize(500)
             .cursor()) {

    while (cursor.hasNext()) {
        processIdempotently(cursor.next());
    }
}
```

Then layer on checkpointing, bounded buffering, cancellation, monitoring, and data consistency policies matching your production requirements.

**Safely reading large datasets is equally a problem of memory, throughput, resource lifecycle, and recoverability — never just a `while (cursor.hasNext())` loop.**
