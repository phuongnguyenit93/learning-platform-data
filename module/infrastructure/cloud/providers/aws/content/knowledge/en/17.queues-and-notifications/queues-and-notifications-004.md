# Message Groups, Deduplication, and Idempotent Consumer Design

In an e-commerce system, a Java/Spring Boot service might emit `OrderCreated`, `OrderPaid`, and `OrderCancelled` events to Amazon SQS/SNS for payment processing, inventory updates, invoicing, or notifications. Asynchronous messaging decouples services and absorbs traffic spikes. However, distributed systems face two hard failure modes: **messages arriving out of business order** and **the same event triggering side effects multiple times**.

**Amazon SQS FIFO** uses `MessageGroupId` to preserve ordering within each group and `MessageDeduplicationId` to block duplicate producer sends within a short window. Even so, **consumers can still receive a message again after a timeout or crash**, so the application must process **idempotently**: re-running the same business event must not create extra charges, duplicate invoices, or unintended state records.

This lesson belongs to the **Queues and Notifications** chapter in the **CLOUD_PROVIDERS_AWS** module; concepts connect to IAM, Regions/AZs, SQS, SNS, Lambda, ECS/EC2, DynamoDB/RDS, VPC endpoints, CloudWatch, and designing secure, resilient, observable, and cost-controlled applications.

> **Three distinct rules:** `MessageGroupId` defines **the scope where order is preserved**; `MessageDeduplicationId` prevents **producer duplicate sends for 5 minutes**; and the business `eventId` plus an idempotency store prevent **duplicate side effects even if a message is redelivered minutes or days later, or via DLQ redrive**.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Distinguish SQS Standard, SQS FIFO, and **SQS Standard fair queues**.
2. Choose the right `MessageGroupId` for orders, accounts, and tenants, recognizing concurrency limits and hot groups.
3. Distinguish `MessageDeduplicationId` from SQS `messageId`, `receiptHandle`, and `SequenceNumber`.
4. Explain the 5-minute deduplication window, content-based SHA-256 hashing, and queue/group `DeduplicationScope`.
5. Analyze why FIFO does not by itself guarantee **exactly-once business processing**.
6. Design an event envelope with `eventId`, `aggregateId`, `aggregateVersion`, and a correlation ID.
7. Implement a transactional inbox in PostgreSQL, conditional writes in DynamoDB, and a transactional outbox on the producer.
8. Use AWS SDK for Java 2.x to send FIFO messages and ack only after database commit.
9. Design SNS FIFO → multiple SQS FIFO queues and handle subscriber filtering.
10. Use Lambda event source mapping with `ReportBatchItemFailures` without breaking FIFO order.
11. Design retries, visibility timeouts, DLQ/redrive, and concurrency limits.
12. Audit IAM, encryption, VPC endpoints, CloudWatch metrics, cost, and complete a read-only lab.

## 2. SQS Standard vs. FIFO: Where Do They Differ?

| Criterion | SQS Standard | SQS FIFO |
|---|---|---|
| Ordering | Best effort; messages may arrive out of send order | Preserves order **within the same group** |
| Duplicate delivery | At-least-once | Deduplicated on enqueue for 5 minutes; consumers still need idempotency |
| `MessageGroupId` | Can be used for per-tenant **fair queues** | **Required**, defines the sequential stream |
| `MessageDeduplicationId` | Does not use the FIFO dedup mechanism | Required explicitly or via content-based dedup |
| Concurrency | High, no FIFO group locking | Independent groups can process in parallel |
| Name | E.g., `order-events` | Mandatory `.fifo` suffix |
| Best suited for | Logs, telemetry, independent jobs, tenant fairness | Order state transitions, keyed ledger/event streams |

### 2.1. Update regarding `MessageGroupId` on Standard

AWS now provides **SQS fair queues** for Standard queues. Producers can send `MessageGroupId` as a **tenant identifier**, allowing fair scheduling to curb noisy-neighbor impact from a heavy tenant.

**Do not confuse them:** a Standard fair queue **does not preserve FIFO ordering** within a group and does not serialize messages for the same tenant. Same field name, different semantics. If the application requires `OrderCreated` to apply before `OrderPaid`, use FIFO or a strong protocol versioning scheme.

## 3. `MessageGroupId` and Ordering in FIFO

With FIFO, every message belongs to a group. Suppose:

~~~text
Group order-101: A1 Created → A2 Paid → A3 Shipped
Group order-202: B1 Created → B2 Cancelled
Group order-303: C1 Created → C2 Paid
~~~

~~~mermaid
flowchart LR
  P["Producer: order service"] --> Q["SQS FIFO"]
  Q --> A["Group order-101: A1 → A2 → A3"]
  Q --> B["Group order-202: B1 → B2"]
  Q --> C["Group order-303: C1 → C2"]
  A --> W1["Worker 1"]
  B --> W2["Worker 2"]
  C --> W3["Worker 3"]
~~~

SQS preserves order **in the sequence it successfully received sends within each group**. Messages across different groups can be received and processed in parallel or interleaved non-deterministically.

**Batch note:** A single `ReceiveMessage` call can return **multiple messages from the same group** in order within **one batch** (up to 10 messages per receive). SQS will not deliver more messages from that group to another receive request until the in-flight batch is deleted or its visibility timeout expires. Inside a batch, the application must process dependent events sequentially.

### 3.1. Choosing groups by aggregate

| Strategy | Pros | Risks |
|---|---|---|
| `order-101`, `order-202` | Preserves per-order sequence, many independent groups | Requires consistent IDs across services |
| `account-456` | Preserves transaction order per account | Very busy accounts can become hot groups |
| `tenant-789` | Simple tenant isolation | A large tenant bottlenecks into a single group |
| `global` for every message | All messages serialized by broker | Low concurrency; one bad message stalls the entire queue |
| New UUID per message | Many groups, high throughput | **Loses ordering across events for the same business entity** |

**Design principle:** Each group must align with the business boundary requiring invariant preservation—typically the **aggregate root ID**. Never split one aggregate across multiple groups just for speed if update ordering matters.

### 3.2. Multiple producers sending concurrently

If Producer A sends version 5 and Producer B sends version 4 for the same group **concurrently**, SQS may record 5 followed by 4. FIFO does not know the business expects 4 before 5. Enforce **per-aggregate publication order** inside a transactional outbox/relay; consumers check **business version** to detect missing, stale, or out-of-order transitions.

The SQS-assigned `SequenceNumber` is a large, **non-contiguous** number; never use it as `aggregateVersion`. Neither `MessageId` nor `receiptHandle` replaces business sequence numbers.

## 4. Hot Groups, Head-of-Line Blocking, and High Throughput

