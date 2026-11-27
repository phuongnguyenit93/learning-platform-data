# Processing Background Work with Streams and Consumer Groups in Spring Data Redis

Redis Streams is a data structure that stores events in ID order, supports position-based reads, and tracks records that have been delivered but not yet finished processing. Combined with **consumer groups**, Streams fit asynchronous workloads such as sending order confirmation emails, updating indexes, synchronizing inventory, dispatching webhooks, or running post-processing tasks.

In Spring Data Redis, we typically use **`StringRedisTemplate` / `RedisTemplate`**, `StreamOperations`, `StreamRecords`, `Consumer`, `StreamReadOptions`, and `StreamOffset` to build producers and consumers. However, a program that merely calls `XADD` and `XREADGROUP` is **not yet a reliable job queue**. You must also design completion acknowledgement (`XACK`), Pending Entries List (PEL) handling, failure recovery, idempotency, retention, concurrency, and observability.

This exercise focuses on the workflow:

~~~text
POST /orders
      |
      v
OrderService -> save order -> emit OrderCreated
                                    |
                                    v
                             Redis Stream
                             orders.events
                                    |
                             Group order-workers
                                    |
                     +--------------+--------------+
                     |              |              |
                  worker-A       worker-B       worker-C
                     |              |              |
                  handler        handler        handler
                     |              |              |
                  commit         commit         commit
                     |              |              |
                    XACK           XACK           XACK
~~~

**Key takeaway:** Consumer groups distribute and track messages, yet **do not automatically guarantee exactly-once business processing**. A message can be redelivered; handlers must be safe against duplicates.

## 1. Objectives and Prerequisites

After this exercise, you will be able to:

1. Initialize a stream and consumer group at the right offset.
2. Write messages via Redis CLI and Spring Data Redis.
3. Read new messages with `XREADGROUP` and `ReadOffset.lastConsumed()`.
4. Call `XACK` only after business side effects have succeeded.
5. Use `XPENDING` to inspect messages delivered but unacknowledged.
6. Use `XAUTOCLAIM` or `XCLAIM` to recover work from crashed consumers.
7. Design an idempotent handler keyed by business event ID.
8. Classify retryable errors, poison messages, and dead-letter queues (DLQ).
9. Define retention to prevent losing unprocessed messages.
10. Test worker crashes, duplicate handling, restarts, timeouts, and load.
11. Understand Streams limitations regarding database transactions, Redis persistence, and Cluster.

Examples use Java 17+, Spring Boot 3.x, Spring Data Redis, a real Redis Server, and Redis CLI. Redis 6.2+ is used for `XAUTOCLAIM`; core Streams/consumer group commands exist since Redis 5. If your project stack uses other versions, check the corresponding APIs and command support.

## 2. Why Not Use Synchronous HTTP for Every Task?

Suppose an order placement request needs to:

~~~text
1. Save the order
2. Send an email
3. Send a webhook
4. Update the dashboard
5. Return the HTTP response
~~~

If email or webhook delivery stalls for 10 seconds, the user may think placing the order failed even though the database already saved it.

Splitting into asynchronous work:

~~~text
HTTP
   -> DB commit
   -> publish event
   -> return orderId and accepted status

Worker
   -> read event
   -> execute side effect
   -> ACK
~~~

Benefits:

- Reduces how long the request waits on steps that do not need to be synchronous.
- Decouples scaling between API and workers.
- Provides a backlog buffer when workers slow down, as long as the stream/Redis retains data.
- Enables pending inspection and crash recovery.
- Allows multiple consumer groups for independent purposes.

New risks:

- Work is not complete the moment HTTP succeeds.
- Events can be processed more than once.
- Producers can commit to the DB and fail to publish.
- Workers can commit to the DB and crash before ACK.
- Streams can grow RAM usage without retention bounds.
- Redis persistence/failover still carries data-loss risks for acknowledged writes.
- Multiple consumers do not guarantee side effects finish in append order.

Therefore you need a full workflow, not just a queue API.

## 3. Streams, Entries, Record IDs, and Consumer Groups

A Stream stores entries under a Redis key:

~~~text
Redis key: orders.events

1700000000100-0
  eventId=evt-101
  orderId=order-101
  eventType=ORDER_CREATED
  schemaVersion=1

1700000000101-0
  eventId=evt-102
  orderId=order-102
  eventType=ORDER_CREATED
  schemaVersion=1
~~~

An entry has an ID of the form `milliseconds-sequence`. With `XADD ... *`, Redis auto-generates the ID. The ID marks the entry's position in the stream; it **does not replace** the business event ID used by producers for deduplication.

Consumer groups track read positions and unacknowledged messages:

~~~text
                         orders.events
                              |
            +-----------------+-----------------+
            |                                   |
        group A:                           group B:
       order-workers                    analytics-workers
            |                                   |
      +-----+-----+                             |
      |           |                         analytics-1
   worker-A    worker-B
~~~

Two consumers in the **same group** split new entries. Two **different groups** track independent positions and can both process every entry for separate purposes.

| Component | Example | Role |
|---|---|---|
| Stream key | `orders.events` | Holds entries |
| Group | `order-workers` | Shares work and manages a PEL |
| Consumer | `worker-A` | Worker identity inside the group |
| Record ID | `1700000000100-0` | Entry identifier within the stream |
| Business event ID | `evt-101` | Identifies the business operation across retries/dedup |
| PEL | Pending Entries List | Tracks delivered, unacknowledged entries |

**`XACK` does not delete an entry from the Stream.** It only clears the entry's pending state for the specified group.

## 4. Preparing Redis and the Application

Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

To run an isolated Redis test server, you can use Docker:

~~~bash
docker run --rm --name redis-streams-lab -p 6379:6379 redis:7.2.5-alpine
~~~

The Redis tag in the example only illustrates a concrete version. In real projects, choose a Redis version/distribution matching production and verify the image used. Never point destructive lab experiments at public ports or production Redis.

Verify:

~~~bash
redis-cli PING
~~~

Expected output:

~~~text
PONG
~~~

Spring Boot 3.x configuration:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 5s

app:
  orders:
    stream-key: orders.events
    group: order-workers
    poll-delay-ms: 250
~~~

`XREADGROUP BLOCK` can wait several seconds when the stream is empty; the command timeout must accommodate the `BLOCK` duration plus network overhead. If production uses Sentinel/Cluster/TLS/ACL, do not simply copy the standalone example.

