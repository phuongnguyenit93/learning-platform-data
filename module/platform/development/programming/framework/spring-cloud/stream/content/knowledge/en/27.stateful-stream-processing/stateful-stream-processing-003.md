# Grouping, Counting, and Aggregating by Key

In event stream processing, many business questions require remembering accumulated results by a key: how many orders each customer has created, what the total transaction amount is for each account, or how many times each product was ordered within a time period. If you only use stateless transformations like `map` and `filter`, the application cannot remember totals computed from previous messages on its own.

Kafka Streams provides `groupByKey`, `groupBy`, `count`, `reduce`, and `aggregate` to group records by key and update accumulated state. The Spring Cloud Stream Kafka Streams binder connects these operations to the `Function`/`Consumer` functional model, input/output bindings, and Spring Boot application configuration. This lesson focuses on choosing the right key, understanding `KTable` results, building counts/aggregations, persisting state stores, and operating stateful topologies.

The examples use the Kafka Streams binder (`spring-cloud-stream-binder-kafka-streams`). This integration is specific to Kafka Streams; the RabbitMQ binder and Pulsar binder do not directly provide Kafka Streams `KStream`/`KTable` types. If using RabbitMQ or Pulsar as the broker, choose a stateful processing mechanism appropriate for the respective binder and platform.

## 1. Problem Statement: Aggregating Events by Key

Suppose an e-commerce system emits `OrderCreated` events to the `orders.created` topic. Each event contains the order ID, customer, and order amount:

```java
public record OrderCreated(
        String eventId,
        String orderId,
        String customerId,
        long totalCents
) {}
```

Some sample events:

| Current Key | eventId | orderId | customerId | totalCents |
| --- | --- | --- | --- | ---: |
| `ORD-101` | `EVT-1` | `ORD-101` | `CUS-A` | 125000 |
| `ORD-102` | `EVT-2` | `ORD-102` | `CUS-B` | 80000 |
| `ORD-103` | `EVT-3` | `ORD-103` | `CUS-A` | 45000 |
| `ORD-104` | `EVT-4` | `ORD-104` | `CUS-A` | 30000 |

If you need to count orders per customer, the aggregation key must be `customerId`, not `orderId`. The result after these four events is:

| customerId | orderCount |
| --- | ---: |
| `CUS-A` | 3 |
| `CUS-B` | 1 |

If you need to sum order totals, the result is:

| customerId | orderCount | totalCents |
| --- | ---: | ---: |
| `CUS-A` | 3 | 250000 |
| `CUS-B` | 1 | 80000 |

The core idea is that every record with the same aggregation key is routed to the same stateful computation. Kafka Streams retains the current result for each key and updates it as new records arrive.

## 2. KStream, KTable, and Data Semantics

Before grouping, you need to distinguish two fundamental data models:

| Type | Meaning | Example |
| --- | --- | --- |
| `KStream<K, V>` | Stream of independent events; each record represents an event that occurred | `OrderCreated`, `PaymentReceived`, `InventoryReserved` |
| `KTable<K, V>` | Table of current state by key; a new record updates the value for that key | Table `customerId -> customerProfile` |

With `KStream`, two records with the same key are two separate events. With `KTable`, two records with the same key usually represent two versions of the same row; the new value replaces the previous one. In a KTable, a record with value `null` is a tombstone, meaning the key is deleted from the table.

When aggregating an event stream, the input is typically a `KStream`. When aggregating a changing table, the input may be a `KTable`, and computations must also account for old values being replaced or keys being deleted.

The Spring Cloud Stream Kafka Streams binder supports input bindings of type `KStream`, `KTable`, and `GlobalKTable`. For counting occurrences of events, `KStream` is the natural choice. For recomputing counts based on current table state, understand `KTable` semantics before choosing an aggregation operation.

## 3. Keys Determine How Grouping Works

