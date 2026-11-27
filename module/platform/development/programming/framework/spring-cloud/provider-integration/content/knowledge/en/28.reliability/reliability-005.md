# Distinguishing Delivery Guarantees from Business-Effect Guarantees

A broker successfully delivering a message does not mean the business logic executed exactly once. A consumer can write to the database and crash before sending an ACK; the broker will redeliver the message and the consumer may run again. Conversely, if the consumer sends an ACK before committing data, the broker may discard the message even though the business work never finished.

When integrating Spring Boot with Azure Service Bus, Event Hubs, AWS SQS, Kinesis, or Google Cloud Pub/Sub, distinguish two questions:

- **Delivery guarantee:** how do the broker and client coordinate so a message is delivered, held, retried, or acknowledged?
- **Business-effect guarantee:** are database state, payments, files, emails, or external actions applied exactly once in business terms?

A broker may provide at-most-once, at-least-once, or a scoped exactly-once mode. Yet a business side effect often spans multiple systems and transaction boundaries. To achieve **effectively-once** behavior, the application must combine delivery semantics with idempotency, transactions, inbox/outbox, deduplication, and reconciliation.

This lesson belongs to the **Reliability** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module: practicing the integration of Spring Boot with managed services from AWS, Azure, and Google Cloud via the corresponding Spring Cloud libraries; learning identity and permissions configuration, storage access, messaging, data, secret protection, integration testing, and evaluating differences across cloud providers.

## 1. Learning Objectives

After this lesson, learners can:

1. Distinguish at-most-once, at-least-once, exactly-once delivery, and effectively-once business effects.
2. Separate the milestones of publish, broker acceptance, delivery, processing, commit, side effect, and ACK.
3. Explain why ACKing before commit risks losing business effects, while committing before ACK can cause redelivery.
4. Design idempotent consumers using an inbox table, unique constraints, and transactions.
5. Combine a transactional outbox with publisher retries and stable message IDs.
6. Understand the scopes of Azure Service Bus/Event Hubs, AWS SQS/Kinesis, and Google Cloud Pub/Sub.
7. Recognize that exactly-once delivery does not automatically make databases, payments, emails, or external services exactly-once.
8. Handle message locks, visibility timeouts, ack deadlines, checkpoints, ordering, and dead-letter queues.
9. Design safe replay, reconciliation, and poison-message handling.
10. Test crash windows, duplicate delivery, lost ACKs, and business side effects via fault injection.

## 2. Two Guarantee Layers to Keep Separate

A message flow typically includes these steps:

~~~text
Producer creates event
    → Publish request
    → Broker accepts and stores message
    → Broker delivers message to consumer
    → Consumer runs handler
    → Consumer produces side effect
    → Consumer commits durable state
    → Consumer ACKs/Completes message
~~~

Each arrow can fail independently. For instance, the broker stored the message while the publisher missed the confirmation; the consumer committed the database while the ACK was lost; or a payment API processed the request while the response timed out.

| Layer | Guarantee to Examine | Primary Controlling Component |
| --- | --- | --- |
| Publish | Did the broker accept the message? | Producer SDK, broker confirmation, retries, and message ID |
| Delivery | Is the message delivered at-most-once or at-least-once? | Broker, subscription/queue, lock/visibility/ack |
| Processing | Can the handler run again? | Consumer, worker lifecycle, retry/redelivery |
| Persistence | Is business state committed? | Database transaction, unique constraint, conditional write |
| External side effect | Did the payment/email/API/file happen? | Provider idempotency, operation reference, reconciliation |
| ACK/checkpoint | Was the broker notified that the message was processed? | Consumer settlement/ack/checkpoint |

**A delivery guarantee is not a business-effect guarantee.** The broker only knows message state under its own protocol. The broker generally cannot know whether the application's database transaction committed or whether a payment provider already charged the card.

## 3. Three Common Delivery Models

### 3.1. At-Most-Once Delivery

A message is delivered at most once within the chosen semantics. If a failure strikes at an unfortunate moment, the message can be lost or never retried.

Characteristics:

- Avoids redelivery/duplicates within the defined delivery scope.
- Can drop messages if the consumer or ACK path fails.
- Suitable when losing occasional events is acceptable or data can be regenerated.
- Unsuitable for business operations that require every request to be processed.

Example: a consumer receives messages in receive-and-delete mode. The broker removes the message from the queue upon delivery; if the process dies right after receiving it, the message is no longer available for redelivery.

### 3.2. At-Least-Once Delivery

The broker continues redelivering until it receives a valid ACK/Complete or the message reaches expiration/DLQ per policy.

Characteristics:

- Reduces the risk of losing messages when a consumer crashes.
- Messages can be delivered more than once.
- Consumers must tolerate duplicate delivery.
- This is the standard model across most managed queues/brokers.

Example: a consumer receives a message, writes to the database, and crashes before completing. The lock/visibility/ack deadline expires; the broker redelivers the message.

### 3.3. Exactly-Once Delivery

A service may offer an exactly-once feature within a specific scope, such as receiving messages or processing a stream within a supported subscription/transaction boundary.

Ask precisely:

- Does exactly-once apply to producer publish, broker storage, consumer delivery, or stream processing?
- Is the scope a queue, subscription, partition, session, or transaction?
- How long does the deduplication/retention window last?
- What are the region, protocol, client library, and configuration requirements?
- Must ACK/commit be confirmed before the broker considers the message done?
- Does it cover the database or external APIs the consumer calls?

Never infer that a feature labeled **exactly-once** guarantees end-to-end business effects.

### Quick Comparison

| Delivery Model | Can Lose Messages? | Can Deliver Duplicates? | Must Consumer Be Idempotent? |
| --- | --- | --- | --- |
| At-most-once | Yes, depending on failure/settlement semantics | Per delivery contract, usually no redelivery | Still needed if producer or side effects can repeat |
| At-least-once | Minimizes loss once broker accepts; still depends on retention/DLQ/config | Yes | Yes |
| Scoped exactly-once delivery | Minimizes duplicate delivery within the defined scope | Duplicates can still occur outside that scope or if app side effects repeat | Yes, especially with external side effects |
| Effectively-once business effect | Goal is a single observable business outcome | Requests/messages may still be redelivered or reprocessed | Protected by idempotency/transactions/reconciliation |

## 4. Delivery, Processing, and Business Effect Are Three Different Things

Example consumer processing an OrderPaid event:

1. Broker delivers event.
2. Consumer reads message.
3. Consumer updates order status to PAID.
4. Consumer sends confirmation email.
5. Consumer ACKs message.

If the consumer crashes at each point, the outcome differs:

| Crash Point | Possible State | Risk |
| --- | --- | --- |
| Before handler starts | No side effects yet | Broker can redeliver |
| After reading message, before commit | Business state not committed | Redelivery is usually safe if handler has not triggered external side effects |
| After database commit, before ACK | Database already changed | Redelivery may update/send email a second time |
| After email, before database commit | Email sent, database not updated | Retry may send a duplicate email |
| After ACK, before side effect | Broker considers message finished | Business work may be permanently lost |
| After external provider processed, response lost | Outcome unknown to consumer | Blind retry may trigger side effect a second time |

The hardest gap is **the window between the side effect and the ACK**. Brokers and databases usually do not share a distributed transaction. Consumers must be designed to survive crashes at every boundary.

## 5. ACK Before or After Commit?

### ACK Before Commit: Risk of Losing Business Impact

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Consumer
    participant DB as Database
    B->>C: Deliver message M1
    C->>B: ACK / Complete
    B-->>C: Message settled
    C->>DB: Write business state
    Note over C,DB: Process crashes before commit
    Note over B: Broker will not redeliver message
    Note over DB: Business state was never written
~~~

If you ACK before durable side effects finish, the broker can remove the message from the queue while the business update never committed. With at-least-once queues, the standard pattern is **commit first, then ACK**.

### Commit Before ACK: Duplicates Possible, Yet Controllable

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Consumer
    participant DB as Database
    B->>C: Deliver message M1
    C->>DB: BEGIN + update business + inbox
    DB-->>C: COMMIT
    C->>B: ACK / Complete
    Note over C,B: ACK lost or process crashed
    B->>C: Redeliver M1
    C->>DB: Insert inbox M1
    DB-->>C: Duplicate key
    C->>B: ACK duplicate, do not repeat business effect
~~~

This is the standard pattern with the **inbox pattern**. The database commits first; if the ACK fails, the broker redelivers, but the inbox unique constraint blocks running the business update again.

### Rules

- For consumers updating a database, write the inbox and business state in the same transaction, commit, and then ACK.
- Never ACK a message merely because the handler started or handed work off to a thread pool.
- If handing work off to an internal background queue, durably persist acceptance before ACKing the original message.
- If side effects target external systems outside the database, use provider idempotency keys, outbox/saga, or reconciliation.
- A failed ACK after commit is a normal failure mode to design for; never treat it as a rare edge case to ignore.

## 6. Why Is End-to-End Exactly-Once So Hard?

Suppose a consumer needs to:

1. Write to a database.
2. Charge a payment provider.
3. Send an email.
4. Complete the message.

These systems do not share one atomic transaction. No single commit can simultaneously lock all side effects.

