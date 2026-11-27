# Implementing a Change Stream with Resume Checkpoints and Deduplication in MongoDB

## 1. Integrated Practice: Goal and Final Outcome

We will build a Java service that watches changes on the `sales.orders` collection in MongoDB. Whenever an order is created, updated, replaced, or deleted, the service updates a fast-read projection collection named `sales.order_read_models`.

Unlike basic examples that merely call `watch()` and `println`, this consumer must **resume cleanly after a restart** and **never apply the same event twice**.

Upon completion, you will be able to:

1. Start a dedicated MongoDB replica set for the lab.
2. Open a Change Stream using the MongoDB Java Sync Driver.
3. Read the `resume token` in BSON form and persist it durably in MongoDB.
4. Record `processed_changes` receipts to identify already-processed events.
5. Update the read model, receipt, and checkpoint within **a single transaction on the same MongoDB deployment**.
6. Stop the consumer, restart it, and resume from the checkpoint.
7. Intentionally rewind the checkpoint to an older token to verify deduplication.
8. Recognize non-resumable errors, unexpected events, and the boundaries of this model.

Expected flow:

```text
                     sales.orders
                           |
                           | INSERT/UPDATE/REPLACE/DELETE
                           v
                    MongoDB oplog
                           |
                           v
                  Change Stream cursor
                           |
                           v
                   Java consumer
                           |
                           v
               Target transaction
                 /          |           \
                v           v            v
       order_read_models  processed_changes  consumer_checkpoints
           (projection)      (receipt)         (resume token)
                \            |              /
                 \___________|_____________/
                             |
                        COMMIT succeeds
                             |
                             v
                      Read next event
```

**Important scope note:** this lab places both source and target collections inside **the same replica set** so a single transaction can cover the projection, receipt, and checkpoint. When source and target reside on two separate clusters—or when a side effect involves email, payments, or an HTTP API—this transaction cannot guarantee atomicity across external systems. Later sections cover safe scaling patterns.

---

## 2. Essential Background Knowledge

**Change Stream** is MongoDB's API for subscribing to recorded data changes on a supported collection, database, or deployment.

An event can carry:

```javascript
{
  _id: {
    _data: "opaque-resume-token"
  },
  operationType: "update",
  clusterTime: Timestamp({ t: 1794662400, i: 1 }),
  ns: {
    db: "sales",
    coll: "orders"
  },
  documentKey: {
    _id: "O100"
  },
  updateDescription: {
    updatedFields: { status: "PAID" },
    removedFields: []
  }
}
```

Key distinctions:

- `event._id`: the **resume token** locating the event in the Change Stream.
- `event.documentKey._id`: the ID of the changed business document.
- `clusterTime`: logical timestamp; it **does not replace** the resume token.
- `operationType`: `insert`, `update`, `replace`, `delete`, or other administrative events.
- `fullDocument`: document included per Change Stream option; not always present.

### 2.1. Necessary Guarantees

Change Streams can resume from a supported point while history remains available, yet they do not automatically make external side effects outside MongoDB exactly-once. For instance, a consumer might update a database, crash before saving its token, and then redeliver the same event.

### 2.2. Why Use a Receipt?

A receipt keyed by unique event identity records whether an event has already been applied to the target. It complements the checkpoint:

- **Checkpoint** tells the consumer where to resume reading.
- **Receipt** tells whether a specific event was already applied.
- **Transaction** ensures the receipt, projection, and checkpoint commit or roll back together in this lab.

### 2.3. Why Ordering Still Matters

An older event applied after a newer event can overwrite state:

```text
E1: status = PAID
E2: status = REFUNDED

Apply E2 first, then E1
=> target becomes wrong (PAID)
```

This lab enforces **one reader, one sequential handler**. When scaling concurrently, you must add per-key ordering, version fencing, or an equivalent protocol.

---

## 3. Prerequisites

You need:

- Java 17 or a Java version compatible with your driver.
- Maven or your project's build tool.
- MongoDB Java **Sync Driver**.
- A MongoDB deployment supporting Change Streams: replica set or sharded cluster.
- Privileges to read the source, create/write target collections, and use transactions in the lab.
- `mongosh` to seed data and verify state.
- Docker if using a local MongoDB container.
- One terminal running the Java consumer and one terminal running `mongosh`.

**Never run `drop()`, modify checkpoints, or shut down `mongod` processes in production.** All data-mutating commands here belong strictly to an isolated lab database.

### 3.1. Version and Topology

Example commands may use the MongoDB 7.0 image for the lab; do not treat that as a hard requirement or latest-version recommendation. Match MongoDB Server, FCV, and Java driver versions to your real system. Change Stream APIs, pre/post-images, and server configuration vary across releases.

### 3.2. Standalone Is Not Enough

A standalone `mongod` does not support Change Streams. A **single data-bearing member** replica set works for a change-detection and transaction lab, though it lacks the fault tolerance and elections of a multi-member replica set.

---

# PART I — CREATING THE LAB ENVIRONMENT

## 4. Start a Single-Node Replica Set with Docker

Example in a Bash terminal with Docker installed:

```bash
docker run -d \
  --name mongo-change-lab \
  -p 127.0.0.1:27017:27017 \
  mongo:7.0 \
  --replSet rs0 \
  --bind_ip_all
```

Initialize the replica set:

```bash
docker exec mongo-change-lab mongosh \
  --quiet \
  --eval 'rs.initiate({_id:"rs0", members:[{_id:0, host:"localhost:27017"}]})'
```

Verify:

```bash
docker exec mongo-change-lab mongosh \
  --quiet \
  --eval 'rs.status().members.map(m=>({name:m.name,state:m.stateStr}))'
```

Wait until the member reaches `PRIMARY`.

### 4.1. Connection String for the Lab

Because this container publishes its port on `127.0.0.1`, you can use:

```text
mongodb://127.0.0.1:27017/?replicaSet=rs0&directConnection=true
```

`directConnection=true` is used here **solely to simplify connecting to a single-node lab**. Production replica sets should use topology discovery with multiple seeds or an SRV URI, TLS, and proper authentication.

### 4.2. Docker Hostname Considerations

Member hostnames advertised in the replica set config must resolve from wherever the driver connects. Using `localhost:27017` fits a local lab publishing its port to the host; for Docker Compose, Kubernetes, or container-to-container clients, use hostnames/DNS resolvable on that network. If the driver connects initially and then fails switching to an unreachable hostname, fix the member config and URI rather than randomly tweaking retry timeouts.

### 4.3. Do Not Run Unauthenticated Network-Exposed MongoDB

This example binds to host loopback to restrict access. Multi-host and production environments require TLS, authentication/keyfiles, and network policies. Never apply an unauthenticated lab setup to a real cluster.

---

## 5. Create Dedicated Collections

Enter `mongosh`:

```bash
docker exec -it mongo-change-lab mongosh
```

In the shell:

```javascript
use sales;

db.createCollection("orders");
db.createCollection("order_read_models");
db.createCollection("processed_changes");
db.createCollection("consumer_checkpoints");
```

If a collection already exists, handle it according to your test environment's state; never run reset scripts on namespaces you do not own.

### 5.1. Role of Each Collection

| Collection | Contents | Written By |
| --- | --- | --- |
| `orders` | Source order data | Application / lab `mongosh` |
| `order_read_models` | Materialized document projection for fast reads | Change Stream consumer |
| `processed_changes` | Receipts for applied events | Change Stream consumer |
| `consumer_checkpoints` | Last committed resume token | Change Stream consumer |

### 5.2. Sample Order Structure

```javascript
{
  _id: "O100",
  tenantId: "T1",
  customerId: "C100",
  status: "PENDING",
  totalMinor: NumberLong("199000"),
  version: NumberLong("1")
}
```

In this lab `_id` uses strings for readability. MongoDB also supports `ObjectId` or other valid BSON types. In a production consumer, never coerce `ObjectId` into strings if the target needs type preservation.

### 5.3. Unique Receipt Index

Every collection has a default unique `_id` index. We use a **BSON document as `_id`** for receipts, embedding both the consumer identity and the full resume token:

```javascript
{
  _id: {
    consumer: "orders-projection-v1",
    token: {
      _data: "opaque-resume-token"
    }
  }
}
```

The same consumer + the same token produces an identical `_id`, so only one receipt can ever be inserted.

**Do not key the receipt by `event.getDocumentKey().get("_id")`** because multiple updates to the same order are distinct events.

---

## 6. Maven Dependencies

An illustrative `pom.xml` for Java 17, Maven, and the MongoDB Java Sync Driver:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>example.mongodb</groupId>
  <artifactId>change-stream-idempotent-lab</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <mongodb.driver.version>5.5.0</mongodb.driver.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.mongodb</groupId>
      <artifactId>mongodb-driver-sync</artifactId>
      <version>${mongodb.driver.version}</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.0</version>
        <configuration>
          <mainClass>example.mongodb.ChangeStreamOrderConsumer</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

These versions are **an illustrative dependency set**, not necessarily the latest releases. Before running, check Maven Central and the Java Driver / MongoDB Server compatibility matrix.

Project layout:

```text
change-stream-idempotent-lab/
  pom.xml
  src/
    main/
      java/
        example/
          mongodb/
            ChangeStreamOrderConsumer.java
```

---

# PART II — CHECKPOINT AND IDEMPOTENCY DESIGN

## 7. Consumer ID Convention

We use:

```text
orders-projection-v1
```

A consumer ID helps:

- Separate multiple logical pipelines.
- Prevent different consumers from overwriting a shared checkpoint.
- Namespace receipt keys.
- Tie `pipelineVersion` to processed state.

If you later change scope, filters, or transform semantics incompatibly, adopt a new `consumerId`/generation or run a controlled checkpoint migration.