## 5. Practicing via Redis CLI Before Writing Java

### 5.1. Creating a Consumer Group

~~~bash
redis-cli XGROUP CREATE orders.events order-workers 0-0 MKSTREAM
~~~

Components:

- `orders.events`: Stream name.
- `order-workers`: consumer group name.
- `0-0`: allows the group to read existing entries from the start of the stream when reading new messages.
- `MKSTREAM`: creates an empty stream if it does not yet exist.

On success, it returns `OK`. If the group already exists, Redis returns a `BUSYGROUP` error. During automatic bootstrap, treat only `BUSYGROUP` as "group already exists"—do not swallow all exceptions.

### 5.2. Distinguishing Group Offsets `0-0` and `$`

~~~bash
redis-cli XGROUP CREATE other.events other-group '$' MKSTREAM
~~~

Starting from `$` begins at the current tail, so pre-existing entries are not delivered as new messages via `>`. Use `0-0` when the group must process existing history.

If the group already exists, re-running `XGROUP CREATE` does not update its offset. Never destroy an active group holding pending items just to move its read position.

### 5.3. Publishing Messages

~~~bash
redis-cli XADD orders.events '*' eventId evt-001 orderId order-101 eventType ORDER_CREATED schemaVersion 1
redis-cli XADD orders.events '*' eventId evt-002 orderId order-102 eventType ORDER_CREATED schemaVersion 1
redis-cli XADD orders.events '*' eventId evt-003 orderId order-103 eventType ORDER_CREATED schemaVersion 1
~~~

`*` lets Redis generate the Record ID. Inspect entries:

~~~bash
redis-cli XRANGE orders.events - + COUNT 10
redis-cli XLEN orders.events
~~~

`XRANGE` is for inspecting data. It does not advance consumer group offsets, create pending entries, or replace `XREADGROUP` for workers.

### 5.4. First Worker Reading Messages

~~~bash
redis-cli XREADGROUP GROUP order-workers worker-A COUNT 2 STREAMS orders.events '>'
~~~

Redis delivers up to two new entries to consumer `worker-A`. The `>` symbol requests entries never previously delivered to the group.

Check pending entries:

~~~bash
redis-cli XPENDING orders.events order-workers
redis-cli XPENDING orders.events order-workers - + 10
~~~

### 5.5. Acknowledging an Entry

Use a real Record ID from the output above, for illustration:

~~~bash
redis-cli XACK orders.events order-workers 1700000000100-0
~~~

Result is typically `1` if the entry was pending in the group and is now acknowledged, or `0` if no matching pending entry existed.

Verify:

~~~bash
redis-cli XPENDING orders.events order-workers
redis-cli XRANGE orders.events - +
~~~

After ACK, the entry can still appear in `XRANGE`; it is simply removed from the group's PEL.

## 6. Distributing Messages Across Consumers

Try opening two terminals:

~~~bash
redis-cli XREADGROUP GROUP order-workers worker-A COUNT 1 BLOCK 2000 STREAMS orders.events '>'
~~~

~~~bash
redis-cli XREADGROUP GROUP order-workers worker-B COUNT 1 BLOCK 2000 STREAMS orders.events '>'
~~~

Redis hands new entries to whichever consumer executes the read command. **There is no guarantee of an even 50/50 split or strict round-robin per entry.** A faster or continuously polling consumer may receive more entries.

Creating a separate `analytics-workers` group on the same stream lets that group read events independently. In summary:

- Same group: work sharing.
- Different groups: independent processing.
- Pub/Sub: broadcasts to online subscribers, with no PEL/ACK.
- Streams: entries remain until trimmed/deleted or Redis data is lost.

## 7. Designing Payloads for Real-World Processing

Sample event payload:

~~~text
eventId       = evt-001
eventType     = ORDER_CREATED
schemaVersion = 1
orderId       = order-101
createdAt     = 2026-11-13T10:15:30Z
~~~

Include:

- **eventId** generated stably by the producer across all retries of the same event.
- **eventType** to dispatch handlers.
- **schemaVersion** to support rolling upgrades.
- **aggregateId** like `orderId` to distinguish business entities.
- **createdAt** to measure business processing latency.
- **trace/correlation ID** if needed, without using high-cardinality IDs as metric labels.

You do not have to cram the entire order JSON into the Stream. For huge payloads or sensitive data, store only the ID and have the worker read from the source of truth.

Define handling for unsupported `eventType`/`schemaVersion` values: classify errors, retain for investigation or route to a DLQ, and never silently ACK and drop them.

## 8. Spring Data Redis Producer: Writing Messages with `XADD`

Example producer:

~~~java
package com.example.orders.stream;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.connection.stream.StreamRecords;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class OrderEventPublisher {

    public static final String STREAM = "orders.events";

    private final StringRedisTemplate redis;

    public OrderEventPublisher(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public RecordId publish(
            String eventId,
            String orderId
    ) {
        Map<String, String> payload = new LinkedHashMap<>();
        payload.put("eventId", eventId);
        payload.put("eventType", "ORDER_CREATED");
        payload.put("schemaVersion", "1");
        payload.put("orderId", orderId);
        payload.put("createdAt", Instant.now().toString());

        var record = StreamRecords.mapBacked(payload)
            .withStreamKey(STREAM);

        RecordId id = redis.opsForStream().add(record);

        if (id == null) {
            throw new IllegalStateException(
                "Redis did not return RecordId"
            );
        }
        return id;
    }
}
~~~

`StringRedisTemplate` works cleanly with String values and fields. If using a template with a different serializer, verify raw keys and hash field/value bytes via integration tests against real Redis.

### 8.1. Record IDs Differ from Business Event IDs

A producer calls:

~~~text
XADD eventId=evt-001 -> Redis appended, response lost
Retry XADD eventId=evt-001 -> Redis appended again
~~~

Redis can generate **two different Record IDs** for the same `eventId`. Thus producers must not generate a fresh business event ID on each retry, and consumers must deduplicate using this stable ID.

### 8.2. Successful Publish Does Not Mean Successful Processing

`XADD` returning a Record ID only confirms Redis accepted/appended the entry per command status. It does not prove:

- A worker read it.
- The handler finished.
- Emails/webhooks were sent.
- The business DB committed.
- The message was `XACK`ed.
- Data was fsynced/replicated durably across all crashes.

If an API needs to report job progress, expose dedicated states like `QUEUED`, `PROCESSING`, `SUCCEEDED`, and `FAILED` instead of reporting "completed" immediately after `XADD`.

## 9. The Dual-Write Gap: DB Commit Followed by Publish

If code does:

~~~text
BEGIN DATABASE TRANSACTION
  INSERT order
COMMIT
XADD orders.events
~~~

the service can crash after `COMMIT` and before `XADD`. The order exists, yet no event was published.

Reversing the order is no safer:

~~~text
XADD
BEGIN DATABASE TRANSACTION
  INSERT order
ROLLBACK
~~~

The event exists, yet no order exists.

Spring JPA's `@Transactional` **does not automatically include Redis Streams in the same distributed transaction**.

### 9.1. Transactional Outbox

For critical workflows, consider:

~~~text
BEGIN DB TRANSACTION
  INSERT orders
  INSERT outbox_events(eventId, payload, status)
COMMIT
     |
     v
Outbox publisher
  -> read unpublished events
  -> XADD with stable eventId
  -> mark published
     |
     v
Redis Stream consumer group
~~~

The outbox publisher might crash after `XADD` and before updating outbox status, causing the message to be republished. Hence **outbox and consumer idempotency belong together**.

Redis Streams transports work, while the database/outbox ensures events emitted alongside business changes are not lost when needed.

## 10. Consumer Group Reading New Entries with `XREADGROUP`

CLI:

~~~bash
redis-cli XREADGROUP GROUP order-workers worker-A COUNT 10 BLOCK 2000 STREAMS orders.events '>'
~~~

Parameters:

| Parameter | Meaning |
|---|---|
| `GROUP order-workers worker-A` | Group and consumer identity |
| `COUNT 10` | Maximum number of entries requested per read |
| `BLOCK 2000` | Wait up to ~2 seconds when no new entries exist |
| `STREAMS orders.events` | Stream key to read |
| `>` | Deliver entries never previously delivered to the group |

In Spring Data Redis:

~~~java
List<MapRecord<String, Object, Object>> records =
    redis.opsForStream().read(
        Consumer.from("order-workers", consumerName),
        StreamReadOptions.empty()
            .count(10)
            .block(Duration.ofSeconds(2)),
        StreamOffset.create(
            "orders.events",
            ReadOffset.lastConsumed()
        )
    );
~~~

`ReadOffset.lastConsumed()` in a group read corresponds to reading new entries from the group's position. Do not use it to fetch pending entries left by crashed consumers.

When no messages arrive, the API may return `null` or an empty collection depending on the call path; handle both.

## 11. Java Consumer: Process First, Then ACK

First separate the business handler:

~~~java
package com.example.orders.stream;

public interface OrderEventHandler {
    // Must be idempotent by stable eventId.
    void applyOnce(
        String eventId,
        String eventType,
        String orderId
    );
}
~~~

A simple polling worker:

~~~java
package com.example.orders.stream;

import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.connection.stream.StreamReadOptions;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class OrderStreamWorker {

    private static final Logger log =
        LoggerFactory.getLogger(OrderStreamWorker.class);

    private static final String STREAM = "orders.events";
    private static final String GROUP = "order-workers";

    private final StringRedisTemplate redis;
    private final OrderEventHandler handler;

    private final String consumerName =
        "worker-" + UUID.randomUUID();

    public OrderStreamWorker(
            StringRedisTemplate redis,
            OrderEventHandler handler
    ) {
        this.redis = redis;
        this.handler = handler;
    }

    @Scheduled(fixedDelay = 250)
    public void readOnce() {
        List<MapRecord<String, Object, Object>> records;

        try {
            records = redis.opsForStream().read(
                Consumer.from(GROUP, consumerName),
                StreamReadOptions.empty()
                    .count(10)
                    .block(Duration.ofSeconds(2)),
                StreamOffset.create(
                    STREAM,
                    ReadOffset.lastConsumed()
                )
            );
        } catch (RuntimeException ex) {
            log.error("Cannot read Redis Stream", ex);
            return;
        }

        if (records == null || records.isEmpty()) {
            return;
        }

        for (var record : records) {
            handleAndAck(record);
        }
    }

    private void handleAndAck(
            MapRecord<String, Object, Object> record
    ) {
        try {
            Map<Object, Object> fields = record.getValue();
            String eventId = required(fields, "eventId");
            String eventType = required(fields, "eventType");
            String orderId = required(fields, "orderId");

            // Succeeds only when the side effect has committed.
            handler.applyOnce(eventId, eventType, orderId);

            Long acked = redis.opsForStream()
                .acknowledge(STREAM, GROUP, record.getId());

            log.debug(
                "record={} eventId={} acked={}",
                record.getId(), eventId, acked
            );
        } catch (RuntimeException ex) {
            // Do not ACK when the handler fails.
            log.error(
                "Processing failed for record={}",
                record.getId(), ex
            );
        }
    }

    private static String required(
            Map<Object, Object> fields,
            String name
    ) {
        Object value = fields.get(name);
        if (!(value instanceof String text)
                || text.isBlank()) {
            throw new IllegalArgumentException(
                "Invalid field: " + name
            );
        }
        return text;
    }
}
~~~

Enable scheduling:

~~~java
@SpringBootApplication
@EnableScheduling
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Key highlights of the example:

- Separate consumer identity per process.
- `ReadOffset.lastConsumed()` reads new entries.
- Each record is processed and then ACKed individually.
- If the handler throws, the record stays pending.
- An ACK timeout does not mean the side effect failed to run.
- This is a **minimal baseline**, lacking reclaim, DLQ, and complete shutdown handling.
- A `@Scheduled` task calling `BLOCK 2s` ties up a scheduler thread; use a dedicated executor/scheduler if other scheduled jobs exist.

## 12. Creating the Group Before Workers Run

The example worker requires the group to exist. In the lab:

~~~bash
redis-cli XGROUP CREATE orders.events order-workers 0-0 MKSTREAM
~~~

A Spring API approach when the stream already exists:

~~~java
redis.opsForStream().createGroup(
    "orders.events",
    ReadOffset.from("0-0"),
    "order-workers"
);
~~~

With APIs that do not pass `MKSTREAM`, creating a group on a missing stream fails. Bootstrap the group during migration/deployment, or invoke `XGROUP CREATE ... MKSTREAM` through the Redis command interface.

If multiple pods start together, one pod creates the group and others receive `BUSYGROUP`. Handle **only the specific "group already exists" error**; never catch and ignore all exceptions, which could hide `NOAUTH`, wrong endpoints, or network outages.

Never use `XGROUP DESTROY` as routine initialization; it wipes crucial group and PEL state.

## 13. Why ACK Only After Business Commit?

Two sequences:

**Dangerous sequence**

~~~text
XREADGROUP
   |
   v
XACK
   |
   v
Call external API
   |
   X worker dies
~~~

The message is no longer pending; job delivery can be lost.

**Sequence suited for retryability**

~~~text
XREADGROUP
   |
   v
Validate payload
   |
   v
Run idempotent handler
   |
   v
Commit durable business outcome
   |
   v
XACK
~~~

If the worker crashes **after commit and before ACK**, the message remains pending and can be reprocessed. That is why the handler must be idempotent.

`XACK` only modifies the group's PEL; an ACKed entry remains in the stream until trimmed or deleted.

## 14. Pending Entries List (PEL)

When `XREADGROUP` delivers a message to a consumer, Redis records entry metadata in the group's PEL.

~~~text
stream entry
     |
     v
XREADGROUP -> consumer-A
     |
     v
Pending Entries List:
   record ID
   consumer owner
   idle time
   delivery count
     |
     +-- XACK -> remove pending entry
     |
     +-- error / crash -> remains pending
~~~

Inspect:

~~~bash
redis-cli XPENDING orders.events order-workers
redis-cli XPENDING orders.events order-workers - + 10
redis-cli XINFO GROUPS orders.events
redis-cli XINFO CONSUMERS orders.events order-workers
~~~

`XPENDING` offers summary and extended forms, showing IDs, owners, idle durations, and delivery counts.

**The PEL stores delivery metadata, not an independent copy of the payload.** If the stream entry is trimmed or deleted, pending metadata may remain while the payload needed for reprocessing is gone.

### 14.1. What Pending Count Does Not Tell You

- Excludes entries never delivered to the group.
- Does not prove the handler started processing.
- Does not prove business effects failed if a worker committed and lost its ACK.
- Does not directly indicate SLA breaches without entry age.
- Does not replace end-to-end business completion metrics.

One message pending for 30 minutes can be far more severe than 100 pending items delivered 1 second ago.

## 15. Pending Messages Do Not Automatically Become New Entries

A common misconception:

~~~text
worker-A receives evt-001
worker-A crashes without ACK
worker-B polls with '>'
~~~

Worker-B will **never receive `evt-001` automatically** via `>`, because the message was already delivered to the group. It stays pending under owner `worker-A`.

To recover:

- The original consumer re-reads **its own pending entries**.
- Or another consumer **claims** entries idle long enough via `XCLAIM` or `XAUTOCLAIM`.

Thus, if you only poll for new entries and ACK, the system **can leave pending work stranded forever** whenever a worker crashes.

## 16. Re-Reading a Consumer's Own Pending Entries

CLI:

~~~bash
redis-cli XREADGROUP GROUP order-workers worker-A COUNT 10 STREAMS orders.events 0
~~~

When the ID is not `>`, group reads inspect the pending history of the **specified consumer**, not pending items belonging to other consumers.

Spring API:

~~~java
var pending = redis.opsForStream().read(
    Consumer.from("order-workers", "worker-A"),
    StreamReadOptions.empty().count(10),
    StreamOffset.create(
        "orders.events",
        ReadOffset.from("0-0")
    )
);
~~~

Notes:

- Use the exact consumer name owning the pending entries.
- Re-reading can affect idle/delivery metadata.
- Continuously reading from `0-0` without ACKing re-fetches the same entries repeatedly.
- Enforce retry delays and attempt limits.
- Do not rely on this alone to rescue pending items from a worker name that no longer exists.

When scaling dynamically or changing worker names on every restart, run a claim-based recovery task.

## 17. Recovering with `XAUTOCLAIM`

Redis 6.2+ supports:

~~~bash
redis-cli XAUTOCLAIM orders.events order-workers worker-B 60000 0-0 COUNT 10
~~~

Meaning:

| Component | Purpose |
|---|---|
| `orders.events` | Stream |
| `order-workers` | Group |
| `worker-B` | Consumer receiving ownership |
| `60000` | Claim only entries idle at least 60,000 ms |
| `0-0` | Starting cursor to scan the PEL |
| `COUNT 10` | Cap on entries returned per call |

The result contains a new cursor and claimed entries. Depending on the Redis version, the reply may also include IDs whose payloads are gone while pending metadata remains. The recovery loop must advance the cursor and handle replies according to your Redis version.

### 17.1. Do Not Claim Too Early

Suppose a handler calls a slow API taking 90 seconds. If recovery claims after 5 seconds:

~~~text
worker-A still processing
     |
     +-- after 5 seconds
              |
              v
worker-B claims same message
              |
              v
both may run business side effect
~~~

Changing ownership in the PEL does not force `worker-A` to stop running. Therefore:

- Choose idle thresholds based on handler duration and SLAs.
- Maintain idempotency even with reasonable thresholds.
- For very long jobs, use ownership/heartbeat mechanisms or external work leases outside the PEL when fitting.
- Do not treat `XAUTOCLAIM` as a distributed lock preventing concurrent execution.

### 17.2. The Recovery Loop Should Run Independently

A schedule might look like:

~~~text
Every 30 seconds:
  scan pending with XAUTOCLAIM
  claim entries idle beyond threshold
  process with same idempotent handler
  XACK after successful commit
  advance scan cursor
  record metrics
~~~

Bound entries per cycle, concurrency, retry rate, and logging. Do not scan the entire PEL continuously during peak traffic.

### 17.3. Using `XCLAIM` When IDs Are Known

`XCLAIM` takes a specific list of IDs and an idle condition; it suits operational tooling targeting specific pending entries. `XAUTOCLAIM` is more convenient for background recovery scanning automatically.

Both can redeliver an entry; neither replaces durable deduplication.

## 18. Preventing Duplicate Processing with an Idempotent Handler

Two common scenarios:

**Producer retry**

~~~text
XADD eventId=evt-001 -> appended
response lost
retry XADD eventId=evt-001 -> another RecordId
~~~

**Consumer crash**

~~~text
XREADGROUP evt-001
business transaction COMMIT
worker crashes before XACK
another worker reclaims evt-001
~~~

Both cause the same business event to be seen multiple times.

The solution is a **stable business event ID and a durable idempotency record**.

### 18.1. Example Database Schema

~~~sql
CREATE TABLE processed_stream_events (
    consumer_group VARCHAR(128) NOT NULL,
    event_id VARCHAR(128) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_group, event_id)
);
~~~

