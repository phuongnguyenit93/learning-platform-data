# Controlling Write Batch Size and Request Limits When Inserting Documents into MongoDB

## 1. Why Must Write Batch Size Be Controlled?

Adding a document to MongoDB usually starts with **insertOne()**. When needing to insert thousands or millions of documents, an application can use **insertMany()** or **bulkWrite()** to reduce round trips with the database. Instead of sending each document in its own network round trip, one call can transmit multiple write operations.

However, **larger batches do not mean a faster system**. MongoDB enforces limits on BSON document size, the number of operations in a single write batch, and message size between client and server. Beyond MongoDB's thresholds, the application also faces memory, connection, timeout, disk throughput, and business responsiveness limits.

For example, a product catalog import service receives 2 million records from a file:

~~~text
CSV / JSONL / API stream
           |
           v
     Parser + validation
           |
           v
   Bounded batch builder
    - count threshold
    - BSON bytes threshold
    - optional time threshold
           |
           v
       MongoDB Driver
    - enforce server limits
    - encode and split batches
           |
           v
         mongod
    - validate and execute
    - acknowledge per write concern
           |
           v
   Report success / partial errors
~~~

If the application reads the entire file into RAM and calls **insertMany()** once, it may hit an **OutOfMemoryError** before the driver even splits the request, or wait far too long before learning part of the data failed. A clearly bounded batching mechanism helps control memory, reduce resource hold times, and handle errors incrementally.

### Distinguishing Three Units

- **Document:** a single BSON record stored in a collection; has its own size limit.
- **Logical batch:** the set of operations an application passes to a single call of **insertMany()** or **bulkWrite()**. This may contain hundreds of thousands of operations.
- **Wire batch / command:** the group of operations the driver actually encodes into one message sent to the server. The driver may split one logical batch into **multiple** smaller requests.

Do not look at a call **insertMany(120000 documents)** and assume the server receives a single command containing 120,000 documents. The MongoDB driver generally splits according to the limits advertised by the server.

## 2. Important Limits to Distinguish

Standard MongoDB builds advertise the following three parameters in connection/handshake metadata:

| Parameter | Common Value | Meaning |
|---|---:|---|
| **maxBsonObjectSize** | **16,777,216 bytes (16 MiB)** | Maximum size of **a single regular BSON document** allowed to be stored. |
| **maxWriteBatchSize** | **100,000 operations** | Maximum number of write operations in **a single write command batch** supported by the server. |
| **maxMessageSizeBytes** | **48,000,000 bytes** | Maximum size of a MongoDB wire protocol message; includes message/command overhead, not just document payloads. |

These are typical technical ceilings, **not optimal application batch sizes**. When interacting with a specific deployment, the driver relies on what the server advertises. Do not hardcode assumptions that every topology and every version are identical while ignoring actual negotiated values.

Unit notes:

- **16 MiB = 16 × 1024 × 1024 = 16,777,216 bytes**.
- **48,000,000 bytes** is roughly **45.8 MiB**, not 48 MiB.
- The number **100,000** limits **operation count**, and does not mean 100,000 documents will automatically fit under the wire message size limit.

### 2.1. Retrieving Limits from the Server

In **mongosh**:

~~~javascript
const hello = db.adminCommand({ hello: 1 });

printjson({
  maxBsonObjectSize: hello.maxBsonObjectSize,
  maxMessageSizeBytes: hello.maxMessageSizeBytes,
  maxWriteBatchSize: hello.maxWriteBatchSize
});
~~~

Example output on a server with common values:

~~~javascript
{
  maxBsonObjectSize: 16777216,
  maxMessageSizeBytes: 48000000,
  maxWriteBatchSize: 100000
}
~~~

This information is part of MongoDB's wire interface. Drivers normally read and manage these limits automatically when selecting a server. For multi-node clusters or routing through **mongos**, inspect the characteristics of the target topology; do not treat one check command as the sole source for every node.

### 2.2. Limit Layers Beyond MongoDB

A write request can be blocked **before reaching the server**:

| Layer | Potential Limits | Symptoms |
|---|---|---|
| **REST API / reverse proxy / API gateway** | HTTP body limits, timeouts, concurrent request limits. | HTTP 413, 429, 504, or other gateway errors depending on config. |
| **Java application** | Heap, GC, queues, threads, connection pool, processing time. | Growing heap, GC pauses, OutOfMemoryError, deep queues. |
| **MongoDB Driver** | Wire batch constraints, encoding, connection pool, timeouts. | Driver splitting batches, waiting for connections, throwing exceptions. |
| **MongoDB Server** | BSON size, command/message size, index/validation, CPU/I/O resources. | Write errors, latency spikes, timeouts, out of disk space. |
| **Replica set / sharded cluster** | Majority acknowledgement, shard distribution, inter-node network. | Increased write latency, throttling, write concern errors. |

**HTTP request limits are not MongoDB wire message limits.** For example, if an API receives a 30 MiB JSON body and Java splits it into MongoDB operations, both layers must be configured appropriately, and 30 MiB of JSON is not necessarily equal to 30 MiB of BSON.

## 3. Single BSON Document Size Limit

MongoDB imposes a standard limit of **16 MiB per BSON document**. This limit covers not just visible data, but the entire BSON representation of fields, field names, values, and structural overhead.

Example of a document containing a very large string field:

~~~javascript
const largeDocument = {
  sourceId: "IMPORT-123",
  payload: "x".repeat(10 * 1024 * 1024)
};
~~~