~~~mermaid
flowchart LR
    M[Broker message] --> C[Spring Boot consumer]
    C --> D[(Database)]
    C --> P[Payment provider]
    C --> E[Email provider]
    C --> A[Broker ACK]
    D -. separate transaction .- P
    P -. separate API .- E
    E -. not in same transaction .- A
~~~

Scenarios:

- Payment provider charged the card, but the consumer lost the response.
- Database commit succeeded, email provider timed out.
- Email sent, consumer crashed before ACK.
- ACK succeeded while database transaction had not committed if ordered wrongly.
- Consumer retries when unsure whether the payment succeeded.

To guarantee a single business outcome, define **invariants** and control each side effect. Systems typically achieve **effectively-once** via:

- Stable idempotency keys across retries.
- Unique constraints/conditional writes at state stores.
- Transactional outbox/inbox.
- Provider APIs supporting idempotency keys.
- State machines/sagas and compensation.
- Reconciliation when outcomes are unknown.
- ACK/checkpoint only after protected state is durable.

No single Spring annotation or broker flag automatically makes all of these systems exactly-once together.

## 7. Effectively-Once: Guaranteeing the Observable Outcome

**Effectively-once** is a design goal: even though messages or requests may be delivered or called multiple times, the system produces one business outcome according to defined invariants.

Example: an OrderPaid event may be delivered 3 times, yet:

- The order table transitions to PAID only once.
- The ledger records only one transaction for that unique business reference.
- The email is sent under a deduplicated notification operation ID.
- The consumer ACKs redeliveries without repeating side effects.

To achieve that, distinguish:

| Component | Protection Mechanism |
| --- | --- |
| Business state in database | Unique constraint, transaction, conditional update |
| Event/command identity | Stable event ID or idempotency key |
| Consumer processing | Inbox/processed-message record |
| Publish intent | Transactional outbox |
| External API | Provider idempotency key or operation-reference lookup |
| Storage object | Deterministic object key, ETag/generation precondition |
| Recovery | State machine, DLQ, reconciliation, and controlled replay |

**Effectively-once does not mean a message is delivered only once.** It means repeated deliveries do not cause unintended changes to the business outcome.

## 8. Inbox Pattern: Protecting Consumer Database Transactions

An inbox table records messages a consumer has processed. The unique key typically combines consumer name and message ID so different consumer logics can independently process the same message if needed.

PostgreSQL example:

~~~sql
CREATE TABLE processed_messages (
    consumer_name VARCHAR(120) NOT NULL,
    message_id    VARCHAR(200) NOT NULL,
    payload_hash  VARCHAR(64) NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    result_ref    VARCHAR(200),
    PRIMARY KEY (consumer_name, message_id)
);
~~~

### Processing Flow

1. Receive message with a stable event ID.
2. Canonicalize the payload and compute a fingerprint if needed.
3. Start a database transaction.
4. Insert the inbox record.
5. On unique conflict:
   - Read the stored fingerprint.
   - If the fingerprint matches, this is a redelivery of the same event; skip the business update.
   - If the fingerprint differs, a producer misused/reused a message ID; route to error handling/investigation.
6. If insert succeeds, apply the business state transition.
7. Commit the inbox and business state in the same transaction.
8. ACK/Complete the message after commit.

### Transaction Diagram

~~~text
BEGIN
  INSERT processed_messages(consumer_name, message_id, payload_hash)
  UPDATE orders / INSERT ledger / UPDATE business state
COMMIT

ACK message
~~~

If the transaction rolls back, both the inbox record and business update roll back together. When the broker redelivers, the consumer can reprocess it. If the transaction commits and the ACK fails, redelivery is blocked by the inbox.

### Consumers Must Have Explicit Scope

Do not rely on message ID alone if multiple producers or consumers share a broker/namespace. Scope can be:

~~~text
(consumer_name, event_id)
~~~

If an event has multiple schema versions, compute the fingerprint from the canonicalized payload and version. Never treat the same event ID with a different payload as a valid duplicate.

## 9. Transactional Outbox: Protecting the Producer

Outbox protects the boundary between business transactions and message publishing.

Suppose the Order API updates the database and must emit OrderCreated:

~~~text
BEGIN DATABASE TRANSACTION
  INSERT orders(...)
  INSERT outbox_events(event_id, event_type, payload, status)
COMMIT

Publisher worker:
  Claim pending outbox event
  Publish with stable event_id as message ID
  Mark sent after broker confirmation
~~~

If the database commits while the broker is temporarily unavailable, the event remains in the outbox. The publisher can retry later. If the broker accepted the message and confirmation was lost, the publisher can resend with the same event ID; the consumer inbox or broker duplicate detection handles duplicates.

