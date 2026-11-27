# Consumer Groups, Consumers, and Group Read Positions in Redis Streams with Spring Data Redis

## 1. Why Do Redis Streams Need Consumer Groups?

Redis Streams stores *entries* with ordered IDs in a stream. Publishers write using `XADD`, and consumers can read using `XREAD`. When multiple instances handle the same kind of work, having every instance independently read the entire stream can cause a single event to be executed multiple times. **Consumer groups** solve the problem of distributing new records across multiple consumers in the same group while tracking records that have been delivered but not yet acknowledged as complete.

Example:

```text
Stream: orders:events
    ID 100-0    OrderCreated(42)
    ID 101-0    OrderCreated(43)
    ID 102-0    OrderCreated(44)

Group: order-workers
    consumer worker-A    receives ID 100-0, 102-0
    consumer worker-B    receives ID 101-0

Another group: audit-workers
    consumer audit-A     can also receive all three IDs
```

Consumers **within the same group** coordinate so each new record is typically delivered to one consumer in the group. **Two different groups** maintain independent read positions and can therefore both receive the same record. A consumer group is a distribution and pending-tracking mechanism; it does not automatically guarantee *exactly-once* business processing.

In Spring Data Redis, the related APIs include `StreamOperations`, `Consumer.from(...)`, `StreamOffset`, `ReadOffset`, and `StreamMessageListenerContainer`.

## 2. How Do Streams, Consumer Groups, and Consumers Differ?

| Component | Scope | Responsibility |
| --- | --- | --- |
| **Stream** | One Redis key, e.g., `orders:events` | Stores records and each record's field/value pairs. |
| **Consumer group** | A named group attached to a stream | Tracks the delivery position for new messages and the group's pending list. |
| **Consumer** | An identity belonging to a group, e.g., `worker-A` | Receives distributed messages and owns pending records until ACK/claim. |
| **Pending Entries List (PEL)** | Management structure of a group, with per-consumer info | Tracks records delivered but not yet acknowledged via `XACK`. |

One stream can have many groups. One group can have many consumers. A consumer name does not have to be a thread or TCP connection name—it is a **logical identity** recorded in Redis metadata.

Three questions must be distinguished:

1. **Is the record still in the stream?** Use `XRANGE` or `XREVRANGE`.
2. **How far has the group delivered new records?** Use `XINFO GROUPS` to inspect `last-delivered-id`.
3. **Has the record been processed and ACKed?** Use `XPENDING` and business state outside Redis.

A group may have already delivered the latest record in the stream while thousands of older records remain pending. **The latest delivery position differs from the successfully processed position.**

## 3. Stream IDs and Special Symbols

Common record IDs have the form:

```text
<millisecondsTime>-<sequenceNumber>
1700000000000-0
1700000000000-1
1700000000001-0
```

When calling `XADD orders:events * ...`, Redis picks the ID automatically. The `*` on write does not carry the meaning of reading new messages in a consumer group.

| Symbol | Context | Meaning |
| --- | --- | --- |
| `0-0` | `XGROUP CREATE` / `XGROUP SETID` | Lowest marker: the new group can receive records already in the stream. |
| `$` | `XGROUP CREATE` | Last stream ID at group creation time: skips backlog before the group was created. |
| `>` | `XREADGROUP` | Requests records **not yet delivered to any consumer in the group**. |
| `0` or `0-0` | `XREADGROUP` | Iterates pending entries of **the calling consumer itself**, not the entire stream. |
| Specific ID | `XREADGROUP` | Iterates pending IDs greater than that marker for the calling consumer itself. |

The two most frequently confused symbols are `$` and `>`: `$` is the tail marker of the stream when initializing a group position; `>` asks Redis to deliver new records based on the group's current position.

## 4. Creating a Group Starting from History or from Now

Suppose several records already exist:

```redis
XADD orders:events * type created orderId 42
XADD orders:events * type created orderId 43
XADD orders:events * type created orderId 44
```

### 4.1. Creating a Group from `0-0`

```redis
XGROUP CREATE orders:events order-workers 0-0
```

The new group starts at the lowest ID. Consumers reading with `>` can receive old records still stored in the stream, and then receive records written afterwards. This is the choice when the group needs to process all retained backlog.

“History” does not mean data deleted by `XDEL` or `XTRIM` will be replayed; Redis does not restore deleted records merely by creating a group at `0-0`.

