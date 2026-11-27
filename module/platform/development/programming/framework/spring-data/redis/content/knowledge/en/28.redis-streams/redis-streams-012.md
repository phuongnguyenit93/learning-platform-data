# Demand Throttling, Pausing Consumption, and Offset Drift Risks

**Redis Streams** lets applications store events as entries with IDs and read them later. With **Spring Data Redis**, streams can be consumed via `StreamOperations`, `StreamMessageListenerContainer`, or `StreamReceiver` (reactive). However, Redis's ability to store many messages does not mean an application can receive and process them without limits.

When producers write faster than consumers process, applications need **demand throttling (backpressure)**: bounding batches, capping in-flight tasks, pausing polls when processing overloads, and resuming when capacity returns. Meanwhile, a serious risk emerges: **offset drift**, where the position considered read or consumed advances ahead of the work actually completed.

This lesson focuses on the differences between **written to the stream**, **delivered to a consumer**, and **processed successfully**; how to pause and resume safely; where events are easily lost or duplicated; and recovery workflows using consumer groups and the Pending Entries List (PEL).

## 1. Why Must Demand Be Throttled?

Suppose a producer writes 2,000 order events/second to a Redis Stream, while a consumer completes only 200 events/second because each event updates a database.

```text
Producer: 2000 events/s
         |
         v
   Redis Stream
   [1][2][3][4][5]......................
         |
         v
Consumer: 200 events/s
         |
         v
   Business handler
         |
         v
       Database
```

If the consumer keeps reading nonstop and dumping every event into an unbounded executor, it can queue tens of thousands of waiting tasks, exhausting memory, connection pools, or thread pools. When the process crashes, many tasks were received without finishing processing.

The remedy is not marking messages done to shrink the backlog, but **bounding how many entries are delivered into the application according to actual processing capacity**. When handlers slow down, reduce or pause starting new batches; undelivered entries remain in the stream as long as the retention policy allows.

Backpressure has limits: if the consumer pauses while the producer keeps writing, the backlog in Redis grows. If event creation rate stays permanently higher than total processing throughput, the backlog will not shrink on its own, even after resuming.

## 2. Concepts That Must Be Distinguished

| Concept | Meaning |
|---|---|
| **Stream ID** | Ordered ID attached to an entry created by `XADD` |
| **Read offset** | Position or rule determining which entries to fetch when reading |
| **Consumer group** | Group of consumers sharing delivery progress and pending state |
| **Last-delivered ID** | Marker Redis has delivered up to in the group; does not prove business success |
| **Pending Entries List (PEL)** | Set of entries delivered to the group but not yet `XACK`ed |
| **ACK** | Confirms an entry was processed per the consumer's business contract |
| **Demand** | Number of elements downstream is ready to accept, especially in Reactive Streams |
| **Pause** | Temporarily halting starting new read/receive batches |
| **Resume** | Continuing reads from the proper state without skipping unfinished work |
| **Retention** | Policy keeping entries in the stream, including trimming/deleting at limits |

An event inside a consumer group passes through this flow:

```text
XADD succeeds
    |
    v
Entry is stored in stream
    |
    v
XREADGROUP delivers to consumer
    |
    +------------------> PEL records delivered, unACKed
    |
    v
Business handler executes
    |
    +-- error/crash ----> still needs PEL recovery
    |
    v
Side effect succeeds
    |
    v
XACK
    |
    v
PEL no longer holds that entry
```

**`XACK` does not delete the entry from the stream.** It confirms completion for one consumer group. Stream entries remain until deleted or trimmed per policy.

If a pause occurs **before reading**, new events stay in the stream undelivered to the group. If a pause or crash occurs **after receiving and before ACK**, events normally sit in the PEL. These two categories require two different continuation paths.

## 3. `XREAD` and `XREADGROUP` Use Offsets Differently

### 3.1. Direct Reading with `XREAD`

A client can read entries with IDs greater than a specified ID:

```redis
XREAD COUNT 10 STREAMS stream:orders:v1 0-0
```

If the client saves its checkpoint as the last **completed** ID, it can resume after a restart:

```redis
XREAD COUNT 10 STREAMS stream:orders:v1 1780000000000-0
```

However, `XREAD` has no PEL and no Redis-managed ACK for business handlers. The application must store the checkpoint itself and decide when the marker may advance.

Incorrect example:

```text
Read batch: 101, 102, 103, 104, 105
    |
    v
Save checkpoint = 105 right upon receipt
    |
    v
Handler finishes 101, 102
    |
    v
JVM crashes before 103
    |
    v
Restart reads after 105
    |
    v
103, 104, 105 are skipped
```

With sequential processing, the checkpoint should advance to the **last completed** ID. With parallel processing, a safe checkpoint is the **contiguous completed** watermark, not necessarily the highest processed ID. If 105 finishes while 103 is still running, advancing the checkpoint past 103 can lose messages on restart.

### 3.2. Reading with a Consumer Group

Create the group:

```redis
XGROUP CREATE stream:orders:v1 order-workers 0 MKSTREAM
```

`0` lets the group read from existing entries; creating the group with `$` skips entries older than that point on the new-message path. Once the group exists:

```redis
XREADGROUP GROUP order-workers worker-a COUNT 10 BLOCK 2000 STREAMS stream:orders:v1 >
```

`>` requests new entries not yet distributed by the group per consumer-group rules. Delivered entries stay in the PEL until ACKed:

```redis
XACK stream:orders:v1 order-workers 1780000000000-0
```

Thanks to the PEL, a delivered-but-unACKed entry remains recoverable after a crash, provided the stream payload has not been deleted/trimmed. However, **reading `>` after a restart does not automatically re-read old PEL entries**. A consumer needs a dedicated pending-recovery flow rather than treating the new-messages path as the entirety of remaining work.

## 4. The Risk of `ReadOffset.latest()`: Skipping Data During Non-Polling Gaps

In Spring Data Redis, `ReadOffset` specifies how the read position is determined. A choice prone to errors during pauses is `ReadOffset.latest()`.

Suppose a consumer reads from “latest” on each poll:

```text
T0: Stream already has entry 100-0.
T1: Poll from latest and receive entry 101-0.
T2: Downstream demand = 0; consumer stops polling.
T3: Producer writes entries 102-0 and 103-0.
T4: Downstream has demand; new poll starts from latest again.
T5: Producer writes entry 104-0.
```

If at T4 “latest” corresponds to `103-0`, the consumer may only receive `104-0` and **skip `102-0` and `103-0`** on its subscription. Those entries may still sit in Redis, yet the new read marker jumped right past them.

| Offset type | Typical meaning | Watch out for |
|---|---|---|
| `ReadOffset.latest()` | Follows entries arriving after the latest marker | Easily misses entries between polls or when demand pauses |
| `ReadOffset.from(id)` | Fetches entries with IDs greater than a known marker | Marker must reflect genuinely accepted progress |
| `ReadOffset.from("0-0")` | Reads from the start of retained stream data in direct mode | May replay history if no checkpoint exists |
| `ReadOffset.lastConsumed()` in consumer group | Uses the group's delivery progress to receive new messages | Does not resolve delivered-but-unACKed PEL entries |
| `ReadOffset.lastConsumed()` in direct read | Uses consumed marker per receiver mechanics | Understand whether the marker updates on receipt or after handler completion |

**Do not treat `latest` as synonymous with “resume from the exact spot where we stopped”** when events must not be lost. For critical streams, use consumer groups with recovery or durable checkpoints tied to processing progress.

## 5. Reactive Demand Alone Does Not Solve Reliability

In Reactor, downstream can request a specific number of items. When demand reaches zero, `StreamReceiver` can pause polling. However, two distinct questions must be answered:

1. **When is downstream ready to accept more?**
2. **Once ready, from which offset will Redis resume reading?**

```text
Reactive downstream requests N entries
                  |
                  v
      StreamReceiver polls Redis
                  |
                  v
       Emits entries into Flux
                  |
                  v
             Demand = 0
                  |
      Receiver may pause polling
                  |
             Producer XADDs more
                  |
                  v
         Demand rises again
                  |
                  v
      Resumes polling from configured offset
           |
           +-- latest: may skip entries between polls
           |
           +-- proper checkpoint/group:
               has a path to resume retained entries
```