### 7.1. Never Share an ID Across Different Consumers

A consumer building `orderReadModels` and another sending emails must not share one checkpoint when they advance independently.

### 7.2. The Lab Uses One Active Instance

In this setup, **run only one process** of `ChangeStreamOrderConsumer` for `orders-projection-v1` at a time. Running two instances lets both read the same tokens and contend in transactions; unique receipts prevent duplicate committed receipts, yet checkpoint ownership and ordering require extra lease/fencing for production-grade multi-instance safety.

---

## 8. Checkpoint Schema

A checkpoint document:

```javascript
{
  _id: "orders-projection-v1",
  stream: "sales.orders",
  version: 1,
  resumeToken: {
    _data: "opaque-server-generated-value"
  },
  updatedAt: ISODate("2026-11-14T10:00:00Z")
}
```

`resumeToken` must preserve **the exact BSON type** returned by the Java Driver.

### 8.1. Do Not Convert the Token to a Timestamp

Never replace it with:

```javascript
{
  lastClusterTime: ISODate("2026-11-14T10:00:00Z")
}
```

`clusterTime` does not uniquely identify each event. In particular, multiple operations inside one transaction can share a logical timestamp.

### 8.2. Do Not Parse `_data`

`resumeToken` is opaque. Never slice prefixes or decode raw bytes to infer ordering. Simply store it and pass it back to `resumeAfter` or `startAfter` as appropriate.

### 8.3. Distinguish Read Tokens from Processed Tokens

A consumer may have fetched event E20 before writing its projection. A token for E20 sitting in RAM **must not** yet be persisted as a durable checkpoint.

---

## 9. Deduplication Receipt Schema

A receipt keyed by consumer and token:

```javascript
{
  _id: {
    consumer: "orders-projection-v1",
    token: {
      _data: "opaque-event-token"
    }
  },
  operationType: "update",
  processedAt: ISODate("2026-11-14T10:00:00Z")
}
```

### 9.1. Why Keep Receipts in the Same Transaction?

If the receipt writes successfully and the projection fails, a replay sees the receipt and skips the event -> lost update.

If the projection writes successfully and the receipt fails, a replay can re-apply the event -> bug for non-idempotent logic.

In this lab, `receipt + projection + checkpoint` commit inside one transaction, leaving no commit gap among the three writes.

### 9.2. Do Not Set an Arbitrary Short TTL on Receipts

If a receipt expires while the consumer can still replay that event, an old event can be reprocessed as new. Retention must align with replay/rebootstrap horizons, checkpointing policy, and business risk.

### 9.3. When Rebootstrap Alters Event Tokens

A resume token guards against replaying the **exact same change event**. If a rebootstrap or migration emits a **new business event** representing the same action, its stream token can differ. Email/payment dispatchers need a stream-independent **business operation ID**.

---

## 10. Transaction Boundary

Each event is processed as follows:

```text
Read event E100
       |
       v
BEGIN TRANSACTION
       |
       +--> find receipt E100
       |
       +--> if absent:
       |       insert receipt E100
       |       upsert/delete projection
       |
       +--> replace checkpoint with token E100
       |
       v
COMMIT TRANSACTION
       |
       v
Read next event
```

If the transaction aborts, neither the projection, the receipt, nor the checkpoint commits.

### 10.1. Requirements

- Target collections and the transaction session belong to **the same MongoDB deployment**.
- MongoDB topology supports multi-document transactions.
- Write concern/durability satisfies requirements.
- Transactions remain short and safe to retry under driver semantics.
- Zero external API calls inside the transaction callback.

### 10.2. Is Idempotency Still Necessary?

Yes. Transactions close one internal gap, yet whenever:

- A consumer redeploys with an older checkpoint,
- Another worker reads overlapping events,
- An operator runs a manual replay, or
- Side effects live outside the transaction,

receipts/idempotency remain a vital safeguard.

### 10.3. What Does the Lab Guarantee?

When the transaction **commits**:

```text
receipt exists
projection reflects event
checkpoint has event token
```

When the transaction **aborts**:

```text
no receipt for event
no projection change from transaction
no checkpoint advance from transaction
```

This guarantees atomicity across target writes within the same deployment; it does not prove external systems outside MongoDB completed their work.

---

# PART III — END-TO-END JAVA IMPLEMENTATION

## 11. Complete Class: ChangeStreamOrderConsumer

Create `src/main/java/example/mongodb/ChangeStreamOrderConsumer.java`.

```java
package example.mongodb;

import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.TransactionOptions;

import com.mongodb.client.ChangeStreamIterable;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoChangeStreamCursor;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;

import com.mongodb.client.model.Filters;
import com.mongodb.client.model.ReplaceOptions;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.FullDocument;
import com.mongodb.client.model.changestream.OperationType;

import org.bson.BsonDocument;
import org.bson.BsonString;
import org.bson.Document;

import java.time.Instant;
import java.util.Date;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class ChangeStreamOrderConsumer {

    private static final String CONSUMER_ID =
        "orders-projection-v1";

    private static final String DATABASE = "sales";

    private static final TransactionOptions TX_OPTIONS =
        TransactionOptions.builder()
            .readConcern(ReadConcern.SNAPSHOT)
            .writeConcern(WriteConcern.MAJORITY)
            .readPreference(ReadPreference.primary())
            .build();

    private final MongoClient client;
    private final MongoCollection<Document> orders;
    private final MongoCollection<Document> readModels;
    private final MongoCollection<BsonDocument> receipts;
    private final MongoCollection<BsonDocument> checkpoints;

    private final AtomicBoolean running =
        new AtomicBoolean(true);

    public ChangeStreamOrderConsumer(MongoClient client) {
        this.client = client;

        MongoDatabase db = client.getDatabase(DATABASE);

        this.orders = db.getCollection("orders");

        this.readModels =
            db.getCollection("order_read_models");

        this.receipts =
            db.getCollection(
                "processed_changes",
                BsonDocument.class
            );

        this.checkpoints =
            db.getCollection(
                "consumer_checkpoints",
                BsonDocument.class
            );
    }

    public void stop() {
        running.set(false);
    }

    public void run() {
        BsonDocument savedToken = loadCheckpoint();

        ChangeStreamIterable<Document> iterable =
            orders.watch()
                .fullDocument(FullDocument.UPDATE_LOOKUP)
                .maxAwaitTime(2, TimeUnit.SECONDS);

        if (savedToken != null) {
            iterable = iterable.resumeAfter(savedToken);
            System.out.println("RESUMING_FROM_CHECKPOINT");
        } else {
            System.out.println("NO_CHECKPOINT_STARTING_FRESH");
        }

        try (MongoChangeStreamCursor<
                 ChangeStreamDocument<Document>> cursor =
                 iterable.cursor()) {

            System.out.println("STREAM_READY");

            while (running.get()) {
                ChangeStreamDocument<Document> event =
                    cursor.tryNext();

                if (event == null) {
                    continue;
                }

                BsonDocument token =
                    event.getResumeToken();

                if (token == null) {
                    throw new IllegalStateException(
                        "Missing resume token"
                    );
                }

                processAtomically(event, token);

                System.out.println(
                    "COMMITTED_EVENT type="
                    + event.getOperationType()
                );
            }
        }
    }

    private BsonDocument loadCheckpoint() {
        BsonDocument record = checkpoints.find(
            Filters.eq("_id", CONSUMER_ID)
        ).first();

        if (record == null) {
            return null;
        }

        return record.getDocument("resumeToken");
    }

    private void processAtomically(
            ChangeStreamDocument<Document> event,
            BsonDocument token
    ) {
        BsonDocument receiptKey =
            new BsonDocument(
                "consumer",
                new BsonString(CONSUMER_ID)
            ).append(
                "token",
                token
            );

        try (ClientSession session =
                 client.startSession()) {

            session.withTransaction(() -> {

                BsonDocument existing =
                    receipts.find(
                        session,
                        Filters.eq("_id", receiptKey)
                    ).first();

                if (existing == null) {
                    receipts.insertOne(
                        session,
                        new BsonDocument(
                            "_id",
                            receiptKey
                        ).append(
                            "operationType",
                            new BsonString(
                                event.getOperationType()
                                    .getValue()
                            )
                        )
                    );

                    applyToReadModel(session, event);
                } else {
                    System.out.println(
                        "DUPLICATE_EVENT_SKIPPED"
                    );
                }

                BsonDocument newCheckpoint =
                    new BsonDocument(
                        "_id",
                        new BsonString(CONSUMER_ID)
                    ).append(
                        "stream",
                        new BsonString("sales.orders")
                    ).append(
                        "resumeToken",
                        token
                    );

                checkpoints.replaceOne(
                    session,
                    Filters.eq("_id", CONSUMER_ID),
                    newCheckpoint,
                    new ReplaceOptions().upsert(true)
                );

                return null;
            }, TX_OPTIONS);
        }
    }

    private void applyToReadModel(
            ClientSession session,
            ChangeStreamDocument<Document> event
    ) {
        OperationType type =
            event.getOperationType();

        if (type == OperationType.INSERT
                || type == OperationType.REPLACE
                || type == OperationType.UPDATE) {

            Document full =
                event.getFullDocument();

            if (full == null) {
                throw new IllegalStateException(
                    "fullDocument is unavailable for "
                    + type
                );
            }

            // Stable transformation: preserve _id/type.
            Document projection =
                new Document(full);

            readModels.replaceOne(
                session,
                Filters.eq("_id", full.get("_id")),
                projection,
                new ReplaceOptions().upsert(true)
            );

        } else if (type == OperationType.DELETE) {

            BsonDocument key =
                event.getDocumentKey();

            if (key == null
                    || !key.containsKey("_id")) {
                throw new IllegalStateException(
                    "Delete missing document key"
                );
            }

            readModels.deleteOne(
                session,
                key
            );

        } else {
            throw new IllegalStateException(
                "Unsupported Change Stream event: "
                + type
            );
        }
    }

    public static void main(String[] args) {
        String uri = System.getenv().getOrDefault(
            "MONGODB_URI",
            "mongodb://127.0.0.1:27017/"
                + "?replicaSet=rs0&directConnection=true"
        );

        AtomicBoolean running =
            new AtomicBoolean(true);

        try (MongoClient client =
                 MongoClients.create(uri)) {

            ChangeStreamOrderConsumer consumer =
                new ChangeStreamOrderConsumer(client);

            Runtime.getRuntime().addShutdownHook(
                new Thread(consumer::stop)
            );

            consumer.run();
        }
    }
}
```

