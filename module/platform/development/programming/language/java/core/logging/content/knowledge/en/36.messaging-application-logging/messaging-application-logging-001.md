# Message Consumer Logging in Java: Accurately Recording Message Processing

## 1. What Is a Message Consumer and What Should Be Logged?

In a **message-driven** application, a *producer* creates messages and sends them to a broker/queue/topic; a *consumer* receives messages and executes business logic. The consumer may run in a Java application using Kafka, RabbitMQ, JMS, or another queuing system.

```text
Producer --> Broker/topic/queue --> Consumer poll/delivery
                                      |
                                      v
                            Deserialize / validate
                                      |
                                      v
                            Execute business logic
                                      |
                             +--------+--------+
                             |                 |
                           success           failure
                             |                 |
                      ACK / commit       retry / reject / DLQ
                             |
                     downstream effects
```

**Message consumer logging** is the practice of recording structured events at meaningful milestones: when a message is received, processing starts, processing succeeds, a transient error occurs, a retry is scheduled, a message is dead-lettered, a duplicate is detected, or the consumer requests acknowledgment of processing.

The goal is not to print the entire payload, but to be able to answer:

- Which message was received by which consumer?
- Which delivery attempt is this; has it already been processed successfully?
- What did the consumer do with the message: process, retry, skip, or send to a dead-letter queue?
- At which step did an error occur, and is it retryable?
- Has the business state been committed or is it still in progress?
- Was the ACK/offset commit **requested**, or was it confirmed by the broker according to the API?
- Why did a message get lost, arrive late, or appear multiple times?

A message can be delivered multiple times, and a single processing attempt can emit multiple log events. Therefore, **do not infer the number of successful business operations from the number of "received" log lines**.

## 2. Distinguishing Consumer Milestones

Good log design uses **clear event names and outcomes**:

| Suggested Event | Meaning That Can Be Asserted | Do Not Automatically Assert |
| --- | --- | --- |
| `consumer.received` | The application observed a message delivery | Business processing is complete |
| `consumer.processing_started` | The handler started processing the delivery | The transaction has committed |
| `consumer.processing_succeeded` | The handler met the defined success condition | The broker has received the ACK |
| `consumer.ack_requested` | The application called the acknowledgment/commit API | The broker has durably persisted the offset or ACK |
| `consumer.offset_commit_succeeded` | The client received a commit result per the API | All downstream side effects are complete |
| `consumer.retry_scheduled` | There is a plan/command to schedule the message for reprocessing | The broker is guaranteed to redeliver |
| `consumer.requeued` | Requeue was requested or confirmed per specific semantics | No duplicates will occur |
| `consumer.dead_lettered` | Moved to dead-letter per the defined confirmation level | The DLQ exists permanently or the message will be processed |
| `consumer.duplicate_detected` | The system determined it has already seen the event/idempotency key | It can be safely skipped in every context |
| `consumer.validation_failed` | Content failed validation rules | Retrying will succeed |

**Watch the semantics:** an `acknowledge()` method may merely mark an offset for the container to commit later, or it may ask the broker to acknowledge delivery per the protocol. Name events to reflect the actual confirmation level; do not log `ACK_CONFIRMED` when only calling a method without confirmation evidence.

### 2.1. Do Not Log "processed" Immediately Upon Receipt

Wrong:

```java
// Non-standalone illustrative code: only received, not yet processed.
log.info("Message processed, id={}", messageId);
businessHandler.process(message);
```

If `process` fails, the log has over-claimed. A more reasonable sequence:

```java
// Integration code; requires handler/logger/variables provided by the application.
log.debug("event=consumer.received id={}", messageId);
businessHandler.process(message); // Commit is not guaranteed if the transaction has not ended.
log.info("event=consumer.processing_succeeded id={}", messageId);
```

For transactional handlers, determine **success after commit**; a log line before commit can be wrong if the transaction rolls back. If using outbox/transactional events, synchronize business state and audit events according to your dedicated design.

## 3. Three Frequently Confused Identifiers

| Identifier | Belongs To | Purpose |
| --- | --- | --- |
| **Message ID / event ID** | Logical message assigned by producer or broker | Identifies content/event that may be redelivered |
| **Delivery/attempt ID** | A specific delivery or execution | Distinguishes duplicate/retry processing attempts |
| **Correlation/trace ID** | Business flow or distributed call chain | Links producer, broker, consumer, and other services |

An illustrative schema:

```json
{
  "event": "consumer.processing_succeeded",
  "timestamp": "2026-11-10T02:00:00Z",
  "service": "billing-service",
  "consumerGroup": "billing-workers",
  "messageId": "evt-2041",
  "messageType": "OrderCreated",
  "correlationId": "corr-719",
  "attempt": 2,
  "source": "orders",
  "partition": 3,
  "offset": 9012,
  "durationMs": 18,
  "outcome": "SUCCEEDED"
}
```

This is **example data**, not the default output of Kafka or Logback. Kafka has topic/partition/offset; RabbitMQ has exchange/routing key/queue and delivery tag; JMS has `JMSMessageID`, `JMSCorrelationID`. Do not mechanically apply Kafka fields to every broker.

Principles:

1. **Do not treat message ID and delivery tag as the same thing.** In RabbitMQ, a delivery tag is tied to a **channel** and a delivery, not a global business identifier.
2. With Kafka, the tuple **topic + partition + offset** identifies a record's position in the topic log within a specific scope; key/value and business event ID are separate concerns.
3. `correlationId` and `traceparent` may be supplied by a producer/client; **validate, bound length, and apply trust policies** before using them in logs.
4. Framework/broker-provided attempt counts have their own semantics; delivery count, retry count, and application processing count do not always match.
5. If the producer does not yet provide a stable business event ID, an offset or JMS message ID can help with investigation, but **idempotency keys must align with business semantics** when handling duplicates across copies/re-publishes.

## 4. Where Should You Log?

You should not emit an INFO line for every variable assignment in a consumer. Choose the points needed for investigation:

```text
receive delivery
  -> consumer.received                   (usually DEBUG / sampled INFO)
  -> deserialize/validate
      -> consumer.invalid_message        (WARN, do not dump raw payload)
  -> duplicate/idempotency check
      -> consumer.duplicate_detected     (INFO/DEBUG depending on requirements)
  -> business transaction
      -> consumer.processing_succeeded   (INFO or metric per policy)
      -> consumer.processing_failed      (WARN/ERROR per impact)
  -> retry policy
      -> consumer.retry_scheduled        (WARN/INFO, attempt, delay, reason)
      -> consumer.dead_lettered          (WARN/ERROR, reason and destination)
  -> acknowledgment / offset commit
      -> consumer.ack_requested          (DEBUG/INFO depending on requirements)
      -> consumer.commit_failed          (ERROR/WARN when outcome is known)
```

**Not every milestone needs to be logged at INFO.** In a system handling tens of thousands of messages per second, logging every receipt and completion can create substantial overhead. If audit events are required to be retained, choose a dedicated audit channel with clear guarantees; do not arbitrarily sample them like diagnostic logs.

A minimal log event should include: `event`, `messageType`, sanitized `messageId`, `consumer`/`group`, source topic/queue, a delivery identifier, `outcome`, duration, and a normalized error category on failure. Add `correlationId` when valid.

## 5. Java 17: Standalone Consumer, Retry, Duplicate, and DLQ Example

The following example uses `java.util.logging` (JUL) built into the JDK and an **in-memory simulated queue**. It demonstrates:

- Message `m-1` is processed successfully.
- Message `m-2` encounters a transient failure on the first attempt; it is re-queued and succeeds on the second attempt.
- Message `m-3` encounters an unrecoverable failure and is moved to a simulated dead-letter list.
- A duplicate delivery of `m-1` is detected as a duplicate.
- The `ACK_REQUESTED` event is logged **after processing or valid duplicate skipping** per the demo rules, not before.
- Finally, summary counters are printed so they can be verified accurately.

**Important:** this is a simulation for learning about event logs, **not a broker**—there is no real ACK, durable DLQ, transaction, authentication, or exactly-once guarantee. The `processed` set exists only in RAM and is not safe to use as a production idempotency system.

