# Building an SQS Listener with Retries and Idempotency

> **Chapter:** Java and Spring Boot Applications  
> **Module:** CLOUD_PROVIDERS_AWS — exploring the AWS ecosystem across Regions/AZs, IAM, VPCs, compute, storage, databases, integration, and serverless. Learners develop skills to select services, design, and deploy secure, observable, resilient, and cost-controlled applications.

## Learning objectives

Amazon Simple Queue Service (Amazon SQS) decouples producers from consumers, absorbs traffic bursts, and handles asynchronous work. However, SQS can deliver a message more than once; a consumer may also crash after committing to the database yet before deleting the message. Therefore, **retries must be paired with idempotency**.

This lesson builds an `OrderCreated` processing flow with Java/Spring Boot, Spring Cloud AWS 3.x, and AWS SDK for Java 2.x. We will design queues, visibility timeouts, retries/DLQs, listener acknowledgment, durable idempotency, database transactions, outboxes, FIFO ordering, graceful shutdown, and observability.

After this lesson, you will be able to:

1. Explain at-least-once delivery in SQS Standard and the semantics of FIFO.
2. Design visibility timeouts, long polling, redrive policies, and dead-letter queues.
3. Distinguish message retries, visibility extensions, delayed retries, and redrives.
4. Configure Spring Cloud AWS listeners and acknowledgment modes.
5. Handle duplicate messages with durable idempotency keys.
6. Combine idempotency records with business database transactions.
7. Use outboxes/idempotent external APIs for side effects outside the database.
8. Understand `MessageGroupId`, `MessageDeduplicationId`, and FIFO limitations.
9. Configure least-privilege IAM, SSE-KMS, and network access.
10. Design graceful shutdown, bounded concurrency, metrics, tracing, and runbooks.

## 1. Why does an application need an SQS listener?

### 1.1. Decoupling requests from time-consuming work

Suppose an API receives a payment/course enrollment request. Within the same request, the system might need to update the database, send emails, update a search index, generate an invoice, and record analytics. Calling everything synchronously ties the API to the uptime and latency of every downstream system.

SQS lets the API write an event to a queue and return quickly; consumers process independently:

~~~mermaid
flowchart LR
    C[Client] --> API[Spring Boot API]
    API --> DB[(Orders DB)]
    API --> Q[(SQS Orders Queue)]
    Q --> W[Spring Boot Worker]
    W --> DB2[(Business DB)]
    W --> MAIL[Email provider]
    W --> SEARCH[Search index]
    Q -. redrive .-> DLQ[(Dead-letter queue)]
~~~

Producers and consumers can scale independently. The queue buffers messages while consumers are temporarily unavailable, within retention and queue limits.

### 1.2. SQS is not a distributed transaction coordinator

A successful `SendMessage` does not commit atomically with the producer's database transaction. Possible failure scenarios:

- The database commits, then the process crashes before sending to SQS;
- Sending to SQS succeeds, yet the response times out and the producer does not know whether the message was sent;
- The consumer commits the DB, yet crashes before `DeleteMessage`;
- The consumer calls payment/email successfully, yet crashes before marking the work complete.

These scenarios produce **duplicate or missing side effects** without additional design. This lesson uses idempotency and outbox/inbox patterns to handle them.

### 1.3. Delivery guarantees and practical goals

With SQS Standard, systems are designed for **at-least-once delivery**: a message may be redelivered, even after a consumer has already processed it in certain failure scenarios. Strict ordering is not guaranteed.

SQS FIFO provides ordering per `MessageGroupId` and sender-side deduplication within the queue's deduplication window. This **does not make the entire end-to-end business workflow exactly-once**. Consumers must still handle redelivered messages safely.

Practical architectural goals:

- Messages can be redelivered;
- Consumers can re-run;
- Database side effects are protected by transactions/unique constraints;
- External side effects use idempotency keys or outbox workflows;
- Messages are acknowledged/deleted only after processing outcomes are durable.

### 1.4. Three layers to keep distinct

| Layer | Mechanism | Problem solved |
|---|---|---|
| Transport retry | SQS visibility timeout/redrive | Redelivers messages when a consumer does not finish |
| Processing idempotency | Event ID + durable inbox/unique key | Prevents applying the same business event twice |
| Side-effect consistency | DB transactions, outbox, external idempotency | Prevents half-completed state across systems |

No single layer completely replaces the other two.

## 2. SQS Standard vs. FIFO

### 2.1. Comparison

| Attribute | Standard queue | FIFO queue |
|---|---|---|
| Throughput | High, scales broadly | Bounded by throughput mode/Region; high-throughput FIFO supported |
| Ordering | No guaranteed order | Guaranteed order within the same message group |
| Duplicate delivery | Possible | Consumer idempotency still required |
| Send deduplication | No queue-level FIFO dedupe | Deduplication ID/content-based dedupe within a 5-minute window |
| Parallelism | Consumers can process many messages in parallel | Parallel across message groups; strict order within each group |
| Queue name | Regular name | Name ending in `.fifo` |
| Use case | Independent events/workloads, high throughput | Ordering per order/account/aggregate |

Choose FIFO when ordering is a business invariant, such as per-account balance updates or sequential order state transitions. When messages are independent and parallelizable, Standard is usually simpler and more flexible.

### 2.2. FIFO does not guarantee exactly-once business processing

FIFO deduplication lets SQS recognize the same `MessageDeduplicationId` within **5 minutes** to prevent duplicate enqueuing during that window. However:

- A consumer can still receive the message again if the visibility timeout expires;
- A consumer can commit a business transaction yet fail to delete the message;
- A retry sent after the deduplication window expires can be re-enqueued;
- Email/payment/search side effects can be invoked again without idempotency.

Therefore, producers use deterministic deduplication IDs and consumers still persist processed `eventId`s in a durable store.

### 2.3. MessageGroupId is the ordering boundary

FIFO example:

~~~text
MessageGroupId = ORDER#order-123
  Event 1: OrderCreated
  Event 2: PaymentAuthorized
  Event 3: OrderShipped

MessageGroupId = ORDER#order-456
  Event 1: OrderCreated
  Event 2: PaymentAuthorized
~~~

Messages within the same group are processed in order; multiple groups can be processed concurrently. Assigning the same group ID to the entire queue can inadvertently serialize nearly your whole workload.

On the application side, do not dispatch messages from the same group onto parallel worker threads and commit out of order. If using batch listeners or custom executors, preserve serial processing per `MessageGroupId` or verify that your framework/container version preserves end-to-end ordering.

Choose groups by the aggregate needing ordering, such as `ORDER#<orderId>` or `ACCOUNT#<accountId>`. Do not use a shared tenant ID as the group if orders within a tenant do not require global ordering.

### 2.4. Event envelope with schema version

Message bodies should use a stable envelope:

~~~json
{
  "eventId": "evt-8b1f4d",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "occurredAt": "2026-11-20T03:00:00Z",
  "tenantId": "tenant-17",
  "aggregateId": "order-123",
  "correlationId": "req-456",
  "payload": {
    "orderId": "order-123",
    "customerId": "customer-42",
    "currency": "VND",
    "totalMinorUnits": 12500000
  }
}
~~~

`eventId` is the business event identity, remaining stable across retries. SQS's `MessageId` identifies a single message delivered to the queue; do not equate it to the event ID when a producer retries with two separate `SendMessage` calls.

`schemaVersion` tells consumers how to deserialize/migrate the event. Never place access tokens, passwords, card data, or unnecessary PII in the body or attributes.

### 2.5. Choosing queue topology

A queue should represent a work stream/consumer contract with compatible retention, retry, concurrency, and security profiles. Split queues when:

- Consumers have different SLAs or throughput;
- One event type requires FIFO while another does not;
- IAM/retention/KMS/ownership differs;
- A slow consumer must not back up another consumer.

Do not create one queue per message type without a clear isolation need.

## 3. Visibility timeout, long polling, and redrive

### 3.1. Message lifecycle

When a consumer receives a message, SQS does not delete it immediately. The message enters the **in-flight** state and stays temporarily hidden from other receive calls for `VisibilityTimeout`.

~~~mermaid
sequenceDiagram
    participant Q as SQS
    participant W as Worker
    participant DB as Database
    W->>Q: ReceiveMessage
    Q-->>W: Message (in flight)
    W->>DB: Process + commit
    alt processing succeeds
        W->>Q: DeleteMessage / acknowledge
        Q-->>W: Deleted
    else worker fails/crashes or skips delete
        Note over Q: Visibility timeout expires
        Q-->>W: Message may be redelivered
    end
~~~

