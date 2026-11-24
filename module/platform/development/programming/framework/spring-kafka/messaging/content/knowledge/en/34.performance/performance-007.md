# Optimizing Partition Count

The partition count determines the maximum parallelism a consumer group can exploit, how records are distributed, and the operational cost of a topic. Choosing too few partitions can cap throughput even when the application has spare CPU and idle consumer instances. Choosing too many increases metadata, file handles, replica count, rebalance work, and storage overhead on the broker.

In Spring Kafka, partitions are a property of the Kafka topic. Listener concurrency determines how many consumers a container runs; it does not create additional partitions. To optimize, estimate actual load, measure processing capacity per partition, determine desired parallelism, and then verify through benchmarks.

## 1. How do partitions affect throughput?

A topic is divided into multiple partitions. Each partition is an ordered log stored on brokers with independent offsets. Producers write records to a partition; consumer groups distribute partitions among member consumers.

For a consumer group, at any given point in time, a partition is assigned to at most one consumer in that group. One consumer can receive multiple partitions, but two consumers in the same group do not concurrently read the same partition as independent copies.

~~~mermaid
flowchart TD
    P[Producer] --> T[(Topic: orders)]
    T --> P0[Partition 0]
    T --> P1[Partition 1]
    T --> P2[Partition 2]
    T --> P3[Partition 3]
    P0 --> C0[Consumer 0]
    P1 --> C1[Consumer 1]
    P2 --> C2[Consumer 2]
    P3 --> C3[Consumer 3]
~~~

If a topic has four partitions and a consumer group has four consumers, each consumer can receive one partition. If the group has only two consumers, each can receive two partitions. If the group has six consumers, at least two consumers will have no partitions to process when the topic only has four partitions.

Thus, partitions set the upper bound for partition-level parallelism within a consumer group. However, throughput does not scale linearly forever with partition count: databases, network, CPU, serialization, broker disk, and downstream dependencies all have their own limits.

## 2. Distinguishing partition count, concurrency, and consumer instances

These three parameters are related but distinct:

| Component | Meaning | Example |
|---|---|---|
| Partition count | Number of independent logs in a topic | Topic `orders` has 12 partitions |
| Listener concurrency | Number of consumer threads/child containers Spring Kafka creates for a listener | `concurrency = 6` |
| Application instances | Number of processes/pods running the application | 3 pods |

Suppose there are three pods, each configured with concurrency two. In total, the consumer group can have six consumers. If the topic has 12 partitions, each consumer can receive roughly two partitions depending on the assignor and group state.

If concurrency is eight per pod, total consumers can reach 24. With a topic of only 12 partitions, at most 12 consumers hold assignments in the group; the remaining consumers do not increase throughput and still incur connection, thread, and management overhead.

Example listener configuration:

~~~java
@KafkaListener(
        id = "orders-listener",
        topics = "orders",
        groupId = "order-service",
        concurrency = "6"
)
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

The concurrency value can be read from application configuration rather than hard-coded. When scaling deployments, calculate total consumers across all pods, not just concurrency on a single instance.

## 3. Estimating partitions from target throughput

One starting point is measuring the safe throughput a single partition can sustain under production-like conditions. Let:

- R: target throughput for the entire topic, in records/second.
- r_p: measured safe throughput on a single partition.
- P_r: number of partitions needed for the throughput target.

Initial estimate:

~~~text
P_r = ceil(R / r_p)
~~~

For example, the system needs to process 18,000 records/second. Benchmarks show one partition sustains around 1,500 records/second stably with acceptable latency and error rate:

~~~text
P_r = ceil(18.000 / 1.500) = 12
~~~

The result 12 is only a starting point. Per-partition capacity depends on record size, bytes/second, batch size, compression, replication, broker hardware, consumer logic, and downstream load.

Use safe throughput with headroom rather than a peak burst number from a short run. If 1,500 records/second is only reached at nearly 100% CPU or with p99 latency violating the SLO, that is not a suitable throughput figure for production sizing.

## 4. Estimating partitions from desired parallelism

Beyond throughput, consider how many consumers you want running concurrently in a group.

Let C be the number of consumers that genuinely need work in the group. For a topic, the partition count should be sufficient to supply work for that level of parallelism:

~~~text
P_c >= C
~~~

If the system has three pods and each pod needs two consumers processing the topic, desired parallelism is six. The topic must have at least six partitions to provide six assignments for that group.

Combining both initial conditions:

~~~text
P >= max(P_r, P_c)
~~~

In practice, also consider growth headroom, hot keys, broker limits, and replication cost. Do not mechanically add a reserve percentage without knowing the scaling target; define specific load-growth scenarios and test them.

