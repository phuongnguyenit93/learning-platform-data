# Key Changes, Repartitioning, and Co-Partitioning Requirements

In Kafka Streams, the record key determines which partition data is distributed to. Stateful operations such as aggregations, joins, and KTable updates require records with the same key to be processed at the same stream task. Therefore, when an application changes a record's key, it often must repartition before executing the subsequent stateful operation.

Repartitioning is also the foundation of co-partitioning: topics participating in a key-based join must have the same number of partitions and use the same key distribution strategy. If one side uses `customerId` to select a partition while the other side uses a different partitioner, two records with the same `customerId` can land on two different tasks and the join will fail to find matching data.

## 1. What Does the Record Key Determine?

Kafka stores records in a topic divided into partitions. A record's key is typically used by the partitioner to choose the partition. Records with the same key, when sent using the same partitioning strategy and the same partition count, go to the same partition. This establishes ordering by key within a partition and allows Kafka Streams to process state locally by key.

For example, suppose the `orders` topic has six partitions. If the key is `order-1001`, creation, update, and cancellation events for that order sent under the same partitioning rule will reside on the same partition. Kafka Streams instances can process partitions independently, while all events for the same key are routed to the same task.

| Component | Meaning |
|---|---|
| Record key | Identifier used to group or route data |
| Partition | Log segment of a topic; unit of distribution for consumers/tasks |
| Partitioner | Rule for selecting a partition for a record |
| Key Serde | Converts keys between Java types and `byte[]` |
| Stream task | Unit processing one or more input partitions along with corresponding state |
| State store | Local storage by key for aggregations, joins, or queries |

The key is not merely a data field for filtering. It determines where the record is processed and thus directly affects the correctness of stateful operations.

## 2. When Do You Need to Change the Key?

An order event may initially be keyed by `orderId`, whereas a revenue report needs to aggregate data by `customerId`. In that case, the application needs to change the key from `orderId` to `customerId`.

Example:

| Original Key | Payload | New Key Needed |
|---|---|---|
| order-1001 | customerId=c-42, amount=120 | c-42 |
| order-1002 | customerId=c-17, amount=80 | c-17 |
| order-1003 | customerId=c-42, amount=55 | c-42 |

Both orders `order-1001` and `order-1003` belong to the same customer `c-42`. To aggregate total revenue per customer, both records must be routed to the same partition under key `c-42`.

### 2.1. Changing Value and Changing Key Are Two Different Operations

The Kafka Streams DSL provides common transformations:

| Operation | Changes Value | Changes Key | Marks Repartition Needed |
|---|---:|---:|---:|
| mapValues | Yes | No | No |
| filter | No | No | No |
| filterNot | No | No | No |
| selectKey | No | Potentially | Yes |
| map | Potentially | Potentially | Yes |
| flatMap | Can produce multiple records | Potentially | Yes |
| flatMapValues | Can produce multiple values | No | No |

If you only normalize customer names in the payload while keeping key `orderId`, you can use `mapValues`. If you want to switch to key `customerId`, use `selectKey` or `map`.

Key change example:

~~~java
KStream<String, Order> ordersByCustomer = orders
    .selectKey((orderId, order) -> order.customerId());
~~~

After `selectKey`, each record's logical key is already `customerId`. However, the record has not necessarily been rewritten into the partition corresponding to the new key yet. `selectKey` marks the stream as needing repartitioning; a downstream grouping or join operation can trigger the redistribution step.

Example changing only the value while keeping the key:

~~~java
public record OrderSummary(
    String orderId,
    String customerId,
    BigDecimal amount
) {}

KStream<String, OrderSummary> summaries = orders
    .mapValues(order -> new OrderSummary(
        order.orderId(),
        order.customerId(),
        order.amount()
    ));
~~~

In this example, the key remains `orderId`. Adding a `customerId` field to the payload does not automatically change the partition key.

## 3. Why Does Changing the Key Often Require Repartitioning?

Suppose the input topic is split into six partitions by `orderId`. A task processing partition 2 may receive many different orders. After changing the key to `customerId`, records with the same `customerId` may be scattered across multiple input partitions.

If the task immediately aggregates by `customerId` without redistributing data, the same customer could end up with multiple local state copies across different tasks. The aggregated result would then fail to represent all events for that customer.