If `A2` fails repeatedly:

~~~text
order-101: A1 [done] → A2 [DB error, retry] → A3 [waiting] → A4 [waiting]
order-202: B1 [processing] → B2 [processing later]
~~~

Group 101 suffers **head-of-line blocking**, while group 202 can still advance. A queue using only a `global` group can have all work stalled by a single poison message.

Effective concurrency is bounded by the number of eligible groups:

\[
C_{\text{effective}} \le \min(G_{\text{ready}}, C_{\text{workers}}, Q_{\text{service}})
\]

This is a modeling formula, not a specific service quota.

SQS supports **high-throughput FIFO** with:

~~~text
DeduplicationScope = messageGroup
FifoThroughputLimit = perMessageGroupId
~~~

In this mode, deduplication happens **within each group**, throughput limits apply per group, and SQS distributes groups across partitions. With `DeduplicationScope=queue` or `FifoThroughputLimit=perQueue`, the queue does not operate in that high-throughput mode.

**TPS limits vary by Region, quota, and batching.** Never lock an architecture onto an outdated static number; consult [SQS message quotas](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/quotas-messages.html). Using many independent groups and `SendMessageBatch` increases throughput, though batch APIs also return **per-entry partial failures**.

## 5. `MessageDeduplicationId` and the 5-Minute Window

FIFO handles producer send retries. Example:

~~~mermaid
sequenceDiagram
  participant P as Producer
  participant Q as SQS FIFO
  participant C as Consumer
  P->>Q: Send A, DedupId=evt-001
  Q--xP: ACK lost
  P->>Q: Retry A, DedupId=evt-001 (30 seconds)
  Q-->>P: Success but suppresses duplicate
  Q->>C: Only one A enqueued
  Note over Q: Dedup ID cached for ~5 minutes
  P->>Q: Retry A after 6 minutes
  Q->>C: A new A may appear
~~~

Once SQS accepts a `MessageDeduplicationId`, duplicate sends within **5 minutes** still receive a success ACK **without delivering a new message**. SQS retains this ID throughout that window **even after the message is received and deleted**.

**Important:** This deduplication applies only when **producers send to FIFO**; it does not prevent consumer redeliveries caused by **visibility timeouts or crashes**, nor does it last forever. Consumers must still be idempotent.

### 5.1. Queue-level vs. message-group-level dedup

| `DeduplicationScope` | Deduplication boundary | Notes |
|---|---|---|
| `queue` | Entire queue | Matching dedup IDs across two groups get suppressed |
| `messageGroup` | Within a single group | Identical IDs in **different groups** are tracked independently |
| Combined with `perMessageGroupId` | High-throughput FIFO | Requires `DeduplicationScope=messageGroup` |

For instance, `order-101` and `order-202` both emit event type `Paid`. If the dedup ID were just `Paid`, two valid events could be suppressed because the ID is **not unique**. Set the dedup ID to a **stable event instance ID**, never the event type.

## 6. Content-Based Deduplication

When `ContentBasedDeduplication=true` and the producer **omits** an explicit dedup ID, SQS computes a **SHA-256 hash of the message body**, **excluding message attributes**.

~~~json
{
  "eventId": "evt-8f20f9c7",
  "eventType": "OrderPaid",
  "aggregateId": "ord-101",
  "aggregateVersion": 5
}
~~~

Two sends with identical bodies within 5 minutes are treated as duplicates per the dedup scope. However:

- If bodies are identical while **message attributes** differ, SQS may still suppress a valid event.
- If the same business event changes timestamps, whitespace, or JSON field order, the byte hash changes and it will not be deduplicated.
- An **explicit `MessageDeduplicationId`** takes precedence over content hashing when supplied.

For order systems, generate `eventId` inside the source transaction and put it both in the body and in the explicit dedup ID, keeping it constant across retries. Any genuinely new event with similar content must have a **new `eventId`**.

### 6.1. Bad choices

| Dedup ID | Why is it wrong? |
|---|---|
| Current timestamp on every retry | Every retry looks like a brand-new event |
| `OrderPaid` for all orders | Suppresses independent events |
| Fresh UUID on every `SendMessage` attempt | Defeats retry protection |
| Static customer ID | Two distinct transactions within 5 minutes get dropped as duplicates |
| SQS `MessageId` as send-side dedup key | `MessageId` is only assigned **after send**, useless when an ACK is lost |

## 7. FIFO Does Not Automatically Deliver Exactly-Once Business Processing

Distinguish two separate mechanisms:

- **Duplicate suppression at enqueue:** SQS FIFO prevents the same dedup ID from entering the queue twice within 5 minutes.
- **Exactly-once business side effects:** consumer databases, payments, and emails must not be applied repeatedly across retries, timeouts, and redrives.

A very common timeline:

~~~mermaid
sequenceDiagram
    participant Q as SQS FIFO
    participant C as Consumer
    participant D as PostgreSQL
    Q->>C: Deliver A (receiptHandle h1)
    C->>D: Update OrderPaid and COMMIT
    D-->>C: Commit succeeded
    Note over C: Crash before DeleteMessage
    Q->>Q: Visibility timeout expires
    Q->>C: Redeliver A (receiptHandle h2)
    C->>D: Check inbox eventId → already processed
    D-->>C: No-op
    C->>Q: DeleteMessage with h2
~~~

SQS **does not** share transactions with RDS. If a consumer commits to the database and dies before deleting the message, the message will be delivered again. Similarly, Lambda event source mapping is **at-least-once** and can retry records. Therefore, never claim “SQS FIFO guarantees once-only database updates” unless you have implemented an **idempotency protocol**.

## 8. Event Envelope and Three Types of IDs

Recommended payload:

~~~json
{
  "schemaVersion": 1,
  "eventId": "evt-8f20f9c7",
  "eventType": "OrderPaid",
  "aggregateType": "Order",
  "aggregateId": "ord-101",
  "aggregateVersion": 5,
  "occurredAt": "2026-11-20T09:30:00Z",
  "correlationId": "req-2d5e78",
  "data": {
    "currency": "VND",
    "amountMinor": 250000
  }
}
~~~

| Key | Purpose |
|---|---|
| `eventId` | Business idempotency key, constant across all retries/republishes |
| `aggregateId` | Message group candidate, e.g., `order-{aggregateId}` |
| `aggregateVersion` | Enforces invariants and detects gaps or stale updates |
| `correlationId` | Distributed tracing across producer → queue → consumer |
| `schemaVersion` | Manages schema evolution |
| `eventType` | Routes to the right consumer handler |
| `occurredAt` | Audit/latency tracking; **never replaces sequence numbers** |

