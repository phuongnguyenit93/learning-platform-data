# At-least-once, exactly-once, and processing guarantee scope in Pub/Sub

An ordering system running on Cloud Run publishes `OrderPaid` events to Google Cloud Pub/Sub. A Java worker on GKE receives the event to update a shipping table. The worker writes the data successfully, yet **loses connectivity before Pub/Sub confirms the ACK**; the event can be redelivered. If the code re-executes the "create shipping task" statement without checking, one order could produce two shipping tasks.

The issue lies at the boundary between **message delivery** and **business side-effect execution (processing/side effect)**. Pub/Sub defaults to **at-least-once delivery**; its **exactly-once delivery** feature is stronger under specific conditions, yet **is not an exactly-once transaction spanning Pub/Sub, Cloud SQL, Cloud Storage, or payment APIs**.

This lesson belongs to the **Pub/Sub and Messaging** chapter of module `CLOUD_PROVIDERS_GCP`. Building on project management, IAM, VPC, Compute Engine, GKE, Cloud Run, storage, and databases, learners will learn how to design safe consumers, automate deployments, and monitor reliability alongside cost. Hands-on commands use an approved lab project; never run them directly in production.

## Learning objectives

After this lesson, you will be able to:

1. Distinguish **at-most-once**, **at-least-once**, **exactly-once delivery**, and **exactly-once business effect**.
2. Explain `publish`, `pull`, `ackId`, `messageId`, `ack deadline`, and the redelivery lifecycle.
3. Identify accurately that **Pub/Sub's exactly-once delivery supports pull/StreamingPull within a single region**, and does not support push or export subscriptions.
4. Distinguish legitimate redelivery, duplicate delivery, and publisher-side duplicates.
5. Use confirmed ACKs, lease extension, flow control, and locational endpoints when needed.
6. Design **idempotent** consumers, dedupe tables, and transactions to avoid duplicate side effects.
7. Choose retry, dead-letter topics, retention, ordering, and replay without misunderstanding guarantee boundaries.
8. Practice with `gcloud` and a Java subscriber using ACK responses; monitor errors and costs.

## 1. Topic, subscription, and the scope of a message

~~~mermaid
flowchart LR
    API["Orders API<br/>Cloud Run"] -->|"publish OrderPaid"| T["Pub/Sub topic<br/>orders-events"]
    T --> S1["Pull subscription<br/>shipping-worker"]
    T --> S2["Push subscription<br/>audit-webhook"]
    S1 --> W["Java workers<br/>GKE / Compute Engine"]
    S2 --> H["Cloud Run HTTP endpoint"]
    W --> DB[("Cloud SQL<br/>shipping_tasks")]
    H --> STORE["Audit destination"]
~~~

- **Topic** receives messages from publishers.
- **Subscription** maintains its own delivery state. Two subscriptions on the same topic receive and acknowledge messages **independently**; ACKing on `shipping-worker` does not acknowledge on behalf of `audit-webhook`.
- **Message ID** (`messageId`) is assigned by Pub/Sub to a published message; it remains stable across **redeliveries** of that same message.
- **ACK ID** (`ackId`) is tied to **a single delivery** to a pull subscriber; when a new delivery occurs, the old ACK ID may no longer be valid.
- **Business event ID** (`eventId`) is assigned by the **application**, so it stays stable across publisher retries for the same business event, e.g., `order-paid:A100:v3`.

Example message:

~~~json
{
  "eventId": "order-paid:A100:v3",
  "orderId": "A100",
  "type": "OrderPaid",
  "revision": 3,
  "occurredAt": "2026-11-19T04:00:00Z"
}
~~~

This JSON is the **application payload**, not the full Pub/Sub API response. `eventId` detects two **separate publishes** of the same business event; relying solely on Pub/Sub `messageId` misses publisher retries.

## 2. Four commonly confused guarantee levels

| Concept | Meaning | What must not be inferred |
| --- | --- | --- |
| **At-most-once** | May be lost, not actively redelivered; suitable for some droppable tasks | Unsuitable for payment events requiring durability |
| **At-least-once delivery** | Pub/Sub attempts to deliver a message at least once to a subscriber within retention, with possible redelivery | "The application processes it only once" |
| **Exactly-once delivery (Pub/Sub)** | For a **pull subscription** with the feature enabled and subscribers in the **same region**, a message with a given `messageId` is not delivered redundantly before ACK expiry or after a **confirmed successful ACK** | No redelivery after NACK/deadline expiry, or no publisher duplicates |
| **Exactly-once business effect** | One business event causes only one effective change, e.g., creating **one** shipping task | Pub/Sub automatically guarantees an atomic Cloud SQL commit + ACK |

**Key terminology:** Pub/Sub exactly-once is a **delivery/ack guarantee for a single Pub/Sub message on a single subscription within the stated scope**. A multi-system workflow achieves a single business effect only when the application uses proper idempotency and transactions.