### 11.1. Breakdown of Responsibilities

- `loadCheckpoint()`: reads the last committed BSON token.
- `orders.watch()`: opens a stream scoped to the collection.
- `.resumeAfter(savedToken)`: resumes right after the saved token.
- `.fullDocument(UPDATE_LOOKUP)`: requests the document for updates when available.
- `cursor.tryNext()`: awaits an event or returns `null` if none arrived.
- `processAtomically()`: starts a target transaction for the event.
- `receipts.find(...)`: checks whether the token was already processed.
- `receipts.insertOne(...)`: records the event receipt.
- `applyToReadModel(...)`: upserts or deletes the projection document.
- `checkpoints.replaceOne(...)`: saves the token **in the same transaction**.
- `withTransaction(...)`: commits or aborts the whole group together.
- `try-with-resources`: closes sessions, cursors, and clients deterministically.

### 11.2. Why Not Call External APIs Inside the Callback?

`withTransaction` can automatically retry the callback upon transient errors. If the callback calls `emailService.send(...)`, an email could be sent multiple times even before resume handling runs. Keep only MongoDB operations inside the transaction; move external side effects to a separate workflow.

### 11.3. Why Is the Handler Sequential?

Sequential execution keeps the checkpoint from advancing past an unfinished event. One reader/one active owner is an assumption of this lab; the code omits distributed leases/fencing.

### 11.4. `fullDocument` Is Not an Exact Historical Post-Image

`UPDATE_LOOKUP` can read state newer than the event being processed; for example, if `PAID` quickly turns into `REFUNDED`, the lookup for the `PAID` event may already see `REFUNDED`. This lab builds a **latest-state projection**, not a business audit log. When exact state transitions are needed, use a domain outbox or server/version-supported pre/post-images.

### 11.5. Null `fullDocument` Handling in This Demo

This lab **throws an error and skips checkpointing** if `fullDocument` is missing on an update/replace. In real workloads, this occurs when a document is deleted before the lookup completes; production code needs an explicit policy (applying `updateDescription` patches, enabling post-images, or rebuilding state). Never silently treat `null` as a delete event.

### 11.6. Note on `main` and Graceful Shutdown

The shutdown hook sets `running = false`. Because `tryNext()` blocks up to `maxAwaitTime`, shutdown latency depends on await/getMore timeouts. Production may need a cancellation controller closing the cursor per `MongoCursor`'s contract within orchestrator deadlines. `main` here is kept minimal for lab use.

### 11.7. Do Not Add PII Logging

Sample logs only print the operation type—never raw customer documents, resume tokens, or credentials.

---

## 12. Why Use `BsonDocument` for Checkpoints and Receipts?

Resume tokens are opaque BSON structures. `BsonDocument` persists the exact driver-provided value without lossy JSON string conversion.

Example:

```java
BsonDocument token = event.getResumeToken();

BsonDocument checkpoint =
    new BsonDocument(
        "_id",
        new BsonString("orders-projection-v1")
    ).append("resumeToken", token);
```

When restoring:

```java
BsonDocument savedToken =
    checkpoint.getDocument("resumeToken");

orders.watch()
    .resumeAfter(savedToken);
```

### 12.1. Avoid Lossy Serialization

Never turn a token into `Map<String, Object>` and serialize it as ad hoc JSON where BSON type metadata may be lost.

### 12.2. Tokens Are Not Login Secrets, Yet Still Sensitive

A token does not grant database privileges, yet it is operational metadata encoding replication position. Avoid exposing it to end clients or public logs.

### 12.3. Never Compare `_data` Strings Lexicographically

Do not sort `resumeToken._data` as strings assuming larger strings represent newer events. MongoDB makes no guarantee enabling client-side token ordering inference.

---

## 13. Why Does the Receipt Key Include Consumer ID?

Suppose two independent projections exist:

```text
orders-search-index-v1
orders-notification-intent-v1
```

The same event E100 must be processed **once per pipeline**, not once across the whole cluster.

Therefore:

```text
(receipt.consumer, receipt.token)
```

is far better than:

```text
receipt.token only
```

whenever pipelines share a receipt collection.

### 13.1. Never Use `documentKey` as Event Identity

Order `"O100"` can undergo multiple updates and a delete:

```text
E1: O100 inserted
E2: O100 status=PAID
E3: O100 status=SHIPPED
E4: O100 deleted
```

Deduplicating by `_id="O100"` would process E1 and wrongly skip E2, E3, and E4.

---

## 14. Atomicity and Duplicate Delivery

Suppose event E1 was already processed, and in the lab an operator rewinds the checkpoint back to a token before E1.

When E1 is redelivered:

```text
Transaction:
  find receipt E1 -> exists
  skip projection write
  save checkpoint E1
  commit
```

Result:

- No second receipt is inserted.
- The projection is not re-applied for this event.
- The checkpoint advances back up to the re-read position.
- The consumer continues smoothly with subsequent events.

### 14.1. Why Keep Receipts Even When Checkpoints Are Atomic?

On the happy path, atomic checkpoints and projections work cleanly. Receipts add essential protection against **manual rewinds**, duplicate deliveries from another source, or handlers needing verifiable proof of application.

### 14.2. Note on Checkpoint Regression

This lab **assumes one active consumer owner** processing sequentially. If two instances share one consumer ID without compare-and-swap/lease fencing, a stale worker can overwrite a newer checkpoint with an older token. Receipts alone do not protect the progress pointer against every race.

### 14.3. Production Should Use Fencing

Tie checkpoints to an owner generation and allow commits only from the worker holding the active lease. Once a worker loses its lease, it must stop applying updates and saving tokens.

---

# PART IV — RUNNING AND VERIFYING THE LAB

## 15. Compile and Run the Consumer

In the project directory:

```bash
mvn -q compile exec:java
```

Optionally pass the URI via environment variable:

```bash
export MONGODB_URI="mongodb://127.0.0.1:27017/?replicaSet=rs0&directConnection=true"
mvn -q compile exec:java
```

The example above uses Bash. In PowerShell:

```powershell
$env:MONGODB_URI = "mongodb://127.0.0.1:27017/?replicaSet=rs0&directConnection=true"
mvn -q compile exec:java
```

First-run startup output:

```text
NO_CHECKPOINT_STARTING_FRESH
STREAM_READY
```

**Only insert events after `STREAM_READY` appears** in this lab step to avoid racing consumer startup against initial writes.

### 15.1. If You See "not supported on standalone"

Check `rs.status()` and the connection string. A `mongod` started with `--replSet` before `rs.initiate()` or without an elected `PRIMARY` is not yet an operational replica set.

### 15.2. On Connection Timeout

Inspect Docker port bindings, advertised replica-set hostnames, networking, TLS/auth, and server selection. Never alter checkpoint semantics to work around connectivity errors.

---

## 16. Test Step 1: Insert

In the `mongosh` terminal:

```javascript
use sales;

db.orders.insertOne({
  _id: "O100",
  tenantId: "T1",
  customerId: "C100",
  status: "PENDING",
  totalMinor: NumberLong("199000"),
  version: NumberLong("1")
});
```

In the consumer terminal, expect:

```text
COMMITTED_EVENT type=insert
```

Check the projection:

```javascript
db.order_read_models.findOne({ _id: "O100" });
```

Expect a document containing `status: "PENDING"` and all source fields.

### 16.1. Inspect the Checkpoint

```javascript
db.consumer_checkpoints.findOne({
  _id: "orders-projection-v1"
});
```

Expect a BSON `resumeToken` and `stream: "sales.orders"`.

### 16.2. Inspect Receipts

```javascript
db.processed_changes.countDocuments();
```

If the lab collection started empty and one event was processed, expect count `1`.

### 16.3. Important: Never Assert with `Thread.sleep(100)`

The consumer runs asynchronously. In automated tests, poll until the projection and checkpoint appear within a reasonable deadline rather than assuming 100 ms after insert is always enough.

---

## 17. Test Step 2: Update

Continue in `mongosh`:

```javascript
db.orders.updateOne(
  { _id: "O100" },
  {
    $set: {
      status: "PAID",
      version: NumberLong("2")
    }
  }
);
```

Consumer:

```text
COMMITTED_EVENT type=update
```

Projection:

```javascript
db.order_read_models.findOne({
  _id: "O100"
});
```

Expected:

```javascript
{
  _id: "O100",
  tenantId: "T1",
  customerId: "C100",
  status: "PAID",
  totalMinor: NumberLong("199000"),
  version: NumberLong("2")
}
```

Receipt count after two events:

```javascript
db.processed_changes.countDocuments();
// 2
```

### 17.1. What This Test Actually Proves

- `insert` and `update` produce distinct events.
- Each event records its own receipt.
- The checkpoint advances after the second event.
- The final projection reflects the update.

It does **not** prove a payment email was sent exactly once; this lab has no external email provider.

---

## 18. Test Step 3: Replace