### Outbox Does Not Guarantee Publish-Exactly-Once

There is a gap:

1. Broker accepts the message.
2. Publisher loses confirmation or crashes.
3. Outbox record remains PENDING.
4. Publisher restarts and sends the same event again.

Thus outbox guarantees **publish intent is not lost** once the database commits, yet duplicates can still be emitted. Use stable event IDs, consumer inboxes, and idempotency to achieve effectively-once.

### Claiming Events Across Multiple Publishers

Multi-replica publishers must claim records atomically—using database row locks, **FOR UPDATE SKIP LOCKED**, or leases with owner tokens/expiry. However, claiming does not eliminate all duplicates: a publisher may lose its lease while publishing after the broker already accepted the message, and a new worker reclaims it. Consumers still must deduplicate.

## 10. Event Identity: Message ID, Event ID, and Correlation ID

These IDs serve distinct purposes:

| ID | Purpose | Stable Across Retries? |
| --- | --- | --- |
| **Event ID** | Identifies an emitted business event | Yes |
| **Message ID** | Identifies a message in the broker | Should be, usually derived from event ID |
| **Idempotency key** | Identifies an intent/command that may be resent | Yes |
| **Correlation ID** | Links steps across a workflow/request | Can remain constant across workflow |
| **Trace ID** | Observes a single trace execution | May differ on redelivery/replay depending on tracing strategy |
| **Delivery count** | Number of times the broker delivered the message | Changes per delivery |

Never use Trace ID as a deduplication key: a new trace may start on message redelivery. Never generate a new Message ID on each publisher retry. Never use delivery count as a business identity.

### Stable Event IDs

Producers should generate the event ID when writing the business event/outbox and persist it in the same transaction. Every re-publish of that event must reuse the same ID. If the event belongs to an aggregate, combine aggregate ID and event sequence/version to detect duplicate or out-of-order events.

## 11. Azure Service Bus: Locks and Settlement Do Not Mean Exactly-Once

Azure Service Bus offers distinct receive modes and settlement semantics.

### Peek-Lock

- The broker holds the message and grants a lock to the consumer.
- The consumer processes the message.
- The consumer calls Complete upon finishing.
- If the consumer calls Abandon, the lock expires, or the process crashes, the message can be redelivered.
- Lock duration and auto-renewal have configuration/service limits.
- Delivery count increments on redelivery; exceeding MaxDeliveryCount can move the message to the dead-letter queue.

This model supports **at-least-once processing**. Consumers must be idempotent.

### Receive-and-Delete

The broker deletes the message as soon as it delivers it to the consumer under this mode's semantics. If the process crashes after receiving but before finishing, the message can be lost. Choose this only when losing messages is acceptable to save a settlement round-trip.

Do not use Receive-and-Delete for payments/orders/commands requiring durable processing unless a separate regeneration/reconciliation mechanism exists.

### Duplicate Detection

Service Bus offers duplicate detection based on MessageId within a configured time window:

- Helps the broker drop duplicate sends with the same MessageId within the entity/window scope.
- Not an unlimited deduplication store.
- A message resent after the window closes or with a different ID is treated as a new message.
- Does not protect side effects a consumer already executed against databases or external APIs.

Still use a consumer inbox/unique constraint for critical business operations.

### Sessions and Ordering

Sessions support sequential processing per session with session locks. This preserves ordering within a session per Service Bus semantics, but does not provide global ordering across all messages in a queue. An expired session lock can still lead to redelivery.

## 12. Azure Event Hubs: A Checkpoint Is a Progress Marker, Not a Business Transaction

Event Hubs is an event streaming service, not a per-message Complete settlement queue like Service Bus.

- Events are appended to partitions.
- Consumers read by offset/sequence within a partition.
- Consumers store checkpoints to record processed positions.
- On restart/rebalance, a consumer resumes from the saved checkpoint.
- If business state committed before the checkpoint was saved, events can be re-read.
- If the checkpoint was saved before business commit, events can be skipped even though side effects never completed.

### Ordering Commit and Checkpoint

For a consumer updating a database:

~~~text
Read event at offset 120
  → Begin DB transaction
  → Insert inbox(event_id) + update business state
  → Commit DB
  → Save Event Hubs checkpoint at offset 120
~~~

If the process crashes after DB commit but before checkpointing, the event can be re-read; the inbox blocks duplicates. If checkpointing happens before DB commit, a crash can lose the business effect.

Checkpoints are typically stored per partition and consumer group. Never treat a successful checkpoint as proof that all external side effects committed if your code updates checkpoints too early.

### Partition Ordering

