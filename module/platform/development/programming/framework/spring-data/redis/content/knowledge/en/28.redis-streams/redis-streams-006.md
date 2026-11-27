# Distinguishing Processing Acknowledgment from Deleting a Record from a Stream

## 1. One Message, Two Different Lifecycles

Suppose a Spring Boot application uses **Spring Data Redis Streams** to process order events. When a user pays, the service publishes a record:

```redis
XADD orders:events * eventType order.paid orderId O-42
```

A consumer in the `billing` group reads the event and records the payment. Next, the application must decide:

- After processing succeeds, should it **acknowledge** to Redis using `XACK`?
- Or must it **delete the record** from the Stream using `XDEL`?
- Are both needed, and if both are used, does order matter?

The core point is that **processing acknowledgment and deleting data are two independent actions**:

- **`XACK`** confirms that a record has been processed within **one specific consumer group**. It removes the reference to that record from that group's **Pending Entries List (PEL)**. **The original record remains in the Stream**.
- **`XDEL`** deletes the record's content from the **Stream**. This operation affects shared data that multiple consumer groups may need. **It is not equivalent to calling `XACK` for every group**, and under traditional mechanics, references to the deleted ID can still remain in the PEL.

```text
                          Redis Stream
                    orders:events (original record)
                    +-------------------------+
                    | 1700000000000-0         |
                    | orderId=O-42            |
                    +------------+------------+
                                 |
                   +-------------+--------------+
                   |                            |
                   v                            v
           Consumer group A              Consumer group B
             "billing"                      "analytics"
                   |                            |
           Pending Entries List          Pending Entries List
                   |                            |
         XACK in group A                 Not finished yet
                   |                            |
              PEL A: removed             PEL B: may remain
                   |
                   +--- Record still in Redis Stream ---+

XDEL deletes the original record in the Stream, not just marking group A.
```

**Operational principle:** consumers should call `XACK` **after business processing succeeds**; deleting or trimming the Stream is a separate **data retention policy** that must account for all consumer groups and replay needs.

This lesson belongs to the **Redis Streams** chapter of Spring Data Redis and focuses on distinguishing these two concepts, the message processing workflow, failure scenarios, and data management when a Stream has multiple consumer groups.

## 2. Understanding Redis Stream and Consumer Group Structure

### 2.1. A Stream Holds Records with IDs

A Redis Stream is a data structure composed of entries ordered by ID. Each entry has an ID and field-value pairs.

Example:

```redis
XADD orders:events * type order.paid orderId O-42 amount 250000
```

Redis returns an ID, for example:

```text
"1700000000000-0"
```

The actual ID assigned by Redis may differ. To view records in the Stream:

```redis
XRANGE orders:events - +
```

To count the records currently remaining in the Stream:

```redis
XLEN orders:events
```

`XRANGE` reads the Stream's source data, while `XLEN` measures the number of entries currently retained. Neither operation **tells you what a specific consumer group has finished processing**.

### 2.2. Consumer Groups Track Delivery

You can create a consumer group:

```redis
XGROUP CREATE orders:events billing 0 MKSTREAM
```

This creates the `billing` group. `MKSTREAM` creates an empty Stream if it does not yet exist; starting position `0` lets the group read existing older entries if present. If `$` is used when creating the group, the group normally starts from the end of the Stream and only receives entries added afterwards.

A consumer fetches new messages:

```redis
XREADGROUP GROUP billing billing-1 COUNT 1 STREAMS orders:events >
```

`>` requests messages never yet delivered to the group. When an entry is delivered via consumer group mechanics, Redis records it in the **Pending Entries List (PEL)** until acknowledged or handled by a related mechanism.

### 2.3. The PEL Stores Confirmation State, Not a Full Copy of the Payload

The PEL holds delivery-management information such as:

- ID of the record awaiting acknowledgment.
- Consumer currently owning processing.
- Elapsed time since the most recent delivery (*idle time*).
- Number of times delivered (*delivery count*).

The entry's field/value content itself resides in the Stream. The PEL is not a full backup copy capable of restoring content deleted from the Stream.

Two different sources of truth:

| Question | Where to check |
|---|---|
| Is the entry still in the Stream? | `XRANGE`, `XREVRANGE`, `XLEN` |
| Which group received it without acknowledging? | `XPENDING`, `XINFO GROUPS` |
| Which consumer owns a pending ID? | Detailed `XPENDING`, `XINFO CONSUMERS` |
| Has an ID been acknowledged by the current group? | The group's PEL no longer has the ID after a successful `XACK` |
| Has business work been processed in the database? | Business/idempotency state in the authoritative system |

**Present in the Stream** and **still pending** are two completely different conditions.

## 3. What Does `XACK` Actually Do?

Redis syntax:

```redis
XACK key group id [id ...]
```

Example:

```redis
XACK orders:events billing 1700000000000-0
```

Meaning: within consumer group `billing`, mark the ID above as acknowledged by removing it from that group's PEL.

If an ID was pending and is successfully acknowledged, the command usually returns:

```text
(integer) 1
```

If the ID is not in the group's PEL or was already acknowledged earlier, the result may be `0`. That **does not prove the record was deleted from the Stream**.

### 3.1. After `XACK`, the Record Remains in the Stream

Example:

```redis
XACK orders:events billing 1700000000000-0
XRANGE orders:events - +
XLEN orders:events
```