Moreover, **an entry emitted into a `Flux` has not necessarily finished business processing successfully**. If downstream uses async handlers and cancels the subscription while handlers are running, “emitted” is not a safe checkpoint.

### 5.1. Concurrency Must Be Bounded

With Reactor, a pipeline can be structured conceptually as:

```java
source.concatMap(record ->
        handleBusiness(record)
                .then(acknowledgeAfterSuccess(record)));
```

This is an **illustrative flow pattern**, not a complete Spring Data Redis API call: `handleBusiness` and `acknowledgeAfterSuccess` are application-defined reactive functions.

`concatMap` processes items in input order, reducing concurrent side-effect hazards. `flatMap` can boost throughput with bounded concurrency, though messages may complete and ACK out of order. If business logic requires strict per-order sequencing, add per-aggregate serialization or corresponding work partitioning.

### 5.2. Auto-ACK Is Not Side-Effect Commit

Spring Data Redis offers variants supporting auto-ACK in reactive receivers. When using auto-ACK, understand exact ACK timing per the API contract—never assume it waits for all asynchronous business-handler work to commit. If a crash happens after auto-ACK and before business results persist, the PEL no longer holds the entry for retries.

**For workflows that must not drop events, prefer explicit ACK after handler success**, paired with idempotency for the window where commit succeeds before ACK.

## 6. Backpressure Requires Controlling In-Flight Counts

Common incidents stem not only from `ReadOffset` but also from how consumers use thread pools.

Conceptually flawed:

```java
for (MapRecord<String, Object, Object> record : records) {
    executor.submit(() -> handler.handle(record.getValue()));

    // Dangerous: only queued the task.
    redis.opsForStream().acknowledge(
            STREAM, GROUP, record.getId());
}
```

If a crash occurs after ACK and before the worker executes the task, the group already marked the event complete. After restart, the normal `>` read path will not redeliver that event.

Better flow:

```text
Free processing slot available?
         |
         v
XREADGROUP COUNT <= availableSlots
         |
         v
Hand message to handler
         |
         v
Handler processes and commits successfully
         |
         v
XACK corresponding entry
         |
         v
Release in-flight slot
```

Design parameters example:

```text
MAX_IN_FLIGHT = 100
POLL_BATCH_SIZE = 20
PAUSE_THRESHOLD = 80
RESUME_THRESHOLD = 40
```

These are illustrative numbers, not Redis defaults. When in-flight >= 80, the consumer stops fetching new batches. When in-flight drops <= 40, polling resumes. Two separate thresholds (hysteresis) avoid rapid toggling.

When only 5 slots remain, do not call `XREADGROUP COUNT 20` and figure out placement later: Redis may deliver 20 entries and create unnecessary pending items. Adjust `COUNT` to actual free slots or wait until capacity opens.

If producers persistently write faster than total consumer throughput, scale out, optimize handlers, throttle producers, or size retention/backlog high enough. Pausing does not make system load disappear.

## 7. Pausing Properly: Stop Fetching, Do Not Fake Completion

In an imperative poll loop, pausing can simply mean **not calling `XREADGROUP` again**. With listener containers or reactive receivers, you may stop subscriptions or pause demand; however, cancelling or stopping does not automatically wait for all handlers to finish.

A controlled pause should:

1. Stop initiating new reads.
2. Stop accepting new tasks into the executor when full.
3. Wait for or manage currently executing handlers.
4. ACK only entries whose side effects completed.
5. Leave unACKed entries for PEL recovery.
6. Ensure retention covers the pause window.
7. On resume, process both new messages and old pending entries.

**Never pause by moving the group offset to the end of the stream or bulk-ACKing to “reduce lag”.** Those actions corrupt processing semantics instead of throttling demand.

### Pausing Before Reading vs. Pausing After Reading

```text
Case A:
    Producer XADDs 101, 102, 103
    Consumer is paused, has not called XREADGROUP
    -> 101, 102, 103 remain as undelivered backlog

Case B:
    Consumer XREADGROUP receives 101, 102, 103
    Handler has only finished 101
    Consumer stops
    -> 102, 103 remain in PEL, unACKed
```