**Never use SQS `messageId` alone as the business idempotency key**: when the same business event is republished after the dedup window, SQS assigns a **new `messageId`**. Independent consumers should key by **`(consumer_name, event_id)`**, since both Billing and Notification must process the same `eventId` for different purposes.

Never put plaintext secrets or PII in event bodies, group IDs, or logs. Use internal business IDs or opaque identifiers.

## 9. What Is an Idempotent Consumer?

Processing event `e` over state `S` is idempotent if:

\[
f(f(S,e),e)=f(S,e)
\]

Re-executing the **same business event** produces no unintended extra effects. This **does not mean the consumer is never invoked twice**.

| Pattern | Example | Limitations |
|---|---|---|
| Naturally idempotent | Setting status to `PAID` instead of incrementing a counter | Audit/email/ledger side effects may still duplicate |
| Unique business key | `UNIQUE(provider_payment_id)` | Requires transactions and unique violation handling |
| Transactional inbox | Writing processed marker + state in same DB transaction | Not atomic with external APIs |
| Conditional state change | Update only if `version=expectedVersion` | Must handle gaps and replays |
| DynamoDB `TransactWriteItems` | Atomically Put dedup key + Update business item | Applies only within supported transaction scope |
| External idempotency key | Payment provider accepts `Idempotency-Key` | Subject to provider retention windows |
| Transactional outbox | Commit domain state + outbox event in same DB transaction | Relay can double-publish; consumer still needs idempotency |

### 9.1. The “check then act” trap

~~~text
if (NOT processed(eventId)) {
    charge_card();
    save_processed(eventId);
}
~~~

Unsafe because two consumers can concurrently observe `processed=false` and both charge the card. Use a **unique constraint + transaction** to serialize races, and pass a stable provider-level idempotency key to external payment APIs.

### 9.2. Idempotency retention horizon

Dedup markers must be retained across the **business replay horizon**, not just 5 minutes. Account for SQS retention, DLQ redrives days later, producer outbox retries, regulatory/audit retention, and payment provider windows. If DynamoDB TTL deletes a marker, an old event replayed afterward can bypass dedup; financial flows require **permanent business invariants** such as unique ledger references.

## 10. Transactional Inbox with PostgreSQL

For consumer `billing-projection` updating a read model after `OrderPaid`, create tables:

~~~sql
CREATE TABLE consumer_inbox (
  consumer_name VARCHAR(120) NOT NULL,
  event_id VARCHAR(160) NOT NULL,
  processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (consumer_name,event_id)
);

CREATE TABLE order_projection (
  order_id VARCHAR(100) PRIMARY KEY,
  status VARCHAR(40) NOT NULL,
  aggregate_version BIGINT NOT NULL
);
~~~

Processing steps inside **one database transaction**:

1. `INSERT INTO consumer_inbox ... ON CONFLICT DO NOTHING`.
2. If **0 rows** inserted, the event was already processed; **skip business side effects**, commit, and ACK.
3. If **1 row** inserted, validate the event version and update business tables.
4. **COMMIT** both the marker and state together.
5. **Only after COMMIT**, call SQS `DeleteMessage`.

Illustrative SQL:

~~~sql
BEGIN;

INSERT INTO consumer_inbox (consumer_name,event_id)
VALUES ('billing-projection','evt-8f20f9c7')
ON CONFLICT DO NOTHING;

-- Application inspects inserted row count:
-- 0 => DUPLICATE, skip business update.
-- 1 => proceed with processing.

INSERT INTO order_projection(order_id,status,aggregate_version)
VALUES ('ord-101','PAID',5)
ON CONFLICT(order_id)
DO UPDATE SET
 status=EXCLUDED.status,
 aggregate_version=EXCLUDED.aggregate_version
WHERE order_projection.aggregate_version < EXCLUDED.aggregate_version;

COMMIT;
~~~

This SQL is an **illustrative scenario**, not a standalone transaction script, because branching on 0 vs. 1 inserted row must happen in application code or a stored procedure. If the business cannot skip version 4 when version 5 arrives, enforce **expected version + 1** and handle gaps instead of simply checking `<`.

### 10.1. Failure-window analysis

| When does the crash occur? | DB state | Retry behavior |
|---|---|---|
| Before COMMIT | Transaction rolls back | Applies cleanly on retry |
| After COMMIT, before `DeleteMessage` | State and inbox committed | Duplicate key → no-op, then delete |
| `DeleteMessage` fails | DB is already consistent | Retry → no-op, then delete |
| Delete **before** DB commit | Message lost while state uncommitted | **Broken design** |

**Never** ACK/delete before the business commit. Keep the inbox marker and business update in the exact same transaction.

## 11. Java Consumer with JDBC and AWS SDK v2

Below is a skeleton for **processing one message** (omitting JSON parsing, network retries/backoff, scheduling, and runbooks). Using Java 21 records:

~~~java
public record OrderEvent(
        String eventId,
        String aggregateId,
        String status,
        long aggregateVersion
) {}
~~~

The code below ensures inbox/state atomicity before ACKing SQS:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.DeleteMessageRequest;
import software.amazon.awssdk.services.sqs.model.Message;

public final class OrdersConsumer {
    private final DataSource db;
    private final SqsClient sqs;
    private final String queueUrl;

    public OrdersConsumer(DataSource db, SqsClient sqs, String queueUrl) {
        this.db = db;
        this.sqs = sqs;
        this.queueUrl = queueUrl;
    }

    public void process(Message message, OrderEvent event) throws SQLException {
        if (event.eventId() == null || event.eventId().isBlank()) {
            throw new IllegalArgumentException("Missing event ID");
        }
        try (Connection conn = db.getConnection()) {
            conn.setAutoCommit(false);
            try {
                int inserted;
                try (PreparedStatement p = conn.prepareStatement(
                        "INSERT INTO consumer_inbox(consumer_name,event_id) "
                      + "VALUES(?,?) ON CONFLICT DO NOTHING")) {
                    p.setString(1, "billing-projection");
                    p.setString(2, event.eventId());
                    inserted = p.executeUpdate();
                }

                if (inserted == 1) {
                    try (PreparedStatement p = conn.prepareStatement(
                            "INSERT INTO order_projection(order_id,status,aggregate_version) "
                          + "VALUES(?,?,?) "
                          + "ON CONFLICT(order_id) DO UPDATE SET "
                          + "status=EXCLUDED.status, "
                          + "aggregate_version=EXCLUDED.aggregate_version "
                          + "WHERE order_projection.aggregate_version "
                          + "< EXCLUDED.aggregate_version")) {
                        p.setString(1, event.aggregateId());
                        p.setString(2, event.status());
                        p.setLong(3, event.aggregateVersion());
                        p.executeUpdate();
                    }
                }
                conn.commit();
            } catch (SQLException ex) {
                conn.rollback();
                throw ex;
            } catch (RuntimeException ex) {
                conn.rollback();
                throw ex;
            }
        }
        // ACK only after transaction commit or confirmed duplicate.
        sqs.deleteMessage(DeleteMessageRequest.builder()
                .queueUrl(queueUrl)
                .receiptHandle(message.receiptHandle())
                .build());
    }
}
~~~