If a consumer completes business work yet fails to delete the message, SQS can redeliver it. This is why consumers must be idempotent **even when acknowledgment mode is configured properly**.

### 3.2. Choosing VisibilityTimeout

`VisibilityTimeout` starts when a message is received. During this window, the consumer is responsible for processing and acknowledging/deleting it.

Base the timeout on:

- Actual p95/p99 processing duration;
- Batch size and concurrent messages being processed;
- Database/downstream wait times;
- Internal SDK/HTTP client retries;
- Shutdown/drain intervals;
- Margin for GC pauses, scheduler delays, and network jitter.

Too short a timeout makes the message reappear while the original worker is still running, causing **two workers to process the same message concurrently**. Too long a timeout delays retries on failed messages and prolongs dead-worker detection.

Do not pick an arbitrary timeout for every workload. Measure processing duration and set the timeout above the expected maximum processing time with appropriate headroom.

### 3.3. Extending visibility for long tasks

If task duration varies, the consumer can call `ChangeMessageVisibility` to extend visibility while still working. Ensure you:

- Extend before the current timeout expires;
- Use a bounded heartbeat and stop it once work finishes;
- Handle failures when extension fails;
- Ensure only the worker holding the message continues side effects;
- Enforce an overall deadline to avoid holding a message indefinitely.

Example for a consumer calling AWS SDK for Java 2.x directly (not a listener that handed the receipt handle to a Spring container): assuming `sqs` is an `SqsClient` configured with the right Region and credentials:

~~~java
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.ChangeMessageVisibilityRequest;

ChangeMessageVisibilityRequest request = ChangeMessageVisibilityRequest.builder()
    .queueUrl(queueUrl)
    .receiptHandle(receiptHandle)
    .visibilityTimeout(120)
    .build();

sqs.changeMessageVisibility(request);
~~~

`receiptHandle` must be the handle from the current receive; never use `MessageId`. If Spring Cloud AWS manages the message lifecycle, use the framework's API/mechanism instead of manually deleting/extending via a separate `SqsClient`.

SQS imposes a maximum visibility limit of **12 hours from the initial receive**. Extensions cannot create an unbounded lease. If jobs can run for hours or require long-lived workflows, consider breaking them into smaller steps or using workflow orchestration.

### 3.4. Long polling

SQS long polling reduces empty responses by waiting for messages to arrive up to a set duration. `WaitTimeSeconds` maxes out at **20 seconds**.

The queue attribute `ReceiveMessageWaitTimeSeconds` configures default long polling; `ReceiveMessage` requests can also specify it per call. With Spring Cloud AWS listener containers, `pollTimeout` is the corresponding polling configuration in supported versions.

Long polling generally cuts API calls and cost compared to short polling. Ensure the HTTP client response timeout exceeds the poll wait time plus network margin; if the client times out before SQS responds, you trigger unnecessary retries.

### 3.5. Queue retention

SQS retains messages up to `MessageRetentionPeriod`:

- Default is typically **4 days**;
- Maximum is **14 days**;
- Queue retention must match backlog handling and replay windows.

Retention is not a long-term backup. If audit/event history must be kept longer, write events to a durable event store/S3/data platform per separate retention requirements.

### 3.6. Dead-letter queue

A **Dead-letter queue (DLQ)** receives messages delivered more than the allowed number of times under the redrive policy.

~~~mermaid
flowchart TD
    Q[(Source queue)] --> W[Listener]
    W -->|success + delete| DONE[Processed]
    W -->|failure / no delete| RETRY[Visible after timeout]
    RETRY --> Q
    RETRY -->|receive count reaches maxReceiveCount| DLQ[(DLQ)]
    DLQ --> TRIAGE[Inspect, fix, redrive]
    TRIAGE --> Q
~~~

Key fields of a redrive policy:

- `deadLetterTargetArn`: ARN of the DLQ;
- `maxReceiveCount`: receive count threshold; when a message reaches it under the redrive policy, SQS moves the message to the DLQ.

Conceptual example:

~~~json
{
  "deadLetterTargetArn": "arn:aws:sqs:ap-southeast-1:111122223333:orders-dlq",
  "maxReceiveCount": 5
}
~~~

This is a sample configuration, not a command to apply blindly to an account. Pick `maxReceiveCount` based on your retry budget, visibility duration, and how transient errors are.

### 3.7. DLQ design rules

- The DLQ must match the source queue type: Standard ↔ Standard, FIFO ↔ FIFO;
- The DLQ needs long enough retention for investigation, usually longer than the source queue;
- Trigger an alarm whenever the DLQ receives messages;
- Record event ID, source queue, receive count, failure category, and correlation ID;
- Never automatically redrive continuously before fixing the root cause;
- Maintain a procedure to verify data/business state before replaying;
- Use an appropriate redrive allow policy to restrict which source queues may target the DLQ.

With Standard queues, message expiration timestamps remain relative to the original enqueue time when moved to a DLQ; FIFO queues reset the enqueue timestamp on move. Thus, set DLQ retention longer than the source and understand how AWS computes retention for your queue type.

**FIFO-specific note:** when the first message in a group moves to the DLQ, subsequent messages in that group can proceed. This avoids stalling the queue forever, yet can leave a gap in the business sequence. If strict absolute ordering is required, evaluate whether a DLQ fits or whether an aggregate pause/reconcile workflow is needed.

### 3.8. Poison messages and failure classification

A **poison** message consistently fails due to payload/schema/business constraints, such as a missing `eventId`, unsupported version, or invalid currency. Infinite retries cannot fix a poison message.

| Failure type | Handling approach |
|---|---|
| Network timeout, throttling, database unavailable | Retry with backoff and bounded attempts |
| Temporary dependency outage | Do not acknowledge; let SQS retry or adjust visibility deliberately |
| Invalid schema/unsupported event version | Persist failure record/route to DLQ; never retry infinitely |
| Business rule rejected | Record audited rejection state; ack/DLQ per contract |
| Already-committed duplicate event | Treat as success; acknowledge |
| IAM/configuration error | Alert/halt rollout; mass retries rarely help |

Never swallow all exceptions and return normally: the listener container will likely acknowledge the message even though the business operation never completed.

### 3.9. Retry delay and backoff

SQS redelivery typically occurs after the visibility timeout when a message is not deleted. For progressive backoff, you can:

- Use `ChangeMessageVisibility` to set the next hidden interval;
- Use retry queues with `DelaySeconds`/message timers within SQS limits;
- Use orchestration/workflows for complex retry schedules.

Never call `Thread.sleep()` inside a listener to wait for a retry. Doing so ties up a thread/concurrency slot, degrades throughput, and can let the visibility timeout expire while the worker sleeps.

### 3.10. Receive count does not replace an idempotency key

SQS provides the `ApproximateReceiveCount` system attribute. Use it for logging, metrics, and retry classification, but remember it is an **approximate receive count**, not an event identity. Never use receive count as an idempotency key; one event could be sent as two separate messages, each starting its own receive count.

## 4. Idempotency: process the same event multiple times, apply it once

### 4.1. What is idempotency?

An operation is **idempotent** when repeating it with the same business input does not alter the final outcome multiple times. Examples:

- Setting an order's state to PAID by event ID can be idempotent;
- Decrementing inventory by 1 on every message receipt is **not idempotent**;
- Sending an email every time the listener runs is **not idempotent**;
- Recording the event ID in a table with a unique constraint detects already-completed processing.

The goal is not to stop SQS from delivering duplicate messages; the goal is to make the consumer **safe when duplicates arrive**.

### 4.2. Use a stable business event ID

Example:

~~~json
{
  "eventId": "evt-8b1f4d",
  "eventType": "OrderCreated",
  "aggregateId": "order-123",
  "schemaVersion": 1
}
~~~

`eventId` is generated once when the business event originates and stays identical across producer retries. Never mint a new UUID on each re-send of the same event, because consumers will treat it as a brand-new event.

SQS `MessageId` works well for correlating/debugging a specific delivery, yet cannot replace the business event ID across producer retries, queue redrives, and replays.

### 4.3. Inbox/processed-message table

A simple relational table:

~~~sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(120) NOT NULL,
    event_id VARCHAR(160) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

`consumer_name` lets independent consumers process the same event. For example, `billing-projection` and `email-notifier` maintain distinct idempotency namespaces.

You can also store a payload hash, schema version, correlation ID, or result reference for auditing. Avoid storing full PII unnecessarily.

If the same `(consumer_name, event_id)` arrives with a different payload hash than the first time, treat it as an integrity/schema violation requiring investigation—never silently skip it as a valid duplicate.

### 4.4. Writing inbox and business updates in the same DB transaction