### 4.2. Creating a Group from `$`

```redis
XGROUP CREATE orders:events order-workers $
```

The starting position equals the last ID of the stream at group creation time. Pre-existing records are not delivered through the `>` new-message read path. This suits cases where you only want events produced **after the group is enabled**.

Mistakenly choosing `$` when backlog processing is needed will skip old records according to the group read position. They may still exist in the stream, yet will not appear on subsequent `XREADGROUP ... >` calls.

### 4.3. When the Stream Does Not Yet Exist

```redis
XGROUP CREATE orders:events order-workers 0-0 MKSTREAM
```

`MKSTREAM` creates an empty stream before creating the group. This is useful during bootstrap. If the group already exists, `XGROUP CREATE` reports `BUSYGROUP`. Handle an already-created group intentionally instead of blindly resetting the group's position on every deploy.

## 5. Consumers Reading New Records with `XREADGROUP ... >`

Consumer A example:

```redis
XREADGROUP GROUP order-workers worker-A COUNT 2 BLOCK 2000 STREAMS orders:events >
```

| Part | Meaning |
| --- | --- |
| `GROUP order-workers worker-A` | Group name and consumer name; Redis can create this consumer on its first read. |
| `COUNT 2` | Requests at most two records in a single read. |
| `BLOCK 2000` | Waits up to 2,000 ms if no new record is currently available. |
| `STREAMS orders:events >` | Reads records never before delivered in the group. |

Consumer B:

```redis
XREADGROUP GROUP order-workers worker-B COUNT 2 BLOCK 2000 STREAMS orders:events >
```

Each record is delivered by Redis to one consumer calling `XREADGROUP` in the group and is normally placed into the PEL. **Redis does not enforce strict round-robin load balancing**: a consumer that polls more often, runs faster, or uses a larger batch size can receive more records.

If `worker-A` received a record, did not `XACK` it, and suddenly stopped running, `worker-B` reading only `>` **will not automatically pick up** A's pending record. To recover that record, you must read pending entries for that consumer or use a claim mechanism.

### Multiple Groups Still Receive the Same Records

Alongside `order-workers`, an `audit-workers` group can have:

```redis
XGROUP CREATE orders:events audit-workers 0-0
XREADGROUP GROUP audit-workers audit-A STREAMS orders:events >
```

The audit group has an independent progress cursor and PEL from `order-workers`. Processing and ACKing in `audit-workers` does not acknowledge on behalf of `order-workers`.

## 6. Group Read Position: `last-delivered-id`

Redis tracks the last ID marked as delivered by the group on the new-message path via the `last-delivered-id` metadata. You can inspect it with:

```redis
XINFO GROUPS orders:events
```

Abbreviated sample output:

```text
name              order-workers
consumers         2
pending           3
last-delivered-id 1700000000002-0
entries-read      ...
lag               ...
```

This shows the group has delivered new records up to ID `1700000000002-0`, **yet three records remain pending**. Therefore `last-delivered-id` is not equivalent to “last successfully processed ID” or “last ACKed ID”.

Some Redis versions include `entries-read` and `lag` fields to help monitor backlog. `lag` can be undefined in certain cases such as special position changes or missing ID-sequence metadata; do not treat an undefined value as 0.

### Are the Group Cursor and Consumer Cursor the Same?

No. Consumers in the same group coordinate around the **group's new-message delivery position**. Each consumer owns a set of pending entries, rather than having an independent new-message cursor like two `XREAD` clients on the same stream.

When the group delivers newer IDs, older pending entries can still remain. Advancing the group cursor **does not auto-ACK**, nor does it clear previously delivered pending entries.

## 7. What Does the Pending Entries List (PEL) Store?

When `XREADGROUP` delivers a record, Redis normally adds metadata to the PEL:

```text
ID 1700000000000-0
    owner: worker-A
    idle time: time since the relevant delivery/claim
    delivery count: number of deliveries per Redis metadata
```

The PEL indicates “delivered but not yet ACKed”; it does not establish whether the application is currently executing it, succeeded, or failed.

Usage:

```redis
XPENDING orders:events order-workers
XPENDING orders:events order-workers - + 10
```

The first command returns summary info such as total pending count, smallest/largest ID, and per-consumer distribution. The second returns details for a number of IDs, owning consumer, idle time, and delivery count.