Note: one consumer can process multiple partitions sequentially or per container mechanics. Adding partitions increases work-distribution potential, but does not automatically add processing threads in the application if concurrency remains low.

## 5. Using both record rate and byte rate

Records/second alone is insufficient to describe Kafka load. A topic with 1 KB events and a topic with 200 KB events have vastly different network, memory, and disk profiles.

Measure at least:

- Average and peak records/second.
- Bytes/second before and after compression.
- Average, p95, and maximum record sizes.
- Key ratio and record distribution across keys.
- Number of consumer groups reading the topic.
- Retention by time and size.
- Replication factor and broker count.

For example, 10,000 records/second with 1 KB payloads equals roughly 10 MB/second of raw payload. If average payload is 100 KB, raw load is nearly 1 GB/second before overhead and compression. The same partition count may work for the first case yet be inadequate for the second.

For systems constrained by byte throughput, size by bytes/second and benchmark realistic payload sizes. Do not increase partitions solely to fix issues caused by oversized records or serializers producing bloated payloads.

## 6. Keys determine partition distribution

When a producer sends keyed records, the Kafka partitioner normally uses the key to route records with the same key to the same partition. This is how per-key ordering is preserved in a topic.

Example:

~~~java
kafkaTemplate.send(
        "orders",
        order.orderId().toString(),
        order
);
~~~

If the key is `orderId`, events for the same order are generally sent to the same partition. Consumers can process that order's events sequentially in partition order.

Choosing a key balances two goals:

- **Ordering:** events requiring order must share the same key.
- **Distribution:** keys must be diverse enough to spread load across many partitions.

If a single shared key such as `"orders"` is used for every record, all records may land in one partition. Raising the partition count cannot fix a hot partition caused by non-diverse keys.

## 7. Identifying hot partitions and hot keys

A topic with 24 partitions does not mean load divides evenly as 1/24 per partition. If one key accounts for 40% of traffic, the partition holding that key can become a bottleneck.

Signs of a hot partition:

- Lag on one or a few partitions is dramatically higher than the rest.
- Consumers assigned the hot partition show higher processing time and CPU.
- Byte rate or record rate is heavily skewed across partitions.
- Certain keys appear with disproportionate frequency.

You can check distribution using broker/client metrics, record metadata in the consumer, or key-analysis tooling. Never look only at total group lag because the sum can mask a single congested partition.

If per-entity ordering is mandatory, hot keys must be addressed in business design or processing architecture. Splitting one key into multiple sub-keys increases distribution, but breaks ordering across that entity's events. Use salted keys only when business logic permits parallel processing with clear reconciliation/versioning mechanisms.

## 8. Increasing partitions can affect ordering

Increasing the partition count of an existing topic is commonly supported by Kafka, but carries a major consequence when producers use the default key-based partitioner.

The partitioner typically computes the partition from a hash of the key modulo the current partition count. When the partition count changes, the same key may map to a different partition for new records. Older records remain in the old partition; newer records may go to a new partition.

Example:

1. Topic has 6 partitions; events for `order-100` go to partition 2.
2. Topic is expanded to 12 partitions.
3. The same key `order-100` is sent again and may route to partition 8.
4. Both partitions are consumed independently; global ordering between old and new events is no longer guaranteed.

Kafka only guarantees ordering within a single partition. Therefore, expanding partition count can break per-key ordering assumptions if using a partition-count-dependent partitioner.

If business logic requires strict per-key ordering, pick a partition count sufficient for the expected lifecycle upfront or design a migration to a new topic with an explicit routing/ordering strategy. You can use a stable custom partitioner or managed mapping, provided both producer and consumer adhere to that contract.

## 9. Replication factor is not partition count

Two settings are frequently confused:

- **Partition count:** number of logical partitions in a topic.
- **Replication factor:** number of copies of each partition across brokers.

For example, a topic with 12 partitions and replication factor 3 has 36 total replica assignments on the cluster. Each partition has one leader and follower replicas as configured.

Replication improves fault tolerance and impacts disk/network cost; partition count affects parallelism, log distribution, and metadata. Increasing replication factor does not add consumer parallelism. Increasing partition count does not automatically improve fault tolerance if replication is inadequate.

Example topic declaration with Spring Kafka:

~~~java
@Bean
NewTopic ordersTopic() {
    return TopicBuilder.name("orders")
            .partitions(12)
            .replicas(3)
            .build();
}
~~~

Spring Kafka's `KafkaAdmin` can use `NewTopic` beans to create topics on application startup, depending on configuration and broker permissions. In production, topic creation should usually be managed via infrastructure processes to prevent individual application instances from altering topology ad hoc.

## 10. Increasing partitions on an existing topic