With PostgreSQL, use `INSERT ... ON CONFLICT DO NOTHING` to claim the event atomically:

~~~sql
INSERT INTO processed_message (consumer_name, event_id)
VALUES (?, ?)
ON CONFLICT (consumer_name, event_id) DO NOTHING;
~~~

If rows inserted equals `1`, this transaction is the first to claim the event and may apply business updates. If `0`, the event was already processed/claimed by a committed transaction; the listener can treat it as a successful duplicate.

**The following example uses PostgreSQL-specific SQL**, not portable syntax across every RDBMS.

~~~mermaid
flowchart TD
    M[Receive eventId] --> TX[Begin DB transaction]
    TX --> I[Insert inbox row with unique key]
    I --> D{Inserted one row?}
    D -->|No| DUP[Already processed]
    DUP --> COMMIT1[Commit / return duplicate]
    D -->|Yes| B[Apply business database changes]
    B --> O[Insert outbox event if needed]
    O --> COMMIT2[Commit all DB changes]
    COMMIT1 --> ACK[Acknowledge SQS]
    COMMIT2 --> ACK
~~~

Crucially, **the inbox insert, business state changes, and outbox insert share the same transaction**. If the business update fails, the transaction rolls back the inbox row too, allowing SQS retries to reattempt.

### 4.5. Java/Spring service with transactions

Example using `JdbcTemplate` and PostgreSQL:

~~~java
@Service
public class OrderEventProcessor {

    private final JdbcTemplate jdbc;

    public OrderEventProcessor(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public ProcessingResult process(OrderCreatedEvent event) {
        int inserted = jdbc.update("""
            INSERT INTO processed_message (consumer_name, event_id)
            VALUES (?, ?)
            ON CONFLICT (consumer_name, event_id) DO NOTHING
            """,
            "order-projection",
            event.eventId().toString()
        );

        if (inserted == 0) {
            return ProcessingResult.DUPLICATE;
        }

        // Same transaction: business update must roll back
        // if any step below fails.
        jdbc.update("""
            UPDATE orders
               SET event_status = ?, updated_at = CURRENT_TIMESTAMP
             WHERE order_id = ?
            """,
            "CREATED",
            event.orderId().toString()
        );

        // If external side effects are needed, insert an outbox row here.
        return ProcessingResult.APPLIED;
    }
}
~~~

This is an illustrative example; production code must inspect `UPDATE` row counts, schema/constraints, event ordering, and missing-order cases. Ensure the method is invoked through a Spring transactional proxy so the transaction actually applies.

With a synchronous listener, when `process` returns through the proxy, the transaction commit has completed. Only then does the listener return normally and `ON_SUCCESS` acknowledgment mode acknowledge the message.

### 4.6. Why not insert the idempotency record first and process afterward?

Anti-pattern:

~~~text
1. INSERT processed_message and COMMIT
2. Update order
3. Crash before order update
4. SQS redelivers
5. Consumer sees processed_message and skips
~~~

The event gets marked processed even though the business update never happened. Put **inbox claim + business writes in one transaction** whenever the same database can participate.

### 4.7. Race condition when two consumers receive the same event

The unique constraint on `(consumer_name, event_id)` is the final guardrail. If two workers process concurrently:

- One transaction succeeds in inserting;
- The other transaction waits/receives a conflict per database semantics;
- Only the winning transaction applies business updates;
- The losing transaction concludes it is a duplicate once the conflicting insert commits.

Do not merely `SELECT` first and `INSERT` later: both workers can `SELECT` “not found” simultaneously and both execute side effects. An **atomic unique constraint/conditional write** is required.

### 4.8. Idempotency record retention

Retain processed IDs for at least the maximum duration a message can be retried, sit in a DLQ, be redriven, or be replayed. Purging records too early allows an older replayed message to execute twice.

If using TTL to clean up inbox rows:

- TTL deletion is typically asynchronous, not exact to the second;
- TTL duration must exceed the retry/redrive/replay horizon;
- Never treat TTL as an exact business expiration lock;
- For financial/ledger/audit domains, idempotency keys may need far longer retention per policy.

### 4.9. Idempotency keys must reflect the business operation

`eventId` alone is not always enough. An API might emit two distinct events representing a single payment attempt. In that case, use a business key such as `paymentAttemptId`, `orderId + actionVersion`, or a durable client-supplied idempotency key.

Avoid using just `orderId` if an order has multiple valid state transitions. The key must distinguish **each business operation** while remaining identical across retries of that operation.

## 5. Database transactions and external side effects

### 5.1. Transactions cover only participating resources

`@Transactional` with JDBC/JPA typically manages transactions within **one relational database transaction manager**. It is not atomic with:

- SQS `DeleteMessage`;
- HTTP calls to a payment provider;
- Email/SMS providers;
- Search indexes;
- Object storage;
- Another database outside the same transaction coordinator.

Never expect a single transaction annotation to commit both SQS and the DB.

### 5.2. Crash window between commit and acknowledgment

~~~text
Receive SQS message
  -> DB transaction commit
  -> Process crashes
  -> SQS message not deleted
  -> Visibility timeout expires
  -> Message delivered again
~~~

The second delivery sees the committed inbox record, skips repeating the business update, returns normally, and acknowledges. This is **at-least-once transport + idempotent consumer**.

If a consumer acknowledges before committing to the DB, crashing after ack loses work permanently. Therefore, ack must follow durable commit.

### 5.3. Transactional outbox

When a business update must emit events/emails/search updates, write an **outbox row** inside the same database transaction:

~~~sql
CREATE TABLE outbox_event (
    outbox_id UUID PRIMARY KEY,
    event_type VARCHAR(120) NOT NULL,
    aggregate_id VARCHAR(160) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ
);
~~~

Transaction:

~~~text
BEGIN
  insert processed_message
  update orders
  insert outbox_event
COMMIT
~~~

A publisher/relay reads unpublished outbox rows, dispatches the SQS/email/search event, and marks them published. If the relay publishes successfully yet crashes before marking published, the event may be re-sent; downstream consumers still need idempotency.

The outbox closes the **dual-write gap between database and broker** by recording business state changes and event intent in one transaction. It does not turn external delivery into exactly-once.

### 5.4. External API idempotency keys

If a payment provider supports idempotency keys, send the same key across every retry of that operation:

~~~http
Idempotency-Key: payment-attempt-7a9...
~~~

If a request times out, query/reconcile the outcome using that same key before initiating a new operation. Never mint a new key simply because the response was lost.

Email providers may lack true idempotency. In that case, an outbox ensures the event is durably emitted yet cannot strictly prevent duplicate emails after an ambiguous timeout; design business notifications to tolerate duplicates or choose providers supporting deduplication.

### 5.5. Never hold DB transactions open during slow HTTP calls

Anti-pattern:

~~~text
BEGIN DB transaction
  insert inbox
  update order
  call payment/email HTTP API (seconds)
COMMIT
ack SQS
~~~

Holding DB locks/connections while waiting on the network increases contention and timeout risks. Better:

1. Transactional DB update + inbox + outbox;
2. Commit;
3. Listener acknowledges;
4. Outbox relay calls external service;
5. Relay records status/retries;
6. External consumer is idempotent.

### 5.6. DynamoDB as an inbox store

If business state also lives in DynamoDB, `TransactWriteItems` can write the idempotency item and business item atomically within the same Region/account transaction limits. Use condition expression `attribute_not_exists(PK)` for the inbox key.

If business state is in RDS while the idempotency item is in DynamoDB, the two writes are not atomic. Keep the inbox table in RDS alongside the RDS business transaction, or use outbox/saga/reconciliation.

## 6. Retry policies by failure type

### 6.1. Retries are not the right response for every exception

A consumer must classify failures:

- **Transient:** network timeouts, throttling, temporary dependency unavailability;
- **Permanent/poison:** invalid payload, unsupported schema version, missing required fields;
- **Business rejection:** canceled order, insufficient limit, disallowed state;
- **Duplicate:** event already committed;
- **Configuration/security:** IAM deny, wrong endpoint, expired secret.

Retrying transient errors can succeed after a delay. Retrying permanent errors only inflates backlog and cost. Duplicates are a **success outcome**, not a retryable failure.

### 6.2. Sample error policy

| Processing outcome | Listener behavior | SQS outcome |
|---|---|---|
| Applied successfully | Return success | Acknowledge/delete |
| Duplicate already committed | Return success | Acknowledge/delete |
| Temporary DB/network outage | Throw retryable exception | No ack; redelivery per visibility/redrive |
| Invalid schema | Persist durable diagnostic, then route DLQ/ack per policy | Never retry infinitely |
| Intentional business rejection | Persist rejection/audit, then return success if contract marks terminal | Acknowledge/delete |
| IAM/endpoint misconfiguration | Fail fast/alert, pause rollout | Avoid infinite retries masking the error |

For permanent errors, a design may explicitly persist a failure record/send to a DLQ via a dedicated workflow. Never both manually send to the DLQ and let the source message auto-redrive without deduplication, or you create duplicate failure records.

### 6.3. Backoff and jitter

When a dependency is overloaded, immediate synchronized retries cause a **thundering herd**. Use exponential backoff with jitter, bounded attempts, and retry budgets. With SQS, implementations include:

- Setting progressive visibility delays via `ChangeMessageVisibility`;
- Using retry/delay queues;
- Throttling consumer concurrency when downstream is overloaded;
- Using circuit breakers to avoid hammering a failing dependency.

Never block listener threads with sleep. Retries need metrics, maximum delays, and a dead-letter path.

### 6.4. Poison messages and DLQ triage

The DLQ is a quarantine zone for investigation:

1. Inspect source queue, event ID, schema version, and approximate receive count;
2. Classify permanent, transient, or configuration errors;
3. Verify whether any partial side effects already occurred;
4. Fix the consumer or data issue;
5. Execute controlled replay/redrive;
6. Watch duplicate/idempotency metrics;
7. Audit who redrove, when, and why.

Never manually edit DLQ payloads and replay them without audit/change control. If schema fixes are needed, prefer tested migration/compatibility handlers.

## 7. Spring Boot and Spring Cloud AWS SQS listeners

### 7.1. Choosing compatible versions

With Spring Boot 3 and Java 17, you can use Spring Cloud AWS 3.x alongside AWS SDK for Java 2.x. Manage versions through the Spring Cloud AWS BOM matching your project's Spring Boot release train.

Maven dependency example:

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>io.awspring.cloud</groupId>
      <artifactId>spring-cloud-aws-dependencies</artifactId>
      <version>${spring-cloud-aws.version}</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter-sqs</artifactId>
  </dependency>
</dependencies>
~~~

`spring-cloud-aws.version` is a project-managed property, not a literal release version. Never mix Spring Cloud AWS 2.x and 3.x imports/configuration; API packages and behaviors differ.

### 7.2. Configuring Region and queue name

Example `application.yml`:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1

app:
  sqs:
    orders-queue: orders-events
~~~

Exact property names must match the selected Spring Cloud AWS version. In production, Region may come from deployment config; never let arbitrary user requests dictate Region.

Credentials should come from the AWS SDK provider chain (ECS task role, EKS Pod Identity/IRSA, EC2 instance profile, or local SSO profile). Never put access keys/secrets into `application.yml`.

### 7.3. SqsAsyncClient and listener container factory

The starter can auto-configure SQS client/container infrastructure. When explicit configuration is needed, e.g.:

~~~java
import java.time.Duration;

import io.awspring.cloud.sqs.config.SqsMessageListenerContainerFactory;
import io.awspring.cloud.sqs.listener.acknowledgement.handler.AcknowledgementMode;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsAsyncClient;

@Configuration
public class SqsListenerConfiguration {