Repartitioning solves this problem by:

1. Reading records after the key has been changed.
2. Writing records to an internal repartition topic using the new key.
3. Having Kafka distribute records into partitions based on the new key.
4. Having Kafka Streams read back from the internal topic.
5. Having downstream aggregate or join operations process records with the same key at the same task.

~~~mermaid
flowchart LR
    A["Topic orders<br/>key = orderId"] --> B["selectKey(customerId)"]
    B --> C["Internal repartition topic<br/>key = customerId"]
    C --> D["Partition by customerId"]
    D --> E["groupByKey / aggregate"]
    E --> F["State store by customerId"]
~~~

Repartitioning introduces a write/read boundary through Kafka. It incurs serialization, network, disk I/O, and additional latency costs, but guarantees data redistribution according to the current key.

## 4. Automatic Repartitioning After selectKey, groupBy, and join

The Kafka Streams DSL tracks certain operations that may change the key. When a stream is marked as needing repartitioning, subsequent operations that require records with the same key to reside in the same partition can automatically create an internal repartition topic.

Common cases:

- `selectKey(...).groupByKey(...)`: groups by the new key and repartitions if needed.
- `selectKey(...).join(...)`: joins by the new key and repartitions the re-keyed stream if the topology can do so.
- `groupBy(...)`: computes a new key for grouping and always performs repartitioning.
- `map(...)` or `flatMap(...)` changing the key before aggregate/join: must ensure data has been distributed by the new key.

`groupByKey()` uses the current key and only repartitions if the stream has been marked as needing repartitioning. If the key has not changed, this is usually a cheaper choice than `groupBy()` because it avoids unnecessary repartitioning.

Example:

~~~java
KGroupedStream<String, Order> grouped = orders
    .selectKey((orderId, order) -> order.customerId())
    .groupByKey(
        Grouped.with(Serdes.String(), orderSerde)
    );
~~~

`selectKey` marks the stream as needing repartitioning. The subsequent `groupByKey` uses the new key and triggers repartitioning to gather records with the same `customerId` into the same partition before aggregation.

Not every processor automatically detects that a key was modified. When using the Processor API or a custom processor that may alter the key, explicitly call `repartition()` before a stateful operation if the topology cannot track that change.

## 5. Explicit Repartitioning

You can call `KStream.repartition()` when you want explicit control over the partition count, internal topic name, Serde, or partitioner.

Example:

~~~java
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.kstream.Repartitioned;

KStream<String, Order> ordersByCustomer = orders
    .selectKey((orderId, order) -> order.customerId())
    .repartition(
        Repartitioned.<String, Order>with(
                Serdes.String(),
                orderSerde
            )
            .withName("orders-by-customer")
            .withNumberOfPartitions(12)
    );
~~~

In this example:

- `Serdes.String()` serializes the `customerId` key.
- `orderSerde` serializes the `Order` payload.
- `withName` sets a stable, easily recognizable name for the repartition processor and internal topic.
- `withNumberOfPartitions(12)` requests twelve partitions for the internal topic.

Kafka Streams manages the internal topic created by `repartition()`. The actual name typically takes the form `application.id-orders-by-customer-repartition`. You can use `Topology.describe()` to inspect node names and internal topics created in the topology.

Explicit repartitioning always introduces a repartition boundary, even when the stream has not been marked as needing repartitioning. Do not call it repeatedly in a row without a reason involving the key or partition count, as each call can add another write/read round-trip.

## 6. Aggregating by the New Key

Suppose a Spring Cloud Stream Kafka Streams Binder application receives order events and calculates total revenue per customer. The input topic is keyed by `orderId`, while the state store needs `customerId` as the key.

Data types:

~~~java
import java.math.BigDecimal;

public record Order(
    String orderId,
    String customerId,
    BigDecimal amount
) {}

public record CustomerTotal(
    BigDecimal total
) {
    static CustomerTotal empty() {
        return new CustomerTotal(BigDecimal.ZERO);
    }

    CustomerTotal add(BigDecimal amount) {
        return new CustomerTotal(
            total.add(amount)
        );
    }
}
~~~

Function:

~~~java
import java.util.function.Function;

import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.common.utils.Bytes;
import org.apache.kafka.streams.kstream.Grouped;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.Materialized;
import org.apache.kafka.streams.state.KeyValueStore;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.apache.kafka.common.serialization.Serde;