Save the file **`MessageConsumerLoggingDemo.java`**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class MessageConsumerLoggingDemo {
    record Message(String id, String type, String correlationId) {}
    record Delivery(Message message, int attempt) {}

    static final class RetryableFailure extends RuntimeException {}
    static final class PermanentFailure extends RuntimeException {}

    private static void process(Delivery delivery) {
        String type = delivery.message().type();
        if ("RETRY_ONCE".equals(type) && delivery.attempt() == 1) {
            throw new RetryableFailure();
        }
        if ("INVALID".equals(type)) {
            throw new PermanentFailure();
        }
        // Simulated business success; no database involved.
    }

    private static void emit(
            Logger logger, Level level, String event, Delivery delivery) {
        Message message = delivery.message();
        logger.log(level, "event=" + event
                + " messageId=" + message.id()
                + " type=" + message.type()
                + " attempt=" + delivery.attempt()
                + " correlationId=" + message.correlationId());
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.consumer");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        Handler stdout = new Handler() {
            {
                setLevel(Level.ALL);
            }

            @Override
            public void publish(LogRecord record) {
                if (record != null && isLoggable(record)) {
                    System.out.println(record.getLevel().getName()
                            + " " + record.getMessage());
                }
            }

            @Override
            public void flush() {
                System.out.flush();
            }

            @Override
            public void close() {
                flush();
            }
        };

        logger.addHandler(stdout);

        try {
            Message first = new Message("m-1", "ORDER_CREATED", "c-1");
            Message transientMessage =
                    new Message("m-2", "RETRY_ONCE", "c-2");
            Message invalid = new Message("m-3", "INVALID", "c-3");

            ArrayDeque<Delivery> queue = new ArrayDeque<>();
            queue.add(new Delivery(first, 1));
            queue.add(new Delivery(transientMessage, 1));
            queue.add(new Delivery(invalid, 1));
            queue.add(new Delivery(first, 1)); // Redelivery of the same logical event.

            Set<String> processed = new HashSet<>();
            List<Message> deadLetters = new ArrayList<>();
            int retries = 0;
            int duplicates = 0;

            while (!queue.isEmpty()) {
                Delivery delivery = queue.removeFirst();
                Message message = delivery.message();

                emit(logger, Level.INFO, "RECEIVED", delivery);

                if (processed.contains(message.id())) {
                    duplicates++;
                    emit(logger, Level.INFO, "DUPLICATE_SKIPPED", delivery);
                    emit(logger, Level.INFO, "ACK_REQUESTED", delivery);
                    continue;
                }

                try {
                    process(delivery);
                    processed.add(message.id());
                    emit(logger, Level.INFO, "SUCCEEDED", delivery);
                    emit(logger, Level.INFO, "ACK_REQUESTED", delivery);
                } catch (RetryableFailure failure) {
                    retries++;
                    queue.addLast(new Delivery(
                            message, delivery.attempt() + 1));
                    emit(logger, Level.WARNING,
                            "RETRY_SCHEDULED", delivery);
                } catch (PermanentFailure failure) {
                    deadLetters.add(message);
                    emit(logger, Level.WARNING, "DLQ_STORED", delivery);
                    emit(logger, Level.INFO, "ACK_REQUESTED", delivery);
                }
            }

            logger.info("event=SUMMARY processed=" + processed.size()
                    + " retries=" + retries
                    + " dlq=" + deadLetters.size()
                    + " duplicates=" + duplicates);
        } finally {
            logger.removeHandler(stdout);
            stdout.close();
        }
    }
}
```

Compile and run with **JDK 17 or later**:

```bash
javac MessageConsumerLoggingDemo.java
java MessageConsumerLoggingDemo
```

Exact **`stdout` output**:

```text
INFO event=RECEIVED messageId=m-1 type=ORDER_CREATED attempt=1 correlationId=c-1
INFO event=SUCCEEDED messageId=m-1 type=ORDER_CREATED attempt=1 correlationId=c-1
INFO event=ACK_REQUESTED messageId=m-1 type=ORDER_CREATED attempt=1 correlationId=c-1
INFO event=RECEIVED messageId=m-2 type=RETRY_ONCE attempt=1 correlationId=c-2
WARNING event=RETRY_SCHEDULED messageId=m-2 type=RETRY_ONCE attempt=1 correlationId=c-2
INFO event=RECEIVED messageId=m-3 type=INVALID attempt=1 correlationId=c-3
WARNING event=DLQ_STORED messageId=m-3 type=INVALID attempt=1 correlationId=c-3
INFO event=ACK_REQUESTED messageId=m-3 type=INVALID attempt=1 correlationId=c-3
INFO event=RECEIVED messageId=m-1 type=ORDER_CREATED attempt=1 correlationId=c-1
INFO event=DUPLICATE_SKIPPED messageId=m-1 type=ORDER_CREATED attempt=1 correlationId=c-1
INFO event=ACK_REQUESTED messageId=m-1 type=ORDER_CREATED attempt=1 correlationId=c-1
INFO event=RECEIVED messageId=m-2 type=RETRY_ONCE attempt=2 correlationId=c-2
INFO event=SUCCEEDED messageId=m-2 type=RETRY_ONCE attempt=2 correlationId=c-2
INFO event=ACK_REQUESTED messageId=m-2 type=RETRY_ONCE attempt=2 correlationId=c-2
INFO event=SUMMARY processed=2 retries=1 dlq=1 duplicates=1
```

### 5.1. Sequence Explanation

- The queue initially contains four deliveries: m-1, m-2, m-3, then a duplicate m-1.
- m-1 succeeds, its ID is added to `processed`, and `ACK_REQUESTED` is logged.
- m-2 throws `RetryableFailure` on the first attempt; the consumer enqueues a new delivery with `attempt=2` at the **end of the queue**. Thus, the retry happens **after** the waiting items.
- m-3 throws `PermanentFailure` and is added to `deadLetters` in RAM. Naming it `DLQ_STORED` in this demo means **stored in a local list**, not a broker with a durable DLQ.
- When the duplicate delivery of m-1 arrives, `processed` already contains that ID; the handler skips simulated business processing and logs `DUPLICATE_SKIPPED`.
- On its second attempt, m-2 runs `process` without error and completes.
- The final result includes two successful logical messages, one retry, one message sent to the simulated dead-letter list, and one duplicate detected.

**Key takeaway:** `processed` is an in-process `HashSet`; it is **neither** durable **nor** concurrency-safe. In a real application, two consumers processing the same business event concurrently could both read "not yet processed"; idempotency requires appropriate uniqueness constraints/transactions/locks. The `ACK_REQUESTED` lines in the example **do not call a broker**. Do not use them as proof that a broker committed an offset or acknowledged delivery.

### 5.2. Why Not Print the Entire Payload?

The example keeps only fixed-value IDs and types. In real systems, message payloads can contain personal data, tokens, payment information, or megabytes of JSON. Logging raw payloads at `INFO` causes data leaks and log storms. On deserialization errors, you may **not be able to read messageId from the body**; prefer broker metadata plus a safe error code instead of trying to print the raw body.

## 6. Designing a Structured Log Schema

Suggested fields for an event:

| Field | Purpose |
| --- | --- |
| `event` | Lifecycle milestone: received, succeeded, retry, ack_requested, dead_lettered |
| `timestamp`, `level` | Recording time and severity level |
| `service`, `instanceId` | Where the consumer is running |
| `consumerGroup` / `subscription` | Message consumption group |
| `sourceTopic` / `sourceQueue` | Message source |
| `partition`, `offset` | Record position when using Kafka |
| `deliveryTag`, `redelivered` | RabbitMQ-appropriate metadata |
| `messageId`, `messageType` | Logical event and schema/type |
| `correlationId`, `traceId` | Request/processing chain correlation |
| `attempt` | Attempt number per defined counter |
| `outcome`, `errorCode` | Success, failure, or rejection |
| `durationMs` | Measured processing duration |
| `retryDelayMs`, `retryReason` | Retry policy details |
| `deadLetterDestination` | Failure destination if confirmed |
| `schemaVersion` | To interpret historical log data accurately |

Not every broker has every one of these fields. The schema should be stable, versioned, and **only include available, meaningful metadata**; use `null` or omit fields when not applicable rather than fabricating offsets or delivery tags.

Use stable event code values instead of only logging `"Exception while processing"`. For example, when searching for retried messages:

```text
event = consumer.retry_scheduled
AND consumerGroup = billing-workers
AND errorCode = TEMPORARY_DEPENDENCY_UNAVAILABLE
```

This is a **conceptual filter**, not the query syntax of a specific storage backend.

## 7. Log Levels for Consumers: INFO, DEBUG, WARN, ERROR

A practical approach:

| Situation | Commonly Considered Level | Why |
| --- | --- | --- |
| Every normal delivery received | DEBUG or sampled INFO | High volume, easy to cause log storms |
| Processing succeeded | INFO if per-message tracking is needed; metric otherwise | Balances traceability and cost |
| Duplicate safely handled | DEBUG/INFO | Explains redelivered messages |
| Retryable failure within retry budget | WARN or INFO | Error occurred but system recovers automatically |
| Permanent failure / DLQ | WARN/ERROR | Requires observation and handling |
| Broker/consumer loop stopped working | ERROR | Infrastructure incident impacting processing progress |
| Deserialization error of a poison message | WARN or ERROR per policy | Must not let one message trigger an uncontrolled log storm |
| Unexpected commit/ack error | WARN/ERROR | Risk of redelivery and duplicate side effects |

**Do not turn log levels into outcomes.** A `consumer.retry_scheduled` event may be logged at WARN, but the `event`/`outcome` fields are what represent the state. Do not log ERROR for millions of normal retries if it only creates alert noise; likewise, do not silently drop an important DLQ event.

Application logs and metrics complement each other. Metric counters can track throughput/attempts/failures, while event logs serve per-case investigation. For operations requiring mandatory auditing, detailed logs must go through a pipeline with dedicated retention/durability requirements; do not use sampling that loses required evidence.

## 8. Retry, Backoff, and Dead-Letter Logging

### 8.1. Classifying Retryable vs. Permanent Failures

Classification examples:

- **Retryable:** transient downstream connection loss, HTTP 503, retryable deadlock, temporary broker rejection.
- **Permanent / unsuitable for verbatim retry:** unparseable schema-invalid payload, missing required field, unsatisfied business rule in the current state, invalid event signature.
- **Unknown:** requires policy/quarantine; do not default to infinite retries.

Classification must be based on specific business logic. An HTTP 400 may be permanent in one API, yet in another API it may relate to un-refreshed configuration; do not apply a blanket rule like "all exceptions of type X are retryable" without evaluating the root cause.

A `retry_scheduled` event should include:

```json
{
  "event": "consumer.retry_scheduled",
  "messageId": "evt-2041",
  "attempt": 3,
  "nextAttempt": 4,
  "retryDelayMs": 4000,
  "errorCode": "DEPENDENCY_UNAVAILABLE",
  "maxAttempts": 5
}
```

This is an illustrative structure. If the broker/container decides the retry, name the state according to the confirmed level: `retry_requested` differs from `retry_enqueued` or `redelivered`.

### 8.2. Why Not Retry Infinitely and Log a Stack Trace Every Time?

If a poison message is continuously delivered:

1. The handler fails.
2. The container retries immediately.
3. Each retry logs a large stack trace.
4. The log queue or disk overflows.
5. Processing of other messages is degraded.

Use a **retry budget, backoff, and jitter** where appropriate, defining a maximum number of attempts and a quarantine/dead-letter path. Log the attempt count, error category, and a correlation ID; detailed stack traces can be logged via sampling/policy without stripping essential investigative fields.

For persistently failing messages, apply **rate limiting** to repeated alerts and use metrics to count occurrences instead of repeatedly printing full payloads.

### 8.3. Dead-Lettering Must Have Real Evidence

Separate these states:

- `dead_letter_requested`: the application intends to move the message.
- `dead_letter_publish_succeeded`: there is evidence the publisher/broker accepted it per contract.
- `dead_lettered`: the message has reached quarantine according to system-defined criteria.
- `original_ack_requested`: acknowledgment of the original message was requested after ensuring processing concluded appropriately.

If a consumer **ACKs the original message before DLQ publish succeeds**, the message can be lost if publishing fails. If DLQ publish succeeds but the original ACK fails, it may be redelivered and dead-lettered again. Depending on the broker, dead-lettering may be handled by the broker after reject/nack rather than by the consumer publishing directly. Verify the actual guarantees provided and design idempotency/reconciliation accordingly.

Do not log `DLQ_SUCCEEDED` when merely calling an API to start publishing without the corresponding confirmation result.

## 9. ACK, Offset Commit, and Broker-Specific Differences

### 9.1. Kafka

A Kafka consumer reads **records** in partitions and tracks position via offsets. Distinguish between:

- **Poll/receive:** the record has been read by the client.
- **Business processing:** whether business logic has run / the transaction has committed.
- **Offset commit:** the consumption position is committed for the consumer group per the API.

If business effects have committed but the offset has not yet been committed, the record may be redelivered/reprocessed. If the offset is committed before business effects are guaranteed to succeed, the record risks being skipped after a crash. That is why **idempotency** is often critical.

In Spring Kafka, calling `Acknowledgment.acknowledge()` with manual acknowledgment mode asks the container to handle ACK/commit per configuration. It does not always prove that a **synchronous broker commit completed at that exact line**; it depends on ack mode, error handler, when the container commits, and related options.

Kafka provides transactional mechanisms and exactly-once semantics for suitable Kafka-to-Kafka flows, but **do not conclude that side effects in an external database or HTTP API are exactly-once** merely because a Kafka transaction exists. Design explicit transaction boundaries.

### 9.2. RabbitMQ (AMQP)

With RabbitMQ manual acknowledgments:

- `basicAck(deliveryTag, false)`: the client sends an ACK request for a delivery tag on that channel.
- `basicNack(deliveryTag, false, true)`: sends a NACK with **requeue**, which can immediately redeliver and create a loop.
- `basicNack(deliveryTag, false, false)` or `basicReject(..., false)`: rejects without requeue; the message may be dead-lettered **if the queue/broker is properly configured with DLX/DLQ**, otherwise it may be dropped.
- `deliveryTag` **is only meaningful within the scope of a channel**, not as a system-wide logical message ID.

Do not describe a normal return from `basicAck` as a **publisher confirm** or a durable per-event acknowledgment from the broker. Understand channels, prefetch, acknowledgment modes, and connection failure handling.

With async processing, be careful about thread/channel ownership, ACK ordering, and especially `multiple=true`, which can affect multiple delivery tags rather than just the message currently observed.

### 9.3. JMS

JMS has its own session/acknowledgment and transaction models. For example, `CLIENT_ACKNOWLEDGE` in many situations acknowledges **messages consumed on the session** when acknowledge is called, not necessarily just the single current message. Transacted sessions have their own commit/rollback semantics; providers may set `JMSRedelivered` or `JMSXDeliveryCount` if supported.

Therefore, fields like `acknowledged=true` or `attempt` must align with the actual **provider, API, and session mode**. Do not copy an audit pattern from Kafka to JMS while ignoring these differences.

## 10. Spring Kafka Integration Example: Log Outcome Then ACK

This example is for an **already configured Spring Boot / Spring Kafka** project. It is not a standalone program to run with `javac`: it requires dependencies, a broker, a listener container, serializers/deserializers, and a business service.

```java
package com.example.messaging;

