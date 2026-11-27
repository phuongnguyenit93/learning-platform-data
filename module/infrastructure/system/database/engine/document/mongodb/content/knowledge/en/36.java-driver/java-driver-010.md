# ClientSession, Transactions, and Retry Behavior of MongoDB Java Driver

> **Module:** Database Engine Document MongoDB  
> **Chapter:** Java Driver  
> **Lesson:** ClientSession, transactions, and driver retry behavior

## 1. The Problem: When an Operation Fails, What Actually Happened?

A Java e-commerce application handles a product purchase request. Within a single API call, the service needs to:

1. Check and decrement remaining inventory quantity.
2. Create an order document.
3. Record an `OrderPlaced` event for asynchronous downstream processing.
4. Return the order ID to the client.

If the inventory update succeeds while the order insert fails, data becomes inconsistent. If the transaction commits successfully on the server but the network connection drops right as the server replies, the client may see **an error even though the data actually committed**. If the driver re-executes the entire callback while that callback calls an external payment gateway, the user could be charged twice.

These three scenarios require distinguishing clearly between:

- **Session:** Operational context between client and server supporting causal consistency and transactions.
- **Transaction:** A group of database operations sharing a single commit/abort outcome.
- **Retry:** How the driver re-executes an eligible operation or entire transaction upon recoverable failures.
- **Idempotency:** How the application guarantees that repeating the same business request does not produce unintended duplicate effects.
- **Unknown outcome:** A state in which the client cannot determine whether a commit succeeded or not.

```text
HTTP request: Place Order
        │
        ▼
MongoDB Java Sync Driver
        │
        ├── MongoClient (thread-safe, connection pools)
        │
        └── ClientSession (bound to one client, used sequentially)
                 │
                 ├── Transaction attempt 1
                 │      update inventory
                 │      insert order
                 │      insert outbox event
                 │      commit / abort
                 │
                 ├── Retry transaction body?
                 │      only on eligible errors
                 │
                 └── Retry commit?
                        if outcome is unknown
                        does not mean re-running business logic
        │
        ▼
Application returns verified result
```

**Goal:** Write correct Java code for transactions and retries, avoid confusing driver retries with exactly-once business processing, and understand support prerequisites, error handling, resource limits, and failover testing.

---

## 2. Concept Map: Session, Transaction, and Retry

| Concept | Role | Do Not Confuse With |
|---|---|---|
| `MongoClient` | Entry point, topology discovery, connection pooling | A single TCP connection |
| `ClientSession` | Logical session and sequential context across operations | An always-active database transaction for the entire session lifetime |
| Implicit session | Driver-managed session for eligible commands | An API that automatically wraps multiple commands in a transaction |
| Explicit session | Application-created via `startSession()` | Inherent multi-document ACID semantics |
| Causal consistency | Preserves causal read/write ordering under matching conditions | Global database snapshot or full linearizability |
| Snapshot session | Supports multiple consistent snapshot reads at one point in time where supported | A multi-document write transaction |
| Multi-document transaction | Group of operations committing or aborting atomically | Atomic boundary covering external payment or email calls |
| Retryable write | Driver can automatically retry an eligible single write command | Automatic retry of `updateMany`/`deleteMany` |
| Retryable read | Driver can automatically retry an eligible read command | Retrying a cursor after multiple batches have been returned |
| `withTransaction()` | Callback API that retries transactions or commits using error labels | Guarantee that the callback runs strictly once |
| Idempotency key | Business constraint preventing duplicate outcomes for repeated requests | A built-in feature generated automatically by the driver |
| Outbox pattern | Recording event-publish intent within the same transaction | Automatic exactly-once delivery to Kafka |

### 2.1. A Session Does Not Equal a Transaction

~~~java
try (ClientSession session = client.startSession()) {
    // Operations attached to the session are NOT yet inside a transaction.
    collection.find(session).first();

    // Calling startTransaction begins a transaction.
    session.startTransaction();

    // ...
}
~~~

You can use a session for causal consistency without starting a transaction. Conversely, a transaction is always bound to a client session.

### 2.2. A Session Is Neither a Socket Nor a Java Thread

The driver may dispatch operations over different physical connections depending on topology and pooling. A logical session has a session ID tracked by the server. Never equate a session with a single TCP socket or a permanently pinned thread.

### 2.3. Transactions Are Not the First Tool for Every Operation

MongoDB guarantees **single-document atomicity**. For example, incrementing a counter or updating two fields in the **same document** rarely requires a multi-document transaction:

~~~javascript
db.inventory.updateOne(
  { _id: "SKU-100", available: { $gte: 2 } },
  { $inc: { available: -2 }, $set: { updatedBy: "checkout" } }
);
~~~

A single-document update is atomic on its own. Reserve multi-document transactions for invariants spanning multiple documents or collections.

---

## 3. Prerequisites for Using Transactions

### 3.1. Server Topology

Multi-document transactions require supported topologies and MongoDB versions:

- **Replica set:** supported since MongoDB 4.0.
- **Sharded cluster:** distributed transactions supported since MongoDB 4.2.
- **Standalone `mongod`:** does not support replica-set multi-document transactions.

A **single-node replica set** is a practical way to test transactions in a local lab; it still runs as a replica set, not standalone.

### 3.2. Driver and Server Versions

You need compatible MongoDB Java Sync Driver and MongoDB Server versions supporting sessions and transactions. Versions affect:

- Transaction options.
- Snapshot session behavior.
- Retryable reads/writes.
- Error labels.
- Command monitoring fields.
- Timeouts and sharded transaction limitations.

Do not assume every MongoDB deployment supports transactions merely because `startTransaction()` compiles in the driver.

### 3.3. Feature Compatibility Version

FCV governs feature availability depending on MongoDB Server version. During upgrades or major-version migrations, verify FCV, command support, and transaction restrictions in the target release.

Never alter FCV hastily just to "fix a failing transaction" without an upgrade runbook.

### 3.4. Access Privileges

The application principal must hold read/write privileges on all participating collections. Sessions and transactions **do not bypass RBAC**.

For instance, an account granted `readWrite` on one business database still lacks permission on another database unless granted an appropriate role.

### 3.5. Data Model and Operations

Evaluate:

- Which business invariants strictly require atomicity across multiple documents?
- How many documents, collections, and shards are touched?
- How long does a transaction stay open?
- How frequent are write conflicts?
- Are any external API calls placed inside the callback?
- Are idempotency keys and outbox records in place?
- What is the impact on p95/p99 latency and storage load?
- Are monitoring and rollback/reconciliation plans adequate?

---

## 4. Installing MongoDB Java Sync Driver

Maven example using a version aligned with your project:

~~~xml
<dependency>
  <groupId>org.mongodb</groupId>
  <artifactId>mongodb-driver-sync</artifactId>
  <version>5.5.0</version>
</dependency>
~~~

The version number above is an **illustrative example**, not a claim of being the latest release at all times. Choose an organization-approved version after reviewing release notes and server compatibility matrices.

Gradle equivalent:

~~~groovy
dependencies {
    implementation "org.mongodb:mongodb-driver-sync:5.5.0"
}
~~~

Rely on your project's dependency management; avoid mixing BSON or `driver-core` artifacts from different major versions on the same classpath.

### 4.1. Key Classes

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.MongoCollection;
import com.mongodb.TransactionOptions;
import com.mongodb.ReadConcern;
import com.mongodb.WriteConcern;
import com.mongodb.ReadPreference;
import org.bson.Document;
~~~

### 4.2. Connecting via Environment Variables

~~~java
String uri = System.getenv("MONGODB_URI");
if (uri == null || uri.isBlank()) {
    throw new IllegalStateException("Missing MONGODB_URI");
}

try (MongoClient client = MongoClients.create(uri)) {
    client.getDatabase("admin")
          .runCommand(new Document("ping", 1));
}
~~~

Example URI for a local single-node replica set:

~~~text
mongodb://127.0.0.1:27017/?replicaSet=rs0&retryWrites=true&retryReads=true
~~~

In production, configure seed lists or SRV records, TLS, `authSource`, pool sizing, and timeouts according to the real topology. Never hardcode usernames or passwords.

---

## 5. Lifecycle of ClientSession

### 5.1. Creating an Explicit Session

~~~java
try (MongoClient client = MongoClients.create(uri);
     ClientSession session = client.startSession()) {

    MongoDatabase db = client.getDatabase("commerce");
    MongoCollection<Document> orders =
            db.getCollection("orders");

    Document first = orders
            .find(session)
            .first();

    System.out.println(first);
}
~~~

`startSession()` allocates a session handle; `try-with-resources` guarantees `close()` runs upon leaving scope.

### 5.2. You Must Pass the Session to Every Operation

A very common bug:

~~~java
try (ClientSession session = client.startSession()) {
    session.startTransaction();

    // WRONG: forgot to pass session to the operation.
    orders.insertOne(new Document("_id", "O-1"));

    session.commitTransaction();
}
~~~

`orders.insertOne(...)` above executes **outside the transaction** because the overload used does not accept `session`.

Correct:

~~~java
try (ClientSession session = client.startSession()) {
    session.startTransaction();

    orders.insertOne(
            session,
            new Document("_id", "O-1"));

    session.commitTransaction();
}
~~~

**Rule:** Every MongoDB operation participating in the transaction must receive the same `ClientSession`, including reads, writes, and permitted commands.

### 5.3. An Explicit Session Can Run Multiple Sequential Transactions

~~~java
try (ClientSession session = client.startSession()) {
    session.startTransaction();
    // Operations for transaction A.
    session.commitTransaction();

    session.startTransaction();
    // Operations for transaction B.
    session.abortTransaction();
}
~~~

