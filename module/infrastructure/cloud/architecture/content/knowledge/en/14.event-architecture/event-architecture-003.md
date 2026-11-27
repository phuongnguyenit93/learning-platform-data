# Designing Topics, Partitions, and Partition Keys

## 1. Why Are Topics, Partitions, and Keys Architectural Decisions?

In an event-driven architecture, producers emit events for consumers to process independently according to business needs. A message broker or event streaming platform ingests, stores, and distributes those events. As traffic grows, a topic is typically split into multiple **partitions** to process in parallel, distribute load, and store data across independent streams. However, partitions are not just a performance setting: they affect event ordering, scalability, availability, data distribution, and how consumers recover from failures.

**The partition key** determines which partition an event goes into. If you pick an unsuitable key, all events can pile into a single partition (*hot partition*), or events belonging to the same entity can scatter across partitions, making ordering and state handling difficult. If you pick too many partitions or change the partition count without accounting for the key-mapping algorithm, your team can incur operational overhead and encounter ordering shifts during replay.

In the **CLOUD_ARCHITECTURE** module, designing event topics, partitions, and keys should start from business requirements, followed by trading off throughput, ordering, reliability, security, cost, and operations using Well-Architected thinking.

After this lesson, you will be able to:

- Distinguish events, topics, partitions, offsets, producers, consumers, and consumer groups.
- Design topics around business domains, data lifecycles, and ownership boundaries.
- Select partition keys based on business relationships, required ordering, and load distribution.
- Estimate partition counts, throughput, and the number of useful consumers.
- Identify hot keys, skew, rebalances, duplicate deliveries, and changes that affect ordering.
- Establish schema, retention, retry, monitoring, and security policies for event streams.

## 2. Core Concepts

| Concept | Meaning | Example |
| --- | --- | --- |
| **Event** | A record describing something that has happened, typically immutable once published | OrderPlaced, PaymentCaptured |
| **Topic** | Logical name for an event stream sharing a purpose or contract | orders.placed.v1 |
| **Partition** | A segment of a topic containing its own ordered sequence of records | Partition 0, 1, 2 |
| **Record / message** | Unit of data written to a partition, usually consisting of key, value, headers, and timestamp | Key order-123, payload OrderPlaced |
| **Offset** | Position of a record within a partition | Offset 1042 of partition 1 |
| **Producer** | Component that writes events to a topic | Order service |
| **Consumer** | Component that reads and processes events | Inventory projection |
| **Consumer group** | Group of consumers coordinating partition assignment to read in parallel | inventory-projection |
| **Partition key** | Value used to route a record to a partition | orderId, customerId, accountId |
| **Retention** | Policy for keeping records by time or size | Retain events for 7 days |

A topic is a naming boundary and logical contract; a partition is the unit of parallelism and ordering inside a topic. In Kafka, each partition is a log ordered by monotonically increasing offsets. **Ordering is guaranteed within a single partition**, rather than having a global order across all partitions of a topic.

~~~mermaid
flowchart TB
    Producer["Producer: Order service"] --> Topic["Topic: orders.placed"]
    subgraph T["Topic with multiple partitions"]
        P0["Partition 0: offset 0,1,2,..."]
        P1["Partition 1: offset 0,1,2,..."]
        P2["Partition 2: offset 0,1,2,..."]
    end
    Topic --> P0
    Topic --> P1
    Topic --> P2
    subgraph G["Consumer group: inventory-projection"]
        C0["Consumer A"]
        C1["Consumer B"]
        C2["Consumer C"]
    end
    P0 --> C0
    P1 --> C1
    P2 --> C2
~~~

The diagram illustrates a consumer group with three consumers and three partitions. The broker can reassign partitions when the number of consumers changes or a rebalance occurs. In a traditional consumer group, two consumers do not concurrently own the same partition; different groups can read the same topic independently.

## 3. Designing Topics Around Business Contracts

