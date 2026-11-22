# Queues and Delivery in Messaging Application Logging (Java)

## 1. What do queue and delivery mean when an application uses a message broker?

Message-driven applications exchange work through a **queue/topic** instead of calling every component directly in a request–response style. A producer creates a message; the broker stores and distributes it; a consumer receives the message, executes business logic, and responds according to the protocol. Logging helps track each stage, but **a single log line does not by itself guarantee that a message arrived or was processed successfully**.

Example:

```text
Order API (producer)
   |
   | send event OrderCreated
   v
Broker queue / topic
   |
   | deliver
   v
Payment Worker (consumer)
   |
   +-- process payment
   |
   +-- ACK / NACK / commit offset / retry / DLQ
   |
   v
Order service / database / downstream

At each step: application log -> appender -> agent -> collector
                                (separate log pipeline)
```

There are **two queue/delivery systems** to distinguish:

1. **Business message delivery:** the broker delivers messages to consumers; it governs ACK, redelivery, retry, DLQ, and the durability of business data.
2. **Log record delivery:** the logging backend may enqueue events into an async appender; the sink may be failing or the collector may be slow. A message that has been ACKed to the broker **does not mean the audit log of its processing has been persisted**.

For example, `logger.info("Processed order {}", id)` does not turn a processing operation into a transaction; the logger call can be filtered out by log level, the event can sit in an undrained queue, or the collector may fail to receive it.

Learning objectives: identify message states and the points where accurate logging is possible, choose an appropriate ACK/retry contract, correlate logs across multiple delivery attempts of the same message, prevent duplicate side effects, and verify behavior with tests and fault injection.

## 2. Foundational Terminology

| Term | Meaning | Logging Considerations |
| --- | --- | --- |
| **Producer** | Component that sends business messages | Log the send request and the broker confirmation result separately |
| **Broker** | System that receives, stores, and routes messages | Capacity, replication, retention, and ack semantics depend on the technology |
| **Queue** | Work channel from which consumers receive deliveries | Not all brokers implement queues the same way |
| **Topic/partition** | Message broadcast channel that can be partitioned | Kafka tracks an offset within each partition |
| **Consumer** | Component that receives and processes messages | Must record attempt, outcome, and duration |
| **Delivery** | A single instance of the broker handing a message to a consumer | A single message may be delivered multiple times |
| **ACK** | Signal confirming receipt/processing per the contract | Broker ACK ≠ audit/log durability |
| **NACK/reject** | Rejection of the current delivery | May requeue, retry, or route to DLQ depending on the broker |
| **Offset commit** | Consumer recording the processed position in a partition | Does not delete the message from the topic |
| **Retry** | Re-attempting processing after an error | Easily causes duplicate effects without idempotency |
| **Redelivery** | Broker delivering the same logical message again | Can happen after a crash, timeout, or reject/requeue |
| **DLQ / dead-letter** | Place to isolate messages that cannot be processed per policy | Does not mean the error has been resolved |
| **Backpressure** | Mechanism to throttle producers/consumers under overload | Finite buffers still need handling when full |
| **Idempotency** | Repeated execution of the same operation produces no unintended side effects | Must rely on durable state in production |
| **Correlation ID** | Links logs across multiple services/attempts | Never use tokens or PII as an ID |

Not every protocol has the same ACK and NACK primitives. RabbitMQ AMQP supports consumer acknowledgments; Kafka typically tracks **offset/position** and has a commit mechanism. Specific choices must be understood in the context of the backend and client library in use.

## 3. Lifecycle of a Message and Where You Can Log

A flow can be broken down into milestones:

```text
Producer:
  CREATED -> SEND_ATTEMPTED -> BROKER_CONFIRMED / SEND_FAILED
                                      |
                                      v
Consumer:
  DELIVERED -> PROCESSING -> BUSINESS_COMMITTED
                                      |
                             ACK/COMMIT_ATTEMPTED
                                      |
                            ACK_CONFIRMED/UNCERTAIN
         \-> RETRY_SCHEDULED / REQUEUED / DEAD_LETTERED
```

This is a **conceptual observability model**, not a built-in automatic state machine in every broker. Log event names must express what has **actually been confirmed**, avoiding vague messages such as `message success`.

### Producer: sending does not mean the broker persisted it

A producer may:

1. Create the message and its ID.
2. Call an asynchronous send API.
3. Receive a confirmation or failure callback/future.
4. Log with the status matching that exact milestone.

`SEND_ATTEMPTED` describes that a send request was issued. `BROKER_CONFIRMED` should appear only after a confirmation signal per the broker contract. If the connection fails **after the broker receives the message but before the callback returns**, the producer may not know whether the message arrived: do not automatically assume `SEND_FAILED` means the message does not exist; retry with an appropriate key/idempotency strategy.

### Consumer: receiving does not mean it has been processed

`DELIVERED` (or `RECEIVED`) means the consumer saw the message. It does **not** mean it was successfully written to a database or that an email was sent. `BUSINESS_COMMITTED` should be logged only after evidence that the side effect reached its contractual milestone. Only after the business work is done does the consumer decide to ACK/commit offset according to policy.

### ACK can be ambiguous

A consumer may process a message and commit to the database successfully, send an ACK, and then lose the connection before knowing whether the broker received the ACK. The broker may redeliver the same message. Therefore:

- `ACK_ATTEMPTED` is the event that **the consumer attempted to acknowledge**.
- `ACK_CONFIRMED` is used only when the client/protocol provides a signal sufficient to verify it.
- `ACK_UNCERTAIN` is meaningful when the connection drops or the result is unknown.
- A redelivery does not by itself prove that the consumer rolled back the previous attempt.

Log along **verified boundaries**, not on a hunch that it "usually succeeds."

## 4. Delivery Guarantees: at-most-once, at-least-once, exactly-once

| Model | Idea | Consequence | Practical Use |
| --- | --- | --- | --- |
| **At-most-once** | Do not retry after an early confirmation point or do not retain messages on failure | Few duplicates, possible loss of work | Low-criticality telemetry or requirements that tolerate loss |
| **At-least-once** | Message remains eligible for redelivery until appropriate ack/commit is reached | Possible duplicate processing | Common for business workers; requires idempotency |
| **Exactly-once** | No observable duplicate effects within a specific scope | Usually requires transactions, dedup/idempotency, and careful design | Specific capability of a broker/pipeline |

**Do not use "exactly once" as a blanket promise for the entire application.** Kafka provides transactional/idempotent producers and exactly-once processing within Kafka-supported boundaries, but updating an external database, sending an email, or calling an external payment gateway **does not automatically participate in the same Kafka transaction**. On the RabbitMQ side, delivery ACKs likewise do not provide exactly-once guarantees for business side effects.

### ACK before or after business logic?

Suppose a message requests a balance update:

```text
Option A:
  ACK/commit progress -> update DB
  Crash between the two steps -> progress advanced but DB not updated
  => risk of lost operation.

Option B:
  update DB -> ACK/commit progress
  Crash between the two steps -> DB updated, broker may redeliver
  => risk of duplicate operation.
```

For fault tolerance, applications typically **execute business logic first, then ACK**, combined with an idempotent consumer; however, late ACKs alone are insufficient if side effects lack deduplication.

### At-least-once does not mean every attempt ends in success

Retries can hit permanent errors, backlogs can fill up, TTLs can expire, and messages can be dead-lettered or exceed retry limits. Delivery guarantees are meaningful only within the **scope and assumptions** of the infrastructure: retention, durability, ack configuration, network partitions, crashes, and stop policies.

## 5. Logging Per Delivery Attempt vs. Per Logical Message

A logical message must be distinguished from its delivery attempts.

| Field | Purpose | Rule |
| --- | --- | --- |
| `messageId` | ID of the business message | Preserved across redeliveries of the same message |
| `operationId` | Business action the message serves | Used to link multiple messages in the same workflow |
| `correlationId` | Request/distributed tracing linkage | Control source/length; never use secrets |
| `deliveryAttempt` | Delivery/processing attempt number | Increment with basis; brokers may not provide an absolute counter |
| `consumerGroup` / `consumerName` | Who received the message | Use only necessary technical identifiers |
| `topic` / `queue` | Where the message arrived | Do not copy untrusted names/values into unescaped schemas |
| `partition` / `offset` | Position in Kafka | Meaningful within a topic-partition |
| `deliveryTag` | AMQP channel delivery identifier | Do not treat as a system-wide message ID |
| `eventType` | `MESSAGE_RECEIVED`, `PROCESSING_FINISHED`, etc. | Expresses a lifecycle milestone |
| `outcome` | `SUCCEEDED`, `FAILED`, `RETRY_SCHEDULED`, etc. | Outcome of the verified milestone |
| `durationMs` | Duration of a single attempt | Do not aggregate across retries unless explicitly defined |
| `reasonCode` | Safe error classification code | Avoid raw exception messages containing sensitive data |

Example:

```json
{
  "schemaVersion": 1,
  "eventId": "log-201",
  "timestamp": "2026-01-01T10:00:00Z",
  "service": "payment-worker",
  "eventType": "MESSAGE_PROCESSING_FINISHED",
  "messageId": "msg-73",
  "operationId": "order-19",
  "queue": "payments",
  "deliveryAttempt": 2,
  "outcome": "SUCCEEDED",
  "durationMs": 24
}
```

This is an illustrative event, not a RabbitMQ/Kafka schema or a live production log. `eventId` in the example can be the ID of the log/telemetry event; do not replace `messageId` with `eventId` if you need to identify **two processing attempts of the same business message**.

### Event names should reflect measurable results

| Log event | What a reader can conclude |
| --- | --- |
| `MESSAGE_RECEIVED` | The consumer received/read a delivery |
| `PROCESSING_STARTED` | An attempt has started |
| `BUSINESS_EFFECT_COMMITTED` | The side effect reached its defined milestone |
| `ACK_REQUESTED` | The application invoked acknowledge/commit |
| `ACK_CONFIRMED` | A confirmation signal was received if supported by the protocol/API |
| `REDELIVERY_OBSERVED` | The same logical message was received again |
| `RETRY_SCHEDULED` | A retry schedule was confirmed to be persisted/queued |
| `DEAD_LETTERED` | The message was routed to the DLQ per contract |
| `PROCESSING_FAILED` | The processing attempt failed; does not by itself state the final operation outcome |

Avoid logging `ACK_SUCCESS` if the API only enqueues an unconfirmed ACK command. With Kafka, calling `commitAsync` should not be treated as a successful offset commit before its callback reports the result.