Never run two transactions concurrently on the same session. One transaction must commit or abort before another begins.

### 5.4. Do Not Share a ClientSession Across Threads

`MongoClient` is thread-safe and meant to be reused. However, `ClientSession` is **not thread-safe**; never use one session concurrently from two Java threads.

Wrong:

~~~java
ClientSession shared = client.startSession();

executor.submit(() -> collection.insertOne(
        shared, new Document("n", 1)));
executor.submit(() -> collection.insertOne(
        shared, new Document("n", 2)));
~~~

Behavior is undefined, especially inside an active transaction.

Better:

- Each request/workflow owns its own session.
- Operations inside a transaction run sequentially.
- Never use `parallelStream()` or concurrent `CompletableFuture` tasks against the same session.

### 5.5. Closing the Session

Use:

~~~java
try (ClientSession session = client.startSession()) {
    // ...
}
~~~

Do not store sessions in singletons, cache user sessions indefinitely, or forget to close them. Long-lived sessions and transactions create resource pressure; sessions are lifecycle-managed resources.

### 5.6. Sessions Belong to the MongoClient That Created Them

Do not pass a session created from `clientA.startSession()` into a collection obtained from `clientB.getDatabase(...)`. A session is tied to the client and topology context that instantiated it.

---

## 6. Implicit and Explicit Sessions

### 6.1. Implicit Sessions

For routine standalone operations:

~~~java
orders.find(eq("status", "PENDING")).first();
orders.insertOne(new Document("_id", "O-2"));
~~~

The driver transparently manages implicit sessions needed for retryable reads, retryable writes, and protocol features.

**You do not need to call `startSession()` for every CRUD call** just to benefit from driver retries.

### 6.2. Explicit Sessions

Use an explicit `ClientSession` when you need:

- Multi-document transactions.
- Causal consistency across a sequence of operations.
- Snapshot sessions where supported.
- Direct control over transaction scope and options.

### 6.3. Session ID and Transaction Number

In MongoDB wire protocol and diagnostics you will see fields like:

- `lsid`: logical session identifier.
- `txnNumber`: transaction and retryable write sequence number.
- `autocommit: false`: indicates an operation belonging to a multi-document transaction on the wire protocol.
- `startTransaction`: protocol marker indicating the first operation starting a transaction on the server.

These fields are managed by the driver and server. **Never manually inject `lsid` or `txnNumber` inside application BSON commands** to simulate internal transaction or retry mechanics.

---

## 7. Causal Consistency: Sessions Are Useful Even Without Transactions

### 7.1. The Problem

A service updates a user profile and immediately reads from a secondary experiencing replication lag. Without causal ordering constraints and suitable read/write concerns, the read may return stale data.

### 7.2. What Causal Consistency Provides

A causally consistent session tracks operation time / cluster time to preserve guarantees such as:

- Read your own writes.
- Monotonic reads.
- Monotonic writes.
- Writes follow reads.

These guarantees depend on server/topology support and matching read/write concerns. Per MongoDB documentation, full causal consistency guarantees require pairing **`majority` read concern and `majority` write concern** in supported contexts.

### 7.3. Configuring Explicit Causal Consistency

~~~java
import com.mongodb.ClientSessionOptions;

ClientSessionOptions options =
        ClientSessionOptions.builder()
                .causallyConsistent(true)
                .build();

try (ClientSession session =
             client.startSession(options)) {

    collection.withWriteConcern(WriteConcern.MAJORITY)
              .insertOne(
                      session,
                      new Document("_id", "C-100")
                              .append("status", "ACTIVE"));

    Document doc = collection
            .withReadConcern(ReadConcern.MAJORITY)
            .find(session, eq("_id", "C-100"))
            .first();

    System.out.println(doc);
}
~~~

This requires server and topology support. Not every workflow requires a transaction; above are **two sequential operations inside one causal session**.

### 7.4. A Causal Session Is Not Multi-Document Atomic

If your code writes:

~~~java
inventory.updateOne(session, ...);
orders.insertOne(session, ...);
~~~

without calling `session.startTransaction()`, those two commands **do not form a multi-document transaction**, even when causal consistency is enabled on the session.

### 7.5. Snapshot Sessions Are a Distinct Concept

Some driver/server versions support snapshot sessions for point-in-time reads outside transactions.

Conceptual example:

~~~java
ClientSessionOptions options =
        ClientSessionOptions.builder()
                .snapshot(true)
                .build();

try (ClientSession session =
             client.startSession(options)) {
    // Snapshot reads permitted per driver/server support.
}
~~~

Snapshot sessions and causal consistency carry distinct constraints; do not enable both blindly. A snapshot session **is not a multi-document write transaction**.

---

## 8. ACID in MongoDB Transactions

### 8.1. Atomicity

When a transaction commits successfully, all its writes commit together per MongoDB guarantees. If aborted, uncommitted writes within the transaction do not become committed state.

### 8.2. Consistency

MongoDB enforces atomicity and isolation mechanics, while **business invariants remain the application's responsibility**. A transaction will not prevent negative stock if your update omits the condition `available >= quantity`.

### 8.3. Isolation

MongoDB transactions provide snapshot isolation with read/write semantics governed by read concern and write-conflict detection. Do not claim that every transaction achieves strict serializable isolation.

Concurrent transactions can still encounter write conflicts, snapshot stale reads, or aborts.

### 8.4. Durability

Durability depends on write concern, replication configuration, and deployment health. Set `WriteConcern.MAJORITY` at the transaction level when majority durability acknowledgment is required.

### 8.5. MongoDB Scope Only

An ACID transaction only covers database operations executed inside that transaction. It never wraps:

- HTTP payment calls.
- Sending emails.
- Publishing directly to external Kafka clusters.
- Writing files to object storage.
- Third-party service invocations.

into MongoDB's atomic commit.

Coordinate those effects using outbox patterns, sagas, idempotency, and reconciliation workflows.

---

## 9. TransactionOptions: Read Concern, Write Concern, and Read Preference

### 9.1. Java Configuration

~~~java
TransactionOptions txnOptions =
        TransactionOptions.builder()
                .readConcern(ReadConcern.SNAPSHOT)
                .writeConcern(WriteConcern.MAJORITY)
                .readPreference(ReadPreference.primary())
                .build();
~~~

### 9.2. Read Concern

Relevant read concern levels:

- `local`.
- `majority`.
- `snapshot`, when supported inside transactions.

`ReadConcern.SNAPSHOT` lets transaction reads see a consistent snapshot per MongoDB semantics. Guarantees that a snapshot reflects majority-committed data also interact with commit write concern; do not treat the word `snapshot` in isolation as proof of total safety across failovers.

### 9.3. Write Concern

Configure `WriteConcern.MAJORITY` at the **transaction level**, rather than arbitrarily setting per-operation write concerns inside the transaction.

~~~java
TransactionOptions options =
        TransactionOptions.builder()
                .writeConcern(WriteConcern.MAJORITY)
                .build();
~~~

Individual writes *inside* a transaction should not carry custom write concerns; write concern applies at commit time per transaction rules.

### 9.4. Read Preference

Operations in a multi-document transaction must route to the **primary**. Configure:

~~~java
.readPreference(ReadPreference.primary())
~~~

explicitly. Do not design write transactions around `secondaryPreferred` read preference.

### 9.5. Defaults

If `TransactionOptions` is omitted, driver/server defaults apply and may inherit settings from client or session per API rules. Therefore:

- Do not assume every transaction defaults to `majority` + `snapshot`.
- Specify options explicitly for critical workflows.
- Verify default transaction options in your active driver version.
- Test behavior against replica set failovers.

### 9.6. maxCommitTime

When supported by your Java Driver version:

~~~java
TransactionOptions options =
        TransactionOptions.builder()
                .readConcern(ReadConcern.SNAPSHOT)
                .writeConcern(WriteConcern.MAJORITY)
                .readPreference(ReadPreference.primary())
                .maxCommitTime(5, java.util.concurrent.TimeUnit.SECONDS)
                .build();
~~~

This caps commit-operation wait time. It **does not mean the entire transaction body aborts after 5 seconds** or substitute for end-to-end deadlines.

---

## 10. Preparing an Example Data Model: Inventory, Orders, Outbox

Three collections in database `commerce_lab`:

