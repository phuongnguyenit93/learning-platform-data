# Sequential Reading, Closing Cursors, and Handling Expired Cursors in MongoDB

When a MongoDB query matches thousands or millions of documents, the application should not load the entire result set into memory just to process each record. MongoDB uses **cursors** to let the client receive and iterate through documents one by one, typically via **batches** transferred between the server and driver. This sequential traversal fits reporting, streaming data processing, data exports, and many high-volume read workloads.

However, a cursor is a resource with a lifecycle. If a program stops reading midway without closing the cursor, the server may have to retain query state until the resource is freed or expires. If a program waits too long between reads, the cursor can expire and a subsequent batch fetch command may fail. Therefore, you must understand all three operations: **sequential reading**, **timely cursor closure**, and **safe recovery when a cursor is no longer valid**.

In this lesson, we practice with **mongosh** and the **MongoDB Java Sync Driver**, then apply a checkpointing mechanism for long-running data processing. This covers **standard cursors**; tailable cursors, Change Streams, and other pagination approaches have specific rules that will be distinguished where necessary.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain how a MongoDB query creates a cursor, returns the first batch, and uses the **getMore** command to load additional data.
- Iterate a cursor using **hasNext()**, **next()**, loops, and **forEach()**; understand why **toArray()** is unsuitable for very large result sets.
- Distinguish **batchSize**, **limit**, **sort**, and **skip**; know that batchSize only controls batched delivery of results.
- Proactively call **close()** in mongosh and **try-with-resources** in Java to avoid holding unnecessary resources.
- Identify expired cursors caused by inactivity, closure, kill commands, expired sessions, or interrupted connections.
- Design error-recovery re-reads using a processed marker (checkpoint), with stable ordering and duplicate-handling principles.

## 2. What Is a Cursor and Why Is It Needed?

Suppose an **orders** collection has one million documents. A query:

~~~javascript
db.orders.find({ status: "PAID" })
~~~

does not mean all matching documents are always sent to the client at once. MongoDB may return a **first batch** along with a server-managed cursor identifier. When the client finishes iterating the current batch, the driver can issue a **getMore** command to receive the next batch. This continues until all results have been read, the cursor is closed, or an error occurs.

~~~text
Application / mongosh                MongoDB server
       |                                   |
       |-------- find(query) ------------->|
       |<------- firstBatch + cursorId ----|
       |                                   |
       |   Read documents in firstBatch    |
       |                                   |
       |-------- getMore(cursorId) ------->|
       |<------- nextBatch + cursorId -----|
       |                                   |
       |   Read documents in nextBatch     |
       |                                   |
       |-------- getMore(cursorId) ------->|
       |<------- final batch / id = 0 -----|
       |                                   |
       |   Cursor has been exhausted       |
       |                                   |
~~~

**firstBatch**, **nextBatch**, and **cursorId** are common components in protocol-level command responses. Java libraries usually abstract away `getMore` handling and provide a familiar iteration API, such as **MongoCursor.next()**.

### 2.1. A Cursor Is an Iteration Pointer, Not a Preloaded List

Example in mongosh:

~~~javascript
const cursor = db.orders.find({ status: "PAID" });
~~~

The **cursor** variable is an object for iterating results. Depending on the driver and operation, sending the query to the server may happen when the client begins fetching results rather than when constructing the filter object. Do not equate holding a cursor object with already having all documents in memory.

### 2.2. Cursors Require Client Resources and May Hold Server State

The server may retain state related to results, traversal position, and the query plan of an open cursor. The client also manages received batches, the cursor object, BSON decoding state, and related resources. When a cursor is no longer needed, closing it reduces resources held on both sides.

This matters when an application handles many concurrent requests. One abandoned cursor per request can accumulate into many cursors waiting to expire.

### 2.3. Not Every Query Keeps a Long-Lived Server Cursor

If a query has few results and all of them are returned in the first batch, the server-side cursor may **finish immediately**. By contrast, a query with many results or partial reading is likely to leave an open cursor. Therefore, programs should close cursors after use even if test datasets are sometimes tiny.

## 3. Preparing Practice Data

The examples below run in **mongosh** connected to a running MongoDB instance. Use a dedicated learning database:

~~~javascript
use cursor_lab
~~~

If the collection does not exist yet, create 24 documents with a unique, ascending **seq** field:

~~~javascript
const docs = Array.from({ length: 24 }, (_, i) => {
  const n = i + 1;
  return {
    _id: "EVT-" + String(n).padStart(4, "0"),
    seq: n,
    category: n % 2 === 0 ? "SYSTEM" : "USER",
    message: "Event " + n,
    processed: false
  };
});

db.events.insertMany(docs);
~~~

Create an index to support ordered reading and checkpoint-based queries:

~~~javascript
db.events.createIndex({ seq: 1 }, { unique: true });
~~~

If you re-run **insertMany** on already-created data, the operation may report duplicate `_id` errors; that is normal behavior. During practice, run the data creation command once on a fresh collection or use a different test database.

Run a check:

~~~javascript
db.events.countDocuments({});
db.events.find(
  {},
  { _id: 1, seq: 1, category: 1 }
).sort({ seq: 1 }).limit(5);
~~~

Expected output shows 24 documents. The first five documents after sorting have **seq from 1 to 5**. This dataset lets you trace each traversal step without reading a huge result set.

## 4. Sequential Reading with a Cursor in mongosh

### 4.1. hasNext() and next()

A typical iteration loop:

~~~javascript
const cursor = db.events
  .find({}, { _id: 1, seq: 1, message: 1 })
  .sort({ seq: 1 })
  .batchSize(5);

try {
  while (cursor.hasNext()) {
    const doc = cursor.next();
    print(doc.seq + " - " + doc.message);
  }
} finally {
  cursor.close();
}
~~~

