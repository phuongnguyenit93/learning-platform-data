# Partition or Consumer Group

## 1. The problem: scaling message throughput while preserving order

An e-commerce system emits the following events:

~~~text
OrderCreated(orderId=O-501)
PaymentAuthorized(orderId=O-501)
OrderCancelled(orderId=O-501)
~~~

The consumer needs to update each order's state in a valid sequence. As event volume grows, the operations team wants to add workers. If you add multiple consumers without a work-splitting strategy, several issues can occur:

- Two workers update the **same order** concurrently, overwriting newer state with older state.
- Adding consumers **does not increase throughput** because the topic only has one partition.
- Creating a new consumer group intending to “share load” actually causes **every event to be processed a second time**.
- Scaling the partition count causes an order's key to hash to a different partition, breaking simple ordering before/after the change.
- The broker redelivers after a crash and the handler produces a **duplicate side effect**, even though the offset was already read once.

Two concepts often confused are **partition** and **consumer group**.

A **partition** is how a broker (especially Kafka) splits a topic's log into multiple storage streams with **local ordering**. A **consumer group** is how consumers coordinate to divide partitions to **jointly process a single logical subscription**. These are **two complementary design axes**, not a mutually exclusive choice of *partition or consumer group*.

~~~mermaid
flowchart LR
    PUB["Order event producer"] --> TOPIC["Topic orders.events"]
    TOPIC --> P0["Partition 0"]
    TOPIC --> P1["Partition 1"]
    TOPIC --> P2["Partition 2"]
    P0 --> A1["Group inventory / Consumer A"]
    P1 --> A2["Group inventory / Consumer B"]
    P2 --> A3["Group inventory / Consumer C"]
~~~

In the **SPRING_INTEGRATION_PATTERN** module, we learn Enterprise Integration Patterns with **Spring Integration** to build loosely coupled, extensible message flows: **Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation**, combined with testing and monitoring processing branches. This lesson belongs to the **Message broker** chapter and focuses on how **partitions, groups, concurrency, and delivery semantics** impact an `IntegrationFlow` at the broker boundary.

**After this lesson**, you will know how to distinguish the two concepts, calculate available concurrency, choose message keys, preserve per-entity ordering, design idempotency/retry/DLQ across rebalances, configure Spring Integration consumers, and write tests verifying that scaling does not break business correctness.

## 2. Accurate definitions: partition, consumer, and consumer group

A **Topic** is a logical stream of records/events. In Kafka, a topic typically has multiple **partitions**:

~~~text
orders.events
  ├── partition 0: offset 0, 1, 2, 3, ...
  ├── partition 1: offset 0, 1, 2, 3, ...
  └── partition 2: offset 0, 1, 2, 3, ...
~~~

Each partition is a sequence of records with monotonically increasing offsets. There is no **global offset across the entire topic** to infer total ordering across all partitions.

A **Consumer** is a client/process reading records. A **Consumer group** in Kafka is a set of consumers sharing the same `group.id` to divide responsibility for processing a topic's partitions. Within the **same group** under the standard subscription model, each partition at any given time is assigned to at most **one active consumer in that group**. Consumers in **different groups** read independently.

Example:

~~~text
Topic has 6 partitions.
Group inventory has 3 consumers: each consumer can receive ~2 partitions.
Group analytics has 2 consumers: each consumer can receive ~3 partitions.

Both Inventory and Analytics receive the records under their own subscriptions.
~~~

The split above illustrates a **balanced distribution**; actual assignment depends on the assignor, membership, subscriptions, and rebalance state. Never assume every group always gets an exact even split of partitions.

## 3. Why is this not an “either partition or consumer group” question?

| Concept | Answers the question | Primary effect |
|---|---|---|
| **Partition** | Which logs is the data split into? | Data distribution, ordering scope boundary, per-partition parallelism ceiling |
| **Consumer group** | Who shares reading a single subscription? | Load balancing, failover, per-group committed offsets |
| **Consumer instance** | Which worker is polling/processing? | Executes the work |
| **Message key** | What criterion assigns a record to a partition? | Affinity for related events |
| **Offset** | Where is a record positioned within a partition? | Tracks read position, retry/replay |
| **Rebalance** | How does partition ownership change? | Membership/failover/scaling |

To process per-order and scale concurrency, you typically need **both**:

1. The producer selects a consistent **partition key**, e.g., `tenantId + orderId`.
2. The topic has a partition count suited to throughput requirements.
3. Workers belong to the **same group** to divide partitions.
4. Business handlers implement **idempotency, transactions, and ordering checks** for retries/rebalances.

**A partition is not a consumer group; a consumer group does not create more partitions.**

## 4. Illustration with 6 partitions

~~~mermaid
flowchart TB
    subgraph T["orders.events — 6 partitions"]
      P0["P0"]
      P1["P1"]
      P2["P2"]
      P3["P3"]
      P4["P4"]
      P5["P5"]
    end
    subgraph G["group.id=inventory — 3 consumers"]
      C1["consumer-1"]
      C2["consumer-2"]
      C3["consumer-3"]
    end
    P0 --> C1
    P1 --> C1
    P2 --> C2
    P3 --> C2
    P4 --> C3
    P5 --> C3
~~~

With standard consumer subscriptions:

- **3 consumers, 6 partitions:** 3 consumers can work concurrently.
- **6 consumers, 6 partitions:** up to 6 consumers receive assigned partitions for this topic.
- **9 consumers, 6 partitions:** at least 3 consumers will receive no partition **for that topic** (they may work on other topics if subscribed).
- **1 consumer, 6 partitions:** one consumer polls/processes all 6 partitions; **does not equal 6 parallel execution threads**.

A group can subscribe to **multiple topics**; the maximum number of active consumers depends on the **total assigned partitions**, not just one topic alone. Actual throughput also depends on CPU, I/O, poll loop, downstream pools, key skew, and broker quotas.

## 5. Basic sizing formula and its limits

For a topic with `P` partitions and a group with `C` compatible consumer instances, the maximum ownership-based parallelism at a point in time (assuming all consume the same topic) is:

\[
\text{active consumers} \le \min(P,C)
\]

This does not mean throughput equals `min(P,C) × speed(worker)` in every system. If one partition holds most of the records, the worker owning it can overload while other workers sit idle.

Suppose:

~~~text
6 partitions.
Group has 3 consumers.
Partitions have balanced load.
Each consumer can sustain ~250 events/second.

Theoretical consumer-tier throughput ≈ 3 × 250 = 750 events/second.
~~~

This is an **illustrative estimate**, not a measurement or guarantee. If the downstream DB only sustains 400 writes/second, adding consumers cannot overcome that bottleneck. If the producer emits 1,200 events/second, backlog/lag will grow.

**Partition count sets an important concurrency ceiling; it does not determine end-to-end throughput by itself.**

## 6. Where is ordering actually guaranteed?

Kafka maintains record order **within each partition** by offset. For example:

~~~text
Partition 2:
  offset 71: OrderCreated(O-501)
  offset 72: PaymentAuthorized(O-501)
  offset 73: OrderCancelled(O-501)
~~~

The consumer polls records in partition order, yet **completing side effects in the right order still depends on the application**. If after reading you dispatch each record to an executor pool without ordering constraints, `offset 73` may commit its business effect before `offset 72`.

There is no **global ordering** between:

~~~text
Partition 0: event A
Partition 1: event B
~~~

Even with timestamps, two independent producers, clock skew, or network retries can cause **event time** to differ from **append order**. If the domain needs business ordering, add an entity version/sequence and handle stale/out-of-order events.

**Broker ordering is a helpful precondition, not proof of correct end-to-end business ordering.**

## 7. Message key: binding same-entity events to the same partition

One strategy:

~~~text
key = tenantId + "|" + orderId
value = OrderEvent
~~~

When the producer uses the **same partitioner, same topic configuration, and unchanged partition count**, records with the same key are normally routed to the same partition. Thus, `O-501`'s events share a single ordering scope.

Example:

~~~text
key="tenant-a|O-501" → P2
  OrderCreated        (offset 71)
  PaymentAuthorized   (offset 72)
  OrderCancelled      (offset 73)

