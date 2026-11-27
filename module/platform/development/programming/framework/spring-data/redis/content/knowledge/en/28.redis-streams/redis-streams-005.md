# Pending Entries List and Processing Confirmation via Acknowledgment in Spring Data Redis Streams

## 1. Why Do Redis Streams Need a Pending Entries List?

Redis Streams is an ordered, log-like data structure used to write and read event records. Unlike regular Pub/Sub, a Stream stores entries so applications can replay them when needed, governed by a system-defined retention policy. When multiple processes divide work using a **consumer group**, Redis needs to know:

- Which messages have been delivered to a consumer?
- Which messages have not yet been reported as finished by the consumer?
- Which consumer currently owns a message?
- How many times has a message been delivered, and when was the most recent time?
- If a consumer fails, who can take over the message?

The structure that tracks this state is the **Pending Entries List (PEL)**.

**The PEL is a set of metadata tracking entries delivered to a consumer group that have not yet been confirmed via acknowledgment (`XACK`).** The PEL is not an independent copy of all payloads in the Stream. The original entry still lives in the Stream according to its storage policy.

This lesson focuses on two mechanisms:

1. **Pending:** after a consumer reads new messages via `XREADGROUP` without `NOACK`, Redis places the message IDs into the group's PEL.
2. **Acknowledgment:** after successful processing, the consumer calls `XACK` to remove the ID from that group's PEL.

Simple lifecycle diagram:

```text
Producer
   |
   | XADD
   v
Redis Stream: orders-stream
   |
   | XREADGROUP GROUP orders-workers worker-A STREAMS orders-stream >
   v
Message delivered to worker-A
   |
   +--> PEL of group "orders-workers" records:
   |       ID, consumer=worker-A, idle time, delivery count
   |
   +--> Application processes data
           |
           +-- Success --> XACK --> removes pending state
           |
           +-- Crash/error --> no XACK --> entry remains in PEL
                                               |
                                               +--> another worker claims and reprocesses
```

This is the foundation for **at-least-once processing when the application implements proper retries/recovery**. It **does not automatically guarantee exactly-once** and does not automatically redeliver every pending message without a consumer or active recovery mechanism.

## 2. Concepts to Distinguish

| Concept | Role | Example |
|---|---|---|
| Stream | Log containing entries | `orders-stream` |
| Stream entry ID | Identifies an entry in the Stream | `1763000000123-0` |
| Consumer group | Group of consumers sharing read progress | `orders-workers` |
| Consumer | Named member within a group | `worker-A` |
| Last-delivered ID | The group's new-message delivery position | A Stream ID |
| Pending Entries List | List of delivered but unacknowledged entries | ID `...-0` owned by `worker-A` |
| Acknowledgment | Confirms a message is processed to remove it from PEL | `XACK orders-stream orders-workers <id>` |
| Claim | Transfers ownership of a pending message to another consumer | `XCLAIM`, `XAUTOCLAIM` |
| Stream retention | Policy for keeping/deleting original entries | `XTRIM`, `MAXLEN`, `MINID` |

Separate **entry data** from **group processing state**:

```text
Redis Stream (data):
    100-0 -> {orderId=o-1, type=CREATED}
    101-0 -> {orderId=o-2, type=PAID}
    102-0 -> {orderId=o-3, type=CANCELLED}

Group orders-workers:
    Last delivered ID: 102-0
    PEL:
        100-0 -> worker-A, pending
        102-0 -> worker-B, pending
    101-0: ACKed, no longer in PEL

Group audit-workers:
    Has its own read position and PEL.
```

An entry can already be ACKed by one group while still pending in another group. `XACK` **is not a global acknowledgment across all groups**.

## 3. Creating a Stream and Consumer Group

Suppose an application processes orders. In Redis CLI, create the group before reading:

```redis
XGROUP CREATE orders-stream orders-workers 0 MKSTREAM
```

Meaning:

- `orders-stream`: Stream name.
- `orders-workers`: consumer group name.
- `0`: starting ID marker; the group can read existing entries from the start of the Stream.
- `MKSTREAM`: creates an empty Stream if the key does not yet exist.

If a group with the same name already exists, Redis returns an error similar to `BUSYGROUP Consumer Group name already exists`. In real applications, group creation needs an idempotent initialization strategy: clearly distinguish “already exists” from permission, connection, or wrong-type errors. Do not catch and ignore every exception.

### 3.1. Choosing Starting Marker `0` vs. `$`

You can create a group when the Stream already contains data:

```redis
XGROUP CREATE orders-stream orders-workers 0
```

or:

```redis
XGROUP CREATE orders-stream orders-workers $
```

Difference:

| Group creation marker | Desired behavior |
|---|---|
| `0` / `0-0` | Existing entries with IDs greater than the marker can also be delivered |
| `$` | The group starts from the current tail of the Stream, primarily receiving new entries arriving after group creation |

If old data must be processed, initializing at `$` can skip existing history. If you only want new events, starting at the beginning of the Stream can make the service process an unexpectedly huge backlog.

Choose the marker based on business requirements. Changing the marker on an already active group should be done deliberately rather than silently “resetting” to paper over a consumer bug.

### 3.2. Writing Data with `XADD`

```redis
XADD orders-stream * orderId o-101 type CREATED
XADD orders-stream * orderId o-102 type PAID
XADD orders-stream * orderId o-103 type CANCELLED
```

The `*` asks Redis to assign a new ID. Redis returns the entry's actual ID, for example:

```text
"1763000000123-0"
```

IDs returned in a real environment will differ. Do not assume an ID matches an example value verbatim.

`XADD` appends an entry to the **Stream**; it does not place the entry into the PEL. An entry only becomes pending after the group delivers it to a consumer under normal tracking mode.

## 4. Reading Messages with `XREADGROUP`

Consumer `worker-A` reads new messages:

```redis
XREADGROUP GROUP orders-workers worker-A COUNT 2 STREAMS orders-stream >
```

Explanation:

- `GROUP orders-workers worker-A`: the group and consumer receiving messages.
- `COUNT 2`: limits the number of entries returned in one read, acting as a batch cap rather than a total cap on the consumer's work.
- `STREAMS orders-stream >`: reads messages **never yet delivered to any consumer in the group**, according to the group's tracked position.
- No `NOACK`: delivered entries are placed into the PEL.

Each consumer in the same group normally receives a subset of new entries, rather than every consumer receiving a broadcast of every entry like Pub/Sub.

After one read, the state might look like:

```text
Stream:
    id1 -> o-101
    id2 -> o-102
    id3 -> o-103

Group orders-workers:
    worker-A was just delivered id1, id2
    PEL:
        id1 -> owner=worker-A
        id2 -> owner=worker-A

id3: not yet delivered by the group, not yet in the PEL.
```

`XREADGROUP` can also take:

