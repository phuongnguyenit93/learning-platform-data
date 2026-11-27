# Coordinating Transactions with Event Publishing Using the Transactional Outbox in MongoDB

## Lesson Objectives

An ordering system typically must do two things after a customer clicks **Place Order**: update business data in MongoDB and publish an `OrderPlaced` event to a message broker so payment, shipping, and analytics services can continue processing. Writing directly to MongoDB and then calling the broker as two independent operations leaves a window where a network glitch or crash can result in **a saved order with no event**, or **a sent event with no saved order**. This is the **dual-write** problem.

The **transactional outbox** pattern solves this by **writing both the business change and an outbox event record inside the same MongoDB transaction**, after which a separate **relay** process reads committed records and publishes them to the broker. Because the relay may retry on failures, consumers must detect and ignore duplicate deliveries.

This lesson belongs to **Database Engine Document MongoDB → Transactions → Coordinating Transactions with Event Publishing Using the Transactional Outbox**. After this lesson, you will be able to:

1. Distinguish an atomic database transaction from publishing to an external system.
2. Identify failure points in both “database first, broker second” and “broker first, database second” sequences.
3. Design an `outboxEvents` collection, event envelope, event ID, schema version, statuses, and indexes.
4. Use sessions and transactions to commit business state + outbox atomically.
5. Understand the `PENDING → PROCESSING → PUBLISHED` lifecycle, atomic claims, leases, retry/backoff, and dead-letter/replay.
6. Explain **at-least-once publication**, duplicate risks, and consumer idempotency / the inbox pattern.
7. Use a polling relay or MongoDB change streams, understanding the limits of resume tokens and oplog retention.
8. Preserve per-aggregate ordering via version numbers, routing keys, and gap-handling policies.
9. Write `mongosh` and Java Sync Driver examples covering callback transactions and relay publication.
10. Configure write concern, monitor backlog age, handle unknown commit outcomes, and test crash windows.
11. Choose safe outbox retention/TTL policies and data reconciliation mechanisms.
12. Distinguish outbox from event sourcing, CDC, distributed transactions, and sagas.

> **Most important takeaway:** A MongoDB transaction only makes **business write + outbox write** atomic. It **does not** bring Kafka, RabbitMQ, or HTTP into the same transaction. Relays typically publish with **at-least-once** delivery, so every critical consumer must be **idempotent**.

---

## 1. The Dual-Write Problem: Why Committing and Then Publishing Is Not Enough

### 1.1. Order Placement Business Flow

Suppose an API receives:

~~~json
{
  "requestId": "REQ-1001",
  "orderId": "ORD-1001",
  "customerId": "CUS-101",
  "productId": "SKU-BOOK-01",
  "quantity": 2
}
~~~

The application must:

- Deduct 2 units from `inventory`.
- Insert an `orders` document.
- Publish `OrderPlaced` so Payment Service or Shipping Service knows about the order.

If all succeed, the system is consistent; if any part fails, the workflow risks getting stuck.

### 1.2. Database First, Broker Second

~~~text
API                MongoDB                  Broker
 |                    |                       |
 |--- update stock -->|                       |
 |--- create order -->|                       |
 |<--- commit OK -----|                       |
 |                    |                       |
 |       CRASH        |                       |
 X                    |                       |
 |         OrderPlaced never published        |
~~~

MongoDB has the order and reduced stock, yet downstream services have no idea. Even though updating stock and creating the order ran inside one MongoDB transaction, sending to the broker sat **outside** that transaction.

### 1.3. Broker First, Database Second

~~~text
API                    Broker               MongoDB
 |                        |                     |
 |-- OrderPlaced -------->|                     |
 |<-- broker ACK ---------|                     |
 |                        |                     |
 |--- create order/update stock -------------->|
 |                        |              ABORT / error
 X                        |                     |
~~~

Consumers might start shipping even though the order was never created. Calling the broker first does not make dual-writes safe either.

### 1.4. Cannot Be Fixed by Reordering

| Sequence | Failure Window | Consequence |
|---|---|---|
| MongoDB commit → broker publish | Crash after commit, before publish | **Lost event** |
| Broker publish → MongoDB commit | Abort after publish | **Phantom event with no matching business state** |
| Broker publish → mark sent | Broker ACK lost or relay crashes | **Possible redelivery** |
| Publish to broker inside transaction callback | Callback retries before commit | **Possible multiple publications** |
| Wait on broker inside transaction | Slow broker, network partition | **Long-running transaction** and still no distributed atomicity |

A MongoDB transaction cannot roll back a message already delivered to a broker. Conversely, a broker transaction cannot roll back a MongoDB order.

### 1.5. Why Is This Failure Mode Serious?

In distributed systems, processes can crash at **any line of code**, and networks can drop between server completion and client receipt. Correctness guarantees must never rely on assuming two sequential operations “almost always succeed”.

---

## 2. Transactional Outbox Architecture

### 2.1. Processing Flow

~~~text
                       Order Service
                             |
                     startTransaction()
                             |
       +---------------------+--------------------+
       |                     |                    |
       v                     v                    v
 update inventory       insert order       insert outbox event
       |                     |                    |
       +---------------------+--------------------+
                             |
                    commitTransaction()
                             |
                    MongoDB transaction
                     /              \
                    /                \
                 COMMIT             ABORT
                    |                  |
                    v                  v
         Order and event          No business write
         persist together         or outbox committed
                    |
                    v
              Outbox relay
                    |
               publish message
                    |
               broker ACK
                    |
              mark PUBLISHED
                    |
                    v
              Message broker
                    |
                    v
            Idempotent consumer
~~~

### 2.2. Four Key Components

| Component | Responsibility | Guarantee or Duty |
|---|---|---|
| Business service | Writes business documents | Business preconditions, concurrency, idempotency |
| MongoDB transaction | Writes business state and outbox using the same session | **Atomic commit/abort** inside MongoDB |
| Relay | Reads outbox, publishes, retries, marks status | Eventual publication given infrastructure and retention |
| Consumer | Receives events, updates its own state | Deduplicates and applies business effects safely |

### 2.3. Two Distinct Success Milestones

Milestone 1 — **Business commit**: order and outbox are confirmed committed by MongoDB per write concern.

Milestone 2 — **Broker publish**: the relay has sent the event and received acknowledgment per the broker's durability policy.

At Milestone 1, you cannot claim the broker has the event. At Milestone 2, you still cannot claim consumers have finished processing it.

### 2.4. Why Must the Event Be a Committed Document?

If the API crashes right after commit, the outbox event remains persisted. Upon restart, the relay finds and publishes it. The event is no longer merely an in-memory object inside a dead process.

### 2.5. Exact Atomic Boundary

In MongoDB:

~~~text
transaction:
  update inventory
  insert order
  insert outbox
commit
~~~

All three writes form one atomic group. Post-commit, the call:

~~~text
broker.publish(...)
~~~

is **not** inside that transaction. That is both the boundary and the reason this pattern is simpler than distributed two-phase commit.

---

## 3. What Does an Outbox Guarantee, and What Does It Not?

### 3.1. Conditional Guarantees

Provided the transaction commits and the outbox persists under proper configuration:

- No committed order (from bug-free code) silently lacks a corresponding event.
- No outbox event commits on its own when the transaction's business writes abort.
- The relay can retry publishing after process restarts.
- A broker outage does not force order-writing APIs to fail immediately; the backlog queues safely in the outbox.

Conditions: no TTL deletes `PENDING` records, the relay recovers, MongoDB has proper durability/backups, no bugs skip events, and operations handle prolonged failures.

### 3.2. Never Make False Promises

An outbox **does not automatically** guarantee:

- Immediate broker receipt at the exact moment of API commit.
- Publishing each message strictly once.
- Every consumer processing each message strictly once.
- Events always arriving in strict version order when multiple relay workers run concurrently.
- External APIs, emails, or payment gateways rolling back alongside MongoDB.
- Zero data loss if the entire infrastructure and backups are destroyed.
- No need for monitoring or operational replay.

### 3.3. Eventual Consistency

For a brief window:

~~~text
Orders:       ORD-1001 is PLACED
Outbox:       OrderPlaced is PENDING
Broker:       no message yet
Shipping:     no shipment created yet
~~~

This state **is acceptable** when the system has an eventual publication SLA. It is not an atomicity bug; it is an expected phase of asynchronous processing.

---

## 4. MongoDB Prerequisites for This Pattern

### 4.1. Transactions Require the Right Deployment

Multi-document transactions are supported on **replica sets** starting in MongoDB 4.0 and **sharded clusters** starting in MongoDB 4.2, with compatible storage engines and configurations. A standalone `mongod` does not support the same multi-document transaction API.

For single-machine learning, you can use a single-node replica set. However, a single-node replica set lacks high availability if that machine fails.

### 4.2. Sessions Are Mandatory

All operations requiring atomicity must share **the same `ClientSession`**:

~~~java
inventory.updateOne(session, filter, update);
orders.insertOne(session, orderDoc);
outbox.insertOne(session, eventDoc);
~~~

If you forget `session` on the outbox insert:

~~~java
outbox.insertOne(eventDoc);
~~~

that operation runs outside the transaction, breaking the “order + outbox commit or abort together” invariant.

### 4.3. Transaction Options

An illustrative configuration:

~~~javascript
session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" },
  readPreference: "primary"
});
~~~

- `readConcern:"snapshot"`: snapshot isolation per MongoDB semantics.
- `writeConcern:"majority"`: commit confirmation at majority level.
- `readPreference:"primary"`: required for write transactions.

Verify default concerns and journaling for your MongoDB version and deployment. `w:"majority"` does not mean all secondaries have applied writes, nor does it replace backups.

### 4.4. Never Wait on the Broker Inside a MongoDB Transaction

A long transaction pins resources and snapshots, increasing write conflicts, cache pressure, and timeouts. MongoDB enforces a transaction lifetime limit, typically defaulting to ~60 seconds in standard setups. Never hold a transaction open while waiting 30 seconds on a broker call—it still **does not become atomic with MongoDB**.

### 4.5. Idempotency Is Needed End-to-End

There are two retry classes:

- Driver transaction/commit retries.
- Client/API gateway request retries after timeouts.

A correct transaction alone does not prevent **an API replay from running as a brand-new business action**. Use stable `requestId` and `eventId` values backed by unique constraints.

---

## 5. Data Model for Orders, Inventory, and Outbox

### 5.1. Inventory

~~~javascript
{
  _id: "SKU-BOOK-01",
  title: "MongoDB Handbook",
  available: 10
}
~~~

### 5.2. Order

~~~javascript
{
  _id: "ORD-1001",
  requestId: "REQ-1001",
  customerId: "CUS-101",
  productId: "SKU-BOOK-01",
  quantity: 2,
  status: "PLACED",
  createdAt: ISODate("2026-11-14T01:00:00Z")
}
~~~

`requestId` identifies the same request across retries. If a client sends the same `requestId` with a different payload, the API should return a conflict rather than silently creating another order.

### 5.3. Outbox Event

~~~javascript
{
  _id: "EVT-ORD-1001-PLACED-v1",
  eventId: "EVT-ORD-1001-PLACED-v1",

  eventType: "OrderPlaced",
  schemaVersion: 1,

  aggregateType: "Order",
  aggregateId: "ORD-1001",
  aggregateVersion: 1,

  topic: "orders.events",
  partitionKey: "ORD-1001",

  occurredAt: ISODate("2026-11-14T01:00:00Z"),
  createdAt: ISODate("2026-11-14T01:00:00Z"),

  payload: {
    orderId: "ORD-1001",
    customerId: "CUS-101",
    productId: "SKU-BOOK-01",
    quantity: 2,
    status: "PLACED"
  },

  status: "PENDING",
  attempts: 0,
  nextAttemptAt: ISODate("2026-11-14T01:00:00Z")
}
~~~

### 5.4. Metadata Explanation

| Field | Meaning |
|---|---|
| `_id` | Outbox document identity |
| `eventId` | Stable ID for publication/processing deduplication |
| `eventType` | Domain event name, e.g., `OrderPlaced` |
| `schemaVersion` | Payload contract version |
| `aggregateType` | Entity type, e.g., `Order` |
| `aggregateId` | Business entity ID |
| `aggregateVersion` | Logical sequence of changes on the same aggregate |
| `topic` | Logical destination topic |
| `partitionKey` | Routing key for broker partitioning if applicable |
| `occurredAt` | Timestamp when the business event occurred |
| `createdAt` | Timestamp when the event was stored |
| `payload` | Event body at commit time |
| `status` | Relay status |
| `attempts` | Number of claim/publish attempts |
| `nextAttemptAt` | Next retry schedule timestamp |
| `claimToken` | Unique ownership ID for a single claim |
| `leaseUntil` | Timestamp when the claim lease expires |
| `publishedAt` | Timestamp when broker ACKed and relay marked success |

### 5.5. Events Should Capture Immutable Business Facts

If the relay stored only `orderId` and read the current order later at publish time, the order might already have transitioned from `PLACED` to `PAID`. The `OrderPlaced` event would then carry an inaccurate point-in-time state.

Good designs capture an immutable payload inside the event-creating transaction, or explicitly specify a notification-plus-lookup event contract.

### 5.6. Minimize Sensitive Data

Never copy an entire order document containing PII, access tokens, or sensitive fields onto the broker. Select fields intentionally and apply schemas, authorization, TLS, and retention policies.

---

## 6. Preparing the Database and Indexes

Run these commands only on a **lab replica set**.

~~~javascript
use outbox_lab

db.inventory.insertOne({
  _id: "SKU-BOOK-01",
  title: "MongoDB Handbook",
  available: 10
});

db.orders.createIndex(
  { requestId: 1 },
  {
    unique: true,
    name: "uk_orders_requestId"
  }
);

db.outboxEvents.createIndex(
  { eventId: 1 },
  {
    unique: true,
    name: "uk_outbox_eventId"
  }
);

db.outboxEvents.createIndex(
  { status: 1, nextAttemptAt: 1, createdAt: 1 },
  { name: "idx_outbox_pending_due" }
);

db.outboxEvents.createIndex(
  { status: 1, leaseUntil: 1, createdAt: 1 },
  { name: "idx_outbox_expired_leases" }
);
~~~

Notes:

- Unique `requestId` prevents duplicate orders on client retries.
- Stable `eventId` enables consumer deduplication.
- You can use `_id` as `eventId` to save one index; decide per API design.
- The relay queries due `PENDING` events and expired leases, so indexes must match actual query patterns.
- Indexes add write overhead on the outbox; check `explain` and write amplification before adding excessive indexes.

When re-running the lab, inserting the product with the same `_id` triggers a duplicate key error. Use a fresh lab database or controlled reset—never drop production data for exercises.

---

## 7. MongoDB Transaction: Writing Business Data Together with Events

### 7.1. Complete `mongosh` Example

~~~javascript
const session = db.getMongo().startSession();

const requestId = "REQ-1001";
const orderId = "ORD-1001";
const eventId = "EVT-ORD-1001-PLACED-v1";
const productId = "SKU-BOOK-01";
const customerId = "CUS-101";
const quantity = 2;

let commitAttempted = false;

try {
  const sdb = session.getDatabase("outbox_lab");
  const inventory = sdb.getCollection("inventory");
  const orders = sdb.getCollection("orders");
  const outbox = sdb.getCollection("outboxEvents");

  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" },
    readPreference: "primary"
  });

  const stock = inventory.updateOne(
    {
      _id: productId,
      available: { $gte: quantity }
    },
    {
      $inc: { available: -quantity }
    }
  );

  if (stock.matchedCount !== 1) {
    throw new Error("OUT_OF_STOCK_OR_NOT_FOUND");
  }

  const now = new Date();

  orders.insertOne({
    _id: orderId,
    requestId: requestId,
    customerId: customerId,
    productId: productId,
    quantity: quantity,
    status: "PLACED",
    createdAt: now
  });

  outbox.insertOne({
    _id: eventId,
    eventId: eventId,
    eventType: "OrderPlaced",
    schemaVersion: 1,
    aggregateType: "Order",
    aggregateId: orderId,
    aggregateVersion: 1,
    topic: "orders.events",
    partitionKey: orderId,
    occurredAt: now,
    createdAt: now,
    payload: {
      orderId: orderId,
      customerId: customerId,
      productId: productId,
      quantity: quantity,
      status: "PLACED"
    },
    status: "PENDING",
    attempts: 0,
    nextAttemptAt: now
  });

  commitAttempted = true;
  session.commitTransaction();

  print("Commit confirmed; event is awaiting relay");
} catch (error) {
  if (!commitAttempted) {
    try {
      session.abortTransaction();
    } catch (abortError) {
      print("Abort also errored: investigate");
    }
  } else {
    print("Commit outcome uncertain; do not auto-retry body");
  }

  throw error;
} finally {
  session.endSession();
}
~~~