In Kafka, a record's key affects which partition the record is written to. Records with the same key are typically sent to the same partition according to the active partitioner. Kafka Streams relies on the key to route records belonging to the same group to the same task and update the corresponding state.

In the order example, if the producer already writes `customerId` as the key, the stream can group by the existing key. If the producer writes `orderId` as the key while the application wants to group by `customerId`, the application must extract the new key from the payload.

These two cases correspond to two operations:

- `groupByKey()`: groups by the record's current key.
- `groupBy(...)`: computes a new key from the current key/value and groups by that new key.

Choosing the right key at the producer can reduce downstream re-keying and repartitioning costs. However, a producer can only choose one key suited to that stream's distribution needs; a single topic cannot simultaneously optimize for every different aggregation if computations require different keys.

## 4. groupByKey: Preserving the Current Key

If records in `orders.by-customer` already have `customerId` as their key, you can use `groupByKey`:

```java
KGroupedStream<String, OrderCreated> ordersByCustomer =
        orders.groupByKey(
                Grouped.with(Serdes.String(), orderCreatedSerde));
```

`groupByKey` does not change the key. It produces a `KGroupedStream`, which is the input type for counting and aggregation operations. When the stream is already partitioned by the right key and no prior operation marked it as needing repartitioning, this is usually more efficient.

If the application previously called `selectKey` to change the key, Kafka Streams marks the stream as needing repartitioning. When a key-based grouping operation runs, the topology uses repartitioning to ensure records with the same key arrive at the same partition before updating the state store.

Do not use `groupByKey` if the current key is still `orderId` while the goal is to group by `customerId`. In that case, orders from the same customer may reside across different partitions and the computation will not produce the intended per-customer totals.

## 5. groupBy: Creating a New Aggregation Key

If the current key is `orderId`, but you want to aggregate by `customerId`, use `groupBy` to extract the key from the payload:

```java
KGroupedStream<String, OrderCreated> ordersByCustomer = orders
        .filter((orderId, event) ->
                event != null && event.customerId() != null)
        .groupBy(
                (orderId, event) -> event.customerId(),
                Grouped.with(Serdes.String(), orderCreatedSerde));
```

In this example:

- The first function receives the current key `orderId` and the `OrderCreated` payload.
- The function returns `customerId`, which becomes the new key for aggregation.
- `Grouped.with` declares Serdes for the new key and the `OrderCreated` value.
- Kafka Streams may create an internal repartition topic to redistribute records by the new key.

`groupBy` can always require repartitioning because the key is recomputed. Repartitioning incurs internal topic write/read, serialization, and network costs. If the stream is already partitioned by the right aggregation key from the start, `groupByKey` can avoid an unnecessary repartition step.

### Do Not Let Null Keys Enter Aggregations

Records with a `null` key cannot be distributed by key as expected. Kafka Streams skips records with null keys in key-based grouping/aggregation operations. Therefore, validate the key before grouping:

```java
KStream<String, OrderCreated> validOrders = orders
        .filter((orderId, event) ->
                event != null
                        && event.customerId() != null
                        && !event.customerId().isBlank());
```

Do not silently replace all null keys with a shared string like `UNKNOWN` if doing so funnels all malformed records into one hot group. If business rules allow grouping records missing keys separately, use an intentional classification value and monitor the number of records routed to that group.

## 6. Serdes Must Match Keys and Values After Grouping

Kafka stores bytes, so Kafka Streams needs a `Serde` (serializer/deserializer) for keys and values at topic boundaries, repartition topics, and state stores.

Common built-in Serdes:

| Java Type | Serde |
| --- | --- |
| `String` | `Serdes.String()` |
| `Long` | `Serdes.Long()` |
| `Integer` | `Serdes.Integer()` |
| `UUID` | `Serdes.UUID()` |
| Business DTO/record | `JsonSerde`, Avro Serde, or custom Serde |