Here:

1. **find()** specifies the filter and projection.
2. **sort({seq: 1})** requests ascending traversal by `seq`.
3. **batchSize(5)** suggests fetching results in batches of an appropriate maximum document count, subject to other server limits.
4. **hasNext()** checks whether more documents remain to read; when needed, it can trigger the client to request the next batch.
5. **next()** retrieves the next document.
6. **finally** ensures **close()** is called even if document processing throws an error.

This is an example of **sequential reading**: the program processes one document at a time without allocating an application-built array of 24 documents from the results.

### 4.2. Do Not Call next() Unconditionally

In the standard model, once a cursor is exhausted, calling `next()` again can throw an error because no document remains. Use `hasNext()` to check and only call `next()` when a value exists. In some iterator APIs, `hasNext()` may also wait for the server to return the next batch, so do not assume `hasNext()` is always an instant local check.

### 4.3. forEach() Helps Process Each Document

A concise alternative:

~~~javascript
const cursor = db.events
  .find({ category: "SYSTEM" })
  .sort({ seq: 1 })
  .batchSize(4);

try {
  cursor.forEach(doc => {
    print("SYSTEM event: " + doc.seq);
  });
} finally {
  cursor.close();
}
~~~

The snippet above reads only events with **even seq** in the sample data, i.e., 12 documents. This iteration style is convenient for simple tasks; if you want to break early on a condition, write checkpoints, or handle per-document errors individually, a **while + hasNext/next** loop can be clearer.

### 4.4. toArray() Differs from Sequential Iteration

~~~javascript
const allEvents = db.events.find().toArray();
~~~

The command above puts the entire result set into **an array in client memory**. Convenient for 24 test documents, yet for millions of documents or large payloads, it can consume massive memory and pressure the application.

| Read approach | Characteristics | Suitable for |
|---|---|---|
| while + next() | Processes one document at a time | Large datasets, streaming business logic |
| forEach() | Callback per document | Simple traversal and processing |
| toArray() | Collects all results | Small datasets of known bounded size |
| findOne() | Fetches one matching document | Only one record needed |
| find().limit(N) | Caps returned results at N documents | Previews or partial processing |

The fact that the server sends results in batches **does not protect the application from running out of memory** if application code subsequently pushes every document into an unbounded list/array.

## 5. How Do batchSize, limit, sort, and skip Differ?

### 5.1. batchSize Controls Batched Delivery

~~~javascript
db.events.find().sort({ seq: 1 }).batchSize(5);
~~~

With 24 documents, the server/driver may take multiple batch fetches to return all data. **batchSize(5) does not mean returning only 5 documents total.** The actual number of documents in each batch is also subject to response limits and server handling; do not expect every batch to contain exactly 5 documents.

Lowering `batchSize` can increase network round trips. Raising `batchSize` can reduce round trips but requires more client buffer memory. Choose based on document size, processing speed, and network latency.

### 5.2. limit Caps Total Document Count

~~~javascript
db.events
  .find()
  .sort({ seq: 1 })
  .limit(5);
~~~

The query above requests at most **5 documents** in the result. Meanwhile, **batchSize(5)** still allows reading all 24 documents sequentially when continuing iteration.

In direct server communication, `limit` and `batchSize` have coordination rules during cursor creation/`getMore`; the key takeaway at the application level is that **limit controls the total number of records to retrieve, whereas batchSize controls batching**.

### 5.3. sort Determines Order, Not batchSize

~~~javascript
db.events
  .find({ category: "USER" })
  .sort({ seq: 1 })
  .batchSize(3);
~~~

Batches may be split into multiple parts, yet the result ordering still follows the query's **sort({seq: 1})** specification. **batchSize does not create ordering**, and unspecified ordering can change with query plans and data state.

### 5.4. skip Is Not a Strong Resumption Mechanism for Large Datasets

~~~javascript
db.events
  .find()
  .sort({ seq: 1 })
  .skip(10)
  .limit(5);
~~~

On an immutable sample dataset, this fetches documents with `seq` 11–15. However, if the dataset changes while paginating, skip positions can shift, causing the application to see duplicates or miss records. With large offsets, the server also has to walk past many results before reaching the target position, increasing cost.

When you need reliable resumption after errors, consider **keyset pagination** on a stable ordered key such as `seq` or a `(createdAt, _id)` pair; a later section illustrates this in detail.

## 6. Proactively Closing Cursors

A cursor may be freed automatically once all results are iterated, but that does not mean a program can ignore resource management.

### 6.1. Closing When Only Partial Results Are Needed

Suppose an application only needs to inspect the first three events and then stop:

~~~javascript
const cursor = db.events
  .find({}, { seq: 1, message: 1 })
  .sort({ seq: 1 })
  .batchSize(5);

try {
  let count = 0;
  while (count < 3 && cursor.hasNext()) {
    printjson(cursor.next());
    count++;
  }
} finally {
  cursor.close();
}
~~~

Here unread results may still remain. **close()** signals that the program no longer needs the cursor. When a server-side cursor remains open, the driver can issue a **killCursors** request to free associated resources. Closing is meaningful even when you have no intention of reading further.

### 6.2. Why Use finally?

If document processing encounters a mid-stream error:

~~~javascript
function processEvent(doc) {
  if (doc.seq === 3) {
    throw new Error("Simulated processing error");
  }
  print(doc.seq);
}
~~~

then the loop may exit before exhausting the cursor. Placing `close()` inside `finally` ensures it still gets called:

~~~javascript
const cursor = db.events.find().sort({ seq: 1 });

try {
  while (cursor.hasNext()) {
    processEvent(cursor.next());
  }
} finally {
  cursor.close();
}
~~~

