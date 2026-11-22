# Inspecting Message Flow with Java Logging

## 1. Why Inspect Message Flow?

In an application using a message broker, the fact that a service sends a message does not mean the message has been persisted by the broker, delivered to a consumer, or processed successfully. A journey may pass through **producer → broker → consumer → database → acknowledgment**, while also triggering retries, redeliveries, dead-letter queues (DLQ), fan-out, and follow-up messages.

**Inspecting message flow** means using structured logging, correlation identifiers, broker metadata, traces, metrics, and business reconciliation to answer: where is a logical message right now, which stages has it passed through, which attempt is this, which steps have been confirmed, and which have only been requested?

Practical questions:

- Has the producer **requested a publish** or has it received **broker confirmation**?
- Which topic/queue did the message enter, and via which partition/offset or routing key?
- Which consumer received it, and did it succeed in business processing or only in deserialization?
- Has the consumer ACKed/committed according to the broker's mechanism?
- Did a transient error lead to a retry, redelivery, or DLQ?
- Are there duplicates, lost confirmations, out-of-order processing, or missing stages?
- Are `traceId`, `messageId`, `correlationId`, and `attemptNo` preserved across threads and services?
- If the dashboard shows no `ERROR`, is that because the message succeeded or because observability data is missing?

**Logging alone does not prove exactly-once or durability.** A log line indicates that the application recorded a state; final confirmation requires reconciling against the broker, outbox/inbox, business database, and commit policy.

## 2. Logical Journey Model of a Message

~~~text
HTTP request / domain event / scheduled job
                    |
                    v
                Producer
               create event
                    |
                    v
             PUBLISH_REQUESTED
                    |
             broker send attempt
                    |
              +-----+------+
              |            |
              v            v
      PUBLISH_CONFIRMED  FAILED / UNKNOWN
              |
              v
       Topic / exchange / queue
              |
              v
         DELIVERY_RECEIVED
              |
              v
        PROCESSING_STARTED
              |
          +---+----+
          |        |
          v        v
       SUCCESS    FAILURE
          |        |
          v        +--> RETRY_SCHEDULED
     ACK/COMMIT               |
          |                   v
          v                REDELIVERY
     COMPLETED                |
                              +--> MAX_ATTEMPTS --> DLQ
~~~

The diagram describes **logical states**, not a single protocol. Kafka has producer callbacks and consumer offset commits; RabbitMQ has publisher confirms and consumer ack/nack/reject. Queue systems that manage visibility timeouts, message locks, or sessions have different settlement mechanisms.

Therefore, **each stage must be precisely defined before logging**. The name `PUBLISHED` in one system may mean `send()` was called, whereas in another it means broker confirmation was received. When inspecting flow, these two meanings must not be conflated.

## 3. Distinguishing Message ID, Event ID, and Trace ID

| Field | Role | Notes |
| --- | --- | --- |
| **messageId** | Identifies a logical message across its processing journey | Should remain stable across retries/redeliveries of the same message |
| **eventId** | Identifies a business event for deduplication | May differ from `messageId` if one event produces multiple messages |
| **correlationId / workflowId** | Links multiple messages belonging to the same workflow/request | A single request may fan out into multiple branches |
| **causationId / parentMessageId** | Points to the message/event that triggered a child message | Helps build a causal relationship graph |
| **traceId** | Links spans in a distributed trace | Not proof of broker ACK |
| **spanId** | Identifies an activity segment within a trace | Changes when a new span is created |
| **attemptNo** | Marks the processing/retry attempt | Must define where it starts and at which boundary it increments |
| **deliveryId** | Identifies a specific broker delivery if available | Brokers do not always provide a global ID |
| **consumerGroup / subscription** | Distinguishes groups processing a message | The same message may be valid for multiple subscribers |
| **topic-partition-offset** | Kafka record coordinates | An offset is only meaningful within its corresponding partition |
| **queue + routingKey + deliveryTag** | RabbitMQ context | Delivery tag is scoped to the channel |

**Do not use `traceId` in place of `messageId`.** A single trace can contain multiple messages, and a single message can be processed multiple times across multiple spans. Similarly, do not use a Kafka offset as a global ID because offsets can collide across partitions.

IDs taken from external clients/headers must be validated, length-bounded, and protected against log injection; if a trustworthy correlation ID is required, generate one at the trust boundary.

## 4. Building a Lifecycle Events Dictionary

An observable system needs a **stable `eventName`**, not just free-form sentences like “message is being handled”.

