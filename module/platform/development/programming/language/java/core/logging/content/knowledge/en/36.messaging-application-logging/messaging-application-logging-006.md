# Message Retries in Java Core Logging

## Learning Objectives

This lesson belongs to the **Messaging Application Logging** group, covering **Message Retries**. In an asynchronous message-processing system, a message may be received multiple times due to transient errors, worker crashes, timeouts, consumer rebalances, unacknowledged ACKs/offsets, or an intentional retry mechanism. Logging here is not merely printing an exception on every failed attempt. Logs must help operators answer: **which message**, **which attempt it is on**, **why it is being retried**, **when it will be retried next**, **whether processing succeeded**, and **whether it was actually moved to a dead-letter queue (DLQ) or only requested to be moved**.

After this lesson, you will be able to:

- Distinguish between **delivery attempt**, **processing attempt**, **business operation**, and **log-sending retries**.
- Design consistent log events for `received`, `processing`, `retry_planned`, `retry_scheduled`, `processed`, `acknowledged`, `retry_exhausted`, and `dead_letter_confirmed`.
- Use `message_id`, `attempt`, `operation_id`, `correlation_id`, and `trace_id` with accurate semantics, avoiding confusion when a message is redelivered.
- Choose appropriate log levels to preserve error signals while avoiding a "log storm" during repeated retries.
- Understand RabbitMQ's ACK/NACK/requeue mechanisms, Kafka's offset commits, and the limits of at-least-once delivery.
- Evaluate backoff, jitter, retry limits, poison messages, DLQ/parking queues, idempotency, and the transactional outbox pattern.
- Run a standalone Java 17 example to observe deterministic retry logs without confusing a "planned" record with broker confirmation.
- Test scenarios involving crashes, timeouts, duplicates, DLQ failures, and security vulnerabilities in log payloads.

**Core Principle:** A retry log must describe **the state proven at the time of writing**. If the broker has not yet confirmed scheduling a retry, do not log "retry scheduled successfully"; if sending to the DLQ was only requested, do not log "moved to DLQ"; if the handler has finished running but the offset is not yet committed, do not claim the message will definitely not be processed again.

## 1. What Is Message Retry?

A message-driven application typically has a producer that publishes messages to a broker/topic/queue, after which a consumer receives and processes them. A message can fail due to:

1. **Transient errors:** downstream timeouts, HTTP 503, temporarily lost database connections, rate limits, or intermittent broker/network issues.
2. **Permanent errors:** invalid schema, missing required fields, an operation rejected in a way that cannot recover through retries, or an unsupported message version.
3. **Ambiguous errors:** the consumer calls an external system and times out before knowing whether the side effect completed.
4. **Consumer/broker infrastructure errors:** process crashes, lost ACKs, rebalances, uncommitted offsets, network partitions, or queue state transitions.

A retry is **a mechanism to reattempt processing**, not proof that a message is processed exactly once. Under at-least-once delivery, a single logical message may reach a consumer multiple times; logs must allow distinguishing between **the number of processing attempts** and **the number of times the business logic actually applied a side effect**.

### Terms to Distinguish

| Concept | Meaning | Logging issue if confused |
| --- | --- | --- |
| **Message ID** | Identifies a logical message by application convention; may not be auto-assigned by the broker | If a new ID is generated on each retry, attempts cannot be correlated |
| **Delivery attempt** | A single delivery of a message from the broker or intermediary to the consumer | Processing attempts may differ from delivery counts if the framework retries in-process |
| **Processing attempt** | A single execution start of the handler's business logic | Miscounting retries when using broker delivery count as total handler invocations |
| **Business operation ID** | Identifies the logical action that requires idempotency protection | Retries may produce multiple logs, but the side effect must execute only once |
| **Consumer instance** | The JVM/pod/worker receiving a message at a given time | Needed to analyze errors occurring on only one instance |
| **Correlation/trace ID** | Links a chain of distributed operations | Not necessarily unique per event or per retry |
| **Broker acknowledgement / offset commit** | Marks processing progress according to broker semantics | Handler return does not always mean the message is ACKed/committed |
| **Retry scheduling** | Queues the message for the next run, immediately or with a delay | "Planned" differs from "confirmed" if publishing to the retry queue/broker fails |
| **Dead-lettering** | Moves an unprocessable message to an error channel | "Requested DLQ" differs from "confirmed routed/persisted at DLQ" |

**Example:** A command `operation_id=pay-71` has `message_id=msg-71`. A consumer receives it once, retries the handler in-process three times, and then crashes before ACKing. The broker redelivers the message to another instance. There may be **multiple handler attempts**, **two broker deliveries**, and **only one logical payment operation**. You cannot deduce how many times payment was charged solely from the total number of `processing_started` logs.

## 2. Message Lifecycle and Key Logging Milestones

A conceptual model:

```text
Producer publishes msg-71
          |
          v
      Broker / queue
          |
          v
    Consumer receives
          |
          +--> start processing, attempt=1
                    |
                    +--> SUCCESS ---> commit/ACK requested ---> ACK confirmed
                    |
                    +--> TRANSIENT FAILURE
                    |      |
                    |      +--> retry planned (backoff)
                    |                 |
                    |           schedule/publish retry
                    |                 |
                    |          confirmed? -> next attempt
                    |
                    +--> PERMANENT FAILURE
                    |      |
                    |      +--> route to DLQ / quarantine
                    |
                    +--> RETRIES EXHAUSTED
                           |
                           +--> route to DLQ / terminal policy
```

Logging milestones should be clear:

| Milestone | Suggested event code | Reference level | What is actually known |
| --- | --- | --- | --- |
| Message received | `message.received` | DEBUG or sampled INFO | Broker/client has delivered the message to the consumer |
| Handler started | `message.processing_started` | DEBUG | Consumer begins processing the attempt |
| Transient failure | `message.processing_failed` | WARN or DEBUG per policy | Handler encountered a classified error |
| Decision to retry | `message.retry_planned` | INFO/WARN depending on risk | Policy chose retry; not yet confirmed as scheduled by the broker |
| Broker confirms retry | `message.retry_scheduled` | INFO | Retry transport has confirmed per API semantics |
| Processing succeeded | `message.processed` | INFO | Handler/business logic succeeded per defined contract |
| ACK/offset commit confirmed | `message.acknowledged` / `message.offset_committed` | DEBUG or INFO when needed | Confirmation received at the corresponding broker milestone |
| Retries exhausted | `message.retry_exhausted` | ERROR/WARN depending on impact | Max attempts reached; no further retries per policy |
| DLQ move requested | `message.dlq_requested` | WARN/ERROR | Consumer/handler **requested** rerouting; success not yet proven |
| DLQ confirmed | `message.dlq_confirmed` | WARN/ERROR or audit | DLQ destination confirmed per contract and verified route |
| Error record replayed | `message.replay_requested` / `message.replayed` | INFO/WARN | Replay must include operator/ID and start a new processing lifecycle |