key="tenant-a|O-502" → P4
  OrderCreated        (offset 19)
  PaymentAuthorized   (offset 20)
~~~

**Note:** the producer must ensure publish ordering for events sharing a key; if multiple producers emit events for an aggregate concurrently without sequence/outbox coordination, landing in the same partition cannot fix an already broken **logical creation order**.

Never use `MessageHeaders.ID`, a random UUID per attempt, or a timestamp as the partition key when you want events of **one order** to have affinity. If the payload contains PII, consider an appropriate hashed/canonical key rather than copying emails or tokens directly into keys unnecessarily.

## 8. Which key should you choose for the business domain?

| Goal | Suitable key | Notes |
|---|---|---|
| Per-order ordering | `tenant + orderId` | Scoping is needed if order IDs can collide |
| Per-account ordering | Authenticated `accountId` | One hot account can create a hotspot |
| Per-cart ordering | `tenant + cartId` | Cart merge/split can change the key |
| Independent telemetry | Device ID or balanced partitioning | Strict ordering may not be required |
| Batch workflow | `batchId` | Large batches can overload one partition |
| Independently processed line items | `orderId + lineId` | Does not guarantee lines of the same order share a partition |

There is no **single key optimal for every consumer**. If Inventory needs ordering by SKU while Order Management needs ordering by `orderId`, you may need an intentionally **repartitioned topic/stream**. Never change keys arbitrarily on the same topic while consumers rely on `orderId` ordering.

**Partition keys are a business consistency and operational decision, not merely load balancing.**

## 9. Hot partitions and key skew

Suppose one merchant generates 60% of events. If the key is `merchantId`, one partition can take massive load:

~~~text
P0: ████████████████████ 60%
P1: ███ 10%
P2: ███ 10%
P3: ███ 10%
P4: ██  5%
P5: ██  5%
~~~

Adding consumers in the same group cannot split a single **hot partition** across multiple consumers simultaneously under standard assignment mechanics.

Options:

- Choose a finer-grained key, e.g., `tenantId + orderId` instead of tenant alone.
- If a single key is extremely hot and business rules allow, split into **shards** and add a controlled re-assembly/ordering layer.
- Use a separate topic or dedicated flow for high-volume tenants.
- Optimize I/O and handlers for the hot partition.
- Apply producer/rate limiting and isolate heavy workloads from other consumers.

**Never randomize partition keys to fix a hotspot if strict per-entity ordering is required.** Throughput may rise, but it breaks the ordering guarantees the application relies on.

## 10. Is increasing partitions always safe?

Suppose a topic grows from 6 to 12 partitions. With a partitioner based on `hash(key)` and partition count, the mapping of the **same key** can shift:

~~~text
Before: key O-501 → partition 2
After:  key O-501 → partition 8
~~~

Older events for `O-501` remain on P2 while newer events go to P8; the two partitions can be processed concurrently. **Per-key ordering across a partition-count change is no longer guaranteed by key hashing alone.**

System-dependent mitigations:

1. Keep the partition count stable and **provision headroom for growth upfront**.
2. Use a custom partition assignment / consistent mapping strategy with an explicit contract and versioning.
3. Perform a controlled drain/cutover, pausing writes briefly and ensuring consumers finish the old set before switching.
4. Create a newly versioned topic with the new partition strategy and execute an explicit migration.
5. Add **aggregate version checks/idempotency** so stale updates are never applied even if events arrive out of order.

Do not rely on one specific hash formula across all Kafka clients/versions. What matters is that **mappings can change when the partition set changes**, so migrations must be tested.

## 11. Same-group consumers vs. different-group consumers

~~~mermaid
flowchart TD
    T["orders.events / P0 P1 P2"] --> I["Group inventory"]
    T --> A["Group analytics"]
    I --> I1["Inventory worker 1"]
    I --> I2["Inventory worker 2"]
    A --> A1["Analytics worker 1"]
    A --> A2["Analytics worker 2"]
~~~

**Within the same group:** members divide partitions. If the inventory service runs three replicas, all three use `group.id=inventory` to **jointly execute one logical subscription**.

**Across two groups:** each group has its own cursor/offset state; Inventory and Analytics can both receive the **same event**. This is the pub/sub model per **logical consumer application**.

A common mistake:

~~~text
Replica inventory-1 → group.id=inventory-1
Replica inventory-2 → group.id=inventory-2
Replica inventory-3 → group.id=inventory-3
~~~

Instead of sharing load, those are **three independent groups**, each typically processing all subscribed messages according to its own offset/cursor. If each event triggers a reservation side effect, you risk **triple reservations** without domain deduplication.

**One logical microservice normally uses one stable group ID across replicas**, unless you genuinely want independent subscriptions.

## 12. Example table: 6 partitions, different consumer group layouts

| Topology | How many logical subscriptions? | Max active partition ownership per group |
|---|---|---|
| 1 group × 1 consumer | 1 | 1 consumer holds 6 partitions |
| 1 group × 3 consumers | 1 | Up to 3 active consumers |
| 1 group × 6 consumers | 1 | Up to 6 active consumers |
| 1 group × 9 consumers | 1 | Up to 6 active consumers on the topic |
| 2 groups × 3 consumers | 2 | Up to 3 active/group; each group receives its own stream |
| 3 groups × 2 consumers | 3 | Up to 2 active/group; total processing may triple |

“Active” in the table means **holding a partition assignment for the illustrated topic**, not continuously CPU-busy every second. A consumer assigned partitions on an empty topic can still sit idle.

**Increasing the group count does not increase load-shared capacity of a single processing function**; it adds independent subscribers.

## 13. Offsets are scoped to topic + partition + group

Kafka record position:

~~~text
topic = orders.events
partition = 2
offset = 71
~~~

Progress is usually tracked per **consumer group**:

~~~text
group.id = inventory
committed offset for partition 2 = 74
~~~

In Kafka, the committed offset normally represents the **next position to read**. After finishing records 71, 72, and 73, the committed offset may be 74.

**Never use an offset alone as a business idempotency key** for external side effects: offsets are scoped per partition/topic and can differ if an event is republished to another topic. Use a stable business event ID or operation ID per contract, optionally recording source position for auditing.

**An offset commit does not prove the database side effect and broker cursor committed atomically.** Crashing between the two operations can cause replays or lost processing if ordered wrongly.

## 14. At-most-once, at-least-once, and limits of exactly-once

Two things to distinguish are **message delivery/offset progress** and **business handler side effects**.

~~~text
A. Commit offset before business processing:
  poll message
  commit offset
  database write
  → process crashes between commit and write: processing may be lost.

B. Business processing then commit offset:
  poll message
  database commit
  commit offset
  → crash between DB commit and offset commit: replay may occur.
~~~

| Policy | Advantage | Risk |
|---|---|---|
| Commit before processing | Can avoid cursor-level replay | Side effect lost on crash |
| Commit after processing | Straightforward at-least-once processing | Duplicate delivery after crash |
| Kafka transactions in a Kafka-to-Kafka pipeline | Can achieve exactly-once semantics **within configured Kafka transaction scope** | Does not automatically include external DB/HTTP calls in the same transaction |
| Business inbox/idempotency in DB | One logical event causes no duplicate effect | Requires unique keys, fingerprints, lifecycle/recovery |

**Do not advertise “exactly-once” for an entire workflow just because the Kafka producer is idempotent or the consumer turns on auto-commit.** Kafka transactions have a defined guarantee boundary; an external HTTP payment, non-transactional JDBC database, or email provider requires its own mechanism.

When a database side effect is the target, normally choose **persist work first, commit offset second**, combined with **domain idempotency**.

## 15. Redelivery does not necessarily mean the producer sent the message twice

Timeline:

~~~mermaid
sequenceDiagram
    participant B as Kafka broker
    participant C as Group consumer
    participant DB as Business DB
    B->>C: partition 2 offset 71
    C->>DB: Process event EV-501
    DB-->>C: COMMIT business effect
    Note over C: Crash before committing offset 72
    B->>C: Redeliver offset 71 after recovery
    C->>DB: Check idempotency key EV-501
    DB-->>C: Already processed; no new effect
    C->>B: Commit next offset 72
