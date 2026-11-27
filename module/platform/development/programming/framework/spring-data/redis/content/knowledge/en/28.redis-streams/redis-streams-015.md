# Retry Policies, Failed Records, and Dead-Letter Streams in Redis Streams

Redis Streams allows applications to write events as records with IDs and multiple fields, then distribute work across multiple consumers via **consumer groups**. Compared to Redis Pub/Sub, Streams retains data for replay and tracks delivered-but-unacknowledged messages. Still, **Redis Streams does not automatically decide how many retries to run, how long to wait between attempts, or when to move a message to an error stream**.

When building an order-processing worker with Spring Data Redis, an event can encounter many situations:

- Calling an external service times out for a few seconds and succeeds on retry.
- Message contents miss a required field, failing no matter how many times it is retried.
- A worker finishes business processing yet gets interrupted before sending `XACK`.
- A worker dies after reading, leaving the message in the **Pending Entries List (PEL)**.
- A message exceeds allowed failure attempts and must move to a **dead-letter stream (DLQ/DLS)** for investigation or manual handling.

A solid policy must distinguish **transient errors**, **permanent errors**, and **ambiguous-outcome errors**, cap execution attempts, define wait intervals between attempts, and persist enough details for recovery.

## 1. Distribution Mechanics: `XREADGROUP`, PEL, and `XACK`

Suppose the application has:

```text
Main stream:        orders:events
Consumer group:     billing-workers
Consumers:          billing-1, billing-2
Dead-letter stream: orders:events:dlq
```

Overall flow:

```text
Producer
   |
   | XADD orders:events ...
   v
Redis Stream orders:events
   |
   | XREADGROUP GROUP billing-workers billing-1 ... >
   v
Consumer billing-1
   |
   +-- Processing succeeds --> XACK --> removed from PEL
   |
   +-- Transient error ------> no ACK
   |                              |
   |                              v
   |                       PEL holds message
   |                              |
   |                        XAUTOCLAIM / XCLAIM
   |                              |
   |                              v
   |                          Reprocess
   |
   +-- Permanent error / max retries exceeded
                |
                v
        XADD orders:events:dlq ...
                |
                v
        XACK original message
```

Redis records a message in the PEL when a consumer group delivers it to a consumer and it has not yet been acknowledged. Related commands:

| Command | Role |
|---|---|
| `XADD` | Appends a new record to a stream |
| `XGROUP CREATE` | Creates a consumer group |
| `XREADGROUP` | Reads records in a group context, delivering to a consumer |
| `XPENDING` | Inspects delivered-but-unacknowledged records |
| `XACK` | Confirms processing, removing the entry from the PEL |
| `XCLAIM` | Transfers ownership of specific pending messages to another consumer |
| `XAUTOCLAIM` | Scans and claims messages idle long enough |
| `XRANGE` | Reads records still in the stream |
| `XINFO GROUPS` / `XINFO CONSUMERS` | Inspects group progress, pending counts, and consumers |

**Crucial:** `XACK` **does not delete the record from the stream**. It only clears the message's pending status for the specified consumer group. The record remains in the stream until removed by `XDEL` or an appropriate trim/delete mechanism.

### At-Least-Once Is the Usual Practical Model

When workers ACK **only after** processing succeeds, a message may be redelivered if a worker dies before ACK. Hence the model is usually described as **at-least-once processing when the application implements proper redelivery/reclaim**. Redis does not automatically run a cron retry for every PEL entry; without recovery logic, messages can sit pending forever.

Never equate “at-least-once” with **exactly-once** business execution. A message that already applied side effects in a database can still be reprocessed if its ACK was lost.

## 2. Creating a Stream and Consumer Group for Testing

Examples use Redis 6.2+ for `XAUTOCLAIM`, with keys dedicated to a test environment.

Create the group along with the stream if missing:

```redis
XGROUP CREATE orders:events billing-workers 0 MKSTREAM
```

In this example, ID `0` allows the group to read messages that already existed before group creation; if the group should only see records added after initialization, choose `$`. Group creation reports `BUSYGROUP` if the group already exists—handle that as “already initialized”, not by recreating the group on every worker startup.

Add a record:

```redis
XADD orders:events * eventId evt-001 orderId ord-42 type PAYMENT_REQUESTED amount 125000
```

Redis returns an ID like:

```text
"1763000000000-0"
```

This is the Redis-generated **Stream Record ID**, distinct from the business `eventId` in the payload. Keep both: the Redis ID for PEL/`XACK` operations, and the business `eventId` for deduplication and cross-system correlation.

Consumer `billing-1` reads new messages:

```redis
XREADGROUP GROUP billing-workers billing-1 COUNT 1 BLOCK 1000 STREAMS orders:events >
```

`>` requests new records **never yet delivered to the consumer group**. Once returned, the message becomes pending for that consumer.

Inspect:

```redis
XPENDING orders:events billing-workers
XPENDING orders:events billing-workers - + 10
```

Sample detailed `XPENDING` output:

```text
1) "1763000000000-0"    # message ID
2) "billing-1"          # current owner
3) (integer) 12000      # idle time in milliseconds
4) (integer) 1          # Redis-recorded delivery count
```

Note: Redis's delivery count **is not how many times a Java method threw an exception**. It increments when a message is redelivered via mechanisms such as pending history reads or claims; if code retries the same object in memory without Redis redelivery, this counter does not reflect those attempts.

Once business processing succeeds:

```redis
XACK orders:events billing-workers 1763000000000-0
```

