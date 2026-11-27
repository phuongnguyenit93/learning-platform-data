# Replaying Data Without Repeating Side Effects

In an event-processing system, replay means sending previously stored messages through a consumer again. Replay is useful for incident recovery, running a new processor version, correcting miscalculated data, or rebuilding state. However, a message may have already produced side effects before the consumer failed or before the broker recorded the acknowledgement. Replaying that message without duplicate protection can charge a customer twice, send multiple emails, misadjust inventory, or create duplicate records.

Delivery reliability in Spring Cloud Stream must be designed alongside business idempotency. Brokers can redeliver messages; consumers must recognize the same event across deliveries, persist processing markers atomically, and guard calls to external systems. This lesson presents safe replay across Kafka, RabbitMQ, and Pulsar while distinguishing acknowledgements, offsets, deduplication, inbox, and outbox.

## Learning Objectives

After this lesson, you will be able to:

- Explain why at-least-once delivery can cause a consumer to receive the same message again.
- Distinguish a stable event ID from a broker offset, delivery tag, or message ID.
- Design idempotent consumers and idempotency keys to prevent repeated side effects.
- Use an inbox/deduplication record within the database transaction.
- Use a transactional outbox to emit downstream events after updating business state.
- Understand the relationship between business processing and acknowledgements/offsets on Kafka, RabbitMQ, and Pulsar.
- Plan replays by time, scope, rate, and ordering.
- Test failure windows between commits, acknowledgements, and external side effects.

## 1. Why Can a Message Be Processed Multiple Times?

In distributed systems, a consumer and broker cannot always know for certain whether an operation completed if a connection drops at an inopportune moment. A typical scenario:

1. Consumer receives `OrderPaid`.
2. Consumer calls the payment service or updates the database successfully.
3. Consumer stops before the acknowledgement or offset commit is recorded by the broker.
4. The broker sees no completion confirmation and redelivers the message.
5. The consumer processes the message again, creating a duplicate side effect.

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Consumer
    participant D as Database / API
    B->>C: Deliver OrderPaid (eventId=evt-100)
    C->>D: Record payment
    D-->>C: Success
    Note over C: Process stops before acknowledgement
    B->>C: Redeliver evt-100
    C->>D: Record payment again
    D-->>C: Risk of repeated side effect
~~~

This is why at-least-once delivery normally permits messages to be redelivered. Its goal is avoiding lost messages under failures, in exchange for requiring consumers to tolerate duplicate deliveries.

### Windows That Cause Duplicates

| When the failure happens | Possible consequence |
|---|---|
| Before processing | Broker redelivers; no side effects occurred yet |
| During processing, before commit | Transaction can roll back; message is redelivered |
| After database commit, before acknowledgement | Database already changed while broker may redeliver |
| After external API succeeds, before saving result/ack | API may execute the action again on retry |
| After acknowledgement | Broker treats message as done; if the app lost prior data, it cannot rely on the broker to recover automatically |

The hardest gap is between when a side effect occurs and when the completion marker is durably persisted. Idempotency design must cover this gap.

## 2. Distinguishing Delivery, Processing, and Side Effects

Three concepts must be separated:

- **Delivery:** the broker hands the message to a consumer.
- **Processing:** the application inspects and runs logic for the message.
- **Side effect:** an external state change such as writing to a database, charging money, sending an email, or calling another service.

A message can be delivered multiple times yet produce only one side effect if the consumer is idempotent. Conversely, a broker might deliver a message once under normal conditions while the application still triggers duplicate side effects due to HTTP-layer retries or retried client commands.

| Mechanism | What does it protect? | What does it not protect automatically? |
|---|---|---|
| Broker acknowledgement/offset | Delivery and consumption progress | Uniqueness of side effects in databases/APIs |
| Producer idempotence | Reduces duplicate records from send retries in some brokers/clients | Duplicate processing in consumers or side effects outside the broker |
| Consumer deduplication | Identifies already-processed events | Side effects outside the transaction without idempotency |
| API idempotency key | Prevents repeating the same business action on key-supporting APIs | Other APIs that do not share keys or state |
| Database transaction | Groups changes within the same database into one unit | Atomic commits across databases, brokers, and external APIs |