These are illustrative **event code conventions**, not default APIs of Java, Kafka, or RabbitMQ. An organization may choose different names, but event meanings must remain fixed and documented in the schema/contract. Level selection depends on impact; a transient timeout that self-recovers may not need a large stack trace printed on every attempt.

### Common Logging Mistakes

- Calling `logger.info("message processed successfully")` right after deserialization succeeds, before the handler finishes.
- Logging `retry_scheduled` before the broker actually accepts the message into the retry topic/queue.
- Logging `dlq_confirmed` immediately after calling the DLQ send API without waiting for the corresponding publish confirm/ack.
- Logging `acknowledged` before the offset commit succeeds; if the commit fails, the message may be redelivered.
- Logging `ERROR` only on the first attempt; the fifth attempt succeeds without a summary log, misleading operators into thinking the message failed.
- Logging only the final error without retaining `attempt_count`/`first_attempt_at`/`last_error_code`, making it hard to know how long retries lasted.

## 3. Minimum Log Schema for Retries

A useful JSON log might look like this:

```json
{
  "timestamp": "2026-11-10T02:00:03.125Z",
  "level": "WARN",
  "service": "payment-consumer",
  "environment": "staging",
  "event": "message.retry_planned",
  "message_id": "msg-71",
  "operation_id": "pay-71",
  "correlation_id": "corr-22",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "destination": "payments.commands",
  "partition": 2,
  "offset": 147,
  "consumer_group": "payment-workers",
  "attempt": 2,
  "max_attempts": 5,
  "next_attempt": 3,
  "retry_delay_ms": 2000,
  "error_code": "DOWNSTREAM_TIMEOUT",
  "exception_type": "java.net.http.HttpTimeoutException",
  "outcome": "RETRY_PLANNED"
}
```

**This is illustrative JSON**, not the default stdout of SLF4J/Logback, and it does not imply that every broker always has `partition`/`offset` fields. Appropriate fields depend on the protocol.

Points to standardize:

1. **`timestamp`:** the time the log event was created at the decision point; if the collector receives it late, keep `observed_timestamp`/ingested time separately.
2. **`message_id`:** a logical ID stable across retries; if the producer does not provide one, consider adding an envelope ID in the schema or a controlled idempotency key.
3. **`operation_id`:** the business operation ID requiring duplicate side-effect protection. One operation may involve multiple messages; the relationship must be clear.
4. **`attempt`:** a 1-based counter for the first processing attempt (a **convention**, not the default in every framework). Distinguish "retries performed" = `attempt - 1` if initial attempt is defined as 1.
5. **`max_attempts`:** total allowed handler executions. If a policy states "max 3 retries," there is typically 1 initial + 3 retries = 4 attempts; avoid conflating the two concepts.
6. **`error_code`:** a stable error code with lower cardinality than raw exception message strings. Exception type and stack trace can be added where context warrants, without including raw payloads.
7. **`retry_delay_ms` and `next_attempt_at`:** used when a delay is planned. If scheduling is not yet confirmed, log `retry_planned` and only switch the event to `retry_scheduled` after real confirmation.
8. **`destination`/`queue`/`topic`:** transport path helpful for debugging, though `partition`/`offset` fields only apply to brokers with corresponding semantics.
9. **`consumer_group`/`consumer_id`:** helps identify rebalances or faulty instances. Do not use high-cardinality IDs directly as metric labels.
10. **`delivery_id` or `delivery_tag`:** information about a single delivery, which may only be meaningful within the current connection/channel; do not use it to replace a stable message ID.

### What Not to Log

- Full message bodies by default—especially payment data, passwords, tokens, cookies, credentials, personal information, or confidential documents.
- Headers such as `Authorization`, `Cookie`, access keys, signatures, or session tokens.
- Full URLs containing tokens in query parameters, connection strings with passwords, or broker credentials.
- Exception messages taken directly from external systems without redaction; some exceptions contain URLs or user data.
- Payloads that fail deserialization automatically just to see "why it is invalid"; instead log schema version, safe field path, message size, error code, and IDs.

Note that `trace_id` is not an authentication token. However, it can still be sensitive metadata depending on policy. For events requiring auditing, log viewing permissions and retention need dedicated policies. Only enable detailed payload logging in secure, time-bounded testing—never by default in production.

## 4. Choosing Log Levels to Avoid a Log Storm

Suppose an HTTP 503 error triggers 10 retries for 100,000 messages; if every attempt prints a full exception stack trace at ERROR, the system can generate millions of lines, choking the collector and obscuring real errors.

A reference policy:

| Event | Suggested level | Conditions/notes |
| --- | --- | --- |
| Message received/start processing | DEBUG | Enable selectively; metrics count all messages |
| Expected retryable failure with retries remaining | WARN or DEBUG | Log error code, attempt, next delay; selective stack trace |
| Retry scheduled/publish confirmed | INFO or DEBUG | Only conclude scheduled when the mechanism actually confirms |
| Success on first attempt | Sampled INFO or DEBUG | Keep throughput/success counts in metrics |
| Success after retry | INFO | Log `attempts_used`, `elapsed_ms`, safe last error code |
| Permanent failure | ERROR or WARN | Distinguish expected invalid input behavior from system incidents |
| Retries exhausted | ERROR | Log total attempts, destination, policy, impact, and DLQ decision |
| DLQ publish failed | ERROR | A critical new failure on the recovery path; requires a dedicated alert |
| DLQ confirmed | WARN/ERROR per policy | Specify which contract it was persisted under |
| Duplicate/idempotency skip | INFO/DEBUG | Do not treat as a new handler success or new business side effect |

**These are not rigid rules for every system.** For instance, an invalid message frequently sent by a client with a bad schema might be a WARN plus a metric; an unprocessable payment command might require ERROR and an alert. What matters is clear event codes and outcomes, not logging ERROR at every step of a retry.

### Strategies to Reduce Duplicate Exception Logs