A topic should reflect a meaningful event stream and a contract mutually understood by producers and consumers. Avoid creating topics strictly one-to-one with database tables, endpoints, or team names if that does not express event semantics.

### 3.1. Choosing Topic Boundaries

- **By business event:** orders.placed, payments.captured, inventory.reserved.
- **By domain ownership:** the Order team owns order lifecycle events; the Payment team owns payment transaction events.
- **By consumption and retention needs:** audit events, integration events, and projection-update events may require different policies.
- **By sensitivity or trust level:** events containing sensitive data may require dedicated topics and access controls.

Avoid generic catch-all topics like events or messages when they bundle too many unrelated contracts. Consumers may end up reading, filtering, and discarding most records, and least-privilege access becomes difficult to enforce.

### 3.2. A Topic Is Not Synonymous with an Event Type

A topic can hold a single event type or multiple types sharing a contract and operational requirements. If bundling multiple event types, each record needs an explicit type/version field and corresponding schema registry/validation.

| One topic per event type | Multiple event types in one topic |
| --- | --- |
| Easy to manage separate schemas, ACLs, retention, and routing | Fewer topics and less metadata; convenient for streams with shared ownership |
| Increases number of topics, partitions, and configurations | Consumers must discriminate by type; policies can be harder to separate |
| Suited to events with differing lifecycles/criticality | Suited to events with similar contracts and operations |

There is no universally optimal topic count. Define the owner, schema, retention, key, consumers, access permissions, and change process for each topic.

### 3.3. Topic Naming and Versioning

Topic names should be consistent, describe the domain and action, and avoid embedding environment names if the platform already separates clusters/namespaces by configuration. Examples:

~~~text
orders.placed.v1
orders.cancelled.v1
payments.captured.v1
inventory.reserved.v1
~~~

Putting a version in the topic name is just one strategy. Some systems manage versions in a schema registry or headers. When a contract changes:

- Adding optional fields with defaults can be backward-compatible if consumers support it.
- Breaking changes such as altering semantics, removing required fields, or changing encoding may require a new topic/version and a migration phase.
- Do not change the meaning of an old event while keeping the same name/schema version; legacy consumers may misinterpret it.
- Define a dual-support window for legacy producers/consumers, along with cutover, replay, and retirement dates for the old topic.

## 4. Partitions: Bounded Parallelism

Partitions split a topic into multiple independent logs. In Kafka, each partition has a leader serving reads/writes and may have replicas on other brokers for fault tolerance according to replication settings. Consumer groups use partitions as the unit of assignment, so the partition count caps the maximum parallelism of a group for that topic.

### 4.1. What Do Partitions Affect?

1. **Throughput:** more partitions allow producers/consumers to distribute work across multiple brokers and workers, provided workload and broker capacity support it.
2. **Ordering:** order is guaranteed only within each partition. Related events need the same key to be routed consistently.
3. **Consumer parallelism:** a traditional consumer group cannot have multiple independent consumers reading the same partition to boost throughput; excess consumers sit idle.
4. **Storage and replication:** each partition adds metadata, log segments, file handles, leader/replica state, and recovery work.
5. **Rebalances:** membership or assignment changes can transfer partition ownership and briefly pause consumption.
6. **Retention and recovery:** partition count affects disk layout, replica recovery time, and operational efficiency.

More partitions do not automatically make a single partition write faster. If all events with the same key funnel into one partition, that partition remains the bottleneck.

### 4.2. Effective Consumer Count

For a topic with P partitions and a traditional consumer group with C consumers, the maximum number of consumers that can directly process partitions in parallel is:

$$
C_active = min(P, C)
$$

If there are 3 partitions and 8 consumers in the same group, at most 3 consumers are assigned partitions; the remaining 5 consumers process nothing for that topic. If there are 12 partitions and 3 consumers, each consumer can be assigned multiple partitions.

This cap only describes partition assignment; actual throughput also depends on per-record processing speed, batching, network, disk, brokers, topic count, and downstream dependencies.