```redis
XREADGROUP GROUP orders-workers worker-B COUNT 10 BLOCK 5000 STREAMS orders-stream >
```

`BLOCK 5000` waits up to about 5 seconds when no new message is available, specified in milliseconds. `BLOCK 0` means waiting indefinitely per Redis semantics; in production applications, understand its impact on connections and shutdown.

### 4.1. Consumer Name Is an Ownership Identity

The name `worker-A` is a string chosen by the application. Redis uses it to associate pending entries with a consumer. Redis does not automatically know a Java process died just because a consumer name remains in the group.

If different processes intentionally use the **same consumer name**, they may read shared pending history under that identity, obscuring actual ownership. Usually, assign a stable consumer name for a worker instance's lifetime, distinct across coexisting workers.

Also plan for when a worker is replaced: you can use a new name and claim pending entries from the old worker rather than merely expecting Redis to reassign messages on its own.

## 5. When Is a PEL Entry Created?

An entry passes through these logical states:

```text
1. Producer calls XADD:
      entry is in Stream
      not yet in group's PEL

2. Consumer calls XREADGROUP ... >:
      entry is delivered to consumer
      entry enters group's PEL
      records owner, timing info, delivery count

3. Processing succeeded, NOT YET XACKed:
      remains in PEL

4. Consumer calls XACK:
      entry is removed from group's PEL
      entry may still remain in Stream

5. If processing fails:
      no XACK
      entry remains pending for retry/claim
```

From this, two conclusions follow:

- **“Message was read” does not mean “message was processed successfully”.** The PEL preserves this distinction.
- **“Message is no longer pending” does not mean “message was deleted from the Stream”.** These are two separate lifecycles.

Redis cannot verify business success by inspecting a Java method. Only when the application explicitly ACKs does Redis record completion at the group level.

### 5.1. The PEL Does Not Alter Stream Payloads

The PEL holds tracking metadata; actual data such as `orderId` and `type` still resides in the original entry. When another consumer claims a pending entry, Redis looks up the payload by ID in the Stream.

If the original entry was deleted or trimmed while the PEL still held its ID, recovery may encounter a **dangling pending entry** with no payload left. Therefore, Stream retention must be designed alongside processing and recovery times; the PEL cannot serve as a backup payload store.

## 6. Inspecting Pending Entries with `XPENDING`

Redis provides the `XPENDING` command to read PEL state.

### 6.1. Summary Form of `XPENDING`

```redis
XPENDING orders-stream orders-workers
```

The logical output typically reports:

1. Total number of pending entries in the group.
2. Smallest pending ID.
3. Largest pending ID.
4. Consumers and their corresponding pending entry counts.

Illustrative example:

```text
pending count = 2
smallest id   = 1763000000123-0
largest id    = 1763000000124-0
consumers     = {worker-A: 2}
```

If the group has no pending entries, the summary shows count 0 and no corresponding ID range.

The strength of the summary form is seeing the size of the unacknowledged backlog without fetching every entry.

### 6.2. Detailed Form of `XPENDING`

```redis
XPENDING orders-stream orders-workers - + 10
```

Where:

- `-`: starts from the smallest ID.
- `+`: up to the largest ID.
- `10`: at most 10 entries to list.

Each entry typically shows:

```text
message ID
owner consumer
idle time (milliseconds)
delivery count
```

Logical example:

```text
ID: 1763000000123-0
Consumer: worker-A
Idle: 42000 ms
Deliveries: 1
```

You can filter by consumer:

```redis
XPENDING orders-stream orders-workers - + 10 worker-A
```

You can filter by minimum idle time on Redis versions supporting that syntax:

```redis
XPENDING orders-stream orders-workers IDLE 60000 - + 10
```

Meaning: inspect entries that are pending and have been idle for at least roughly 60 seconds. When using `IDLE`, check syntax and Redis version support in your deployment environment.

### 6.3. Is Idle Time Total Processing Time?

Idle time reflects the elapsed time since the most recent delivery/claim according to PEL metadata. When an entry is redelivered or claimed, that timing metadata can be updated. Thus, idle time does not necessarily equal age since `XADD` or total time since the entry first entered the group.

`delivery count` should also be understood as the number of deliveries tracked by Redis, not the number of times the handler definitely completed business work.

### 6.4. Do Not Use `XPENDING` as a Substitute for Reading Payloads

`XPENDING` is for monitoring ownership and delivery history. It is not an equivalent API to `XREADGROUP ... >` for receiving new messages with full payloads.

To process pending entries, re-read pending entries belonging to the same consumer via history mode or transfer ownership with `XCLAIM`/`XAUTOCLAIM`.

## 7. Acknowledgment with `XACK`

Once the handler finishes the necessary work, call:

```redis
XACK orders-stream orders-workers 1763000000123-0
```

Syntax:

```redis
XACK <stream-key> <group-name> <id> [id ...]
```

`XACK` removes the specified IDs from the PEL of **that consumer group**. The return value is the **number of entries acknowledged and removed from the PEL**.

Example:

```redis
XACK orders-stream orders-workers 1763000000123-0 1763000000124-0
```

The result can be `2` if both IDs were pending in the group and successfully ACKed, or smaller if one or more IDs were no longer pending.

### 7.1. `XACK` Does Not Delete Entries from the Stream

After ACK:

```text
Stream:
    id1 -> {orderId=o-101, type=CREATED}    (may still remain)
    id2 -> {orderId=o-102, type=PAID}       (may still remain)

Group orders-workers:
    PEL: id1, id2 are gone
```

You can inspect the original entries with:

```redis
XRANGE orders-stream - +
```

On large Streams, avoid unbounded `XRANGE - +` in production. Limit the entry count:

```redis
XRANGE orders-stream - + COUNT 10
```

To remove data from the Stream, use a retention/trim policy or appropriate entry deletion commands. Do not confuse clearing the PEL with cleaning up the log.

### 7.2. ACK Does Not Validate Business Outcomes

Redis does not check the database, email gateway, or handler correctness before `XACK`. If the application ACKs early and then performs the work, an error after ACK can lose the chance to retry via the PEL.

Flawed design in many systems:

```text
XREADGROUP -> XACK -> call database -> database error
```

Here the PEL no longer holds the message while business work remains incomplete.

A usually safer order:

```text
XREADGROUP -> validate -> durable processing -> XACK
```

Even so, this order still has a duplicate window if business work succeeds and ACK fails. Therefore, **idempotency** is needed when high reliability is required.

### 7.3. What Does `XACK` Returning `0` Mean?

If `XACK` is called for an ID not present in the group's PEL, Redis may return `0`. Causes include:

- The entry was already ACKed earlier.
- The entry was never delivered to the group.
- The entry was already removed from the PEL by another cleanup operation.
- The application passed the wrong Stream key, group, or ID.

Do not interpret `0` simply as “the message does not exist in the Stream”. Those are two separate questions: **is it still pending?** and **does the original entry still exist?**