```text
inventory
  _id: SKU-100
  available: 25
  reserved: 0

orders
  _id: order-...
  requestId: checkout-...
  sku: SKU-100
  quantity: 2
  status: CREATED

outbox
  _id: order-created:<orderId>
  type: OrderCreated
  payload: { orderId, sku, quantity }
  processed: false
~~~

### 10.1. Why Include `requestId`?

HTTP clients can retry after timeouts. `requestId` (an idempotency key) lets the application recognize retries of **the same order request** instead of creating duplicate orders.

### 10.2. Why Include `outbox`?

A MongoDB transaction cannot atomically commit to an external message broker. Recording **the intent to publish an event** inside the same transaction alongside order and inventory updates allows a downstream worker to publish reliably, retry safely, and mark completion.

### 10.3. Initializing Lab Data

In `mongosh` connected to a lab replica set:

~~~javascript
const lab = db.getSiblingDB("commerce_lab");

lab.inventory.insertOne({
  _id: "SKU-100",
  available: 25,
  reserved: 0,
  updatedAt: new Date()
});

lab.orders.createIndex(
  { requestId: 1 },
  { unique: true, name: "uq_order_request" }
);

lab.orders.createIndex(
  { status: 1, createdAt: -1 },
  { name: "idx_status_created" }
);

lab.outbox.createIndex(
  { processed: 1, createdAt: 1 },
  { name: "idx_outbox_pending" }
);

printjson(lab.inventory.findOne({ _id: "SKU-100" }));
~~~

Run initialization only on an **empty lab database**. Never run `dropDatabase()` on production just to reset an experiment.

### 10.4. Business Invariant

For a purchase of quantity = 2:

- `inventory.available` must decrease from 25 to 23.
- One matching `orders` document is inserted.
- One matching `outbox` event is inserted.
- If any step fails, nothing in the transaction commits.

Inventory deductions must use a conditional update to prevent overselling under concurrent transactions.

---

## 11. Manual Transaction API: Start, Commit, Abort

Explicit control flow to understand the underlying API:

~~~java
import com.mongodb.TransactionOptions;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Updates.set;

public final class ManualTransactionDemo {

    static void markTwoDocuments(
            MongoClient client,
            MongoCollection<Document> orders,
            MongoCollection<Document> outbox) {

        TransactionOptions options = TransactionOptions.builder()
                .readConcern(ReadConcern.SNAPSHOT)
                .writeConcern(WriteConcern.MAJORITY)
                .readPreference(ReadPreference.primary())
                .build();

        try (ClientSession session = client.startSession()) {
            session.startTransaction(options);

            try {
                orders.updateOne(
                        session,
                        eq("_id", "O-100"),
                        set("status", "CONFIRMED"));

                outbox.insertOne(
                        session,
                        new Document("_id", "confirmed:O-100")
                                .append("type", "OrderConfirmed"));
            } catch (RuntimeException bodyError) {
                try {
                    session.abortTransaction();
                } catch (RuntimeException abortError) {
                    bodyError.addSuppressed(abortError);
                }
                throw bodyError;
            }

            // If commit encounters an unknown-outcome error, DO NOT
            // automatically assume data rolled back.
            session.commitTransaction();
        }
    }
}
~~~

### 11.1. Why Separate Commit from the Body `catch` Block?

Errors during transaction body execution typically call for aborting the active transaction. However, an error **during commit** may leave the client uncertain whether commit succeeded.

Catching every exception, calling `abortTransaction()`, and claiming the rollback succeeded can mislead the application when the server actually committed the changes.

### 11.2. Where Manual Retry Gets Hard

You must distinguish carefully between:

- Transient errors before commit → retry the **entire transaction**.
- Unknown commit outcome errors → retry **commit** using the same transaction context without blindly re-running writes.
- Business errors (out of stock) → do not retry infinitely.
- Duplicate key errors → evaluate idempotency and business semantics.
- Non-retryable errors → fail clearly with context.

Implementing every branch accurately is error-prone; that is why the driver provides `withTransaction()`.

---

## 12. `withTransaction()`: The Preferred API for Most Workflows

`ClientSession.withTransaction(...)` accepts a callback representing the transaction body and handles driver-supported retry semantics automatically.

Short example:

~~~java
try (ClientSession session = client.startSession()) {
    String orderId = session.withTransaction(() -> {
        orders.insertOne(
                session,
                new Document("_id", "O-101")
                        .append("status", "CREATED"));

        outbox.insertOne(
                session,
                new Document("_id", "created:O-101")
                        .append("type", "OrderCreated"));

        return "O-101";
    }, txnOptions);

    System.out.println("Committed order " + orderId);
}
~~~

### 12.1. Why Must the Callback Be Free of External Side Effects?

The driver **may invoke the callback multiple times** if the transaction encounters eligible transient errors.

Never write:

~~~java
session.withTransaction(() -> {
    chargeCreditCard();
    sendEmail();
    orders.insertOne(session, order);
    return orderId;
}, txnOptions);
~~~

This is a severe anti-pattern. Payment charges and emails do not roll back when a MongoDB transaction aborts. A second callback attempt can charge the card or send emails twice.

### 12.2. When a Transaction Retries, What Actually Re-Runs?

When the driver retries an entire transaction due to an eligible labeled error:

- The previous attempt aborts or never commits.
- The callback may execute again from the start.
- Writes from the aborted attempt never become committed data.
- Side effects outside MongoDB **do not roll back automatically**.

### 12.3. Errors During Commit Differ from Errors in the Body

If commit outcome is unknown, the driver can **retry commit** for the same transaction based on error labels instead of immediately re-running the callback.

Why? Because the transaction may already be committed on the server. Re-running the callback could cause duplicate business operations or conflicts.

### 12.4. `withTransaction` Does Not Retry Forever

The driver enforces retry conditions and time limits. When retries cannot recover or the error is non-retryable, `withTransaction` throws the exception.

Your application still needs final error handling, idempotency, and reconciliation; never treat `withTransaction()` as a 100% success guarantee.

---

## 13. Full Java Example: Placing an Order and Reserving Inventory in a Transaction

### 13.1. Goals

- Inventory decreases only if sufficient stock remains.
- Order and outbox event are inserted in the same transaction.
- One idempotency key per request.
- No HTTP, email, or Kafka calls inside the callback.
- Allow driver-managed transaction retries where supported.

### 13.2. Java Service

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

import java.time.Instant;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.gte;
import static com.mongodb.client.model.Updates.inc;

public final class PlaceOrderService {

    private final MongoClient client;
    private final MongoCollection<Document> inventory;
    private final MongoCollection<Document> orders;
    private final MongoCollection<Document> outbox;

    private final TransactionOptions txnOptions =
            TransactionOptions.builder()
                    .readConcern(ReadConcern.SNAPSHOT)
                    .writeConcern(WriteConcern.MAJORITY)
                    .readPreference(ReadPreference.primary())
                    .build();

    public PlaceOrderService(MongoClient client) {
        this.client = client;
        MongoDatabase db = client.getDatabase("commerce_lab");
        this.inventory = db.getCollection("inventory");
        this.orders = db.getCollection("orders");
        this.outbox = db.getCollection("outbox");
    }

    public String placeOrder(
            String requestId,
            String sku,
            int quantity) {

        if (requestId == null || requestId.isBlank()) {
            throw new IllegalArgumentException("Missing requestId");
        }
        if (sku == null || sku.isBlank() || quantity <= 0) {
            throw new IllegalArgumentException("Invalid item");
        }

        // Deterministic identity for the same application request.
        final String orderId = "order:" + requestId;
        final String eventId = "event:" + requestId;

        try (ClientSession session = client.startSession()) {
            return session.withTransaction(() -> {
                UpdateResult reserved = inventory.updateOne(
                        session,
                        and(
                                eq("_id", sku),
                                gte("available", quantity)
                        ),
                        inc("available", -quantity)
                );

                if (reserved.getModifiedCount() != 1) {
                    throw new IllegalStateException(
                            "Insufficient inventory");
                }

                orders.insertOne(
                        session,
                        new Document("_id", orderId)
                                .append("requestId", requestId)
                                .append("sku", sku)
                                .append("quantity", quantity)
                                .append("status", "CREATED")
                                .append("createdAt",
                                        java.util.Date.from(
                                                Instant.now()))
                );

                outbox.insertOne(
                        session,
                        new Document("_id", eventId)
                                .append("type", "OrderCreated")
                                .append("orderId", orderId)
                                .append("processed", false)
                                .append("createdAt",
                                        java.util.Date.from(
                                                Instant.now()))
                );

                return orderId;
            }, txnOptions);
        }
    }
}
~~~

### 13.3. What Each Piece Does

1. `requestId` is the verified client/request idempotency identifier at the application layer.
2. `orderId` and `eventId` are derived **outside the callback** from `requestId`, rather than generating fresh UUIDs on each attempt.
3. Conditional `updateOne` decrements stock only if sufficient quantity exists.
4. `modifiedCount == 1` confirms one inventory record was decremented; otherwise a business exception aborts.
5. Both order and outbox inserts receive `session`.
6. `withTransaction` manages commit, abort, and retry per driver semantics.
7. External payment/email calls stay out of the transaction callback.

### 13.4. What Application Issues Still Remain to Handle?

Yes—consider what happens if a request is retried after the transaction has already committed:

- The second execution tries to decrement inventory first.
- Then inserting the order hits a duplicate `_id` or unique `requestId` error.
- The second transaction aborts cleanly, so inventory is not deducted again if abort works properly.
- However, the service would throw a duplicate-key exception instead of returning the already-created order.

Therefore, production APIs need **idempotency lookup and reconciliation**: check for an existing order by `requestId` upfront, guard against races via the unique index, and query committed state after duplicate-key or unknown-outcome errors.

Do not mistake this illustrative service for a complete idempotent HTTP endpoint.

### 13.5. Never Catch Everything and Return Success

If `withTransaction()` throws, the application must evaluate:

- Was it a business validation failure?
- Was it a duplicate request whose order already exists?
- Might the transaction have committed without the client receiving the response?
- Should the endpoint return HTTP 409, 503, 202, or a verification-pending status?

Never claim "order succeeded" without verified evidence.

---

## 14. Re-Reading Results by Idempotency Key

A service can model request handling like this:

```text
requestId = checkout-2026-abc

If order does not exist:
    attempt order creation transaction

If order already exists:
    return that existing order (after verifying request payload matches)

If commit outcome is unknown:
    query order by requestId with suitable consistency
    decide success/pending/retry per policy
~~~

### 14.1. Unique Index

~~~javascript
db.getSiblingDB("commerce_lab").orders.createIndex(
  { requestId: 1 },
  { unique: true, name: "uq_request" }
);
~~~

Do not create duplicate indexes if one already exists. A unique index enforces database-level protection against two orders sharing one `requestId`.

### 14.2. Bind the Idempotency Key to the Payload

