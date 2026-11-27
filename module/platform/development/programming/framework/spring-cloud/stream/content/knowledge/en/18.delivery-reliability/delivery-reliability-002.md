# Designing Safe Repeated Processing (Idempotency) with Event IDs

In a messaging system, an event can be delivered multiple times. A consumer might have updated the database and stopped before acknowledging the message; the broker will redeliver it when the consumer reconnects. A producer might also resend because it did not receive a publish confirmation even though the broker already received the message. These are normal occurrences in an at-least-once delivery model.

If every delivery creates a new effect, an order might have inventory deducted twice, a payment might be recorded twice, or an email might be sent repeatedly. **Idempotency** enables an event to be processed repeatedly while the final business effect remains equivalent to processing it once. A common approach is attaching a stable `eventId` to each event and recording the IDs already processed by the consumer.

This lesson belongs to the **Reliability** chapter of the `SPRING_CLOUD_STREAM` module. The module uses the `Supplier`/`Function`/`Consumer` functional model, bindings, and binders for Kafka, RabbitMQ, or Pulsar. The content focuses on event ID design, duplicate tracking, transaction boundaries, concurrent processing, external API integration, replay, and testing.

## 1. Why Can a Message Be Processed Multiple Times?

A message broker cannot know on its own that all business effects have completed inside a database or external service. For example:

1. Consumer receives `OrderPlaced`.
2. Consumer writes the inventory deduction to the database.
3. Database commits successfully.
4. The process stops before the broker receives the acknowledgement or offset commit.
5. The message is redelivered after the consumer restarts.
6. The consumer deducts inventory a second time if there is no deduplication mechanism.

```text
Broker                Consumer                  Database
  |                       |                         |
  |---- OrderPlaced ----->|                         |
  |                       |---- decrement stock --->|
  |                       |                         | commit
  |                       |<------ success ----------|
  |                       X process stops            |
  |                                                  |
  |---- redeliver ------->|                         |
  |                       |---- decrement again ---->|  <-- duplicate effect
```

Broker redelivery is not necessarily a broker error. The consumer may have completed part of the work without completing the entire acknowledgement protocol. Similarly, a producer may retry publishing after a timeout and create two records for the same event if a stable event ID is not used.

Therefore, consumers should assume a message can arrive at least once and sometimes multiple times. Idempotency mechanisms sit at the boundary of business effects so redeliveries produce no additional side effects.

## 2. What Is Idempotency?

An idempotent operation has the property that executing it once or multiple times with the same identifier and the same business content leaves the resulting state unchanged after the first execution.

For example, setting an order status to `CONFIRMED` can often be idempotent if the operation simply updates to the same state. Conversely, `balance = balance - amount` is not idempotent: running it twice deducts the amount twice.

| Operation | Property | Reason |
|---|---|---|
| Setting order status to `CONFIRMED` | Can be idempotent | Repeating the same value does not change the result after the first time |
| Incrementing a counter by 1 | Not idempotent | Each call increases the counter further |
| Deducting inventory by quantity | Not idempotent without checking the event | Message redelivery can deduct again |
| Inserting a record with unique key `eventId` | Can be idempotent | Unique constraint prevents creating duplicate records |
| Sending email via an API without an idempotency key | Not guaranteed idempotent | A timeout can cause the application to resend an email already accepted by the provider |

Idempotency does not mean every call returns the exact same technical-layer response. The first call might return `APPLIED`, while the next returns `DUPLICATE`; what must be preserved is that the business effect is applied only once.

## 3. Event IDs Must Remain Stable Across All Retries

`eventId` is the unique identifier of a specific event. The producer should generate the ID when the event is formed and keep that exact ID across publish retries. The consumer uses this ID to recognize redeliveries of the same event.

Example payload:

```json
{
  "eventId": "018f4a1e-7b2d-7c40-9f42-8a53e8a2d011",
  "eventType": "OrderPlaced",
  "occurredAt": "2026-11-24T09:15:00Z",
  "orderId": "ORD-2026-0042",
  "customerId": "CUS-018",
  "items": [
    { "sku": "COFFEE-01", "quantity": 2 }
  ]
}
```

When the producer retries sending this event, it must resend the same `eventId`, not generate a new ID on every `send` call. If every retry generates a new UUID, the consumer will treat the retries as different events and deduplication will no longer work.

A good event ID has the following characteristics:

- Unique within the scope of the defined producer or event source.
- Immutable throughout the entire lifecycle of the event.
- Generated before the first publish and durably persisted if the producer needs to retry after a restart.
- Independent of the time the consumer receives the message.
- Can be carried in the payload or header according to the agreed contract.