| Event | Valid Moment | Must Not Be Misinterpreted As |
| --- | --- | --- |
| MESSAGE_CREATED | Logical envelope created | Not necessarily published yet |
| PUBLISH_REQUESTED | Producer called send API | No broker confirmation yet |
| PUBLISH_CONFIRMED | Callback/future/confirm reported success per configuration | Consumer has not necessarily processed it |
| PUBLISH_FAILED | Send/confirm API reported an error | If an ACK was lost, the broker may still have received it |
| DELIVERY_RECEIVED | Consumer received the record/delivery | Handler has not finished yet |
| PROCESSING_STARTED | Handler started processing | Side effects have not committed yet |
| PROCESSING_SUCCEEDED | Action completed per business contract | ACK/offset commit may not have finished yet |
| PROCESSING_FAILED | An attempt failed | The message may be retried |
| RETRY_SCHEDULED | Retry scheduled per policy | Does not mean the broker has redelivered it |
| REDELIVERED | A new delivery actually occurred | Not a new business message |
| ACKNOWLEDGED | Broker settlement/commit executed via appropriate API | Does not by itself prove exactly-once |
| DEAD_LETTERED | Message moved to DLQ per policy with required confirmation | Root cause has not been resolved yet |
| DEDUPLICATE_SKIPPED | Event was already processed, so side effects were skipped | This is a valid handling branch for redelivery |
| REPLAYED | A controlled replay occurred from DLQ/archive | Requires separate idempotency policy and audit |

These names are **recommended conventions**. In production, there must be documentation clearly defining the conditions for emitting each event, which producer/consumer is responsible, and which system provides confirmation.

### Example Distinguishing Two Moments

~~~text
2026-11-10T02:41:00Z INFO event=PUBLISH_REQUESTED messageId=msg-101
2026-11-10T02:41:01Z INFO event=PUBLISH_CONFIRMED messageId=msg-101
2026-11-10T02:41:03Z INFO event=DELIVERY_RECEIVED messageId=msg-101
2026-11-10T02:41:04Z INFO event=PROCESSING_SUCCEEDED messageId=msg-101
2026-11-10T02:41:05Z INFO event=ACKNOWLEDGED messageId=msg-101
~~~

These are **illustrative logs**, not the default timing or behavior of any broker. Having separate stages prevents investigators from mistakenly concluding that an app having “sent” a message means the transaction is complete.

## 5. Schema of a Structured Log Event

JSON example for a consumer processing successfully:

~~~json
{
  "timestamp": "2026-11-10T02:41:04Z",
  "level": "INFO",
  "service": "order-consumer",
  "environment": "production",
  "instanceId": "worker-3",
  "event": "PROCESSING_SUCCEEDED",
  "messageId": "msg-101",
  "eventId": "evt-101",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "correlationId": "req-42",
  "consumerGroup": "orders",
  "topic": "order-commands",
  "partition": 2,
  "offset": 108,
  "attemptNo": 2,
  "durationMs": 37,
  "outcome": "SUCCESS"
}
~~~

This is an **illustrative schema**, not JSON auto-generated by Java SE. Fields should be consistently defined in name, data type, and meaning:

1. **timestamp** should have an explicit timezone/UTC; record both `occurredAt` and `recordedAt` if they need to be distinguished.
2. **service/environment/version/instance** to identify which deployment emitted the event.
3. **messageId/eventId/correlationId** from the envelope/headers; do not use the raw payload as an ID.
4. **event** has a finite set of values, which is better for dashboards/alerts than free-text messages.
5. **attemptNo**, `retryReasonCode`, `retryable`, `errorCode` when an error occurs.
6. **broker coordinates** (`topic`/`partition`/`offset` or `queue`/`routingKey`) only when the API actually provides them.
7. **duration/outcome** measured around a business-meaningful step; do not use the time of a single logger call as processing latency.
8. **exception.type** and minimal diagnostic data on failure; do not dump the entire payload by default.

In the JSON encoder, serialization must properly escape quotes, Unicode, and newlines. Structured logging solves **framing and querying**, but **does not automatically redact** tokens or private data.

## 6. Producer: Observing Publish Requests and Broker Confirmation

On the producer side, log stages when **calling send/publish** and when **receiving the callback/future result**. An asynchronous send typically returns control to the caller before the broker confirms.

~~~text
producer.send()
   |
   +--> PUBLISH_REQUESTED
   |
   +--> async callback:
          |
          +-- success --> PUBLISH_CONFIRMED + broker metadata
          |
          +-- error --> PUBLISH_FAILED / UNKNOWN + errorCode
~~~

**A timeout is an ambiguous situation**: the producer may lose the ACK after the broker has already received the record. Never claim “the message was definitely not sent” solely from a timeout. Retries can create duplicates; use a stable `eventId` and idempotency aligned with the business contract.