~~~

This is **a Kafka record being re-read** because the cursor was not committed, not necessarily a producer duplicate.

At the application level, you can also encounter:

- Producer retries/republishes of the same logical event.
- DLQ replays creating new records in another topic.
- Snapshots/backfills re-emitting old events.
- A new consumer group starting from an earlier offset.
- A handler retrying internally after a transient error.

Hence, idempotency should rely on a scoped **business eventId/operationId**, not solely `topic-partition-offset` or a local in-memory set.

## 16. What is a consumer group rebalance?

A group with partition ownership:

~~~text
Initial:
  P0 P1 → C1
  P2 P3 → C2
  P4 P5 → C3
~~~

When C2 dies or leaves the group:

~~~text
After rebalance:
  P0 P1 P2 → C1
  P3 P4 P5 → C3
~~~

**Rebalance** is the process by which a group adjusts partition assignments when membership, subscriptions, or related metadata change. During handoff, throughput can be affected, and uncommitted records may be re-read by the new owner.

Triggers/factors:

- Deployments/restarts or autoscaling replicas up/down.
- A consumer failing to poll on time or its session expiring.
- A consumer holding records too long, exceeding poll interval policy.
- Changing partition counts.
- Changing subscribed topics or group protocol/assignor.
- Network issues or coordinator changes.

**Do not assume a rebalance always pauses every consumer**: eager, cooperative, and incremental mechanisms and different protocols/versions behave differently. Still, assume **partition ownership can transfer** and design recovery accordingly.

## 17. Why can a rebalance cause duplicate side effects?

A scenario:

~~~text
Consumer C1 owns P2.
C1 polls offset 71 (order O-501).
C1 writes database COMMIT.
C1 has not yet committed offset 72.
Group rebalance → P2 assigned to C2.
C2 starts at committed offset 71.
C2 processes O-501 again.
~~~

You cannot eliminate this scenario entirely by adding partitions or trying to keep members alive forever. You need:

1. Durable **idempotency** at the business boundary.
2. **Commit progress after work reaches a durable milestone**.
3. Handle partition revocation/reassignment in long-running handlers.
4. Prevent a stale worker from writing indefinitely after losing ownership if keyed data could be corrupted — use **fencing/leases/aggregate versions** when needed.
5. When an external side effect's outcome is unknown, reconcile instead of re-executing with a fresh key.

Group membership solves **read-responsibility distribution**; it does not automatically make business side effects exactly-once.

## 18. Rebalance listeners, cooperative assignment, and static membership

In Kafka clients, assignment strategies and group membership can be tuned to reduce unnecessary handoffs. Key concepts to know:

- **Eager rebalance:** many partition assignments may be revoked and reassigned in a single wave.
- **Cooperative/incremental rebalance:** narrows the scope of revocations in supported configurations/protocols.
- **Static membership:** uses stable identities for consumer instances to reduce churn during brief restarts under certain conditions.
- **Group protocol/version:** governs newer assign/rebalance behaviors; verify against deployed broker, client, and Spring Kafka versions.

**Never rely solely on rebalance optimization for correctness.** Even with optimal tuning, crashes, network partitions, and duplicate replays still happen. Write tests for consumer loss, restarts, and rebalances mid-commit.

For long-running tasks, consider decoupling polling from bounded processing, pausing/resuming partitions, or persisting a durable intent before ACK instead of blocking the poll loop indefinitely. These choices must preserve offset/recovery semantics.

## 19. `max.poll.interval.ms` and slow handlers

A consumer may poll many records but process slowly:

~~~text
poll 500 records
  → each calls external API
  → processing exceeds allowed poll interval
  → membership/assignment changes
  → record processing may replay
~~~

Parameters like `max.poll.records`, `max.poll.interval.ms`, heartbeat/session timeouts, poll timeout, and concurrency interact differently. There is no single “standard” set of values for every workload.

Operational guidance:

1. Measure **p95/p99 per-record processing time**.
2. Cap records per poll when synchronous processing is expensive.
3. Choose timeouts for a controlled worst case; do not raise them indefinitely to mask slow services.
4. If offloading to an executor, enforce a **bounded queue** and accurate completion/offset tracking.
5. Use pause/resume when internal backlogs saturate, per container capabilities.
6. Prioritize reducing remote latency/timeouts or moving long workflows to a durable work queue.

**Pushing polled records to an `ExecutorChannel` and committing offsets immediately does not give at-least-once processing**; if the JVM crashes before workers finish, recovery responsibility for those messages can be lost.

## 20. Adding downstream threads can break per-partition ordering

An IntegrationFlow:

~~~text
Kafka consumer reads P2:
  offset 71: create O-501
  offset 72: pay O-501
  offset 73: cancel O-501

DirectChannel → sequential handler
  typically offers easier-to-control ordering.

ExecutorChannel → 3 worker threads
  offset 73 can complete before offset 72.
~~~

**Kafka ordering** is log and fetch order; **application processing order** depends on scheduling, transactions, retries, and completion. For a strict per-order state machine:

- Keep processing sequential per partition/key where side effects occur; or
- Use a keyed execution lane / serial executor per business key; or
- Apply version/sequence guards and idempotent state transitions, rejecting stale writes.

If handlers process records independently (e.g., order-agnostic metrics), downstream parallelism can fit well. Never **accidentally route stateful commands into a shared executor pool without defining ordering requirements**.

## 21. Fan-out in Spring Integration is not the same as a consumer group

Three easily confused concepts:

~~~text
Kafka topic + Group A:
  partitions are divided among consumers belonging to Group A.

Spring Integration PublishSubscribeChannel:
  one message can be broadcast to multiple subscribers within one app context.

Spring Integration DirectChannel:
  can dispatch to one subscriber per send according to dispatcher semantics.
~~~

**`PublishSubscribeChannel`** is an in-flow fan-out mechanism; it does not create a separate Kafka group offset. **`DirectChannel`** does not create broker partition ownership. And a Kafka consumer group does not decide which Router/Transformer runs after a message enters the app.

Example:

~~~text
Group inventory receives event EV-501 once per logical subscription.
  → PublishSubscribeChannel to Validator + Metrics + Business handler
~~~

These are **multiple local subscribers handling the same event**, not multiple Kafka groups. If the Metrics handler is slow or fails, the impact depends on the channel/executor/error policy.

Do not use `PublishSubscribeChannel` to mimic competing consumers when the goal is work sharing (one business worker per record). And do not scale app replicas with distinct group IDs per replica unless you want independent fan-out.

## 22. RabbitMQ: competing consumers on a queue

In typical RabbitMQ queue usage, one pattern is:

~~~mermaid
flowchart LR
    P["Publisher"] --> EX["Exchange"]
    EX --> Q["Queue inventory.commands"]
    Q --> C1["Consumer 1"]
    Q --> C2["Consumer 2"]
    Q --> C3["Consumer 3"]
~~~

A message in the queue is **delivered to one consumer** in normal delivery, and can be **redelivered** to another consumer if unacked when a consumer/connection drops. This is the **competing consumers** pattern, similar in **load-sharing** intent to a Kafka group, though storage/cursor mechanics differ.

To deliver the same event to two applications:

~~~text
Exchange orders.events
  ├── queue inventory.events → inventory consumers
  └── queue analytics.events → analytics consumers
~~~

Each queue receives a copy via bindings/routing and maintains its own ACKs/backlog. **Never treat a Kafka consumer group as strictly equivalent to a RabbitMQ queue**: Kafka log partitions and group committed offsets differ from queue delivery/ACK and retention semantics.

With RabbitMQ, concurrency, prefetch, ACK/requeue, quorum/classic queues, and dead-lettering have their own semantics; do not blindly copy Kafka's `min(partitions, consumers)` formula to a queue without equivalent partition semantics.

## 23. JMS queues, topics, and shared subscriptions

In JMS-style messaging:

| Model | General meaning |
|---|---|
| **JMS Queue** | Competing consumers receive messages from one queue per provider semantics |
| **JMS Topic** | Pub/sub where subscriptions can receive copies of messages |
| **Durable subscription** | Retains subscription state per provider/configuration |
| **Shared subscription** | Multiple consumers share message delivery for a single subscription if supported by the provider/JMS version |