Event Hubs guarantees ordering within a partition by log/offset, not global ordering across all partitions. If business logic needs ordering per aggregate, producers must pick an appropriate partition key and consumers must validate version/sequence.

## 13. AWS SQS and Kinesis

### SQS Standard

- Provides at-least-once delivery; duplicates can occur.
- Visibility timeout hides a message for a period after receipt.
- The consumer deletes the message after processing succeeds.
- If visibility timeout expires before delete, the message can be redelivered.
- DLQ/redrive policy handles messages exceeding the configured receive count.

Consumers should commit business state and inbox before deleting the message. If delete fails after commit, redelivery must be caught by the inbox.

### SQS FIFO

FIFO supports ordering per message group and deduplication IDs within a service-defined deduplication window. This reduces duplicate publishes within its supported scope, but does not replace an idempotent consumer for databases or external side effects.

Do not confuse FIFO ordering with queue-wide ordering: ordering is maintained per message group. A slow message group can throttle throughput for that group.

### Kinesis Data Streams

Kinesis is a sharded streaming log. Consumers typically track sequence numbers and checkpoint processed positions. If a consumer commits to a database and checkpointing fails, records can be re-read. If checkpointing precedes database commit, a crash can skip business effects.

Use event IDs/sequences, inboxes, or conditional writes to prevent duplicates; handle ordering per shard/partition key and design for resharding/rebalancing.

## 14. Google Cloud Pub/Sub

Pub/Sub supports multiple subscription/delivery modes. Read the exact semantics of your subscription and client library.

### Default At-Least-Once

In the at-least-once model, messages can be redelivered if the subscriber fails to ACK on time or the ACK is not confirmed per contract. Ack deadline and lease extension determine how long a subscriber retains processing rights before redelivery.

Consumers should:

1. Receive message.
2. Write inbox and business state in a transaction.
3. Commit.
4. ACK message.
5. If ACK fails or the subscriber crashes, redelivery is caught by the inbox.

### Exactly-Once Delivery Feature

Pub/Sub offers an exactly-once delivery feature for supported subscription/client modes under specific conditions. Check current documentation for region, subscription type, client library, and ACK confirmation semantics.

Even when a subscription enables exactly-once delivery:

- It does not form a shared transaction with PostgreSQL, Cloud SQL, Firestore, or payment APIs.
- A consumer can still repeat a side effect if code retries or creates a new operation.
- Publisher retries and business command idempotency still require separate handling.
- Replay, seek, or administrative operations may behave differently from normal delivery flows.

### Ordering Keys

Ordering keys help preserve order for messages sharing the same key when supported and configured. Ordering does not equal an exactly-once business effect; consumers still must guard against duplicates, retries, and versioning issues.

## 15. Spring Boot and Spring Cloud Stream: ACK Semantics Belong to the Binder

Spring Boot can consume messages via native SDKs or **Spring Cloud Stream**. Spring Cloud Stream provides uniform function/consumer programming models, while settlement/ack behavior depends on the **binder**, **consumer mode**, **ack configuration**, and version.

Example function bean:

~~~java
import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;

@Configuration
public class OrderEventConsumerConfiguration {

    @Bean
    public Consumer<Message<OrderCreated>> orderCreated(
            OrderApplicationService orderApplicationService) {
        return message -> {
            OrderCreated event = message.getPayload();
            orderApplicationService.handle(event);
        };
    }
}
~~~

This snippet shows the shape of a functional consumer; the specific binder decides when settlement occurs and how exceptions are handled.

### What Must Be Verified in the Binder

- When the handler returns normally, when does the binder ACK/complete?
- When the handler throws an exception, how does the binder retry internally, abandon/nack, or route to a DLQ?
- Is manual acknowledgment available? Which API/context is provided?
- Does the binder integrate with broker or database transactions?
- How do batch listeners handle partial failures?
- Where are consumer concurrency, prefetch, lock renewal, and max delivery configured?
- Do binder retries stack on top of SDK retries or Spring Retry?

Never assume a single ACK configuration works identically across Azure Service Bus, Kafka, RabbitMQ, SQS, and Pub/Sub. Read your binder/version documentation and write integration tests proving commit/ACK ordering.

### Principles Inside the Handler

The handler should invoke an application service with an explicit transaction boundary:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderEventHandler {

    private final InboxRepository inbox;
    private final OrderRepository orders;

    public OrderEventHandler(
            InboxRepository inbox,
            OrderRepository orders) {
        this.inbox = inbox;
        this.orders = orders;
    }

    @Transactional
    public void handle(OrderCreated event) {
        InboxResult result = inbox.tryRecord(
                "order-projection",
                event.eventId(),
                event.payloadHash());

        if (result == InboxResult.DUPLICATE_SAME_PAYLOAD) {
            return;
        }
        if (result == InboxResult.DUPLICATE_DIFFERENT_PAYLOAD) {
            throw new MessageIdentityConflictException();
        }

        orders.applyCreatedEvent(
                event.orderId(),
                event.eventVersion());
    }
}
~~~

