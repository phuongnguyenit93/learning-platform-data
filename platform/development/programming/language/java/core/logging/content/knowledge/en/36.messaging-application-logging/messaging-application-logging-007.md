# Dead-Letter Messages in Java Messaging Applications

## 1. What is a dead-letter message?

In an application using a message broker, a **dead-letter message** is a message that cannot be processed successfully under the current policy and is **routed to a separate destination for handling** instead of looping indefinitely on the main flow. The destination is commonly called a **dead-letter queue (DLQ)** or **dead-letter topic (DLT)**, depending on the system.

For example, an application receives an `OrderConfirmed` event, but the message schema is missing a required field. Re-running the same data will not fix the schema on its own. If the consumer repeatedly receives it, logs an exception, and retries indefinitely, it will waste resources, spam the logs, and potentially delay valid messages behind it. Moving the failed message to a DLQ helps **isolate the problem** so that operators or a remediation workflow can handle it later.

~~~text
                Producer
                   |
                   v
           Main queue / topic
                   |
                   v
               Consumer
                   |
             Process message
                   |
        +----------+-----------+
        |                      |
     Success                 Failure
        |                      |
        v               Classify failure
   Ack / commit          /          \
                 Temporary            Permanent
                    |                    |
              Bounded retry              v
                    |                DLQ / DLT
           +--------+-------+             |
           |                |             v
        Success        Exhausted      Inspect / repair /
           |                |         approved replay
           v                v
      Ack / commit        DLQ / DLT
~~~

**A dead-letter message is not an error log line.** Logs describe what happened; a DLQ holds **the message object itself that needs investigation or reprocessing**. The two complement each other: the DLQ stores the data/message, while logging provides context, cause, attempt count, transfer status, and operational observability.

### Distinguishing the terms

| Term | Role |
| --- | --- |
| **Main message** | Data sent by a producer for a consumer to process business logic |
| **Retry / redelivery** | Re-attempting to process the same message after a failure |
| **Retry queue/topic** | A channel or mechanism that delays a message before the next attempt |
| **Dead-letter message** | A message classified to be removed from the main flow after failure |
| **DLQ/DLT** | A queue/topic that stores dead-letter messages |
| **Poison message** | A message that causes the consumer to keep failing in a way that cannot be resolved by retrying |
| **Parking lot/quarantine** | A longer-term holding area for manual investigation or special handling; may be separate from the DLQ |

Terminology and mechanisms depend on the broker or framework. Not every broker has a built-in DLQ concept with the exact same semantics; some systems use regular topics managed by the application or framework itself.

## 2. Why do messages end up in a dead-letter destination?

A message typically needs to be moved to a DLQ when:

1. **Invalid payload:** missing required fields, malformed format, or unsupported schema version.
2. **Permanent business rule rejection:** an action type is disallowed or a business state cannot be resolved by retrying. Consider whether this is an expected error that should terminate cleanly, or a genuine failure that belongs in a DLQ.
3. **Deserialization failure:** incompatible JSON/Avro/Protobuf or message envelope.
4. **Retries exhausted:** a transient error persists beyond the retry budget.
5. **Delivery limits exceeded:** some brokers support dead-lettering when a message is rejected, its TTL expires, the queue overflows, or the delivery limit is exceeded, depending on configuration.
6. **Unrecoverable consumer processing error:** for example, a legacy message that cannot be mapped to a new domain model.

It is important to **classify the root cause** before deciding to retry or dead-letter.

| Error category | Examples | Common handling approach |
| --- | --- | --- |
| **Permanent / non-retryable** | Invalid schema, missing required data | Send to DLQ early, with a stable reason code |
| **Transient / retryable** | Network timeout, downstream service temporarily unavailable | Retry with backoff, jitter, and a cap |
| **Unknown / unexpected** | Unclassified new bug | Bounded retry or quarantine per policy; alert |
| **Controlled business rejection** | Validly rejected command, not a technical failure | Record business outcome instead of treating as poison |
| **Infrastructure delivery failure** | Failed to publish to DLQ or failed to confirm ack | Do not silently drop the message; trigger delivery-failure handling |

You should not send every exception straight to the DLQ: a transient timeout may resolve within a few seconds. Conversely, you should not infinitely retry a message with an invalid schema, as that only slows down the system.