The string above contains roughly 10 MiB of ASCII characters, yet **the BSON size of the whole document exceeds the string's size** due to field names and BSON metadata. With multi-byte UTF-8 characters, the gap between **character count** and **byte count** is even larger.

### 3.1. Do Not Measure Using JSON String Length

~~~javascript
const doc = {
  name: "Test Product",
  quantity: NumberInt(10),
  createdAt: new Date()
};

// JSON string length is not BSON size.
print(JSON.stringify(doc).length);

// In mongosh, read the encoded BSON size.
print(Object.bsonsize(doc));
~~~

**JSON.stringify(doc).length** counts JavaScript UTF-16 code units of the JSON string, not actual BSON bytes. It ignores differences between BSON and JSON as well as BSON values with specialized types.

For documents already stored in a collection, you can use the aggregation expression **$bsonSize**:

~~~javascript
db.products.aggregate([
  {
    $project: {
      _id: 1,
      bsonBytes: { $bsonSize: "$$ROOT" }
    }
  },
  { $sort: { bsonBytes: -1 } },
  { $limit: 10 }
]);
~~~

The result returns each document's BSON size measured on the server. On large collections, this pipeline may scan a lot of data; bound its scope in production. Measuring **document size** also does not capture the full overhead of an entire **wire message**.

### 3.2. Why Large Documents Cause Problems Even Under 16 MiB

A document within the size limit can still incur heavy costs:

- Reading the document transfers many bytes over the network.
- Queries returning large documents consume significant server and client RAM.
- Updating a single field can increase cache, storage, and replication pressure.
- Multiple large documents in one batch push the total payload rapidly toward the message limit.
- Continuously growing arrays can push a document past the threshold on a later update.

For example, avoid embedding an unbounded event history:

~~~javascript
{
  orderId: "ORD-100",
  events: [
    /* hundreds of thousands of events can bloat the document */
  ]
}
~~~

If history keeps growing, split it into an **order_events** collection, link via **orderId**, and create an appropriate index. You cannot fix a document exceeding 16 MiB merely by reducing the number of documents in a batch.

### 3.3. What to Do with an Oversized Record?

Depending on the data:

1. **Normalize the document model:** move unbounded arrays, blobs, or histories into another collection.
2. **Store large files separately:** use **GridFS** when files must live in MongoDB, or object storage when appropriate for the architecture.
3. **Reduce duplicated data:** avoid embedding an entire huge structure into every document when a reference suffices.
4. **Reject bad input clearly:** if business rules require records to stay small, reject records exceeding a soft threshold before sending them to the server.

**GridFS** splits files into multiple chunks/documents and maintains metadata; it does not "stretch" the 16 MiB limit of any individual BSON document.

## 4. Operation Count Limit in One Write Batch

**maxWriteBatchSize** limits the number of operations placed into a single write command batch on the server. A common value is **100,000**. Drivers respect this limit and can automatically split operations across multiple requests.

Example:

~~~javascript
const docs = [];

for (let i = 0; i < 120000; i++) {
  docs.push({
    sourceId: "ROW-" + i,
    kind: "IMPORT",
    value: i
  });
}

db.import_rows.insertMany(docs, { ordered: false });
~~~

At the API call level, this is one **120,000-document insertMany**. At the wire protocol level, the driver must obey protocol limits and may issue multiple batches. A Java application behaves the same way.

**Do not run the 120,000-document example in the shell or production without checking disk space, time, and memory.** The example above illustrates the difference between a logical batch and wire batches.

### 4.1. You Can Hit the Byte Limit Before the Count Limit

Suppose each document encodes to **50 KiB** on average. A batch of **1,000 documents** has a payload of roughly:

\[
1,000 \times 50\ \text{KiB}
= 50,000\ \text{KiB}
\approx 48.83\ \text{MiB}
\]

This already exceeds the common **48,000,000-byte** wire message limit even before adding command overhead. Thus, even though 1,000 is far below 100,000, the driver still has to split by **byte size**.

Conversely, 100,000 tiny documents can hit the **count limit** before the byte limit.

### 4.2. Sending Multiple Operations in One Request Does Not Make It a Transaction

**insertMany()** or **bulkWrite()** does not implicitly guarantee atomicity of the **entire batch**:

- MongoDB guarantees atomicity for a single write operation on **one document** according to its semantics.
- In a multi-document batch, some writes may succeed while others fail.
- A bulk write may be split by the driver into multiple write commands.
- **ordered/unordered** affects processing order and behavior on error, and does not turn the whole batch into an all-or-nothing unit.

If business logic genuinely requires multiple documents to form a single transactional unit, consider a **multi-document transaction** on a supported topology. Transactions carry their own overhead and limits; they do not bypass per-document BSON limits or operational constraints.

## 5. MongoDB Message Size Limit

**maxMessageSizeBytes** is a wire protocol layer limit. The common **48,000,000-byte** value applies to messages exchanged with MongoDB; you cannot simply sum the text length of a JSON array for an exact calculation.

A write command also includes:

- command name and collection/database metadata;
- options such as **ordered**, **writeConcern**, and session/transaction metadata when present;
- encoding of the BSON array or document sequence;
- header/protocol overhead and other fields depending on request type.

Therefore, in application design, maintain a **safety margin** instead of aiming right at 48,000,000 bytes for the document payload alone.

### 5.1. Wire Protocol Limits and Optimal Performance Are Two Different Things