**Do not close only on the success path**, because network errors, logic errors, or user cancellations can all terminate the loop early.

### 6.3. Closing a Cursor Differs from Closing a Connection

Closing a **cursor** frees resources for a single query. Closing a **MongoClient** terminates client resource usage, including connection pools and background tasks. In a Java server application, you typically **reuse MongoClient** across many requests and **close each MongoCursor** after each read.

Do not create a new `MongoClient` per document just to avoid cursor management; that increases connection overhead and complicates operations.

## 7. Iterating and Closing Cursors in the MongoDB Java Sync Driver

In Java, the MongoDB Sync Driver provides **MongoCollection**, **FindIterable**, and **MongoCursor**. A **FindIterable** describes how to fetch results, while **MongoCursor** is used for sequential iteration. **MongoCursor** implements resource closing, so it works with **try-with-resources**.

The example requires a project with the appropriate **org.mongodb:mongodb-driver-sync** dependency and an environment variable **MONGODB_URI** pointing to MongoDB.

### 7.1. Complete Example: Ordered Reading and Automatic Closure

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

public class SequentialCursorReader {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> events = client
                    .getDatabase("cursor_lab")
                    .getCollection("events");

            try (MongoCursor<Document> cursor = events.find()
                    .projection(Projections.include("seq", "message"))
                    .sort(Sorts.ascending("seq"))
                    .batchSize(5)
                    .iterator()) {

                while (cursor.hasNext()) {
                    Document doc = cursor.next();
                    int seq = doc.getInteger("seq");
                    String message = doc.getString("message");
                    System.out.println(seq + " - " + message);
                }
            }
        }
    }
}
~~~

In this program:

1. **MongoClient** creates and manages connections according to driver configuration.
2. **events.find()** builds the query.
3. **sort()** specifies the result ordering.
4. **batchSize(5)** sets the desired batch size.
5. **iterator()** returns a `MongoCursor` for iteration.
6. **try-with-resources** calls `close()` upon exiting scope, even if `hasNext()`, `next()`, or document processing throws an exception.

The sample closes `MongoClient` when the CLI program ends. In long-running web/Spring Boot applications, `MongoClient` is normally managed at the application or dependency-injection level; **do not close the client after every query**. You still must close the cursor within the scope of each read.

### 7.2. Stopping Early While Still Releasing the Cursor

~~~java
try (MongoCursor<Document> cursor = events.find()
        .sort(Sorts.ascending("seq"))
        .batchSize(10)
        .iterator()) {

    int processed = 0;
    while (cursor.hasNext() && processed < 3) {
        Document event = cursor.next();
        System.out.println(event.getInteger("seq"));
        processed++;
    }
}
~~~

The loop reads at most three documents. Upon exiting the `try` block, the driver closes the cursor. This case is especially important because the server may still hold many unsent documents.

### 7.3. Avoid into(new ArrayList<>()) for Unbounded Data

~~~java
// Suitable only when the data size is known beforehand to be small.
List<Document> allEvents = events.find()
        .into(new ArrayList<>());
~~~

**into()** collects all returned documents into a Java collection. The driver may load results in batches at the wire layer, yet the final `List` can still grow large enough to exhaust memory.

If the task is reading millions of documents and processing each record, use **MongoCursor in try-with-resources** or a reactive API fitting the application's architecture, with backpressure control.

## 8. What Is an Expired Cursor?

An open cursor is not guaranteed to live forever. MongoDB has mechanisms to reclaim inactive cursors to prevent resource leaks.

### 8.1. Cursor Inactivity Duration

In common configurations, MongoDB may close a **cursor that has been inactive for about 10 minutes** (the default for idle cursors governed by timeout management). If a program reads one batch and pauses for a long time before requesting the next batch, the server may treat the cursor as abandoned and close it.

Example scenario:

~~~text
T0      Client receives 1 batch, server cursor still remains
T1      Client processes batch very slowly or sits idle
T2      Idle duration exceeds server threshold
T3      Server closes cursor per timeout policy
T4      Client attempts getMore with old cursorId -> error
~~~

The exact threshold, cleanup schedule, and behavior depend on MongoDB configuration, version, and cursor type. The **10-minute** figure is a common default for understanding the mechanism, not a guarantee that every cursor closes at exactly second 600.

**Important:** long processing inside client code does not mean the cursor is actively communicating with the server. If the client does not send a session/cursor refresh operation during processing, the server may consider the cursor or session idle.

### 8.2. Session Timeout Can Also Cause Cursor Closure

MongoDB uses **logical sessions** to track many client operations. By common default, a session inactive for around **30 minutes** can expire. When a session expires, the server can close cursors associated with that session.

Therefore, distinguish:

| Cause | Concept | Consequence |
|---|---|---|
| Cursor idle timeout | Cursor unused for the configured server policy duration | Server may close cursor |
| Logical session timeout | Client session lacks refresh activity for too long | Cursors belonging to the session may be closed |
| Client explicitly calls `close()` | Application read enough or canceled operation | Cursor is released |
| Server `killCursors` | Administrative or explicit cursor cancellation | Subsequent `getMore` cannot use old cursor |
| Network error / connection change / failover | Client loses previous access path to results | Cursor may be unresumable depending on error type |
| Exhausted all results | Cursor has no more documents to return | Cursor completes normally |

A cursor closing when all results are read **is not an error**. By contrast, an error while unread data still remains can leave processing incomplete. Applications need to distinguish these two cases.

### 8.3. noCursorTimeout Does Not Make a Cursor Live Forever

MongoDB supports the **noCursorTimeout** option to bypass the normal idle timeout for cursors. In mongosh, you can use:

~~~javascript
const cursor = db.events
  .find()
  .sort({ seq: 1 })
  .noCursorTimeout();