### 2.1. "Exactly-once" still has legitimate redeliveries

Exactly-once does not promise "the callback runs only once under all failures." When the client **NACKs** or the **ack deadline expires** without extension, Pub/Sub can redeliver the **same message ID**. It promises no **unexpected duplicate delivery** while a message is validly outstanding or **after an ACK has been confirmed by the service**. Therefore distinguish:

- **Legitimate redelivery:** client NACKed or failed to ACK/extend on time.
- **Unexpected duplicate delivery:** message redelivered **before deadline expiry** or **after a successful ACK**. Exactly-once prevents this type within supported scope.
- **Publisher-side duplicates:** publisher sends the same business event twice, creating **two distinct Pub/Sub messages** (usually with different message IDs). An exactly-once subscription can still receive both.

## 3. ACK lifecycle and points of potential redelivery

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant S as Pub/Sub
    participant C as Subscriber
    participant D as Cloud SQL
    P->>S: Publish event E
    S-->>P: messageId M1
    S->>C: Deliver M1, ackId A1
    C->>D: Commit shipping task E
    D-->>C: COMMIT succeeded
    Note over C,S: Network error before ACK confirmed
    S-->>C: Ack deadline expired
    S->>C: Redeliver M1, ackId A2
    C->>D: See E already processed → do not write duplicate
    C->>S: ACK A2
    S-->>C: ACK confirmed
~~~

There are three distinct milestones:

1. **Publish success:** Pub/Sub accepted the message and returned `messageId`; does not prove any consumer finished.
2. **Business commit:** DB/payment/object was updated; does not guarantee Pub/Sub has ACKed.
3. **ACK confirmed:** subscription received and confirmed the ACK; with exactly-once pull, Pub/Sub will not redeliver that message ID **within the guarantee scope**.

### 3.1. ACKing before commit causes data loss

~~~text
Wrong:
  receive M1
  ACK M1
  update database  → app crash

Consequence: Pub/Sub considers the message done even though business work never finished.
~~~

The standard pattern is **check → durable transaction/side effect → ACK**. If ACK fails after commit, the subscriber must tolerate redelivery and detect that the work was already performed.

### 3.2. Post-commit crash window

~~~text
receive → DB COMMIT → process crash → not yet ACKed

Next delivery:
  if durable dedupe marker exists → ACK, do not write duplicate;
  if no marker exists → risk of creating the effect a second time.
~~~

Do not mitigate this risk by raising the ack deadline indefinitely. Solve **business idempotency**, combined with lease management to reduce unnecessary redeliveries.

## 4. At-least-once: Pub/Sub's default

Pub/Sub provides **at-least-once delivery** by default across subscription types, with ordering disabled by default. Under normal conditions a message is typically delivered once, yet systems **must be designed to tolerate redelivery**.

Common causes:

- Subscriber crashes or restarts before ACK.
- Processing exceeds `ackDeadline` without the client extending the lease.
- Client calls `NACK` because a dependency failed.
- ACK request/response suffers a network failure; subscriber does not know whether the server accepted the ACK.
- Transient service glitches causing rare duplicate deliveries.
- Unsafe publisher retries creating a **new message** for the same business event.

**At-least-once does not mean "messages are kept forever."** Once message retention expires, data may no longer be delivered by Pub/Sub; topic/subscription deletion or retention/replay policies also affect availability. Design replay, backups, and alerts according to RPO requirements.

## 5. What does Pub/Sub's exactly-once delivery guarantee?

Enabling `enableExactlyOnceDelivery` on a **pull subscription**:

- Subscribers can inspect the **actual ACK outcome from the service** using a supported client library.
- Pub/Sub does not redeliver a message **after a successful ACK**.
- While a delivery remains **outstanding** and its deadline has not expired, the message is not sent redundantly.
- When multiple legitimate deliveries of the same message exist, only the **latest delivery's ACK ID** can be used; older ACK IDs are rejected.
- Guarantees apply per **Pub/Sub message ID**, on **one subscription**, within **one cloud region**.

**Not supported:** push subscriptions, BigQuery/Cloud Storage/Bigtable export subscriptions, and webhook delivery models like Pub/Sub push → Cloud Run. If you want Pub/Sub exactly-once with Java, use **Pull or StreamingPull** with a supported client library, check ACK results, and control connection regions.

| Scenario | Can exactly-once pull prevent it? | Why |
| --- | --- | --- |
| Successful ACK confirmed yet Pub/Sub resends M1 | **Yes**, within regional scope | That is a duplicate delivery |
| Client NACKs M1, Pub/Sub redelivers M1 | **No** | That is a legitimate redelivery |
| M1 deadline expires, redelivered with same messageId and new ackId | **No** | Previous ACK never completed |
| Publisher publishes the same event twice as M1 and M2 | **No** | Two distinct Pub/Sub messages |
| Cloud SQL commit succeeded but ACK M1 failed | **No** | DB commit is outside the ACK transaction |
| Two different subscriptions both receive M1 | **Not an error** | Each subscription has its own delivery state |
| Intentional seek/replay brings old messages back | **Not a normal delivery error** | Admin-requested replay behavior |