    @Bean
    SqsAsyncClient sqsAsyncClient() {
        return SqsAsyncClient.builder()
            .region(Region.AP_SOUTHEAST_1)
            .build();
    }

    @Bean
    SqsMessageListenerContainerFactory<Object>
    defaultSqsListenerContainerFactory(SqsAsyncClient sqsAsyncClient) {
        return SqsMessageListenerContainerFactory.builder()
            .sqsAsyncClient(sqsAsyncClient)
            .configure(options -> options
                .acknowledgementMode(AcknowledgementMode.ON_SUCCESS)
                .maxConcurrentMessages(20)
                .maxMessagesPerPoll(10)
                .pollTimeout(Duration.ofSeconds(20)))
            .build();
    }
}
~~~

This shows the Spring Cloud AWS 3.x API pattern; pin a specific minor version and verify imports/options against your project's version. If the starter already provides `SqsAsyncClient`, do not inadvertently declare a conflicting duplicate bean.

`maxConcurrentMessages` caps how many messages the container processes concurrently; `maxMessagesPerPoll` cannot exceed SQS `ReceiveMessage`'s 10-message limit. `pollTimeout` configures long polling; the HTTP client response timeout must exceed the poll duration plus network margin.

### 7.4. Listener with ON_SUCCESS acknowledgment

~~~java
import io.awspring.cloud.sqs.annotation.SqsListener;
import org.springframework.stereotype.Component;

@Component
public class OrdersListener {

    private final OrderEventProcessor processor;

    public OrdersListener(OrderEventProcessor processor) {
        this.processor = processor;
    }

    @SqsListener("${app.sqs.orders-queue}")
    public void onOrderCreated(OrderCreatedEvent event) {
        processor.process(event);
    }
}
~~~

With `AcknowledgementMode.ON_SUCCESS`, the container acknowledges the message after the listener completes normally. If `processor.process(...)` throws an exception, the listener is not considered successful and the message can be redelivered per visibility timeout/redrive policy.

**Never catch an exception, merely log it, and return** if the business transaction did not complete. Returning normally is interpreted as success and the message may be acknowledged.

### 7.5. Manual acknowledgment

Manual ack fits when the app must explicitly control acknowledgment after commit or after recording a durable failure. Conceptual example for Spring Cloud AWS 3.x:

~~~java
import io.awspring.cloud.sqs.annotation.SqsListener;
import io.awspring.cloud.sqs.listener.acknowledgement.Acknowledgement;
import org.springframework.stereotype.Component;

@Component
public class ManualOrdersListener {

    private final OrderEventProcessor processor;

    public ManualOrdersListener(OrderEventProcessor processor) {
        this.processor = processor;
    }

    @SqsListener(value = "${app.sqs.orders-queue}", acknowledgementMode = "MANUAL")
    public void onMessage(
            OrderCreatedEvent event,
            Acknowledgement acknowledgement) {

        processor.process(event); // transaction commits when method returns
        acknowledgement.acknowledgeAsync().join();
    }
}
~~~

Enum/annotation attribute names may vary across minor versions. In production configuration, prefer setting manual mode on listener container options via the corresponding enum if supported by your version. Never enable manual mode and forget to call `acknowledge`: messages will redeliver once visibility expires.

### 7.6. Why should listeners stay thin?

A listener should only:

1. Receive and deserialize the message;
2. Perform basic envelope validation;
3. Call the application service;
4. Let exceptions propagate per retry policy;
5. Acknowledge per the configured mode.

Business transactions and idempotency belong in the service/repository layer so they can be tested independently and reused from APIs or replay jobs. Never cram DB queries, payment calls, retry sleeps, and payload logging inside listener methods.

### 7.7. Deserialization and schema compatibility

When a queue carries multi-version events, do not assume every message shares the exact same schema. Use a shared envelope and dispatch on `eventType`/`schemaVersion`.

- Validate event ID, event type, and required fields;
- Route unsupported versions to the DLQ per policy;
- Maintain backward compatibility when adding optional fields;
- Avoid repurposing existing fields;
- Never log raw bodies containing PII/secrets when deserialization fails;
- Persist raw payloads to a restricted failure store only if required by incident procedures.

## 8. Java SDK v2 producer: reliable message publishing

### 8.1. Standard queue

Producer example using AWS SDK for Java 2.x:

~~~java
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.SendMessageRequest;

public final class OrderEventPublisher {

    private final SqsClient sqs;
    private final String queueUrl;

    public OrderEventPublisher(SqsClient sqs, String queueUrl) {
        this.sqs = sqs;
        this.queueUrl = queueUrl;
    }