Return value `1` means one pending entry was ACKed. Now `XPENDING` no longer lists that entry, yet:

```redis
XRANGE orders:events - +
```

still shows the original record. That is normal behavior.

## 3. Classifying Errors Before Choosing Retries

Do not retry all exceptions identically. Identify which conditions **are likely to change by waiting** versus those requiring data fixes or operator intervention.

| Error group | Examples | Starting policy |
|---|---|---|
| **Transient** | HTTP 503, connection timeout, partner maintenance | Bounded retry with backoff |
| **Rate limiting (throttling)** | HTTP 429 or overloaded Redis/DB | Retry per `Retry-After` if present, add jitter |
| **Permanent** | Missing `orderId`, broken JSON, unsupported schema, invalid business code | Do not loop fruitlessly; move to DLQ or mark rejected |
| **Ambiguous outcome** | Payment request sent, connection dropped before response | Query status by idempotency key before retrying |
| **Code/deployment bug** | `NullPointerException`, wrong decoder config, incompatible class | Cap retries; alert and investigate |
| **Sustained resource failure** | Out of memory or unable to write DLQ | Do not ACK source message; alert and restore infrastructure |

For example, a payment API call timing out does not prove the payment did not occur. Retrying with a fresh request lacking an idempotency key risks double-charging. Prioritize checking outcome by `eventId` or stable transaction key instead of blindly “retrying 5 times”.

### Why Separate Business Errors from Infrastructure Errors?

A malformed-schema message belongs somewhere payloads can be investigated. A network-timeout message can succeed a few seconds later. Leaving both sitting in pending under infinite retries causes the system to:

- Resend doomed requests repeatedly.
- Pile extra load onto an already struggling dependency.
- Accumulate huge pending lists, slowing healthy consumers.
- Bury critical errors in log noise.

Hence a typical strategy combines: **bounded retries**, **backoff**, **DLQ**, **alerts**, and **controlled replay**.

## 4. Retry Policies: Attempts, Idle Time, Backoff, and Jitter

Suppose processing `PAYMENT_REQUESTED` allows up to **5 attempts** including the initial try, with growing delays:

```text
Attempt 1: immediately upon receiving message
Attempt 2: after at least 2 seconds
Attempt 3: after at least 4 seconds
Attempt 4: after at least 8 seconds
Attempt 5: after at least 16 seconds
After Attempt 5 fails: write DLQ and ACK original message
```

This illustrates bounded **exponential backoff**. In practice, apply a ceiling such as 60 seconds or 5 minutes, plus **jitter** so thousands of messages do not retry in lockstep.

Illustrative formula:

```text
delay(n) = min(maxDelay, baseDelay * 2^(n-2)) + randomJitter

Where:
  n = 2, 3, 4... is the index of the next attempt.
  baseDelay = 2 seconds.
  maxDelay = 60 seconds.
```

Retry limits are not rigid universal constants: base them on SLAs, acceptable latency, side-effect safety, recoverability, and per-call cost.

### 4.1. PEL Idle Time Is Not Backoff

`XPENDING` reports **idle time**—elapsed time since the message was last delivered or claimed. `XAUTOCLAIM` claims entries idle longer than a threshold. This is a great tool for **recovering stuck messages**, not a scheduler implementing per-business exponential backoff formulas.

Example:

```redis
XAUTOCLAIM orders:events billing-workers recovery-1 30000 0-0 COUNT 20
```

This transfers ownership of pending entries idle over 30,000 ms to consumer `recovery-1`, scanning from `0-0`.

The command returns:

1. Cursor for further scanning, becoming `0-0` when a pass finishes.
2. List of newly claimed messages.
3. On newer Redis versions, optionally a list of IDs removed/trimmed from the stream while metadata remained in the PEL.

In Redis 6.2+, `XAUTOCLAIM` does not necessarily return all eligible entries in one call. It scans by cursor with a cap on PEL items inspected per turn; follow the returned cursor to keep scanning, and re-run periodically even after a pass finishes. Redis 7.0+ can clean up orphaned PEL entries while scanning.

**A 30-second threshold does not mean retrying at exactly 30 seconds.** Retries happen only when the application runs the reclaimer and claims the entry. If the recovery job runs once per minute, actual wait time can be longer.

### 4.2. Do Not Claim Too Early

Suppose normal business processing sometimes takes 45 seconds. If the reclaimer claims any message idle over 10 seconds, it can grab messages **while the original worker is still running**:

```text
t0    billing-1 receives evt-001 and begins calling partner
t10   recovery-1 calls XAUTOCLAIM on evt-001
t11   recovery-1 also processes evt-001
t45   billing-1 finishes and prepares to XACK
```

Both workers can produce side effects concurrently. Transferring PEL ownership **does not cancel** the old worker's Java task or in-flight HTTP request.

Therefore, choose `min-idle-time` based on real timeouts and processing durations. For very long jobs, use explicit heartbeats/leases, split work into smaller steps, or limit concurrency—never set an idle time shorter than processing duration and hope for “exactly once”.

### 4.3. Delivery Count vs. Business Failure Count

`XPENDING ... - + 10` returns how many times Redis delivered/claimed a message. This helps spot poison messages, yet does not necessarily equal external service calls. For example:

- A worker might retry three times in memory within **one delivery**.
- A worker might get killed right after receipt before even attempting work, yet delivery count still increments.
- `XAUTOCLAIM ... JUSTID` returns only IDs and **does not** increment the delivery counter.
- An application might store retry state separately in Redis/DB and schedule backoff explicitly.