After `XACK`, `XRANGE` can still display the processed record and `XLEN` does not drop solely because of the ACK command.

Reason: the Stream holds entry history; the consumer group is a delivery-tracking state layer. `XACK` operates on the **group's PEL**, not on Stream contents.

### 3.2. After `XACK`, the Entry Is No Longer Pending in That Group

Check:

```redis
XPENDING orders:events billing
```

Once all entries are ACKed, the group's total pending count can return to `0`.

This is useful because:

- Redis no longer considers the entry unacknowledged work for the group.
- Other consumers do not need to reclaim that entry as unfinished group work.
- Related PEL metadata is freed.
- The system can distinguish confirmed work from work needing retry.

### 3.3. `XACK` Does Not Mean “Exactly-Once Processing”

A message can be processed successfully and then the program dies **before sending `XACK`**:

```text
Consumer reads entry
        |
        v
Database write succeeds
        |
        v
Application stops
        |
        XACK was not sent
        |
        v
Entry stays pending and may be redelivered
```

When the message is reprocessed, without deduplication, the business effect can run twice.

`XACK` is an acknowledgment at the **consumer group** level, not an atomic transaction across Redis and a database, HTTP API, or payment system.

## 4. What Does `XDEL` Actually Do?

Redis syntax:

```redis
XDEL key id [id ...]
```

Example:

```redis
XDEL orders:events 1700000000000-0
```

This command deletes the **entry with the specified ID** from the Stream's contents. If the entry existed, Redis may return `1` as the number of deleted entries.

After deletion:

```redis
XRANGE orders:events - +
XLEN orders:events
```

`XRANGE` no longer shows the deleted entry, and `XLEN` decreases by the number of entries actually removed from the Stream.

### 4.1. `XDEL` Is Not `XACK`

`XDEL` takes no consumer group parameter:

```text
XACK orders:events billing <ID>
                    ^^^^^^^
               Group to acknowledge

XDEL orders:events <ID>
       No group name
```

Thus `XDEL` cannot mean “finished processing in the `billing` group”. It acts on the shared Stream record, not on one group's acknowledgment state.

In traditional Stream mechanics, if an ID has already been delivered and is still pending, **deleting the entry with `XDEL` does not automatically clean up every reference to that ID in the PEL**. This creates a state where the PEL holds a reference to a record with no payload left.

### 4.2. What Happens If `XDEL` Runs Before `XACK`?

Suppose:

```text
Stream:    entry E exists
PEL A:     E is pending
```

Another process calls:

```redis
XDEL orders:events <E>
```

The state can become:

```text
Stream:    entry E is gone
PEL A:     still holds reference to E
```

When the consumer tries to re-read its own pending entries, it may see the ID without recovering the original fields/values. Redis 7.0+ can clean up PEL references to deleted entries during certain reclaim operations such as `XAUTOCLAIM`, yet that **does not mean `XDEL` auto-ACKs and clears all pending entries**.

If a job needs the message content to retry, deleting the payload before all necessary consumers finish risks losing the ability to reprocess.

### 4.3. Does `XDEL` Delete the Entire Stream Key?

Do not confuse **deleting one entry** with **deleting the Stream key**:

```redis
XDEL orders:events <ID>
```

targets only the entry with that ID.

Whereas:

```redis
DEL orders:events
```

deletes the **entire Stream key** along with its data and related metadata. This is a very different action that can wipe out the entire Stream history and its consumer groups.

## 5. Comparison Table: `XACK` vs. `XDEL`

| Criterion | `XACK` | `XDEL` |
|---|---|---|
| Purpose | Confirm processing within a consumer group | Delete entry from the Stream |
| Syntax | `XACK stream group id` | `XDEL stream id` |
| Requires group name? | **Yes** | No |
| Effect on specified group's PEL | Removes the acknowledged pending reference | Not an ACK operation |
| Effect on entry payload | **Preserved** | **Removed from Stream** |
| Effect on other groups | Does not ACK for other groups | Other groups can lose payload needed for processing |
| `XRANGE` afterwards | Can still view the entry | Deleted entry is gone |
| `XLEN` afterwards | Does not drop from ACK | Can drop |
| `XPENDING` for processing group | Decreases when ACK succeeds | Pending reference may remain |
| When to use? | **After business processing succeeds** | When retention policy permits deletion |
| Complete deduplication solution? | No | No |
| Creates a transaction with SQL? | No | No |

**In short:** `XACK` answers “does this group still need to retry this entry?”; `XDEL` answers “does this entry still remain in the Stream data?”.

## 6. Redis CLI Practice: ACK Without Deleting the Entry

Run this on a development Redis instance. Use an isolated namespace to avoid affecting real data.

### Step 1: Create a Group

```redis
XGROUP CREATE demo:orders:events demo-billing 0 MKSTREAM
```

Run this once when the group does not exist yet. Running it again yields `BUSYGROUP`; that signals the group already exists—do not automatically delete and recreate the group when encountering this error.

### Step 2: Add an Entry

```redis
XADD demo:orders:events * type order.paid orderId O-42 amount 250000
```

Suppose Redis returns ID:

```text
1700000000000-0
```

In the following commands, **replace `<ID>` with the actual ID returned by `XADD`**. The number above is illustrative only.

### Step 3: Consumer Reads the New Message

```redis
XREADGROUP GROUP demo-billing bill-1 COUNT 1 STREAMS demo:orders:events >
```