- Keep one log with sufficient context at the message-processing boundary; do not log and re-`throw` the same exception across every service/repository layer.
- If retrying many times for the same error code, log a short event on intermediate attempts; log controlled details on the **first failure** and/or **exhausted** state.
- Replace thousands of repetitive lines with metrics like `retry_attempts_total`, `retry_exhausted_total`, and time-window summaries, without losing the ability to investigate by message ID when needed.
- Sampling transient logs can be acceptable, but never arbitrarily sample audit logs, security events, or mandatory critical outcomes.
- Do not compute expensive serialized payloads or stack traces before checking the enabled log level, because Java evaluates arguments before calling the logger.

## 5. Classify Errors Before Deciding to Retry

Retrying every exception is an anti-pattern:

| Error type | Examples | Typical appropriate action | Log contents |
| --- | --- | --- | --- |
| **Transient** | Downstream 503, network timeout, broker temporarily unavailable | Bounded backoff, safe retry | `error_code`, attempt, next delay, latency |
| **Rate-limited** | HTTP 429 / quota | Honor retry-after if provided and appropriate, add jitter | Safe reason/limit, retry plan |
| **Permanent/schema** | Payload missing required field, unsupported schema version | Do not retry same data indefinitely; DLQ/quarantine or reject per policy | Schema version, violation code, message ID |
| **Business rejection** | Access denied, business rule unsatisfied | Do not auto-retry as transient | Outcome rejected/denied, safe reason |
| **Ambiguous side effect** | Timeout after remote API may have already processed | Reconcile/idempotent retry; do not conclude "unprocessed" | Operation ID, timeout, `outcome=UNKNOWN` |
| **Consumer bug** | `NullPointerException` from code | May need limits, DLQ, and alert; infinite retries do not fix bugs | Exception type, app version, attempt/exhaustion |
| **Resource pressure** | Disk full, OOM risk, connection pool exhausted | Protect infrastructure, shed load, circuit breaker, or pause consumption | Error category, queue lag, health indicators |

Classification must live at the business/adapter layer where sufficient context exists. Classifying solely by exception message strings is fragile. A `TimeoutException` does not guarantee the remote side effect did **not** occur. If the remote operation must not duplicate, use an idempotency key/reconciliation according to the corresponding contract.

A **poison message** is a message that repeatedly fails if retries cannot change the input or required conditions. It can block a partition/queue, amplify a retry storm, and generate noisy logs. There must be attempt limits, a DLQ/parking policy, retention periods, and monitored handling mechanisms.

## 6. Retry Policy: Backoff, Jitter, and Limits

A commonly used strategy is **exponential backoff**:

\[d_n = \min(d_{\max}, d_{\text{base}} \times 2^{n-1})\]

Here `n` is the sequence number of the **upcoming scheduled retry**, starting from 1 (not necessarily the current attempt number in every framework). For example, with a 1-second base and 30-second cap:

| Retry number | Delay without jitter |
| ---: | ---: |
| 1 | 1 second |
| 2 | 2 seconds |
| 3 | 4 seconds |
| 4 | 8 seconds |
| 5 | 16 seconds |
| 6 onward | max 30 seconds per cap |

**Jitter** is controlled randomness added to the retry schedule to prevent thousands of consumers from hitting a downstream service simultaneously right as it recovers. Do not assume a library's jitter formula; *full jitter*, *equal jitter*, and *decorrelated jitter* have different distributions. For downstream rate limits, honor `Retry-After` if protocol and policy allow.

Decisions to publish explicitly:

- Does `max_attempts` mean total handler invocations or only retries?
- Is retry performed immediately in-process or sent to a delayed queue/topic?
- Does the retry delay survive a consumer restart?
- Which errors are retryable, and which go straight to the DLQ?
- Are retries prioritized by priority/tenant, or concurrency-limited?
- When the retry service fails, when is the original message ACKed/committed?
- Are there limits on total processing time, TTL, and circuit breakers?

**Important Warning:** Calling `Thread.sleep(...)` directly inside a message listener can occupy the consumer thread, reducing concurrency and affecting broker heartbeats/polling or partition ordering. For long delays, consider the framework's retry mechanism, delayed queues/topics, or a durable scheduler. Specific mechanisms depend on RabbitMQ, Kafka, and the library used.

## 7. Standalone Java 17: Simulating Transparent Retry Logs

This example uses **JDK 17+**, requiring no broker, SLF4J, or external libraries. It simulates three messages:

1. `msg-101` encounters a transient error for two attempts and succeeds on attempt 3.
2. `msg-202` has a permanent schema error and **requests** a move to the DLQ immediately on attempt 1.
3. `msg-303` always times out, exhausts the maximum of 3 attempts, and then **requests** a move to the DLQ.

To avoid false conclusions, the program uses `message.retry_planned` (merely the decision to retry) and `message.dlq_requested` (merely a move request); it does **not** print `retry_scheduled` or `dlq_confirmed` because it is not connected to a broker. Delays are **planned values**; the program intentionally does not `sleep`, and has no queue or durable ACK. `Clock.fixed(...)` keeps timestamps/output deterministic.

Create the file **`RetryMessageLoggingDemo.java`**:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

public class RetryMessageLoggingDemo {
    record Message(String id, String operationId) {
    }

    static class RetryableFailure extends Exception {
        private final String code;

        RetryableFailure(String code) {
            super(code);
            this.code = code;
        }

        String code() {
            return code;
        }
    }

    static class PermanentFailure extends Exception {
        private final String code;

        PermanentFailure(String code) {
            super(code);
            this.code = code;
        }

        String code() {
            return code;
        }
    }

    static void handle(Message message, int attempt)
            throws RetryableFailure, PermanentFailure {
        if ("msg-101".equals(message.id()) && attempt < 3) {
            throw new RetryableFailure("DOWNSTREAM_TIMEOUT");
        }
        if ("msg-202".equals(message.id())) {
            throw new PermanentFailure("SCHEMA_INVALID");
        }
        if ("msg-303".equals(message.id())) {
            throw new RetryableFailure("DOWNSTREAM_TIMEOUT");
        }
    }

    static void log(Clock clock, String event, Message message,
                    int attempt, String details) {
        System.out.println("at=" + Instant.now(clock)
                + " event=" + event
                + " message_id=" + message.id()
                + " operation_id=" + message.operationId()
                + " attempt=" + attempt
                + " " + details);
    }