### 4.3. Partition Count and Replication Factor Are Separate Decisions

- **Partition count** determines the number of independent logs, load distribution, and parallelism.
- **Replication factor** determines how many copies of each partition exist across brokers.
- **min.insync.replicas** and producer acknowledgment policies determine write durability guarantees when brokers fail.

Increasing partitions does not increase tolerance for broker failures; increasing the replication factor does not increase consumer parallelism. Choose them independently based on throughput, durability, availability, and cost.

## 5. Choosing Partition Keys by Business Semantics

The partition key is often the single most important choice for keeping related events in the same partition. In Kafka, producers use a partitioner to map a key to a partition; a common default is hashing the key modulo the partition count, though the exact algorithm depends on the client/partitioner and configuration.

### 5.1. Choosing Keys for Required Ordering

Ask: **Which events must be processed in relative order?**

| Business flow | Ordering to preserve | Candidate key |
| --- | --- | --- |
| Status of an order | Placed → paid → cancelled/refunded per order | orderId |
| Balance of an account | Debits/credits for the same account | accountId |
| State of an IoT device | Readings/commands for the device | deviceId |
| State of a customer | Profile updates for the same customer | customerId |
| Inventory by SKU/warehouse | Adjustments for the same stock unit | warehouseId + sku |

If the key is orderId, all events for the same order normally land in the same partition as long as partition count and partitioner do not change. That lets consumers process events for that order sequentially by partition, while other orders are spread out.

### 5.2. A Key Does Not Have to Be a Database Primary Key

A primary key identifies a record in a database; a partition key defines **the unit that must stay co-located and ordered** in a stream. They can be the same value, though they do not have to be.

For instance, orderId works well for keeping an order lifecycle together; however, a consumer aggregating credit limits by customerId needs orders for a given customer in the same partition if logic requires per-customer ordering. You may need another stream/projection with its own key, or design the consumer with explicit concurrency and versioning handling.

### 5.3. Empty or Null Keys

If a producer omits the key, the partitioner may distribute records via round-robin, sticky partitioning, or another mechanism depending on client/version. This can improve load balancing but does not preserve per-entity ordering. Avoid null keys when business logic requires serializing changes to the same entity.

Keys must be stable and have a canonical representation. Avoid unstable object serialization, standalone timestamps, or values that change across events for the same entity. If a key contains personal data, consider an internal ID or tokenization to avoid exposing data in logs/monitoring.

## 6. Key Distribution and Hot Partitions

### 6.1. Cardinality and Load Skew

A partition key's **cardinality** is the number of distinct values that can occur. High cardinality generally enables better distribution, though it does not guarantee uniform load. If one key occurs at a disproportionately high rate, the partition receiving that key bears heavier load.

Examples:

- eventType has only 4 values, and one type accounts for 90% of events: load easily concentrates on one partition or a small subset.
- countryCode has few values; if one country generates most traffic, its corresponding partition can run hot.
- customerId has many values, yet one enterprise customer emits millions of events: a single key can still become a hot key.
- orderId has high cardinality and traffic is usually spread out; an order burst can still create a short-lived hot key.

### 6.2. Illustrative Load Distribution Example

Suppose a topic has 8 partitions and 100,000 events/second:

| Key choice | Assumed distribution | Consequence |
| --- | --- | --- |
| No key, sticky/round-robin | Roughly 12,500 events/s per partition in an ideal case | More balanced, but loses per-entity ordering |
| eventType where one type is 80% | A few partitions receive most of the data | Hot partition; consumers cannot increase parallelism for that key |
| orderId with many values | Traffic spreads across partitions if hashing and load are fairly even | Preserves per-order ordering |
| customerId with one very large customer | That customer's partition may receive an overwhelming share | Needs hot-key mitigation if logic allows decomposition |

These numbers are illustrative; hash partitioning does not guarantee each key sits in its own partition, and actual distribution must be measured on your system's key data.