Redis returns the message and ID. Because the message was delivered via a consumer group, it becomes pending until acknowledged.

### Step 4: Inspect the PEL

```redis
XPENDING demo:orders:events demo-billing
```

The output should show 1 pending entry. To inspect a specific ID range in detail:

```redis
XPENDING demo:orders:events demo-billing - + 10
```

The output includes the ID, owning consumer, idle time, and delivery count.

### Step 5: `XACK` After Processing Succeeds

```redis
XACK demo:orders:events demo-billing <ID>
```

If the ID was pending, the result is normally `1`.

### Step 6: Compare States

```redis
XPENDING demo:orders:events demo-billing
XRANGE demo:orders:events - +
XLEN demo:orders:events
```

What to observe:

- Total pending in `demo-billing` drops to 0 if no other entries exist.
- Record `<ID>` still appears in `XRANGE`.
- `XLEN` still counts that entry.

Thus you can verify for yourself that **ACK does not delete the record from the Stream**.

### Step 7: Intentionally Delete the Original Data

Only in a lab environment, after finishing observations:

```redis
XDEL demo:orders:events <ID>
XRANGE demo:orders:events - +
XLEN demo:orders:events
```

Now record `<ID>` is no longer displayed. This action is different from `XACK` in Step 5.

## 7. Multiple Consumer Groups Needing the Same Entry

One Stream can serve independent groups:

```text
                      orders:events
                      +-----------+
                      | Event E   |
                      +-----+-----+
                            |
                +-----------+------------+
                |                        |
                v                        v
           Group billing             Group analytics
           Record payment           Aggregate reports
                |                        |
                v                        v
             XACK E                 Has not read E
                |                        |
            PEL billing = 0          Not finished yet
                |
                +------- Entry E is still needed for analytics
```

`XACK` in group `billing` **does not acknowledge for** group `analytics`. Each group has its own delivery progress and PEL.

### 7.1. Creating Two Groups and Reading Independently

Redis CLI example:

```redis
XGROUP CREATE demo:multi:orders billing 0 MKSTREAM
XGROUP CREATE demo:multi:orders analytics 0

XADD demo:multi:orders * type order.paid orderId O-42
```

Save the ID returned by `XADD`.

A consumer in `billing` reads:

```redis
XREADGROUP GROUP billing bill-1 COUNT 1 STREAMS demo:multi:orders >
```

A consumer in `analytics` can also read the same entry:

```redis
XREADGROUP GROUP analytics analytics-1 COUNT 1 STREAMS demo:multi:orders >
```

The `billing` group finishes first:

```redis
XACK demo:multi:orders billing <ID>
XPENDING demo:multi:orders billing
XPENDING demo:multi:orders analytics
```

Expected state: pending in `billing` is cleared, while `analytics` still has a pending entry because it has not ACKed.

If at this moment someone calls:

```redis
XDEL demo:multi:orders <ID>
```

the original payload is deleted even though `analytics` still needs the data to process or retry. This is a classic example of **deleting data too early**.

### 7.2. Rules When Multiple Groups Exist

Do not let a single consumer group arbitrarily delete an entry immediately after it finishes processing if:

- Other groups also read that Stream.
- A group is temporarily offline or processing slowly.
- Data must be kept for auditing or reprocessing.
- The Stream has a retention SLA over a time window.

In real designs, usually **each consumer only handles `XACK` for its own group**. A separate retention component decides when entries can be trimmed/deleted per Stream-wide policy.

## 8. Success, Failure, and When to ACK

### 8.1. Recommended Sequence

A worker receiving a payment event:

```text
XREADGROUP
     |
     v
Receive entry E, Redis places E in PEL
     |
     v
Validate and process business logic
     |
     +---- Processing error ----> Do not ACK
     |                              |
     |                              v
     |                          E stays pending
     |                          for retry/reclaim
     |
     v
Record business success
     |
     v
XACK E for current group
     |
     v
Finish processing
```

**Only ACK after the required side effects have completed** per the business boundary. If the requirement is a database write, verify whether the database transaction has committed.

### 8.2. ACKing Before Processing Is Dangerous

If code does this:

```text
XREADGROUP -> XACK -> call PaymentService -> PaymentService fails
```

the entry has left the PEL. Redis no longer tracks that entry as pending group work, and standard PEL-based retry mechanisms will not pick it up again. The payload may still be in the Stream, yet the application would need a separate recovery process to detect and process it.

Therefore, do not use **auto-ack on receipt** if tasks can fail and must be retried via the PEL.

### 8.3. Processing Succeeded Without ACK

The opposite case:

```text
XREADGROUP -> database write succeeds -> crash before XACK
```

Redis keeps the entry in the PEL. After recovery, the entry can be reprocessed.

This is why workers need **idempotency**—for example, storing processed `eventId` values in the database with a unique constraint and applying business effects in the same transaction.

### 8.4. Typical Failure Windows

| Failure timing | Observable Redis state | Handling approach |
|---|---|---|
| Crash before receiving entry | Entry not yet delivered to group | Another consumer can read the new message |
| Crash after `XREADGROUP`, before business work | Pending | Reclaim/retry when eligible |
| Business logic error | Pending if not ACKed | Bounded retries or error handling |
| Database commits, crash before ACK | Pending even though effect succeeded | **Idempotent** retry, then ACK |
| ACK succeeds but app misses response | PEL may already be cleared | Must verify; do not assume ACK definitely failed |
| `XDEL` before another consumer processes | Payload gone | Risk of losing reprocessing capability |
| Trim deletes a still-pending entry | PEL may retain reference | Must handle dangling references |