### 5.1. Cost of exactly-once coordination

Exactly-once requires additional coordination and state inside Pub/Sub, which can cause **higher publish-to-subscribe latency** than standard subscriptions. For high throughput, Google Cloud recommends **StreamingPull**. Benchmark latency, throughput, quotas, and fees against current pricing; do not enable it just because the feature name sounds "safer."

## 6. Regional scope: an often overlooked condition

Pub/Sub explicitly states that the exactly-once guarantee applies only when **subscribers connect to the service in the same region**. If workers are spread across multiple regions and automatically use their nearest endpoints, duplicate deliveries can still occur even with exactly-once enabled.

~~~mermaid
flowchart LR
    T["Pub/Sub subscription<br/>exactly-once enabled"] --> A["Worker A<br/>asia-southeast1"]
    T --> B["Worker B<br/>asia-southeast1"]
    A --> EP["Locational endpoint<br/>asia-southeast1"]
    B --> EP
    T -. "Multi-region consumers using different endpoints<br/>do not get the same guarantee" .-> C["Worker C<br/>another region"]
~~~

**Recommendation:** when you need exactly-once, pin all subscriber clients to **the same supported locational endpoint**, e.g., `asia-southeast1-pubsub.googleapis.com:443`. Publishers can send from other regions; the same-region connection requirement primarily applies to **subscribers**. Do not equate a locational endpoint with a data residency guarantee: Pub/Sub also has **regional endpoints** and Message Storage Policies with distinct properties.

For GKE/Compute Engine apps running in a single region, the default endpoint typically routes to the nearest matching region; however, when moving to multi-region DR, you must **verify how clients actually connect**. If active-active multi-region consumption is required, re-evaluate delivery guarantees and idempotency before advertising it as exactly-once.

## 7. Ack deadline, lease extension, and ACK IDs

When a subscriber pulls a message, Pub/Sub sets an **acknowledgment deadline**: the wait window before the message becomes eligible for redelivery. The subscriber can extend it via `ModifyAckDeadline`; high-level client libraries provide **lease management**.

| Scenario | Consequence |
| --- | --- |
| Processing finishes and ACKs within deadline | Message is confirmed if the service receives the ACK |
| Slow processing, lease extended in time | Reduces expiration-driven redeliveries |
| Slow processing, lease expires before ACK | New delivery occurs with a new ACK ID |
| ACK with stale ID when exactly-once is enabled | May receive `INVALID_ARGUMENT`; do not assume ACKed |
| NACK | Message may be redelivered per retry policy |
| Worker crash | Lease eventually expires, message returns to backlog |

With exactly-once, the ACK/ModifyAckDeadline API **returns explicit errors when an ACK ID has expired**, unlike some best-effort behavior when exactly-once is off. In the Java client, review `minDurationPerAckExtension` and `maxDurationPerAckExtension` (maximum **600 seconds** per extension per docs). This is not a promise that a message can run for unlimited minutes.

### 7.1. Lease management does not replace flow control

If a worker pulls 1,000 messages but can only process 50 concurrently, the rest can expire their deadlines even with zero network errors. Use **max outstanding messages/bytes**, bounded worker pools, and autoscaling to keep workload within processing capacity.

**Reduce ACK expirations before blindly adding instances.** Measure CPU, DB connection pools, processing duration, and subscription backlog; if downstream is already bottlenecked, adding workers can increase errors and duplicates.

## 8. Publishers must also be idempotent

Suppose the publisher sends `OrderPaid` to Pub/Sub. The server persists it successfully, but the HTTP/gRPC response is lost. The publisher sends **a new publish request**, and Pub/Sub may assign a **different message ID**. An exactly-once subscription **does not merge these two messages**.

~~~text
Business event: order-paid:A100:v3

Publish attempt 1 → Pub/Sub messageId 701
Publish retry     → Pub/Sub messageId 702

The consumer can legitimately receive both 701 and 702.
~~~

Mitigation approach:

1. Generate a **stable `eventId`** when the business event is created, not regenerated on each publish retry.
2. Include `eventId` in payload/attributes.
3. Subscribers use **`eventId`** (or a business transaction key) to deduplicate.
4. Publishers track publish success/failure and persist retry state where needed.
5. When a database change and publish must stay together, apply a **transactional outbox**.

**Pub/Sub message ID distinguishes redeliveries of the same Pub/Sub message; business event ID distinguishes re-publications of the same application event.**

## 9. Idempotent consumer with Cloud SQL: transactional inbox

Typical design: the worker updates `shipping_tasks` while inserting `eventId` into `processed_events` **within the same Cloud SQL transaction**.