## 3. Lifecycle of a dead-letter message

A typical workflow looks like this:

1. The consumer receives the message, preserving its **ID**, source, approved headers, tracing information, and delivery context.
2. The consumer attempts processing; if successful, it acknowledges completion according to the broker's mechanism.
3. If an error occurs, classify it as **retryable** or **non-retryable**, and record a standardized logging event.
4. For transient errors, use bounded retries with a delay policy; avoid creating a hot loop.
5. For permanent errors or exhausted retries, route the message to the DLQ/DLT, preserving the data needed for investigation or replay.
6. Acknowledge the original message as complete **only after the DLQ transfer has been confirmed according to the system's contract**; or rely on a reliable automatic dead-lettering mechanism provided by the broker.
7. Monitoring systems raise alerts when the DLQ grows, messages sit unaddressed for too long, or a specific error type spikes.
8. Authorized operators investigate the root cause, fix the issue, and then replay or retire the message according to procedure.

**There is no guarantee that "publish to DLQ then ack source" is atomic across all brokers.** If the two actions happen separately, a failure window can exist; the design must account for the broker, transaction/ack semantics, and business requirements.

## 4. How does a DLQ relate to logging?

The DLQ manages quarantined messages; logging explains **why, when, where, and under what policy** a message was moved. Logs need sufficient metadata while avoiding logging the raw payload if it contains personal data or secrets.

For example, a good log event:

~~~text
event=message_dead_lettered
messageId=msg-1042
source=orders.confirmed
destination=orders.confirmed.dlq
consumer=shipping-worker
attempt=3
reasonCode=SCHEMA_INVALID
traceId=trace-demo-001
outcome=DLQ_PUBLISH_CONFIRMED
~~~

This is only an **illustrative schema example**, not the output of the Java program in the next section. In practice, message IDs, trace IDs, destinations, and consumer names can also leak internal information; classify them according to your policy.

Consider including the following fields:

| Field | Purpose |
| --- | --- |
| `event` | Distinguishes `message_retry_scheduled`, `message_dead_lettered`, `message_replayed` |
| `messageId` / `eventId` | Correlates attempts and supports deduplication |
| `source` | Original queue/topic/subscription |
| `destination` | DLQ/DLT or retry channel |
| `consumer` / `service` | Processing component |
| `attempt` | Attempt number according to a **clearly defined policy** |
| `reasonCode` | Stable error code for aggregation and alerting |
| `exceptionType` | Controlled error type; logging the raw exception message is not required |
| `traceId` / `correlationId` | Links back to the originating request or job |
| `outcome` | Distinguishes an attempted DLQ publish from a confirmed publish |
| `occurredAt` | Event timestamp, ideally in UTC when emitting JSON |
| `retryPolicyVersion` | Helpful when retry configuration changes over time |

**In particular:** logging `DLQ_PUBLISH_ATTEMPTED` does not mean the DLQ has persisted the message. Only report `DLQ_PUBLISH_CONFIRMED` when you have a confirmation signal appropriate to the broker and durability policy; some libraries do not provide this guarantee by default.

Do not put raw message bodies, credentials, tokens, cookies, payment details, or exceptions containing sensitive payloads into logs. If content inspection is needed, keep the message in a **protected DLQ channel** with role-based access rather than copying it into multiple logging systems.

## 5. Standalone Java 17 example: bounded retry then DLQ

The program below simulates an **in-memory consumer, retry queue, and DLQ**, requiring no external broker or dependencies beyond the JDK. The goal is to understand state transitions and logging, not to demonstrate real-world delivery guarantees.

Four mock messages:

- `m-1`, kind `OK`: succeeds immediately.
- `m-2`, kind `FLAKY`: fails temporarily on the first two attempts, succeeds on the third.
- `m-3`, kind `INVALID`: invalid schema, sent to the DLQ immediately.
- `m-4`, kind `UNAVAILABLE`: fails temporarily every time, sent to the DLQ after three attempts.

The `kind` values are purely demo control labels, **not real payloads**, so the logs do not print sensitive information.