If policy states “at most 5 payment calls”, persist a reliable **business attempt count** instead of treating Redis delivery count as that counter by default.

## 5. Two Common Retry Strategies

### 5.1. Keep Messages in the PEL and Reclaim

Workflow:

```text
XREADGROUP returns message
       |
       v
Transient processing error
       |
       +--> DO NOT XACK
                |
                v
        PEL keeps message
                |
                v
        Background reclaimer XAUTOCLAIM
                |
                v
           Reprocess
```

Pros: no need to duplicate payloads into a retry stream; Redis already provides PEL and claiming. Cons: waits depend on idle time and reclaimer schedule, per-message dynamic backoff schedules are awkward, and slow workers require care.

Fits tasks with relatively predictable durations where dead-consumer recovery matters more than exact retry schedules.

### 5.2. Use a Dedicated Retry Stream or Scheduler

An application can route failed messages to a dedicated stream like `orders:events:retry`, attaching:

```text
originalId    = 1763000000000-0
eventId       = evt-001
attempt       = 2
nextAttemptAt = 2026-11-13T04:20:00Z
errorCode     = PARTNER_TIMEOUT
```

A scheduler component forwards messages to processing workers only once `nextAttemptAt` arrives. This is **application logic**, not an automatic “delayed message” feature of Redis Streams. Consumers reading a stream do not automatically pause until each record's `nextAttemptAt`; scheduling logic must be implemented.

Another design uses a Sorted Set scored by epoch milliseconds of `nextAttemptAt`, with a job pulling due IDs and re-emitting them to the stream. With multiple workers, claim scheduled items safely so two schedulers do not pick up the same task.

Pros: easy to express per-event exponential backoff and jitter. Cons: adds write/ACK/state-transition flows, requiring idempotency and crash recovery between operations.

### Comparison

| Criterion | PEL + `XAUTOCLAIM` | Retry stream / scheduler |
|---|---|---|
| Storing failed messages | Remains in main stream and PEL | Adds retry records/schedule |
| Re-triggering | Reclaimer finds pending items idle long enough | Scheduler checks when `nextAttemptAt` is due |
| Per-message custom backoff | Harder; needs external metadata beyond PEL | Natural with dedicated scheduling |
| Risk of concurrent runs if claimed early | Yes | Yes if scheduler/claiming is misdesigned |
| Components to operate | Fewer | More |
| Worker crash recovery | Built-in fit | Must recover both retry state and consumer state |

Both models can be combined: use the PEL for dead-consumer crash recovery, and a retry stream/scheduler for well-classified transient failures.

## 6. Dead-Letter Stream: What to Store and When to Route?

A **dead-letter stream** (often called DLQ, even though a Redis Stream is not a classic queue) stores records the main pipeline cannot complete under policy:

- Data errors that cannot self-heal.
- Business errors ineligible for retry.
- Exceeded retry attempts.
- Cases requiring human operator review and decision.

Example creating a DLQ record:

```redis
XADD orders:events:dlq * originalStream orders:events originalId 1763000000000-0 eventId evt-001 orderId ord-42 errorCode INVALID_AMOUNT attempts 1 failedAt 2026-11-13T04:00:00Z
```

Only then ACK the original record:

```redis
XACK orders:events billing-workers 1763000000000-0
```

### 6.1. Fields to Store in the DLQ

| Field | Meaning |
|---|---|
| `originalStream` | Source stream |
| `originalId` | Original record ID for traceability |
| `eventId` | Business ID for deduplication |
| `payload` or required fields | Data needed to diagnose or replay |
| `errorCode` | Stable error code, e.g., `INVALID_AMOUNT` |
| `errorMessage` | Short description, avoiding leaking secrets |
| `attempts` | Number of attempts executed per policy |
| `firstFailedAt` and `lastFailedAt` | First occurrence and latest failure timestamps |
| `consumerGroup`, `consumerName` | Worker/group that encountered the failure |
| `schemaVersion` | Aids reading records after schema changes |
| `correlationId` / `traceId` | Links logs and original requests |

Never put passwords, tokens, card numbers, sensitive personal data, or unsanitized stack traces into a broadly accessible DLQ. For large payloads, store a reference to secure storage instead of copying everything.

### 6.2. A DLQ Is Not a “Trash Can” to Ignore Forever

Define:

1. Who monitors DLQ depth and record age?
2. When do alerts fire?
3. Who is authorized to inspect/edit payloads?
4. What criteria permit replaying?
5. How long is DLQ data retained, and how is it trimmed/deleted?
6. If an event failed due to a now-fixed bug, will replaying it duplicate side effects?

Build a dashboard or operations tool displaying `errorCode`, `eventId`, attempt count, and resolution status after investigation.

## 7. Safe Ordering: Write to DLQ First, Then `XACK`

These two commands are not always executed as one transaction:

```text
1. XADD orders:events:dlq ...
2. XACK orders:events billing-workers <id>
```

If you **ACK first** and crash before `XADD`, the message disappears from the PEL without ever reaching the DLQ.

If you **`XADD` first** and crash before `XACK`, the message stays pending and can be reclaimed, creating **two DLQ entries** unless deduplicated.

The `XADD → XACK` order is generally safer for preserving failure data, paired with DLQ duplicate detection (e.g., keying by `originalStream + originalId + consumerGroup` or a stable business key).

### 7.1. When Both Keys Share the Same Redis and Hash Slot