Replace the whole document while preserving `_id`:

```javascript
db.orders.replaceOne(
  { _id: "O100" },
  {
    _id: "O100",
    tenantId: "T1",
    customerId: "C100",
    status: "FULFILLED",
    totalMinor: NumberLong("199000"),
    version: NumberLong("3")
  }
);
```

Verify:

```javascript
db.order_read_models.findOne({
  _id: "O100"
});
```

Expect status `FULFILLED`.

### 18.1. Do Not Confuse Replace with Update

`replaceOne()` emits a Change Stream `replace` event; the consumer must handle this type as well if the business needs to track every state change.

### 18.2. Checkpoint After Replace

Upon success, the receipt count increments by 1 and the checkpoint updates to the `replace` event's resume token.

---

## 19. Test Step 4: Delete

```javascript
db.orders.deleteOne({
  _id: "O100"
});
```

Consumer:

```text
COMMITTED_EVENT type=delete
```

Verify:

```javascript
db.order_read_models.findOne({
  _id: "O100"
});
// null
```

Receipt count increments by one more once the delete event commits.

### 19.1. Why Not Use `fullDocument` on Delete?

Delete events normally carry only `documentKey` identifying the deleted record. If downstream logic needs the customer's email or tenant ID upon deletion, design key mappings, pre-images, or an outbox instead of assuming `fullDocument` exists.

### 19.2. Sharded Collections

`documentKey` can contain shard key fields. This lab is unsharded so the key passes straight into `deleteOne`. When source and target differ in shard key or schema, apply proper mapping and routing.

---

## 20. Test Step 5: Stop and Restart

After events commit and a checkpoint exists, stop the consumer with Ctrl+C.

Restart it:

```bash
mvn -q compile exec:java
```

Output:

```text
RESUMING_FROM_CHECKPOINT
STREAM_READY
```

Create a new event:

```javascript
db.orders.insertOne({
  _id: "O101",
  tenantId: "T1",
  status: "PENDING",
  version: NumberLong("1")
});
```

Verify:

```javascript
db.order_read_models.findOne({
  _id: "O101"
});
```

Expect `O101` to be created after the restart.

### 20.1. What Was Proven

- Resume tokens live beyond process RAM.
- A restarted consumer resumes from the committed checkpoint.
- New events are not missed.
- Server cursor IDs do not need to be persisted.

### 20.2. Never Store Server Cursor IDs as Tokens

A MongoDB server cursor ID is ephemeral session state. A Change Stream resume token is the recovery anchor defined by the API.

---

# PART V — INTENTIONAL REPLAY TO VERIFY DEDUPLICATION

## 21. Why Test Replay Explicitly?

A consumer running error-free for 10 minutes can still fail when killed right between applying an effect and saving its checkpoint. To verify deduplication, you must test **redelivering the exact same event**.

This lab supports two methods:

1. **Manual checkpoint rewind** in a test database.
2. **Failure injection** right before or after transaction commit.

Never manually edit production checkpoints without a recovery runbook, ownership approval, and backups.

---

## 22. Prepare a Clean Event Sequence for Replay

On the lab's `sales` database, only when prior test records will not interfere, insert a fresh document:

```javascript
db.orders.insertOne({
  _id: "O200",
  tenantId: "T2",
  status: "NEW",
  version: NumberLong("1")
});
```

Wait for the consumer to process `O200` and save its checkpoint token.

Stow away the first token:

```javascript
const checkpointBeforeUpdate =
  db.consumer_checkpoints.findOne({
    _id: "orders-projection-v1"
  }).resumeToken;

db.lab_control.replaceOne(
  { _id: "saved-before-update" },
  {
    _id: "saved-before-update",
    token: checkpointBeforeUpdate
  },
  { upsert: true }
);
```

The `lab_control` collection is strictly for testing in an isolated environment.

### 22.1. Why Wait for Commit Before Saving the Token?

Reading the checkpoint before the insert commits could capture an older token. Always verify `order_read_models` and the receipt count instead of guessing timing.

### 22.2. Emit the Second Event

```javascript
db.orders.updateOne(
  { _id: "O200" },
  {
    $set: {
      status: "PAID",
      version: NumberLong("2")
    }
  }
);
```

Wait until the projection shows `PAID`, then record the receipt count:

```javascript
const receiptsAfterUpdate =
  db.processed_changes.countDocuments();

print(receiptsAfterUpdate);
```

---

## 23. Rewind the Checkpoint to an Old Token: Lab Only

**Stop the consumer first**, confirming no instance using this consumer ID remains running.

In `mongosh`:

```javascript
const oldToken =
  db.lab_control.findOne({
    _id: "saved-before-update"
  }).token;

db.consumer_checkpoints.updateOne(
  { _id: "orders-projection-v1" },
  {
    $set: {
      resumeToken: oldToken
    }
  }
);
```

The checkpoint now points to the token **after inserting `O200` but before updating `O200`**.

Start the consumer again:

```bash
mvn -q compile exec:java
```

Expect the console to show the replayed event recognized via its existing receipt:

```text
RESUMING_FROM_CHECKPOINT
STREAM_READY
DUPLICATE_EVENT_SKIPPED
COMMITTED_EVENT type=update
```

### 23.1. Checks to Verify

```javascript
db.order_read_models.findOne({
  _id: "O200"
});
```

Still shows `status: "PAID"`.

```javascript
db.processed_changes.countDocuments();
```

Did not increase because the update event already had a receipt.

### 23.2. What Does This Test Prove?

- The consumer can re-read an already-processed event.
- The prior receipt still exists.
- The handler skips re-applying the projection for that event.
- The checkpoint catches back up to the re-read position.

### 23.3. Does Not Equal System-Wide Exactly-Once

If the handler had sent an email before recording the receipt, the email could have been sent twice. MongoDB's receipt/projection transaction does not encompass external email providers.

---

## 24. Failure Injection: Crash Before Transaction Commit

Suppose the handler executes:

```text
BEGIN
  insert receipt E300
  update read model E300
  write checkpoint E300
  crash before COMMIT
```

If the process dies abruptly before committing, the uncommitted transaction leaves no partial committed state.

After restart:

```text
resume after earlier checkpoint
read E300 again
transaction applies E300
commit
```

### 24.1. Assertions to Verify

- No receipt for E300 exists from the aborted transaction.
- No half-written projection update exists from that transaction.
- Checkpoint did not advance past E300.
- Replay after restart applies E300 cleanly.

### 24.2. Ambiguous Commit Failure

If the process crashes **right after sending commit** before receiving the reply, it is uncertain whether commit succeeded. On restart, inspect the durable checkpoint:

- If commit succeeded, the token, receipt, and projection were saved; resume after E300.
- If commit aborted, the older token remains; E300 is redelivered and applied.
- If a rollback occurred under weaker durability settings, older events may replay; receipts and idempotency still protect you.

### 24.3. Never Test by Killing Production `mongod`

Use worker failure hooks or a test process with an isolated database. Never crash a live primary to verify application logic.

---

## 25. Failure Injection: Crash After Transaction Commit

Flow:

```text
BEGIN
  receipt E301
  projection E301
  checkpoint E301
COMMIT SUCCESS
process crashes before next poll
```

After restart, the consumer loads token E301 and calls `resumeAfter(E301)`.

Expected:

- E301 is not reprocessed.
- Subsequent event E302 is received.
- Projection, receipt, and checkpoint are all present.
- No half-applied state exists.

### 25.1. Why Is `withTransaction` Helpful?

Certain transient errors let the driver retry the callback/commit under defined semantics. Keep only idempotent/transactional MongoDB calls inside the callback with stable event/token inputs and zero external side effects.

### 25.2. What If the Target Does Not Support Transactions?

Adopt another strategy:

- Idempotent state writes.
- Receipt and checkpoint ordering built to tolerate replays.
- Durable outboxes or queues.
- Reconciliation jobs to heal partial effects.
- Never claim atomicity that the underlying deployment cannot provide.

---

# PART VI — EXPLAINING THE SUBTLE PARTS

## 26. `resumeAfter`, `startAfter`, `startAtOperationTime`

| API | When to Use | Caveats |
| --- | --- | --- |
| `resumeAfter(token)` | Normal restarts from a stream token | Token and history must remain valid |
| `startAfter(token)` | Reopening after an invalidate token where supported | Does not automatically rebuild a dropped collection |
| `startAtOperationTime(ts)` | Starting at a BSON logical timestamp with available history | Does not pinpoint a single event like a token |

### 26.1. This Lab Uses `resumeAfter`

Since the checkpoint always stores the last committed event token, `resumeAfter(token)` is the right fit.

### 26.2. Handling `invalidate`

`resumeAfter` cannot resume past an `invalidate` event in the normal way. Depending on scope and conditions, `startAfter` can open a fresh stream. Still, if a collection was dropped and recreated, the projection usually needs a full rebuild.

### 26.3. Do Not Combine Multiple Starting Options

A Change Stream must specify **only one starting position**.

### 26.4. `startAtOperationTime` Does Not Take a Java `Date`

It expects a BSON `Timestamp` (seconds + increment); never pass `new Date()` or cast a timestamp to a token.

---

## 27. Why Not Use `clusterTime` as the Checkpoint?

Suppose two events in the same transaction share one logical timestamp:

```text
E1 clusterTime = T100
E2 clusterTime = T100
```

If the consumer processes E1 and stores only `T100`, on restart it cannot tell whether E2 was already handled.

A resume token pinpoints exact stream position per Change Stream semantics. **Store the exact event token** rather than inventing an approximate timestamp checkpoint.

### 27.1. Never Use Wall-Clock Time as a Sequence

Hosts suffer clock skew; Java's `Instant.now()` records client processing time, not stream offset.