### 6.3. Detecting Hot Partitions

- Monitor bytes in/out, record rates, and request latency per partition/broker.
- Compare consumer lag per partition; one partition with steadily rising lag while others sit idle signals skew.
- Analyze key frequencies via sampling or safe telemetry; avoid logging full sensitive keys.
- Measure key load percentiles, not just average cardinality.
- Correlate partition load with broker leaders, disk, network, and consumer processing time.

### 6.4. Mitigating Hot Keys Without Breaking Ordering

1. **Choose a better key:** replace eventType or broad tenant keys with a more evenly distributed entity key, if business ordering allows.
2. **Split topics by load domain:** isolate high-traffic or distinct-policy streams.
3. **Logical sharding (key salting):** append a shard suffix to spread load, but only when total ordering across the whole key is not required and a proper aggregation step exists.
4. **Separate update streams:** coalesce/batch events or move to a compacted state stream where appropriate.
5. **Optimize consumers:** batch processing, efficient I/O, fewer synchronous calls, and increased downstream capacity.

Do not simply add partitions and expect a hot key to distribute itself. A single key still maps to a single partition in a topic if key semantics remain unchanged.

## 7. Ordering: At What Scope Is Order Preserved?

Kafka guarantees that records within the same partition are read in offset order. The broker appends records to the log and consumers read in that order. However, **there is no global ordering between partition 0 and partition 1**. Separate consumer groups also advance at independent speeds and offset positions.

~~~mermaid
flowchart TB
    subgraph P0["Partition 0"]
        A1["Order A: placed"]
        A2["Order A: paid"]
        A3["Order A: shipped"]
        A1 --> A2 --> A3
    end
    subgraph P1["Partition 1"]
        B1["Order B: placed"]
        B2["Order B: cancelled"]
        B1 --> B2
    end
    P0 -. "No global ordering with P1" .- P1
~~~

If events for order A and order B sit in different partitions, a consumer may receive event B before finishing event A. That is not a broker bug; it is the result of parallel processing.

### 7.1. Ordering Does Not Replace Versioning and Idempotency

Even when the same entity uses a single key, consumers still must handle:

- **Duplicate delivery:** events may be reprocessed when offsets have not committed or after failures.
- **Producer out-of-order emission:** upstream services may emit events out of business sequence; the broker does not reorder them.
- **Replay/backfill:** new consumers may read history and interact with current state.
- **Concurrent producers:** two producers writing the same key may not produce the desired business order without coordination.
- **Retry topics:** retrying via another topic can cause newer events to be processed before an event waiting to retry.

Use an aggregateVersion, sequence number, or business event time when you need to detect stale/out-of-order updates. An idempotency key/eventId helps consumers eliminate duplicate side effects; offset commits must align with data persistence.

### 7.2. Producer Idempotence and Transactions

Kafka producer idempotence reduces duplicates caused by producer-layer retries within supported semantics; it does not automatically make consumers process external databases exactly once. Kafka transactions can coordinate reading/writing Kafka topics and committing offsets within a Kafka transaction under an appropriate model, but they do not automatically wrap a PostgreSQL transaction or payment API.

If a consumer writes to a database and then commits its offset, crashing between those two steps can cause the record to be redelivered. You need idempotent database writes, an inbox/dedup table, or a suitable coordination mechanism. Do not advertise end-to-end exactly-once simply by toggling a single producer setting.

## 8. Changing Partition Counts and Its Impact on Key Mapping

In partitioners based on hash modulo partition count, the partition is conceptually computed as:

$$
partition = hash(key) mod P
$$

When P changes, the same key can map to a different partition. Consequently, new events for an entity may go to a new partition while older events remain in the old partition. If consumers read concurrently, **per-entity ordering can break during the transition window**.

Not every client and partitioner uses the exact modulo formula; sticky partitioning, custom partitioners, and consistent hashing can behave differently. Even so, **partition topology is part of routing semantics**, so changing partition counts requires planning.