To resume safely, Case A reads subsequent new entries; Case B also needs a mechanism to recover IDs delivered but not yet processed.

## 8. Trying Pause and Resume with Redis CLI

Create a test stream/group:

```bash
redis-cli XGROUP CREATE stream:orders:demo order-workers 0 MKSTREAM
```

Producer writes three events:

```bash
redis-cli XADD stream:orders:demo '*' eventId evt-1 type CREATED
redis-cli XADD stream:orders:demo '*' eventId evt-2 type PAID
redis-cli XADD stream:orders:demo '*' eventId evt-3 type PACKED
```

Consumer fetches up to two events:

```bash
redis-cli XREADGROUP GROUP order-workers worker-a \
    COUNT 2 STREAMS stream:orders:demo '>'
```

After successful processing, ACK the actual IDs received. Do not keep angle-bracket placeholders when running Redis commands:

```text
XACK stream:orders:demo order-workers <actual-ID-of-evt-1> <actual-ID-of-evt-2>
```

Now **pause** by refraining from calling `XREADGROUP`. Producer keeps sending:

```bash
redis-cli XADD stream:orders:demo '*' eventId evt-4 type SHIPPED
redis-cli XADD stream:orders:demo '*' eventId evt-5 type DELIVERED
```

When resuming:

```bash
redis-cli XREADGROUP GROUP order-workers worker-a \
    COUNT 10 STREAMS stream:orders:demo '>'
```

Messages not yet delivered to the group can still be read if not deleted/trimmed. However, if the consumer had already received events and crashed before ACK, a PEL recovery flow is needed in addition to `>`.

## 9. Java Example: Batch Polling and Pause/Resume with Spring Data Redis

A controllable approach is calling `StringRedisTemplate.opsForStream().read(...)` to read bounded batches, process synchronously, and ACK after success.

The example assumes consumer group `order-workers` was already created by deployment/infrastructure commands. Separating group creation from the read loop avoids multiple replicas racing to create a missing group.

### 9.1. Enabling Scheduling

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration
@EnableScheduling
public class OrderStreamSchedulingConfig {
}
```

### 9.2. Business Handler

```java
import java.util.Map;

public interface OrderEventHandler {
    // Returns normally when side effects are complete.
    // Throws an exception if processing cannot be confirmed.
    void handle(Map<Object, Object> event);
}
```

### 9.3. Consumer with a Pause Flag

```java
import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.core.StreamReadOptions;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class OrderStreamPoller {

    private static final Logger log =
            LoggerFactory.getLogger(OrderStreamPoller.class);

    private static final String STREAM = "stream:orders:v1";
    private static final String GROUP = "order-workers";
    private static final String CONSUMER = "order-worker-a";

    private final AtomicBoolean paused = new AtomicBoolean(false);
    private final StringRedisTemplate redis;
    private final OrderEventHandler handler;

    public OrderStreamPoller(
            StringRedisTemplate redis,
            OrderEventHandler handler) {
        this.redis = redis;
        this.handler = handler;
    }

    public void pauseNewReads() {
        paused.set(true);
    }

    public void resumeNewReads() {
        paused.set(false);
    }

    public boolean isPaused() {
        return paused.get();
    }

    @Scheduled(fixedDelayString = "${app.orders.poll-delay-ms:200}")
    public void pollOnce() {
        if (paused.get()) {
            return; // Do not fetch a new batch while paused.
        }

        List<MapRecord<String, Object, Object>> records;

        try {
            records = redis.opsForStream().read(
                    Consumer.from(GROUP, CONSUMER),
                    StreamReadOptions.empty()
                            .count(10)
                            .block(Duration.ofMillis(200)),
                    StreamOffset.create(
                            STREAM, ReadOffset.lastConsumed()));
        } catch (RuntimeException error) {
            log.warn("Unable to poll Redis Stream", error);
            return;
        }

        if (records == null || records.isEmpty()) {
            return;
        }

        for (MapRecord<String, Object, Object> record : records) {
            try {
                handler.handle(record.getValue());

                // ACK only after business processing completes.
                redis.opsForStream().acknowledge(
                        STREAM, GROUP, record.getId());
            } catch (RuntimeException error) {
                log.error(
                        "Event not acknowledged: {}",
                        record.getId(), error);

                // Failed event still needs PEL retry/recovery path.
                break;
            }
        }
    }
}
```

Properties of this approach:

- `count(10)` limits entries fetched per poll.
- `block(200ms)` waits briefly when no new entries exist, avoiding needless tight polling.
- `fixedDelay` schedules the next poll after the previous run finishes.
- When `paused = true`, the next batch is not read. If paused **mid-batch**, this still finishes the current batch—a simple *drain in-flight* pattern.
- If the handler throws an exception, the failing message and remaining unACKed entries in the batch need subsequent recovery.
- Does not manually jump a checkpoint to latest on resume; the group continues managing delivery state.
- **This example does not yet implement PEL recovery** and uses a single instance for clarity. Production needs restart/pending-claim handling.

With multiple replicas, do not give every consumer the same name `order-worker-a` without an ownership rule. Each instance/slot typically gets a distinct consumer name; new workers claim pending entries from old workers after an appropriate idle threshold.

This is a **synchronous read** example to keep ACK boundaries obvious. If handlers offload to an async executor, bound in-flight tasks and ACK in the completion callback, not upon submission.

## 10. Do Not ACK Merely Upon Enqueueing a Task

Mistake:

```java
for (MapRecord<String, Object, Object> record : records) {
    executor.submit(() -> handler.handle(record.getValue()));

    redis.opsForStream().acknowledge(
            STREAM, GROUP, record.getId()); // Too early!
}
```

If a crash happens after ACK and before the task starts, the event is no longer pending; the consumer group has no basis to redeliver it.

Instead:

```text
XREADGROUP
    |
    v