### 27.2. Never Use Document ID as a Checkpoint

A single document can update many times. Cursor position and document identity are distinct concepts.

---

## 28. Post-Batch Resume Tokens and Empty Batches

When no new events exist, the server may return an empty batch carrying a `postBatchResumeToken`/high-watermark. The MongoDB Java Driver exposes:

```java
BsonDocument token = cursor.getResumeToken();
```

This differs from the token attached to a specific event.

### 28.1. Why Does This Lab Checkpoint Only Event Tokens?

To keep correctness simple: with a sequential handler, the checkpoint always tracks the last successfully committed event.

### 28.2. Benefit of Persisting High-Watermarks

Low-traffic consumers can otherwise hold a stale token for hours; advancing to empty-batch high-watermarks helps avoid falling behind oplog history retention.

### 28.3. Risk

If a reader prefetches events while worker threads process asynchronously, saving a newer high-watermark too early can skip unacknowledged events.

Only persist `getResumeToken()` from empty batches when **zero pending/in-flight work precedes that position** under a sound ownership and checkpoint protocol.

---

## 29. `UPDATE_LOOKUP` Is Not an Exact Historical Post-Image

Suppose the source mutates rapidly:

```text
T1: status=PENDING
T2: status=PAID
T3: status=REFUNDED
T4: worker receives update event from T2
```

`fullDocument(UPDATE_LOOKUP)` can return the current state `REFUNDED` at lookup time, not necessarily the state right after T2.

### 29.1. What Does This Lab Build?

A read model tracking current document state. Once events catch up sequentially and writes quiesce, the projection converges to source state. It is not an event-sourcing log preserving every intermediate transition.

### 29.2. When Exact Transition Notifications Are Required

An `OrderPaid` email must reflect the exact business transition, not whatever state a delayed lookup sees later.

Consider:

- A transactional outbox.
- Immutable domain event IDs.
- Change Stream pre/post-images where server and collection configuration support them.
- A durable event log with sufficient retention.

### 29.3. If `fullDocument` Is Null

This happens when a document is deleted before lookup completes. Handlers must not assume `null` means delete unless policy guarantees it. This lab throws an exception to block checkpointing and force explicit production semantics.

---

## 30. Deletes and Unexpected Events

This lab handles:

```text
insert
update
replace
delete
```

Events such as:

```text
drop
rename
invalidate
```

must follow an explicit policy. This lab throws an exception so it **never falsely reports success**.

### 30.1. Do Not Filter Out Critical Events and Assume Health

If a stream aggregation pipeline strips `invalidate` or DDL events carelessly, the consumer misses namespace changes. Choose an explicit policy for schema and migration events.

### 30.2. Halt Intentionally on Unrecoverable Errors

An unrecoverable error should transition the consumer to `FAILED`, `REBOOTSTRAP_REQUIRED`, or another explicit state instead of spinning in an infinite retry loop.

---

## 31. What Happens When Oplog History Expires?

`resumeAfter` requires the token to remain inside accessible oplog history per server semantics. The oplog window is bounded by oplog size/retention and write volume.

```text
T0 checkpoint saved
T1 consumer offline
T2 source writes heavily
T3 old oplog history rolled over
T4 consumer resumes token T0 -> ERROR
```

Once history for the token is lost:

1. Never delete the token and open the stream "from now" while claiming data completeness.
2. Mark the consumer as requiring **rebootstrap** or replay from another durable source.
3. Assess the business impact of potentially missed events.
4. Rebuild the projection from source state using a consistent capture boundary.
5. Reconcile results against the source.
6. Only report `HEALTHY` after catch-up finishes.

### 31.1. Enlarging the Oplog Afterward Does Not Restore the Past

Increasing oplog size or retention helps prevent future failures; it cannot resurrect already-evicted entries.

### 31.2. Domain Events Need Longer Retention

If every past transition required sending an email, a current-state snapshot after rebootstrap cannot reconstruct lost transitions. A durable outbox or event log is needed.

---

## 32. Bootstrapping Documents Created Before `watch()`

If a collection already holds millions of orders, opening a fresh Change Stream **does not emit insert events for historical rows**.

A new projection needs an initial load.

### 32.1. The Wrong Approach

```text
1. Scan all existing orders
2. End scan
3. Start Change Stream
```

Writes occurring between the scan and starting the Change Stream can be missed.

### 32.2. Safer Conceptual Approach

```text
Establish safe CDC starting point
              |
              v
Persist changes durably from T0
              |
              +------------------+
              |                  |
              v                  v
       Backfill snapshot     Capture live changes
              |                  |
              +------------------+
                         |
                         v
                Replay changes in order
                         |
                         v
                Reconcile + go live
```

### 32.3. Overwrite Traps

If backfill writes `PENDING` after CDC already wrote `PAID`, the projection regresses. Guard against this using:

- Backfill followed by ordered replay of captured events.
- Version-aware conditional writes.
- Supported snapshot/migration tooling.
- Brief write pauses if SLAs allow.

### 32.4. Oplog Window Must Suffice

If the initial scan takes hours, ensure stream events from `T0` are durably captured and replayed without losing oplog history mid-run.

---

## 33. Where to Store State When Source and Target Live on Different Clusters

Production topology example:

```text
MongoDB source cluster A
       |
       v
Change Stream consumer
       |
       v
MongoDB target cluster B
       |
       +--> projection
       +--> receipt
       +--> checkpoint
```

A transaction on target cluster B can atomically combine projection, receipt, and checkpoint as long as all three live on B and topology supports transactions.

However, that transaction **does not span** source cluster A or external services.

### 33.1. When Target Is Elasticsearch

No distributed transaction spans an Elasticsearch index write and a MongoDB checkpoint. Use deterministic document IDs/versions, retries, durable queues, and reconciliation.

### 33.2. When Target Is Kafka

Connectors or outboxes help, yet end-to-end exactly-once requires examining offset commits and sink semantics. Never assume Kafka transactions automatically merge a MongoDB event and external business effects into one atomic unit.

### 33.3. When Target Is an Email Provider

Provider-side idempotency keys, delivery ledgers, and reconciliation prevent duplicate sends; the MongoDB resume token is only one piece.

---

# PART VII — UPGRADING TO A PRODUCTION SYSTEM

## 34. Worker Leases and Fencing

This lab assumes one consumer process. Production runs Kubernetes replicas, autoscaling, or rolling updates where two instances can overlap briefly.

```text
Worker A owns consumerId
        |
   A becomes paused
        |
   Lease expires
        |
Worker B owns consumerId
        |
A wakes up and tries to commit old token
```

Without fencing, A could overwrite B's newer checkpoint with an old token.

### 34.1. Suggested Lease Structure

```javascript
{
  _id: "orders-projection-v1",
  ownerId: "pod-42",
  generation: NumberLong("12"),
  leaseUntil: ISODate("2026-11-14T10:01:00Z")
}
```

### 34.2. Principles

- Each logical stream or partition has one active owner.
- Acquiring a new lease increments a fencing generation.
- Every transaction/checkpoint write verifies the current generation.
- Any worker whose lease expires stops applying updates and checkpointing.
- Never check the lease only at startup; enforce it on the write path.

### 34.3. Receipts Do Not Replace Fencing

Receipts block applying the exact same event twice, yet do not prevent a zombie worker from **rewinding the checkpoint** or writing stale transformations.

---

## 35. When Scaling to Multiple Workers

Single reader:

```text
MongoChangeStreamCursor
          |
          v
     Ordered dispatcher
          |
    +-----+-----+
    |           |
  Key A       Key B
  Worker A    Worker B
```

### 35.1. Partition by Aggregate Key

Route by `documentKey._id` or business aggregate ID so all events for a single order enter the same ordered queue.

### 35.2. Preserve Per-Key Ordering

Never let E5 and E6 for the same order finish out of order and overwrite newer state.

### 35.3. Contiguous Prefix Checkpointing

If E10 finishes, E11 is still in flight, and E12 finishes, **do not checkpoint past E11**.

Advance only up to the point where all prior events are acknowledged unless a proven partitioned checkpoint protocol is used.

### 35.4. Queues Must Be Bounded

An unbounded `LinkedBlockingQueue` facing 30,000 source events/s and a 300 events/s sink will exhaust JVM heap quickly.

### 35.5. Backpressure Has Costs

Halting fetches increases consumer lag and threatens the oplog window. Address bottlenecks with scaling, metrics, durable buffering, or source throttling—not unbounded in-memory queues.

---

## 36. Transaction Throughput and Cost

In this lab, each event opens a transaction:

```text
find receipt
insert receipt
upsert/delete projection
upsert checkpoint
commit
```

This makes correctness boundaries crystal clear, though throughput can be constrained by:

- Transaction setup and commit round trips.
- Majority write latency.
- Index maintenance on receipts and checkpoints.
- Document sizes.
- Active consumer count.
- Disk IOPS.
- Network RTT.

### 36.1. Can Transactions Be Batched?

Yes, provided you handle:

- One receipt per event in the batch.
- Strict event ordering.
- All-or-nothing batch commit/abort.
- Checkpointing at the last event of the batch.
- Transaction lifetime and size limits.
- Replaying the batch on crashes.
- Keeping external side effects out of the batch transaction.

### 36.2. Must Receipts Live Forever?

When checkpoints and projections share an atomic transaction with a single active consumer and no manual replays or external side effects, receipts may be optional. However, removing receipts must align with replay/rebootstrap policies and audit requirements, never guesswork.

### 36.3. Receipt TTLs Must Match Retention Policy

A TTL index cleaning old receipts saves disk space, yet premature expiry makes old events look "new" during delayed replays. Never pick a 1-hour TTL if operations allow replaying events from days ago.

---

