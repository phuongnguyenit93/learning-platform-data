# Mitigating Key Skew and Handling Hot Partitions

Partitioning enables a topic or message stream to be processed in parallel. However, increasing the partition count does not automatically balance load. If most events carry the same key, producers repeatedly route them to the same partition; the consumer handling that partition becomes overloaded while other partitions remain idle. This phenomenon is commonly known as **key skew**, **partition skew**, or a **hot partition**.

In Spring Cloud Stream, key selection and how the binder maps keys to partitions determine load distribution. This lesson covers how to identify skew, choose suitable keys, configure partitioning with the Kafka binder, handle hot keys via controlled sharding, and apply equivalent partitioning approaches to RabbitMQ or Pulsar.

## 1. What are partition skew and hot partitions?

A topic has multiple partitions, yet traffic is unevenly distributed:

~~~text
Topic: orders

Partition 0  ############################  48% traffic
Partition 1  ########                      14% traffic
Partition 2  ######                         9% traffic
Partition 3  #####                          8% traffic
Partition 4  ####                           7% traffic
Partition 5  ####                           6% traffic
Partition 6  ###                            5% traffic
Partition 7  ##                             3% traffic
~~~

Partition 0 becomes a hotspot. The consumer assigned to this partition may accumulate lag continuously while other consumers underutilize CPU or I/O. Total system throughput is bounded by the slowest partition or hottest key.

Distinguish three concepts:

- **Key skew:** uneven key distribution. A few keys appear far more frequently than others.
- **Partition skew:** uneven distribution of records, bytes, or processing cost across partitions.
- **Hot partition:** a partition experiencing sustained high load or latency, becoming the pipeline's bottleneck.

Key skew usually causes partition skew when partitions are chosen via `hash(key)`. However, partition skew can also arise from varying record sizes, message subsets that are more expensive to process, unbalanced partition assignments, or consumers with uneven capacity.

### Example: one oversized tenant

Suppose a system processes order events for multiple enterprise customers:

| Tenant | Message share | Partition by tenant key |
|---|---:|---|
| `tenant-a` | 52% | Partition 3 |
| `tenant-b` | 12% | Partition 5 |
| `tenant-c` | 9% | Partition 1 |
| `tenant-d` | 7% | Partition 6 |
| Remaining tenants | 20% | Remaining partitions |

If the key is `tenantId`, every event for `tenant-a` lands in the same partition to preserve per-tenant ordering. This is semantically correct if all updates for a tenant must be processed sequentially, yet it creates a throughput ceiling for the large tenant.

Do not rush to change the key before defining ordering requirements. The first question is: must the system preserve ordering across an entire tenant, per order, per account, or only per business aggregate?

## 2. Why does a partition become hot?

Common causes:

1. **Naturally skewed keys:** one tenant, customer, account, or device generates the bulk of traffic.
2. **Low-cardinality keys:** using `eventType`, `country`, `status`, or a boolean value as the key concentrates messages into a few partitions.
3. **Default or missing keys:** producers send null/constant keys while a binder or custom selector maps those values onto the same partition. Note that native Kafka producers without a key typically use sticky partitioning and rotate partitions per batch; do not assume all keyless messages land on one fixed partition.
4. **One workflow emits far more events than others:** for instance, a large store, a settlement account, or a promotional campaign creating traffic spikes.
5. **Uneven processing cost:** certain keys call external APIs, perform large joins, or execute CPU-heavy computations.
6. **Partition count changes:** changing partition count can shift hash mappings, producing different distribution and observed ordering than before.
7. **Consumer-side limits:** partition count may be adequate while consumer concurrency, CPU, I/O, or downstream connection pools lack capacity.

Adding partitions only increases parallelism across distinct keys. If all messages still use one key and require same-key messages to land in the same partition, adding partitions cannot split that hot key.

## 3. Choose keys aligned with business ordering boundaries

The partition key should represent the unit for which the application must preserve order or state. Do not pick a key simply because that field happens to be present in the payload.