Never accept an arbitrary `requestId` without payload verification. If a client reuses the same key with a different `sku` or `quantity`, reject it as a conflicting request.

Example record structure:

~~~javascript
{
  requestId: "checkout-2026-abc",
  requestHash: "HASH_OF_CANONICAL_BUSINESS_INPUT",
  orderId: "order:checkout-2026-abc",
  status: "CREATED"
}
~~~

The hash is illustrative; never emit raw PII into keys, metrics, or logs. Design idempotency record TTL and retention to fit business rules.

### 14.3. Reconciliation Reads Are Not Blind Retries

When commit outcome is unknown, a properly configured read checks whether a durable record matching business invariants already exists. Keep in mind:

- Reads hitting a lagging secondary may miss newly committed writes.
- Rollbacks/failovers can affect visibility if write concern was too weak.
- Inspect order, inventory, and outbox states coherently.
- When certainty is lacking, return pending and let background reconciliation finish instead of deducting inventory twice.

---

## 15. Transaction Retries: Two Crucial Branches

MongoDB drivers rely on **error labels** to determine how transaction errors should be handled.

### 15.1. `TransientTransactionError`

Label:

~~~text
TransientTransactionError
~~~

generally indicates the transaction failed due to a transient condition during execution.

Handling model:

```text
Transaction body attempt
      │
      ├── success → commit
      │
      └── error labeled TransientTransactionError
              │
              └── retry WHOLE transaction callback
                     with a new transaction attempt
~~~

Because the callback can re-run, **keep external side effects out of it**.

### 15.2. `UnknownTransactionCommitResult`

Label:

~~~text
UnknownTransactionCommitResult
~~~

indicates the client **cannot determine** whether commit succeeded in that failure scenario.

Handling model:

```text
Transaction body completed
          │
          ▼
commitTransaction
          │
          ├── success → committed
          │
          └── UnknownTransactionCommitResult
                   │
                   └── retry COMMIT for same transaction
                       do not immediately re-run body
~~~

**It means neither guaranteed abort nor guaranteed commit**—the outcome is ambiguous from the client's viewpoint.

### 15.3. Why Are the Two Branches Different?

A transient error prior to commit requires executing the database operations cleanly in a fresh attempt. By contrast, if the server already committed and the connection dropped before the ack returned, re-running the body would create unintended duplicate operations.

### 15.4. Errors Outside Both Labels

Not every error is retryable:

- Validation errors.
- Authorization failures (`Unauthorized`).
- Duplicate keys caused by business invariants.
- Disallowed operations inside a transaction.
- Unsupported server/topology.
- Time or resource limit exhaustion.
- Application exceptions like `IllegalStateException("Insufficient inventory")`.

Other error labels exist with version-dependent behavior; never wrap every exception in blanket retries.

---

## 16. Inspecting Error Labels in Java

The MongoDB Java Driver exposes `MongoException.hasErrorLabel(...)`.

~~~java
import com.mongodb.MongoException;

try {
    doTransaction();
} catch (MongoException e) {
    boolean transientTxn =
            e.hasErrorLabel("TransientTransactionError");

    boolean unknownCommit =
            e.hasErrorLabel("UnknownTransactionCommitResult");

    System.err.println(
            "transientTxn=" + transientTxn +
            ", unknownCommit=" + unknownCommit +
            ", errorCode=" + e.getCode());

    throw e;
}
~~~

This snippet illustrates reading labels only. Do not retry the whole transaction inside `catch` if `doTransaction()` already uses `withTransaction()`, which runs spec-defined retries internally.

### 16.1. Do Not Infer Retryability from Error Message Strings

Wrong:

~~~java
if (e.getMessage().contains("not primary")) {
    retryEverything();
}
~~~

Error text varies across server and driver versions and is a brittle API contract for retry decisions.

Prefer:

- Error labels.
- Documented error codes and categories.
- Driver retry helpers.
- Documented exception types.
- Business idempotency rules.

### 16.2. Error Labels Do Not Change Business Semantics

Even when a label marks an error retryable, external side effects inside callbacks remain unsafe. Correct driver-layer retries **never automatically deliver end-to-end exactly-once execution**.

---

## 17. Retryable Writes: Automatic Retry for Eligible Single Writes

### 17.1. What Are Retryable Writes?

When `retryWrites=true` and both topology and command qualify, MongoDB Java Driver automatically retries eligible **single-statement write operations** after recoverable network or failover errors.

Example:

~~~java
orders.insertOne(
        new Document("_id", "O-200")
                .append("status", "CREATED"));
~~~

If the response drops after the server executes the write, the driver leverages session/transaction numbering protocols to prevent duplicate execution under supported semantics.

### 17.2. URI Configuration

~~~text
mongodb://mongo1.example.internal:27017,mongo2.example.internal:27017,mongo3.example.internal:27017/?replicaSet=rs0&retryWrites=true
~~~

In modern MongoDB Java Driver releases, retryable writes are typically **enabled by default** where supported. Still, verify your connection string, driver version, and cluster settings explicitly rather than guessing.

### 17.3. Commonly Eligible Operations

Examples typically eligible as retryable writes when conditions are met:

- `insertOne()`.
- `updateOne()`.
- `replaceOne()`.
- `deleteOne()`.
- `findOneAndUpdate()`.
- `findOneAndReplace()`.
- `findOneAndDelete()`.
- Certain bulk writes subject to statement-type restrictions.

### 17.4. Operations Not Treated as Retryable Single-Statement Writes

Examples:

- `updateMany()`.
- `deleteMany()`.
- Multi-write patterns outside the retryable writes specification.
- Write concern `w:0`.
- Commands outside the eligible set.
- Unsupported topologies or server versions.

Never write a wrapper claiming "`retryWrites=true` makes every write safe to retry".

### 17.5. Comparison Table

| Java Operation | Eligible for Retryable Write? | Notes |
|---|---|---|
| `insertOne` | Yes, when eligible | Uses session/txn numbering |
| `updateOne` | Yes, when eligible | Single statement |
| `replaceOne` | Yes, when eligible | Single statement |
| `deleteOne` | Yes, when eligible | Single statement |
| `findOneAndUpdate` | Yes, when eligible | Single-document read-modify-write |
| `updateMany` | No (under standard retryable writes) | Multi-document match |
| `deleteMany` | No (under standard retryable writes) | Multi-document match |
| `bulkWrite` | Depends on single vs. multi statements | Check driver/server docs |
| Multi-document transaction | Retried via transaction mechanism | Individual statements inside do not retry independently |

### 17.6. Retryable Writes Do Not Solve Duplicate Application Requests

If an HTTP client resends **the same request** after an earlier attempt succeeded, that is an **application-level retry**, not the driver retrying a single wire command.

If your code calls `new ObjectId()` on every HTTP attempt, the driver has no way to tell that two requests came from the same business intent.

Use idempotency keys and unique indexes for requests clients may resubmit.

---

## 18. Retryable Reads: Automatic Retry for Eligible Read Operations

### 18.1. Configuration

~~~text
mongodb://mongo1.example.internal:27017/?replicaSet=rs0&retryReads=true
~~~

Modern Java Drivers typically enable retryable reads by default when supported.

### 18.2. Commonly Eligible Operations

- `find`.
- `aggregate` pipelines excluding write stages.
- `distinct`.
- Certain metadata and initial cursor commands per the driver spec.

Never assume every "read-looking" method retries automatically; verify operation eligibility in documentation.

### 18.3. `getMore` Is Not Retryable Like the Initial `find`

MongoDB cursors stream results in batches:

```text
find      → firstBatch
getMore   → secondBatch
getMore   → thirdBatch
~~~

The driver can retry initial `find` per the retryable reads specification. However, `getMore` is **not** a standard retryable read.

If a cursor fails after yielding partial batches, never assume "`retryReads=true` guarantees delivering the rest of the cursor exactly once".

### 18.4. Reading Mutating Data

Even when a `find` retries successfully, evaluate consistency. Concurrent writes occurring between attempts can yield different documents.

Retryable reads do not provide a single consistent snapshot across independent commands.

### 18.5. Aggregations with `$out` or `$merge`

Aggregations containing write stages like `$out` or `$merge` have different semantics from read-only aggregations and should not be treated as standard retryable reads.

### 18.6. `maxTimeMS` and Timeouts

Setting `maxTimeMS` or client-side timeouts bounds execution time, yet timing out neither makes an operation retryable nor proves "the operation never happened".

---

## 19. Retryable Reads/Writes vs. Transaction Retries

| Dimension | Retryable Read/Write | Transaction Retry |
|---|---|---|
| Scope | Single eligible command | Multi-operation transaction |
| Configured via | Connection settings/defaults | Session transaction API, `withTransaction` |
| Trigger condition | Eligible operation/topology/error | Error labels and transaction state |
| Re-runs business callback | No (not an application callback) | Potentially yes with `withTransaction` |
| Handles unknown commit outcome | N/A (not a transaction commit) | Retries commit per label |
| Multi-document atomicity | No | Yes within MongoDB |
| Exactly-once external side effects | No | Also no |
| Business idempotency key | Still required | Still required |

### 19.1. `retryWrites=true` Does Not Retry an Entire Transaction Body

Inside a transaction, rely on transaction retry APIs and logic; do not expect `retryWrites=true` to retry individual `updateOne(session, ...)` calls independently as standalone writes.

### 19.2. `withTransaction` Does Not Retry Separate HTTP Requests

The driver only manages attempts within a single service invocation. If the client loses the HTTP response and sends a second request, the server receives **a new invocation**. Only a business idempotency key handles that scenario.

### 19.3. A Database Write Attempt Can Execute More Than Once Internally

Through transaction aborts or retryable write protocols, MongoDB prevents unintended duplicate committed effects within its scope. Metrics or logs may show multiple attempts; that does not mean business records were duplicated.

---

## 20. Common Transaction Errors

### 20.1. WriteConflict

Two concurrent transactions try modifying the same document:

```text
Transaction A reads stock 10
Transaction B reads stock 10
A updates stock
B tries same document
→ one side may receive WriteConflict / transient abort
~~~