### 8.1. When Should You Increase Partitions?

- Higher throughput is needed and brokers have capacity.
- The consumer group needs more parallelism and logic can scale by key.
- Data volume grows and existing partitions hit reasonable storage/throughput limits.
- A transition plan exists to safeguard ordering and key mapping.

### 8.2. Safe Transition Options

- **Create a new topic version:** move producers to the new topic with the updated partition count; use controlled cutover/drain/replay.
- **Keep partition counts stable:** provision sensible capacity headroom initially rather than resizing frequently.
- **Epoch/shard-map routing:** for specialized systems, manage an explicit versioned key→partition map; validate correctness thoroughly.
- **Dual-publish and reconcile:** write to both topics during transition, provided consumers deduplicate and enforce cutover ordering.

Do not delete or recreate a topic just to reset partitions without a plan for retention, replay, ACLs, consumer offsets, and data recovery.

## 9. Compaction, Retention, and Keys

Topics with a **delete** cleanup policy retain records by time or size and purge older log segments once eligible. **Compacted** topics retain the latest record per key during compaction, fitting certain state streams. Many configurations support combining delete and compact with specific semantics.

| Topic type | Used for | Role of key |
| --- | --- | --- |
| Event history, time-based retention | Event history, audit, or integration | Preserves per-entity ordering and grouping |
| Compacted state topic | Current state snapshot per entity | Identifies which record is retained after compaction |
| Retry / DLQ topic | Failed events or events needing investigation | Preserves correlation; requires retry metadata |

A tombstone (a record with a key and null value in a compacted topic) typically signals key deletion during compaction; it is not an immediate deletion command and does not replace retention/backups. Consumers must understand tombstones and the configured tombstone retention window.

Retention must account for replay, audit, privacy/deletion rules, disk costs, replication, consumer catch-up speed, and broker capacity. An event stream does not automatically become an infinite historical archive.

## 10. Designing Producers and Partition Keys in Code

Java example with a Kafka producer: the key is orderId and the value is the serialized event. This snippet focuses on routing and does not represent a full production configuration.

~~~java
ProducerRecord<String, OrderPlaced> record =
    new ProducerRecord<>(
        "orders.placed.v1",
        event.orderId(),   // partition key
        event
    );

producer.send(record, (metadata, exception) -> {
    if (exception != null) {
        // Log send failure; handle retries per policy,
        // do not retry indefinitely inside the callback.
        logger.error("Failed to publish OrderPlaced", exception);
        return;
    }
    logger.info(
        "Published order event to partition={}, offset={}",
        metadata.partition(),
        metadata.offset()
    );
});
~~~

The producer record supplies the string key orderId; the partitioner chooses the partition based on the key and configuration. In production, configure bootstrap servers, serializers, TLS/SASL, idempotence, acks, retries, delivery timeout, and error handling. Never log sensitive payloads.

### 10.1. Sample Producer Configuration

~~~properties
bootstrap.servers=broker-1.example.internal:9093,broker-2.example.internal:9093
key.serializer=org.apache.kafka.common.serialization.StringSerializer
value.serializer=org.apache.kafka.common.serialization.ByteArraySerializer
acks=all
enable.idempotence=true
delivery.timeout.ms=120000
request.timeout.ms=30000
max.in.flight.requests.per.connection=5
~~~

This configuration is illustrative; client and broker versions have differing defaults and compatibility behavior. If using custom serializers or a Schema Registry, configure the matching serializer. acks=all and idempotence improve producer send reliability but do not guarantee the consumer has committed the event to a database.

## 11. Consumer Groups, Assignment, and Rebalances

A consumer group divides partitions among its members for parallel processing. When a member joins, misses heartbeats, leaves the group, or partition counts change, the broker/client can trigger a rebalance.

### 11.1. How Do Rebalances Affect Processing?