When `groupBy` changes the key type, you must provide a Serde for the new key. When the value is a DTO, make sure the Serde reads/writes the right schema and is compatible with other producers.

Example declaring a JSON Serde for an event:

```java
import org.apache.kafka.common.serialization.Serde;
import org.springframework.kafka.support.serializer.JsonSerde;

@Bean
public Serde<OrderCreated> orderCreatedSerde() {
    return new JsonSerde<>(OrderCreated.class);
}
```

The Kafka Streams binder can infer Serdes from `Function` or `Consumer` parameter types, `Serde` beans registered in the application, and types natively supported by Kafka Streams. If it cannot infer them accurately, configure Serdes explicitly on the binding or inside the topology. In particular, Serdes for `Grouped` and `Materialized` remain the processing code's responsibility when required by the DSL.

For example, binding-level Serdes for an input binding can be configured under `spring.cloud.stream.kafka.streams.bindings.<binding>.consumer.keySerde` and `valueSerde`. For an output binding, the corresponding properties live under `producer.keySerde` and `producer.valueSerde`. Use Serde class names appropriate for your project's version and data format.

## 7. Count: Counting Records by Key

`count()` is appropriate when you need to count records per key. It takes a `KGroupedStream` and returns a `KTable<K, Long>` holding the current count for each key.

```java
KTable<String, Long> orderCounts = ordersByCustomer
        .count(Materialized.as("customer-order-counts"));
```

With three events for `CUS-A`, the current value for that key is `3`. Each time another valid record arrives for `CUS-A`, the state is incremented by one and the KTable emits a new update.

`count()` counts records, not numeric values inside the payload. If each record contains `quantity = 5`, `count()` still only increments by one. To sum quantities or amounts, use `reduce()` or `aggregate()`.

### Converting a KTable to a KStream to Emit Results

Kafka Streams returns the result of `count()` as a `KTable`, because it represents the current value per key. If you want the binder to send updates to an output topic, convert the table to a stream using `toStream()`:

```java
KStream<String, Long> countUpdates = orderCounts.toStream();
```

Each output record represents one update to the current value. For example, `CUS-A` may emit `1`, `2`, and then `3`. The output topic then contains an update history, not just a single record per customer.

If downstream needs the latest state table, it can consume the topic as a changelog/KTable or configure the output topic with log compaction by key. Do not assume `toStream()` automatically deletes old values from the topic.

## 8. Complete Example: Counting Orders by Customer

Here is a Kafka Streams processor using the Spring Cloud Stream functional model:

```java
import java.util.function.Function;

import org.apache.kafka.common.serialization.Serde;
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.common.utils.Bytes;
import org.apache.kafka.streams.KeyValue;
import org.apache.kafka.streams.kstream.Grouped;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.Materialized;
import org.apache.kafka.streams.state.KeyValueStore;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.support.serializer.JsonSerde;

public record OrderCreated(
        String eventId,
        String orderId,
        String customerId,
        long totalCents
) {}

public record CustomerOrderCount(String customerId, long orderCount) {}

@Configuration
public class CustomerOrderCounter {

    @Bean
    public Serde<OrderCreated> orderCreatedSerde() {
        return new JsonSerde<>(OrderCreated.class);
    }

    @Bean
    public Function<KStream<String, OrderCreated>,
            KStream<String, CustomerOrderCount>> countOrdersByCustomer(
                    Serde<OrderCreated> orderCreatedSerde) {

        return orders -> orders
                .filter((orderId, event) ->
                        event != null
                                && event.customerId() != null
                                && !event.customerId().isBlank())
                .groupBy(
                        (orderId, event) -> event.customerId(),
                        Grouped.with(Serdes.String(), orderCreatedSerde))
                .count(Materialized
                        .<String, Long, KeyValueStore<Bytes, byte[]>>as(
                                "customer-order-counts")
                        .withKeySerde(Serdes.String())
                        .withValueSerde(Serdes.Long()))
                .toStream()
                .map((customerId, count) -> KeyValue.pair(
                        customerId,
                        new CustomerOrderCount(customerId, count)));
    }
}
```