A long-pending entry can result from a crashed process, logic bugs, slow external dependencies, or an unusually hard-to-process record. Combine this with application metrics before intervening.

## 8. `XACK` Confirms Processing, Without Deleting the Stream Entry

After successfully processing a record:

```redis
XACK orders:events order-workers 1700000000000-0
```

Redis removes that record from the group's PEL. **The record data remains in the stream** until deleted or trimmed according to the retention policy.

| Command | Group new-delivery position | PEL | Stream data |
| --- | --- | --- | --- |
| `XREADGROUP ... >` | May advance | Adds new pending | Still present |
| `XACK` | Does not move cursor | Removes acknowledged pending | Still present |
| `XDEL` | Does not directly confirm progress | Can leave pending without payload to reprocess | Deletes entry |
| `XTRIM` | Does not check whether all groups ACKed | Can affect pending if trimmed before processing | Trims entries |

Example:

```redis
XLEN orders:events
XACK orders:events order-workers 1700000000000-0
XLEN orders:events
```

`XLEN` does not drop just because of `XACK`. ACK is scoped to the group; retention is scoped to the stream.

If you ACK **before** finishing business writes and the worker dies, work can be lost at the application level because the record is no longer pending. If you write data successfully **before** ACK and the worker dies, the record can be reprocessed. Therefore, ACK after processing succeeds and design **idempotency** for side effects.

## 9. Crucial Difference: `XREADGROUP ... >` vs. `XREADGROUP ... 0`

### Reading New Messages for the Group: `>`

```redis
XREADGROUP GROUP order-workers worker-A COUNT 10 STREAMS orders:events >
```

This looks for records never yet delivered in the group. It **does not return pending entries of `worker-A` or `worker-B`** simply because they are unacknowledged.

### Re-Reading a Consumer's Own Pending Entries: `0`

```redis
XREADGROUP GROUP order-workers worker-A COUNT 10 STREAMS orders:events 0
```

This reads pending entries currently owned by **`worker-A`**, starting from the low marker. It does not re-read the whole stream and does not fetch `worker-B`'s pending entries.

With a specific ID:

```redis
XREADGROUP GROUP order-workers worker-A COUNT 10 STREAMS orders:events 1700000000000-0
```

Redis iterates pending IDs greater than the supplied marker. This can be used to paginate pending entries by record ID.

| Command | Data returned |
| --- | --- |
| `XREADGROUP GROUP g A STREAMS s >` | New records not yet delivered in group `g` |
| `XREADGROUP GROUP g A STREAMS s 0` | Pending records currently belonging to A |
| `XREADGROUP GROUP g B STREAMS s 0` | Pending records currently belonging to B |
| `XAUTOCLAIM s g B ...` | Pending records idle long enough, transferred in ownership to B |

To create a new group that reads from the start of the stream, pass `0-0` to **`XGROUP CREATE`**, and then still read new messages with `>`. Changing the polling code to ID `0-0` on an active group does not reset the group to read the entire stream.

## 10. Failed Consumers: `XCLAIM` and `XAUTOCLAIM`

If `worker-A` dies after receiving a message, A's pending entries remain. Redis does not automatically push pending entries to `worker-B` via `>`. You can use claim operations.

### Taking Over an ID with `XCLAIM`

```redis
XCLAIM orders:events order-workers worker-B 60000 1700000000000-0
```

Here `60000` is the minimum idle time in milliseconds. When the claim succeeds, the record is reassigned to `worker-B` to process and ACK within the same group.

### Scanning and Claiming with `XAUTOCLAIM`

Redis 6.2 and later support:

```redis
XAUTOCLAIM orders:events order-workers worker-B 60000 0-0 COUNT 20
```

This scans the PEL from cursor `0-0`, finds records idle long enough, claims them for `worker-B`, and returns the claimed records along with the cursor for the next scan. When there are many pending entries, continue using the returned cursor until the scan pass finishes; new pending entries may appear afterwards.

Some Redis versions also return a list of IDs removed from the PEL because the corresponding records were deleted from the stream. Therefore, handle the case where pending metadata exists without a payload to process.

**Claiming does not prove the old worker is dead.** `worker-A` might be executing a long-running task. Claiming too early causes both A and B to execute side effects. Idle thresholds must reflect real latency, and the application still needs idempotency or an appropriate fencing mechanism.

