# Capped Collections and Cursors Waiting for New Data

## 1. Problem: Tracking a Continuously Written Stream of Records

Suppose a payment service writes a technical message each time it executes a processing step: receiving a request, calling a payment gateway, receiving a response, and completing. An operations dashboard wants to display new messages as soon as they appear, much like the `tail -f` command on Linux. With a regular `find()` query, the application receives all documents present at read time and the cursor ends. To see new data, the application would have to re-query on its own.

MongoDB provides a set of mechanisms to address this case:

- **Capped collection**: a size-bounded collection managed as a circular buffer; when full, older records are evicted from the dataset to make room for new records.
- **Tailable cursor**: a cursor for capped collections that can remain positioned at the end of the data and read documents **inserted** later.
- **`awaitData`**: an option that causes a `getMore` operation to wait for a period of time when no new documents are available yet, instead of continuously returning empty batches.

In the **SPRING_DATA_MONGODB** module, Spring Data MongoDB helps create capped collections via `MongoTemplate`, open streams using `ReactiveMongoTemplate.tail(...)` or a repository annotated with `@Tailable`, and integrate the listener lifecycle into a Spring application.

~~~text
Writer A -----------+
                    |
Writer B -------+   v
                +--> capped collection: [E97][E98][E99][E100]
                    |                        ^         ^
                    |                        |         |
                    +--> tailable cursor ----+---------+--> wait for E101 insert
                                                              |
Writer C -------------------------------------- insert E101 ---+
                                                              |
                                                     receive E101 and keep waiting
~~~

Lesson objectives:

1. Distinguish between **byte-based** and **document-count** limits, and understand old-record eviction and its storage implications.
2. Create, inspect, and write data to a capped collection using `mongosh` and Spring Data MongoDB.
3. Explain the differences between a regular cursor, `tailable`, and `tailable + awaitData`.
4. Build a reactive Spring Data consumer that follows new documents, actively cancels its subscription, and recognizes stream completion/errors.
5. Identify scenarios where a cursor is closed or data is overwritten before being read, and choose an appropriate mechanism when lossless recovery is required.

## 2. How Capped Collections Work as a Circular Buffer

### 2.1. Capacity Limits

When creating a collection, you declare:

| MongoDB Option | Required? | Meaning |
| --- | --- | --- |
| `capped: true` | Yes, to create a capped collection | Enables the size-bounded collection structure |
| `size` | Yes | Collection size limit in **bytes**; must be greater than 0 |
| `max` | No | Maximum number of documents retained; does not replace the `size` requirement |

MongoDB uses the size limit and, if specified, the document count limit to decide when older records must make room. Because each document varies in size, **`size: 5 MiB` is not equivalent to 5,000 records**, even when `max: 5000` is also configured.

Example of a collection with a maximum of 5 MiB and 5,000 records:

~~~javascript
use tail_demo

db.createCollection("activity_log", {
  capped: true,
  size: 5 * 1024 * 1024,
  max: 5000
})
~~~

The collection above may start evicting old records **before** reaching 5,000 documents if the byte limit is reached first. Similarly, if 5,000 documents are reached before the byte threshold, the document count limit applies.

A capped collection is not like a permanent archival table: once the buffer wraps around, older records are removed from the data source. With multiple concurrent writers, MongoDB also **does not guarantee that the returned order strictly matches the insert order across clients**.

### 2.2. What Is Kept and What Is Lost

~~~text
Available space:
[E1][E2][E3][      ][      ]

After multiple inserts:
[E1][E2][E3][E4][E5]

Adding E6 when at capacity:
[E2][E3][E4][E5][E6]
 ^ E1 is no longer in the collection
~~~

The diagram only illustrates the *logical* circular buffer; it is not a map of physical byte locations on disk. Do not assume that MongoDB always removes exactly one document per insert: the number of evicted documents depends on actual sizes and thresholds.

There are three important consequences:

- **Retention is determined by capacity and write rate**, not by a guaranteed duration. A write spike can reduce retention to a few minutes instead of several hours.
- **A slow consumer can lose its read position.** When the record at the cursor's current position has been overwritten, the tailable cursor can become invalid.
- **There is no infinite history for replay.** A record evicted from a capped collection cannot be retrieved from that collection itself.

### 2.3. Design Constraints

According to MongoDB limitations, keep in mind:

- Capped collections **cannot be sharded**.
- Do not perform **writes to a capped collection inside a transaction**; do not use `$out` to write results into one.
- A capped collection is not a good fit for general-purpose CRUD requiring arbitrary deletes or document-size growth updates. Treat each document as an **append-only** record and avoid updates that increase document size.
- The collection must be **explicitly created as capped**. If an application accidentally inserts into a non-existent collection name first, MongoDB may create a regular collection; tailable queries will then fail to behave as expected.
- A capped collection is not a queue with ACKs, transactional consumption, or consumer groups. Each subscriber reads independently; MongoDB does not partition work across subscribers.

For data requiring time-based deletion, indexed queries, state mutations, or sharding, a **regular collection + TTL index** or another mechanism may be more appropriate.

## 3. Creating and Inspecting a Capped Collection with mongosh

Use a local MongoDB instance or a deployment where collection creation is permitted, then run:

~~~javascript
use tail_demo

// Only create if no collection with this name exists yet:
db.createCollection("activity_log", {
  capped: true,
  size: 5242880,
  max: 5000
})

// Must return true:
db.activity_log.isCapped()

// Inspect declared options:
db.getCollectionInfos({ name: "activity_log" })

// A seed record so the cursor has data when opened:
db.activity_log.insertOne({
  source: "bootstrap",
  level: "INFO",
  message: "Collection is ready",
  createdAt: new Date()
})
~~~

When re-running the example, skip `createCollection` if the collection already exists. Do not delete real data just to re-run an example. To check current storage usage and document count:

~~~javascript
db.activity_log.stats()

db.activity_log.find()
  .sort({ $natural: -1 })
  .limit(5)
~~~

`$natural: -1` lets you inspect documents near the end of the collection first. To observe natural order in the tailable read direction, you can use `$natural: 1`. This is natural storage order, **not a guarantee of ordering by `createdAt`, `_id`, or a global cross-client order**.

### 3.1. Creating the Collection from Spring Data MongoDB

If configuring schema in Java, invoke `MongoTemplate` during a managed initialization step (migration/bootstrap) **before writers and consumers start**:

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.CollectionOptions;

public final class ActivityLogSchema {
    private static final String COLLECTION = "activity_log";

    private ActivityLogSchema() {}

    public static void createForFreshDatabase(MongoTemplate mongoTemplate) {
        if (mongoTemplate.collectionExists(COLLECTION)) {
            // Do not treat "already exists" as proof the collection is capped.
            // Verify via isCapped() or listCollections options.
            return;
        }

        mongoTemplate.createCollection(
            COLLECTION,
            CollectionOptions.empty()
                .capped()
                .size(5L * 1024 * 1024)
                .maxDocuments(5000)
        );
    }
}
~~~

The example above demonstrates the `CollectionOptions.empty().capped().size(...).maxDocuments(...)` API. In multi-instance applications, have **a single coordinating process** run migrations, handle concurrent creation across instances, and **fail fast** if the collection already exists as non-capped. Having matching collection names and entity types does not automatically convert a regular collection into a capped one.

### 3.2. Resizing After Creation

MongoDB provides administrative commands for modifying capped collection limits, such as `collMod` with `cappedSize` or `cappedMax` in supported versions. This is a capacity-changing operation that can evict older records; use it only after checking the server version and data retention plan. Do not assume changing a property on a Java entity will alter an existing collection's properties.

## 4. Regular Cursors, tailable, and awaitData