**No single `XACK` operation guarantees “exactly once” across Redis and another data system.** Exactly-once at the business-effect level must be built from transactions and appropriate idempotency mechanisms.

## 9. Pending Entries List and Recovering Failed Consumers

### 9.1. `XPENDING`: Knowing What Is Waiting

Reading via a consumer group puts entries in the PEL until ACKed. Check:

```redis
XPENDING orders:events billing
```

To view details:

```redis
XPENDING orders:events billing - + 20
```

Useful information:

- Total pending entries.
- Range of IDs with pending entries.
- Consumers holding pending entries.
- Idle time and delivery count.

Do not treat “pending = 0” as meaning the Stream is empty. It only describes the acknowledgment state of **the queried group**.

### 9.2. Re-Reading a Consumer's Own Pending Entries

A consumer uses `>` to fetch **new entries never delivered to the group**:

```redis
XREADGROUP GROUP billing bill-1 COUNT 10 STREAMS orders:events >
```

To read **pending history of that same consumer**, use a specific ID such as `0`:

```redis
XREADGROUP GROUP billing bill-1 COUNT 10 STREAMS orders:events 0
```

Two distinct options:

- `>`: stream of new work.
- `0`: inspects pending entries previously delivered to **that consumer** at the corresponding read position.

Continuously polling `>` **does not automatically re-fetch old pending entries**. This property is vital when designing workers that restart after a failure.

### 9.3. `XCLAIM` and `XAUTOCLAIM`

If consumer `bill-1` died while holding many pending entries, another consumer can take over processing via claiming, for instance:

```redis
XAUTOCLAIM orders:events billing bill-2 60000 0-0 COUNT 10
```

This example finds pending entries with at least 60 seconds of idle time and transfers ownership to `bill-2`, per `XAUTOCLAIM` mechanics.

Once claimed, `bill-2` reprocesses business logic, checks idempotency, and calls **`XACK`** upon completion. Do not use `XDEL` to “quickly clear” a pending entry, because that destroys the payload workers need for retries.

Design considerations:

- The `min-idle-time` threshold must match normal processing durations.
- Retries must have a max attempt cap or a policy routing to an error stream.
- With parallel processing, multiple workers must not concurrently apply non-idempotent side effects.
- Monitor long-lived pending entries and delivery counts.
- When reclaiming an entry whose payload was deleted, handle the **missing content** case; in Redis 7.0+, `XAUTOCLAIM` also has mechanics to clean up some dangling PEL references when encountering deleted entries.

### 9.4. Why `XDEL` Is Not a Tool for Resolving Pending Entries

A pending entry means “the group received it but has not confirmed completion”. To close out the group's processing responsibility:

1. Execute the business work or handle failure per policy.
2. Only when eligible, call `XACK` (or equivalent ACK mechanism).

`XDEL` only deletes the shared payload without verifying business completion. Thus `XDEL` is not a substitute for ACK or retries.

## 10. Spring Data Redis: ACK and DELETE Are Two Different APIs

Spring Data Redis exposes `StreamOperations` via `RedisTemplate.opsForStream()`.

### 10.1. ACKing a Record

In Spring Data Redis, you can call:

```java
import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.core.StringRedisTemplate;

public class StreamAckExample {

    private final StringRedisTemplate redis;

    public StreamAckExample(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long acknowledge(String recordId) {
        return redis.opsForStream().acknowledge(
                "orders:events",
                "billing",
                RecordId.of(recordId)
        );
    }
}
```

Semantically equivalent to:

```redis
XACK orders:events billing <ID>
```

The `acknowledge(...)` method takes a group name because ACK belongs to **one consumer group**.

If the `Long` result is `1`, one corresponding pending reference was ACKed. Returning `0` can happen because the ID was no longer in the PEL or was already ACKed earlier; do not infer that the payload was deleted.

### 10.2. Deleting a Record from a Stream

Spring Data Redis also provides `delete(...)` on `StreamOperations`:

```java
public Long deleteFromStream(String recordId) {
    return redis.opsForStream().delete(
            "orders:events",
            RecordId.of(recordId)
    );
}
```

Semantically equivalent to:

```redis
XDEL orders:events <ID>
```

There is no group name because this mutates **shared Stream data**.

The two Java methods have similar return types yet **do not share the same effect**. Do not merge `acknowledge(...)` and `delete(...)` into a single `complete(...)` method that blurs processing policy with retention policy.

### 10.3. A Listener That ACKs Only After Processing Succeeds

Spring Data Redis example with `StreamListener`:

```java
package com.example.redis.stream;

import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.stream.StreamListener;
import org.springframework.stereotype.Component;

@Component
public class BillingStreamListener
        implements StreamListener<String, MapRecord<String, String, String>> {

    private static final String STREAM = "orders:events";
    private static final String GROUP = "billing";

    private final StringRedisTemplate redis;
    private final BillingProcessor processor;

    public BillingStreamListener(
            StringRedisTemplate redis,
            BillingProcessor processor) {
        this.redis = redis;
        this.processor = processor;
    }

    @Override
    public void onMessage(MapRecord<String, String, String> record) {

        // Business component must use event ID or business key
        // to handle redeliveries safely.
        processor.processIdempotently(
                record.getId().getValue(),
                record.getValue()
        );

        // Only reaches here if processor does not throw
        // and required business work is complete.
        redis.opsForStream().acknowledge(
                STREAM,
                GROUP,
                record.getId()
        );

        // Do NOT delete the entry from the Stream here by default.
        // Retention policy is handled separately.
    }
}
```

