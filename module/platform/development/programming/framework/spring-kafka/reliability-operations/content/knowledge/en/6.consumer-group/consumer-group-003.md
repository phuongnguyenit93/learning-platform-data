# Concurrency and Partition Count

In Spring Kafka, concurrency determines how many consumers a listener container creates for parallel reading. A topic's partition count determines how many independent units of data consumers in the same consumer group can process independently. These two settings must be designed together: increasing concurrency only increases parallel processing capacity when the group still has partitions not yet claimed by other consumers.

For example, topic `orders.in` has 6 partitions. An application running one listener with concurrency equal to 3 creates 3 consumers in the same group. Each consumer can receive 2 partitions. Increasing concurrency to 6 allows each consumer to receive one partition. Increasing it to 10 means at most 6 consumers have partitions to process; the remaining 4 consumers receive none.

```text
Topic orders.in: 6 partitions

Concurrency = 3                  Concurrency = 6
Consumer 0 <- P0, P1             Consumer 0 <- P0
Consumer 1 <- P2, P3             Consumer 1 <- P1
Consumer 2 <- P4, P5             Consumer 2 <- P2
                                 Consumer 3 <- P3
                                 Consumer 4 <- P4
                                 Consumer 5 <- P5
```

Each partition is assigned to at most one consumer in the same group at a given time. Therefore, partitions are the fundamental parallelism limit of a consumer group, whereas concurrency is the number of consumers the application requests to run.

## 1. Consumer Groups and Parallelism Limits

Kafka divides a topic into independent partitions. A consumer group coordinates dividing those partitions among consumers sharing the same `group.id`. For a topic with `P` partitions and a group with `C` consumers subscribed to that topic:

- If `C` is less than `P`, some consumers will receive multiple partitions.
- If `C` equals `P`, each consumer can receive one partition.
- If `C` is greater than `P`, at least `C - P` consumers have no partitions to read.

When a listener subscribes to multiple topics, consider the total number of partitions the listener subscription can receive. For instance, if a listener reads `orders.in` with 6 partitions and `payments.in` with 4 partitions, the group has 10 partitions within that subscription scope. However, how they are divided among consumers also depends on the partition assignor and the subscriptions of consumers in the group.

One consumer can process multiple partitions, but one partition is not shared simultaneously by two consumers in the same group. This is the mechanism that lets Kafka preserve record ordering within a partition and avoid two consumers concurrently advancing offsets for the same partition.

### 1.1 Multiple consumer groups do not increase parallelism for the same processing stream

Two different consumer groups can both read an entire topic independently. For example, `order-enricher` and `order-audit` both receive records from `orders.in`; each group has its own offsets and each group can be assigned all partitions. Adding a new group creates another independent consumption stream rather than splitting load for the existing group.

To increase the number of consumers sharing load for one workload, consumers must join the same group ID and register matching subscriptions. If each replica is accidentally configured with a different `group.id`, every replica may read the entire topic instead of splitting partitions.

## 2. Configuring Concurrency in Spring Kafka

Spring Kafka implements concurrency using a `ConcurrentMessageListenerContainer` that manages multiple child `KafkaMessageListenerContainer` instances. Each child container owns its own Kafka consumer and joins the consumer group using the listener's group ID.

With Spring Boot, you can configure default concurrency for listener containers:

```yaml
spring:
  kafka:
    consumer:
      group-id: order-enricher
    listener:
      concurrency: 3
```

This value is used when Boot auto-configures the listener container factory. If the application declares its own factory, concurrency can be set directly:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, Order>
orderListenerContainerFactory(
        ConsumerFactory<String, Order> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, Order>();
    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    return factory;
}
```

A listener can select that factory:

```java
@KafkaListener(
        topics = "${app.topics.orders-in}",
        groupId = "${spring.kafka.consumer.group-id}",
        containerFactory = "orderListenerContainerFactory")
public void onOrder(ConsumerRecord<String, Order> record) {
    orderService.process(record.value());
}
```

If you only want to change concurrency for a single listener, it can be declared directly on the annotation:

```java
@KafkaListener(
        topics = "${app.topics.orders-in}",
        groupId = "order-enricher",
        concurrency = "${app.kafka.orders.concurrency:3}")