Remediation:

- Keep transactions short.
- Use conditional updates.
- Use `withTransaction()` for built-in retry handling.
- Reduce contention on hot documents.
- Avoid unbounded manual retry loops.

### 20.2. Lock Contention

Long transactions hold or wait on locks/resources, harming latency and throughput.

Never keep a transaction open while waiting for:

- A user typing an OTP.
- A payment gateway taking tens of seconds.
- Flaky external APIs.
- Long worker sleeps or backoffs.

Keep those steps **outside transactions** and coordinate via sagas or outbox workflows.

### 20.3. `TransactionLifetimeLimitSeconds`

On many MongoDB deployments, the default transaction lifetime limit is around **60 seconds**, though operators can configure the exact value and defaults may vary by version or provider.

Transactions exceeding this limit are aborted.

Never raise the lifetime limit to hours just to wrap external HTTP calls; shorten the transaction body instead.

### 20.4. DuplicateKey

A `DuplicateKey` error on `insertOne` can indicate:

- An HTTP `requestId` already processed earlier.
- Concurrent requests carrying the same idempotency key.
- Data inconsistency.
- Broken ID generation logic.
- A race between transactions.

Never retry duplicate-key errors indefinitely. Look up the existing document and verify payload hashes according to business rules.

### 20.5. Unauthorized

Missing collection privileges or executing disallowed commands inside a transaction. Retrying with the same credentials/roles will not succeed.

### 20.6. TransactionTooLargeForCache

An oversized transaction can breach cache/resource thresholds and abort. Split work into smaller batches or redesign the workflow rather than assuming adding RAM is the sole fix.

### 20.7. Primary Stepdown / Network Error

When the primary changes:

- Transactions may receive transient errors.
- Commit outcomes may become unknown.
- The driver rediscovers topology and retries when eligible.
- The application handles the final resolved result.

Never assume "network exception = transaction definitely aborted".

### 20.8. Write Concern Timeout

If commit reports a write concern timeout, inspect error labels along with server/driver semantics. A write concern timeout does not automatically mean the write failed to commit.

### 20.9. Inactive / Expired Session

Logical sessions have server/driver-managed timeouts and resource lifecycles. Very long operations or leaked sessions trigger session-related errors.

Open and close sessions per request or workflow; never retain them indefinitely.

---

## 21. Operations Restricted Inside Transactions

Multi-document transactions do not allow every MongoDB command across all versions and topologies.

Check restrictions on:

- Certain DDL and collection/index management operations.
- Certain administrative commands.
- Aggregation stages `$out` or `$merge`.
- Capped collection limitations.
- Implicit collection creation or cross-shard rules depending on version.
- Commands disallowed by driver/server within transactions.
- Transaction time and resource limits.

Never assume "since a command works outside a transaction, it must also work inside one".

### 21.1. Never Create Indexes Inside an Order Callback

Prepare indexes before traffic arrives:

~~~javascript
db.getSiblingDB("commerce_lab").orders.createIndex(
  { requestId: 1 },
  { unique: true, name: "uq_request" }
);
~~~

Do not run `createIndex` on every request inside a transaction merely to skip a migration step.

### 21.2. Never Mix Schema Migrations Inside Business Transactions

Schema and index updates belong in dedicated migration plans, not bundled into customer checkout transactions without verification and support checks.

### 21.3. Sharded Transactions Carry Higher Overhead

Transactions spanning multiple shards require distributed commit coordination, increasing network traffic, resource consumption, and tail latency.

Favor data models that co-locate related writes on one shard where practical, without blindly sacrificing correctness.

---

## 22. Transaction Isolation and Concurrent Updates

### 22.1. Snapshots Do Not Eliminate Conflicts

Two transactions can read from separate snapshots, yet when both update the same document, MongoDB resolves the conflict.

One transaction may abort with a transient error so the driver or application can retry.

### 22.2. Conditional Updates Pair Naturally with Transactions

To deduct stock safely:

~~~java
UpdateResult result = inventory.updateOne(
        session,
        and(
                eq("_id", sku),
                gte("available", quantity)
        ),
        inc("available", -quantity)
);

if (result.getModifiedCount() != 1) {
    throw new IllegalStateException("Out of stock");
}
~~~

The predicate `available >= quantity` expresses the invariant directly. Reading `available` first and issuing an unconditional write with an app-computed value risks anomalies without proper concurrency control.

### 22.3. Business Locks vs. MongoDB Transactions

When workflows need long-lived business locks, never hold a MongoDB multi-document transaction open for minutes. Use:

- Reservation documents with explicit expiry timestamps.
- State machines.
- Compare-and-set version fields.
- Outbox/sagas.
- Application retry policies.

### 22.4. Snapshot Stale Reads

An active transaction reads from a snapshot that excludes concurrent external updates committed afterward. Never assume every read inside a transaction sees "the latest committed value on primary".

---

## 23. Transaction Performance: Keep Them as Short as Possible

### 23.1. Overhead of Transactions

Transactions increase:

- Lock and resource retention.
- Probability of write conflicts.
- Oplog and replication load.
- WiredTiger cache pressure.
- Tail latency.
- Network round trips.
- Cross-shard coordination overhead.
- Recovery complexity after timeouts.

### 23.2. Do Not Turn Transactions into Unbounded "Batch Containers"

Wrong:

~~~java
session.withTransaction(() -> {
    for (Order order : oneMillionOrders) {
        collection.insertOne(session, toDocument(order));
    }
    return null;
}, txnOptions);
~~~

A single gigantic transaction is not a safe way to migrate millions of documents. Split into batches with durable checkpoints, idempotency, and migration runbooks.

### 23.3. Keep Heavy Business Computation Outside Transactions

Avoid CPU-intensive image processing, CSV parsing, encrypting huge payloads, or calling external APIs inside transaction callbacks.

Run input validation and computations that do not depend on the transaction snapshot **before** starting the transaction.

### 23.4. Sequence Operations Cleanly

Touch only required documents. Add indexes so filters and updates run fast instead of holding transactions open during large scans.

### 23.5. SLOs and Limits

Configure:

- Operation timeouts matching driver/server policies.
- Commit timeouts where supported.
- Circuit breakers and HTTP deadlines.
- Retry budgets.
- Backoff when the application retries after driver exceptions.

Never set retry budgets far exceeding the HTTP deadline without asynchronous job execution and reconciliation.

---

## 24. Application-Level Retry Policies: Do's and Don'ts

### 24.1. Never "Catch Exception and Loop Forever"

Wrong:

~~~java
while (true) {
    try {
        placeOrder();
        break;
    } catch (Exception ignored) {
        // Endless retry, hides permanent errors.
    }
}
~~~

Consequences:

- Infinite retries on permanent authorization or validation errors.
- Load storms.
- Lost visibility into unknown commit outcomes.
- Exhausted connection pools and thread capacity.
- Repeated execution of business requests.

### 24.2. Define a Retry Budget

When adding application-level retries above the driver, enforce:

- Maximum attempt count or total elapsed time limit.
- Exponential backoff with jitter.
- Retries restricted to eligible error categories.
- Stable idempotency keys.
- Per-attempt telemetry.
- Deadline propagation.
- Unknown-outcome reconciliation.

### 24.3. Do Not Blindly Retry Callbacks from the Web Layer After Helper Exhaustion

If `withTransaction` already performed several attempts and threw, the web layer should not blindly invoke the entire service method again without checking idempotency and error state.

### 24.4. Idempotency Has Design Costs

Unique indexes and state checks require careful planning:

- What TTL/retention period applies?
- How is the canonical payload hash computed?
- What response goes back if a key is reused with different inputs?
- If a request is `IN_PROGRESS`, return pending or wait?
- When commit outcome is unknown, when do you re-query?
- If the order committed while outbox publishing failed, how does the worker recover?

---

## 25. Transactions and the Outbox Pattern

### 25.1. The Dual-Write Problem

Wrong:

~~~text
1. Commit order to MongoDB
2. Publish OrderCreated to Kafka
~~~

If step 1 succeeds and step 2 fails, downstream services never hear about the new order.

Reversing the order is also broken:

~~~text
1. Publish OrderCreated to Kafka
2. Commit order to MongoDB
~~~

If publishing succeeds and the DB fails, downstream consumers react to an order that does not exist.

### 25.2. How Outbox Solves This

Inside one MongoDB transaction:

~~~text
update inventory
insert order
insert outbox event
COMMIT
~~~

After commit, an asynchronous worker does:

~~~text
read pending outbox event
publish to broker
mark outbox processed
~~~

If publishing succeeds and the worker crashes before marking processed, the event may be republished. Therefore, downstream consumers still need **idempotency and deduplication**.

### 25.3. Never Promise Exactly-Once Across MongoDB and an External Broker

MongoDB transactions cannot atomically commit to Kafka, SMTP, or payment gateways. Outbox guarantees atomicity between **business state and event-publish intent** inside MongoDB, followed by at-least-once delivery plus consumer deduplication.

### 25.4. Outbox Worker Sample Flow

~~~text
repeat:
  find one pending outbox record
  publish with eventId as dedupe key
  if broker ack:
      mark processed with conditional update
  else:
      backoff and retry
~~~