A 20 MiB batch may be valid at the protocol level yet still cause:

- high latency while encoding, sending, and waiting for acknowledgement;
- CPU/GC pressure on the JVM when building and retaining document lists;
- long queues when the driver lacks available connections;
- p95/p99 latency spikes under busy I/O;
- high error-handling overhead if many documents hit validation/duplicate key errors.

Hence, **operational batch size** usually needs to be much smaller than server ceilings. A starting point might be a few hundred to a few thousand documents with a byte threshold well below the wire message limit, followed by real measurement. These figures are **tuning parameters**, not mandatory MongoDB defaults.

## 6. Driver Auto-Batching: What It Does and Does Not Do

MongoDB Drivers fetch server limit metadata and perform encoding/request splitting so protocol limits are not violated. This helps when code calls **insertMany()** or **bulkWrite()** with a large logical batch.

However, driver auto-splitting does not mean the application is free to:

1. Load millions of documents into a single unbounded **List**.
2. Fire unbounded asynchronous requests that overflow queues.
3. Treat a single API call as an atomic transaction.
4. Ignore duplicate keys, validation errors, write concern errors, or timeouts.
5. Assume retrying the entire list is safe in all situations.

~~~text
App builds a 2,000,000-element List<Document>
                    |
           RAM already consumed
                    |
           driver receives List
                    |
        splits into multiple commands
                    |
               MongoDB server
~~~

The driver solves **wire command** limits. The application must still solve **memory/backpressure**, per-group error handling, and business semantics.

### 6.1. Do Not Manually Assemble Oversized Commands

Use official driver APIs like **insertMany** and **bulkWrite** instead of manually constructing a gigantic BSON command to send via **runCommand**, unless you thoroughly understand the protocol and have a special need. Drivers handle supporting logic such as routing, retries, sessions, and batch splitting.

## 7. Choosing Between insertOne, insertMany, and bulkWrite

| API | Unit Provided | When to Use | Notes |
|---|---|---|---|
| **insertOne(document)** | One document. | Single-entity creation APIs; simple, straightforward error reporting. | Each request has network overhead; lower throughput if sent sequentially millions of times. |
| **insertMany(documents)** | Multiple inserts. | Data loading, imports, writing uniform insert-only lists of documents. | Has ordered/unordered; can partially succeed. |
| **bulkWrite(models)** | Multiple write model types. | Need to combine inserts, updates, replaces, and deletes in a workflow. | Error tracking and ordering are more complex; not an automatic transaction. |

Example inserting three documents:

~~~javascript
db.import_rows.insertMany(
  [
    { sourceId: "A-01", quantity: NumberInt(1) },
    { sourceId: "A-02", quantity: NumberInt(2) },
    { sourceId: "A-03", quantity: NumberInt(3) }
  ],
  { ordered: true }
);
~~~

Example bulkWrite:

~~~javascript
db.import_rows.bulkWrite(
  [
    {
      insertOne: {
        document: { sourceId: "B-01", quantity: NumberInt(3) }
      }
    },
    {
      updateOne: {
        filter: { sourceId: "A-01" },
        update: { $inc: { quantity: 1 } }
      }
    },
    {
      replaceOne: {
        filter: { sourceId: "A-02" },
        replacement: {
          sourceId: "A-02",
          quantity: NumberInt(99)
        }
      }
    }
  ],
  { ordered: true }
);
~~~

An **updateOne** or **replaceOne** in bulkWrite does not guarantee the post-update document shrinks. If the resulting document exceeds the BSON document size limit, MongoDB can reject the operation.

## 8. How Ordered and Unordered Affect Error Handling

### 8.1. Ordered: Stop on Sequential Write Error

By default, **insertMany** uses **ordered: true**. The driver/server attempts execution in order and, upon hitting a write error such as duplicate key, does not continue remaining operations per ordered rules.

Example with an existing unique index:

~~~javascript
db.batch_orders.createIndex({ orderCode: 1 }, { unique: true });

db.batch_orders.insertOne({
  orderCode: "ORD-001",
  amount: NumberDecimal("10.00")
});

db.batch_orders.insertMany(
  [
    { orderCode: "ORD-002", amount: NumberDecimal("20.00") },
    { orderCode: "ORD-001", amount: NumberDecimal("30.00") },
    { orderCode: "ORD-003", amount: NumberDecimal("40.00") }
  ],
  { ordered: true }
);
~~~

Here **ORD-002** may be inserted successfully before the second operation triggers a duplicate key error. After that error, the **ORD-003** operation is not continued under normal ordered mode.

**The whole batch is not rolled back**: ORD-002 can still exist.

### 8.2. Unordered: Continue Eligible Operations

~~~javascript
db.batch_orders.insertMany(
  [
    { orderCode: "ORD-004", amount: NumberDecimal("20.00") },
    { orderCode: "ORD-001", amount: NumberDecimal("30.00") },
    { orderCode: "ORD-005", amount: NumberDecimal("40.00") }
  ],
  { ordered: false }
);
~~~

With **ordered: false**, MongoDB can continue processing other operations despite a duplicate key on one element. Succeeded and failed operations must be tracked separately. **Do not assume execution order or completion order** matches the input list, especially in sharded environments.

### 8.3. Mode Selection Mindset

| Case | Typically Consider |
|---|---|
| Later step strictly depends on earlier step and must stop on error. | **ordered: true**, but do not treat as a transaction. |
| Importing many independent records; want to keep processing valid records when one fails. | **ordered: false** + per-item error reporting. |
| Business requires all to succeed or all to fail together. | Design a transaction or separate compensating workflow. |