| Candidate key | Expected distribution | When appropriate | Risks |
|---|---|---|---|
| `tenantId` | One tenant always maps to the same partition. | Need to serialize all changes within a tenant. | Large tenants create hot partitions. |
| `customerId` | One customer always maps to the same partition. | Need per-customer ordering. | Very active customers cause skew. |
| `orderId` | Each order is a separate key. | Need event ordering per order. | Does not preserve cross-order customer ordering if required. |
| `accountId` | Each account is a separate key. | Need to serialize account balances or state. | Omnibus or system accounts can run hot. |
| `deviceId` | Each device is a separate key. | Need telemetry or device state ordering. | Shared gateways cause many messages to share a key. |
| `eventType` | Only a small number of key groups. | Only when grouping by event type with balanced per-type load. | Low cardinality; prone to hot spots. |
| No key | Distributed per producer/binder policy. | When per-key ordering is not needed. | No ordering guarantee per business entity. |

Practical rules:

- Choose a key with sufficient cardinality distributed roughly in proportion to workload.
- Choose the exact aggregate the business requires to be serialized.
- Avoid keys where a handful of values account for most traffic.
- Keep key generation consistent across producers and programming languages.
- Document the key contract in the schema or event specification.

A high-cardinality key can still suffer skew if one specific key generates 40% of traffic. Measure actual key frequencies rather than merely counting distinct keys.

## 4. Measure skew before changing partitioning

Do not optimize based on gut feel or total throughput alone. Measure at least these groups:

| Metric group | Signals to collect | Questions |
|---|---|---|
| Partition traffic | Records/sec and bytes/sec per partition | Which partition receives the most data? |
| Lag | Consumer lag per topic/partition and lag duration | Which partition is falling behind the producer? |
| Latency | Processing latency p50/p95/p99 per partition or key group | Do certain keys take abnormally long to process? |
| Consumer | CPU, thread utilization, poll rate, commit rate, rebalances | Are consumers resource-constrained or assignment-constrained? |
| Key distribution | Top keys by record count, bytes, and processing cost | Does one key or key group dominate load? |
| Downstream | API latency, database connection pool, rate limits, retries | Is the hot partition the root cause or merely surfacing a downstream bottleneck? |

### Imbalance ratio

You can track a simple ratio:

\[
\text{SkewRatio} =
\frac{\text{Max load on a single partition}}
{\text{Average load per partition}}
\]

For example, 8 partitions totaling 80,000 records/minute:

- Average load: 10,000 records/minute.
- Largest partition: 42,000 records/minute.
- SkewRatio: 4.2.

A ratio of 4.2 shows the busiest partition receives 4.2x the average load. This is a signal to investigate, not proof by itself that the partition is overloaded. Cross-check lag, processing latency, and consumer resources.

Measure both record rate and byte rate. A partition with fewer records but large payloads or heavy processing can still be a hotspot.

### Reading lag per partition

With Kafka, aggregate consumer lag can hide one fast-growing partition. Inspect per-partition lag within the same consumer group. If one partition climbs steadily while others stay near zero, investigate key distribution and processing duration for keys mapped to that partition.

Do not conclude from a single snapshot. Compare across time windows, peak hours, campaign days, and rebalance events. Distinguish brief lag from producer bursts from sustained lag where consumer capacity trails arrival rate.

## 5. Distinguishing Spring Cloud Stream partitioning from Kafka native keys

Spring Cloud Stream has a generic partitioning mechanism across binders. Kafka also has native partitioning based on record keys. The two mechanisms are related but not identical:

| Mechanism | Key properties | Purpose |
|---|---|---|
| Generic Spring Cloud Stream partitioning | `partitionKeyExpression`, `partitionKeyExtractorName`, `partitionSelectorExpression`, `partitionCount` | Computes partitions via the binder's generic mechanism; useful for middleware without native partitioning or custom selector logic. |
| Kafka native partitioning | `KafkaHeaders.KEY` or Kafka producer `messageKeyExpression` | Sends a record key to the Kafka producer so the client/broker picks partitions by key. |