## 8. A Full Lifecycle Using `redis-cli`

In a test environment, use a dedicated Stream and group name:

```redis
XGROUP CREATE demo:orders demo-workers 0 MKSTREAM
```

Publish two entries:

```redis
XADD demo:orders * orderId o-201 action CREATED
XADD demo:orders * orderId o-202 action PAID
```

Redis returns real IDs, denoted `ID_A` and `ID_B` below. When running commands yourself, replace those placeholders with the IDs returned by Redis.

Consumer receives messages:

```redis
XREADGROUP GROUP demo-workers consumer-A COUNT 2 STREAMS demo:orders >
```

Inspect the PEL:

```redis
XPENDING demo:orders demo-workers
XPENDING demo:orders demo-workers - + 10
```

After completing business processing for `ID_A`, ACK it:

```text
XACK demo:orders demo-workers <ID_A>
```

This is illustrative syntax; `<ID_A>` must be replaced with the concrete ID before running.

Check again:

```redis
XPENDING demo:orders demo-workers
```

The count drops from 2 to 1. Meanwhile, the original entries can still be read using `XRANGE`.

Finally, after successfully processing `ID_B`, ACK the remaining entry:

```text
XACK demo:orders demo-workers <ID_B>
```

After this step, assuming no other pending entries exist, the count drops to 0. **The Stream does not become empty just because the PEL is empty.**

### 8.1. What Happens If `XREADGROUP` Is Called Again?

Once all new entries have been delivered to the group, continuing to call:

```redis
XREADGROUP GROUP demo-workers consumer-A COUNT 10 STREAMS demo:orders >
```

means `>` will not return entries that are still pending just because they have not been ACKed. Reading new messages and handling pending messages are **two separate flows**.

This is one of the common reasons systems stop processing certain entries after a crash: new consumers only read `>` and have no recovery process.

## 9. Re-Reading a Consumer's Own Pending Entries

In `XREADGROUP`, ID `>` means reading messages **new to the group**. By specifying a concrete ID such as `0`, a consumer can re-read the pending history of **that same consumer**:

```redis
XREADGROUP GROUP demo-workers consumer-A COUNT 10 STREAMS demo:orders 0
```

Key differences:

| ID after Stream name in `XREADGROUP` | Meaning |
|---|---|
| `>` | Reads entries never delivered to any consumer in the group |
| `0` / `0-0` | Reads pending entries already owned by the current consumer name, starting from the specified position |
| A specific ID | Reads pending history of the current consumer after that ID, per command rules |

**Do not confuse reading the same consumer's pending entries with taking ownership from another consumer.** If `worker-A` dies and `worker-B` calls `XREADGROUP ... worker-B ... 0`, `worker-B` does not automatically receive the PEL belonging to `worker-A`.

For `worker-B` to take over pending messages owned by `worker-A`, you must **claim** them with `XCLAIM` or `XAUTOCLAIM` (or an equivalent recovery mechanism).

### 9.1. When Is Reading the Same Consumer's Pending History Useful?

A consumer with a stable name can restart and proactively re-read messages it previously received but has not yet ACKed. Handle these cases:

- Messages that finished processing before the crash whose ACK never reached Redis.
- Messages that have not yet been processed.
- Original messages that were trimmed/deleted and no longer have payloads.
- Redelivered messages increasing the delivery count.

Add idempotency, retry limits, and the ability to move failing entries to a DLQ if they cannot be processed successfully.

## 10. Consumer Crash: The PEL Does Not Automatically Disappear

Suppose:

```text
t1: worker-A receives entry id1.
    PEL: id1 -> owner worker-A.

t2: worker-A calls payment API.
    API completes, but worker-A crashes before XACK.

t3: worker-B keeps reading with >.
    worker-B can receive NEW messages, but does not automatically see id1.

t4: After some time:
    PEL still holds id1 -> worker-A until ACKed/claimed/cleaned via an appropriate mechanism.
```

Redis does not automatically know which parts of business work completed. A consumer disconnecting is not confirmation that the message must be re-executed immediately.

If `worker-B` keeps reading `>`, `id1` can remain pending for a very long time. The system needs a strategy to detect entries that have been idle too long and let another consumer take ownership.

## 11. `XCLAIM`: Transferring Ownership of a Pending Entry

The `XCLAIM` command lets a consumer request that eligible pending entries be transferred to it.

Typical syntax:

```redis
XCLAIM <stream> <group> <new-consumer> <min-idle-time-ms> <id> [id ...]
```

Example:

```redis
XCLAIM demo:orders demo-workers consumer-B 60000 1763000000123-0
```

Assuming the ID is pending and has been idle for at least 60,000 ms, Redis transfers ownership from `consumer-A` to `consumer-B` and returns the entry data.

Important details:

- `min-idle-time-ms` is not a message TTL; it is the **minimum idle time threshold** required to allow claiming.
- Claiming can update metadata such as owner, idle time, and delivery count.
- The entry stays in the PEL; only the owning consumer changes.
- The new consumer must **finish processing and then `XACK`**; claiming alone is not an ACK.
- If the old consumer is still running slowly, both the old and new consumers may process the same business action. Claiming cannot recall side effects already initiated by the old consumer's code.

### 11.1. Choosing a Sensible `min-idle-time`

If a job normally takes 3 minutes, setting `min-idle-time` to 5 seconds can cause another worker to claim it while the first worker is still processing normally, causing duplicates and contention.

If set too long, genuinely abandoned entries take a long time to be retried.

Consider:

- Average and p99 processing times.
- Timeouts of the task and dependent APIs.
- Any application-level heartbeat/ownership mechanism if present.
- Cost of duplicate execution.
- Maximum acceptable recovery time after a crash.

No single 60-second value fits every workload. The threshold in the example is purely illustrative.

## 12. `XAUTOCLAIM`: Automatically Finding and Claiming Idle Pending Entries

Redis 6.2 and newer support `XAUTOCLAIM`, which scans the PEL by cursor and claims entries that have been idle long enough.

Common syntax:

```redis
XAUTOCLAIM <stream> <group> <consumer> <min-idle-time-ms> <start> [COUNT <count>]
```

Example:

```redis
XAUTOCLAIM demo:orders demo-workers consumer-B 60000 0-0 COUNT 10
```

This looks for pending entries idle long enough starting from ID `0-0`, claims eligible entries for `consumer-B`, and returns the next cursor along with the claimed messages. On Redis versions that also report IDs cleaned up because the original entry no longer exists, the response may include that list too.

**`XAUTOCLAIM` does not mean the system runs recovery periodically on its own.** It is a command the application must invoke. For automatic recovery, you need a worker/scheduler or a bounded recovery loop.

### 12.1. Cursor and `COUNT`