In a single Redis instance, `XADD` and `XACK` can be grouped in `MULTI`/`EXEC` so other clients do not interleave between them. However, Redis transactions **do not roll back earlier commands if a later command errors during `EXEC`**. Never call this an exactly-once solution.

In Redis Cluster, multi-key commands/transactions generally require all keys in the same hash slot. You can design:

```text
orders:{billing}:events
orders:{billing}:events:dlq
```

Both keys share hash tag `{billing}` and map to the same slot, supporting same-slot multi-key operations. However, funneling too much traffic into one slot creates a **hot shard**; partition appropriately instead of putting every stream in the system under one global tag.

If the DLQ lives in another system or another Cluster, `MULTI`/`EXEC` cannot merge two stores into an atomic commit. The application needs idempotency, retries, and reconciliation.

### 7.2. Redis 8.2 and Advanced Reference-Handling Commands

Newer Redis versions add combined delete/ACK controls such as `XACKDEL` and consumer-group-aware policies. They help manage stream cleanup, yet do not replace DLQ routing or idempotency controls. When using new commands, verify server and Spring Data Redis driver support.

## 8. Reading and ACKing Messages with Spring Data Redis

A Spring Boot application needs the dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

Sample `application.yml` for a test Redis instance:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
```

The examples below use `StringRedisTemplate` and String field values for easy inspection. If your app uses custom JSON/byte serializers, configure `MapRecord` generics and serializers consistently.

### 8.1. Reading via a Consumer Group

```java
import java.time.Duration;
import java.util.List;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.core.StreamOperations;
import org.springframework.data.redis.core.StreamReadOptions;
import org.springframework.data.redis.core.StringRedisTemplate;

public class OrderStreamPoller {

    private static final String STREAM = "orders:events";
    private static final String GROUP = "billing-workers";

    private final StringRedisTemplate template;

    public OrderStreamPoller(StringRedisTemplate template) {
        this.template = template;
    }

    public List<MapRecord<String, String, String>> poll(String consumerName) {
        StreamOperations<String, String, String> streamOps =
                template.opsForStream();

        return streamOps.read(
                Consumer.from(GROUP, consumerName),
                StreamReadOptions.empty()
                        .count(10)
                        .block(Duration.ofSeconds(1)),
                StreamOffset.create(STREAM, ReadOffset.lastConsumed())
        );
    }
}
```

`ReadOffset.lastConsumed()` in a consumer group context targets **new messages not yet delivered to the group**. It does not automatically iterate pending messages left by dead consumers. Hence this poller alone is **not enough** to guarantee retries and recovery.

When using `StreamOperations.read(...)` with a blocking option, the result can be empty or null on timeout; handle that normally rather than treating it as a business error.

### 8.2. ACK Only After Processing Succeeds

Minimal logic example:

```java
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.core.StringRedisTemplate;

public class OrderRecordProcessor {

    private static final String STREAM = "orders:events";
    private static final String GROUP = "billing-workers";

    private final StringRedisTemplate template;
    private final BillingService billingService;

    public OrderRecordProcessor(
            StringRedisTemplate template,
            BillingService billingService) {
        this.template = template;
        this.billingService = billingService;
    }

    public void process(MapRecord<String, String, String> record) {
        try {
            billingService.processPayment(
                    record.getValue().get("eventId"),
                    record.getValue().get("orderId"),
                    record.getValue().get("amount")
            );

            template.opsForStream().acknowledge(
                    STREAM, GROUP, record.getId());
        } catch (RuntimeException error) {
            // Do not ACK: message stays pending for recovery worker.
            // Log with eventId, record ID, and error category.
            System.err.println(
                    "Failed to process " + record.getId() + ": " + error);
        }
    }
}
```

`BillingService` is an application-defined business interface, not a Spring Data Redis component. It must validate schema, currency codes, amounts, and idempotency before triggering side effects such as calling a payment gateway.

This simple code **does not yet classify errors** or route to a DLQ; it only demonstrates post-success ACKing. Real applications must handle backoff, attempt limits, and permanent errors as shown in the next sections.

### 8.3. Consumer Container: Avoid Auto-ACK for Retryable Work

Spring Data Redis provides `StreamMessageListenerContainer` to manage polling and dispatching:

```java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.stream.StreamMessageListenerContainer;
import org.springframework.data.redis.stream.StreamMessageListenerContainer.StreamMessageListenerContainerOptions;

@Configuration
public class OrderStreamConsumerConfig {

    @Bean(initMethod = "start", destroyMethod = "stop")
    public StreamMessageListenerContainer<
            String, MapRecord<String, String, String>> orderListenerContainer(
            RedisConnectionFactory connectionFactory,
            OrderRecordProcessor processor) {

        StreamMessageListenerContainerOptions<
                String, MapRecord<String, String, String>> options =
                StreamMessageListenerContainerOptions.builder()
                        .pollTimeout(Duration.ofSeconds(1))
                        .build();

        StreamMessageListenerContainer<
                String, MapRecord<String, String, String>> container =
                StreamMessageListenerContainer.create(
                        connectionFactory, options);

        container.receive(
                Consumer.from("billing-workers", "billing-instance-1"),
                StreamOffset.create("orders:events",
                        ReadOffset.lastConsumed()),
                processor::process
        );

        return container;
    }
}
```

In production, `consumerName` must distinguish active instances/consumers rather than giving every replica the same hardcoded name. The consumer group **must exist before** the container starts polling—for instance, via provisioning or startup logic handling `BUSYGROUP` and race conditions.

The key point is using `receive(...)` with **manual ACK** after processing. `receiveAutoAck(...)` confirms messages immediately on receipt before business work finishes, so if the callback fails, the message may no longer be pending for retries. Auto-ACK fits only when dropping in-flight messages on failure is acceptable.

Errors in the **polling layer or listener container** need dedicated error handlers and monitoring; never assume every callback exception turns into a scheduled Redis retry automatically.

## 9. Example Moving Failed Messages to a DLQ with Spring Data Redis

Suppose the processor detects an invalid payload and wants to move it to the DLQ immediately without retrying. The DLQ record should keep a link back to the original record.

```java
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.connection.stream.StreamRecords;
import org.springframework.data.redis.core.StringRedisTemplate;

