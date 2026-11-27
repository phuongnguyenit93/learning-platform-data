# Cursor Lifecycle, `getMore`, and Batch Loading Mechanism in MongoDB

## 1. Why Don't Multi-Document Queries Return Everything Immediately?

Suppose an application needs to retrieve all customer events over 12 months. A MongoDB collection can contain hundreds of thousands or millions of documents. If the server tried to bundle all results into a single response and the application loaded everything into memory, the system would run into several problems:

- The network response could be too large and take a long time.
- The server would have to maintain or generate a massive amount of result data before sending it.
- The application would consume a lot of memory and easily crash with out-of-memory errors.
- It would be impossible to incrementally process the first documents while thousands of documents remain behind them.
- When the network is interrupted, transferring overly large payloads becomes difficult to control.

MongoDB solves this with **cursors** and **batching**. Instead of returning the entire result set at once, MongoDB typically sends **a first batch of results** and a **cursor ID**. When the application needs to read more, the driver sends a **`getMore`** command to receive the next batch. This process repeats until there are no more results or the cursor is closed.

```text
Application/driver                   MongoDB server
       |                                   |
       |---- find or aggregate ----------->|
       |                                   | Plan query, begin reading
       |<--- firstBatch + cursor ID -------|
       |                                   |
       | Process each document in batch    |
       |                                   |
       |---- getMore(cursor ID) ---------->|
       |                                   | Continue reading results
       |<--- nextBatch + cursor ID --------|
       |                                   |
       | Continue processing               |
       |                                   |
       |---- getMore(cursor ID) ---------->|
       |<--- nextBatch + cursor ID = 0 ----|
       |                                   |
       | No more data, end reading         |
```

This is the **logical flow**. MongoDB drivers usually send `getMore` automatically; developers do not have to manually manage cursor IDs in typical applications.

### Three Concepts to Separate

| Concept | Meaning |
|---|---|
| **Query** | A request to find or process documents, e.g. `find({ status: "PAID" })` |
| **Cursor** | A mechanism that allows continuing to read a query's results across multiple round-trips |
| **Batch** | A group of documents transferred from the server to the client in a single response |

A cursor can deliver **multiple batches**, and each batch contains **multiple documents**. A cursor can also end right after the first batch if the result set is small. Not every query needs to execute `getMore`.

## 2. Preparing Sample Data

Run the examples on a test database in **mongosh**. Create an `events` collection containing six events:

```javascript
db.events.insertMany([
  {
    _id: "E001",
    customerId: "C01",
    eventType: "LOGIN",
    createdAt: ISODate("2026-11-01T08:00:00Z")
  },
  {
    _id: "E002",
    customerId: "C01",
    eventType: "VIEW",
    createdAt: ISODate("2026-11-01T08:05:00Z")
  },
  {
    _id: "E003",
    customerId: "C01",
    eventType: "ADD_TO_CART",
    createdAt: ISODate("2026-11-01T08:10:00Z")
  },
  {
    _id: "E004",
    customerId: "C01",
    eventType: "CHECKOUT",
    createdAt: ISODate("2026-11-01T08:15:00Z")
  },
  {
    _id: "E005",
    customerId: "C01",
    eventType: "PAYMENT",
    createdAt: ISODate("2026-11-01T08:20:00Z")
  },
  {
    _id: "E006",
    customerId: "C02",
    eventType: "LOGIN",
    createdAt: ISODate("2026-11-01T09:00:00Z")
  }
]);
```

When filtering by `customerId: "C01"` and sorting by `createdAt` ascending, we expect **five** events, `E001` through `E005`. In the following examples, `batchSize: 2` helps illustrate returning multiple batches, although in practice an appropriate batch size is usually different.

You should only use a dedicated collection for practice; do not create test data or send arbitrary cursor management commands against production data.

## 3. Cursors on Two Sides: Client and Server

An important point is that the word "cursor" can refer to **two related objects that are not completely identical**.

### 3.1. Driver or mongosh Cursor

When writing:

```javascript
const cursor = db.events
  .find({ customerId: "C01" })
  .sort({ createdAt: 1, _id: 1 });
```

the `cursor` variable in the application is the **client API cursor object**. It provides a way to iterate over documents and manages fetching additional data, typically offering methods such as `hasNext()`, `next()`, `toArray()`, or `close()` depending on the driver.

Drivers may defer command execution until the application starts iterating or requests results. Therefore, do not assume that merely initializing a cursor variable means MongoDB has already opened a cursor on the server. When the command is sent depends on the driver's API and lazy execution behavior.

### 3.2. MongoDB Server-Side Cursor

The server can maintain a **server-side cursor** to continue query execution across `getMore` commands. When processing a `find` or `aggregate` command, the response may look like:

```javascript
{
  cursor: {
    firstBatch: [
      { _id: "E001", customerId: "C01", /* ... */ },
      { _id: "E002", customerId: "C01", /* ... */ }
    ],
    id: NumberLong("123456789"),
    ns: "demo.events"
  },
  ok: 1
}
```

The response above is an **illustrative schema**, not an actual ID value. The `ns` field is the collection's namespace; the database name in your example may differ. A server-side cursor can hold execution state and associated resources for continued reading.

Once the driver fetches all results, the cursor on the server terminates. The driver tracks the necessary state to know which documents it has received and whether it still needs to send `getMore`.

### 3.3. Each Batch Does Not Have a New Cursor

