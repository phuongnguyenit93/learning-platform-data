# Transaction and Idempotency Checklist

Kafka delivers events durably, yet a reliable messaging pipeline must still answer two questions: **when is a group of operations considered completed together** and **what happens if the same event is delivered multiple times**. Kafka transactions can coordinate consuming records, publishing new records, and committing offsets within a single Kafka transaction. Idempotency lets business logic tolerate duplicates caused by retries, crashes, rebalances, or replays.

These two mechanisms complement each other but are not identical. Producer idempotence prevents duplicates from producer retries within one producer session; Kafka transactions create an atomic boundary across Kafka operations; business idempotency prevents side effects from being applied repeatedly. Neither mechanism automatically makes a database update, HTTP call, or payment API exactly-once.

This article is a design and operations checklist for Spring Kafka. Use it when reviewing producers, consumers, retry/DLT, transactions, database integration, and replay workflows before taking an event stream to production.

## 1. Distinguish the guarantee mechanisms

| Mechanism | What does it protect? | Limitations |
| --- | --- | --- |
| Producer idempotence | Broker avoids writing duplicates from producer retries within the same producer session/sequence | Does not stop the application from intentionally sending the same business event multiple times |
| Kafka transaction | Multiple Kafka operations commit or abort together | Does not automatically include databases, HTTP, or external systems outside Kafka |
| Consumer offset commit | Persists how far a consumer group has processed | Can redeliver if side effects completed before the offset committed |
| Business idempotency | Same event/request ID does not apply business side effects multiple times | Requires storing keys and outcomes long enough and handling race conditions properly |
| Inbox pattern | Records processed event in the same database transaction as the business update | Protects only side effects inside that same DB transaction |
| Outbox pattern | Saves business change and publish intent in the same DB transaction | Relay/CDC can still republish; consumers should still be idempotent |
| Saga/compensation | Coordinates and compensates workflows across multiple systems | Not a distributed ACID transaction |

Identify actual requirements before choosing mechanisms: do you need zero lost events, zero duplicate business effects, no output emitted when input aborts, or coordination across multiple systems? Each requirement has a different guarantee boundary.

## 2. Define transaction boundaries

Before configuring Spring Kafka, map out every operation in the flow:

```text
Producer service
  1. Create event
  2. Publish Kafka record

Consumer service
  3. Consume input record
  4. Update database
  5. Publish next output/event
  6. Commit input offset
```

Label each step as Kafka, database, or external system. A Kafka transaction coordinates only the Kafka operations enlisted in that transaction. If step 4 is an independent JDBC commit, Kafka cannot automatically roll back the database when step 5 fails.

**Boundary checklist:**

- [ ] Identified whether the transaction begins at the producer or the listener container.
- [ ] Listed all side effects in the flow: Kafka, database, HTTP, payment, email, files, or cache.
- [ ] Identified which operations actually belong inside the same Kafka transaction.
- [ ] Determined whether the database transaction has its own boundary or uses outbox/inbox.
- [ ] Decided behavior when the process crashes between two side effects.
- [ ] Identified which operations can be retried or redelivered.
- [ ] Defined what constitutes successful event processing from a business standpoint.

## 3. Producer: idempotence and send configuration

Kafka producer idempotence uses a producer ID and sequence numbers so the broker recognizes retries of the same batch, avoiding duplicate writes on network errors or producer-layer retries. This mechanism is a useful foundation for publish reliability.

In modern Kafka clients, idempotence is often enabled by default under compatible settings; still verify the effective config of your application and broker/client version. Illustrative config:

```yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        max.in.flight.requests.per.connection: 5
```

`acks=all` instructs the broker to wait for acknowledgements from replicas in the ISR per Kafka semantics; replication factor, `min.insync.replicas`, and ISR health must also be properly designed. Idempotence enforces compatibility constraints across `acks`, retries, and `max.in.flight.requests.per.connection`; do not alter them independently without checking your client version.

**Producer checklist:**