For a Kafka producer, success metadata can include `topic`, `partition`, and `offset`. For RabbitMQ, use publisher confirms along with appropriate route/return handling, because a broker-confirmed publish does not by itself prove routing to a queue with a consumer.

For a **transactional outbox**, a complete inspection flow also needs to verify:

- whether the business commit created the outbox record;
- whether the outbox publisher polled and sent the request;
- whether the broker confirm callback arrived;
- whether outbox rows marked sent have duplicate `eventId`s;
- whether the age of unprocessed outbox records is growing abnormally.

**`PUBLISH_CONFIRMED` is not `PROCESSING_SUCCEEDED`**: the broker receiving data is an independent step from the consumer processing it.

## 7. Consumer: Processing Success Differs from ACK/Commit

A consumer typically has three critical boundaries:

~~~text
DELIVERY_RECEIVED
       |
       v
PROCESSING_STARTED
       |
  business transaction
       |
       v
PROCESSING_SUCCEEDED
       |
       v
ACKNOWLEDGED / OFFSET_COMMITTED
~~~

If the consumer ACKs before side effects are committed, a crash can make the broker consider the message complete even though the DB was not updated. If the DB commit succeeds but the ACK has not been performed, the broker may redeliver and cause a **duplicate delivery**.

This leads to three requirements:

- Define the **point of processing success** according to the business transaction, not an early log line.
- Design an **inbox/dedup record, idempotency key, or atomic transaction** if side effects must not repeat.
- Log ACK/offset commit right when the settlement API succeeds; do not infer it from the handler returning.

For consumers using auto-commit, understand that commits may not align exactly with when side effects finish. When debugging, inspect the specific commit policy rather than assuming “the offset advanced so every transaction succeeded.”

**A consumer ACK does not prove that side effects outside the broker are exactly-once.** That is why message flow must be reconciled against the DB/inbox/outbox when guarantees are required.

## 8. Retry, Redelivery, Backoff, and DLQ

A logical message may have multiple deliveries:

~~~text
msg-102 attempt=1 PROCESSING_FAILED errorCode=TEMPORARY_DB_ERROR
msg-102 attempt=1 RETRY_SCHEDULED delayMs=500
msg-102 attempt=2 PROCESSING_STARTED
msg-102 attempt=2 PROCESSING_SUCCEEDED
msg-102 attempt=2 ACKNOWLEDGED
~~~

Practices to standardize:

| Field | Purpose |
| --- | --- |
| messageId/eventId | Persistent across attempts of the same logical event |
| attemptNo | Distinguishes processing attempt count |
| errorCode | Categorizes error causes with a stable set of values |
| retryable | Indicates whether the error is scheduled for retry |
| backoffMs / nextAttemptAt | Tracks retry schedule and avoids retry storms |
| deliveryTag / offset | Broker context per delivery |
| DLQ destination | Storage location for finally failed messages |
| replayOf / parentMessageId | Distinguishes a replayed message from its source |

**`PROCESSING_FAILED` is not a terminal failure.** The second attempt may succeed. For unrecoverable errors, apply a policy to route to a DLQ or an appropriate terminal state—never retry infinitely.

**A DLQ is not the end of an investigation.** Messages may need inspection, data correction, and controlled replay; replay actions must be audited and must avoid duplicating side effects.

If retry delays or requeuing cause the broker to redeliver rapidly in a tight loop, log rates can spike and obscure the real cause. Monitor retry rate, DLQ age, and backlog alongside `ERROR` log counts.

## 9. Delivery Semantics, Duplicates, and Idempotency

| Semantics | What Can Happen | Requirement When Reading Flow |
| --- | --- | --- |
| **At-most-once** | Events may be lost; little or no retry by design | Verify completeness from the source |
| **At-least-once** | An event may reach the consumer multiple times | Idempotency and attempt/delivery tracking |
| **Exactly-once within a specific scope** | May be supported by the broker under specific conditions | Do not extrapolate to external databases/APIs outside the transaction |
| **Transactional outbox + inbox** | Connects business commits with publish/consume | Still requires retries, dedup, and reconciliation |

Typical scenario:

~~~text
attempt=1: DATABASE_COMMITTED
attempt=1: ACK_FAILED
attempt=2: DELIVERY_RECEIVED
attempt=2: DEDUPLICATE_SKIPPED
attempt=2: ACKNOWLEDGED
~~~

Two deliveries resulting in only **one side effect** is the correct outcome when the consumer has valid deduplication. Dashboards must distinguish between **attempt failures** and **logical messages failed** so a single incident is not double-counted.

