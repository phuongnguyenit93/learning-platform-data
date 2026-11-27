# Impact of `ReadOffset` on Missing or Duplicate Records in Spring Data Redis Streams

Redis Streams allows an application to store records with **ordered IDs** and read back records already written to the stream. In Spring Data Redis, `ReadOffset` determines **where the next read begins**. This seemingly minor choice decides whether a reader reads backlog, misses records arriving in the gap between two polls, or re-reads data upon restarting.

Three easily confused options:

- `ReadOffset.latest()`: starts from the current end of the stream; fits cases where you **only care about new records**, yet can skip existing data or records arriving between reads if you repeatedly re-acquire the tail position.
- `ReadOffset.from(id)`: reads records with IDs **greater than** a specific ID; suits readers managing their own checkpoints, though saving the checkpoint at the wrong moment can cause **missed** or **duplicate** processing.
- `ReadOffset.lastConsumed()`: used in a **consumer group** context to receive new records not yet delivered by the group via `XREADGROUP` (corresponding to `>` in Redis semantics). It does not automatically recover every *pending* record when a consumer fails.

Most importantly: **`ReadOffset` determines read position, not whether a record's business processing succeeded.** To build a reliable flow, combine offsets with checkpointing, ACKs, pending reclaiming, retention, and idempotency policies.

## 1. How Does a Redis Stream Store Records?

A Redis Stream contains entries consisting of an ID and a set of field/value pairs. Example using Redis CLI:

```redis
XADD orders:events * eventId evt-101 type ORDER_CREATED orderId order-101
XADD orders:events * eventId evt-102 type ORDER_PAID orderId order-101
XADD orders:events * eventId evt-103 type ORDER_SHIPPED orderId order-101
```

Redis might generate example IDs such as:

```text
1731000000000-0   ORDER_CREATED
1731000000100-0   ORDER_PAID
1731000000200-0   ORDER_SHIPPED
```

These numbers are illustrative, not fixed IDs guaranteed on your machine. IDs typically have two parts separated by `-`; Redis orders the stream by ID. Never treat IDs as business timestamps reliably derived from every producer's clock.

Data flow:

```text
          Redis Stream: orders:events

ID A            ID B              ID C
 |               |                 |
 v               v                 v
ORDER_CREATED -> ORDER_PAID -> ORDER_SHIPPED
                      ^
                      |
                Reader's current read position
```

A reader must decide whether to read from the **beginning of the stream**, **after a known ID**, or **only from records produced after the present moment**. Spring Data Redis expresses this choice using `ReadOffset`.

### 1.1. Redis Streams Differs from Redis Pub/Sub

Redis Pub/Sub delivers messages to connected subscribers without storing history for late subscribers. Redis Streams persists records in a data structure so readers can read by ID as long as records remain retained.

However, **being stored does not automatically guarantee zero data loss**. If a reader intentionally reads from the tail, advances its checkpoint past an unprocessed record, or the stream is trimmed before processing, data can still be missed.

## 2. Which Read Behaviors Does `ReadOffset` Map To?

In Redis CLI, `XREAD` uses a stream ID to express read position:

```redis
XREAD COUNT 10 STREAMS orders:events 0-0
```

This reads entries with IDs greater than `0-0`. Since most Redis-generated records have IDs greater than `0-0`, this is the common way to read remaining backlog.

To wait only for entries added **after the read command starts**, Redis supports the `$` symbol:

```redis
XREAD BLOCK 2000 STREAMS orders:events $
```

Inside a consumer group, `XREADGROUP` uses `>` to request **new entries not yet delivered to any consumer in the group**:

```redis
XREADGROUP GROUP order-workers worker-1 COUNT 10 STREAMS orders:events >
```

Java options are typically interpreted as:

| Spring Data Redis | Primary meaning | Use case |
|---|---|---|
| `ReadOffset.latest()` | Starts at the end of the stream at read time, similar to `$` in `XREAD` | Only need new messages, okay skipping history |
| `ReadOffset.from("0-0")` | Reads after ID `0-0` | Read backlog from the start of retained data |
| `ReadOffset.from(lastId)` | Reads entries with IDs greater than checkpoint `lastId` | Reader manages its own offset |
| `ReadOffset.lastConsumed()` | Reads at the group's delivery position, usually matching `>` in `XREADGROUP` | Consumer group receiving new entries |
| Specific ID in `XREADGROUP`, e.g., `0` | Inspects pending entries of that consumer per Redis semantics | Pending recovery, not reading all undelivered entries |

**Watch the scope:** `ReadOffset.lastConsumed()` is used with consumer groups; do not treat it as an automatic durable checkpoint for arbitrary standalone readers. Likewise, passing a numeric ID to `XREADGROUP` has different semantics from passing that ID to `XREAD`. Consider **both the read command and the offset value**.

### 2.1. The Supplied ID Is the *Already-Passed* Position, Not the First Entry to Read

Suppose there are three entries with IDs A, B, C where `A < B < C`.

```text
XREAD ... A  -> typically returns B, C
XREAD ... B  -> typically returns C
XREAD ... C  -> only waits for / receives entries newer than C
```

Redis applies the condition **ID greater than the supplied ID** for `XREAD`. If the checkpoint stores the last ID **successfully processed**, the next read uses that exact checkpoint.

A common bug is storing the ID **to be processed first** and passing it to `ReadOffset.from(id)`, causing that very entry to be skipped.

## 3. `ReadOffset.latest()`: Future-Only Reads and the Risk of Skipping Records

Suppose the stream already contains:

```text
A: ORDER_CREATED
B: ORDER_PAID
C: ORDER_SHIPPED
```

The reader starts with:

```java
StreamOffset.create(
    "orders:events",
    ReadOffset.latest()
)
```

When mapped to `XREAD` from `$`, Redis uses **the end of the stream at the moment the read command is processed** as the marker. A, B, and C already existed before that time and are not returned.

```text
A ---- B ---- C        | reader starts at tail
                       |
                       +---- D newly arrives -> can read D
```

This is the **right behavior if the requirement is observing real-time events from subscription time onward**. It is wrong if business logic requires processing A, B, and C as well.

### 3.1. Gaps Between Two Polls

A larger risk arises when a reader **repeatedly reads from `latest()`**, especially when each read does not retain the last received ID.

```text
t0   Reader calls XREAD BLOCK ... $ and waits
t1   Record D arrives; reader receives D
t2   Read finishes, Java is processing D
t3   Record E is XADDed to the stream
t4   Java finishes processing D
t5   Reader calls XREAD BLOCK ... $ again
```

At `t5`, `$` refers to the end of the stream **now containing E**, so that read can skip E and wait only for entries arriving after `t5`.

```text
                     D was received
                         |
                         v
... C ---- D ---- E ---- | XREAD from "$" at t5
                 ^
                 |
       E may not be returned to this reader
```

This is why `latest()` is unsuitable for workers that must process every entry. Spring Data Redis documentation also distinguishes reading from latest vs. reading from a specific ID: reading from a known ID avoids this gap while entries remain in the stream.

**Caveat:** the description above applies when an `XREAD` genuinely uses `$`/the current tail position. A container or driver may track or update offsets internally depending on its implementation; when designing for reliability, rely on the `ReadOffset` strategy and actual API behavior rather than assuming a container turns `latest()` into a durable checkpoint.

### 3.2. When Is `latest()` a Sensible Choice?

- A real-time dashboard only interested in new updates since opening.
- Telemetry or notifications where dropping a few events is acceptable because current state can be fetched from another source.
- Listeners with no obligation to process backlog.
- Applications intentionally accepting missed messages during unsubscribed or paused windows.

Do not use `latest()` for:

- Business ledgers requiring every event.
- Tasks needing catch-up after downtime.
- Multi-step data synchronization where missing one event corrupts state.
- Billing, order-placement, or inventory-deduction flows where omissions are unacceptable.

If you only need the latest state rather than processing every event, it is sometimes better to **read current state from the data source** instead of relying on a stream consumer configured for future-only delivery.

## 4. `ReadOffset.from(id)`: Continuing After an Explicit Position

`ReadOffset.from(id)` uses a specific ID as the checkpoint. For example:

```java
StreamOffset<String> offset = StreamOffset.create(
    "orders:events",
    ReadOffset.from("1731000000100-0")
);
```

Assuming that ID belongs to event B and the stream also holds C, an `XREAD` call can return C and newer entries.

Model:

```text
A ---- B ---- C ---- D ---- E
       ^
       |
    checkpoint=B
                 |
                 +--> reads C, D, E
```

The advantage is **not jumping back to the end of the stream after each poll**. If E arrives while the application is processing D, the next read from D still fetches E as long as E remains retained.

However, `ReadOffset.from(id)` **does not know on its own which records finished processing successfully**. The application must decide what the checkpoint is and where to store it.

### 4.1. Without a Durable Checkpoint: Re-Reading from the Start on Restart

If an application always starts with:

```java
ReadOffset.from("0-0")
```

it reads from the start of whatever history remains in the stream. That is useful for a full-rescan job, yet on service restarts it can reprocess thousands of old entries.

```text
Run 1: A, B, C processed
App restarts
Run 2: reads A, B, C again from 0-0
```

If the handler merely calls `cache.evict(productId)`, repetition may be acceptable. If the handler records payments or increments business counters, repetition can corrupt data.

Therefore, a **durable** checkpoint is needed if an independent reader must resume across restarts without rescanning everything.

### 4.2. Checkpoints Should Represent Processed Progress Only

Suppose a reader processes A, B, C sequentially.

```text
Read A -> process A succeeds -> checkpoint A
Read B -> process B succeeds -> checkpoint B
Read C -> process C succeeds -> checkpoint C
```

After restart, `ReadOffset.from(C)` reads entries newer than C.

If the checkpoint is saved **immediately upon receiving the message** before processing, a crash can lose work:

```text
Receive B
Save checkpoint = B
App crashes before processing B
Restart from B -> Redis only returns entries > B
B is never processed
```

Conversely, if processing finishes before checkpointing:

```text
Receive B
Process B succeeds
App crashes before saving checkpoint = B
Restart from A -> B is read again
```

The second case introduces **duplicate processing**, which can be controlled with idempotency. This is the standard trade-off for *at-least-once processing* with a custom checkpoint, provided data remains in the stream and checkpoint storage is genuinely durable.

## 5. Two Failure Windows: Checkpoint Before or After Processing?

This is the most critical aspect when designing a reader that manages its own offset.

| Operation order | If crash happens in between | Risk |
|---|---|---|
| **Checkpoint → process** | New position saved while side effect is unfinished | **Lost processing** |
| **Process → checkpoint** | Side effect finished while position is unsaved | **Duplicate processing** |
| Process and checkpoint in **one atomic transaction in the same data store** | Avoids half-done state within that transaction scope | Requires real transactions and shared data-store boundary |
| Process in DB, checkpoint in Redis independently | No automatic distributed commit | Failure window remains; needs idempotency/recovery |

Illustration with side effects in PostgreSQL and checkpoint in Redis:

```text
DB Transaction commits:
    UPDATE payments ...       -> succeeds

Redis checkpoint:
    SET stream:checkpoint ... -> not yet called

JVM crashes
```