Here `BillingProcessor` is an application-provided service responsible for business processing and deduplication:

```java
package com.example.redis.stream;

import java.util.Map;

public interface BillingProcessor {

    void processIdempotently(
            String streamEntryId,
            Map<String, String> fields
    );
}
```

In real systems, a business method typically uses a database transaction and a unique constraint on `streamEntryId` or `eventId` to avoid applying effects twice when a record is redelivered.

**Core idea:** do not `XACK` on the failure path. Note that exceptions in a listener can affect the subscription/container; configure retries, reclaiming, and error handlers explicitly.

### 10.4. Configuring the Container to Receive Messages by Consumer Group

Spring Data Redis provides `StreamMessageListenerContainer` for receiving messages imperatively:

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
public class BillingStreamConfiguration {

    @Bean
    public StreamMessageListenerContainer<
            String, MapRecord<String, String, String>>
    billingStreamContainer(
            RedisConnectionFactory connectionFactory,
            BillingStreamListener listener) {

        var options = StreamMessageListenerContainer
                .StreamMessageListenerContainerOptions
                .<String, MapRecord<String, String, String>>builder()
                .pollTimeout(Duration.ofSeconds(1))
                .build();

        var container = StreamMessageListenerContainer.create(
                connectionFactory,
                options
        );

        container.receive(
                Consumer.from("billing", "billing-1"),
                StreamOffset.create(
                        "orders:events",
                        ReadOffset.lastConsumed()
                ),
                listener
        );

        return container;
    }
}
```

The example assumes group `billing` **already exists** before the consumer starts—for instance, created via `XGROUP CREATE`. Do not delete and recreate the group on every application startup, as that can wipe out delivery-progress metadata.

`StreamMessageListenerContainer` has its lifecycle managed by Spring. With `receive(...)`, records **require manual ACK** after processing. With `receiveAutoAck(...)`, records are acknowledged on receipt; that is **not** a safe default policy for work needing retries after handler failure.

Depending on your Spring Data Redis version, class names and builder generics may vary slightly; use the API of your chosen version. The core APIs `opsForStream().acknowledge(...)`, `opsForStream().delete(...)`, `StreamListener`, and `StreamMessageListenerContainer` are the focus of this example.

## 11. Notes on ACK Results, Network Errors, and Idempotency

Suppose the application finishes processing and sends `XACK`. The outcome of `acknowledge(...)` can be affected by network errors:

```text
Application                     Redis
    |                             |
    | XACK E --------------------> |
    |                             | XACK succeeds
    |                             |
    |     [Connection lost before app receives response]
    |
    | Uncertain whether ACK succeeded or not
```

In this situation, never assume:

- “There was an exception, so Redis definitely did not ACK.”
- “`XACK` returned 0, so business work definitely never ran.”
- “The PEL is empty, so the database definitely committed.”

Separate **group ACK state** from **business state**. When reconciliation is needed, inspect the PEL, database state, and the application's own idempotency records.

### 11.1. A Pattern to Prevent Duplicate Processing

Suppose every event carries an immutable `eventId`, or uses the Stream entry ID as a processing identifier. In the database, maintain a table:

```text
processed_events
  event_id (UNIQUE)
  processed_at