`XAUTOCLAIM` uses a cursor to avoid scanning the entire PEL in a single call. The application should retain the returned cursor and continue scanning if needed, rather than always running `0-0` once and assuming all pending entries were inspected.

`COUNT` is the maximum number of entries desired to claim in one call, while internal entries examined are bounded by Redis mechanics. Do not expect every call to return exactly `COUNT` entries or scan the entire PEL at once.

When the returned cursor is `0-0`, the current scan pass has reached the end of the examined range. That does not guarantee the PEL will stay free of eligible entries: other entries' idle times continue increasing, new messages keep getting delivered, and new pending entries may appear.

### 12.2. Conceptual Recovery Loop

```text
cursor = "0-0"

Loop with bounded iterations/transactions:
    response = XAUTOCLAIM(stream, group, recoveryConsumer,
                          minIdle, cursor, COUNT 20)
    cursor = response.nextCursor

    For each claimed message:
        if processing succeeds:
            XACK(stream, group, message.id)
        if processing fails:
            keep pending, record error, wait for retry/compensation

    If cursor == "0-0":
        end current scan pass
```

Apply backoff, rate limiting, and avoid too many recovery workers aggressively competing at once. Do not let a recovery job scan the PEL at an unbounded rate and starve new message processing.

### 12.3. `XCLAIM` or `XAUTOCLAIM`?

| Situation | Choice |
|---|---|
| Exact ID needing ownership transfer is already known | `XCLAIM` |
| Need to scan long-idle pending entries to reclaim work | `XAUTOCLAIM` |
| Need stats on pending entries, consumers, and idle times | `XPENDING` |
| Need to read new messages | `XREADGROUP ... >` |
| Need to read pending entries of the same consumer name | `XREADGROUP ... 0` |
| Processing finished and want to clear pending | `XACK` |

For large systems, `XAUTOCLAIM` is usually more convenient than listing IDs with `XPENDING` and calling `XCLAIM` one by one, though cursor management, concurrency, and idempotency are still required.

## 13. Distinguishing Pending from Failed and Retryable

A pending entry **is not synonymous** with a failed entry. It might currently be processed normally by a worker, or finished while the ACK has not yet reached Redis.

```text
Pending =
    "Redis delivered to group, has not received ACK"

Failed =
    "Application knows this processing attempt failed"

Retryable =
    "Application decides the work can run again"
```

These three concepts must be managed separately.

A common flawed design:

```java
try {
    processOrder(record);
} catch (Exception ex) {
    // Leave pending for later recovery.
}
```

Without tracking, retry limits, or dead-letter handling, permanently failing messages remain stuck pending forever. Conversely, ACKing inside `finally` can mark incomplete work as done.

### 13.1. Error Categories to Distinguish

| Error type | Example | Handling direction |
|---|---|---|
| Transient error | Database timeout, API 503 | Retry with backoff and cap |
| Invalid payload error | Missing `orderId`, wrong schema | Move to DLQ / intentionally log failure event |
| Unprocessable business error | Order in invalid state | Per policy: record rejection or DLQ |
| Consumer crash | Process dies mid-processing | Recover pending via `XCLAIM`/`XAUTOCLAIM` |
| ACK failed after business success | Redis connection lost | May be reprocessed; requires idempotency |
| Original entry trimmed | PEL has ID but no payload | Handle dangling pending, adjust retention |

The PEL only provides delivery status. Deciding to **retry, drop, alert, or send to a DLQ** belongs to the application.

## 14. Standard Processing Pattern: ACK Only After Success

A consumer can process along this flow:

```text
Start:
    XREADGROUP fetches message

Validate:
    Check ID, schema, required fields

Idempotency:
    Check whether eventId/orderId was already processed

Business transaction:
    Persist durable data or perform controlled side effects

After success:
    XACK message.id

On error:
    Do not ACK blindly
    Record error
    Allow retry/recovery or move to DLQ per policy
```

The hard part is that **the business transaction and `XACK` are not automatically atomic across two systems**. If source data lives in PostgreSQL, a committed SQL transaction does not guarantee Redis `XACK` will succeed. And if `XACK` succeeds before the SQL commit, a crash can lose work.

### 14.1. Duplicate Window When ACK Follows Commit

```text
t1: Worker receives event E.
t2: Worker updates orders table; SQL COMMIT succeeds.
t3: Worker crashes before XACK.
t4: E remains in PEL.
t5: Recovery claims E and invokes handler again.
```

If the handler charges money or sends an email a second time, the system may produce duplicate side effects.

Thus, practical at-least-once designs need an **idempotent consumer**.

### 14.2. Idempotency by `eventId`

Each event should carry a stable business ID:

```json
{
  "eventId": "evt-1001",
  "orderId": "o-101",
  "type": "OrderPaid",
  "amount": 150000
}
```

On the system owning the data, you can maintain a table:

```sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

Inside the **same SQL transaction** as the business update, attempt to insert the unique `event_id`. If the insert hits a duplicate conflict, the handler knows this event was already applied earlier and can skip the second side effect and ACK.

This is a conceptual design. Actual SQL logic must match your database, unique-constraint handling, and business rules. If business logic involves side effects outside SQL (such as email or a payment gateway), add an outbox, provider idempotency keys, or compensation/reconciliation.

Do not assume that saving a Redis "processed" key with `SETNX` in a separate step automatically guarantees atomic synchronization with a database commit.

## 15. Spring Data Redis: Reading with `StreamOperations`

Spring Data Redis provides `StreamOperations` for working with Redis Streams in Java. The examples below use `StringRedisTemplate` with String keys and fields.

Spring Boot dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
```

Example Redis connection config:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
```

Initialize the Stream/group with Redis CLI:

```redis
XGROUP CREATE orders-stream orders-workers 0 MKSTREAM
```

Or create the group via the Spring Data Redis API when appropriate, handling the case where the group already exists:

```java
StreamOperations<String, String, String> ops =
    stringRedisTemplate.opsForStream();

ops.createGroup(
    "orders-stream",
    ReadOffset.from("0-0"),
    "orders-workers"
);
```

The Java snippet assumes these imports:

```java
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.core.StreamOperations;
```

Creating a group when the Stream does not yet exist may require creating the Stream first or selecting an initialization API/mechanism appropriate for your version. The CLI command with `MKSTREAM` is clearer in the initial example. Do not unconditionally create the group every time a worker starts without handling `BUSYGROUP`.

### 15.1. Group Reads with `ReadOffset.lastConsumed()`

Example polling service:

```java
package com.example.orders;

import java.time.Duration;
import java.util.List;