import java.util.concurrent.TimeUnit;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

@Component
public class OrderMessageConsumer {
    private static final Logger LOG =
            LoggerFactory.getLogger(OrderMessageConsumer.class);

    private final OrderHandler handler;

    public OrderMessageConsumer(OrderHandler handler) {
        this.handler = handler;
    }

    @KafkaListener(topics = "orders", groupId = "billing-workers")
    public void consume(ConsumerRecord<String, String> record,
                        Acknowledgment ack) {
        long startedAt = System.nanoTime();

        try {
            // Handler must guarantee idempotency and commit per contract.
            handler.processIdempotently(record.key(), record.value());
        } catch (RuntimeException failure) {
            LOG.warn(
                "event=consumer.processing_failed topic={} partition={} "
              + "offset={} errorType={}",
                record.topic(), record.partition(), record.offset(),
                failure.getClass().getSimpleName());
            throw failure; // Let the configured error handler/retry policy handle it.
        }

        long durationMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - startedAt);

        LOG.info("event=consumer.processing_succeeded topic={} "
                + "partition={} offset={} durationMs={}",
                record.topic(), record.partition(), record.offset(),
                durationMs);

        ack.acknowledge(); // Request ACK per container configuration.
        LOG.debug("event=consumer.ack_requested topic={} partition={} "
                + "offset={}",
                record.topic(), record.partition(), record.offset());
    }

    public interface OrderHandler {
        void processIdempotently(String key, String value);
    }
}
```

Design explanation:

1. `record.topic()`, `partition()`, and `offset()` identify the Kafka record's position; do not log the full payload or raw key if they contain PII.
2. `handler.processIdempotently(...)` is a **contract delegated to business logic**; the interface does not implement idempotency by itself. An implementation with a unique key, transaction, or equivalent mechanism is required.
3. Only after the handler returns normally does the consumer log processing success and call `ack.acknowledge()`. If the handler throws `RuntimeException`, the code logs the failure and **rethrows**, allowing the configured Spring Kafka error handler to process it.
4. **Manual acknowledgment mode** must be configured (e.g., `MANUAL` or `MANUAL_IMMEDIATE` depending on version and requirements) and aligned with the retry/error handler. If the container uses auto ACK, this code contract is incorrect.
5. Logging `ack_requested` does not claim that the offset has committed successfully. To log `commit_succeeded`, obtain the commit result/callback from the appropriate API/configuration.
6. `LOG.warn` avoids printing the full `record.value()`, exception message, or headers, because they may contain sensitive data.
7. When a listener processes batches or uses concurrency/rebalancing, offset commit ordering is more complex than a single-record ACK; test the actual behavior.

**This is an integration pattern**, with no fixed output and no built-in broker or error handler implementation. If processing participates in a transaction where commit happens after the method returns, the `processing_succeeded` line is only accurate if the handler contract proves the transaction has committed at return time. Adjust event placement to match the actual transaction lifecycle.

### 10.1. Emitting an Event with a Correlation ID

If a message carries a validated business `eventId` and `correlationId` in headers, you can log them alongside Kafka coordinates. However:

- Do not trust any arbitrary ID header as an authenticated identity.
- Headers may be missing, duplicated, or contain undecodable bytes; define clear fallbacks.
- Do not log raw unbounded `traceparent`/baggage; validate format and size.
- For batch consumers, each record needs its own message ID; a batch ID only identifies the poll batch and does not replace event IDs.

## 11. MDC and Trace Context in Consumers

Web app logging typically has a request ID set by HTTP middleware. **Message consumers do not automatically have an HTTP request context.** When processing a message, you can restore correlation/trace context from headers per policy, then bind it to MDC for logs on the same thread.

Integration snippet with SLF4J:

```java
import org.slf4j.MDC;