After restart, the entry can reappear because the checkpoint is still old. If the DB update is not idempotent, business logic risks executing twice.

**Do not move the checkpoint earlier just to avoid duplicates on a dashboard.** If records are critical, prioritize never skipping work, and build idempotency and recoverable processing state.

## 6. Example of Reading Without a Consumer Group Using `ReadOffset.from(...)`

Spring Data Redis provides `StreamOperations` and `StreamReadOptions` for `XREAD`.

Illustrative sequential reader; `CheckpointStore` is an application-provided abstraction to **durably persist** the last successfully processed ID:

```java
package com.example.orders;

import java.util.List;

import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.connection.stream.StreamReadOptions;
import org.springframework.data.redis.core.StringRedisTemplate;

public class OrderStreamReader {

    private static final String STREAM = "orders:events";

    private final StringRedisTemplate redis;
    private final CheckpointStore checkpoints;
    private final OrderEventHandler handler;

    public OrderStreamReader(
            StringRedisTemplate redis,
            CheckpointStore checkpoints,
            OrderEventHandler handler
    ) {
        this.redis = redis;
        this.checkpoints = checkpoints;
        this.handler = handler;
    }

    public void pollOnce() {
        String lastProcessedId = checkpoints.load(STREAM)
                .orElse("0-0");

        List<MapRecord<String, Object, Object>> records =
                redis.opsForStream().read(
                    StreamReadOptions.empty().count(20),
                    StreamOffset.create(
                        STREAM,
                        ReadOffset.from(lastProcessedId)
                    )
                );

        if (records == null || records.isEmpty()) {
            return;
        }

        for (MapRecord<String, Object, Object> record : records) {
            // If processing fails, stop without advancing the checkpoint.
            handler.handle(record);

            checkpoints.save(
                STREAM,
                record.getId().getValue()
            );
        }
    }
}
```

Application interfaces:

```java
package com.example.orders;

import java.util.Optional;
import org.springframework.data.redis.connection.stream.MapRecord;

public interface CheckpointStore {
    Optional<String> load(String streamKey);
    void save(String streamKey, String lastProcessedId);
}

public interface OrderEventHandler {
    void handle(MapRecord<String, Object, Object> record);
}
```

Key contracts:

1. `load` returns a **durably persisted** checkpoint, not merely a static variable in the JVM.
2. `save` is called **only after the handler confirms processing succeeded**.
3. The reader processes sequentially by ID; if the handler throws an exception at B, do not advance the checkpoint to C.
4. If `save` fails after the handler applied side effects, the next poll can re-read the entry just processed.
5. Handlers need idempotency if side effects must not repeat.
6. With multiple instances reading independently from a shared checkpoint, a coordination/ownership mechanism is required; otherwise they may process the same entries and overwrite each other's checkpoints.

This is a **single sequential reader** pattern. It does not substitute for a consumer group when dividing work across multiple workers.

### 6.1. Do Not Update the Checkpoint to the Last Record of a Batch Before Processing

A dangerous bug:

```java
List<MapRecord<String, Object, Object>> batch = readBatch();

String lastId = batch.get(batch.size() - 1).getId().getValue();

// WRONG if the batch still has unprocessed entries:
checkpointStore.save(STREAM, lastId);

for (var record : batch) {
    handler.handle(record);
}
```

If the app crashes mid-loop, unprocessed entries before `lastId` are skipped on restart.

The simplest approach is checkpointing after each successful entry. If performance requires batch checkpointing, verify **the entire batch succeeded** and accept that crashing before saving the batch checkpoint can reprocess some entries.

### 6.2. Parallel Processing Complicates Checkpointing

If a reader hands A, B, C to three threads:

```text
A: takes 500 ms
B: takes  50 ms -> finishes first
C: takes  80 ms -> finishes before A
```

Do not save checkpoint C just because C finished: A is still in progress, and restarting from C will skip A.

Under parallel processing, a safe checkpoint must represent the **contiguous completed boundary** or persist per-ID completion state. If that complexity is unnecessary, use a sequential reader or key-partitioned processing with independent progress.

## 7. How Does a Consumer Group Differ from a Self-Checkpointing Reader?

A Redis Streams consumer group is created with `XGROUP` and uses `XREADGROUP` to distribute entries across consumers in the same group.

Create a group reading available backlog too:

```redis
XGROUP CREATE orders:events order-workers 0-0 MKSTREAM
```

Components:

- `orders:events`: stream name.
- `order-workers`: consumer group name.
- `0-0`: the group starts before regular entries, enabling backlog reads.
- `MKSTREAM`: creates the stream if it does not exist.

Then:

```redis
XREADGROUP GROUP order-workers worker-a COUNT 10 STREAMS orders:events >
```

`>` requests entries **never yet delivered** in the group. Redis stores the group's delivery progress and creates *pending* state for delivered-but-unacknowledged entries.

**Consumer groups separate two vital states:**

1. **Delivered to a consumer** (*delivered*).
2. **Confirmed processed** (*acknowledged*) via `XACK`.

This distinction does not exist in standalone `XREAD` carrying only an offset ID.

### 7.1. `ReadOffset.lastConsumed()` in Spring Data Redis

When registering a group consumer with Spring Data Redis APIs, the common pattern is:

```java
Consumer.from("order-workers", "worker-a"),

StreamOffset.create(
    "orders:events",
    ReadOffset.lastConsumed()
)
```

This read direction corresponds to requesting **new entries** for the group, typically executed by Redis as `XREADGROUP ... >`.

Understand that the name `lastConsumed()` does not mean:

- “The last entry finished its application side effect”.
- “The last entry was `XACK`ed”.
- “Automatically re-fetch every pending entry from the previous run”.
- “Automatically replay trimmed entries”.
- “Automatically guarantee exactly-once”.