```

At processing time:

1. Start a database transaction.
2. Attempt to insert `event_id` into the table with a unique constraint.
3. If it already exists, treat the prior business effect as completed per policy.
4. If it does not exist, execute the business operation and record the processed marker in the same transaction.
5. Commit the transaction.
6. Call `XACK` for the current group's entry.

If the application dies after step 5 and before step 6, the entry stays pending, yet the retry sees `event_id` is already recorded and skips duplicating side effects. Then the consumer can ACK.

This is a **design pattern**, not an automatic “exactly once” feature of Redis Streams. Applying it across multiple databases or external services also requires dedicated idempotency mechanisms for each side effect.

## 12. Delete by Retention Policy, Not by Each Worker's Whim

### 12.1. Why Is Retention Needed?

If every entry is only ACKed with no delete/trim mechanism, the Stream keeps all processed data. Its size grows over time:

```text
Day 1:      100,000 entries
Day 7:      700,000 entries
Day 30:   3,000,000 entries
```

Redis consumes RAM, and keeping history indefinitely is usually unnecessary for every application.

Therefore, the application should define a **retention policy**: keep at most how many entries, for how long, or delete only after mandatory groups have processed them.

### 12.2. `XTRIM` to Cap a Stream

Example:

```redis
XTRIM orders:events MAXLEN ~ 100000
```

This keeps the Stream size near 100,000 entries; `~` allows approximate trimming to optimize how Redis stores data.

You can also apply the limit when adding entries:

```redis
XADD orders:events MAXLEN ~ 100000 * type order.paid orderId O-42
```

Remember:

- `MAXLEN` caps **entry count**, not total bytes.
- `~` is approximate; actual entry count may remain higher than the threshold for a while.
- Trimming/deleting can remove payloads that slow consumers have not processed yet.
- Redis **does not automatically know** every group has processed an entry merely because it is old or beyond the count threshold.

In traditional Redis versions, trimming such as `XTRIM` can by default leave PEL references pointing to deleted entries. Thus retention must be designed alongside pending handling and group count.

### 12.3. Do Not Delete Immediately After ACK If Other Groups Exist

Unsafe sequence:

```text
Billing:   XREADGROUP -> process -> XACK -> immediate XDEL
Analytics: unread / still pending -> payload lost
```

A safer alternative:

```text
Billing:   XREADGROUP -> process -> XACK
Analytics: XREADGROUP -> process -> XACK
Retention: check shared deletion criteria -> delete/trim per policy
```

Checking eligibility can be based on:

- Progress of critical groups.
- Time window or retention ID threshold.
- History retention window for investigations.
- Legal/operational policies.
- Deletion modes aware of all groups' ACK status when supported by the Redis version.

Note: checking `XPENDING = 0` alone is not necessarily enough to confirm **all old entries were read**, because a group might not have read any entries yet and therefore have no pending items. Monitor both delivery/ACK progress and retention conditions.

## 13. Redis 8.2 and Later: `XACKDEL`, `XDELEX`, and Reference Modes

Starting in **Redis 8.2**, Streams commands add options for handling the relationship between original entries and consumer groups.

### 13.1. `XACKDEL`: Combining ACK and Conditional Deletion

Syntax:

```redis
XACKDEL key group [KEEPREF | DELREF | ACKED] IDS numids id [id ...]
```

Single-entry ID example:

```redis
XACKDEL orders:events billing ACKED IDS 1 <ID>
```

This combines ACKing in the specified group with deleting the entry according to a **reference policy**.

Important options:

| Mode | Core meaning |
|---|---|
| `KEEPREF` (default) | ACKs in the specified group and deletes the entry from the Stream, **keeping** other existing PEL references |
| `DELREF` | ACKs in the specified group, deletes the entry, and **deletes references to the entry across all groups** |
| `ACKED` | ACKs in the specified group and only deletes the entry if **all consumer groups** have read and acknowledged that entry |

**`ACKED`** is particularly worth considering when multiple groups exist: one group finishing early will not delete the payload while another group has not finished yet.

However, even `ACKED` does not turn Redis into a distributed transaction with a database. The application must still ACK after business success and still needs idempotency on retries.

### 13.2. `XDELEX`: Policy-Aware Deletion Instead of Simple `XDEL`

Redis 8.2 also adds:

```redis
XDELEX key [KEEPREF | DELREF | ACKED] IDS numids id [id ...]
```

Example:

```redis
XDELEX orders:events ACKED IDS 1 <ID>
```

With `ACKED`, Redis only deletes entries meeting the condition of having been read and acknowledged by all groups. This is a useful tool for consumer-group-aware cleanup jobs.

Distinguish:

- **`XACKDEL`**: ACKs in a **specified group**, then conditionally deletes.
- **`XDELEX`**: focuses on deleting entries with a reference policy, without taking a group to ACK a specific processing step.
- **`XDEL`**: traditional entry deletion, without the policy options of the two commands above.

### 13.3. `XTRIM` and `XADD` Also Support the New Modes

Redis 8.2 extends `KEEPREF`, `DELREF`, and `ACKED` options to trimming in `XTRIM` and `XADD`.

Example:

```redis
XTRIM orders:events ACKED MAXLEN 100000
```

The `ACKED` option tells Redis to trim only entries already acknowledged by the necessary consumer groups per command semantics, instead of arbitrarily dropping payloads still needed for processing.

Before using them, verify your Redis server version and client/Spring Data Redis version. **Do not send 8.2 commands to older Redis servers**: the server will reject the syntax. In modern Spring Data Redis, an `acknowledgeAndDelete(...)` API may exist, though naming and support level depend on library version. Projects on older versions may need to keep `acknowledge` and retention separate or plan a deliberate upgrade.

### 13.4. When Should You Avoid `DELREF`?

`DELREF` removes PEL references across **all groups**, meaning it can erase retry traces for groups that have not finished processing yet. Only use it if the business intent is to abandon that work and accept losing recovery for it.

`KEEPREF` keeps references yet can leave dangling references once the payload is deleted; `ACKED` is preferable in many situations where slow consumer groups must be protected.

Do not focus only on the word “delete” and overlook its impact on processing progress.

## 14. Common Operational Questions

### 14.1. After `XACK`, Can You Still Read the Entry with `XRANGE`?

**Yes**, if the entry has not been deleted or trimmed. `XACK` only removes the group's pending reference; it does not delete Stream contents.

### 14.2. After `XACK`, Will the Current Group Re-Receive the Entry via `XREADGROUP` with `>`?

Normally **no**. `>` fetches new entries never delivered in the group; an entry already delivered and ACKed does not become “new” again just because it remains in the Stream.

You can read Stream history with `XRANGE` or create a new group at an appropriate starting point, but those are replay mechanisms distinct from retrying ACKed group pending entries.

### 14.3. After `XDEL`, `XPENDING` Still Lists the ID—Is That a Redis Bug?

Not necessarily. Under traditional mechanics, PEL references can persist even when the original payload was deleted. Distinguish “message still pending” from “content still available to reprocess”.

To clean up, use PEL reclaim/cleanup mechanisms or newer deletion options matching your Redis version, rather than assuming `XPENDING` drops to 0 after `XDEL`.

### 14.4. Does `XACK` Returning `0` Mean the Data Was Deleted?

**No.** It usually means that ID was not removed from the PEL by that call—for example, because it was already ACKed earlier or was not pending in the specified group. Use `XRANGE`/`XLEN` to check source data if needed.

### 14.5. Does `XDEL` Returning `1` Mean Business Processing Finished?

**No.** It only reports that the entry existed and was removed from the Stream; it says nothing about whether `billing`, `analytics`, or external services completed.

### 14.6. Should You Delete an Entry Immediately Upon Successful `XACK`?

Only when **retention policy permits** and no other consumer group or replay need depends on that payload. In multi-group systems, deleting directly inside individual listeners is usually a risky design.

### 14.7. Can You Set `EXPIRE` on Individual Stream Entries?

Regular Redis TTLs apply to the **Stream key**, not individual entries. `EXPIRE orders:events 3600` can expire the **entire Stream key**, not just processed entries.

To bound entry history, use `XTRIM`, `MAXLEN`/`MINID` policies, or deletion options suited to your Redis version and business needs.

### 14.8. What If a New Consumer Group Is Created Days Later?

If the new group needs to read history, ensure retention has not already removed those entries and choose the appropriate starting offset. Just because existing groups ACKed an entry does not guarantee history is preserved forever for future groups.

Therefore, retention policies must state a clear contract on replay window and which consumer groups are protected by the system.

## 15. Inspecting the System with Redis Commands

In test environments or during incident investigation, you can run:

```redis
XINFO STREAM orders:events
XINFO GROUPS orders:events
XINFO CONSUMERS orders:events billing