// Inside the method processing a single message:
// validatedCorrelationId has already been checked for length and characters.
String previous = MDC.get("correlationId");
try {
    if (validatedCorrelationId == null) {
        MDC.remove("correlationId");
    } else {
        MDC.put("correlationId", validatedCorrelationId);
    }

    processMessage();
} finally {
    if (previous == null) {
        MDC.remove("correlationId");
    } else {
        MDC.put("correlationId", previous);
    }
}
```

This is **not a standalone class**; it assumes `processMessage()` and the corresponding variable already exist. Preserving the previous value avoids corrupting the MDC of a nested scope.

Key points:

- `MDC` is typically thread-bound; thread pools **reuse threads**, so context must be restored/cleared in `finally`.
- When using `CompletableFuture`, Reactor/WebFlux, or another executor, context does not automatically propagate across threads; use the framework's proper context propagation mechanism.
- If messages are processed in parallel, do not use a shared static mutable `correlationId` across all listeners.
- Do not let unvalidated headers decide file/topic routing or become high-cardinality metric labels.
- Trace context such as W3C `traceparent` links spans between producer and consumer when propagated properly; **a trace ID does not replace a message ID** and does not prove business success.

## 12. Idempotency: Why Logging "duplicate" Is Not Enough

Many messaging systems provide **at-least-once delivery**: the broker may deliver the same message again if the consumer crashes or ACK/commit has not succeeded. In that case:

```text
receive m-1
 -> update database succeeds
 -> JVM crashes before ACK
 -> broker redelivers m-1
 -> update database may be repeated