**Limitations of this example:** The code illustrates a read projection that safely ignores older versions when `WHERE aggregate_version < ...` does not match. Strict state machines must verify exact prior/next versions and handle gaps. Validate `status`, `aggregateId`, schemas, authorization, and business rules before updating the DB. Add retries, metrics, input validation, monitoring, shutdown hooks, and DB-appropriate transaction isolation. External payment/notification APIs **cannot** be made atomic solely via a PostgreSQL transaction; pair them with partner idempotency keys and outbox/reconciliation.

### 11.1. Long polling is not a “harmless read”

~~~java
import java.util.List;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.ReceiveMessageRequest;
import software.amazon.awssdk.services.sqs.model.Message;

public final class ReceiveLoopExample {
    public static void main(String[] args) {
        String url = System.getenv("ORDERS_FIFO_QUEUE_URL");
        try (SqsClient sqs = SqsClient.create()) {
            while (!Thread.currentThread().isInterrupted()) {
                List<Message> batch = sqs.receiveMessage(
                        ReceiveMessageRequest.builder()
                            .queueUrl(url)
                            .waitTimeSeconds(20)
                            .maxNumberOfMessages(10)
                            .build())
                    .messages();
                for (Message m : batch) {
                    // Parse event then invoke idempotent consumer.
                    // On error: do not ACK uncommitted records.
                    // Preserve ordering within each FIFO group.
                }
            }
        }
    }
}
~~~

`ReceiveMessage` turns messages **invisible**, increments receive counts, and can lock FIFO groups. Never run a skeleton loop against a production queue without real business processing and monitoring.

## 12. DynamoDB Conditional Writes and Transactions

If storing processed markers in DynamoDB:

~~~text
PK = CONSUMER#billing-projection#EVENT#evt-8f20f9c7
status = COMPLETED
processedAt = 2026-11-20T09:30:12Z
expiresAt = ...
~~~

A `PutItem` with condition `attribute_not_exists(pk)` prevents two workers from both creating the marker. However, if the business update lives elsewhere, the marker **does not guarantee atomicity**.

When both the marker and state reside in DynamoDB, use **`TransactWriteItems`**:

~~~text
Transaction:
  1. Put inbox key if attribute_not_exists(pk)
  2. Update order state if version matches
Result: both succeed or both fail.
~~~

If the transaction fails because the marker already exists, you can treat it as a duplicate after verifying the key/state. Never treat **every** conditional failure as a duplicate: a business version mismatch can indicate data inconsistency.

**TTL cleanup is not instantaneous**, and once a marker is purged, replaying an old event can pass dedup; payments and ledgers need long-lived unique references.

## 13. Transactional Outbox for Producers

An idempotent consumer solves the **receiving side**, yet producers also have a gap:

~~~text
UPDATE orders SET status='PAID';
COMMIT;
publish OrderPaid to SNS/SQS;   // Crash before publish → lost event.
~~~

Reversing the order (publishing before COMMIT) risks emitting events for rolled-back transactions. Use a **transactional outbox**:

1. Inside the same DB transaction, update `orders`.
2. Insert `outbox_events(event_id, aggregate_id, version, payload, status)`.
3. Commit both.
4. A relay/CDC reads the outbox and publishes with `MessageGroupId=aggregateId` and `MessageDeduplicationId=eventId`.
5. The relay marks the row published; if it crashes before marking, **it may publish again**.
6. Consumer inboxes handle duplicate business events.

~~~mermaid
flowchart LR
    API["Order API"] --> TX["PostgreSQL transaction"]
    TX --> ORD["orders table"]
    TX --> OUT["outbox_events"]
    OUT --> REL["Relay / CDC"]
    REL --> SNS["SNS/SQS FIFO"]
    SNS --> CON["Idempotent consumer"]
    CON --> DB["Consumer business DB"]
~~~

**Outbox does not mean exactly-once publishing.** It closes the risk of **DB committed but event never published**; the relay can still send twice, especially after a lost ACK. Maintain per-aggregate publication order so version 5 is never emitted before version 4 when multiple relay workers run.

## 14. SNS FIFO Fan-Out to Multiple SQS FIFO Queues

One event must reach Billing, Inventory, and Notifications:

~~~mermaid
flowchart TD
    PUB["Order service + outbox"] --> TOPIC["SNS FIFO: order-events.fifo"]
    TOPIC --> BILL["SQS FIFO: billing.fifo"]
    TOPIC --> INV["SQS FIFO: inventory.fifo"]
    TOPIC --> NOT["SQS FIFO: notification.fifo"]
    BILL --> B["Billing consumer + inbox"]
    INV --> I["Inventory consumer + inbox"]
    NOT --> N["Notification consumer + inbox"]
~~~

SNS FIFO forwards **`MessageGroupId`** to subscribed SQS FIFO queues to preserve per-group order under service conditions. Each subscriber maintains its own queue, retries, and idempotency. If an **SQS Standard** queue subscribes instead, strict FIFO consumer ordering is lost.

### 14.1. SNS `FifoThroughputScope`

SNS FIFO uses the attribute:

- `Topic`: deduplication at topic scope; the default per documentation.
- `MessageGroup`: deduplication per group, enabling high throughput.

Per current AWS documentation, once `FifoThroughputScope` is changed to `MessageGroup`, **it cannot be reverted back to `Topic`**. Decide carefully before modifying production. With high-throughput SNS FIFO, consider enabling high-throughput SQS FIFO on subscribed queues as well.

### 14.2. Subscription filtering and delivery

SNS FIFO supports filtering on message attributes or body. When filtering is enabled, never promise “every event reaches every queue”: filters drop non-matching events, and AWS notes **at-most-once** caveats for filtered subscriptions.

SNS FIFO does not deliver directly to Standard-style email/SMS/HTTP(S) endpoints while preserving strict FIFO guarantees. To process SNS FIFO with Lambda, use **SNS FIFO → SQS FIFO → Lambda**; to send emails, have the worker call SES/notification APIs with idempotency logic.

