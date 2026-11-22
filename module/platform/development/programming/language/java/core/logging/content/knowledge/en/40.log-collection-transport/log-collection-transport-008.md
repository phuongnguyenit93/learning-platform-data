# Log Transport Retry in Java Core Logging

## 1. What Is Transport Retry?

In a logging system with a collector or centralized log store, **transport retry** is the act of re-attempting to send a log event or a batch of logs when the previous transmission was not confirmed as successful according to the transport contract. This is a step in the **log pipeline**, not the re-execution of the business operation that originally generated the log.

~~~text
Java application
       |
       v
Logger / Handler / Appender
       |
       v
Local buffer / queue / file spool
       |
       v
Exporter / log shipper
       |
    send batch --------------------+
       |                           |
       v                           v
Collector / gateway            Network failure
       |                           |
       v                           v
Response / acknowledgment     Retry policy
       |                           |
       +--> accepted               +--> delay, retry,
            (per contract)              or stop
       |
       v
Index / durable store (may be a later step)
~~~

For example, a Java application records an `order_loaded` event. The exporter batches 100 events and sends an HTTP request to the collector; the collector temporarily returns `503`. The exporter can retain the batch and resend it after a delay. If the application **re-runs `loadOrder()` itself** just because the exporter failed to send the log, we have conflated two different types of retries and risk creating duplicate business side effects.

A well-designed logging system must clearly answer four questions:

1. **At which layer should retries happen?** Appender, log shipper, collector exporter, or application?
2. **What counts as success?** HTTP 202, broker ACK, collector having enqueued the data, or durable storage?
3. **When should retries stop?** By attempt count, data age, elapsed time, error type, or resource limits?
4. **What if the send outcome is ambiguous?** You may get duplicates, lost records, or both depending on the design.

**Important distinction:** `logger.info(...)` returning normally does not mean the event has reached the collector. It may have only been accepted into a local queue, buffer, or file. Similarly, `send()` not throwing an exception does not guarantee that the final log store has confirmed durable persistence.

## 2. Which Errors Can Be Retried?

Not every transport failure should be retried. Failures must be classified by **recoverability** and the **destination's contract**.

| Outcome group | Common scenarios | How to handle |
| --- | --- | --- |
| **Accepted / confirmed** | Destination returns acknowledgment per contract | Mark the batch/event complete at the corresponding delivery layer |
| **Transient / retryable** | Temporary connection drop, overloaded destination, `503`, sometimes `429` | Bounded retry, backoff, jitter; respect guidance from destination |
| **Permanent / non-retryable** | Invalid payload schema, bad encoding, persistent config error | Do not retry indefinitely with the same data; classify, quarantine, and alert |
| **Ambiguous / unknown** | Timeout after sending request; connection lost before receiving ACK | Destination may have already received it; retrying requires dedup/idempotency policy |
| **Partial success** | Some events accepted, others rejected/retryable | Handle only the unsuccessful portion per API semantics; avoid blind resend |

Some HTTP examples as a **design starting point**, not fixed rules for every collector:

- `429 Too Many Requests`: usually a rate-limiting signal; check `Retry-After` and backpressure policies.
- `500`, `502`, `503`, `504`: usually worth bounded retries; first check API documentation, deduplication support, and cost.
- `408 Request Timeout`, connection timeout, or I/O exception: may be retried, but the outcome of the previous attempt **may be unknown**, especially after the request was sent.
- `400 Bad Request`: usually an invalid payload; resending without changing the data will not help. Some systems return per-record error details.
- `401`/`403`: usually an authentication/authorization issue; handle credentials/config through a separate flow, **do not hot-retry**.
- `413 Content Too Large`: usually requires reducing batch size or adjusting limits, not resending the whole batch indefinitely.
- `404` or wrong URL: usually requires fixing the endpoint/config, not blind retries.

**Do not rely solely on the status code** if the collector defines special semantics. For example, an API might return `200` with a body reporting partial failures, or `202` confirming only that the payload was queued. The receiving system's contract determines success and retry policy.