A regular cursor opened via `find()` reads batches and closes once results are exhausted. Data inserted afterward does **not** reopen a regular cursor.

A tailable cursor differs in that it keeps its position at the end of a capped collection. Even after reading all existing documents, the client can issue `getMore` to receive subsequently inserted documents.

~~~mermaid
flowchart TD
    A["Open find on capped collection"] --> B["Read existing documents"]
    B --> C{"Current batch exhausted?"}
    C -->|"No"| B
    C -->|"Yes, regular cursor"| D["Cursor ends"]
    C -->|"Yes, tailable"| E["Keep cursor at end"]
    E --> F{"New insert?"}
    F -->|"Yes"| G["getMore returns new documents"]
    G --> E
    F -->|"Not yet, awaitData"| H["getMore waits for data / timeout"]
    H --> E
~~~

| Mechanism | When current data is exhausted | When no new records exist yet | Purpose |
| --- | --- | --- | --- |
| Regular `find` | Cursor closes | Does not wait | Finite result queries |
| `tailable` | Cursor can remain open | Client must issue another `getMore` | Follow inserts on a capped collection |
| `tailable + awaitData` | Cursor can remain open | Server waits briefly during `getMore` | Follow inserts with fewer empty polls |

**`awaitData` does not promise to wait forever.** If the wait timeout expires with no documents available, the server may return an **empty batch** while the cursor remains alive. Therefore, an `empty batch` does not mean "end of stream." The driver or Spring Data layer must continue interacting with a still-valid cursor. The wait duration can be configured via the driver's `maxAwaitTimeMS` mechanism.

A tailable cursor **does not use indexes** for its read path; by nature it scans in natural order. When a query has a filter, the initial scan can be expensive, and if no matching document exists when opened, the stream may terminate early. For indexed conditional reads, MongoDB generally recommends a regular cursor + tracking the last seen value to re-query.

### 4.1. Trying Directly in Two mongosh Sessions

In window A, after creating and seeding the collection:

~~~javascript
use tail_demo

const cursor = db.activity_log.find({})
  .tailable({ awaitData: true })
  .maxAwaitTimeMS(2000)

// Read an existing document:
if (cursor.hasNext()) {
  printjson(cursor.next())
}

// Call hasNext()/next() again to observe new documents.
// You must manage open cursor state, timeouts, and loop termination
// when writing a long-running polling loop.
~~~

In window B:

~~~javascript
use tail_demo

db.activity_log.insertOne({
  source: "payments",
  level: "INFO",
  message: "Payment request accepted",
  createdAt: new Date()
})
~~~

Switch back to A and call `cursor.hasNext()` then `cursor.next()` to receive the new record (if the cursor is still valid). `hasNext()` may wait for a period; a single `false` return due to timeout is not enough to conclude the entire data source has ended. In production code, prefer letting the driver/Spring Data manage the receive loop rather than writing a CPU-busy `while(true)` loop.

## 5. Reactive Spring Data: Reading Document Streams with tail(...)

In Spring Data MongoDB, the primary API is:

~~~java
Flux<T> tail(Query query, Class<T> entityClass, String collectionName);
~~~

This method is defined on `ReactiveMongoOperations`/`ReactiveMongoTemplate`. It returns a `Flux<T>`; reading begins upon **subscription**. In the example below, we consume `org.bson.Document` directly to focus on the cursor and avoid assumptions about entity mapping.

Project requirements: Spring Boot with **Spring Data MongoDB Reactive** (for example, the `spring-boot-starter-data-mongodb-reactive` starter), connected to the `tail_demo` database and the properly created `activity_log` collection. A typical local configuration:

~~~properties
spring.data.mongodb.uri=mongodb://localhost:27017/tail_demo
~~~

### 5.1. Reactive Consumer with a Clear Lifecycle

~~~java
import jakarta.annotation.PreDestroy;
import org.bson.Document;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Component;
import reactor.core.Disposable;
import reactor.core.publisher.Flux;