try {
  while (cursor.hasNext()) {
    printjson(cursor.next());
  }
} finally {
  cursor.close();
}
~~~

In the Java Sync Driver, `FindIterable` can be configured:

~~~java
try (MongoCursor<Document> cursor = events.find()
        .sort(Sorts.ascending("seq"))
        .noCursorTimeout(true)
        .iterator()) {

    while (cursor.hasNext()) {
        processEvent(cursor.next());
    }
}
~~~

Here **processEvent** represents application-defined processing logic.

**Remember:** `noCursorTimeout` **does not exempt the cursor from logical session expiration**. If the session is deemed inactive for too long, the cursor can still be closed. Additionally, server restarts, `killCursors`, network errors, and other failures can still invalidate the cursor.

Consequently, `noCursorTimeout` is not a primary strategy to guarantee a multi-hour batch job never loses progress. If long reads are truly necessary, split work into resumable segments with checkpoints, manage sessions per server/driver guidance, and ensure resources are closed.

### 8.4. When Should You Avoid noCursorTimeout?

If an application has a bug that leaks cursors, `noCursorTimeout` risks keeping cursors holding resources longer than standard policy allows. In web apps with high request volume or batch jobs that are frequently canceled, this increases cursor accumulation risk.

Before enabling this option, understand per-batch processing duration, actual idle gaps, session timeout, and cursor closure behavior. Many workloads improve simply by **reducing work between `getMore` calls**, **processing in independent pages**, or **writing checkpoints**.

## 9. Recognizing Closed or Non-Existent Cursor Errors

Suppose the client holds a `cursorId` that the server has already cleaned up. When the driver requests more data, the **getMore** command may fail with an error such as **CursorNotFound** (commonly MongoDB error code **43**). MongoDB drivers may surface this as a cursor-related exception or `MongoException`, depending on library version and situation.

Notable symptoms:

- The application reads several batches, then fails in **hasNext()** or **next()**, even though the same filter worked earlier.
- Logs/exceptions indicate **cursor id no longer exists**, cursor was killed, or operation was interrupted.
- The job spends too long processing each batch between `getMore` turns.
- The client already closed the cursor or the session ended, yet code still tries to read.
- Network disconnection, server restart, or topology change prevents the cursor from continuing.

Not every cursor read failure is a timeout. Permission errors, BSON decoding errors, server unavailability, or invalid query conditions can also occur. When handling errors, inspect the **exception type, error code, and operational context**, rather than retrying all errors identically.

### 9.1. Do Not Continue Reading an Invalidated Cursor

Once the server no longer holds the `cursorId`, the client cannot simply resume **that same cursorId**. An appropriate response typically is:

1. Record the position successfully processed so far.
2. Close the old cursor on the client side.
3. Evaluate whether the error is retryable.
4. Create a **new query** starting after the last processed position.
5. Continue with duplicate-processing safeguards where needed.

Recreating a cursor with the original filter without bounding the resumption point can re-read all documents from the start. If earlier documents already sent emails, wrote files, or updated external systems, the consequence can be duplicated actions.

### 9.2. Do Not Treat Every Error as CursorNotFound

| Situation | Appropriate handling |
|---|---|
| Cursor finished reading normally | Complete task, close resources |
| `CursorNotFound` after idle period | Evaluate opening a new query from checkpoint |
| Client explicitly called `close()`, then code called `next()` | Fix object lifecycle; do not retry indefinitely |
| Transient network error | Bounded retry, verify idempotency and resumption point |
| Bad filter or BSON decode error | Fix data/code; retrying verbatim will likely repeat the error |
| Server overloaded | Monitor, throttle, backoff, and inspect operations |
| Missing permissions or misconfiguration | Fix permissions/configuration before re-running |

Cases of **failure without progress tracking or checkpoints** must be designed explicitly; never assume you can resume cleanly from the exact old position.

## 10. Recovering After Cursor Expiration Using Checkpoints

A **checkpoint** records which portion of data has been successfully processed. If an old cursor cannot continue, the application uses the checkpoint to construct a **new query** fetching only documents after the recorded position.

In our lesson dataset, the **seq** field is ascending and has a **unique index**. This provides a convenient key for experimenting with resumption:

~~~text
First cursor:     seq = 1, 2, 3, 4, 5, 6, ...
                                  |
                         Processed up to seq=4
                                  |
                      Timeout / network error
                                  |
                                  v
                      Checkpoint lastSeq=4
                                  |
                                  v
New cursor:       find({ seq: { $gt: 4 } }).sort({ seq: 1 })
                                  |
                                  v
                     seq = 5, 6, 7, 8, ...
~~~

The **$gt: lastSeq** condition skips records already processed up to `lastSeq`, while **sort({seq: 1})** maintains deterministic ordering.

### 10.1. Iterating Across Independent Pages in mongosh

Example reading pages of at most five documents:

~~~javascript
let lastSeq = 0;
const pageSize = 5;

while (true) {
  const page = db.events
    .find(
      { seq: { $gt: lastSeq } },
      { _id: 1, seq: 1, message: 1 }
    )
    .sort({ seq: 1 })
    .limit(pageSize)
    .toArray();

  if (page.length === 0) {
    break;
  }

  for (const event of page) {
    print("Processed " + event.seq);
    lastSeq = event.seq;
  }
}
~~~

In this example, **toArray() collects only one page of at most five documents**, not the entire collection. Each iteration creates a bounded query and a resumption point, removing the need to hold a single long-lived cursor across the entire batch job.

This example demonstrates the **mechanism**. The `lastSeq` variable resides in mongosh memory; if the process terminates, the variable is lost. For real recoverable jobs, persist the checkpoint to durable storage after completing work for the corresponding document.

### 10.2. When Is It Safe to Advance the Checkpoint?

Suppose processing an event includes writing data to another system. Core rule:

> Only mark a document as processed once all mandatory actions for that document have succeeded per the business contract.

If you advance `lastSeq` **before** writing the outcome successfully and the program crashes, the next run will skip an incompletely processed document. Conversely, if you finish writing the outcome but crash before persisting the checkpoint, the next run may reprocess the document.

Therefore, checkpoints enable **progress resumption**, not automatic exactly-once processing. Operations with side effects require **idempotency**, unique processing keys, appropriate transactions, or outbox/inbox patterns depending on system architecture.

### 10.3. Using Two Keys When the Sort Field Is Not Unique

In practice, multiple documents may share the same **createdAt**. If you only store a timestamp checkpoint and query:

~~~javascript
{ createdAt: { $gt: lastCreatedAt } }
~~~

then documents **with the same createdAt** that were not yet processed can be skipped. You need a secondary tie-breaker key for stable ordering, such as **(createdAt, _id)**:

~~~javascript
const lastCreatedAt = ISODate("2026-11-14T09:00:00Z");
const lastId = ObjectId("66f1c2a4b1d2e3f405162738");

db.auditEvents.find({
  $or: [
    { createdAt: { $gt: lastCreatedAt } },
    {
      createdAt: lastCreatedAt,
      _id: { $gt: lastId }
    }
  ]
})
  .sort({ createdAt: 1, _id: 1 })
  .limit(100);
~~~

This is a conceptual example on an **auditEvents** collection, assuming `_id` is an `ObjectId` and both fields have consistent BSON types. The query should be backed by an appropriate index, such as **{createdAt: 1, _id: 1}**.

To serve as a checkpoint, the ordering must be **well-defined and stable**—in particular, key values of processed records must not be arbitrarily mutated. If sort values can change, a document can jump from behind the checkpoint to ahead of it or vice versa.

### 10.4. Does Using _id Guarantee Strict Insertion Order?

`ObjectId` includes a timestamp component, yet sorting by `ObjectId` should not be treated as strict proof of absolute insertion order across multiple clients, especially when clients generate `ObjectId` values independently, clocks differ, or late writes occur. In our practice example, **seq was explicitly designed to be unique and monotonically increasing**, making it suitable as a resumption point.

In business systems, clearly define the ordering key, key generation timing, uniqueness, mutability, and late-arriving records. If you require an immutable complete snapshot of a dataset at a specific point in time, checkpointing alone over a mutating collection may be insufficient to guarantee those semantics.

## 11. Java: Processing in Small Pages for Resumability

For a batch job at risk of spending a long time per record, instead of holding one continuous cursor open for hours, you can choose an architecture that **reads short pages, finishes processing, saves the checkpoint, and opens the next page**.

The Java Sync Driver example below shows how to read pages by `seq`. This code prints logs for illustration; to recover across restarts, a real application must load and persist the checkpoint in a database or job state store.

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

import java.util.ArrayList;
import java.util.List;

public class PagedCursorReader {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        int pageSize = 5;
        int lastSeq = 0; // In a real app: read from persisted checkpoint.

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> events = client
                    .getDatabase("cursor_lab")
                    .getCollection("events");

            while (true) {
                List<Document> page = events
                        .find(Filters.gt("seq", lastSeq))
                        .sort(Sorts.ascending("seq"))
                        .limit(pageSize)
                        .into(new ArrayList<>());

                if (page.isEmpty()) {
                    break;
                }

                for (Document event : page) {
                    int seq = event.getInteger("seq");
                    // Replace with actual processing logic here.
                    System.out.println("Processed event " + seq);

                    // Advance marker only after processing succeeds.
                    lastSeq = seq;
                    // In a real app: persist durable checkpoint here.
                }
            }
        }
    }
}
~~~

Each page holds at most five documents, so **into(new ArrayList<>())** has a clear bound here. Each page query still uses a cursor inside the driver, yet the application avoids holding a long-lived `MongoCursor` across the entire processing loop.

### 11.1. What If an Error Occurs Mid-Page?

Suppose a page has `seq` 11–15, and the application finishes 11 and 12 before failing on 13:

- If the durably persisted checkpoint is **12**, the next run queries **seq > 12**.
- If the checkpoint was only saved up to **10**, 11 and 12 may need reprocessing; logic must tolerate duplicates.
- If the checkpoint was prematurely bumped to **15** right after loading the page before processing finished, the next run will skip items 13 through 15.

Hence, **reading a page does not equal finishing the page**. Checkpoint persistence timing must correspond to business success.

### 11.2. When Should You Keep a Long-Running Cursor?

A continuously iterated cursor can still be appropriate when:

- The application can process each document quickly.
- Every batch is consumed steadily.
- There is no need to stop and resume at a business checkpoint.
- The result set size and read duration fit within expected operational limits.

Conversely, if each document involves long network operations, external service calls, or multi-step work that cannot finish quickly, **paging and checkpointing** generally reduce dependence on a single cursor's lifetime.

## 12. Errors During Java Iteration: Scoping Retries Properly

In the MongoDB Java Sync Driver, errors can arise during the initial query, when the driver invokes `getMore`, or when application code processes each document. You can handle them at the exception level:

~~~java
import com.mongodb.MongoException;
import com.mongodb.client.MongoCursor;
import org.bson.Document;

try (MongoCursor<Document> cursor = events.find()
        .sort(new Document("seq", 1))
        .iterator()) {

    while (cursor.hasNext()) {
        Document event = cursor.next();
        System.out.println(event.getInteger("seq"));
    }
} catch (MongoException ex) {
    System.err.println(
            "MongoDB read failed; errorCode=" + ex.getCode()
    );
    throw ex;
}
~~~

This illustrative snippet assumes an existing `events` variable in scope. The `try-with-resources` block closes the cursor automatically even when an exception is thrown.