If multiple producers can generate the same ID value, combine `source` or `producerId` into the deduplication key. For example, the key is `(source, eventId)` rather than `eventId` alone.

## 4. Distinguishing Event ID from Business Key and Correlation ID

Three types of identifiers often appear together but serve different purposes:

| Identifier | Represents | Example | Used for |
|---|---|---|---|
| `eventId` | One event occurrence | `evt-8f2...` | Deduplication and tracing a single logical message |
| `orderId` | A business entity | `ORD-42` | Identifying the order, applying rules per aggregate |
| `correlationId` | An interaction flow or process | `corr-91a...` | Linking logs and messages across multiple services |

A single order may emit multiple events: `OrderPlaced`, `OrderConfirmed`, `OrderShipped`. Each event needs its own `eventId` while potentially sharing `orderId` and `correlationId` depending on the workflow.

Do not use `orderId` as the event ID if the same order can emit multiple events of the same type or multiple updates. Doing so can cause deduplication by `orderId` to mistakenly discard valid events.

## 5. Recording Event IDs with the Inbox Pattern

A common implementation is creating an inbox table to record events already applied by a consumer. The unique key combines the logical consumer name with the event ID, because two independent consumers may need to process the same event.

Example PostgreSQL schema:

```sql
CREATE TABLE processed_message (
    consumer_name  VARCHAR(120) NOT NULL,
    source_name    VARCHAR(120) NOT NULL,
    event_id       VARCHAR(160) NOT NULL,
    payload_hash   VARCHAR(128),
    processed_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, source_name, event_id)
);
```

`consumer_name` is the stable name of a processing role, such as `inventory-projection`. `source_name` identifies the event-producing source. `event_id` identifies the event. The primary key prevents the same consumer from applying the same event twice.

If two independent consumers both read `orders.events`, they must have different inbox namespaces. For example, both `inventory-projection` and `analytics-projection` are allowed to process the same `eventId`, because those are two distinct business effects.

Do not use a pod name or hostname as `consumer_name`; those values change across deployments and would give each replica its own separate deduplication space. The consumer name must represent the logical group sharing the database or deduplication store.

## 6. Writing the Inbox and Updating Business State in the Same Transaction

The most important rule is that recording the `eventId` marker and applying the business change must happen inside the same database transaction. If the inbox write succeeds while the business update fails and the two operations are not in the same transaction, redeliveries could be marked as duplicates even though the business effect never completed.

With PostgreSQL, `INSERT ... ON CONFLICT DO NOTHING` can be used to determine whether the event has already been processed:

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

record OrderPlaced(String eventId, String source, String orderId,
                   String sku, int quantity) {}

enum ApplyResult {
    APPLIED,
    DUPLICATE
}

@Service
class InventoryEventHandler {

    private final JdbcTemplate jdbc;