    public void publish(String jsonBody) {
        SendMessageRequest request = SendMessageRequest.builder()
            .queueUrl(queueUrl)
            .messageBody(jsonBody)
            .build();

        sqs.sendMessage(request);
    }
}
~~~

Queue URLs should be resolved/configured from trusted configuration. Never accept arbitrary queue URLs from API callers; that invites confused-deputy/SSRF-like routing and sending data to queues outside your ownership.

### 8.2. FIFO queue

For FIFO, producers must supply `MessageGroupId`; they may provide `MessageDeduplicationId` or enable content-based deduplication on the queue:

~~~java
SendMessageRequest request = SendMessageRequest.builder()
    .queueUrl(fifoQueueUrl)
    .messageBody(jsonBody)
    .messageGroupId("ORDER#" + orderId)
    .messageDeduplicationId(eventId)
    .build();

sqs.sendMessage(request);
~~~

`MessageDeduplicationId` should stay stable for the same event. The deduplication window is **5 minutes**; it is not a durable idempotency store across the entire lifetime of an event.

When content-based deduplication is enabled, SQS computes the deduplication ID from the message body; message attributes are excluded from the content-based deduplication hash. If the body changes due to timestamps or random metadata, identical business events may fail to deduplicate as intended.

### 8.3. Producer retries and ambiguous timeouts

If `SendMessage` times out, the producer does not know whether SQS accepted the message. Retry with the same event ID and payload:

- FIFO: reuse the same `MessageDeduplicationId` within the dedupe window;
- Standard: consumers must tolerate duplicates;
- Both: preserve the exact business event ID;
- If the event originates from a DB transaction, use an outbox so the publisher can retry durably.

Never generate a new event ID on retry solely because a request timed out.

### 8.4. Outbox relays must not hold transactions open

A relay can claim a batch of outbox rows, commit the claim/lease, publish messages, and then mark them sent. If it crashes after publishing yet before marking sent, the relay may re-publish. Consumer idempotency handles the duplicate.

You can use CDC/Debezium or a polling relay; choose based on throughput, latency, and operational capability. Ensure leases have timeouts so stale claims recover after crashes.

## 9. Acknowledgment and deletion semantics

### 9.1. Acknowledgment means DeleteMessage

In SQS, final acknowledgment corresponds to deleting the message using the receipt handle from the current receive. `MessageId` is not a receipt handle. If the receipt handle is stale or invalid, deletion may not succeed as expected.

The Spring Cloud AWS container manages receipt handles and acknowledgment flows; do not call `DeleteMessage` manually by ID when the framework owns the message lifecycle.

### 9.2. When to acknowledge?

| Ack timing | Consequence |
|---|---|
| Before DB commit | Crashing after ack can lose the event |
| After DB commit + inbox/idempotency | Safer; duplicates can be safely skipped |
| After external API without idempotency | Timeouts/crashes can cause duplicate side effects |
| After durable rejection record | Safe to ack if policy defines it as terminal |
| No ack on transient error | SQS redelivers after visibility timeout |

**Ack after durable outcome** is the rule. A durable outcome may be a committed business transaction, an already-handled duplicate, or a persisted permanent failure designated not to retry.

### 9.3. Acknowledgment batching

Spring Cloud AWS can batch acknowledgments to reduce API calls. When batching is enabled, a message may finish processing before `DeleteMessageBatch` executes. Consumers must remain idempotent during this window.

If a batch delete partially fails, the container/framework must handle failed entries. Check behavior and metrics for your Spring Cloud AWS version; never assume every message in a batch was deleted.

### 9.4. Batch listeners and partial failures

A batch contains multiple messages; if one item fails, acknowledgment semantics depend on listener mode and framework version. When processing batches, clearly establish:

- Which messages committed business transactions?
- Which messages are eligible for ack?
- Is partial acknowledgment/failed-message handling supported?
- Does a single exception redeliver the entire batch?
- Are committed side effects idempotent if the batch re-runs?

Do not confuse partial batch responses in **AWS Lambda SQS event source mappings** with Spring Cloud AWS listener containers; the two integrations have distinct configurations.

## 10. Queue configuration as infrastructure

### 10.1. Queue attributes to decide

| Attribute | Purpose | Design guidance |
|---|---|---|
| `VisibilityTimeout` | Duration a message stays hidden after receive | Based on processing p99 + headroom |
| `ReceiveMessageWaitTimeSeconds` | Long polling | Commonly 20 seconds where appropriate |
| `MessageRetentionPeriod` | Message retention duration | Sized to backlog/recovery window |
| `RedrivePolicy` | Moves messages to DLQ | Set intentional `maxReceiveCount` |
| `KmsMasterKeyId` | SSE-KMS encryption key | Pick key/policy per compliance |
| `FifoQueue` | Enables FIFO semantics | Both source and DLQ must match type |
| `ContentBasedDeduplication` | Derives dedupe ID from body | Enable only when bodies are suitably deterministic |

Define queue attributes via IaC (CloudFormation/CDK/Terraform) for reviewability, version control, and environment reproducibility. Never configure dev/staging/prod inconsistently by hand without a source of truth.

### 10.2. CloudFormation example for Standard queue + DLQ

~~~yaml
Resources:
  OrdersDlq:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: orders-events-dlq
      MessageRetentionPeriod: 1209600

  OrdersQueue:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: orders-events
      VisibilityTimeout: 120
      ReceiveMessageWaitTimeSeconds: 20
      MessageRetentionPeriod: 345600
      RedrivePolicy:
        deadLetterTargetArn: !GetAtt OrdersDlq.Arn
        maxReceiveCount: 5
~~~

The values 120 seconds, 20 seconds, 4 days, and 5 receives are **illustrative examples**; size them to measured processing times, retry budgets, and retention needs. The DLQ in this example has longer retention than the source queue.

### 10.3. FIFO queue + FIFO DLQ

For FIFO, both queues require FIFO configuration and `.fifo` suffixes:

~~~yaml
Resources:
  OrdersFifoDlq:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: orders-events-dlq.fifo
      FifoQueue: true
      MessageRetentionPeriod: 1209600

  OrdersFifoQueue:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: orders-events.fifo
      FifoQueue: true
      ContentBasedDeduplication: false
      VisibilityTimeout: 120
      ReceiveMessageWaitTimeSeconds: 20
      RedrivePolicy:
        deadLetterTargetArn: !GetAtt OrdersFifoDlq.Arn
        maxReceiveCount: 5
~~~

When providing an explicit `MessageDeduplicationId`, `ContentBasedDeduplication` can remain false. Choose one strategy deliberately; do not rely on content hashing if message bodies include timestamps or random fields that vary per send.

### 10.4. Queue visibility timeout vs. listener behavior

Containers have their own concurrency/batch settings, yet the SQS queue still enforces the visibility timeout. Account for:

- Per-message processing time;
- Batch processing duration if the listener processes batches;
- Slow external API calls;
- Whether visibility extension is enabled;
- Graceful shutdown/drain intervals;
- Retry policies and redrive counts.

If a 10-message batch runs sequentially in 90 seconds, a 60-second timeout can make the first messages visible again before the batch finishes. Configure concurrency and timeouts based on **how long messages actually stay in flight**.

### 10.5. Queue policies and DLQ redrive allow policies

Queue policies restrict which principals/services may send or receive messages. Redrive allow policies restrict which source queues may send messages to a DLQ. Do not let a DLQ accept messages from arbitrary queues in an account without proper ownership.

If SQS receives events from SNS/EventBridge/Lambda, the policy must allow the exact service principal/source ARN per the corresponding integration guide.

### 10.6. Inspecting queues with AWS CLI (read-only)

In an authorized sandbox account/Region, inspect queue URLs and attributes without mutating the queue:

~~~bash
REGION=ap-southeast-1
QUEUE_URL=$(aws sqs get-queue-url --queue-name orders-events --region "$REGION" --query QueueUrl --output text)

aws sqs get-queue-attributes --queue-url "$QUEUE_URL" --attribute-names All --region "$REGION" --output json
~~~

Inspect `VisibilityTimeout`, `ReceiveMessageWaitTimeSeconds`, `MessageRetentionPeriod`, `RedrivePolicy`, `KmsMasterKeyId`, and queue type. `get-queue-attributes` is read-only; never paste sensitive queue URLs/ARNs or payloads into public logs.

## 11. IAM, KMS, and private networking

### 11.1. Least privilege for consumers

Consumers typically need these actions on the source queue:

- `sqs:ReceiveMessage`;
- `sqs:DeleteMessage`;
- `sqs:ChangeMessageVisibility` if extending visibility;
- `sqs:GetQueueAttributes`;
- `sqs:GetQueueUrl` if the framework resolves queue URLs by name.

Do not grant `sqs:*` across all queues if the worker only consumes the orders queue.

### 11.2. Producer permissions

Producers usually need only `sqs:SendMessage` on the target queue. Even for FIFO sends, the IAM action remains `SendMessage`; FIFO parameters reside in the request.

If the app reads attributes or resolves URLs, add only the needed permissions. Separate producer roles from consumer roles when the two workloads have distinct ownership or security boundaries.

### 11.3. KMS permissions with SSE-KMS

If the queue uses a customer-managed KMS key, producers and consumers need KMS permissions matching the encryption workflow and key policy. Typically evaluate `kms:GenerateDataKey`/`kms:Decrypt` for producers and `kms:Decrypt` for consumers, depending on integration and key usage.

Both the KMS key policy and IAM identity policy must allow access. An SQS queue policy cannot replace a KMS key policy. Never grant `kms:*` across all keys.

### 11.4. Encryption in transit and at rest

SQS APIs use HTTPS/TLS to protect requests in transit. Server-side encryption protects message bodies at rest. Choose SSE-SQS or SSE-KMS based on compliance, key ownership, auditing, and cross-account requirements.

Never place secrets in message bodies just because the queue is encrypted; consumers, DLQ readers, logs, and exports can still read payloads.

### 11.5. VPC endpoints for SQS

In private environments, use an **Interface VPC Endpoint** for SQS:

- Enable Private DNS if required by the architecture;
- Allow HTTPS/443 from worker security groups on the endpoint security group;
- Scope queues/actions via the endpoint policy;
- Allow the intended principals via the queue/resource policy;
- Verify DNS and routing from ECS/EKS/EC2 subnets;
- Confirm the endpoint and queue reside in the matching partition/Region.

PrivateLink alone does not satisfy IAM authorization. Both a network path and valid policies are required.

### 11.6. Queue URLs and Regions

The SQS client Region must match the queue Region. Never use a queue URL from another account/Region just because the string parses cleanly. Resolve queue URLs from deployment config/trusted resource discovery, validate account/Region, and never accept arbitrary URLs from external clients.

### 11.7. Example consumer policy scoped to a single queue

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ConsumeOrdersQueue",
      "Effect": "Allow",
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:ChangeMessageVisibility",
        "sqs:GetQueueAttributes",
        "sqs:GetQueueUrl"
      ],
      "Resource": "arn:aws:sqs:ap-southeast-1:111122223333:orders-events"
    }
  ]
}
~~~