public void onOrder(ConsumerRecord<String, Order> record) {
    orderService.process(record.value());
}
```

Concurrency on `@KafkaListener` applies to that listener's container. It lets listeners with different loads and parallelism needs use separate settings. When choosing how to configure it, check which factory the listener actually uses; a concurrency value on a different factory has no effect on this listener.

## 3. Calculating Total Consumers Across Multiple Replicas

Concurrency is typically configured per application instance. If you run `R` replicas and each replica creates `C` consumers for the same listener/group, the total number of consumers joining the group is approximately:

\[
N = R \times C
\]

For a topic with `P` partitions, the number of consumers that can be assigned at least one partition cannot exceed:

\[
N_{active} \leq \min(P, R \times C)
\]

For example, a topic has 12 partitions, the application runs 3 replicas, and each replica has concurrency 2:

| Metric | Value |
|---|---:|
| Partition count | 12 |
| Replica count | 3 |
| Concurrency per replica | 2 |
| Total consumers in group | 6 |
| Average partitions per consumer | 2 |

If scaled up to 6 replicas with concurrency 2, the group has 12 consumers and can utilize all 12 partitions. If scaled up to 8 replicas, the group has 16 consumers, yet at most 12 consumers are assigned partitions. The remaining four consumers stay in the group without reading records.

This formula describes the limit of active consumers when subscribing to the same set of partitions. When multiple listeners in the same group have different subscriptions, inspect the actual assignment for each subscription rather than summing partitions across all topics in the cluster.

## 4. Partition Assignors Determine How Partitions Are Divided

Kafka uses a partition assignor to decide which consumer receives which partition. Active consumer count indicates the parallelism limit, but does not guarantee each consumer gets the exact same number of partitions. The outcome also depends on the assignor, topic count, subscriptions, and current members in the group.

Common assignors include:

| Assignor | General distribution behavior | Things to note |
|---|---|---|
| `RangeAssignor` | Divides each topic's partitions into contiguous ranges for consumers | With multi-topic subscriptions, one consumer may receive partitions at the same index from multiple topics, causing uneven load across consumers. |
| `RoundRobinAssignor` | Distributes partitions sequentially across eligible consumers | Can spread partitions from multiple topics more evenly when subscriptions are compatible. |
| `StickyAssignor` | Tries to preserve previous assignments as much as possible while rebalancing | Reduces the number of partitions that must move when group membership changes. |
| `CooperativeStickyAssignor` | Sticky balancing using a cooperative/incremental mechanism | Can avoid stop-the-world assignment pauses during rebalances; requires compatible configuration across consumers and client versions. |

For example, 3 consumers `C0`, `C1`, `C2` all subscribe to two topics `orders.in` and `payments.in`, each with 3 partitions. With `RangeAssignor`, each topic may be split by corresponding range: `C0` receives partition 0 of both topics, `C1` receives partition 1 of both topics, and `C2` receives partition 2 of both topics. Each consumer gets two partitions, yet if one topic has substantially higher load than the other, load across consumers may become imbalanced.

Do not choose an assignor solely by name. Check the Kafka consumer's `partition.assignment.strategy` configuration, client version, and compatibility across all members in the group. Changing assignors can trigger a rebalance during rollout.

## 5. Concurrency Does Not Create Additional Partitions

Concurrency only creates more consumers; it does not split one partition into multiple parts. If a topic has 3 partitions, a group cannot have 8 consumers independently reading 8 slices of that topic. Raising concurrency from 3 to 8 simply leaves 5 consumers without partitions.

If throughput requires more than one partition can provide, increasing the partition count may be necessary. However, this is a topic topology change, not a zero-cost speed dial. Consider:

- Whether data can be partitioned by key to provide enough partitions while preserving ordering per business entity.
- Write and read rates, record size, replication factor, and broker capacity.
- Log file counts, metadata, replicas, and recovery overhead when brokers restart.
- Consumer counts, connection counts, and rebalance duration when the group changes.
- The impact of adding partitions on how keys map to partitions.

With the default hash-based key partitioner, increasing the partition count can route new records for the same key to a different partition than older records. In that case, older records remain in the previous partition while newer records land in the new partition; Kafka does not guarantee global order across two partitions. If ordering by `orderId` is mandatory, evaluate the impact of increasing partitions before modifying a live topic with existing data.

## 6. Partitions Are the Unit of Ordering

Kafka guarantees ordering within a partition. A consumer assigned that partition reads records in offset order. If two records with the same `orderId` must be processed sequentially, producers typically use `orderId` as the key so those records are routed to the same partition.

```text
orders.in