With a group, to know which entries were delivered yet not ACKed, inspect the **Pending Entries List (PEL)** and run a proper reprocessing flow.

## 8. `XGROUP CREATE ... $` Can Skip Backlog Even When Using `lastConsumed()`

An easily misunderstood scenario:

The stream already holds A, B, C:

```text
orders:events:
    A -> B -> C
```

The group is created at the tail:

```redis
XGROUP CREATE orders:events order-workers $ MKSTREAM
```

The group sets its starting position **after existing data**. Consumer:

```redis
XREADGROUP GROUP order-workers worker-a STREAMS orders:events >
```

only receives new entries added after the group's starting marker, not A, B, C.

```text
A ---- B ---- C | group created at "$" ---- D ---- E
                ^
                |
       Group starts after C
                                   |
                                   +-- receives D, E
```

**This is a decision made at group creation time**, not just a Java reader choice.

Comparison:

| Group creation approach | Common consequence |
|---|---|
| `XGROUP CREATE stream group 0-0` | Can receive retained backlog from the start via `>` |
| `XGROUP CREATE stream group $` | Skips existing backlog; receives new entries |
| Group already exists | Initial creation arguments are not reapplied when services restart; Redis keeps existing group state |
| `XGROUP SETID` changes group position | Alters which new entries are delivered; use very carefully with full awareness of PEL |

If the requirement is processing every entry written before service deployment, creating the group at `0-0` (or an explicit business marker) is standard. If you only want future events, `$` can be intentional.

Do not assume `ReadOffset.lastConsumed()` overrides a group that was originally created with `$`.

## 9. Pending Entries List: Delivered but Unacknowledged Records

Suppose consumer A reads an entry:

```redis
XREADGROUP GROUP order-workers worker-a COUNT 1 STREAMS orders:events >
```

Redis marks that entry **pending** for that group/consumer until acknowledged:

```redis
XACK orders:events order-workers <entry-id>
```

If the consumer crashes **after receiving and before `XACK`**, the entry does not turn back into a never-delivered entry. It stays in the PEL.

```text
              Redis Stream             Consumer Group
                 entry B
                    |
                    v
                 Delivered -------------> PEL: B (worker-a)
                    |
                    v
               Worker crashes
                    |
                    X (no XACK)
                    |
                    v
              B stays pending
```

Another consumer B calling:

```redis
XREADGROUP GROUP order-workers worker-b STREAMS orders:events >
```

primarily receives **new undelivered entries**, not automatically picking up A's pending entry B.

### 9.1. Inspecting Pending Entries

Redis CLI:

```redis
XPENDING orders:events order-workers
```

This shows summary info: pending count, ID range, and relevant consumers.

More detailed inspection:

```redis
XPENDING orders:events order-workers - + 10
```

Output can include:

- Pending entry ID.
- Owning consumer name.
- Idle time since last delivery.
- Delivery count tracked by Redis.

These metrics help detect stopped consumers or slow messages. Still, “long pending” does not always mean the consumer died: a valid job might still be running. Tune timeouts to match business logic.

### 9.2. Re-Reading a Consumer's Own Pending Entries

With `XREADGROUP`, passing a specific ID other than `>` (e.g., `0`) accesses the pending history **of that named consumer itself**, not the list of all unread entries across the whole group.

Example:

```redis
XREADGROUP GROUP order-workers worker-a COUNT 10 STREAMS orders:events 0
```

This lets consumer A inspect pending entries associated with that exact consumer name.

Common pitfall: `0` in `XREADGROUP` with a consumer group **does not mean the exact same thing** as `0-0` in regular `XREAD`. With `XREADGROUP`, it reads that consumer's pending history.

### 9.3. Transferring Pending Entries from an Old Consumer to a New One

If worker A lost connection and does not return, worker B can use `XCLAIM` or `XAUTOCLAIM` to take ownership of pending entries meeting an idle threshold.

Illustrative example:

```redis
XAUTOCLAIM orders:events order-workers worker-b 60000 0-0 COUNT 20
```

Meaning:

- `order-workers`: group.
- `worker-b`: consumer claiming entries.
- `60000`: requires at least 60,000 ms idle time.
- `0-0`: starting point to scan pending entries.
- `COUNT 20`: cap on scanned/claimed items per command semantics.

`XAUTOCLAIM` returns a cursor to keep scanning; one call does not necessarily scan the entire PEL. Process returned results and continue if pending entries remain, within batch limits and monitoring.

Once business processing succeeds, the new worker calls `XACK`.

**Idempotency is required:** consumer A might still be running or may have finished side effects right before dying prior to ACK; worker B claims and reprocesses. Never infer from “claimed” that side effects never happened before.

## 10. Crashing Before vs. After `XACK` Determines Loss vs. Duplication

For consumer groups, the boundary mirrors checkpointing but involves ACKs and the PEL.

| Sequence | If crash happens in between | Consequence |
|---|---|---|
| **ACK → process** | Pending state cleared before side effects finish | Can **lose processing** |
| **Process → ACK** | Side effects finished while pending entry is unACKed | Can **duplicate processing** on reclaim |
| Process → ACK, no reclaim mechanism | Pending entry stays stuck indefinitely | No duplicates, yet recovery never completes |
| Idempotent process → ACK + sensible reclaim | May reprocess without repeating business side effects | Practical *at-least-once* path |
| Process in DB and ACK in Redis | Two operations across two different resources | No automatic distributed exactly-once |

Example:

```text
Worker A:
    XREADGROUP -> receives event B
    UPDATE database -> commits
    JVM crashes before XACK

Worker B:
    XAUTOCLAIM -> receives event B again
    UPDATE database a second time?
```