A Kafka group, RabbitMQ queue, and JMS shared subscription **share the goal of coordinating multiple workers**, but are **not identical** in partition ordering, offset/replay, retention, ACK, broker transactions, or failover.

When designing Spring Integration across multiple brokers, standardize **business contracts** and **recovery semantics**, without assuming transports have 1:1 equivalent APIs/protocols.

## 24. How do partitioned-log brokers and queue brokers differ?

| Question | Kafka topic partitions | Typical RabbitMQ queue | JMS queue (general) |
|---|---|---|---|
| Data splitting | Partitions within a topic | Queue + routing/bindings | Destination queue |
| Load sharing within one logical subscriber | Consumers in same group divide partitions | Competing consumers | Competing queue consumers |
| Cursor/ACK | Committed offsets per group/partition | ACK, requeue/delivery state | Ack/transaction per JMS provider |
| History replay | Possible via retention and offset reset/seek | Not an append-only log by default | Provider-dependent, not like Kafka by default |
| Ordering | Per partition, needs separate end-to-end guarantees | Can be affected by concurrency/redelivery | Provider/consumer behavior |
| Scale cap | Typically tied to assigned partition count | Not bound by Kafka partition counts | Not bound by Kafka partition counts |
| One event to multiple logical subscribers | Independent consumer groups | Multiple queues bound to exchange | Multiple topic subscriptions |

**Do not pick an API/adapter just because names look similar.** Ask requirements-driven questions: need replay? per-key ordering? independent subscriptions? low-latency RPC? work queue? DLQ retention? remote commit recovery?

## 25. When to choose more partitions, and when to choose more groups?

Choose **more partitions** when the goal is:

- More consumers in the **same processing application** need to process independently.
- Current throughput is bottlenecked by a single partition/leader/consumer lane.
- You have a partition key preserving ordering by business identity.
- You accept broker metadata, storage/replication, and migration costs.

Choose **adding a consumer group** when the goal is:

- A **new** logical application needs the same event stream, e.g., Analytics alongside Inventory.
- You need an independent lifecycle/offset/replay policy.
- One consumer must not consume events away from another application.

Choose **more replicas in the same group** when:

- The topic already has enough partitions to split the work.
- Consumer CPU/I/O is the bottleneck.
- Downstream capacity and retry/idempotency are ready.

**Do not add another group to speed up one service if each event must trigger only one business operation.** Doing so duplicates logical consumption and risks duplicating side effects.

## 26. Architectural decisions by concrete requirement

| Requirement | Design to consider | Trade-off |
|---|---|---|
| Every order processed in order | Key by `tenant+orderId`, single processing lane per key | Hot keys can bottleneck |
| Scale throughput across independent orders | Multiple Kafka partitions and consumer replicas in one group | Rebalance, cost, data skew |
| Both Inventory and Analytics receive events | Two Kafka consumer groups | Two subscriptions, two offset/backlog streams |
| Job queue with competing workers | RabbitMQ queue + multiple consumers | ACK/requeue and per-key order must be designed |
| Reprocess last week's events | Kafka group/seek or retention-based replay workflow | Side effects require deduplication |
| Fan-out one event inside the same app | Spring Integration `PublishSubscribeChannel` | Does not replace consumer groups or durability |
| One warehouse handles an entire order | Key by order | Can block parallel line processing |
| Each line processed independently | Key by `lineId` + explicit manifest Aggregator | Loses strict total order per order |

No topology simultaneously guarantees **absolute global ordering**, **infinite parallelism**, **zero duplicates**, and **unconditional availability**. Define business invariants first, then optimize concurrency within their bounds.

## 27. Spring Integration architecture with Kafka at ingress

An event stream:

~~~mermaid
flowchart LR
    PUB["Order event producer"] --> K["Kafka orders.events / 6 partitions"]
    K --> AD["Spring Integration Kafka inbound adapter"]
    AD --> CH["MessageChannel"]
    CH --> FIL["Filter/Validate"]
    FIL --> ROUTE["Router"]
    ROUTE --> HAND["Service Activator / business service"]
    HAND --> DB["DB + inbox/outbox"]
~~~

The **Kafka inbound adapter** receives records at the broker boundary and emits Spring `Message<?>` instances into the flow. **Group ID and partition assignment** belong to the Kafka consumer/container layer, not a property created downstream by a Router.

One process comprises three responsibility tiers:

1. **Kafka consumer/container:** group membership, polling, assignment, offset commits, and transport recovery.
2. **Spring Integration channels/endpoints:** validation, routing, transformation, business invocation, and error flow.
3. **Business state:** domain transactions/idempotency/consistency.

If tier 2 or 3 is flawed, adding partitions won't rescue correctness; if tier 1 commits offsets too early, even a correct business handler can **lose work on crash**.

## 28. Configuring group ID and concurrency: understand before scaling replicas

Example properties for a consumer application:

~~~properties
spring.kafka.bootstrap-servers=localhost:9092
spring.kafka.consumer.group-id=inventory-reservations
spring.kafka.consumer.enable-auto-commit=false
spring.kafka.consumer.auto-offset-reset=earliest
~~~

**This is a Spring Boot/Spring Kafka configuration example**, not a substitute for bean definitions of a specific Spring Integration Kafka adapter. You must define deserializers, security, container ack/error handling, and topic lifecycle in the project.

Key points:

- `group-id=inventory-reservations` must remain stable across replicas of the same logical consumer.
- `enable-auto-commit=false` lets the container/application design the commit policy, **without automatically guaranteeing** offsets commit after the DB transaction.
- `auto-offset-reset=earliest` applies only when **no valid committed offset exists** for the corresponding group/partition or on intentional resets; it **does not cause an existing group to re-read from the start** on every deploy.
- Changing `group-id` creates an **independent subscription state** and reads history per offset policy, so treat it as a business-impacting migration.

**Do not change `group-id` to temporarily clear lag.** A new group does not “inherit” the business progress or idempotency state of the old group automatically.

## 29. Sample Kafka message-driven adapter wired into an IntegrationFlow

Illustrative Spring Kafka container configuration with a Spring Integration adapter:

~~~java
@Bean
ConcurrentMessageListenerContainer<String, OrderEvent>
orderEventContainer(ConsumerFactory<String, OrderEvent> factory) {
    ContainerProperties props =
        new ContainerProperties("orders.events");
    props.setGroupId("inventory-reservations");
    props.setAckMode(ContainerProperties.AckMode.RECORD);

    ConcurrentMessageListenerContainer<String, OrderEvent>
        container =
            new ConcurrentMessageListenerContainer<>(factory, props);
    container.setConcurrency(3);
    return container;
}

@Bean
IntegrationFlow inventoryOrderFlow(
        ConcurrentMessageListenerContainer<String, OrderEvent> container,
        OrderEventHandler handler) {
    KafkaMessageDrivenChannelAdapter<String, OrderEvent> inbound =
        new KafkaMessageDrivenChannelAdapter<>(
            container,
            KafkaMessageDrivenChannelAdapter.ListenerMode.record);

    return IntegrationFlow.from(inbound)
        .handle(
            OrderEvent.class,
            (event, headers) -> {
                handler.applyIdempotently(event);
                return null; // One-way consumer, no reply needed.
            })
        .get();
}
~~~

**This is an illustrative structural skeleton**, not standalone copy/paste code: `OrderEvent`/`OrderEventHandler` are application types; you need imports, matching `ConsumerFactory`/deserializer beans, handler transactions, a Kafka error handler, and ack/retry policies. Container/adapter APIs and listener modes must be checked against your **exact Spring Integration Kafka/Spring Kafka version** before running.

`concurrency=3` creates **three internal listener consumers inside the container** on the example instance, **not three additional consumer groups**. If deploying 2 replicas each with concurrency 3, the group can have 6 consumer members sharing 6 partitions, depending on actual assignment.

**Lifecycle note:** the container is managed by Spring/the adapter; avoid accidentally creating two independent listeners on the same topic/group unintentionally. Do not register a second `@KafkaListener` for the same function without realizing you created competing consumers.