    static void consume(Message message, int maxAttempts, Clock clock) {
        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                handle(message, attempt);
                log(clock, "message.processed", message, attempt,
                        "outcome=SUCCESS attempts_used=" + attempt);
                return;
            } catch (PermanentFailure error) {
                log(clock, "message.dlq_requested", message, attempt,
                        "reason=" + error.code()
                        + " outcome=PERMANENT_FAILURE");
                return;
            } catch (RetryableFailure error) {
                if (attempt < maxAttempts) {
                    long delayMs = 1000L << (attempt - 1);
                    log(clock, "message.retry_planned", message, attempt,
                            "next_attempt=" + (attempt + 1)
                            + " delay_ms=" + delayMs
                            + " error_code=" + error.code());
                } else {
                    log(clock, "message.retry_exhausted", message,
                            attempt, "error_code=" + error.code());
                    log(clock, "message.dlq_requested", message,
                            attempt, "reason=RETRIES_EXHAUSTED");
                }
            }
        }
    }

    public static void main(String[] args) {
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-10T02:00:00Z"),
                ZoneOffset.UTC);

        consume(new Message("msg-101", "op-101"), 3, clock);
        consume(new Message("msg-202", "op-202"), 3, clock);
        consume(new Message("msg-303", "op-303"), 3, clock);
    }
}
```

Compile and run:

```bash
javac RetryMessageLoggingDemo.java
java RetryMessageLoggingDemo
```

**Exact stdout:**

```text
at=2026-11-10T02:00:00Z event=message.retry_planned message_id=msg-101 operation_id=op-101 attempt=1 next_attempt=2 delay_ms=1000 error_code=DOWNSTREAM_TIMEOUT
at=2026-11-10T02:00:00Z event=message.retry_planned message_id=msg-101 operation_id=op-101 attempt=2 next_attempt=3 delay_ms=2000 error_code=DOWNSTREAM_TIMEOUT
at=2026-11-10T02:00:00Z event=message.processed message_id=msg-101 operation_id=op-101 attempt=3 outcome=SUCCESS attempts_used=3
at=2026-11-10T02:00:00Z event=message.dlq_requested message_id=msg-202 operation_id=op-202 attempt=1 reason=SCHEMA_INVALID outcome=PERMANENT_FAILURE
at=2026-11-10T02:00:00Z event=message.retry_planned message_id=msg-303 operation_id=op-303 attempt=1 next_attempt=2 delay_ms=1000 error_code=DOWNSTREAM_TIMEOUT
at=2026-11-10T02:00:00Z event=message.retry_planned message_id=msg-303 operation_id=op-303 attempt=2 next_attempt=3 delay_ms=2000 error_code=DOWNSTREAM_TIMEOUT
at=2026-11-10T02:00:00Z event=message.retry_exhausted message_id=msg-303 operation_id=op-303 attempt=3 error_code=DOWNSTREAM_TIMEOUT
at=2026-11-10T02:00:00Z event=message.dlq_requested message_id=msg-303 operation_id=op-303 attempt=3 reason=RETRIES_EXHAUSTED
```

### Step-by-Step Explanation

1. `Message` uses a Java record (supported in JDK 17); `id` is the logical message ID, and `operationId` is the business operation ID. They are preserved across attempts.
2. `RetryableFailure` and `PermanentFailure` represent error classification via distinct types, rather than parsing exception message strings.
3. `maxAttempts=3` consists of **one initial run + up to two retries**. After failing on attempt 3, there is no next attempt.
4. Delays of `1000` and `2000` ms are **planned** exponential backoff values. There is no `Thread.sleep` and no message sent to a broker, so all timestamps are identical due to `Clock.fixed`.
5. `msg-101` succeeds on attempt 3. `message.processed` only means the simulated processing function returned successfully; it does **not** prove an ACK/offset commit or durable side effect persistence.
6. `msg-202` hits a permanent error, so it does not consume the retry budget; it emits `message.dlq_requested` immediately.
7. `msg-303` tries exactly three times, emitting `message.retry_exhausted` and `message.dlq_requested`. Actually delivering the message to a DLQ requires a publisher/transport with confirmation; this example does not do that.
8. No payloads, tokens, or arbitrary exception messages are logged. All IDs and error codes are safe dummy data.

### Upgrading for Real Broker Integration

In a production system, replace the loop in `consume` with:

- A broker adapter receiving messages, carrying reliable ID/correlation/attempt metadata.
- A business handler with idempotency and a clear success/failure contract.
- A retry policy with timers/delayed queues/topics or a durable retry framework.
- Publisher/consumer ACKs to know whether retry scheduling, DLQ routing, and offset commits succeeded.
- Logging at **confirmation boundaries** such as `retry_planned` vs `retry_scheduled`, and `dlq_requested` vs `dlq_confirmed`.

This example demonstrates logging semantics, not production RabbitMQ/Kafka code. Do not use it as a real consumer because it lacks retry delays, broker acknowledgements, durable storage, multi-consumer thread-safety, or process crash recovery.

## 8. SLF4J/Logback: Logging with Message Context

In an application using SLF4J, parameterized logging keeps information more structured than repeated string concatenation:

```java
// SLF4J integration snippet: assume logger and metadata
// are declared and data has been verified as safe to log.
logger.warn(
    "event=message.retry_planned message_id={} attempt={} next_attempt={} " +
    "delay_ms={} error_code={}",
    messageId, attempt, nextAttempt, delayMs, errorCode);