If `UPDATE` is “add 100 to balance”, running twice gives the wrong result. If the DB transaction checks that `eventId` is unprocessed and writes both the side effect and processed marker **in the same transaction**, worker B recognizes event B as a duplicate and ACKs safely.

This illustrates the rule: **the system can deliver/read repeatedly, so business side effects must be idempotent**.

## 11. Do Not ACK Before Processing Finishes

With Spring Data Redis, a group listener typically receives a message, runs the handler, and ACKs after success:

```text
receive message
    |
    v
validate and deserialize
    |
    v
businessHandler.handle(message)
    |
    +-- error ----------> no ACK -> pending/retry/reclaim per policy
    |
    +-- success --------> XACK
```

Some APIs/containers offer an **auto-ack** mode. Understand that mode's exact ACK timing: if the system requires recovery after handler failures, do not choose auto-ack without verifying what it guarantees.

If you ACK immediately upon receiving a message or before business commits, a subsequent exception leaves the message out of pending so it cannot be retried via PEL. For tasks requiring guaranteed completion, generally use **manual ACK after handler success**.

Do not treat `XACK` as a rollback or stream-record deletion call. `XACK` only marks the entry no longer pending in the group; the entry can remain in the stream until removed by `XDEL`, trimming, or another storage policy.

## 12. Group Listener Example with `ReadOffset.lastConsumed()`

Spring Data Redis provides `StreamMessageListenerContainer` to poll streams and dispatch messages to a `StreamListener`.

Example illustrating a consumer group processing messages and ACKing manually:

```java
package com.example.orders;

import java.time.Duration;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.stream.StreamMessageListenerContainer;
import org.springframework.data.redis.stream.StreamMessageListenerContainer
        .StreamMessageListenerContainerOptions;

@Configuration(proxyBeanMethods = false)
public class OrderStreamListenerConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(
                OrderStreamListenerConfiguration.class
            );

    @Bean
    public StreamMessageListenerContainer<
        String, MapRecord<String, String, String>
    > orderStreamContainer(
        RedisConnectionFactory connectionFactory,
        StringRedisTemplate redis,
        OrderRecordHandler handler
    ) {
        StreamMessageListenerContainerOptions<
            String, MapRecord<String, String, String>
        > options = StreamMessageListenerContainerOptions
                .<String, MapRecord<String, String, String>>builder()
                .pollTimeout(Duration.ofSeconds(2))
                .build();

        var container = StreamMessageListenerContainer.create(
            connectionFactory, options
        );

        container.receive(
            Consumer.from("order-workers", "worker-a"),
            StreamOffset.create(
                "orders:events",
                ReadOffset.lastConsumed()
            ),
            message -> {
                try {
                    handler.handle(message);

                    redis.opsForStream().acknowledge(
                        "orders:events",
                        "order-workers",
                        message.getId()
                    );
                } catch (Exception ex) {
                    log.error(
                        "Stream processing failed; record remains pending: {}",
                        message.getId(),
                        ex
                    );
                    // Do not ACK: reprocess via pending/reclaim policy.
                }
            }
        );

        return container;
    }
}
```

Application interface:

```java
package com.example.orders;

import org.springframework.data.redis.connection.stream.MapRecord;

public interface OrderRecordHandler {
    void handle(MapRecord<String, String, String> message);
}
```

Notes to keep in mind:

- This is an illustrative configuration example; generic/serializer declarations on `StreamMessageListenerContainerOptions` must fit your Spring Data Redis version and record format.
- Consumer group `order-workers` must **already be created** before the listener starts reading. `XGROUP CREATE` can run in a controlled initialization step; handle the “group already exists” case instead of treating it as a system error.
- Consumer name `worker-a` should be managed per deployment topology; sharing the same name across multiple instances makes recovery/ownership hard to track.
- If the handler throws an exception and code catches it, the message **stays pending**; catching errors does not create retries by itself. You need a reclaim worker/process.
- If `acknowledge(...)` fails after the handler succeeds, the entry can be reprocessed. The handler must still be idempotent.
- Spring's container has a lifecycle; let Spring manage start/stop rather than creating a container outside context and forgetting to start it.
- If using an auto-ACK consumer or a different API, verify exact callback and ACK semantics; this example intentionally ACKs after the handler.

### 12.1. Why Not Use `ReadOffset.latest()` in the Group Snippet?

Consumer groups use group delivery state and `>` to receive new entries. `ReadOffset.lastConsumed()` expresses that goal clearly. Using `latest()` as if running standalone `XREAD` can yield unintended semantics, invalid calls, or improper `XREADGROUP` behavior depending on API mapping.

When using consumer groups, clearly separate:

```text
ReadOffset.lastConsumed() -> receive new entries in the group
pending recovery           -> use pending history / claim
group creation ID          -> decides initial backlog
```

These are **three distinct mechanisms** that cannot be replaced by a single offset.

## 13. Why `lastConsumed()` Does Not Mean “Successfully Processed”?

The name `lastConsumed` might suggest Redis knows where the application finished processing. In a consumer group, Redis primarily knows:

- Which entries the group delivered.
- Which consumers own pending entries.
- Which entries were `XACK`ed.
- `last-delivered-id` used to select new entries.

Redis **cannot know on its own** whether a PostgreSQL transaction, HTTP call, email, or external service mutation completed business work properly.

Example:

```text
XREADGROUP -> delivers B to worker-a
worker-a starts processing B
DB commits
worker-a crashes before XACK
```

The group knows B is still pending. It does not know the DB committed. During recovery, B can run again. That is why idempotency must live where side effects are persisted.