@Configuration
class CustomerTotalsConfiguration {

    @Bean
    Function<KStream<String, Order>, KStream<String, CustomerTotal>>
    customerTotals(
        Serde<Order> orderSerde,
        Serde<CustomerTotal> totalSerde
    ) {
        return orders -> orders
            .selectKey((orderId, order) -> order.customerId())
            .groupByKey(
                Grouped.with(Serdes.String(), orderSerde)
            )
            .aggregate(
                CustomerTotal::empty,
                (customerId, order, current) ->
                    current.add(order.amount()),
                Materialized
                    .<String, CustomerTotal,
                        KeyValueStore<Bytes, byte[]>>as("customer-totals")
                    .withKeySerde(Serdes.String())
                    .withValueSerde(totalSerde)
            )
            .toStream();
    }
}
~~~

`selectKey` swaps `orderId` for `customerId`. `groupByKey` requires records with the same `customerId` to be grouped into one partition; Kafka Streams creates an internal repartition if needed. `aggregate` updates the state store by `customerId` and emits a changelog as a `KTable`; `toStream()` converts the result into a `KStream` so the binder can send it to the output binding.

In this example, the state store holds the current total revenue for each customer. If the same customer has orders across multiple source partitions, repartitioning guarantees that updates for that customer are handled by the same task.

## 7. What Is Co-Partitioning?

Two or more topics are called co-partitioned when they satisfy the distribution requirements necessary for a key-based join to function correctly:

1. The input topics have the same number of partitions.
2. Producers of the topics use the same partitioning strategy.
3. The same logical key is serialized consistently and maps to the same partition index across all topics.

For example, both `orders.by-customer` and `customers.by-id` have 12 partitions. When a record with key `c-42` in both topics is distributed using the same key Serde and partitioner, both records reside in the partition with the same index. Kafka Streams can assign them to the same task for joining.

~~~mermaid
flowchart TD
    A["orders.by-customer<br/>12 partitions"] --> C["Task processing partition 4"]
    B["customers.by-id<br/>12 partitions"] --> C
    C --> D["Join by customerId"]
    D --> E["OrderWithCustomer"]
~~~

Co-partitioning does not mean both topics have the same data or the same record counts. The requirement is having the same partition count and the same rule mapping a key to its corresponding partition.

## 8. Why Do Joins Require Co-Partitioning?

Kafka Streams performs joins by key. When joining two streams, the task processing a partition must see records from both sides with the same key. If record `c-42` in topic A sits in partition 4 while record `c-42` in topic B sits in partition 9, two independent tasks will not have enough data to join.

Join operations to pay attention to:

| Join Operation | Co-Partitioning Required |
|---|---|
| KStream-KStream | Yes; usually a time-windowed join |
| KStream-KTable | Yes; stream key must match the table partition's key |
| KTable-KTable primary-key join | Yes |
| KStream-GlobalKTable | No co-partitioning required; each instance has a copy of GlobalKTable |
| KTable foreign-key join | Kafka Streams handles internal distribution; does not apply the same co-partitioning requirement as primary-key joins |

Kafka Streams checks the partition counts of join sources during partition assignment. If the partition counts do not match, the application may throw an exception at this step. Kafka Streams cannot automatically verify whether every custom partitioner distributes the same key to the same partition; that responsibility belongs to the application.

## 9. Example: Joining Two KStreams by customerId

Suppose:

- Topic `orders.raw` has 6 partitions and is keyed by `orderId`.
- Topic `customers.raw` has 12 partitions and is keyed by `customerId`.
- The application wants to join orders with customer information by `customerId`.

Before joining, change the order key to `customerId` and repartition both sides to 12 partitions. Even if the `customers` topic already uses `customerId` as its key, if its partition count differs, you still need to repartition to the same partition count within the topology.

Additional data types:

~~~java
public record Customer(
    String customerId,
    String displayName
) {}

public record OrderWithCustomer(
    Order order,
    Customer customer
) {}
~~~

~~~java
import java.time.Duration;
import java.util.function.BiFunction;