- Consumers may briefly pause fetching/processing while partitions are revoked and reassigned, depending on protocol/strategy.
- If record processing takes too long, missed polls/heartbeats can cause a consumer to be considered dead.
- Newly assigned partitions resume from the last committed offset, so uncommitted records are reread.
- If offsets are committed before the DB write succeeds, records can be lost from the consumer's perspective.
- If offsets are committed after the DB write and a crash happens in between, records can be processed twice.

### 11.2. Offset Management

An offset tracks the consumer's read position in **each partition**. Only acknowledge progress after required side effects complete or when idempotency protects reprocessing.

With parallel batch processing within a partition, commit only the highest contiguous completed offset; never commit past an in-flight record, or a crash could skip it.

### 11.3. Consumers Exceeding Partition Count

If a topic has 6 partitions and a group has 10 consumers, at most 6 consumers receive partitions; 4 consumers sit idle. When higher throughput is needed, adding partitions can help, but only if producers, brokers, downstream systems, and key distribution support it. Often optimizing batching, queries, compression, or consumer logic is more effective than adding partitions.

## 12. Estimating Partition Count and Throughput

There is no single sizing formula suited to every broker. A preliminary model can be used:

- R: total record rate to process (records/second),
- r: sustained throughput measured for one partition under load testing,
- P: number of partitions.

Estimate:

$$
P >= ceil(R / r)
$$

For example, with a target load of 24,000 records/second and load tests showing one partition handles 3,000 records/second steadily:

$$
P >= ceil(24000 / 3000) = 8
$$

The number 8 is a **theoretical starting point**, before factoring in headroom, replication, skew, record size, network, disk, downstream consumers, rebalances, and recovery requirements. If a hot key accounts for 40% of load, scaling from 8 to 16 partitions still may not relieve the partition holding that key.

### 12.1. Sizing by Consumer Throughput

If a single consumer steadily processes q records/second and total target rate is R, the approximate number of consumers needed is:

$$
C >= ceil(R / q)
$$

Because each consumer group relies on distinct partitions for parallelism, the partition count must be large enough to assign to those consumers. Yet excessive partitions raise broker overhead, memory usage, file handles, metadata, recovery time, and rebalance cost.

### 12.2. Message Size

Records/second alone does not tell the whole story when record sizes vary. Measure bytes/second, compression ratios, batch sizes, maximum message sizes, request sizes, and network bandwidth. A topic with 10,000 events/second at 1 KB each looks very different from 10,000 events/second at 1 MB each.

## 13. Topic-Level Security and Access Control

Topics serve as practical ACL and governance boundaries. Avoid letting every producer/consumer read and write every topic.

- **Producer ACLs:** only the owning service may write to topics it owns.
- **Consumer ACLs:** only teams/services needing the data may read; avoid wildcards without justification.
- **Consumer group ACLs:** restrict who can use specific group IDs when supported by the broker.
- **Schema governance:** restrict who can register schemas, change compatibility, and delete versions.
- **Encryption in transit:** TLS between producers, brokers, and consumers; rotate certificates/credentials.
- **Encryption at rest:** encrypt storage and backups per cloud/broker policy.
- **Sensitive keys:** avoid using emails, phone numbers, or personal data directly as keys if they may appear in logs/metrics.
- **Data minimization:** events should only include required fields; account for retention, right-to-erasure, and masking.

If the key is customerId, use an internal ID or stable token rather than email/phone. However, if you need the same customer to stay on the same partition, the token must remain deterministic across secret versions; key rotation requires planning so entities do not unexpectedly jump partitions.

## 14. Operating and Monitoring Topics and Partitions

Monitor brokers, topics, partitions, producers, consumers, and downstream systems. Dashboards showing only aggregate throughput can mask hot partitions or lagging consumer groups.