~~~sql
-- PostgreSQL example; create tables in your lab environment schema.
CREATE TABLE processed_events (
    consumer_name TEXT NOT NULL,
    event_id TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE shipping_tasks (
    event_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    status TEXT NOT NULL
);
~~~

Consumer transaction pseudocode:

~~~text
BEGIN TRANSACTION;

INSERT INTO processed_events(consumer_name, event_id)
VALUES ('shipping-worker', :eventId)
ON CONFLICT DO NOTHING
RETURNING event_id;

IF no row inserted:
    -- Already processed, do not repeat side effect.
    COMMIT;
    ACK Pub/Sub message;
    RETURN;

-- Business validation: order exists, valid event,
-- no state-transition or version violation.
INSERT INTO shipping_tasks(event_id, order_id, status)
VALUES (:eventId, :orderId, 'READY');

COMMIT;  -- Both marker and business effect become durable together.
ACK Pub/Sub message;  -- ACK only after COMMIT.
~~~

**This is transaction pseudocode, not a PL/pgSQL block to paste and run verbatim.** In Java, use a JDBC transaction with `setAutoCommit(false)` or Spring `@Transactional` to **force the marker and business update to commit together**. If business validation/insert fails, **ROLLBACK everything**, never leaving a false "processed" marker.

### 9.1. Why does the transaction solve the crash window?

- **Crash before COMMIT:** neither marker nor shipping task is committed → redelivery reprocesses it.
- **Crash after COMMIT but before ACK:** marker already exists → redelivery does not create a second shipping task, then ACKs.
- **Two workers receive the same business event:** the unique constraint on `(consumer_name,event_id)` serializes contention; one transaction wins, and the other skips or waits and detects the duplicate.

This guarantee holds only when **both the marker and the side effect** live inside the **same database transaction**. If the side effect is an email, payment, or third-party HTTP call, a Cloud SQL transaction **cannot be atomic** with external APIs; you need a **target idempotency key**, outbox/inbox, and reconciliation.

### 9.2. Do not use RAM cache for deduplication

A static `HashSet<String> processedIds` in Java lives only inside one process. When GKE/Cloud Run scales across multiple replicas or restarts, the cache is lost. Deduplication needs a **durable, shared store** with unique/transaction constraints. Marker TTL must be long enough to cover possible replays and publisher retries; purging markers too early can reintroduce duplicate effects later.

## 10. Transactional outbox on the publisher side

The inverse case: Orders API commits `payment_status=PAID` to Cloud SQL and crashes **before publishing**. Simply calling DB then Pub/Sub sequentially risks losing the event.

A **transactional outbox** writes business state and the event to publish in the **same DB transaction**:

~~~mermaid
flowchart LR
    APP["Orders API"] --> TX["DB transaction:<br/>update order + insert outbox"]
    TX --> RELAY["Outbox relay"]
    RELAY --> PUB["Pub/Sub topic"]
    PUB --> CON["Consumer inbox + transaction"]
    CON --> DB["Shipping task"]
~~~

Pseudocode:

~~~text
BEGIN;
UPDATE orders SET payment_status = 'PAID' WHERE id = :orderId;
INSERT INTO outbox(event_id, payload, published)
VALUES (:stableEventId, :jsonPayload, false);
COMMIT;

Outbox relay:
    read unpublished records
    publish Pub/Sub message with eventId
    receive publish response
    mark outbox record as sent
~~~

If the relay publishes successfully but crashes before marking `published`, it may republish → consumers still need **inbox/dedupe**. An outbox reduces the **risk of losing events** between DB and Pub/Sub, yet does not by itself create an atomic distributed transaction across two systems.

## 11. Ordering differs from exactly-once

Pub/Sub supports **message ordering by ordering key** when the subscription enables the feature, messages with the same key are published from the **same region**, and the source follows all ordering requirements.

| Need | Feature |
| --- | --- |
| Avoid processing the same Pub/Sub message after confirmed ACK | Exactly-once delivery (pull, regional) |
| Receive messages for the same order in supported publish order | Message ordering by `orderingKey=orderId` |
| One `OrderPaid` never creates two shipping tasks | Business idempotency + durable transaction |
| One business event is not accidentally published twice | Publisher eventId/outbox/dedupe |
| No state contention between two different orders | Appropriate business transactions/partitioning |

With **ordering + exactly-once**, ACKs for messages with the same ordering key must be sent **in order**. Out-of-order ACKs can return transient errors; if deadlines expire, legitimate redeliveries occur. Combining both features can reduce throughput; do not enable ordering topic-wide if the business only needs independent per-message processing.

**An ordering key is not a database lock.** If the same order can be updated concurrently by an HTTP API and a consumer, use optimistic locking or version checks in the DB.

## 12. Push, Cloud Run, and Eventarc: limits you cannot ignore

| Receive model | Pub/Sub exactly-once? | How to design |
| --- | --- | --- |
| Java `Subscriber` on GKE using StreamingPull | **Can be enabled**, when meeting region/client library rules | Confirmed ACK + idempotent business logic |
| Batch Pull API | **Can be enabled** | ACK response/deadline checks |
| Pub/Sub push → Cloud Run HTTP endpoint | **No** | HTTP success/failure + idempotency key |
| Eventarc → Cloud Run function | **Not Pub/Sub exactly-once by default** | CloudEvents event ID + durable dedupe |
| BigQuery/Cloud Storage export subscription | **No** | Design dedicated sink/storage semantics |
| Dataflow pipeline | Dataflow processing semantics **per its own docs** | Do not infer from Pub/Sub's exactly-once flag |

A **push ACK** is an HTTP success response, yet the sender cannot be certain the response arrived and was processed across all network failures; thus push does not have confirmed-ACK semantics like pull exactly-once. If a Cloud Run service processes push events, use **inbox/idempotency** rather than trying to enable `--enable-exactly-once-delivery` on a push subscription.

## 13. gcloud lab: comparing two pull subscriptions

**Prerequisites:** lab project with approved Billing/API/IAM. Commands creating/deleting resources can incur charges and affect subscription data; never run on production topics.

~~~bash
gcloud config get-value project

gcloud services enable pubsub.googleapis.com \
  --project=PROJECT_ID

# New lab topic; if one exists, use an equivalent dedicated lab topic.
gcloud pubsub topics create orders-events-lab \
  --project=PROJECT_ID

# Default subscription: at-least-once, pull.
gcloud pubsub subscriptions create orders-atleast-lab \
  --topic=orders-events-lab \
  --ack-deadline=30 \
  --project=PROJECT_ID

# Pull subscription with exactly-once delivery.
gcloud pubsub subscriptions create orders-exactly-lab \
  --topic=orders-events-lab \
  --ack-deadline=60 \
  --enable-exactly-once-delivery \
  --project=PROJECT_ID
~~~

Attaching **two subscriptions to the same topic** gives each subscription its **own** message copy; it does not mean Pub/Sub created two publisher messages.

Inspect:

~~~bash
gcloud pubsub subscriptions describe orders-atleast-lab \
  --project=PROJECT_ID \
  --format="yaml(name,topic,ackDeadlineSeconds,enableExactlyOnceDelivery)"

gcloud pubsub subscriptions describe orders-exactly-lab \
  --project=PROJECT_ID \
  --format="yaml(name,topic,ackDeadlineSeconds,enableExactlyOnceDelivery)"
~~~

Publish a test event:

~~~bash
gcloud pubsub topics publish orders-events-lab \
  --message='{"eventId":"order-paid:LAB-1:v1","orderId":"LAB-1"}' \
  --project=PROJECT_ID
~~~

Manual pull **without auto-ACK**:

~~~bash
gcloud pubsub subscriptions pull orders-atleast-lab \
  --limit=1 --project=PROJECT_ID

gcloud pubsub subscriptions pull orders-exactly-lab \
  --limit=1 --project=PROJECT_ID
~~~

Without ACKing, once the deadline passes, the message **may** be redelivered with the same `messageId`. Do not expect redelivery at exactly 30 or 60 seconds; retry policy and delivery state can delay it.

If you run:

~~~bash
gcloud pubsub subscriptions pull orders-atleast-lab \
  --limit=1 --auto-ack --project=PROJECT_ID
~~~

then `gcloud` ACKs immediately via CLI behavior; this command is **for demos only**, does not represent business processing before ACK, and **cannot be used to verify confirmed ACK behavior of a Java exactly-once subscriber**.

**Do not try to force duplicate deliveries by breaking production networking.** This lab only observes configuration and semantics; ACK-confirmation testing should use the Java client in the next section.

## 14. Java subscriber: process then check ACK response

Use `com.google.cloud:google-cloud-pubsub` at a version supporting exactly-once (refer to docs recommending **v1.139.0 or later**; use a vetted version in production). Authenticate via **Application Default Credentials**: GKE Workload Identity Federation, Compute Engine service account, or developer ADC; avoid embedding service account private keys in source.

Example class receiving Pub/Sub messages and checking ACK results:

~~~java
import com.google.cloud.pubsub.v1.AckReplyConsumerWithResponse;
import com.google.cloud.pubsub.v1.AckResponse;
import com.google.cloud.pubsub.v1.MessageReceiverWithAckResponse;
import com.google.cloud.pubsub.v1.Subscriber;
import com.google.pubsub.v1.ProjectSubscriptionName;
import com.google.pubsub.v1.PubsubMessage;
import java.util.concurrent.ExecutionException;

public class ExactlyOnceShippingSubscriber {
    public static void main(String[] args) {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: java ExactlyOnceShippingSubscriber PROJECT_ID SUBSCRIPTION_ID");
        }

        ProjectSubscriptionName subName =
                ProjectSubscriptionName.of(args[0], args[1]);

        MessageReceiverWithAckResponse receiver =
                (PubsubMessage msg, AckReplyConsumerWithResponse reply) -> {
                    String messageId = msg.getMessageId();

                    // DEMO ONLY: replace with Cloud SQL transaction + durable dedupe.
                    try {
                        processIdempotently(msg);
                    } catch (RuntimeException failure) {
                        System.err.println("Business error, NACK: " + messageId);
                        reply.nack();
                        return;
                    }

                    try {
                        // ACK only after business logic has COMMITTED.
                        AckResponse result = reply.ack().get();
                        if (result == AckResponse.SUCCESSFUL) {
                            System.out.println("ACK confirmed: " + messageId);
                        } else {
                            System.err.println("ACK not confirmed, messageId="
                                    + messageId + " result=" + result);
                            // If redelivered: DB dedupe protects the side effect.
                        }
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        System.err.println("ACK interrupted: " + messageId);
                    } catch (ExecutionException ex) {
                        System.err.println("ACK failed: " + messageId
                                + " cause=" + ex.getCause());
                    }
                };

        Subscriber subscriber = Subscriber.newBuilder(subName, receiver)
                .setEndpoint("asia-southeast1-pubsub.googleapis.com:443")
                .build();

        Runtime.getRuntime().addShutdownHook(
                new Thread(() -> subscriber.stopAsync().awaitTerminated()));

        subscriber.startAsync().awaitRunning();
        System.out.println("Listening: " + subName);
        subscriber.awaitTerminated();
    }

    private static void processIdempotently(PubsubMessage msg) {
        // Side-effect-free example; production needs a transaction as in Section 9.
        System.out.println("Event received, messageId=" + msg.getMessageId());
    }
}
~~~