A cursor ID is used to **continue the same result stream**. Within the same query command, `getMore` accepts the cursor ID issued by the server and returns the next batch. When the cursor is exhausted, the server typically returns an ID of **0**, indicating there is no remaining server-side cursor to request from.

Do not confuse **cursor ID** with a document's `_id`:

- `_id` identifies a stored document.
- `cursor.id` identifies a temporary live cursor on the server, used for `getMore`.
- A cursor ID is not a business key or a durable pagination token.

## 4. Lifecycle of a Typical Cursor

A typical MongoDB cursor generally goes through the following phases:

### Phase 1 — Request Creation and Server Selection

The application configures `find()` or `aggregate()`. The driver selects an appropriate server/router based on topology, read preference, and the operation's session. The driver uses a connection from the connection pool when sending the command.

### Phase 2 — Server Execution and Creating the First Batch

MongoDB analyzes the filter, indexes, sort, pipeline, and limits. The server performs enough work needed to return the results in the first batch. If there is still unread data, the server issues a non-zero cursor ID.

**Do not assume that just setting `batchSize: 2` guarantees the server computes only two documents and stops all processing.** Some queries contain stages that must process a large amount of data before returning the first result, such as a sort that cannot use an index or a blocking `$group` aggregation stage.

### Phase 3 — Client Consumes the Batch

The driver decodes BSON documents into programming language values and passes them to the application. The application can process each document, build a response, write to a file, or compute aggregations.

During this phase, the client may still have documents in the **local buffer** of the batch it just received. Calling `next()` does not necessarily send a network request per document.

### Phase 4 — Sending `getMore` When Needed

When the current batch is exhausted while the server cursor is still open, the driver sends `getMore` to request the next batch. The server resumes the cursor's work and returns `nextBatch`.

### Phase 5 — Completion or Early Closure

A cursor can end in several ways:

- **Natural exhaustion:** the server returns cursor ID = 0; the driver knows all results have been read.
- **Early closure by the application:** the client calls `close()` or an equivalent method; the driver may send `killCursors` to free server resources.
- **Inactivity timeout:** the server may close idle cursors according to its timeout policy.
- **Errors or topology changes:** changes in the associated connection, server, session, or transaction can render continuing the read invalid.

Logical state diagram:

```text
     Prepare query on client
               |
               v
     Send find / aggregate
               |
               v
       Receive firstBatch
               |
               +---- cursorId = 0 ----> Read remaining batch ----> END
               |
       non-zero cursorId
               |
               v
       Read received documents
               |
               +---- application close() ----> killCursors / cleanup
               |
               +---- error / timeout --------> cursor cannot continue
               |
               v
        Send getMore
               |
               v
         Receive nextBatch
               |
               +---- cursorId = 0 ----> Read remaining batch ----> END
               |
               +---- non-zero cursorId ----> Repeat
```

**Cursors are short-lived.** Do not store a cursor ID as a "next page" in a database or send it to a frontend to be used hours later.

## 5. Observing `firstBatch` and `getMore` at the Command Level

When using `find()` in mongosh, many steps are handled automatically by the shell and driver. To inspect responses at the command level, you can send `find` using `db.runCommand()`:

```javascript
const initial = db.runCommand({
  find: "events",
  filter: { customerId: "C01" },
  sort: { createdAt: 1, _id: 1 },
  batchSize: 2
});

printjson(initial);
```

On the sample dataset, `firstBatch` may contain:

```javascript
[
  { _id: "E001", customerId: "C01", /* ... */ },
  { _id: "E002", customerId: "C01", /* ... */ }
]
```

If more data remains, `initial.cursor.id` is non-zero. We can use that ID for the subsequent `getMore`:

```javascript
// Run only when initial.ok === 1 and initial.cursor.id is non-zero.
const second = db.runCommand({
  getMore: initial.cursor.id,
  collection: "events",
  batchSize: 2
});

printjson(second);
```

A typical `getMore` response looks like:

```javascript
{
  cursor: {
    nextBatch: [
      { _id: "E003", customerId: "C01", /* ... */ },
      { _id: "E004", customerId: "C01", /* ... */ }
    ],
    id: NumberLong("123456789"),
    ns: "demo.events"
  },
  ok: 1
}
```

When you need to read E005, send another `getMore` command using the **cursor ID from the latest response**:

```javascript
// Run only when second.cursor.id is non-zero.
const third = db.runCommand({
  getMore: second.cursor.id,
  collection: "events",
  batchSize: 2
});

printjson(third);
```

After the batch containing E005, a standard cursor will be exhausted; the response may carry `id: NumberLong("0")`. When the cursor ID is 0, do not send another `getMore` with that ID.

### 5.1. Command Structure to Remember

| Field | In which command? | Role |
|---|---|---|
| `find: "events"` | `find` | Name of the collection being queried |
| `filter` | `find` | Condition for selecting documents |
| `sort` | `find` | Ordering of results |
| `batchSize` | `find` / `getMore` | Requests the desired maximum number of documents for the batch |
| `cursor.firstBatch` | `find` / `aggregate` response | First batch of documents |
| `cursor.nextBatch` | `getMore` response | Next batch of documents |
| `cursor.id` | Response with cursor | Cursor identifier; 0 indicates no cursor remains on the server |
| `cursor.ns` | Response with cursor | Source namespace of the cursor |
| `getMore` | `getMore` command | Cursor ID to continue reading |
| `collection` | `getMore` command | Collection containing the cursor according to the namespace |