Within **one DB transaction**:

~~~text
BEGIN
  INSERT processed_stream_events(group, eventId)
  if insert says "already exists":
      return no-op
  else:
      perform business DB side effect
COMMIT
~~~

The unique constraint prevents two transactions from recording first-time processing for the same `group + eventId`.

### 18.2. Spring Service Pseudocode

~~~java
@Service
public class OrderHandler implements OrderEventHandler {

    private final ProcessedEventRepository processed;
    private final OrderRepository orders;

    @Transactional
    @Override
    public void applyOnce(
        String eventId,
        String eventType,
        String orderId
    ) {
        if (!processed.tryInsert(
                "order-workers", eventId)) {
            return;
        }

        if (!"ORDER_CREATED".equals(eventType)) {
            throw new IllegalArgumentException(
                "Unsupported eventType"
            );
        }

        orders.markConfirmationPending(orderId);
    }
}
~~~

`ProcessedEventRepository.tryInsert` is an abstraction to implement via an atomic database operation, such as `INSERT ... ON CONFLICT DO NOTHING` checking affected row count.

**Important:** inserting the idempotency marker and applying the business update must share the same transaction. If the marker commits first and the business operation fails afterward, the message would appear processed even though the side effect never occurred.

### 18.3. External APIs Do Not Roll Back with the DB