```

This is a **snippet** requiring the SLF4J dependency and declared variables. It is not a standalone Java program. Using placeholders avoids eager string concatenation, though if expensive arguments are built before the call, Java still evaluates them. At high volume, limit verbosity and measure allocations.

### MDC and Context Leakage Across Messages

A consumer thread pool may process message A and then message B on the **same thread**. If the MDC is not cleared, logs for B could carry A's `message_id`/`trace_id`, misleading investigations or leaking data between tenants.

Scoped MDC example (**SLF4J snippet**):

```java
try (org.slf4j.MDC.MDCCloseable messageScope =
             org.slf4j.MDC.putCloseable("message_id", messageId)) {
    // Invoke handler and write logs within the current message scope.
    processMessage();
}
```

You must define `processMessage()`, `messageId`, and a compatible MDC backend. When the scope exits, this key is removed from the MDC by `MDCCloseable`; if code has prior context for the same key or manages multiple keys, there should be a policy to **save and restore the original context** or use a unified scope, rather than blindly clearing context from an enclosing task. With `CompletableFuture`, executors, or async workers, MDC/trace context **does not propagate automatically in all configurations**; use appropriate instrumentation/propagation and test to avoid lost context or cross-request contamination.

**Do not trust headers from producers by default.** An untrusted client might self-report `attempt=999` or `tenant_id=admin`. Fields controlling retries or authorization must be validated and managed within trusted system metadata. Logging can distinguish `reported_attempt` and `internal_attempt` when needed for investigation.

## 9. RabbitMQ: ACK/NACK, Requeue, and DLQ

RabbitMQ consumes messages via broker delivery to a consumer. In the manual acknowledgement model:

- **ACK**: the consumer confirms the delivery was processed per contract; the broker may remove the delivery from the unacked state. It does not by itself prove an external business side effect was committed.
- **NACK/reject with requeue=true**: asks the broker to put the message back for redelivery according to queue semantics. If the error persists, the message can be redelivered continuously, creating a **hot retry loop** and a log storm.
- **NACK/reject with requeue=false**: the broker may dead-letter the message if the queue has a configured dead-letter exchange/routing, or discard it per policy. **Do not assume a DLQ always exists.**
- **DLX/DLQ**: depending on queue type, dead-lettering policy, and configuration, the message may route to an error-handling queue; actual confirmations/status must be observed.

A **delivery tag** is tied to a RabbitMQ channel, not a system-wide stable message ID. Do not use a delivery tag as an idempotency key. The `redelivered` flag indicates a delivery was previously redelivered as known by the broker, but it is insufficient to accurately count all handler attempts or all side effects that have occurred.

When you want to delay a retry:

1. The consumer classifies the transient failure.
2. Chooses the delay/backoff and where the retry will run next, such as a configured delayed/retry queue.
3. Publishes the retry copy, **waiting for publish confirms or an equivalent confirmation mechanism** per policy.
4. Only ACKs the original once there is assurance the message will not be lost between "ACK original" and "publish retry".
5. If publishing fails, do not log "retry scheduled" as fact; report the error and apply the recovery policy.

This is a **business pattern**, not a guarantee that the two steps (publish + ACK) are atomic across all configurations. Gaps or duplicates can occur if a crash/timeout happens between steps. Design idempotency/durable relays to tolerate at-least-once delivery. For RabbitMQ quorum queues and delivery limits or delayed-message plugins, check documentation for the **exact queue type and version** because semantics differ.

### RabbitMQ-Specific Logging

Useful fields: `queue`, `exchange`, `routing_key`, `message_id`, `correlation_id`, `consumer_tag`, `redelivered`, `delivery_tag`, and trusted attempt metadata. Do not log the body by default.

Example event after a retry publish **has been confirmed**:

```json
{
  "event": "message.retry_scheduled",
  "message_id": "msg-71",
  "queue": "payments.retry.5s",
  "attempt": 1,
  "next_attempt": 2,
  "retry_delay_ms": 5000,
  "publish_confirmation": "CONFIRMED"
}
```

The JSON only illustrates a schema; RabbitMQ does not emit this field automatically. If ACKing the original subsequently fails, log the **ACK status** as well and accept the possibility of a duplicate. A successful retry publish does not automatically confirm that the original was ACKed.

## 10. Kafka: How Retries Differ from RabbitMQ

A Kafka consumer reads records by `topic`/`partition`/`offset`. In Kafka, **committing an offset** represents the read progress of a consumer group; it is **not** a per-message ACK like RabbitMQ. A consumer can process a record multiple times if the offset is not committed or if a rebalance/crash occurs. Retry APIs/frameworks use different strategies.

Distinguish these models:

### 10.1. In-Place Retry on the Consumer Thread

The handler holds the current record and retries in the same process. This is simple, but if `sleep` is long or retries block, it can impede consumer polling/heartbeats or stall the partition from advancing, depending on framework/configuration. Log the handler's `attempt`, while **the offset remains the record's offset**; do not assume each attempt gets a new offset.

### 10.2. Retry Topics and Delayed Processing

An application/framework may publish failed records to one or more retry topics with different delays. In that case:

- The retry record may carry a new broker-level metadata/message envelope, but you must **preserve the original message ID/operation ID** for correlation.
- The `topic` and `offset` of the retry record **differ** from the source; they must not be used as the unique identifier of the business operation.
- Committing the source offset and publishing the retry record are two operations that must be designed to avoid loss/duplicates; atomic transaction support depends on Kafka integration and the business data source.
- Retry topics can alter ordering among messages with the same key; if ordering matters, a dedicated policy is required.

### 10.3. When to Log `offset_committed`?

Only after the commit API or framework mechanism reports success per contract. Returning from the handler does not mean the offset is committed; with auto-commit, semantics differ further. If the framework commits in batches, `message.processed` should still be understood as handler success rather than confirming commit of each individual record.

If you need exactly-once processing in a specific Kafka pipeline, study **Kafka transactions**, `read_committed`, idempotent producers, and the application's semantic scope. "Exactly-once processing" in a properly configured Kafka pipeline **does not automatically cover** external side effects outside Kafka such as sending emails, calling payment APIs, or modifying an external database. Logs must reflect that boundary accurately.

### Kafka Fields Useful for Investigation

- `topic`, `partition`, `offset` of the current record and `original_topic/partition/offset` when routed to a retry topic.
- `consumer_group`, `consumer_instance`, and a desensitized `record_key` if needed.
- `message_id`/`operation_id` stable across retries, validated retry headers, and source/ingest timestamps.
- Separate event codes for `rebalance`, `commit_failed`, `retry_topic_publish_failed`, and `replayed`.

Note that high consumer group lag does not by itself prove logs were lost; it reflects group read progress and must be cross-referenced with retry/backlog/handler metrics.

## 11. Idempotency and Reliability During Reprocessing

A primary hazard of message retries is **repeated side effects**. For example, a consumer calls a payment API, the remote server records the transaction, but the response is lost due to a network timeout. If the consumer retries without an idempotency key, it may charge twice. Logging is vital for investigation, but it **does not replace** mechanisms that prevent double effects.

### 11.1. Idempotent Consumer Using a Business Key

One design stores successfully processed `operation_id`/`message_id` values in a DB. When the same message arrives again, the consumer checks and skips the side effect:

```text
Receive message with operation_id=pay-71
BEGIN transaction
  INSERT processed_operations(operation_id=pay-71) if absent
  IF already exists:
      skip duplicate effect
  ELSE:
      apply business state change