If the entire batch needs "all-or-nothing" semantics, setting **ordered: true** is not enough.

## 9. Designing Batch Thresholds at the Application Layer

A practical batch builder should bound at least by **document count** and **estimated/measured total BSON bytes**. For slow-arriving data streams, add a **maximum wait time** to avoid holding batches too long.

### 9.1. Three Soft Thresholds

Example chosen by an application:

~~~text
TARGET_MAX_DOCUMENTS  = 500 documents / application batch
TARGET_MAX_BSON_BYTES = 4 MiB / application batch
MAX_WAIT              = 200 ms / application batch
~~~

These are merely **illustrative application settings**, not MongoDB limits. Systems with small documents, fast networks, and heavy load may raise thresholds; systems requiring low latency or handling huge documents may lower them.

Flush rules could be:

~~~text
Flush when any condition is met:

  pendingCount >= 500
       OR
  pendingBsonBytes + nextDocumentBytes > 4 MiB
       OR
  oldestPendingAge >= 200 ms
       OR
  stream ends
~~~

The **count threshold** controls operation count. The **byte threshold** controls payload size. The **time threshold** bounds waiting latency when data arrives sparsely. For offline file imports, the time threshold may be unnecessary.

### 9.2. Handling a Single Document Exceeding the Soft Threshold

A 6 MiB BSON document is valid because it is still under 16 MiB, yet larger than **TARGET_MAX_BSON_BYTES = 4 MiB** in our example. There are two clear strategies:

- **Allow a single-document batch containing just that document**, provided the document is valid for the server and the system accepts the cost.
- **Enforce a stricter business limit**, e.g., import records must not exceed 4 MiB, and reject or offload large files to appropriate storage.

Never put a 6 MiB document into an infinite "flush then retry" loop because even an empty batch won't fit under 4 MiB. The batch builder must have an explicit path for oversized singletons.

### 9.3. Keeping a Safety Margin

Total BSON bytes of documents do not equal the entire message size, because command/protocol overhead also applies. Soft byte thresholds should sit **significantly below** maxMessageSizeBytes; do not set the document payload limit to exactly 48,000,000 bytes expecting the driver to send it as one request.

The driver remains the final layer enforcing negotiated technical limits. Application thresholds exist to control resource usage and latency.

### 9.4. Count + Bytes Batching Algorithm

~~~text
batch       = empty
batchBytes  = 0

for each document from bounded source:
    prepare stable _id / idempotency key
    validate document
    size = measure BSON bytes with actual codec

    if size > allowedDocumentSize:
        send to rejected-record report
        continue

    if batch is not empty AND
       (batch.count >= targetCount OR
        batchBytes + size > targetBytes):
        send batch
        handle acknowledgment / partial errors
        clear batch
        batchBytes = 0

    append document to batch
    batchBytes += size

flush remaining batch at end
~~~

**Measure size after adding _id**, because the driver may auto-assign **_id** if missing. If you calculate size beforehand and then add fields or convert POJOs/BSON with a different codec, the estimate will no longer be accurate.

## 10. Java Example: Splitting insertMany by Count and BSON Bytes

The Java Sync Driver provides **MongoCollection<Document>**, **InsertManyOptions**, **DocumentCodec**, **BsonBinaryWriter**, and **BasicOutputBuffer** to build a batch-splitting pipeline. The example below assumes the application already holds a **MongoCollection<Document>** and reads data from an **Iterable<Document>**.

The values 500 documents, 4 MiB/batch, and 15 MiB/document are **example safeguard policies**, intentionally stricter than standard server limits:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.InsertManyOptions;
import org.bson.BsonBinaryWriter;
import org.bson.Document;
import org.bson.codecs.DocumentCodec;
import org.bson.codecs.EncoderContext;
import org.bson.io.BasicOutputBuffer;
import org.bson.types.ObjectId;

import java.util.ArrayList;
import java.util.List;

public final class BatchInsertService {
    private static final int MAX_DOCUMENTS = 500;
    private static final long TARGET_BATCH_BYTES = 4L * 1024 * 1024;
    private static final long MAX_DOCUMENT_BYTES = 15L * 1024 * 1024;

    private final MongoCollection<Document> collection;
    private final DocumentCodec codec = new DocumentCodec();

    public BatchInsertService(MongoCollection<Document> collection) {
        this.collection = collection;
    }

    public void insert(Iterable<Document> source) {
        List<Document> batch = new ArrayList<>(MAX_DOCUMENTS);
        long batchBytes = 0;

        for (Document document : source) {
            // Stabilize _id before measuring size and sending.
            document.putIfAbsent("_id", new ObjectId());

            int docBytes = bsonSize(document);

            if (docBytes > MAX_DOCUMENT_BYTES) {
                throw new IllegalArgumentException(
                    "Import document exceeds application size policy: "
                    + docBytes + " bytes"
                );
            }

            boolean hitCount = batch.size() >= MAX_DOCUMENTS;
            boolean hitBytes =
                    batchBytes + docBytes > TARGET_BATCH_BYTES;

            if (!batch.isEmpty() && (hitCount || hitBytes)) {
                send(batch);
                batch = new ArrayList<>(MAX_DOCUMENTS);
                batchBytes = 0;
            }

            // A document > 4 MiB is sent as a single-element batch.
            batch.add(document);
            batchBytes += docBytes;
        }

        if (!batch.isEmpty()) {
            send(batch);
        }
    }