```

If the consumer only logs `Duplicate skipped` based on an in-memory `HashSet`, after a restart that set is empty and the message will run again. In production, you can use:

- **Unique constraints** on `eventId`/idempotency key in the database.
- A **processed-message table** updated in the same transaction as business state.
- **Upsert/idempotent operations** when business logic permits.
- **Inbox/outbox** patterns with durable storage, retries, and reconciliation.
- **Optimistic concurrency/version checks** when multiple events target the same entity.

Model example (pseudo-SQL, not tied to a specific dialect):

```sql
BEGIN TRANSACTION;
-- Insert an idempotency key with a unique constraint.
-- If the key already exists: check status and skip per policy.
INSERT INTO processed_message(message_id) VALUES ('evt-2041');
-- Perform business state changes in the same transaction.
UPDATE account_balance SET ... WHERE ...;
COMMIT;
```

This is a **sketch**, not runnable SQL: `UPDATE ...` intentionally represents only the business step, so do not use this snippet as an executable script. The core point is that **marking as processed and applying side effects must be consistent**, rather than inserting a `processed` record outside the transaction.

When `consumer.duplicate_detected` appears, the log should clarify the decision:

- Has the duplicate record been verified as **the same event already processed successfully**?
- Or is a previous attempt still `PROCESSING` and in need of retry?
- Is there a conflict with the same ID but a different payload/version?
- Did the consumer **ACK the skip request**, or does processing need to continue?

**Do not assume every duplicate ID is safe to skip**, especially if the first attempt did not commit business state or an intermediate state was not handled properly.

## 13. Loggers, Filters, and Sinks Can Also Lose Consumer Logs

Calling `logger.info(...)` does not guarantee the event reaches storage. A logging pipeline may pass through:

```text
Consumer code
   -> logger level/filter
   -> encoder/formatter
   -> AsyncAppender / queue (optional)
   -> console/file/network
   -> collector
   -> storage / retention