With the Kafka binder, Spring Cloud Stream documentation recommends using Kafka's native partitioning whenever possible. Only use generic binder partitioning when you need custom partition keys or specialized expressions. Avoid configuring both mechanisms without knowing which final key and partition selector actually govern partition selection.

### Configuring Kafka native keys

Example producer using `customerId` as the Kafka record key:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders
      kafka:
        bindings:
          publishOrder-out-0:
            producer:
              message-key-expression: payload.customerId
~~~

Assuming the payload has this data type:

~~~java
record OrderEvent(String customerId, String orderId, String tenantId) {
}
~~~

A producer can construct a `Message` and set `KafkaHeaders.KEY` directly:

~~~java
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<OrderEvent> toKafkaMessage(OrderEvent event) {
    return MessageBuilder
            .withPayload(event)
            .setHeader(KafkaHeaders.KEY, event.customerId())
            .build();
}
~~~

When a record key is set, the default Kafka producer chooses the partition from the hash of the key and current partition count. Records sharing the same key go to the same partition, preserving per-key ordering within that partition.

### Configuring generic Spring Cloud Stream partitioning

When the partition key comes from a custom header or generic binder logic:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders
          producer:
            partition-key-expression: headers['partitionKey']
            partition-count: 12
~~~

Spring Cloud Stream evaluates the key from `partition-key-expression`, then uses `partitionSelectorExpression` or `PartitionSelectorStrategy` if present. By default, partition selection hashes the key modulo partition count. `partitionCount` must be greater than 1 for generic partitioning to take effect.

For Kafka, prefer one clear mechanism. If you want the Kafka key stored on the record so downstream consumers can inspect and reuse it, use Kafka native keys. If using generic binder partitioning with a custom header, verify the resulting partition and stored record key against your actual binder version.

## 6. Why increasing partition count alone does not fix a hot key

Suppose key `tenant-a` hashes to partition 3 in an 8-partition topic. When the topic expands to 16 partitions, the key still hashes to one value and maps to a single partition. The partition ID may change, yet that key's traffic remains concentrated on one partition.

Increasing partitions can help:

- Spread many independent keys across more partitions.
- Increase how many consumers can process in parallel.
- Provide headroom for future growth.

Increasing partitions cannot:

- Split a single key across multiple partitions while preserving whole-key order.
- Speed up a consumer bottlenecked by CPU or a downstream dependency.
- Balance one key that carries most traffic if key semantics stay unchanged.

In addition, changing partition count alters modulo hash results. Older and newer records for the same key may land in different partitions after topic expansion. If business logic relies on per-key order, plan migrations and drain existing data before changing partition counts.

## 7. Strategies to reduce key skew

No single strategy fits every workload. Choose based on ordering requirements, consistency, and state aggregation needs.

| Strategy | Approach | Advantages | Trade-offs |
|---|---|---|---|
| Re-choose the key | Use order ID instead of tenant ID if only per-order order is needed. | Better distribution, simple change. | Loses tenant-wide ordering. |
| Composite key | Combine main entity with an independent dimension, e.g., `tenantId:orderId`. | Creates many keys for large tenants. | Requires redefining state/order boundaries. |
| Key salting/sharding | Append a deterministic shard suffix to hot keys. | Splits one hot key into multiple sub-keys. | Loses global key order; requires merge if combined output is needed. |
| Isolate hot tenants | Route large tenants to a dedicated topic or stream. | Isolates impact on other tenants. | Adds config, operations, and cost. |
| Producer-side batching/aggregation | Merge multiple small updates into one summary event over a short window. | Cuts record count and overhead. | Adds latency; needs duplicate handling and batch limits. |
| Rate limiting/backpressure | Throttle producers or enforce per-key rate limits. | Protects consumers and downstreams. | Increases business completion time or upstream queueing. |
| Increase processing capacity | Optimize consumer, I/O, state stores, and downstreams. | Preserves exact key semantics. | Cannot exceed single-partition/single-key sequential limits. |

## 8. Re-choosing the key when business rules allow