    private int bsonSize(Document document) {
        BasicOutputBuffer output = new BasicOutputBuffer();

        try (BsonBinaryWriter writer = new BsonBinaryWriter(output)) {
            codec.encode(
                writer,
                document,
                EncoderContext.builder().build()
            );
        }

        return output.getPosition();
    }

    private void send(List<Document> batch) {
        collection.insertMany(
            batch,
            new InsertManyOptions().ordered(false)
        );
    }
}
~~~

### 10.1. How to Use

~~~java
MongoCollection<Document> products =
        mongoDatabase.getCollection("import_products");

BatchInsertService service = new BatchInsertService(products);

List<Document> source = List.of(
    new Document("sourceId", "ROW-1").append("name", "Mouse"),
    new Document("sourceId", "ROW-2").append("name", "Keyboard"),
    new Document("sourceId", "ROW-3").append("name", "Monitor")
);

service.insert(source);
~~~

When ingesting large files, replace **List.of(...)** with a **line-by-line/streaming** reader and keep buffered in-memory items bounded. **Iterable** can represent a lazy source, though whether it actually reads lazily depends on its implementation.

### 10.2. Limitations of the Java Example

This example demonstrates the batching algorithm and is **not yet a production-ready import component**:

- **DocumentCodec** measures BSON for **Document** instances and pre-prepared values; if the application uses a different POJO codec/mapper, measure using **the actual codec used for writing**.
- **TARGET_BATCH_BYTES** only sums BSON document bytes; it does not include full command/wire overhead.
- **ordered(false)** allows partial success. If **insertMany** throws an exception, the example **stops** at that batch; a production app must collect results, handle failed records, and decide whether to continue subsequent batches.
- Generating **ObjectId** in the app before sending helps keep identifiers stable for checking/retrying, but does not by itself guarantee full business idempotency. Use a unique business key.
- The 15 MiB/document cap is an **example policy**, not MongoDB rejecting every document over 15 MiB.
- For systems using sessions, transactions, write concerns, or reactive APIs, pass and handle those parameters per the application contract.

In practice, tune **MAX_DOCUMENTS**, **TARGET_BATCH_BYTES**, and concurrency based on metrics rather than using one universal setting for every collection.

## 11. mongosh Example: Splitting a List by Count

If simply experimenting with a small dataset where document sizes are controlled, you can split into chunks in JavaScript:

~~~javascript
const docs = Array.from({ length: 2500 }, (_, i) => ({
  sourceId: "TEST-" + i,
  quantity: NumberInt(i)
}));

const maxDocsPerCall = 500;

for (let start = 0; start < docs.length; start += maxDocsPerCall) {
  const chunk = docs.slice(start, start + maxDocsPerCall);
  db.import_rows.insertMany(chunk, { ordered: false });
}
~~~

This example creates at most **500 documents per insertMany call**. It does not track total BSON bytes, so it is **insufficient** for sources with widely varying document sizes. For real data, add a byte threshold as in Section 9's algorithm and avoid materializing the entire input into an array before splitting.

## 12. Backpressure: Bounded Batches Can Still Have Unbounded Queues

Suppose an application generates data at **30,000 documents/second**, while the database can only durably write **20,000 documents/second** under current conditions. Even with 500-document batches, if the producer keeps pushing unchecked, the queue grows continuously:

~~~text
Producer: 30,000 docs/s
           |
           v
       Unbounded queue     <--- accumulates +10,000 docs/s
           |
           v
    Batch writer: 20,000 docs/s
           |
           v
         MongoDB
~~~

The solution is **backpressure**: bound the number of queued documents/batches, in-flight requests, and work generation rate.

~~~text
Producer
   |
   v
Bounded queue (capacity)
   |
   +-- full --> producer waits / rejects / persists externally
   |
   v
N batch workers (bounded concurrency)
   |
   v
MongoDB connection pool
   |
   v
MongoDB
~~~

Common approaches:

1. **Producer blocking:** when the queue is full, wait for writers to drain some items.
2. **Rate limiting:** cap the number of batches or bytes accepted per second per contract.
3. **Bounded concurrency:** do not fire thousands of batches in parallel if the connection pool and server cannot sustain them.
4. **Durable queue:** use a persistent queue when ingestion rate must be decoupled from database write rate.
5. **Admission control:** reject or signal retry-later when overloaded instead of silently piling up RAM.

**The number of MongoDB connections is not the optimal number of concurrent batches.** Increasing concurrency can boost throughput up to a point, then degrade latency, lock contention, cache pressure, and timeout rates. Measure on real workloads.

## 13. Partial Failure, Retries, and Idempotency

A batch can partially succeed because:

- documents collide on **_id** or a unique business key;
- documents fail schema validation;
- a document is too large;
- write concern is not met within the timeout;
- a network error or node failover occurs mid-operation;
- disk space or system resources are exhausted;
- driver/server timeouts occur;
- individual operation errors occur inside **bulkWrite**.

### 13.1. Classify Errors Before Retrying

