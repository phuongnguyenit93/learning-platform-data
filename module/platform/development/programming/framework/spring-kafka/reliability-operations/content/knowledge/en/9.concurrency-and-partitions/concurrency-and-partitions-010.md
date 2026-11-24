# Uneven Partition Distribution

In Kafka, a partition is the unit of storage, reading, and parallel processing. A topic with multiple partitions can be processed concurrently by multiple consumers in a consumer group. However, having many partitions does not automatically guarantee evenly balanced load. Some partitions may receive most records, contain larger records, or be assigned unevenly to one consumer. As a result, one consumer or broker becomes overloaded while others sit idle.

When investigating this phenomenon, distinguish three layers of issues:

1. **Producer distributing data unevenly:** keys or the partitioner cause certain partitions to receive more records/bytes.
2. **Consumer group assigning partitions unevenly:** the assignment strategy or topic topology leaves one consumer holding more partitions than others.
3. **Broker leader/replica placement uneven:** one broker handles more read/write traffic than the remaining brokers.

These three issues can occur simultaneously, yet require different fixes. Increasing `concurrency` only helps when unassigned partitions exist; it does not automatically split a hot partition into multiple independent streams.

## 1. Partitions Are the Boundary of Parallelism and Ordering

Kafka only guarantees record ordering within a single partition. At any point in time, a consumer group assigns a partition to at most one consumer member for processing. Therefore, partition count limits the group's maximum parallelism for that topic.

For example, the `orders` topic has six partitions:

```text
Topic orders
  partition 0  ----> consumer A
  partition 1  ----> consumer A
  partition 2  ----> consumer B
  partition 3  ----> consumer B
  partition 4  ----> consumer C
  partition 5  ----> consumer C
```

Three consumers can process six partitions in parallel, each holding two partitions. If there were only two partitions, adding a third consumer would not increase concurrent reading streams in the group: at least one consumer would receive no partitions.

However, equal partition counts do not equal balanced load. If partition 0 receives 70% of all records, consumer A can still be overloaded even though every consumer holds exactly two partitions. Examine both assigned partition counts and the actual workload of each partition.

## 2. Distinguishing Three Types of Imbalance

| Type of imbalance | Symptom | Common causes | Primary remediation |
|---|---|---|---|
| Producer data skew | A few partitions have much higher records/bytes | Hot keys, low key cardinality, partitioner, or skewed data distribution | Redesign keys, routing, or load-splitting strategy. |
| Consumer assignment skew | One consumer holds more partitions or skewed total load | Assignment strategy, multiple topics with differing partition counts, mismatched consumer count | Choose an appropriate assignor, adjust partition/consumer counts. |
| Broker skew | One broker has higher leader traffic, disk, or network usage | Concentrated partition leaders, replica placement, or skewed client load | Reassign partitions and balance leaders/replicas. |

Before changing configuration, identify which layer is causing the bottleneck. For instance, switching from `RangeAssignor` to `RoundRobinAssignor` can balance partition counts across consumer members, yet will not stop a hot key from writing to the same partition.

## 3. Producers Distributing Records Across Partitions

When a producer sends keyed records, the default partitioner typically hashes the key to select a partition. Records with the same key are consistently routed to the same partition within a stable partition topology, allowing Kafka to preserve ordering for records of that key.

Example:

```java
kafkaTemplate.send("orders", order.getCustomerId(), order);
```

If one customer generates most orders, the partition holding that customer's key can run much hotter than other partitions. If the key only has a few distinct values such as `region`, `status`, or a constant, records may concentrate into very few partitions.

For unkeyed records, producer partitioners may use different distribution/batching strategies. Therefore, inspect actual keys, serializers, partitioners, and producer configuration before assuming Kafka spreads records evenly.

### 3.1 Hot Keys and Low Cardinality