Suppose a system used `tenantId` as the key to keep all tenant events ordered. After analysis, the engineering team determines events are independent per `orderId`; no rule requires two different orders to be processed sequentially.

The key can be changed to `orderId`:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          publishOrder-out-0:
            producer:
              message-key-expression: payload.orderId
~~~

Events for the same order still land on the same partition, while different orders spread across partitions. This is usually the simplest skew fix once ordering boundaries are accurately identified.

Before changing keys, check:

- Does any consumer assume all events for a tenant reside in the same partition?
- Does any aggregation or join use tenant ID as its state key?
- Must ordering hold across `OrderCreated`, `PaymentAuthorized`, and `OrderShipped` for the same order?
- Can old and new producers coexist during the transition?
- Can old and new records be read/joined under the same contract?

## 9. Composite keys and sub-entity splitting

A composite key builds the key from multiple fields:

~~~text
tenant-a:order-101
tenant-a:order-102
tenant-a:order-103
tenant-b:order-201
~~~

Example:

~~~java
String partitionKey(OrderEvent event) {
    return event.tenantId() + ":" + event.orderId();
}
~~~

Composite keys work well when state is managed independently per entity pair. However, if all processing eventually updates a single per-tenant aggregate, the hotspot can reappear at the aggregation step.

Do not append an arbitrary field just to generate more keys. The added field must carry business meaning and allow consumers to process independently. Combining unstable fields can unintentionally scatter events belonging to the same aggregate.

## 10. Key salting: splitting one hot key into multiple shards

When a key must represent a large tenant or account, you can append a shard suffix to create multiple sub-keys:

~~~text
tenant-a#0
tenant-a#1
tenant-a#2
tenant-a#3
tenant-a#4
tenant-a#5
tenant-a#6
tenant-a#7
~~~

Instead of every event using `tenant-a`, the producer deterministically chooses a shard from a well-distributed field such as `orderId`:

~~~java
int shardFor(String orderId, int shardCount) {
    return Math.floorMod(orderId.hashCode(), shardCount);
}

String partitionKey(OrderEvent event) {
    int shard = shardFor(event.orderId(), 8);
    return event.tenantId() + "#" + shard;
}
~~~

With the same `orderId`, the shard is always identical so one order's events stay on the same sub-key. Different orders of the same tenant distribute across shards.

For producers written in multiple languages to compute identical shards, specify the hash algorithm, encoding, and null-handling in the contract. `String.hashCode()` works when all producers follow identical Java semantics; polyglot systems should standardize on a well-specified stable hash such as Murmur3 over UTF-8 bytes.

### Key limitation of salting

Salting changes ordering:

- Before salting, all events for `tenant-a` were processed in order on one partition.
- After salting, shards run in parallel; order holds only within each shard/sub-key.
- Tenant-wide order cannot be inferred from independent partitions.

Use salting only when business rules permit parallel processing across shards. If tenant-wide ordering or updating a single indivisible state is required, salting can corrupt business results.

## 11. Two-stage aggregation after sharding

For associative counts or aggregations, a common pattern aggregates locally per shard and then merges partial results:

~~~mermaid
flowchart TD
    A[Order events for tenant-a] --> B[Partition by tenant-a#shard]
    B --> C1[Shard 0 aggregate]
    B --> C2[Shard 1 aggregate]
    B --> C3[Shard 2 aggregate]
    B --> C4[Shard 3 aggregate]
    C1 --> D[Partial aggregate events]
    C2 --> D
    C3 --> D
    C4 --> D
    D --> E[Merge by original tenant ID]
    E --> F[Tenant summary]
~~~

For example, each shard emits total orders per 1-minute window:

| Shard | Tenant | Window | Partial count |
|---|---|---|---:|
| 0 | tenant-a | 10:00 | 1,250 |
| 1 | tenant-a | 10:00 | 1,110 |
| 2 | tenant-a | 10:00 | 1,390 |
| 3 | tenant-a | 10:00 | 1,180 |

The merge stage sums partial counts to produce the tenant total. This reduces update frequency at the merge stage when shards roll up many events into one partial result.

However, if the merge stage consumes every fine-grained event and updates the same state key continuously, the hotspot simply moves to the final stage. Roll up by window or batch before merging, and measure load at both stages.

Salting does not fit every operation. Sums and counts combine easily; medians, exact distinct counts, event ordering, and certain stateful computations require specialized merge algorithms or different data structures.

## 12. Isolating hot tenants onto dedicated streams

If one tenant vastly exceeds all others and needs distinct operational policies, route that tenant to a dedicated destination:

~~~text
orders.standard  <- majority of tenants
orders.large     <- very high-volume tenant
~~~

Spring Cloud Stream can use a function or `StreamBridge` to route by business attribute:

~~~java
String destinationFor(OrderEvent event) {
    return event.tenantId().equals("tenant-a")
            ? "orders-large"
            : "orders-standard";
}
~~~

In production systems, the hot-tenant list should live in configuration or a controlled routing service, not hard-coded inside the function. Ensure consumers, schemas, retries, and DLQs are configured for both destinations.

Stream isolation prevents large tenants from inflating lag for other tenants. Still, if the dedicated stream uses a single key and requires sequential handling, that single partition retains a throughput cap. In that case, improve consumer capacity within ordering constraints, batch, or shard if business rules permit.

## 13. Custom partition selectors in Spring Cloud Stream

Spring Cloud Stream lets you replace generic partition selection with `PartitionSelectorStrategy` or SpEL `partitionSelectorExpression`. This helps when the default hash distributes a specific key set poorly.

Example selector receiving a normalized key:

~~~java
import org.springframework.cloud.stream.binder.PartitionSelectorStrategy;
import org.springframework.stereotype.Component;

@Component("balancedPartitionSelector")
public class BalancedPartitionSelector
        implements PartitionSelectorStrategy {

    @Override
    public int selectPartition(Object key, int partitionCount) {
        String normalized = String.valueOf(key).toLowerCase();
        return Math.floorMod(normalized.hashCode(), partitionCount);
    }
}
~~~

Binding configuration:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          producer:
            partition-key-expression: payload.tenantId
            partition-count: 12
            partition-selector-name: balancedPartitionSelector
~~~

The selector must return a valid partition index from `0` to `partitionCount - 1`. Normalization must match across producers; otherwise the same key can route to different partitions.

A custom selector cannot split a single key across multiple partitions if the input key stays identical and selection must remain deterministic per key. To split a hot key, change the key contract with a shard suffix or use another business-aware routing strategy.

With the Kafka binder, remember Kafka native partitioning has its own algorithm. Spring Cloud Stream's generic partition selector does not automatically override the Kafka native partitioner in all configurations. Verify which mechanism your binder uses and inspect actual partitions via record metadata.

## 14. Consumer configuration and partition count

Parallel consumers within a consumer group are bounded by assigned partitions. With 6 partitions and 10 consumer instances at concurrency 1, at least 4 consumers receive no partitions. Adding consumers past the partition count does not increase throughput.

Example:

~~~yaml
spring:
  cloud:
    function:
      definition: consumeOrder
    stream:
      bindings:
        consumeOrder-in-0:
          destination: orders
          group: order-processor
          consumer:
            concurrency: 2
~~~

In this example, `concurrency` creates multiple consumer threads inside the application. Compute total slots as instances × concurrency and compare against partition count. Adding consumers only helps when enough independent partitions exist and downstreams have capacity.

For generic Spring Cloud Stream partitioning, consumers use `partitioned`, `instanceIndex`, and `instanceCount`. With the Kafka binder, the Kafka consumer group automatically distributes native partitions across instances; do not enable generic partitioned consumer settings merely because the Kafka topic has partitions.

When planning partition counts, weigh:

- Required parallelism now and in the future.
- Traffic growth rate and message sizes.
- Number of independent keys and key distribution.
- Number of consumer instances/concurrency you can operate.
- File, replica, metadata, and rebalance overhead of many partitions.
- Ability to change partition counts without breaking ordering or state.

## 15. Monitoring and handling hot partitions with Kafka Streams

Kafka Streams creates tasks from input partitions. A hot key still flows into the same task/partition after grouping or repartitioning by that key. Increasing `num.stream.threads` does not split one task across multiple partitions.

For topologies with `groupByKey`, `groupBy`, joins, or aggregations, inspect keys before repartitioning. If every record for one tenant is grouped by tenant ID, that tenant's state store still takes concentrated load.

Options:

- Re-choose the key to an independent entity if business rules allow.
- Salt keys before repartitioning and use two-stage aggregation if operations are associative.
- Isolate hot tenants into separate topologies or `applicationId`s for resource isolation.
- Optimize processors, RocksDB, serialization, and downstreams to cut per-record cost.
- Use windowed aggregation or batching where possible to reduce state store updates.

Never change keys mid-stream in a running stateful topology without a state migration plan. Changelog topics, repartition topics, and local state stores reflect old key semantics; changing them may require state reset or controlled state recovery.

## 16. RabbitMQ: hot queues and scaling strategies

A classic RabbitMQ queue is not equivalent to a Kafka partition. A queue is a FIFO stream; multiple consumers can pull from it, yet a hot queue still hits processing limits on the queue replica.

RabbitMQ notes that a single queue replica is bounded by one CPU core on its hot code path. Consequently, a single queue can bottleneck at very high throughput. Approaches:

- Split workloads across multiple queues by tenant, key group, or business domain.
- Use exchanges and routing keys to route to independent queues.
- Split queues only when messages can run independently; if queue-wide order is required, accept that limit.
- For log/stream workloads requiring scale-out, evaluate RabbitMQ Streams or Super Streams.

### Sharding queues

Example:

~~~text
orders.exchange
  routing key orders.shard.0 -> orders.0
  routing key orders.shard.1 -> orders.1
  routing key orders.shard.2 -> orders.2
  routing key orders.shard.3 -> orders.3
~~~

Producers compute the shard from the business key and publish with the corresponding routing key. Each queue can have its own consumers. Keep the mapping stable so the same entity always lands in the same queue when per-entity ordering is needed.

With the Spring Cloud Stream Rabbit binder, configure destination, group, routing key expressions, and queue bindings per your binder version. Verify provisioned queues/exchanges and actual routing keys via the RabbitMQ Management UI or HTTP API; do not assume a single queue group automatically creates multiple shards.

### RabbitMQ Streams and Super Streams

RabbitMQ Streams are append-only log data structures with semantics distinct from classic queues. Super Streams split one logical stream into multiple partition streams, which can pair with single active consumer to preserve per-partition order.

Super Streams fit when workloads clearly need stream semantics and hit single-stream limits. They add operational complexity; do not switch to Super Streams just to patch a queue with poorly tuned consumers.

## 17. Pulsar: partitioned topics and key routing

A Pulsar partitioned topic is implemented as multiple internal topics spread across brokers. Producers pick partitions via routing modes; subscription types determine how messages are distributed to consumers.

Main routing modes:

| Mode | When message has a key | When message has no key |
|---|---|---|
| `RoundRobinPartition` | Hashes key to corresponding partition. | Distributes round-robin at batching boundaries. |
| `SinglePartition` | Hashes key to corresponding partition. | Picks one partition and sends all messages there. |
| `CustomPartition` | Uses a custom message router. | Router selects the partition. |

To raise throughput while keeping per-key ordering, attach a stable key to messages so same-key messages go to the same partition. Never use keyless `SinglePartition` for workloads needing distribution, because all messages from a producer may pile onto one partition.

### Shared and Key_Shared subscriptions

- `Shared` distributes messages round-robin across consumers with no ordering guarantee.
- `Key_Shared` distributes by key/ordering key; same-key messages are delivered to one consumer, enabling parallelism across keys while keeping per-key order.

When using `Key_Shared`, producers must disable batching or use key-based batching so batches do not mix different keys. If a batch mixes keys and the broker routes by the first key, messages can be delivered to the wrong consumer relative to expected semantics.

Partitioning and subscription are separate decisions. Increasing partition count addresses topic/broker distribution; choosing subscription type governs how consumers split messages. Check both to avoid a hot partition or a hot consumer.

## 18. Measuring before and after changes

A key or shard-count change must be evaluated on the same dataset and time window.

| Metric | Before change | After change | What to confirm |
|---|---|---|---|
| Max/average records per partition | Baseline | Re-measure | Skew ratio decreased. |
| Max/average bytes per partition | Baseline | Re-measure | Byte distribution is more balanced. |
| Max consumer lag | Baseline | Re-measure | Lag on slowest partition dropped. |
| p95/p99 processing latency | Baseline | Re-measure | Latency did not spike from merging or routing. |
| Duplicate/retry rate | Baseline | Re-measure | No abnormal duplicate increase. |
| Out-of-order business events | Baseline | Re-measure | Ordering still satisfies contract. |
| Downstream saturation | Baseline | Re-measure | Bottleneck did not merely shift to DB/API. |

Do not look only at averages. A distribution with a clean average can still hide a hot partition if the top key holds a huge share.

## 19. Migration plan for changing keys or shards

Changing keys can impact ordering, state, and consumers. Controlled migration workflow:

1. Identify entities requiring ordering and confirm with business owners.
2. Measure top keys, per-partition traffic, lag, and latency to quantify skew.
3. Choose strategy: re-key, composite key, salting, tenant isolation, or scaling consumers.
4. Document the new key contract, hash algorithm, shard count, and legacy event handling.
5. Test with realistic data distributions, including hot keys and bursts.
6. If needed, emit to a new topic/version instead of silently changing semantics on the live topic.
7. Run parallel or shadow consumers to compare outputs, avoiding duplicate business side effects.
8. Cut producers/consumers over per plan while monitoring lag and ordering.
9. Keep rollback capability throughout the transition.
10. Delete the old stream only after draining backlog and verifying zero remaining consumers.

If changing Kafka partition counts, inspect impact on key-to-partition mapping and ordering. If using Kafka Streams, evaluate state stores/changelogs and topology migration separately.

## 20. Testing distribution and correctness

Unit test for partition key generation:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class OrderPartitionKeyTest {

    @Test
    void sameOrderAlwaysMapsToSameShard() {
        assertThat(shardFor("order-101", 8))
                .isEqualTo(shardFor("order-101", 8));
    }

    @Test
    void shardIsWithinConfiguredRange() {
        int shard = shardFor("order-202", 8);
        assertThat(shard).isBetween(0, 7);
    }

    @Test
    void differentOrdersCanUseDifferentShards() {
        var shards = java.util.stream.IntStream.range(0, 100)
                .mapToObj(i -> shardFor("order-" + i, 8))
                .distinct()
                .count();

        assertThat(shards).isGreaterThan(1);
    }

    private int shardFor(String orderId, int shardCount) {
        return Math.floorMod(orderId.hashCode(), shardCount);
    }
}
~~~

This test verifies determinism and range, but does not prove real-world balance. Add tests with representative datasets:

- Generate keys following production-like distributions.
- Include one or more heavy hot keys.
- Compute simulated record and byte counts per shard.
- Compare skew ratio before and after the new strategy.
- Verify the same entity stays on the same shard across runs.
- Verify events requiring order still share the same key/partition.
- Verify the merge stage matches unsharded results.

### Integration testing with Kafka

Against a test Kafka broker:

1. Create the topic with the planned partition count.
2. Send realistic keyed records through the Spring Cloud Stream Kafka binder.
3. Read `KafkaHeaders.RECEIVED_PARTITION` on the consumer or inspect producer record metadata.
4. Count records and bytes per partition.
5. Verify identical keys route consistently.
6. Simulate a hot key and observe per-partition lag.
7. Test the sharding strategy and compare distributions.

When testing consumer groups, run multiple instances or concurrency and verify partition assignments. Do not verify producer partition IDs alone; the ultimate goal is consumers handling load with proper latency and order.

## 21. Common pitfalls

| Symptom | Possible cause | Fix |
|---|---|---|
| Added partitions yet one stays hot | One key carries most traffic. | Re-choose key or shard the hot key if ordering allows. |
| Added consumers yet lag stays high | Fewer partitions than consumers or one partition is hot. | Check assignments and per-partition lag. |
| Same customer processed out of order after key change | New key broke required ordering boundary. | Restore aggregate key or add sequence/version handling. |
| Same key lands on different partitions across producers | Inconsistent hash/encoding/selector or mixed binder/native partitioning. | Standardize key and algorithm; inspect actual partitions. |
| Salting produces wrong aggregations | Merge stage miscombines partial state or drops events. | Design idempotent merge with explicit windows and semantics. |
| Hot partition moves to merge stage | Merge updates one root key per fine-grained event. | Roll up partial results per window/batch before merging. |
| Expanding Kafka topic alters ordering | Modulo hash over partition count changed mapping. | Plan migration, drain data, and guard ordering. |
| RabbitMQ has many consumers yet queue stays hot | Bottleneck is a single queue replica or prefetch/downstream. | Shard across queues or evaluate RabbitMQ Streams/Super Streams. |
| Pulsar `Key_Shared` distributes unexpectedly | Producer batches mix keys or keys are missing. | Disable batching or use key-based batching; verify keys. |
| One Pulsar consumer takes most load | Skewed key distribution or uneven key-to-consumer mapping. | Measure top keys, shard hot keys if semantics permit, check mapping. |
| Hash test looks balanced yet production skews | Real distribution differs from assumptions or certain keys cost more. | Measure real traffic, bytes, and processing cost. |

## 22. Pre-deployment checklist

- [ ] Identified the exact business aggregate requiring ordering.
- [ ] Measured key distribution and top keys by records, bytes, and processing cost.
- [ ] Measured lag and throughput per partition or queue.
- [ ] Separated key skew from consumer/downstream bottlenecks.
- [ ] Key cardinality and distribution fit the workload.
- [ ] Kafka native keys and generic Spring Cloud Stream partitioning do not unintentionally overlap.
- [ ] Partition count suffices for planned consumer concurrency.
- [ ] Not relying on partition increases alone to split a single hot key.
- [ ] Salting/sharding used only where whole-key ordering can be relaxed.
- [ ] Valid merge strategy exists for sharded aggregates.
- [ ] Hash algorithm and encoding standardized across producers.
- [ ] Hot-tenant isolation plan ready if needed.
- [ ] RabbitMQ queue topology or Pulsar partitions/subscriptions fit semantics.
- [ ] Distribution tested with representative data and hot-key scenarios.
- [ ] Ordering, duplicates, retries, state migration, and rollback verified.
- [ ] Dashboards monitor skew ratio, lag, processing latency, and downstream saturation.

Mitigating key skew begins by understanding what ordering boundary a key represents. If keys are overly concentrated, the target partition runs hot no matter how many partitions the topic has. Spring Cloud Stream lets you configure keys and partition selection; Kafka, RabbitMQ, and Pulsar each have partitioning semantics that must be respected. Re-choose keys where business rules allow, use composite keys or salting when aggregates can be split, and isolate hot tenants when isolation is needed. Every change must be measured on real data and verified for both distribution and ordering correctness.

## References

- [Spring Cloud Stream — Partitioning](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-partitioning.html)
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream — Partitioning with the Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/partitions.html)
- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Apache Kafka — Producer Configuration](https://kafka.apache.org/42/generated/producer_config.html)
- [Apache Kafka — Monitoring](https://kafka.apache.org/42/operations/monitoring/)
- [RabbitMQ — Queues and Parallelism](https://www.rabbitmq.com/docs/queues)
- [RabbitMQ — Streams and Super Streams](https://www.rabbitmq.com/docs/streams)
- [Apache Pulsar — Partitioned Topics and Routing Modes](https://pulsar.apache.org/docs/next/concepts-messaging/)
- [Apache Pulsar — Producer Routing](https://pulsar.apache.org/docs/client-libraries/producers/)