@Component
public class ActivityTailConsumer {
    private static final Logger log =
        LoggerFactory.getLogger(ActivityTailConsumer.class);

    private final ReactiveMongoTemplate mongoTemplate;
    private Disposable subscription;

    public ActivityTailConsumer(ReactiveMongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void start() {
        Flux<Document> stream = mongoTemplate.tail(
            new Query(),
            Document.class,
            "activity_log"
        );

        subscription = stream.subscribe(
            event -> log.info(
                "Source={}, level={}, message={}",
                event.getString("source"),
                event.getString("level"),
                event.getString("message")
            ),
            error -> log.error("Tailable cursor encountered an error", error),
            () -> log.warn("Tailable cursor completed")
        );
    }

    @PreDestroy
    public void stop() {
        if (subscription != null) {
            subscription.dispose();
        }
    }
}
~~~

Key points to read accurately from this code:

1. `new Query()` means **no document filter**; the consumer will receive existing documents first, then wait for new documents while the cursor remains valid.
2. `tail(...)` builds the `Flux` source, whereas `subscribe(...)` registers consumption. Merely declaring a `Flux` without subscribing produces no log output.
3. The `error` lambda records stream failure; the `complete` lambda records stream termination. **This is not yet a self-recovering system**.
4. `subscription.dispose()` during application shutdown helps close the cursor/release resources. Never create a new subscription per HTTP request.
5. Reading a document does not mean a side effect such as indexing into Elasticsearch, sending an email, or updating another database has completed. This example only logs to demonstrate the data source.

In production, if the handler performs asynchronous I/O, prefer processing items through a `concatMap` pipeline or appropriate concurrency limits, avoiding nested `subscribe()` calls inside `doOnNext`; monitor errors and handler latency.

### 5.2. Reactive Writer to Test the Stream

A writer can use `ReactiveMongoTemplate.insert(...)` and return a `Mono` for the caller to subscribe to or compose:

~~~java
import java.time.Instant;
import java.util.Date;

import org.bson.Document;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import reactor.core.publisher.Mono;

public final class ActivityLogWriter {
    private final ReactiveMongoTemplate mongoTemplate;

    public ActivityLogWriter(ReactiveMongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public Mono<Document> append(String message) {
        Document event = new Document("source", "payments")
            .append("level", "INFO")
            .append("message", message)
            .append("createdAt", Date.from(Instant.now()));

        return mongoTemplate.insert(event, "activity_log");
    }
}
~~~

The caller can invoke `writer.append("Order received")` and **subscribe** within the application flow or an appropriate reactive composition. Calling the method and ignoring the returned `Mono` will not execute the insert. Furthermore, the capped collection must be created before the writer runs.

### 5.3. Should You Filter Directly in tail?

For example:

~~~java
import static org.springframework.data.mongodb.core.query.Criteria.where;

Query paymentsOnly = new Query(where("source").is("payments"));

Flux<Document> payments = mongoTemplate.tail(
    paymentsOnly,
    Document.class,
    "activity_log"
);
~~~

This filter is valid expressively, but has a drawback: if no record with `source = "payments"` exists when opened, the cursor may not remain open long-term. It also does not leverage indexes the way a regular `find` does.

For aggregated logs, a simple option is to tail all documents and filter in the consumer when throughput is low enough and extra reads are acceptable; for high-volume data requiring indexed queries, consider **watermark polling** or a more suitable event-publishing mechanism.

## 6. Reactive Repositories and @Tailable

If you have mapped documents to a domain type, Spring Data allows annotating a repository query method with `@Tailable`. Minimal example for an entity with appropriate getters/setters/constructors:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import org.springframework.data.mongodb.repository.Tailable;
import org.bson.types.ObjectId;
import reactor.core.publisher.Flux;

@Document(collection = "activity_log")
public class ActivityEvent {
    @Id
    private ObjectId id;
    private String source;
    private String level;
    private String message;