In this example:

1. The input binding is `countOrdersByCustomer-in-0`.
2. `groupBy` extracts `customerId` from the payload to form the aggregation key.
3. `Grouped.with` supplies Serdes for the `String` key and `OrderCreated` value.
4. `count` updates the record count per customer.
5. `Materialized.as` names the state store `customer-order-counts`.
6. `toStream` turns KTable updates into output records.
7. `map` builds a `CustomerOrderCount` payload for easier downstream consumption.

Java records can be placed in separate files per project conventions. Ensure the JSON Serde can serialize/deserialize those records and that the schema is agreed upon across producers/consumers.

## 9. Binding Configuration and Application ID

The function above has one input and one output. The Kafka Streams binder automatically derives binding names from the bean name:

- `countOrdersByCustomer-in-0`
- `countOrdersByCustomer-out-0`

Example configuration:

```yaml
spring:
  application:
    name: customer-order-counter
  cloud:
    function:
      definition: countOrdersByCustomer
    stream:
      bindings:
        countOrdersByCustomer-in-0:
          destination: orders.created
        countOrdersByCustomer-out-0:
          destination: customers.order-counts
      kafka:
        streams:
          binder:
            applicationId: customer-order-counter
            brokers: localhost:9092
```

`applicationId` is the identifier of the Kafka Streams application. Replicas of the same application must share the same application ID to coordinate tasks and state under Kafka Streams mechanics. Independent applications need distinct application IDs so they do not share consumer groups and state.

In production, configure an explicit, stable application ID. Do not generate a random ID per replica, as each replica would then become an independent Kafka Streams application, re-read all data, and create its own state store.

The Kafka Streams binder uses `KStream` for input/output in the example. `KTable` and `GlobalKTable` are supported on inputs. If an application defines multiple processors/functions within the same Spring Boot context, explicitly select which functions to activate via `spring.cloud.function.definition` and configure an appropriate application ID for each processor.

## 10. Reduce: Combining Values of the Same Type

`reduce()` fits when the aggregated result has the same type as the input value. For instance, if the grouped input is `KGroupedStream<String, Long>`, you can sum the values:

```java
KTable<String, Long> totalByCustomer = amountsByCustomer
        .reduce(Long::sum, Materialized.as("customer-total-cents"));
```

If a customer has values `100`, `250`, and `50`, the accumulated result is `400`. `reduce` does not require an initial value because the first value in the group becomes the initial value.

`reduce` is commonly used when the merge operation combines two values of the same type, such as:

- Summing amounts.
- Finding a maximum or minimum value.
- Concatenating strings or combining structures of the same type according to business rules.

The reduce function should be associative so that results do not depend on how Kafka Streams groups or restores state. Avoid operations that depend on processing order if the topology can process partitions in parallel.

## 11. Aggregate: Producing a Result Structure Different from the Input Type

`aggregate()` is more general than `reduce()`. It lets you build an accumulated value whose type differs from the input value and requires:

1. `Initializer`: creates the initial value for a key.
2. `Aggregator`: receives the key, new value, and current aggregate, and returns the new aggregate.

For example, suppose you want to compute both order count and total amount per customer. Use `CustomerStats` as the result structure:

```java
public record CustomerStats(long orderCount, long totalCents) {

    public static CustomerStats empty() {
        return new CustomerStats(0, 0);
    }

    public CustomerStats add(OrderCreated event) {
        return new CustomerStats(
                orderCount + 1,
                totalCents + event.totalCents());
    }
}
```

The aggregate operation:

```java
KTable<String, CustomerStats> customerStats = ordersByCustomer
        .aggregate(
                CustomerStats::empty,
                (customerId, event, current) -> current.add(event),
                Materialized
                        .<String, CustomerStats,
                                KeyValueStore<Bytes, byte[]>>as(
                                        "customer-order-stats")
                        .withKeySerde(Serdes.String())
                        .withValueSerde(customerStatsSerde));
```