## 3. Retrying Does Not Equal Durable Storage

Let us separate the milestones in an event's lifecycle:

~~~text
EVENT_CREATED
    |
    v
ACCEPTED_BY_LOCAL_BUFFER
    |
    v
SENT_BY_EXPORTER
    |
    v
RECEIVED_OR_ACKED_BY_COLLECTOR
    |
    v
INDEXED_OR_DURABLY_STORED
~~~

Depending on the infrastructure, an acknowledgment at the `RECEIVED` step may **not** prove `DURABLY_STORED`. TCP finishing sending bytes does not prove the destination application parsed, accepted, or persisted the data. Even HTTP `2xx` only means what the specific contract defines.

When designing logging, clearly define the **delivery guarantee**:

- **Best effort:** may drop on error, congestion, or shutdown; trades reliability for lower overhead.
- **At-most-once:** avoids duplicate sends, but may lose data when send outcomes are ambiguous.
- **At-least-once:** retries until an ACK is received per policy; reduces data loss on transient errors, at the cost of **possible duplicates**.
- **Exactly-once at the final destination:** requires specific acknowledgment, transaction/dedup mechanisms across the entire path; cannot be inferred merely because the exporter retries.

Audit logs or critical business logs may need stronger delivery channels than routine diagnostic logs. When integrity is mandatory, consider a persistent queue, outbox/inbox, event IDs, acknowledgments, integrity checks, and an appropriate independent storage system. **Retry is only one part of reliability, not a standalone guarantee.**

## 4. Exponential Backoff and Jitter

An exporter must not immediately resend on `503` errors without a delay. Hot retries add load precisely when the collector is already overloaded, increasing queue depth, network traffic, and cost.

A simple backoff schedule:

\[
d_n = \min(d_{max}, d_0\, 2^{n-1})
\]

Where:

- `n`: number of **failed** send attempts, starting at 1.
- `d0`: initial wait time, for example 250 ms.
- `dMax`: cap, for example 2,000 ms.

| Failed attempt | Delay per formula (d0=250 ms, max=2,000 ms) |
| --- | ---: |
| 1 | 250 ms |
| 2 | 500 ms |
| 3 | 1,000 ms |
| 4 | 2,000 ms |
| 5 and beyond | 2,000 ms |

Such a uniform sequence easily causes thousands of clients to retry simultaneously and trigger a **thundering herd**. Therefore, in production, **jitter** (randomness) is usually added to spread out retry times. An example:

~~~text
cappedDelay = min(maxDelay, baseDelay * 2^(failureCount - 1))
actualDelay = random(0, cappedDelay)      # full jitter
~~~

Some systems use equal jitter or decorrelated jitter. There is no single optimal formula; choose based on load, SLA, collector type, and latency requirements. Set a **total retry limit**, per-request timeout, maximum total allowed duration, and final action when the budget is exhausted.

**`Retry-After`:** if the destination returns this header with a corresponding response, parse it as seconds or an HTTP date, use an appropriate clock, and cap the wait duration per policy. Do not arbitrarily add or multiply it with backoff without clear rules; the goal is to respect the receiver's pace while still protecting the local buffer.

**Distinguish four values:** `connectTimeout`, `requestTimeout`, `backoffDelay`, and `maxRetryAge`. A send waiting 5 seconds for a response does not mean waiting 5 seconds before retrying; timeout and delay are two separate decisions.

## 5. Standalone Java 17 Example: Simulating an Exporter Retry Policy

This example uses only **Java SE 17 and JUL**, requiring no broker or network service. A mock `Transport` returns scripted outcomes for easy verification:

- `batch-1`: two transient errors, then ACK on attempt 3.
- `batch-2`: permanent error on attempt 1.
- `batch-3`: attempt 1 outcome unknown, followed by transient errors, exhausting all 4 attempts.

To keep the example fast with **deterministic stdout**, the program **only computes and logs the delay schedule** without actually calling `Thread.sleep`. It models **retry logic**, not network transport, persistent queues, jitter, or receiver deduplication. Message payloads are not printed to the log.