public class DeadLetterWriter {

    private static final String STREAM = "orders:events";
    private static final String GROUP = "billing-workers";
    private static final String DLQ = "orders:events:dlq";

    private final StringRedisTemplate template;

    public DeadLetterWriter(StringRedisTemplate template) {
        this.template = template;
    }

    public void move(
            MapRecord<String, String, String> original,
            String errorCode,
            int attempts) {

        Map<String, String> fields =
                new LinkedHashMap<>(original.getValue());
        fields.put("originalStream", STREAM);
        fields.put("originalId", original.getId().getValue());
        fields.put("consumerGroup", GROUP);
        fields.put("errorCode", errorCode);
        fields.put("attempts", Integer.toString(attempts));
        fields.put("failedAt", Instant.now().toString());

        // Write DLQ first; do not ACK if writing fails.
        RecordId dlqId = template.opsForStream().add(
                StreamRecords.newRecord().in(DLQ).ofMap(fields));

        if (dlqId == null) {
            throw new IllegalStateException("Could not append DLQ record");
        }

        // Only after Redis accepts the DLQ record, ACK the original record.
        template.opsForStream().acknowledge(
                STREAM, GROUP, original.getId());
    }
}
```

This illustrates **safe priority ordering**, not an atomic state transition across `XADD` and `XACK`. If the process dies in between, the message can be moved to the DLQ a second time. Production deployments need **deduplication**—such as a Redis key `consumerGroup:originalStream:originalId` created with an appropriate mechanism, or a unique decision record store coordinated with the DLQ append.

If `XADD` fails, do not ACK. If `XACK` fails/times out after `XADD`, do not guess whether the original message was ACKed; recovery must reconcile against the DLQ idempotently.

### Structuring Handling by Exception Type

A workflow can be sketched as:

```java
try {
    businessProcessor.handle(event); // must be idempotent
    streamOps.acknowledge(SOURCE, GROUP, record.getId());
} catch (InvalidEventException permanent) {
    deadLetterWriter.move(record, "INVALID_EVENT", attemptCount);
} catch (TransientPartnerException transientError) {
    // Keep pending or schedule retry per policy.
    // Do not XACK here unless retry responsibility is safely handed off.
    retryPolicy.recordFailureAndSchedule(record, transientError);
} catch (RuntimeException unknown) {
    // Flag ambiguous outcome; avoid blind retries.
    incidentReporter.report(record, unknown);
}
```

`InvalidEventException`, `TransientPartnerException`, `retryPolicy`, and `incidentReporter` are **application-defined types and components** shown to convey the concept. To use them in a real project, implement them backed by durable attempt/backoff/recovery state rather than copying this pseudocode verbatim as standalone runnable code.

## 10. Recovery Worker: Re-Reading the PEL Properly

A consumer group reading only new records with `XREADGROUP ... >` will **not automatically reprocess** records received by an earlier consumer before it died.

Suppose messages are pending under `billing-1`:

```redis
XPENDING orders:events billing-workers - + 10
```

A recovery worker can run:

```redis
XAUTOCLAIM orders:events billing-workers recovery-1 60000 0-0 COUNT 10
```

Where:

- `recovery-1` is the consumer taking new ownership.
- `60000` is the minimum idle time of 60,000 ms.
- `0-0` is the cursor where scanning begins.
- `COUNT 10` caps the target records to claim in one turn.

Once claimed, **the recovery worker itself must process the returned records**, classify errors, ACK on success, or move to the DLQ once attempts are exhausted. `XAUTOCLAIM` only transfers ownership; it does not run business handlers.

### 10.1. Iterating the Cursor to the End of a Pass

Suppose a response returns cursor `1763000000010-0`. The worker must continue:

```redis
XAUTOCLAIM orders:events billing-workers recovery-1 60000 1763000000010-0 COUNT 10
```

When the result returns cursor `0-0`, the current scan pass is complete. The job can sleep and restart from `0-0` later because messages not idle long enough during the previous pass may qualify afterwards.

Do not blindly call `XAUTOCLAIM ... COUNT 10` from `0-0` once a minute and assume you inspected the whole PEL if the pending list is large. Follow the cursor and cap iterations/job duration.

### 10.2. `XCLAIM` When Exact IDs Are Known

If you observe a specific message ID pending too long:

```redis
XCLAIM orders:events billing-workers recovery-1 60000 1763000000000-0
```

`XCLAIM` fits when you already have the exact list of IDs to reclaim. `XAUTOCLAIM` fits scanning idle messages without manually iterating `XPENDING`.

Avoid running two independent reclaimers fighting to claim the same messages back and forth. Even when Redis transfers ownership cleanly, an old worker's task might still be mid-flight; timeouts/leases and idempotency are essential.

### 10.3. Redis Retry Count Does Not Necessarily Equal Policy Count

`XCLAIM` and `XAUTOCLAIM` normally increment a message's delivery count. However, with `JUSTID`, Redis returns only IDs and **does not** increment the delivery counter. Command variants and in-app retries can skew the count.

If policy requires “at most 5 real processing attempts”, maintain a business attempt counter or explicitly count **successful claims that entered processing**, rather than relying blindly on delivery count.

## 11. Designing Retries with Backoff Without Blocking Workers

A common mistake:

```java
try {
    callPartner();
} catch (Exception error) {
    Thread.sleep(60_000);
    callPartner();
}
```

Putting this directly inside a listener ties up the worker thread and message ownership for the entire sleep. With thousands of failing messages, thread pools and new-message capacity collapse.

Instead of sleeping inside the handler:

1. Classify the error and decide the next retry time.
2. Persist retry state durably: `attempt`, `nextAttemptAt`, `eventId`, failure reason.
3. Put the message on a retry schedule or leave it pending for controlled recovery.
4. Free the current worker's resources immediately.
5. Let a scheduler pick up due messages and route them back to consumers.

When designing a retry stream, ACK the original message **only after** retry responsibility is durably handed off, just like the DLQ rule. If writing the retry schedule fails, do not ACK the source.

### Limiting Retry Pressure

A good policy typically includes:

- `maxAttempts` or `maxAge`: stops infinite loops.
- `baseDelay`, `maxDelay`, and jitter: dampens synchronized retry storms.
- Concurrency limits: prevents hammering an overloaded external service.
- Circuit breakers: pauses calls when a downstream dependency fails system-wide.
- Error classification by stable codes rather than raw exception strings.
- Dashboards for pending, retry, and DLQ states to spot stalled flows.

Never compute retry timing purely in process memory where restarts wipe out the schedule. Unprocessed messages are critical state; persist recovery state durably.

## 12. Idempotency: Mandatory for Safe Reprocessing

Trace this flow:

```text
1. Worker receives evt-001.
2. Calls payment service -> succeeds.
3. Worker crashes before XACK.
4. PEL still holds evt-001.
5. Reclaimer claims and processes evt-001 again.
```

Without idempotency, the customer can be charged twice.

### A Sound Design

- Producers attach a unique, stable `eventId` to each business event.
- For database writes, maintain `processed_events(event_id PRIMARY KEY, status, ...)` and update it **in the same SQL transaction as internal side effects**.
- For external API calls, pass `eventId` or a stable idempotency key to the partner if supported; on ambiguous outcomes, query status using that key.
- When encountering the same `eventId` again, inspect prior results to decide whether to ACK, retry, or reconcile.

**Be careful with plain `SET NX` before processing:**

```redis
SET processed:evt-001 1 NX EX 86400
```

If the app records “processed” **before** executing business logic and crashes, redelivery sees the `processed` key and skips work that **never completed**. A temporary lock/lease or `IN_PROGRESS` status needs expiration and recovery; `DONE` is recorded only once side effects actually succeed.

Even when storing idempotency in Redis, distinguish acquiring a lock, recording outcomes, and ACKing; when actions span multiple systems, there is no default atomic commit. Design explicitly for ambiguous results.

## 13. Poison Messages and the Risk of Blocking Throughput

A **poison message** is a record that repeatedly fails on every worker—for example, due to a broken schema or data causing the decoder to throw an exception.

Without `maxAttempts` and a DLQ:

```text
evt-001 -> claim -> error -> pending
        -> claim -> error -> pending
        -> claim -> error -> pending
        -> ... loops forever