`aggregate` initializes each customer with `CustomerStats.empty()`. Each new record produces a new `CustomerStats` object with the order count incremented by one and the total amount increased by the event's `totalCents`.

In production, declare the corresponding `Serde<CustomerStats>`, such as a JSON Serde or Avro Serde. When dealing with money, prefer integers in the smallest currency unit like cents or a decimal type with clear rounding rules; do not use `double` for monetary calculations requiring precision.

Example JSON Serde for the aggregate:

```java
@Bean
public Serde<CustomerStats> customerStatsSerde() {
    return new JsonSerde<>(CustomerStats.class);
}
```

### Avoid Mutating Aggregate Objects In Place

Return a new aggregate as shown above rather than mutating the received object in place. Using immutable objects makes logic easier to test and avoids bugs caused by shared references or unclear state updates.

## 12. Comparing count, reduce, and aggregate

| Operation | Input | Initial Value | Result | Example |
| --- | --- | --- | --- | --- |
| `count()` | Grouped records | Automatically initialized to 0 | `Long` | Order count per customer |
| `reduce()` | Values of the same type | Not needed; uses the first value | Same type as input value | Sum of `Long` amounts |
| `aggregate()` | Grouped values | Initializer required | Can differ from input type | Order count, total amount, and latest timestamp in one DTO |

Choose the operation based on data semantics. `count()` does not sum a quantity field inside the payload. `reduce()` is inconvenient when you need to change the result type. `aggregate()` is more flexible, though it requires defining an initializer, aggregator, and state store Serde.

## 13. KGroupedStream and KGroupedTable Are Not the Same

Grouping can produce a `KGroupedStream` from a `KStream` or a `KGroupedTable` from a `KTable`. Update semantics differ:

- With `KGroupedStream`, each record is a new event. `count` increments per record; `aggregate` folds one more value into the state.
- With `KGroupedTable`, a key can be updated with a new value or deleted via a tombstone. When a row changes groups, the aggregation must reflect subtracting the old value from the old group and adding the new value to the new group.

Therefore, `aggregate` operations on a grouped table can require both an adder and a subtractor to reverse the effect of the old value. Do not apply KStream event-counting logic to a changelog table without accounting for updates and deletes.

For example, if the `ordersById` table has key `ORD-1` with customer `CUS-A`, and later the same key is updated to customer `CUS-B`, that is a modified row. When counting orders per customer from a KTable, `CUS-A`'s count must decrease and `CUS-B`'s count must increase. Treating that update as a brand-new order creation event produces wrong counts.

## 14. What Is a Materialized State Store?

`count`, `reduce`, and `aggregate` need to retain state across records. Kafka Streams materializes the results into a state store. When using the high-level DSL, the state store is created automatically whenever the topology contains an operation that requires state.

Naming the store with `Materialized.as("customer-order-counts")` helps:

- Give a stable name for observing and querying state.
- Configure Serdes for the store's keys/values.
- Configure retention for windowed stores when applicable.
- Connect the store to Interactive Queries APIs if the application needs to read current state.

For persistent state stores, data is typically stored locally on the instance (e.g., RocksDB) and backed up by a Kafka changelog topic. When an instance fails or a task moves to another instance, Kafka Streams can restore state by reading the changelog. This is why state stores can preserve accumulated results across restarts without requiring the application to reload all state from an external database.

Do not disable changelog logging for critical state stores without understanding the consequences: the store loses full recovery from its changelog and cannot have standby replicas through that mechanism.

### State Store Names Must Be Stable and Unique

Do not reuse the same store name for independent aggregations within the same topology. The store name also becomes part of operational infrastructure; renaming it can cause Kafka Streams to create a new store/changelog and rebuild state from the input topic. Treat renames as migration changes, especially for topics with finite retention.