A hot key is a key appearing at a much higher rate than other keys. For example, a system has millions of customers, yet one major customer generates 40% of total events. If the partitioner uses `customerId`, all records for that customer go to the same partition.

```text
customerId = C-001  -> partition 2: 40% traffic
customerId = C-002  -> partition 5:  2% traffic
customerId = C-003  -> partition 0:  1% traffic
customerId = C-004  -> partition 4:  1% traffic
other customers    -> remaining partitions
```

A hot partition can cause:

- Continuously growing lag on the consumer handling that partition.
- Higher CPU or processing duration on the consumer holding the hot partition compared to peers.
- Higher producer latency or inefficient batching when writing to that partition.
- Records of the same key queuing in order, bounding throughput to a single consumer thread.

Increasing partition count does not fix a hot key on its own. The same key still hashes to a single partition in the new topology; expanding partitions can merely move that key to a different partition rather than splitting records of that key across multiple partitions.

### 3.2 Choosing Keys Based on Ordering Requirements

The key should reflect the unit for which business logic requires ordering. If per-order ordering is needed, `orderId` may fit. If per-customer ordering is needed, `customerId` is the natural choice, though a high-volume customer can create a hot partition.

Do not pick a key solely for a balanced histogram if doing so breaks business semantics. Switching from `customerId` to another key lets events for the same customer land across multiple partitions and run concurrently, losing global per-customer ordering.

If a hot key strictly requires ordering, consider capping that key's throughput, optimizing processing, isolating large tenants, or splitting flows with a business design that includes an explicit aggregation/sequencing step.

### 3.3 Salting and Splitting a Hot Key

When business rules allow parallel processing of events for a single key, you can append a shard/salt to the routing key:

```java
int shard = Math.floorMod(event.getEventId().hashCode(), 8);
String partitionKey = event.getCustomerId() + "-" + shard;

kafkaTemplate.send("customer-events", partitionKey, event);
```

This spreads one customer's load across multiple partitions. However, records for that customer are no longer ordered relative to one another. If downstream needs aggregated per-customer state, an explicit merge step, versioning, or synchronization mechanism is required.

Other options include:

- Moving very large tenants to a dedicated topic with dedicated partitions and consumers.
- Splitting events by task type if each type can be processed independently.
- Introducing an intermediate processing tier to coalesce or throttle the hot key's rate.
- Rate-limiting at the source so the hot partition does not exceed processing capacity.

Salting is appropriate only when semantics tolerate losing original key order. Do not apply it as a purely technical optimization without verifying business impact.

## 4. Expanding Partitions Can Change Key Distribution

With partitioners based on hashes and partition counts, changing the partition count can remap many keys to different partitions. For example, a key previously routed to partition 2 in a six-partition topic may map to a different partition after expanding to ten partitions.

This has several consequences:

- New records for the same key may land in a different partition than older records.
- There is no global ordering between old and new records across two partitions.
- The consumer group may rebalance when topology changes or consumers discover new partitions.
- Stateful processing tied to partition ownership may need state migration/rebuilding.

Therefore, increasing partitions is a topology change that requires planning. Check whether the application relies on long-lived per-key ordering, partition-local state, or replay procedures. For keys requiring strict ordering over time, partition expansion must be tested and rolled out carefully.

## 5. Consumer Assignments Can Be Uneven

A Kafka consumer group uses a partition assignor to divide subscribed partitions among members. Spring Kafka creates consumers from listener containers; when `concurrency` is configured, one container can create multiple consumer threads/members joining the group.

Example concurrency configuration:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, Order> orderFactory(
        ConsumerFactory<String, Order> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, Order>();
    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(6);
    return factory;
}
```

With one application replica, this factory creates up to six consumers for the listener container. With three replicas in the same group, total members can reach 18 for that listener. Partition count and assignment strategy determine which members receive partitions.

### 5.1 RangeAssignor

`RangeAssignor` divides each topic's partitions into contiguous ranges across consumer members. For a single topic, counts are usually fairly balanced; if partitions do not divide evenly by consumers, a few members receive one extra partition.

The imbalance becomes more obvious when a group subscribes to multiple topics with similar partition counts. Range assignor divides each topic independently, so the same member can receive the remainder from multiple topics.

Example with two topics `orders` and `payments`, each with three partitions, handled by two consumers:

```text
Range assignment (illustrative)