**Important:** This code illustrates the atomic boundary and proper session handle usage. It **does not implement full commit retries** on `UnknownTransactionCommitResult`. Production code should use the official driver's transaction callback or proper error-label commit retry handling; never assume a network error at commit means the transaction aborted.

### 7.2. Why Is Stock Deduction Conditional?

~~~javascript
{
  _id: "SKU-BOOK-01",
  available: { $gte: 2 }
}
~~~

ensures stock decreases only if two units remain. Checking beforehand with `findOne()` and updating unconditionally introduces races under concurrency.

### 7.3. If Outbox Insert Fails

Suppose `eventId` already exists, causing a duplicate key on outbox insert. The transaction aborts, so stock is not deducted and the order is not persisted from this attempt.

### 7.4. If Commit Succeeds

After commit:

~~~javascript
db.inventory.findOne({ _id: "SKU-BOOK-01" });
db.orders.findOne({ requestId: "REQ-1001" });
db.outboxEvents.findOne({
  eventId: "EVT-ORD-1001-PLACED-v1"
});
~~~

Starting from stock 10 and running once:

| Collection | Expected State |
|---|---|
| `inventory` | `available: 8` |
| `orders` | One document `ORD-1001` |
| `outboxEvents` | One `OrderPlaced` event, `status:"PENDING"` |

**At this moment, you still cannot assert the broker received the message.**

### 7.5. If the API Retries the Same `requestId`

A new transaction will hit a duplicate key on `orderId` or `requestId`. Since all business writes belong to the same transaction, the aborted retry does not deduct stock again.

The API layer must look up the already-committed order for that `requestId`, verify the original payload matches, and return the corresponding response. Unique indexes are foundational, yet do not build the complete idempotency response on their own.

---

## 8. When to Commit and When to Abort?

### 8.1. Commit

Call `commitTransaction()` when:

- Business preconditions hold.
- All MongoDB writes requiring atomicity succeeded on the same session.
- The outbox event was written.
- No errors require stopping the operation.

### 8.2. Abort

Call `abortTransaction()` when:

- Stock is insufficient.
- The user is not authorized to place the order.
- Account or product data is invalid.
- Order or outbox insertion fails unrecoverably.
- Business logic cancels before commit.

### 8.3. Never Publish Before Commit

If an event is published immediately after inserting into the outbox yet **before** MongoDB commits, the transaction might abort while the brokered event cannot be recalled. The relay must read only **committed** records—never publish inside the transaction callback.

### 8.4. Abort Does Not Undo External Side Effects

An already-sent email or payment API call does not vanish when MongoDB aborts. Wrapping an external API inside a transaction expecting rollback is futile.

---

## 9. Relay State Machine

An outbox event needs a well-defined operational lifecycle.

~~~text
            MongoDB transaction COMMIT
                         |
                         v
                      PENDING
                         |
               Worker atomic claim
                         |
                         v
                    PROCESSING
                    /     |      \
                   /      |       \
         broker ack     error    worker crash
              |           |            |
              v           v            |
          PUBLISHED     PENDING        |
                        retry          |
                              lease expires
                                    |
                                    v
                                 reclaim
                                    |
                               PROCESSING

     If error cannot resolve automatically:
       DEAD / QUARANTINED + alert + replay plan
~~~

### 9.1. Status Meanings

| Status | Meaning |
|---|---|
| `PENDING` | Event committed, not yet confirmed by the broker |
| `PROCESSING` | Claimed by a relay instance with a lease |
| `PUBLISHED` | Broker ACKed per policy and relay marked success |
| `DEAD` | Automatic retries paused; requires operational review/replay |
| `CANCELLED` | Used only when the domain has explicit cancellation rules; never delete committed facts arbitrarily |

### 9.2. Additional Fields Upon Claim

~~~javascript
{
  status: "PROCESSING",
  attempts: 3,
  claimToken: "worker-claim-123",
  leaseUntil: ISODate("2026-11-14T02:00:30Z"),
  nextAttemptAt: ISODate("2026-11-14T02:00:00Z")
}
~~~

- `claimToken` uniquely identifies a single claim.
- `leaseUntil` enables recovery if the worker crashes.
- `attempts` tracks total claim/publish attempts.
- `nextAttemptAt` schedules retry backoff.

### 9.3. A Lease Is Not an Exactly-Once Lock

Worker A holds a 30-second lease, yet publishing stalls for 35 seconds. Worker B reclaims and sends the same event. Worker A may still receive a broker ACK afterward. Proper claiming **does not eliminate duplicate broker messages**. Consumers must still be idempotent.

---

## 10. Polling Relay: Atomic Claim with `findOneAndUpdate`

### 10.1. Why Must Claims Be Atomic?

Wrong:

~~~javascript
const event = db.outboxEvents.findOne({
  status: "PENDING"
});

// Two workers can read the same event before updating.
db.outboxEvents.updateOne(
  { _id: event._id },
  { $set: { status: "PROCESSING" } }
);
~~~

Both Worker A and Worker B can read the event and both publish it.

### 10.2. Atomic Claim

~~~javascript
const now = new Date();
const leaseDurationMs = 30000;
const claimToken = new ObjectId().toHexString();

const claimed = db.outboxEvents.findOneAndUpdate(
  {
    nextAttemptAt: { $lte: now },
    $or: [
      { status: "PENDING" },
      {
        status: "PROCESSING",
        leaseUntil: { $lte: now }
      }
    ]
  },
  {
    $set: {
      status: "PROCESSING",
      claimToken: claimToken,
      leaseUntil: new Date(
        now.getTime() + leaseDurationMs
      )
    },
    $inc: { attempts: 1 }
  },
  {
    sort: {
      createdAt: 1,
      _id: 1
    },
    returnDocument: "after"
  }
);

printjson(claimed);
~~~

`findOneAndUpdate` atomically selects and modifies **one document** matching the filter. If no eligible event exists, it returns `null`.

### 10.3. Query Targets Due `PENDING` and Reclaims

The filter selects:

- `PENDING` events with `nextAttemptAt <= now`.
- `PROCESSING` events with `leaseUntil <= now` due for retry.

With multiple workers, MongoDB acts as the shared claim coordinator without requiring an in-memory mutex inside a single process.

### 10.4. Clocks and Leases

Workers can experience clock skew. Size lease duration against p99 broker publish latency, timeouts, GC pauses, and network conditions; synchronize system clocks or use a consistent clock strategy. If publishing can outlast the lease, renew the lease conditionally using `claimToken` and current status.

### 10.5. Atomic Claim Does Not Guarantee Strict Event Ordering

Two workers can claim two consecutive events for the same aggregate, and one worker can finish publishing before the other. Sorting by `createdAt` in `findOneAndUpdate` only picks the candidate at claim time; it does not guarantee broker arrival order under concurrent workers.

If strict per-aggregate ordering is required, add dedicated ordering controls.

---

## 11. Publish, Broker ACK, and Marking `PUBLISHED`

### 11.1. Publishing Must Await Real Acknowledgment

At the publisher interface level:

~~~text
publish(
  topic = event.topic,
  key = event.partitionKey,
  headers = { eventId, eventType, schemaVersion },
  body = event.payload
)

Await broker acknowledgement.
Only after ACK per durability policy mark PUBLISHED.
~~~