| Layer | Metrics / signals |
| --- | --- |
| Topic | Partition count, retention, replication factor, bytes/records in/out |
| Partition | Leader distribution, replica ISR, size, traffic skew, under-replicated partitions |
| Broker | Disk utilization, network throughput, request latency, CPU, memory, request queue |
| Producer | Send latency, retries, error rate, batch size, compression, record size |
| Consumer group | Lag per partition, processing rate, rebalance count/duration, commit failures |
| Downstream | DB saturation, API rate limits, processing latency, DLQ growth |

### 14.1. Consumer Lag

Consumer lag is the distance between a partition's latest written offset and the offset processed/committed by the consumer, as defined by your monitoring tool. Sustained lag growth can stem from slow consumers, too few consumers, partition skew, overloaded downstream systems, or failing consumers.

Do not watch only total lag. Track maximum lag and oldest record age per partition; a single hot partition can stall even when total lag looks small.

### 14.2. Leaders and Replicas

Monitor leader imbalance, under-replicated partitions, offline partitions, ISR shrinks, and recovery times. High replication factors require adequate disk/network and replication throughput; if brokers lack capacity, increasing replication can slow the system down.

### 14.3. Runbook for Rising Lag

1. Identify the affected group, topic, and partitions with the highest lag.
2. Compare records/bytes in against processing/commit rates; check for key or partition skew.
3. Inspect consumer errors, retries, rebalances, and per-record processing time.
4. Check downstream dependencies such as databases, API rate limits, object storage, and connection pools.
5. Scale consumers only if spare partitions and downstream capacity exist; otherwise fix the bottleneck or throttle producer rates.
6. Monitor backlog age, lag, and SLOs after changes; update the runbook if the root cause recurs.

## 15. Reliability: Retry Topics, Dead Letters, and Replay

A consumer should not block an entire partition indefinitely over a single failing record. Yet routing every error straight to a DLQ can break business semantics or ordering. Classify errors instead:

| Error | Common handling approach |
| --- | --- |
| Transient downstream failure | Retry with backoff, capped attempts, and deadlines |
| Invalid schema/payload | Dead-letter, alert, preserve metadata for investigation |
| Business rule violation | Record rejection or emit review event; do not retry blindly |
| Credential/permission error | Pause or throttle consumer and alert; avoid flooding DLQ |
| Downstream overload | Apply backpressure, lower concurrency, controlled pause |

Retry topics create separate flows and can alter ordering. For example, if OrderPlaced is retried while PaymentCaptured for the same order is already processed, state can become corrupted. Options include:

- Retry in-place on the same partition with pause/backoff, accepting bounded blocking for that key/partition.
- Use a retry topic carrying attempt/next-retry metadata with entity/version-aware consumers enforcing order.
- Separate technical failures from business events; use durable state machines or workflows.
- Dead-letter as a last resort after thresholds are exceeded, with replay procedures after fixes and idempotency tracking.

DLQ records should retain original topic/partition/offset, key, headers, schema version, exception class, and timestamp, while stripping or masking unnecessary sensitive payloads. Reprocessing requires an owner, approval, and safeguards against duplicate side effects.

## 16. Well-Architected: Trade-offs to Evaluate

| Perspective | Topic/partition/key decision | Trade-off |
| --- | --- | --- |
| **Operational Excellence / Operations** | Topic ownership, schema registry, partition plans, IaC, and runbooks | Good conventions reduce errors but require governance and automation |
| **Security** | Topic/group ACLs, TLS, encryption at rest, key privacy | Narrow permissions reduce exposure but increase identity and rotation management |
| **Reliability** | Replication, acks, ISR, idempotency, retention, and replay | Higher durability costs disk/network and latency |
| **Performance Efficiency** | Partition count, key distribution, batching/compression | More partitions boost parallelism but raise overhead and rebalance impact |
| **Cost Optimization** | Throughput sizing, retention, replication, consumer capacity | Longer retention and replicas raise storage/egress; too few partitions grow backlogs |
| **Sustainability** | Reduce redundant records, right-size retention, compression, and capacity | Saving resources must preserve headroom for peaks and recovery |