If a handler sends an email and crashes before recording the marker, the email may send twice on retry.

Consider:

- Downstream APIs supporting idempotency keys.
- An outbox/command table for email-send requests.
- Send status tracking and provider reconciliation.
- Business-specific deduplication/replay logic.
- Never claiming exactly-once without matching safeguards on external side effects.

## 19. Error Handling and Retry Policies

Not every error should be retried:

| Category | Example | Handling |
|---|---|---|
| Transient | DB timeout, HTTP 503 | Backoff + jitter + retry cap |
| Permanent payload | Missing `eventId`, unsupported version | DLQ/quarantine |
| Valid duplicate | Event ID already committed | No-op and ACK |
| Redis unavailable | Read/ACK command timeout | Reconnect, treat outcome as uncertain |
| Misconfiguration | `NOGROUP`, ACL denial | Fix configuration, alert |
| Uncertain external outcome | Email API timeout after sending | Reconcile/dedupe, do not blindly repeat |
| Business validation | Order not found | Per contract: bounded retry or quarantine |

If a handler throws and skips ACK, the entry stays pending. However, **leaving items pending without a recovery job is not a complete retry policy**.

### 19.1. Avoiding Poison-Message Hot Loops

An entry missing a required field fails the handler every time. Re-reading it immediately creates:

~~~text
read -> fail -> read -> fail -> read -> fail -> ...
~~~

This spikes CPU, logs, and DB load. Add:

- Exponential backoff with jitter.
- Retry limits and maximum delay caps.
- Fatal vs transient error classification.
- A dead-letter queue after an appropriate attempt threshold.
- Age/retry metrics and alerts.
- Ensuring one poison message never stalls healthy entries indefinitely.

## 20. Designing a Dead-Letter Queue

A stream dedicated to messages that cannot be processed automatically:

~~~text
orders.events.dlq
~~~

Payload can include:

~~~text
originalStream     orders.events
originalRecordId   1700000000100-0
eventId            evt-001
eventType          ORDER_CREATED
failureCategory    INVALID_SCHEMA
attemptCount       5
failedAt           2026-11-13T10:30:00Z
~~~

Never put passwords, tokens, or sensitive raw stack traces into Redis messages. A DLQ must have clear ownership and retention.

### 20.1. Ordering DLQ Move and ACK

Dangerous sequence:

~~~text
XACK original
XADD DLQ
crash between steps -> message disappears from pending
~~~

A more recoverable sequence:

~~~text
XADD DLQ
XACK original
~~~

If a crash happens after `XADD DLQ` and before `XACK`, the message may be sent to the DLQ again on retry. Thus DLQ and recovery should deduplicate by `eventId`/`originalRecordId`.

In Redis Cluster, you cannot assume an atomic multi-key Lua script/transaction between the original stream and the DLQ if the two keys sit in different hash slots. If Redis-side atomicity is required, verify same-slot constraints, Redis version, and client behavior—remembering Redis atomicity still does not cover external DBs.

### 20.2. Operating a DLQ

- Monitor DLQ length and oldest entry age.
- Define who investigates.
- Provide replay tooling preserving the stable event ID.
- Maintain audit logs for manual retries.
- Throttle replays to avoid overload.
- Never delete DLQ items simply because an alert fired.
- Keep retention long enough to cover incident resolution.

## 21. Retention: Preventing Unbounded Growth Without Losing Work

`XACK` does not delete entries. If producers write continuously, the stream grows unboundedly without retention.

Example:

~~~bash
redis-cli XADD orders.events MAXLEN '~' 100000 '*' eventId evt-500 orderId order-500 eventType ORDER_CREATED
~~~

In standard Redis CLI, raw syntax is:

~~~text
XADD key MAXLEN ~ count * field value ...
~~~

`~` performs approximate trimming, potentially keeping slightly more than the target count. Separate trim command:

~~~bash
redis-cli XTRIM orders.events MAXLEN '~' 100000
~~~

### 21.1. Improper Trimming Can Destroy Pending Payloads

Suppose `worker-A` received an entry without ACKing yet, while producers write rapidly and trim old entries. At recovery time, the PEL may retain metadata while the original entry is gone, depending on Redis version and trimming mechanics.

Retention must account for:

- Peak producer rate.
- Maximum consumer downtime.
- Minimum processing rate when degraded.
- Retry/backoff/recovery windows.
- The slowest consumer group.
- Audit/replay needs.
- Storage/memory headroom.
- Data RPO/RTO.

Do not pick `MAXLEN 100000` just because it looks neat. At 10,000 entries/sec, 100,000 entries equals roughly 10 seconds of data at that rate, **even before considering batch/trimming behavior**.