Workers must address:

- Concurrent worker instances.
- Duplicate publishes.
- Retry and backoff.
- Poison messages.
- Dead-letter queues.
- Broker acknowledgments.
- Observability and retention.

### 25.5. Why Not Publish Inside the `withTransaction` Callback?

The callback can re-run, and external brokers cannot roll back with MongoDB. Outbox decouples external side effects from the callback while keeping event intent transactional.

---

## 26. Causal Reads, Read Concern, and Post-Commit Consistency

### 26.1. Why Care About `readConcern` After Commit?

Writing with a weak write concern followed by failover can alter durability and visibility. Reading immediately after commit from a lagging secondary without causal/session controls can observe stale state.

### 26.2. Majority Write Concern

Committing transactions with `WriteConcern.MAJORITY` waits for replica set majority acknowledgment, reducing certain rollback risks compared to weaker acknowledgment in supported topologies.

It does not make deployments immune to all infrastructure outages or disasters.

### 26.3. `ReadConcern.SNAPSHOT`

Within a transaction, snapshot reads provide a consistent view per snapshot semantics. Paired with majority commit, MongoDB documents guarantees over majority-committed snapshots.

Do not confuse `ReadConcern.SNAPSHOT` with `ReadPreference.secondary()`.

### 26.4. Causally Consistent Sessions

When sequential operations need read-your-own-writes without multi-document atomicity, a causal session paired with majority read and write concerns can suffice without starting transactions.

### 26.5. Reads Outside Transactions

A read on a different session, different node, or different timestamp sees its own consistency semantics. Transactions do not magically enforce instant global visibility everywhere across differing replication lags and read preferences.

---

## 27. Choosing the Right Mechanism for Each Problem

| Requirement | Consider Using |
|---|---|
| Update 2 fields in 1 document | Single-document atomic update |
| Insert a single order | `insertOne` + unique business key |
| Retry network errors on eligible single write | Driver retryable write |
| Retry `find` on eligible network error | Driver retryable read |
| Update inventory + insert order atomically | Multi-document transaction |
| Read your own writes across sequential calls | Causally consistent session with matching concerns |
| Multiple consistent reads without writes | Snapshot session where supported |
| DB write + Kafka event | Transaction + outbox |
| Third-party payment + DB state | Saga/idempotency/reconciliation (never hold DB txn across HTTP) |
| Bulk migration of millions of documents | Batching + checkpointing (never one giant transaction) |
| Client resends HTTP requests | Application idempotency key |
| Unknown commit outcome | Driver commit retry + state reconciliation |
| Offload reads to secondaries | Read preference + causal consistency (never write transactions on secondaries) |
| Make every query ultra-fast | Query modeling, indexing, profiling (transactions do not add speed) |

---

## 28. Transactions in Spring and Frameworks

Many Java frameworks wrap driver transactions—for instance, Spring Data MongoDB with `MongoTransactionManager`.

Conceptual example:

~~~java
@Transactional
public void placeOrder(...) {
    inventoryRepository.reserve(...);
    orderRepository.save(...);
}
~~~

However, **do not assume an annotation guarantees a working MongoDB transaction** if:

- No transaction manager is configured.
- The server runs standalone.
- Code bypasses Spring templates with a separate raw `MongoClient` not bound to the session.
- Async tasks run outside the transaction thread context.
- Self-invocation bypasses framework proxies.
- Database operations execute without binding the session.
- Framework default concerns or timeouts mismatch requirements.

This lesson focuses directly on the **Java Sync Driver API**; when using a framework, consult its version-specific docs to see how session binding and propagation work.

### 28.1. Transaction Boundaries

Even inside frameworks, place transaction boundaries at the business service layer—never at controllers spanning long external HTTP calls.

### 28.2. Retrying `@Transactional` Is Not Identical to `withTransaction`

Frameworks implement separate retry mechanisms. Combining framework retries and driver retries requires strict ordering, idempotency, and retry-budget control to avoid unexpected retry amplification.

---

## 29. Command Monitoring: Observing Retries Without Leaking Data

The Java Driver provides `CommandListener` for inspecting commands.

### 29.1. Minimal Safe Listener Example

~~~java
import com.mongodb.event.CommandFailedEvent;
import com.mongodb.event.CommandListener;
import com.mongodb.event.CommandStartedEvent;
import com.mongodb.event.CommandSucceededEvent;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.concurrent.TimeUnit;

public final class SafeCommandListener
        implements CommandListener {

    private static final Logger LOG =
            LoggerFactory.getLogger(SafeCommandListener.class);

    @Override
    public void commandStarted(CommandStartedEvent event) {
        LOG.debug(
                "mongo.start command={} database={} requestId={}",
                event.getCommandName(),
                event.getDatabaseName(),
                event.getRequestId());
    }

    @Override
    public void commandSucceeded(CommandSucceededEvent event) {
        LOG.debug(
                "mongo.success command={} requestId={} elapsedMs={}",
                event.getCommandName(),
                event.getRequestId(),
                event.getElapsedTime(TimeUnit.MILLISECONDS));
    }

    @Override
    public void commandFailed(CommandFailedEvent event) {
        LOG.warn(
                "mongo.failed command={} requestId={} elapsedMs={} exceptionType={}",
                event.getCommandName(),
                event.getRequestId(),
                event.getElapsedTime(TimeUnit.MILLISECONDS),
                event.getThrowable().getClass().getSimpleName());
    }
}
~~~

**Never log the full `event.getCommand()` BSON document in production**: commands may contain PII, passwords, or sensitive payloads. Logging every successful command at `INFO` level can also cause log storms.

### 29.2. Registering the Listener

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

String uri = System.getenv("MONGODB_URI");

MongoClientSettings settings = MongoClientSettings.builder()
        .applyConnectionString(new ConnectionString(uri))
        .addCommandListener(new SafeCommandListener())
        .build();

try (MongoClient client = MongoClients.create(settings)) {
    // Application workload.
}
~~~

### 29.3. Observing Transaction Commands

You may observe events for commands such as:

- `insert`, `update`, `find`...
- `commitTransaction`.
- `abortTransaction`.

During retries, monitoring records extra attempts. Do not equate raw `commandStarted` counts with committed business orders.

### 29.4. Metrics to Track

- Transaction attempt count.
- Transaction commit/abort counts.
- Error labels by category.
- Retry counts per command type.
- Transaction duration p50/p95/p99.
- `WriteConflict` rates.
- Unknown commit outcomes.
- Connection pool wait times.
- Replica set elections/stepdowns.
- Server CPU, I/O, and cache health.
- Pending outbox age and duplicate publish counts.
- Idempotency conflicts.

### 29.5. Monitoring Is Not the Source of Truth for Commit Outcome

The driver may hit a network failure during commit even though the server committed. Distinguish **confirmed failures** from **unknown outcomes** in any "commit failed" metric.

---

## 30. Practicing with a Local Single-Node Replica Set

### 30.1. Why Not Standalone?

MongoDB multi-document transactions require a supported topology. For local learning, a single-node replica set is the simplest option.

### 30.2. Starting a Lab `mongod`

Linux/macOS example (requires MongoDB Server binaries and an appropriate data directory):

~~~bash
mkdir -p ./mongo-rs-lab
mongod --replSet rs0 --port 27017 --dbpath ./mongo-rs-lab --bind_ip 127.0.0.1
~~~

This is an **isolated lab process**; do not reuse a port or `dbPath` belonging to another running MongoDB service. On Windows, pick a valid folder and matching PowerShell path.

### 30.3. Initiating the Single-Node Replica Set

Open `mongosh`:

~~~javascript
rs.initiate({
  _id: "rs0",
  members: [
    { _id: 0, host: "127.0.0.1:27017" }
  ]
});
~~~

Wait for the node to elect `PRIMARY`:

~~~javascript
rs.status();
db.adminCommand({ hello: 1 });
~~~

Perform this only in lab environments. Never re-run `rs.initiate()` on an existing production replica set.

### 30.4. Connection String

~~~text
mongodb://127.0.0.1:27017/?replicaSet=rs0&retryWrites=true&retryReads=true
~~~

If auth or TLS is enabled, append the proper options and pull credentials from a secret manager.

### 30.5. Testing with a Simple Transaction

~~~java
try (ClientSession session = client.startSession()) {
    session.startTransaction();

    collection.insertOne(
            session,
            new Document("_id", "txn-lab-001"));

    session.commitTransaction();
}
~~~

Verify the document exists:

~~~javascript
db.getSiblingDB("commerce_lab")
  .getCollection("orders")
  .findOne({ _id: "txn-lab-001" });
~~~

---

## 31. Lab: Testing Transaction Abort

### 31.1. Start a Transaction and Abort It

~~~java
try (ClientSession session = client.startSession()) {
    session.startTransaction();

    orders.insertOne(
            session,
            new Document("_id", "abort-lab-001")
                    .append("status", "TEMPORARY"));

    session.abortTransaction();
}
~~~

### 31.2. Verify

~~~javascript
db.getSiblingDB("commerce_lab")
  .orders.findOne({ _id: "abort-lab-001" });
~~~

Expect `null` in the lab (assuming the document did not exist beforehand), because the aborted transaction's writes were discarded.

### 31.3. Deliberate Bug Experiment: Omitting `session`

~~~java
try (ClientSession session = client.startSession()) {
    session.startTransaction();

    orders.insertOne(
            new Document("_id", "outside-txn-001"));

    session.abortTransaction();
}
~~~

`outside-txn-001` may be persisted anyway because `insertOne` did not receive `session` and ran outside the transaction.

Run this experiment in the lab only; it demonstrates the anti-pattern so you learn to spot the bug.