This is an illustrative example: tryRecord must rely on a unique constraint/atomic insert, and if the message ID matches with a different payload hash, it must raise a conflict. Broker ACK happens only after the handler call finishes per the binder's settlement semantics.

## 16. Business Side Effects Outside the Database

An inbox protects side effects inside the same database transaction. Yet if a consumer calls a payment provider, sends an email, or writes a Blob, the inbox transaction cannot be atomic with external systems.

### Payment Provider

Use a stable provider idempotency key per payment operation. If a request times out:

- Look up status using the provider reference/key.
- If it succeeded, update local state and do not charge again.
- If not received, retry with the same key per contract.
- If status is unclear, keep UNKNOWN and reconcile.

### Email/Notification

Email providers may not support idempotency. In that case, use a notification outbox, provider message reference, internal deduplication, or accept duplicates per business policy. You cannot claim exactly-once email solely because broker delivery is exactly-once.

### Blob Storage

Use deterministic object keys derived from document/event ID, conditional create/ETag, metadata storing the operation reference, and state checks before re-uploading. If overwrites are allowed, define versioning and conflict handling clearly.

### External APIs

If a partner API supports idempotency keys, pass the same key across all retries. If not, use status lookup, business references, or reconciliation workflows. If there is no way to determine the outcome, do not blindly retry side effects.

## 17. Poison Messages, Retries, and Dead-Letter Queues

A message may fail repeatedly due to invalid payloads, unsupported schema versions, or missing referenced data.

Distinguish:

- **Transient failure:** temporarily unavailable service, network reset, throttling.
- **Permanent failure:** malformed payload, business rule rejection, unprocessable schema.
- **Unknown outcome:** side effect may have happened, but the consumer cannot verify.
- **Poison message:** a message that repeatedly crashes or fails the consumer, due to bad data or a bug.

Never retry poison messages infinitely. Use delivery counts/max attempts, backoff, and broker DLQs. DLQs should preserve message ID, correlation ID, schema version, failure category, and non-sensitive diagnostics.

### DLQ/Replay Workflow

1. Route messages exceeding thresholds to a DLQ or quarantine.
2. Classify the failure and determine whether any side effects already occurred.
3. Fix data/configuration/code or deploy a compatible handler.
4. Verify idempotency/inbox state before replaying.
5. Replay with the original event ID if it represents the same business event.
6. Monitor duplicates, ordering, and replay impact.
7. Audit who replayed, when, and why.

Never assign a new ID when replaying the same event just to bypass deduplication. Doing so tricks the consumer into treating it as a brand-new business event.

## 18. Ordering Does Not Equal Exactly-Once

Messages can arrive in order while side effects repeat; or a message can execute once yet out of order.

| Concept | Question |
| --- | --- |
| Delivery ordering | In what order does the broker deliver messages? |
| Processing ordering | In what order do consumers finish handlers? |
| Commit ordering | In what order does the database commit events? |
| Business sequence | Which event version is valid next? |
| Exactly-once effect | Does one event produce exactly one business effect? |

If OrderCreated version 1 and OrderPaid version 2 reach two parallel workers, version 2 may commit before version 1. Consumers must check aggregate version/sequence, partition/session keys, or serialize processing per aggregate.

You can track the last processed version:

~~~sql
UPDATE order_projection
SET status = 'CONFIRMED',
    last_event_version = :event_version
WHERE order_id = :order_id
  AND last_event_version = :event_version - 1;
~~~

If no row is updated, the version changed or the resource does not exist. Read state and decide to merge/retry/reorder/quarantine; do not silently ignore every conflict.

## 19. Transaction Boundaries and Processing Models

| Model | Guarantee | Limitations |
| --- | --- | --- |
| ACK before side effect | Reduces redelivery after ACK | Can lose business effects if side effect fails |
| Side effect then ACK | Reduces loss after processing; at-least-once | Duplicates if crash happens before ACK |
| Inbox + DB transaction then ACK | Effectively-once DB business state per inbox key | Excludes external side effects outside the transaction |
| Outbox + publisher retry | No lost publish intent once DB commits | Publishing can still duplicate |
| Provider idempotency key | Reduces duplicate side effects at provider per contract | Depends on provider support and key retention/scope |
| Distributed transaction/transactional messaging | Can be atomic across supported participants | Not universal; increases coupling/operational complexity |
| Saga + compensation | Coordinates multi-step distributed work | Compensation is not instant rollback and can fail |