This illustrates a consumer policy requiring receive, delete, and visibility extension. If the listener uses a fixed queue URL directly, `GetQueueUrl` may be omitted; if visibility extension is unused, omit `ChangeMessageVisibility`. Producers should have a separate policy granting only `sqs:SendMessage`. Add dedicated KMS permissions when using SSE-KMS and inspect queue/key resource policies.

## 12. Concurrency, backpressure, and throughput

### 12.1. Bounded concurrency

If each message takes 2 seconds and the container allows 100 concurrent messages, the downstream database can receive 100 concurrent operations from a single instance. Across 10 ECS tasks, theoretical concurrency reaches 1,000.

~~~text
Total in-flight work
  = number of worker instances
    x maxConcurrentMessages per instance
~~~

Capacity sizing must consider:

- Database connection pools;
- Downstream API rate limits;
- CPU/memory;
- SQS in-flight message quotas;
- FIFO message group concurrency;
- Retry/visibility behavior.

Never crank concurrency to an arbitrary high number assuming the queue will simply drain faster.

### 12.2. Backpressure

When the database becomes overloaded:

- Lower `maxConcurrentMessages`;
- Slow down worker scaling or temporarily pause listeners;
- Apply circuit breakers/rate limiters;
- Configure controlled visibility/retry policies;
- Monitor oldest message age and backlog;
- Stop pulling more messages than can be durably processed.

Backpressure protects downstream systems, yet causes backlog growth. Configure SLO alerts and capacity plans to drain the backlog before message retention expires.

### 12.3. FIFO concurrency

FIFO can process concurrently across distinct `MessageGroupId`s while preserving order within each group. A group whose head message retries for a long time blocks subsequent messages in that same group (head-of-line blocking).

Choose group IDs granular enough to allow parallelism while preserving invariants. Never split one order across multiple groups if its state transitions require strict ordering.

### 12.4. Batch size

SQS `ReceiveMessage` returns up to **10 messages per call**. Larger batches cut API calls, yet can:

- Increase the time for an entire batch to finish;
- Increase memory usage;
- Extend required visibility timeouts;
- Cause batch retries to trigger extra duplicate work;
- Complicate failure isolation.

With Spring Cloud AWS, `maxMessagesPerPoll` and `maxConcurrentMessages` are distinct knobs; understand version semantics and measure before raising them.

### 12.5. Scaling on queue metrics

Workers can scale on backlog/oldest message age, though never solely on visible message count. If messages are in flight or a dependency is throttling, adding workers can worsen contention.

Use autoscaling with cooldowns, maximum capacity caps, and downstream alarms. With FIFO, the number of active message groups can limit effective parallelism regardless of high worker counts.

## 13. Graceful shutdown and message ownership

### 13.1. Why can shutdown cause duplicates?

A container may be mid-message when an ECS task/Kubernetes pod receives a terminate signal. If the process stops before the transaction finishes:

- The message is not acknowledged;
- Visibility timeout expires;
- SQS redelivers the message to another worker.

If the transaction committed yet the process stopped before ack, the message redelivers and inbox idempotency detects the duplicate.

This is a normal failure mode for distributed consumers—never a reason to ack early.

### 13.2. Recommended shutdown sequence

~~~mermaid
sequenceDiagram
    participant P as Platform (ECS/K8s)
    participant C as SQS container
    participant W as Worker
    participant DB as Database
    P->>C: SIGTERM / stop lifecycle
    C->>C: Stop new polling
    C->>W: Allow in-flight work to finish
    W->>DB: Commit transaction
    W->>C: Listener success
    C->>P: Drain/close within grace period
    Note over P,C: Work not completed must remain unacknowledged
~~~

During shutdown:

1. Stop polling for new messages;
2. Wait for in-flight processing within the grace period;
3. Commit transactions and ack completed messages;
4. Leave incomplete messages unacknowledged;
5. Close SQS/HTTP clients after the listener container stops.

### 13.3. Spring Boot graceful shutdown

`server.shutdown=graceful` primarily governs graceful shutdown of the embedded web server; it does not automatically prove every SQS listener drained. Spring lifecycle timeout can be configured:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 45s
~~~

45 seconds is an example. Check listener container lifecycle behavior for your Spring Cloud AWS version, set a sufficient application termination grace period, and test `SIGTERM` while messages are in flight.

### 13.4. ECS and Kubernetes

- ECS `stopTimeout`/task shutdown window must exceed expected drain time within platform limits;
- Kubernetes `terminationGracePeriodSeconds` must match maximum processing duration;
- Do not let readiness/liveness probes trigger restart loops during transient queue/service outages;
- If the shutdown timeout expires, the process can be killed; inbox/idempotency must still guard against duplicates;
- Do not rely on `preStop` sleeps as a substitute for proper listener lifecycles.

### 13.5. In-flight work and visibility timeout

If a container stops polling while a message is still running, visibility must remain long enough for the worker to drain. If work cannot finish before the deadline, leave the message unacknowledged and accept redelivery. Never extend visibility indefinitely just to avoid duplicates; idempotency is the proper safeguard.

## 14. Observability: metrics, logs, and tracing

### 14.1. SQS CloudWatch metrics

Key queue metrics:

| Metric | Meaning | Alert when |
|---|---|---|
| `ApproximateNumberOfMessagesVisible` | Messages waiting to be received | Sustained backlog growth |
| `ApproximateNumberOfMessagesNotVisible` | In-flight messages | Abnormal spikes or stuck messages |
| `ApproximateNumberOfMessagesDelayed` | Delayed messages | Unexpected surge in retry delays |
| `ApproximateAgeOfOldestMessage` | Age of oldest message | Exceeds processing SLO/retention budget |
| `NumberOfMessagesSent` | Messages sent to queue | Traffic spikes/producer loops |
| `NumberOfMessagesReceived` | Messages received | Rising retries/duplicates |
| `NumberOfMessagesDeleted` | Messages deleted | Compare against received/succeeded |
| `NumberOfEmptyReceives` | Polls returning no messages | Polling inefficiency/misconfiguration |

Queue metrics have specific aggregation semantics and several are approximate. Do not treat `NumberOfMessagesReceived - NumberOfMessagesDeleted` as an exact unprocessed count in all cases.

### 14.2. Application metrics

Emit custom metrics per queue/consumer:

- `messages_processed_total`;
- `messages_duplicate_total`;
- `messages_retryable_failure_total`;
- `messages_permanent_failure_total`;
- `message_processing_duration`;
- `message_receive_count`;
- `idempotency_conflict_total`;
- `outbox_publish_lag`;
- `dlq_message_count`;
- `downstream_dependency_error_total`.

Keep metric dimensions low-cardinality, such as queue, event type, and result. Never use event ID, order ID, or user ID as metric dimensions because cardinality explodes and may expose sensitive data.

### 14.3. Structured logs

Safe logging example:

~~~json
{
  "level": "INFO",
  "message": "SQS event processed",
  "queue": "orders-events",
  "eventType": "OrderCreated",
  "eventId": "evt-8b1f4d",
  "sqsMessageId": "sqs-message-id",
  "receiveCount": 2,
  "result": "DUPLICATE",
  "correlationId": "req-456",
  "durationMs": 14
}
~~~