    InventoryEventHandler(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public ApplyResult handle(OrderPlaced event) {
        int inserted = jdbc.update("""
            INSERT INTO processed_message
                (consumer_name, source_name, event_id)
            VALUES (?, ?, ?)
            ON CONFLICT (consumer_name, source_name, event_id) DO NOTHING
            """,
            "inventory-projection",
            event.source(),
            event.eventId()
        );

        if (inserted == 0) {
            return ApplyResult.DUPLICATE;
        }

        jdbc.update("""
            UPDATE inventory
               SET available = available - ?
             WHERE sku = ?
            """,
            event.quantity(),
            event.sku()
        );

        return ApplyResult.APPLIED;
    }
}
```

In this example:

1. The database attempts to insert the key `(consumer_name, source_name, event_id)`.
2. If the key already exists, `inserted` is `0`; the handler returns `DUPLICATE` and does not deduct inventory.
3. If the insert succeeds, the handler updates inventory and returns `APPLIED`.
4. If updating inventory fails, the exception rolls back the transaction; the newly inserted inbox record is rolled back too.
5. When the message is redelivered, the operation can be retried from scratch.

This guarantee only holds when the inbox and business data reside in the same transaction manager/database transaction. If the inventory update lives in a different database or calls an external API, a local transaction cannot automatically roll back effects that occurred in the other system.

In production code, check the number of updated rows in the `inventory` table, handle nonexistent SKUs, and validate quantities. This snippet focuses on illustrating the inbox transaction boundary; business validation rules must be added.

## 7. Why Unique Constraints Matter Under Concurrency

A naive implementation might look like this:

```java
if (!repository.existsByEventId(event.eventId())) {
    repository.save(new ProcessedMessage(event.eventId()));
    applyBusinessChange(event);
}
```

This code has a race condition. Two threads can both check `exists` and both get `false` before either writes any data. Then both execute the business effect.

A unique constraint in the database is the final line of defense because checking and inserting the key is synchronized by the database. You can catch a duplicate key exception or use syntax like `ON CONFLICT DO NOTHING` to handle it explicitly. Do not rely solely on a prior check in Java.

When using JPA, ensure the unique constraint actually exists in the database and the transaction is properly managed. A unique violation exception may mark the transaction as rollback-only; it is not always safe to catch the exception and keep using that transaction. Insert-ignore approaches depend on the database and repository API.

## 8. Same Event ID with Different Payload Is Abnormal

If two messages have the same `eventId` but different content, the later message should not automatically be treated as a valid duplicate. This may indicate producer ID reuse, a serialization bug, data tampering, or a security incident.

A `payload_hash` or schema version can also be stored to detect this case:

```text
Inbox key: (consumer_name, source_name, event_id)
First payload hash:   7b2f...
Second payload hash:  91ac...

Same event ID but different hash
          |
          v
  Record IDENTITY_CONFLICT
          |
          v
  Quarantine and investigate
```

The hash should be computed from a canonicalized payload representation or from immutable message bytes per the contract. JSON can differ in property order while carrying the same logical data; if you hash raw bytes, two semantically equivalent JSON payloads might yield different hashes. Choose an appropriate canonicalization approach.

Do not overwrite the original payload hash with the new hash. Record the conflict for investigation and do not apply the business effect a second time.

## 9. Event ID in Payload or Message Header?

The event ID can be passed in the payload or in a header. Each approach has pros and cons:

| Location | Pros | Considerations |
|---|---|---|
| JSON payload | ID travels with the event contract and is easy to store/replay | DTO must include the event ID field; consumer must deserialize the payload |
| Message header | Separates metadata from business data; works with `Message<T>` | Header mapping varies across binders; must ensure the ID is preserved through the broker |
| Both | Contract and metadata can be cross-checked | Must define which value is the source of truth; reject if they mismatch |

Example creating a message with an event ID in the header:

```java
import java.util.UUID;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

record OrderPayload(String orderId, String status) {}

OrderPayload payload = new OrderPayload("ORD-42", "PLACED");
String eventId = UUID.randomUUID().toString(); // generated once for this event

Message<OrderPayload> message = MessageBuilder
    .withPayload(payload)
    .setHeader("eventId", eventId)
    .setHeader("eventType", "OrderPlaced")
    .build();
```

The producer must construct the message once and preserve the header across publish retries. Persist `eventId` alongside the outbox record or durable send state so retries after a restart still reuse that same ID. Do not place UUID generation inside code that runs again on every retry. If the consumer needs to deduplicate after a message passes through multiple brokers or connectors, verify whether headers are mapped and preserved; a payload ID is often easier to carry across systems.

## 10. Spring Cloud Stream Consumer Using Event IDs

A consumer can receive a DTO using the functional model:

```java
import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class InventoryConsumerConfiguration {

    @Bean
    Consumer<OrderPlaced> inventoryProjection(
            InventoryEventHandler handler) {
        return event -> handler.handle(event);
    }
}
```

Binding configuration:

```yaml
spring:
  cloud:
    function:
      definition: inventoryProjection
    stream:
      bindings:
        inventoryProjection-in-0:
          destination: orders.placed
          group: inventory-projection
          content-type: application/json
```

A binding group lets replicas of the same logical consumer share load. The inbox table uses the same `consumer_name` across all replicas in the group so they coordinate deduplication. If each replica used a different name, the same event could be applied once per replica.

If there is an independent analytics consumer, it needs its own inbox namespace such as `analytics-projection`. One consumer processing an event must not prevent another consumer from processing the same event for a different business purpose.

## 11. Acknowledgement Must Happen After the Business Transaction Completes

A key principle: do not acknowledge a message as processed before the transaction storing the business effect and inbox marker commits successfully.

```text
Receive message
    |
    v
Open DB transaction
    |
    v
Insert event ID into inbox
    |
    +---- already exists ----> do not reapply
    |
    v
Apply business changes
    |
    v
Commit transaction
    |
    v
Finish handler
    |
    v
Binder/broker acknowledges per configuration
```

If the process stops after commit but before acknowledgement, the broker may redeliver the message. The inbox recognizes the event has already been applied and the handler does not repeat the effect. Then the consumer finishes the redelivery so the binder can acknowledge it.

If acknowledgement occurs before the transaction commits and the process stops in between, the message may be treated as processed while the database change was never saved. How acknowledgement and offset commits are configured depends on the binder; verify the actual ordering in the version you use.

## 12. Idempotency for Effects Outside the Database

An inbox transaction only protects changes within the same database transaction. If a handler calls a payment API, sends an email, or calls another service, there is an unavoidable failure gap:

1. The external service executed the effect.
2. The consumer timed out before receiving the response or before writing the inbox.
3. The message is redelivered.
4. The consumer calls the external service again.

There are three common approaches:

- **Idempotency key at the target API:** send `eventId` or a stable business key; the receiving service stores the key and returns the prior result on repeated requests.
- **Command/outbox:** write the outbound request to the database in the same business transaction; a worker sends the request and updates its status while also using an idempotency key at the target.
- **Saga/compensation:** if the operation cannot be made idempotent, design compensating steps and workflow states to handle partial effects.

Do not mark an event as complete in the inbox before the external effect has a definite status, unless that status itself means "scheduled for execution" and the external work is durably stored in an outbox/job table. If you write the inbox first, call the external API afterward, and crash in between, redeliveries might be skipped even though the API was never called.

## 13. Combining Inbox and Outbox

Inbox protects the consumer from duplicate processing. Outbox protects the producer from the failure gap between committing the database and publishing the message.

Example order-creation service:

```text
Single DB transaction
  +-- INSERT order
  +-- INSERT outbox(event_id, payload, status='NEW')
              |
              v
       Outbox relay reads record
              |
              v
       Publish message to broker
              |
              v
       Mark record as sent
```

If the relay publishes successfully but crashes before marking `SENT`, the relay may publish the same outbox record again. Therefore, outbox does not guarantee sending only once; it guarantees the event is saved with the transaction and can be replayed. The consumer still needs an event ID and inbox to prevent duplicate effects.

When designing the system, the producer generates the event ID once and stores it in the outbox. The relay does not generate a new ID on retries. The consumer uses that same ID to deduplicate. The two patterns complement each other at both ends of the messaging flow.

## 14. Scope and Retention Duration of Deduplication Markers

An inbox table cannot grow indefinitely without a retention policy. However, deleting event ID markers too early allows an old message to be processed again.

The retention period should be greater than or equal to the window over which the system can replay messages, including:

- Topic or queue retention.
- DLQ and retry destination retention.
- Operational replay window after an incident.
- Backup/restore and disaster recovery window.
- Audit or business reconciliation requirements.

If a Kafka topic allows reading back 30 days of data while the inbox only keeps 7 days, replaying from day 20 could reapply business effects. Align broker retention and inbox retention.

For high-volume event systems, the inbox can be time-partitioned, old records archived, or markers stored in a TTL-backed store. Data cleanup must be based on an agreed replay horizon. Do not delete records simply because they exceed an arbitrary age threshold.

## 15. Intentional Replay and Consumer Versioning

Sometimes you need to replay full history to rebuild a projection or fix a logic bug. If you reuse the same inbox namespace, all old events will be recognized as already processed and skipped.

You can use a new `consumer_name` or projection version for the rebuild, for example:

| Purpose | Inbox namespace |
|---|---|
| Current inventory projection | `inventory-projection-v1` |
| Rebuild projection with new logic | `inventory-projection-v2` |
| Independent analytics | `analytics-projection-v1` |

Only change the namespace when you genuinely want to reapply history into a new state. Do not create a new namespace on every restart, as that disables deduplication. Replaying external effects such as payments or emails requires a separate policy; projection-rebuild mechanisms should not be used to re-execute real-world transactions.

## 16. Broker Differences Do Not Eliminate the Need for Idempotency

Kafka, RabbitMQ, and Pulsar have different acknowledgement and redelivery mechanisms, yet consumers still need to be safe against duplicates:

| Broker | Situation that can lead to reprocessing | What to control |
|---|---|---|
| Kafka | Consumer finishes processing but offset has not committed; rebalance or restart causes records to be re-read | Tie offset commit to processing outcome; use event ID and inbox; understand Kafka transaction scope |
| RabbitMQ | Consumer channel/connection closes before ack; unacknowledged messages are requeued | Ack after transaction completes; monitor redeliveries; use inbox to protect side effects |
| Pulsar | Consumer does not ack or ack times out; subscription redelivers message | Ack after processing; understand subscription and redelivery policies; use a stable event ID |

Kafka has transaction mechanisms and exactly-once semantics for certain Kafka-to-Kafka flows, but they do not automatically cover an external database or payment API. RabbitMQ publisher confirms and consumer acknowledgements likewise do not form a shared transaction with a business database. Pulsar transactions have their own scope and support boundaries; they do not automatically guarantee an external API is called exactly once.

Therefore, business-level idempotency remains essential even when the broker provides strong delivery features.

## 17. Testing Idempotency

A thorough test suite should verify not only sending the same event ID twice, but also concurrency races and crashes at transaction boundaries:

| Scenario | How to test | Expected outcome |
|---|---|---|
| Same event sent twice sequentially | Invoke handler twice with the same ID | Business effect occurs only once |
| Two events with different IDs | Send two distinct valid events | Both are applied |
| Two different logical consumers | Same event into two consumer names | Each consumer applies once independently |
| Two threads with the same event ID | Invoke concurrently from two threads | Unique constraint lets only one transaction apply the effect |
| Business update fails | Throw error after inserting inbox | Transaction rolls back both inbox and business update |
| Crash after DB commit before ack | Simulate redelivery after commit | Redelivery detects duplicate, does not repeat effect |
| Same ID with different payload | Send same key with different hash | Records identity conflict and quarantines |
| Old event after cleanup | Replay event outside inbox retention | Verify policy prevents repeated effect as required |
| Outbox relay publishes twice | Publish same outbox event twice | Consumer inbox prevents duplicate application |
| External API times out after succeeding | Retry with same idempotency key | Target API returns matching result, creates no new effect |

Concurrency tests should run against a database compatible with production because unique constraints, isolation levels, and insert-ignore syntax have specific semantics. Mock repositories cannot verify database race conditions.

## 18. Observability and Operations

Metrics and logs to monitor:

- Count of newly applied messages (`APPLIED`).
- Count of messages skipped as duplicates (`DUPLICATE`).
- Count of cases with the same event ID but different payload hash.
- Count of inbox insert errors or transaction rollbacks.
- Redelivery count by binder/broker.
- Age and count of inbox records, and storage growth rate.
- Count of pending, failed-publish, or republished outbox records.
- Rate of idempotency key conflicts at external APIs.

Logs should include `eventId`, `source`, `consumerName`, `correlationId`, and the `APPLIED`/`DUPLICATE` outcome. Do not use event ID as a high-cardinality metric label; use aggregate counters by binding, logical consumer, and outcome type.

When duplicate rates spike suddenly, check consumer restarts, rebalances, timeouts, broker redeliveries, producer retries, and processing duration. Duplicates are not necessarily failures if idempotency is working, but an abnormal spike can indicate delivery trouble or misconfigured acknowledgements.

## 19. Workflow for Designing Event-ID Idempotency

When building a Spring Cloud Stream consumer:

1. Specify the event ID in the message contract and identify the ID source.
2. Generate the ID once when the event is created; keep the same ID across all publish retries.
3. Define the deduplication namespace consisting of logical consumer, source, and event ID.
4. Create an inbox table with a unique constraint in the database.
5. Insert the inbox marker and apply business changes in the same transaction.
6. Acknowledge the message after the transaction commits per the binder mechanism.
7. Use an idempotency key at external APIs or outbox/saga for effects outside the database transaction.
8. Define how to handle the same ID with a different payload.
9. Retain deduplication markers long enough relative to retention and the replay horizon.
10. Separate namespaces for intentional projection rebuilds; do not change namespaces on every restart.
11. Test sequential duplicates, concurrency, crash windows, and real redelivery.
12. Monitor duplicate rate, inbox storage, outbox backlog, and transaction errors.

## 20. Self-Check

- [ ] Can explain why a consumer may receive the same message multiple times.
- [ ] Distinguish event ID, business key, and correlation ID.
- [ ] Ensure the producer preserves the event ID across publish retries.
- [ ] Design the inbox key by logical consumer, source, and event ID.
- [ ] Can explain why inbox insert and business update must share a transaction.
- [ ] Understand the role of unique constraints when two threads process the same event.
- [ ] Detect cases with the same event ID but different payloads.
- [ ] Distinguish inbox from outbox and know how to combine both patterns.
- [ ] Determine deduplication retention duration based on the replay horizon.
- [ ] Can explain why broker exactly-once does not automatically cover databases or external APIs.
- [ ] Can design tests for duplicates, concurrency, crashes, and redeliveries.

## Conclusion

Idempotency lets a consumer handle redelivery safely when a broker or producer sends the same event again. Producers must create `eventId` once and preserve it across all publish attempts; consumers record the ID in an inbox with a unique constraint and apply both the inbox marker and the business changes in one transaction. For effects outside the database, target-API idempotency keys or a durable workflow such as outbox/saga are required. Retention duration must cover broker retention and the replay horizon, and each logical consumer needs its own namespace. Kafka, RabbitMQ, and Pulsar mechanisms reduce delivery risk but do not replace business-layer idempotency.