## 30. Container concurrency vs. in-flow executor concurrency

Two scaling approaches:

~~~text
A. Container concurrency=3
   consumer C1 owns P0,P1
   consumer C2 owns P2,P3
   consumer C3 owns P4,P5
   each handles assigned records synchronously.

B. Container concurrency=1
   consumer C1 polls P0..P5
   sends all records to ExecutorChannel pool=8
   → worker completion order does not follow partition order by default.
~~~

In approach A, consumer members and partition assignments scale together. In approach B, **a single Kafka consumer still polls** and submits work to a thread pool; if offsets are committed merely upon enqueuing, there is a **loss window** if the process crashes before workers complete.

If async workers are needed, additionally design:

- Bounded backlogs and backpressure.
- Durable work handoff or per-partition completion tracking.
- Offset commits only after an appropriate processed/durable milestone.
- Ordering/fencing by partition or business key.
- Explicit worker error handling.

**Do not add executor threads to bypass partition count without defining delivery and ordering guarantees.**

## 31. Mapping Kafka record metadata to Spring messages

An inbound message may carry:

~~~text
payload = OrderEvent(eventId=EV-501, orderId=O-501)
headers:
  kafka_receivedTopic = orders.events
  kafka_receivedPartitionId = 2
  kafka_offset = 71
  kafka_receivedMessageKey = tenant-a|O-501
  businessCorrelationId = tenant-a|O-501|revision-3
~~~

**This is a conceptual metadata representation**. Exact constant/header names such as `KafkaHeaders.RECEIVED_TOPIC`, `KafkaHeaders.RECEIVED_PARTITION`, `KafkaHeaders.OFFSET`, and received-key may vary across Spring Kafka versions; check the API for your exact version instead of hardcoding strings in business services.

Do not confuse:

- **Kafka record key**: used for partitioning and transport-level record identity.
- **Business event ID**: used for domain deduplication.
- **Kafka partition/offset**: source position for observability/replay.
- **Spring `MessageHeaders.ID`**: message object ID inside the flow.
- **Business correlation**: groups logical workflows/Splitter/Aggregator.

When crossing HTTP or other brokers, custom headers may not be mapped; if business IDs must survive transport/replay, put them in the **wire contract** or an appropriate durable mapping.

## 32. Never build group IDs from instance, host, or pod names

A dangerous configuration:

~~~java
String groupId = "inventory-" + System.getenv("HOSTNAME");
~~~

If each pod has a different hostname:

~~~text
inventory-pod-1 → group inventory-pod-1
inventory-pod-2 → group inventory-pod-2
inventory-pod-3 → group inventory-pod-3
~~~

Each pod becomes **its own logical subscriber**, rather than three workers in the same group. For `PlaceOrderEvent`, all three could invoke the side-effecting handler if offset policy and retention deliver the event to all three.

**Group ID** identifies the logical consumer application, whereas `client.id`/instance identity assists observability and membership. The two IDs do not substitute for each other.

If you genuinely want a **shadow consumer** reading separately for testing, use a distinct group with **side effects disabled or isolated**; never let two groups write to the same production table without explicit deduplication/authorization.

## 33. Watch out for deserialization and poison pills

A Kafka record with malformed JSON/schema:

~~~text
topic orders.events / P2 / offset 71
value = malformed JSON
~~~

Failure can occur in the deserializer **before Spring Integration even creates a `Message`**. In that case, Filters/Transformers in the flow may never be invoked.

You must design:

1. An error-handling deserializer/container strategy per your Kafka client/Spring Kafka version.
2. Classification of **permanent malformed input** vs. **temporary infrastructure failure**.
3. Recovery/DLT records containing topic/partition/offset and a safe `reasonCode`.
4. Never infinitely retry a byte payload that permanently violates the schema.
5. Quarantine/DLT publishing must achieve durability before relinquishing source processing responsibility.
6. Replays must have versioned mapping policies and business idempotency.

**DLT/DLQ is a recovery mechanism configured by the application/container, not an automatic byproduct of adding `@MessagingGateway` or `@ServiceActivator`.**

## 34. Spring Integration error channel vs. Kafka container recoverer

A diagram:

~~~text
Kafka bytes
  → Consumer deserializer
      ├── failure: container/deserializer error handling
      └── success: Spring Integration inbound adapter
           → Filter/Transformer/Service Activator
               ├── sync exception: adapter/container boundary
               └── async failure: ErrorMessage/errorChannel or worker recoverer
~~~

Do not claim **every exception goes to the global `errorChannel`**. If a payload has already been dispatched through an `ExecutorChannel`, errors can happen after the Kafka poll loop has returned; recovery and offset ownership must be designed at the **right async boundary**.

| Error | Where detected | Typical handling path to consider |
|---|---|---|
| Invalid bytes/schema | Deserializer | Container error handler / DLT |
| Filter rejection | Flow endpoint | Typed exception/discard channel per contract |
| Mapper type error | Transformer | Error channel or container handler depending on sync/async |
| DB timeout | Service Activator | Bounded retry, do not ACK and lose work |
| Business conflict | Domain handler | Terminal outcome/DLT per contract |
| Async worker crash | Worker queue/executor | Durable recovery, not logging alone |
| Offset commit failure | Kafka container | Rebalance/redelivery readiness + idempotency |

**An ACK on a Spring Message is not necessarily a Kafka offset commit**; if using manual acknowledgement, understand the exact metadata/acknowledgment exposed by the adapter/container and version-specific commit semantics.

## 35. Filter drops and offset progression

Suppose a Filter:

~~~java
@Filter(inputChannel = "orders.events.in")
public boolean accept(OrderEvent event) {
    return event.type() != OrderEventType.DEBUG;
}
~~~

If `DEBUG` is an **event type permitted to be ignored** by contract, treating it as processed/skipped and committing the offset can be valid. However, if a Filter drops a message due to **malformed required fields**, a request–reply consumer or downstream Aggregator could wait forever while the offset advances.

**Distinguish three cases**:

- **Intentionally ignored:** event outside subscription business logic, with a skip metric.
- **Permanently rejected:** input violates contract, with a DLT/rejection record.
- **Temporarily failed:** dependency down, requiring retry/recovery.

Never catch DB errors and return `false` as a Filter rejection; doing so turns an outage into permanently skipped messages.

## 36. Retries, DLT, and ordering within the same partition

A hot partition:

~~~text
P2:
  offset 71: invalid event EV-501
  offset 72: valid event EV-502
  offset 73: valid event EV-503
~~~

If an error handler retries offset 71 repeatedly using a blocking strategy, offsets 72/73 may **stall**. If EV-501 is moved to a DLT and offset 71 is committed/skipped, later offsets can proceed, yet **order/business dependencies** between EV-501 and EV-502 may go unprotected.

Two common policies:

1. **Block partition until resolved:** preserves stricter sequential processing but increases lag/hot-partition risk.
2. **Skip/quarantine terminal poison pill:** keeps throughput moving; valid only if business rules allow subsequent events to process when an earlier one is sidelined.

With delayed/non-blocking retries through another topic, note especially that **per-key ordering may no longer hold** when a failed record is diverted while newer records flow straight through.

**Retry policy is a consistency choice**, not just a “number of retries” setting.

## 37. Domain idempotency for a consumer group

A handler processing `OrderCreated`:

~~~java
record OrderEvent(
    String tenantId,
    String eventId,
    String orderId,
    int aggregateVersion,
    OrderEventType type
) {}

enum OrderEventType {
    CREATED, PAYMENT_AUTHORIZED, CANCELLED, DEBUG
}
~~~

A business store can define a unique key:

~~~sql
CREATE TABLE processed_order_event (
    tenant_id VARCHAR(80) NOT NULL,
    event_id VARCHAR(120) NOT NULL,
    payload_fingerprint VARCHAR(128) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, event_id)
);
~~~

**Never write the marker first and then call a DB write outside the transaction.** The marker and side effect must be atomic when using the same database; for external HTTP side effects, remote idempotency/reconciliation is required. `aggregateVersion` helps guard against **stale/out-of-order state transitions**, without replacing `eventId` deduplication.