```

This wastes resources and inflates pending/backlogs. If a message fails decoding right at the listener's serialization layer, the business callback may **never even be invoked**; this case needs container/codec-level error handling and raw-record recovery rather than just a `catch` inside the business processor.

A practical strategy:

1. Log error codes and message IDs without printing sensitive payloads.
2. Detect permanent schema errors and route to the DLQ immediately.
3. For unclassified errors, run bounded retries and alert.
4. If DLQ writes fail, leave the source pending and fire high-severity alerts.
5. Provide a workflow to inspect and replay after fixing bugs/schemas.

Never let one corrupted record crash workers endlessly without isolation.

## 14. Trimming, Retention, and the Risk of Losing Pending Payloads

Streams retain records until deleted or trimmed per storage policies. If you run:

```redis
XTRIM orders:events MAXLEN ~ 10000
```

Redis can evict older records to cap space. **Never assume pending records are always preserved until ACK** across every Redis configuration and version. A trimmed or `XDEL`ed record may lose its payload in the stream even though pending metadata existed.

In Redis 7.0+, `XAUTOCLAIM` can detect and purge pending entries whose stream records no longer exist. At that point, recovery cannot reconstruct original data from the PEL alone.

Therefore:

- Size retention for **max processing time + retry/backoff duration + acceptable downtime**.
- Check the oldest pending entry before trimming aggressively.
- Give the DLQ its own retention; failed messages often need longer retention than the source stream.
- When using Redis 8.2+ reference controls during delete/trim, understand exact policy semantics before changing defaults.
- For high-durability workloads, evaluate persistence, replication, and backups—not just TTL/`MAXLEN`.

**Note:** `XACK` does not delete original records from the stream. With multiple consumer groups, each group has its own progress and PEL; deleting records right after one group ACKs can deprive other groups of data to read or recover.

## 15. Redis Cluster, Multiple Streams, and Consistency

In Redis Cluster, multi-key operations can be restricted to the same hash slot. If the application wants Lua or `MULTI`/`EXEC` to coordinate between the source stream and the DLQ, watch slot placement:

```text
orders:{billing}:events
orders:{billing}:events:dlq
orders:{billing}:events:retry
```

Keys sharing `{billing}` map to the same slot. However, putting all messages under one hash tag sends all traffic to a single shard, forfeiting horizontal sharding. For multi-tenant systems, use finer tags like `{billing-tenant42}` and distribute evenly.

If the DLQ or retry schedule lives in PostgreSQL, Kafka, or another Redis Cluster, no single Redis transaction transitions state across systems. Use state logs, idempotency, and compensation/reconciliation.

### Redis Transactions Do Not Replace Per-Command Error Checks

`MULTI`/`EXEC` groups Redis commands to run sequentially without interleaving, yet **Redis does not roll back earlier commands if a subsequent command fails at runtime**. Even when source and DLQ share a slot, verify:

- Did `XADD` succeed?
- Did `XACK` confirm the intended pending message?
- If the `EXEC` response was lost, might the commands have executed anyway?
- On restart, can you tell whether the event was already moved to the DLQ earlier?

Never let the word “transaction” imply exactly-once or guaranteed handoff in all scenarios.

## 16. System Observability and Alerting

Measure **incoming volume**, **processing rate**, **latency**, **pending counts**, **retries**, **DLQ depth**, and **side effects**:

| Metric | Purpose |
|---|---|
| `stream.received.count` | New messages read |
| `stream.processed.count` | Messages processed successfully |
| `stream.ack.count` | Messages ACKed after processing |
| `stream.pending.count` | Size of the group's PEL |
| `stream.pending.oldest_idle_ms` | Detects long-stuck messages |
| `stream.retry.attempts` | Attempt counts and distribution |
| `stream.retry.scheduled.count` | Scheduled retry backlog |
| `stream.dlq.count` | Messages routed to DLQ |
| `stream.dlq.oldest_age` | Oldest unresolved error message |
| `stream.consumer.recovery.count` | How often messages must be reclaimed |
| `stream.business.duplicate_prevented` | Redeliveries safely caught by idempotency |

Metric names in the table are **suggested custom metrics**, not built-in Spring Data Redis metrics. For Redis CLI:

```redis
XLEN orders:events
XLEN orders:events:dlq