### 14.3. SQS queue policy for SNS

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowOneSnsFifoTopic",
      "Effect": "Allow",
      "Principal": { "Service": "sns.amazonaws.com" },
      "Action": "sqs:SendMessage",
      "Resource": "arn:aws:sqs:ap-southeast-1:111122223333:billing.fifo",
      "Condition": {
        "ArnEquals": {
          "aws:SourceArn": "arn:aws:sns:ap-southeast-1:111122223333:order-events.fifo"
        }
      }
    }
  ]
}
~~~

IDs and ARNs are illustrative. With SSE-KMS, check key policies too. Never allow arbitrary SNS topics to send to the billing queue when only one topic is authorized.

## 15. Lambda Consumers for SQS FIFO and Partial Batch Failures

Lambda event source mapping polls the queue and invokes your function with batches, **at least once**. If a batch processes A1/A2 successfully but fails on A3, and the handler **throws an exception**, the **entire batch** can be retried. Seeing A1/A2 again is normal—the consumer must be idempotent.

Enable on the event source mapping:

~~~text
FunctionResponseTypes = ["ReportBatchItemFailures"]
~~~

The handler returns `batchItemFailures` containing the `messageId`s to retry. For FIFO:

1. Process the batch **in order**.
2. On the first record failure, **stop processing subsequent records** (the safest strategy).
3. Return the **`messageId` of the failed record plus every unprocessed record**.
4. Only records before the failure are deleted by Lambda.
5. Do not throw an uncaught exception after constructing a partial response; throwing marks the **entire batch** failed.

### 15.1. Java Lambda handler

~~~java
import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;
import com.amazonaws.services.lambda.runtime.events.SQSEvent;
import com.amazonaws.services.lambda.runtime.events.SQSBatchResponse;
import java.util.ArrayList;
import java.util.List;

public final class OrderedFifoHandler
        implements RequestHandler<SQSEvent, SQSBatchResponse> {

    @Override
    public SQSBatchResponse handleRequest(SQSEvent event, Context context) {
        List<SQSBatchResponse.BatchItemFailure> failures = new ArrayList<>();
        List<SQSEvent.SQSMessage> batch = event.getRecords();
        for (int i = 0; i < batch.size(); i++) {
            SQSEvent.SQSMessage message = batch.get(i);
            try {
                processIdempotently(message);
            } catch (Exception ex) {
                context.getLogger().log(
                    "Batch failed at messageId=" + message.getMessageId());
                // FIFO: do not process records after the first failure.
                for (int j = i; j < batch.size(); j++) {
                    failures.add(new SQSBatchResponse.BatchItemFailure(
                        batch.get(j).getMessageId()));
                }
                break;
            }
        }
        return new SQSBatchResponse(failures);
    }

    private void processIdempotently(SQSEvent.SQSMessage msg) {
        // TODO: Validate event + transactional inbox + business processing.
        throw new UnsupportedOperationException("Implement consumer");
    }
}
~~~

**Note:** This is a **skeleton**; `processIdempotently` is intentionally unimplemented and always fails—never deploy it verbatim. `SQSEvent`/`SQSBatchResponse` come from `aws-lambda-java-events`. If optimizing per-group within a batch, ensure a failed group skips all later records in that group and returns exact failure IDs.

**Lambda FIFO concurrency** is capped by active groups, event source mapping maximum concurrency, reserved concurrency, and service quotas. Provisioning 100 workers will not make a `global` group process 100 messages concurrently.

## 16. Visibility Timeout, Receipt Handles, and Retries

When a consumer calls `ReceiveMessage`, the message **stays in the queue but is temporarily hidden**. `VisibilityTimeout` defaults to **30 seconds**, configurable up to **12 hours**.

- If `DeleteMessage` is not called before timeout expiration, the message can be redelivered.
- Use `ChangeMessageVisibility` to extend during long jobs; never exceed **12 hours total from the initial receive**.
- Size timeout from P99 processing time + network jitter—neither too short (premature redelivery) nor too long (group stalled too long).
- `ReceiptHandle` **changes on every receive**; always delete with the current handle rather than caching an old handle.
- `ReceiveRequestAttemptId` helps safely retry FIFO receive requests per API semantics; it is **not** a business dedup key.

For Lambda SQS mappings, AWS requires **Lambda timeout ≤ queue visibility timeout**, and generally recommends queue visibility of at least **6 × function timeout**, plus the batching window if set, to absorb throttling/retries. This is an operational guideline, not a consumer exactly-once guarantee.

## 17. Dead-Letter Queues and Redrive Without Breaking Business Order

A poison message failing repeatedly can be routed to a **dead-letter queue (DLQ)** via `maxReceiveCount`. For a FIFO source, use a **FIFO DLQ** per AWS rules, typically in the same account and Region.

~~~mermaid
flowchart LR
    Q["SQS FIFO source"] --> C["Idempotent consumer"]
    C -->|"Commit + Delete"| DONE["Done"]
    C -->|"Fail, visibility expires"| Q
    Q -->|"maxReceiveCount exceeded"| DLQ["SQS FIFO DLQ"]
    DLQ --> REVIEW["Triage + approved redrive"]
    REVIEW --> Q
~~~

**Major warning:** Moving version 3 of `order-A` to a DLQ while continuing to process version 4 can break **business ordering**, even on FIFO. AWS explicitly cautions that **DLQs are unsuitable for flows where every step must execute strictly sequentially** without reconciliation.

When redriving messages from a DLQ, they can **interleave with newly arriving events** in the source queue. SQS can also alter dedup IDs when moving FIFO → FIFO DLQ, so preserve a **stable `eventId` in the body**, business versions, and a replay runbook.

Appropriate recovery steps:

1. Classify transient failures, poison payloads, or permission/network issues.
2. Retain the DLQ long enough for analysis; restrict access to bodies containing PII.
3. Fix the consumer, schema, or permissions and test against representative messages.
4. For strict state machines, **pause or coordinate** producers/consumers for the affected group during replay if needed.
5. Enforce `aggregateVersion` checks to reject stale versions after newer ones.
6. Monitor DLQ backlog and perform business reconciliation after redrive.

SQS retention is configurable from **1 minute to 14 days**, defaulting to **4 days**. Never let messages expire while the team is still investigating.

## 18. Java Producer with AWS SDK v2

Example sending an event with an ID kept constant across retries:

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.SendMessageRequest;

public final class OrderPublisher {
    public static void main(String[] args) {
        String queueUrl = System.getenv("ORDERS_FIFO_QUEUE_URL");
        String eventId = "evt-8f20f9c7";
        String orderId = "ord-101";
        String payload = """
          {"eventId":"evt-8f20f9c7","eventType":"OrderPaid",
           "aggregateId":"ord-101","aggregateVersion":5}
          """;

        try (SqsClient sqs = SqsClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build()) {
            var result = sqs.sendMessage(
                SendMessageRequest.builder()
                    .queueUrl(queueUrl)
                    .messageGroupId("order-" + orderId)
                    .messageDeduplicationId(eventId)
                    .messageBody(payload)
                    .build());
            System.out.println("Accepted SQS messageId=" + result.messageId());
        }
    }
}
~~~