XPENDING orders:events billing
XPENDING orders:events billing - + 20

XLEN orders:events
XRANGE orders:events - + COUNT 10
```

Meaning:

| Command | Primary observation |
|---|---|
| `XINFO STREAM` | Stream metadata, entry count, first/last entry details |
| `XINFO GROUPS` | Groups, progress, and group state |
| `XINFO CONSUMERS` | Consumers within a group and their pending counts |
| `XPENDING` | Unacknowledged pending entries in a group |
| `XLEN` | Number of entries retained in the Stream |
| `XRANGE` | Entry data remaining in the Stream |

Avoid repeatedly running unbounded `XRANGE stream - +` on huge Streams inside request paths just to check status. Use `COUNT`, pagination, Stream stats, and application metrics instead.

Metrics to monitor:

- **Pending count** per group.
- Age / idle time of the oldest pending entry.
- Receive, business-success, and ACK rates.
- Reclaim/retry counts and events exceeding retry limits.
- Stream entry/byte count and growth rate.
- Trimmed/deleted entry count and missing-payload rate.
- State of the slowest consumer group.
- Business errors, timeouts, and idempotent duplicate-handling counts.

A small `XLEN` alongside a large pending count can signal payloads were trimmed/deleted too early or a lifecycle bug exists. Continuously growing `XLEN` with `pending = 0` across all groups can indicate no retention policy is active.

## 16. Designing a Safe Processing Pipeline

A practical workflow can divide responsibilities across three components:

```text
            Producer
               |
               | XADD
               v
             STREAM
               |
        +------+-------+
        |              |
        v              v
    Group billing    Group analytics
        |              |
   process + ACK   process + ACK
        |              |
        +------+-------+
               |
         Retention Policy
               |
   eligible + age/limit reached
               |
      XTRIM / XDELEX / XDEL