## 6. Retry, Redelivery, and Poison Messages

A **transient error** might be a brief network timeout, an overloaded dependency, or a recoverable connectivity issue. A **permanent/business error** might be an invalid schema, missing required fields, or a message type the consumer does not support. Policies must distinguish between them to avoid retrying an unresolvable error.

A conceptual flow:

```text
PROCESS
  |
  +-- Success ------------------------> ACK
  |
  +-- Retryable error -- attempts left -> retry with backoff
  |
  +-- Invalid / attempts exhausted ---> DLQ + alert
  |
  +-- Result unknown -----------------> reconcile/idempotency check
```

### Error Classification

| Error Type | Recommended Action | Log Content |
| --- | --- | --- |
| Temporary timeout | Retry with delay/backoff and jitter | `RETRY_SCHEDULED`, attempt, next delay |
| Rate limit | Honor retry-after when present, limit concurrency | `RATE_LIMITED`, source, next attempt time |
| Invalid schema | Reject or DLQ per policy | `REJECTED`, non-sensitive error code |
| Invalid credentials/config | Alert, pause, or DLQ; no unbounded hot retry | `CONFIGURATION_FAILURE`, affected service |
| Suspected prior commit | Query/idempotency/reconcile before repeating side effect | `RESULT_UNCERTAIN` |
| Repeated failures | Move to DLQ or quarantine | `RETRY_EXHAUSTED`, attempt count, DLQ id |

**Never use an unbounded `while(true)` retry loop.** Backoff, jitter, retry budgets, and dead-letter policies protect both broker and consumer when downstream systems fail. Immediately requeuing to the head of a queue lets the same poison message spin continuously and starve healthy messages.

### A dead-letter queue does not fix errors by itself

A DLQ stores messages that could not be processed under policy, but it still requires:
- Clear read/write permissions and sufficient retention for investigation without exhausting storage.
- Alerts on the count/rate of messages entering the DLQ.
- Tooling to inspect metadata and safe reason codes without exposing sensitive raw payloads on dashboards.
- A process to fix the root cause and **re-drive** after schema compatibility checks, avoiding infinite loops.
- A mechanism to preserve message ID/correlation ID and log `REPLAY_REQUESTED`/`REPLAY_COMPLETED` events when needed.
- Verification that duplicate processing is safe upon replay; a DLQ does not eliminate the need for idempotency.

Do not assume every broker automatically moves messages to a DLQ after 3 attempts: you must configure the appropriate counter, policy, queue binding/dead-letter exchange, or middleware.

## 7. Standalone Java 17 Example: Redelivery, Lost ACK, Idempotency, and DLQ

This example **simulates an in-memory broker**, not a real RabbitMQ or Kafka instance. It intentionally lets message `m1` succeed in processing while its ACK is lost, causing redelivery; the consumer keeps a set of processed IDs so it does not apply the side effect twice. Message `m2` always fails and is routed to the DLQ after three attempts.

The example demonstrates **state transitions** and how to emit distinct logs; it does not claim that an in-memory queue or set provides durability or exactly-once guarantees.