Kafka allows increasing partition counts, but does not support reducing partition counts directly via standard alter-partition operations. If a topic was created with too many partitions, reducing it typically means creating a new topic with fewer partitions and migrating data/producers/consumers according to plan.

Example increasing partitions using `AdminClient`:

~~~java
Map<String, NewPartitions> changes = Map.of(
        "orders",
        NewPartitions.increaseTo(18)
);

adminClient.createPartitions(changes)
        .all()
        .get(30, TimeUnit.SECONDS);
~~~

This increases from the current count to 18, rather than setting an arbitrary partition count. Before running, verify the current count, cluster limits, partition assignments, and ordering impact.

Do not automatically invoke partition increases on every application startup without control. Topic topology is an infrastructure decision with long-term effects on consumers, key mapping, and broker overhead.

## 11. Cost of too many partitions

Every partition creates metadata and state that brokers, controllers, producers, and consumers must manage. Excessive partitions can increase:

- Leader/follower replicas and ISR management overhead.
- Segment files, file handles, and log cleanup work.
- Metadata exchanged between brokers and clients.
- Separate per-partition producer batches.
- Rebalance overhead and partition distribution time.
- Consumer group offset tracking memory and structures.
- Recovery and verification time during broker restarts or partition leader elections.

More partitions can split load, yet also leave each partition with fewer records. Producers batch per partition; when records scatter across very many partitions, batches can become smaller, hurting batching and compression efficiency.

There is no universal partition limit for all clusters. Capacity depends on Kafka version, broker settings, broker count, disk capacity, workload, replication, and number of consumer groups. Base decisions on measured operational limits of your cluster rather than applying a generic rule of thumb.

## 12. Retention and storage capacity

Topic storage depends on byte throughput, retention, replication, and compression level. A rough estimate:

~~~text
Logical size ≈ byte_rate * retention_seconds
Physical size ≈ logical_size * replication_factor
~~~

For example, a topic writing 5 MB/second with 24-hour retention:

~~~text
5 MB/s * 86,400 s ≈ 432,000 MB ≈ 432 GB
~~~

With replication factor 3, theoretical total replica storage is roughly 1,296 GB, excluding segment overhead, indexes, filesystem overhead, and operational headroom. Compression can reduce actual disk usage, though the ratio depends on data and producer settings.

Partition count divides logical size across multiple logs; it does not make total data disappear. Increasing partitions can increase segment and index counts, so calculate retention and disk at both topic and cluster levels.

## 13. Choosing partition count across consumer groups

A topic can be read by multiple independent consumer groups. Partition count caps parallelism per group, not the sum of consumers across all groups combined.

For example, topic `orders` has 12 partitions:

- Group `billing` has 6 consumers: each consumer can receive roughly 2 partitions.
- Group `inventory` has 12 consumers: each consumer can receive one partition.
- Group `analytics` has 3 consumers: each consumer can receive roughly 4 partitions.

The three groups track progress independently, and each reads the entire topic in its own way. Adding groups does not increase partition count, though it adds read load on brokers and network.

When sizing, list important consumer groups, their expected concurrency, and individual SLAs. A topic might satisfy `billing` throughput yet fail `analytics` parallelism needs if that group requires more workers than partitions.

## 14. Linking partitions with batching and producer throughput

Producers group records into batches per partition. Configurations such as `batch.size`, `linger.ms`, compression, and in-flight requests govern how producers transmit data.

If partition count is too high relative to traffic, many partitions may not get enough records to fill batches quickly. This can increase small batches and reduce compression/send efficiency.

If partition count is too low, producers may concentrate traffic onto too few leader brokers, creating network or disk bottlenecks. Inspect leader distribution and broker load when evaluating throughput.

Do not add partitions just to increase batch size. Measure actual batch sizes, request rates, byte rates, and broker load. Producer settings should be tuned alongside the partitioning strategy.

## 15. Benchmarking workflow to choose partition count

A practical workflow:

1. **Describe the workload:** records/second, bytes/second, payload sizes, key distribution, retention, and consumer groups.
2. **Set targets:** throughput, p95/p99 latency, maximum lag, and expected growth.
3. **Pick a baseline:** create the topic with a moderate partition count and test-appropriate replication.
4. **Measure one partition:** determine safe throughput under realistic consumer and downstream conditions.
5. **Scale partitions gradually:** test levels like 3, 6, 12, 18; observe whether throughput keeps scaling or saturates.
6. **Test concurrency:** vary consumer concurrency and application instances to find useful parallelism.
7. **Check key skew:** confirm traffic spreads reasonably and no hot partition exists.
8. **Test failures/rebalances:** stop consumers or brokers in test scenarios to measure recovery time.
9. **Check resource cost:** observe CPU, disk, network, open files, replicas, and startup/rebalance duration.
10. **Choose a level with headroom:** meets peak load and SLOs while leaving room for reasonable growth.