import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.core.StreamOperations;
import org.springframework.data.redis.core.StreamReadOptions;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderStreamWorker {

    private static final String STREAM = "orders-stream";
    private static final String GROUP = "orders-workers";

    private final StringRedisTemplate redis;
    private final OrderEventHandler handler;

    public OrderStreamWorker(
            StringRedisTemplate redis,
            OrderEventHandler handler) {
        this.redis = redis;
        this.handler = handler;
    }

    public void pollOnce(String consumerName) {
        StreamOperations<String, String, String> ops =
            redis.opsForStream();

        List<MapRecord<String, String, String>> records =
            ops.read(
                Consumer.from(GROUP, consumerName),
                StreamReadOptions.empty()
                    .count(10)
                    .block(Duration.ofSeconds(2)),
                StreamOffset.create(
                    STREAM,
                    ReadOffset.lastConsumed()
                )
            );

        if (records == null || records.isEmpty()) {
            return;
        }

        for (MapRecord<String, String, String> record : records) {
            try {
                handler.handle(record);

                // Acknowledge ONLY AFTER the handler succeeds.
                Long acknowledged = ops.acknowledge(
                    STREAM,
                    GROUP,
                    record.getId()
                );

                if (acknowledged == null || acknowledged == 0L) {
                    // Log/metric: ID is no longer pending in the group.
                }
            } catch (Exception failure) {
                // Log with ID/consumer context; do not ACK blindly.
                // Message remains pending for recovery per policy.
            }
        }
    }
}
```

`OrderEventHandler` is a business interface defined by the application, for example:

```java
package com.example.orders;

import org.springframework.data.redis.connection.stream.MapRecord;

public interface OrderEventHandler {
    void handle(MapRecord<String, String, String> event);
}
```

Key points to understand:

- `Consumer.from(GROUP, consumerName)` identifies the group and receiving consumer.
- `StreamOffset.create(STREAM, ReadOffset.lastConsumed())` expresses reading new entries for the consumer group (corresponding to the intent of `>`).
- `count(10)` caps the number of entries per read.
- `block(Duration.ofSeconds(2))` uses a bounded wait so the application can control polling loops and shutdown.
- `ops.acknowledge(...)` confirms processing and removes the ID from the PEL.
- `handler.handle(...)` should be idempotent to stay safe against duplicates.
- Catching errors without ACKing is only appropriate when a **recovery/poison-message policy** exists; otherwise pending entries can accumulate forever.

`pollOnce` is only a single poll, not a complete worker system with scheduler, lifecycle, shutdown, or recovery. In production, a coordinating component is needed to drive polling and monitor errors.

### 15.2. Why Not Use `ReadOffset.latest()` Out of Habit?

Spring Data Redis offers different `ReadOffset` values to express read positions. With a consumer group, to receive entries not yet delivered to the group based on saved progress, use the appropriate offset—typically `ReadOffset.lastConsumed()`.

`ReadOffset.latest()` means reading from the current tail in the corresponding read modes; using the wrong offset can skip entries, especially when polling. Do not treat every offset as equivalent to `>`.

### 15.3. Ensuring Serializer Consistency

`StringRedisTemplate` supports String keys and values. With `MapRecord`, fields/values in the example are treated as Strings. If the producer uses JSON or another binary serializer, the handler must deserialize the matching format.

Regardless of the object type the payload is decoded into, the **Stream ID** is the critical identifier for ACKing. Never synthesize a new ID to call `acknowledge`, and never pass `orderId` in place of the Redis Stream entry ID.

## 16. `StreamMessageListenerContainer` and Manual Acknowledgment

Besides polling with `StreamOperations`, Spring Data Redis has `StreamMessageListenerContainer` to manage the lifecycle of polling and dispatching messages from a Stream.

Diagram:

```text
Redis Stream
    |
    v
StreamMessageListenerContainer
    |
    v
StreamListener.onMessage(record)
    |
    +--> process business
    |
    +--> acknowledge via StreamOperations
```

Container configuration example (common API style):

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

@Configuration
public class OrderStreamContainerConfig {

    @Bean
    StreamMessageListenerContainer<String, MapRecord<String, String, String>>
    orderStreamContainer(
            RedisConnectionFactory connectionFactory,
            OrderStreamListener listener) {

        var options =
            StreamMessageListenerContainer
                .StreamMessageListenerContainerOptions
                .builder()
                .pollTimeout(Duration.ofSeconds(1))
                .build();

        StreamMessageListenerContainer<String, MapRecord<String, String, String>>
            container = StreamMessageListenerContainer.create(
                connectionFactory,
                options
            );

        container.receive(
            Consumer.from("orders-workers", "worker-A"),
            StreamOffset.create(
                "orders-stream",
                ReadOffset.lastConsumed()
            ),
            listener
        );

        container.start();
        return container;
    }
}
```

In a real project, container lifecycle should be managed appropriately by Spring; avoid starting multiple times or creating duplicate subscriptions when configuring beans. Generic types and builder options may need adjustment for your Spring Data Redis version, especially with custom template serializers or other record types.

A listener with manual ACK:

```java
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.stream.StreamListener;
import org.springframework.stereotype.Component;

@Component
public class OrderStreamListener
        implements StreamListener<String, MapRecord<String, String, String>> {

    private final StringRedisTemplate redis;
    private final OrderEventHandler handler;

    public OrderStreamListener(
            StringRedisTemplate redis,
            OrderEventHandler handler) {
        this.redis = redis;
        this.handler = handler;
    }

    @Override
    public void onMessage(MapRecord<String, String, String> record) {
        try {
            handler.handle(record);

            redis.opsForStream().acknowledge(
                "orders-stream",
                "orders-workers",
                record.getId()
            );
        } catch (Exception failure) {
            // Do not ACK if handler did not finish.
            // Log, record metrics; let recovery handle per policy.
        }
    }
}
```

Here the listener calls ACK after the handler because we want to control the exact confirmation timing. Never combine a manual-ACK listener with an auto-ack configuration on the same flow without understanding the execution order.

### 16.1. `auto-ack` vs. Manual ACK

Some consumer registration overloads on the listener container support **auto-acknowledgment** per their contract. With auto-ack, the container decides when to ACK, typically tied to dispatch/callback completion per the implementation mechanism.

If business logic needs to commit a database transaction, call an external API, or write an outbox record before acknowledging, verify whether auto-ack is appropriate. For cases requiring `handler.handle` to succeed before ACK, manual ACK makes the ordering explicit.

Auto-ack does not guarantee all side effects succeeded, especially if the listener catches and swallows exceptions or offloads work to another thread and returns early.

### 16.2. Slow Callbacks and Load Limits

If a handler takes several seconds, delivering too many messages concurrently can inflate pending counts and idle times. Choose carefully:

- Number of running consumers.
- Batch size / `COUNT`.
- Worker thread count and concurrency level.
- Timeouts and backpressure.
- Processing duration compared to the auto-claim threshold.
- Shutdown behavior to avoid leaving large numbers of in-flight messages unfinished.

Do not scale up consumer count without verifying the underlying database can handle the load.

## 17. Monitoring: Lag and Pending Are Not the Same