### 21.2. Account for Every Consumer Group

If `order-workers` ACKs quickly while `analytics-workers` lags by an hour, trimming entries ACKed by `order-workers` breaks analytics. Retention must protect all active consumer groups that need the data.

When a group is retired, follow a decommissioning process checking pending/lag before deleting group metadata rather than dropping it silently.

## 22. Work Ordering and Multiple Workers

Redis Streams maintain entry ordering by ID, yet **do not guarantee side-effect completion order** across multiple workers.

~~~text
entry 100 -> worker-A -> handler takes 5 seconds
entry 101 -> worker-B -> handler takes 100 ms

entry 101 may commit before entry 100.
~~~

If events are independent, this is fine. If two events for the same order must apply in sequence, add:

- Aggregate `orderId` and version/sequence numbers in payloads.
- Version guards in the DB.
- Partition keys and work routing.
- A single sequential consumer within the scope requiring ordering.
- Reconciliation when gaps are detected.
- Avoiding increasing concurrency in ways that violate invariants.

Consumer groups **do not partition by `orderId` automatically**. The same order can be handed to different consumers across consecutive deliveries.

### 22.1. Version Guard

~~~text
DB order version = 4

Event version 5 -> apply -> DB version 5
Event version 5 -> duplicate -> no-op
Event version 7 -> missing version 6 -> defer/reconcile
~~~

This is only a pattern; business logic must define versioning/consistency per actual aggregate.

## 23. `StreamMessageListenerContainer` Instead of Manual Polling

Spring Data Redis provides `StreamMessageListenerContainer` to manage polling and callbacks.

Illustrative configuration skeleton:

~~~java
@Bean
StreamMessageListenerContainer<String,
        MapRecord<String, String, String>> orderStreamContainer(
        RedisConnectionFactory connectionFactory
) {
    var options = StreamMessageListenerContainer
        .StreamMessageListenerContainerOptions
        .<String, MapRecord<String, String, String>>builder()
        .pollTimeout(Duration.ofSeconds(2))
        .build();

    return StreamMessageListenerContainer.create(
        connectionFactory, options
    );
}
~~~

Registering a subscription:

~~~java
container.receive(
    Consumer.from("order-workers", consumerName),
    StreamOffset.create(
        "orders.events",
        ReadOffset.lastConsumed()
    ),
    message -> {
        // Validate -> handle idempotently -> XACK.
    }
);
~~~

This snippet is an **API skeleton**; real applications need type imports, container subscription lifecycle management, and generic signatures verified for their Spring Data Redis version.

The listener container handles polling/dispatch, **without automatically guaranteeing**:

- That the group already exists.
- Transactional/idempotent handlers.
- Post-commit ACKs.
- Pending recovery/claiming.
- Backoff retries.
- DLQs.
- Ordering and consumer scaling.
- Durable publishing from the DB.

Some APIs offer auto-ack. Never enable auto-ack for critical work if it ACKs entries before business side effects actually commit.

## 24. Reactive Readers and Concurrency Limits

With WebFlux, you can use `StreamReceiver` and reactive operations appropriate to your version. Keep the same rule:

~~~text
Reactive receive
   -> validate
   -> business side effect
   -> commit
   -> XACK
~~~

Specifically:

- Avoid `.block()` on Netty event-loop threads.
- Bound `flatMap(concurrency)` for independent handlers.
- When ordering is required, consider `concatMap` or partitioning.
- Cancellation can occur after Redis already delivered an entry.
- Pending recovery is still mandatory.
- Do not spawn unbounded publishers/commands.
- Client timeouts after ACK carry the same uncertain outcome as in synchronous models.

Reactive backpressure does not make Redis operations or side effects exactly-once.

## 25. Sizing Consumers, Connections, and Throughput

There are three distinct parameters:

1. Number of consumer processes or subscriptions in the same group.
2. Entries fetched per read (`COUNT`).
3. Concurrent handlers running simultaneously.

Hypothetical example:

~~~text
4 application pods
2 consumers per pod
COUNT 10
up to 8 concurrent handler tasks per pod
~~~

Consumer and handler counts do not necessarily equal Redis TCP connection counts, especially with Lettuce shared/dedicated connection semantics.

If a handler averages 200 ms, one sequential worker has an ideal throughput of roughly:

\[
1 / 0.2 = 5 \text{ events/s}
\]

With 10 independent workers and sufficient downstream capacity, the ideal rate is around 50 events/s. In practice, measure Redis read/ACK RTT, DB, APIs, payloads, retries, latency percentiles, and contention.

### 25.1. Backlog Grows When Producers Outpace Consumers

Suppose:

~~~text
Arrivals = 500 events/s
Completions = 350 events/s
Net growth = 150 events/s
~~~

After 10 minutes, uncompleted backlog grows by roughly:

\[
150 \times 600 = 90{,}000
\]

if rates stay constant. This drives early alerting before business deadlines are missed.

### 25.2. Blocking Connection Budget

`XREADGROUP BLOCK` holds a connection while waiting. With Lettuce, blocking commands typically require dedicated connections depending on factory/client configuration; with Jedis, pool demand needs even closer measurement.

Account for:

~~~text
blocking readers
+ transaction/session connections
+ Pub/Sub subscriptions
+ regular Redis connections
+ Redis Cluster node connections
+ rolling deployment surge
~~~

Adding workers will not raise throughput if the DB or email provider is the bottleneck.

## 26. What Should You Monitor?

Redis CLI:

~~~bash
redis-cli XLEN orders.events
redis-cli XINFO STREAM orders.events
redis-cli XINFO GROUPS orders.events
redis-cli XINFO CONSUMERS orders.events order-workers
redis-cli XPENDING orders.events order-workers
redis-cli XPENDING orders.events order-workers - + 20
redis-cli INFO memory
redis-cli INFO clients
redis-cli INFO commandstats
~~~

| Metric | Meaning | Limitation |
|---|---|---|
| `XLEN` | Total entries remaining in stream | Not unprocessed backlog |
| Group `pending` | Entries delivered, not yet ACKed | Excludes undelivered entries |
| Group `lag` | Estimated undelivered entries when Redis tracks it | Not unfinished side effects |
| `last-delivered-id` | Last new-delivery position | Does not prove ACK |
| Consumer pending | Pending items owned by consumer | Does not prove worker is alive |
| Pending idle | Time since last delivery | Not business event age |
| Delivery count | Redis delivery attempts | Does not equal external API call count |
| Stream memory | Key RAM reported by Redis | Excludes full RSS/COW/cgroup overhead |