Do not choose distributed transactions merely to avoid writing inbox/outbox. Evaluate participant count, broker/database support, failure recovery, latency, and operations. Across diverse managed services and cloud providers, outbox/inbox and sagas are usually more practical.

## 20. Observability: Measure Delivery and Business Effects Separately

Metrics must separate the two layers:

| Metric | Indicates |
| --- | --- |
| publish_attempts_total | Producer publish attempts |
| broker_publish_confirmed_total | Confirmed publishes |
| delivery_attempts_total | Consumer deliveries/receives |
| handler_started_total | Handler starts |
| handler_succeeded_total | Handler completions |
| business_effect_committed_total | Business transactions/effects committed |
| inbox_duplicate_total | Previously processed messages detected |
| ack_failed_total | Failed ACKs/Completes/checkpoints |
| redelivery_total | Broker redeliveries |
| dead_letter_total | Messages sent to DLQ |
| unknown_outcome_total | Side effects requiring reconciliation |
| replay_total | Replayed messages |
| processing_lag_seconds | Latency from publish to commit |

Never equate delivered message count with successful business transactions. One message may be delivered multiple times while only one business effect commits. Conversely, a successful broker ACK does not prove an external payment/email succeeded.

### Logs and Traces

Record controlled fields:

- Event ID/message ID.
- Consumer name and subscription/queue.
- Delivery count/attempt number.
- Aggregate ID and event version if permitted.
- Processing duration, commit outcome, and ACK outcome.
- Error category, retry delay, and DLQ reason.

Do not log payloads containing personal data, tokens, secrets, connection strings, or sensitive payment details. Avoid using event ID as a high-cardinality metric label.

## 21. Testing Delivery Guarantees vs. Business-Effect Guarantees

A test verifying only that a consumer received a message is not enough. Verify crash windows and final state.

### Test Matrix

| Scenario | Expected Delivery | Expected Business Effect |
| --- | --- | --- |
| Handler succeeds, ACK succeeds | Normal single delivery | One commit |
| Crash before transaction | Redelivery | One commit after retry |
| Crash after DB commit, before ACK | Redelivery | Inbox blocks second business commit |
| ACK before commit then crash | No redelivery per ACKed mode | Test must expose risk of lost business effect |
| ACK response lost | Possible redelivery per broker | No repeated side effects |
| Broker publish accepted, producer loses confirmation | Producer may republish | Consumer deduplicates same event ID |
| Payment provider succeeds, response lost | Message/request may retry | Same provider idempotency key, one payment |
| Poison message | Bounded retries then DLQ | No partial side effects outside policy |
| DLQ replay | Message redelivered per workflow | No duplicate business effect |
| Out-of-order events | Possible per partition/session contract | Version check prevents state regression |

### Fault Injection

1. Kill the consumer after database commit but before ACK.
2. Drop the connection right after the broker accepts a publish.
3. Force ACK/Complete to time out.
4. Force an external API to time out after processing the request.
5. Let lock/visibility/ack deadline expire while the handler runs.
6. Start two consumers receiving/claiming the same operation concurrently.
7. Replay an old message near inbox retention expiration.
8. Send the same message ID with a different payload to verify conflict detection.
9. Send out-of-order event versions.
10. Verify DLQ and replay preserve the original event ID.

### Testing Against Real Services

- Use Azure Service Bus/Storage, AWS SQS, or Google Pub/Sub in a dedicated dev/test environment.
- Run the real client library/binder and settlement configuration used in production.
- Count delivery attempts, ACKs/completes, and business commits.
- Verify broker exactly-once/duplicate-detection features within their supported scope.
- Verify database/inbox/outbox final state via queries.
- Never run destructive fault injection on production queues/topics.

## 22. Lab Exercise: Building an Effectively-Once Consumer

**Context:** Spring Boot consumes OrderPaid events from a managed broker. The consumer must update the order, write a ledger entry, and emit OrderReceiptRequested. The broker may redeliver messages; ACKs may fail after database commit.

### Part A — Define the Contract

1. Specify the broker and delivery model.
2. Specify MessageId/EventId, subscription/queue, and retention.
3. Determine whether ACK/Complete/checkpoint is performed by the SDK or binder.
4. Document message lock/visibility/ack deadline or checkpoint semantics.
5. Define the business invariant: one OrderPaid event creates only one ledger entry per payment reference.

### Part B — Design the Consumer Transaction