XINFO GROUPS orders:events
XINFO CONSUMERS orders:events billing-workers

XPENDING orders:events billing-workers
XPENDING orders:events billing-workers IDLE 60000 - + 20

XRANGE orders:events:dlq - + COUNT 10
```

Never run unbounded `XRANGE stream - +` on large production streams just to debug. For long streams, cap with `COUNT` and paginate by ID.

### Alerting Signals

- Pending count climbs steadily without throughput rising.
- Pending idle time far exceeds business timeouts.
- The same `eventId` appears in multiple retries/DLQ records.
- Sudden DLQ spikes under a specific `errorCode`.
- Consumer group makes no progress while new records keep arriving.
- Sharp rise in external service timeouts.
- Messages ACKed with no corresponding evidence of side-effect completion.
- Source stream retention threatens to evict unresolved pending messages.

Error data must be detailed enough to operate, while avoiding storing credentials or sensitive payloads in logs or dashboards without strict access controls.

## 17. Common Implementation Mistakes

| Symptom | Cause | Remedy |
|---|---|---|
| Worker restarts and skips prior messages | Reads only `XREADGROUP ... >`, never reclaims PEL | Implement `XAUTOCLAIM`/`XCLAIM` for pending entries |
| Message keeps retrying without ever succeeding | No permanent vs. transient distinction | Cap attempts and route to DLQ |
| Payment called twice | Business work succeeded then crashed before ACK | Idempotency keys and status reconciliation |
| Skewed retry counts | Treated PEL delivery count as business failure count | Track attempts explicitly per policy |
| Reclaimer runs concurrently with active worker | `min-idle-time` too short | Align threshold with timeouts, add leases and idempotency |
| Message lost before reaching DLQ | ACKed source before writing DLQ | Write DLQ first, ACK second, with deduplication |
| Duplicate DLQ records | Crash after DLQ `XADD` and before `XACK` | Deduplicate by original stream/group/ID or `eventId` |
| Callback fails yet PEL has no message | Auto-ack was used | Switch to manual ACK for retryable work |
| Missing payload when claiming pending entry | Stream trimmed/deleted before recovery | Size retention to cover retry windows and downtime |
| Retries trigger traffic spikes | No backoff, jitter, or concurrency cap | Schedule with ceiling and limits |
| Consumer reads new messages while old pending grows | Missing dedicated recovery job | Monitor PEL and run periodic reclaimer |
| `XAUTOCLAIM` handles only a few messages | Ignored cursor, called once | Iterate cursor to `0-0` and run periodically |
| Lua/transaction across source and DLQ fails `CROSSSLOT` | Stream keys map to different hash slots | Use matching hash tags or avoid multi-key atomicity |
| DLQ grows with nobody handling it | Missing operational workflow | Set alerts, ownership, and inspect/replay tooling |

## 18. Reproducible Practice Labs with Redis CLI

Run in a test Redis instance using dedicated keys so real data is untouched.

### Lab 1 — Pending and ACK

1. Create stream/group with `XGROUP CREATE orders:events billing-workers 0 MKSTREAM`.
2. Write two messages with `XADD`.
3. Read one message with `XREADGROUP GROUP billing-workers billing-1 COUNT 1 STREAMS orders:events >`.
4. Run `XPENDING` and record ID, owner, idle time, and deliveries.
5. `XACK` the exact ID and verify the PEL shrinks while `XRANGE` still shows the original record.

### Lab 2 — Simulating Worker Death and Reclaiming

1. Have `billing-1` read a message **without ACKing**.
2. Stop the consumer or simulate worker death.
3. Once idle exceeds the test threshold, call `XAUTOCLAIM` from `recovery-1`.
4. Observe the new owner and delivery count.
5. Call `XACK` after processing completes.

Lab-only command with a 5-second threshold:

```redis
XAUTOCLAIM orders:events billing-workers recovery-1 5000 0-0 COUNT 10
```

In production, never default to 5 seconds if business processing can take longer.

### Lab 3 — Poison Message to DLQ

1. Write a message with `amount = invalid`.
2. Consumer reads it and validator detects a permanent schema error.
3. `XADD orders:events:dlq` with `originalId`, `eventId`, `errorCode = INVALID_AMOUNT`, and failure timestamp.
4. `XACK` the original message after the DLQ write succeeds.
5. Inspect `XRANGE orders:events:dlq - + COUNT 10` and `XPENDING`.

### Lab 4 — Failure Between DLQ and ACK

1. Have a consumer receive an unprocessable message.
2. Write the DLQ record and **intentionally stop the program before `XACK`**.
3. Reclaimer picks up the pending message again.
4. Check whether the program detects the message is already in the DLQ.
5. Design a way to prevent duplicate DLQ writes or mark duplicates for operators.

### Lab 5 — Retry Backoff

1. Choose `maxAttempts = 4` with waits of 2, 4, and 8 seconds.
2. Simulate an external service failing twice and then succeeding.
3. Record `attempt`, `nextAttemptAt`, and actual processing timestamp.
4. Verify the worker **does not sleep on the listener thread during waits**.
5. Simulate failing all four times and confirm the message moves to the DLQ without infinite retries.

### Lab 6 — Retention While Pending

1. Create a pending message and intentionally skip ACKing.
2. In the test environment, trim or delete the original record.
3. Observe `XPENDING` and `XAUTOCLAIM` on your Redis version.
4. Explain why the PEL is not a fallback payload store once stream records are deleted.

## 19. Pre-Deployment Design Checklist

Before shipping workers to production, answer these questions:

1. Which messages retry, and which go straight to the DLQ?
2. What are `maxAttempts` and `maxAge`?
3. Does backoff include jitter and concurrency limits?
4. Who runs the reclaimer, with what `min-idle-time`, and how is the cursor iterated?
5. Can a consumer take longer than `min-idle`? If so, how do you prevent concurrent processing?
6. Do DLQ records store enough info to investigate/replay without exposing sensitive data?
7. If the DLQ write succeeds and ACK fails, does the system deduplicate?
8. If business processing succeeds and ACK fails, is idempotency in place?
9. Is retention on both source stream and DLQ long enough for downtime and retries?
10. Are dashboards/alerts configured for pending counts, retries, DLQ depth, and stalled consumers?
11. When deploying a new schema, how will older DLQ records be read and replayed?
12. On Redis Cluster, do multi-key operations satisfy hash-slot and driver rules?

## 20. Conclusion

Redis Streams provides the building blocks for message reprocessing via **consumer groups**, the **PEL**, `XACK`, `XPENDING`, `XCLAIM`, and `XAUTOCLAIM`. However, Redis does not choose retry counts, compute exponential backoff, or route failed records to dead-letter streams for you. Those are application policies.

The processing path should be: **process successfully then ACK**; schedule bounded retries for transient errors; for permanent errors or exhausted retries, **write to the DLQ first, ACK the source second**, with duplicate detection. Reclaimers must actively recover idle PEL items without claiming so early that two consumers run concurrently.

Finally, treat redeliveries as normal operation. **Idempotency, retention, alerting, reconciliation, and DLQ replay procedures** matter just as much as Redis commands themselves. Without designing those pieces, a system can simultaneously lose failed records and apply side effects twice even while Redis Streams works exactly as designed.

## References

- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html): `StreamOperations`, consumer groups, listener containers, and acknowledgment.
- [Spring Data Redis — StreamMessageListenerContainer API](https://docs.spring.io/spring-data/data-redis/docs/current/api/org/springframework/data/redis/stream/StreamMessageListenerContainer.html): `receive`, `receiveAutoAck`, and registering listeners.
- [Redis — Streams data type](https://redis.io/docs/latest/develop/data-types/streams/): producers, consumer groups, and record storage.
- [Redis — XREADGROUP](https://redis.io/docs/latest/commands/xreadgroup/): reading via consumer groups and the meaning of `>`.
- [Redis — XPENDING](https://redis.io/docs/latest/commands/xpending/): inspecting PEL, idle time, and delivery count.
- [Redis — XACK](https://redis.io/docs/latest/commands/xack/): acknowledging messages and removing from the PEL.
- [Redis — XCLAIM](https://redis.io/docs/latest/commands/xclaim/): transferring pending message ownership.
- [Redis — XAUTOCLAIM](https://redis.io/docs/latest/commands/xautoclaim/): scanning pending items by idle time and cursor, limits, and `JUSTID`.
- [Redis — XADD](https://redis.io/docs/latest/commands/xadd/): creating stream records and optional retention.
- [Redis — XTRIM](https://redis.io/docs/latest/commands/xtrim/): trimming streams and effects on older records.