**Points to understand, rather than just copying code:**

- `MessageReceiverWithAckResponse` and `reply.ack().get()` distinguish a **confirmed ACK** from an ACK request merely having been sent.
- `processIdempotently` in the demo **only logs**, which does not achieve an exactly-once business effect. In real systems, replace it with a durable `processed_events + shipping_tasks` transaction before ACK.
- When ACK fails, **do not roll back an already-committed DB transaction**; wait for redelivery to deduplicate, inspect ACK ID/deadlines, and alert.
- Choose the **same locational endpoint** for all exactly-once subscribers in the system; if running across regions, redesign accordingly.
- The sample waits for ACK synchronously for clarity; production requires flow control, executor/lease settings, graceful shutdown, and backpressure tuned for throughput.
- Workers and ACK callbacks must be thread-safe; never log payloads containing PII.

## 15. Retry, dead-letter topic, and replay

### 15.1. Retry policy

Pub/Sub supports immediate or exponential backoff retries per subscription. When a message is NACKed or its deadline expires, Pub/Sub may redeliver it to **another worker** connected to the same subscription. Every worker must enforce the same dedupe rules.

Error classification:

| Error type | Handling |
| --- | --- |
| Temporary Cloud SQL timeout/503 | NACK or allow redelivery; retry/backoff and limit load |
| Permanently invalid payload | Route to error handling/DLQ to avoid poison-message loops |
| Business event already processed | ACK without re-creating side effects |
| KSA/service account missing IAM | Fix permissions; infinite retries will not fix it |
| Uncertain downstream side effect outcome | Reconcile via idempotency key rather than blindly resending |