### 7.1. Source Code `QueueDeliveryDemo.java`

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class QueueDeliveryDemo {
    record Message(String id, String body) {}
    record Delivery(Message message, int attempt) {}

    static final class FakeBroker {
        private final Deque<Delivery> queue = new ArrayDeque<>();
        private final List<Delivery> dlq = new ArrayList<>();

        void publish(String id, String body) {
            queue.addLast(new Delivery(new Message(id, body), 1));
            System.out.println("PUBLISHED id=" + id);
        }

        Delivery next() {
            return queue.pollFirst();
        }

        void ack(Delivery delivery) {
            System.out.println("ACK id=" + delivery.message().id());
        }

        void redeliverAfterLostAck(Delivery delivery) {
            int nextAttempt = delivery.attempt() + 1;
            queue.addLast(new Delivery(delivery.message(), nextAttempt));
            System.out.println("REDELIVERED id="
                    + delivery.message().id()
                    + " attempt=" + nextAttempt);
        }

        void nackRetryOrDlq(Delivery delivery, int maxAttempts) {
            String id = delivery.message().id();

            if (delivery.attempt() >= maxAttempts) {
                dlq.add(delivery);
                System.out.println("DLQ id=" + id
                        + " attempts=" + delivery.attempt());
            } else {
                int nextAttempt = delivery.attempt() + 1;
                queue.addLast(new Delivery(
                        delivery.message(), nextAttempt));
                System.out.println("REQUEUED id=" + id
                        + " attempt=" + nextAttempt);
            }
        }

        int pendingCount() {
            return queue.size();
        }

        int dlqCount() {
            return dlq.size();
        }
    }

    static final class Consumer {
        private final Set<String> applied = new HashSet<>();

        void handle(Delivery delivery, FakeBroker broker) {
            String id = delivery.message().id();
            int attempt = delivery.attempt();

            if (applied.contains(id)) {
                System.out.println("DEDUP id=" + id
                        + " attempt=" + attempt);
                broker.ack(delivery);
                return;
            }

            if ("m2".equals(id)) {
                System.out.println("FAILED id=" + id
                        + " attempt=" + attempt);
                broker.nackRetryOrDlq(delivery, 3);
                return;
            }

            // Simulate that the business effect has been applied.
            applied.add(id);
            System.out.println("APPLIED id=" + id
                    + " attempt=" + attempt);

            if ("m1".equals(id) && attempt == 1) {
                // Intentionally simulate an ACK not being recorded by the broker.
                System.out.println("ACK_LOST id=" + id);
                broker.redeliverAfterLostAck(delivery);
            } else {
                broker.ack(delivery);
            }
        }

        int appliedCount() {
            return applied.size();
        }
    }

    public static void main(String[] args) {
        FakeBroker broker = new FakeBroker();
        Consumer consumer = new Consumer();

        broker.publish("m1", "valid");
        broker.publish("m2", "always-fails");

        Delivery delivery;
        while ((delivery = broker.next()) != null) {
            consumer.handle(delivery, broker);
        }

        System.out.println("applied=" + consumer.appliedCount());
        System.out.println("dlq=" + broker.dlqCount());
        System.out.println("pending=" + broker.pendingCount());
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac QueueDeliveryDemo.java
java QueueDeliveryDemo
```

**Exact stdout** when running this example standalone:

```text
PUBLISHED id=m1
PUBLISHED id=m2
APPLIED id=m1 attempt=1
ACK_LOST id=m1
REDELIVERED id=m1 attempt=2
FAILED id=m2 attempt=1
REQUEUED id=m2 attempt=2
DEDUP id=m1 attempt=2
ACK id=m1
FAILED id=m2 attempt=2
REQUEUED id=m2 attempt=3
FAILED id=m2 attempt=3
DLQ id=m2 attempts=3
applied=1
dlq=1
pending=0
```

### 7.2. State-by-State Explanation

1. `PUBLISHED`: the fake broker placed both messages into the deque. This is an **in-memory record**, not a disk/replication confirmation.
2. The consumer receives `m1`, applies the business effect once, and simulates a lost ACK. The broker re-enqueues `m1` with `attempt=2`.
3. `m2` fails on its first attempt; the fake broker appends it to the back of the queue without dropping the event.
4. When `m1` is delivered a second time, the `applied` set already contains its ID, so the consumer logs `DEDUP` and ACKs without applying the side effect again.
5. `m2` fails on attempt 2, retries a 3rd time, and moves to the DLQ. The `DLQ` log is evidence that the example's logic moved it into the in-memory DLQ list.
6. The final counts `applied=1`, `dlq=1`, and `pending=0` reflect the state of the two fake collections. This does not imply a production application/broker will exhibit this exact ordering or guarantee.

### 7.3. What This Example Intentionally Leaves Unsolved

- The `HashSet` deduplication works **only while the same process is alive**; a restart loses the state.
- `applied.add(id)` and the business effect are not bound inside a durable transaction. In production, the update and processed-ID marker must be atomic or backed by a dedicated idempotency mechanism.
- `FakeBroker` has no persistence, replication, ack protocol, timeouts, multiple consumers, concurrency, or partitions.
- The retry loop has no delay so stdout remains easy to verify. Production systems require backoff and load limits.
- Message bodies are not printed to the console because they may contain customer data or secrets; the example logs only ID, attempt, and status.
- **Lost ACK** is simulated explicitly: calling `redeliverAfterLostAck` after consumer execution is not a built-in API in RabbitMQ or Kafka.

This example is suitable for learning the lifecycle and testing decision logic, but it does not replace integration tests against a real broker and database.

## 8. Idempotent Consumers: Deduplication Must Accompany Business Logic

A common algorithm:

```text
Receive message with messageId
   |
   v
Start DB transaction
   |
   +-- messageId already processed? -> do not re-apply effect
   |                                -> commit -> ACK
   |
   v
Check business conditions
   |
   v
Execute mutation + store processed messageId marker
   |
   v
Commit DB transaction
   |
   v
ACK broker per contract
```

In SQL, the processed-markers table can have a unique key `(consumerName, messageId)`, or use a business key/idempotency key directly in the business table. When multiple consumers receive the same ID concurrently, the unique constraint/transaction ensures both cannot apply the effect **if all related operations are inside the same transaction**.

Illustrative pseudocode, not a complete SQL script for every RDBMS:

```sql
BEGIN;

-- INSERT the messageId marker; if there is a conflict, determine it was already processed.
INSERT INTO processed_messages (consumer_name, message_id)
VALUES ('payment-worker', 'm1');

-- Apply the side effect only when the new insert succeeds.
UPDATE orders
SET status = 'PAID'
WHERE id = 'order-19' AND status = 'PENDING';

COMMIT;
```

You must check the `INSERT` and `UPDATE` results, locking/isolation levels, and unique-key error codes for your specific database. If the transaction rolls back, both the processed marker and the mutation must roll back. **Do not log `SUCCESS` just because an `UPDATE` statement threw no exception when it actually updated 0 rows.**

### Side Effects Outside the DB Transaction

Sending an email or calling a payment gateway does not automatically join the `processed_messages` table transaction. If the email succeeds and the process crashes before committing the processed marker, redelivery may send the email again. In that case you need:

- An idempotency key supported by the external system; or
- A transactional outbox for outbound commands, paired with an idempotent downstream consumer; or
- A reconciliation process / `UNKNOWN` state when the remote outcome is uncertain.

A single local database transaction **does not guarantee exactly-once behavior for external side effects**.

## 9. Transactional Outbox and Inbox for Messaging Systems

### Producer Outbox

A risk on the producer side:

```text
COMMIT order database
    |
    v
send OrderCreated to broker
    X Process crash
=> Order exists, but the message was never published.
```

The **transactional outbox** pattern stores the business change and a pending-publish record in the same database transaction; a dispatcher then sends outbox records to the broker and marks them dispatched per the ack policy.

```text
DB transaction:
  update order
  insert outbox(eventId, payload, status=PENDING)
  COMMIT
       |
       v
Dispatcher -> Broker (retry if needed)
       |
       v
Broker confirmation -> mark dispatched
```

If the broker receives the message but the dispatcher loses the response, the same event may be sent again. Therefore, consumers still need dedup/idempotency; the outbox closes the gap between DB commit and message publication, **it does not by itself create end-to-end exactly-once**.

### Consumer Inbox

The **inbox** pattern stores processed `messageId` values under a unique key in the same transaction as the side effect, preventing redeliveries from re-executing it. Complex workflows can store `RECEIVED/PROCESSING/COMPLETED/FAILED` states, provided they also design leases/timeouts and recovery for processes that die while `PROCESSING`.

Each inbox state can have its own log, but do not treat `inbox.status=COMPLETED` as proof that the delivery log reached the collector.

## 10. Applying Correctly with RabbitMQ

RabbitMQ (AMQP 0-9-1) has **publisher confirms** and **consumer acknowledgments** — two distinct confirmation paths.

- Publisher confirms tell the producer that the broker accepted the publish under the configured semantics. They do **not** confirm that a consumer processed it.
- With manual consumer acks, the consumer calls `basicAck` when work reaches the chosen milestone.
- `basicNack`/`basicReject` can reject a delivery; the `requeue` flag controls whether it is returned to the queue. Immediate requeuing while the consumer is still failing can cause a hot loop.
- `deliveryTag` is meaningful only within a channel; do not use it as a cross-service message ID.
- When a connection/channel closes before ACK, unacked messages can generally be redelivered depending on configuration and queue state; do not assume they are preserved across every type of infrastructure failure.
- Prefetch (`basicQos`) limits how many unacked messages a consumer holds, affecting throughput and backpressure.

Illustrative snippet **within an application that already has a configured RabbitMQ Java client**, not a standalone program:

```java
long tag = delivery.getEnvelope().getDeliveryTag();
String messageId = delivery.getProperties().getMessageId();

try {
    processIdempotently(delivery.getBody(), messageId);
    channel.basicAck(tag, false);
    logger.info("message processed and ack attempted id={}", messageId);
} catch (TransientBusinessException e) {
    channel.basicNack(tag, false, true);
    logger.warn("message requeued id={}", messageId);
}
```

This snippet omits many real-world details: `delivery`, `channel`, `logger`, `processIdempotently`, and the exception type are application components; it cannot compile standalone. `basicAck` typically sends an acknowledgment frame; **the API returning does not necessarily mean the broker has durably acked it** under all connection failure scenarios. In practice, you must handle channel/connection failures, permanent errors, DLX/DLQ, and separate retry policies. When `basicNack` itself fails, logs must reflect that ACK/NACK is **uncertain**, not claim it was definitely requeued.

### Message redelivered flag

Some deliveries carry a `redeliver` flag from the broker indicating the message was previously delivered. This is a useful signal, but **do not use it in place of an idempotency key** or a durable attempt counter. A message might be published twice with different IDs, or the broker may lack enough history to provide the attempt count your application expects.

## 11. Applying Correctly with Kafka

Kafka does not have RabbitMQ-style per-message ACK/NACK on the consumer side. Consumers read records by **topic-partition-offset** and store a **committed offset** for the consumer group to know where to resume after a restart or rebalance.

- The offset within each partition identifies a record's position, not a system-wide message ID.
- Auto-commit may be unsuitable when processing requires side effects before recording progress. Manual commit gives explicit control over processing-before-commit order.
- If the side effect completes and the consumer crashes before committing the offset, the record may be read again. The consumer must be idempotent.
- If the offset is committed before the side effect and the consumer crashes, the record may be skipped on resume, causing lost work.
- Kafka typically commits the **next offset to read**; when a record at offset `n` is processed, the committed position represents `n+1` for that partition.
- Rebalances can reassign partitions to other instances; in-flight tasks and partition ownership must be managed carefully.
- A permanent parse/validation error can block partition progress; use a retry topic, DLQ, or controlled skip policy aligned with business and audit contracts.

Illustrative snippet **within a configured Kafka consumer with `consumer` and `record` variables in scope**, not standalone:

```java
TopicPartition tp =
        new TopicPartition(record.topic(), record.partition());

try {
    processIdempotently(record.value(), record.key());
    consumer.commitSync(
        Map.of(tp, new OffsetAndMetadata(record.offset() + 1)));
    logger.info(
        "record processed; offset commit returned topic={} "
            + "partition={} offset={}",
        record.topic(), record.partition(), record.offset());
} catch (Exception e) {
    logger.warn(
        "processing or commit failed topic={} partition={} offset={}",
        record.topic(), record.partition(), record.offset());
    // Do not automatically advance the offset in the error branch.
    // Classify the error and decide seek/retry/DLQ according to design.
}
```

This example is not meant to be copied verbatim into a loop polling multiple records/partitions; in batches you must track contiguous processed offset ranges and never commit past an unsuccessful record. `commitSync` can fail or time out; offset commit state sometimes needs reconciliation. During rebalances, consumer thread ownership must be controlled.

Kafka supports idempotent producers and transactions for certain read-process-write flows within Kafka, provided consumer isolation levels and transactions are configured properly. **Do not assume a Kafka transaction covers external databases or HTTP APIs.**

## 12. Proper Logging in Java Producers/Consumers

### Avoid free-form messages; choose queryable fields

In a system using SLF4J:

```java
logger.info(
    "message received id={} topic={} partition={} offset={} attempt={}",
    messageId, topic, partition, offset, attempt);

logger.info(
    "message processed id={} outcome={} durationMs={}",
    messageId, outcome, durationMs);

logger.warn(
    "message retry scheduled id={} reasonCode={} attempt={}",
    messageId, reasonCode, attempt);
```

This is illustrative code inside an application that already defines those variables. Placeholder calls produce **text messages**, not automatic structured JSON. For pipelines requiring reliable field queries, use structured logging/JSON encoders suited to your backend and verify the actual output.

### When to log ERROR, WARN, INFO?

A suggested policy, not a mandatory standard:

- `DEBUG`: message receipt and normal path details when volume is high and per-event visibility is unnecessary.
- `INFO`: observable milestones such as processing completed, DLQ re-drive, or required business state transitions.
- `WARN`: retryable errors, unexpected redeliveries, slow offset commits, growing backlogs.
- `ERROR`: messages exceeding the retry budget, critical failures, prolonged disconnections, configuration errors, or mandatory events failing to persist.

Do not use log levels as a substitute for `outcome`. A `DENIED` result due to business policy can be a normal outcome and need not be `ERROR`. Conversely, losing a mandatory audit event can be a critical incident even if the business message finished processing.

### Preserving correlation across threads

MDC/ThreadContext can attach `messageId`, `operationId`, and `correlationId` to logs:

```java
// Example for an SLF4J application: process each delivery on a worker.
Map<String, String> before = MDC.getCopyOfContextMap();
try {
    MDC.put("messageId", validatedMessageId);
    MDC.put("operationId", validatedOperationId);
    processOneMessage();
} finally {
    if (before == null) {
        MDC.clear();
    } else {
        MDC.setContextMap(before);
    }
}
```

This snippet is **not standalone**; it assumes `java.util.Map` and `org.slf4j.MDC` are imported and actual variables/methods exist. Security condition: validate correlation IDs at the boundary, and never copy tokens or raw payloads into MDC. When using executors or reactive frameworks, MDC is typically thread-bound; propagate context using the framework's supported mechanism rather than assuming `CompletableFuture` copies it automatically.

If a handler fails to clear MDC, a reused worker thread can log the wrong `messageId` from a previous delivery, misleading redelivery investigations onto another request.

## 13. Backpressure, Consumer Lag, and Deep Queues

Delivery cannot be sustained if producers outpace consumers for long enough while the system has finite resources.

Common operational signals:

| Metric | How to Interpret |
| --- | --- |
| Queue depth / ready messages | Backlog of waiting work, if exposed by the broker |
| Unacked / in-flight | Messages delivered but not yet ACKed |
| Consumer lag | Difference between consumer progress and log end offset in Kafka |
| Redelivery rate | Frequency of messages needing redelivery |
| Retry scheduled / exhausted | How many events are waiting or have exceeded the retry budget |
| DLQ ingress / age | Rate and age of messages entering the DLQ |
| Processing p95/p99 | Latency of a single attempt; avoid looking only at averages |
| Ack/commit failure | Sign that progress is not being confirmed |
| Outbox pending age | Delay in publishing messages even after business DB commit |
| Logging queue depth / drops | Whether log observability itself is experiencing an outage |

Metric names vary by broker, client, and agent; the table above lists the kinds of signals to look for, **not universal default metric names**.

When queue backlog grows, you can:
- Increase consumer count within partition/ordering constraints and database capacity.
- Reduce heavy per-message work or batch appropriately.
- Configure prefetch/max in-flight limits to avoid holding too many messages in memory.
- Retry with backoff to avoid hammering an overloaded dependency.
- Isolate poison messages through controlled retry/DLQ policies.
- Tune producer rates or admission control according to SLAs.

**Adding consumers does not always increase throughput.** Kafka limits parallelism within a consumer group by the number of partitions and their assignment; the database or downstream service may already be the bottleneck. Uncontrolled scaling can increase contention and retry rates.

## 14. Ordering: Log Order and Processing Order Are Not the Same

Message `m1` may be published before `m2`, yet `m2` finishes first due to parallel processing, retries, or network issues.

- A **single queue + single sequential consumer** makes FIFO easier to observe, but you must still account for delivery/requeue behavior.
- **Kafka** preserves record order **within a single partition** by offset; it does not guarantee global order across partitions.
- **RabbitMQ** has specific ordering rules, but multiple consumers, requeuing, and priorities can make processing/completion order differ from publish order.
- **Async appenders/log collectors** can also display logs late, batched, or ingested out of creation order.

To reconstruct a timeline, use source `occurredAt`, `ingestedAt` if available, `messageId`, `operationId`, `attempt`, `partition+offset`, or `sequence` within a defined scope. Timestamps across hosts can suffer from clock skew; do not assert causal order solely by sorting timestamps.

### A redelivery log does not prove a processing error

A consumer can:
1. Commit the side effect successfully.
2. Send an ACK but lose the connection.
3. Receive the same message again.

Looking only at two `MESSAGE_RECEIVED` lines shows two deliveries, not whether the business effect was duplicated. Log `PROCESSING_APPLIED` or `DEDUPLICATED` at the right boundaries, linked to a reliable idempotency store and event ID.

## 15. Logging Backend Queues: Another Layer of Risk

Messaging applications often emit heavy logging on the hot path. With Logback's `AsyncAppender`, logging events enter a **separate in-memory queue** before a worker writes them to a file, console, or collector.

```text
Business producer -> broker -> consumer -> DB/ACK
                                    |
                                    v
                              logger.info(...)
                                    |
                                    v
                             AsyncAppender queue
                                    |
                                    v
                               logging sink
```

Distinguish clearly:

- Broker ACK speaks only to the business message.
- Logger level/filters decide whether an event is emitted at all.
- `AsyncAppender` can buffer events in memory; a crash loses undrained events.
- When the log queue fills up, the backend may block the logging thread or discard lower-level events depending on configuration.
- A slow async logging worker does not mean the business consumer should retry the message.
- Graceful shutdown/log draining must be designed; even draining the queue does not prove a remote collector is durable if the transport lacks appropriate acknowledgments.

In Logback, `queueSize`, `discardingThreshold`, `neverBlock`, and `maxFlushTime` control `AsyncAppender` behavior; semantics differ across backends. Do not assume `neverBlock=true` gives "zero business impact and zero log loss": when the queue is full, it can drop events.

**Critical audits** such as permission changes or financial transactions should not rely solely on best-effort async `INFO` logs when durability is required. Use an audit repository/outbox or an acknowledged persistence path and monitor sink availability.

## 16. Securing Message Data in Logs

Business messages can contain payment details, identifiers, addresses, tokens, documents, or large payloads. Never log the entire message body just because a message broker is involved.

What to log:
- `messageId`, `operationId`, `queue`/`topic`, `partition`/`offset` when needed.
- `schemaVersion`, message type, outcome, `reasonCode`.
- Attempt, latency, retry delay, DLQ destination, and verified status.
- Resource IDs **evaluated** as appropriate and safe to log.

What to avoid:
- Passwords, private keys, access/refresh tokens, session cookies, raw `Authorization` headers.
- Entire JSON/XML payloads or object `toString()` outputs that may contain PII.
- Unvetted exception messages/stack traces if they can contain sensitive URIs, credentials, or queries.
- Client-supplied `correlationId` values without validation, which enables log injection.
- Business payloads in metric labels with high cardinality or broad access.

If raw messages must be retained for forensics, store them in a vault with proper access control, encryption, retention, and access auditing—do not send them to a general log collector. DLQs can also hold raw payloads and require equivalent protection.

## 17. Testing Queues and Delivery

### 17.1. Basic Test Matrix

| Scenario | Business Expectation | Log Expectation |
| --- | --- | --- |
| Successful publish | Broker accepts per contract | `SEND_ATTEMPTED` and `BROKER_CONFIRMED` at the right milestones |
| Publish timeout | May or may not have been received | Uncertain state; IDs support reconciliation |
| Consumer receives and succeeds | Effect verified before ACK | `RECEIVED`, `COMMITTED`, `ACK_ATTEMPTED` in causal order |
| Consumer crashes before effect | Message remains eligible for redelivery per contract | No false `COMMITTED` log |
| Crash after effect, before ACK | Redelivery possible | Second attempt logs `DEDUPLICATED`, no duplicate effect |
| Transient error | Bounded retry with backoff | Attempt + `reasonCode`, no unbounded stack spam |
| Poison message | Quarantined/DLQ per policy | `RETRY_EXHAUSTED`/`DEAD_LETTERED` with ID |
| Kafka commit fails | Record may be re-read | Do not log commit confirmed unless verified |
| High queue backlog | Stays within memory/disk budget | Queue/lag/backpressure metrics and alerts |
| Log sink fails | Business policy still holds | Independent logging metrics/status; mandatory audits not silently lost |
| Two concurrent consumers | No double-effect | Compare ID/effect sets; do not enforce global ordering |
| DLQ re-drive | Only authorized events replayed | Preserve correlation, idempotency, retry history |

### 17.2. Unit Tests You Can Run Immediately on `QueueDeliveryDemo`

With the fake broker, write tests to verify:
- Publish `m1`, `m2` and drain the queue: `appliedCount()==1`, `dlqCount()==1`, `pendingCount()==0`.
- Capture stdout or swap in a test event collector: `APPLIED m1` appears only **once**, and `DEDUP m1` appears on redelivery.
- `m2` is tried exactly three times and moves to the DLQ.
- NACK/requeue is never confused with ACK.
- If a configurable retry budget is added, verify the threshold prevents an infinite loop.

Do not turn the demo's text output into a production logging standard. Tests should observe **state and structured events**, then validate the backend's actual output in a separate integration test.

### 17.3. Integration Tests with a Real Broker

Use an isolated test broker/container (RabbitMQ/Kafka matching your stack), a test database, and unique event IDs:

1. Send a message and verify producer ack/commit per the protocol.
2. Start the consumer and pause right before/after business commit using a latch or hook.
3. Kill/restart the consumer at different failure points to measure redelivery.
4. Verify the number of business mutations via the idempotency key, not merely by counting `RECEIVED`.
5. Check that logs include `messageId`, `attempt`, outcome, and `reasonCode`.
6. Take the collector offline separately; verify which logs are lost and that message processing continues as designed.
7. Test retry budgets, DLQ, and re-drive without creating unintended duplicates.
8. Clean up queues/topics/test groups and temp files; never send real payloads or connect to production.

When testing async logging, use `BlockingQueue.poll(timeout)`, a latch, or an actual sink ack; **never use `Thread.sleep(500)` and assume the message/log was delivered**. When asserting an event must *not* appear, use a proper drain/sentinel/FIFO boundary or definitive confirmation mechanism.

### 17.4. Fault Injections to Include

- Broker unavailable during producer send.
- Broker confirms, but producer loses the response.
- Consumer finishes processing, but ACK/commit is not recorded.
- Consumer crashes mid-transaction.
- DB update conflict/rollback.
- Downstream side effect succeeds, but callback times out.
- Immediate requeue causing a hot loop, and verifying backoff resolves it.
- Unparseable message payload.
- Full queue, expired retention, or full DLQ.
- Log appender/collector fails while business processing continues.

A well-designed system can clearly answer **where duplicates can happen**, **where messages can be lost**, **which event proves what**, and **how to recover** from each failure mode.

## 18. Common Issues and How to Handle Them

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| Multiple `MESSAGE_RECEIVED` for same ID | Redelivery, retry, or duplicate publish | Distinguish message ID vs. attempt; check ACK/dedup |
| Business logic runs twice | ACK lost after commit, missing idempotency | Transactional inbox/idempotency key |
| `PROCESSED` logged but DB unchanged | Logged before commit or 0 rows updated | Finalize outcome only after verifying mutation |
| Message "disappeared" | Early ACK, retention, TTL, auto-commit, query filter | Reconcile broker metadata/offsets with producer source |
| Queue stuck on one record | Poison message retrying indefinitely | Bounded retries, backoff, DLQ |
| Kafka lag grows while consumer is alive | Slow processing, pause, rebalance, DB bottleneck | Profile processing, limit concurrency, check partitions |
| RabbitMQ unacked grows | Consumer not ACKing, dead workers, or prefetch too high | Inspect consumer lifecycle and unacked count |
| DLQ grows continuously | Schema mismatch or prolonged dependency outage | Classify reasons, fix root cause before re-drive |
| ACK logged yet still redelivered | Ambiguous ACK/dropped connection or misnamed milestone | Separate `ACK_REQUESTED` from confirmed |
| Logs lost while messages still process | Async logging queue discarding or collector down | Monitor log pipeline separately; ensure audit durability |
| Logs show another request's `messageId` | MDC leak across thread pool | Restore/clear MDC and test concurrency |
| Dashboard shows events out of order | Ingest delay, clock skew, multiple partitions | Use event ID, offset/sequence, and source timestamp |
| Scaling consumers gives no speedup | Partition limit or downstream bottleneck | Identify throughput bottleneck before scaling |

## 19. Production Readiness Checklist

- [ ] Distinguish **business message delivery** from **log event delivery**.
- [ ] Define names and semantics for `RECEIVED/COMMITTED/ACK_REQUESTED/RETRY/DLQ` milestones.
- [ ] Producer knows when it receives broker confirmation and how to handle ambiguous send outcomes.
- [ ] Consumer commits business effects before ACK/offset commit per contract.
- [ ] Idempotency keys and appropriate transactional/durable state are in place.
- [ ] Retries have timeouts, backoff, budgets, and transient/permanent classification.
- [ ] DLQ/re-drive, retention, access controls, and backlog alerts are configured.
- [ ] Logs include `messageId`, `operationId`, `attempt`, and Kafka `topic-partition-offset` where applicable.
- [ ] Do not promise global ordering or exactly-once outside broker/pipeline boundaries.
- [ ] MDC/correlation is propagated and cleared at worker boundaries; raw payloads are never logged.
- [ ] Monitor queue depth, lag, unacked, redelivery, DLQ, and ACK/commit failures.
- [ ] Logging pipeline has independent metrics/status and a defined policy when the async queue fills.
- [ ] Critical business audits have a durable persistence contract rather than relying solely on `logger.info`.
- [ ] Crash tests cover pre/post-commit, lost ACK, duplicates, retries, and collector outages.
- [ ] Runbooks exist for reconciling missing/duplicate messages and performing safe replays.

**Key takeaway:** queues decouple send time from receive time, but they do not automatically guarantee "processed once." Logs must make clear **which delivery attempt**, **which operation**, **which ACK milestone was reached**, **whether the business effect committed**, and **whether the logging path itself is reliable**. Combining a consistent observability schema, properly timed ACKs, durable idempotency, bounded retry/DLQ policies, and fault-injection testing makes messaging systems observable, recoverable, and safe to operate.