**This operation has real side effects** when pointed at a valid queue and IAM role: it can trigger business processing and billing. Never run it against a production queue just to “test syntax”. Pull `eventId` from the **outbox record** rather than generating a new UUID on every relay retry. The SDK uses the default credentials chain (ECS/EC2/EKS IAM role or dev profile); never hardcode AWS secret keys.

`SendMessageBatch` cuts overhead, but each response reports **per-entry successes and failures**; retry failed entries with stable dedup IDs. Never assume HTTP 200 on a batch means every message published successfully.

## 19. IAM, Encryption, Networking, and Auditing

| Role | Key IAM actions | Scope |
|---|---|---|
| SQS producer | `sqs:SendMessage` | Exact queue ARN |
| SNS publisher | `sns:Publish` | Exact topic ARN |
| ECS/EC2 consumer | `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:ChangeMessageVisibility`, `sqs:GetQueueAttributes` | Exact queue ARN |
| Lambda SQS event source role | `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:GetQueueAttributes` | Source queue; KMS permissions when needed |
| SNS → SQS policy | `sqs:SendMessage` for `sns.amazonaws.com` | Queue policy scoped by topic `aws:SourceArn` |
| DLQ operator | `sqs:StartMessageMoveTask`/`sqs:CancelMessageMoveTask` and related permissions | Elevated permission requiring approval |

**SSE-SQS/SSE-KMS** protects data at rest, but does not replace TLS, IAM, input validation, or idempotency. With a customer-managed KMS key, verify `kms:GenerateDataKey`, `kms:Decrypt`, and key policy grants for producers, consumers, and AWS services along the path.

An ECS worker in a private subnet without NAT can call AWS APIs via **Interface VPC Endpoints**, for example:

~~~text
com.amazonaws.ap-southeast-1.sqs
com.amazonaws.ap-southeast-1.sns
~~~

Configure endpoint security group inbound TCP 443, Private DNS, routes/NACLs, and IAM/endpoint policies. **Lambda SQS event source mapping** is polled by the Lambda service itself—unlike function code explicitly calling the SQS API—so you do not need an SQS VPC endpoint *just for event source mapping polling*.

Keep CloudTrail for control-plane API auditing, CloudWatch for metrics/logs, and business `eventId`/`correlationId` for tracing. Never log full payloads containing PII or credentials.

## 20. Read-Only AWS CLI: Inspecting Queue and Topic Config

Examples use profile `dev`, Region `ap-southeast-1`, and placeholder account `111122223333`. Replace URLs and ARNs with authorized resources before running.

### 20.1. Identity and queue list

~~~bash
aws sts get-caller-identity \
  --profile dev \
  --query '{Account:Account,Arn:Arn}' \
  --output json

aws sqs list-queues \
  --queue-name-prefix orders- \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

### 20.2. Reading queue attributes

~~~bash
aws sqs get-queue-attributes \
  --queue-url https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders.fifo \
  --attribute-names \
    QueueArn FifoQueue ContentBasedDeduplication \
    DeduplicationScope FifoThroughputLimit \
    VisibilityTimeout MessageRetentionPeriod RedrivePolicy \
    ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

| Attribute | How to interpret |
|---|---|
| `FifoQueue` | Is the queue truly FIFO? |
| `ContentBasedDeduplication` | Uses automatic body SHA-256 when explicit dedup ID is omitted? |
| `DeduplicationScope` | `queue` or `messageGroup`? |
| `FifoThroughputLimit` | `perQueue` or `perMessageGroupId`? |
| `VisibilityTimeout` | Long enough for P99 worker/Lambda processing? |
| `MessageRetentionPeriod` | Sufficient triage and recovery window? |
| `RedrivePolicy` | DLQ/`maxReceiveCount` and impact on ordering? |

`ApproximateNumberOfMessages` is an **estimate**, not an exact count of business transactions.

### 20.3. SNS FIFO topic/subscription

~~~bash
aws sns get-topic-attributes \
  --topic-arn arn:aws:sns:ap-southeast-1:111122223333:order-events.fifo \
  --profile dev \
  --region ap-southeast-1 \
  --output json

aws sns list-subscriptions-by-topic \
  --topic-arn arn:aws:sns:ap-southeast-1:111122223333:order-events.fifo \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

Check `FifoTopic`, `ContentBasedDeduplication`, `FifoThroughputScope`, and filter policies. When inspecting exact filter rules, call `get-subscription-attributes` with the subscription ARN.

### 20.4. Lambda event source mapping

~~~bash
aws lambda list-event-source-mappings \
  --event-source-arn arn:aws:sqs:ap-southeast-1:111122223333/orders.fifo \
  --profile dev \
  --region ap-southeast-1 \
  --query 'EventSourceMappings[].{UUID:UUID,State:State,BatchSize:BatchSize,FunctionResponseTypes:FunctionResponseTypes,Scaling:ScalingConfig}' \
  --output json
~~~

### 20.5. Never treat `ReceiveMessage` as a read-only operation

`ReceiveMessage` **makes messages invisible** for the timeout and **increments the receive count**. If a queue has a DLQ, a casual “peek” pushes messages closer to `maxReceiveCount`. Use `GetQueueAttributes` or CloudWatch for inspection, or only call receive on an authorized lab queue.

## 21. Console and CLI: Creating and Sending Messages (State-Mutating)

### 21.1. Configuring a FIFO queue via Console

In SQS → Create queue:

1. Select **FIFO**, named `orders.fifo`.
2. Choose content-based dedup appropriately or standardize on explicit event IDs.
3. If high throughput is needed, set `DeduplicationScope=messageGroup` and `FifoThroughputLimit=perMessageGroupId`.
4. Set visibility timeout and retention based on SLAs rather than blindly keeping defaults.
5. Configure a FIFO DLQ, `maxReceiveCount`, and redrive procedures preserving business order.
6. Configure encryption, queue policies, and CloudWatch alarms.
7. Test error and duplicate handling in dev before taking live traffic.

### 21.2. Example `SendMessage` (run only on a lab queue)

~~~bash
# SENDS A REAL MESSAGE - can trigger business work; do not run in production.
aws sqs send-message \
  --queue-url https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders.fifo \
  --message-body '{"eventId":"evt-8f20f9c7","eventType":"OrderPaid","aggregateId":"ord-101","aggregateVersion":5}' \
  --message-group-id order-ord-101 \
  --message-deduplication-id evt-8f20f9c7 \
  --profile dev \
  --region ap-southeast-1