### 15.2. Dead-letter topic is best-effort, not exactly-once

You can attach a **dead-letter topic (DLT)** to a subscription for failing messages. `maxDeliveryAttempts` is configurable from **5 to 100** (default 5 when enabled), though **the actual attempt count is approximate**, not a strict hard cap. The Pub/Sub service agent needs **Publisher** permission on the DLT and **Subscriber** permission on the source subscription to forward and ACK messages properly.

~~~bash
# Example for the lab topic/subscription created earlier.
gcloud pubsub topics create orders-dead-lab \
  --project=PROJECT_ID

gcloud pubsub subscriptions create orders-dead-inspect-lab \
  --topic=orders-dead-lab \
  --project=PROJECT_ID

gcloud pubsub subscriptions update orders-atleast-lab \
  --dead-letter-topic=orders-dead-lab \
  --max-delivery-attempts=5 \
  --project=PROJECT_ID
~~~

**Not enough for DLT to work yet:** admins must grant permissions to the **Pub/Sub service agent** in the right project per the Dead-letter topics docs. Afterward, monitor `subscription/dead_letter_message_count`, DLT backlog, and your triage process.

### 15.3. Retention, seek, and intentional replay

ACKed messages are normally no longer delivered on a subscription. However, if **retain acknowledged messages/topic retention** is enabled, or **snapshot + seek** is used under supported conditions, admins can **intentionally re-inject old messages into the processing stream**. The dedupe store must account for **business replays**, never assuming "already ACKed means the event will never appear again."