If the producer API merely buffers in RAM and returns, marking `PUBLISHED` immediately risks losing messages when the producer process crashes.

### 11.2. Conditional Update After ACK

~~~javascript
const updated = db.outboxEvents.updateOne(
  {
    _id: claimed._id,
    status: "PROCESSING",
    claimToken: claimed.claimToken
  },
  {
    $set: {
      status: "PUBLISHED",
      publishedAt: new Date()
    },
    $unset: {
      claimToken: "",
      leaseUntil: ""
    }
  }
);

printjson(updated);
~~~

If `modifiedCount` = 0, never overwrite unconditionally. The lease may have expired and another worker reclaimed it. The broker may have already received the event, so consumers must deduplicate.

### 11.3. Why Not Mark Before Publishing?

~~~text
Mark PUBLISHED
  |
  v
Process crashes
  |
  v
Broker does not have event
  |
  v
Relay skips because already PUBLISHED
~~~

That loses the event. **Publish → ACK → mark** is chosen to guarantee at-least-once delivery even though duplicates can occur.

### 11.4. When Broker ACK Is Lost

A producer timeout does not prove the broker failed to persist the message. When the relay retries, the message can arrive twice. Keep the exact same `eventId` across all attempts.

---

## 12. Retries, Backoff, and `DEAD` Events

### 12.1. When Publishing Fails

The relay should:

- Classify the error (network timeout, permissions, missing topic, invalid schema...).
- Compute retry delay.
- Reset to `PENDING` with an updated `nextAttemptAt` if it still holds the claim.
- Emit metrics and sanitized error codes free of sensitive details.
- Move to `DEAD` / quarantine when manual intervention is needed.

~~~javascript
const retryDelayMs = 5000;

db.outboxEvents.updateOne(
  {
    _id: claimed._id,
    status: "PROCESSING",
    claimToken: claimed.claimToken
  },
  {
    $set: {
      status: "PENDING",
      nextAttemptAt: new Date(
        Date.now() + retryDelayMs
      ),
      lastErrorCode: "BROKER_TIMEOUT"
    },
    $unset: {
      claimToken: "",
      leaseUntil: ""
    }
  }
);
~~~

### 12.2. Exponential Backoff with Jitter

An illustrative formula:

\[
delay(n)=\min(maxDelay,\ baseDelay \times 2^{n-1})+jitter
\]

For example: 1s, 2s, 4s, 8s... capped at `maxDelay`, adding jitter to prevent retry storms.

### 12.3. Never Infinitely Retry a Schema-Invalid Event

If the broker rejects an incompatible payload, rapid retries will never fix the bug. Mark it `DEAD` or `QUARANTINED` with an alert, fix the schema or destination, and replay in a controlled manner.

**`DEAD` does not mean successfully published.** It represents an unfulfilled delivery obligation.

### 12.4. Retries Can Deliver Older Events Late

If event version 1 retries for a while, version 2 might publish earlier when multiple unblocked workers run. Consumers must handle ordering or the relay must enforce per-aggregate sequencing.

---

## 13. Failure Matrix You Must Understand

| Failure Point | MongoDB Business State | Outbox | Broker | Recovery |
|---|---|---|---|---|
| Error before commit | Not committed | Not committed | Not sent | Abort; no phantom event created |
| Commit succeeds then API crashes | Present | `PENDING` | Uncertain | Relay picks up outbox after restart |
| Claimed then worker dies before publish | Present | `PROCESSING` | Uncertain | Lease expires; another worker reclaims |
| Broker ACKs then crash before mark | Present | `PROCESSING`/`PENDING` | **Likely received** | Republished; consumer deduplicates |
| Marked `PUBLISHED` then worker dies | Present | `PUBLISHED` | ACKed | Relay does not need to resend |
| Prolonged broker outage | Present | `PENDING` backlog | Unavailable | Retries, alerts, outbox preserved |
| Consumer commits local DB then broker ACK lost | Present | `PUBLISHED` | Broker redelivers | Inbox/dedupe prevents duplicate side effects |

### 13.1. Why Does an Outbox Increase Durability?

Once committed, the intent to publish lives as a durable database document, independent of the API process staying alive.

### 13.2. Why Do Duplicates Still Happen?

Publishing to the broker and marking in MongoDB are **two non-atomic operations across separate systems**. A crash between them causes redelivery. This is not a bug you can eliminate with a few lines of `try`/`catch`.

### 13.3. The Core Property Is At-Least-Once

A properly operated outbox relay achieves eventual at-least-once publication. Effectively-once business effects require consumer idempotency and clear boundary guarantees.

---

## 14. Consumer Idempotency and the Inbox Pattern

### 14.1. One Event Can Arrive Multiple Times

~~~json
{
  "eventId": "EVT-ORD-1001-PLACED-v1",
  "eventType": "OrderPlaced",
  "aggregateId": "ORD-1001",
  "payload": {
    "orderId": "ORD-1001",
    "productId": "SKU-BOOK-01",
    "quantity": 2
  }
}
~~~

Even if the broker delivers two copies, Shipping Service should create **one shipment** for the order when business rules dictate one.

### 14.2. Inbox Record

~~~javascript
{
  _id: "ShippingService:EVT-ORD-1001-PLACED-v1",
  consumer: "ShippingService",
  eventId: "EVT-ORD-1001-PLACED-v1",
  processedAt: ISODate("2026-11-14T01:05:00Z")
}
~~~

`_id` or a unique index on `(consumer, eventId)` prevents the same consumer from recording an event twice.

### 14.3. Inbox Marker Must Share a Transaction with the Business Effect

Consumer processing:

~~~text
Local MongoDB transaction:
  insert inbox eventId
  create shipment
commit
  |
  v
ack broker message
~~~

If the transaction aborts, neither inbox nor shipment is written. If the transaction commits yet the broker ACK is lost, the message redelivers, the consumer finds `eventId` already in the inbox, and skips repeating the business effect.

### 14.4. `mongosh` Consumer Demo

~~~javascript
const session = db.getMongo().startSession();
let commitAttempted = false;

try {
  const sdb = session.getDatabase("shipping_lab");
  const inbox = sdb.getCollection("processedEvents");
  const shipments = sdb.getCollection("shipments");

  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" },
    readPreference: "primary"
  });

  inbox.insertOne({
    _id: "ShippingService:EVT-ORD-1001-PLACED-v1",
    consumer: "ShippingService",
    eventId: "EVT-ORD-1001-PLACED-v1",
    processedAt: new Date()
  });

  shipments.insertOne({
    _id: "SHIP-ORD-1001",
    orderId: "ORD-1001",
    status: "PENDING"
  });

  commitAttempted = true;
  session.commitTransaction();
} catch (error) {
  if (!commitAttempted) {
    try { session.abortTransaction(); } catch (ignored) {}
  }
  throw error;
} finally {
  session.endSession();
}
~~~

This is an **atomic inbox + shipment demo**, not a complete broker callback. Production code must distinguish already-processed duplicates, transient errors, and unknown commits, and **ACK the broker only after confirming local commit** or reconciling prior completion.

### 14.5. What If the Consumer Must Call an HTTP API?

An inbox transaction cannot roll back an external API. Use an idempotency key on the downstream service, a secondary outbox, a saga/compensation, or reconciliation. Never claim “the inbox guarantees exactly-once for every email”.

---

## 15. At-Least-Once, Exactly-Once, and Business Effects

| Level | Meaning | Notes |
|---|---|---|
| At-most-once | Zero or one delivery; losses possible | Marking before publishing opens a loss window |
| At-least-once | Retried until ACK/recovery per policy | Duplicates possible |
| Broker-internal exactly-once | Guaranteed within specified protocol/features | Does not automatically span MongoDB |
| Effectively-once business effect | Despite duplicate messages, business effect applies once | Deduplication + atomic local state / idempotent side effects |

### 15.1. Why Can't a Relay Prove Exactly-Once?

If the relay publishes successfully and dies before marking, recovery republishes the event. Across distinct systems, you cannot atomically commit to the broker and update outbox status using solely a MongoDB transaction.