P0: order-100 created -> order-100 paid -> order-100 shipped
P1: order-200 created -> order-200 paid
P2: order-300 created -> order-300 cancelled

Consumer C0 processes P0
Consumer C1 processes P1
Consumer C2 processes P2
```

Partitions can be processed in parallel, while the ordering of each individual order is preserved within its respective partition. If the application offloads records to an executor or asynchronously processes multiple records from the same partition concurrently, it can break business completion ordering even though Kafka delivered the records in order. When ordering matters, avoid uncontrolled parallelism within the same partition.

Increasing consumers does not increase independent ordering streams within one partition. To scale processing, you need sufficient partitions and reasonably well-distributed keys. If every record uses the same key, they all concentrate in one partition and one consumer; the remaining consumers sit idle even if the topic has many partitions.

## 7. Skewed Load and Hot Partitions

Partition count does not guarantee that load is evenly distributed. A topic with 12 partitions can still be bottlenecked by a single partition if most records share the same key or if a few keys are disproportionately hot. This is the hot partition phenomenon.

For example, if a producer uses `countryCode` as the key and most orders come from one country, the partition holding that key may receive the bulk of traffic. Other consumers finish the remaining partitions quickly and wait, while one consumer is continuously overloaded.

Monitor lag per partition rather than looking only at total group lag. A single partition with steadily climbing lag while other partitions stay near zero usually indicates skewed key distribution or uneven processing time. Mitigations may include:

- Choosing a key with cardinality and distribution better suited to business ordering requirements.
- Optimizing processing for the record types creating the hot partition.
- Splitting workloads with divergent traffic profiles into separate topics.
- Using an intentional key-sharding strategy if business rules permit changing ordering boundaries.

Do not append random suffixes to keys arbitrarily. That can spread load, but it breaks per-entity ordering and sends events for the same order to multiple partitions.

## 8. Concurrency and Record Processing Time

Every consumer must keep polling Kafka to maintain group membership. If a listener processes for too long, the consumer can exceed `max.poll.interval.ms`; the broker and group coordinator may consider the consumer inactive and trigger a rebalance. Another consumer may take over the partition while the old execution is still running in the application.

Configurations to evaluate together:

| Property | Meaning | Operational reasoning |
|---|---|---|
| `max.poll.records` | Maximum number of records returned in a single poll | Lowering this can reduce work per poll, at the cost of more polls and overhead. |
| `max.poll.interval.ms` | Maximum time between polls before the consumer is considered stalled | Must be large enough for batch/poll processing under peak load, with a safety margin. |
| `session.timeout.ms` | Time the coordinator waits for heartbeats before considering a consumer session lost | Relates to detecting disconnected consumers; does not replace poll processing limits. |
| `heartbeat.interval.ms` | Heartbeat interval in the corresponding consumer mode | Must be compatible with session timeout and the group protocol/client configuration in use. |

In modern Kafka clients, heartbeats can be sent by a background thread while the application thread processes records, yet `max.poll.interval.ms` still bounds the time between poll calls. Do not simply raise session timeout to fix a slow-processing listener.

For record listeners, the container invokes the listener per record on the consumer processing thread. For batch listeners, the listener receives a batch from the poll; total batch processing time must fit within the poll budget. When processing asynchronously, explicitly design when records are acknowledged and ensure offsets are never committed past incomplete records.

## 9. Choosing Concurrency Based on Real Capacity

The goal is not to set concurrency as high as possible. Each consumer adds background work such as polling, heartbeats, network I/O, deserialization, and partition management. Listeners also consume CPU, memory, connection pools, and dependency resources.

An initial sizing approach:

1. Determine the topic's partition count and expected traffic.
2. Measure average and high-percentile processing times for a record.
3. Determine the processing capacity of a single consumer given allocated resources.
4. Set concurrency so total consumers do not exceed useful parallelism of the partition subscription.
5. Gradually increase replicas or concurrency in load tests while monitoring throughput, lag, CPU, heap, connection pools, and processing time.
6. Keep headroom for rebalances, traffic spikes, and slow dependencies.

If listeners are primarily I/O-bound, more consumers can be utilized than in CPU-bound workloads, though consumer count remains bounded by partitions and downstream capacity. If a listener uses a database connection pool capped at 10 connections while concurrency is 40, many consumers will contend for connections and increase latency instead of throughput.

Look at both application thread counts and assigned partitions. Increasing concurrency does not help when the bottleneck lies in a database, HTTP service, broker disk, or a hot partition.

## 10. Rebalances When Changing Concurrency or Replicas

When consumers join or leave a group, the group coordinator must redistribute partitions. This is called a rebalance. A rebalance can happen when:

- The application scales replicas up or down.
- The listener container increases or decreases concurrency.
- A consumer is stopped, crashes, or loses connectivity.
- Subscriptions change or topics are added to a pattern subscription.
- Topic partitions change.
- A consumer fails to poll within the allowed window or is evicted from the group.

During a rebalance, partitions may be revoked from old consumers and assigned to new consumers. The container coordinates with the Kafka client to stop accepting new work, finish or handle in-flight records per configuration semantics, and continue with the new assignment. Rebalance duration increases latency and can cause temporary lag spikes.

To limit the impact:

- Use graceful shutdown so containers stop cleanly and commit/ack according to configuration.
- Avoid scaling replicas continuously on minor lag fluctuations.
- Choose an appropriate assignor, considering cooperative rebalance if the client and group support it.
- Keep listener processing time within poll and timeout budgets.
- Track rebalance counts, rebalance durations, and when they occur relative to deployments.

If using static membership with `group.instance.id`, each consumer member needs a proper identity that never collides across active members. With a concurrent container, check how your Spring Kafka version generates or suffixes identities for child consumers; never assign the exact same `group.instance.id` to multiple consumers.

## 11. When to Increase Partitions, Concurrency, or Replicas?

These three changes address different constraints:

| Change | Effect | When appropriate |
|---|---|---|
| Increase concurrency in an instance | Creates more consumer threads/child containers in the same process | The process has spare CPU/memory and the topic still has unexploited partitions. |
| Increase replica count | Adds processes and consumers to the group | One instance lacks resources or load distribution and higher fault tolerance are needed. |
| Increase partition count | Creates more parallel units in the topic | The group already uses all partitions, more parallelism is needed, and key distribution allows it. |

For example, a topic has 4 partitions, one replica has concurrency 4, and lag grows. Scaling to 8 replicas with concurrency 4 does not create more partitions; most consumers sit idle. If brokers and the key model permit, increasing the topic to 8 partitions and scaling consumers can increase parallelism. However, if lag is concentrated on a hot partition, merely adding partitions may not solve it because the hot key still hashes to a single partition.

Before adding partitions, verify broker capacity for additional replicas, storage space, cluster-wide partition counts, consumer assignors, key distribution, and ordering requirements. Partition count should be treated as a long-term design decision because reducing partitions later is generally not as straightforward as increasing them.

## 12. Observing and Diagnosing Concurrency

Metrics that should be monitored together:

- **Consumer lag per partition:** detects backlogged partitions or hot keys.
- **Active consumer count and assigned partition count:** detects surplus consumers or unassigned partitions.
- **Throughput per consumer and partition:** checks whether load is balanced evenly.
- **Listener duration:** detects slow processing and long tail outliers.
- **Poll interval and rebalance count:** detects consumers considered stalled or group churn.
- **CPU, heap, GC, and connection pools:** identifies bottlenecks within the process or dependencies.
- **Retry counts, errors, and DLT:** distinguishes high-traffic lag from lag caused by repeated failing records.

Example interpretation guide:

| Observation | Possible cause | Investigation direction |
|---|---|---|
| High lag across all partitions, high CPU | Application processing capacity is insufficient | Measure listener duration, increase resources or parallelism if partitions remain available. |
| High lag on one partition, low on others | Hot partition or a very slow-processing record | Inspect keys, record sizes, and logs by partition/offset. |
| Many consumers without assignments | More consumers than partitions or mismatched subscriptions | Check total concurrency, replicas, group ID, and topic subscriptions. |
| Lag spikes during rollouts | Frequent rebalances or prolonged shutdowns | Check deployment strategy, graceful shutdown, assignor, and rebalance duration. |
| Lag grows despite low CPU | Consumers waiting on dependencies or I/O-bound | Check DB pool, HTTP latency, retries, and connections. |

Do not look solely at total consumer lag. Total lag can mask a single congested partition; nor can you conclude concurrency is too low from lag alone if a downstream dependency is the real bottleneck.

## 13. Testing Partition Distribution and Concurrency

Integration tests should verify actual assignments within the group. For a topic with 6 partitions and listener concurrency 3, verify the group has 3 consumers and all 6 partitions are assigned. Then increase concurrency to 8 and confirm the number of consumers holding assignments does not exceed 6.

Scenarios to cover:

1. One instance, concurrency less than partition count: confirm consumers receive multiple partitions.
2. One instance, concurrency equal to partition count: confirm the group utilizes all partitions.
3. Concurrency greater than partition count: confirm surplus consumers receive no partitions.
4. Multiple replicas in the same group: confirm total consumers match the sum of per-replica concurrency.
5. Two different group IDs: confirm each group receives an independent stream of records.
6. Adding/removing replicas: observe rebalances and confirm no records are lost under configured commit semantics.
7. Skewed key distribution: confirm per-partition lag reflects the hot partition.
8. Slow listener processing: confirm poll timeouts and retry settings behave properly without unexpected rebalances.

When testing, use `AdminClient` or Kafka tools to inspect partition assignments and consumer group state. Wait for assignment stability using explicit conditions rather than fixed sleeps. Clean up consumer groups and topics after tests so subsequent runs are unaffected.

## 14. Common Configuration Mistakes

- **Raising concurrency beyond the partition count expecting throughput to keep scaling:** surplus consumers will receive no partitions.
- **Giving each replica a different group ID:** every replica may read the entire topic instead of sharing load.
- **Setting concurrency higher than downstream capacity:** many consumers contend for database or HTTP connections, increasing latency.
- **Looking only at total lag:** misses hot partitions or a single very slow record.
- **Adding partitions without checking key distribution:** can alter key mappings and impact per-entity ordering.
- **Concurrently processing records from the same partition yourself:** can cause business completion order to diverge from Kafka order.
- **Ignoring rebalances when scaling:** continuous deployments or autoscaling can cause disruption and lag spikes.
- **Configuring duplicate `group.instance.id` across multiple consumers:** triggers static membership fencing errors and destabilizes the group.
- **Raising `session.timeout.ms` to fix slow listeners:** ignores `max.poll.interval.ms` limits and the true root cause of slow polling.

## 15. Workflow for Sizing Listener Configuration

When designing a listener for a topic, start from the partition count and actual load. Identify which key governs business ordering, then check whether keys are evenly distributed. Choose per-instance concurrency so total consumers across replicas exploit the useful partitions. Finally, measure throughput and lag under rising load to tune resources and configuration.

A configuration that can serve as a starting point:

```yaml
spring:
  kafka:
    consumer:
      group-id: order-enricher
      enable-auto-commit: false
      properties:
        max.poll.interval.ms: 300000
        max.poll.records: 100
    listener:
      concurrency: 3
      ack-mode: record
```

The values above are only an initial configuration example. `max.poll.records`, `max.poll.interval.ms`, ack mode, concurrency, and replica count must be tuned according to processing time, batch size, retry policy, and topic topology. Spring Kafka containers typically manage offset commits; keep auto-commit disabled so offsets follow container semantics.

Before deploying, answer four questions: how many partitions does the topic have, how many total consumers are in the group, which partitions/keys could become hot spots, and can the listener finish within the poll budget. These answers show whether current concurrency can utilize all partitions and whether adding consumers will genuinely improve throughput.
