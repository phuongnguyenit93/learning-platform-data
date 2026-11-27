# Distinguishing Database Change Streams from Business Events

When building applications with **Spring Data MongoDB**, we can monitor document changes using **MongoDB change streams** via the driver, `MongoTemplate`, or `ReactiveMongoTemplate`. However, a document changing does **not mean** the system has produced a meaningful business event. Distinguishing between these two kinds of events helps design reliable integrations, avoid triggering wrong business workflows, and reduce coupling between systems.

## 1. Two Concepts Answering Two Different Questions

### Change stream: "How did the data just change?"

A MongoDB change stream is a stream of notifications about changes **recorded** in the database. An application can watch at the collection, database, or deployment scope (depending on APIs and privileges). A notification typically describes the operation type (`insert`, `update`, `replace`, `delete`, ...), namespace, document key, time associated with the change, and a **resume token** to continue reading the stream.

For example, suppose the `orders` collection has the document:

~~~json
{
  "_id": "ORD-1042",
  "customerId": "CUS-88",
  "status": "CREATED",
  "totalMinor": 125000
}
~~~

When an update changing `status` from `CREATED` to `PAID` is saved, the change stream may emit an `update` event with `documentKey` `ORD-1042` and `updateDescription.updatedFields.status` set to `PAID`. It only confirms **that a data change occurred**; this record alone does not prove who made the change, why, whether business rules were satisfied, or what the `PAID` status means in the system.

### Business event: "What meaningful domain fact just happened?"

A **business event** (or *domain event*, depending on system boundaries) records a fact meaningful to users and business rules: `OrderPlaced`, `PaymentCaptured`, `OrderCancelled`, `InventoryReserved`... Events are typically created after processing a command and validating business conditions.

An event contract might look like:

~~~json
{
  "eventId": "evt-7d5b",
  "type": "PaymentCaptured",
  "version": 1,
  "aggregateId": "ORD-1042",
  "occurredAt": "2026-11-20T05:10:00Z",
  "payload": {
    "paymentId": "PAY-9001",
    "amountMinor": 125000,
    "currency": "VND"
  }
}
~~~

`PaymentCaptured` signifies that a payment capture transaction succeeded under payment rules. It may lead to multiple data changes (inserting a payment record, updating the order, writing history); conversely, simply modifying a `status` field does not necessarily prove payment was captured.

**Key takeaway:** Change streams reflect **storage operations**; business events reflect **domain meaning and system commitments**.

## 2. Direct Comparison

| Criterion | MongoDB change stream | Business event |
| --- | --- | --- |
| Origin | MongoDB observing recorded data changes | Application or domain logic establishing a business fact |
| Question answered | Which document was inserted, updated, replaced, deleted? | Was the order placed, payment captured, inventory reserved? |
| Naming | `insert`, `update`, `replace`, `delete` | `OrderPlaced`, `PaymentCaptured`, `ShipmentDispatched` |
| Context | Collection, document key, changed fields, resume token | Event ID, business entity, schema version, required business payload |
| Abstraction level | Tied to the storage model | Tied to domain language and rules |
| Impact of DB schema changes | Consumers reading directly are easily affected | Event contract can stay stable even if storage layout changes |
| Suitable scenarios | Data synchronization, updating search indexes/caches, observing changes, waking an outbox publisher | Inter-service communication, payment workflows, notifications, business reporting |
| Replay capability | Relies on resume tokens and history still retained in the oplog | Depends on the event store/broker, retention policy, and designed replay mechanics |

Do not call every change stream message a "domain event". Nor should you assume one business event maps to exactly one CRUD operation.

## 3. Common Sources of Confusion

Consider an order system using the `orders` collection:

| Change observed in MongoDB | Conclusion that *may* be true | Conclusion you must NOT infer automatically |
| --- | --- | --- |
| `insert` document with `status: CREATED` | A new order document exists | A customer just successfully placed an order: the record might come from historical import or recovery |
| `update status: PAID` | The status field changed | The payment gateway actually captured funds, since it could be a manual fix or resync |
| `delete` document | The document was removed | The customer requested cancellation: deletion could come from TTL, maintenance tasks, or retention rules |
| Updating multiple fields in one transaction | Several pieces of data changed together | Each field corresponds to a separate business event |
| No updates seen on `orders` | The collection emitted no observable changes | No business events occurred: an event might not modify this collection |