In MongoDB, **CursorNotFound** commonly corresponds to error code **43**, though cursor-related failures can also surface with other exception types or codes. Do not check just one number and assume all other failures are safe to resume.

### 12.1. A Controlled Retry Strategy

For checkpointed tasks:

~~~text
Read checkpoint from durable storage
              |
              v
     Open query after checkpoint
              |
              v
        Receive document / page
              |
              v
       Business processing succeeded?
          /                \
        Yes                 No
         |                   |
   Save checkpoint     Classify error
         |                   |
      Continue       Transient error?
                          /     \
                        Yes      No
                         |        |
                 Bounded backoff Report error / stop job
                         |
                Open new query from checkpoint
~~~

Limit retry attempts, apply **backoff** suited to your infrastructure, and support job cancellation. Do not infinitely retry data errors or permission errors. And **do not try to keep using a broken MongoCursor**; open a new query with an explicit checkpoint.

### 12.2. Should You Catch and Re-Run the Entire Query Automatically?

If all operations merely **read and print to the screen**, repeating results may be acceptable. However, if each document triggers invoice creation, sends an email, or updates another system, retrying the whole query can duplicate side effects.

Systems must pair checkpoints with idempotency design—such as recording processed event IDs or using writes with unique keys. Some scenarios require transactions, outbox patterns, or cross-service consistency mechanisms; a cursor alone does not solve those requirements.

## 13. An Active Query Does Not Guarantee a Frozen Snapshot

A standard cursor does not automatically create an immutable copy of the entire collection at the moment the query opens. If other processes insert, update, or delete documents while you iterate across multiple batches, the observed dataset can reflect concurrent changes depending on concurrency and specific read concern/transaction rules.

For example:

~~~text
Job reads by seq 1 ... 1000
             |
             +--- Another service updates seq, deletes a record, or inserts a record
             |
             +--- Job continues reading or opens a new page
~~~

If **seq is a stable key**, `seq`-based pages are generally easier to resume than `skip` offsets. Nevertheless, even keyset pagination does not automatically guarantee reading all changes in a single snapshot if documents are deleted, keys are updated, or new data is inserted behind the current position.

### 13.1. Bounding the Dataset to Process

For a batch job scanning data that existed before the job started, you can record a **high-water mark**, such as the maximum `seq` at start time:

~~~javascript
const newest = db.events
  .find({}, { seq: 1 })
  .sort({ seq: -1 })
  .limit(1)
  .toArray();

const maxSeqAtStart = newest.length > 0 ? newest[0].seq : 0;
~~~

Then process:

~~~javascript
db.events.find({
  seq: {
    $gt: lastSeq,
    $lte: maxSeqAtStart
  }
}).sort({ seq: 1 }).limit(100);
~~~

**maxSeqAtStart** prevents the job from running forever if new records with higher `seq` values are continuously appended. This is a boundary on the chosen key, **not a substitute for snapshot isolation**: older documents can still be modified or deleted while the job runs.

### 13.2. When Strong Consistency Is Required

If business requirements demand a consistent result set as of a specific point in time, evaluate **read concern**, transactions supporting snapshot views, or export/snapshot architectures appropriate for your MongoDB deployment. Those approaches carry their own operational costs and limits. Do not assume calling `find().sort()` alone creates a snapshot you can hold for hours.

Choosing the right model depends on whether the job may skip deleted documents, whether it must capture every update, whether new records appearing mid-run are acceptable, and what guarantees are needed during failover.

## 14. Distinguishing Cursor Timeouts from Operation Query Timeouts

MongoDB applications involve multiple kinds of timeouts affecting different stages:

| Mechanism | What is bounded? | Replaces closing the cursor? |
|---|---|---|
| Cursor idle timeout | Duration a cursor sits unused per server policy | No |
| Logical session timeout | Duration a session remains inactive per policy | No |
| `maxTimeMS` / equivalent API `maxTime` | Execution time allowed for server operations in scope | No |
| Driver socket/read timeout | Network wait time per client configuration | No |
| Application job deadline | Total time allowed for the entire processing job | No |

A query **running too long** and a cursor **sitting idle too long** are two distinct situations. Do not arbitrarily raise `maxTimeMS` expecting it to prevent cursors from expiring when `getMore` stops being called.

### 14.1. maxTimeMS Does Not Mean "Cursor Lives for N Milliseconds"

Example query:

~~~javascript
db.events
  .find({ category: "SYSTEM" })
  .maxTimeMS(10000);
~~~

Depending on operation type, configuration, and version, `maxTimeMS` caps execution time permitted by the server. It is **not the number of milliseconds the server will keep an idle cursor alive after sending a batch**. Do not use `maxTimeMS` as a substitute for `close()`, `noCursorTimeout`, or a checkpointing strategy.

### 14.2. How Batch Size Affects Idle Risk

Suppose each document takes 30 seconds of business processing and the application only requests the next batch after finishing the current batch:

| batchSize | Theoretical processing time for one full batch |
|---|---|
| 5 | 2.5 minutes |
| 20 | 10 minutes |
| 100 | 50 minutes |

These are only estimates for a hypothetical scenario; actual documents per batch can differ from the setting and real processing time fluctuates. Still, it illustrates the issue: **an overly large batch combined with slow processing can create gaps between `getMore` calls long enough to hit cursor/session timeouts**.

Ways to mitigate the risk include processing quickly inside the iteration loop, offloading heavy work to another queue, keeping batch sizes reasonable, or using checkpointed pagination when processing takes long.

### 14.3. noCursorTimeout and Session Refreshing

**noCursorTimeout** is useful once cursor retention requirements are well understood, yet sessions still have their own expiration policies. For exceptionally long jobs, some designs use explicit sessions and periodic **refreshSessions** calls following guidance appropriate to the server and driver version. This adds lifecycle management responsibility; refreshing alone does not protect against every cause of cursor loss.