Consumer A: orders-0, orders-1, payments-0, payments-1  -> 4 partitions
Consumer B: orders-2, payments-2                        -> 2 partitions
```

Partition counts per member differ even though both topics have the exact same partition count.

### 5.2 RoundRobinAssignor

`RoundRobinAssignor` distributes partitions cyclically across compatible group subscriptions. In the example above, partitions can be interleaved so both consumers receive nearly equal counts:

```text
Round-robin assignment (illustrative)

Consumer A: orders-0, orders-2, payments-1  -> 3 partitions
Consumer B: orders-1, payments-0, payments-2 -> 3 partitions
```

This is worth considering when a group subscribes to multiple topics and RangeAssignor produces skewed partition counts. However, RoundRobinAssignor still balances partition counts, not record counts, record sizes, or processing times.

### 5.3 CooperativeStickyAssignor

`CooperativeStickyAssignor` tries to preserve existing assignments where possible while rebalancing partitions to keep members balanced as the group changes. Its cooperative mechanism allows incremental rebalances, reducing full-stop revocations compared to eager rebalancing.

This assignor is helpful when applications need to minimize disruption during scaling or rollouts. However, stickiness prioritizes assignment stability; it neither detects high-traffic partitions automatically nor splits a hot partition across multiple consumers.

### 5.4 Choosing an Assignor in Spring Kafka

You can configure the consumer property `partition.assignment.strategy` via Spring Boot:

```yaml
spring:
  kafka:
    consumer:
      properties:
        partition.assignment.strategy: org.apache.kafka.clients.consumer.RoundRobinAssignor
```

Or select cooperative sticky if your Kafka client version and entire consumer group support that strategy:

```yaml
spring:
  kafka:
    consumer:
      properties:
        partition.assignment.strategy: org.apache.kafka.clients.consumer.CooperativeStickyAssignor