For example, if business rules state that `OrderPaid` is only emitted after receiving valid confirmation from a payment provider, listening for `orders.status` turning into `PAID` is **not enough** to draw that conclusion. Consumers should rely on a trustworthy business contract, or a translation layer backed by sufficient evidence and clear rules.

## 4. Using Spring Data MongoDB to Read Data Changes

In reactive applications, `ReactiveMongoTemplate` provides an API to create a `Flux` of `ChangeStreamEvent`. The following example only tracks technical changes to the `orders` collection; it **does not yet emit** business events:

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.ChangeStreamEvent;
import org.springframework.data.mongodb.core.ChangeStreamOptions;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public class OrderChangeFeed {
    private final ReactiveMongoTemplate mongo;

    public OrderChangeFeed(ReactiveMongoTemplate mongo) {
        this.mongo = mongo;
    }

    public Flux<ChangeStreamEvent<Document>> changes() {
        return mongo.changeStream(
            "orders",
            ChangeStreamOptions.empty(),
            Document.class
        );
    }
}
~~~

The application must **attach a subscriber** to actually receive data. In real deployments, you must manage subscription lifecycle, connection errors, backpressure, checkpoint persistence, and restarts; do not place an ad-hoc `subscribe()` inside every HTTP request and leave streams running unmanaged. For synchronous tasks, Spring Data MongoDB also provides change stream listening via the corresponding `MongoTemplate` and message listener container APIs.

Technical limitations to understand:

- **MongoDB prerequisites:** Change streams require MongoDB running as a replica set or sharded cluster; they do not work as normal change streams on a standalone server. The monitoring account must have appropriate privileges.
- **Event payload:** On `update`, the event may contain an *update description* without the full new document. `fullDocument` lookup modes (such as `updateLookup`) perform a query to fetch the document and should not be treated as an immutable snapshot at the exact operation time; on `delete`, there is usually no document left to query. Do not design business logic assuming `fullDocument` is always present.
- **Ordering and recovery:** Resume tokens allow continuing the stream while the required change history still exists. If a token is older than the oplog or the stream is invalidated, the system needs a re-initialization/reconciliation plan and cannot assume infinite historical replay.
- **Delivery semantics:** Change streams do not automatically guarantee exactly-once processing in applications outside MongoDB. Subscribers must still deliberately handle retries, duplicates, and checkpoints.

## 5. From Change Streams to Business Events: Common Architectures

### Approach A — Inferring directly from a business collection

A consumer can watch `orders` and map `update status = PAID` to `OrderPaid`. This approach is only safe when **every** write path follows the exact same rules, provides enough information to prove business conditions, and defines how to handle historical data, manual edits, duplicate updates, and schema changes.

If there are multiple write paths (APIs, batch jobs, migrations, admin tools), inference easily breaks. It can also tightly couple consumers to collection structure. For critical workflows like recording payments, deducting inventory, or issuing refunds, emit the event at the point where the application **knows for sure** the business fact occurred.

### Approach B — Transactional outbox with MongoDB change streams

The application validates business conditions, writes the state, and writes an **outbox record** representing the business event within the same MongoDB transaction. After the transaction commits, a publisher watches the change stream on the `outbox_events` collection, reads the event content, and forwards it to a broker or receiving system.

~~~mermaid
flowchart LR
    A[Receive place-order command] --> B[Validate business rules]
    B --> C[MongoDB transaction]
    C --> D[(orders)]
    C --> E[(outbox_events)]
    E --> F[Outbox change stream]
    F --> G[Publisher]
    G --> H[Broker / receiver]
    H --> I[Idempotent consumer]
~~~

Here there are **two distinct layers**:

1. The `insert` notification on `outbox_events` is a **database change event**, used as a transport trigger.
2. The outbox document containing `type: OrderPlaced`, `eventId`, `aggregateId`, `payload`... is the **business event** the system wants to publish.

Minimal example using `MongoTemplate` to write data and the outbox in one transaction:

~~~java
import java.time.Instant;
import java.util.Date;
import java.util.UUID;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PlaceOrderService {
    private final MongoTemplate mongo;

    public PlaceOrderService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    @Transactional
    public void placeOrder(String orderId, long totalMinor) {
        // In practice: validate the command and check business rules before writing.
        mongo.insert(new Document("_id", orderId)
            .append("status", "PLACED")
            .append("totalMinor", totalMinor), "orders");

        mongo.insert(new Document("_id", UUID.randomUUID().toString())
            .append("type", "OrderPlaced")
            .append("version", 1)
            .append("aggregateId", orderId)
            .append("occurredAt", Date.from(Instant.now()))
            .append("payload", new Document("totalMinor", totalMinor)),
            "outbox_events");
    }
}
~~~

**Mandatory conditions for this example:** `MongoTransactionManager` must be configured and MongoDB must support multi-document transactions (a replica set or compatible sharded cluster). Without a real transaction, the two inserts could partially succeed, breaking consistency between data and outbox. In production code, you must also handle command idempotency, unique keys, business errors, and state transition rules.

The publisher watching `outbox_events` merely forwards the **recorded event contract** without guessing intent from `orders` fields. If the broker send succeeds but the publisher fails before saving its checkpoint, the event may be sent again. Therefore, the outbox solves **recording state alongside intent to publish**, while duplicate delivery still requires `eventId` and an idempotent consumer.

## 6. Designing Delivery, Recovery, and Testing

### Saving checkpoints and avoiding lost events

When using resume tokens to continue reading a change stream, operation order should follow the actual execution flow:

1. Receive the change on the outbox collection along with its resume token.
2. Push the business event to the broker; wait for the acknowledgment that the system considers durable confirmation.
3. **Only then** persist the checkpoint durably. On restart, resume from the appropriate checkpoint.

Saving the checkpoint **before** broker acknowledgment can lose events. Saving after acknowledgment can cause an event to be sent twice if the process fails between the two steps. That is why consumers need deduplication, typically via `eventId` and a processed-event tracking mechanism suited to the domain.

In addition to checkpointing, define a policy for expired tokens: pause, report a clear error, reconcile/re-scan remaining outbox records, and then resume from a consistent anchor. Do not purge outbox records sooner than consumers can recover; TTL or cleanup rules must align with retention and replay requirements.

### Operational metrics to monitor

- **Event publishing latency:** time from outbox commit to broker acknowledgment; alert when backlog grows.
- **Recoverability:** last checkpoint timestamp, resume token errors, connection drops, remaining oplog window for recovery.
- **Contract quality:** unique event identifiers, standardized `type` and `version`, keeping consumers decoupled from internal document layout.
- **Data security:** payloads contain only fields consumers need; do not copy sensitive fields from documents onto a broker by default.
- **Scalability:** failure handling, bounded retries, appropriate dead-letter/reconciliation; preserving per-aggregate order if business rules require it and the design guarantees it.

### Test scenarios worth implementing

| Scenario | What to verify |
| --- | --- |
| Valid order insert | Order and outbox written in the same transaction; `OrderPlaced` emitted with one business ID |
| Transaction rollback | No partial order/outbox written; no event emitted for the failed transaction |
| Maintenance script updates `status` | Not misinterpreted as `PaymentCaptured` without business proof |
| Publisher sends to broker then stops before checkpoint | May resend; consumer does not execute business side effects twice |
| Consumer stopped longer than oplog retention | Alert triggers and resync/reconciliation workflow runs, not silent skipping |
| Adding fields or restructuring `orders` storage | `OrderPlaced` contract remains compatible or explicitly versioned |

When integration-testing change streams and transactions, use a real MongoDB replica set (such as a properly configured Testcontainers environment) rather than assuming standalone MongoDB behaves the same way.

## 7. Choosing the Right Tool for the Goal

If the goal is **synchronizing search indexes, refreshing caches, capturing document changes, or driving an outbox publisher**, a change stream is a suitable tool. It provides a trail of data operations and a way to resume reading, though consumers must still handle retries and consistency checks.

If the goal is **notifying another system of a business fact** (such as an order confirmed, payment captured, or refund approved), define the event in domain terms and emit it where the conditions are verified. With Spring Data MongoDB, a transactional outbox combined with a change stream is often a practical choice for reliably transporting that event externally.

**Remember:** `update orders.status` is information about data; `PaymentCaptured` is a business commitment. They may be related, but they cannot substitute for each other solely based on matching field values.