The sample responses use illustrative IDs and database names. In real implementations, the driver also manages server info, sessions, timeouts, authentication, and protocol context to route `getMore` to the right place. **The `db.runCommand` example is only for understanding the mechanism**, not a recommendation to implement your own MongoDB driver.

### 5.2. Must Continue on the Same Server and in the Same Context

A server-side cursor is bound to the context that created it: namespace, appropriate server, session (when present), and execution resources. You cannot arbitrarily take a cursor ID from one server and send `getMore` to a random other server.

The driver stores the information needed to send `getMore` to the right destination. In some modes, such as load-balanced deployments or transactions, there may be a requirement to **pin** a connection/server for the lifetime of the cursor. When using standard driver APIs, applications should not manually manage those routing details.

## 6. What Does Batch Size Actually Control?

### 6.1. `batchSize` Is a Target Document Count, Not Total Results

```javascript
const cursor = db.events.find({ customerId: "C01" })
  .sort({ createdAt: 1, _id: 1 })
  .batchSize(2);

while (cursor.hasNext()) {
  printjson(cursor.next());
}
```

`batchSize(2)` asks the driver/server to exchange results in small batches of roughly up to two documents, subject to response limits and execution mechanics. **It does not limit the query to returning only two documents**: the loop can read all five events.

In contrast:

```javascript
db.events.find({ customerId: "C01" })
  .sort({ createdAt: 1, _id: 1 })
  .limit(2);
```

`limit(2)` restricts the **total number of documents** returned by the query. That is a completely different meaning.

### 6.2. `batchSize`, `limit`, and Page Record Count in an API

| Concept | What does it limit? | Does it automatically create HTTP pagination? |
|---|---|---|
| `batchSize(100)` | Desired number of documents per server → driver batch | No |
| `limit(100)` | Maximum number of documents for the query | No, does not create subsequent pages automatically |
| `skip(100)` | Skips the first 100 documents in query order | Only one component of offset pagination |
| `pageSize = 20` in a REST API | Number of items to return in one business response | Designed by the application itself |

An endpoint returning 20 documents might use a batch size of 100; because of `limit(20)`, it does not need all 100. Conversely, a query returning 10,000 documents might use `batchSize(200)` to incrementally process 50 or more batches without any HTTP pages at all.

### 6.3. First Batch and Response Size Limits

For typical `find` and `aggregate` operations, MongoDB has default rules for the first batch—often up to **101 documents or 16 MiB of data**, whichever is reached first if no other batch size is specified. Subsequent batches are subject to response size limits, and `getMore` may return **fewer documents** than requested if the data is large enough or due to other execution conditions.

Important points:

- `batchSize` is a **document count**, not a byte count or RAM size.
- Responses are also bounded by payload size, so a batch of 1,000 documents is not guaranteed to contain all 1,000 documents.
- The size limit of **a single BSON document** is 16 MiB; this is a different concept from the batch size limit.
- Default batch values can depend on operation type, version, and client configuration; do not write code relying on the number 101 as an immutable contract in all cases.

### 6.4. `batchSize(0)` Does Not Mean Reading 0 Documents Forever

At the `find` command level, `batchSize: 0` can be used to request an **empty first batch** while still creating a cursor to read from later:

```javascript
const response = db.runCommand({
  find: "events",
  filter: { customerId: "C01" },
  batchSize: 0
});

printjson(response.cursor);
```

Depending on the command and situation, the response may contain `firstBatch: []` and a non-zero cursor ID. A subsequent `getMore` request can continue fetching data. This is a command-level control mechanism; do not use it to express "a query with no results". If you truly only need to check existence or count, use the appropriate API.

## 7. How Drivers Automatically Call `getMore`

In most application code, developers see a regular loop:

```text
for each document in cursor:
    process document
```

Underneath, however, what happens may look like:

```text
Client buffer: [doc1, doc2]
next() -> doc1              [no new request]
next() -> doc2              [no new request]
next() -> empty buffer
Driver sends getMore
Client buffer: [doc3, doc4]
next() -> doc3              [read from buffer]
next() -> doc4              [read from buffer]
...
```

The driver is responsible for:

1. Holding the cursor ID and server/session information.
2. Checking whether buffered documents remain in the current batch.
3. Sending `getMore` when needed and while the server cursor is still alive.
4. Decoding BSON into programming language objects/values.
5. Signaling end-of-data or throwing an error if reading cannot continue.
6. Sending a command to close the cursor when the application closes early and when supported by the API.

Therefore, **one call to `next()` does not equal one network call**. Nor does one `getMore` call equal one document.

### 7.1. Java Sync Driver Code: Controlled Iteration and Resource Closing

Example using the MongoDB Java Sync Driver and `org.bson.Document`:

```java
import com.mongodb.client.FindIterable;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import org.bson.Document;

import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Sorts.ascending;

public class ReadByBatches {
    public static void main(String[] args) {
        try (MongoClient client =
                     MongoClients.create("mongodb://localhost:27017")) {

            MongoCollection<Document> events = client
                    .getDatabase("learning")
                    .getCollection("events");

            FindIterable<Document> iterable = events
                    .find(eq("customerId", "C01"))
                    .sort(ascending("createdAt", "_id"))
                    .batchSize(100);

            // try-with-resources proactively closes the cursor even if processing throws an error.
            try (MongoCursor<Document> cursor = iterable.iterator()) {
                while (cursor.hasNext()) {
                    Document event = cursor.next();
                    System.out.println(event.toJson());
                }
            }
        }
    }
}
```

Key points to note:

- `FindIterable<Document>` describes the query and options.
- `MongoCursor<Document>` is the object iterated in the application.
- The driver sends `getMore` when it needs to read another batch; application code does not call `getMore` directly.
- `try-with-resources` ensures `close()` is called when exiting the block, even if processing a document throws an exception.
- `batchSize(100)` does not cause `System.out.println` to print only 100 lines.

**Do not use `into(new ArrayList<>())` or `toArray()` for a very large result set** if the goal is sequential processing and bounded RAM. APIs that collect all results into an in-memory collection consume memory proportional to the number of retained documents, even though the driver receives them from the server in batches.

### 7.2. Node.js Code: Iterating a Cursor with Async Iterator

```javascript
import { MongoClient } from "mongodb";

const client = new MongoClient("mongodb://localhost:27017");
await client.connect();

try {
  const events = client.db("learning").collection("events");
  const cursor = events
    .find({ customerId: "C01" })
    .sort({ createdAt: 1, _id: 1 })
    .batchSize(100);

  try {
    for await (const event of cursor) {
      console.log(event._id, event.eventType);
    }
  } finally {
    await cursor.close();
  }
} finally {
  await client.close();
}
```

The driver handles batch loading and awaits async I/O. When the application processes each event slowly, the loop naturally provides a level of consumer-side **backpressure**: it does not have to continuously send `getMore` at maximum speed in every scenario. Buffering and prefetching details still depend on the driver and version.

### 7.3. Processing Code That May Stop Early

```java
try (MongoCursor<Document> cursor = iterable.iterator()) {
    int processed = 0;

    while (cursor.hasNext()) {
        Document event = cursor.next();
        processEvent(event); // Business logic function defined by the application.

        if (++processed >= 500) {
            break;
        }
    }
}
```

When stopping early, the `try` block closes the cursor instead of leaving the server holding unread state. If the requirement only needs 500 documents, you should usually place `limit(500)` directly on the query when appropriate; that also expresses the exact intent to the server.

## 8. `getMore`, Round-Trips, and Latency

Suppose you need to read 10,000 documents and each batch contains exactly 100 documents; the driver then needs roughly 100 batches, consisting of the first batch and multiple `getMore` round-trips. This is a rounded illustrative example; the actual batch count can differ due to size limits and execution mechanics.

A smaller batch leads to **more network round-trips**; a larger batch usually reduces the number of `getMore` trips but increases buffer memory and the amount of unconsumed data on the client.

### 8.1. Qualitative Comparison

| Batch size | Potential advantage | Cost/risk |
|---|---|---|
| Very small, e.g. 1–5 | Client receives few documents per turn, reducing queued data awaiting processing | Many round-trips, high overhead |
| Medium, e.g. 100–500 | Trade-off between round-trips and memory for many workloads | Still needs measuring based on document size and network |
| Very large | Can reduce `getMore` trips for small documents | Batches may hit byte limits; higher memory usage and batch latency |

There is no universal size for every query. A batch containing 200 documents of a few hundred bytes each is very different from 200 documents of several hundred kilobytes each.

### 8.2. A Simple Estimation Formula

If the total number of documents is `N` and the ideal batch size is `B`, the minimum number of batches by count is approximately:

\[
\text{batchCount} \approx \left\lceil\frac{N}{B}\right\rceil
\]

In practice, byte limits and batch return conditions can make the batch count higher. The formula only serves as a rough guide, not an exact prediction of the number of `getMore` commands.

### 8.3. Increasing Batch Size Does Not Fix Every Slow Query

If a query has to scan millions of documents or sort a large dataset before producing results, merely increasing batch size does not eliminate server-side cost. You must also check:

- Do indexes support the `filter` and `sort`?
- Does the pipeline have blocking stages such as certain `$sort` or `$group` scenarios?
- Does the projection return too many large fields?
- Is it necessary to load the entire result set?
- Is the application processing each document so slowly that received batches sit waiting in memory?
- Does the network connection have high latency or limited bandwidth?

This is why optimizing query plans and optimizing batch size are two related but distinct tasks.

## 9. Cursor Timeout, Sessions, and `noCursorTimeout`

### 9.1. Why Does MongoDB Automatically Close Idle Cursors?

An unexhausted cursor can hold server-side resources. If an application abandons a cursor, the server must have a mechanism to reclaim it rather than letting cursors live indefinitely.

In many MongoDB configurations, a standard cursor may be closed after about **10 minutes of inactivity**. This value depends on the server timeout configuration and can vary by environment. A cursor being read normally by an application is not guaranteed to stay alive forever; if too much time passes without a `getMore` call, it may be considered idle.

For example:

```text
Application receives batch #1 at 10:00
Application processes batch #1 for a very long time
No getMore within the idle timeout window
Server cleans up cursor
Application sends getMore at 10:15 -> cursor may no longer exist
```

This is why a server cursor should not be treated as a "read session" to be reused hours later.

### 9.2. `noCursorTimeout` Does Not Mean It Can Never Expire

MongoDB has the **`noCursorTimeout`** option (or corresponding driver API) to instruct the server not to apply the normal idle timeout to the cursor.

```javascript
const cursor = db.events
  .find({ customerId: "C01" })
  .noCursorTimeout();
```

This option **does not guarantee the cursor will live forever**:

- The session bound to the cursor can expire.
- The connection, server, router, or topology can change.
- The application can close the cursor.
- An administrator can close resources; server failures also destroy cursor context.