| Error Type | Handling Mindset |
|---|---|
| **Duplicate key** | Verify whether the record was already created or is a genuine data conflict. Do not retry blindly. |
| **Schema validation** | Route the record back for validation/source repair; retrying identical data will not fix the error. |
| **Document too large** | Redesign the document or reject the record; shrinking batch size does not make one document smaller. |
| **Temporary network/failover** | Check error labels, driver retry semantics, and idempotency before retrying. |
| **Write concern timeout/error** | The write may have executed without reaching the required acknowledgement level. Inspect state rather than assuming failure. |
| **Overload / timeout** | Reduce concurrency or batch size, or tune retries with backoff/jitter; inspect metrics. |

A **timeout does not prove a document was not inserted**. The client may lose the response after the server already applied the operation. That is why imports need ID/business-key reconciliation.

### 13.2. Using Unique Business Keys for Idempotency

For example, records from a source system carry **sourceSystem** and **externalId**:

~~~javascript
db.import_orders.createIndex(
  { sourceSystem: 1, externalId: 1 },
  { unique: true, name: "uq_source_external_id" }
);
~~~

When resending the same record, the index prevents creating two documents with the same source identity. However, a unique index **does not automatically verify identical content**: if the same **externalId** arrives with a different amount, that is a business conflict requiring resolution.

Another option is **upsert with $setOnInsert** for create-once flows:

~~~javascript
db.import_orders.updateOne(
  {
    sourceSystem: "ERP",
    externalId: "ERP-1001"
  },
  {
    $setOnInsert: {
      sourceSystem: "ERP",
      externalId: "ERP-1001",
      amount: NumberDecimal("250000.00"),
      status: "NEW"
    }
  },
  { upsert: true }
);
~~~

Combined with an appropriate unique index, this works well for idempotent ingestion. If business logic requires updating new data, do not mechanically use **$setOnInsert**; define version, timestamp, or deduplication rules instead.

### 13.3. Managing Failing Operation Indices

When handling **BulkWriteException** in Java, error info may include the **index** of the operation within that bulk list along with the error code and message. The application must maintain the mapping across:

~~~text
input record -> logical batch -> operation index -> sourceId
~~~

If you split 10,000 records into 20 batches of 500 records, **operation index 3** of the 5th batch is not **line 3 of the entire file**. Store **sourceId/line number** and each batch's offset to report errors accurately. Do not try to guess global indices from internal details of how the driver splits wire batches.

### 13.4. Retryable Writes Do Not Mean Every Bulk Operation Retries Safely

MongoDB Drivers support **retryable writes** for eligible operations and conditions, typically via **retryWrites=true**. However:

- Not every operation in a bulk request shares the same retry eligibility.
- Certain multi-document updates/deletes or transactional operations have different semantics.
- The driver may already have retried within supported bounds before surfacing an error.
- Application-level retries must still account for duplicate keys, side effects, and uncertain states.

The reliable solution is an **idempotent ingestion contract**, persisting source checkpoints and replaying only items identified as needing reprocessing.

## 14. Write Concern and Batch Size

**Write concern** determines acknowledgement conditions. In a replica set, a large batch combined with **w: "majority"** can exhibit higher latency than **w: 1**, depending on replication lag and load. Batch thresholds must be measured under actual production write concern settings.

Example configuration in mongosh:

~~~javascript
db.import_orders.insertMany(
  [
    {
      sourceSystem: "ERP",
      externalId: "ERP-1002",
      amount: NumberDecimal("150000.00")
    },
    {
      sourceSystem: "ERP",
      externalId: "ERP-1003",
      amount: NumberDecimal("300000.00")
    }
  ],
  {
    ordered: false,
    writeConcern: {
      w: "majority",
      wtimeout: 10000
    }
  }
);
~~~

**wtimeout** caps how long the server waits to satisfy the write concern; it does not automatically set a timeout for all encoding, sending, or driver processing stages. In Java, there are also settings such as server selection timeout, socket/read timeout, or operation timeout depending on version and API.

**Batch size is not a durability policy**: splitting 10,000 documents into 20 batches of 500 does not change the semantics of **w: "majority"**, though it affects processing time, load, and the blast radius of errors to track.

## 15. Transactions Do Not Eliminate Size Limits

A multi-document transaction may be required when business logic demands modifying multiple entities together. However:

- Each BSON document must still obey its size limit.
- Transactions incur state-retention overhead, resources, and time/snapshot limits.
- Huge batches inside a single transaction can increase contention, replication overhead, and timeout risk.
- Never wrap an entire multi-million-row import file in one transaction just to "get atomicity."

If a large import flow must only publish data once the whole file is valid, consider **a staging collection + validation + publish/swap workflow**, or batch/job status flags so incomplete data stays hidden from users. The exact strategy depends on topology and read patterns.

## 16. Batch Size in a Sharded Cluster

In a sharded cluster, the driver sends operations to **mongos**, and the router directs them to the appropriate shards. With unordered bulk writes, MongoDB can distribute operations across multiple shards and exploit more parallelism depending on the workload.

However, a batch of 10,000 documents targeting **one hot shard key** can still overload a single shard. Deciding factors include:

- shard key and value distribution;
- request ratio hitting each shard;
- document/index size;
- network between **mongos** and shards;
- balancing state, replication, and disk health;
- write concern.

If a large batch writes for one "giant" tenant and one shard stays saturated, merely adding more parallel batches will not spread data more evenly. Re-examine the **shard key**, workload, and ingestion rate.

## 17. Choosing Practical Thresholds by Goal

There is no single fixed batch size that fits every application. Start with conservative thresholds and adjust based on measurements.

