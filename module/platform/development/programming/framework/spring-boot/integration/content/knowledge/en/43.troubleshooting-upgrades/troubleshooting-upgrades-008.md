# Lost, Duplicate, or Out-of-Order Messages Due to Misunderstanding Acknowledge and Commit

## 1. Scenario: Message Received Yet Data Still Ends Up Wrong

A Spring Boot application consumes `OrderPaid` events from Kafka, updates PostgreSQL, and publishes notifications to RabbitMQ. After a library upgrade or scaling up consumers, operations reports three symptoms:

- **Lost:** logs show the consumer received the event, yet the database has no corresponding row.
- **Duplicate:** the same event updates balances or sends emails twice.
- **Out of order:** status `PAID` is overwritten back to `CREATED` by a late-arriving older event.

All three symptoms usually stem from confusing **message received**, **business processing succeeded**, **transaction committed**, **read progress acknowledged/committed**, and **ordering guarantees**. These milestones are not automatically one atomic operation.

In Spring Boot Integration, a single flow may cross HTTP clients, databases, caches, and brokers, each with its own confirmation mechanism. This lesson explains how to pinpoint root causes, order milestones properly, configure Spring Kafka and Spring AMQP, handle JMS, and test failure scenarios after upgrades.

## 2. Distinguishing Confirmation Types

### Acknowledge Does Not Mean Business Commit

**Acknowledge (ack)** informs the sender or broker that the receiver accepted a message under that protocol's rules. Its exact guarantee depends on the system:

| Concept | Who Confirms to Whom? | What Is Guaranteed | What Is **Not** Guaranteed |
| --- | --- | --- | --- |
| Kafka producer `acks=all` | Broker confirms to producer | Record accepted per replica/ISR policy | Consumer read it or database updated |
| Kafka consumer offset commit | Consumer group stores next read position | Offsets **before the committed position** are typically not redelivered on normal resume | Downstream DB/HTTP side effects committed |
| RabbitMQ publisher confirm | Broker confirms to publisher | Broker received/handled publish per routing and storage rules | Consumer processed it successfully |
| RabbitMQ consumer `basicAck` | Consumer confirms delivery to broker | Broker may remove delivery from unacked state | Consumer's DB transaction or HTTP call succeeded |
| JMS `Session.commit()` | Transacted session commits within JMS scope | JMS operations on that session commit | External database transactions automatically commit with it |
| HTTP `2xx` | Server responds to client | Request accepted/handled per that HTTP API's contract | All downstream async tasks persisted durably |

**Kafka offset commit is not a database commit.** Kafka stores offsets per **consumer group and topic-partition**. Committing offset `105` means that on normal resume, the consumer reads starting at offset `105`; records `0..104` are treated as passed. Do not misread it as "record 105 just finished processing."

**RabbitMQ delivery acknowledgement is not a producer confirm.** They govern opposite ends of the pipe. Publisher confirms can succeed while consumers later fail; consumer ACKs can fire before database writes commit if called at the wrong spot.

### Milestone Ordering

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Consumer Spring Boot
    participant D as Database
    B->>C: Deliver event E
    C->>D: BEGIN + business processing
    D-->>C: DB COMMIT succeeded
    C->>B: Ack / commit offset
    Note over C,B: If crashing before ack, E may be redelivered
    Note over C,D: If acking before DB COMMIT, updates can be lost
~~~

When side effects persist to a DB, the safer order is **process and commit DB first, ACK/commit progress afterward**, paired with **idempotency** to survive redelivery if the consumer crashes between the two steps.

This is a pragmatic *at-least-once* design—it does not merge DB and broker into an atomic transaction. Acking before DB writes introduces a data-loss window; committing DB before ACKing introduces a duplicate-delivery window. Swapping `ack()` placement alone cannot eliminate both windows.

## 3. Failure Matrix: Why Messages Are Lost or Duplicated