Scenarios:

- Same key + same fingerprint → can treat as already processed.
- Same key + different fingerprint → conflict/audit; do not silently discard a different payload.
- New event ID with an aggregate version lower than committed version → apply stale event policy.
- Producer emits a duplicate logical effect under a new `eventId` → requires a domain operation ID or appropriate constraint; `eventId` deduplication alone cannot solve this.

**Kafka group assignment guarantees one temporary owner, not that business DB writes become exactly-once.**

## 38. Transactional inbox with version guard

A service skeleton:

~~~java
@Service
class OrderEventHandler {
    private final ProcessedEventRepository inbox;
    private final OrderStateRepository orders;
    private final EventFingerprint fingerprint;

    OrderEventHandler(
            ProcessedEventRepository inbox,
            OrderStateRepository orders,
            EventFingerprint fingerprint) {
        this.inbox = inbox;
        this.orders = orders;
        this.fingerprint = fingerprint;
    }

    @Transactional
    public void applyIdempotently(OrderEvent event) {
        validateTrustedTenantAndPayload(event);
        String eventHash = fingerprint.canonicalHash(event);
        boolean first = inbox.insertIfAbsent(
            event.tenantId(), event.eventId(), eventHash);

        if (!first) {
            inbox.assertSameFingerprint(
                event.tenantId(), event.eventId(), eventHash);
            return; // Duplicate already reached committed state.
        }

        orders.applyIfVersionValid(
            event.tenantId(),
            event.orderId(),
            event.aggregateVersion(),
            event.type());
    }

    private void validateTrustedTenantAndPayload(OrderEvent event) {
        // Application validation + verified ingress identity.
    }

}
~~~

The repositories/methods and `EventFingerprint` are **application abstractions**, not complete code; production must provide a consistent canonical serialization/hash for `canonicalHash`, verified uniqueness constraints, and tested transaction boundaries. If `applyIfVersionValid` detects a version gap needing a later retry, **throw an error to roll back the inbox marker** instead of simply returning and marking the event processed.

`@Transactional` on the handler must be invoked through the Spring-managed bean/proxy; internal self-invocation via `this.method()` can bypass the default transaction proxy. If using an async channel, the transaction must open on the **worker thread actually running DB code**.

## 39. Correlation with Splitter/Aggregator under a consumer group

When each `OrderEvent` splits into three child tasks:

~~~text
Kafka P2 offset 71 → OrderEvent(order=O-501)
    → Splitter:
        stock   member A
        pricing member B
        fraud   member C
    → workers/remote endpoints
    → Aggregator (expected A,B,C)
    → OrderReady/OrderRejected
~~~

**Kafka partition assignment** is not an **Aggregator correlation group**. One consumer can own multiple partitions, each carrying many orders; the Aggregator's group key must be a **business scope** such as `tenantId + orderId + operation/revision`, never `group.id` or `partitionId`.

Invariants:

- Child identities do not collide: members A/B/C.
- Correlation ID stays stable across retries/replays.
- Duplicate children must not count as new members.
- Child errors must have a **terminal failure outcome** or whole-group failure policy.
- `GroupStore` release/timeout/expiry must not turn late replies into a second summary.
- Parent offset commit must align with the **durable handoff/completion milestone** committed by the flow.

If the Kafka consumer ACKs the parent right after the Splitter enqueues onto an in-memory executor, a crash can **lose child tasks** even though the parent offset committed. A durable outbox/work queue or explicit transaction protocol is required for long workflows.

## 40. Reading lag accurately: group lag vs. business-processing latency

A common metric is per-partition **consumer lag** for a group:

\[
\operatorname{lag}_{g,p}
=\max(0,\ \operatorname{logEndOffset}_{p}
-\operatorname{committedOffset}_{g,p})
\]

This measures distance in **offset positions**, not automatically the number of unfinished business operations. With compacted logs, offsets can have gaps; with async processing, commits may precede or follow durable business completion depending on design.

Example:

~~~text
P2 log end offset = 190
Group inventory committed next offset = 150
Reported lag ≈ 40 offset positions
~~~

Lag can rise because producers outpace consumers, due to a hot partition, frequent rebalances, slow DBs, blocking poison-pill retries, or delayed commit progress. **Zero lag does not prove all child tasks downstream of an `ExecutorChannel` have finished** if offsets are committed upon in-memory enqueuing.

Also measure per-partition lag, message age, throughput, handler latency, retry rate, and **business completion backlog**. Do not rely solely on total group lag.

## 41. Metrics to monitor

The following metrics are **application/operational recommendations**, not a claim that Spring Integration provides all of them out of the box:

| Metric | Explanation |
|---|---|
| `consumer.group.assigned.partitions` | Number of partitions currently assigned to each member |
| `consumer.partition.lag` | Lag per partition |
| `consumer.partition.oldest.age` | Age of the oldest unprocessed record |
| `consumer.poll.records.count` | Records polled |
| `consumer.handler.duration` | Handler latency p50/p95/p99 |
| `consumer.handler.success.count` | Durable business completions |
| `consumer.handler.failure.count` | Failures by `reasonCode` |
| `consumer.commit.failure.count` | Offset commit failures |
| `consumer.rebalance.count` | Frequency of ownership changes |
| `consumer.rebalance.duration` | Rebalance duration |
| `consumer.duplicate.detected.count` | Successful deduplications |
| `consumer.stale.version.count` | Stale/out-of-order events |
| `consumer.retry.attempt.count` | Retry amplification |
| `consumer.dlt.pending.count` | Terminal error backlog |
| `consumer.async.work.pending.count` | Accepted work not yet completed |

Metric labels should only hold low-cardinality values such as topic/group/partition, operation, and error class. **Never use `eventId`, `orderId`, customer email, raw payload, or trace ID as metric labels**.

## 42. Structured logging: separating transport position from business identity

A protected log entry:

~~~text
sourceTopic=orders.events
sourcePartition=2
sourceOffset=71
consumerGroup=inventory-reservations
eventId=EV-501
tenantScope=tenant-a
orderId=O-501
aggregateVersion=3
handlerOutcome=SUCCEEDED
idempotencyOutcome=FIRST_COMMIT
offsetCommitRequested=true
~~~

Redelivery:

~~~text
sourceTopic=orders.events
sourcePartition=2
sourceOffset=71
consumerGroup=inventory-reservations
eventId=EV-501
handlerOutcome=DUPLICATE_COMPLETED
businessSideEffectCount=0
~~~

Never include bearer tokens, credentials, or full raw payloads in logs. Logging source position aids investigation; business event ID enables deduplication. **`offsetCommitRequested=true` does not mean the commit definitely succeeded.**

## 43. Unit testing a stable business partition key

A pure function producing the key:

~~~java
final class OrderPartitionKey {
    static String forOrder(String tenantId, String orderId) {
        if (tenantId == null || tenantId.isBlank()
                || orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException(
                "MISSING_PARTITION_KEY_COMPONENT");
        }
        return tenantId.length() + ":" + tenantId
            + ":" + orderId.length() + ":" + orderId;
    }
}
~~~

Length-prefixed encoding reduces ambiguity when fields contain delimiter characters. Production systems can use versioned canonical binary encoding or hashed keys.

~~~java
@Test
void sameOrderKeepsStableBusinessPartitionKey() {
    String first =
        OrderPartitionKey.forOrder("tenant-a", "O-501");
    String retry =
        OrderPartitionKey.forOrder("tenant-a", "O-501");
    String otherTenant =
        OrderPartitionKey.forOrder("tenant-b", "O-501");

    assertEquals(first, retry);
    assertNotEquals(first, otherTenant);
}

@Test
void missingOrderIdIsRejected() {
    assertThrows(IllegalArgumentException.class,
        () -> OrderPartitionKey.forOrder("tenant-a", null));
}
~~~

**This test validates the key contract**, not partition assignment across partition-count migrations. You still need producer tests against a real partitioner/cluster configuration.

## 44. Producer test: same key routes to the same partition

A conceptual Kafka producer:

~~~java
OrderEvent created = new OrderEvent(
    "tenant-a", "EV-501", "O-501", 1,
    OrderEventType.CREATED);