Check slot in bounded executor
    |
    v
Submit task
    |
    v
Task executes and commits successfully
    |
    v
XACK corresponding entry
```

Under parallel processing, ACKs can occur out of ID order. That is permissible in the consumer group model when business logic does not require strict ordered completion. If updates target the same aggregate where order matters, serialize by aggregate, enforce version checks, or partition work accordingly.

**ACK is business confirmation**, not a signal that “the message entered an internal queue”.

## 11. Pending Entries List: Recovering After a Crash

The PEL lists messages delivered yet not ACKed. Check:

```bash
redis-cli XPENDING stream:orders:v1 order-workers
```

To inspect individual entries in detail:

```bash
redis-cli XPENDING stream:orders:v1 order-workers - + 20
```

You can see IDs, owning consumers, idle times, and delivery counts. This reveals incomplete work even while the program continues reading new events.

### 11.1. Reading Pending Entries Received by the Same Consumer

In a consumer group, pass a specific ID such as `0` instead of `>` to read pending entries belonging to **that same consumer**:

```bash
redis-cli XREADGROUP GROUP order-workers worker-a \
    COUNT 10 STREAMS stream:orders:v1 0
```

This path does not fetch pending entries owned by another consumer.

### 11.2. Claiming Pending Entries from a Dead Consumer

Worker B can take over worker A's idle pending entries using `XAUTOCLAIM`:

```bash
redis-cli XAUTOCLAIM stream:orders:v1 order-workers worker-b \
    60000 0-0 COUNT 50