## 15. Materialized State Stores in the Kafka Streams Binder

For DSL operations like `count(Materialized.as(...))`, the store is created by the topology. If an input binding is a `KTable` and you want to materialize the incoming data into a specifically named store, the Kafka Streams binder supports the `materializedAs` property on the consumer binding:

```yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          bindings:
            process-in-1:
              consumer:
                materializedAs: incoming-customer-table
```

This property is for materializing an incoming `KTable` binding. It does not replace `Materialized.as(...)` on `count`, `reduce`, or `aggregate` in the DSL. Distinguish the input table's state store from the state store created by an aggregation operation.

With the low-level Processor API, the application may need to register a `StoreBuilder` bean manually. With the high-level DSL, stateful operations usually create the needed stores automatically; only declare them manually when the topology or API requires it.

## 16. Windowed Aggregation: Aggregating by Key and Window

Unwindowed aggregations retain one accumulated value per key for the entire lifetime of stored state. If the business question is "how many orders did each customer place in the last 5 minutes" or "how many units of each product sold per hour", you need to combine grouping with windowing.

Common window types:

| Type | Behavior | Example |
| --- | --- | --- |
| Tumbling | Fixed-size, non-overlapping windows | Count orders in each 5-minute interval |
| Hopping | Fixed-size, potentially overlapping windows with an advance step | Count orders over 10 minutes, updated every minute |
| Sliding | Windows based on timestamp difference between records; used for corresponding computations/joins | Compare two events occurring within 30 seconds |
| Session | Activity-based windows that extend on new events and close after an inactivity gap | Group a customer's activity sequence |

Example counting orders per customer in 5-minute windows, allowing late events up to 1 minute:

```java
import java.time.Duration;

import org.apache.kafka.streams.kstream.TimeWindows;

KTable<Windowed<String>, Long> fiveMinuteCounts = ordersByCustomer
        .windowedBy(TimeWindows.ofSizeAndGrace(
                Duration.ofMinutes(5),
                Duration.ofMinutes(1)))
        .count(Materialized.as("customer-order-counts-5m"));
```

The result key is `Windowed<String>`, containing the customer ID and window metadata. Do not discard the window start/end if downstream needs to distinguish two separate windows for the same customer.

### Event Time, Grace Period, and Late Events

Kafka Streams uses the record timestamp from `TimestampExtractor` to determine the window. If a record arrives late but its timestamp falls in a window that has not closed yet, the grace period allows it to still be counted. Once stream time passes the window end plus grace, overly late records are excluded from that window's computation.

The grace period is not a fixed waiting time before emitting any results. It defines the acceptable lateness threshold for the window. Choose it based on real lateness distributions and business requirements.

### Emit Updates Continuously or Only Final Results?

A windowed aggregation KTable can emit updates whenever the count changes. If downstream only needs the final result when the window closes, you can use suppression (`untilWindowCloses`) to buffer and emit only the final result. A suppression buffer needs bounded capacity and a policy when full; do not use an unbounded buffer for production traffic without sizing memory first.

## 17. Repartitioning, Partition Count, and Hot Keys

When `groupBy` changes the key, Kafka Streams may create an internal repartition topic. The partition count of the repartition topic affects parallelism. Key choice also governs load distribution:

- If most records belong to one customer ID, one partition can become a hot partition.
- If the key has too low cardinality, useful task concurrency is limited.
- If the key is a random value, records for the same entity will not land in the same state.
- If producers use different serialization or partitioners, records with the same logical key may not be distributed consistently.

To scale, consider source partition counts, repartition topics, instance count, and stream threads. Adding instances alone does not create more partitions or split a hot key. Any specific key still has to be processed sequentially within the task owning that partition.

If you change partition counts, re-evaluate key distribution, state stores, and processing order. Some keys may map to new partitions; state is migrated and restored via Kafka Streams mechanics, but business ordering across the migration boundary still requires careful design.