---

## 32. Lab: Testing Business Exceptions Inside a Transaction

### 32.1. Requesting Quantity Exceeding Available Stock

With `SKU-100` having `available = 25`, request `quantity = 100`:

~~~java
service.placeOrder("request-out-of-stock", "SKU-100", 100);
~~~

Inside the service:

~~~java
UpdateResult reserved = inventory.updateOne(
        session,
        and(
                eq("_id", "SKU-100"),
                gte("available", 100)),
        inc("available", -100));

if (reserved.getModifiedCount() != 1) {
    throw new IllegalStateException(
            "Insufficient inventory");
}
~~~

### 32.2. Expected Outcome

- The transaction callback throws a business exception.
- Neither order nor outbox document commits.
- Inventory remains untouched.
- The driver does not endlessly retry out-of-stock errors.

### 32.3. Distinguish Retryable Errors from Business Errors

Insufficient stock is not a transient network glitch. Retrying will not conjure inventory unless another business state change occurs.

An appropriate HTTP response might be 409 Conflict or a contract-defined domain error—not 500 with infinite retries.

---

## 33. Concurrency Lab: Two Transactions Competing for the Same Inventory

### 33.1. Scenario

Two concurrent requests buy the last remaining unit of a product.

~~~text
Available = 1

Request A: quantity 1
Request B: quantity 1
~~~

### 33.2. Desired Behavior

Exactly one order commits successfully, and inventory never turns negative.

### 33.3. Mechanics

- Conditional update `available >= quantity`.
- MongoDB snapshot isolation and write conflict detection.
- Driver transaction retry upon transient conflict.
- Upon retry, the losing request sees insufficient inventory and fails cleanly with the business exception.

### 33.4. Takeaway

**Using transactions alone is insufficient** if your code skips checking `modifiedCount` or omits the conditional invariant. At the same time, you do not need to manually lock the entire collection to serialize a conditional update.

### 33.5. Safe Concurrency Testing Practice

Run the concurrency test in a small lab using an executor where **each task creates its own `ClientSession`**—never share one `ClientSession` across tasks.

---

## 34. Lab: Testing Failover and Retries

### 34.1. Why Use a Multi-Node Replica Set?

A single-node replica set supports transactions but cannot simulate electing a new primary during failover. To test driver retries across a primary stepdown, run a multi-member data-bearing replica set in the lab.

### 34.2. Scenarios to Test

- Primary stepdown immediately before a write.
- Network timeout during a read.
- `WriteConflict` inside the transaction body.
- Dropped connection around commit.
- Retryable write where the response drops before reaching the client.
- HTTP retry arriving after a transaction has already committed.

### 34.3. Never Use Failpoints Casually in Production

MongoDB offers testing failpoints such as `failCommand` on supported deployments/versions/privileges. They exist for fault injection in tests—**not as casual production debugging tools**.

Enable them only in isolated labs with strict duration bounds and cleanup.

### 34.4. Invariants to Verify

For every test:

1. Requests either recover or fail according to policy.
2. Inventory never goes negative.
3. No two orders share the same `requestId`.
4. Outbox entries keep deterministic event identities.
5. Zero duplicate payment charges or emails originate from transaction callbacks.
6. Logs contain sanitized error labels.
7. Driver retries remain bounded.
8. Unknown commit outcomes trigger proper reconciliation.

---

## 35. An Application-Level Retry State Machine

You can model the lifecycle as:

```text
NEW
 │
 ▼
RUNNING_TRANSACTION
 │
 ├── business failure ──> REJECTED
 │
 ├── transient txn error ──> RETRY_TRANSACTION
 │                           (bounded by driver/policy)
 │
 └── body completed ──> COMMITTING
                            │
                            ├── commit success ──> COMMITTED
                            │
                            └── unknown result ──> RETRY_COMMIT
                                                      │
                                                      ├── confirmed
                                                      │    └── COMMITTED
                                                      └── unresolved
                                                           └── RECONCILE
~~~

### 35.1. What Is `RECONCILE`?

Inspect the business record by `requestId` and check invariants using suitable read/write concerns.

When certainty is unavailable:

- Never deduct inventory again automatically.
- Optionally return pending/accepted while background verification resolves it.
- Track idempotency state.
- Set deadlines and alerts for stuck operations.

### 35.2. Transaction Retries Do Not Mean Retrying HTTP Side Effects

Each layer retries only what it controls safely:

- Driver: eligible commands and transaction attempts.
- Application: idempotent business requests.
- Outbox worker: event delivery with deduplication.
- Payment adapter: provider-side idempotency keys.

### 35.3. Backoff

For retries outside the driver, use exponential backoff with jitter and a bounded budget. Never busy-loop while a primary is failing over or the database is unreachable.

---

## 36. Common Anti-Patterns

| Anti-Pattern | Why It Fails | Better Approach |
|---|---|---|
| Using a session without `startTransaction` | No multi-document atomicity | Call transaction API when atomicity is needed |
| Starting a transaction without passing `session` | Operations execute outside the transaction | Pass `session` to every DB operation |
| Sharing one session across threads | Not thread-safe | Give each workflow its own session |
| Forgetting to close sessions | Resource leak | Use `try-with-resources` |
| Creating a new `MongoClient` per request | Rebuilds connection pools constantly | Reuse `MongoClient` |
| Sending email inside `withTransaction` callback | Callback may re-execute | Use the outbox worker pattern |
| Charging credit card inside callback | Risks double-charging | External idempotency + saga |
| Retrying every exception | Loops forever on permanent errors | Inspect error labels / typed policies |
| Assuming commit error = definite abort | Commit outcome may be unknown | Retry commit or reconcile state |
| Retrying whole body on `UnknownTransactionCommitResult` | Risk of duplicate business actions | Retry commit on same transaction |
| Omitting `requestId` | HTTP retries create duplicate orders | Idempotency key + unique index |
| Generating fresh UUIDs per transaction attempt | Non-deterministic IDs across retries | Precompute deterministic IDs outside callback |
| Skipping `modifiedCount` checks | Treats out-of-stock as success | Conditional update + invariant validation |
| Holding transactions open for minutes waiting on payment | Lock contention and lifetime aborts | Move external calls outside transactions |
| Wrapping every operation in multi-doc txn | Unnecessary overhead | Prefer single-document atomicity |
| Using standalone `mongod` for transaction lab | Unsupported | Single-node replica set |
| Secondary read preference inside write txn | Violates primary routing requirement | Use `ReadPreference.primary()` |
| Per-operation write concern inside txn | Misaligned with transaction semantics | Set `WriteConcern` on `TransactionOptions` |
| Expecting `retryWrites=true` to retry `updateMany` | Not eligible | Application-level idempotent retry if needed |
| Expecting `retryReads=true` to retry `getMore` | Outside standard mechanism | Handle cursor errors and checkpointing |
| Logging raw queries containing PII | Data leak | Safe metadata logging |
| Counting command events as committed transactions | Retries inflate attempt counts | Measure commits and business outcomes |
| Never testing failover | Unknown outcomes only surface in outages | Replica set failover integration tests |
| Stacking unbudgeted retry layers | Retry storms / amplification | Bounded end-to-end retry budget |
| Retrying `DuplicateKey` like a network timeout | Misreads business semantics | Look up existing idempotency record |
| Claiming transactions guarantee exactly-once Kafka publish | Scope stops at MongoDB | Outbox + consumer deduplication |
| Ignoring cross-shard transaction overhead | Tail latency spikes | Co-locate data model & monitor latency |

---

## 37. Production Transaction Incident Runbook

### Step 1 — Determine Scope

- Which endpoint or service?
- Which MongoDB cluster, replica set, or shards?
- When did it start?
- Which driver and server versions?
- Any recent deployments or primary stepdowns?
- Attempts/retries per request?

### Step 2 — Classify Symptoms

- Body error before commit?
- Unknown commit result?
- Business/write conflict?
- Unauthorized or validation failure?
- Network timeout?
- Server selection timeout?
- Transaction lifetime exceeded?

### Step 3 — Inspect Error Labels

- `TransientTransactionError`?
- `UnknownTransactionCommitResult`?
- `RetryableWriteError` for eligible single writes?
- Error code and category?

Do not rely solely on `grep` against message substrings.

### Step 4 — Review Consistency Options

- Read concern.
- Write concern (especially `majority`).
- Primary read preference.
- `TransactionOptions`.
- Client timeout and retry settings.
- Session lifecycle management.

### Step 5 — Inspect Data and Business State

- Order record by `requestId`.
- Inventory balance.
- Outbox event record.
- Payment provider state if applicable.
- Duplicate key logs/records.

Never manually mutate records before verifying committed vs. unknown state.

### Step 6 — Check Server Health

- Primary availability.
- Elections/stepdowns.
- Replication lag.
- CPU, disk I/O, and cache health.
- Write conflict metrics.
- Transaction lifetimes and timeouts.
- Shard targeting and cross-shard coordination overhead.

### Step 7 — Mitigation

- Reduce contention/hotspots.
- Tune queries and indexes.
- Shorten transactions.
- Adjust backoff and retry budgets.
- Tune connection pools and timeouts.
- Offload external side effects to outbox workers.
- Implement idempotency and reconciliation.

### Step 8 — Verification

- No negative inventory balances.
- No duplicate orders per `requestId`.
- Retry rate back to baseline.
- Unknown commit outcomes reconciled.
- Outbox backlog draining normally.
- p95/p99 latency recovered.
- Zero session/transaction resource leaks.

### Step 9 — Postmortem

Document root causes and design constraints—never just "MongoDB retries automatically". Sanitize logs so credentials, PII, and raw payloads are never exposed.

---

## 38. Code Review Checklist for ClientSession and Transactions

### 38.1. Session Lifecycle

- [ ] `MongoClient` reused across the app, not created per request.
- [ ] Sessions created from the matching client.
- [ ] Sessions never shared across threads.
- [ ] Protected by `try-with-resources` or `finally` close.
- [ ] Every DB operation inside a transaction receives `session`.
- [ ] No parallel operations executed on the same session.

### 38.2. Transaction Correctness

- [ ] Server topology supports transactions.
- [ ] Read preference set to primary.
- [ ] `ReadConcern` and `WriteConcern` chosen intentionally.
- [ ] Conditional updates enforce business invariants.
- [ ] All writes requiring atomicity share the same session/transaction.
- [ ] Zero external API calls inside callbacks.
- [ ] Transactions never held open across user interaction.
- [ ] Transaction bodies are short and backed by indexes.
- [ ] Business errors handled distinctly from transient errors.

### 38.3. Retry Semantics

- [ ] Clear understanding of when `retryWrites`/`retryReads` apply.
- [ ] Not treating `updateMany`/`deleteMany` as retryable single writes.
- [ ] Not treating `getMore` as a retryable read.
- [ ] Using `withTransaction` or label-aware manual retry logic.
- [ ] Distinguishing `TransientTransactionError` from `UnknownTransactionCommitResult`.
- [ ] Not retrying the full callback on unknown commit outcomes.
- [ ] No unbounded retry loops.
- [ ] Idempotency keys implemented for HTTP/API retries.
- [ ] Not generating fresh IDs inside each callback attempt.
- [ ] Reconciliation implemented for unknown outcomes.
- [ ] Backoff and deadlines applied to app-level retries.

### 38.4. Security and Observability

- [ ] Zero hardcoded passwords.
- [ ] No logging of raw commands or session secrets.
- [ ] Metrics separate attempts, commits, and business outcomes.
- [ ] Monitoring tracks write conflicts, retries, and unknown commits.
- [ ] Integration tests cover replica set failover.
- [ ] No PII inside metric labels.
- [ ] Outbox consumers implement deduplication.

---

## 39. Questions and Exercises

### Exercise A — Identifying Real Transaction Membership

Given:

~~~java
try (ClientSession session = client.startSession()) {
    session.startTransaction();
    inventory.updateOne(session, filter, update);
    orders.insertOne(order);
    session.commitTransaction();
}
~~~

Questions:

1. Which operation participates in the transaction?
2. If commit fails, could `orders.insertOne(order)` already be persisted?
3. How do you fix it so both become atomic?

### Exercise B — Retry Labels

Explain the differences among:

- `TransientTransactionError`.
- `UnknownTransactionCommitResult`.
- `RetryableWriteError`.

Which justifies retrying the entire transaction? Which calls for retrying commit?

### Exercise C — Outbox

Design a transaction:

1. Deduct inventory.
2. Create order.
3. Insert outbox event.

After commit, a worker publishes the event. If it publishes successfully and crashes before marking it processed, what must the consumer handle?

### Exercise D — Retryable Operations

Classify:

- `insertOne`.
- `updateOne`.
- `updateMany`.
- `deleteOne`.
- `deleteMany`.
- `find`.
- `aggregate` with `$out`.
- `getMore`.
- `findOneAndUpdate`.

Explain eligibility criteria and unsupported cases.

### Exercise E — Causal Consistency

A user updates their profile and immediately reads from a secondary.

1. When does a causally consistent session help?
2. What read/write concern conditions apply?
3. Why doesn't a causal session turn two writes into an atomic transaction?

### Exercise F — Transactions and Concurrent Inventory

Two requests order a SKU with `available = 1`, each with `quantity = 1`.

1. Write the conditional update.
2. Predict concurrent behavior.
3. Explain `WriteConflict`.
4. Why might one side retry and then fail as out of stock?
5. Verify stock never drops below zero.

### Exercise G — Unknown Commit Outcome

The client calls commit; the server may have committed, yet the response drops.

1. Should you abort and report "order failed"?
2. Should you immediately re-run the callback?
3. How does the driver retry commit?
4. When retries fail to resolve it, how do you reconcile via `requestId`?
5. What HTTP response works when status remains unresolved?

### Exercise H — Java Session Concurrency

A singleton holds one `ClientSession` shared across 20 request threads.

1. What is wrong?
2. Is `ClientSession` thread-safe?
3. Redesign the `MongoClient` and session lifecycles.
4. During an active transaction, may you run operations in parallel on that session?

### Exercise I — Performance Measurement

A service jumps from 10 ms to 250 ms after replacing a single-document update with a 3-collection transaction.

1. Is the multi-document transaction genuinely needed?
2. Do writes span multiple shards?
3. Are write conflicts or hot documents occurring?
4. How long does the transaction stay open?
5. Are outbox external API calls hiding inside the callback?
6. How would you measure attempt counts and commit latency?

### Exercise J — Failover Testing

Design a test plan for a three-node replica set covering:

- Primary stepdown before transaction start.
- Primary stepdown mid-transaction.
- Dropped response around commit.
- HTTP client retry after commit.
- Duplicate idempotency keys.
- Repeated outbox deliveries.

Specify expected business invariants, not merely expected exceptions.

### Exercise K — Spring `@Transactional`

A Spring service uses `@Transactional`, while raw `MongoCollection` calls run through a separate client instance.

1. Are those operations guaranteed to join the transaction?
2. How must `MongoTransactionManager` and session binding be configured?
3. Should a payment HTTP call live inside the annotated method?
4. How do framework retries and driver retries interact?

### Exercise L — Architecture Proposal

Given the workflow:

~~~text
Create order
Reserve inventory
Charge card
Send email
Publish Kafka event
~~~

Separate cleanly into:

- MongoDB atomic transaction scope.
- External payment idempotency.
- Outbox.
- Saga/compensation.
- Recovery/reconciliation.
- Monitoring.

Do not claim one MongoDB atomic transaction covers the entire workflow.

---

## 40. Official Reference Documentation

Always consult documentation matching your exact MongoDB Server and MongoDB Java Sync Driver versions, since APIs, retry behavior, error labels, and topology limits evolve across releases.

- [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/)
- [MongoDB Java Sync Driver — Client-Side Sessions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/#client-side-sessions)
- [MongoDB Java Sync Driver — Configure Connection Options](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/)
- [MongoDB Java Sync Driver — Retryable Reads and Writes](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/retryable-reads-and-writes/)
- [MongoDB Java Sync Driver — Monitoring](https://www.mongodb.com/docs/drivers/java/sync/current/monitoring-and-logging/monitoring/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Manual — Transactions Production Considerations](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/)
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/)
- [MongoDB Manual — Retryable Reads](https://www.mongodb.com/docs/manual/core/retryable-reads/)
- [MongoDB Manual — Causal Consistency and Read/Write Concerns](https://www.mongodb.com/docs/manual/core/causal-consistency-read-write-concerns/)
- [MongoDB Manual — Read Concern snapshot](https://www.mongodb.com/docs/manual/reference/read-concern-snapshot/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Manual — Transaction Error Handling](https://www.mongodb.com/docs/manual/core/transactions/#transactions-and-error-handling)
- [MongoDB Specifications — Transactions](https://github.com/mongodb/specifications/blob/master/source/transactions/transactions.md)
- [MongoDB Specifications — Retryable Writes](https://github.com/mongodb/specifications/blob/master/source/retryable-writes/retryable-writes.md)
- [MongoDB Specifications — Retryable Reads](https://github.com/mongodb/specifications/blob/master/source/retryable-reads/retryable-reads.md)

> **Practice note:** Cross-check APIs with your active driver dependency. Simplified examples demonstrate overall control flow and should be integrated with authentication, validation, logging, and exception mapping before production deployment. Run write/delete exercises only inside an isolated lab.

---

## 41. Summary

1. **`ClientSession` represents a logical session context**, not automatically a transaction. For multi-operation atomicity, invoke the transaction API and pass the same `session` to **every participating DB operation**.
2. **Transactions require supported topologies**, typically a replica set or sharded cluster. Standalone `mongod` does not provide multi-document transaction support.
3. **Reuse `MongoClient`; use sessions sequentially and close them cleanly**. Never share a `ClientSession` across request threads.
4. **Configure `TransactionOptions` explicitly** for read concern, write concern, and primary read preference; majority commits suit workflows requiring strong durability.
5. **`withTransaction()`** retries transaction callbacks and commits based on error labels, meaning callbacks **can execute multiple times**.
6. **`TransientTransactionError`** typically allows retrying the whole transaction; **`UnknownTransactionCommitResult`** calls for retrying commit or reconciling state rather than blindly re-running business mutations.
7. **Retryable writes and reads** apply selectively per operation. `updateMany`/`deleteMany` and `getMore` do not behave like retryable `updateOne`/`find`.
8. **Driver retries never create exactly-once business execution**. HTTP retries require idempotency keys and unique constraints; external effects rely on outbox, sagas, or provider idempotency.
9. **Keep transactions short**, avoid external calls, and monitor contention, timeouts, and size limits; never cram million-document migrations into one transaction.
10. **Observe and test failovers** by tracking attempt counts, commit outcomes, business invariants, and duplicate suppression—not just raw exception counts.

**Conclusion:** Using the MongoDB Java Driver effectively means applying **transactions when atomicity is required, sessions when causal/snapshot context is needed, retries when operations/errors qualify, and idempotency whenever business requests may replay**. Only the proper combination of all four layers preserves correctness across write conflicts, network drops, and primary failovers.