## 37. Retrying Transient Failures

A consumer can encounter:

- Connection resets.
- Temporary server selection timeouts.
- Primary elections.
- Network partitions.
- Target write concern timeouts.
- Transaction write conflicts/retries.
- CPU or disk pressure.

The Java Driver's Change Stream implementation automatically resumes certain errors per API contract, yet applications still need an outer restart policy.

### 37.1. Handling Flow

```text
Stream read / apply throws
          |
          v
Classify error
          |
     +----+----+
     |         |
Transient    Non-recoverable
     |         |
     v         v
Close cursor  Mark FAILED
Backoff       Alert
Reload token  No silent skip
Reopen        Rebootstrap if needed
```

### 37.2. Never Retry Every Error Forever

Unsupported event types, schema violations, bad permissions, or expired history must never spin in a tight `try again` loop.

### 37.3. Backoff and Jitter

Illustrative policy:

```text
Attempt 1: 200 ms + jitter
Attempt 2: 500 ms + jitter
Attempt 3: 1 s + jitter
Attempt 4: 2 s + jitter
Cap:       30 s
```

This is an illustration, not a universal SLA configuration.

---

## 38. `writeConcern: majority` and Ambiguity

The lab transaction uses:

```java
TransactionOptions.builder()
    .readConcern(ReadConcern.SNAPSHOT)
    .writeConcern(WriteConcern.MAJORITY)
    .readPreference(ReadPreference.primary())
    .build();
```

### 38.1. Why Choose Majority?

To give committed projections, receipts, and checkpoints proper durability on multi-member replica sets, minimizing the risk of committed state rolling back.

### 38.2. A Single-Node Lab Still Has Only One Copy

`w:majority` on a single-node replica set cannot substitute for data redundancy, backups, or the fault tolerance of multi-member deployments.

### 38.3. Timeouts Do Not Prove Failure

A network timeout after sending commit leaves the client uncertain. The driver retries commits automatically when labeled retryable; after a restart, inspect durable checkpoints/receipts and let idempotent replay settle state.

### 38.4. Never Swallow Duplicate-Key Errors from Other Indexes

If `order_read_models` enforces a business unique index and a projection write violates it, never treat every `E11000` as "already processed". Receipt duplicates and business-constraint duplicates are totally different failures.

---

## 39. Observability and Monitoring

Useful metrics:

| Metric | Question Answered |
| --- | --- |
| Consumer running / last successful poll | Is the worker alive? |
| Last event processed at | Are events flowing? |
| Last checkpoint commit at | Is the token advancing? |
| Events/sec | Current throughput |
| Duplicate receipts seen | Are replays or duplicate deliveries happening? |
| Transaction commit errors | Is the target accepting writes? |
| Resume attempts | Are network and topology stable? |
| Oplog window | Is enough history left to resume? |
| Consumer lag | How far behind is the worker? |
| In-flight / queue depth | Is backpressure building? |
| Unknown event types | Did schemas or DDL change? |
| Projection mismatches | Is derived data accurate? |
| History lost / rebootstrap count | Is a rebuild needed? |

### 39.1. Zero Events Does Not Mean a Dead Consumer

A quiet collection may sit idle for hours. Monitor cursor/poll heartbeats rather than `events/sec = 0` alone.

### 39.2. Low Lag Does Not Guarantee Correct Data

A buggy transformation that still advances checkpoints quickly produces `lag = 0` alongside corrupt projections. Schedule periodic reconciliation.

### 39.3. Alert on Headroom

If the source oplog window is 2 hours and consumer lag reaches 90 minutes and rising, intervene before the resume token expires.

---

## 40. Automated Testing: Tier Breakdown

### Unit Tests

- Event type -> projection action mapping.
- Deterministic transformations.
- Receipt key combining consumer + token.
- Unsupported event types throwing errors.
- Retry classifier and backoff math.
- Version/tombstone policies if added.

### Integration Tests

- Real MongoDB replica set.
- `insert`/`update`/`replace`/`delete` events.
- Checkpoint BSON round-trip.
- Transaction atomicity.
- Restarting via `resumeAfter`.
- Replaying an old token does not re-apply the projection.
- Scoped MongoDB roles and permissions.

### Fault-Injection Tests

- Crash before target transaction commit.
- Crash right after commit before the next event.
- Expired resume token (`history lost`).
- Downstream timeouts.
- Worker lease expiration.
- Concurrent delete race during `UPDATE_LOOKUP`.

### End-to-End Tests

- Order API writes to source.
- Consumer builds projection.
- Client reads projection.
- If delivering notifications, verify provider/ledger idempotency.

---

## 41. Example JUnit Integration Test Skeleton

For automated execution, use a Testcontainers MongoDB replica set or dedicated test cluster alongside Awaitility or bounded deadline polling.

```java
@Test
void insertIsProjectedAndCheckpointed() {
    String id = "test-" + UUID.randomUUID();

    // Start consumer and wait for STREAM_READY.
    // Insert into sales.orders with _id=id.

    await()
        .atMost(Duration.ofSeconds(30))
        .pollInterval(Duration.ofMillis(200))
        .untilAsserted(() -> {
            assertNotNull(
                readModels.find(
                    Filters.eq("_id", id)
                ).first()
            );
        });

    assertNotNull(
        checkpoints.find(
            Filters.eq("_id", "orders-projection-v1")
        ).first()
    );

    // Stop consumer and close all resources.
}
```

This is a skeleton because `readModels`, `checkpoints`, `await`, and the consumer lifecycle must be wired by your actual JUnit/Testcontainers project.

### 41.1. Wait for Consumer Readiness

Never call `executor.submit(consumer::run)` and immediately insert: the worker may not have opened the stream yet.

### 41.2. Isolate IDs per Test

Give each test its own `_id`, consumer ID, or database so concurrent tests do not corrupt receipt counts or checkpoints.

### 41.3. Never Rely on Fixed Sleeps

`Thread.sleep(500)` may pass on a laptop and flake in CI due to scheduling or network jitter. Poll assertions until a deadline with clear failure diagnostics.

---

## 42. Testing Transaction Rollback

Design a test hook:

```text
Inside transaction:
  insert receipt
  update projection
  save checkpoint
  throw synthetic exception before commit
```

Expected:

- Transaction aborts.
- Receipt does not exist.
- Projection reflects no change.
- Checkpoint still holds the older token.
- Removing the hook and restarting processes the event cleanly.

### 42.1. Do Not Throw After Commit and Call It a Rollback Test

Throwing **after commit** does not roll back committed data—that tests replay/unknown outcome handling instead.

### 42.2. Inject Failures at the Right Layer

Add a `FailureHook` interface to the consumer to inject pre-commit faults in dedicated integration tests. There is no need to kill `mongod` just to verify application transaction boundaries.

---

## 43. Testing Deduplication via Receipts

Scenario:

1. Consumer receives E1.
2. Commits projection, receipt, and checkpoint for E1.
3. Stops consumer.
4. Rewinds checkpoint to the token before E1 (lab only).
5. Restarts consumer.
6. Receives E1 again.
7. Asserts receipt count did not rise and projection did not unexpectedly change.
8. Asserts checkpoint advances past E1 once replay finishes.

### 43.1. Do Not Assert Only via Logs

Seeing `"DUPLICATE_EVENT_SKIPPED"` is helpful, yet insufficient to prove final database state. Check receipt counts, projection documents, and checkpoint tokens.

### 43.2. Do Not Simulate Replay by Issuing a Second Identical Update

Two identical writes can generate two distinct events—or a no-op update that emits no event at all. To test deduplicating **the same event**, actually replay its token or replay the same event ID.

---

## 44. Testing Two-Worker Concurrency

If two instances accidentally share one consumer ID:

- Both open streams.
- Both receive the same event.
- One receipt transaction commits while the other hits a unique-key conflict or write conflict.
- Checkpoints can regress without fencing and sequencing.

This lab **does not support** two active consumers sharing one ID. When scaling out, add distributed ownership and test:

```text
A owns generation=10
B attempts -> rejected

A loses lease
B owns generation=11
A old transaction -> rejected by fencing
B advances checkpoint
```

Never treat unique receipts alone as a cluster coordination mechanism.

---

## 45. Testing `invalidate` and History Lost

On an isolated lab collection, you can drop/rename the collection and observe stream invalidation. Verify:

- The consumer never checkpoints an unhandled event as succeeded.
- Restarts do not loop endlessly calling `resumeAfter(invalidateToken)`.
- Recovery policy distinguishes missing namespaces from rebuild triggers.
- Expired tokens transition state to `REBOOTSTRAP_REQUIRED`.

### 45.1. Never Force Oplog Rollover in Production

Test history loss via fault injection or an isolated lab with a tiny oplog and controlled load; never blast millions of writes into a real cluster just to evict history.

### 45.2. Snapshots Cannot Recreate Missed Historical Notifications

If every past transition required sending notifications, keep domain events or outboxes durable long enough. A current-state snapshot reconstructs final state, not every event lost in the gap.

---

# PART VIII — EXTENDING TO REAL-WORLD NOTIFICATIONS

## 46. Why Not Send Emails Directly Inside a Change Stream Callback?

Consider:

```text
Change Stream event E400
          |
          v
emailProvider.send("Order paid")
          |
          v
Provider sends email
          |
          v
Network response lost
          |
          v
Consumer retries E400
          |
          v
Email may be sent twice
```

MongoDB's receipt/projection/checkpoint transaction **does not cover** the external email provider.

### 46.1. Use a Notification Intent

Instead of sending inline:

```text
Change Stream
     |
     v
Create notification intent
  stable ID: "order-O100-paid-C100"
     |
     v
Checkpoint Change Stream event
     |
     v
Separate delivery worker
     |
     v
Email provider with idempotency key
```