Log only identifiers needed for operations per policy. Never log raw message bodies, credentials, session tokens, payment details, or full customer PII. Protect `eventId` and `MessageId` according to data classification if they can link to users.

### 14.4. Distributed tracing

Propagate trace context via message attributes or the event envelope per your convention (e.g., W3C Trace Context). The producer creates a publish span; the consumer creates receive/process spans; outbox relays and downstream calls link trace context.

SQS is an asynchronous boundary, so traces split across producer and consumer spans. Never expect an HTTP request span to remain open when a consumer runs minutes later.

### 14.5. SLO-based alerts

Useful alerts:

- Oldest message age exceeds threshold;
- Visible backlog growing continuously;
- Any messages in DLQ;
- Sudden spike in retry/duplicate ratio;
- Processing p95/p99 exceeds budget;
- Stuck in-flight messages;
- Consumer count = 0 when queue needs draining;
- High downstream DB/API throttling or error rates.

Attach runbooks/owners to alerts and avoid paging on brief spikes that do not threaten SLOs.

## 15. Testing listeners, retries, and idempotency

### 15.1. Unit testing the business processor

Test cases to cover:

1. New event: business state updated, inbox row inserted;
2. Same event ID re-sent: business update not applied a second time;
3. Business update fails: transaction rolls back inbox row as well;
4. Two concurrent workers: unique constraint lets only one transaction apply;
5. External side effect: outbox record created in the same transaction;
6. Unsupported event schema version: permanent failure handled per policy.

Do not merely mock repositories to claim idempotency; write integration tests against a real database/unique constraint (such as Testcontainers PostgreSQL).

### 15.2. Integration testing with an SQS emulator

LocalStack or Testcontainers helps test queue integration:

- Create Standard and FIFO queues;
- Send messages and receive via listener;
- Verify acknowledgment/deletion;
- Throw retryable exceptions to confirm redelivery;
- Verify DLQ redrive at `maxReceiveCount`;
- Test duplicate event IDs;
- Test FIFO ordering per group;
- Send `SIGTERM` mid-processing to verify shutdown.

Emulators do not faithfully replicate IAM, KMS, quotas, eventual delivery, endpoint policies, or every AWS behavior. Keep a set of smoke tests in a controlled AWS sandbox.

### 15.3. Testing the commit-before-ack crash window

This is a critical test:

~~~text
1. Worker receives event E.
2. Inbox + business update commit.
3. Test simulates a crash before acknowledgment.
4. Visibility timeout expires, E is redelivered.
5. Worker processes E a second time.
6. Inbox unique constraint detects duplicate.
7. Business update does not execute again.
8. Listener returns success and acks.
~~~

This test proves idempotency at the business database layer rather than merely asserting a listener method ran once.

### 15.4. Testing retries and DLQs

- Use short visibility timeouts in a test sandbox;
- Intentionally throw controlled exceptions;
- Observe receive count incrementing;
- Confirm message moves to DLQ after `maxReceiveCount`;
- Redrive after fixing the consumer;
- Verify idempotency still holds when the message returns to the source queue.

Never lower production visibility timeouts to test. Test queues/DLQs must have dedicated names, tags, and owners.

### 15.5. Load and backpressure testing

Gradually increase producer rate and observe:

- Queue age/backlog;
- Worker concurrency and memory;
- DB connection pool saturation;
- Downstream throttling;
- Visibility expirations/duplicate processing;
- Retry/DLQ rates;
- End-to-end p95/p99 latency.

Load tests must use synthetic data and budgets. Never run flood tests against production queues.

## 16. Design scenario: OrderCreated worker

### 16.1. Requirements

A course-selling platform has the following requirements:

- API creates orders and records `OrderCreated` events;
- Consumer updates a projection and triggers email delivery;
- An order must never have state applied twice due to duplicate messages;
- Payment/email providers may time out;
- Workers run across multiple ECS tasks;
- Queues may accumulate backlog during downstream database maintenance;
- Permanently failing messages must move to a DLQ for investigation;
- The system needs age/backlog monitoring and safe shutdown.

### 16.2. Proposed architecture

~~~mermaid
flowchart TD
    API[Spring Boot Order API] --> DB[(Orders DB)]
    DB --> OB[Transactional outbox]
    OB --> RELAY[Outbox relay]
    RELAY --> Q[(SQS Standard)]
    Q --> W1[Spring Boot worker task 1]
    Q --> W2[Spring Boot worker task 2]
    Q --> W3[Spring Boot worker task N]
    W1 --> TX[Inbox + projection transaction]
    W2 --> TX
    W3 --> TX
    TX --> OUT[Notification outbox]
    OUT --> NP[Notification publisher]
    NP --> EMAIL[Email provider]
    Q -->|redrive| DLQ[(Orders DLQ)]
~~~

### 16.3. Processing flow

1. The API creates the order and outbox event within the same RDS transaction.
2. The relay publishes the event with a stable event ID.
3. SQS delivers the message to a worker.
4. The listener deserializes the envelope and calls `OrderEventProcessor`.
5. The processor inserts an inbox record using a unique key.
6. If duplicate, return `DUPLICATE` without updating the projection.
7. If new, update the projection and insert the notification outbox row in the same DB transaction.
8. Transaction commits; listener returns success.
9. Spring Cloud AWS `ON_SUCCESS` acknowledges the message.
10. The notification publisher sends the email with an idempotency key if supported by the provider, and updates outbox status.
11. Transient errors are left unacknowledged; SQS redelivers per visibility/redrive.
12. Poison errors move to the DLQ; alert and triage before redriving.

### 16.4. Decisions to capture in an ADR

- Standard vs. FIFO; if FIFO, which aggregate needs ordering?
- Where is `eventId` generated and how is it kept stable across retries?
- What is the database inbox unique key and retention window?
- Which transaction manager covers business writes and inbox/outbox?
- Visibility timeout and maximum processing duration?
- `maxReceiveCount`, DLQ retention, and redrive owner?
- Listener concurrency relative to the database pool?
- External API idempotency/reconciliation?
- Shutdown grace period?
- SLOs/alarms and replay auditing?

## 17. Fault diagnosis and runbook

### 17.1. Common incident table

| Symptom | Possible cause | Check and resolve |
|---|---|---|
| Message arrives repeatedly | Visibility timeout too short, worker crash, delete failure | Compare processing duration, visibility, and delete/ack errors |
| Duplicate DB updates | Missing durable idempotency or changing event ID | Inbox unique key, producer event identity |
| Listener succeeds yet business incomplete | Exception caught and swallowed before return | Propagate exceptions or record terminal outcome before ack |
| Message never retries | Listener acks early or wrong manual ack | Check acknowledgment mode and ack calls |
| Message hits DLQ too early | Low `maxReceiveCount` or prolonged transient outage | Check receive count, retry budget, and dependency health |
| DLQ growing continuously | Poison payload, schema mismatch, IAM/config error | Classify error and halt automatic redrive |
| FIFO group stalled | Head message in group retrying long or poisoned | Inspect group ID, visibility, and DLQ; review ordering contract |
| Consumer receives no messages | Wrong Region/queue URL, IAM deny, listener not started | Check effective Region, queue name, `ReceiveMessage` permission |
| SQS `AccessDenied` | IAM role, queue policy, endpoint policy | Inspect principal/resource/condition |
| KMS `AccessDenied` | Missing KMS permissions or key policy | Check key policy and producer/consumer grants |
| `UnknownHost`/timeout | DNS/VPC endpoint/routes/SG | Test DNS, HTTPS/443, and endpoint policy |
| Deserialization error | JSON/schema/content type mismatch | Check `schemaVersion`, converter, and payload shape |
| Oldest message age rising | Low consumer capacity or slow downstream | Backpressure, concurrency, dependency latency |
| In-flight messages climbing indefinitely | Stuck worker, visibility extension loop, or ack skipped | Thread dumps, processing spans, visibility lifecycle |
| Redrive fails | Mismatched DLQ type/policy/permissions | Check source/DLQ types, redrive allow policy, and IAM |

### 17.2. 10-step runbook

~~~text
1. Identify source queue, DLQ, Region, account, and consumer deployment.
2. Inspect ApproximateAgeOfOldestMessage and visible/not-visible backlog.
3. Check DLQ count, receive count, and event type/schemaVersion.
4. Cross-check eventId against inbox/idempotency records.
5. Determine whether the transaction committed or external side effects ran.
6. Classify as transient, poison, business rejection, or IAM/configuration.
7. Verify visibility timeout, maxReceiveCount, and listener acknowledgment mode.
8. Inspect worker concurrency, DB pool, downstream throttling, and networking.
9. Fix root cause, run sandbox tests, and verify duplicate safety.
10. Execute controlled redrive, monitor metrics, and record audit logs.
~~~