| Crash / Failure Point | DB Committed? | Broker Progress Acked / Committed? | Typical Consequence |
| --- | --- | --- | --- |
| Before processing | No | No | Broker can redeliver; needs retry |
| **Ack early, then processing fails** | **No** | **Yes** | **Business effect lost:** cursor moved past message |
| **DB commit then crash before ack** | **Yes** | **No** | **Redelivery:** non-idempotent handlers duplicate side effects |
| Both DB commit and ack succeed | Yes | Yes | Completed on both sides under normal operation |
| Timeout sending ack / commit | Possibly yes | **Unknown** | Do not guess state; redelivery possible, reconcile |
| Ack succeeded yet external HTTP call failed | Possibly yes | Yes | DB and external system can diverge; needs outbox/compensation |

"Lost message" sometimes means only **no longer redelivered to this consumer group**, while the broker has not deleted the bytes. Kafka retains records per retention policy; a committed offset causes the app to **skip** records still sitting on the topic. In RabbitMQ, an acked delivery is typically removed from the queue, changing replay options.

**Common bug:** a listener calls an `@Async` service, returns immediately, and ACKs while DB writes run asynchronously. The ACK only confirms work was *scheduled*, not committed. Wait for completion or write a durable inbox record before ACKing.

### Scopes of At-Most-Once, At-Least-Once, and Exactly-Once

- **At-most-once:** work may be lost when progress commits before processing, though that mechanism will not redeliver duplicates.
- **At-least-once:** messages may be redelivered; business logic must tolerate duplicates. Commonly achieved by committing/ACKing after processing.
- **Exactly-once:** meaningful only when **scope** is stated. Kafka supports transactional read–process–write within Kafka when producers, consumers, and transactions are configured properly; that **does not automatically make** PostgreSQL updates, REST calls, or emails exactly-once.

Across heterogeneous integration systems, the practical standard is **at-least-once delivery + idempotent effects**, combined with outbox/inbox tables along critical paths.

## 4. Kafka: Offset Commits, Acknowledgements, Retries, and Ordering

### Offsets Belong to Partitions, Not Whole Topics

~~~text
Topic order-status, group order-projector
  partition 0: ... [offset 40] [41] [42] [43]
  partition 1: ... [offset 80] [81] [82] [83]

If group committed:
  partition 0 -> 43 : next read typically starts at 43
  partition 1 -> 82 : next read typically starts at 82
~~~

There is no "topic-wide offset" enforcing global order. Kafka guarantees append order only within **one partition**. If events for one order scatter across partitions (due to unstable keys), consumers can observe `PAID` before `CREATED`.

Within a consumer group, each partition is assigned to one consumer at a time, yet **async processing**, rebalances, retries, partition-count changes, or parallel pipelines can still reorder business effects relative to read order. Raising concurrency never guarantees serial updates per entity automatically.

### Commit Modes to Distinguish

| Mechanism | Practical Meaning | Risks to Verify |
| --- | --- | --- |
| Kafka client `enable.auto.commit=true` | Client periodically commits polled positions on its own cadence | Cursor advances past slow or async processing |
| Spring Kafka `AckMode.BATCH` | Container commits after processing records in a poll batch per config | One failing record affects batch progress depending on error handler |
| `AckMode.RECORD` | Container commits after each record succeeds in listener | Commit overhead and error-handler behavior |
| `AckMode.MANUAL` | Listener signals completion; container commits on batch-like schedule | Calling `acknowledge()` does not mean instant commit on that line |
| `AckMode.MANUAL_IMMEDIATE` | Listener ACKs on consumer thread requesting immediate commit | Still must handle commit errors, rebalances, and sync/async modes |

Exact names and semantics vary across Spring Kafka versions, listener types, transactional containers, `asyncAcks`, and error handlers. On upgrades, **inspect live listener container factories and condition/config logs** instead of guessing from one YAML key.

### Spring Boot Example: Commit Progress After DB Transaction Completes

~~~yaml
# application.yml (Spring Boot + Spring for Apache Kafka)
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      enable-auto-commit: false
      auto-offset-reset: earliest
    listener:
      ack-mode: manual_immediate
~~~

`auto-offset-reset: earliest` applies only when **no valid committed offset exists** for that partition/group; it will not "replay from the beginning" if the group already committed offsets.

Suppose the event has shape:

~~~json
{
  "eventId": "partner-a:evt-8192",
  "orderId": "ORD-1024",
  "version": 7,
  "status": "PAID"
}
~~~

Record processing in the **same PostgreSQL transaction** as the projection update:

~~~sql
CREATE TABLE consumed_event (
    event_id TEXT PRIMARY KEY,
    consumed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE order_projection (
    order_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    last_version BIGINT NOT NULL
);
~~~

~~~java
// OrderEvent.java
public record OrderEvent(
        String eventId, String orderId, long version, String status) {}
~~~

~~~java
// OrderProjectionService.java: PostgreSQL + Spring JDBC illustration
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderProjectionService {

    private final JdbcTemplate jdbc;

    public OrderProjectionService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void apply(OrderEvent event) {
        int inserted = jdbc.update("""
            INSERT INTO consumed_event(event_id)
            VALUES (?)
            ON CONFLICT (event_id) DO NOTHING
            """, event.eventId());
        if (inserted == 0) {
            return; // same eventId already processed and committed
        }

        jdbc.update("""
            INSERT INTO order_projection(order_id, status, last_version)
            VALUES (?, ?, ?)
            ON CONFLICT (order_id) DO UPDATE SET
                status = EXCLUDED.status,
                last_version = EXCLUDED.last_version
            WHERE order_projection.last_version < EXCLUDED.last_version
            """, event.orderId(), event.status(), event.version());
    }
}
~~~

This assumes each event carries **full state** and `version` increases monotonically per `orderId`. The conditional update applies only newer versions, so stale events never overwrite newer states. If events carry deltas (e.g., "add 100 to balance") or require contiguous sequence numbers, skipping gaps is unsafe: buffer by key, detect missing versions, and replay/reconcile.

Never deduplicate with separate "SELECT if exists then INSERT" queries outside atomic constraints, as concurrent consumers race past the check. The unique constraint on `consumed_event.event_id` is the primary concurrency guard, and both `INSERT` and projection update must share **the exact same database transaction manager**. Remember `@Transactional` works only when called via the Spring proxy, not via same-instance self-invocation.

Kafka listener:

~~~java
// OrderKafkaListener.java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

@Component
public class OrderKafkaListener {

    private final ObjectMapper json;
    private final OrderProjectionService projection;

    public OrderKafkaListener(
            ObjectMapper json, OrderProjectionService projection) {
        this.json = json;
        this.projection = projection;
    }

    @KafkaListener(
        topics = "partner.order-status",
        groupId = "order-projector")
    public void consume(
            ConsumerRecord<String, String> record,
            Acknowledgment acknowledgment) throws JsonProcessingException {
        OrderEvent event = json.readValue(record.value(), OrderEvent.class);
        projection.apply(event);       // DB transaction commits on return
        acknowledgment.acknowledge(); // only then report completion
    }
}
~~~

This flow is intentionally synchronous. If `projection.apply` throws, execution never reaches `acknowledge()`; retries and DLT depend on the configured `DefaultErrorHandler`/container. If the DB transaction commits and the consumer crashes before committing offsets, the broker redelivers and `consumed_event` deduplicates safely.

**Never retry every exception infinitely.** Schema-broken JSON, missing required fields, or invalid events belong in DLT/quarantine with alerts and explicit disposition rules. Limit retries with backoff and observability to transient network/DB failures.

### Kafka Pitfalls to Avoid

1. **Producer `acks=all` does not commit consumer offsets.** A durable broker write can still sit unconsumed by your app.
2. **`acknowledge()` is not a database commit.** Call it only after business transactions return cleanly; wait for completion if async.
3. **Manual ACK does not automatically isolate batch errors.** Committing past an unprocessed record skips it. With `asyncAcks` or parallel processing, verify how the container handles out-of-order ACKs and crashes.
4. **Rebalances trigger redeliveries.** Consumers losing partitions via `max.poll.interval.ms` or group changes fail to commit offsets; already-committed DB records reappear.
5. **DLT recovery also advances offsets.** Error handlers can mark recovered records and advance the cursor; confirm DLT publishing succeeded and check version-specific recovery commit rules.
6. **Kafka transactions do not span external databases.** Transactional producers and offset-in-transaction work across Kafka topics only. Crossing PostgreSQL still requires outbox/inbox and idempotency.

## 5. RabbitMQ: Delivery Ack, Requeue, and Redelivery Ordering

In RabbitMQ, deliveries carry a channel-scoped **delivery tag**. In manual acknowledgement mode:

- `basicAck(deliveryTag, false)` confirms that single delivery; once processed by the broker, it leaves unacked state.
- `basicNack(deliveryTag, false, true)` rejects and requests **requeue**; this is immediate redelivery, not a delayed backoff retry.
- `basicReject(deliveryTag, false)` rejects **without requeue**; routes to a dead-letter exchange if configured, or drops the message otherwise.
- `basicAck(deliveryTag, true)` confirms **all unacked deliveries** up to that tag on **the same channel**. Passing `multiple=true` accidentally confirms messages still in flight.

Delivery tags are valid only on the originating channel; never save a tag to ACK on another channel or after channel closure.

### Spring AMQP: `AUTO` vs. RabbitMQ `autoAck`

Spring AMQP `AcknowledgeMode.AUTO` (the common container default) means **the Spring container automatically ACKs after the listener succeeds**, or rejects/nacks on failure per policy. It is **different** from protocol-level `autoAck=true` (where the broker fires and forgets without manual ACKs).

Spring AMQP `AcknowledgeMode.MANUAL` requires explicit app ACK/NACK calls. `AcknowledgeMode.NONE` skips broker ACKs altogether and is unsuitable whenever durable processing must precede confirmation.

Example:

~~~yaml
spring:
  rabbitmq:
    listener:
      simple:
        acknowledge-mode: manual
        prefetch: 10
~~~

~~~java
// OrderRabbitListener.java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.rabbitmq.client.Channel;
import java.io.IOException;
import org.springframework.amqp.core.AmqpHeaders;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@Component
public class OrderRabbitListener {

    private final ObjectMapper json;
    private final OrderProjectionService projection;

    public OrderRabbitListener(
            ObjectMapper json, OrderProjectionService projection) {
        this.json = json;
        this.projection = projection;
    }

    @RabbitListener(queues = "partner.order-status")
    public void consume(
            String body, Channel channel,
            @Header(AmqpHeaders.DELIVERY_TAG) long tag) throws IOException {
        try {
            OrderEvent event = json.readValue(body, OrderEvent.class);
            projection.apply(event);       // DB transaction already completed
            channel.basicAck(tag, false); // confirm this exact delivery
        } catch (JsonProcessingException invalidJson) {
            channel.basicReject(tag, false); // requires DLX to avoid losing bad data
        } catch (Exception failure) {
            channel.basicNack(tag, false, false); // route to DLX if configured
        }
    }
}
~~~

This assumes the queue already has a **dead-letter exchange (DLX)** and separate retry/quarantine handling. `basicNack(..., requeue=false)` does not auto-create retry queues; without a DLX, messages can be discarded. In production, separate transient errors for bounded delayed retries, cap poison messages, and emit alerts instead of looping.

Never replace error branches with infinite `basicNack(tag, false, true)`: broken messages redeliver immediately in a tight loop, burning CPU, clogging queues, and scrambling order. If a channel or connection drops before ACK, unacked deliveries requeue and redeliver—another reason idempotency remains mandatory even when ACKing after DB commits.

### Why RabbitMQ Does Not Guarantee Ordered Business Effects

Queues enqueue in order, yet multiple consumers, `prefetch > 1`, parallel workers, requeues, nacks, retry queues, DLXs, and redeliveries break strict ordering. An older event can arrive after a newer one even if initially enqueued in order. The `redelivered` flag is a diagnostic hint, **not a unique event ID** for deduplication.

Publisher confirms are separate: publishers should enable confirms to ensure the broker accepted the message, plus publisher returns/`mandatory` or valid topology to catch unroutable messages. A successful publisher confirm never guarantees the consumer received or committed the event.

## 6. JMS and Other Brokers: Ack Semantics Depend on Session

In JMS, **Session** acknowledgement mode and transaction settings control redelivery:

| JMS Mode | Characteristics | Misconception Risk |
| --- | --- | --- |
| `AUTO_ACKNOWLEDGE` | Session/container ACKs per receive/listener lifecycle | Listener return does not imply `@Async` tasks finished |
| `CLIENT_ACKNOWLEDGE` | App invokes `message.acknowledge()` | Calling it typically ACKs **all unacked messages received on that Session**, not just one |
| `DUPS_OK_ACKNOWLEDGE` | Lazy ACKs allowing duplicate deliveries | Requires idempotency |
| `SESSION_TRANSACTED` | `Session.commit()`/`rollback()` governs JMS transaction | Does not automatically span PostgreSQL transactions |

Spring's JMS listener container supports session transactions and transaction managers; exact commit/rollback behavior depends on container config and JMS provider. Never conflate **JMS local transactions**, **database transactions**, and **XA/JTA distributed transactions**. True cross-resource atomicity requires compatible transaction coordination with performance/complexity trade-offs; in most integrations, inbox/outbox is simpler and safer.

For Apache Pulsar or other subscription-based brokers, likewise separate **consumer ACK** from external DB commits; cumulative vs. individual ACKs, negative ACKs, redelivery, and ordering depend on subscription type, batching, and client version. Never mechanically apply "one ACK equals one Kafka offset commit" across all brokers.

## 7. Out-of-Order: Separate Broker Order from Business Order

**Ordered delivery** is how the broker hands out messages. **Ordered processing** is sequential execution in listeners. **Ordered effects** means final system state reflects true business sequence. All three are distinct.

Example:

~~~text
orderId = ORD-1024
event version 5: CREATED
event version 6: CONFIRMED
event version 7: PAID

Consumer A receives version 7; writes DB fast.
Consumer B retries version 5; writes DB late.
Without a version guard on UPDATE, DB reverts to CREATED.
~~~

Three practices normally work together:

1. **Route by stable entity key.** In Kafka, key messages by `orderId` so all events for one order land in the same partition (assuming stable partition counts/topology); never use random event IDs as keys when entity ordering matters.
2. **Limit per-entity concurrency.** Align consumer/partition assignment, executors, retries, and rebalances; never assume multi-consumer queues preserve effect ordering.
3. **Enforce business version guards.** Use `version`, sequence numbers, or CAS/optimistic locking in SQL to reject stale updates. For non-idempotent deltas requiring every step, detect gaps and buffer, replay, or quarantine.

**Idempotency solves duplicates only**—not out-of-order delivery. A previously unseen `eventId` can still be **older** than current state. Conversely, version checks alone do not prevent duplicate emails or duplicate debits on retries.

In HTTP → broker → DB → cache pipelines, updating caches before DB commits—or without versioned invalidation—lets stale callbacks overwrite fresh cache entries. Each adapter must clarify the source of truth and cache update timing.

## 8. Investigation Workflow for Lost, Duplicate, or Out-of-Order Incidents

### Step 1 — Pick a Representative Event and Reconstruct Its Timeline

Select an event with clear `eventId`, `businessKey` (e.g., `orderId`), `version`, and `traceId`. Align timestamps across producer, broker, consumer, and database logs:

~~~text
10:00:00.001 producer publish eventId=evt-8192
10:00:00.013 broker append (topic, partition=2, offset=351)
10:00:00.021 consumer receive (group=order-projector)
10:00:00.030 DB BEGIN
10:00:00.044 DB COMMIT success
10:00:00.045 consumer ack/commit attempt
10:00:00.047 commit result: timeout/unknown
10:00:02.100 consumer receive again (same eventId)
10:00:02.103 duplicate key -> skip safely
~~~

Never log full sensitive payloads. Helpful safe fields: `eventId`, `orderId`, `version`, `topic`, `partition`, `offset`, `consumerGroup`, `deliveryTag` (RabbitMQ), `redelivered`, `attempt`, `transactionId`, start/end timestamps, and commit result.

### Step 2 — Answer Four Boundary Questions

1. **Did the broker actually accept and store/route the message?** Check Kafka producer ACKs/errors, RabbitMQ publisher confirms/returns, permissions, and topology.
2. **Did the consumer receive the message?** Check group assignment, committed offset vs. position/lag; in RabbitMQ check ready/unacked, consumer counts, redeliveries, and DLQs.
3. **What did the DB or target store commit?** Inspect transaction logs, domain rows, inbox/idempotency tables, and outboxes—not just "process success" logs.
4. **When did the ACK/offset commit happen?** Verify actual ACK mode, executing thread, error handler, retry/DLT recovery, and container commit rules.

### Step 3 — Match Symptoms to Likely Causes

| Observed Symptom | Primary Suspect | Verification |
| --- | --- | --- |
| Committed offset passed the event yet DB shows no change | Auto-commit or ACK before DB commit; handler swallowed error as success | Align timeline, transaction, and ACK call site |
| DB applied the change twice for the same `eventId` | Redelivery after DB commit before ACK; missing idempotency | Check unique keys/inbox, offset/ACK errors, and crashes |
| Kafka still holds the record yet group does not re-read | Offset already committed; reset policy ignored because group has offset | Check committed offset and plan controlled replay |
| RabbitMQ queue holds persistent unacked messages | Missing manual ACK, stalled handler, or excessive prefetch | Check channels, delivery tags, threads, and timeouts |
| RabbitMQ ready/requeued surging | Tight-loop requeue on poison message | Configure bounded retries, backoff, DLQ, and inspect payload error |
| Newer state overwritten by older state | Unstable partition key, retries/concurrency, missing version guard | Inspect keys, versions, and parallel paths |
| Messages suddenly lost to DLT after upgrade | Error handler / `ackAfterHandle` / recoverer behavior shifted | Read release notes, recovery config, and DLT publishing |
| Messages land in DLT while consumer group moves on | Framework treated record as recovered | Verify DLT replay rules, monitoring, and SLAs |

### Step 4 — Fix the Data Flow, Not Just Retry Counts

- Move ACK/offset commits after business transaction commits; for async flows, await durable completion or write an inbox row first.
- Enforce `eventId` or business idempotency keys via unique constraints/atomic inserts—not non-atomic cache read-then-write checks.
- Add version checks, gap handling, and entity-key routing wherever order matters.
- Standardize bounded retries, backoff, error classification, DLT/quarantine, and replay procedures reusing original idempotency keys.
- When publishing to another broker after DB writes, adopt **transactional outbox**: persist domain change + outbox in one DB transaction, publish asynchronously and mark sent; downstream consumers stay idempotent because publishing can repeat.

## 9. After Upgrading Spring Boot, Spring Kafka, or Spring AMQP

Upgrades can alter defaults, bean configs, error handlers, transaction integration, and listener completion rules. Never assume post-upgrade defects mean the broker lost data.

### Version Comparison Checklist

| Component | What to Verify | Impact If Wrong |
| --- | --- | --- |
| Spring Kafka `AckMode` & `enable.auto.commit` | Active container factory, custom beans, config overrides | Offsets commit at the wrong moment |
| Kafka error handler / recoverer / DLT | Retries/backoff, `ackAfterHandle`, recovered offset commit | Skips bad records silently or loops forever |
| Kafka transactions | Transaction manager, producer ID, isolation level, offsets in TX | Reads aborted records or mis-scopes transactions |
| Kafka concurrency / polling | `max.poll.interval.ms`, `max.poll.records`, executors, rebalances | Rebalances, duplicates, out-of-order effects |
| Spring AMQP listener ACK mode | `AUTO`/`MANUAL`/`NONE`, container factory type, error handler | Early ACKs or hung deliveries |
| RabbitMQ retry / DLX / prefetch | `defaultRequeueRejected`, DLX, `prefetch`, policy | Poison loops or silently dropped messages |
| JMS session transactions | Acknowledgement mode, `sessionTransacted`, transaction manager | Inconsistent commits relative to DB |
| DB transactions & async | `@Transactional` proxies, propagation, `@Async`/Reactor `subscribe` | ACKs fire before real commit |

**Safe upgrade strategy:** pin dependencies to Spring Boot's BOM, read release notes for changed modules, capture live listener container configurations, compare before/after behavior on identical test events, and monitor metrics/alerts after rollout. If switching listeners from synchronous to reactive/async, explicitly define who awaits completion and who calls ACK; returning a freshly constructed `Mono` or `CompletableFuture` does not mean side effects completed.

Never try to guarantee correctness merely by extending retention, adding replicas, or bumping retry counts. Lock down the **business commit milestone** and **broker progress milestone** first.

## 10. Realistic Fault-Injection Test Matrix

In an isolated integration environment using real brokers (e.g., Testcontainers) and test databases, assert **domain records, inbox/idempotency tables, offsets/ACKs, side-effect counts, DLTs, and version ordering**:

| Test Case | How to Trigger | Expected Result |
| --- | --- | --- |
| Crash before DB commit | Throw exception mid-transaction | Zero DB updates; record remains eligible for retry |
| Crash after DB commit before ACK | Inject fault right after service returns | Event redelivered yet unique event ID prevents duplicate effect |
| Timeout during ACK / offset commit | Simulate network drop or rebalance on commit | Handle uncertain state; redelivery stays safe |
| Schema-invalid JSON | Send payload with missing field or wrong type | Quarantined/DLT per policy with alert; no infinite loop |
| Duplicate event | Send two records with identical `eventId` | Single business effect |
| Out-of-order events | Send version 7 then version 5 for same `orderId` | Final state stays at version 7 |
| Async processing | Slow task or failure after callback | Never ACKs prior to durable commit |
| Rebalance | Stop one consumer mid-flight; add another | Zero dropped messages; duplicates handled idempotently |
| RabbitMQ poison retry | Message throws persistently | Bounded retries then routed to DLQ without blocking consumers |
| Publish to second broker | DB commits yet initial publish fails | Outbox retries; downstream avoids duplicate side effects |

If the system handles live users or sensitive partner APIs, execute crash/replay drills only in test environments with synthetic fixtures. When replaying production, scope consumer groups, time windows, and batches carefully; forecast side effects and never reset offsets wholesale without verifying idempotency.

## 11. Diagnostic Exercises and Self-Check Questions

**Scenario A — "Kafka swallowed our orders."** A listener polls offset 201, calls `acknowledge()`, then fires an `@Async` DB write. The process crashes; offset 202 committed while the DB lacks the order. Root cause is **acknowledging progress earlier than durable persistence**. Fix by processing synchronously/awaiting completion, or writing a durable inbox row before ACKing, plus idempotency for redeliveries.

**Scenario B — "A webhook processed twice."** DB committed, yet RabbitMQ `basicAck` failed to reach the broker due to a dropped connection. The broker redelivers. This is normal **at-least-once** behavior, not a broker bug. Enforce a stable event ID and unique constraint inside the same transaction as the business update.

**Scenario C — "A paid order reverted to newly created."** Event `version=7` processed before `version=5` due to retries and concurrency; because their event IDs differed, inbox deduplication let both through. Fix with conditional version checks or keyed ordering/gap handling per event contract.

**Self-Check:**

1. **Does Kafka producer `acks=all` mean the consumer wrote the database?** No; it confirms broker publication per Kafka policy only.
2. **Does committing offset `58` mean record 58 finished processing?** No; it stores `58` as the next position to read.
3. **Why can ACKing after DB commit still result in redelivery?** A crash or timeout between DB commit and broker ACK leaves the broker unsure of progress.
4. **Is Spring AMQP `AUTO` identical to RabbitMQ `autoAck=true`?** No; container `AUTO` ACKs after the listener completes successfully.
5. **Does an idempotency key preserve ordering automatically?** No; you also need ordering keys, version guards, or gap handling.
6. **Can Kafka transactions guarantee exactly-once emails?** No; Kafka transaction scope does not include external email servers.

When troubleshooting, build an evidence-backed timeline for **publish → deliver → process → DB commit → broker ACK/offset commit**. When designing new flows, choose **ACK after business commit**, add **idempotency** for redeliveries, and enforce **version/ordering policies** to protect state. These three decisions prevent data loss, duplicates, and out-of-order corruption at every integration boundary instead of relying on "message received" logs.