```

### 16.1. Producer Responsibilities

- Write events with IDs, schemas, and data sufficient for processing.
- Handle publish failures and idempotency if the producer can retry.
- Do not configure trimming so short that slow consumers miss data.
- If events must never be lost, consider an outbox and suitable persistence/replication.

### 16.2. Consumer Responsibilities

- Read via a group and track pending state.
- Process idempotently.
- **ACK only after completing required business work**.
- Leave entries pending when failures require retries.
- Implement pending reclaim for entries abandoned by dead workers.
- Do not call `XDEL` simply because an ACK just succeeded.

### 16.3. Retention Responsibilities

- Know how many critical groups the system has.
- Define history retention windows and deletion criteria.
- Monitor slow groups and neglected pending entries.
- Assess the risk of deleting payloads before other groups finish.
- On Redis 8.2+, consider `ACKED` modes to prevent premature deletion.
- Test on development environments before changing trim/delete behavior.

### 16.4. What Does “Safe” Mean for Critical Data?

Redis Streams stores data in Redis alongside consumer group metadata, yet data retention also depends on cluster persistence, replication, failover, and retention configuration. Never treat “`XACK`ed” as sufficient proof of durability guarantees across multiple systems.

For payments or critical transactions, design the entire data path: producer, source database, events, consumers, deduplication, retries, monitoring, and retention policy.

## 17. Practice Exercises

### Exercise A: Verify `XACK` Does Not Reduce `XLEN`

1. Create a Stream and group using `XGROUP CREATE ... MKSTREAM`.
2. Add an entry using `XADD`.
3. Read using `XREADGROUP ... >`.
4. Inspect `XPENDING`.
5. Call `XACK`.
6. Inspect `XPENDING`, `XRANGE`, and `XLEN` again.

Expected observation: the PEL shrinks while the entry remains in the Stream.

### Exercise B: `XDEL` Before ACK

1. Create a different Stream and group from Exercise A.
2. Add and read an entry so it becomes pending.
3. Call `XDEL` while the entry is still pending.
4. Inspect `XPENDING` and `XRANGE`.
5. Use a suitable re-read/reclaim mechanism to observe the case where the ID exists in metadata without a payload.

Conclusion: `XDEL` is not an ACK operation; deleting payloads while pending creates recovery risks.

### Exercise C: Two Independent Groups

1. Create `billing` and `analytics` on the same Stream.
2. Add an entry and let both groups read it.
3. Call `XACK` only in `billing`.
4. Inspect `XPENDING` for each group.
5. Keep the entry in the Stream until `analytics` finishes processing.

Conclusion: ACK is scoped to one group; the entry payload belongs to the shared Stream.

### Exercise D: Application Error Handling

Build a consumer that simulates failing after reading. Do not ACK. Inspect pending state, then recover the consumer or reclaim via `XAUTOCLAIM` with an appropriate idle threshold. Reprocess with deduplication and ACK.

Conclusion: pending state enables retries; `XDEL` cannot replace this mechanism.

### Exercise E: Redis 8.2 and Conditional Deletion

If running Redis 8.2 or newer, try `XACKDEL ... ACKED` on a Stream with two groups. Confirm the entry is **not deleted** while the second group has not finished, then ACK in the second group and verify conditional deletion.

Do not run this exercise on older Redis versions and do not mix it with real business data.

## 18. Self-Check Questions

**Question 1.** A consumer called `XACK`. Why does `XRANGE` still show the entry?

Because `XACK` only acknowledges within a consumer group by removing the PEL reference; it does not delete the record's content in the Stream.

**Question 2.** Does `XDEL` make pending entries disappear for every group?

Not under traditional `XDEL` behavior. The command deletes the original entry; the PEL can retain references to the deleted ID. Redis 8.2 provides advanced deletion options to control those references.

**Question 3.** Group `billing` ACKed, while `analytics` has not processed yet. Should `XDEL` run immediately?

Normally no, because `analytics` may still need the payload. Separate per-group ACK from Stream-wide retention policy.

**Question 4.** Why must ACK follow database commit?

If you ACK first and business work fails, the entry may no longer be pending for retries. If the commit succeeds and the process crashes before ACK, idempotency lets it reprocess safely and then ACK.

**Question 5.** Does `pending = 0` mean the Stream is empty?

No. Pending only reports unacknowledged entries in a consumer group, not the number of entries stored in the Stream. Use `XLEN` to inspect retained entry count.

**Question 6.** Does `XREADGROUP ... >` automatically pick up old pending entries from a dead consumer?

No. `>` fetches new entries never delivered to the group. Use pending-history reads or claim/reclaim commands like `XAUTOCLAIM` depending on recovery needs.

**Question 7.** If an entry is trimmed while still pending, what can happen?

The payload is removed from the Stream while the PEL still holds the ID, preventing retries from retrieving content. Retention policies must account for all groups and pending state.

**Question 8.** What does `XACKDEL ... ACKED` in Redis 8.2+ help with?

It combines ACKing for a specified group with conditional deletion once relevant groups have read and acknowledged the entry, helping prevent premature deletion before other groups finish.

**Question 9.** Why does a successful ACK not prove every side effect happened only once?

Because the consumer may have completed processing earlier and crashed before ACK, causing the message to be redelivered. Idempotency must be designed at the business layer.

**Question 10.** What should you do when a permanently broken message must be retired?

Define an explicit error-handling policy—for example, writing to a dead-letter stream/queue as required, recording the failure reason, and ACKing only after error handoff/handling completes. Never default to `XDEL` to hide processing failures.

## 19. Key Takeaways

- **`XACK` confirms processing within a single consumer group**, removing the ID from that group's PEL without **deleting the payload** from the Redis Stream.
- **`XDEL` deletes the original entry from the Stream**, not an ACK; waiting PEL references can remain without payload for retries.
- **`XPENDING` and `XLEN` measure two different things**: unacknowledged work in a group vs. entries still retained.
- **ACK after business success**; handle errors with pending/reclaim and idempotency instead of deleting data prematurely.
- **Multiple consumer groups have independent progress**. One group ACKing does not entitle it to decide other groups no longer need the entry.
- **Retention is a separate policy**. Use `XTRIM`, conditional deletion, and slow-group monitoring; Redis 8.2+ adds `XACKDEL`, `XDELEX`, and `KEEPREF`, `DELREF`, `ACKED` modes.
- Never equate “ACK succeeded” with “exactly-once business transaction” or “data was freed from the Stream”.

### References

- [Redis — XACK](https://redis.io/docs/latest/commands/xack/).
- [Redis — XDEL](https://redis.io/docs/latest/commands/xdel/).
- [Redis — XPENDING](https://redis.io/docs/latest/commands/xpending/).
- [Redis — XREADGROUP](https://redis.io/docs/latest/commands/xreadgroup/).
- [Redis — XAUTOCLAIM](https://redis.io/docs/latest/commands/xautoclaim/).
- [Redis — XACKDEL (Redis 8.2+)](https://redis.io/docs/latest/commands/xackdel/).
- [Redis — XDELEX (Redis 8.2+)](https://redis.io/docs/latest/commands/xdelex/).
- [Redis — XTRIM](https://redis.io/docs/latest/commands/xtrim/).
- [Redis — Streams](https://redis.io/docs/latest/develop/data-types/streams/).
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html).
- [Spring Data Redis — StreamOperations API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/StreamOperations.html).