MongoDB uses **logical sessions**. In many configurations, a session that is inactive past the session timeout—often around **30 minutes** by default—can expire; associated cursors may also be cleaned up, even when `noCursorTimeout` is enabled. Therefore, do not rely on `noCursorTimeout` as the sole solution for workflows that spend a very long time processing each batch.

### 9.3. When to Consider Keeping a Cursor Open Long-Term?

A large export job may need to read for hours. However, choosing to keep a cursor alive for a very long time typically increases failure recovery complexity. Alternative strategies include:

- Reading at a steady pace, processing each document quickly, and keeping batch size moderate.
- Using a streaming pipeline to process data instead of collecting everything into RAM.
- Using **keyset pagination** on a stable key, saving the last processed checkpoint, and starting a new query when needed.
- Splitting the export into multiple retryable ID or date ranges.
- For point-in-time consistency requirements, designing an appropriate snapshot/transaction or data capture mechanism whose limits and costs are well understood.

`noCursorTimeout` should be used deliberately, paired with session management and resource cleanup, rather than turned on by default for every query.

## 10. Closing a Cursor with `close()` or `killCursors`

### 10.1. Natural Exhaustion

For a query with few results, the server may return everything in `firstBatch` with a cursor ID of 0. The driver does not need to send `getMore` or `killCursors` for a server cursor that has already finished.

For larger queries, after the final batch, `getMore` returns `cursor.id = 0`. The driver may still have the last documents in its local batch buffer for the application to finish reading.

### 10.2. Early Closure via Client API

In application code, use `close()` or the language/driver's resource management mechanism. The driver will attempt to free the cursor on the server if still needed.

Example in mongosh:

```javascript
const cursor = db.events.find({ customerId: "C01" }).batchSize(2);

if (cursor.hasNext()) {
  printjson(cursor.next());
}

cursor.close();
```

Closing after reading only one document helps avoid keeping a cursor open on the server once the application has decided to stop.

### 10.3. The `killCursors` Command at the Command Level

If working manually with a valid cursor ID, MongoDB provides the `killCursors` command:

```javascript
// Run only if initial.cursor.id is non-zero and the cursor still exists.
db.runCommand({
  killCursors: "events",
  cursors: [initial.cursor.id]
});
```

This illustrates how to close a server-side cursor in the appropriate database/namespace. Do not send `killCursors` for guessed cursor IDs or cursors belonging to other processes. Normal applications should let the **driver** handle this.

### 10.4. Cleanup in All Error Paths

A mid-run business logic error can also cause the client to stop reading. If managing manually, place cursor closure inside `finally` or `try-with-resources`:

```javascript
const cursor = db.events.find({ customerId: "C01" });

try {
  while (cursor.hasNext()) {
    const event = cursor.next();
    // Business processing; may throw an exception.
    print(event._id);
  }
} finally {
  cursor.close();
}
```

Closing a cursor is part of resource management, similar to closing a stream or file. However, closing an already-exhausted cursor is not an error; drivers handle that case cleanly.

## 11. Cursors and Pagination: Two Different Layers

Beginners often think "cursor = pagination". In reality, **a cursor exists to continue fetching batches of a single query**, whereas **pagination** is a contract for slicing data for a user or API.

### 11.1. Offset Pagination Using `skip` and `limit`

Consider an order-listing API with `pageSize = 20`:

```javascript
// Page 1
db.events.find({ customerId: "C01" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(0)
  .limit(20);

// Page 2
db.events.find({ customerId: "C01" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(20)
  .limit(20);
```

Each page call may create **a new cursor on the server**. This is not a `getMore` request on the same cursor across clicks of the user's "next page" button.

Advantage of offset pagination: simple, easy to provide page numbers and jump to page N.

Disadvantages:

- Large `skip` values can waste effort scanning/discarding many results before reaching the target position.
- If data is inserted or deleted between two requests, results may be duplicated or skipped.
- If the sort lacks a unique secondary tie-breaker key, documents with identical sort values may appear in an unstable order.

### 11.2. Keyset Pagination Using Sort Keys

For large datasets or continuous scroll feeds, **keyset (seek) pagination** is usually more suitable. Instead of asking to skip `N` documents, query the next page using a condition meaning "after the last key of the previous page".

Suppose the first page sorts by newest timestamp, then by `_id` to handle cases where multiple events share the same timestamp:

```javascript
db.events.find({ customerId: "C01" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
```

For the next page, record:

```javascript
const lastCreatedAt = ISODate("2026-11-01T08:10:00Z");
const lastId = "E003";
```

Then query documents that **come after** that key pair in descending order:

```javascript
db.events.find({
  customerId: "C01",
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    {
      createdAt: lastCreatedAt,
      _id: { $lt: lastId }
    }
  ]
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
```

This is **a new query**, not sending `getMore` on an old cursor. The application's page token can encode or sign the values of `lastCreatedAt`, `lastId`, and filter conditions, instead of exposing or holding onto a server cursor ID.

Recommended index for this pattern:

```javascript
db.events.createIndex({
  customerId: 1,
  createdAt: -1,
  _id: -1
});
```

The index gives the planner an option that supports filtering by customer and the ordering; the performance of the `$or` condition should be checked with `explain()` on real data.

### 11.3. Pagination Does Not Automatically Create a Consistent Snapshot

If new data is inserted between page reads, result ordering can change. Keyset pagination reduces duplicate/missing item issues caused by positional shifting compared to offset pagination, but it **does not freeze the entire dataset**:

- A document may be deleted before the user reaches the page containing it.
- A sort field such as `createdAt` may be updated.
- A document's filter condition status may change.
- Independent page requests may read data at different points in time.