### 15.2. Broker Exactly-Once Does Not Span the Database

Kafka and certain brokers offer transaction/exactly-once features within supported broker/stream scopes. Those features do not merge a MongoDB business commit and a broker publish into one joint distributed transaction.

### 15.3. Design Rules

- Keep `eventId` stable.
- Let the publisher retry.
- Make consumers idempotent.
- Commit local business writes + inbox markers atomically where possible.
- Give external side effects idempotency or compensation too.
- Track metrics for duplicate detections and reconcile outcomes.

---

## 16. Preserving Per-Aggregate Ordering

### 16.1. Why Does Event Order Matter?

For one order:

~~~text
OrderPlaced    version 1
OrderPaid      version 2
OrderShipped   version 3
~~~

If a consumer receives `OrderShipped` before `OrderPlaced`, logic may fail or infer invalid state.

### 16.2. Timestamps Are Not Enough

Two events can share the same timestamp, producer clocks drift, and network delays reorder arrivals relative to business commit order. Use **`aggregateVersion`** or sequences assigned under concurrency control.

### 16.3. Version Must Bind to Business State

Update the order version atomically alongside the event write so you never emit a v2 event while business state stays at v1. Use optimistic concurrency filters on `aggregateVersion` when appropriate:

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-1001",
    version: 1
  },
  {
    $set: { status: "PAID" },
    $inc: { version: 1 }
  }
);
~~~

This snippet shows only the conditional update; in the outbox pattern, it must execute **in the same transaction** as inserting the `OrderPaid` version 2 event.

### 16.4. Partition Keys

On brokers supporting ordered partitions, keying by `aggregateId` routes all events for an order to the same partition. However, if multiple publishers send v2 before v1, the broker will not re-sort them by version.

### 16.5. Strict Ordering Requires Extra Rules

- Serialize publication per aggregate or route an aggregate to a single relay lane.
- Do not publish version N+1 before version N completes per policy.
- Guard concurrent state via atomic claims/ownership.
- Have consumers store `lastAppliedVersion`.
- Detect duplicates (N already applied) and gaps (receiving N+2 before N+1).
- Reconcile when gaps persist or a predecessor event turns `DEAD`.

Sorting candidates by `createdAt` in polling queries **is not enough** when multiple relay workers publish in parallel.

### 16.6. Not Every Event Needs Strict Total Ordering

If analytics only adds idempotent counters that converge eventually, strict sequencing overhead may be unnecessary. Specify ordering guarantees **per consumer / business invariant**.

---

## 17. Change Streams as a Relay Signal

MongoDB **change streams** watch committed changes on a supported collection, database, or deployment—typically a replica set or sharded cluster.

### 17.1. Watching Outbox Inserts

~~~javascript
const stream = db.outboxEvents.watch([
  {
    $match: {
      operationType: "insert"
    }
  }
]);

while (stream.hasNext()) {
  const change = stream.next();

  printjson({
    eventId: change.fullDocument.eventId,
    resumeToken: change._id
  });

  // Demo prints only.
  // Production must publish/ack/checkpoint safely.
}
~~~

### 17.2. Advantages

- Near-immediate notification when an outbox record commits.
- Eliminates tight polling intervals and empty queries.
- Relays discover new events quickly.
- Resume tokens allow continuing the stream within oplog history limits.

### 17.3. Resume Tokens Must Be Checkpointed Safely

Wrong:

~~~text
Change stream receives evt1
  |
  v
Save resume token as processed
  |
  v
Crash before broker publish
  |
  v
Resume from new token => evt1 may be skipped
~~~

Checkpointed tokens must reflect **completed processing progress**. With parallel processing, a newer event's token does not prove older events finished publishing.

### 17.4. Change Streams Depend on Oplog History

If a relay stays offline long enough that its resume token falls out of oplog history, resuming fails. Have a recovery plan.

### 17.5. Robust Design: Change Stream + Backlog Scan

~~~text
Source of truth: outboxEvents collection
Change stream: signal that new events arrived
Periodic scan: PENDING + expired PROCESSING leases
Broker: publish and ACK
State: mark PUBLISHED
~~~

On startup, the relay scans the outbox for events committed before the watch started. If the stream breaks, periodic polling recovery keeps things moving.

### 17.6. Watch Out for Watching Updates

If you watch all updates on the outbox, every `PENDING → PROCESSING → PUBLISHED` transition emits change events. Filter by `operationType`/fields or treat the stream purely as a wake-up signal to avoid feedback loops.

---

## 18. Polling vs. Change Streams

| Criterion | Polling | Change Streams |
|---|---|---|
| Mechanism | Periodically query `PENDING` / expired leases | Subscribe to change events |
| Setup | Straightforward | Requires stream lifecycle/resume management |
| Latency | Bounded by polling interval | Typically lower |
| Idle load | Empty queries when quiet | Much less polling chatter |
| Old event recovery | Built into outbox scan | Requires startup scan or reliable checkpoints |
| Oplog history | Indirect via MongoDB replication | Critical for resuming |
| Duplicate events | Possible | Still possible |
| Strict broker order | Not automatic | Not automatic under parallel publish |
| Needs inbox idempotency | Yes | Yes |

Choose based on SLA, complexity, and operational readiness. Change streams do not mean “exactly-once”.

---

## 19. Java Sync Driver: Transaction Creating Order and Outbox

This example uses the official driver's callback transaction API to reduce manual retry bugs. It assumes lab collections and indexes exist and the client is connected to a replica set.

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import org.bson.Document;

import java.util.Date;

public class OrderOutboxService {

    private final MongoClient client;
    private final MongoCollection<Document> inventory;
    private final MongoCollection<Document> orders;
    private final MongoCollection<Document> outbox;

    public OrderOutboxService(MongoClient client) {
        this.client = client;

        MongoDatabase db = client.getDatabase("outbox_lab");
        inventory = db.getCollection("inventory");
        orders = db.getCollection("orders");
        outbox = db.getCollection("outboxEvents");
    }

    public void placeOrder(
            String orderId,
            String requestId,
            String customerId,
            String productId,
            int quantity) {

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "quantity must be positive"
            );
        }

        String eventId = "EVT-" + orderId + "-PLACED-v1";

        TransactionOptions options =
            TransactionOptions.builder()
                .readConcern(ReadConcern.SNAPSHOT)
                .writeConcern(WriteConcern.MAJORITY)
                .readPreference(ReadPreference.primary())
                .build();

        try (ClientSession session = client.startSession()) {
            session.withTransaction(() -> {

                var stock = inventory.updateOne(
                    session,
                    Filters.and(
                        Filters.eq("_id", productId),
                        Filters.gte("available", quantity)
                    ),
                    Updates.inc("available", -quantity)
                );

                if (stock.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                        "OUT_OF_STOCK_OR_NOT_FOUND"
                    );
                }

                Date now = new Date();

                orders.insertOne(
                    session,
                    new Document("_id", orderId)
                        .append("requestId", requestId)
                        .append("customerId", customerId)
                        .append("productId", productId)
                        .append("quantity", quantity)
                        .append("status", "PLACED")
                        .append("createdAt", now)
                );

                Document payload =
                    new Document("orderId", orderId)
                        .append("customerId", customerId)
                        .append("productId", productId)
                        .append("quantity", quantity)
                        .append("status", "PLACED");

                outbox.insertOne(
                    session,
                    new Document("_id", eventId)
                        .append("eventId", eventId)
                        .append("eventType", "OrderPlaced")
                        .append("schemaVersion", 1)
                        .append("aggregateType", "Order")
                        .append("aggregateId", orderId)
                        .append("aggregateVersion", 1)
                        .append("topic", "orders.events")
                        .append("partitionKey", orderId)
                        .append("occurredAt", now)
                        .append("createdAt", now)
                        .append("payload", payload)
                        .append("status", "PENDING")
                        .append("attempts", 0)
                        .append("nextAttemptAt", now)
                );

                return null;
            }, options);
        }
    }
}
~~~

### 19.1. Why Does the Callback Fit Well?

`session.withTransaction` manages start/commit/abort and handles transient/commit-uncertainty retries per the driver contract. Because the callback can re-run, keep only **MongoDB operations and retry-safe business checks** inside.