**Do not treat every retry as a new message.** If a workflow intentionally emits a new replacement message, give it a new `eventId` and a `causationId` pointing to the original event; if it is a redelivery of the same event, keep IDs stable per the contract.

## 10. Standalone Java 17: Inspecting Flow and Retries

This example uses only **Java SE 17**, with no real broker. An in-memory queue simulates the journey of three messages: immediate success, one retry then success, and three failed attempts routed to the DLQ. All events are printed in deterministic order for easy comparison.

Create **MessageFlowDemo.java**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.Queue;

public class MessageFlowDemo {
    record Message(String messageId, String traceId, String payload) {}
    record Delivery(Message message, int attempt) {}

    private static void emit(List<String> lines, Message message,
                             String stage, int attempt) {
        String line = "FLOW id=" + message.messageId()
                + " trace=" + message.traceId()
                + " stage=" + stage
                + " attempt=" + attempt;
        lines.add(line);
        System.out.println(line);
    }

    public static void main(String[] args) {
        List<Message> messages = List.of(
                new Message("msg-101", "trace-101", "ok"),
                new Message("msg-102", "trace-102", "retry-once"),
                new Message("msg-103", "trace-103", "always-fail"));

        Queue<Delivery> queue = new ArrayDeque<>();
        List<String> lines = new ArrayList<>();

        for (Message message : messages) {
            emit(lines, message, "PUBLISHED", 0);
            queue.add(new Delivery(message, 1));
        }

        int acknowledged = 0;
        int deadLettered = 0;
        int retries = 0;

        while (!queue.isEmpty()) {
            Delivery delivery = queue.remove();
            Message message = delivery.message();
            int attempt = delivery.attempt();
            emit(lines, message, "DELIVERED", attempt);

            boolean failed = "always-fail".equals(message.payload())
                    || ("retry-once".equals(message.payload())
                        && attempt == 1);

            if (failed && attempt < 3) {
                emit(lines, message, "RETRY_SCHEDULED", attempt);
                queue.add(new Delivery(message, attempt + 1));
                retries++;
            } else if (failed) {
                emit(lines, message, "DEAD_LETTERED", attempt);
                deadLettered++;
            } else {
                emit(lines, message, "PROCESSED", attempt);
                emit(lines, message, "ACKNOWLEDGED", attempt);
                acknowledged++;
            }
        }

        System.out.println("SUMMARY published=" + messages.size()
                + " ack=" + acknowledged
                + " dlq=" + deadLettered
                + " retries=" + retries
                + " records=" + lines.size());

        if (acknowledged + deadLettered != messages.size()) {
            throw new IllegalStateException("Terminal states mismatch");
        }
    }
}
~~~

Compile and run:

~~~bash
javac MessageFlowDemo.java
java MessageFlowDemo
~~~

**Exact stdout** on a successful run:

~~~text
FLOW id=msg-101 trace=trace-101 stage=PUBLISHED attempt=0
FLOW id=msg-102 trace=trace-102 stage=PUBLISHED attempt=0
FLOW id=msg-103 trace=trace-103 stage=PUBLISHED attempt=0
FLOW id=msg-101 trace=trace-101 stage=DELIVERED attempt=1
FLOW id=msg-101 trace=trace-101 stage=PROCESSED attempt=1
FLOW id=msg-101 trace=trace-101 stage=ACKNOWLEDGED attempt=1
FLOW id=msg-102 trace=trace-102 stage=DELIVERED attempt=1
FLOW id=msg-102 trace=trace-102 stage=RETRY_SCHEDULED attempt=1
FLOW id=msg-103 trace=trace-103 stage=DELIVERED attempt=1
FLOW id=msg-103 trace=trace-103 stage=RETRY_SCHEDULED attempt=1
FLOW id=msg-102 trace=trace-102 stage=DELIVERED attempt=2
FLOW id=msg-102 trace=trace-102 stage=PROCESSED attempt=2
FLOW id=msg-102 trace=trace-102 stage=ACKNOWLEDGED attempt=2
FLOW id=msg-103 trace=trace-103 stage=DELIVERED attempt=2
FLOW id=msg-103 trace=trace-103 stage=RETRY_SCHEDULED attempt=2
FLOW id=msg-103 trace=trace-103 stage=DELIVERED attempt=3
FLOW id=msg-103 trace=trace-103 stage=DEAD_LETTERED attempt=3
SUMMARY published=3 ack=2 dlq=1 retries=3 records=17
~~~

Explanation:

1. **msg-101:** attempt 1 succeeds, with terminal ACK.
2. **msg-102:** attempt 1 fails, attempt 2 succeeds with terminal ACK.
3. **msg-103:** attempts 1 and 2 fail, attempt 3 enters terminal DLQ.
4. There are **3 logical messages**, but **6 delivery attempts** and **17 stage records**.
5. **retries=3**: one for `msg-102`, two for `msg-103`.
6. **traceId** is passed via the simulated message record; there is no tracing SDK or auto-generated span.
7. **ACKNOWLEDGED/PUBLISHED** are only in-memory simulations, with no broker connection and no durability guarantee.

The output is deterministic because the program uses a single sequential `ArrayDeque` without concurrent workers. Do not use this output to infer stage ordering in a multi-partition or multi-consumer system.

## 11. Attaching Message Context to SLF4J MDC

In applications using SLF4J/Logback, **Mapped Diagnostic Context (MDC)** attaches IDs to multiple log lines. Example text pattern:

~~~text
%d{ISO8601} %-5level message=%X{messageId} trace=%X{traceId} %logger - %msg%n
~~~

This is only an **illustrative pattern**; an appropriate encoder/appender must be configured at runtime. The **`%X{traceId}` pattern does not create tracing**: MDC must be populated by application code or instrumentation.

Integration snippet (requires SLF4J dependency and an application-provided `Runnable` handler):

~~~java
import org.slf4j.MDC;

void consume(String messageId, String traceId, Runnable handler) {
    String oldMessage = MDC.get("messageId");
    String oldTrace = MDC.get("traceId");
    try {
        MDC.put("messageId", messageId);
        MDC.put("traceId", traceId);
        handler.run();
    } finally {
        if (oldMessage == null) MDC.remove("messageId");
        else MDC.put("messageId", oldMessage);

        if (oldTrace == null) MDC.remove("traceId");
        else MDC.put("traceId", oldTrace);
    }
}
~~~

In a thread pool, forgetting to clear/restore MDC can cause logs for message B to mistakenly inherit the ID of message A. When `CompletableFuture` or an executor switches a task to another thread, `ThreadLocal`/MDC does not usually propagate automatically; you must capture/activate/restore it or use your framework's propagation mechanism.

**Never put raw payloads, `Authorization` headers, or emails into MDC**. An encoder that outputs the entire MDC will emit these values across many log lines. Message IDs from external headers must be validated before use.

## 12. Tracing Across Brokers and Async Boundaries

A trace can connect producer stages, broker boundaries, consumers, and downstream databases/APIs via instrumentation. W3C Trace Context uses the **`traceparent`** header and optionally **`tracestate`**; some systems use OpenTelemetry propagators to inject/extract context.

~~~text
Producer span -- inject headers --> Broker delivery
                                         |
                                         v
                               Consumer extracts context
                                         |
                                         v
                                Processing span + logs
~~~

Key points to understand:

- `traceId` is only meaningful with a real tracing context, not a random string labeled `traceId`.
- Async consumers, batches, and fan-out may use **span links** instead of a single parent-child chain; the representation depends on instrumentation and semantic conventions.
- Trace sampling can cause spans to be missing in the UI even when the message passed through all stages.
- Trace context does not replace `messageId` and broker coordinates.
- Do not put baggage containing PII/secrets into headers or logs; keep only permitted fields.
- If headers are missing or invalid, record **`context_missing`** or create a new context per policy instead of pretending an accurate link exists.

For consumer handlers that dispatch work across a thread pool, propagate trace context and MDC within the proper scope; avoid mixing traces of multiple messages processed concurrently.

## 13. Kafka: Topic, Partition, Offset, and Commit

With the Kafka Java client, the record coordinates for debugging are **cluster/topic/partition/offset**, accompanied by `eventId`/`messageId`. An offset is only meaningful within **a single partition**, not as a global sequence.

What to track:

1. Producer sends the request, attaching `messageId` to the key/header/value per contract.
2. Success callback/future receives `RecordMetadata` and logs `topic`, `partition`, and `offset`.
3. Error callback logs `exceptionType`/`errorCode`; timeouts may be an ambiguous outcome.
4. Consumer poll receives `topic`/`partition`/`offset` and logs delivery and `consumerGroup`.
5. Handler commits side effects and logs `PROCESSING_SUCCEEDED` once the contract is satisfied.
6. Commit offsets per policy and log the callback result or appropriate commit action.
7. Rebalances, seeks, retry topics, and DLQ routing should have distinct events if they affect flow.

Java integration snippet requiring the Kafka client along with `producer`, `record`, `logger`, and `messageId` already defined in the application:

~~~java
producer.send(record, (metadata, error) -> {
    if (error == null) {
        logger.info("event=PUBLISH_CONFIRMED messageId={} "
                + "topic={} partition={} offset={}",
                messageId, metadata.topic(),
                metadata.partition(), metadata.offset());
    } else {
        logger.error("event=PUBLISH_FAILED messageId={}",
                messageId, error);
    }
});
~~~