Never redrive a DLQ just to bring the queue count back to zero. If the root cause remains unfixed, messages will return to the DLQ and add load.

### 17.3. Safe redrive

Before redriving:

- Confirm the fixed consumer version is deployed;
- Check whether events already produced prior side effects;
- Confirm inbox/idempotency retention has not expired;
- Set a redrive rate matched to capacity;
- Limit the initial batch and observe metrics;
- Ensure an owner, ticket/change record, and stop/rollback criteria exist.

When replaying history past idempotency retention, create a reconciliation process or business-specific replay key. Never delete processed IDs just to “re-run” without evaluating side effects.

## 18. Self-check questions and answers

### 18.1. Questions

1. Why is SQS Standard designed for at-least-once delivery?
2. Within what scope does SQS FIFO guarantee ordering?
3. How long is the FIFO `MessageDeduplicationId` deduplication window?
4. Why does FIFO still require consumer idempotency?
5. When does the visibility timeout start?
6. What happens if a consumer fails to delete a message?
7. When is `ChangeMessageVisibility` needed?
8. What is the maximum long polling duration in seconds?
9. What is `maxReceiveCount` used for?
10. Must a source queue and its DLQ be the same queue type?
11. Why should DLQ retention be longer than the source queue's retention?
12. Does SQS `MessageId` replace a business `eventId`?
13. Why shouldn't `ApproximateReceiveCount` be used as an idempotency key?
14. What does `AcknowledgementMode.ON_SUCCESS` mean?
15. Why shouldn't exceptions be swallowed and returned from a listener?
16. Which transaction should contain both the inbox record and business update?
17. Why is `SELECT` followed by `INSERT` insufficient to stop duplicate races?
18. How does a transactional outbox close the dual-write gap?
19. Is `@Transactional` atomic with `DeleteMessage` or external HTTP APIs?
20. Why must acknowledgment follow durable commit?
21. How does `maxConcurrentMessages` affect downstream capacity?
22. Why can a FIFO message group cause head-of-line blocking?
23. Which CloudWatch metrics help detect backlogs and DLQs?
24. What should graceful shutdown do with in-flight messages?
25. Why can't LocalStack tests replace AWS sandbox smoke tests?

### 18.2. Suggested answers

1. SQS can redeliver messages in certain failure scenarios; consumers must tolerate duplicates.
2. In order within the same `MessageGroupId`; different groups can run in parallel.
3. 5 minutes.
4. A consumer can still commit and crash before deleting; the message will redeliver.
5. When SQS delivers the message to a consumer on receive.
6. The message becomes visible again after the visibility timeout expires.
7. When processing exceeds the expected timeout and the message must stay in flight safely.
8. 20 seconds.
9. Limits receive attempts before redriving to the DLQ.
10. Yes; Standard sources use Standard DLQs, and FIFO sources use FIFO DLQs.
11. To preserve time for investigation/replay; expiration semantics also vary by queue type.
12. No; `MessageId` is a transport identity, whereas `eventId` is a stable business identity across retries.
13. Receive count only tracks approximate delivery attempts, not business operation identity.
14. Acknowledge only when the listener completes successfully.
15. The framework may treat a normal return as success and delete the message before business work finishes.
16. The same transaction as business database writes, inbox unique insert, and outbox insert if needed.
17. Two workers can both observe “not found” before inserting; only a unique constraint/conditional write is atomic.
18. Business updates and event intent are committed in one database transaction; the relay may re-publish, so consumers stay idempotent.
19. No; transactions cover only resources managed by the transaction manager.
20. Acking before commit risks losing events if the process crashes.
21. Total concurrency multiplies across instances and must fit within DB pools/downstream limits.
22. A retrying head message blocks subsequent messages in that same group.
23. `ApproximateAgeOfOldestMessage`, `ApproximateNumberOfMessagesVisible`/`NotVisible`, DLQ visible count, and custom failure metrics.
24. Stop polling, drain/commit/ack completed messages; leave incomplete messages unacknowledged for redelivery.
25. Emulators do not fully reproduce IAM/KMS/quotas/networking/production delivery behavior.

## 19. Production deployment checklist

### Queues and delivery

- [ ] Standard vs. FIFO selected based on ordering and throughput needs.
- [ ] Event envelope carries a stable `eventId`, `eventType`, `schemaVersion`, `occurredAt`, and correlation ID.
- [ ] Visibility timeout sized to processing p99 + margin.
- [ ] Long polling and HTTP response timeouts aligned compatibly.
- [ ] Queue retention covers backlog and recovery windows.
- [ ] DLQ matches source queue type, with proper redrive policy and retention.
- [ ] `maxReceiveCount` aligned with retry budget.
- [ ] Redrive allow policy, replay owner, and audit workflow defined.
- [ ] FIFO `MessageGroupId` partitioned by the aggregate needing ordering.
- [ ] FIFO `MessageDeduplicationId` kept stable; not treated as durable idempotency.

### Consumers and correctness

- [ ] Spring Cloud AWS/Spring Boot versions managed via a compatible BOM.
- [ ] Acknowledgment mode configured explicitly and tested on the exact version.
- [ ] Listeners never swallow exceptions when processing has not completed.
- [ ] Inbox/processed-message table enforces a unique key on consumer + business event ID.
- [ ] Inbox insert and business DB changes execute within the same transaction.
- [ ] Duplicates treated as success and acknowledged after verifying durable state.
- [ ] External side effects use outboxes, provider idempotency, or reconciliation.
- [ ] DB transactions are never held open during slow HTTP calls.
- [ ] Retries distinguish transient, permanent, business, and configuration errors.
- [ ] Never use `Thread.sleep` inside listeners for backoff.
- [ ] Idempotency retention exceeds retry/DLQ/replay horizons.

### Security and operations

- [ ] Consumer/producer IAM roles follow least privilege scoped to queue ARNs.
- [ ] KMS key policies/permissions tested when using SSE-KMS.
- [ ] VPC endpoints/DNS/SG/queue policies verified from the runtime.
- [ ] Raw payloads, PII, credentials, and presigned URLs are never logged.
- [ ] Alarms cover backlog, oldest age, in-flight count, retries, duplicates, and DLQ.
- [ ] Trace context/correlation IDs propagate across the asynchronous boundary.
- [ ] Listener concurrency fits DB pools and downstream rate limits.
- [ ] Graceful shutdown stops polling and drains in-flight work within the grace period.
- [ ] Tests cover crash-after-commit-before-ack, retries, DLQs, and duplicate races.
- [ ] AWS sandbox smoke tests exist alongside emulator tests.
- [ ] Runbooks, redrive audits, capacity plans, and budgets are in place.

**Expected outcome:** you can build an SQS listener in Spring Boot with bounded retries, durable idempotency, acknowledgment after durable outcomes, controlled DLQ/replay workflows, and sufficient observability to operate cleanly when consumers or downstreams fail.

## Official AWS and Spring Documentation

- [Amazon SQS at-least-once delivery](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/standard-queues-at-least-once-delivery.html)
- [Amazon SQS visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html)
- [Amazon SQS long polling](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-short-and-long-polling.html)
- [Amazon SQS dead-letter queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html)
- [Amazon SQS redrive allow policy](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html)
- [Amazon SQS FIFO queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-queues.html)
- [Amazon SQS message deduplication](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-queues-exactly-once-processing.html)
- [Amazon SQS message attributes and system attributes](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-message-metadata.html)
- [Amazon SQS CloudWatch metrics](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-available-cloudwatch-metrics.html)
- [Amazon SQS server-side encryption](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-server-side-encryption.html)
- [Amazon SQS IAM policy examples](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-basic-examples-of-sqs-policies.html)
- [AWS SDK for Java 2.x SQS examples](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/examples-sqs.html)
- [Spring Cloud AWS reference documentation](https://docs.awspring.io/spring-cloud-aws/docs/current/reference/html/index.html)
- [Spring Cloud AWS SQS integration](https://docs.awspring.io/spring-cloud-aws/docs/current/reference/html/index.html#sqs-integration)
- [Spring Framework transaction management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)

> **Application note:** Queue names, ARNs, event IDs, order IDs, account IDs, timeouts, and code in this lesson are training examples. Never apply sample commands/configurations directly in production without review. SQS/Spring Cloud AWS APIs, quotas, and behaviors can vary by Region/version; pin dependency versions, consult the matching documentation, test in a sandbox, and protect sensitive data.