OrderEvent paid = new OrderEvent(
    "tenant-a", "EV-502", "O-501", 2,
    OrderEventType.PAYMENT_AUTHORIZED);

String key = OrderPartitionKey.forOrder(
    created.tenantId(), created.orderId());

kafkaTemplate.send("orders.events", key, created);
kafkaTemplate.send("orders.events", key, paid);
~~~

In an integration test with a fixed topic, inspect `RecordMetadata.partition()` to verify both records land on the same partition **under the active partitioner**. Having the same key does not guarantee business creation order if multiple producers publish for the same order concurrently and race.

Never run tests against a production broker; use an isolated test broker (embedded/Testcontainers) and manage test topic/group lifecycles separately.

## 45. Integration test: 6 partitions, 3 consumers in the same group

~~~text
Topic test.orders: 6 partitions
Group test.inventory: 3 consumers
Produce 600 independent events, keys spread across many orders

Expected:
  every eventId has one committed business outcome;
  no eventId missing;
  assignments cover all 6 partitions;
  handler invocations may exceed distinct commits after retry.
~~~

The test should:

1. Create a topic with exactly 6 partitions.
2. Have three consumers with the same group ID join and wait for actual assignment.
3. Publish events with traceable event IDs and business keys.
4. Wait until inbox/DB reaches 600 **distinct completed effects**, not just 600 receives.
5. Assert there are zero duplicate business effects.
6. Verify assignments cover all partitions without unnecessarily forcing a 2/2/2 split.
7. Stop the group and verify recovery/committed progress per policy.

**Do not use `assert each consumer receives exactly 200` as a correctness invariant.** Key skew and uneven assignments can occur without losing any events.

## 46. Integration test: two groups receive the same events independently

~~~text
Topic test.orders (6 partitions)
Group test.inventory: 2 consumers
Group test.analytics: 2 consumers
~~~

Expectations:

- Inventory commits 600 distinct event IDs into its own projection.
- Analytics commits 600 distinct event IDs into an independent projection.
- Inventory's progress does not alter Analytics' cursor.
- Stopping Analytics does not block Inventory from reading.
- Restarting Analytics allows it to catch up per retention/offset policy.

**Two groups are two logical subscriptions**, not four workers splitting one consumer workload. Tests must use separate stores/projections; avoid letting Analytics accidentally invoke Inventory's side-effecting `reserveStock()`.

## 47. Fault injection: crash after DB commit before offset commit

~~~text
P2 offset 71, EV-501.
Consumer C1:
  DB COMMIT + inbox EV-501
  crash before committing next offset 72

Consumer C2:
  owns P2 after rebalance
  reads EV-501 again
  inbox detects completed duplicate
  no new business mutation
  commits progress
~~~

Assertions:

- Offset 71 may be read more than once.
- EV-501 has only **one** committed side effect.
- The duplicate attempt does not trap the partition in infinite retries.
- Same key with a different fingerprint raises a conflict rather than being silently ignored.
- Rollback before DB commit leaves no poisoned inbox marker behind.
- Partition ownership/progress recovers after rebalance.

Tests must inject faults around a **real transaction commit**, rather than only mocking `handler.apply()` to return true.

## 48. Testing ordering when downstream runs concurrently

Three events:

~~~text
EV-1: O-501 version 1 CREATED
EV-2: O-501 version 2 PAYMENT_AUTHORIZED
EV-3: O-501 version 3 CANCELLED
~~~

Test two topologies:

1. **Sequential handler per partition** with an aggregate version guard.
2. **`ExecutorChannel`/thread pool:** use test latches so EV-3 completes before EV-2.

Assertions:

- Final domain state must be valid per the state machine/version policy.
- Version 2 must not be applied as a fresh update **after** version 3 has committed.
- If EV-3 depends on EV-2, the handler must intentionally retry/defer/reject; never skip and commit the event as a success.
- Duplicate EV-2 must not emit payment/stock effects a second time.
- Offset progression must not advance ahead of durable processing without a safe handoff.

**A correct ordering key is insufficient if a downstream executor destroys ordering.** Tests must run on the real topology.

## 49. Testing poison pills, retries, and DLT

~~~text
P2 offset 71: malformed JSON
P2 offset 72: valid OrderCreated(O-502)
~~~

Checks:

- The deserializer detects malformed bytes **before `IntegrationFlow`** when appropriate.
- Errors are accurately classified as permanent vs. transient.
- Permanent poison pills go to DLT/quarantine with source position and `reasonCode`.
- Offsets are committed/skipped only after recovery is durable per policy.
- Valid offset 72 is not processed irresponsibly.
- If business logic requires strict ordering, do not treat 72 as successful while 71 remains an unresolved mandatory event.
- DLT unavailability must not cause silent ACKs/drops.
- Replaying from DLT must not cause duplicate side effects.

**Zero lag is not success if the DLT backlog grows with no owner resolving failures.** Measure both poison pill counts and recovery time.

## 50. Testing partition expansion and group migration

An integration test when a topic scales from 6 to 12 partitions:

1. Publish version 1/2 events for an order with a fixed key.
2. Record actual partition assignments.
3. Increase the partition count in the **test environment**.
4. Publish version 3 event for the same key.
5. Verify the key may route to a different partition under the active partitioner.
6. Use `aggregateVersion` or a cutover protocol to detect/prevent overwriting newer state with older state.
7. Measure backlog and rebalance impacts.

Do not write a test asserting a fixed modulo hash to claim every Kafka client shares the same mapping. What matters is **verifying correctness when mappings change**.

For **group ID migration**, test that a new group can start from `earliest/latest` depending on committed offsets/reset policy, and will **read independently of the old group**. Never switch to a new group without an explicit decision on backfilling and deduplicating business side effects.

## 51. Security and governance of partition/group configuration

Risks:

- An untrusted caller specifies `group.id`, topic, or tenant to read unauthorized streams.
- A service uses a new group ID, causing full history reprocessing.
- A test consumer group accidentally reads production topics and triggers side effects.
- DLQs hold sensitive payloads/headers with improper retention/access control.
- Polymorphic/untrusted deserializer packages expand the attack surface.
- Partition keys embed emails, phone numbers, tokens, or unnecessary personal identifiers.
- A worker is granted broader publish/consume topic permissions than required.

Controls:

1. Use Kafka ACLs/service identities, TLS/SASL per deployment, and least-privilege topic/group permissions.
2. Configure `group.id` and topic names from trusted deployment config, never directly from messages.
3. Validate deserializer schemas/types and bound message byte sizes and headers.
4. Scope business idempotency keys by tenant/source without trusting raw tenant headers.
5. Use protected DLTs/quarantines with retention, encryption, auditing, and access control.
6. Restrict which application groups are allowed on production streams.
7. Maintain a change-review process for partition counts, group IDs, retention/compaction, and offset resets.

**Consumer group ID is a subscription identity, not authorization proof for a business operation.** If a consumer processes `CancelOrderCommand`, the handler must still validate/authorize across the appropriate trust boundary.

## 52. Pre-deployment design checklist

- Identify **logical consumer applications**: who truly needs the same event stream?
- Distinguish Kafka **partitions**, consumer members, and **group IDs**.
- Choose partition keys matching the domain's **ordering scope**.
- Confirm partition count supports expected concurrency without unnecessary overhead.
- Plan for **hot keys/key skew**.
- Account for partition count changes altering key-to-partition mappings.
- Have replicas of the same logical workload share **one group ID**.
- Do not treat adding groups as a way to load-balance one consumer function.
- Choose offset/ACK policies grounded in durable completion/handoff.
- Implement transactional inbox/idempotency for replays and broker redeliveries.
- Add aggregate version/ordering checks for stateful commands.
- Verify async channels do not commit offsets prematurely.
- Establish retry/DLT/error channels classifying permanent vs. transient failures.
- Define strategies for rebalances, crash recovery, and long-running handlers.
- Secure topics/groups/headers, source/tenant identity, and DLT.
- Build tests for concurrency, duplicates/rebalances, poison pills, and migrations.
- Track metrics for per-partition lag, handler latency, business completion, and side effects.