For most business tasks requiring recovery, a **checkpoint + new query** architecture is usually easier to control than trying to keep a single cursor alive across every interruption.

## 15. Observing and Monitoring Cursors in Operations

A system with many open, unclosed cursors can accumulate resource usage, especially if the application frequently breaks out of iteration early or has error paths that bypass `finally`.

### 15.1. Inspecting Overview Metrics via serverStatus

With an account holding appropriate privileges, you can run:

~~~javascript
db.serverStatus().metrics.cursor;
~~~

Metrics may include figures on currently open cursors and timed-out cursors, such as fields structured like **open.total** and **timedOut**. Exact field/group names can differ across MongoDB versions, so verify actual server output.

Useful aggregate metrics for observing trends:

- **Open cursor count** rising steadily even as requests finish may suggest leaks or new workloads.
- **Timed-out cursor count** climbing rapidly can indicate applications pausing too long between reads or abandoning cursors.
- **Job duration** and **documents processed per second** help identify slow batch processing.
- **Retries from checkpoint** show whether the system frequently loses cursors mid-work.

A single server metric alone does not prove which application is leaking cursors. Cross-check logs, tracing, workload characteristics, and deployment versions.

### 15.2. Logging Batch Job Progress

An informative progress log might contain:

~~~text
jobId=export-2026-11-14
checkpoint.seq=12500
processedCount=12500
batchSize=200
durationSeconds=180
retryCount=1
status=RUNNING
~~~

Benefits of logging:

1. Shows how far the job has progressed.
2. Helps pinpoint which step failed.
3. Compares actual throughput against cursor lifetimes.
4. Supports recovery from the right checkpoint.

Do not write connection passwords, tokens, or entire sensitive documents directly into progress logs.

### 15.3. Avoid Killing Cursors of Other Workloads

MongoDB provides the administrative **killCursors** command and tools to inspect active operations. These actions can disrupt queries from other applications. During practice, proactively **close()** cursors created by your own program; if investigating a production incident, identify the exact client, session, and cursor before running administrative actions.

## 16. Standard Cursors, Tailable Cursors, and Change Streams

The phrase "continuous reading" can be misleading: exhausting a result set with a standard cursor differs from **watching for new documents** or **tracking database changes**.

| Mechanism | Purpose | When no current data remains |
|---|---|---|
| Standard cursor | Iterates results of a query | Finishes once exhausted |
| Tailable cursor | Continues reading documents appended to a capped collection | Can keep waiting for new documents while cursor remains valid |
| Change Streams | Tracks change events via MongoDB Change Streams API | Can await new events and use a resume token when supported |

### 16.1. Why Standard find() Is Not a "Watch Forever" Command

~~~javascript
db.events.find({ category: "SYSTEM" });
~~~

Once a standard cursor finishes its results, it completes. If new documents matching the filter are inserted afterward, the completed cursor **does not automatically turn into an infinite watch stream**.

To track ongoing changes, consider **Change Streams** when your deployment supports them, or **tailable cursors** for capped collections when appropriate. These mechanisms come with additional rules for waiting, timeouts, resumption, and delivery semantics; they are not drop-in replacements for one another.

### 16.2. Tailable Cursors Can Miss Old Documents

A tailable cursor on a capped collection relies on the buffer still retaining data. If a producer writes fast enough that older documents are overwritten before the consumer reads them, the consumer can miss data. Therefore, do not treat a tailable cursor as a guaranteed-delivery queue for every event.

### 16.3. Change Streams Have Their Own Resume Tokens

Change Streams provide a **resume token** mechanism to help continue after certain interruptions, though resumability still depends on available change history/oplog retention and supported deployment conditions. Do not apply a standard cursor's `seq` checkpoint directly to Change Streams, or assume every cursor automatically provides a resume token.

## 17. Common Design Mistakes

| Symptom | Common cause | Remedy |
|---|---|---|
| Java batch job leaves many `MongoCursor` instances open | Not closing in error/early-break paths | Use `try-with-resources` scoped to each cursor |
| mongosh stops after a few documents, server keeps cursor | Not calling `close()` on break or exception | Use `try/finally` and `cursor.close()` |
| `CursorNotFound` after very slow batch processing | Cursor/session likely expired during gap without `getMore` | Reduce work between batches, paginate, use checkpoints |
| `noCursorTimeout` set yet cursor still lost | Session expired or another failure occurred | Check session, server, network, and design recovery |
| Re-running query after error causes duplicate processing | No checkpoint saved or non-idempotent side effects | Persist checkpoints properly, handle duplicates safely |
| Saving checkpoint upon loading page loses records | Failed before finishing processing last documents on page | Advance checkpoint only after business success |
| `find().toArray()` causes out-of-memory error | Collecting large dataset into a `List`/`Array` | Iterate document-by-document or bounded pages with `limit` |
| Raising `batchSize` to "read fast" causes more idle errors | Large batch takes too long to process before next `getMore` | Measure processing rate and tune `batchSize` |
| `skip/limit` duplicates or skips records during concurrent writes | Offsets shift when data is inserted/deleted | Keyset pagination on a stable ordered key |
| Sorting by `createdAt` skips records with identical timestamps | Checkpoint lacks a secondary tie-breaker key | Use `(createdAt, _id)` pair or another unique key |
| Treating `ObjectId` `_id` as a strict global clock | `ObjectId` can be generated by many clients; ordering is not strict | Define a progress key per business design |
| Setting `maxTimeMS` to prevent cursor idle timeout | Two different timeout mechanisms | Separate operation timeout from idle/session timeout |
| Query finishes reading and gets mistaken for cursor failure | Cursor completed normally after final results | Distinguish end-of-data from `getMore` exceptions |
| `MongoClient` created/closed per document | Confusing client lifecycle with cursor lifecycle | Reuse `MongoClient`, close `MongoCursor` per query |