COMMIT
ACK/commit progress according to broker contract
```

This is **pseudocode**; it requires a unique constraint and appropriate transaction/isolation levels. Doing a `SELECT` followed by `INSERT` without concurrency constraints lets two workers both see "does not exist" and execute the side effect twice. If the side effect is a call to an external system, a local DB transaction does **not** guarantee atomicity with the external API; you need an idempotency contract, outbox/saga, or reconciliation.

A log for a duplicate might look like:

```text
event=message.duplicate_skipped message_id=msg-71 operation_id=pay-71 reason=already_processed
```

Do not log `message.processed outcome=NEW_SUCCESS` for a skipped duplicate if no new business processing occurred. A message skipped because it was already processed is not an error; it can be logged at INFO/DEBUG and increment an `idempotency_skips_total` metric.

### 11.2. Transactional Outbox

When processing must update a DB and then emit a downstream event, you can write **both the business change and the outbox event in the same transaction**. A publisher reads the outbox and retries when the broker fails. This reduces the risk of "DB committed but event publish lost." However, the publisher may still resend, so the consumer still needs to be idempotent.

Similarly, when moving a failed message to a retry topic/DLQ and then ACKing the original, determine the durability of the handoff; do not claim the routing is atomic unless the broker API or transaction provides that guarantee.

### 11.3. Outcome UNKNOWN

When an external call times out:

```text
event=message.side_effect_outcome_unknown
message_id=msg-71
operation_id=pay-71
error_code=REMOTE_TIMEOUT
next_action=RECONCILE_OR_IDEMPOTENT_RETRY
```

Do not log `payment.failed` as a certainty if the remote system might have already charged. Probe/reconcile by operation ID or retry safely using an idempotency key. In logs, distinguish **a communication failure on the attempt** from **the business effect not having occurred**.

## 12. Retries, Dead-Letter Queues, and Poison Messages

A DLQ/parking queue protects the pipeline from messages that cannot be processed under the current policy. However, a DLQ is not a "trash bin": messages inside may contain sensitive data and require retention policies, access controls, alerting, reprocessing capability, and traceability.

### Moving to a DLQ Requires Two Milestones

1. **`message.dlq_requested`**: the application decides the message will not be retried further and requests routing.
2. **`message.dlq_confirmed`**: a component/broker confirms per contract that the message was received at the corresponding DLQ destination.

If the broker mechanism dead-letters directly upon NACK/reject, the application may only know it "requested the broker to apply the policy" without per-message confirmation in the DLQ. In that case, do not pretend it is confirmed; combine broker metrics, DLQ consumers/inspection, and end-to-end tests to verify.

Useful information when exhausted:

```json
{
  "event": "message.retry_exhausted",
  "message_id": "msg-303",
  "operation_id": "op-303",
  "attempt": 5,
  "max_attempts": 5,
  "first_attempt_at": "2026-11-10T02:00:00Z",
  "last_attempt_at": "2026-11-10T02:01:14Z",
  "error_code": "DOWNSTREAM_TIMEOUT",
  "terminal_policy": "DLQ",
  "outcome": "RETRIES_EXHAUSTED"
}
```

This is a **schema example**, not an actual log. If an operator later replays the message, keep `original_message_id`/`operation_id`, add `replay_id`, `replay_reason`, actor/approver per policy, and link the old/new lifecycles. Do not delete old retry history or reset IDs in a way that loses the investigation trail.

### Do Not Replay the DLQ Indefinitely

A poison message may continue failing after a replay. Limit replay rounds, control who is permitted to replay, verify that the version/schema has been fixed, separate replay traffic from business traffic, and have a kill switch if a log storm is detected. Replays require auditing because they can re-trigger side effects.

## 13. Metrics and Tracing Alongside Retry Logs

Per-attempt logging helps investigate individual messages, but system-wide monitoring should have independent metrics:

| Suggested metric | Definition | Avoid confusing |
| --- | --- | --- |
| `messages_received_total` | Deliveries observed at the consumer | Not equal to unique logical messages |
| `message_processing_attempts_total` | Handler executions run | Can exceed deliveries with in-process retries |
| `message_retry_planned_total` | Times policy chose to retry | Broker may not have accepted scheduling |
| `message_retry_scheduled_total` | Times scheduling was confirmed | Does not prove the next attempt ran |
| `messages_processed_total` | Successful handler completions per contract | Does not prove ACK/offset commit |
| `message_processing_failures_total` | Failed attempts, by error category | Differs from final failed logical messages |
| `message_retries_exhausted_total` | Logical messages that exhausted retry budget | Does not prove DLQ success |
| `message_dlq_failures_total` | Failed DLQ moves or publish routes | Needs dedicated alert |
| `message_duplicate_skips_total` | Deliveries skipped due to idempotency | Not message loss |
| `message_processing_duration_seconds` | Histogram of handler duration | Excludes queue residence unless defined so |
| `message_retry_delay_seconds` | Distribution of chosen/actual delays | Do not mix planned and actual |
| `message_age_seconds` / `retry_queue_lag` | Latency from original event to processing time | May differ from broker consumer lag |
| `broker_commit_failures_total` | ACK/offset commit errors by adapter | Names and semantics vary by broker |

These names are suggestions and are not built into every framework. With Prometheus/metrics, **do not use `message_id`, `operation_id`, or `trace_id` as metric labels** due to massive cardinality. Use bounded-value labels like `service`, `consumer_group`, `error_category`, `outcome`, and controlled topic/queue names. Detailed IDs belong in logs/traces, not metric labels.

### Trace Context Across Retries

An original message carries trace context propagated by the producer. Across retries, you can maintain links to the original trace via parent context or span links depending on instrumentation/semantics:

- Do not force all attempts spaced hours apart into a single long-running continuous span.
- Create a span per delivery/processing attempt when the tracing stack supports it, keeping `message_id`/`operation_id` for correlation.
- Validate tracing headers from untrusted sources per policy.
- When executors/async listeners switch threads, context propagation and cleanup must be tested—do not assume MDC/`ThreadContext` always propagates properly.

Investigation typically starts with `message_id` and follows event codes `retry_planned`, `retry_scheduled`, `processed`, `acknowledged`, or `dlq_confirmed`. If the trailing events are missing, determine whether the worker crashed, the log sink dropped data, the broker action failed, or the system simply hasn't indexed yet.

## 14. How Logging Failures Can Make Retries Worse

If every retry produces large logs and the system retries in bulk, the logging sink can become a bottleneck:

- **Sync logging** can block the consumer thread on I/O, increasing processing latency.
- **Async logging** has a bounded queue; when full, it may block the producer or drop logs depending on policy.
- **Collector outages** delay or drop logs; never use log line counts as the sole count of processed messages.
- **Repeated stack traces** create huge volume, reducing log shipper throughput and increasing retention/storage costs.
- **Sensitive logs from payloads/exceptions** can spread widely across collectors, DLQs, and dashboards.

Separate at least four metrics: message handler attempts, application-policy-filtered logs, logging queue drops, and actual broker redeliveries. If a dashboard shows fewer retry logs, errors have not necessarily decreased—log levels/sampling or the logging pipeline may be congested.

If audit/critical events must not be lost, design a dedicated durable path and an approved fail-open/fail-closed policy. **Do not rely on a general logging appender as the sole basis for deciding ACKs**; broker acknowledgement must be based on processing results and delivery policy, not on whether a log was printed.

## 15. Timing and Ordering During Message Retries

A message might be published at 09:00, run attempt 1 at 09:01, retry attempt 2 at 09:03, and reach the DLQ at 09:20. Separate these timestamps:

- `produced_at`: when the producer created the message (clear origin and trust level).
- `first_received_at`: when the consumer first observed the message.
- `attempt_started_at` and `attempt_finished_at`: boundaries of each handler attempt.
- `retry_planned_at` / `retry_scheduled_at`: when policy decided and when the scheduler/broker confirmed.
- `next_attempt_at`: earliest expected time, not necessarily exact worker start time.
- `last_failure_at`: when the last error occurred.
- `dlq_requested_at` / `dlq_confirmed_at`: two distinct milestones.
- `ingested_at`: when the collector/indexer received the log, which may be delayed by queuing.

Use `Instant`/ISO-8601 with an explicit offset for storing timestamps; use `System.nanoTime()` to measure **durations within the same JVM**, never as an epoch timestamp across services. Clock skew can make timestamps across two machines appear out of order; combine attempt sequences, broker offsets, business versions, causal links, and event IDs.

**Ordering** depends on the broker and retry approach:

- A Kafka partition has ordering by record offset **within that partition**, but routing failures to a retry topic allows newer records to overtake waiting records.
- RabbitMQ requeues and multiple consumers can cause delivery/processing order to differ from publish order.
- Async/scheduled retries may run on different workers, not preserving the original request order.

If business logic requires strict per-key ordering, design partitioning/serial execution and a specialized retry policy; do not assume order is preserved just because log timestamps increase monotonically.

## 16. Logging Test Scenarios for Retries

A test suite should verify both **positive paths** and **negative paths**:

| Code | Scenario | Correct log | What must not happen |
| --- | --- | --- | --- |
| R1 | Success on attempt 1 | `processed` with `attempt=1`, outcome SUCCESS | No retry/exhausted events |
| R2 | Transient fail then success | `retry_planned`/`scheduled` at proper milestones, then `processed` | No terminal FAILED when it ultimately succeeded |
| R3 | Permanent invalid schema | `dlq_requested` or reject per policy on first attempt | No infinite retries |
| R4 | Max attempts exhausted | `retry_exhausted` with count, reason, and terminal policy | No next attempt beyond limit |
| R5 | Retry publish fails | `retry_publish_failed`, original retained/handled per policy | No false `retry_scheduled` success |
| R6 | DLQ publish fails | `dlq_publish_failed` with alert/metric | No `dlq_confirmed` without confirmation |
| R7 | Handler succeeds then crashes before ACK/commit | Redelivery may arrive; idempotent skip | No second business side effect |
| R8 | Remote timeout after side effect | `outcome=UNKNOWN`, reconciliation/idempotency | Do not claim side effect definitely failed |
| R9 | Invalid or missing retry header | Default/validation policy with safe log | Do not trust arbitrary retry count/tenant input |
| R10 | Consumer rebalance during processing | Log includes group/partition/instance and commit status | Do not treat handler return as offset commit |
| R11 | 1,000 messages fail simultaneously | Metrics and log volume within budget | No log storm exhausting queue/CPU |
| R12 | DLQ replay after bug fix | Links original ID, replay ID, and actor | Do not lose prior retry history |
| R13 | Collector down during retries | Message processing follows policy and log loss is measured | Do not assume missing logs = no retries |
| R14 | Message contains dummy secret | Logs contain only approved metadata | No raw secret leaked to logs, DLQ, or traces |

### How to Implement Integration Tests

1. Create test messages with unique `message_id` and `operation_id`.
2. Simulate a downstream transient error for a deterministic number of times, then recover.
3. Verify handler attempt counts, retry delays, scheduling acknowledgement timing, and actual business effects.
4. Trigger a permanent error; verify no unintended retries occur and observe DLQ/parking per contract.
5. Stop the consumer after the side effect but before the broker ACK; restart and verify no extra side effect occurs due to idempotency.
6. Force retry/DLQ publish failures to prove log events **do not report success before confirmation**.
7. Measure log volume, queue depth, CPU, p95/p99 handler latency, consumer lag, and visibility latency.
8. Query centralized logs by message ID, checking correlation/tracing, exception codes, and absence of sensitive raw payloads.
9. Clean up the test environment and verify no leftover test messages or temporary queues affect real users.

If using a real broker, set clear timeouts and cleanup; a test asserting "exact log count immediately after the handler" may flake due to asynchronous appenders/collectors. Wait with a deadline, distinguishing **did not reach the sink** from **not yet searchable**.

## 17. Runbook for Abnormal Retry Spikes

When `retry_attempts_total`/`retry_exhausted_total` alerts spike:

1. **Determine scope:** queue/topic, consumer group, service release, time window, error category, and number of affected logical messages.
2. **Separate signals:** how many deliveries, processing attempts, exhausted messages, and duplicate skips? Avoid counting ERROR lines as broken messages.
3. **Identify error source:** downstream 5xx/timeouts, schema changes, invalid auth, rate limits, DB outage, poison messages, or consumer bugs.
4. **Inspect retry policy:** max attempts, backoff, jitter, queue capacity, pending/retry topic lag, hot requeues, and concurrency.
5. **Check broker ACK/offsets:** are there unexpected redeliveries from crashes/rebalances/commit failures? Did retry publishes succeed while original ACKs failed, causing duplicates?
6. **Assess side effects:** could the business operation have partially succeeded? Are idempotency keys and reconciliation in place?
7. **Check the DLQ:** did exhausted messages actually enter the DLQ? Does the DLQ have proper permissions/quotas/retention? Is anything stuck at the publish step?
8. **Shed load safely:** per policy, reduce concurrency, trip circuit breakers, increase backoff, cap retry storms, and fix root causes; do not disable auditing or delete uninvestigated messages.
9. **Verify recovery:** processing success rate rises, consumer lag drops, queue backlog drains, and log visibility and error metrics return to normal.
10. **Prevent recurrence:** add regression tests for schemas, retry policies, dedup/ACK boundaries, and dashboards/tracing.

If a poison message repeating the same ID heats up a partition, do not choose "retry forever until fixed." Have a monitored terminal policy, triage workflow, and safe replay capability.

## 18. Common Design and Logging Mistakes

| Mistake | Why it is dangerous | How to fix |
| --- | --- | --- |
| Printing `ERROR` + stack trace on every attempt | Log storm hides root cause and clogs logging pipeline | Event codes, bounded verbosity, summaries, and metrics |
| No stable message ID | Cannot correlate retries across consumer instances/topics | Attach application-level ID, preserve original ID across retries |
| `attempt=0` in one place, `attempt=1` in another | Dashboards and policies miscount | Document contract, use one convention, and test boundaries |
| Confusing max retries with max attempts | Retries too many or too few times | Define total handler invocations vs retry count |
| Logging "retry scheduled" before publish confirm | Reports false success when broker is failing | Planned → confirmation/failure events |
| Logging "DLQ complete" right after NACK | Unknown if DLX actually routed/persisted | Check broker semantics and DLQ evidence |
| Relying on log calls to ACK messages | Log sink does not guarantee business outcome | ACK/commit based on processing + durable policy |
| Retrying all validation errors | Poison messages burn resources | Classify permanent/transient and DLQ |
| Reading retry count from untrusted headers | Bypasses policy, misroutes tenants, or over-retries | Validate and use internal attempts |
| Using broker offset/delivery tag as business ID | Unstable across retries or connections | Separate operation ID / idempotency key |
| Long `Thread.sleep` inside listener | Blocks thread/partition, may affect poll/heartbeat | Scheduled retry / delayed queue or proper policy |
| Not idempotent when ACKs are lost | Same side effect executes multiple times | DB unique constraint / outbox / idempotency key |
| Retrying remote timeout and assuming "unprocessed" | Double charge/mutation | `UNKNOWN` outcome + reconciliation |
| Logging raw payloads and headers on error | Leaks PII/secrets to centralized logs | Log only safe metadata, error codes, redaction |
| Not monitoring DLQ publish errors | Messages stuck/lost from investigation | Metrics/alerts and tested failure paths |
| Measuring only log lines instead of attempts | Log sampling/drops create false numbers | Business metrics and broker counters |
| Reusing MDC across messages | Wrong correlation / tenant leakage | Scoping, cleanup, propagation tests |
| Judging ordering solely from timestamps | Async retries reorder / clock skew | Version/offset/attempt sequence and causal links |

## 19. Practical Implementation Checklist

- [ ] Are message ID, operation ID, correlation ID, and attempt/delivery counts clearly defined?
- [ ] Are handler attempts, broker deliveries, and retry publishes distinguished?
- [ ] Does the error classifier identify transient/permanent/ambiguous errors with unit tests?
- [ ] Are max attempts, exponential backoff, jitter, and total retry TTL configured and tested?
- [ ] Do `retry_planned`, `retry_scheduled`, and `retry_publish_failed` have distinct meanings?
- [ ] Are `dlq_requested` and `dlq_confirmed` emitted only at the exact acknowledgement boundary?
- [ ] Is ACK/offset commit kept distinct from handler success?
- [ ] Is the consumer idempotent for business side effects, handling duplicates and `UNKNOWN` outcomes?
- [ ] Do logs include message ID, attempt, reason code, next delay, service, consumer instance, and appropriate broker context?
- [ ] Are raw payloads, secrets, tokens, and untrusted exception messages excluded from logs?
- [ ] Is MDC/trace context propagated and cleaned up properly across thread pools/async boundaries?
- [ ] Are there metrics for attempts, retry planned/scheduled, exhausted, DLQ failures, and idempotency skips with bounded labels?
- [ ] Have transient recovery, permanent invalid, process crash, rebalance, publish failure, and DLQ replay been tested?
- [ ] Are dashboards/alerts in place for retry storms and poison messages?
- [ ] Are there runbooks, owners, DLQ handling permissions, and sufficient retention for investigation?
- [ ] Is there a rollback procedure when changing retry policies without losing audit trails?

**Completion Criteria:** You can explain a message's lifecycle across multiple attempts, distinguish planned from confirmed at broker boundaries, avoid confusing ACK with handler success, design retry logs sufficient for investigation without leaking payloads, and run the Java 17 example with output matching the table.

## 20. Self-Check Questions

1. A message is delivered twice by the broker, but the handler retries three times on the first delivery: how can `delivery_attempts` and `processing_attempts` differ?
2. Why should `message_id` and `operation_id` not be replaced by a Kafka offset or RabbitMQ delivery tag?
3. When a handler fails because data is missing a required field, what makes retrying multiple times dangerous?
4. What is the difference between `message.retry_planned` and `message.retry_scheduled`?
5. When publishing to a DLQ fails after ACKing the original, what incident can occur?
6. Why does a client timeout after calling a payment API not prove the payment was not executed?
7. A Kafka consumer processes a record successfully but crashes before committing the offset; what happens and what mechanism is needed?
8. Why can a retry topic alter the ordering of messages with the same key?
9. Why do per-attempt logs not replace a total processing attempts metric?
10. When every attempt prints an ERROR stack trace, how can the logging pipeline impact the consumer itself?
11. How do you ensure logs for message B do not carry the MDC/trace ID of message A in a thread pool?
12. Does Kafka's support for exactly-once semantics within a pipeline guarantee an external email or payment API executes only once?
13. What should be logged when a retry publisher returns a timeout and it is unknown whether the broker received the message?
14. When an operator replays a DLQ message, which IDs/milestones must be preserved to investigate the full history?
15. Why does the `RetryMessageLoggingDemo` example not print `dlq_confirmed` even though it has a DLQ decision branch?

## References

- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms) — distinguishing consumer and publisher acknowledgements.
- [RabbitMQ — Negative Acknowledgements](https://www.rabbitmq.com/docs/nack) — requeue/reject semantics and redelivery risks.
- [RabbitMQ — Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx) — dead-lettering configuration and behavior.
- [Apache Kafka — Consumer Configuration](https://kafka.apache.org/documentation/#consumerconfigs) — offset commits, polling, and consumer progress.
- [Apache Kafka — Delivery Semantics](https://kafka.apache.org/documentation/#semantics) — delivery guarantees and limits of exactly-once.
- [Spring for Apache Kafka — Non-Blocking Retries](https://docs.spring.io/spring-kafka/reference/retrytopic.html) — retry topics and ordering tradeoffs.
- [SLF4J Manual](https://www.slf4j.org/manual.html) — parameterized logging, logger API, and MDC.
- [Oracle Java SE 17 — Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html) — injectable clock / deterministic testing.
- [Oracle Java SE 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html) — explicit timestamps in logs.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) — sensitive data, event signals, and log protection.