import org.apache.kafka.common.serialization.Serde;
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.kstream.JoinWindows;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.Repartitioned;
import org.apache.kafka.streams.kstream.StreamJoined;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderEnrichmentConfiguration {

    @Bean
    BiFunction<
        KStream<String, Order>,
        KStream<String, Customer>,
        KStream<String, OrderWithCustomer>
    > enrichOrders(
        Serde<Order> orderSerde,
        Serde<Customer> customerSerde
    ) {
        return (orders, customers) -> {
            KStream<String, Order> ordersByCustomer = orders
                .selectKey((orderId, order) -> order.customerId())
                .repartition(
                    Repartitioned.<String, Order>with(
                            Serdes.String(), orderSerde
                        )
                        .withName("orders-by-customer")
                        .withNumberOfPartitions(12)
                );

            KStream<String, Customer> customersById = customers
                .repartition(
                    Repartitioned.<String, Customer>with(
                            Serdes.String(), customerSerde
                        )
                        .withName("customers-by-id")
                        .withNumberOfPartitions(12)
                );

            return ordersByCustomer.join(
                customersById,
                (order, customer) ->
                    new OrderWithCustomer(order, customer),
                JoinWindows.ofTimeDifferenceWithNoGrace(
                    Duration.ofMinutes(10)
                ),
                StreamJoined.with(
                    Serdes.String(),
                    orderSerde,
                    customerSerde
                )
            );
        };
    }
}
~~~

This is an example of a KStream-KStream windowed join: two events with the same `customerId` must arrive within a 10-minute window based on record timestamps to produce an output. In real applications, pick a window and grace period suitable for event lateness; the example uses `ofTimeDifferenceWithNoGrace` to illustrate configuring a window without waiting for an extra grace period.

Repartitioning both sides to 12 partitions yields the same partition count and uses the same `String` key Serde. If the input topics are already co-partitioned and no key change is required, you can omit the repartition steps to reduce overhead.

## 10. Using GlobalKTable When Appropriate

`GlobalKTable` is an option for small- or medium-sized reference tables that need lookups from every partition. Kafka Streams replicates the entire `GlobalKTable` dataset to every application instance. Because every instance has a full replica, a `KStream` can join with a `GlobalKTable` without requiring co-partitioning.

| KTable | GlobalKTable |
|---|---|
| Each data partition is processed at its corresponding task | Every instance holds a full copy of the table |
| Primary-key join requires co-partitioning | No co-partitioning required |
| Suitable for large partitioned tables | Suitable for smaller reference datasets |
| Less data replicated to each instance | Consumes memory, network, and sync time on every instance |

Do not use `GlobalKTable` solely to avoid partition design. If the reference table is large, replicating the entire dataset to every instance can substantially increase operational costs.

## 11. Key Serde and Partitioner Must Be Consistent

Co-partitioning depends on key bytes and the partitioner, not just field names in a Java object. Two producers might both use `customerId=c-42` yet serialize it into different bytes or use different partitioners; as a result, they can write to different partitions.

Conditions to verify:

- Same logical key type across topics participating in the join.
- Same Serde or serializer producing consistent byte representations.
- Same partitioner or `StreamPartitioner`.
- Same number of partitions.
- No custom producer distributing keys differently from the rest of the producers.

For example, if the key is a `String`, input bindings can use `Serdes.String()`. If the key is an Avro or custom object type, ensure producers and the Kafka Streams binder use the same schema/Serde and serialization rules.

### 11.1. Per-Binding Serde Configuration in the Kafka Streams Binder

The Spring Cloud Stream Kafka Streams Binder can infer Serdes from function types and Serde beans. When types are complex or there are multiple distinct inputs, declaring Serdes explicitly per binding helps prevent deserialization mismatches.

Example:

~~~yaml
spring:
  cloud:
    function:
      definition: enrichOrders
    stream:
      bindings:
        enrichOrders-in-0:
          destination: orders.raw
        enrichOrders-in-1:
          destination: customers.raw
        enrichOrders-out-0:
          destination: orders.with-customer
    kafka:
      streams:
        bindings:
          enrichOrders-in-0:
            consumer:
              keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
              valueSerde: com.example.OrderSerde
          enrichOrders-in-1:
            consumer:
              keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
              valueSerde: com.example.CustomerSerde
          enrichOrders-out-0:
            producer:
              keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
              valueSerde: com.example.OrderWithCustomerSerde
~~~