On the other hand, if the application ACKs B before DB commit and the DB transaction rolls back, Redis already marks B non-pending even though business processing failed.

**ACK is the consumer's confirmation to the stream group**, not an automatic certificate of success across all related systems.

## 14. Groups with Multiple Workers: Ordering and Duplicate Processing

Suppose entries A, B, C are delivered by the group to two workers:

```text
Stream: A -> B -> C

worker-a receives A
worker-b receives B
worker-a receives C
```

This can happen:

```text
worker-a processes A in 500 ms
worker-b processes B in  50 ms
worker-a processes C in  70 ms

B finishes before A
```

Redis Streams has ID order, yet **side-effect completion order across multiple consumers is not guaranteed by `ReadOffset` alone**.

If business logic requires ordered updates for the same `orderId`:

- Attach a version/sequence to events and check before applying.
- Partition processing so events for the same aggregate have clear ownership.
- Use conditional updates / optimistic locking at the database.
- Or choose a single sequential consumer when throughput and SLA permit.

Do not rely on `ReadOffset.from(...)` or `lastConsumed()` to replace an ordering mechanism across multiple workers.

With consumer groups, work distribution also depends on group membership, pending state, and claiming; restarts/timeouts can cause an entry to be reprocessed by a different consumer.

## 15. Retention, `XTRIM`, and `XDEL`: Even the Right Offset Cannot Read Missing Data

`ReadOffset.from(lastId)` only tells Redis which position to read from. It **does not guarantee entries after that position are still stored**.

Suppose the stream has A, B, C, D, E:

```text
A ---- B ---- C ---- D ---- E
       ^
       |
    checkpoint=B
```

If the stream is trimmed to keep only D and E:

```text
D ---- E
```

A reader starting from B can only read remaining entries, namely D and E. C was removed from the stream, so it cannot be recovered merely by adjusting `ReadOffset`.

Related mechanisms:

- `XTRIM`: trims entries by ID or count limit.
- `XADD ... MAXLEN` / `MINID`: combines appending an entry with retention bounds.
- `XDEL`: deletes specific entries.
- Persistence settings, Redis failures, or admin actions also affect recoverability.
- A pending entry in the PEL can lose its payload if the entry was deleted/trimmed; the PEL and stream data do not automatically stay in sync forever.

Therefore, define a **minimum retention window** exceeding expected downtime/retry lag, and monitor consumer lag and pending entries.

### 15.1. What Conditions Does “At-Least-Once” Depend On?

A pipeline using post-processing checkpoints or consumer group + ACK/reclaim can target *at-least-once processing*, but only when:

1. Entries are written and stay in the stream long enough.
2. Readers never advance checkpoints past unfinished entries.
3. Pending entries are detected and reprocessed.
4. No unrecoverable error destroys source data.
5. Handlers tolerate duplicates.
6. Redis durability/failover requirements are satisfied in the actual deployment.

Absolute at-least-once cannot be promised by a single line of `ReadOffset.lastConsumed()`.

## 16. Adding `BLOCK` and `COUNT` Does Not Change Offset Meaning

When reading streams, Spring Data Redis can use `StreamReadOptions`:

```java
StreamReadOptions.empty()
    .count(20)
    .block(Duration.ofSeconds(2))
```

- `COUNT 20`: hint/cap on entries read in one turn per Redis command.
- `BLOCK 2000`: waits up to roughly 2 seconds if no matching entries are present yet.
- `ReadOffset`: marker selecting which entries are eligible to return.

Changing `COUNT` or `BLOCK` does not fix misusing `$`:

```text
XREAD BLOCK 2000 STREAMS orders:events $
```

still starts at the end of the stream on that read call. If a record arrives right before the command and the reader uses `$` again, it can be skipped regardless of how long `BLOCK` is set.

Similarly, passing `COUNT 100` does not make the handler auto-ACK 100 entries after business success. Offset, batching, ACK, and concurrency are independent decisions.

### 16.1. On Poll Timeout, How Do You Avoid Skipping Entries?

For non-group readers, keep `lastProcessedId`:

```text
Poll from ID=B
No data -> timeout
Poll again from ID=B
Got C -> process C -> checkpoint C
Poll from ID=C
```

Do not reuse `latest()` on every poll if the goal is capturing every entry.

With consumer groups, each read for new entries uses `lastConsumed()`/`>` per group semantics. Simultaneously run a separate process to detect **pending** entries needing recovery.

## 17. Illustrative Scenario in Redis CLI

This section helps directly observe the difference between plain stream reads and consumer groups. Use a test Redis instance—never run on production streams.

### 17.1. Create a Sample Stream

```redis
XADD lab:orders * type CREATED orderId 101
XADD lab:orders * type PAID orderId 101
XADD lab:orders * type SHIPPED orderId 101
XRANGE lab:orders - +
```

Record the IDs Redis returns for each `XADD`. In the following examples, replace `<id-a>`, `<id-b>` with actual IDs.

### 17.2. `XREAD` from the Beginning

```redis
XREAD COUNT 10 STREAMS lab:orders 0-0
```

Existing entries are returned in ascending ID order.

### 17.3. `XREAD` After a Processed ID

```redis
XREAD COUNT 10 STREAMS lab:orders <id-b>
```

If `<id-b>` is the ID of the `PAID` entry, the result contains entries with larger IDs, such as `SHIPPED`.

### 17.4. `XREAD` from the Tail

In terminal A:

```redis
XREAD BLOCK 10000 STREAMS lab:orders $
```

In terminal B, add an event while terminal A is waiting:

```redis
XADD lab:orders * type CANCELLED orderId 101
```

Terminal A receives `CANCELLED`. However, if `CANCELLED` had been added **before** terminal A called `XREAD ... $`, it would be treated as history and not returned on that read.