Do not label the whole system "exactly-once" merely because one component offers idempotence or transactions. Define the exact protected boundary.

## 3. Using a Stable Event ID to Identify Events

Consumers need an identifier that remains constant across redeliveries and replays. Typically the producer generates `eventId` when the business event is emitted.

Example:

~~~java
public record OrderPaid(
    String eventId,
    String orderId,
    String paymentId,
    BigDecimal amount,
    Instant occurredAt
) {}
~~~

`eventId` represents one concrete event. If the broker redelivers the message, `eventId` must remain unchanged. If the producer emits a new event for the same order at a later point, the new event needs a different `eventId`.

Do not use the following values as business idempotency keys:

- Kafka offset: changes when messages are rewritten or replayed into another topic.
- RabbitMQ delivery tag: only meaningful within a specific channel and delivery.
- Pulsar message ID: identifies broker storage position, not necessarily preserved on republish.
- Message receipt timestamp: each delivery can have a different timestamp.
- A UUID generated inside the consumer per invocation: redelivery creates a new key and fails to detect duplicates.

If the producer does not yet provide an `eventId`, choose a stable business key such as `paymentId` or `orderId + eventType + aggregateVersion`. Never choose a combination that can collide across legitimate distinct events.

## 4. Idempotent Consumers

An idempotent operation can be executed multiple times with the same input while leaving the final state equivalent to executing it once. For example:

- Setting order status to `PAID` can be idempotent if conditionally updated and not triggering repeated side effects.
- Adding 100 to a balance every time is not idempotent.
- Recording `paymentId` with a unique constraint can prevent a payment from being recorded twice.
- Sending an email on every handler run is not idempotent if the email provider lacks idempotency support.

Example status update:

~~~sql
UPDATE orders
SET status = 'PAID'
WHERE order_id = :orderId
  AND status <> 'PAID';
~~~

This statement avoids re-updating an order already marked `PAID`, but if other code still sends an email or deducts funds on every invocation, those side effects still repeat. Idempotency must cover every protected effect, not just one SQL statement.

### Business Idempotency Keys

For payment operations, use `paymentId` or `eventId` as the key:

~~~java
paymentClient.capture(
    paymentId,
    amount,
    eventId
);
~~~

If the payment API supports an idempotency key, resend the exact same key on retries of the same operation. Do not generate a new key per retry. The API can return the stored result instead of capturing again.

If the external API does not support idempotency, the consumer cannot strictly guarantee the action won't repeat in a lost-response window. In that case, you need a different integration contract, pre-retry status lookups, reconciliation, or manual exception handling.

## 5. The Inbox Pattern: Recording Processed Messages

An inbox is a table recording messages a consumer has received and processed. A unique key such as `(consumer_name, event_id)` detects redeliveries of the same event.

Example PostgreSQL schema:

~~~sql
CREATE TABLE processed_messages (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(200) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

The consumer opens a transaction, attempts to insert `eventId` into the inbox, and only applies business changes if a new row was created. PostgreSQL statement:

~~~sql
INSERT INTO processed_messages (consumer_name, event_id)
VALUES (:consumerName, :eventId)
ON CONFLICT (consumer_name, event_id) DO NOTHING;
~~~

If 1 row is inserted, this is the first processing attempt for that event in that consumer. If 0 rows are inserted, the event was already recorded; the consumer can finish cleanly without repeating side effects in this transaction.

### Processing Inbox and Business Logic in the Same Transaction

Example with Spring JDBC and PostgreSQL:

~~~java
@Service
public class OrderPaidHandler {

    private final JdbcTemplate jdbc;

    public OrderPaidHandler(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void handle(OrderPaid event) {
        int inserted = jdbc.update("""
            INSERT INTO processed_messages (consumer_name, event_id)
            VALUES (?, ?)
            ON CONFLICT (consumer_name, event_id) DO NOTHING
            """,
            "accounting",
            event.eventId()
        );

        if (inserted == 0) {
            return; // Event was already processed
        }

        jdbc.update("""
            UPDATE orders
            SET status = 'PAID'
            WHERE order_id = ?
            """,
            event.orderId()
        );

        jdbc.update("""
            INSERT INTO payment_ledger (payment_id, order_id, amount)
            VALUES (?, ?, ?)
            """,
            event.paymentId(),
            event.orderId(),
            event.amount()
        );
    }
}
~~~

The critical condition is that the inbox record and business changes commit in the same database transaction. If business updates fail, the transaction rolls back the inbox record too; when the broker redelivers, the consumer can retry. If the transaction commits but the acknowledgement is lost, the redelivery hits the inbox record and avoids repeating database changes.

This example uses PostgreSQL's `ON CONFLICT` syntax. For other databases, use the corresponding insert-if-absent syntax and ensure the unique constraint is enforced by the database, rather than checking via `SELECT` before `INSERT`. Two consumers can check the same event concurrently; only a unique constraint resolves contention reliably.

### Why Not Save the Inbox First and Process Later?

If you write and commit the inbox first and update business data afterward, a failure between the two steps leaves the event marked as processed even though the side effect never occurred. Redeliveries would be skipped and business data would be missing.

If you update business data first, commit, and write the inbox afterward, a failure between the two steps lets the side effect occur again on redelivery.

Therefore, the inbox and changes in the same database must share the same transaction. For side effects outside the database, additional idempotency or an outbox is required.

## 6. Scope and Retention of Deduplication Records

Inbox keys must be scoped per consumer. The same event may legitimately be processed by multiple consumers for different purposes, so the key typically combines consumer name and `eventId`.

Example:

| consumer_name | event_id | Meaning |
|---|---|---|
| accounting | evt-100 | Accounting consumer processed it |
| notification | evt-100 | Notification consumer processed it |
| inventory | evt-100 | Inventory consumer processed it |

Do not use a global `eventId` table that lets one consumer accidentally block other consumers.

Inbox retention must be at least as long as the window over which messages can be replayed or redelivered. If the broker retains data for 30 days while inbox records are purged after 7 days, replaying an old message on day 20 can recreate side effects.

Consider:

- Topic/queue retention and historical replay capability.
- How long DLQs may be retained and replayed.
- Database backup/restore potentially losing recent inbox records.
- Audit requirements and business trail retention periods.
- Table size and partitioning/archiving strategy.

For financial or legal side effects, long-term retention in an idempotency ledger may be required by business policy instead of short TTL deletion.

## 7. Side Effects Outside the Database

A database transaction cannot automatically cover an HTTP API, email provider, or external payment system without a supported distributed transaction protocol. Avoid assuming `@Transactional` makes a database and an external API commit atomically.

Example handler:
1. Write inbox to database.
2. Call email-sending API.
3. Update notification status.
4. Commit database.

If the email API succeeds while the database rolls back, the message is redelivered and the email may be sent again. If the database commits first and the API fails, the status might be marked complete even though the email was never sent.

Protection techniques:

- Use idempotency keys supported by the external API.
- Save the side-effect request in an outbox inside the database transaction.
- Use a dedicated worker to dispatch the outbox and mark status after receiving results.
- Use intermediate states such as `PENDING`, `SENT`, `FAILED` for controlled retries.
- Reconcile with the external system when outcomes are ambiguous.

For email providers without idempotency support, you can store a notification key and check internal status, though an uncertainty window still exists if the provider accepts the email while the response is lost. Accept and manage that risk via reconciliation or a deduplication-capable provider.

## 8. The Outbox Pattern When Downstream Events Must Be Emitted

Outbox solves the problem where a database update succeeds while publishing the downstream message fails. Instead of writing to the database and sending directly inside the same request, the application writes both the business change and the outbox record in the same transaction.

~~~mermaid
flowchart TD
    A["Consumer receives event"] --> B["Database transaction"]
    B --> C["Write inbox / dedup"]
    C --> D["Update business state"]
    D --> E["Write outbox event"]
    E --> F["Commit transaction"]
    F --> G["Outbox relay reads event"]
    G --> H["Publish to broker"]
    H --> I["Mark as published"]
~~~

Example outbox table:

~~~sql
CREATE TABLE outbox_events (
    event_id VARCHAR(200) PRIMARY KEY,
    aggregate_id VARCHAR(200) NOT NULL,
    event_type VARCHAR(150) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ
);
~~~

Inside the message-handling transaction, the application updates state and appends an outbox record. A relay or CDC connector reads the outbox and publishes the event. If the relay publishes successfully but crashes before setting `published_at`, it may publish again; downstream consumers still need to be idempotent.

Inbox and outbox address two opposite directions:

- Inbox prevents duplicate processing when an inbound message is redelivered.
- Outbox guarantees outbound event emission intent is stored alongside business changes.
- Downstream consumers still need idempotency because the relay can republish.

## 9. Acknowledgements and Replay on Kafka

Kafka stores records in topics by partition and offset. Consumer groups track progress via offsets. If database processing finishes but the offset has not committed, records can be re-read after a restart or rebalance.

In an at-least-once processing model, the order is typically designed as:
1. Read record.
2. Process and commit the database transaction.
3. After successful processing, commit offset per the binder/container mechanism.

If the process dies between steps 2 and 3, Kafka redelivers the record. Inbox deduplication lets the consumer skip the already-committed side effect.

### Kafka Transactions and Exactly-Once

Kafka transactions can coordinate reading from Kafka, writing to Kafka, and committing offsets within one Kafka transaction when the application/binder is properly configured. This is the basis for exactly-once semantics within Kafka read-process-write pipelines. It does not automatically make a database call, email, or external API part of the Kafka transaction.

If the pipeline writes to a database, you still need inbox/idempotency or an appropriate transaction coordination strategy. Never infer that enabling Kafka transactions prevents duplicate side effects in external systems.

### Kafka Replay

Replay can be performed by:
- Creating a new consumer group to re-read data according to the offset reset policy.
- Resetting an existing group's offsets to a chosen position.
- Using a tool to read the topic and republish to a dedicated replay destination.

Resetting offsets on a production group can cause running consumers to re-read large volumes of data. Stop or coordinate consumers, record original offsets, select the partition/offset range, and prepare a rollback plan.

During replay, preserve the original `eventId` so the inbox recognizes already-processed messages. When republishing to a new topic, the new broker offset does not replace the original `eventId`.

## 10. Acknowledgements and Replay on RabbitMQ

RabbitMQ consumers receive messages over a channel. With manual acknowledgement, the consumer acks only after successful processing. If the connection/channel closes before ack, the broker can requeue and redeliver the message.

A safe flow:
1. Receive message.
2. Process inside a database transaction with an inbox.
3. Commit database.
4. Ack message after successful processing.
5. If the process dies after commit before ack, the message is redelivered while the inbox blocks repeated side effects.

RabbitMQ's delivery tag is only valid within a channel and is not a business event ID. The `redelivered` flag helps observe redeliveries, but does not replace deduplication because a message can be republished as a new message.

When replaying from a DLQ, messages can be republished to the original exchange/queue or a dedicated replay destination. Preserve the original `eventId`, add metadata about the replay run if needed for auditing, and avoid creating infinite DLQ loops. Verify routing keys, TTL, queue policies, and target consumer acknowledgements.

## 11. Acknowledgements and Replay on Pulsar

Pulsar tracks consumption progress via subscription cursors. Consumers acknowledge messages after processing; unacknowledged messages can be redelivered per ack timeout, negative acknowledgement, or subscription policy.

If the database commits successfully while the acknowledgement does not reach the broker, the message may be redelivered. An inbox record with a stable `eventId` prevents repeated side effects.

Pulsar can support retry letter topics and dead-letter topics depending on client/binder configuration. During replay, understand where the subscription is reading, whether to seek/reset the cursor or republish messages. Republishing creates a new broker message, so the native message ID may differ; keep `eventId` in the payload or business metadata.

With `Key_Shared` or other subscription types, message ordering and distribution carry distinct semantics. If replaying messages in a different order than the original stream, consumers should check aggregate version or sequence to avoid applying stale state over newer state.

## 12. Controlled Replay

Replay is more than resending messages. A safe replay procedure clearly defines source, scope, target, and rate.

### Before Replay

- Confirm the root cause has been fixed.
- Select the event set by `eventId`, time range, partition/offset, or DLQ.
- Verify the target consumer has adequate inbox/idempotency protection.
- Verify schema and payload versions.
- Decide whether replay should re-run all side effects or only rebuild state.
- Clarify per-aggregate ordering and handling of stale events.
- Record expected volume, scope, and the operator/process initiating it.

### During Replay

- Use a dedicated replay topic or consumer group when appropriate.
- Rate-limit throughput to avoid overloading downstream dependencies.
- Attach `replayRunId` and source metadata for traceability.
- Preserve the original `eventId`.
- Monitor counts of succeeded, duplicate-suppressed, failed, and DLQ events.
- Halt the replay if error rates or backlog exceed thresholds.

### After Replay

- Reconcile input event counts against newly processed, duplicate, and failed counts.
- Verify business state and external side effects.
- Record replayed offsets/cursors or scope.
- Keep an audit record explaining the impact of the run.
- Confirm no unexpected messages remain stuck in retry/DLQ.

A replay run should have its own identifier without replacing the original `eventId`. `replayRunId` traces a specific replay execution; `eventId` identifies the business event.

## 13. Ordering and Stale Events

Idempotency alone does not solve ordering. If an aggregate has events:
- `OrderCreated`, version 1
- `OrderPaid`, version 2
- `OrderShipped`, version 3

Replaying only `OrderCreated` after state has reached version 3 could revert data to an older state if the handler does not check version.

You can store aggregate version and apply only newer events:

~~~sql
UPDATE orders
SET status = :newStatus,
    version = :eventVersion
WHERE order_id = :orderId
  AND version < :eventVersion;
~~~

This statement illustrates monotonic version control. Define how to handle events skipped due to stale versions, events missing versions, or two events sharing a version. For some domains, sequential processing or rebuilding state from the event log is needed rather than simply ignoring older events.

Partitioning by aggregate key helps related events stay ordered within a partition, though replays may route messages down a different path or across changed partition counts. Version checks remain valuable to protect state.

## 14. Testing Failure Windows

Normal tests are not enough to prove safe replay. Simulate process termination at critical points:

| Simulated stop point | Outcome to verify |
|---|---|
| Before writing inbox | Broker redelivers and consumer processes normally |
| After inbox insert but before business update | Transaction rolls back; redelivery is processed |
| After business update but before commit | Transaction rolls back all DB changes |
| After DB commit but before ack/offset commit | Broker redelivers; inbox prevents duplicate DB side effects |
| After external API succeeds but before saving result | API idempotency key prevents duplicate effects or reconciliation detects state |
| After outbox publish but before marking published | Relay can republish; downstream consumer deduplicates |
| When replaying an event older than current state | Version guard prevents overwriting newer state |

### Testing the Inbox

- Send the same `eventId` twice.
- Run two consumer instances concurrently with the same `eventId`.
- Verify the unique constraint allows only one transaction to process the first delivery.
- Verify duplicates create no extra ledger entries or business changes.
- Roll back a transaction and verify subsequent deliveries can still process.

### Testing External APIs

Use a mock server supporting idempotency keys:
- Call with the same key twice.
- Verify the server creates only one effect.
- Force a response timeout after the server has recorded the request.
- Retry with the same key and verify the stored result is returned.

### Testing the Broker

With Kafka, test offset commits and redelivery after restart. With RabbitMQ, test manual ack and redelivery on channel close. With Pulsar, test ack/nack, redelivery, and subscription cursors. Broker integration tests should run with near-production settings because Test Binder does not fully simulate each broker's semantics.

## 15. Common Mistakes

| Symptom | Root cause | Fix |
|---|---|---|
| Charged twice after restart | DB/API committed before ack, non-idempotent consumer | Inbox and payment idempotency keys |
| Message skipped even though business logic did not run | Inbox written and committed before side effects | Combine inbox and DB updates in one transaction |
| Email sent twice | Email provider succeeded but response was lost | Provider idempotency if available; outbox and reconciliation |
| Replay creates new effects | Replay generated new eventIds or dedup records expired | Keep original eventIds and sufficient retention |
| One consumer blocks another consumer | Inbox key used global eventId only | Use composite key `consumer_name + event_id` |
| Kafka offset reset causes broad reprocessing | Replay scope was not bounded | Save original offsets, pick partition/range, and use a dedicated group when appropriate |
| RabbitMQ redelivered flag used as dedup key | Redelivered flag does not identify the event | Use a stable `eventId` |
| Pulsar republish not recognized as duplicate | Relied on new native message ID | Keep `eventId` in payload/metadata |
| Old event overwrites new state | No aggregate version check | Version guard or ordered processing |
| Outbox emits duplicate messages | Relay crashed after publish before marking | Idempotent downstream consumers |
| Deduplication stops working after several days | Inbox records purged too early | Align retention with the replay horizon |

## 16. Hands-On Exercise: Safely Replaying OrderPaid

Build an `accounting` consumer receiving `OrderPaid`:

1. Ensure the producer generates a stable `eventId` and preserves it across retries/replays.
2. Create `processed_messages` with unique key `(consumer_name, event_id)`.
3. Create `payment_ledger` with a unique constraint on `paymentId`.
4. Write a handler using one database transaction to insert into the inbox and write the ledger.
5. If the inbox insert creates no new row, finish processing without writing the ledger again.
6. If the transaction fails, verify both inbox and ledger roll back together.
7. Ack/commit offsets after the transaction succeeds per the binder mechanism.
8. Simulate stopping the process after DB commit but before ack; verify the broker redelivers and deduplication blocks repetition.
9. If calling an external payment API, pass the same `eventId`/`paymentId` as the idempotency key across all retries.
10. Add an outbox if the handler needs to emit `AccountingEntryCreated` after commit.
11. Replay the same `eventId` from a DLQ or replay topic and verify no second ledger entry is created.
12. Replay an event with an older version and verify the version guard does not overwrite newer state.
13. Run the tests on Kafka, RabbitMQ, or Pulsar according to the actual binder.

Acceptance checklist:

| Item | Outcome to verify |
|---|---|
| Event identity | `eventId` stable across delivery and replay |
| Inbox | Unique key scoped by consumer and event |
| Atomicity | Inbox and DB changes share one transaction |
| External API | Same idempotency key across retries |
| Outbox | Outbound event persisted alongside business changes |
| Acknowledgement | Confirmed only after durable processing |
| Replay scope | Explicit scope, rate, and audit trail |
| Ordering | Aggregate version or ordering rules |
| Retention | Dedup records retained long enough for replay |
| Failure injection | Major failure windows tested |

## Conclusion

Safe data replay requires recognizing the same event across multiple deliveries and protecting each side effect. Broker acknowledgements, Kafka offsets, and Pulsar subscription cursors track delivery progress; they do not automatically guarantee a single database update or a single external API call.

Use a stable `eventId`, inbox/deduplication in the same transaction as business changes, idempotency keys for external APIs, and an outbox when downstream events must be emitted. Retain dedup records long enough, enforce ordering with aggregate versions, and execute scoped, audited replays. This design lets consumers withstand redeliveries, retries, and replays on Kafka, RabbitMQ, or Pulsar without unintended repeated side effects.

## References

- [Spring Cloud Stream – Consumer Properties and Acknowledgement](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream – Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder.html)
- [Spring Cloud Stream – Rabbit Binder](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview.html)
- [Apache Kafka – Design and Delivery Semantics](https://kafka.apache.org/documentation/#semantics)
- [Apache Pulsar – Messaging and Acknowledgement](https://pulsar.apache.org/docs/next/concepts-messaging/)
