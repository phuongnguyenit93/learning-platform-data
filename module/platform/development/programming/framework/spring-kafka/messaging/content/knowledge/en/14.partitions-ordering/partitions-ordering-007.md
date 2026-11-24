# Hot partitions and uneven distribution

Kafka divides a topic into partitions for parallel storage and processing. However, one partition can receive significantly more records or bytes than the remaining partitions. This phenomenon is commonly called a **hot partition**. It can overload the consumer handling that single partition and drive up consumer lag, while other consumers sit idle with spare capacity.

Hot partitions usually stem from how producers choose keys and distribute records. A key with very high frequency is continuously routed to the same partition under the default partitioner. Yet uneven distribution can also arise from producers specifying partitions directly, custom partitioners, skewed business traffic, differing record processing costs, or partition leaders concentrated on a single broker.

This lesson belongs to the **Partitions and ordering** chapter of the **SPRING_KAFKA_MESSAGING** module, focusing on identifying root causes, designing keys, distributing load, and handling hot partitions while clearly understanding event ordering trade-offs.

## Learning objectives

After this lesson, you can:

- Explain hot partitions and distinguish them from overloaded brokers or consumers.
- Identify key skew, partition skew, and leader/broker skew.
- Understand why a key is typically routed consistently to the same partition.
- Measure record counts, bytes, lag, and processing time per partition.
- Design partition keys aligned with business ordering boundaries.
- Choose ways to handle hot keys via sharding, salting, or splitting topics.
- Evaluate the impact of increasing partitions on key mapping and ordering.
- Know when partition reassignment helps and when it does not.
- Test distribution using skewed data resembling production traffic.

## 1. What is a hot partition?

A hot partition is a partition with substantially higher traffic or processing cost than other partitions in the same topic. For example, topic `orders.created` has 12 partitions, yet partition 3 receives 45% of all records while each remaining partition receives around 5%.

~~~mermaid
flowchart TB
    P[Producer records] --> D[Partitioner]
    D --> P0["Partition 0: 5%"]
    D --> P1["Partition 1: 5%"]
    D --> P2["Partition 2: 5%"]
    D --> HOT["Partition 3: 45% - HOT"]
    D --> P4["Partition 4: 5%"]
    D --> P5["Partition 5: 5%"]
    HOT --> C[One consumer member]
    C --> L[Consumer lag increases]
~~~

A hot partition can cause:

- The consumer assigned to that partition to process slower than other members.
- Lag on that specific partition to climb continuously.
- The broker hosting the hot partition's leader to experience high CPU, disk, or network usage.
- Producers to encounter higher latency when sending to the hot partition.
- Other partitions to have spare capacity yet be unable to share the hot partition's work within the same consumer group.

A hot partition does not necessarily mean the entire topic has high throughput. A partition can become hot due to few records with large payloads or very heavy per-record processing logic. Therefore, inspect record counts, bytes, and processing duration together.

## 2. Distinguishing types of imbalance

Before fixing the issue, identify which layer has the imbalance.

| Imbalance type | Symptom | Common causes |
|---|---|---|
| Key skew | A few keys account for most records | One tenant, customer, or entity with disproportionately high traffic. |
| Partition traffic skew | One partition receives more records or bytes | Key skew, direct partition specification, or custom partitioner. |
| Broker/leader skew | One broker bears higher load than others | Many heavy partition leaders concentrated on that broker, replica placement, or uneven broker load. |
| Consumer processing skew | One consumer has higher lag than other members | Assigned partition carries heavy data, slow processing, or uneven downstream calls. |
| Payload skew | Similar record counts, yet mismatched bytes or processing costs | Certain event types have huge payloads or require heavy business operations. |

A topic can suffer multiple types simultaneously. For example, a large tenant creates key skew, making partition 3 hot; partition 3's leader sits on broker 1; and the consumer reading partition 3 calls a slow downstream service. Merely adding brokers or consumers will not automatically fix the entire causal chain.

## 3. Why can keys create hot partitions?

For keyed records, the default Kafka producer typically uses the serialized key to determine the partition. The same key is usually routed to the same partition while partition count and partitioner remain unchanged.