```

Do not change assignors without checking compatibility across members in the same group and Kafka client versions. During rollouts, members may temporarily run different application versions; ensure compatible assignment strategy configuration during the transition.

## 6. Concurrency Must Match Partition Count

For a topic with eight partitions, a consumer group can process at most eight partitions concurrently. If total concurrency across all replicas is four, consumers may hold two partitions each. If total concurrency is twelve, at least four consumers receive no partitions from that topic.

Example:

| Partition count | Total consumers in group | Consequence |
|---:|---:|---|
| 8 | 4 | Each consumer may receive roughly two partitions. |
| 8 | 8 | Can achieve one consumer per partition. |
| 8 | 12 | Some consumers receive no partitions. |
| 8 | 2 | Only two consumers process; each holds multiple partitions. |

This is the partition-level parallelism limit. If raising concurrency fails to increase throughput, check whether the group already has one consumer per partition. Once this limit is reached, adding more consumers will not process the topic faster; optimize processing, revisit partitioning, or split business streams.

Do not look solely at `factory.setConcurrency()` on one instance. Total group members also depend on replica count, the number of listener containers using the same group, and other listeners subscribing to the topic. Actual consumer count can differ from expected configuration if the application runs multiple containers.

## 7. Broker Leaders and Replicas Can Also Be Imbalanced

Each partition has one leader broker responsible for handling writes and standard reads; follower replicas replicate data. If multiple high-traffic partition leaders reside on the same broker, that broker can become overloaded even when consumer assignments are balanced.

Example:

```text
Broker 1: leader p0, p1, p2, p3  -> heavy write/read
Broker 2: leader p4             -> light write/read
Broker 3: leader p5             -> light write/read
```

Distinguish:

- **Replica assignment:** which brokers store replicas of a partition.
- **Leader distribution:** which broker currently acts as leader for each partition.
- **Consumer assignment:** which consumer group member reads each partition.

Changing the consumer assignor does not move leaders across brokers. If broker leaders are skewed, inspect replica placement, preferred leaders, partition reassignments, and broker health. Reassignments must account for replication factor, ISR, network, and disk load to avoid adding pressure to the cluster.

## 8. Measuring Load Distribution per Partition

Total consumer lag for a group can mask a hot partition. For example, a total lag of 10,000 records may look stable, yet if 9,500 records sit in one partition while the others are near zero, one business stream may be stalled.

Monitor at least the following metrics by topic, partition, consumer member, and broker:

| Metric | Meaning | Usage |
|---|---|---|
| Records in per partition | Number of records written to each partition | Detect producer skew and hot keys. |
| Bytes in/out per partition | Volume of bytes written/read | Detect partitions with large records or heavy byte load. |
| Consumer lag per partition | Distance between log end offset and committed offset | Identify partitions where consumers fall behind. |
| Processing latency per partition | Time to process records/batches per partition | Distinguish high record count from slow business logic. |
| Records consumed per member | Number of records processed by each consumer | Detect skewed assignments or processing speed differences. |
| CPU, network, disk per broker | Broker resources | Find overloaded leader/replica brokers. |
| Rebalance count/duration | Frequency and duration of rebalances | Detect continuous assignment churn. |

Observe both absolute values and rates of change. A partition with high lag that is draining quickly may be less concerning than a partition with small lag climbing steadily. Also distinguish offset lag from time lag: varying record sizes and arrival rates mean identical offset lag values can carry very different operational significance.

Logs and traces should include topic, partition, offset, key, or event ID. Never log sensitive payloads just to diagnose skew. To identify hot keys, aggregate hashed keys or use bounded-cardinality metrics rather than creating a metric label per unique key.

## 9. Workflow for Investigating Uneven Partitions

When a consumer or partition shows high lag, investigate in order:

1. **Check per-partition lag.** Determine whether one partition is hot or all partitions are climbing.
2. **Compare records and bytes in.** If one partition receives more data, investigate keys, partitioner, and producers.
3. **Compare processing latency.** If record volumes are similar yet processing times diverge, check business logic, dependencies, or payload sizes.
4. **Inspect consumer assignments.** Check which member holds which partitions and how many partitions each member receives.
5. **Check actual member count.** Cross-check per-replica concurrency, replica count, and other containers sharing the group.
6. **Check broker leaders.** If one broker shows high network/disk/CPU, check leader distribution and replica placement.
7. **Identify ordering constraints.** Before changing keys or salting, verify which entity requires ordering.
8. **Change one factor in a controlled step.** Adjust keys, assignor, concurrency, or topology separately to measure impact.

For instance, if partition 3 has rapidly rising lag, high records-in, and the consumer holding partition 3 matches peer throughput, the producer is likely generating a hot partition. If every partition receives similar traffic yet one consumer holds four partitions while another holds one, check assignment strategy and subscriptions. If consumer lag is comparable yet broker 1 shows high disk latency, investigate broker placement.

## 10. Remediations by Root Cause

| Root cause | Remediation | Impacts to consider |
|---|---|---|
| Hot key from one entity generating heavy events | Isolate large entity streams, shard keys if business permits, or throttle rate | May alter per-entity ordering; needs merge step if sharded. |
| Low key cardinality | Choose a key with distribution suited to the ordering unit | May change ordering semantics and partition mapping. |
| Skewed range assignment across multiple topics | Evaluate `RoundRobinAssignor` or another suitable assignor | Can trigger rebalances and requires group-wide config compatibility. |
| Too many consumers relative to partitions | Lower concurrency/replicas or expand partitions carefully | Expanding partitions can alter key mapping and topology. |
| Too few consumers relative to partitions | Raise concurrency/replicas up to partition limit | Can increase load on brokers and dependencies. |
| Partition leaders concentrated on one broker | Reassign replicas and balance leaders | Reassignment consumes network/disk and requires ISR monitoring. |
| Large records or heavy processing on one event type | Split topics or optimize payloads/processors | Increases operational and schema management complexity. |

Do not apply all fixes simultaneously. Change one variable, re-measure record/byte distribution, lag, processing latency, and broker resources, then decide the next step.

## 11. Preserving Ordering When Redistributing Data

Partitions are Kafka's ordering boundary. When changing keys, using a custom partitioner, or increasing partition counts, records for the same entity can shift across multiple partitions. The consumer group may process them concurrently and complete out of original order.

Before altering routing, answer:

- Is ordering guaranteed by event, order, customer, account, or which aggregate?
- Can events of the same entity be processed in parallel?
- If sharding, how does the system merge results and enforce versioning?
- Can replays from old and new topics run concurrently?
- Does the old topic need draining or phased traffic migration?

If per-key ordering is a hard requirement, keep keys stable and optimize the hot partition's consumer/processor first. If ordering can be relaxed, design shard keys alongside an explicit aggregation mechanism.

## 12. Testing Partition Distribution

Distribution tests require representative data. A test sending only a few records with random keys cannot catch production hot keys.

Scenarios to include:

1. Produce a record set with high key cardinality and measure records/bytes per partition.
2. Produce data where one hot key dominates traffic and verify metrics detect the hot partition.
3. Run a consumer group across multiple topics with different partition counts; compare RangeAssignor and RoundRobinAssignor assignments.
4. Test concurrency below, equal to, and above partition count; observe which members receive partitions and which remain idle.
5. Expand partitions in a test environment; inspect key mapping, per-entity ordering, and rebalances.
6. Create a controlled skewed leader distribution; observe broker load and test reassignment procedures.
7. Replay data after changing routing; verify idempotency, versioning, and business ordering.

Wait on explicit conditions with finite timeouts in integration tests. For skew analysis, send enough records for a meaningful histogram and keep data seeds fixed for clean before/after comparisons.

## 13. Common Mistakes

- **Only raising concurrency when lag is high:** if one partition is hot, adding consumers cannot split that partition across multiple consumers.
- **Looking only at total lag:** total lag masks congested partitions.
- **Assuming equal partition counts mean equal load:** key skew and record sizes can heavily skew load.
- **Using RoundRobinAssignor to fix a hot key:** assignors distribute partitions to members; they do not change the producer's partitioner.
- **Adding partitions without evaluating ordering:** keys may remap to different partitions and break ordering over time.
- **Salting keys without a merge step:** events for the same entity can complete out of order.
- **Confusing consumer assignment with broker leader distribution:** two different layers requiring different tools and fixes.
- **Adding more consumers than partitions:** excess consumers add no parallel capacity for the topic.
- **Switching assignors simultaneously without compatibility checks:** members in the same group may disagree on assignment strategies during rollouts.

## 14. Designing Partition Distribution for Production

A stable design starts with ordering requirements and expected load. Choose keys matching the entity that requires ordering; estimate partition counts from throughput and target parallelism; align overall concurrency with partition count; choose an assignor suited to subscription topology; and distribute replicas/leaders across brokers to avoid hotspots.

After deployment, monitor records, bytes, lag, and processing latency per partition. When skew appears, identify whether it is producer, consumer assignment, or broker skew before changing anything. For hot keys, weigh the impact of salting and partition expansion on ordering. For assignment skew, check member count and assignor. For broker skew, inspect leader/replica placement.

The goal is not making every partition hold an identical number of records. The goal is distributing work within business constraints, preserving necessary ordering, and ensuring no partition, consumer, or broker becomes a prolonged bottleneck.