## 18. Practice Exercises

Perform these exercises on the **cursor_lab** database created in Section 3. Any exercise modifying data should be run on test data to avoid affecting real systems.

### Exercise 1. Sequential Reading and Closing the Cursor

Requirement: print `seq` and `message` of all documents in ascending `seq` order with `batchSize` equal to 4, ensuring the cursor is closed when finished.

**Reference solution:**

~~~javascript
const cursor = db.events.find(
  {},
  { seq: 1, message: 1 }
).sort({ seq: 1 }).batchSize(4);

try {
  while (cursor.hasNext()) {
    const doc = cursor.next();
    print(doc.seq + ": " + doc.message);
  }
} finally {
  cursor.close();
}
~~~

With the unmodified sample dataset, you will read **24 documents**, from `seq` 1 to `seq` 24. Using `batchSize(4)` does not cap the total document count at 4.

### Exercise 2. Early Termination

Requirement: read only the first three documents while still closing the cursor.

**Reference solution:**

~~~javascript
const cursor = db.events.find().sort({ seq: 1 });

try {
  for (let i = 0; i < 3 && cursor.hasNext(); i++) {
    printjson(cursor.next());
  }
} finally {
  cursor.close();
}
~~~

Explain why `close()` still matters when 21 unread documents may remain in the query.

### Exercise 3. Comparing batchSize and limit

Predict the maximum number of documents each query can return:

~~~javascript
db.events.find().batchSize(3)
db.events.find().limit(3)
db.events.find().batchSize(3).limit(8)
~~~

**Guidance:** The first query can still iterate all 24 documents; the second returns at most 3; the third returns at most 8, potentially split across multiple batches as needed.

### Exercise 4. Handling Failures After a Checkpoint

Suppose a job successfully processed and persisted checkpoint **lastSeq = 12**, then encountered a `CursorNotFound` error. Write the query to resume from the next record:

~~~javascript
const lastSeq = 12;

db.events
  .find({ seq: { $gt: lastSeq } })
  .sort({ seq: 1 })
  .limit(5);
~~~

The next page returns **seq 13–17** if the sample dataset is intact. Why must `$gt` be used instead of `$gte` in the resumption filter? Because `seq` 12 has already been confirmed as processed.

### Exercise 5. Checkpointing at the Wrong Time

A job successfully processed `seq` 1–7 and failed while processing `seq` 8, yet the checkpoint was written as 10 as soon as the page loaded.

Explain:

1. What happens if the next run queries `seq > 10`?
2. Which value should the checkpoint have stored?
3. If the task finished processing `seq` 7 but crashed before saving checkpoint 7, what mechanism is needed to tolerate reprocessing?

**Hint:** `seq` 8–10 could be skipped; the safe checkpoint after success is 7; idempotent processing or consistent business-state-and-checkpoint persistence is required.

### Exercise 6. Pagination with a Non-Unique Field

Suppose many events share the same **createdAt**. A job stores only `lastCreatedAt` and queries `createdAt > lastCreatedAt`. Why does the job risk missing documents? Write a filter using both `createdAt` and `_id` as an ordering pair, along with `sort({createdAt:1,_id:1})`.

**Guidance:** documents with `createdAt` equal to the last marker but larger `_id` values may not have been processed yet. You need the condition **createdAt greater than marker, OR createdAt equal to marker AND _id greater than lastId**.

### Exercise 7. Idle Time Analysis

Suppose each document requires 20 seconds of application-side processing. Compare reading batches of 5, 20, and 100 documents before requesting the next batch.

Calculate the theoretical processing time of each batch, identify scenarios at risk of exceeding typical idle intervals, and propose an architectural change.

**Hint:** times are approximately **100 seconds**, **400 seconds**, and **2,000 seconds**, respectively. Consider cursor and session timeouts; short paged reads, checkpoints, and decoupled workers help avoid relying on long-lived cursors.

### Exercise 8. Predicting Behavior After Cursor Closure

In a Java application that already called `cursor.close()`, code still calls `cursor.next()`. Does this mean enabling `noCursorTimeout` would let it continue?

**Guidance:** No. A cursor that has been **explicitly** closed has ended its lifecycle; `noCursorTimeout` only affects server timeout behavior and cannot make a closed object readable again. Fix the cursor's scope or open a new query as needed.

## 19. Implementation Principles for Production Applications

When designing a MongoDB read job, answer these questions:

1. **Do you need all documents at once?** If not, iterate one document at a time with a cursor, or split into bounded pages.
2. **Do you need stable sorting?** If resuming or paginating, choose a consistent sort key, consider uniqueness, and add a supporting index.
3. **How long does each document take to process?** If processing can be slow, avoid leaving cursors idle for long; consider checkpointing.
4. **Who closes the cursor?** In mongosh, use `try/finally`; in Java Sync Driver, use `try-with-resources`.
5. **If the server closes the cursor, what does the program do?** Classify the error, close resources, and open a new query from the checkpoint when safe.
6. **If a document is reprocessed, does it cause harm?** Design idempotent processing or appropriate consistency guarantees.
7. **Is a snapshot or continuous change feed required?** Choose appropriate read concerns/transactions or sync architectures instead of assuming standard cursors provide them automatically.

Cursors allow MongoDB to transfer and process large result sets sequentially. To use them safely, **iterate in sensible batches**, **close resources even on errors**, and **do not depend on a cursor living forever**. When tasks run long or may be interrupted, a stable data order paired with durable checkpoints forms the foundation for resuming work without silently skipping or duplicating records.