| Context | Starting Policy to Try | Metrics to Observe |
|---|---|---|
| **REST API creating a few documents** | insertOne or very small batches. | p95/p99 latency, request timeouts. |
| **Offline CSV import** | A few hundred to a few thousand documents, with byte cap and streaming source. | docs/s, MB/s, heap, GC, disk latency, write errors. |
| **Large/variable-size documents** | Byte cap matters more than count; isolate oversized singletons. | per-document BSON bytes, p95 batch bytes, encoding time. |
| **Multi-tenant/multi-shard** | Batch by source or tenant if helpful for fairness; bounded concurrency. | per-shard load, hot tenants, failover effects. |
| **Real-time event stream** | Smaller batches, flush on max wait time. | ingest lag, end-to-end latency, queue depth. |
| **Majority write concern required** | Measure under real majority config; avoid flooding concurrent requests. | majority acknowledgement latency, replication lag. |

These thresholds are only suggestions for **benchmarking**. They do not replace load testing and capacity evaluation.

### 17.1. Incremental Testing

One tuning approach:

1. Select a representative dataset: matching production size distribution, BSON types, indexes, and document counts.
2. Record a baseline with small batches, such as **100 documents** and a bounded number of writers.
3. Step up to 250/500/1,000 documents per trial while keeping byte limits and concurrency controlled.
4. Measure throughput, p95/p99 batch latency, heap, GC, disk I/O, network, write concern latency, and error counts.
5. Once throughput plateaus or latency/resource health degrades, pick the setting prior to that inflection point; re-evaluate separately when the workload changes.

Never benchmark in production using an unbounded import command. Use controlled data and environments, especially when collections carry large indexes or share the cluster with other applications.

### 17.2. Metrics to Log per Batch

~~~text
import_job_id
batch_id
source_offset_start / end
document_count
estimated_bson_bytes
encode_duration_ms
send_duration_ms
ack_duration_ms
inserted_count
duplicate_count
validation_error_count
retry_count
final_status
~~~

These details help distinguish **oversized batches**, **overloaded servers**, **data errors**, and **slow network transfers**. Do not log raw sensitive contents of every document just for debugging.

## 18. Parameters Commonly Confused with Write Batch Limits

| Parameter | Category | Do Not Confuse With |
|---|---|---|
| **maxWriteBatchSize** | Number of operations in one write command batch. | Optimal document count for one API call. |
| **maxBsonObjectSize** | Size of one BSON document. | Total bytes of a logical batch. |
| **maxMessageSizeBytes** | Size of one MongoDB wire message. | HTTP body limit or application heap size. |
| **cursor batchSize** | Number of documents in a **read** result batch. | **Write** batch size of insertMany. |
| **maxTimeMS** | Time limit for eligible operations. | Byte limit or write operation count limit. |
| **maxPoolSize** | Number of connections in the connection pool. | Optimal documents per batch or parallel batches. |
| **w / j / wtimeout** | Write concern acknowledgement level and wait timeout. | Wire protocol request splitting mechanism. |
| **16 MiB document limit** | How many bytes a single document can store. | Size of a file stored via GridFS. |

A parameter name containing "batch" is not necessarily about the write path. For example, **cursor.batchSize()** governs fetching **query results**, not **insertMany()**.

## 19. Common Mistakes During Imports

### 19.1. Batching by 100,000 Documents Because That Is the Server Limit

**Problem:** that is the ceiling for a single write command, not the optimum. Variable-size documents can hit the message byte limit earlier, and the application may run out of RAM.

**Fix:** enforce count/bytes/time thresholds in the application layer and let the driver enforce wire constraints.

### 19.2. Calculating Size with JSON.stringify

**Problem:** string length differs from BSON bytes; ObjectId, Date, Decimal128, Binary, and UTF-8 characters have different representations.

**Fix:** measure BSON with the actual codec, such as **Object.bsonsize** in mongosh or the corresponding BSON encoder in the driver.

### 19.3. Shrinking Batches Still Fails on an Oversized Document

**Problem:** a 20 MiB document exceeds the limit of **one** BSON document; sending 1 document/batch still won't work.

**Fix:** refactor the schema, drop unnecessary data, or use GridFS/object storage for blobs.

### 19.4. Increasing Concurrency to Compensate for Small Batches

**Problem:** too many writers can inflate connection pool queues, replication lag, I/O, and timeouts.

**Fix:** bounded concurrency + backpressure; measure throughput/latency under the same write concern.

### 19.5. Using ordered:true and Expecting Whole-Batch Rollback

**Problem:** documents written before an error can still remain in the collection.

**Fix:** design partial failure handling and choose transactions or compensating workflows if multi-document atomicity is truly needed.

### 19.6. Retrying the Entire Batch After Timeout

**Problem:** some documents may already have been added; retries may hit duplicate key errors or create duplicate records if _id is unstable.

**Fix:** maintain stable identities, use unique business keys, inspect state before retrying, and handle errors per record.

### 19.7. Reporting insertedCount Equal to Submitted Elements

**Problem:** in a 500-document batch with 20 duplicate keys, the number of inserted documents is not 500.

**Fix:** distinguish **attempted count**, **acknowledged success**, **rejected/failed**, **uncertain outcome**, and **previously existing**.

### 19.8. Holding Batches Too Long Under Low Traffic

**Problem:** count/byte thresholds fill slowly, leaving documents sitting in memory for seconds or minutes.

**Fix:** for real-time ingestion, add a **flush interval / max wait age**, and ensure a final flush on graceful stream shutdown.