- [ ] Producer idempotence is enabled or the default in the Kafka client in use is verified.
- [ ] `acks` and `min.insync.replicas` satisfy desired durability.
- [ ] Retries, delivery timeout, and request timeout match SLAs.
- [ ] `max.in.flight.requests.per.connection` is compatible with idempotence and ordering requirements.
- [ ] Key/partition strategy is defined to keep ordering per aggregate when needed.
- [ ] Send failure callbacks/futures are handled and recorded, never ignored.
- [ ] Business events carry a stable `eventId` generated once before publishing/retrying.
- [ ] Producers do not generate a new event ID each time the same business action is resent.
- [ ] Schemas, serializers, and headers are verified before production sends.

Producer idempotence does not replace a business event ID. If code calls `send()` twice for the same event, the broker can accept two valid records because those are two application-level sends.

## 4. Kafka transactions in Spring Kafka

Kafka transactions allow publishing multiple records and committing consumer offsets within a single transaction. If the transaction aborts, output records remain invisible to `read_committed` consumers, and offsets enlisted in the transaction are not committed as part of that transaction.

In Spring Boot, configure `transaction-id-prefix` so Spring Kafka creates a transactional producer:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: ${INSTANCE_ID:orders-1}-tx-
      properties:
        enable.idempotence: true
    consumer:
      properties:
        isolation.level: read_committed
```

`transaction-id-prefix` must be unique across active application instances. If two instances share the same prefix and produce colliding transactional IDs, the broker can fence the older producer. Use a stable pod/instance identity across the instance's lifetime and check how prefixes are assigned during scaling/restarts.

Spring Boot can auto-configure a transactional `ProducerFactory` when `spring.kafka.producer.transaction-id-prefix` is present. If you define `ProducerFactory` manually, verify the transaction ID prefix and transaction config apply to that factory.

Create `KafkaTransactionManager` from the right `ProducerFactory`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.transaction.KafkaTransactionManager;

@Configuration
public class KafkaTransactionConfiguration {

    @Bean
    KafkaTransactionManager<String, OrderEvent> kafkaTransactionManager(
            ProducerFactory<String, OrderEvent> producerFactory
    ) {
        return new KafkaTransactionManager<>(producerFactory);
    }
}
```

Spring Boot may already create a `KafkaTransactionManager` bean when a transaction prefix is configured. Only declare the bean manually if the application needs a custom manager or auto-configuration does not supply one; avoid accidentally creating two managers managing the same `ProducerFactory`.

For listener containers, attach the Kafka-aware transaction manager to container properties:

```java
factory.getContainerProperties()
        .setKafkaAwareTransactionManager(kafkaTransactionManager);
```

When the container manages a Kafka transaction, the listener can publish output with a `KafkaTemplate` participating in the active transaction. The input record's offset is sent to the transaction to commit alongside the output.

For a producer service actively sending a group of records in a transaction, you can reference the transaction manager by qualifier:

```java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public OrderEventPublisher(KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional("kafkaTransactionManager")
    public void publish(OrderEvent event) {
        kafkaTemplate.send("orders.events", event.orderId(), event);
        kafkaTemplate.send("orders.audit", event.orderId(), event.toAuditEvent());
    }
}
```

Both sends participate in the same thread-bound Kafka transaction. If the method throws an exception that rolls back the transaction, both outputs abort. This is a Kafka transaction; if the method also updates a database via another transaction manager, apply the dual-write/outbox analysis covered later.

**Kafka transaction checklist:**

- [ ] ProducerFactory is genuinely a transactional producer factory.
- [ ] `transaction-id-prefix` is unique across running instances.
- [ ] Listener container uses the right `KafkaTransactionManager` if atomic consume-process-produce in Kafka is needed.
- [ ] `KafkaTemplate` is built from the corresponding ProducerFactory to join transactions.
- [ ] Downstream consumers use `isolation.level=read_committed` if aborted output must remain hidden.
- [ ] Transaction timeout accommodates normal processing without being excessively long.
- [ ] Listeners do not perform excessively long blocking work inside transactions.
- [ ] Exceptions meant to trigger rollback are not caught and swallowed.
- [ ] Error handling after rollback and DLT/recovery policies are configured.
- [ ] Metrics/logs exist for transaction commits, aborts, timeouts, and producer fencing.