To tell whether a worker group is healthy, you need at least two perspectives:

1. **Lag / new backlog:** how many entries have not yet been delivered to the group, where that metric is available.
2. **Pending backlog:** how many entries have been delivered but not yet ACKed.

Redis provides these commands:

```redis
XINFO STREAM orders-stream
XINFO GROUPS orders-stream
XINFO CONSUMERS orders-stream orders-workers

XPENDING orders-stream orders-workers
XPENDING orders-stream orders-workers - + 20
```

`XINFO GROUPS` can report `pending`, `last-delivered-id`, and `lag` when supported by the Redis version and computable. In special cases such as group creation, cursor overrides, or trimming, `lag` may be unavailable or may not simply reflect the entire backlog; do not treat it as an infallible metric in all situations.

An important state:

```text
Group lag:     0
Group pending: 500
```

This can mean Redis has already delivered all new entries to the group, **yet 500 entries remain unacknowledged**. The system has not necessarily finished its work.

Conversely:

```text
Group lag:     10,000
Group pending: 0
```

can mean the group has many undelivered entries yet none awaiting ACK. You need higher reading/processing throughput rather than pending recovery.

### 17.1. Operational Metrics to Collect

| Metric | Meaning |
|---|---|
| Stream length (`XLEN`) | Entries retained in the Stream, not the exact backlog of one group |
| Pending count | Entries delivered but not yet ACKed |
| Pending oldest idle | Hints at entries that may be stuck |
| Per-consumer pending | Unacknowledged load per consumer |
| Delivery count | Sign that an entry is being redelivered/claimed repeatedly |
| Group lag | Estimated undelivered entries per group progress, when available |
| Handler success/failure | Business outcome |
| ACK success/failure | Whether confirmations are reaching Redis |
| Claim/recovery rate | How often the system has to rescue pending entries |
| DLQ size | Number of failing entries needing investigation |
| Handler latency p95/p99 | Input for tuning idle thresholds and scaling |

In particular, never use `XLEN == 0` as the sole condition for “all work finished”, and never treat `pending == 0` as “finished reading the entire Stream”.

## 18. Long-Lived Pending Entries: Identifying Troubled Consumers

Suppose:

```text
worker-A: pending 1000, very high idle time
worker-B: pending 2, just delivered
worker-C: pending 0
```

`worker-A` may be dead. Or `worker-A` may be running a long job or stuck on a slow dependency.

A sound procedure:

1. Check instance health and logs.
2. Inspect the PEL summary and idle details.
3. Compare idle time with normal processing times.
4. Check whether processing is actively running for the same message ID.
5. If eligible, claim for a recovery worker.
6. Retry idempotently; ACK upon success.
7. Track delivery counts and escalate repeatedly failing messages.

Do not “claim all pending entries the instant a consumer misses a 5-second heartbeat” if tasks can legitimately take several minutes. That can spawn multiple concurrent executions for the same message.

## 19. Poison Messages and Dead Letter Queues

A **poison message** is a message a consumer repeatedly fails to process—for example, due to missing required fields, bad schema, or unrecoverable business errors.

If workers simply keep claiming and retrying forever:

```text
worker-A receives E -> fails
worker-B claims E -> fails
worker-C claims E -> fails
...
```

The PEL stays populated for a long time, delivery counts climb, and workers waste CPU and API calls.

A typical DLQ policy:

```text
Receive message E
     |
     v
Validate / process
     |
     +-- Success --------------------------> XACK E
     |
     +-- Transient error ------------------> Wait for retry with backoff
     |
     +-- Permanent error or max retries ---> Write E + failure reason to DLQ
                                                |
                                                +--> Confirm DLQ write succeeded
                                                |
                                                +--> XACK E from original group
```

The DLQ can be another Redis Stream:

```redis
XADD orders-stream:dlq * originalId 1763000000123-0 reason INVALID_PAYLOAD
```

In practice, supply the real ID and appropriate payload/metadata. To aid investigation, store:

- Original stream name and original entry ID.
- Business event ID.
- Payload or payload reference, avoiding unauthorized exposure of secrets.
- Failure reason, timestamp, and delivery count.
- Schema version.
- Information needed to repair and replay in a controlled manner.

### 19.1. Are Writing to the DLQ and Calling `XACK` Atomic?

If the DLQ and source Stream reside on the same Redis instance/slot, you can design an appropriate transaction/script; never assume two separate commands:

```redis
XADD orders-stream:dlq ...
XACK orders-stream orders-workers <id>
```

form an atomic unit.

Possible outcomes:

- DLQ write succeeds, ACK fails: recovery may create a duplicate DLQ record if not idempotent.
- ACK succeeds, DLQ write fails (if ACK ran first): the failure trace needing attention is lost.

If strong guarantees are required, design an idempotent DLQ or a same-slot transaction/script when appropriate. On Redis Cluster, keys in different slots cannot be updated atomically via `MULTI`/Lua alone.

### 19.2. When to ACK a Poison Message

For errors unfixable by retries, ACKing after **the error record is safely stored per policy** can make sense. Failing to ACK leaves the message retrying indefinitely. However, ACKing without leaving a trace or recovery path can lose business data.

This is a business decision, not an automatic PEL behavior.

## 20. Retention: `XACK`, `XDEL`, and `XTRIM` Are Distinct Operations

Three groups of operations:

| Command | What does it modify? | Meaning |
|---|---|---|
| `XACK` | Removes pending entry from the group's PEL | Confirms processing within the group |
| `XDEL` | Deletes data entry from the Stream | Not an ACK |
| `XTRIM` | Trims entries by length/ID limit | Retention policy |
| `XADD ... MAXLEN` | Appends and caps log length optionally | Retention at write time |
| `XGROUP DESTROY` | Deletes a consumer group and its state | Group administration, does not delete the whole Stream |

Remember:

```text
ACK message != DELETE entry
DELETE entry != ACK message
```

If the Stream is trimmed/deleted before a slow group ACKs, the PEL may retain IDs without payloads. Redis has mechanisms to handle dangling PEL entries in some commands/versions, yet this **does not replace** proper retention sizing.

### 20.1. `XTRIM` Example

Keep an approximate entry count:

```redis
XTRIM orders-stream MAXLEN ~ 100000
```

`~` permits approximate trimming to save processing effort, depending on Redis internals. This is only an example; do not use `100,000` if real backlog windows can exceed that capacity.

Key questions:

- How long might the slowest consumer take to catch up?
- How many groups use the Stream?
- How long can a message remain pending before recovery?
- If keeping by `MAXLEN`, what is the peak write rate?
- Must replay be supported from a historical time or ID?

With multiple groups, retention must respect the **slowest group** if that group still needs the data. Trimming based only on the fastest group's progress can destroy payloads another group has not yet processed.

### 20.2. Pending Metrics Cannot Replace a Retention Policy