Example:

~~~java
kafkaTemplate.send(
        "orders.created",
        customerId,
        event
);
~~~

If one large customer generates 40% of all orders, every event carrying that `customerId` goes to the same partition under the default partitioner. Remaining partitions may receive far less load.

High key diversity does not automatically guarantee even distribution. If 90% of records belong to one popular key and 10% belong to thousands of other keys, the partition holding the popular key can still become a hot partition.

Key patterns prone to skew:

- A constant value used for all records, such as the string key `"orders"`.
- A single `tenantId` for a customer with outsized traffic.
- A single `accountId` receiving nearly all transactions.
- A `category` or `region` with much higher traffic than other groups.
- Null keys combined with explicit partition assignment or an unbalanced custom partitioner.

With null keys, modern Kafka producers' default partitioner typically uses sticky partitioning to batch records onto one partition for a period to improve batching, then switches partitions. Therefore, do not assume every null-key record is strictly round-robined record by record.

## 4. Choosing keys by ordering boundary

The partition key should reflect the unit of data where business logic requires preserving order. Answer the question: which events must strictly be processed in relative order?

Example:

| Business need | Potentially suitable key | Ordering preserved within |
|---|---|---|
| Changes to the same order | `orderId` | One order |
| Transactions on the same account | `accountId` | One account |
| Events from the same device | `deviceId` | One device |
| Changes for the same customer | `customerId` | One customer |
| Events not needing per-entity ordering | Load-distributing key or null | No per-entity ordering guarantee |

If `customerId` is used as the key yet one customer generates most traffic, that customer's partition gets hot. If business rules only require ordering per `orderId`, use `orderId` to spread that customer's orders across more partitions.

Changing keys requires understanding trade-offs:

- Keys that are too coarse, such as `tenantId`, can pack many entities into one partition and cause skew.
- Keys that are too granular, such as `eventId`, distribute well yet lose ordering among events of the same entity.
- An appropriate key both distributes load reasonably and preserves ordering at the exact scope required by business rules.

No single key is optimal for every type of consumer. If two use cases demand vastly different partitioning schemes, you may need two topics with separate key models or an intermediate processing stream.

## 5. Measuring to identify hot partitions

Do not conclude a hot partition exists from total consumer lag alone. Compare each partition over the same time window.

Metrics to collect:

- Records into each partition per second or minute.
- Bytes into each partition.
- Records read and processed by consumers per partition.
- Consumer lag per partition and lag growth rate.
- Processing times p50, p95, p99 by partition or event type.
- Leader of each partition and which broker hosts the leader.
- Broker CPU, disk I/O, network throughput, and request latency.
- Producer send latency, retries, timeouts, and batch size.

You can construct an observation table:

| Partition | Records/s | Bytes/s | Consumer lag | Processing p95 |
|---|---:|---:|---:|---:|
| 0 | 850 | 1.8 MB | 120 | 18 ms |
| 1 | 910 | 1.9 MB | 150 | 20 ms |
| 2 | 4,800 | 10.5 MB | 18,000 | 95 ms |
| 3 | 870 | 1.7 MB | 130 | 19 ms |

The figures above are illustrative examples only. Partition 2 has much higher traffic and lag, so inspect the keys routed to that partition, payloads, and processing logic.

Useful tools and data sources:

- Kafka consumer group description to view per-partition lag.
- Kafka broker metrics or JMX exporter to check BytesIn, MessagesIn, request latency, and broker load.
- Producer metrics to track sent records, batches, and request latency.
- Spring Kafka listener/container metrics and application metrics to measure processing duration.
- Logs containing topic, partition, offset, event type, and appropriately masked or truncated keys.

Do not use high-cardinality keys as metric labels. Use logs or traces for event-level context and keep metric label sets bounded.

## 6. Checking the producer partitioner and explicit partition assignment

A producer can choose a partition by key, via a custom partitioner, or by having the application specify the partition directly.

Example of manual partition assignment:

~~~java
ProducerRecord<String, OrderCreatedEvent> record =
        new ProducerRecord<>(
                "orders.created",
                2,
                event.orderId(),
                event
        );