### Do Not Delete a Consumer Just to “Restart” Pending Entries

`XGROUP DELCONSUMER` removes the consumer's metadata and the pending entries attached to it per command semantics. Inspect or transfer pending entries before deleting a consumer. If a worker simply changes its name after a restart, reading `>` under the new name will not automatically rescue pending entries from the old name.

## 11. Spring Data Redis: `Consumer`, `ReadOffset`, and `StreamOffset`

Mapping between Redis and Java:

| Redis | Spring Data Redis |
| --- | --- |
| Stream key `orders:events` | `StreamOffset.create("orders:events", ...)` |
| Group `order-workers` | `Consumer.from("order-workers", "worker-A")` |
| Read new via `>` | `ReadOffset.lastConsumed()` when reading with a consumer group |
| Read via `XREADGROUP` | `StreamOperations.read(Consumer, options, offsets)` |
| ACK an ID | `opsForStream().acknowledge(stream, group, recordId)` |
| Polling and callbacks | `StreamMessageListenerContainer` |

An important point is that `ReadOffset.lastConsumed()` **in consumer group mode** is used to request new messages based on the group's progress, corresponding to `>`. It does not mean “the last ID `consumer A` ACKed”.

### 11.1. Polling a Batch via `StringRedisTemplate`

```java
import java.time.Duration;
import java.util.List;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.connection.stream.StreamReadOptions;
import org.springframework.data.redis.core.StringRedisTemplate;

public class OrderStreamPoller {

    private final StringRedisTemplate redis;

    public OrderStreamPoller(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void pollOnce() {
        List<MapRecord<String, Object, Object>> messages =
                redis.opsForStream().read(
                        Consumer.from("order-workers", "worker-A"),
                        StreamReadOptions.empty()
                                .count(10)
                                .block(Duration.ofSeconds(2)),
                        StreamOffset.create(
                                "orders:events",
                                ReadOffset.lastConsumed()));

        if (messages == null) {
            return;
        }

        for (MapRecord<String, Object, Object> message : messages) {
            try {
                String orderId = String.valueOf(
                        message.getValue().get("orderId"));

                // Process business logic idempotently.
                processOrder(orderId);

                redis.opsForStream().acknowledge(
                        "orders:events",
                        "order-workers",
                        message.getId());
            } catch (Exception ex) {
                // Log/record metrics; do not ACK so it remains pending.
                // Must have a separate pending-recovery mechanism.
            }
        }
    }

    private void processOrder(String orderId) {
        // Implement application business logic.
    }
}
```

This example assumes the stream has an `orderId` field in a format readable by `StringRedisTemplate`. When using custom serializers or object mapping, adjust generic types and decoding accordingly.

Note that the code above only illustrates **reading new messages**; it does not include a pending-recovery worker, retry policy, or dead-letter handling—add those when the application requires processing guarantees.

### 11.2. Using `StreamMessageListenerContainer`

Callback-style listener:

```java
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.stream.StreamListener;
import org.springframework.stereotype.Component;

@Component
public class OrderStreamListener
        implements StreamListener<String,
                MapRecord<String, String, String>> {

    private final StringRedisTemplate redis;

    public OrderStreamListener(StringRedisTemplate redis) {
        this.redis = redis;
    }

    @Override
    public void onMessage(MapRecord<String, String, String> message) {
        try {
            String orderId = message.getValue().get("orderId");
            String recordId = message.getId().getValue();

            processIdempotently(orderId, recordId);

            redis.opsForStream().acknowledge(
                    "orders:events",
                    "order-workers",
                    message.getId());
        } catch (Exception ex) {
            // Log error details and record ID.
            // Do not ACK until processing is complete.
        }
    }

    private void processIdempotently(String orderId, String recordId) {
        // Example: persist result with a unique business/event ID.
    }
}
```

Container configuration:

```java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.serializer.RedisSerializer;
import org.springframework.data.redis.stream.StreamMessageListenerContainer;

@Configuration
public class StreamConsumerConfiguration {

    @Bean
    public StreamMessageListenerContainer<String,
            MapRecord<String, String, String>> streamContainer(
            RedisConnectionFactory connectionFactory,
            OrderStreamListener listener) {

        var options = StreamMessageListenerContainer
                .StreamMessageListenerContainerOptions
                .<String, MapRecord<String, String, String>>builder()
                .pollTimeout(Duration.ofSeconds(2))
                .batchSize(10)
                .keySerializer(RedisSerializer.string())
                .hashKeySerializer(RedisSerializer.string())
                .hashValueSerializer(RedisSerializer.string())
                .build();

        var container = StreamMessageListenerContainer
                .create(connectionFactory, options);

        container.receive(
                Consumer.from("order-workers", "worker-A"),
                StreamOffset.create(
                        "orders:events",
                        ReadOffset.lastConsumed()),
                listener);

        return container;
    }
}
```

The container is a Spring bean with a lifecycle for starting and stopping subscriptions. The name `worker-A` is illustrative; in multi-instance deployments, configure a **distinct consumer name for each active instance**. If two processes share the same consumer name, tracking ownership and recovery becomes hard to control. Conversely, when a consumer changes its name after a restart, pending entries attached to the old name still need to be claimed or recovered by design.

In applications using different serialization configs, declare matching key, hash-key, and hash-value serializers. The container handles polling/callbacks; **it does not automatically create groups, auto-ACK every business operation, or claim all old pending entries**.

## 12. Choosing `ReadOffset` Must Depend on Read Mode

Spring Data Redis offers ways to construct read offsets, yet **the same offset can have different meanings in `XREAD` and `XREADGROUP`**.

| Choice | Direct stream read (no group) | Consumer group read |
| --- | --- | --- |
| `ReadOffset.from("0-0")` | Starts after the given ID in stream data | Iterates the calling consumer's pending entries; does not recreate the group from scratch |
| `ReadOffset.latest()` | Picks the current tail, similar to `$` | Not the standard choice for polling new group messages |
| `ReadOffset.lastConsumed()` | Uses a consumed position per abstraction | In a consumer group, requests new records (`>`) |

**To process backlog from the beginning:** create the group at `0-0` and then poll with `lastConsumed()`.

**To process only messages produced after initialization:** create the group at `$` and then poll with `lastConsumed()`.

Keep the two decisions separate: *where the group starts* (via `XGROUP CREATE`/`SETID`) and *whether the consumer wants new messages or pending ones* (via `>`/ID in `XREADGROUP`).

If you use `ReadOffset.latest()` to poll a stream **without a group**, messages arriving between two polls can be skipped when the next poll again picks the current tail. Inside a consumer group, `lastConsumed()` avoids that confusing “latest” offset behavior on the new-message path.

## 13. Handling Pending Entries When the Application Restarts

Scenario:

```text
worker-A receives record 100-0 via XREADGROUP ... >
worker-A writes successfully to database
worker-A loses connection before XACK

Redis:
  record 100-0 remains pending with owner = worker-A

worker-B reads with >:
  receives only new records, does NOT automatically receive 100-0

Recovery:
  worker-A reads its pending entries from ID 0, or
  worker-B claims 100-0 once idle time is sufficient
```

If `worker-B` reprocesses `100-0`, the database side effect may occur a second time. Therefore, use the record ID, event ID, or business ID as an idempotency key—for instance, a database unique constraint within the same transaction as the business mutation.

A practical policy:

1. Poll new records via `lastConsumed()`.
2. ACK **after** durable side effects complete.
3. When the handler fails, keep pending; record errors with bounds.
4. Monitor pending age and delivery count.
5. Run a process to read the consumer's pending entries or `XAUTOCLAIM` with a sensible idle threshold.
6. Cap retries and provide a dead-letter stream/error record for unprocessable messages; only ACK the source message once forwarding to the next stage has been confirmed per policy.
7. Tune concurrency and batch size so pending entries do not grow unbounded.

Without a pending-recovery path, a consumer group—even with a PEL—can leave work “stuck” indefinitely.

## 14. Changing a Group's Position with `XGROUP SETID`

Redis supports adjusting a group's read position:

```redis
XGROUP SETID orders:events order-workers 0-0
```

This command updates **`last-delivered-id`**. It does not roll back changes made by consumers, does not clear the PEL, and does not reset business state. Moving the position backward can cause old messages to be reconsidered on the new-read path, risking duplicates. Moving it forward to the end can skip backlog.

Notes:

- Records already deleted from the stream cannot be recovered via `SETID`.
- Existing pending entries must be handled separately.
- Resetting the cursor while multiple workers are running can cause unpredictable results.
- Idempotent group initialization should not automatically run `SETID` on every deployment.

If you need to replay a dataset independently, creating a **new consumer group** at the right marker is often easier to control than resetting a production group.

## 15. Stream Retention Differs from Group ACK Status

Inspection commands:

```redis
XLEN orders:events
XRANGE orders:events - + COUNT 10
XINFO STREAM orders:events
XINFO GROUPS orders:events
XINFO CONSUMERS orders:events order-workers
XPENDING orders:events order-workers
```

- `XLEN` measures stored records remaining.
- `XRANGE` views currently remaining records.
- `XINFO STREAM` views stream metadata.
- `XINFO GROUPS` views groups and new-delivery progress.
- `XINFO CONSUMERS` views consumers and per-consumer pending counts.
- `XPENDING` views unacknowledged work.

Example capping stream length:

```redis
XTRIM orders:events MAXLEN ~ 100000
```

`~` requests approximate trimming for performance optimization. **The command does not verify that all groups have finished before deleting records.** If retention is too short, pending records or undelivered backlog can lose their payloads. Retention design must account for ingress rate, processing rate, longest outage duration, and replay needs.

Newer Redis versions add deletion options that consider consumer group state, though you must verify exact semantics and version support before using them.

## 16. Do Redis Streams Consumer Groups Guarantee Exactly-Once?

**Not automatically.** Consumer groups provide distribution and pending metadata for applications to build processing/retry logic, yet business outcomes can still repeat:

| Failure occurs when | Redis state | Risk |
| --- | --- | --- |
| Worker dies before processing and before ACK | Record pending | Requires recovery/claim to continue |
| Worker finishes processing but dies before ACK | Record still pending | Retry may repeat side effects |
| Worker ACKs before committing results | Pending is gone | Error after ACK can lose work |
| Worker reads with `NOACK` | No normal pending created | No PEL recovery path on failure |

Only by combining idempotency, timely acknowledgment, controlled retries, and pending recovery can you effectively achieve *at-least-once* processing for retained, accessible data. Even then, integrations with SQL, HTTP, or external systems require dedicated deduplication and error handling.

## 17. Monitoring Groups and Consumers in Operations

Use:

```redis
XINFO GROUPS orders:events
XINFO CONSUMERS orders:events order-workers
XPENDING orders:events order-workers
```

| Signal | What to understand |
| --- | --- |
| `last-delivered-id` | New-record delivery marker, not completion marker |
| `pending` | Number of delivered records not yet ACKed |
| `lag` | Estimated undelivered records when Redis has enough metadata; sometimes undefined |
| Consumer idle/inactive | Activity level; exact meaning depends on Redis version |
| Delivery count | Hints that a record was redelivered/claimed repeatedly |
| ACK rate | Rate of confirmed processing |
| Processing latency | Execution duration used to choose claim thresholds |
| Dead-letter count | Number of records unprocessable under retry policy |

Commands requiring caution:

- `XGROUP DESTROY` deletes the group and its pending state.
- `XGROUP SETID ... $` can skip undelivered records.
- `XGROUP DELCONSUMER` affects pending entries owned by that consumer.
- Aggressive `XTRIM` can delete records needed for retries.
- Unverified bulk `XACK` can clear pending entries without completing work.

## 18. Hands-On with Two Consumers

This exercise uses a dedicated test stream.

### Step 1: Create a Group

```redis
XGROUP CREATE demo:orders:events demo-workers 0-0 MKSTREAM
```

### Step 2: Add Three Records

```redis
XADD demo:orders:events * type created orderId 101
XADD demo:orders:events * type created orderId 102
XADD demo:orders:events * type created orderId 103
```

Record the IDs returned by Redis.

### Step 3: Consumer A Reads Two Records

```redis
XREADGROUP GROUP demo-workers worker-A COUNT 2 STREAMS demo:orders:events >
XPENDING demo:orders:events demo-workers
```

### Step 4: Consumer B Reads the Remaining Record

```redis
XREADGROUP GROUP demo-workers worker-B COUNT 2 STREAMS demo:orders:events >
```

Consumer B normally receives the third undelivered record. If B keeps reading with `>` when no new records exist, it does not automatically take A's pending records.

### Step 5: ACK One Record Owned by A