## 16. Monitoring subscriptions and controlling cost

Useful Cloud Monitoring metrics:

| Metric / data | Action |
| --- | --- |
| `subscription/num_undelivered_messages` | Monitor backlog and subscriber capacity |
| `subscription/oldest_unacked_message_age` | Alert when RPO/processing delay exceeds target |
| `subscription/expired_ack_deadlines_count` | Review lease extension/processing time |
| `subscription/exactly_once_warning_count` | Inspect ACK/ModifyAckDeadline failures; **diagnostic indicator only**, can be noisy |
| `subscription/dead_letter_message_count` | Investigate unprocessable messages |
| Subscriber logs `messageId`, `eventId`, delivery attempt, ackResult | Distinguish Pub/Sub redelivery from publisher duplicates |
| DB processed-events unique conflicts | Measure business dedupe hits; do not treat every conflict as an error |
| Pub/Sub billing/egress/storage | Evaluate costs of message volume, retention/retries, and networking |

**Do not rely on a single metric to conclude duplicates occurred.** `exactly_once_warning_count` can increase from operations on expired ACK IDs without indicating Pub/Sub violated its guarantee. Correlate message ID, ACK result, deadlines, and client region.

### 16.1. Pricing and IAM

- Pub/Sub bills by data volume, storage/retention, message delivery, and network/feature factors per current pricing; exactly-once, ordering, retries, and DLTs can affect latency and resource usage.
- Publishers need `roles/pubsub.publisher` on the topic.
- Subscribers need `roles/pubsub.subscriber` on the subscription to pull and ACK.
- Admins creating subscriptions/topics need narrowly scoped management roles on the target resources.
- If a consumer writes to Cloud SQL/Cloud Storage, grant **separate permissions** to its runtime identity; Pub/Sub ACK does not grant database IAM.

Set Cloud Billing budget alerts per project and service, keeping in mind **budget alerts are not hard spending caps**. Protect data and SLOs before cutting retention or flow control for cost.

## 17. End-to-end scenario: OrderPaid → one shipping task

**Assumptions:** `orders-api` receives payment over HTTP, writes to Cloud SQL, and emits `OrderPaid` to Pub/Sub. GKE `shipping-worker` uses Pull/StreamingPull, accesses Cloud SQL to create `shipping_tasks`, and calls a carrier partner API.

| Risk | Mechanism |
| --- | --- |
| DB commit succeeds yet publish fails | Transactional outbox |
| Publisher republishes the same event | Stable business `eventId` |
| Subscriber crashes after DB commit | Transactional inbox + unique key |
| Pub/Sub redelivers after ack timeout | Confirmed ACK, lease management |
| Avoid unexpected duplicate deliveries | Exactly-once pull in the same region |
| Duplicate carrier API call when response lost | Send **idempotency key** to partner or reconcile |
| Message payload fails repeatedly | Retry/backoff + DLT + on-call triage |
| Backlog grows during flash sale peak | Flow control, metric-based autoscaling, and DB quotas |

### 17.1. Three failure drills to practice

1. **Crash before COMMIT:** message unACKed → redelivered → creates exactly one shipping task.
2. **Crash after COMMIT before ACK:** redelivered → finds `processed_events` → ACKs without duplicate write.
3. **Publisher retry creates M1/M2:** same business `eventId` → consumer creates only one shipping task.

For carrier APIs outside Cloud SQL, idempotency keys and reconciliation are still required. **You cannot claim "all side effects happen exactly once" just by enabling one subscription flag.**

## 18. Self-check exercises

**Question 1.** Does at-least-once mean the subscriber callback runs only once?

*Answer:* No. Messages can be redelivered; the consumer must be idempotent.

**Question 2.** Does Pub/Sub exactly-once support push subscriptions to Cloud Run?

*Answer:* No. Exactly-once delivery only supports pull/StreamingPull, not push or export.

**Question 3.** A message receives a confirmed successful ACK and is then redelivered in the same region with exactly-once enabled. Is that consistent with the guarantee?

*Answer:* No. After a confirmed ACK, Pub/Sub does not redeliver the same messageId within supported scope.

**Question 4.** A subscriber NACKs M1 and receives M1 again. Does that violate exactly-once?

*Answer:* No. That is a legitimate redelivery.

**Question 5.** Publisher retries create M1 and M2 for the same `OrderPaid`. Does exactly-once deduplicate them automatically?

*Answer:* No. You need a shared business event ID or idempotency key.

**Question 6.** Why is `messageId` insufficient to prevent creating two shipping tasks on publisher retries?

*Answer:* Two publishes can receive two different Pub/Sub message IDs; the business ID must stay stable.

**Question 7.** A worker commits to Cloud SQL and crashes before ACK. How do you avoid duplicate writes?