## 18. Duplicates and Count Correctness

`count()` increments by one for each record processed by the topology. If the same event is published twice with the same `eventId`, a plain count still increments by two. Kafka Streams cannot automatically deduce that two records represent the same business event just because their payloads match.

If the source can emit duplicates, consider:

- Using a unique `eventId` and deduplicating before grouping.
- Maintaining a state store recording processed event IDs within an appropriate retention window.
- Setting a deduplication time bound to prevent unbounded state growth.
- Designing idempotent producers and appropriate transactions when publishing events.
- Testing restart/replay scenarios to verify counts do not inflate unexpectedly.

Kafka Streams provides processing guarantees to coordinate offsets, state stores, and output topics within Kafka's scope. Exactly-once mode can reduce duplicate effects from Kafka Streams internal retries, but it does not automatically eliminate two duplicate business events with different `eventId`s and does not make an external database commit atomic alongside Kafka.

## 19. Interactive Queries: Reading Current Aggregated State

Once a state store is materialized with a stable name, the application can query current values without re-reading the entire output topic. Kafka Streams supports Interactive Queries; the Spring Cloud Stream Kafka Streams binder provides `InteractiveQueryService` to access state stores.

Conceptual example:

```java
ReadOnlyKeyValueStore<String, Long> store =
        interactiveQueryService.getQueryableStoreType(
                "customer-order-counts",
                QueryableStoreTypes.keyValueStore());

Long count = store.get("CUS-A");
```

The specific API should be used inside a bean injected with `InteractiveQueryService` and the matching store type. When the application runs across multiple instances, each instance holds only a subset of state based on its assigned partitions/tasks. To query an arbitrary key, identify which instance owns that key and route the request to the right host. Configuring `application.server` and an appropriate discovery/routing mechanism is required for distributed queries.

Interactive Queries is a read-only state API. Do not mutate the state store directly through a query API to alter aggregated results; all updates should flow through the topology so changelogs and results stay consistent.

## 20. Testing Grouping and Aggregation

You should test the topology at multiple levels:

### Unit Testing Key-Mapping Logic

Verify that events with a valid `customerId` are grouped properly; null events or missing keys are filtered or handled per policy. Verify that records with the same customer ID produce the same grouping key.

### TopologyTestDriver

Kafka Streams provides `TopologyTestDriver` to test topologies without a real Kafka broker. Tests can create input topics, pipe records with keys/timestamps, read output topics, and assert count/aggregate results.

Scenarios to cover:

- Two events with the same key increment the count from 1 to 2.
- Two different keys maintain independent state.
- `groupBy` switches from order ID to customer ID.
- Input, output, and state store Serdes work properly.
- Records with null keys or invalid payloads are handled according to policy.
- Window boundaries, grace periods, and late events.
- Duplicate event IDs do not inflate results if the topology includes deduplication.

### Integration Testing with Kafka

Test against a real broker or Testcontainers to verify repartition topics, changelog topics, ACLs, application ID, recovery after restart, and scaling behavior. `TopologyTestDriver` does not fully simulate networking, broker rebalances, topic provisioning, or state recovery from changelogs.

## 21. Observing and Operating Stateful Aggregations

Key metrics include:

- Input and output throughput per processor.
- Consumer lag and processing latency.
- Rebalance counts and assigned task/partition counts.
- State store restoration time after restarts or task migrations.
- Local state store size and disk usage.
- Changelog write rate and internal repartition topic size.
- Key count, per-key record distribution, and signs of hot partitions.
- Dropped record counts due to null keys, schema errors, or exceeding window grace.
- Duplicate rate if the application performs deduplication.

When state store restoration is slow, inspect changelog size, local state directory, broker throughput, and partition assignments. When one partition lags significantly behind others, check for key skew before simply adding more instances.