Never say “`pending = 0`, so delete the whole Stream” if another group exists, new consumers need history, or data retention obligations apply longer. Conversely, keeping the Stream unbounded forever just to enable retries can cause uncontrolled RAM growth.

Retention design and PEL recovery must be treated as two parts of the same data lifecycle.

## 21. `NOACK`: Skipping the PEL Trades Off Reliability

Redis supports reading a group with the `NOACK` option:

```redis
XREADGROUP GROUP orders-workers worker-A NOACK STREAMS orders-stream >
```

In this mode, Redis does not add delivered messages to the PEL under normal tracking. This reduces acknowledgment overhead while **giving up PEL-based recovery** for those messages.

Comparison table:

| Feature | Normal `XREADGROUP` | `XREADGROUP` with `NOACK` |
|---|---|---|
| New entries delivered | Yes | Yes |
| Pending state recorded | Yes | No |
| Must call `XACK` | Yes after successful processing | Not under `NOACK` mechanics |
| Crash recovery via PEL | Possible if recovery is implemented | Not via PEL for those messages |
| Suited for mandatory-processing tasks | Usually better suited | Usually unsuitable |
| Metadata overhead | Has PEL | Reduced PEL overhead |

`NOACK` does not turn delivery into exactly-once; it simply gives up part of the tracking. Only use it when losing crash-retry capability is acceptable—for example, lightweight best-effort tasks or data reproducible from another source.

## 22. PEL Across Multiple Consumer Groups

A Stream can have two groups:

```redis
XGROUP CREATE orders-stream orders-workers 0
XGROUP CREATE orders-stream audit-workers 0
```

The two groups have independent progress and PELs:

```text
Redis Stream orders-stream
    |
    +--> orders-workers
    |      consumer-A receives id1
    |      XACK id1 in orders-workers
    |
    +--> audit-workers
           audit-1 receives id1
           id1 remains pending in audit-workers
```

Calling:

```redis
XACK orders-stream orders-workers <id1>
```

does not clear pending state in `audit-workers`.

This allows multiple service groups to process the same event source according to different responsibilities. However, it also complicates retention: the log must be kept long enough for every group that needs payloads.

A consumer group distributes work **within one group**; across groups, each group maintains independent progress and can process the same entries.

## 23. Redis Cluster and Operational Scope

Redis Streams are standard Redis keys, so each Stream belongs to one hash slot. Operations such as:

```redis
XREADGROUP GROUP orders-workers worker-A STREAMS orders-stream >
XACK orders-stream orders-workers <id>
XPENDING orders-stream orders-workers
XAUTOCLAIM orders-stream orders-workers worker-B 60000 0-0
```

each operate on a single Stream key in these examples, routing cleanly to the node owning that key's slot.

However:

- `XREAD`/`XREADGROUP` across multiple Stream keys in different hash slots can violate Redis Cluster multi-key limits.
- Transactions or scripts updating both a DLQ Stream and state keys must verify **whether all keys share the same hash slot**.
- Do not expect Redis Cluster to provide atomic transactions across different primaries.
- Resharding/failover and connection errors can affect ACK calls. If it is uncertain whether an ACK succeeded, check state and rely on idempotency instead of blindly retrying side effects.

You can design hash tags for the same slot when atomicity across two keys is genuinely needed:

```text
orders:{tenant-7}:stream
orders:{tenant-7}:dlq
```

However, overly broad tenant hash tags can create hot slots. Balance transaction scope against load distribution.

## 24. Common Failure Scenarios

### 24.1. “Processed already, yet `XPENDING` still shows entries”

The application may not have called `XACK`, may have passed the wrong group/ID, hit an ACK connection error, or the ACK has not reached Redis. Check the ACK return value, Stream name, group, and original Redis ID—do not substitute a business ID.

### 24.2. “All new messages are processed, yet pending does not shrink”

`XREADGROUP ... >` still delivers new messages while old entries sit idle. A recovery worker is needed to scan pending entries and conditionally ACK after processing.

### 24.3. “New worker does not re-read messages left by the old worker”

Reading history with `0` only returns pending entries of the calling consumer name. Use `XCLAIM` or `XAUTOCLAIM` to transfer ownership from the old consumer.

### 24.4. “A message was processed twice”

Business work may have finished and the consumer crashed before ACK, or the entry was claimed while the old worker was still running. Add idempotency and tune `min-idle-time` rather than concluding Redis Streams violated your desired semantics.

### 24.5. “ACK made messages disappear from `XRANGE`”

`XACK` does not delete payloads; if entries are gone from the Stream, `XDEL`, `XTRIM`, retention policies, or another app acted on it. Investigate what is cleaning up the Stream.

### 24.6. “`XPENDING` spiked after a new deployment”

The handler may be hitting serializer/schema errors, loaders may be slow, consumers may fail to ACK, or recovery may be missing. Inspect logs by message ID, delivery count, and oldest idle time; do not rush to clear the PEL just to make metrics look clean.

### 24.7. “`XAUTOCLAIM` returns no messages even though pending entries exist”

Entries may not have been idle long enough, the cursor has not scanned the relevant region yet, another consumer already claimed them, or payloads were trimmed. Check `XPENDING`, `min-idle-time`, and the cursor.

### 24.8. “Redis Stream keeps growing even though pending is 0”

ACK does not delete Stream entries. Configure retention aligned with all consumer groups and replay needs.

### 24.9. “Running multiple workers, yet only one worker has pending entries”

New-entry distribution depends on active `XREADGROUP` requests, batch sizes, processing speed, and consumer names. Redis does not promise strict round-robin fairness in all cases. Inspect polling/concurrency rather than just PEL counts.

### 24.10. “Read with `NOACK`, so recovery is impossible”

That is the design of `NOACK`, not a PEL bug. If you want pending tracking and retries, do not use `NOACK`.

## 25. Designing a Complete Worker Architecture

A suggested architecture:

```text
                     Redis Stream
                         |
               XREADGROUP / consumer group
                         |
         +---------------+---------------+
         |               |               |
      Worker A         Worker B        Worker C
         |               |               |
       process          process         process
         |               |               |
       XACK             XACK            XACK
                         |
                 Pending entries
                         |
                    Recovery job
                  XPENDING/XAUTOCLAIM
                         |
                 Retry idempotently
                         |
                   Success -> XACK
                   Failure -> DLQ policy
```

### 25.1. Role of Normal Workers

- Receive new messages (`>`).
- Validate payload/schema.
- Process idempotently.
- ACK upon success.
- Log errors clearly without swallowing context.
- Enforce concurrency limits and graceful shutdown.

### 25.2. Role of the Recovery Worker

- Observe idle pending entries.
- Claim conditionally with an appropriate `min-idle-time`.
- Reprocess using the same idempotent logic.
- Record retry and claim count metrics.
- Move to DLQ when retry policy limits are exceeded.
- Avoid causing retry storms or contention with normal workers.