```redis
XACK demo:orders:events demo-workers <actual-id-of-record-A>
XLEN demo:orders:events
XPENDING demo:orders:events demo-workers
```

`XPENDING` decreases if the ACK succeeds, whereas `XLEN` does not decrease just from ACKing.

### Step 6: A Re-Reads Its Pending Entries

```redis
XREADGROUP GROUP demo-workers worker-A COUNT 10 STREAMS demo:orders:events 0
```

This reads A's pending entries, not all stored records.

### Step 7: B Takes Over A's Pending Entry

In Redis 6.2+ on a test environment:

```redis
XAUTOCLAIM demo:orders:events demo-workers worker-B 1000 0-0 COUNT 10
```

The 1-second threshold is illustrative. In production, choose a high enough value based on business processing duration to avoid claiming a record that A is still processing normally.

### Step 8: Inspect Metadata

```redis
XINFO GROUPS demo:orders:events
XINFO CONSUMERS demo:orders:events demo-workers
XPENDING demo:orders:events demo-workers
XLEN demo:orders:events
```

Pending count can drop to 0 while all three records remain in the stream. This is the difference between processing state and retention.

## 19. Common Misconceptions

**“Each consumer in a group has an independent cursor for the whole stream.”**  
No. The group coordinates the new-record delivery position; each consumer mainly has its own pending entries and metadata.

**“`last-delivered-id` is the last ACKed ID.”**  
No. A group can deliver records up to the end of the stream while many pending entries remain unprocessed.

**“`XREADGROUP ... >` will automatically retry failed records.”**  
No. Failed delivered records stay pending; you must read pending entries or claim them.

**“`XREADGROUP ... 0` reads the entire stream from the start.”**  
No. Within a consumer group, it iterates the calling consumer's pending entries.

**“Creating a group at `$` helps read backlog.”**  
No. It initializes the group at the stream's tail at creation time.

**“`XACK` deletes data from the stream.”**  
No. `XACK` only removes pending status in the group; it does not enforce retention.

**“Multiple consumers and ACKs give automatic exactly-once.”**  
No. Duplicate processing can still occur after connection errors and retries; idempotency is required.

**“`lag = 0` means all work is finished.”**  
No. The group may still have unacknowledged pending entries.

## 20. Self-Check Questions

1. Why do two consumers in one group coordinate message distribution, whereas two different groups can both receive the same message?
2. How does `XGROUP CREATE stream group 0-0` differ from `XGROUP CREATE stream group $`?
3. What does `last-delivered-id` reflect and how does it differ from ACK status?
4. Why is A's pending entry not picked up by B via `XREADGROUP ... >`?
5. When reading with `XREADGROUP ... 0`, whose pending entries does Redis return?
6. Does `XACK` reduce `XLEN`?
7. Why does `XAUTOCLAIM` need an appropriate `min-idle-time` and idempotency?
8. What kind of messages does Spring Data Redis request when using `ReadOffset.lastConsumed()` in a consumer group?
9. If SQL commits and the worker dies before ACK, what is the risk during recovery?
10. When `pending > 0` but `lag = 0`, has the group finished its work?

**Remember:** In Redis Streams, **the group holds the new-message delivery position**, **consumers receive shares of the group's work**, and **the PEL tracks delivered but unacknowledged messages**. Choose the group starting position with `0-0` or `$`, read new messages with `>` (via `ReadOffset.lastConsumed()` in Spring Data Redis), and design ACK, recovery, and retention separately.

## References

- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html): `StreamOperations`, consumer groups, offsets, and listener containers.
- [Redis — XGROUP CREATE](https://redis.io/docs/latest/commands/xgroup-create/): creating groups and choosing `0-0` or `$`.
- [Redis — XREADGROUP](https://redis.io/docs/latest/commands/xreadgroup/): reading new messages with `>` and pending entries by ID.
- [Redis — XPENDING](https://redis.io/docs/latest/commands/xpending/): inspecting the Pending Entries List.
- [Redis — XACK](https://redis.io/docs/latest/commands/xack/): confirming processing in a group.
- [Redis — XAUTOCLAIM](https://redis.io/docs/latest/commands/xautoclaim/): taking over pending entries by idle time.
- [Redis — XINFO GROUPS](https://redis.io/docs/latest/commands/xinfo-groups/): `last-delivered-id`, pending, and lag.