~~~

### 21.3. Lambda partial batch flag (state-mutating)

~~~bash
# Only after the handler properly implements SQSBatchResponse.
aws lambda update-event-source-mapping \
  --uuid 00000000-0000-0000-0000-000000000001 \
  --function-response-types ReportBatchItemFailures \
  --profile dev \
  --region ap-southeast-1
~~~

`UUID` is a placeholder. If the handler still throws exceptions outward, the flag **will not automatically stop** duplicate processing.

## 22. Monitoring, SLOs, and Cost

### 22.1. Key metrics

| Source | Suggested metrics | Purpose |
|---|---|---|
| SQS | `ApproximateNumberOfMessagesVisible` | Backlog |
| SQS | `ApproximateNumberOfMessagesNotVisible` | In-flight messages |
| SQS | `ApproximateAgeOfOldestMessage` | Processing latency |
| SQS | `NumberOfMessagesSent`/`Received`/`Deleted` | API trends, not unique business counts |
| DLQ | Message count/age and redrive failures | Poison events |
| Lambda | `Errors`, `Duration`, `Throttles`, concurrency | Failures, retries, concurrency |
| App | `inbox_duplicate`, `event_processing_lag_seconds`, per-group lag | Actual duplicates and ordering |
| DB | Transaction conflicts, unique violations, lock wait time | Idempotency store health |
| SNS | Publish/delivery failure metrics | Fan-out reliability |

Never use `SQS Approximate*` metrics to prove once-only payment execution. Use **ledgers and business reconciliation** to verify.

### 22.2. Logging/Tracing

Log `eventId`, `aggregateId`, `aggregateVersion`, `correlationId`, SQS `messageId`/`ApproximateReceiveCount` (if available), consumer name, and outcome:

~~~text
consumer=billing-projection
eventId=evt-8f20f9c7
aggregateId=ord-101
groupId=order-ord-101
outcome=APPLIED | DUPLICATE_SKIPPED | RETRY | DLQ
~~~

Never log payment cards, tokens, or full event payloads containing PII.

### 22.3. Cost

| Component | Potential charges |
|---|---|
| SQS Standard/FIFO | API calls, payload billing, data transfer |
| SNS FIFO | Publish/delivery, data transfer |
| Lambda | Invocations, duration, provisioned polling mode if used |
| RDS/DynamoDB | Inbox/outbox reads/writes, transactions, retention |
| KMS | SSE-KMS keys and API usage |
| PrivateLink/NAT | Endpoint-hours/data processing, Internet egress |
| CloudWatch/CloudTrail | Logs, metrics, alarms, auditing |
| DLQ/retention | Retry calls and storage for unprocessed messages |

A queue with 20 independent groups and 50 workers will not necessarily run faster than 20 workers. Tune around **latency, retry rate, and effective group cardinality**, not just thread counts.

## 23. Troubleshooting by Symptom

| Symptom | Possible cause | Resolution |
|---|---|---|
| FIFO `SendMessage` complains of missing group/dedup | Missing group or omitted dedup when content-based is off | Supply stable IDs |
| Two independent orders produce only one queued event | Duplicate dedup ID under `queue` scope | Use unique event IDs; check queue attributes |
| Retry after 6 minutes creates a new message | 5-minute dedup window expired | Rely on consumer inbox/business keys |
| Order version 5 arrives before 4 | Multiple producers publishing out of order | Per-aggregate relay ordering, version checks |
| One group is blocked | Poison event / visibility timeout | Triage, DLQ with order-aware runbook |
| FIFO queue has low parallelism | Too few groups or `global` group | Design aggregate-based group IDs |
| Standard fair queue does not preserve order | Standard `MessageGroupId` only provides fairness semantics | Choose FIFO if ordering is required |
| Same invoice generated twice | DB commit then SQS redelivery, missing inbox | Atomic unique marker + business transaction |
| Inbox shows processed, but business data missing | Marker committed in a separate transaction | Commit both in the same transaction |
| Duplicate charge despite valid inbox | External charge not inside DB transaction | Provider idempotency key, reconciliation |
| Succeeded Lambda batch records get retried | Whole batch threw / missing partial failures | `ReportBatchItemFailures`, FIFO stop on failure |
| Messages moved to DLQ replay out of order | Redrive interleaved with new messages | Version-aware reconciliation |
| Lab `ReceiveMessage` alters backlog | Receive hides messages and increments receive count | Read attributes/metrics instead |
| SNS FIFO fails to reach queue | Subscription filter, queue policy, KMS | Check `SourceArn`, filters, DLQ |
| SQS `AccessDenied` | IAM / queue policy / KMS / VPCE deny | Verify caller, ARN, endpoint policy |
| Consumer delete fails | Stale receipt handle or missing IAM `DeleteMessage` | Use current handle and verify role permissions |
| High throughput not active | Wrong attributes | Set `DeduplicationScope`/`FifoThroughputLimit` |
| Messages vanish after several days | Retention expired, unmonitored DLQ | Align retention/SLO, set redrive/alarms |

### 23.1. Diagnostic workflow

1. Verify AWS account, Region, queue/topic ARN, and FIFO vs. Standard type.
2. Inspect `MessageGroupId`, `MessageDeduplicationId`, `DeduplicationScope`, and content-based settings.
3. Check business `eventId`/`aggregateId`/`aggregateVersion` in the outbox/payload.
4. Inspect consumer transactions, unique constraints, and ack/delete timing.
5. For Lambda, verify batch failure responses, mapping, concurrency, and visibility.
6. For SNS, verify topic subscription filters, queue policies, and KMS.
7. Cross-check CloudWatch + business DB + DLQ; replay via runbook instead of opening wildcard permissions.

## 24. Scenario Practice and Self-Assessment Questions

### 24.1. Real-world scenario

An Order API on ECS accepts orders. PostgreSQL stores state and an outbox. SNS FIFO fans out events to three FIFO queues: Billing, Inventory, and Notification. Requirements:

- `OrderCreated` before `OrderPaid` and `OrderShipped` **for the same order**.
- Different orders process in parallel.
- Producer or Lambda crashes must never double-charge.
- DLQ replays must never apply an older version over a newer version.

Design:

1. `MessageGroupId=order-{aggregateId}`.
2. `MessageDeduplicationId=eventId`, constant across retries.
3. Producer transactional outbox committed with the business transaction; relay preserves per-aggregate order.
4. Each consumer maintains a unique inbox key `(consumerName,eventId)`.
5. Business updates and inbox markers are atomic; external charges include provider idempotency keys.
6. Lambda partial batch responses + FIFO stop after first error.
7. SQS visibility timeout/DLQ sized to SLAs, with version-aware redrive.
8. Metrics for backlog, lag, duplicates, and DB conflicts, plus least-privilege IAM.