Create the file **`DeadLetterMessageDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.Queue;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class DeadLetterMessageDemo {
    private static final int MAX_ATTEMPTS = 3;

    record Message(String id, String kind) {}
    record Delivery(Message message, int attempt) {}
    record DeadLetter(Message original, String reasonCode, int attempts) {}

    static class InvalidMessage extends RuntimeException {}
    static class TemporaryFailure extends RuntimeException {}

    private static void process(Delivery delivery) {
        String kind = delivery.message().kind();
        switch (kind) {
            case "OK" -> { }
            case "FLAKY" -> {
                if (delivery.attempt() < 3) {
                    throw new TemporaryFailure();
                }
            }
            case "UNAVAILABLE" -> throw new TemporaryFailure();
            default -> throw new InvalidMessage();
        }
    }

    private static Logger newDemoLogger() {
        Logger logger = Logger.getLogger("demo.message.deadletter");
        logger.setLevel(Level.INFO);
        logger.setUseParentHandlers(false);

        Handler handler = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.print(getFormatter().format(record));
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
        handler.setLevel(Level.INFO);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + ": "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        logger.addHandler(handler);
        return logger;
    }

    public static void main(String[] args) {
        Queue<Delivery> deliveries = new ArrayDeque<>();
        deliveries.add(new Delivery(new Message("m-1", "OK"), 1));
        deliveries.add(new Delivery(new Message("m-2", "FLAKY"), 1));
        deliveries.add(new Delivery(new Message("m-3", "INVALID"), 1));
        deliveries.add(new Delivery(new Message("m-4", "UNAVAILABLE"), 1));

        List<DeadLetter> dlq = new ArrayList<>();
        Logger logger = newDemoLogger();
        int acknowledged = 0;

        try {
            while (!deliveries.isEmpty()) {
                Delivery delivery = deliveries.remove();
                Message message = delivery.message();
                try {
                    process(delivery);
                    acknowledged++;
                    logger.info("ACK id=" + message.id()
                            + " attempt=" + delivery.attempt());
                } catch (InvalidMessage ex) {
                    dlq.add(new DeadLetter(
                            message, "SCHEMA_INVALID", delivery.attempt()));
                    logger.warning("DLQ id=" + message.id()
                            + " reason=SCHEMA_INVALID attempts="
                            + delivery.attempt());
                } catch (TemporaryFailure ex) {
                    if (delivery.attempt() < MAX_ATTEMPTS) {
                        int next = delivery.attempt() + 1;
                        deliveries.add(new Delivery(message, next));
                        logger.info("RETRY id=" + message.id()
                                + " nextAttempt=" + next);
                    } else {
                        dlq.add(new DeadLetter(
                                message, "RETRY_EXHAUSTED",
                                delivery.attempt()));
                        logger.warning("DLQ id=" + message.id()
                                + " reason=RETRY_EXHAUSTED attempts="
                                + delivery.attempt());
                    }
                }
            }
            logger.info("SUMMARY acknowledged=" + acknowledged
                    + " deadLetters=" + dlq.size());
        } finally {
            for (Handler handler : logger.getHandlers()) {
                logger.removeHandler(handler);
                handler.close();
            }
        }
    }
}
~~~

Compile and run with **JDK 17 or later**:

~~~bash
javac DeadLetterMessageDemo.java
java DeadLetterMessageDemo
~~~

**Exact stdout in this single-threaded demo:**

~~~text
INFO: ACK id=m-1 attempt=1
INFO: RETRY id=m-2 nextAttempt=2
WARNING: DLQ id=m-3 reason=SCHEMA_INVALID attempts=1
INFO: RETRY id=m-4 nextAttempt=2
INFO: RETRY id=m-2 nextAttempt=3
INFO: RETRY id=m-4 nextAttempt=3
INFO: ACK id=m-2 attempt=3
WARNING: DLQ id=m-4 reason=RETRY_EXHAUSTED attempts=3
INFO: SUMMARY acknowledged=2 deadLetters=2
~~~

**Stderr:** none on a successful run because the custom JUL `Handler` explicitly prints to `System.out`; JUL's standard `ConsoleHandler` normally uses stderr.

### Explaining the output

- `m-1` is processed successfully right away and logs `ACK`.
- `m-2` is re-queued for attempts 2 and 3; on attempt 3 it succeeds, so it **does not go to the DLQ**.
- `m-3` is invalid, so it **goes to the DLQ on attempt 1**, without pointless retries.
- `m-4` always fails temporarily; once its 3-attempt budget is exhausted, it **goes to the DLQ** with `RETRY_EXHAUSTED`.
- `acknowledged=2`, `deadLetters=2` count simulated messages, not delivery attempts. The total number of processing invocations is higher than the original message count due to retries.

`DeadLetter` **retains the `Message original` object in the DLQ list**; the logger only records the ID and reason code. In a real system, the DLQ must retain enough data for investigation or policy-based replay, while sensitive fields must still be protected. `MAX_ATTEMPTS=3` is defined as **three total processing attempts**, including the initial attempt, not three retries after the first attempt.

**Important limitations:** the queue in this demo lives in RAM; a process crash loses all data. Retries are placed immediately at the back of the queue, **with no delay, backoff, ack, transaction, or broker confirms**. The simulated processing order does not represent Kafka partitions, RabbitMQ, JMS, or SQS. Therefore, use this code only to learn failure classification and logging—do not use it as-is for production deployment.

## 6. How does retry differ from dead-lettering?

**Retry** expects that the underlying cause of failure may resolve; **dead-lettering** isolates a message when the automated pipeline no longer wants to process it on the main flow.

| Aspect | Retry | Dead-letter |
| --- | --- | --- |
| Goal | Try again to complete processing | Hold the failed message for repair, investigation, or discard decision |
| State | Still within the automated processing path | Separated from the main processing path |
| Suitable for | Timeouts, temporary dependency outages | Invalid schema, permanent errors, retry limit exceeded |
| Limits | Attempt count, message age, total duration | Storage capacity, retention, access permissions, backlog |
| Observability | `message_retry_scheduled`, attempt, delay | `message_dead_lettered`, reason, original destination |
| Risks | Retry storms, duplicate side effects, blocking the flow | DLQ overflow, forgotten messages, replay causing repeated failures |

A common retry policy is **exponential backoff with jitter**; for example, waiting roughly 1 second, 2 seconds, 4 seconds up to a maximum cap. You should cap the total number of attempts, wait time, and load budget placed on dependencies. For ordered or partitioned consumers, delaying a message can affect subsequent messages; you cannot assume every broker allows pulling a message out and re-emitting it without altering ordering.

**Retries are not free:** the same message might have already written to the database successfully before the consumer lost its connection prior to acking. The next delivery could produce duplicate side effects. Therefore, **idempotency** must be considered even before a message ever reaches the DLQ.

### Avoiding infinite retries and hot loops

An anti-pattern:

~~~text
consume -> exception -> nack(requeue=true)
             ^               |
             +---------------+
~~~

If a message can never succeed, this loop can generate thousands of deliveries and exceptions, saturating the consumer and flooding logs. You must use appropriate retry delays, attempt thresholds, permanent error classification, and a dead-letter/parking-lot mechanism.

## 7. Ack rules when sending to a DLQ

In messaging systems with explicit **acknowledgment**, a common design rule is:

**Do not treat the original message as completed until the DLQ publish has been confirmed at the required reliability level.**

~~~text
Consumer receives original message
           |
    Decide dead-letter
           |
    Publish to DLQ
           |
       Confirmed?
       /        \
     No         Yes
      |          |
 Retry/preserve  Ack original
 without drop       |
                  Done
~~~

If the application **acks the original first and then publishes to the DLQ**: the process may crash after the ack but before the publish, losing the message.

If it **publishes to the DLQ first and then acks the original**: the process may crash after a successful publish but before the ack, causing the original message to be redelivered and creating a duplicate in the DLQ. This is why **stable IDs, deduplication, and idempotency** are necessary—rather than claiming "publishing to a DLQ is exactly-once."

Some brokers provide built-in dead-lettering when a consumer rejects or nacks a message in a supported way. That mechanism differs from an application manually publishing to a DLQ and then acking the original; **delivery guarantees, publisher confirm/transaction handling, and the risk of message loss or duplication depend on the broker, queue type, version, and configuration**. Always read the documentation for your specific setup and test real failure scenarios.

### If publishing to the DLQ fails

- Log a DLQ-transfer failure event with **message ID, destination, error code, and unconfirmed outcome**; avoid logging the raw body.
- Do not silently drop the original message.
- Apply a retry or hold the message in a suitable durable store; avoid hot-loop retries that add pressure to the system.
- Alert operations if the DLQ or dead-letter path is unavailable.
- Verify that the broker's default dead-letter configuration does not accidentally create a loop between queues/topics.

If the broker does not support a unified transaction spanning business state changes, publishing, and acking, you may need a **transactional outbox/inbox**, event IDs, and an idempotent consumer, depending on reliability requirements.

## 8. Messaging ecosystems and how they view DLQ/DLT

### RabbitMQ / AMQP

RabbitMQ provides a **dead-letter exchange (DLX)** mechanism. Depending on queue configuration and policies, a message can be dead-lettered when rejected/nacked with `requeue=false`, when its TTL expires, when the queue exceeds its length limit, or when the delivery limit is exceeded on supported queue types. Messages can be routed from the DLX to a dead-letter storage queue by routing key.

Key points to understand:

- `basicReject`/`basicNack` with `requeue=true` is **not equivalent** to sending to a DLQ; it requests redelivery.
- A DLX is an **exchange**, not a queue itself; proper bindings and routing are required for messages to reach the intended DLQ.
- Dead-letter policies, retention, queue limits, and delivery safety must be verified. There can be conditions where a routed message fails to land as configured; do not assume dead-lettering is unconditionally safe.
- Historical headers such as broker dead-letter metadata should only be interpreted according to the exact semantics of the running broker version; avoid inferring business processing attempt counts from a field not defined for that purpose.

### Apache Kafka

Kafka uses **topics**. In many systems, a DLT is a **design pattern implemented by the consumer or framework**, not a built-in topic type that automatically receives failed records. A consumer can publish a failed record to a separate topic and then handle the original record's offset according to the application contract.

Important distinctions:

- **Committing an offset** for a partition marks consumption progress, rather than acting as an independent per-message `ack` as in some queue brokers.
- A failing record can affect the ordering of subsequent records in the same partition; skipping, retrying, or sending to a DLT changes ordering behavior.
- Publishing to a DLT and then committing the offset has similar failure windows; stronger guarantees require examining Kafka transactions, idempotent producers, consumer-group semantics, and the boundaries of external side effects.
- Frameworks like Spring for Apache Kafka may provide error handlers and DLT publishers, but retry topics, backoff, recoverers, and offset commits depend on specific configuration.

### JMS and other brokers

In JMS, redelivery, acknowledgment, and DLQ behavior depend on the **JMS provider**. There is no universal queue name or dead-letter policy across all implementations. Brokers may use a redelivery limit, error destination, or dead-letter queue depending on the product.

In managed queue services, a DLQ is often paired with a **redrive policy** or maximum receive count. You should check retention rules, visibility timeouts, max receive counts, and replay permissions. Those concepts cannot be mapped directly onto Kafka or JMS without consulting the specific product's contract.

**Conclusion:** choose your retry/ack algorithm and dead-letter mechanism based on **the actual broker in use**, rather than merely renaming methods from one backend to another.

## 9. Metadata to keep in a dead-letter record

A well-structured dead-letter record typically needs **the original message or enough data to reprocess it** along with traceability metadata. A conceptual example:

~~~json
{
  "messageId": "msg-1042",
  "originalDestination": "orders.confirmed",
  "originalKey": "order-42",
  "deadLetterReason": "SCHEMA_INVALID",
  "attempts": 1,
  "consumer": "shipping-worker",
  "firstSeenAt": "2026-01-15T10:00:00Z",
  "deadLetteredAt": "2026-01-15T10:00:03Z",
  "traceId": "trace-demo-001",
  "schemaVersion": 2,
  "payloadRef": "protected-store-ref-123"
}
~~~

This is a **metadata example**, not a universal JSON format shared across brokers. In practice, the message body may reside directly in the DLT or be referenced in a secure store. If the payload failed serialization, recovering the original data requires a dedicated plan; you should not reconstruct a message solely from an error string.

Decisions to make:

- **Stable message ID:** preserve the original ID during transfer and replay; you can add a separate `deliveryId`/`replayId` to distinguish deliveries.
- **Origin:** topic/queue, partition/offset, or routing key where applicable.
- **Classified error:** `reasonCode`, exception type; avoid embedding full stack traces and bodies in headers.
- **Processing count:** clearly define whether the first attempt is 1 or 0 and who increments the counter; a broker's redelivery flag does not necessarily equal the total number of handler invocations.
- **Timestamps:** first seen, last retry, and dead-lettered time; use standardized timestamps.
- **Tracing:** trace/correlation IDs per policy; never log authentication tokens.
- **Versions:** schema, application release, and retry policy so you know which version failed on the message.

**Security:** a DLQ can contain PII, customer documents, or payment data. Restrict access to authorized personnel; enforce retention, encryption, and audit logging for read/replay actions. Copying raw messages into alert logs or support tickets can create uncontrolled duplicates.

## 10. Observing the DLQ in logging and monitoring

Do not track only `ERROR` logs or exception counts; track the **message lifecycle**.

| Signal | Operational meaning |
| --- | --- |
| `message_processing_failed` | An attempt failed; retries may still remain |
| `message_retry_scheduled` | A retry has been scheduled/handed off to the retry mechanism |
| `message_dead_lettered` | Message moved to DLQ per policy; distinguish attempted vs. confirmed |
| `message_replay_requested` | Who or what mechanism requested a replay |
| `message_replay_completed` | Replay finished with a confirmed outcome |
| `dlq_depth` / backlog | Number of messages currently queued in the DLQ |
| `dlq_oldest_age` | Age of the oldest unprocessed message |
| `retry_attempts_total` | Retry rate, helping detect a failing dependency |
| `dead_letter_rate` | Rate of messages entering the DLQ by source and reason code |
| `dlq_publish_failures` | The quarantine path itself is experiencing issues |

**Metrics do not replace logs:** metrics measure trends, logs trace individual messages, and the DLQ holds the messages that need action. Link them via `messageId`, `traceId`, `reasonCode`, and destination, but avoid using per-message IDs as **metric labels** due to excessive cardinality.

For example, a useful alert is not simply "DLQ count > 0": a known test message might sit in the DLQ intentionally. Distinguish anomalies by rate, backlog age, error category, severity, and DLQ publish failures.

### Structured logs and sensitive information

An example event:

~~~text
event=message_retry_scheduled messageId=m-4
attempt=2 nextAttempt=3 reasonCode=DEPENDENCY_TIMEOUT
delayMs=2000 consumer=shipping-worker
~~~

This is an example of a delayed retry policy, **not the output of the Section 5 demo**, where retries happen immediately in RAM. Do not log message contents or `exception.getMessage()` if they might contain customer data. Use only stable enums/reason codes and vetted fields.

## 11. Replay: controlled reprocessing of DLQ messages

A DLQ is not a "fire-and-forget" bin. Once code, schemas, or dependent data are fixed, you may need to replay messages. However, dumping every message from the DLQ back into the original queue at once can trigger repeated failures.

A good replay process:

1. **Triage by reason code:** identify which failures have been fixed and which still cannot be processed.
2. **Reconcile business state:** did the action partially succeed earlier? Would retrying create duplicate records, payments, or notifications?
3. **Evaluate schema/version:** can the current consumer read old payloads, or is migration required?
4. **Select scope:** filter by message ID, time range, reason, or tenant—do not replay everything indiscriminately.
5. **Dry-run or small-batch test** if the system supports safe verification; measure impact and backlog.
6. **Execute replay with rate limiting**, controlling load and new attempt budgets to avoid overwhelming the main flow.
7. **Record a replay audit event:** who requested it, when, from which DLQ, and the outcome; do not log unnecessary PII.
8. **Monitor post-replay:** track how many messages succeed and how many fall back into the DLQ; maintain traceability.
9. **Do not delete the DLQ record until processing is confirmed complete**, following the system's preservation and retention policies.

Avoid **infinite automated replay loops**: a message re-enters the DLQ because the root cause was not fixed, gets replayed again, and destabilizes the system. Unfixable messages may require long-term quarantine or a documented discard workflow with an audit trail.

**Ordering and idempotency:** a message replayed later may arrive after newer events for the same entity. The consumer must decide how to handle an older message relative to the current version/sequence/state; simply "re-running" is not always valid from a business standpoint.

## 12. Common pitfalls

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| Consumer logs exceptions continuously | Poison message is immediately requeued infinitely | Retry limits, backoff, permanent error classification |
| DLQ has no messages despite "DLQ" logs | Only intent was logged, never published or confirmed | Distinguish attempted vs. confirmed; check destination/bindings |
| Message lost after handler failure | Original acked/committed before DLQ persisted | Fix ordering or use an appropriate transaction/outbox design |
| Duplicate copies of a message in DLQ | DLQ publish succeeded but source ack failed, causing redelivery | Event ID, idempotent handoff, and deduplication |
| Retries take too long before DLQ | Attempt limit/TTL/backoff is too high | Retry budget aligned with SLA and error type |
| DLQ fills up or backlog grows indefinitely | No observability/repair/replay process | Depth/age metrics, ownership, retention, alerts |
| Replay fails again | Schema, data, or dependency has not been fixed | Triage root cause before replaying |
| Replay creates duplicate data | Consumer is not idempotent or side effects already occurred | Deduplicate by business key/event ID |
| Logs contain raw customer payloads | Logger prints body or raw exception | Metadata allowlist, secure DLQ, restricted logging |
| Ordering is altered | Retry topic/DLT moves messages out of original partition | Review ordering contract by broker and entity |
| Inconsistent attempt counts | Broker redelivery count differs from application policy | Define counting rules and log the source clearly |
| DLQ routes back to the main queue | Binding/routing policy creates a loop | Inspect DLX bindings, retry routes, and limits |

## 13. Dead-letter implementation checklist for Java applications

- [ ] Clearly classify transient, permanent, business rejection, and unknown errors.
- [ ] Define attempt budgets, backoff, jitter, timeouts, and retry stop conditions.
- [ ] Define DLQs/DLTs per source or error group, with clear naming and ownership.
- [ ] Ensure failed messages retain enough data for investigation and replay as required.
- [ ] Preserve message ID, trace ID, original source, and reason code; never embed secrets in logs.
- [ ] Distinguish publish attempted from confirmed, and do not ack the original too early.
- [ ] Evaluate duplicate delivery, idempotency, and ordering.
- [ ] Verify the specific broker's configuration instead of assuming all DLQs share the same semantics.
- [ ] Monitor DLQ depth, backlog age, dead-letter rate, publish failures, and replays.
- [ ] Establish a DLQ operating procedure: review, fix, selective replay, or policy-based retirement.
- [ ] Configure access control, encryption, retention, and access auditing for the DLQ, as payloads may be sensitive.
- [ ] Test poison messages, transient outages, consumer crashes, DLQ outages, duplicates/replays, and shutdowns.

### Self-check

**Q1.** If a message is missing a required field, will retrying it ten times reliably solve the problem?  
**A:** No. This is likely a permanent/schema error; it should be classified and dead-lettered early.

**Q2.** Does `logger.error("sent to DLQ")` prove that the message is stored in the DLQ?  
**A:** No. Logs must distinguish between an intended publish and a broker-confirmed publish.

**Q3.** If publishing to the DLQ succeeds but acking the original fails, what can happen?  
**A:** The original message may be redelivered, leading to duplicates; stable IDs and idempotency/deduplication are required.

**Q4.** Does Kafka have an automatic DLQ identical to the reject mechanism of every RabbitMQ queue?  
**A:** No. In Kafka, a DLT is typically a pattern implemented by the application or framework; offsets, transactions, and replays have their own semantics.

**Q5.** Should you paste a failed message's payload into Slack or a support ticket to make debugging easier?  
**A:** Not by default. Payloads may contain PII or secrets; use controlled-access channels and minimal metadata logging.

**Q6.** After fixing a bug, is it always safe to replay the entire DLQ immediately?  
**A:** No. It can cause duplicate side effects, break ordering, or trigger retry storms; replay selectively, throttle load, and verify outcomes.

**Key takeaway:** A dead-letter message is a **message isolated after a processing failure**, not a line in an exception log. Good design combines error classification, bounded retries, properly confirmed DLQ routing, structured and privacy-safe logging, backlog monitoring, and an idempotent replay process. Guarantees against message loss or duplication depend on the broker's contract and the entire processing pipeline—not merely on having a queue named `DLQ`.