### 26.1. Business Completion Metrics

Instrument:

- Event publish successes/failures.
- Event receive counts.
- Handler successes/errors/retries.
- Processing duration.
- Latency from `createdAt` to **side-effect commit**.
- Oldest uncompleted business event.
- Pending recovery/claim counts.
- DLQ count and oldest entry age.
- ACK successes/timeouts.
- Duplicate event no-op counts.
- Consumer reconnects.

Metric names can look like `app_stream_handler_total` and `app_stream_processing_delay_seconds`, though these are **application-defined custom metrics**, not provided out of the box by Spring Data Redis.

Never use raw `eventId`, `orderId`, or Redis keys as Prometheus labels: cardinality and data exposure risks are severe.

## 27. Graceful Shutdown and Rolling Deploys

When Kubernetes stops a worker:

~~~text
SIGTERM
  -> stop polling new messages
  -> let in-flight handlers finish within grace period
  -> ACK only successfully committed work
  -> exit
~~~

If the grace period expires before ACK, messages stay pending for recovery. Ensure:

- Bounded `BLOCK` timeouts.
- Clean subscription/scheduler lifecycle shutdown.
- Clear consumer identity policies.
- Adequate `terminationGracePeriodSeconds`.
- Recovery workers claiming pending entries after a safe idle threshold.
- Never ACKing all in-flight entries on `SIGTERM`.

### 27.1. Consumer Names Across Restarts

- **Stable name per worker identity:** easy to re-read its own pending items, but must prevent two processes from sharing the same name.
- **Unique name per process:** prevents collisions during rolling deploys, though old processes' pending items must be claimed.

Choose per your architecture; do not treat the UUID in the example as the universal answer for every service.

## 28. Failure Scenarios to Test

### 28.1. Worker Dies Before Business Commit

~~~text
XREADGROUP -> pending
worker crashes
recovery claims
handler executes once
XACK
~~~

The test verifies events are not forgotten.

### 28.2. Worker Dies After Commit Before ACK

~~~text
XREADGROUP -> handler COMMIT
worker crashes before ACK
recovery claims
handler sees processed eventId -> no-op
XACK
~~~

The test verifies side effects do not execute twice.

### 28.3. Producer Timeout After XADD

~~~text
XADD actually appended
response lost
producer retries same eventId
second Redis entry appears
~~~

The test verifies deduplication by business event ID, not merely Record ID.

### 28.4. Handler Receives Invalid Schema

~~~text
missing eventId
-> validation error
-> retry policy decides permanent error
-> safely publish DLQ
-> ACK original after durable quarantine
~~~

Must never spin in a hot retry loop forever.

### 28.5. `XACK` or Redis Connection Errors

The handler may have committed while ACK succeeded, failed, or timed out. Tests must distinguish uncertain outcomes and avoid repeating non-idempotent external side effects.

### 28.6. Stream Trimmed Too Early

Test alerts/retention when a consumer group stays offline for a long time or backlog grows. Never set `MAXLEN` small enough to wipe unprocessed entries.

### 28.7. Two Workers Competing on Reclaim

Test `worker-A` running slowly (not dead) while `worker-B` claims after the idle threshold; only business-layer idempotency protects side effects.

### 28.8. Restarts and Failover

Test appropriate Redis persistence/replication, startup group state, reconnects, and processing replays; never assume Redis write ACKs mean zero loss if the primary dies before replication/persistence.

## 29. Testcontainers with a Real Redis Server

An integration test needs real Redis, not just a mocked `RedisTemplate`. You can use:

~~~java
@SpringBootTest
@Testcontainers
class StreamIntegrationTest {

    @Container
    static final GenericContainer<?> redis =
        new GenericContainer<>(
            DockerImageName.parse("redis:7.2.5-alpine")
        ).withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", redis::getHost);
        registry.add(
            "spring.data.redis.port",
            () -> redis.getMappedPort(6379)
        );
    }

    @Autowired
    StringRedisTemplate template;

    @Test
    void shouldReadAndAckMessage() {
        // 1. Create namespaced stream/group.
        // 2. XADD with stable eventId.
        // 3. XREADGROUP with test consumer.
        // 4. Assert payload, RecordId, and pending.
        // 5. Handler commits, XACK.
        // 6. Assert pending is cleared.
    }
}
~~~

This is an **illustrative skeleton**, not a full runnable test because setup/assertion steps must be filled in for your real contract. The key point is that the test JVM connects to the Redis container via its dynamic host and port.

The suite should include:

| Test | Objective |
|---|---|
| Publish/read/ACK | Happy path |
| Two consumers, one group | Work sharing |
| Two groups | Independent processing |
| Exception before ACK | PEL remains |
| Crash before commit | Reclaim and retry |
| Crash after commit | Idempotent no-op |
| Duplicate eventId | Deduplication |
| Poison message | DLQ routing |
| Claim after idle | Recovery threshold |
| Early claim while worker alive | No duplicate business effect |
| Redis timeout | Uncertain outcome handling |
| Trimming | Retention safety |
| Stream missing/group missing | Error classification |
| Consumer restart | Pending recovery |
| Failover | Reconnect/retry semantics |
| Cluster topology | Slot routing/command support |

If a scheduled worker runs automatically inside the test context, it may steal messages before the test method reads them. Separate profiles, stream/group namespaces, or control lifecycles explicitly to prevent test races.

## 30. Redis Cluster: Hash Slot Constraints

In Redis Cluster, each stream key maps to one hash slot. Single-stream `XADD`/`XREADGROUP` calls are routed by cluster-aware clients to the slot-owning node.

However, a multi-stream `XREAD`/`XREADGROUP` command can hit **same-slot** constraints. Do not assume one command can read streams hosted across different primaries.

When co-location is needed:

~~~text
events:{tenant-42}:orders
events:{tenant-42}:payments
~~~

Both keys share a hash tag and map to the same slot. Still, overly broad hash tags can create hot slots.

When designing a DLQ:

~~~text
orders:{partition-1}:events
orders:{partition-1}:dlq
~~~

can help if Redis-side multi-key transactions/scripts are needed, subject to API, Redis version, and durability limits—remembering not to funnel all system events under one global hash tag just for convenience.