Binding names are derived from the function name `enrichOrders`: `enrichOrders-in-0`, `enrichOrders-in-1`, and `enrichOrders-out-0`. Both inputs need compatible key Serdes because the join uses `customerId`. Value Serdes can differ because the two topics carry different data types.

If using Serde beans and the binder can infer them from the function's generic types, you do not necessarily have to declare class names on every binding. When explicit control is needed, use per-binding properties as shown. Check configuration keys against your project's specific Kafka Streams Binder version.

## 12. Distinguishing Kafka Streams Repartitioning from Spring Cloud Stream Partitioning

Spring Cloud Stream has a general binder partitioning mechanism, typically using `partitionKeyExpression` and `partitionCount` on output bindings. That mechanism is useful for middleware where the binder calculates partitions itself or when the application wants a custom partition key.

The Kafka Streams DSL has its own mechanisms:

- `selectKey` changes the record key.
- `groupByKey`, `groupBy`, or `join` can trigger repartitioning.
- `repartition(Repartitioned)` creates an internal topic and redistributes by key/partitioner.
- Kafka Streams manages internal repartition topics inside the topology.

Do not confuse `spring.cloud.stream.bindings.<binding>.producer.partitionKeyExpression` with repartitioning inside a Kafka Streams topology. Output binding partitioning configuration determines where output records are written; `KStream.repartition()` creates a redistribution boundary before subsequent processing operations.

If you need to customize how records are sent from a Kafka Streams Binder output binding, you can provide a `StreamPartitioner` bean and reference it via `streamPartitionerBeanName` on the producer binding. That configures sink output partitioning; it does not replace repartitioning before an aggregation or join.

## 13. Internal Repartition Topics and Operations

Internal repartition topics created by Kafka Streams have names tied to `application.id` and the processor/repartition name. The topic is used to write records after changing keys and then read them back in downstream steps.

Characteristics:

- Kafka Streams manages the lifecycle of internal topics.
- Partition count can be specified with `Repartitioned.withNumberOfPartitions`.
- Key/value Serdes of the repartition topic must match the data types after the key change.
- Internal topics increase network, disk I/O, and latency.
- Internal topics require an appropriate replication factor and broker permissions.

You can set the replication factor for internal topics through Kafka Streams configuration:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            configuration:
              replication.factor: 3
~~~

This is binder-level configuration and applies to processors using that binder. If the application has multiple functions with separate settings, per-function configuration can be used according to your binder version's capabilities.

The principal running Kafka Streams needs permissions to read input topics, write output topics, create/read/write internal repartition topics, and manage state changelog topics as required by the cluster authorizer. Do not grant permissions only to business topics while overlooking internal topics.

## 14. Changing Partition Counts Can Alter Key Placement

When a topic's partition count changes, how keys map to partitions can also change. For instance, a key that previously landed in partition 2 of a six-partition topic may land in a different partition after the topic is expanded to twelve partitions.

This affects:

- Relative ordering of events with the same key across the partition-change boundary.
- Co-partitioning across topics participating in a join.
- Kafka Streams state store and task distribution.
- State/changelog recovery plans when the topology or partition count changes.

Do not increase partitions on one side of a join while forgetting the other side. If topics must remain co-partitioned, plan changes together and re-verify the partitioner. For stateful applications running in production, evaluate a migration or state-rebuild strategy before altering partition counts.

Kafka does not support reducing the partition count of a topic through standard administrative operations. If you need to decrease the partition count, you generally have to create a new topic, migrate data, and switch the application to the new topic under a migration plan.

## 15. Handling Null Keys and Invalid Data

Grouping and joining operations rely on keys. Records with a null key cannot be grouped by `customerId` or matched with a record of the same key on the other side.

Before repartitioning:

- Validate that the field used as the key is not null or blank.
- Decide how to handle records missing `customerId`: reject, DLQ, quarantine, or use another valid business key.
- Do not assign all keyless records to a shared string like `unknown` if doing so funnels all bad data into a single partition.
- Check whether key values are evenly distributed; one customer generating the bulk of traffic can create a hot partition.

A single key with too many records can overload one partition and one task. Repartitioning alone does not solve a hot key if all records still share the same key. When business rules allow, you can shard the key into sub-shards and perform a final aggregation step to combine the shards.

## 16. Testing Repartitioning and Co-Partitioning