```

Here `60000` is the minimum idle time in milliseconds. The command can return a scan cursor; continue from the returned cursor if the scan pass is not yet complete. Once claimed, worker B processes and only ACKs when side effects genuinely complete.

**Never claim too early** while worker A is still processing: two workers can execute side effects concurrently. Pick `min-idle` from workflow processing/lease durations, monitor workers, and implement idempotency.

### 11.3. The PEL Does Not Store an Independent Payload Copy

The PEL tracks delivery and ACK metadata; it is not a secondary durable content store. If stream entries were `XDEL`ed or trimmed, payloads may no longer exist for replay even if pending metadata remains. Hence retention is a prerequisite for recovery.

## 12. Why Can Long Pauses Cause Data Loss?

Suppose:

```text
Producer: 5,000 entries/s
Stream keeps ~100,000 entries
Consumer pauses for 60 seconds
```

In 60 seconds, the producer writes ~300,000 entries. Under count-based trimming, older entries can be evicted before the consumer reads them. On resume, the group cannot recover deleted payloads.

Example producer capping stream size:

```redis
XADD stream:orders:v1 MAXLEN ~ 100000 '*' eventId evt-300 type PAID
```

`~` performs approximate trimming to cut overhead—it does not promise keeping strictly 100,000 entries at every instant.

### Designing Retention Around Recovery Time

- Estimate maximum offline/pause duration.
- Include retry, recovery, and pending catch-up time.
- Use peak write rates, not just averages.
- Monitor the first remaining ID in the stream, not just entry count.
- With multiple groups, size for the slowest group still needing events.
- If stream retention cannot cover expected outage durations, adjust retention, throttle producers, or move to an appropriate log/broker platform.

**Backpressure protects consumers from overload, yet backlog still consumes Redis memory.** Pausing cannot remain safe indefinitely on a stream with finite retention.

## 13. Observing Offsets: Group Lag Is Not the Unprocessed Event Count

Redis Stream IDs have millisecond and sequence components, e.g., `1780000000000-0`. Subtracting two ID timestamps does not yield an exact message count:

```text
last stream ID   = 1780000000500-0
group delivered  = 1780000000400-0

A 100 ms gap does NOT mean 100 messages of lag.
```

Use Redis commands to inspect:

```bash
redis-cli XINFO STREAM stream:orders:v1
redis-cli XINFO GROUPS stream:orders:v1
redis-cli XINFO CONSUMERS stream:orders:v1 order-workers
redis-cli XPENDING stream:orders:v1 order-workers
redis-cli XLEN stream:orders:v1
```

`XINFO GROUPS` can report `last-delivered-id`, pending count, and on supporting Redis versions, `lag`. Understand:

- Group lag mainly describes **delivery** progress, not whether all side effects finished.
- A group with `lag = 0` can still have many unACKed pending entries.
- Deletions, trimming, non-contiguous IDs, or group overrides can make lag undefined or incomplete as a picture of backlog.
- `XPENDING` shows delivered-but-unfinished work; watch pending age, not just count.
- Never compute exact backlog by subtracting two stream IDs.

Additional application metrics needed:

| Metric | Question |
|---|---|
| Producer append rate | How many new events per second? |
| Delivery rate | How many events is the group receiving? |
| Business success rate | How many events completed business processing? |
| ACK rate | How many events were acknowledged? |
| In-flight count | How many tasks are currently executing? |
| Executor queue depth | Is work backing up inside the JVM? |
| Pending count / oldest age | How long have delivered events been stuck? |
| Pause duration | How long has the consumer paused polling? |
| Recovery throughput | How fast are pending entries draining? |
| Retention head ID | Are unprocessed events at risk of being trimmed? |
| Handler p50/p95/p99 | Does capacity keep up with producers? |
| Retry/duplicate rate | Are replays triggering duplicate side effects? |

A health check verifying only that the Redis TCP connection is alive **is insufficient** to prove consumers are keeping up with backlog.

## 14. Processing Pending Entries and New Messages Together

A production system typically needs two responsibilities:

```text
Redis Stream
      |
      +--> New-message lane: XREADGROUP ... >
      |
      +--> Recovery lane: XPENDING / XAUTOCLAIM
                                |
                                v
                         Shared capacity limit
                                |
                                v
                       Idempotent handler
                                |
                                v
                              XACK