## 22. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Count stays 0 or never increases | Wrong binding, wrong function definition, or records lack a valid key | Check bindings, payloads, and keys before grouping. |
| All customers share the same count | Accidentally using a shared key or `groupByKey` when the current key is not customer ID | Use `groupBy` to extract the right key or fix the producer key. |
| One key has multiple states across partitions | Inconsistent producer/partitioner or key mutated before grouping | Normalize keys and ensure repartitioning before aggregating. |
| Application fails with Serde error on startup or runtime | Incompatible Serde used for key/value/state store | Configure Serdes explicitly for bindings, `Grouped`, and `Materialized`. |
| State store is recreated on every deploy | Changed application ID, store name, or wiped local state/changelog | Keep application ID and store names stable; manage migrations with a plan. |
| Total amount is wrong after duplicates | Count/aggregate treats every record as a new event | Deduplicate by event ID or ensure idempotent producers. |
| KTable output emits multiple updates | `toStream()` emits changelog updates rather than only a final snapshot | Have downstream understand update semantics or use a compacted topic for latest-by-key. |
| Window misses late records | Stream time already passed window end + grace | Choose an appropriate grace period and monitor late records. |
| One partition has very high lag | Key skew/hot key | Re-evaluate the key, partitioning scheme, or intentional business-level sharding. |
| Interactive query cannot find key | Key resides on another instance or store is not ready yet | Use host metadata, `application.server`, and retry while the store initializes. |

## 23. Implementation Checklist for Key-Based Aggregation

Before writing the topology, answer:

1. Is the input an event `KStream` or a state `KTable`?
2. Which business key defines the aggregation group?
3. Is the current key already right, or must `groupBy` compute a new key?
4. Is repartitioning needed, and do internal topics have sufficient partitions/ACLs?
5. Which Serdes are used for keys, values, repartitioning, and state stores?
6. Do you need `count`, `reduce`, or `aggregate`?
7. Do you need time/session windows or a rolling total by key?
8. Does the state store have a stable name and appropriate changelog?
9. Is the output an update stream or does downstream need a snapshot/latest value per key?
10. How are duplicates, late events, and schema changes handled?
11. Are the application ID, partition count, and replica count appropriate?
12. Which metrics, alerts, and integration tests prove the topology recovers correctly?

## References

- [Spring Cloud Stream Kafka Streams Binder — Programming Model](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/programming-model.html)
- [Spring Cloud Stream Kafka Streams Binder — State Store](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/state-store.html)
- [Spring Cloud Stream Kafka Streams Binder — Serialization and Deserialization](https://docs.spring.io/spring-cloud-stream-binder-kafka/docs/current/reference/html/kafka-streams.html)
- [Apache Kafka Streams — DSL API: Grouping, Aggregating and Windowing](https://kafka.apache.org/documentation/streams/developer-guide/dsl-api/)
- [Apache Kafka Streams — Processor API and Fault-tolerant State Stores](https://kafka.apache.org/documentation/streams/developer-guide/processor-api/)
- [Apache Kafka Streams — Interactive Queries](https://kafka.apache.org/documentation/streams/developer-guide/interactive-queries/)

Cross-check against the documentation for the Spring Cloud Stream release train and Kafka Streams version your project uses, especially window APIs, Serde inference, application ID configuration, and state stores. Examples in this lesson illustrate the functional binder model; specific property names or APIs may vary across versions.

## Conclusion

Grouping and aggregating by key form the foundation of stateful stream processing. `groupByKey` uses the existing key; `groupBy` derives a new key and may trigger repartitioning. After grouping, `count` counts records, `reduce` combines values of the same type, and `aggregate` lets you build a state structure different from the input type. The result is typically a `KTable` materialized into a state store that can be converted into a `KStream` to emit updates. To keep calculations accurate and recovery reliable, choose keys carefully, configure Serdes, keep state store/changelog names stable, handle duplicates and windows properly, and test both the topology and real Kafka environments.