Separate testing key-change logic from topology and broker integration testing.

### 16.1. Logic Testing with TopologyTestDriver

`TopologyTestDriver` can verify:

1. `selectKey` produces the `customerId` key accurately.
2. `mapValues` does not change the key.
3. Aggregation gathers records with the same `customerId`.
4. Joins produce results when both sides have matching keys and compatible timestamps.
5. Null-key records or invalid data are handled per policy.

`TopologyTestDriver` tests topology logic in memory; it does not replace verifying that an actual broker creates the right partitions or distributes records through an internal topic.

### 16.2. Integration Testing with Real Kafka

Use Kafka Testcontainers or a cluster integration environment to verify:

- Input topics have the expected number of partitions.
- Producers send the same key to the same partition across all joined topics.
- Internal repartition topics are created with the desired partition count.
- Key Serdes and value Serdes can serialize/deserialize real data.
- Joins do not fail due to mismatched partition counts.
- Records with the same key from both topics reach the same task and produce output.
- Partition count changes are caught during the deployment process.

You can use commands:

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 \
  --describe --topic orders.raw

kafka-topics.sh --bootstrap-server localhost:9092 \
  --describe --topic customers.raw
~~~

Compare the partition counts of the two topics and inspect internal topics created under `application.id`. To verify actual partitioning, send several sample keys to both topics and inspect each record's partition metadata.

## 17. Common Errors and Diagnostics

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Aggregation for the same customerId yields multiple independent results | Changed key without repartitioning before grouping/stateful operation | Use `selectKey` followed by `groupByKey` or `repartition` |
| Join fails to find records with matching keys | Two topics are not co-partitioned or use different partitioners | Check partition counts, key Serde, and partitioner |
| Kafka Streams throws partition error during join | Partition counts of the two sources differ | Repartition one or both sides to the same partition count |
| Internal topic is not created | Missing ACLs, wrong Serde, or broker forbids topic creation | Check broker logs, ACLs, and Serdes |
| Data cannot be deserialized after repartitioning | Incompatible key/value Serde on internal topic | Declare Serdes matching the types after key change |
| One partition has high lag | Key skew or hot key | Analyze key distribution; consider business-level sharding |
| Join produces wrong results after increasing partitions | Joined topics were scaled out of sync or use different partitioners | Plan co-partitioning and migration together |
| Processor API changes key but state is still wrong | No auto-repartition after custom processor | Call `repartition` explicitly |

## 18. Workflow for Designing Key Changes and Joins

1. Identify the current key of each input topic.
2. Identify the business key needed for aggregation or joining.
3. Check whether the new key can be null, skewed, or unstable.
4. Use `selectKey` or `groupBy` to produce the new key.
5. Let the DSL auto-repartition at the grouping/join point when possible; use explicit `repartition` if you need to specify partition count, Serde, name, or partitioner.
6. Verify that joined topics have the same number of partitions.
7. Verify that producers use the same key serialization and partitioning strategy.
8. Configure Serdes for input, output, and internal repartition topics.
9. Verify permissions to create/read/write internal topics and changelog topics.
10. Test with `TopologyTestDriver` and real Kafka.
11. Monitor partition lag, task distribution, state stores, and internal topics.
12. Plan a migration if partition counts must change in production.

## Official References

- [Apache Kafka Streams DSL](https://kafka.apache.org/44/streams/developer-guide/dsl-api/): `selectKey`, `groupByKey`, `groupBy`, automatic repartitioning, and join operations.
- [Apache Kafka Streams - KStream API](https://kafka.apache.org/40/javadoc/org/apache/kafka/streams/kstream/KStream.html): co-partitioning requirements, join behavior, and repartitioning.
- [Apache Kafka - Repartitioned API](https://kafka.apache.org/43/javadoc/org/apache/kafka/streams/kstream/Repartitioned.html): configuring key/value Serdes, name, and partition count for internal repartition topics.
- [Spring Cloud Stream Kafka Streams Binder Reference](https://docs.spring.io/spring-cloud-stream-binder-kafka/docs/current/reference/html/kafka-streams.html): functional binding, Serde inference, stateful processing, and Kafka Streams integration.
- [Spring Cloud Stream Kafka Streams Binder - Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/configuration-options.html): per-binding input/output Serde configuration, application ID, and `StreamPartitioner`.