### 24.2. Exercises

**A.** A1/A2/A3 are in `order-101`; B1/B2 are in `order-202`. A2 fails for 90 seconds. Must B2 wait for A2? **No**, different groups. Must A3 wait for A2? **Yes**.

**B.** Producer sends `eventId=X`, times out, retries after 30 seconds, then retries again after 6 minutes. How many valid business effects should occur? **One**, thanks to the idempotent consumer; the broker suppresses the 30-second send, but does not guarantee suppression at 6 minutes.

**C.** Billing and Inventory both receive `eventId` X. Should they share a single `unique(eventId)` table? **No** if shared across services; key by **`(consumerName,eventId)`**.

**D.** Lambda finishes writing to the DB and crashes before delete. Is that an SQS bug? **No**; redelivery is expected. The consumer safely no-ops via its inbox.

**E.** Using group `global` for one million orders. Will raising Lambda concurrency scale throughput proportionally? **No**; one group enforces strict sequential execution.

**F.** Redriving version 3 from a DLQ after version 4 already committed. Should state revert to version 3? **No**; enforce version invariants and reconciliation.

### 24.3. Read-only CLI lab

Use the commands from section 20 to fill in:

| Configuration | Observed value | Conclusion |
|---|---|---|
| FIFO/Standard | `FifoQueue` | Does it guarantee per-group order? |
| Dedup scope | `queue/messageGroup` | Is there risk of suppressing events in other groups? |
| Content dedup | `true/false` | Must producers pass explicit IDs? |
| Visibility | Seconds | Sufficient for P99 worker latency? |
| DLQ | `RedrivePolicy` | Are invariants preserved during replay? |
| Lambda mapping | `FunctionResponseTypes` | Is partial failure response enabled? |
| SNS topic | `FifoThroughputScope` | Are dedup scope and topic throughput right? |
| Authorization | IAM/queue policy/KMS | Does it follow least privilege? |

**No real messages need to be sent, received, deleted, or redriven** to complete this lab.

### 24.4. Self-check questions

1. Does SQS Standard have `MessageGroupId`, and what is it used for?
2. Does FIFO preserve order across the entire queue or per group?
3. Can you receive from only one group via an API parameter?
4. Can `SequenceNumber` be used as a business aggregate version?
5. How do `MessageDeduplicationId` and `eventId` differ in purpose?
6. How long is the SQS FIFO deduplication window?
7. Does content-based dedup hash message attributes too?
8. How do queue-level and message-group-level dedup differ?
9. Why can a message still be redelivered after a DB commit?
10. Why is a `SELECT processed` before `INSERT` unsafe?
11. Is a transactional inbox atomic with an external payment gateway?
12. Why can a producer transactional outbox still publish duplicates?
13. Does SNS FIFO delivering to SQS Standard preserve FIFO processing?
14. In a FIFO Lambda batch, which IDs must be returned after the first error?
15. Does visibility timeout delete a message?
16. Does a receipt handle stay the same across receives?
17. How can a DLQ break business ordering?
18. Why shouldn't SQS `messageId` be used as the business idempotency key?
19. Which two attributes enable SQS high-throughput FIFO?
20. Which metrics reflect backlog and duplicate business effects?

### Answer guide

- **Group:** FIFO orders per aggregate; Standard fair queue groups only provide fairness.
- **Dedup:** **5-minute** window based on explicit ID or SHA-256 of body excluding attributes.
- **Consumer:** Redeliveries happen, so keep a stable `eventId`, transactional inbox/unique business keys, and commit before ACK.
- **Producer:** Use an outbox to prevent lost events; relays can still double-publish.
- **Operations:** Lambda partial batch failures for FIFO, version-aware retry/visibility/DLQ, IAM/KMS, metrics, and cost controls.

## 25. Official Documentation

1. [Amazon SQS overview](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/welcome.html).
2. [FIFO queue delivery logic](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-queues-understanding-logic.html).
3. [Exactly-once processing in Amazon SQS](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-queues-exactly-once-processing.html).
4. [MessageDeduplicationId behavior](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/using-messagededuplicationid-property.html).
5. [MessageGroupId with FIFO queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/using-messagegroupid-property.html).
6. [SQS Standard fair queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-fair-queues.html).
7. [SQS high-throughput FIFO](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/high-throughput-fifo.html).
8. [Enabling high-throughput FIFO](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/enable-high-throughput-fifo.html).
9. [Visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html).
10. [FIFO message IDs and receipt handles](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-fifo-queue-message-identifiers.html).
11. [Dead-letter queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html).
12. [DLQ redrive](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-configure-dead-letter-queue-redrive.html).
13. [Using Lambda with SQS](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html).
14. [Handling Lambda SQS errors and partial batches](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html).
15. [Configuring Lambda SQS event source mappings](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-configure.html).
16. [Java SDK v2 SQS examples](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/java_sqs_code_examples.html).
17. [SNS FIFO message grouping](https://docs.aws.amazon.com/sns/latest/dg/fifo-message-grouping.html).
18. [SNS FIFO delivery](https://docs.aws.amazon.com/sns/latest/dg/fifo-message-delivery.html).
19. [SNS FIFO deduplication](https://docs.aws.amazon.com/sns/latest/dg/fifo-message-dedup.html).
20. [SNS high-throughput FIFO topics](https://docs.aws.amazon.com/sns/latest/dg/fifo-high-throughput.html).
21. [SNS FIFO subscription filtering](https://docs.aws.amazon.com/sns/latest/dg/fifo-message-filtering.html).
22. [SQS CloudWatch metrics](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-available-cloudwatch-metrics.html).
23. [SQS IAM access control](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-authentication-and-access-control.html).
24. [SQS VPC endpoints](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-internetwork-traffic-privacy.html).
25. [SQS pricing](https://aws.amazon.com/sqs/pricing/) and [SNS pricing](https://aws.amazon.com/sns/pricing/).

> **Key takeaway:** **FIFO alone does not make databases, payments, or emails “exactly once”**. Choose `MessageGroupId` by aggregate; generate a stable `MessageDeduplicationId` per business event; carry `eventId` and `aggregateVersion` in the payload; have consumers use a **transactional inbox/unique constraint** and **ACK only after commit**; and have producers use an outbox and handle retries. Control visibility, DLQs, Lambda partial batches, networking, IAM, and monitoring so retries never turn into duplicate business effects.