### 46.2. Data Shape

```javascript
{
  _id: "notification-order-O100-paid-C100",
  businessEventId: "order-O100-paid-v2",
  recipientId: "C100",
  channel: "EMAIL",
  state: "PENDING",
  attempts: 0,
  createdAt: ISODate("2026-11-14T10:00:00Z")
}
```

### 46.3. Business-Level Side-Effect Idempotency

Always use a stable business event ID rather than relying on stream tokens that can change across rebootstraps or migrations.

---

## 47. Transactional Outbox for Domain Events

When notifications require exact state at transition time, write the domain event inside the same source transaction as the order update:

```text
BEGIN TRANSACTION on source
    |
    +--> update order O100 status=PAID
    |
    +--> insert outbox OrderPaid event
    |
COMMIT
    |
    v
Change Stream watches outbox
    |
    v
Reliable delivery pipeline
```

Immutable outbox event:

```javascript
{
  _id: "order-O100-paid-event-v2",
  aggregateId: "O100",
  type: "OrderPaid",
  version: NumberLong("2"),
  payload: {
    customerId: "C100",
    totalMinor: NumberLong("199000")
  },
  createdAt: ISODate("2026-11-14T10:00:00Z")
}
```

### 47.1. Outboxes Support Long-Term Replay

If outbox rows are retained sufficiently long, a worker can sweep pending events even after oplog history expires. The Change Stream acts as a **low-latency wake-up signal**, while the outbox remains the durable source of truth.

### 47.2. Delivery Idempotency Is Still Required

Publishing or emailing can succeed right before the worker crashes prior to marking delivery complete. An outbox alone does not eliminate external provider ambiguity.

### 47.3. Never Confuse Storage Changes with Business Intent

An admin data fix may update an order row without intending to resend `OrderPaid`. Domain events decouple business intent from storage mutations.

---

## 48. When the Target Is a Search Index

For example, syncing `orders` to Elasticsearch/OpenSearch:

```text
MongoDB orders
    |
    v
Change Stream
    |
    v
Transform to search document
    |
    v
Search index update by stable order ID
    |
    v
Checkpoint after acknowledged result
```

Rules:

- Key documents by a stable business ID.
- Ensure eventual convergence on updates and deletes.
- Guard against stale updates and out-of-order events.
- Use optimistic versioning if the search sink supports it.
- Maintain a reindex/rebootstrap path.
- Persist checkpoints and consumer metadata.
- Monitor lag and index mismatches.
- Never claim atomic transactions spanning MongoDB and a search engine.

---

## 49. When the Target Is a Cache

When only invalidation is needed:

```text
Order updated
    |
    v
Change Stream consumer
    |
    v
Invalidate cache key order:O100
```

Deleting a cache key multiple times is naturally idempotent, yet you still must:

- Never drop events and leave caches permanently stale.
- Treat cache TTLs as fallbacks, not substitutes for CDC recovery.
- Flush or rebuild affected keys on history loss.
- Handle deletes with invalidation too.
- Namespace multi-tenant keys to avoid collisions.

Cache invalidation fits Change Streams especially well because repeating `invalidate` is normally harmless.

---

# PART IX — TROUBLESHOOTING

## 50. Consumer Receives No Events

Check:

1. Is the source actually a replica set or sharded cluster?
2. Does `rs.status()` show a healthy `PRIMARY`?
3. Does the Java URI target the right database and collection?
4. Do credentials grant `changeStream` and `find` privileges?
5. Did the consumer print `STREAM_READY` before events were written?
6. Is the operation type handled by your switch/if blocks?
7. Did an aggregation pipeline filter out events by mistake?
8. Did another consumer advance the checkpoint further?
9. Have writes reached majority commit if required?
10. Are networking, TLS, and DNS healthy?

### 50.1. `watch()` Does Not Receive Old Data

That is normal behavior; historical documents require an initial bootstrap.

### 50.2. Missing Events Due to Scope Mismatch

A consumer watching `sales.orders` receives nothing for changes to `sales.payments`. Verify namespace scope before increasing timeouts.

---

## 51. Consumer Keeps Receiving the Same Event

Hypotheses:

- Saving the checkpoint failed.
- Resume token was not updated.
- Handler threw before committing the transaction.
- An unsupported event type puts the worker in a crash-restart loop.
- Another stale instance rewound the token.
- Missing write privilege on the checkpoint collection.
- `loadCheckpoint()` queried the wrong consumer ID.

Inspect:

```javascript
db.consumer_checkpoints.findOne({
  _id: "orders-projection-v1"
});
```

and receipts:

```javascript
db.processed_changes.countDocuments();
```

### 51.1. Never Fix This by Deleting the Token

Deleting the checkpoint and starting from "now" silently drops unprocessed events.

### 51.2. Fix Application Bugs First

If an event arrives with `fullDocument == null` and throws continuously, network retries will never cure it. Implement a policy using `updateDescription`, post-images, or an outbox.

---

## 52. Checkpoint Exists Yet Projection Is Wrong

Possible causes:

- Buggy projection transformation.
- `UPDATE_LOOKUP` saw a newer state than expected.
- Confused `event._id` with `documentKey._id`.
- Cross-consumer receipt collision.
- Schema mismatch between source and target.
- Projection queries using stale secondary read preference.
- Zombie worker overwrote state.
- Manual rewind replayed events out of order.
- Unsupported event skipped while checkpoint still advanced.
- Multi-document transaction omitted around effect and token.

Compare source and target at a consistent logical point rather than relying on raw document counts alone.

---

## 53. `E11000` Error When Inserting a Receipt

Either a receipt for that token already exists, **or** another unique constraint fired.

In our sequential single-owner lab, code checks for the receipt before inserting inside the transaction; if `E11000` still appears, investigate:

- Two processes sharing the same consumer ID?
- Transaction retry or concurrency write conflict?
- Non-deterministic serialization of the receipt key?
- Another unique index on `processed_changes`?
- Shared consumer ID across source/target?
- Manual test/migration script edited collection state?

**Never swallow every `MongoException` 11000 as success**, especially if it came from a business unique index on the projection collection.

---

## 54. History Lost Errors

Symptoms:

- Resuming from the saved token fails.
- Server reports the resume point is no longer in the change stream history (or equivalent release-specific error).
- Consumer stayed offline longer than the oplog retention window.

Actions:

1. Mark `REBOOTSTRAP_REQUIRED`.
2. Do not advance the checkpoint.
3. Assess source-of-truth vs. target divergence.
4. Rebuild/catch up from a consistent anchor point.
5. Verify recovery completeness before marking healthy.

---

## 55. Consumer Falls Behind Increasingly

Measure:

- Source event rate.
- Target transaction commit latency.
- Checkpoint write pressure.
- MongoDB server CPU/IOPS.
- Oplog retention window.
- Reader `getMore` latency.
- Receipt collection and index sizes.
- Queue depth if buffered.
- Retry rates and transaction conflicts.

Mitigations can include:

- Tuning projection indexes.
- Shrinking `fullDocument` payloads.
- Careful transaction batching.
- Scaling target capacity.
- Key-partitioned workers preserving per-key ordering.
- Durable queues to absorb traffic spikes.
- Adjusting receipt retention per protocol.
- Adding lag metrics and backpressure.

Never scale by simply launching extra instances under the same checkpoint ID—that introduces concurrency races.

---

# PART X — CHECKLIST AND EXERCISES

## 56. Lab Completion Checklist

- [ ] MongoDB lab running as a replica set.
- [ ] Consumer opens `watch()` cleanly.
- [ ] All four designed collections exist.
- [ ] Resume token persisted as raw BSON.
- [ ] Checkpoint keyed by consumer ID.
- [ ] Receipt key combines consumer ID + event token.
- [ ] Handler supports `insert`/`update`/`replace`/`delete`.
- [ ] Projection, receipt, and checkpoint share one transaction.
- [ ] Checkpoint commits only alongside or after projection/receipt.
- [ ] Insert creates read model document.
- [ ] Update modifies read model document.
- [ ] Replace updates the full document.
- [ ] Delete removes the read model document.
- [ ] Restart loads saved checkpoint.
- [ ] Post-restart events process properly.
- [ ] Manual rewind triggers duplicate detection.
- [ ] Receipt count does not grow on same-token replay.
- [ ] Only one consumer per ID runs in the lab.
- [ ] `UPDATE_LOOKUP` limitations understood.
- [ ] Historical data requires initial bootstrap.
- [ ] History loss triggers rebootstrap rather than skipping.
- [ ] Zero external API calls inside transaction callback.
- [ ] Never executed against production namespaces.

---

## 57. Exercise 1 — What Is the Resume Token?

An update event contains:

```javascript
{
  _id: { _data: "token-A" },
  documentKey: { _id: "O100" }
}
```

**Question:** Which token is saved for `resumeAfter`?

**Answer:** `event._id` / Java `event.getResumeToken()`, not `"O100"`.

---

## 58. Exercise 2 — Why Not Checkpoint Before Applying?

```text
1. save token E5
2. write projection E5
3. write fails
4. restart
```

**Answer:** Restarting after E5 skips the unapplied event. Commit effects and checkpoints atomically, or checkpoint only after acknowledged effects with idempotent replay.

---

## 59. Exercise 3 — Crash Between Apply and Checkpoint

In an architecture with two separate writes, the projection succeeds and the process crashes before saving the token.

**Answer:** E5 replays on restart; the handler must be idempotent. This lab avoids internal half-state via an atomic transaction.

---

## 60. Exercise 4 — Manual Rewind

E10 already has a receipt, the checkpoint is rewound to E9, and the consumer redelivers E10.