### 19.2. Never Trigger External Side Effects Inside the Callback

Wrong:

~~~java
session.withTransaction(() -> {
    orders.insertOne(session, orderDocument);

    // Can execute multiple times if transaction callback retries.
    emailService.sendConfirmation(orderId);

    outbox.insertOne(session, eventDocument);
    return null;
});
~~~

Email sits outside the transaction, so it can fire even if the transaction aborts or the callback retries.

### 19.3. Keep `requestId` Stable

An HTTP request retried after a timeout must keep `requestId` and `orderId` unchanged. If the first attempt committed and the retry runs again, unique constraints catch the duplicate; the application layer looks up the existing order, compares payloads, and returns an idempotent response.

### 19.4. Error Labels

Never catch every MongoDB exception and retry forever. Out-of-stock or duplicate request with a different payload are business errors. Transient errors call for retrying the full transaction; `UnknownTransactionCommitResult` calls for retrying/reconciling commit rather than re-running the business operation with a new ID.

### 19.5. Spring Data MongoDB

In Spring, you can use `MongoTransactionManager` and `@Transactional` once replica set, versions, and transaction manager are configured properly. Still, **`@Transactional` does not wrap broker calls** or separate SQL databases.

In the service layer, business writes and outbox inserts must share the same session/transaction context. Watch out for proxy-bypassing self-invocation or repository/driver handles outside the transaction.

---

## 20. Java Sync Driver: Relay Claim and Publish

### 20.1. Producer Interface with ACK Semantics

~~~java
public interface EventPublisher {

    /**
     * Returns only after broker ACK per durability policy.
     * On timeout, the broker may still have persisted the message.
     */
    void publishAndAwaitAck(
        String topic,
        String partitionKey,
        String eventId,
        Document payload
    ) throws Exception;
}
~~~

Never use a method that merely queues in RAM and treats publishing as succeeded.

### 20.2. Atomic Claim

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.FindOneAndUpdateOptions;
import com.mongodb.client.model.ReturnDocument;
import com.mongodb.client.model.Sorts;
import com.mongodb.client.model.Updates;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.time.Duration;
import java.util.Date;
import java.util.UUID;

public class OutboxClaims {

    public static Document claimOne(
            MongoCollection<Document> outbox,
            Duration lease) {

        Date now = new Date();
        Date until = new Date(
            now.getTime() + lease.toMillis()
        );

        String token = UUID.randomUUID().toString();

        Bson eligible = Filters.and(
            Filters.lte("nextAttemptAt", now),
            Filters.or(
                Filters.eq("status", "PENDING"),
                Filters.and(
                    Filters.eq("status", "PROCESSING"),
                    Filters.lte("leaseUntil", now)
                )
            )
        );

        Bson update = Updates.combine(
            Updates.set("status", "PROCESSING"),
            Updates.set("claimToken", token),
            Updates.set("leaseUntil", until),
            Updates.inc("attempts", 1)
        );

        FindOneAndUpdateOptions options =
            new FindOneAndUpdateOptions()
                .sort(Sorts.ascending("createdAt", "_id"))
                .returnDocument(ReturnDocument.AFTER);

        return outbox.findOneAndUpdate(
            eligible, update, options
        );
    }
}
~~~

### 20.3. Publish and Mark

~~~java
Document event = OutboxClaims.claimOne(
    outbox,
    Duration.ofSeconds(30)
);

if (event != null) {
    publisher.publishAndAwaitAck(
        event.getString("topic"),
        event.getString("partitionKey"),
        event.getString("eventId"),
        event.get("payload", Document.class)
    );

    var result = outbox.updateOne(
        Filters.and(
            Filters.eq("_id", event.get("_id")),
            Filters.eq("status", "PROCESSING"),
            Filters.eq(
                "claimToken",
                event.getString("claimToken")
            )
        ),
        Updates.combine(
            Updates.set("status", "PUBLISHED"),
            Updates.set("publishedAt", new Date()),
            Updates.unset("claimToken"),
            Updates.unset("leaseUntil")
        )
    );

    if (result.getModifiedCount() != 1) {
        // Lease may have expired or another worker reclaimed.
        // Broker may already have the message; consumers must deduplicate.
    }
}
~~~

This snippet shows only the **happy path**. Production relays need `try`/`catch`, backoff, retry scheduling, broker timeouts, lease renewal if needed, metrics, and graceful shutdown.

### 20.4. Graceful Shutdown

When stopping the service:

1. Stop claiming new events.
2. Finish or bound waiting for in-flight publishes.
3. Mark `PUBLISHED` only after broker ACK.
4. Let leases expire if work could not finish.
5. Never delete unpublished outbox events.
6. On restart, scan `PENDING` and expired leases.

---

## 21. TTL, Retention, and Preventing Event Loss

### 21.1. Wrong: TTL Across the Entire Outbox on `createdAt`

~~~javascript
db.outboxEvents.createIndex(
  { createdAt: 1 },
  {
    expireAfterSeconds: 3600
  }
);
~~~

If the broker goes down for over an hour, `PENDING` events get purged by TTL before publishing. The outbox fails to preserve intent.

### 21.2. Better: TTL on `publishedAt`

~~~javascript
db.outboxEvents.createIndex(
  { publishedAt: 1 },
  {
    name: "ttl_published_outbox_30d",
    expireAfterSeconds: 2592000
  }
);
~~~

Only documents carrying a `publishedAt` date are subject to this TTL. `PENDING` and `PROCESSING` events **must not** have `publishedAt`.

### 21.3. TTL Is Not a Real-Time Scheduler

MongoDB's TTL monitor deletes expired documents periodically and can lag; `nextAttemptAt` drives relay retry scheduling. Never use TTL as an event delivery timer.

### 21.4. Retention Across Systems Must Align

- Outbox retention.
- Broker retention/replay window.
- Consumer inbox/deduplication retention.
- Audit/security retention.
- Backup/PITR retention.

If consumer deduplication records expire after one day while the broker replays 30-day-old messages, replays will re-trigger side effects. Design retention policies holistically.

### 21.5. Archiving and Replay

You can archive `PUBLISHED` events to object storage or an audit archive before TTL expiration. During replay, keep the original `eventId` for the same business fact, track replay attempts, and rate-limit to avoid flooding downstream notifications.

---

## 22. Freshness, Performance, and Cost

### 22.1. Outbox Increases Writes

One order can generate:

- Update inventory.
- Insert order.
- Insert outbox.
- Update outbox to `PROCESSING`.
- Update outbox to `PUBLISHED`.
- Corresponding index maintenance.

At thousands of orders per second, the outbox increases storage, oplog volume, replication traffic, disk I/O, and cache pressure. Do capacity planning rather than treating it as free.

### 22.2. Polling Intervals and Latency

Aggressive polling lowers wait latency at the cost of empty queries. Slower polling cuts query load while raising commit-to-publish latency.

Benchmark p50/p95/p99 of:

~~~text
business commit timestamp -> broker acknowledgment timestamp
~~~

Monitor alongside oldest pending backlog age to catch tail latency under traffic spikes.

### 22.3. Index Trade-Offs

Indexes are needed for due `PENDING` and expired `PROCESSING` queries, yet excessive indexes slow writes. Use `explain("executionStats")` to inspect keys/docs examined and sorts, especially when the outbox holds millions of documents.

### 22.4. Payload Size

BSON documents have size limits; never stuff large files or binaries into outbox events. Avoid embedding full PII payloads. Store references to durable storage with matching read permissions and retention when appropriate.

### 22.5. Transactions on Sharded Clusters

If business collections and the outbox reside on different shards, transactions require distributed commit coordination, adding latency. Align shard keys and access patterns with atomic boundaries while respecting sharded unique index constraints.

### 22.6. Tenant Fairness

In multi-tenant SaaS, one tenant with a massive backlog can starve workers for everyone else. Partition or cap concurrency per tenant, aggregate, or topic without violating ordering requirements.

---

## 23. Monitoring and Alerting