If business logic requires a list "exactly as of a point in time", you must additionally choose an appropriate consistency/snapshot mechanism or use an export with checkpoints and clear invariants.

### 11.4. Why Not Use MongoDB's Cursor ID as a Page Token?

A cursor ID:

- Has a short lifetime and can expire due to idle/session timeout.
- Is tied to the server/router and the context that created the cursor.
- Is not a durable token that can resume on any machine after failover.
- Does not identify a stable data position when queries or business requirements change.

Therefore, **API pagination should define its own tokens** from meaningful fields in the data ordering, with validation and access-control checks. Server cursors may still be used underneath to fetch batches for **a single API request**.

## 12. Tailable Cursors and `getMore` When No New Data Exists Yet

Not every cursor follows "read to the end and close". MongoDB supports **tailable cursors** for suitable use cases on **capped collections**, allowing applications to keep observing newly inserted data.

With a standard cursor, when data runs out, the server returns ID = 0. With a tailable cursor, **having no documents temporarily** does not necessarily mean the read stream has ended permanently.

### 12.1. What Is a Tailable Cursor?

A tailable cursor is similar to "tailing" a log file:

```text
Tailable cursor reads existing records
                |
                v
       No new records yet
                |
        Cursor can remain open
                |
                v
  New records arrive -> getMore returns more data
```

Differences from queries fetching a fixed list:

- Used in contexts supporting tailable behavior, typically capped collections.
- Reading order and waiting for additional data have specific constraints.
- Not a general-purpose replacement for every form of change tracking on every collection.

### 12.2. `awaitData` and Empty Batches

In certain tailable cursor mechanisms, the **`awaitData`** option allows `getMore` to wait for a period of time when no new data is available yet, instead of returning immediately.

A `getMore` response with **`nextBatch: []` and a non-zero cursor ID** can express "there is no new data at this moment, but the cursor is still alive".

Therefore:

> **Do not use an "empty batch" as the sole condition to conclude a cursor is exhausted.** You must distinguish the cursor ID state and the type of cursor in use.

When working with change streams, the driver also uses a cursor- and `getMore`-based mechanism to retrieve subsequent changes. Change streams additionally have **resume tokens** and their own recovery rules; do not treat a resume token as a server cursor ID.

### 12.3. A Change Stream Differs from a Pagination Cursor

```javascript
// Run only on deployments that support change streams.
const stream = db.events.watch();

// Wait for new events; this is a continuous observation example.
while (stream.hasNext()) {
  printjson(stream.next());
}
```

The stream above can continue long-term until closed or encountering an error condition. It is not "the next page of 20 existing events". When an application builds a change stream consumer, it must manage resume tokens, handle duplicate events, monitor lag, and clean up resources.

## 13. Cursors, Read Concern, and Data Changes During Reading

A cursor reading multiple batches can span a period while other applications insert, update, or delete documents. This leads to the question: **Do all batches represent a fixed snapshot of the data?**

Normally, **you must not assume** that solely because it is the same cursor. Visibility of changes depends on read concern, topology, query type, stages, session, and transaction context.

### 13.1. Cursor Lifecycle Does Not Replace Consistency Guarantees

```text
Batch 1 returns documents A, B
              |
         Another application writes data
              |
Batch 2 returns subsequent results
```

From this diagram, you cannot conclude with certainty that batch 2 sees the "exact same" snapshot as batch 1, or that all new writes will appear immediately. Applications must select a consistency level based on actual needs.

### 13.2. Sessions, Transactions, and Snapshots

A transaction with an appropriate read concern can provide a consistent view along transaction boundaries. However, long transactions carry operational costs, time limits, and resource constraints; do not use a transaction lasting hours just to hold a massive export cursor.

If the goal is an end-of-day report, designs such as data snapshots, period-closing states, or checkpoints on immutable keys may be more suitable depending on requirements.

### 13.3. Reading from Secondaries

Drivers can select a secondary based on `readPreference`. The cursor and associated `getMore` commands must continue in the proper read context. A secondary may lag behind the primary; `readConcern: "majority"` also does not automatically mean "seeing the latest writes on the primary". This is a **replication and consistency** issue, not batch size control.

## 14. Aggregate Queries Also Have Cursors

Not only `find()` returns a cursor. With `aggregate()`, the driver can also fetch results in multiple batches:

```javascript
const cursor = db.events.aggregate(
  [
    { $match: { customerId: "C01" } },
    { $sort: { createdAt: 1, _id: 1 } },
    { $project: { eventType: 1, createdAt: 1 } }
  ],
  { cursor: { batchSize: 2 } }
);

while (cursor.hasNext()) {
  printjson(cursor.next());
}
```

In mongosh, aggregate calls and cursor configuration may be supported by the driver/shell through specific API parameters; the example above expresses the intent to use a cursor with batch size 2.

### 14.1. Small Batches Do Not Eliminate Blocking Stages

Consider the pipeline:

```javascript
db.events.aggregate([
  { $match: { customerId: "C01" } },
  {
    $group: {
      _id: "$eventType",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
```

`$group` must group documents to determine counts. `$sort` on the newly computed `count` may also need to hold many intermediate results. Consequently, returning the first batch may have to **wait quite a while** even if `batchSize` is only 2.

In other words:

- **Batching** controls **result delivery**.
- **Query execution** determines the work required to **produce results**.

A pipeline may produce partial results early or have to process vast amounts of data before yielding the first document; this depends on the stages and optimization capabilities.