kafkaTemplate.send(record);
~~~

In this example, the record is sent straight to partition 2. If many producers hard-code partition 2, that partition can get hot regardless of key diversity.

Before changing consumers or brokers, verify:

- Whether producers pass a key.
- Whether any producer passes a partition number directly.
- Whether a custom partitioner is configured.
- Whether key serializers are consistent across producers.
- Whether producer versions share the same partitioning rules.
- Whether partition count changed around the time traffic skewed.

If multiple producers use different serializers or partitioners, the same key string may not route as expected. The partition key contract must be aligned across all producers writing to the same topic.

## 7. Does increasing partitions solve a hot key?

Increasing the partition count can boost a topic's overall parallelism and distribute many distinct keys across more partitions. However, it **does not split a single hot key across multiple partitions** while using the same key and default partitioner.

For example, key `tenant-42` continues hashing to one partition after the topic expands from 12 to 24 partitions. That key still concentrates on one partition. Some other keys may redistribute due to the changed partition count.

Keep in mind:

- Kafka does not automatically move old records to newly added partitions when expanding partitions.
- Key-to-partition mapping results can change when partition count changes.
- Old records for a key may sit in an old partition while new records land in a new partition.
- Ordering among records of the same key may no longer hold across that change.
- Adding partitions increases metadata, log files, replicas, and broker management overhead.

Therefore, increasing partitions is a solution when you need greater parallelism for many keys or to scale a consumer group. If the cause is one overly hot key, you need to change the key model or isolate the workload.

## 8. Sharding or salting for hot keys

When one entity produces too many records, you can split that entity's workload into multiple shards. Instead of a single key, the producer generates a fixed set of stable shard keys to distribute records across partitions.

For example, the system has one large customer, yet ordering is only required per order. You can use `orderId` to pick a shard within the customer:

~~~java
int shardCount = 8;
int shard = Math.floorMod(orderId.hashCode(), shardCount);
String partitionKey = customerId + "#" + shard;

kafkaTemplate.send(
        "orders.created",
        partitionKey,
        event
);
~~~

Events for the same `orderId` share the same shard key and typically land in the same partition under the default partitioner. Different `orderId` values for the same customer can spread across up to eight shard groups.

This is a business-level sharding technique. `shardCount` must be configured stably and tested against real traffic. If `shardCount` changes, key mapping can shift and entity ordering across the transition period must be handled explicitly.

Trade-offs:

- Increases parallelism by splitting the workload of a large entity.
- Preserves ordering within the scope of each shard key.
- Loses overall ordering across shards of the same customer.
- Consumers or downstream systems may need to aggregate data from multiple shards.
- Hot shards still require monitoring because hash distribution does not guarantee perfectly even load.

Do not use random salting if events of the same order require sequence. If each event receives a random salt, events of the same order can fall into multiple partitions and be processed independently.

## 9. Choosing a strategy based on ordering requirements

Some workloads cannot split a hot key while still preserving global order for that key. If every change to an account must be processed sequentially, `accountId` is the right key and one partition must process that event stream in order.

In this case, there is an architectural limit: preserving sequential order for one key prevents simultaneously distributing that key's records across multiple independent partitions while relying on default Kafka ordering.

Available options:

| Requirement | Strategy | Trade-off |
|---|---|---|
| Ordering of all events for one entity | Keep `entityId` as key, optimize partition processing | Entity throughput is bounded by one partition. |
| Ordering per order only, not customer-wide | Use `orderId` or `customerId` + per-order shard | Loses customer-wide ordering. |
| No per-key ordering needed | Use load-distributing keys or appropriate null keys | Consumers must handle events independently and tolerate varied order. |
| One massive tenant can be isolated | Separate the large tenant into a dedicated topic or stream | Increases provisioning and operational complexity. |
| Must restore order after fan-out | Shards process in parallel then merge via sequence/version | Requires an extra coordination layer and sequence management. |

If entity-wide order is required yet a single partition's speed is insufficient, revisit the domain model: reduce event volume, coalesce events, process via snapshots, or split the aggregate into independent entities. No consumer setting lets a single partition be processed in parallel by multiple members in the same group while automatically preserving default order.