### 30.1. Failover and MOVED/ASK

Redis Cluster/Sentinel failover can trigger reconnects, timeouts, or `MOVED`/`ASK` redirects. In-flight commands can have uncertain outcomes.

- Producers still need stable `eventId`s.
- Consumers still need idempotency.
- Blocking reads need proper reconnect/resubscription.
- Pending items need recovery.
- Do not treat a standalone Redis integration test as proof of Cluster readiness.

## 31. Redis Durability, Eviction, and Risk of Losing Work

Redis Streams run in in-memory Redis. When used for critical job queues, consider:

- RDB snapshots may omit recent writes.
- AOF `appendfsync everysec` does not strictly guarantee at most one second of loss under all failures.
- Replica replication is normally asynchronous.
- Failovers can lose recently acknowledged writes.
- Redis memory pressure can reject writes.
- If an eviction policy allows evicting stream keys, jobs can be lost.
- If a stream is deleted or trimmed too early, the PEL cannot reconstruct lost payloads.

For critical workloads, consider **durable outboxes + reconciliation + retention**. Redis persistence/replication is quantified in RPO/RTO, never replaced by "Streams never lose messages".

### 31.1. Never Share Cache Eviction Policies with Non-Lossy Queues

If a Redis instance hosts both disposable caches and critical jobs, `allkeys-lru` can evict stream keys under RAM pressure. Separate workloads or choose policies matching each data contract.

`noeviction` does not solve capacity on its own; when memory fills, producers receive write errors. Combine backpressure, capacity alerts, and outboxes/retries.

## 32. Worker Operations Checklist

**Producer**

- [ ] Stable event ID, event type, schema version.
- [ ] Consistent stream key and serializer.
- [ ] Outbox if DB commit followed by publish must be reliable.
- [ ] Publish timeouts handled with deduplication.
- [ ] Metrics and alerts for publish failures.
- [ ] Payloads avoid unnecessary sensitive data.

**Consumer**

- [ ] Group created once at the right offset.
- [ ] Clear consumer identity per process/pod.
- [ ] `ReadOffset.lastConsumed()` used only for new entries.
- [ ] ACK only after side effects commit.
- [ ] Handler idempotent by business event ID.
- [ ] Pending recovery/`XAUTOCLAIM` implemented.
- [ ] Claim idle threshold not set too low.
- [ ] Retries with backoff, max attempts, and DLQ.
- [ ] Graceful shutdown does not prematurely ACK.
- [ ] Concurrency bounded to downstream capacity.
- [ ] Versioning/partitioning strategy when ordering matters.

**Redis and Operations**

- [ ] Monitor `XINFO GROUPS`, `XPENDING`, and consumer health.
- [ ] Track oldest uncompleted business event, not only `XLEN`.
- [ ] Retention protects both undelivered backlog and pending entries across all groups.
- [ ] Memory/disk headroom sized for payloads and backlog growth.
- [ ] Alerts for DLQ growth and documented redrive process.
- [ ] Failover, persistence, and RPO plans in place.
- [ ] Never use `XTRIM`/`XGROUP DESTROY` to "clear errors" without understanding data impact.
- [ ] Tested crashes, duplicates, ACK timeouts, and recovery.
- [ ] If using Cluster, tested same-slot/multi-stream behavior.

## 33. Misconceptions to Avoid

**"Consumer groups work like Pub/Sub; every consumer receives every entry."** False. Consumers in the same group split new entries.

**"`XREADGROUP >` automatically redelivers messages from crashed workers."** False. Pending messages must be re-read by the same consumer or claimed.

**"`XACK` deletes the entry from the Stream."** False. It only clears pending status within the group.

**"`XLEN` is the number of unprocessed jobs."** False. The stream also holds ACKed entries not yet trimmed.

**"`lag=0` means every event is complete."** False. Pending unacknowledged entries may still exist.

**"`XAUTOCLAIM` prevents all duplicates."** False. Stale workers may still be running, and producers can publish duplicates.

**"`COUNT 100` creates a 100-message transaction."** False. ACKs and side effects are not batch-atomic.

**"More consumers still preserve strict ordering."** False. Completion order can differ from Stream ID order.

**"JPA `@Transactional` makes DB and Redis `XADD` atomic."** False. You need an outbox or another consistency pattern.

**"`XADD` returning an ID means the event was fsynced on all replicas."** False. Durability depends on configuration and topology.

**"Auto-ACK fits every processor."** False. ACKing before business commits risks losing work.

**"No need to trim the Stream because messages vanish after ACK."** False. Retention must be designed explicitly.

**"A DLQ is just a dumping ground for failed messages."** False. It needs ownership, replay, dedup, and retention.

**"Reactive consumers need no concurrency limits."** False. Redis, network, buffers, and downstreams are all finite.

## 34. Conclusion and Recommended Implementation Flow

A Spring Data Redis Streams workflow can be structured as:

~~~text
Business DB transaction
       |
       +-- outbox if reliable publish is required
       |
       v
XADD (stable eventId)
       |
       v
Redis Stream
       |
       v
XREADGROUP ... >
       |
       v
Validate + idempotent handler
       |
       v
Commit side effect
       |
       v
XACK
       |
       +-- error/crash: PEL
                            |
                            v
                         XAUTOCLAIM
                            |
                      retry / DLQ
~~~

Core principles:

1. **Streams store entries; consumer groups manage distribution and the PEL.**
2. **`XREADGROUP ... >` reads new entries**; existing pending items require an explicit recovery mechanism.
3. **`XACK` runs only after side effects complete**, never to mask errors.
4. **Redelivery is normal**; require stable `eventId`s and durable idempotency.
5. **Outboxes bridge the DB-commit-to-publish gap** in workflows needing reliability.
6. **Retries and DLQs** handle poison messages without duplicating external side effects.
7. **Retention must protect both undelivered messages and pending items for every group.**
8. **Ordering, concurrency, and connection sizing** must match business rules and downstream capacity.
9. **Monitor business completion delay**, not merely stream length or pending count.
10. **Test crashes, reconnects, duplicates, and failovers** against real Redis servers/topologies before trusting a queue with critical work.

Redis Streams is a capable tool for building asynchronous workers in Spring Boot. System reliability comes not from a single Redis command, but from the **complete contract spanning producer, stream, consumer group, database, side effects, ACKs, recovery, and operations**.