Do not benchmark solely with tiny, keyless records or a dummy no-op consumer if production uses large payloads and a real database. Test workloads should mirror how producers choose keys, serializers compress data, and consumers call downstream systems.

## 16. Example sizing table

Suppose a workload has the following figures:

| Parameter | Assumed value |
|---|---:|
| Target throughput | 12,000 records/second |
| Safe throughput/partition | 1,000 records/second |
| Consumer pods | 4 |
| Concurrency per pod | 3 |
| Desired consumers | 12 |
| Partitions by throughput | 12 |
| Partitions by parallelism | 12 |

By both baseline criteria, the baseline is 12 partitions. Next, benchmark to verify:

- Can it reach 12,000 records/second with real downstream activity?
- Does traffic distribute evenly across all 12 partitions?
- Does p95/p99 latency meet the SLO at peak?
- Do brokers have sufficient disk/network and replica capacity?
- When one pod stops, can remaining consumers clear the backlog?
- When scaling out to 6 pods, does the topic have enough partitions to utilize additional consumers?

If benchmarks show throughput reaches only 8,000 records/second due to the database, increasing partitions to 24 may not help. Address the database bottleneck or reduce per-record work first.

## 17. When to create a new topic to change partitioning

Creating a new topic instead of increasing partitions directly can be appropriate when:

- You need to reduce the partition count.
- You need to change the key or partitioner while keeping ordering clear.
- You want to change schema, retention, or replication in the same migration wave.
- You need to switch from tenant-based distribution to aggregate-based distribution.
- You want full control over cutover timing and rollback.

A migration can include:

1. Creating the new topic with the chosen partition count and key strategy.
2. Deploying consumers capable of reading the new topic.
3. Moving producers to the new topic via dual-publish or a controlled cutover.
4. Reconciling event IDs/versions to detect missing or duplicate events.
5. Waiting for the new consumer group to catch up and verifying data.
6. Shifting traffic completely, then retiring the old topic per retention/runbook.

Dual-publish can create duplicates or out-of-order events without identifiers and idempotency. For per-aggregate ordering requirements, define a clear cutover point or versioning mechanism so consumers detect older vs. newer events.

## 18. Common sizing pitfalls

| Symptom | Possible cause | Suggested action |
|---|---|---|
| Consumers idle despite high lag | Partition count lower than needed consumer parallelism | Evaluate increasing partitions or optimizing processing |
| Increased partitions yet throughput unchanged | Bottleneck in DB, CPU, network, or hot key | Measure each dependency and key distribution |
| One partition has very high lag | Hot key or skewed partition assignment | Analyze key distribution and leader load |
| Many idle consumers | Concurrency/group members exceed partition count | Reduce consumers or increase partitions when justified |
| Per-key ordering broken after scaling | Keys mapped to different partitions after count increase | Design ordering-preserving routing/migration |
| Poor producer batching | Many low-traffic partitions fragmenting batches | Measure batch size and reconsider partition count |
| High broker resource consumption | Excessive partitions/replicas | Review topic topology and cluster limits |
| Cannot reduce partitions | Kafka does not support reducing partitions directly | Create a new topic and migrate |
| Prolonged group rebalances | Too many partitions or too many consumers changing at once | Measure rebalances, choose assignor, and roll out smoothly |

## 19. Pre-finalization checklist for partition count

- [ ] Measured peak record rate and byte rate.
- [ ] Measured actual payload sizes and compression.
- [ ] Benchmarked safe throughput per partition.
- [ ] Partition count suffices for desired consumer parallelism.
- [ ] Calculated total concurrency across all application instances.
- [ ] Keys distribute evenly enough without unexpected hot partitions.
- [ ] Identified per-key ordering requirements.
- [ ] Evaluated the impact of increasing partitions on key mapping.
- [ ] Kept partition count distinct from replication factor.
- [ ] Brokers have sufficient CPU, disk, network, file handles, and headroom for replicas.
- [ ] Retention and storage calculated across all replicas.
- [ ] Considered all consumer groups reading the topic.
- [ ] Benchmarked throughput, latency, lag, rebalances, and failure recovery.
- [ ] Migration plan exists if partition reduction or key strategy changes are needed.

Optimizing partition count is a balancing act between throughput, parallelism, ordering, and broker cost. Start from workload and consumer concurrency, measure safe capacity per partition, and benchmark with realistic key distributions and payloads. In particular, treat partition count as a long-term architectural decision: increasing partitions can alter key mapping, while decreasing partitions generally requires migrating to a new topic.