```

If both the recovery lane and new-message lane open unbounded concurrency, combined database load still overflows. Share a processing budget or allocate explicit quotas.

For events mutating the same entity, ordering between the two lanes matters too. For instance, recovering `ORDER_CREATED` after the new-message lane already processed `ORDER_PAID`: if a handler overwrites state blindly, final state can regress. Use version checks, per-aggregate serialization, or prioritize recovery before new messages per business rules.

No single ordering policy fits all flows: a versioned snapshot updater and an additive balance accumulator have completely different requirements.

## 15. Idempotency: Reprocessing Is a Normal Occurrence

Consumer groups and PELs enable recovery, not single-execution side-effect guarantees.

```text
1. Worker A receives event e-101.
2. A updates the database successfully.
3. A crashes before XACK.
4. Worker B reclaims e-101.
5. B receives the same event e-101 again.
```

If the handler merely runs `UPDATE total = total + amount`, the side effect is applied twice. You need a business event ID and idempotency rules.

Example payload:

```json
{
  "eventId": "evt-101",
  "orderId": "order-9",
  "version": 42,
  "type": "ORDER_PAID",
  "totalInCents": 350000
}
```

Inside the same database transaction, a handler can:

1. Check whether the event ID or version was already processed.
2. If not, update the projection.
3. Record the processed event ID or new version.
4. Commit the transaction.
5. After commit, call `XACK`.

If a crash occurs between steps 4 and 5, the replay sees the event was already processed and ACKs without applying a new side effect.

**Never ACK before commit** just to keep the PEL small. And never expect a database transaction to automatically include Redis `XACK`; they are separate resources unless coordinated by an explicit protocol.

## 16. Poison Messages and Dead-Letter Flows

A message that always fails due to malformed payloads or bad source data can retry infinitely:

```text
Message 101
  -> handler fails
  -> reclaimed
  -> handler fails
  -> reclaimed
  -> ...
```

To prevent getting stuck:

- Separate transient failures from unprocessable payloads.
- Cap retries and apply backoff with jitter.
- Track delivery counts and pending age.
- Move failing records to a dead-letter stream or durable store with enough metadata for investigation.
- Only ACK the source after error-handling policy completes (e.g., DLQ write succeeded).
- Provide tooling to fix data and perform controlled redrives.
- Apply idempotency because writing to the DLQ and ACKing the source are two steps that can fail in between.

Never “fix” a poison message by jumping the whole group's offset to the end of the stream; that can drop many other valid events.

## 17. Planned Pauses During Deployments

A pragmatic shutdown workflow:

```text
Deployment starts
     |
     v
Mark instance draining
     |
     v
Stop polling new batches
     |
     v
Wait for in-flight work up to deadline
     |
     +-- Succeeded: ACK corresponding entries
     |
     +-- Unfinished: leave pending
     |
     v
Close connections and stop instance
     |
     v
New instance starts
     |
     v
Recover old pending entries once eligible
     |
     v