### 19.9. Treating Compressed Bytes as BSON Bytes

**Problem:** BSON size can differ from compressed network size, pre-encoding JSON size, and on-disk compressed storage size.

**Fix:** measure the right unit at the right layer. MongoDB wire limits and application policies must clearly state what they measure.

## 20. Mini Practice Exercises

### Exercise 1 — Inspecting Server Limits

Run **hello** from Section 2.1 and record the three values. Estimate by hand:

- Roughly how big is the payload for 1,500 documents of ~1 KiB BSON each?
- Roughly how big is the payload for 1,500 documents of ~40 KiB BSON each?
- In each case, which limit is likely hit first: count limit or byte limit?

Note: this calculation ignores overhead and is only for mental modeling, not a replacement for driver request splitting.

### Exercise 2 — Checking BSON Size by Field

~~~javascript
const small = { name: "Mouse", count: NumberInt(10) };
const large = {
  name: "Large description",
  description: "A".repeat(1024 * 1024)
};

print(Object.bsonsize(small));
print(Object.bsonsize(large));
~~~

Compare the output with **JSON.stringify(...).length**. Explain why the two numbers are not necessarily equal.

### Exercise 3 — Manual Count-Based Batching

Practice **2,500 documents** and **maxDocsPerCall = 500** per Section 11. Count the number of **insertMany** calls made by the application and explain why the application call count does not necessarily equal the actual server command count if documents are large.

### Exercise 4 — Ordered/Unordered on Duplicate Key

Create a **unique index** on **orderCode**; run the two examples from Section 8 on a separate test collection. Observe:

- which documents remain after the error;
- what exception/error is reported;
- why **ordered: true** is not equivalent to a transaction.

### Exercise 5 — Designing a 1-Million-Row Import

Suppose documents have BSON sizes from **0.5 KiB to 100 KiB** and the source can emit 30,000 documents/second. Propose:

- count, byte, and time thresholds per batch;
- how to keep the **queue bounded**;
- initial concurrent worker count and tuning plan;
- how to persist source progress to resume after failure;
- how to handle identity/idempotency per record;
- per-record error reporting by **source offset** and **sourceId**.

You do not need to pick one "magic" number right away; what matters is the bounding rules and measurement plan.

## 21. Review Questions

1. What is the difference between a **logical batch**, a **wire batch**, and a **single BSON document**?
2. Why does MongoDB have separate **maxWriteBatchSize** and **maxMessageSizeBytes** limits?
3. Can a document exceeding 16 MiB be inserted by setting batch size = 1?
4. Why should **48,000,000 bytes** not be called exactly **48 MiB**?
5. If the driver already splits batches automatically, why does the application still need a memory-bounded batch builder?
6. When **ordered: false**, what happens if one document hits a duplicate key error?
7. Does a default **insertMany** batch provide whole-batch atomicity? Why or why not?
8. Does a write concern timeout error prove the operation was not saved?
9. Why must stable **_id** or business keys be assigned before retrying?
10. Why should **BSON bytes** be measured rather than JSON character length when enforcing byte thresholds?
11. What problem does backpressure solve that splitting into 500-document batches alone does not?
12. Which metrics should be monitored to decide whether to increase or decrease batch size?

## 22. Conclusion

To insert large volumes of documents reliably into MongoDB, clearly separate **hard server limits** from **application-chosen soft thresholds**:

~~~text
One document:
  BSON size <= server maxBsonObjectSize
  (commonly: 16 MiB)

One write command:
  operations <= maxWriteBatchSize
  (commonly: 100,000)

One wire message:
  message bytes <= maxMessageSizeBytes
  (commonly: 48,000,000 bytes)

Application:
  chunk by count + BSON bytes [+ max wait]
  bounded queue + bounded concurrency
  error accounting + idempotent retry
  measure throughput, latency, and resources
~~~

A solid ingestion pipeline is not just calling **insertMany** instead of **insertOne**. It must manage incoming data flow, per-document size, batch bounds, concurrency, write outcomes, and resumability after errors. **The MongoDB Driver helps ensure requests are protocol-valid; the application is responsible for correctness and operability of the end-to-end workflow.**

### Official MongoDB References

- [MongoDB Limits and Thresholds](https://www.mongodb.com/docs/manual/reference/limits/) — BSON document limits, write batch limits, and related thresholds.
- [db.collection.insertMany()](https://www.mongodb.com/docs/manual/reference/method/db.collection.insertMany/) — inserting multiple documents and ordered/unordered behavior.
- [db.collection.bulkWrite()](https://www.mongodb.com/docs/manual/reference/method/db.collection.bulkWrite/) — bulk operations combining multiple write types.
- [MongoDB Bulk Write Operations](https://www.mongodb.com/docs/manual/core/bulk-write-operations/) — bulk processing and differences between ordered/unordered.
- [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — acknowledgement and write concern error scenarios.
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) — Java API, insertMany, bulkWrite, error handling, and connection settings.
- [Object.bsonsize()](https://www.mongodb.com/docs/manual/reference/method/Object.bsonsize/) and [$bsonSize](https://www.mongodb.com/docs/manual/reference/operator/aggregation/bsonSize/) — measuring BSON document size.

When applying figures or options from this lesson to real systems, check the **MongoDB and driver versions in use**, inspect parameters from the target server, and validate with a representative workload. Values like 500 documents/batch or 4 MiB/batch are operational choices for testing, not fixed technical limits of MongoDB.