**This is not a standalone program.** Callback success means the broker confirmed according to producer/cluster configuration, not that the consumer has finished.

Notes:

- **Consumer lag** measures backlog per group/partition, not the exact processing latency of individual messages.
- Kafka preserves record ordering within a single partition; **there is no default global ordering** across partitions.
- Rebalances and commit behavior can cause redelivery; idempotency must be handled.
- An observed offset “jump” alone does not prove record loss: isolation level, transaction/control records, filtering, or compaction can affect it.
- Auto-commit does not guarantee that the business DB transaction has committed.

## 14. RabbitMQ: Publisher Confirms, Routing, and ACK/NACK

With RabbitMQ, distinguish three groups of confirmations:

- **Publisher confirm:** the broker reports publish status via the confirm mechanism, not consumer completion.
- **Routing/returns:** whether an exchange routes to a queue depends on bindings, the `mandatory` flag/return handling, and configuration.
- **Consumer acknowledgments:** `basicAck`, `basicNack`, or `basicReject` represent settlement of a delivery on a channel.

When logging on the consumer, include `queue`, `consumerTag` if appropriate, `messageId`, attempt/delivery context, `routingKey`, `errorCode`, and terminal outcome. **Delivery tag is scoped to the channel** and does not replace `messageId`.

A common mistake is continuous `nack` + `requeue` without delay or retry limits, causing a **retry storm**. Policies can use retry queues, dead-letter exchanges, TTL, delayed delivery (when a suitable mechanism exists), and DLQs. **Do not assume calling `nack` automatically creates backoff.**

~~~text
DELIVERY_RECEIVED queue=order.commands messageId=msg-102
PROCESSING_FAILED attempt=1 errorCode=DB_UNAVAILABLE
RETRY_SCHEDULED attempt=2 backoffMs=500
DELIVERY_RECEIVED queue=order.retry messageId=msg-102
PROCESSING_SUCCEEDED attempt=2
ACKNOWLEDGED
~~~

These lines are **illustrative**. In a real runtime, inspect the corresponding queue, DLX, routing, and confirm results. Sending to a DLQ is also an action that can fail or remain incomplete.

## 15. Multi-Service Flows, Fan-Out, and Sagas

One message can spawn multiple child messages:

~~~text
order.created (workflowId=w-55)
    |
    +--> inventory.reserve ---> inventory.reserved
    |
    +--> payment.authorize ---> payment.authorized
    |
    +--> notification.send ---> notification.sent
                                      |
                                      v
                               order.completed
~~~

To reconstruct the journey:

- One **workflowId/correlationId** for the entire workflow.
- A **distinct `messageId`** for each message.
- A **causationId/parentMessageId** showing which message triggered the new message.
- A **stepName/attempt/outcome** for each branch.
- A **terminal workflow outcome** when all required branches complete or receive compensating actions.
- Track timeouts and outstanding branches; do not mark a workflow completed just because one branch ACKed.

If using a saga, explicitly log **compensation requested/succeeded/failed** events. A step that previously succeeded and was later compensated represents two valid historical events—do not edit old logs to make the successful step disappear.

In multi-subscription fan-out, the same `messageId` can be validly processed by multiple consumers. Terminal uniqueness checks must be keyed by **`messageId` + `subscription`/`consumerGroup` + `workflowStep`**, not by `messageId` globally.

## 16. Invariants to Verify Flow

Define invariants according to the **business contract**, not just line counts:

| Invariant | Value | Limitation |
| --- | --- | --- |
| Every logical event has an origin | Locate source producer/outbox | Logs may be sampled/dropped |
| Publish has an outcome | Confirmed, failed, or UNKNOWN after deadline | Timeout may leave state unknown |
| Delivery has an attempt | Know each processing attempt | Brokers do not always provide a standard retry count |
| Side effects do not repeat illegally | Dedup by `eventId` | Multiple valid subscribers may exist |
| Settlement aligns with commit | ACK after success point per policy | Broker and business transactions differ |
| Terminal outcome within SLA | Completed, canceled, or DLQ | In-flight items may not have reached deadline yet |
| Valid causal links | Fan-out/fan-in have parent/workflow IDs | Clocks do not prove causality |
| Missing events can be reconciled | Compare against outbox/inbox/broker/DB | Reading logs alone is insufficient |

**The number of ACKs does not necessarily equal the number of published messages** when multiple subscriptions or filters exist. A flow can have a valid “pending” state; when computing missing terminals, use a time window/SLA and a source-of-truth system.