### 14.2. `$limit` Is Not Synonymous with `batchSize`

```javascript
db.events.aggregate([
  { $match: { customerId: "C01" } },
  { $sort: { createdAt: -1 } },
  { $limit: 3 }
]);
```

`$limit: 3` only allows three documents to pass downstream in the pipeline; whether those results are received in one batch or multiple batches is a separate matter. For pagination, `$limit` and sort order belong to **result semantics**, whereas batch size belongs to **how results are transported**.

## 15. Monitoring and Diagnosing Cursors in Operations

Do not guess that an application is slow simply because `getMore` appears many times. An investigation usually begins by identifying **where the latency originates**.

### 15.1. Breaking Down Latency

```text
Total application data-read time
    ├── waiting for server selection / acquiring connection
    ├── server execution time to return firstBatch
    ├── batch transmission and decoding time
    ├── application document processing time
    ├── getMore round-trips (server + network)
    └── wait time due to backpressure / resources
```

If the application takes a long time to process each document, a long-lived cursor is not necessarily caused by slow MongoDB execution. Conversely, if the server has to run an unindexed scan, increasing batch size will not remove the root cause.

### 15.2. Using `explain()` to Inspect Query Work

```javascript
db.events.find({ customerId: "C01" })
  .sort({ createdAt: 1, _id: 1 })
  .explain("executionStats");
```

Signals such as `COLLSCAN`, `IXSCAN`, `FETCH`, keys/documents examined, and documents returned show whether the server is doing too much work. However, query `explain()` **does not fully describe** per-document processing time in the application or every `getMore` turn during an actual export.

A suitable index might be:

```javascript
db.events.createIndex({
  customerId: 1,
  createdAt: 1,
  _id: 1
});
```

This index matches the equality filter on `customerId` and the ascending `createdAt, _id` order. Whether the planner uses it still depends on data distribution and execution conditions.

### 15.3. Observing `getMore` Commands

Observability sources may include:

- **Driver command monitoring:** tracks commands such as `find`, `aggregate`, and `getMore` along with duration, error counts, and frequency.
- **Database profiler / diagnostic logs:** in appropriate environments and with proper permissions, helps analyze slow commands, including fetching subsequent data.
- **`serverStatus` / cursor metrics:** depending on the version, provides figures on open cursors, timed-out cursors, and related health indicators.
- **`currentOp` or `$currentOp`:** inspects certain active operations when monitoring privileges are available.
- **Application metrics:** processed document count, total bytes, throughput, processing time per batch, and retry counts.

Do not enable high-level profiling on production arbitrarily; monitoring tools can incur overhead and require administrative privileges.

### 15.4. Notable Warning Signs

| Observation | Hypothesis to verify |
|---|---|
| Many `getMore` calls, each batch very small | Small batch size, large documents, or workload batch-return mechanics |
| Slow right before `firstBatch` | Server query plan, blocking stages, server selection, or connection acquisition |
| Fast `firstBatch` but slow total export | Many round-trips, per-document processing, network speed, or throttling |
| Cursor not found error | Cursor timeout, closed cursor, expired session, or topology change |
| Very large number of open cursors | Application not closing early, many concurrent queries, or long-lived consumers |
| Application RAM grows with record count | Accumulating into a list/array instead of streaming processing |
| Export duplicates/skips after retry | Unstable checkpoint or faulty pagination logic |

A single metric alone is insufficient to draw conclusions. For example, a high open cursor count may be normal when many active change streams exist; always cross-check against design and actual load.

## 16. Mid-Stream Failures: Can an Old Cursor Be Resumed?

Suppose an application has processed 10,000 documents, and then a server failover or network drop occurs while sending `getMore`. There are distinct issues to separate:

1. **Transient errors may be handled by the driver:** depending on the operation, driver, and session context, some errors have specific retry rules.
2. **The old cursor is no longer valid:** the client cannot arbitrarily take a cursor ID and resume it on any server.
3. **Partial results have already been processed:** creating a new query from the beginning without a checkpoint may reprocess documents.

Therefore, for long-running processes, design **application-level recoverability**:

```text
Read batch
    |
    v
Process documents in stable key order
    |
    v
Write checkpoint of last successfully processed document
    |
    +---- error ----> Open new query from checkpoint
    |
    v
Continue
```

The checkpoint does not need to be a cursor ID; it can be a `(createdAt, _id)` pair or a unique monotonically increasing key matching the read order. If processing has external side effects (writing files, calling APIs, payments), define how to **prevent duplicate processing** on retry.

**Important condition:** only persist a checkpoint after the corresponding data has been successfully processed according to business rules. If you save the checkpoint first and the process crashes, documents can be skipped. If processing succeeds before the checkpoint is saved, a rerun may encounter duplicate documents; idempotency handling is required.

## 17. Common Misconceptions

| Misconception | Reality |
|---|---|
| `find()` always returns all results in one network call | MongoDB typically returns a first batch and uses `getMore` for subsequent batches |
| `batchSize(100)` means the query only finds 100 documents | `batchSize` mainly controls transfer batches, while `limit` restricts total results |
| Every `next()` is a `getMore` command | Drivers usually read from a pre-buffered batch first |
| `getMore` creates a completely new query like `find` | It continues an existing server cursor |
| The first batch always has exactly 101 documents | The default has byte limits and varies by context; it can be fewer or the cursor can finish immediately |
| An empty batch definitely means no more data | Tailable/change-stream cursors can remain alive even when no new data has arrived yet |
| Cursor ID is a durable API pagination token | Cursor ID is a temporary, context-dependent server resource |
| `toArray()` still uses little RAM because MongoDB batches | Collecting all documents into an array increases application RAM usage |
| `noCursorTimeout` keeps a cursor alive forever | Sessions, server errors, topology changes, or explicit closes can still end it |
| Increasing batch size always speeds up queries | It can reduce round-trips, but does not eliminate scans/sorts or slow app processing |
| One cursor reading multiple batches guarantees a snapshot | Consistency must be designed using appropriate read concerns/sessions/transactions |
| `skip(1000)` fetches the 1,000th batch of the same cursor | Offset pagination runs a new query instructed to discard leading results |
| No need to close cursors when stopping early | Closing frees server and client resources |