*Answer:* Write a durable marker and the business update **in the same DB transaction**, then ACK after COMMIT.

**Question 8.** A worker calls an email API inside a DB transaction. Are the email and DB atomic?

*Answer:* No. External APIs need idempotency keys and outbox/reconciliation.

**Question 9.** Subscribers in two different regions connect to Pub/Sub simultaneously. Can you claim the same exactly-once guarantee as in one region?

*Answer:* No. Pub/Sub's guarantee is regional; you need the same locational endpoint and an appropriate failover design.

**Question 10.** Is the old `ackId` still valid after a message expires its deadline and is redelivered with a new `ackId`?

*Answer:* With exactly-once, only the latest delivery's ACK ID is valid; old IDs are rejected.

**Question 11.** If combining ordering and exactly-once, can you ACK M3 before M1/M2 of the same key to speed things up?

*Answer:* You should not; ACKs must follow order, otherwise they may be rejected or cause redelivery.

**Question 12.** Does `maxDeliveryAttempts=5` guarantee a message enters the DLT on the exact fifth attempt?

*Answer:* No. DLT forwarding is best-effort, the attempt count is approximate, and proper IAM is required.

**Question 13.** Does an increase in `exactly_once_warning_count` prove Pub/Sub sent duplicates?

*Answer:* No. That metric also records invalid ACK IDs or request failures; correlate logs.

**Question 14.** Is ACKing before commit safe if you want lower latency?

*Answer:* No. A crash after ACK and before commit can lose the work.

## 19. Pre-production checklist

- [ ] Distinguished **delivery** goals from **business effects**; documented which effects require idempotency.
- [ ] Every business event has a **stable `eventId`**, not just Pub/Sub's `messageId`.
- [ ] Consumers persist durable side effects **before ACK**.
- [ ] Dedupe marker and DB update reside **in the same transaction** whenever possible.
- [ ] External APIs have appropriate idempotency keys, compensation, or reconciliation.
- [ ] If using exactly-once: **pull/StreamingPull** subscription, confirmed ACK, same region/endpoint.
- [ ] Lease extension, max outstanding messages/bytes, and worker concurrency are load-tested.
- [ ] Code never assumes an old ACK ID remains valid after redelivery.
- [ ] Ordering key is enabled only when needed, with ordered ACKs if combined with exactly-once.
- [ ] Retry, retention, DLT IAM, and poison-message handling have been rehearsed.
- [ ] If replay/seek is used, dedupe state and business rules handle old events cleanly.
- [ ] Dashboards monitor backlog, oldest age, expired ack deadlines, ack warnings, and DLT.
- [ ] Publisher/Subscriber/runtime IAM follows least privilege; no secrets in payloads/logs.
- [ ] SLOs, budget alerts, and runbooks exist for crash-window, duplicate publish, and ACK failures.

## 20. Conclusion

**At-least-once is the default; Pub/Sub's exactly-once is a scoped delivery/ACK guarantee, not a cross-system transaction.** With pull/StreamingPull in one region and confirmed ACKs, Pub/Sub prevents unexpected duplicate deliveries of the same Pub/Sub message. Yet **NACKs, deadline expirations, publisher retries, and external side effects** still require sound application design.

A reliable consumer follows a concise formula: **stable business event ID → idempotent handling via durable transaction → ACK after COMMIT → inspect ACK result → monitor retries/backlog**. That is how message delivery guarantees become verifiable business outcomes.

## Official references

- [Pub/Sub exactly-once delivery](https://cloud.google.com/pubsub/docs/exactly-once-delivery)
- [Pub/Sub subscription overview](https://cloud.google.com/pubsub/docs/subscription-overview)
- [Pub/Sub subscription properties](https://cloud.google.com/pubsub/docs/subscription-properties)
- [Pub/Sub pull subscriptions](https://cloud.google.com/pubsub/docs/pull)
- [Best practices for Pub/Sub subscribers](https://cloud.google.com/pubsub/docs/subscribe-best-practices)
- [Troubleshoot pull subscriptions](https://cloud.google.com/pubsub/docs/pull-troubleshooting)
- [Pub/Sub API endpoints and regional routing](https://cloud.google.com/pubsub/docs/reference/service_apis_overview)
- [Java sample: subscribe with exactly-once delivery](https://cloud.google.com/pubsub/docs/samples/pubsub-subscriber-exactly-once)
- [Pub/Sub message ordering](https://cloud.google.com/pubsub/docs/ordering)
- [Pub/Sub dead-letter topics](https://cloud.google.com/pubsub/docs/dead-letter-topics)
- [gcloud pubsub subscriptions create](https://cloud.google.com/sdk/gcloud/reference/pubsub/subscriptions/create)
- [Pub/Sub monitoring](https://cloud.google.com/pubsub/docs/monitoring)
- [Pub/Sub pricing](https://cloud.google.com/pubsub/pricing)