    // Declare constructors and getters/setters per project mapping
    // conventions; omitted here to keep the repository focus clear.
}

public interface ActivityEventRepository
        extends ReactiveMongoRepository<ActivityEvent, ObjectId> {

    @Tailable
    Flux<ActivityEvent> findBySource(String source);
}
~~~

`@Tailable` only makes sense for methods returning multiple elements, such as `Flux<ActivityEvent>`. It does not turn a regular collection into a capped one, does not automatically guarantee recovery when a cursor dies, and is not meant for fetching a single `Mono` result. Just like the `paymentsOnly` example, `findBySource(...)` risks completing if no matching record exists initially. Use a repository when the entity model is clear; use `ReactiveMongoTemplate.tail(...)` when you need control over the query, collection name, or raw BSON documents.

## 7. When Only Synchronous MongoTemplate Is Available

Spring Data MongoDB also supports tailable cursors via `MessageListenerContainer` with `TailableCursorRequest` when an application uses the synchronous driver. A synchronous listener requires a long-running task and thread resources, so applications with many subscribers should generally consider reactive first.

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.messaging.DefaultMessageListenerContainer;
import org.springframework.data.mongodb.core.messaging.MessageListener;
import org.springframework.data.mongodb.core.messaging.TailableCursorRequest;

public final class SyncTailExample {
    public static void run(MongoTemplate template) {
        DefaultMessageListenerContainer container =
            new DefaultMessageListenerContainer(template);

        MessageListener<Document, Document> listener =
            message -> System.out.println(message.getBody().toJson());

        TailableCursorRequest request = TailableCursorRequest.builder()
            .collection("activity_log")
            .publishTo(listener)
            .build();

        container.register(request, Document.class);
        container.start();

        // Production app: keep the container in a managed bean
        // and call container.stop() at lifecycle shutdown.
    }
}
~~~

This snippet only illustrates registration; it is **not** a complete self-stopping program. Keep the `container` instance in a Spring bean and call `container.stop()` on shutdown. The listener does not replace retries, checkpointing, or deduplication at the business layer.

## 8. Scenarios Where the Stream Stops or Loses Records

### 8.1. Empty Collection or Non-Matching Query

A tailable cursor can close immediately if the query returns no matching documents when created. That is why the lab **inserted a seed record before subscribing**. In real systems, you cannot always rely on a dummy seed to guarantee a match for every filter; you must design controlled reopening and account for potential record loss during the gap.

~~~text
T0: capped collection is empty
T1: consumer opens tail -> cursor has no initial result, may complete
T2: writer inserts E1
T3: consumer has already stopped, so it misses E1
~~~

Normal `Flux` completion must also be observed, not just exceptions. If you only configure `retryWhen(...)` for **errors**, silent completion may never re-subscribe; a repeat/resubscribe mechanism with an appropriate delay may be needed. However, **reopening a cursor does not recover records that were already evicted**.

### 8.2. Cursor Overtaken by the Circular Buffer

~~~text
Consumer reads up to E100
Writer produces E101 ... E50000 very quickly
Collection is small, E100 and subsequent events are evicted
Consumer calls getMore -> current position may no longer be valid
~~~

Do not let consumer throughput remain lower than event generation rate over a long period and expect `awaitData` to fix it. `awaitData` only helps wait when data is **not yet available**; it does not expand capacity or create a durable queue.

### 8.3. Disconnects, Failover, and Restarts

A cursor's lifecycle is tied to a connection/session and server state. When the application stops, a connection drops, a collection is dropped, or a cursor is invalidated, the consumer must reopen and determine what time window was missed.

**Tailable cursors do not provide a resume token** like MongoDB Change Streams. If recovery is required, you must design it yourself: include an event identifier/sequence number on each document, persist a processing watermark, retain a durable history long enough, and provide a **backfill/reconciliation** path via an appropriate query. Merely saving `Instant.now()` on restart cannot prove no events were missed.

In particular, `ObjectId` helps identify documents, but it is **not a strict transactional sequence number across multiple writers**; you cannot infer exactly-once delivery or total order just by comparing `_id`.

### 8.4. Slow Subscribers and Backpressure

Even though `Flux` supports backpressure, writers can still keep inserting into the capped collection. Slow subscribers, blocking handlers, oversized in-memory buffers, or exhausted connection pools all increase the risk of the cursor falling behind. If records are critical business events, do not casually apply `onBackpressureDrop`: dropping at the consumer means losing delivered data.

## 9. Choosing the Right Mechanism for Product Requirements

| Requirement | Capped + tailable cursor | Change stream | Periodic query / regular data |
| --- | --- | --- | --- |
| Follow **newly inserted documents** | Suitable for bounded logs/buffers | Has insert events along with other change types | Can use a watermark |
| Follow **updates/deletes** | Does not emit update/delete events in the CDC sense | Suitable | Requires diff/tombstone design |
| Long-term retention | Unsuitable if overwritten | Reads history only within oplog window; not an event store | Depends on retention design |
| Topology requirements | Capped collection; works on standalone | Requires replica set or sharded cluster | Depends on query/database |
| Resume after restart | No resume token | Has resume token bounded by oplog history | Self-managed watermark |
| Source collection sharding | Capped does not support sharding | Can watch eligible collections in a cluster | Regular collections can be sharded |
| Consumer groups / exactly-once | No | Not built-in | Not built-in |

Some typical architectural choices:

- **Live technical log viewer where losing old lines is acceptable**: capped collection + tailable cursor is a clean implementation.
- **Syncing a search index when orders undergo insert, update, delete**: prefer change streams if topology and recovery requirements allow.
- **Long-term audit/compliance history requiring multi-field queries**: use a regular collection with retention/index/backup policies; a capped collection is not a single source of truth.
- **Order processing queue guaranteeing retries/ACKs across competing workers**: requires a durable queue/outbox/broker and idempotency; a tailable cursor is only a read signal.
- **Time-range or indexed-filter queries**: a regular cursor with a watermark can be more efficient than a tailable cursor's natural-order scan.

## 10. Capacity Estimation and Operational Observability

If each log document averages 800 bytes, the system ingests 200 documents/second, and you want to retain roughly 10 minutes of data:

~~~text
200 docs/sec × 600 sec = 120,000 documents
120,000 × 800 bytes = 96,000,000 bytes (~91.6 MiB)
~~~

This covers average payload size only; BSON overhead, metadata, size variance, traffic spikes, and document-count limits can make actual retention lower. Use capacity with headroom and **measure under load testing**. The 5 MiB configuration in this lesson is for demo purposes only and will not retain 10 minutes at the throughput above.

Metrics to collect at the application and MongoDB layers:

| Signal | Question to Answer |
| --- | --- |
| `isCapped()` and collection options | Is the collection actually of the right type and limits? |
| `countDocuments`, `stats`, and actual size | How much capacity is the buffer currently using? |
| Open subscription/cursor count | Are duplicate listeners being created or disposals missed? |
| Elapsed time from `createdAt` to processing | Is the reader keeping up with writers? |
| `onError`/`onComplete` counts, reopen counts | Is the consumer silently dying or looping on errors? |
| Missing event sequence numbers / reconciliation errors | Were any records lost during restart/overwrite? |
| Write rate and average/max document size | What is the expected retention under increased load? |

Do not attach high-cardinality document IDs or raw messages to metric labels. Distinguish between "5 minutes with no logs because the system is idle" and "5 minutes with no logs because the consumer terminated": monitor subscription state and worker heartbeats.

### 10.1. Common Troubleshooting

| Symptom | Causes to Check | Appropriate Action |
| --- | --- | --- |
| Error when opening `tail` | Collection does not exist or is not capped | Check `isCapped()`; create/migrate properly before inserting |
| Not receiving new documents | Not subscribed, stream completed, filter does not match | Check `onComplete`/`onError` callbacks, seed, filter, subscriptions |
| Receiving many old documents at startup | `tail(new Query())` reads existing data | Explicitly design bootstrap/starting point; do not assume future-only |
| Dropped lines during write bursts | Capped buffer wraps quickly, slow cursor reads | Increase retention, reduce handler latency, use durable source if lossless |
| High CPU even with no writes | Consumer busy-polling `hasNext` or tight restart loop | Use `awaitData`/reactive, backoff, and inspect cursor state |
| Connection/thread leaks across redeploys | Uncancelled subscription or container not stopped | Bind resource lifecycle to Spring beans |
| Duplicate processing | Two instances tailing simultaneously, or replay after restart | Isolate worker ownership / dedupe by event ID; do not assume exactly-once |

## 11. End-of-Lesson Practice and Self-Check Criteria

Run on a test database:

1. Create `activity_log` as shown in the example and verify `db.activity_log.isCapped() === true`.
2. Insert a seed record. Start the Spring Boot app with `ActivityTailConsumer`, then insert 2 more records from `mongosh`. Observe that the console receives both the record present at subscription time and the subsequently inserted ones.
3. Stop the application and verify resources are released via `dispose()`. Restart to observe that opening a new cursor **does not resume from a token**.
4. On a **separate** test collection, reduce `size`/`max` or insert a large volume of logs to observe old documents being evicted. Compare `find().sort({$natural: 1})` results before and after.
5. Try opening tail on an empty collection or with a non-matching filter; observe completion/errors and determine how subscription lifecycle must be handled.
6. Run the same listener on two test instances. Verify that the same document can arrive at multiple subscribers; explain why this is not a work-sharing queue.

Answer these questions before using this mechanism in production:

- If the stream is completely silent, how do you distinguish "no new inserts" from "consumer is dead"?
- During a 20-minute disconnect when the capped collection only retains 10 minutes, what data is unrecoverable?
- Why does `awaitData` reduce empty polling without guaranteeing zero lost events?
- Why shouldn't you use a tailable cursor directly to capture **update/delete** events on an `orders` collection?
- An application needs to write an order and an outbox event in a single transaction; should a capped collection serve as the primary outbox source? Why?

## 12. Key Takeaways

**Capped collections** provide bounded document storage that automatically evicts old data by limit; **tailable cursors** follow new documents via natural scan; **`awaitData`** lets the cursor wait on the server during each `getMore`. Together, these three are useful for near-real-time log/telemetry streams where losing older history is acceptable.

In Spring Data MongoDB, you can implement this with `ReactiveMongoTemplate.tail(...)`, `@Tailable` on a reactive repository, or `MessageListenerContainer` for the imperative API. Whichever approach you use, create the collection properly beforehand, manage subscriptions, observe completion/errors, size capacity realistically, and provide a dedicated recovery mechanism if zero data loss is required.

### References

- [MongoDB Manual — Capped Collections](https://www.mongodb.com/docs/manual/core/capped-collections/)
- [MongoDB Manual — Create a Capped Collection](https://www.mongodb.com/docs/manual/core/capped-collections/create-capped-collection/)
- [MongoDB Manual — Tailable Cursors](https://www.mongodb.com/docs/manual/core/tailable-cursors/)
- [MongoDB Manual — cursor.tailable()](https://www.mongodb.com/docs/manual/reference/method/cursor.tailable/)
- [Spring Data MongoDB — Tailable Cursors](https://docs.spring.io/spring-data/mongodb/reference/mongodb/tailable-cursors.html)
- [Spring Data MongoDB — ReactiveMongoTemplate API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/ReactiveMongoTemplate.html)