## 10. Isolating workloads via topics or tenant shards

One large tenant can dominate a shared topic's traffic. If that tenant has distinct throughput or SLA needs, separating it into a dedicated topic helps isolate load and operational policies.

Example:

- `orders.created`: regular tenants.
- `orders.created.large-tenant`: workload of the high-traffic tenant.
- `orders.audit`: audit stream with separate retention and consumers.

Topic isolation enables:

- Choosing a dedicated partition count for heavy workloads.
- Configuring retention and replication per need.
- Setting independent consumer groups and scaling.
- Monitoring lag, throughput, and errors separately.
- Preventing one tenant from impacting other tenants.

In return, producers must route topics by clear rules, consumers may need to subscribe to multiple topics, and managing schemas, ACLs, retention, and DLTs becomes more complex. Split topics only when clear operational or SLA boundaries justify it.

## 11. Reassigning partitions across brokers

Sometimes records are relatively evenly distributed across partitions, yet one broker remains hot because it hosts leaders for multiple high-traffic partitions. This is broker/leader skew, distinct from key skew.

Kafka supports replica reassignment and changing leader placement to balance load across brokers. This can relieve pressure on a broker, yet does not reduce record volume on a hot partition and cannot split one partition across multiple leader brokers simultaneously.

Before reassignment:

1. Inspect leader and replica placement.
2. Measure disk, network, CPU, and request latency per broker.
3. Verify replication factor, ISR, and disk capacity.
4. Plan reassignment with bandwidth throttling.
5. Monitor under-replicated partitions and ISR during migration.
6. Verify leader distribution and load after completion.

If one partition still receives 45% of traffic, reassignment only moves where that partition's load lands. To reduce data skew, address key/partitioning or isolate the workload.

## 12. Optimizing consumers and brokers after fixing distribution

Once key distribution is sound, ensure consumers and brokers still have adequate capacity.

Optimization directions may include:

- Increasing consumer concurrency when unallocated partitions remain.
- Optimizing database and downstream service processing.
- Using batch processing when business logic supports bulk operations.
- Bounding asynchronous work to prevent memory exhaustion and out-of-order offset commits.
- Tuning producer batching, compression, and linger to improve network efficiency.
- Balancing leaders and replicas across brokers.
- Scaling broker resources when bottlenecks truly lie in CPU, disk, or network.

Consumer concurrency cannot exceed the group's partition assignment limit. If one partition is hot, adding consumer members to the same group does not split that partition across multiple members. You must reduce work per partition or change how workload is distributed.

Compression and batching reduce transport overhead, but cannot fix a hot key piling into one partition. Treat them as efficiency optimizations after addressing distribution root causes.

## 13. Testing distribution with skewed data

A test that generates equal numbers of records per key will usually miss hot partitions. Generate skewed workloads mimicking production.

For example, a distribution test should include:

- One tenant generating the majority of traffic.
- Many small tenants with low traffic.
- Some keys with large payloads.
- Events of the same entity requiring order preservation.
- Producers using the exact serializers and partitioners from production.

You can check distribution by counting records per partition:

~~~java
Map<Integer, Long> counts = new HashMap<>();

for (int i = 0; i < events.size(); i++) {
    SendResult<String, OrderCreatedEvent> result =
            kafkaTemplate.send(
                    "orders.created",
                    events.get(i).partitionKey(),
                    events.get(i)
            ).get(10, TimeUnit.SECONDS);

    int partition = result.getRecordMetadata().partition();
    counts.merge(partition, 1L, Long::sum);
}
~~~

This is an illustrative example for testing; do not call `get` sequentially like this in throughput benchmarks as it alters load characteristics. When measuring real throughput, send asynchronously with bounded in-flight limits and collect metadata inside callbacks.

Essential tests to cover:

| Test | What to verify |
|---|---|
| Uniform keys | Baseline distribution across partitions. |
| Skewed keys | Detect hot partitions when one key or tenant dominates traffic. |
| Sharded key | Hot workload distributes across the designed shard count. |
| Ordering per entity | Events of the same entity still follow the expected partition and order. |
| Partition expansion | Detect key mapping shifts when increasing partitions. |
| Broker reassignment | Broker load shifts while partition traffic remains unchanged. |
| Consumer load | Per-partition lag and processing times accurately reflect bottlenecks. |

Do not set rigid distribution thresholds requiring every partition to have exactly `1/N` records. Real workloads are rarely uniform. Define acceptable skew based on SLAs and processing capacity.

## 14. Production hot partition incident workflow

When rising lag or a hot broker is detected, handle it in sequence:

1. Identify the topic and partition with abnormal lag, bytes, or record rate.
2. Check which consumer owns the partition and the listener's processing time.
3. Sample keys or event types on the hot partition; mask sensitive data when logging.
4. Cross-reference key frequencies to find the traffic-heavy tenant or entity.
5. Verify whether producers specify partitions explicitly or use a custom partitioner.
6. Determine whether the bottleneck is key skew, payload size, consumer logic, or broker leader placement.
7. Choose the right fix: optimize processing, shard keys, isolate topics, or reassign broker leaders.
8. Assess impacts on ordering and replay before altering partitioning.
9. Test with skewed workloads on staging.
10. Roll out with monitoring and compare before/after metrics.
11. Prepare a rollback plan if lag or error rates climb.
12. Update documentation for key contracts and topic ownership.

Do not abruptly change keys or partition counts merely to make charts look balanced. If event ordering is a business requirement, an uncoordinated partitioning change can introduce bugs harder to detect than lag itself.

## 15. Capstone exercise: handling a hot tenant in orders.created

Suppose topic `orders.created` has 12 partitions. One tenant generates 45% of traffic and the partition holding that tenant's key has continuously rising lag.

Requirements:

1. Measure records/s and bytes/s per partition.
2. Collect key frequency statistics to identify the skewing tenant.
3. Check whether producers use `tenantId` as key or assign fixed partitions.
4. Determine whether business rules require ordering by tenant, customer, or order.
5. Try `orderId` as key to spread that tenant's orders across multiple partitions.
6. If per-order ordering is required, design a stable shard key keyed by `orderId`.
7. Compare before/after workloads using identically skewed test data.
8. Verify events of the same order maintain ordering within their shard.
9. Test increasing partitions and record which keys are remapped.
10. Test isolating the large tenant into a separate topic and evaluate operational cost.
11. Inspect consumer lag, throughput, broker load, and downstream latency.
12. Write an architecture decision record stating benefits, ordering trade-offs, and migration plan.

The exercise is complete when you identify the root cause of the hot partition, select a strategy matching ordering constraints, and prove with metrics that load distributes better without breaking the event contract.

## 16. Learning progression and completion criteria

| Stage | Core focus | Self-check criteria |
|---|---|---|
| 1. Identification | Hot partitions and skew | Distinguish key, partition, broker, and consumer skew. |
| 2. Key design | Keys and ordering boundaries | Select keys matching the unit requiring order preservation. |
| 3. Producer | Partitioner and explicit partitions | Spot producer configurations concentrating traffic. |
| 4. Metrics | Records, bytes, lag, latency | Measure skew on a per-partition basis. |
| 5. Scaling | Partition count and consumer concurrency | Understand limits of adding partitions/consumers. |
| 6. Sharding | Salting, shard keys, topic isolation | Distribute hot workloads and state ordering trade-offs clearly. |
| 7. Broker | Leader placement and reassignment | Separate broker skew from key skew. |
| 8. Testing | Skewed workloads and ordering tests | Test with skewed data resembling production. |
| 9. Operations | Incident response and migration | Resolve hot partitions with metrics and a rollback plan. |

The lesson is complete when you can identify a hot partition via metrics, trace root causes in keys and producers, choose an appropriate sharding or workload isolation strategy, and explain its impact on event ordering.

Hot partitions are not merely a shortage of consumers. They usually originate from workload skew and how producers map keys to partitions. Solving them properly requires combining key design, ordering boundaries, per-partition metrics, broker/consumer capacity, and a controlled rollout plan.

