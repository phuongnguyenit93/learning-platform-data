# Partition Ordering Guarantees in Debezium and Spring Integration

## 1. The Problem: Receiving Every Event Yet Applying Them Out of Order

In the **SPRING_INTEGRATION_ADAPTERS** module, external systems connect via inbound/outbound adapters, gateways, pollers, and `MessageChannel`s. A common pipeline uses **Debezium** to read changes from a source database's transaction log, emit CDC events to Kafka, and have a **Spring Integration Kafka inbound adapter** pass messages to transformers, routers, and service activators that update a target system.

Suppose order `orders.id = 42` changes in sequence:

~~~text
T1: status = NEW
T2: status = PAID
T3: status = SHIPPED
~~~

The database committed in order `T1 → T2 → T3`. If the program receives all three events but processes them in parallel and writes `SHIPPED` before `PAID`, the final projection can **regress from `SHIPPED` back to `PAID`**. The system did not lose a record, yet **the result is still wrong**.

**Per-partition ordering** is a key Kafka guarantee: records within the **same topic-partition** have a deterministic order defined by their log offsets. However, that guarantee alone solves only part of the problem. For the target system to stay accurate, you must understand the entire path: **database log → Debezium → Kafka partition → consumer → Spring Integration `MessageChannel` → sink transaction**.

After this lesson, you will be able to:

1. Distinguish source transaction order, Kafka record order, and actual sink processing order.
2. Understand the role of the **Kafka record key**, partitioner, and offset in maintaining per-entity sequentiality.
3. Design consumer groups, listener concurrency, and `MessageChannel`s without inadvertently scrambling order.
4. Explain the impact of snapshots, multi-table transactions, multiple partitions, retries, DLTs, replays, and primary-key changes.
5. Choose an appropriate processing strategy when you need per-key, per-partition, or global ordering.

## 2. Kafka's Exact Guarantee: One Ordered Log per Partition

A Kafka **topic** can have multiple **partitions**. Within each partition, the broker stores records as an append-only sequence with monotonically increasing offsets:

~~~mermaid
flowchart LR
    D[Debezium source] --> P0[(Topic orders · partition 0<br/>offset 15 → 16 → 17)]
    D --> P1[(Topic orders · partition 1<br/>offset 28 → 29 → 30)]
    D --> P2[(Topic orders · partition 2<br/>offset 7 → 8 → 9)]
    P0 --> C0[Consumer A]
    P1 --> C1[Consumer B]
    P2 --> C2[Consumer B]
~~~

**Kafka guarantees ordering within each partition, not a global offset or global order across partitions.** Offset `30` on partition 1 does not mean "after" offset `17` on partition 0 in business time.

Example within the same topic:

| Partition | Offset | Record | Meaning |
|---:|---:|---|---|
| 1 | 28 | `order=42, status=NEW` | Initial state |
| 1 | 29 | `order=42, status=PAID` | Next update |
| 1 | 30 | `order=42, status=SHIPPED` | Latest update |
| 0 | 15 | `order=99, status=NEW` | Different order |

From partition 1's log, the order **28 → 29 → 30** is certain. You cannot conclude whether partition 0 offset 15 occurred before, between, or after those three records solely from Kafka offsets.

### Three Kinds of Order Commonly Confused

| Kind of Order | Who Manages It? | Actual Guarantee |
|---|---|---|
| **Source transaction/change order** | Database and CDC mechanism | Source log orders changes; intra- or cross-transaction order depends on DB and connector |
| **Record order within a Kafka partition** | Kafka broker/producer | Records appended to the same partition have increasing offsets and are read in log order |
| **Processing/commit order in target app** | Listener container, Spring Integration, workers, DB sink | Preserved only if processing, acks, and concurrency maintain the desired relationship |

Thus, "Kafka guarantees ordering" **does not mean** a service activator automatically finishes writing each record in source order by default.

## 3. Record Keys Determine Whether Changes for the Same Entity Group Together

Debezium normally uses the **row's primary key** as the Kafka record key for keyed tables (exact behavior depends on connector and config). Example:

~~~sql
CREATE TABLE sales.orders (
    id BIGINT PRIMARY KEY,
    status VARCHAR(24) NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
~~~

Two updates to the same `id=42` share the same logical key:

~~~text
Event E1:
  key   = {"id":42}
  value = {"op":"u", "after":{"id":42,"status":"PAID"}, ...}

Event E2:
  key   = {"id":42}
  value = {"op":"u", "after":{"id":42,"status":"SHIPPED"}, ...}
~~~

With a **deterministic, unchanged partitioner**, keys producing identical serialized bytes are routed to the **same partition** of the same topic. If Debezium sends E1 then E2 in order to that partition, Kafka stores E1 before E2.

Conditions to verify:

- **Stable keys:** events for the same entity share identical key values and serialization (including data type and key format).
- **Stable topic:** if an SMT renames topics or a router splits one key across multiple topics, ordering loses its single axis.
- **Stable partitioner:** partition selection rules, topic partition count, and explicit partitions (if any) do not change across events that must remain ordered.
- **Ordered source producer:** the CDC stream and pipeline do not reorder records when publishing. Kafka only preserves **actual append order** inside a partition.
- **Ordered sink processing:** never dispatch two events with the same key to independent workers that commit in completion order.

**Never infer ordering from keys alone:** Kafka keys are the standard routing input, but applications can override behavior via custom partitioners, null keys, key SMTs, or explicit partition targeting.

### Composite Keys, Missing Keys, and Key Changes

If a table has a composite primary key (`order_id`, `line_no`), a Kafka key may contain **both** fields; business identity is not always a single integer.

If a table **lacks a primary key**, connectors may emit null keys or use custom key configurations. When `key=null`, never assume updates to the same row land on the same partition or work safely with compaction/upserts.

**Changing a primary key** can generate a logical sequence of **delete on old key** followed by **create on new key** (connector-dependent), plus a tombstone. The old and new keys may land on **two different partitions**. Never assume the application observes those records in global order; use a key-transition policy with independent, idempotent delete and upsert handling.

## 4. Distinguishing Source Log Position from Kafka Offset

Debezium reads source changes using database-specific mechanisms:

- MySQL: binary log; metadata can include `file`, `pos`, `row`, and `gtid`.
- PostgreSQL: WAL via logical decoding; metadata can include `lsn` and transaction information.
- Other databases have their own positioning systems.

In Kafka, each record is stored at a **topic-partition-offset**. These two positions **cannot be converted directly**:

~~~text
MySQL source change: mysql-bin.000031 : 47280
    -> Debezium
    -> Kafka topic orders-cdc.sales.orders, partition 2, offset 518
~~~

The source offset lets the **connector** resume after restart; the consumer group offset lets the **Spring Kafka consumer** resume reading Kafka. Source offsets can also store snapshot state and extra metadata beyond a single log position.

One source transaction can generate multiple CDC records across multiple rows/tables, landing in **multiple topics/partitions**. You cannot treat a single Kafka offset as a transaction-wide sequence number; nor can you simply compare per-event `ts_ms` values for "absolute order", because timestamps can collide, come from different clocks, or diverge from commit order.

## 5. From Binlog/WAL to Partitions: Key Boundaries

### 5.1. Source Read Order Does Not Mean Cross-Topic Order

A single transaction can modify two tables at once:

~~~sql
BEGIN;
UPDATE sales.orders SET status = 'PAID' WHERE id = 42;
INSERT INTO sales.payments (id, order_id, amount)
VALUES (9001, 42, 125000);
COMMIT;
~~~

Debezium may emit one row CDC event to `orders-cdc.sales.orders` and another to `orders-cdc.sales.payments`. Each topic has independent offsets; even if the connector observes the source transaction in a set order, **two independent consumers do not synchronize when orders and payments events are processed**.

When business logic requires **atomic** cross-table application, you can:

1. Use a **transactional outbox** in the source database to emit a single composite business event.
2. Leverage Debezium transaction metadata (if supported and enabled) to identify event groups/order and build a stateful, checkpointed aggregator.
3. Design a reconciling sink or wait until all prerequisites are met before publishing state.

Do not try to solve "atomic multi-table commits" merely by adding partitions or consumers.

### 5.2. How Does Transaction Metadata Help?

Some Debezium connectors attach `transaction` metadata when enabled, for example:

~~~json
{
  "op": "u",
  "after": {"id": 42, "status": "PAID"},
  "transaction": {
    "id": "tx-illustrative",
    "total_order": 3,
    "data_collection_order": 2
  }
}
~~~

This **abbreviated example** is not a universal payload across all connectors. Intra-transaction ordering fields help analyze or reconstruct event groups under an explicit contract. However, Kafka and Spring Integration **do not automatically wait across partitions to reassemble source transactions** merely because `transaction.total_order` is present. Relying on it requires buffering, completion detection, durable state, and handling missing events.

### 5.3. Snapshots and Streaming Can Interleave

Initial snapshots typically emit `op="r"` for existing rows before transitioning to streaming at an appropriate log boundary. Incremental snapshots emit chunked `r` events **while streaming is active**. Therefore, never assume **all `r` events always precede all `u` events** across an entire topic.

Debezium uses snapshot windows and collision resolution to reconcile snapshot reads with log changes per connector and version. Still, if an application splits snapshot and streaming records onto separate async channels or workers, they can commit out of order.

For instance, an older snapshot record `status=NEW` finishing **after** a streaming event `status=PAID` can overwrite the projection back to `NEW`. When building projections, define snapshot handling and update rules using reliable versions or source/partition ordering.

## 6. Consumer Groups: Who Gets Assigned Each Partition?

Within a Kafka **consumer group**, at any normal point in time **each partition is assigned to at most one active consumer member** in that group. One consumer can own **multiple partitions**, and multiple consumers enable parallelism **across partitions**.

Example:

| Topic Partitions | Consumer Members | Typical Assignment |
|---|---:|---|
| 3 | 1 | One consumer reads all three partitions |
| 3 | 2 | Partitions split between the two consumers |
| 3 | 3 | Each consumer typically owns one partition |
| 3 | 6 | At most three members get assigned for this topic; extra members sit idle |

This table considers **one topic with three partitions**; real assignments depend on all subscribed topics, partition assignors, instances, and consumer groups.

### Do Rebalances Break Ordering?

When consumers join or leave, a Kafka rebalance can move a partition from member A to member B. Record order in the log **does not change**. However, an application can still corrupt order if:

- A handed offset 101 to an asynchronous worker that has not yet written to the target.
- A rebalance happens and B starts processing from the last committed offset.
- A's old background task finishes and writes to the target **after** B has already applied a newer record.

To prevent "zombie processing", manage **in-flight work**, drain or cancel tasks on partition revocation, and apply fencing/versioning or transactional guards. Consumer group member counts alone cannot protect target state.

## 7. Spring Integration: `MessageChannel` Determines Actual Processing Order

The Kafka inbound adapter feeds records into a Spring Integration flow. **Channel type** and handler concurrency heavily govern ordering outcomes.

| Component / Config | Effect on Ordering |
|---|---|
| `DirectChannel` with synchronous handler | Caller processes the message on the calling thread; ideal for finishing target writes before pulling the next record on that consumer thread |
| `ExecutorChannel` | Hands messages to a thread pool; a later offset can finish before an earlier offset |
| `QueueChannel` + multiple pollers/workers | Messages dequeue in FIFO order, but **business commit times** can invert |
| Asynchronous `PublishSubscribeChannel` | Multiple subscribers/workers finish at different speeds; requires explicit coordination to confirm all branches |
| Transformer/router/service activator | Calling async APIs or internal executors breaks order even if the outer channel is synchronous |
| Outbound Kafka/JMS/HTTP adapter | Target completion order depends on external brokers/services, retries, and callbacks |
| Kafka listener concurrency | Parallelizes across partitions; verify how the listener container manages partitions and errors |

A straightforward pattern when **per-partition ordering is prioritized**:

~~~mermaid
flowchart LR
    K[(Kafka partition p)] --> C[Listener thread<br/>reads offset n then n+1]
    C --> D[DirectChannel]
    D --> T[Synchronous transformer]
    T --> H[Synchronous service activator]
    H --> DB[(Projection transaction)]
    DB --> A[Ack/commit per config]
~~~

In this pattern, the handler should **wait for the target transaction to commit** before returning. If you introduce async processing mid-flow, add corresponding ordering/ack coordination rather than assuming `send()` returning means the sink committed.

### 7.1. Conceptual Configuration Example

The snippet below illustrates the **contract**, not a complete standalone Spring Boot/Kafka setup:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;

@Configuration
public class CdcChannels {
    @Bean
    MessageChannel orderedCdcChannel() {
        return new DirectChannel();
    }
}
~~~

A Spring Integration Kafka inbound adapter can connect to `orderedCdcChannel`. The receiving side still requires serializers/deserializers, converters, error handling, a Kafka container, and transactions; the snippet above only defines a **synchronous channel**.

When higher throughput is needed, try increasing **partition counts** and matching consumer counts while measuring lag, rather than immediately putting a multi-threaded `ExecutorChannel` in front of a single partition. Still evaluate source load, key ordering, and partition-remapping impacts.

### 7.2. Is `concurrency = 1` Enough?

`concurrency=1` generally runs a listener container on one consumer thread, but it does **not** guarantee end-to-end ordering if:

- Multiple instances or consumer groups write to the same projection.
- A handler spawns an async task and returns early.
- Records go into a work queue where multiple workers update the same key concurrently.
- Rebalances leave stale tasks, or DLT replays/multiple topics write into the same table.

Conversely, **`concurrency > 1`** does not automatically break per-partition ordering if the listener container assigns separate partitions to separate threads and each partition's processing remains sequential. Distinguish **parallelism across partitions** (usually safe for independent keys) from **parallelism within a single partition** (requires explicit coordination).

## 8. Offset Commits Must Align with Processing Completion

A Kafka consumer group stores a **committed offset** indicating where to resume reading next. Normally, the committed value for a partition represents the **next offset to process**—for example, after processing offset 101, the committed position is 102.

Typical safe sequence:

~~~text
Poll record 100
  -> parse
  -> validate
  -> write projection (transaction commit)
  -> mark record 100 handled
Poll/process record 101
  -> ...
Commit consumer offset per ack mode and safe processing checkpoint
~~~

If target data is written **before the Kafka offset commits**, a crash can redeliver the record. That is at-least-once delivery: handlers must be idempotent.

If the Kafka offset commits **before** the target transaction is safe, a crash can skip the record for that consumer group even though the projection was never updated.

### 8.1. Offsets Cannot "Jump" Over Unfinished Records

Suppose partition 2 has records `100, 101, 102` processed concurrently by three workers:

| Offset | Status | Safe to Commit Position 103? |
|---:|---|---|
| 100 | Written to target | Not yet if 101 or 102 isn't finished |
| 101 | Retrying | **No** |
| 102 | Written to target | **No** while 101 remains unresolved |

Committing 103 tells the consumer group that all prior records are done, risking losing record 101 after a restart.

If intra-partition parallelism is required, track a **contiguous completed-offset frontier**, committing only up to the end of the contiguous safe prefix while cleanly handling in-flight tasks across rebalances and errors. Because this adds complexity, use it only when throughput demands it.

### 8.2. Can a Durable Channel Replace a DB Transaction?

If an inbound adapter writes messages to a durable queue and acknowledges only after safe persistence, that queue acts as a **controlled handoff point** with its own downstream checkpoints. Still, verify:

- Does the queue survive restarts?
- Are keys and partition/offset metadata preserved to replay in order?
- Can a message enter the queue while the target DB remains out of date?
- Does the queue flow have retries, deduplication, fencing, and DLQ handling?

Never commit Kafka offsets merely because a message entered an **in-memory queue**; if the process dies, unprocessed messages vanish.

## 9. How Retries, DLTs, and Late Events Break Ordering

A classic failure pattern:

~~~text
offset 201: order=42, status=PAID      -> mapping error -> sent to DLT
offset 202: order=42, status=SHIPPED   -> applied successfully
... several minutes later ...
redrive 201 -> UPSERT status=PAID      -> projection regresses
~~~

Sending a failed record to a **Dead Letter Topic (DLT)** lets the consumer proceed per policy, but **does not guarantee business state remains ordered**.

Options depending on goals:

1. **Strict ordering:** perform bounded retries, then pause the partition/key if the record still cannot proceed safely; fix and resume from that exact record.
2. **Allow error isolation:** publish to DLT and advance, provided the sink can reject stale records without overwriting newer state; monitor and reconcile gaps.
3. **Versioned state:** accept only events newer than the current reliable version/sequence, including delete markers so old events cannot resurrect deleted rows.
4. **Recompute current state:** when projections need only current state, fetch from source or run policy-driven reconciliation instead of unconditionally applying stale deltas.

**Timestamps are not a universal solution:** `ts_ms` values can collide, suffer clock skew, reflect snapshots, or measure connector processing time. A reliable version/ordering key must have defined scope and comparison rules matched to your connector, source, and business key. Nor can offsets from different partitions be compared as a global version.

### Deletes and Tombstones

A Debezium delete event typically has `op="d"` with `after=null`; a **Kafka tombstone** is a record with the same key and a Kafka-level `null` value emitted for log compaction.

~~~text
offset 300: key={"id":42}, value={...,"op":"d","after":null}
offset 301: key={"id":42}, value=null  (if tombstones are enabled)
~~~

If an older update replays after a DELETE, an unconditional upsert can **resurrect a deleted row**. Store a **tombstone/version marker** in the projection so older events cannot revive deleted state, or enforce strict ordered processing and controlled replays. Never treat Kafka log compaction as an automatic guard for target database commit order.

## 10. What Happens When Adding Partitions or Changing the Partitioner?

Suppose a Kafka topic initially has 4 partitions and hashing `{"id":42}` maps it to partition 1. Later, operations expands the topic to 8 partitions. **Partition mapping can shift**, sending newer events for `id=42` to a different partition while older events sit in the previous one.

~~~text
Before change:
  partition 1: order=42, PAID

After change:
  partition 5: order=42, SHIPPED

Both partitions are read independently
  -> SHIPPED may commit to target before PAID
~~~

Changing key serializers, SMTs, topic routing, producer partitioning strategies, or custom partitioners can produce the exact same effect.

**Design notes:**

- Size partition counts upfront for expected throughput and ordering needs.
- When long-term per-key ordering matters, treat partition count changes as a **data/routing migration**, not a routine tuning tweak.
- Consider migrating to a new topic: pause source writes or drain backlog on the old route, reconcile, and cut over producers/consumers safely.
- Ensure old and new pipelines never write concurrently to the same projection without versioning or fencing.

Adding partitions does not break every record/key automatically, but **you cannot preserve the same-key → same-partition invariant across topology changes** without a verified migration plan.

## 11. Three Ordering Requirements and Matching Architectures

| Requirement | Reference Design | Costs / Limitations |
|---|---|---|
| **Per-record order (`orderId`)** | Stable Kafka key, stable partition mapping, sequential per-partition processing or per-key sequencer, idempotent sink | Scales across keys; hot keys can bottleneck a partition |
| **Per-business-group order (`customerId`)** | Key by customer or use an outbox/business event topic; sequential group processing | Multiple orders for one customer share one partition; key changes and fan-out need care |
| **Single global order across all events** | Single partition or stateful global coordinator/sequencer | Limits throughput; multi-table/multi-source CDC does not provide global total order natively |

True global ordering across **multiple source databases** requires a shared sequence authority or coordination protocol. Kafka offsets cannot establish total order across partitions, and per-database transaction IDs are not globally comparable.

### 11.1. When to Use a Transactional Outbox

If the requirement is "when payment succeeds, emit an `OrderPaid` event after updating both orders and payments in one transaction", an **outbox table** written in that source transaction lets you emit one business record keyed by `orderId`, rather than having consumers stitch together multiple row CDC topics.

Debezium captures the outbox row change and an appropriate SMT/routing strategy places the event on the business topic. Outboxes clarify **semantic boundaries** and key choice, though you still must manage partition counts, retries, and downstream idempotency.

### 11.2. When Is a Per-Key Sequencer Needed?

A per-key sequencer or actor/mailbox lets different keys run concurrently while keeping each key sequential. However, if one Kafka partition fans out to multiple workers, Kafka offset commit logic must track the **contiguous completed offset frontier**, and member/instance changes must fence out late writes from old workers. That is a stateful coordination problem—you cannot solve it across multiple instances with an in-JVM `ConcurrentHashMap<key, Lock>`.

## 12. Example Handler Hardened with Idempotency and Ordering

Suppose a PostgreSQL projection `reporting.orders` consumes Kafka CDC for `sales.orders`. Events arrive from **a stable topic-partition** and process sequentially per key; the app must protect against consumer replays after crashes.

The **simple approach** is an idempotent UPSERT for the current state:

~~~sql
INSERT INTO reporting.orders (id, status)
VALUES (42, 'PAID')
ON CONFLICT (id)
DO UPDATE SET status = EXCLUDED.status;
~~~

This handles repeated delivery of the exact `PAID` event, but is **insufficient** if an older `PAID` event replays **after** `SHIPPED`.

If the target pipeline may encounter late/out-of-order events, maintain a `source_version` using an ordering rule **proven valid per record**. Illustrative **pseudocode**:

~~~text
onCdcRecord(event, kafkaRecord):
    key = validatedBusinessKey(event, kafkaRecord)
    version = trustworthyVersionForThisSourceAndKey(event)

    transaction:
        current = selectProjectionStateForUpdate(key)

        if current exists and version <= current.lastAppliedVersion:
            return ALREADY_HANDLED_OR_STALE

        if event.op in ["r", "c", "u"]:
            saveProjectionAndVersion(key, event.after, version)
        else if event.op == "d":
            saveDeleteMarkerAndVersion(key, version)
        else:
            failWithContext(event)

    acknowledgeAfterTransactionOrDurableRecovery()
~~~

Points requiring caution:

- **`trustworthyVersionForThisSourceAndKey` is an architecture-defined contract**, not a built-in API. A standalone `lsn` or binlog `pos` may not differentiate individual rows in a transaction; never compare them across separate clusters, connectors, or partitions.
- For snapshots, versions must reflect real snapshot boundaries/policies; never treat consumer arrival time as source order.
- Version comparison and target writes must be **atomic** so two workers cannot pass the check concurrently.
- Delete markers must be retained long enough to prevent old events from resurrecting deleted rows.
- When processing strictly sequentially on a fixed partition, versioning serves mainly as defense-in-depth for replays, DLTs, and topology changes.

### 12.1. Can Kafka Offsets Be Used as Versions?

**Yes, within a narrow scope**, if all updates for a projection key always land in **one fixed topic-partition** and the system controls all replay paths. In that case, `(topic, partition, offset)` identifies record position on Kafka, with offsets increasing within that partition.

However, this **breaks down if** the key moves to another partition, records come from two topics, two independent producers exist, redrives publish to a new topic, or Debezium replays an older source event at a **new Kafka offset**. An older source event re-emitted with a higher Kafka offset would trick a "highest offset wins" rule.

Never build last-write-wins logic solely on Kafka offsets if any of those cases can occur.

## 13. Common Failure Symptoms

| Symptom | Likely Cause | How to Check / Fix |
|---|---|---|
| Order regresses after raising throughput | `ExecutorChannel`/worker pool ran two same-key events in parallel | Check handler start/finish timestamps; use `DirectChannel` or per-key sequencing |
| Broke right after increasing Kafka partitions | Key → partition mapping shifted | Compare partitions for the same key before/after; plan migration |
| Works with 1 instance, fails when scaled | Stale async task writes after rebalance; multiple groups hit one sink | Inspect assignments, in-flight tasks, fencing, idempotent transactions |
| State wrong after DLT redrive | Older event applied after newer event | Version/dedupe, partition pause, reconciliation; retain delete markers |
| Payment update arrives before order update | Two independent tables/topics/partitions | Use an outbox or transaction metadata coordinator if merging is required |
| Consumer group offset rises while projection misses updates | Early ack before DB write, swallowed exception, non-durable queue | Check transaction boundaries, listener error handling, commit points |
| Keyless table scrambles distributed data | Null or unstable keys | Add a reliable identity key or change capture contract |
| Snapshot overwrites newer update | `r` and `u` processed on async branches without ordering | Check incremental snapshots, per-key sequencing, and versioning |
| High consumer lag on one partition while others sit idle | Hot key or poison-pill blocking partition | Monitor per-partition lag; revisit partition keys or poison-pill handling |

## 14. Practice: Reading Offsets and Predicting Outcomes

A Debezium MySQL pipeline emits `sales.orders` changes to Kafka topic `orders-cdc.sales.orders` with **3 partitions**. Spring Integration uses a Kafka inbound adapter and updates projections by `id`.

Suppose these records were appended:

| Topic-partition | Offset | Key | `after.status` |
|---|---:|---|---|
| P1 | 100 | `{"id":42}` | NEW |
| P1 | 101 | `{"id":42}` | PAID |
| P1 | 102 | `{"id":42}` | SHIPPED |
| P2 | 77 | `{"id":99}` | NEW |

Later, the app switches from synchronous `DirectChannel` to an `ExecutorChannel` with 8 workers. The worker handling offset 102 finishes faster than the worker handling offset 101.

**Questions:**

1. Did Kafka violate log ordering inside partition P1?
2. Why might order 42's projection still end up as `PAID`?
3. If offset 101 is still running while offset 102 already wrote to the target, should the consumer commit position 103?
4. If offset 101 failed and went to the DLT, what must happen before redriving it once 102 has succeeded?
5. When increasing the topic from 3 to 6 partitions, what must be verified to preserve order for order 42?
6. If events for `orders.id=42` and `payments.order_id=42` live in two different topics, can you compare their offsets directly to establish business order?

<details>
<summary>Solution Hints</summary>

1. **No.** Kafka still stored P1:100 → 101 → 102. The application's processing change caused DB commits to happen out of Kafka order.
2. Worker 102 wrote `SHIPPED` first; worker 101 wrote `PAID` afterward, overwriting the newer state. Enforce sequential per-partition/per-key processing or reliable versioning.
3. **No**, unless 101 is finished or durably recovered. Committing 103 skips 101 for the group, risking data loss on crash.
4. Check whether 101 still needs applying and protect the projection from stale writes; use versioning/dedup/reconciliation or block the key until order is restored.
5. Verify hash/partitioner, serialized keys, pre/post-change mappings, backlog draining, and migration plans. The same key can map to a new partition.
6. **No.** Kafka offsets are only comparable within a single partition. If cross-table transactions must stay unified, use explicit coordination or an outbox/business event.

</details>

### Design Exercise

A system must update an `account_balance` table from CDC, guaranteeing **balances are never credited/debited twice** while recovering cleanly after consumer restarts. Propose:

- Partition key if each account is processed independently.
- Suitable channel and concurrency in Spring Integration.
- Idempotency, transaction, offset acknowledgment, and duplicate-handling mechanisms.
- Behavior if an older event is redriven from the DLT after a newer update.

Hint: for financial domains, consider processing **events with unique IDs via a transactional outbox** or syncing absolute state guarded by a reliable version, rather than turning every row update into a non-idempotent "add to balance" command.

## 15. Checklist for Order-Preserving CDC Pipelines

- [ ] Define **ordering scope**: per row, per customer/account, per transaction, or global.
- [ ] Inspect actual Debezium Kafka keys, schema/key converters, SMTs, topic routing, and partitioners.
- [ ] Ensure stable keys route to the same partition during periods requiring ordering.
- [ ] Treat Kafka offsets as **topic-partition-scoped**; never compare offsets across partitions as a global sequence.
- [ ] Verify MySQL/PostgreSQL source behavior, snapshot mode, log positions, and transaction metadata if used.
- [ ] Account for how initial/incremental snapshots interleave `r` events with streaming `u/c/d` events.
- [ ] Configure Spring Integration channels, listener concurrency, and worker/async handoffs to match ordering needs.
- [ ] Confirm ack/commits happen only after target transactions or durable recovery steps succeed per policy.
- [ ] When processing a partition concurrently, never commit past unfinished or unrecovered offsets.
- [ ] Apply scoped idempotency/versioning; test replays, deletes/tombstones, and stale events.
- [ ] Maintain poison-pill/DLT procedures that do not silently break per-key ordering.
- [ ] Re-evaluate ordering guarantees whenever changing partition counts, partitioners, keys, or topics.
- [ ] Monitor **per-partition** consumer lag, rebalances, per-key processing times, and target write latency.
- [ ] Rehearse restarts and rebalances with in-flight messages and confirm projections never regress state.

**Key Takeaway:** Kafka guarantees **record ordering within each partition**. Debezium brings changes from the transaction log; record keys and partitioning determine which changes share that order. In **Spring Integration**, ordering reaches the target system accurately only when processing is synchronous or explicitly coordinated, offsets commit after safe completion, and idempotency plus recovery guard against retries, replays, DLTs, and topology changes.