Create **`LogTransportRetryDemo.java`**:

~~~java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LogTransportRetryDemo {
    private static final int MAX_ATTEMPTS = 4;

    enum SendResult {
        ACKED, RETRYABLE, PERMANENT, UNKNOWN
    }

    enum Outcome {
        DELIVERED, PERMANENT_FAILED, EXHAUSTED
    }

    record Batch(String batchId, String eventName) {}

    interface Transport {
        SendResult send(Batch batch);
    }

    private static Transport scripted(SendResult... results) {
        if (results.length == 0) {
            throw new IllegalArgumentException("Missing results");
        }
        return new Transport() {
            private int index;

            @Override
            public SendResult send(Batch batch) {
                if (index < results.length) {
                    return results[index++];
                }
                return results[results.length - 1];
            }
        };
    }

    private static long backoffMillis(int failedAttempt) {
        long base = 250L;
        long cap = 2_000L;
        return Math.min(cap, base << (failedAttempt - 1));
    }

    private static Outcome deliver(
            Batch batch, Transport transport, Logger logger) {
        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            SendResult result = transport.send(batch);

            if (result == SendResult.ACKED) {
                logger.info("event=transport_confirmed batchId="
                        + batch.batchId() + " attempt=" + attempt);
                return Outcome.DELIVERED;
            }

            if (result == SendResult.PERMANENT) {
                logger.warning("event=transport_rejected batchId="
                        + batch.batchId() + " attempt=" + attempt);
                return Outcome.PERMANENT_FAILED;
            }

            if (attempt == MAX_ATTEMPTS) {
                logger.severe("event=transport_exhausted batchId="
                        + batch.batchId() + " attempt=" + attempt
                        + " lastResult=" + result);
                return Outcome.EXHAUSTED;
            }

            logger.warning("event=transport_retry_scheduled batchId="
                    + batch.batchId() + " attempt=" + attempt
                    + " result=" + result
                    + " delayMs=" + backoffMillis(attempt));
        }
        throw new AssertionError("Unreachable");
    }

    private static Logger loggerWithStdoutHandler() {
        Logger logger = Logger.getLogger("demo.transport.retry");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);

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
        handler.setLevel(Level.ALL);
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
        Logger logger = loggerWithStdoutHandler();
        try {
            Outcome first = deliver(
                    new Batch("batch-1", "order_loaded"),
                    scripted(SendResult.RETRYABLE,
                            SendResult.RETRYABLE,
                            SendResult.ACKED),
                    logger);

            Outcome second = deliver(
                    new Batch("batch-2", "order_loaded"),
                    scripted(SendResult.PERMANENT),
                    logger);

            Outcome third = deliver(
                    new Batch("batch-3", "order_loaded"),
                    scripted(SendResult.UNKNOWN,
                            SendResult.RETRYABLE,
                            SendResult.RETRYABLE,
                            SendResult.RETRYABLE),
                    logger);

            int delivered =
                    (first == Outcome.DELIVERED ? 1 : 0)
                    + (second == Outcome.DELIVERED ? 1 : 0)
                    + (third == Outcome.DELIVERED ? 1 : 0);

            logger.info("event=summary delivered=" + delivered
                    + " failed=" + (3 - delivered));
        } finally {
            for (Handler handler : logger.getHandlers()) {
                logger.removeHandler(handler);
                handler.close();
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac LogTransportRetryDemo.java
java LogTransportRetryDemo
~~~

**Exact stdout of the example:**

~~~text
WARNING: event=transport_retry_scheduled batchId=batch-1 attempt=1 result=RETRYABLE delayMs=250
WARNING: event=transport_retry_scheduled batchId=batch-1 attempt=2 result=RETRYABLE delayMs=500
INFO: event=transport_confirmed batchId=batch-1 attempt=3
WARNING: event=transport_rejected batchId=batch-2 attempt=1
WARNING: event=transport_retry_scheduled batchId=batch-3 attempt=1 result=UNKNOWN delayMs=250
WARNING: event=transport_retry_scheduled batchId=batch-3 attempt=2 result=RETRYABLE delayMs=500
WARNING: event=transport_retry_scheduled batchId=batch-3 attempt=3 result=RETRYABLE delayMs=1000
SEVERE: event=transport_exhausted batchId=batch-3 attempt=4 lastResult=RETRYABLE
INFO: event=summary delivered=1 failed=2
~~~

**Stderr:** empty on a successful run. The standard JUL `ConsoleHandler` normally writes to stderr, but this example **does not use `ConsoleHandler`**; the custom `Handler` explicitly writes to stdout and the formatter strips dynamic timestamps.

### Case-by-Case Explanation

- `batch-1`: attempts 1 and 2 return `RETRYABLE`. The policy schedules delays of 250 ms and 500 ms; attempt 3 receives `ACKED`, so retries stop.
- `batch-2`: `PERMANENT` stops immediately, avoiding a retry storm with an invalid payload.
- `batch-3`: `UNKNOWN` means **we do not know whether the destination received the previous attempt**. When retrying in a real system, you must accept possible duplicates or rely on receiver deduplication. After attempt 4, it becomes `EXHAUSTED`.
- `MAX_ATTEMPTS=4` means **four total send attempts**, not four retries after the initial attempt.
- `backoffMillis` demonstrates capped exponential backoff without **jitter**; the code does not sleep or persist data to disk. Thus, the `retry_scheduled` line only models **policy intent/schedule**, not an actually running timer.
- `Batch.eventName` is part of the object but is not logged in the event line; backend message IDs or metadata can be classified as needed. Avoid printing the full batch payload on every retry.

**Do not put this simulation code directly into production.** A real exporter needs queue preservation, async/timeout handling, cancellation, thread management, retry budgets, backpressure, acknowledgment signals, and restart handling.

## 6. Sending Over HTTP in Java: Recognizing Outcomes and Controlling Timeouts

A real HTTP exporter can use JDK 17's `java.net.http.HttpClient`. The snippet below **only illustrates a single send**, not a standalone program or a complete retry loop:

~~~java
// Integration snippet; client, endpoint, ndjson, and batchId are already created.
// endpoint must be an approved collector destination.
HttpRequest request = HttpRequest.newBuilder(URI.create(endpoint))
        .timeout(Duration.ofSeconds(5))
        .header("Content-Type", "application/x-ndjson")
        .header("X-Batch-Id", batchId)
        .POST(HttpRequest.BodyPublishers.ofString(
                ndjson, StandardCharsets.UTF_8))
        .build();

HttpResponse<Void> response =
        client.send(request, HttpResponse.BodyHandlers.discarding());

int status = response.statusCode();
~~~

Imports required for integration:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
~~~

Based on `status`, apply a policy **tailored to the collector in use**. For instance, `429` may require `Retry-After`; `503` may be retryable; `400` may require quarantining the payload. Handle `IOException`, timeouts, and `InterruptedException` from `send`. If you catch `InterruptedException` without rethrowing, you should normally restore the interrupt flag via `Thread.currentThread().interrupt()`, rather than silently continuing to retry while the system is trying to shut down.

**`X-Batch-Id` is only an example header.** It does not automatically enable idempotency. Only when the collector is designed to accept this ID, store state, and deduplicate per contract does it prevent duplicate ingestion. Some collectors do not understand this header or ignore it completely.

**Do not read `response.statusCode() == 200` and assume every event is persisted.** Check the list of supported success statuses, the response body (if partial success exists), async status behavior, and endpoint permissions.

## 7. Queues, Buffers, and Backpressure During Transport Outages

If the collector is unavailable for 30 minutes, per-request retries do not answer **where new events will go**. You need a buffering and backpressure policy:

| Design | Advantages | Risks / conditions |
| --- | --- | --- |
| In-memory queue | Fast, reduces I/O | Lost on process crash/restart; can exhaust heap |
| File spool / persistent queue | Can survive restarts when configured properly | Disk full, permissions, corruption, durability, operational complexity |
| Block producer when queue is full | Reduces drops if upstream can wait | Logging can slow down or stall main requests |
| Controlled drop | Protects the main application | Must track dropped log counts and acceptable loss |
| Sampling / reduced verbosity | Reduces load for diagnostic logs | Not suitable for all log types, especially mandatory audit logs |
| Priority / audit channel separation | Guarantees resources for critical events | Requires independent design, policy, and monitoring |

**Unbounded buffers are not a solution.** During a prolonged collector outage, an unbounded in-memory queue can cause a JVM OOM; an unbounded disk queue can fill the filesystem and affect other applications. The design must enforce maximum capacity/age limits and define actions when thresholds are exceeded.

For data that must be retained, decide whether the application will **fail closed, block, write to a durable outbox, or report an explicit error** when it cannot persist logs. For routine diagnostic logs, protecting application availability may matter more than waiting indefinitely. This trade-off must be explicitly decided in SLOs/policies, not left as an unknown side effect of the appender.

### Retry in the Application or in the Collector?

- **Appender/exporter in Java:** suitable when the library provides battle-tested queuing, retry, circuit breaking, or persistent storage. Do not hand-roll transport retries at every call site.
- **Host or sidecar agent/log shipper:** the application writes to stdout/file, and the agent handles reading, buffering, retrying, and shipping. The application does not wait on a network exporter per request.
- **Intermediate collector:** can receive from many agents and retry toward the downstream store. In this case, an acknowledgment from the collector may only confirm receipt into an intermediate queue.

**Assign one layer to own retries per hop**, while understanding that other layers may also retry on their own hops. If the application retries HTTP, the agent retries, and the collector retries without a shared retry budget, **retry amplification** occurs; a minor disconnect can generate far more requests than normal traffic.

## 8. Unknown Send Outcomes and Duplicate Risk

A commonly misunderstood scenario:

~~~text
Exporter                       Collector
   |                               |
   | --- POST batch-42 ----------> |
   |                               | accepted batch
   |  X response lost / timeout    |
   |
   | --- POST batch-42 again ----> |
   |                               | duplicate possible
~~~

If the exporter times out **after** the collector has already accepted the batch, it lacks enough information to be sure the first attempt failed. Retrying improves **at-least-once delivery** reliability, but can also produce duplicate logs.

Deduplication strategies:

1. Assign a unique `eventId` to each event at the source, or a stable `batchId` for a **fixed** set of events.
2. When retrying, **keep the same ID** and corresponding batch contents; do not mint a new ID for the same event just because it is a retry.
3. The destination needs a real dedup/idempotency mechanism with retention covering the retry window, and must handle races between duplicate requests.
4. Keep transport metadata (`attempt`, `lastErrorCode`, `firstSeenAt`) separate; do not turn each retry into a new business event.
5. Verify with tests simulating lost ACKs, timeouts, and restarts to know when duplicates occur.

**Do not conflate two levels of duplication:** an event can be emitted **twice from Java** due to logger hierarchy/handler duplication, whereas another event is emitted once but **re-sent by the exporter**. Distinguish the source of duplication when investigating.

If the collector supports **partial success**, do not automatically resend the entire batch without inspecting the response contract. You may need to retry only the unaccepted events or accept duplicate risk to preserve data according to policy.

## 9. Batching, Ordering, Size Limits, and Retries

Logs are typically sent in batches to reduce network overhead. However, batching introduces additional considerations:

- **Batch size:** too large can trigger `413` and increase latency and memory usage; too small increases overhead.
- **Flush interval:** events may sit in a queue waiting to reach batch size; define when to flush.
- **Partial acknowledgment:** which events did the receiver actually accept?
- **Ordering:** if batch 2 succeeds before batch 1 (which is retrying), logs may arrive at the store out of emission order.
- **Compression:** agree on encoding, size limits, and decompression error handling.
- **Event boundaries:** with NDJSON, each record must be valid JSON; retries are not an excuse to arbitrarily merge or truncate records.
- **Retention and loss:** when a queue or spool hits its cap, which batch is evicted? Is the drop count measured?

**Do not assume strict global ordering across threads, hosts, or services.** Use timestamps, event IDs, request/trace IDs, and sequence numbers when the use case requires ordering. IP addresses, process IDs, and standalone timestamps are insufficient to prove global order.

A single permanently invalid event can cause **an entire batch to be rejected** if the API is all-or-nothing. You need a controlled quarantine/batch-bisection policy or size limits, but should not split batches indefinitely without depth/attempt caps.

## 10. Transport Observability: Logs, Metrics, and Alerts

A retry system cannot be operated solely by logging "retrying..." on every attempt. Maintain standardized **metrics** broken down by collector, outcome, and reason code:

| Signal | Question to answer |
| --- | --- |
| `export_attempts_total` | How many times was the transport actually invoked? |
| `export_success_total` | How many batches/events were ACKed per contract? |
| `export_failures_total` | How are transient, permanent, and timeout failures categorized? |
| `export_retries_total` | How many retries occurred; are there signs of a storm? |
| `queue_size` / `queue_bytes` | How much unsent data is queued? |
| `oldest_queued_age_seconds` | How long has the oldest queued event been waiting? |
| `dropped_events_total` | How many events were dropped due to overflow policy? |
| `export_latency_seconds` | Duration per send or from creation to ACK |
| `last_success_timestamp` | How long since the last successful send? |
| `partial_failure_total` | How many responses were partial-success? |

The metric names in the table are **design examples**, not standard names provided by every exporter.

### Preventing "Log Storms" and Error Loops

If an exporter fails and uses **that very same exporter** to emit `logger.error("export failed")`, each failure generates more logs to transport, causing more failures—a self-amplifying loop. Instead:

- Rate-limit internal exporter logs; aggregate errors over time intervals.
- Use metrics or an independent diagnostic channel with minimal dependency on the failing destination.
- Emit events only on **state transitions** (healthy -> degraded, retrying -> recovered, retry -> exhausted) when possible.
- Do not add `messageId`/`batchId` as per-event metric labels due to excessive cardinality.
- Alert on backlog/age/drops and outage duration, not on a single isolated exception.

Example diagnostic event:

~~~text
event=log_export_retry_scheduled
destination=collector-primary
reasonCode=SERVICE_UNAVAILABLE
attempt=2 delayMs=500 queueSize=3200
~~~

Such an event aids investigation, but **does not prove that the retry actually ran or succeeded**. When a real ACK is received, emit a distinct event such as `log_export_confirmed` and update metrics accordingly.

## 11. Shutdown, Restart, and Preserving Unsent Data

A shutdown hook can help flush or drain queues during a **graceful JVM shutdown**, but provides no guarantee on `SIGKILL`, process crashes, host power loss, or exceeding container grace periods.

For exporters that must preserve data across restarts:

1. Determine whether events are in **RAM** or already written to a **persistent queue**.
2. Verify fsync/durability settings and handle corrupted or full spool files.
3. On restart, define how unacknowledged batches are recovered and retried.
4. Do not advance or delete checkpoints/offsets before the hop's acknowledgment criteria are met.
5. Attach event IDs and handle duplicates, since a crash can happen after an ACK but before updating the checkpoint.
6. Set timeouts and graceful shutdown for workers, without treating shutdown hooks as the sole mechanism.

**Tailing files with offsets/checkpoints:** file shippers typically track read positions in a file. "Read up to offset X" is different from "successfully sent/persisted data up to offset X." Understand the shipper's checkpointing and rotation/truncation policies to evaluate loss or duplication.

**Container stdout:** an application writing to stdout successfully only proves data reached the container/runtime stream in context; the log agent and collector can still lag, drop, or retry. For audit logs requiring strong durability, use a dedicated architecture and acknowledgment mechanism.

## 12. Security and Privacy in Retries

Retries can create **multiple copies of the same log**: in RAM queues, file spools, network buffers, intermediate collectors, and the final store. Protect data at every stage.

- **Do not log payloads in transport error messages.** HTTP response bodies may contain sensitive data echoed back by proxies or backends.
- Use controlled `batchId`, `destinationCode`, `attempt`, and `reasonCode` instead of dumping entire NDJSON payloads.
- Avoid logging access tokens, cookies, emails, phone numbers, IPs, or personal IDs without a clear purpose.
- Secure file spools: OS permissions, appropriate encryption, retention limits, and handling of deletion or disk-full conditions.
- Do not fail over sensitive logs to unauthorized regions or third-party endpoints.
- When debugging retries, do not paste raw requests/responses into tickets, chats, or alerts without proper access controls.
- Ensure HTTP libraries do not accidentally include `Authorization` headers or query parameters in stack traces.
- Verify collector TLS/certificates and authentication settings; never disable TLS verification just to "make retries succeed."
- Hashed or pseudonymized data may still be linkable to individuals; enforce retention and access controls.

**Maximum retry duration also affects retention:** a batch held in a spool for extra hours or days creates a secondary data store. Retention policies on the collector do not automatically apply to agent file spools.

## 13. Testing Transport Retries with Fault Injection

Before deploying to production, test not only the happy path but also failure paths.

| Test scenario | What to verify |
| --- | --- |
| Collector returns `503` twice then `2xx` | Retries exact count/delay; marks confirmed only on ACK |
| Returns `429` with `Retry-After` | Applies appropriate wait policy without creating a retry storm |
| Returns `400` due to invalid schema | Does not retry indefinitely; quarantines and records metrics |
| Network timeout after server received data | UNKNOWN outcome; dedup/at-least-once behaves as expected |
| Collector accepts partial batch | Does not silently drop failed parts; does not resend improperly per contract |
| Queue near capacity while collector is down | Blocks/drops/spills per policy; emits metrics, no OOM |
| Disk spool full or unwritable | Alerts and reacts as defined; never claims "durable" when unwritten |
| Kill process between send and ACK | Verifies recovery, resend, and duplicate risk |
| Restart with un-ACKed batches | Recovers checkpoints and preserves event IDs |
| Multiple exporters retrying simultaneously | No synchronized load spike; jitter/cap works effectively |
| Shutdown while queue still has data | Bounded graceful drain; clear handling of remaining data |
| Wrong authorization or TLS config | Does not auto-disable security; does not hot-retry |
| Primary log exporter fails | Internal diagnostics/metrics do not cause a log storm loop |
| Payload contains test secret | Payload is not leaked in exceptions, spools, or alerts outside policy |

### Unit Testing the Policy (Network-Independent)

In the `LogTransportRetryDemo` example, you can test these properties:

- With `RETRYABLE, RETRYABLE, ACKED`: `Transport.send` is called exactly 3 times, returning `DELIVERED`.
- With `PERMANENT`: called only once, returning `PERMANENT_FAILED`.
- With four retryable/unknown outcomes: does not exceed `MAX_ATTEMPTS=4`, returning `EXHAUSTED`.
- Delays: 250, 500, 1,000 ms, capped at 2,000 ms per formula.
- Batch ID remains **unchanged** across all attempts.
- Raw payloads are not logged in event logs, only approved metadata.

These are recommended test requirements, **not a claim that unit tests were executed in a specific CI environment**. For a real HTTP exporter, use a stub server capable of returning statuses, delays, connection drops, and intentional duplicates; inspect records at the test collector when possible.

## 14. Common Implementation Mistakes

| Mistake | Consequence | Remedy |
| --- | --- | --- |
| Retrying immediately with no delay | Increases load when collector is overloaded | Backoff + jitter + cap |
| Retrying all HTTP `4xx` errors forever | Cannot fix payload/config; wastes resources | Classify permanent errors and handle separately |
| Treating timeout as guaranteed failure | May send duplicates when server already received it | Define UNKNOWN, use dedup/idempotency |
| Treating `2xx` as final durable storage | ACK may only confirm an intermediate layer | Check the contract of each hop |
| Unbounded in-memory queue | JVM OOM, impacts business logic | Bound queue, apply backpressure/drop/spool |
| Not monitoring drops and queue age | Silent log loss | Metrics, dashboards, alerts |
| Logging every export error via the same exporter | Self-amplifying log storm | Independent diagnostics, rate limiting |
| Resending entire batch after partial success | Duplicates or incorrect event counts | Handle response per contract |
| Looking only at `logger.info` call count | Unknown whether events reached collector | Measure ACKs, backlog, and end-to-end delivery |
| Generating a new batch ID on each retry | Receiver cannot deduplicate the same batch | Use a stable ID for the same content |
| Ignoring shutdown/restart | Queue loss or unintended duplicates | Durable queue, checkpointing, idempotency |
| Retrying auth failures by disabling TLS | Introduces security vulnerabilities | Fix credentials/certs via proper process |
| Keeping spools with PII without retention limits | Creates a secondary data store | Access control, encryption, retention |
| Calling `Thread.sleep` on request threads on failure | Slows requests and exhausts threads | Separate executor/shipper, intentional backpressure |

## 15. Operational Checklist

- [ ] Identify which hop owns retries and what ACK means at each hop.
- [ ] Classify outcomes `ACKED / RETRYABLE / PERMANENT / UNKNOWN / PARTIAL` per contract.
- [ ] Configure timeouts, max attempts, max retry age, backoff, jitter, and `Retry-After`.
- [ ] Do not hot-retry unrecoverable schema/permission/config errors.
- [ ] Design bounded queues/buffers with clear overflow policies.
- [ ] Decide on RAM vs. persistent queues, checkpointing, restart, and graceful shutdown.
- [ ] Ensure stable event/batch IDs to support deduplication on resend.
- [ ] Handle partial success, oversized batches, duplicates, and ordering when required.
- [ ] Monitor `queue_size`, age, retries, failures, drops, and last success.
- [ ] Prevent log storms from the exporter itself; use independent diagnostics/metrics.
- [ ] Keep payloads/tokens/PII out of transport error logs and alerts.
- [ ] Test `429`, `503`, post-ACK timeouts, crashes, disk full, restarts, and receiver downtime.
- [ ] Distinguish delivery guarantees for diagnostic logs vs. durable audit/business events.
- [ ] Verify actual agent, collector, and backend versions/configs before relying on automatic retries.

### Self-Check Questions

**Q1.** Does `logger.info()` succeeding mean the log was received by the collector?  
**A:** No. The event may still be sitting in a local queue or buffer.

**Q2.** The exporter timed out after sending a batch. Can we be sure the collector did not receive it?  
**A:** No. This is an unknown outcome; resending may create duplicates and requires a dedup/idempotency policy.

**Q3.** Why should jitter be used?  
**A:** So multiple exporters do not retry simultaneously when a collector recovers or is overloaded.

**Q4.** When the collector returns `400` due to an invalid JSON schema, should we retry the same batch indefinitely?  
**A:** No. Classify it as a permanent error, quarantine it, and fix the payload or schema.

**Q5.** Does `Retry-After` mean every exporter must sleep for that exact value?  
**A:** Not strictly. You must follow the endpoint's header convention, parse the format correctly, and combine it with safety caps and load policies.

**Q6.** Why can a persistent queue still produce duplicates?  
**A:** A send may have been received, but the exporter crashed before persisting the local checkpoint/ACK, causing a resend after restart.

**Q7.** Should every retry error be sent to the same failing log channel?  
**A:** No. That can trigger a log storm loop; prefer metrics or a less dependent diagnostic channel.

**Key takeaway:** Transport retries help logs survive transient network or destination failures, but they are only reliable when paired with **outcome classification, backoff/jitter, retry limits, queuing/backpressure, well-defined ACKs, stable IDs, duplicate handling, and observability**. They do not guarantee `exactly once` or final durable storage on their own; you must define the contract for every hop in the logging pipeline.