## 18. Practice Exercises

### Exercise 1 — Observing the First Batch and `getMore`

With the six events from Section 2:

1. Send a `find` command filtering `customerId: "C01"` with `batchSize: 2`.
2. Inspect `cursor.firstBatch`, `cursor.id`, and `cursor.ns`.
3. If the cursor ID is non-zero, send `getMore` for the same collection with batch size 2.
4. Continue reading until the cursor ID equals 0.
5. Explain why five documents can be received across three batches.

Distinguish **documents per batch**, **total documents in the query**, and **number of commands sent**.

### Exercise 2 — `batchSize` vs. `limit`

Try predicting the results of three queries:

```javascript
// A
db.events.find({ customerId: "C01" }).batchSize(2);

// B
db.events.find({ customerId: "C01" }).limit(2);

// C
db.events.find({ customerId: "C01" })
  .limit(3)
  .batchSize(2);
```

Which query can return at most two documents? Which can return all five? Can query C require more than one batch? Add `sort` if you want to determine the exact order of documents selected by `limit`.

### Exercise 3 — Identifying High-RAM Scenarios

Given two hypothetical Java approaches:

```java
// Approach A: collect all documents before processing.
List<Document> all = events.find().into(new ArrayList<>());
for (Document event : all) {
    processEvent(event);
}

// Approach B: process one document at a time, closing the cursor when done.
try (MongoCursor<Document> cursor = events.find().iterator()) {
    while (cursor.hasNext()) {
        processEvent(cursor.next());
    }
}
```

Explain the difference in application memory usage and the impact of `batchSize` on each approach. Which approach is better suited for exporting millions of documents?

### Exercise 4 — Stopping Early and Closing the Cursor

A worker only wants to process at most 50 events from a very large collection. Write code in Java or Node.js that:

- Uses `limit(50)` if business logic permits.
- Iterates through the cursor.
- Guarantees closing the cursor even if `processEvent` throws an error.

Explain why you should not rely on cursor timeout to clean up resources.

### Exercise 5 — Building an API Pagination Endpoint

Design the endpoint:

```text
GET /events?customerId=C01&pageSize=20&after=...
```

Propose:

1. A sort order including `createdAt` and `_id`.
2. The fields stored in the `after` token.
3. The filter for fetching the next page under descending sort.
4. An index supporting the search condition.
5. Why the token should not directly contain a server cursor ID.
6. How the application detects `hasNext`, such as reading up to `pageSize + 1` documents.

### Exercise 6 — Data Changing Between Pages

An application reads page 1 and then reads page 2 30 seconds later. During that interval:

- A new event is inserted with the newest `createdAt`.
- An older event is deleted.
- Another event has its `createdAt` modified.

Analyze the risk of duplicates/skips under offset pagination vs. keyset pagination. Can keyset solve all cases? When is a snapshot needed?

### Exercise 7 — Why a Small Batch Size Does Not Speed Up a Pipeline

An aggregation has `$match`, `$group`, and `$sort` over millions of events. The application sets batch size 1 yet still waits a long time before the first document arrives.

Explain:

- Which stages have to do heavy work before returning results?
- What does batch size actually restrict?
- Can this be improved with indexes, early filtering, projection, or pre-aggregated summaries?
- What information should you look for using `explain()`?

### Exercise 8 — Error Handling and Checkpoints

A worker reads in `(createdAt, _id)` order, has processed up to `E050`, and encounters a `getMore` error:

1. Why shouldn't you guess a cursor ID to resume?
2. Which checkpoint must be saved to open a new query?
3. If sending an email succeeded before the checkpoint was saved, what could happen on rerun?
4. What needs to be done to ensure correct business outcomes under duplicate processing?

## 19. Summary of Key Principles

**A cursor is a mechanism to continue reading a query**, not a list fully loaded into RAM and not a durable pagination token. The driver manages the client-side cursor; MongoDB can maintain a server-side cursor and cursor ID to continue across multiple batches.

**`firstBatch` and `nextBatch` are batches of documents transmitted to the client.** When the current batch is exhausted and the server cursor is still alive, the driver sends `getMore`. A cursor ID of 0 indicates there is no remaining server-side cursor to continue.

**`batchSize`, `limit`, and API pagination are three separate scopes.** Batch size controls data transferred per round-trip; limit controls the number of result documents; pagination determines how an application splits data for users.

**Cursors have lifecycles and resource costs.** Close cursors when stopping early, understand cursor/session timeouts, do not assume `noCursorTimeout` solves everything, and use streaming when result sets are large.

**Batch tuning does not replace query or consistency optimization.** Indexes, sorts, pipelines, read concerns, topology, and document processing logic still govern execution time and data correctness. For long-running processes or multi-request pagination, design stable sort keys and recoverable checkpoints rather than depending on an indefinitely living server cursor.