Resume reading new messages
```

Do not assume calling `container.stop()` or cancelling a reactive subscription automatically waits for every callback, drains thread pools, ACKs accurately, and recovers all pending items. Exact lifecycle API behavior varies by version and config; the application must define in-flight ownership.

If stopping a container shared by multiple subscriptions, stopping the whole container can affect more streams than the single source you meant to pause. Separate container configs or poller controls per workload when independent pausing is needed.

In multi-replica deployments, avoid letting a new replica immediately claim pending entries that an old replica **is legitimately draining**. Idle thresholds should align with max processing durations and shutdown deadlines.

## 18. Incident Scenario: Large Backlog, Low Lag, Stuck Pending

Suppose an order-processing group shows:

```text
Stream has 50,000 entries.
Group has delivered nearly all 50,000 entries.
8,000 entries remain pending without ACK.
Consumers keep reading and processing new events.
```

Looking only at `last-delivered-id` near the stream tail or low lag might make operators think the system “caught up”. In reality, 8,000 delivered events remain unfinished, likely due to worker crashes, ACK failures, or stuck handlers.

Investigation steps:

1. Run `XINFO GROUPS` and `XPENDING` to check pending counts.
2. Check which consumers hold pending entries and how old they are.
3. Check handler error logs, ACK failures, processing durations, and process health.
4. Never adjust group offsets to hide pending counts.
5. If old workers died, reclaim idle entries via `XAUTOCLAIM`.
6. Reprocess idempotently; ACK after success.
7. Compare against the retention head to see if payloads remain readable or were trimmed.
8. Tune `COUNT`, concurrency, queues, and timeouts to match ingress load.

This is an example of **delivery progress drifting from business progress**, which cannot be fully detected from a “stream lag” chart alone.

## 19. Pre-Production Verification Through Testing

A controlled test suite should simulate both throughput and failures:

| Scenario | What to verify |
|---|---|
| Producer writes faster than consumer | In-flight work stays bounded without unbounded queues |
| Pause 30 seconds then resume | Messages added during pause are still read if within retention |
| Crash after `XREADGROUP` before handler | Entry remains in PEL and is recoverable |
| Crash after DB commit before `XACK` | Idempotent handler prevents duplicate side effects |
| Cancel reactive subscription when demand=0 | Offset does not jump to latest and skip needed entries |
| Consumer A dies while B stays alive | B reclaims A's pending entries after proper idle threshold |
| Handler fails consistently | Retries are bounded, routed to DLQ, and observable |
| Stream trimmed during long outage | Alerts fire and missing-payload detection runs |
| Group created with `$` | System does not accidentally skip required history |
| Group lag drops while pending rises | Monitoring still reports business backlog |
| Parallel processing of same-order events | Version/ordering logic prevents stale state overwrites |
| Redis restart/failover | Consumer recovers group, pending items, and connections per durability SLA |

In tests, measure **business-processed events**, not just events received from Redis. A system with a high ACK rate whose handlers fail to commit properly does not meet reliability requirements.

## 20. Choosing Mechanisms by Goal

| Goal | Recommended mechanism |
|---|---|
| Reduce fetched entries when downstream slows | Small `COUNT`, bounded executor, in-flight cap |
| Pause fetching new batches | Pause polling or control demand/lifecycle cleanly |
| Resume from last position with `XREAD` | Checkpoint tied to completed processing progress |
| Process without losing events via consumer group | `ReadOffset.lastConsumed()` for new messages + PEL recovery |
| Avoid skipping entries between polls | Avoid `ReadOffset.latest()` when full coverage is needed |
| Recover pending entries of current consumer | `XREADGROUP` with explicit ID per pending mechanics |
| Recover pending entries of a dead worker | `XAUTOCLAIM` with min idle and cursor |
| Avoid losing events after crashes | ACK after commit and sufficiently long retention |
| Tolerate redelivery after crashes | Idempotent handlers by event ID / version |
| Avoid toxic pending loops | Retry policy, backoff, durable DLQ |
| Increase throughput without overload | Bounded worker scaling, watch DB and ordering |

## 21. Decision Flowchart

```text
How many events must the Redis Streams consumer process?
                        |
                        v
          Are missed events acceptable?
                  +-----+-----+
                  |           |
                 Yes          No
                  |           |
                  v           v
           Lightweight     Consumer group,
           notifications   ACK, PEL recovery
           may pick              |
           latest                v
                  |        Bound in-flight work
                  |              |
                  +-------+------+
                          |
                          v
                   Downstream overloaded?
                          |
                    +-----+-----+
                    |           |
                   No          Yes
                    |           |
                    v           v
              Continue      Pause new reads,
              bounded poll  drain in-flight
                    |           |
                    +-----+-----+
                          |
                          v
                  Resume at right offset
                          |
                          v
                Process pending and new
                          |
                          v
              Verify retention, ACK,
              idempotency, and metrics
```

## 22. Conclusion

**Demand throttling** in Spring Data Redis Streams is more than slowing down `XREAD`/`XREADGROUP` calls. A proper design caps delivered-but-unprocessed entries, stops fetching more when full, and resumes at the right position after pauses or restarts.

**Offset drift** occurs when using `ReadOffset.latest()` across polling pauses, saving checkpoints from newly received IDs instead of processed IDs, creating or shifting groups to the wrong marker, or reading only `>` while forgetting old PEL items. Redis Streams offers groups, `XACK`, and `XAUTOCLAIM` to manage progress, yet does not protect trimmed entries and does not guarantee exactly-once side effects.

A system becomes reliable when all four conditions hold: **never fetch beyond capacity, never ACK early, never neglect pending entries, and never trim data before it can be recovered**. When producers permanently outpace consumers, increase processing capacity, reduce event emission, or choose a storage platform built for larger backlogs—pausing and resuming alone cannot fix a chronic throughput mismatch.