### 25.3. Role of the Retention Manager

- Bound Stream data by time or length with clear justification.
- Account for the slowest group, longest pending entry, and replay needs.
- Avoid trimming payloads needed for retries.
- Monitor RAM and entry volume.
- Clean up stale consumers/groups through controlled operational procedures; never delete groups just to lower pending metrics.

### 25.4. Role of Monitoring

- Alert when oldest pending idle time exceeds thresholds.
- Alert when pending count rises steadily while ACK throughput is low.
- Track successfully processed message rate alongside incoming rate.
- Separate delivery lag from unacknowledged pending counts.
- Monitor DLQ size, ACK errors, claim errors, and handler latency.

## 26. Practice Labs

### Lab 1 — Observing the PEL Before and After ACK

1. Create a group with `XGROUP CREATE lab:orders lab-workers 0 MKSTREAM`.
2. Add three messages with `XADD`.
3. Call `XREADGROUP GROUP lab-workers worker-A COUNT 2 STREAMS lab:orders >`.
4. Call `XPENDING lab:orders lab-workers` and observe the count.
5. ACK one processed ID.
6. Call `XPENDING` again.
7. Use `XRANGE lab:orders - + COUNT 10` to confirm original entries may still remain.

Explain the difference between reducing pending count and deleting entries.

### Lab 2 — Consumer Crash and Recovery

1. Have `worker-A` read a message without ACKing it.
2. Stop `worker-A`.
3. Have `worker-B` read with `XREADGROUP ... >`.
4. Explain why `worker-B` does not automatically receive `worker-A`'s pending message.
5. Once idle long enough, call `XAUTOCLAIM` or `XCLAIM` to transfer ownership.
6. ACK after completion.
7. Inspect owner and delivery count with `XPENDING`.

### Lab 3 — Reading History of the Same Consumer

1. Leave `worker-A` with two pending messages.
2. Call `XREADGROUP GROUP lab-workers worker-A STREAMS lab:orders 0`.
3. Compare with `XREADGROUP ... >`.
4. Introduce `worker-B` and call with offset `0`.
5. Explain the difference between a consumer's own pending history and group-wide pending entries.

### Lab 4 — Two Independent Groups

Create `business-group` and `audit-group` on the same Stream. Have each group read the same entry via separate consumers. ACK in `business-group` and inspect `XPENDING` in both groups. Explain why one group's ACK does not substitute for the other group's ACK.

### Lab 5 — Trying `NOACK`

Read an entry with `XREADGROUP ... NOACK` and inspect the PEL. Compare with an entry read normally. Analyze what happens if the worker crashes after receiving a message under `NOACK`.

### Lab 6 — ACK Failure After Database Success

Simulate the logic:

```text
Process E:
    UPDATE database
    COMMIT
    crash before XACK
```

Then recover E. Propose a uniqueness key by `eventId` within the same database transaction to prevent side effects from being applied twice.

### Lab 7 — Poison Message and DLQ

Create a message with a malformed payload. Design the flow:

```text
delivery 1 -> failed
delivery 2 -> failed
delivery 3 -> failed
write DLQ -> ACK original
```

Explain how to handle a case where the DLQ write succeeds but ACK times out. A stable ID is needed so duplicate error records are not created on retry.

### Lab 8 — Retention and Pending Entries

Create a group with pending messages, then use `XTRIM` in a test environment to remove old payloads. Observe looking up entries by ID and running recovery. Answer: Why cannot the PEL serve as a recoverable payload backup once the Stream has been trimmed?

## 27. Self-Assessment Questions

1. Does an entry added via `XADD` enter the PEL immediately?
2. Why does `XREADGROUP ... >` not automatically return already-pending entries?
3. What information does the PEL track besides Stream ID?
4. How does the `XPENDING` summary differ from the range form?
5. What data does `XACK` delete and what data does it leave untouched?
6. Why can a message ACKed in group A still remain pending in group B?
7. Does `XREADGROUP ... 0` fetch pending entries of another consumer?
8. When should you use `XCLAIM`, and when `XAUTOCLAIM`?
9. Why can a `min-idle-time` that is too low cause duplicate processing?
10. Why does the order “business commit -> ACK” still require idempotency?
11. How does `NOACK` change recovery capability?
12. Why does a pending count of 0 not mean the Stream is empty?
13. How can a poison message hurt throughput?
14. If the Stream is trimmed while the PEL still holds entries, what problem can recovery encounter?
15. How do group lag and pending count describe two different kinds of backlog?

## 28. Summary Notes

- **The PEL is the list of entries delivered by a consumer group but not yet ACKed**, storing metadata about ownership, idle time, and delivery count.
- `XADD` writes entries to the Stream; `XREADGROUP ... >` delivers new entries to the group and places them in the PEL unless `NOACK` is specified.
- **`XACK` removes the ID from the group's PEL; it does not delete the payload from the Stream.**
- `XPENDING` reports pending count, owner, idle time, and delivery count for monitoring and recovery.
- `XREADGROUP ... 0` reads pending history for **that same consumer name**; to move pending entries to another consumer, use `XCLAIM` or `XAUTOCLAIM`.
- Messages are not automatically reprocessed by another consumer just because an old worker died; applications need a recovery worker and retry policy.
- **ACKing after successful processing** is generally safer than ACKing beforehand, yet duplicates can still happen if the business commit succeeds and ACK fails.
- Practical at-least-once processing requires **idempotent handlers**; exactly-once cannot be inferred from Redis Streams and the PEL alone.
- `NOACK` disables pending tracking, trading away recovery capability.
- Stream retention must be sized alongside the PEL and the slowest group; `XTRIM` or `XDEL` does not replace `XACK`.
- Poison messages need bounded retries, a DLQ, logging, and escalation rather than infinite loops.
- In Spring Data Redis, `StreamOperations` and listener containers help read Streams; ACK timing must match the boundary where business completion is durable.

### Official References

- [Redis — Introduction to Streams](https://redis.io/docs/latest/develop/data-types/streams/)
- [Redis — XREADGROUP](https://redis.io/docs/latest/commands/xreadgroup/)
- [Redis — XPENDING](https://redis.io/docs/latest/commands/xpending/)
- [Redis — XACK](https://redis.io/docs/latest/commands/xack/)
- [Redis — XCLAIM](https://redis.io/docs/latest/commands/xclaim/)
- [Redis — XAUTOCLAIM](https://redis.io/docs/latest/commands/xautoclaim/)
- [Redis — XGROUP CREATE](https://redis.io/docs/latest/commands/xgroup-create/)
- [Redis — XINFO GROUPS](https://redis.io/docs/latest/commands/xinfo-groups/)
- [Redis — XTRIM](https://redis.io/docs/latest/commands/xtrim/)
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html)
- [Spring Data Redis — Stream Processing](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html)