| Metric | Question Answered |
|---|---|
| `PENDING` count | How many events remain unsent? |
| Oldest `PENDING` age | How long has the oldest event waited? |
| `PROCESSING` count | How many events currently hold a lease? |
| Expired lease count | Are workers crashing or stalling? |
| `DEAD` count | Do any events need manual intervention? |
| Publish successes/failures | Is broker publishing healthy? |
| Retry attempts | Is a retry storm occurring? |
| Broker ACK latency | Is the broker responding slowly? |
| Commit-to-publish p95/p99 | Are event delivery SLAs met? |
| Consumer duplicate count | How frequent are duplicate deliveries? |
| Consumer processing lag | Are downstream services keeping up? |
| Transaction abort rate | Are producer write conflicts or business errors rising? |

### 23.1. `mongosh` Inspection Commands

~~~javascript
db.outboxEvents.countDocuments({
  status: "PENDING"
});

db.outboxEvents.countDocuments({
  status: "DEAD"
});

db.outboxEvents.find(
  { status: "PENDING" },
  {
    _id: 1,
    eventType: 1,
    attempts: 1,
    createdAt: 1,
    nextAttemptAt: 1
  }
).sort({ createdAt: 1 }).limit(20);
~~~

These inspect state; never dump full payloads containing sensitive data into logs.

### 23.2. Typical Alerts

- Oldest `PENDING` age exceeds SLA.
- Backlog grows continuously.
- `DEAD` count > 0.
- Sudden spike in broker errors.
- Unusual spike in expired leases.
- Consumer lag crosses threshold.
- Write concern errors or replica set lag.
- TTL or storage capacity nearing limits.

Tune thresholds to actual workloads; no single value fits every deployment.

---

## 24. Runbook When the Relay Fails

### Step 1 — Identify Stuck Events

Filter `PENDING`, expired `PROCESSING`, and `DEAD` events; record `eventId`, `aggregateId`, `attempts`, and age.

### Step 2 — Check MongoDB

Verify replica set primary, replication lag, write concern errors, disk space, query/index plans, and TTL policies.

### Step 3 — Check the Broker

Verify authentication, TLS, topics/exchanges, producer acknowledgments, quotas, partition availability, and schema validation.

### Step 4 — Classify the Failure

- Transient network error.
- Broker outage.
- Schema-invalid payload.
- Missing destination.
- Message too large.
- Missing publish permissions.
- Ordering gap.
- Consumer incompatibility.

### Step 5 — Controlled Recovery

Fix the root cause, reset status/`nextAttemptAt` per runbook, keep `eventId` unchanged, verify ordering, and rate-limit publishing when draining large backlogs.

### Step 6 — Guard Against Duplicates

Before bulk replay, confirm consumer inbox/idempotency works. If downstream calls external APIs, verify idempotency keys and compensating actions.

### Step 7 — Reconcile

Compare `PLACED` business orders against outbox `OrderPlaced` events, brokered events, and consumer processing records by time window and `requestId`. Reconciliation catches bugs or legacy pre-outbox records.

### Step 8 — Postmortem

Document timeline, root cause, replayed event IDs, duplicate counts, backlog recovery time, and alert/test improvements.

---

## 25. Related Alternatives

### 25.1. Direct Publish After Commit

Simple to write, yet has a crash gap. Acceptable only if losing events is tolerable.

### 25.2. Polling Outbox

Easy recovery using collection state with no resume token dependency, though incurs polling queries/latency and needs leases/retries.

### 25.3. Outbox with Change Streams

Lowers latency, yet requires managing stream lifecycles, resume tokens, oplog history, and startup backlog scans. Deduplication is still mandatory.

### 25.4. CDC on Business Collections

Change data capture can watch order updates directly; however, raw document diffs do not always equal intentional domain events. An outbox records explicit event envelopes.

### 25.5. Event Sourcing

Event sourcing stores an event log as the aggregate's source of truth. Transactional outbox keeps normal business state while adding outbound events. They can complement each other, yet are not synonymous.

### 25.6. Sagas

Sagas coordinate multi-step workflows across services with compensation when needed. Outbox ensures each locally committed step emits durable events to trigger the next step. The two patterns complement each other.

### 25.7. Distributed Two-Phase Commit

Distributed systems can use transaction coordinators where resources and protocols support them, yet you cannot assume MongoDB and a message broker form a distributed ACID transaction just via `@Transactional`.

---

## 26. Common Design Mistakes

**Mistake 1 — Publishing to the broker inside the transaction callback.** Callbacks can retry; sent messages do not roll back.

**Mistake 2 — Inserting into the outbox outside the session.** If the business transaction aborts, the outbox event remains and gets published erroneously.

**Mistake 3 — Marking `PUBLISHED` before broker ACK.** A crash loses the event.

**Mistake 4 — Changing `eventId` across retries.** Consumers cannot detect duplicates.

**Mistake 5 — Believing atomic claims prevent all duplicates.** Lease expiry and lost broker ACKs still produce duplicates.

**Mistake 6 — Retrying broker timeouts with a new `eventId`.** Destroys deduplication.

**Mistake 7 — Writing the inbox marker before the business effect outside the same transaction.** Crashes create phantom processed markers.

**Mistake 8 — ACKing the broker before committing locally in the consumer.** Crashes lose side effects.

**Mistake 9 — Sorting only by `createdAt` and expecting strict order with multiple workers.** Parallel publishing can reorder events.

**Mistake 10 — Omitting `aggregateVersion`.** Consumers struggle to detect missing or out-of-order events.

**Mistake 11 — Setting TTL on `createdAt` for all documents.** Prolonged broker outages purge `PENDING` events.

**Mistake 12 — Saving the change stream resume token before publishing.** Restarts skip unsent events.

**Mistake 13 — Watching inserts only, without a startup backlog scan.** Pre-existing events will not re-emit automatically.

**Mistake 14 — Failing to distinguish unknown commits from aborted transactions.** Clients may create duplicate orders on retry.

**Mistake 15 — Infinitely retrying schema errors.** Creates poison-message loops and wastes resources.

**Mistake 16 — Treating `DEAD` as completed.** Delivery is still unfulfilled.

**Mistake 17 — Lacking backlog age metrics.** Stuck events go unnoticed for hours.

**Mistake 18 — Storing full MongoDB documents as event messages.** Leaks PII, couples schemas, and bloats payloads.

**Mistake 19 — Assuming outbox `PUBLISHED` means consumers finished.** Those are two independent milestones.

**Mistake 20 — Using one global transaction to publish a massive batch.** Provides zero broker atomicity while creating long MongoDB transactions.

---

## 27. Testing Real Failure Points

### 27.1. Abort Before Commit

Intentionally throw after decrementing inventory and before outbox insert/commit. Verify stock stays unchanged and neither order nor outbox event exists.

### 27.2. Duplicate Key on Outbox Insert

Trigger a duplicate `eventId`. Verify the transaction rolls back both the inventory update and order insert.

### 27.3. Crash Right After MongoDB Commit

Stop the relay, commit an order, and confirm the `PENDING` outbox record persists. Start the relay and verify the event publishes.

### 27.4. Crash After Claim

Claim a `PENDING` event and kill the worker before calling the broker. Wait for lease expiry and verify another worker reclaims and publishes.

### 27.5. Crash After Broker ACK

Broker receives the event, yet the relay dies before marking `PUBLISHED`. Restart the relay, let it republish, and confirm the consumer creates only one business effect via its inbox.

### 27.6. Two-Worker Race

Have two workers claim one `PENDING` event concurrently. Verify only one claim succeeds while the lease is active. Test lease expiry to confirm duplicates remain possible.

### 27.7. Prolonged Broker Outage

Stop the broker longer than polling intervals. Verify events are not purged by TTL, backlog rises, alerts trigger, and delivery recovers when the broker returns.

### 27.8. Unknown Commit Outcome

Cut the network during MongoDB commit. Retry the API with the same `requestId`/`orderId` and confirm stock is not deducted twice.

### 27.9. Consumer Redelivery

Have the consumer commit shipment + inbox, then crash before ACKing the broker. Verify the redelivered message does not create a second shipment.