## 5. Exactly-once semantics: how far does the guarantee go?

Kafka exactly-once semantics (EOS) typically refers to coordinating consume-process-produce inside Kafka: input offsets and output records commit within the same Kafka transaction. This avoids scenarios where output committed while input offsets did not, or vice versa, in a properly configured Kafka-to-Kafka flow.

EOS does not mean the business method is invoked only once. A listener can be invoked again after crashes or rollbacks; side effects outside Kafka still require idempotency.

Example:

```text
Input topic -> listener -> Output topic
                  |
                  +-- Kafka transaction:
                      - publish output record
                      - commit input offset
```

If the transaction aborts, output is invisible to `read_committed` consumers and the input offset is not committed in that transaction. The input record can be redelivered for another processing attempt.

**EOS checklist:**

- [ ] Exactly-once scope is explicitly described as Kafka-to-Kafka.
- [ ] Producer transactions and listener container transactions are configured properly.
- [ ] Input offsets participate in the same transaction as outputs.
- [ ] Downstream consumers use `read_committed` when aborted output must be hidden.
- [ ] Business side effects outside Kafka have separate idempotency or outbox/inbox mechanisms.
- [ ] Never advertise "system-wide exactly-once" solely because Kafka transactions are enabled.

## 6. Consumer offsets and processing boundaries

In normal processing, the consumer group commits offsets after the listener finishes successfully according to `AckMode` and container semantics. If the database commits successfully but the process dies before offset commit, the record can be redelivered. If the offset commits before the database commits, a crash can lose the chance to reprocess the record.

```text
DB commit -> process crash -> Kafka offset uncommitted
                         -> record redelivered
                         -> business operation risks running twice
```

This is why consumers need idempotency whenever external side effects exist outside Kafka.

**Consumer checklist:**

- [ ] `enable.auto.commit` and Spring Kafka `AckMode` are chosen intentionally.
- [ ] Offsets are confirmed only after the defined processing boundary.
- [ ] Listener exceptions are not swallowed when container rollback/retry is needed.
- [ ] Manual acknowledgments are invoked only after side effects finish.
- [ ] Duplicates from crashes between business commit and offset commit are handled.
- [ ] Behavior during mid-processing rebalances or shutdowns is tested.
- [ ] Batch listeners have explicit partial-failure/acknowledgment policies.
- [ ] Async handoffs do not commit offsets before actual work completes.

With Kafka transactional listeners, offsets can be sent into the Kafka transaction. With standard database listeners, DB commits and Kafka offset commits remain two separate commit systems unless additional coordination is introduced.

## 7. Idempotency keys for events and commands

Every event/command with side effects needs a stable identifier. You can use `eventId`, `commandId`, or `requestId` generated by the producer before sending. That identifier must remain unchanged across producer retries, consumer redeliveries, and DLT replays.

Example event envelope:

```java
public record OrderPaid(
        String eventId,
        String orderId,
        String paymentId,
        long occurredAt
) {}
```

`eventId` identifies a specific event; `orderId` identifies the aggregate; `paymentId` can identify the payment operation in the payment system. Do not overload a single field for every purpose if the semantics differ.

**Idempotency key checklist:**

- [ ] The ID is created at the business origin prior to the first publish.
- [ ] The ID remains unchanged on producer retries or republishes of the same event.
- [ ] The ID includes a namespace/event type if multiple sources could collide.
- [ ] The consumer defines uniqueness scope clearly: global, tenant, event type, or per consumer.
- [ ] The ID is retained longer than retention, retry, DLT, and replay windows.
- [ ] Replays preserve the original event ID for deduplication.
- [ ] Do not use Kafka offsets as business idempotency keys, as offsets are only unique within one topic-partition.

## 8. Inbox/deduplication table in the database

For consumers updating a database, the inbox pattern records processed event markers and business updates in the same database transaction. If the event is redelivered, a unique constraint on event ID detects the duplicate.

Example schema:

```sql
CREATE TABLE processed_messages (
    consumer_name VARCHAR(120) NOT NULL,
    event_id VARCHAR(160) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Example service:

```java
@Transactional
public void handle(OrderPaid event) {
    boolean firstDelivery = inboxRepository.insertIfAbsent(
            "billing-projection",
            event.eventId()
    );

    if (!firstDelivery) {
        return; // Event has already been applied in this consumer.
    }

    invoiceRepository.markPaid(event.orderId(), event.paymentId());
}
```

`insertIfAbsent` must rely on a unique constraint or atomic upsert suitable for your database. Do not perform a separate `SELECT` then `INSERT` without handling race conditions: two consumer threads could both see the event as absent simultaneously.

The inbox row and the business update must be in the same DB transaction. If the business update rolls back, the inbox insert rolls back too so the next delivery can reprocess. If the transaction commits, any redelivery sees the inbox row and skips the duplicate side effect.

**Inbox checklist:**

- [ ] Unique constraint protects `(consumer_name, event_id)` or equivalent key.
- [ ] Inbox insert and business update share the same DB transaction.
- [ ] Duplicate path returns successfully so offsets can continue committing.
- [ ] Race conditions across consumers are resolved by database constraints.
- [ ] Retention/cleanup policy does not purge keys still within retry/replay windows.
- [ ] Metrics count skipped duplicates.
- [ ] Consumer name/handler versions are managed so independent projections do not share dedup namespaces inappropriately.

## 9. Outbox pattern for database-to-Kafka

A service frequently needs to update a database and publish a corresponding event. If the DB commits first and publishing fails, data changed without emitting the event. If publishing happens first and the DB rolls back, the event describes a change that never persisted.

Outbox solves dual-write by saving the business change and an outbox row inside the same DB transaction:

```text
BEGIN DB TRANSACTION
  UPDATE orders ...
  INSERT INTO outbox(event_id, aggregate_id, event_type, payload, ...)
COMMIT