**Answer:** The consumer sees the existing receipt, skips re-applying the projection, and advances the checkpoint past E10 under the single-owner protocol.

---

## 61. Exercise 5 — Duplicate Business ID

Order `O100` receives three updates. What happens if receipts use `O100` alone as `_id`?

**Answer:** The first update is recorded and the next two are wrongly skipped as duplicates. Always key receipts by event identity/token or business event version.

---

## 62. Exercise 6 — `UPDATE_LOOKUP`

An order transitions from `PAID` to `REFUNDED` rapidly while a slow consumer processes the `PAID` update event.

**Answer:** Lookup may observe `REFUNDED`. Never rely on `UPDATE_LOOKUP` as an exact historical after-image for audits or transition notifications.

---

## 63. Exercise 7 — Deletes

The source deletes `O100`, while the handler only handles `insert`/`update`.

**Answer:** The target retains a stale document. Implement a `delete` handler or tombstone schema.

---

## 64. Exercise 8 — Two Workers

Two pods share the same consumer ID and both read E100.

**Answer:** Receipts prevent double-committing inside transactions, yet leases/fencing are required to protect checkpoints and ordering; never run two active instances with the unmodified lab code.

---

## 65. Exercise 9 — Parallel Acks

E11 is unfinished while E12 has finished. Can we persist token E12 as the checkpoint?

**Answer:** No under sequential/contiguous-prefix checkpointing, because a restart would skip E11.

---

## 66. Exercise 10 — History Lost

A consumer is down for 48 hours while the source oplog holds only 6 hours of history.

**Answer:** Never delete the token and start watching from now. Rebootstrap or replay from an adequately retained durable event log.

---

## 67. Exercise 11 — Receipt Before Email

A worker inserts the receipt and crashes right before sending an email.

**Answer:** If replay skips whenever a receipt exists, the email is lost permanently. Separate notification intents plus delivery tracking/provider idempotency instead of a single unique receipt.

---

## 68. Exercise 12 — Email Before Receipt

The email sends, the network response times out, and the worker retries.

**Answer:** Two emails may go out. Pass a stable idempotency key to the provider or reconcile unknown outcomes.

---

## 69. Exercise 13 — Changing Event Filters

Consumer v1 watched inserts only; v2 adds updates while reusing v1's resume token.

**Answer:** Historical updates prior to v1's token were ignored and will not reappear. Perform a controlled checkpoint migration, bump `pipelineVersion`, or rebootstrap.

---

## 70. Exercise 14 — Outbox

Why use an outbox for `OrderPaid` instead of inferring it from raw status updates?

**Answer:** Outboxes store immutable business intent with stable event IDs/versions, commit atomically alongside the order, and preserve history per retention policy.

---

## 71. Exercise 15 — Transaction Callback

A `withTransaction` callback calls `emailService.send()` and then updates MongoDB.

**Answer:** Unsafe because callbacks can retry automatically. Offload external side effects to an idempotent delivery worker.

---

## 72. Exercise 16 — Empty Batches

`tryNext()` returns `null` repeatedly.

**Answer:** There may simply be no new events yet—not an ended stream. Maintain health/readiness probes and consider tracking post-batch tokens per API rules.

---

## 73. Exercise 17 — Source and Target on Separate Clusters

Can one MongoDB transaction atomically commit a source event, a target projection, and an external email together?

**Answer:** No. Use outboxes, idempotent sinks, durable checkpoints, and cross-system reconciliation.

---

## 74. Exercise 18 — Receipt TTL

Receipts use a 1-hour TTL while operations support replays after one week.

**Answer:** Unsuitable. Expired receipts allow replaying week-old events as brand new. Match retention to the replay horizon and business rules.

---

## 75. Exercise 19 — Lag Is Zero Yet Read Model Is Wrong

A hash audit shows 0.1% divergence between source and target.

**Answer:** Transformations can be buggy or events skipped while checkpoints keep advancing. Periodic reconciliation is mandatory alongside lag metrics.

---

## 76. Exercise 20 — High-Watermark

A reader has three events in flight while the cursor returns a newer `postBatchResumeToken`.

**Answer:** Never persist that token as the checkpoint before all three in-flight events are acknowledged; otherwise restarts drop unfinished work.

---

## 77. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "Change Streams automatically process everything once." | Resumes and retries can redeliver events; idempotency is required. |
| "Reading an event justifies checkpointing it." | Effects must be confirmed or committed atomically with the checkpoint. |
| "Resume token equals document ID." | It is an opaque event-level BSON token. |
| "`clusterTime` works as a drop-in token replacement." | Timestamps do not uniquely distinguish individual events. |
| "Keeping the token in RAM suffices for restarts." | Checkpoints must be persisted durably. |
| "Separate source and target clusters share one MongoDB transaction." | No single transaction spans independent deployments. |
| "Writing a receipt before emailing guarantees once-only delivery." | Crashing before the email call loses the email permanently. |
| "Emailing before writing a receipt prevents duplicates." | Ambiguous timeouts lead to duplicate sends. |
| "Atomic checkpoints eliminate the need for idempotency." | Manual rewinds, replays, and external side effects still need it. |
| "Keying receipts by order ID is sufficient." | A single order produces many events over its lifetime. |
| "`UPDATE_LOOKUP` always captures the exact state at event time." | Concurrent writes can surface newer state or `null`. |
| "Delete events always include `fullDocument`." | Deletes normally carry only `documentKey`. |
| "Replaying an older event cannot corrupt state." | Unordered or unfenced replays can overwrite newer state. |
| "Running two consumers with one ID automatically load-balances." | It causes duplicate work and checkpoint regressions. |
| "Unbounded queues improve reliability." | They cause OOM crashes and lack durability. |
| "An empty batch means the stream closed." | It simply means no matching changes arrived within wait time. |
| "The driver auto-resumes every error forever." | Only supported transient conditions auto-resume. |
| "Deleting the checkpoint on history loss is a clean recovery." | It silently loses missed changes. |
| "Change Streams auto-backfill historical documents." | Existing data needs a separate snapshot/backfill plan. |
| "Saving the high-watermark is always safe." | Never advance past unacknowledged in-flight events. |
| "Matching counts and zero lag guarantee data correctness." | Field values, BSON types, and transforms can still be wrong. |
| "A receipt collection doubles as a long-term audit log." | Real audit logs require dedicated retention, security, and business context. |
| "MongoDB transactions allow external API calls in callbacks." | Driver retries duplicate external side effects. |

---

## 78. References

Official sources and tool documentation to consult during implementation:

1. [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/) — scope, mechanics, and resuming.
2. [MongoDB Manual — Change Events](https://www.mongodb.com/docs/manual/reference/change-events/) — event types and payload fields.
3. [MongoDB Manual — Change Stream Production Recommendations](https://www.mongodb.com/docs/manual/administration/change-streams-production-recommendations/) — operations, oplog retention, and production guidance.
4. [MongoDB Manual — Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/) — history windows and replication.
5. [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — multi-document atomicity.
6. [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — durability and majority acknowledgment.
7. [MongoDB Java Sync Driver — Change Streams](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/change-streams/) — watch, resume, and options.
8. [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/) — `ClientSession`, `withTransaction`, and retries.
9. [MongoDB Java Driver — MongoChangeStreamCursor Javadoc](https://mongodb.github.io/mongo-java-driver/5.7/apidocs/driver-sync/com/mongodb/client/MongoChangeStreamCursor.html) — cursor API, `getResumeToken`, `tryNext`.
10. [MongoDB Java Driver — ChangeStreamIterable Javadoc](https://mongodb.github.io/mongo-java-driver/5.7/apidocs/driver-sync/com/mongodb/client/ChangeStreamIterable.html) — `resumeAfter`, `startAfter`, options.
11. [MongoDB Manual — Change Stream Pre- and Post-Images](https://www.mongodb.com/docs/manual/changeStreams/#change-streams-with-document-pre--and-post-images) — capturing exact document before/after images.
12. [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/) — retry boundaries and error semantics.
13. [MongoDB Kafka Connector](https://www.mongodb.com/docs/kafka-connector/current/) — connector-based pipelines.
14. [Testcontainers MongoDB Module](https://java.testcontainers.org/modules/databases/mongodb/) — integration testing against real MongoDB.
15. [Awaitility Usage](https://github.com/awaitility/awaitility/wiki/Usage) — deadline-based polling for asynchronous tests.

This document describes **an integrated lab**. APIs, exception classes, and behavior vary by Java Driver, MongoDB Server, FCV, and topology. Before production, verify exact versions and perform Content QA, integration/performance testing, fault-injection testing, and security reviews per team process.

---

## 79. Conclusion

Building a Change Stream consumer capable of **resuming after restarts** and **deduplicating replays** takes more than an event-reading loop:

- **Resume token:** persisted in original BSON form, durably, scoped per consumer.
- **Checkpoint:** advanced only after confirmed effects or committed atomically alongside them.
- **Receipt / idempotency:** marks events processed so replays do not repeat side effects.
- **Ordering:** single sequential reader in the lab; production adds leases, fencing, and per-key ordering when scaling out.
- **Recovery:** resumes from checkpoints while oplog history holds; never silently skips events on history loss.
- **Bootstrap:** seeds historical documents into targets without dropping concurrent writes.
- **Observability:** tracks lag, oplog window headroom, duplicate receipts, checkpoint progress, and data mismatches.
- **Transaction boundaries:** a target MongoDB transaction never covers external email, payment, or foreign systems; use outboxes and business idempotency.

In this lab, `order_read_models`, `processed_changes`, and `consumer_checkpoints` commit together in one MongoDB transaction. Consequently, once an event commits, **target state, processing proof, and resume anchor remain consistent**—forming a solid foundation for reliable sync and notification pipelines.