**End-to-end exactly-once** cannot be proven from logs alone; it requires atomicity, idempotency, and reconciliation of actual side effects.

## 17. How Metrics and Traces Complement Logs

| Tool | When to Use | Limitation |
| --- | --- | --- |
| **Structured logs** | Trace the journey of a `messageId` and each `errorCode` | May be sampled, dropped, or past retention |
| **Distributed traces** | Inspect latency/call graphs across services | Not always complete with async/sampling |
| **Metrics** | Detect rising lag, retry rate, DLQ size | Not keyed by specific individual IDs |
| **Broker tools** | Inspect offsets, queue depth, consumer connectivity | Do not prove DB side effects |
| **Outbox/inbox/business DB** | Reconcile commits, dedup, terminal outcomes | Lack timeline detail without logs |

Useful metrics include:

- Producer publish requests/confirms/failures and confirmation latency.
- Consumer delivery/success/failure **per attempt** and **per logical message**.
- Processing duration p50/p95/p99; oldest message age and consumer lag.
- Retries scheduled, redeliveries, DLQ ingress, DLQ age, and replay outcomes.
- Outbox age/backlog; inbox dedup hits; outstanding workflow steps.
- Async logger queue fullness, collector parse errors, log drop count, and trace context missing rate.

**Do not put `messageId`/`traceId`/`requestId` into metric labels** because cardinality explodes rapidly. Use `service`, `topic`/`queue`, `group`, `outcome`, and `errorCode` with finite value domains; dynamic IDs belong in logs and traces.

## 18. Backpressure and Logging Pipeline Durability

Under high load, the logging pipeline itself can become a bottleneck:

~~~text
Message handler -> logger -> async queue -> formatter -> stdout/file
                                              |
                                              v
                                       collector/backend
~~~

**Backpressure** refers to mechanisms that throttle the producer when a queue or sink cannot keep up. With an async appender, a full queue can block processing threads, drop log events, or apply another policy depending on the provider/configuration. Therefore:

- Do not assume enabling async logging is free or that every `ERROR` is preserved.
- Know the queue capacity, blocking/discard policy, and flush behavior on shutdown.
- Monitor log drop rate and ingestion delay; if they rise, **a gap in logs does not prove a gap in message flow**.
- Avoid dumping payloads/stack traces on every retry attempt unless necessary; high volume can drown out critical events.
- Mandatory audit records must use a durable storage channel per contract, not rely solely on a best-effort diagnostic logger.

**Broker backpressure** is a separate issue: queue depth/consumer lag grows when consumers process slowly. A service can simultaneously backlog messages and drop logs; in that case, outbox/inbox and broker metadata are even more critical for investigation.

## 19. Runbook: Finding Breaks in the Message Flow

Start from `correlationId` or `messageId` and check in order:

1. **Business source / outbox:** does the origin event exist and did it commit?
2. **Producer:** did `PUBLISH_REQUESTED` appear? Did the callback report `CONFIRMED`, `FAILED`, or `UNKNOWN`?
3. **Broker:** does the record/queue entry exist? Are `topic`/`partition`/`offset`, routing, and ACLs correct?
4. **Consumer:** which `group`/`subscription` received it; is there lag or thread pool congestion?
5. **Processing:** did the handler start and finish; which `exceptionType`/`errorCode` occurred?
6. **Business DB:** did side effects commit; does the inbox dedup table have a record?
7. **ACK/offset:** did settlement happen after success, or did it hit a timeout/rebalance?
8. **Retry/DLQ:** did `attempt` increment; are backoff and routing working properly?
9. **Downstream:** did the handler emit new messages, and is `causationId` linked properly?
10. **Telemetry:** did the collector drop logs, have a parser mismatch, sample, or expire retention?

Quick triage table:

| Observation | Hypothesis | How to Verify |
| --- | --- | --- |
| Requested but not Confirmed | Callback error, timeout, crash, log drop | Producer callback, outbox, broker query |
| Confirmed but not Received | Consumer offline, lag, wrong routing/group | Broker depth, subscription, ACL |
| Received but not Processing | Deserialization error, congested handler queue | Error handler, executor, thread dump |
| Succeeded but not ACKed | Crash between commit and ACK, commit failure | Business DB, broker offset, inbox |
| Multiple failed attempts | Retry/redelivery or duplicate logs | `attemptNo`, `eventId`, dedup |
| ACKed but business data missing | Early ACK, side effect rollback, wrong contract | Transaction logs and DB state |
| Retry scheduled but not delivered | Retry queue/scheduler failure, TTL/routing | Retry infrastructure, DLQ |
| DLQ event logged but DLQ empty | Move failed, already replayed, expired | DLX config, retention, ops history |
| TraceId breaks between services | Header or context propagation failure | Instrumentation, propagator, MDC |
| No logs seen but broker advances | Sampling/retention/collector issue | Metrics, raw sink, broker metadata |