### 27.10. Ordering Gap

Deliver version 2 before version 1. Confirm the consumer blocks/reconciles or follows policy rather than silently marking version 1 applied.

### 27.11. Change Stream Resume Failure

Take the stream offline in staging and invalidate its resume token. Confirm the relay scans the `PENDING` backlog rather than skipping events.

### 27.12. TTL Retention Test

Seed old `PENDING` and `PUBLISHED` events. Confirm TTL removes only `PUBLISHED` records with matching `publishedAt`, leaving `PENDING` intact.

### 27.13. Schema Evolution

Run v1 and v2 consumers concurrently during a rollout. `schemaVersion` 2 adds a new field; contract tests confirm compatibility or migration behavior.

---

## 28. Practice Exercises

### Exercise 1 — Dual-Write Analysis

Draw timelines for both database/broker orderings. Mark the exact crash points causing lost events or phantom events.

### Exercise 2 — Schema & Indexes

Create `inventory`, `orders`, `outboxEvents`, unique indexes on `requestId` and `eventId`, and claim/expiry indexes. Explain each index.

### Exercise 3 — Transaction Commit

Write a `mongosh` transaction decrementing stock, inserting an order, and inserting an `OrderPlaced` outbox event. Verify all three commit together.

### Exercise 4 — Transaction Abort

Intentionally order more units than available stock. Verify stock stays untouched and no order or outbox event exists.

### Exercise 5 — Duplicate Request

Resend a request with the same `requestId`. Verify stock is not deducted twice. What should the API return when payloads match vs. differ?

### Exercise 6 — Polling Atomic Claim

Use `findOneAndUpdate` to claim `PENDING` events. Run two workers and explain why leases and filters matter.

### Exercise 7 — Lease Expiry

Worker A claims and stalls. Worker B reclaims after lease expiry. Analyze duplicate delivery when Worker A was merely slow rather than dead.

### Exercise 8 — Broker ACK and Crash

Have the relay publish without marking `PUBLISHED`. Restart and republish. Write an idempotent consumer processing the same `eventId` once.

### Exercise 9 — Consumer Local Inbox Transaction

Write `processedEvents` and `shipments` inside the same MongoDB transaction. Verify an error between writes aborts both.

### Exercise 10 — Backoff and `DEAD`

Design exponential backoff, jitter, max attempts, and a replay procedure for poison events.

### Exercise 11 — Change Streams

Watch outbox inserts. Analyze why startup backlog scans, safe resume token checkpoints, and oplog retention awareness are necessary.

### Exercise 12 — Ordering

Produce `OrderPlaced` v1, `OrderPaid` v2, and `OrderShipped` v3. Design `aggregateVersion` and consumer gap detection.

### Exercise 13 — Java Producer

Write `OrderOutboxService` using `ClientSession` + `withTransaction`. Keep message broker calls out of the callback.

### Exercise 14 — Java Relay

Implement `claimOne`, `publishAndAwaitAck`, and marking `PUBLISHED` guarded by `claimToken`. Add publish failure/retry handling.

### Exercise 15 — TTL

Why can a 1-hour `createdAt` TTL lose events during a 2-hour broker outage? Design a `publishedAt` TTL instead.

### Exercise 16 — Consumer External API

If a consumer calls a shipping carrier API, how should idempotency keys and reconciliation handle lost HTTP responses?

### Exercise 17 — Load Test

Suppose 5,000 orders/sec each emit an outbox event. Design a benchmark measuring MongoDB writes, relay throughput, backlog growth, broker ACKs, and catch-up time.

### Exercise 18 — Reconciliation

Write a reconciliation plan comparing `PLACED` orders with outbox events, broker acknowledgments, and consumer processing records by `requestId` and time window.

---

## 29. Review Questions

1. What is a dual-write?
2. Why can committing to MongoDB and then publishing to a broker lose events?
3. Why can publishing to a broker and then committing to MongoDB create phantom events?
4. Which transaction holds the outbox event insert?
5. Why must all writes pass the same `ClientSession`?
6. When the business transaction aborts, does the outbox record remain?
7. Once the business transaction commits, has the broker definitely received the event?
8. What does the relay do?
9. How do `PENDING`, `PROCESSING`, and `PUBLISHED` differ?
10. Why mark `PUBLISHED` only after broker ACK?
11. How is marking before publishing dangerous?
12. Which race does atomic `findOneAndUpdate` prevent?
13. What are `claimToken` and `leaseUntil` used for?
14. Do leases eliminate duplicate broker publications completely?
15. How does backoff help?
16. Does a `DEAD` event mean processing finished?
17. What is at-least-once publication?
18. Why must consumers be idempotent?
19. What is the inbox pattern?
20. Why should the consumer inbox and business effect share a transaction?
21. When should the consumer ACK the broker?
22. Why must `eventId` remain stable across retries?
23. How does `aggregateVersion` differ from `schemaVersion`?
24. Why are timestamps insufficient to guarantee ordering?
25. When should you use `aggregateId` as the broker partition key?
26. How do change streams assist a relay?
27. Why is a backlog scan still needed even with change streams?
28. What failure occurs if a resume token is saved too early?
29. Why is TTL on `createdAt` dangerous?
30. Why is TTL on `publishedAt` safer?
31. What does MongoDB `writeConcern: "majority"` achieve?
32. How should `UnknownTransactionCommitResult` be handled?
33. Why shouldn't a transaction callback call external APIs?
34. Does outbox `PUBLISHED` prove consumers finished processing?
35. How does an outbox differ from event sourcing?
36. How do outboxes support sagas?
37. Why can sharded transactions be costly?
38. Which metrics detect a stalled relay?
39. During prolonged broker downtime, what must remain durable in MongoDB?
40. What crash test proves consumers handle duplicates safely?

---

## 30. Summary

The transactional outbox coordinates **MongoDB business transactions** with **asynchronous event publishing**:

~~~text
API
 |
 v
MongoDB transaction:
  update business data
  insert outbox event
 |
 v
commit
 |
 v
relay claim
 |
 v
publish broker + await ACK
 |
 v
mark PUBLISHED
 |
 v
consumer dedupe/inbox
 |
 v
local business commit
 |
 v
broker ACK
~~~

Key principles:

1. **Business writes and outbox inserts must share the same session and transaction.**
2. **Never publish directly to the broker inside a transaction callback.**
3. **A MongoDB commit does not mean the broker already received the event.**
4. **The relay must publish and await broker ACK before marking `PUBLISHED`.**
5. **Embrace at-least-once delivery and design idempotent consumers**, rather than promising end-to-end exactly-once.
6. **Atomic claims, leases, retry/backoff, and crash recovery** make the relay resilient.
7. **Stable `eventId`, `aggregateVersion`, and ordering policies** handle duplicates and out-of-order arrivals.
8. **Change streams never replace outbox state and recovery scans.**
9. **Retention must purge only published events per policy**, never deleting `PENDING` early.
10. **Monitoring, replay, and reconciliation** are integral parts of production architecture.

A reliable transactional outbox system must answer: **After a business commit, does the event persist durably? If the relay dies, will it be retried? If the broker receives duplicates, does the consumer handle them safely? If events stall for long, can operations detect and recover them?**

## References

- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Manual — Transactions and Applications](https://www.mongodb.com/docs/manual/core/transactions-in-applications/)
- [MongoDB Manual — Production Considerations for Transactions](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Manual — Read Concern Snapshot](https://www.mongodb.com/docs/manual/reference/read-concern-snapshot/)
- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [MongoDB Manual — `db.collection.findOneAndUpdate()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.findOneAndUpdate/)
- [MongoDB Manual — TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/)
- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/)
- [MongoDB Manual — BSON Limits](https://www.mongodb.com/docs/manual/reference/limits/)
- [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/)
- [MongoDB Java Sync Driver — Change Streams](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/change-streams/)
- [Spring Data MongoDB — Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html)
- [Microservices Patterns — Transactional Outbox](https://microservices.io/patterns/data/transactional-outbox.html)
- [Microservices Patterns — Idempotent Consumer](https://microservices.io/patterns/communication-style/idempotent-consumer.html)