```

Cases to distinguish:

- DEBUG disabled: a `received` event is not created/written per policy.
- Handler/appender filter drops an event even when the logger allows it.
- Logging queue full: the framework may block or drop depending on configuration.
- File/collector failure: records never reach the destination.
- JVM crash: events sitting only in an in-memory queue may be lost.
- Log shipping retry: duplicate records may appear at the collector.
- Logger reconfigured at runtime: log volume and types fluctuate.

If a message represents a transaction requiring mandatory auditing, **do not replace a durable audit trail with asynchronous diagnostic logs**. You may need database/outbox records and an independent storage path per business constraints.

## 14. Security and Privacy in Consumer Logs

Message payloads can contain more sensitive data than HTTP request headers: orders, payment data, customer profiles, JWTs, secrets, API keys, or credentials.

Practical principles:

1. **Do not log raw payloads at INFO/WARN/ERROR** merely because the consumer failed. Use `messageId`, `messageType`, version, and a sanitized error code.
2. If a deserialization error prevents parsing the payload, log broker coordinates and the parser error as an **errorCode/exception class**, without dumping full raw bytes.
3. **Do not log credentials, tokens, passwords**, connection strings, or unnecessary identifying information into messages/logs.
4. Correlation headers, routing keys, or exception messages may contain untrusted input; prevent **log injection** from CR/LF, escape sequences, and oversized payloads.
5. Use a structured encoder/JSON escaping, field allowlists, and size limits before passing data to the logger/queue.
6. Do not use message ID, correlation ID, or user ID as a **metric label**; high cardinality can overload the metrics system.
7. If payload inspection is needed for investigation, use a separate access-controlled retrieval channel with masking, short retention, and access auditing.
8. Protect read permissions on files/topics/collectors; logs can expose cash flows, business state, and sensitive identifiers.
9. For mandatory audit events, ensure integrity, durability, retention, and reconcilability according to your threat model.
10. Do not assume a hashed value is automatically safe: low-entropy data can be reversed via dictionary attacks.

`Throwable.getMessage()` can also contain raw data from the message. Log the exception class and error code first; only log stack traces in an appropriate diagnostic channel when needed.

## 15. Performance: Do Not Flood Your Own Logging System

In a high-throughput message consumer, logging on every delivery can generate an event volume equal to or exceeding the message input. If each message writes four INFO logs, processing 10,000 messages/second already produces 40,000 log events/second, **not counting retries and exception stack traces**.

Choose logging points by purpose:

- **DEBUG:** received/start with minimal metadata when investigation is needed.
- **INFO or metric:** processing succeeded with sampling/aggregation if not a mandatory audit event.
- **WARN/ERROR:** retry budget exceeded, DLQ, stalled worker, commit failures, severe downstream errors.
- **Metrics:** received/succeeded/failed/retried/dead-lettered counts, duration, consumer lag.
- **Tracing:** a span for processing, linking producer/consumer via trace context.

You usually do not need `if (log.isDebugEnabled())` for every literal or placeholder with already-computed variables. However, when constructing expensive details like a JSON payload, stack trace string, or header list:

```java
// Integration snippet: serializeDebugInfo(...) may be CPU-intensive.
if (log.isDebugEnabled()) {
    log.debug("consumer.debug messageId={} details={}",
            messageId, serializeDebugInfo(message));
}
```

Using placeholders does not make `serializeDebugInfo(message)` lazy. Only compute expensive data when the level is enabled or use a compatible Supplier API.

Do not measure "received count" by counting INFO logs if log levels can change or sampling is enabled. Use independently instrumented counters for operational metrics.

## 16. Metrics, Tracing, and Alerts for Message Consumers

Recommended metrics (**not default in every framework**):

| Metric | Meaning | Notes |
| --- | --- | --- |
| `consumer_deliveries_total{topic,group}` | Number of broker deliveries / consumer receipts | Includes redeliveries |
| `consumer_processed_total{outcome,type}` | Processing count by outcome | Clearly define "processed" |
| `consumer_retries_total{reason,type}` | Number of retry decisions/executions | Distinguish scheduled from delivered |
| `consumer_dead_letters_total{reason,type}` | Messages moved to DLQ per confirmation milestone | Do not infer from call count |
| `consumer_processing_duration_seconds` | Handler latency histogram | Measures business duration accurately |
| `consumer_ack_failures_total` | ACK/commit failures per API | Only when framework provides observable results |
| `consumer_lag` | Consumer backlog | Definition depends on Kafka/queue |
| `consumer_oldest_message_age_seconds` | Age of waiting messages | Depends on broker/clock |
| `consumer_inflight_messages` | Number of events currently being processed | Distinguish from queue backlog |

Labels such as `topic`, `group`, `messageType`, and `errorCode` should belong to a **bounded set**. Do not put `messageId`, `traceId`, `correlationId`, raw payloads, or exception messages into metric labels.

Useful alerts:

- Sustained increase in consumer lag.
- Successful processing throughput drops while received count remains high.
- Abnormal spike in retry rate and DLQ rate.
- Many messages failing repeatedly with the same `errorCode`.
- Commit/ACK errors or repeated consumer rebalances.
- Rising p95/p99 processing duration.
- Worker dead (no longer polling/acking) while broker backlog continues to grow.
- DLQ growing without a recovery/triage procedure.

**Logs, metrics, and tracing do not replace one another.** Logs help analyze a specific event; metrics detect trends and anomalies; tracing connects distributed hops.

## 17. Testing Consumer Logging with Concrete Scenarios

| Scenario | Expected Log and Business Behavior |
| --- | --- |
| Single valid message | Success outcome; ACK/commit per policy |
| Invalid message | Error classified; not marked as succeeded |
| Transient failure | Attempt logged and retry decision with appropriate backoff |
| Permanent failure | Moved to quarantine/DLQ per policy, no infinite retry |
| Two deliveries with same business event ID | Side effects not duplicated; logs can explain the duplicate |
| Crash after business commit, before ACK | Redelivery may occur; idempotency preserves correct result |
| Offset commit succeeds before side effect | Test proves this is a risky order to avoid |
| DLQ publish fails | Do not ACK original as completed without appropriate guarantees |
| Missing correlation header | Fallback applied, no NPE |
| Header contains newline/control chars | Cannot forge log lines or break structured JSON |
| Payload contains tokens, PII | Not emitted to logs/stack traces against policy |
| Parallel consumer execution | MDC does not mix IDs between messages |
| Rebalance / shutdown | Incomplete/inflight/commit observed per API |
| Full logging queue | Does not trigger a log storm that stalls the system |
| Sink/collector failure | Metrics/alerts still reflect the incident |
| Redelivery after timeout | Not double-counted as multiple business successes |

For unit tests, route the logger through a **test appender** and assert exact `event/messageId/outcome/attempt` fields. For integration tests, spin up a test broker or appropriate container and intentionally trigger ACK failures, retries, and DLQ routing; verify database state, consumer offsets, and final audit records.

Do not just assert "one `processed` line appeared" and conclude exactly-once is guaranteed. Tests must verify **side effects and commit boundaries**.

## 18. Common Pitfalls

### 18.1. Logging "message success" Before Business Commit

If the transaction rolls back, the log falsely reports success. Place the event after the real commit boundary or use an outbox in the same transaction.

### 18.2. Calling ACK Before Processing

Some brokers may treat the message as consumed before business logic finishes, losing the ability to reprocess after a crash. Understand auto/manual ACK and choose an order safe for your business requirements.

### 18.3. Equating `acknowledge()` with Broker Persistence Confirmation

The acknowledgment API may only send a command or mark an offset, not provide a final receipt. Log `ack_requested` unless you actually have a callback/confirmation.

### 18.4. Using messageId from the Payload Without Validation

The payload may lack an ID, have duplicate IDs, contain control characters, or come from an untrusted sender. Validate/escape it and use safe broker coordinates as a fallback.

### 18.5. Logging the Full Payload on Deserialization Failure

This is precisely when the payload may contain malicious data or secrets. Log only metadata and an appropriate error code; keep raw payloads in a strictly access-controlled quarantine store if needed.

### 18.6. Treating Redelivery as a Consumer Bug

With at-least-once delivery, redelivery is expected when ACK/commit has not completed. What matters is **idempotency and the reason for redelivery**, not merely emitting WARN for every duplicate.

### 18.7. Counting Retries by Counting WARN Logs

WARN logs may be disabled, filtered, dropped, or sampled, and a single retry can emit multiple events. Use metrics and a clear `attempt`/`retryScheduled` schema.

### 18.8. Not Clearing MDC in a Thread Pool

A worker thread may be reused for the next message, causing the old message's correlation ID to stick. Always restore/clear MDC in `finally`.

### 18.9. Using the Same Logger Sink for Mandatory Audits and Noisy DEBUG

A shared queue/sink can drop or block critical audit events during a log storm. Separate pipelines based on durability and access-control requirements.

### 18.10. Assuming Every `dead_lettered` Event Is Durably Persisted

The DLQ destination may fail, publisher confirms may not have arrived, or the original ACK may fail. Base states on actual guarantees and implement reconciliation.

## 19. Implementation Checklist

- [ ] Define `received`, `processing_succeeded`, `ack_requested`, `retry`, and `dead_lettered` milestones and when they are emitted.
- [ ] Include logical message ID, source/topic/queue, consumer group, delivery/attempt, and correlation ID when available.
- [ ] Distinguish **business commit** from ACK/offset commit; log `succeeded` only after the real success condition.
- [ ] Implement durable idempotency for side effects that may be reprocessed.
- [ ] Classify retryable/permanent failures, retry budgets, backoff, and DLQ procedures.
- [ ] Do not ACK the original message prematurely before DLQ/retry/side effects have appropriate guarantees.
- [ ] Use structured logging, stable event codes, error codes, and input length limits.
- [ ] Never log raw payloads/tokens/PII/secrets and never put dynamic IDs into metric labels.
- [ ] Restore/clear MDC after each message; propagate trace context properly across async boundaries.
- [ ] Follow the **actual semantics of Kafka, RabbitMQ, or JMS**, without copying ACK semantics across brokers.
- [ ] Control log volume, async appender backpressure, sampling, and log storms.
- [ ] Track received/succeeded/failed/retried/DLQ, lag, processing duration, and ACK errors with independent metrics.
- [ ] Test redelivery, duplicates, rollbacks, crashes, DLQ failures, commit errors, rebalances, and shutdowns.
- [ ] If logs serve as mandatory audit evidence, design durability/retention/integrity separately from diagnostic logging.

**Conclusion:** Message consumer logging must explain **which message was received, how it was processed, on which attempt, and which confirmation boundary it reached**. Clearly recording `received`, `processing_succeeded`, `retry`, `dead_lettered`, and `ack_requested` makes investigation straightforward, but **does not replace idempotency, transactions, and broker guarantees**. To make logs trustworthy, emit events at the right moments, protect sensitive data, and verify the actual write path to the sink.