### 17.5. Create a Group from the Start and Read New Group Entries

Use a fresh stream/group to avoid stale state in testing:

```redis
XGROUP CREATE lab:orders lab-workers 0-0
XREADGROUP GROUP lab-workers worker-1 COUNT 2 STREAMS lab:orders >
XPENDING lab:orders lab-workers
```

The first two entries become pending until ACKed.

ACK one entry:

```redis
XACK lab:orders lab-workers <id-a>
```

Check again:

```redis
XPENDING lab:orders lab-workers
```

The ACKed entry is gone from the PEL, yet still appears in `XRANGE` because `XACK` does not delete it from the stream.

### 17.6. Read a Consumer's Own Pending Entries and Claim

```redis
XREADGROUP GROUP lab-workers worker-1 COUNT 10 STREAMS lab:orders 0
```

This uses a numeric offset to read `worker-1`'s pending history.

When another consumer needs to claim entries unACKed for long enough:

```redis
XAUTOCLAIM lab:orders lab-workers worker-2 60000 0-0 COUNT 10
```

Only entries meeting the idle condition are claimed by that command. Claiming should be paired with reprocessing and post-success ACK; it is not “clear all pending”.

### 17.7. Comparing a Group Created at `$`

Create another stream:

```redis
XADD lab:new-orders * event first
XADD lab:new-orders * event second
XGROUP CREATE lab:new-orders newest-only $ 
XREADGROUP GROUP newest-only worker-1 STREAMS lab:new-orders >
```

The first read does not return the two older entries. Add:

```redis
XADD lab:new-orders * event third
XREADGROUP GROUP newest-only worker-1 STREAMS lab:new-orders >
```

The group receives the new `third` entry, illustrating the effect of the offset chosen **when creating the group**.

## 18. Decision Table When Choosing `ReadOffset`

| Requirement | Starting choice | Must also add |
|---|---|---|
| Receive only new notifications from listen start | `ReadOffset.latest()` with `XREAD` | Accept missing backlog / gaps between polls |
| Read all retained entries for a one-off scan | `ReadOffset.from("0-0")` | Verify whether replay is safe |
| Dedicated reader resuming across restarts | `ReadOffset.from(checkpoint)` | Durable post-processing checkpoint, idempotency |
| Multiple workers dividing work by group | `ReadOffset.lastConsumed()` | Group created at right marker, manual ACK, pending recovery |
| Consumer crashed, need unACKed entries | Pending history or `XAUTOCLAIM`/`XCLAIM` | Idempotent reprocessing, ACK, idle threshold |
| Need to replay all events from a historical point | Dedicated reader or new group at matching ID | Sufficient stream retention; avoid casually mutating prod groups |
| Must never drop any important event | Offset alone is insufficient | Durable source, retry/reclaim, retention, monitoring, idempotency |
| Need exactly-once DB side effects | No `ReadOffset` satisfies this alone | DB transactions/idempotency keys or proper coordination |

A memorable design rule:

> **Offset decides which records can be delivered; checkpoint/ACK decides how progress is marked; idempotency decides whether duplicate processing is safe.**

## 19. Common Misconceptions

**“`latest()` guarantees receiving all new records, even across gaps between polls.”** False whenever each read grabs a fresh `$`. Entries arriving before the next read can be skipped.

**“`from(id)` re-reads the entry with that exact ID.”** With `XREAD`, returned entries have IDs greater than the given marker; set the checkpoint to the last **processed** ID, not the first **to-process** ID.

**“Reading from `0-0` is always safe for a multi-year service.”** Not automatically. Restarts can re-read massive old event backlogs; if the stream was trimmed, removed events cannot be re-read.

**“`lastConsumed()` means last ACKed.”** Do not equate them. Groups track delivery and ACKs separately; delivered-but-unACKed entries sit in the PEL.

**“A new consumer using `lastConsumed()` will automatically handle a dead consumer's pending entries.”** False. `>` normally fetches new entries; another consumer's pending entries must be reclaimed.

**“Creating a group with `$` and using `lastConsumed()` will read backlog.”** False. The group initialized at the end of the existing stream.

**“ACKing immediately upon receiving a message prevents duplicate processing.”** It can lose processing if side effects have not completed. Prevent duplicates with idempotency, not by sacrificing recoverability.

**“ACKing after processing guarantees exactly-once.”** No. Crashing between side effects and ACK causes the record to be reprocessed upon reclaim.

**“A consumer group always preserves side-effect completion order.”** No. Multiple workers, threads, and retries can finish events out of ID order.

**“Redis keeps pending entries, so payloads cannot be lost.”** No. Trimming or deleting entries removes payloads; pending metadata does not replace stream retention.

**“A large `COUNT` or long `BLOCK` fixes offset mistakes.”** No. Those options control batching and waiting, not the meaning of `$`, explicit IDs, or `>`.

**“Storing the checkpoint in a static variable is enough.”** Not durable across restarts and unsafe across multiple instances.

**“Under parallel processing, finishing record C means checkpointing C is safe.”** Not if A or B is still unfinished. A single checkpoint must represent a contiguous processed boundary.

## 20. Operational Design to Detect Missing or Duplicate Records

An application can run for weeks without throwing exceptions while silently skipping events or duplicating work on restarts. Multi-layer monitoring is therefore necessary.

### 20.1. For Non-Group Readers

- Last processed checkpoint ID and update timestamp.
- First/last IDs remaining in the stream (`XINFO STREAM` or bounded `XRANGE`).
- Difference between event time and processing time.
- Successful/failed entry counts by type.
- Duplicate count caught by `eventId`.
- Restart resume counts.
- Suspicious gaps from checkpoint jumps or stream retention.