Outbox relay / CDC -> Kafka topic
```

Simple schema example:

```sql
CREATE TABLE outbox_events (
    event_id VARCHAR(160) PRIMARY KEY,
    aggregate_id VARCHAR(160) NOT NULL,
    event_type VARCHAR(160) NOT NULL,
    payload JSON NOT NULL,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL
);
```

The relay can poll the outbox table or use CDC such as Debezium. If the relay publishes successfully but crashes before marking the row published, the same event can be published again. Consumers must still be idempotent using the event ID.

**Outbox checklist:**

- [ ] Business update and outbox insert share the same DB transaction.
- [ ] Outbox event has a stable ID, aggregate ID, event type, schema version, and timestamp.
- [ ] Relay/CDC has retries and backlog observability.
- [ ] Multi-worker relays use proper claiming/locking mechanisms.
- [ ] Duplicate publishes are tolerated and deduplicated by consumers.
- [ ] Retention/cleanup runs after events are emitted and no longer needed for outbox replay.
- [ ] Alerts trigger when outbox backlog grows or unpublished event age breaches SLA.

Outbox ensures publish intent is durably persisted alongside business updates; it does not turn the entire system into a single distributed transaction.

## 10. Combining Kafka transactions with databases

Spring can coordinate multiple transaction managers sequentially or via transaction synchronization, but that does not automatically create a distributed atomic commit between Kafka and a relational database. One transaction manager can commit first; if the second transaction manager fails to commit, the two systems can diverge in state.

When a listener updates a database and publishes to Kafka, answer:

- Does the database commit first or does Kafka commit first?
- If the second commit fails, can the first operation roll back?
- Can listener redelivery repeat DB updates or outputs?
- Are outbox/inbox tables in place to recover?

For critical business flows, outbox/inbox is usually easier to operate and verify than assuming two local transaction managers create an XA transaction. Use XA/JTA only when infrastructure, drivers, brokers, and operations explicitly support it and the team understands the cost of distributed transactions.

| Flow pattern | Typically suitable design |
| --- | --- |
| Kafka input → Kafka output | Kafka transaction + consume-process-produce EOS |
| Kafka input → database update | Inbox/dedup in same DB transaction, offset commit after listener succeeds |
| Database update → Kafka output | Transactional outbox + relay/CDC |
| Kafka input → external API | Downstream idempotency key, status query/reconciliation, and compensation when needed |
| Kafka input → database + Kafka output | Inbox for input and outbox for output; define DB transaction and Kafka offset boundaries clearly |

## 11. Idempotency for external APIs and side effects

If a listener calls a payment gateway, sends email, or calls another HTTP service, a DB inbox cannot roll back external side effects. Use idempotency keys if supported by the downstream API:

```text
POST /payments
Idempotency-Key: payment-command-8f...
```

Downstream stores the key and outcome, returning the same result when receiving the repeated request. If downstream does not support idempotency, design stateful workflows, reconciliation, or compensation; exactly-once cannot be guaranteed by Kafka offsets alone.

**External side-effects checklist:**

- [ ] Every command carries a stable idempotency key.
- [ ] Downstream APIs accept and persist the key when supported.
- [ ] Timeouts are never misinterpreted as guaranteed failures.
- [ ] A status query mechanism exists when a call outcome is unknown.
- [ ] Emails/notifications have deduplication or documented duplicate tolerance.
- [ ] Non-rollbackable side effects have compensation/reconciliation steps.
- [ ] Never blindly retry a payment command without checking the prior call's state.

## 12. Retries, DLT, and replay

Retries can cause a record to be processed multiple times. Blocking retries, non-blocking retry topics, and DLTs differ in ordering, offset, and timing semantics. Regardless of the choice, business handlers should still be idempotent.

Retry/DLT checklist:

- [ ] Classify transient, permanent, and validation errors.
- [ ] Retry only errors likely to succeed on subsequent attempts.
- [ ] Bound attempts and backoff; avoid infinite retries.
- [ ] Choose blocking vs. non-blocking retries and accept ordering trade-offs.
- [ ] DLT retains event ID, original topic/partition/offset, exception metadata, and needed trace headers.
- [ ] Alerts trigger when DLT receives records or backlog grows.
- [ ] Replay analysis and approval workflows exist.
- [ ] Replays preserve the original event ID if representing the same business event.
- [ ] Consumer idempotency still works during replay.
- [ ] Do not delete DLT records before confirming recovery completed.

A replay may be the first time a new consumer projection sees an event or a reprocessing of an old event. Define deduplication namespaces and policies accordingly; do not purge inbox tables casually before replaying.

## 13. Ordering and concurrency

Kafka only guarantees ordering within a single partition. If events of the same aggregate must be processed in order, use the aggregate ID as the key so they land in the same partition.

When scaling consumer concurrency, useful consumers in a group are capped by partition assignment. If a listener dispatches records to a thread pool for parallel processing, business completion order may differ from the order Kafka delivered records.

Ordering/concurrency checklist:

- [ ] Choose message keys per aggregate requiring ordering.
- [ ] Related events share the same topic/partitioning strategy.
- [ ] Concurrency does not exceed partition and downstream capacity.
- [ ] Async processing does not commit offsets before side effects complete.
- [ ] When processing in parallel, enforce aggregate sequence/version checks where needed.
- [ ] Retries/DLT do not imply ordering guarantees the system does not actually provide.
- [ ] Explicit policies exist for duplicate and out-of-order events.

## 14. Event contracts and schema evolution

Idempotency only works if event identities and contracts are stable. Events should use a consistent envelope, for example:

```json
{
  "eventId": "evt-01J...",
  "eventType": "OrderPaid",
  "schemaVersion": 2,
  "aggregateId": "order-123",
  "occurredAt": "2026-11-17T10:15:30Z",
  "correlationId": "request-456",
  "payload": {
    "paymentId": "pay-789"
  }
}
```

Contract checklist:

- [ ] `eventId` is unique and stable.
- [ ] Event type and schema version are present.
- [ ] Aggregate key fits ordering requirements.
- [ ] Timestamps follow a clear standard, preferring UTC.
- [ ] Correlation ID and trace context have distinct purposes.
- [ ] Consumers remain compatible with old/new schemas per compatibility policy.
- [ ] Do not compute idempotency keys from mutable payloads after the event has been emitted.

## 15. Security and transaction permissions

Transactional producers use transactional IDs and require matching cluster ACLs. Consumers need read permission on topics and groups; producers need write permission on topics. Permissions on transaction resources depend on your authorization mechanism and Kafka version/cluster configuration.

Security checklist:

- [ ] Producers/consumers use TLS or SASL per cluster policy.
- [ ] Principals hold only required permissions on topics/groups/transactional IDs.
- [ ] Transactional ID prefixes are never shared arbitrarily across different applications.
- [ ] Secrets and credentials never appear in source or logs.
- [ ] Event payloads omit unnecessary sensitive data.
- [ ] DLT and outbox/inbox tables have proper access controls and retention.
- [ ] Replay tools have audit trails and restricted permissions.

## 16. Testing transactions and idempotency

Unit tests verify deduplication logic and duplicate handling; integration tests require a real broker or equivalent Kafka environment to validate transactions, offsets, and isolation semantics.

**Mandatory scenarios to cover:**

1. Publish a record successfully with an idempotent producer.
2. Producer retries after a network error and verify no duplicates from internal retries.
3. Listener consumes input, publishes output in a transaction, and commits successfully.
4. Throw an exception before commit and verify the transaction aborts.
5. Use a `read_committed` consumer to verify aborted output is invisible.
6. Send the same event ID twice and verify business side effects apply only once.
7. Send two copies of the same event ID concurrently to verify unique constraint/race handling.
8. Crash after DB commit but before Kafka offset commit and verify the inbox blocks duplicate side effects.
9. Outbox relay publishes successfully then restarts before marking published; verify consumer deduplicates.
10. Exhaust retry attempts and verify the record routes to the DLT.
11. Replay from DLT with the original event ID and verify behavior matches policy.
12. Send out-of-order events and verify aggregate version/sequence guards if present.
13. Restart/rebalance a consumer mid-processing to test offsets and duplicate handling.
14. Test transactional ID fencing when two instances accidentally share a prefix in an isolated test environment.

Do not merely assert that the listener was invoked. Check database state, committed offsets, output topic visibility, and side-effect counts. Use Testcontainers or Embedded Kafka matching your version to test broker behavior; avoid fixed `Thread.sleep()`, using Awaitility/latches with bounded timeouts instead.

## 17. Pre-production failure drills

Execute controlled drills in staging:

| Failure drill | Expected outcome |
| --- | --- |
| Kill producer after send, before caller receives ack | Caller handles ambiguous result; stable event ID makes retry safe |
| Kill consumer after DB commit, before offset commit | Record may redeliver; inbox prevents duplicate side effects |
| Abort Kafka transaction after producing output | `read_committed` consumer does not see aborted output |
| Lose broker connection mid-transaction | Transaction timeout/abort recorded; listener retries per policy |
| Restart a transactional instance | New instance gets valid transactional ID; stale producer is fenced if ID collides |
| Outbox relay stops for a long period | Backlog grows, alerts fire; relay resumes from durable outbox |
| DLT replay with same event ID | Dedup policy prevents unwanted duplicate business updates |
| Downstream HTTP timeout after processing | Query/idempotency key determines outcome before retrying |

Run failure drills only in permitted test environments with permitted data. Capture metrics, logs, offsets, and DB state to verify recovery rather than merely checking that processes restart.

## 18. Required metrics and alerts

Track these indicators to detect transaction/idempotency issues:

| Metric/log | Purpose |
| --- | --- |
| Transaction commit/abort rate | Detect unusual spikes in rollbacks |
| Transaction duration/timeout | Detect transactions held open too long |
| Producer send failure/retry | Monitor publish reliability |
| Producer fencing count/error | Detect transactional ID conflicts |
| Consumer redelivery/retry count | Measure reprocessing rate |
| Idempotency duplicate hits | Track deduplicated duplicate events |
| Inbox insert conflicts | Detect duplicate deliveries or replays |
| Outbox pending count/oldest age | Detect events waiting to be relayed |
| Consumer lag | Detect backlog |
| DLT publish rate/backlog | Track unprocessable records |
| Replay count and operator identity | Audit recovery operations |

Alerts should rely on trends and SLAs: sustained transaction aborts, any fencing occurrences, outbox oldest age exceeding thresholds, growing DLT backlogs, or non-decreasing consumer lag. Do not alert on a single transaction abort if it is an expected rollback from a validation/business exception.

## 19. Operating idempotency data

Inbox/processed-message tables can grow continuously. Define retention policies aligned with how long events can be resent or replayed.

Retention checklist:

- [ ] Retention exceeds the maximum retry window.
- [ ] Retention exceeds the committed DLT replay window.
- [ ] Accounts for how long producers/outboxes might re-emit events.
- [ ] Clean up in batches to avoid lock/IO spikes.
- [ ] Do not delete keys currently being replayed or still needed for reconciliation.
- [ ] Proper indexes/partitioning ensure duplicate lookups do not slow hot paths.
- [ ] Backup/restore policies cover inbox/outbox alongside business data.

If the system needs to replay historical events spanning years, keeping idempotency keys for only a few days will not protect replays. In that case define replay semantics explicitly: build a new projection under a new namespace, or retain deduplication keys long enough to prevent repeated side effects.

## 20. Comprehensive go-live checklist

### Design and semantics

- [ ] Desired delivery semantics defined for each stream.
- [ ] Producer idempotence, Kafka transactions, and business idempotency distinguished.
- [ ] Kafka/DB/external side-effect boundaries mapped.
- [ ] Event ID, correlation ID, aggregate key, and schema version defined.
- [ ] Ordering, concurrency, retry, and replay policies defined.

### Producer and Kafka transactions

- [ ] Idempotent producer, `acks`, and replication policy verified.
- [ ] Transaction ID prefixes unique across instances.
- [ ] Listener containers and KafkaTemplate use the right transactional ProducerFactory.
- [ ] Input offsets and output records participate in the same Kafka transaction when EOS is needed.
- [ ] Downstream consumers use `read_committed` when aborted output must be hidden.

### Database and side effects

- [ ] Consumers have inbox/unique constraints if DB side effects must be idempotent.
- [ ] Outbox is used when DB updates and Kafka publish intents must commit durably together.
- [ ] External APIs use idempotency keys or reconciliation workflows.
- [ ] DB commits and Kafka offset commits are not assumed to be atomic.

### Reliability and recovery

- [ ] Retry/DLT attempts, backoff, and exception classifications are clear.
- [ ] Replays preserve original event IDs or use a new namespace per policy.
- [ ] Consumers handle duplicates and out-of-order events safely.
- [ ] Shutdown/rebalance/crash scenarios have been tested.
- [ ] Failure drills verified final state across both Kafka and databases.

### Security and operations

- [ ] ACLs, TLS/SASL, transactional IDs, and secrets are protected.
- [ ] Inbox/outbox retention, backups, and cleanup are planned.
- [ ] Dashboards/alerts cover transaction, retry, duplicate, outbox, DLT, and lag metrics.
- [ ] Replay tools have audit trails and restricted permissions.
- [ ] Runbooks document handling fencing, aborts, duplicates, backlogs, and DLT.

A reliable Kafka flow never comes from a single configuration flag. Producer idempotence handles producer-layer retries; Kafka transactions coordinate outputs and offsets inside Kafka; inbox/outbox and business idempotency protect database boundaries; downstream idempotency/reconciliation protects external side effects. Test real crash and replay points, then use this checklist as a go-live gate and periodic review document.

## 21. Self-check

1. How does producer idempotence differ from business idempotency?
2. Which operations can a Kafka transaction guarantee atomicity for?
3. Why does Kafka EOS not make database updates exactly-once?
4. Within what scope must `transaction-id-prefix` be unique, and what failure occurs if it collides?
5. Why should downstream consumers use `read_committed` when reading transactional output?
6. What scenario arises from crashing after a DB commit but before an offset commit?
7. How does the inbox pattern rely on unique constraints and DB transactions?
8. How does outbox solve dual-writes, and why can the relay still publish duplicates?
9. Why do external payment/email side effects need their own idempotency keys?
10. In what scenarios should a DLT replay preserve the original event ID?
11. Which failure drills prove that offsets, transactions, and idempotency work properly?
12. Which metrics reveal transactional ID fencing, duplicates, and outbox backlogs?