**Absence of logs does not prove a stage did not happen.** What matters is identifying which evidence sources are reliable and which states remain `UNKNOWN`.

## 20. Security and Log Cost Control

Do not put raw payloads, headers containing secrets, or request/response bodies into general logs merely for debugging convenience. Messages may carry personal data, tokens, payment details, or business secrets.

What to record:

- Validated IDs (`messageId`/`eventId`/`traceId`/`correlationId`).
- Event name, service, destination, `consumerGroup`, `attemptNo`.
- Status/outcome/`errorCode`/`exceptionType` and timing.
- Broker coordinates when returned.
- Payload schema/version and size if needed, **not** the raw payload.

What to avoid:

- `Authorization`, `Cookie`, access/refresh tokens, and API keys.
- Dumping the entire JSON message on `ERROR`.
- Unchecked exception messages/stack traces embedding URLs/queries/secrets.
- MDC containing raw user objects or emails.
- Log forging caused by CR/LF in headers/payloads breaking text logs; use structured encoders, validation, and sink-appropriate escaping.

**Redaction at the collector is an additional layer, not a substitute for minimization at the source.** Once a token reaches stdout/files, it may exist in multiple copies before the collector masks it.

For performance, logging every stage at `INFO` under extreme throughput can increase costs. Distinguish **essential lifecycle events**, debug-only logs, aggregated metrics, and sampled traces. Do not disable mandatory audit events.

## 21. End-to-End Testing in Staging

| Scenario | Expectation |
| --- | --- |
| Normal message | Complete publish confirm, delivery, processing, settlement |
| Producer timeout / lost ACK | `UNKNOWN` state handled; retry does not duplicate side effects |
| Broker unavailable | Producer fails/retries sensibly; outbox backlog measured |
| Crash before business commit | Message recovered/redelivered per contract |
| Crash after DB commit but before ACK | Redelivery deduplicated; no duplicate side effects |
| Transient handler failure | Retry/backoff works; `attemptNo` increments |
| Poison message / invalid schema | Clear `errorCode`, no secret dump, routed to DLQ |
| Consumer group rebalance | Ownership and offsets do not cause business data loss |
| Multiple partitions | No assumption of global ordering |
| Fan-out to multiple consumers | Correct terminal state per subscription |
| DLQ replay | Audited, causation link preserved, idempotent |
| Thread pool reuse | MDC does not mix context across messages |
| Collector outage | Backpressure/drops measured; business flow reconciled |
| Payload with CR/LF or secrets | Encoder/redaction prevents leaks or forged events |
| Missing trace context | `context_missing` signaled; no false trace linking |

The Java 17 example in Section 10 is a unit-level simulation: 3 messages, 6 deliveries, 3 retries, 2 ACKs, and 1 DLQ. It **does not replace** integration tests with a real broker, database, and collector.

Crash, network partition, or poison-message experiments must run on **authorized test environments**; never cause unplanned disruption in production.

## 22. Operational Checklist

| Check | Criterion |
| --- | --- |
| Event contract | Producer/consumer/retry/terminal have clear stage semantics |
| Identity | Distinguish `messageId`, `eventId`, `traceId`, `correlationId`, and `attemptNo` |
| Structured output | Consistent schema, explicit timestamp, finite `errorCode`s |
| Producer | Callback/confirm logged at the actual broker confirmation milestone |
| Consumer | Processing result and ACK/offset commit are not conflated |
| Retry | Backoff, attempt limit, redelivery, and DLQ are observable |
| Delivery | Duplicates handled via idempotency/inbox |
| Outbox | Business commit and publish reconciled, with lag alerts |
| Ordering | Contract defined per partition/stream and causal links |
| Trace/MDC | Context propagated across headers/threads and cleaned up in scope |
| Metrics | Lag, oldest age, DLQ count, retry rate, log drops |
| Privacy | No leaked credentials/payloads; protected against log forging |
| Backpressure | Queue overflow understood in both broker and logging pipeline |
| Verification | Invariants and staging failure tests in place |
| Incident runbook | Trace from ID → producer → broker → consumer → terminal |

**Conclusion:** effective message flow inspection requires **stable identifiers, clear lifecycle events, distinguishing broker confirmation from business processing and settlement, visibility into retries/DLQ, and verification against business state**. Java logging builds the timeline; broker metadata, distributed tracing, metrics, and outbox/inbox are complementary sources that confirm the actual path and prevent jumping to conclusions from a single “message received” line.