1. Create an inbox table with unique key (consumer_name, event_id).
2. In one transaction, insert the inbox record and update order/ledger.
3. If the inbox detects a duplicate with matching payload hash, do not repeat business effects.
4. If the event ID matches with a different payload hash, route to error/investigation.
5. Commit before ACK/Complete.
6. Verify transaction rollback rolls back both inbox and business state.

### Part C — Emit Downstream Events

1. Write OrderReceiptRequested to the outbox in the same transaction as the business update.
2. Publisher sends the event with a stable ID.
3. If publish confirmation is unclear, the publisher retries with the same ID.
4. Downstream consumers use an inbox or corresponding idempotency key.
5. If the email provider lacks idempotency, document the limitation and reconciliation plan.

### Part D — Testing

1. Deliver the same event three times; only one ledger entry is created.
2. Crash after commit before ACK; redelivery does not duplicate the ledger.
3. Drop the outbox publisher's ACK; the event may resend, yet the consumer deduplicates it.
4. Send the same ID with a different payload; conflict must be detected.
5. Replay from DLQ; preserve event identity and audit trail.
6. Force payment/email API timeout after side effect; verify unknown outcome and reconciliation.

### Deliverables

- Table contrasting delivery guarantee and business-effect guarantee.
- Diagram of publish, delivery, commit, side effect, and ACK.
- Inbox/outbox schemas with unique constraints.
- Test evidence for crash after commit before ACK.
- Evidence duplicate delivery creates no second business effect.
- Policies for unknown outcomes, DLQ, replay, and retention.
- Separate metrics for delivery attempts, ACKs, and business commits.

### Self-Check Questions

1. How does at-least-once delivery differ from an exactly-once business effect?
2. Why can ACKing before commit lose business work?
3. Why can committing before ACK lead to duplicate delivery?
4. Which transaction must the inbox belong to in order to protect business state?
5. What gap between database and broker does the outbox solve?
6. Does a subscription's exactly-once delivery cover a payment API called by the consumer?
7. Why must an Event Hubs checkpoint be saved after business commit?
8. How does Service Bus Peek-Lock differ from Receive-and-Delete?
9. Which scopes do SQS FIFO deduplication and consumer inbox protect respectively?
10. What does Pub/Sub exactly-once delivery not replace at the application layer?
11. Why must event IDs stay stable across publisher retries and DLQ replays?
12. How do you distinguish a message delivered multiple times from a business effect committed multiple times?

## 23. Takeaways

- **Delivery guarantees** describe how the broker delivers messages; **business-effect guarantees** describe the application's actual state and side effects.
- At-most-once can drop messages; at-least-once can redeliver duplicates; exactly-once is meaningful only within a defined service/transaction scope.
- For database-updating consumers, typically commit inbox + business state first and then ACK. If ACK fails, redelivery is caught by the inbox.
- Outbox protects publish intent in the same database transaction; publishers can still emit duplicates if confirmation is lost.
- Exactly-once delivery does not automatically cover payments, emails, Blobs, databases, or APIs outside the broker.
- Effectively-once is achieved via stable event identity, unique constraints, inbox/outbox, provider idempotency keys, state machines, and reconciliation.
- Service Bus locks, Event Hubs checkpoints, SQS visibility timeouts, and Pub/Sub ack deadlines have different semantics; check your exact binder/client version.
- DLQ/replay must preserve event identity and inspect prior side effects before re-emitting.
- Measure delivery attempts, handler runs, business commits, ACK failures, duplicates, and unknown outcomes as separate metrics.

## References

- [Azure Service Bus message locks and settlement](https://learn.microsoft.com/azure/service-bus-messaging/message-transfers-locks-settlement)
- [Azure Service Bus duplicate detection](https://learn.microsoft.com/azure/service-bus-messaging/duplicate-detection)
- [Azure Event Hubs checkpoints and consumer groups](https://learn.microsoft.com/azure/event-hubs/event-hubs-features)
- [AWS SQS Standard queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/standard-queues.html)
- [Amazon SQS FIFO queues and exactly-once processing](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-queues-exactly-once-processing.html)
- [Amazon SQS visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html)
- [Amazon Kinesis Data Streams consumers](https://docs.aws.amazon.com/streams/latest/dev/building-consumers.html)
- [Google Cloud Pub/Sub exactly-once delivery](https://cloud.google.com/pubsub/docs/exactly-once-delivery)
- [Google Cloud Pub/Sub subscription overview](https://cloud.google.com/pubsub/docs/subscription-overview)
- [Spring Cloud Stream reference](https://docs.spring.io/spring-cloud-stream/reference/)
- [Transactional outbox pattern](https://learn.microsoft.com/azure/architecture/databases/guide/transactional-outbox-cosmos)