Do not optimize purely for throughput if business logic requires ordering or auditing. Do not optimize purely for ordering by dumping all events into one partition if the system must scale. **Keys and partitions should reflect the smallest serialization boundary the business truly needs.**

## 17. Practice Lab: Designing an E-Commerce Event Stream

An e-commerce platform emits OrderPlaced, PaymentAuthorized, OrderCancelled, InventoryReserved, and ShipmentCreated. There are three consumer groups: inventory projection, customer notification, and analytics. Peak load is projected at 30,000 events/second, with one enterprise customer generating 25% of total events during a campaign. The inventory consumer must preserve exact order of changes for the same order; analytics can process with higher latency.

**Assignment Requirements:**

1. Define topic boundaries, owners, and schemas/versions for the events; explain which events belong together or in separate topics.
2. Choose a partition key for the order lifecycle topic and explain why orderId, customerId, or eventType is suitable or unsuitable.
3. Propose an initial partition count from measured or assumed load-test throughput; state headroom, replication factor, and consumer limits.
4. Analyze the hot key caused by the enterprise customer generating 25% of traffic; propose at least two skew-mitigation strategies and state their ordering impact.
5. Explain consumer group assignment for 12 partitions with 3, 12, and 16 consumers; state which consumers are idle.
6. Design retry, DLQ, and replay for InventoryReserved failing due to database timeouts; ensure no duplicate side effects occur.
7. Outline a plan to increase partitions or migrate to a new topic version without breaking per-order event ordering.
8. Propose dashboards/alerts for producer latency, partition skew, under-replicated partitions, and consumer lag.
9. Write an ADR for the partition key and partition count, including triggers for revisiting the decision as traffic or business rules evolve.

### Evaluation Hints

A solid design explicitly states **which entity requires ordering**, how keys distribute, and the desired parallelism. If inventory must process per order, orderId is usually the natural candidate for the order lifecycle stream; however, if a customer hot key is an issue, you cannot switch to a random key and still expect automatic per-order ordering. You can separate streams, apply two-tier partitioning, or use explicit versioning/dedup handling.

Partition count must be grounded in throughput measured in an equivalent environment, not derived backward from a desired consumer count. If the partition count is larger than the consumer count, there are idle consumers; if the consumer count exceeds the partition count, adding consumers does not increase parallelism for the group.

## 18. Pre-Production Topic Checklist

- [ ] Topic has a defined purpose, owner, event contract, and consumers.
- [ ] Partition key reflects the entity requiring ordering and has measured load distribution.
- [ ] Cardinality, hot keys, key privacy, and campaign skew have been evaluated.
- [ ] Partition count is based on load-tested throughput/record size, consumer parallelism, and headroom.
- [ ] Replication factor, acks, min ISR, and durability are chosen independently of partition count.
- [ ] Policies exist for schema compatibility, versioning, migration, and replay.
- [ ] Appropriate retention, compaction, tombstones, and privacy/deletion rules are in place.
- [ ] Consumer groups, offset commits, rebalances, and idempotency have been tested.
- [ ] Retries, DLQ, backoff, ordering, and replay have owners and runbooks.
- [ ] Least-privilege ACLs for producers/consumers/groups, TLS, and encryption at rest are configured.
- [ ] Metrics include lag per partition, throughput, latency, ISR, skew, and downstream saturation.
- [ ] Changing partition counts has a key-remapping and ordering plan.
- [ ] Load tests cover warm/peak/burst traffic, broker failures, consumer rebalances, and downstream outages.
- [ ] Total cost of brokers, storage, replication, network, retention, and operations is approved.

**Key takeaway:** Topics define the contract of an event stream; partitions define independent logs for load distribution and parallel processing; keys determine which events stay together to preserve per-entity ordering. Good design chooses keys by **business semantics**, chooses partitions by **measured throughput and parallelism**, and treats hot keys, rebalances, retries, retention, and topology changes as architectural decisions with long-term impact.