If the checkpoint is older than the earliest retained stream entry, record that **full replay is impossible** rather than silently jumping to newer entries and reporting everything processed cleanly.

### 20.2. For Consumer Groups

Useful Redis CLI commands:

```redis
XINFO STREAM orders:events
XINFO GROUPS orders:events
XINFO CONSUMERS orders:events order-workers
XPENDING orders:events order-workers
```

Metrics to watch:

| Metric | Meaning |
|---|---|
| Stream length | Entries still retained; not all-time total events |
| Group `last-delivered-id` | Position of new entries delivered per group |
| Group lag (if provided by Redis and meaningful) | Entries behind the delivery cursor, not failed pending entries |
| Pending count | Delivered entries not yet ACKed |
| Pending idle | Identifies entries at risk of abandonment |
| Delivery count | Sign of redelivery, interpreted per Redis mechanics |
| Handler success/error | Separates message receipt from processing success |
| Claim/retry count | Spots failing consumers and duplication pressure |
| Oldest retained ID | Evaluates risk of trimming ahead of processing progress |

**`Group lag = 0` does not mean every event succeeded.** The group may have delivered all new entries while holding huge unACKed pending backlogs.

Similarly, a small pending count does not prove zero data loss if ACKs happened too early or the group started at `$` when backlog already existed.

### 20.3. Do Not Infer Lost Records Solely from Non-Contiguous IDs

Stream IDs are not arithmetically contiguous. Two consecutive IDs do not have to differ by `1`, because IDs reflect timestamps and sequences.

To detect lost business events, rely on event IDs/sequences managed by the **business source** or reconcile against a reliable outbox/event log. A large numeric jump between Redis Stream IDs does not prove missing events.

## 21. Recommended Architecture for Reliable Flows

Suppose an order system requires every event to be processed, retried after crashes, and never duplicate side effects:

```text
Producer
   |
   v
XADD orders:events
   |
   v
Consumer group "order-workers"
   |
   +-- XREADGROUP ... > / ReadOffset.lastConsumed()
   |         |
   |         v
   |    handler with eventId idempotency
   |         |
   |         v
   |    commit side effect
   |         |
   |         v
   |        XACK
   |
   +-- Recovery job
          |
          +-- XPENDING / XAUTOCLAIM
          |
          +-- idempotent reprocessing
          |
          +-- XACK after success
```

In addition to these components, you need:

1. Create the group at the right marker (`0-0` if backlog is needed; `$` if intentionally starting from future data).
2. Keep retention long enough to outlast downtime/retry lag.
3. Use intentional consumer identities and monitor pending ownership.
4. Never use auto-ack before side effects complete when recovery is required.
5. Define a poison-message policy: bounded retries, error persistence, and dead-lettering by design.
6. Place idempotency in the same transaction as critical side effects whenever possible.
7. With multiple workers, manage per-aggregate ordering/versioning.
8. Only report “processed” when business criteria are met, not merely because `XREADGROUP` returned a message.

In critical systems, also evaluate Redis persistence/replication and the write gap between the source DB and the Redis Stream. If the DB commits while `XADD` never runs, no consumer `ReadOffset` can recreate an event that was never written; consider a transactional outbox on the producer.

## 22. Diagnostic Checklist for Missing or Duplicate Events

**If events are missing:**

1. Is the reader passing `ReadOffset.latest()`/`$` on every poll?
2. Was the group created at `$` when the stream already had backlog?
3. Was the checkpoint saved before the handler succeeded?
4. Did ACK happen before the business commit?
5. Was the stream trimmed/`XDEL`ed before reading or reclaiming?
6. Are unACKed pending entries neglected because new consumers only read `>`?
7. Did deserialization/handler errors occur while the system still reported success?
8. Is there a gap between the event-emitting source and `XADD`?

**If events are duplicated:**

1. Is the reader restarting from `0-0` every time?
2. Is the checkpoint durably persisted after processing?
3. Did a crash happen between processing and checkpointing/ACKing?
4. Is `XAUTOCLAIM` firing while the original worker is still running slowly?
5. Is the producer retrying `XADD` for the same business event with a new stream ID?
6. Are multiple independent readers reading the full stream?
7. Does the handler lack idempotency on `eventId`?
8. Is parallel processing advancing a single checkpoint past unfinished entries?

No single offset configuration fixes all these issues. Define **where data is considered delivered, where work is considered done, and how recovery behaves when a process stops in between**.

## 23. Conclusion

`ReadOffset` is a decisive factor in the reliability of Redis Streams in Spring Data Redis:

- **`ReadOffset.latest()`** suits readers caring only about new records, yet can skip backlog and records arriving between polls if reading from the tail repeatedly.
- **`ReadOffset.from(id)`** resumes reading from an explicit ID; for standalone readers, pair it with durable checkpoints updated only after processing succeeds, accepting possible replays to avoid losing work.
- **`ReadOffset.lastConsumed()`** is used for consumer groups receiving new entries. It must go hand in hand with the **group creation ID**, `XACK`, PEL monitoring, and pending claim/retry mechanics; on its own, it does not recover delivered-but-unACKed entries.

Across every model, **offsets do not replace idempotency, retention, or business transactions**. To minimize data loss, never advance progress before processing succeeds and ensure replayability. To handle duplicates safely, use event IDs with idempotent updates. To preserve ordering, control concurrency and versions instead of relying solely on stream ID order.

Once you clearly understand the boundaries between **read**, **delivered**, **processed**, **ACKed**, and **retained in the stream**, your application can choose the right `ReadOffset` for its requirements and build a fault-recoverable consumption pipeline without false delivery assumptions.