**Even a complete checklist still requires testing against a real broker/container.** Pure Java unit tests cannot verify partition assignment, broker offsets, DLT publishing, or rebalance behavior.

## 53. Runbook when consumer lag rises after scaling

Suppose replicas were scaled from 3 to 9 yet throughput barely changed:

1. **Check partition count:** how many partitions does the topic have? With 6 partitions, 9 members cannot all hold assigned partitions from this topic.
2. **Check group IDs:** do replicas actually share the same `group.id`, or were 9 independent groups created by mistake?
3. **Check assignments:** how are partitions distributed; is there a hot partition?
4. **Check per-partition lag:** is one partition stalled or are all growing?
5. **Check handler latency:** are the DB, downstream HTTP services, locks, or connection pools saturated?
6. **Check rebalance count:** are autoscaling or long polls causing continuous ownership churn?
7. **Check poison pills/retries:** is a single offset blocking an entire partition?
8. **Check executor queues:** is Kafka lag low while async tasks remain pending?
9. **Check offset commits:** are commits happening after durable side effects?
10. **Check duplicate business effects:** are redeliveries or two groups causing double writes?
11. **Evaluate key skew:** is the partition key too coarse, like a single `merchantId`?
12. **Take action:** optimize handlers/bulkheads, scale partitions with a migration plan, fix group IDs, or adjust topology to match requirements.
13. **Verify after change:** confirm not only that lag drops, but that distinct business outcomes remain accurate.

If three groups were accidentally deployed instead of one, **do not just fix the group ID and ignore side effects that already happened**. Reconcile the DB/outbox, resolve duplicates, and inspect committed offsets/replay state before cutover.

## 54. Common misconceptions

**“Partitions and consumer groups are two alternative ways to split load; pick one.”** False. In Kafka, they are two complementary dimensions of the same subscription topology.

**“With a 6-partition topic, a consumer group can run 60 workers processing all 6 partitions in parallel.”** Not under standard partition assignment.

**“Adding consumer groups makes each event get processed faster by a single worker.”** False. Independent groups may all process the same record.

**“Same partition key always guarantees right business order.”** Not if producers race or downstream processing runs in parallel.

**“Ordering is guaranteed across the entire topic.”** False; Kafka's ordering scope is per partition.

**“One consumer receiving 6 partitions means 6 execution threads.”** False.

**“Increasing partitions is always harmless to key/order mapping.”** False; keys can map to new partitions.

**“Group IDs should include pod names to avoid conflicts.”** False if those pods are meant to share one workload.

**“`auto-offset-reset=earliest` replays from the beginning on every deploy.”** Not once the group already has valid committed offsets.

**“Committing an offset means the business transaction committed.”** Not automatically.

**“Turning auto-commit off guarantees exactly-once.”** False; you still need error/ack/transaction/idempotency policies.

**“Producer idempotence solves duplicate HTTP payments.”** False; that is a side effect in another resource.

**“Rebalances only affect latency; they cannot cause replays.”** False; uncommitted records can be reprocessed.

**“`ExecutorChannel` preserves per-partition processing order.”** Not if workers finish out of order.

**“Spring Integration's `PublishSubscribeChannel` is equivalent to a Kafka consumer group.”** False.

**“A RabbitMQ queue has the same partition counts/offsets as Kafka.”** Not for a standard queue.

**“DLT retries do not affect ordering.”** They can if subsequent records proceed ahead of the failed event.

**“Kafka lag = 0 means all child jobs finished.”** Not when async work is handled non-durably.

**“An offset is a good idempotency key for any domain.”** False; it only identifies source position within a topic/partition.

**“A new group can safely run the same side-effecting handler just because it has a different name.”** False; isolation/idempotency is required.

## 55. Practice exercise: scale cleanly without duplicating business side effects

Build a mini-project **OrderEventBrokerProcessing**:

1. Create Kafka topic `orders.events` with 6 partitions in a test environment.
2. Design `OrderEvent` with `eventId`, `tenantId`, `orderId`, `aggregateVersion`, and `type`.
3. Write a pure function building partition keys from `tenant + orderId`.
4. Use a Spring Kafka producer to publish events for the same order and inspect partition metadata.
5. Create a Spring Integration Kafka inbound adapter, `DirectChannel`, and Service Activator.
6. Configure group `inventory-reservations` with container `concurrency=3`.
7. Implement a transactional inbox + order projection + aggregate version checks.
8. Send 600 events; assert 600 distinct business completions and inspect group assignments.
9. Scale consumers to 9 on 6 partitions; observe members with no assigned partitions on the topic.
10. Create group `analytics-projection`; prove it is an independent subscription.
11. Intentionally use a per-pod group ID and observe duplicate logical consumption (with **mock side effects**, never a production DB).
12. Inject a crash after DB commit and before offset commit; assert redelivery does not double-write.
13. Test one malformed record followed by one valid record on the same partition; design DLT/recovery.
14. Insert an `ExecutorChannel`, intentionally reorder completions; add a version guard or key-serial handler.
15. Introduce a hot key, measure per-partition lag, and propose improvements.
16. Increase partitions in the test topic, verify key mapping impact and migration handling.
17. Add a 3-child Splitter and an Aggregator with failure outcome/member manifest.
18. Compare against a RabbitMQ queue with three competing consumers if a test environment is available.
19. Build a dashboard for lag, rebalances, retries, DLT, and distinct business commits.
20. Write a runbook for when scaling fails to improve throughput.

**Completion criteria:** be able to explain and prove **partitions are the storage/ordering scope; consumer groups are subscription/load balancing**; scaling produces no duplicate business side effects; replays/rebalances/poison pills are handled durably; separate groups receive independent streams; monitoring reflects both offset progress and business completion.

## 56. Key takeaways

**Partition or consumer group** is really a question about **two coordinating design choices** in Kafka: **partitions** split a topic into ordered logs; **consumer groups** determine how consumers divide partitions to jointly process one logical subscription. **Adding a consumer group** creates an independent subscriber; **adding consumers to the same group** shares workload if enough partitions exist. Do not substitute one concept for the other.

To preserve per-order ordering, choose a **message key matching the business scope**, remember Kafka orders **per partition**, and note that async flows can complete out of order. When scaling partitions, changing group membership, or rebalancing, prepare **redelivery/idempotency/aggregate version guards**. Offset commits, broker ACKs, Filter discards, Spring `errorChannel`, and business DB commits are **distinct milestones**, not inherently atomic.

In **Spring Integration**, the Kafka inbound adapter/consumer container manages groups, polling, and partition assignment; Router/Filter/Transformer/Service Activator process messages inside the flow; Splitter/Aggregator use **separate business correlation**, not the Kafka group ID as a group key. Compared with RabbitMQ/JMS, the competing-consumers goal is similar, while queue/ACK/replay semantics differ.

**Choose topology around ordering, throughput, and side-effect invariants, then prove it with integration tests against a real or isolated test broker.** A well-scaled configuration achieves target throughput without losing messages or duplicating business effects across crashes, retries, and rebalances.

### References

- Apache Kafka Documentation, **Consumer and Consumer Groups**: https://kafka.apache.org/documentation/#consumerapi
- Apache Kafka Documentation, **Design and Message Delivery Semantics**: https://kafka.apache.org/documentation/#design
- Apache Kafka Documentation, **Operations**: https://kafka.apache.org/documentation/#operations
- Spring Integration Reference, **Kafka Support**: https://docs.spring.io/spring-integration/reference/kafka.html
- Spring Integration Reference, **Message Channels**: https://docs.spring.io/spring-integration/reference/channel.html
- Spring Integration Reference, **Error Handling**: https://docs.spring.io/spring-integration/reference/error-handling.html
- Spring Integration Reference, **Aggregator**: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Kafka Reference, **Message Listener Containers**: https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html
- Spring Kafka Reference, **Handling Exceptions**: https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html
- RabbitMQ Tutorials, **Work Queues**: https://www.rabbitmq.com/tutorials/tutorial-two-java
- RabbitMQ Tutorials, **Publish/Subscribe**: https://www.rabbitmq.com/tutorials/tutorial-three-java
