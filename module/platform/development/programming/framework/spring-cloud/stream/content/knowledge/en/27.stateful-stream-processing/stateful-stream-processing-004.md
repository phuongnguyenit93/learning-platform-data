# Joining KStream, KTable, and GlobalKTable

In event processing, a transaction stream often needs to be enriched with reference data such as customer profiles, product catalogs, or account states. Kafka Streams provides three essential abstractions to represent data and perform joins: KStream, KTable, and GlobalKTable. Choosing the right input type determines the join semantics, partition requirements, how state is stored, and scaling costs.

KStream represents independent events, where each record is an occurrence. KTable represents the latest state by key, built from a changelog supporting inserts, updates, and deletes. GlobalKTable also represents the latest state, except every Kafka Streams instance reads all partitions of the source topic to maintain a complete local copy. Consequently, a KStream-KStream join is a time-windowed join; a KStream-KTable join is a table lookup triggered when an event arrives; a KTable-KTable join produces a continuously updated result table; and a KStream-GlobalKTable join is well suited for enriching with reference data by foreign key without requiring the two topics to be co-partitioned.

The Spring Cloud Stream Kafka Streams binder lets you declare these types directly in `Supplier`/`Function`/`Consumer` signatures. The binder creates input bindings corresponding to `KStream`, `KTable`, or `GlobalKTable`, and the application then uses the Kafka Streams DSL to build the topology. This lesson covers the semantics of each join type, partitioning requirements, windows/grace periods, Serdes, state stores, binder configuration, testing, and operations.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish KStream, KTable, and GlobalKTable by record semantics.
- Choose the appropriate join type for events, state tables, and reference data.
- Implement KStream-KStream joins with `JoinWindows` and grace periods.
- Implement KStream-KTable joins to enrich events with the latest state.
- Implement KTable-KTable joins to build a continuously updated result table.
- Use KStream-GlobalKTable joins for foreign-key lookups.
- Explain co-partitioning, repartitioning, and partition-key constraints.
- Configure multiple input bindings in the Spring Cloud Stream Kafka Streams binder.
- Select Serdes, materialize state stores, and understand tombstones.
- Test joins with `TopologyTestDriver` and verify real behavior against Kafka.

## 1. Three Ways of Viewing Data in Kafka Streams

Kafka stores records as key-value pairs inside partitions. Kafka Streams adds semantics to that sequence of records by interpreting it either as an event stream or as a state changelog.

### 1.1. KStream: Event Stream

KStream is an unbounded stream of records. Each record is treated as an independent event, similar to appending a new entry to a ledger. Two records with the same key do not mean the second replaces the first.

Example:

~~~text
Topic clicks:
  (user-17, 1)
  (user-17, 3)
~~~

These are two click events. Summing values per user yields 4. The second record does not erase the first record.

KStream is suitable for:

- Order creation events.
- Payment confirmation events.
- Page views or clicks.
- Activity logs and device events.
- Transactions requiring time-based analysis.

### 1.2. KTable: Latest State by Key

KTable is built from a changelog stream. A record with an existing key is treated as an update to that key's current value. A null value is a tombstone, representing deletion of the key from the table.

Example:

~~~text
Topic customer-profile:
  (user-17, "Bronze")
  (user-17, "Gold")
  (user-22, "Silver")
  (user-22, null)
~~~

Final state:

~~~text
user-17 -> Gold
~~~

The `Gold` record replaces `Bronze`. The tombstone removes `user-22` from the table. These are upsert/delete semantics, similar to a relational table updated by primary key.

KTable is suitable for:

- Current customer profiles.
- Latest order statuses.
- Active price sheets or configurations.
- CDC data reflecting inserts/updates/deletes from a database.
- Continuously updated dimension tables.

### 1.3. GlobalKTable: Full Replica on Every Instance

GlobalKTable is also a changelog table, except every Kafka Streams instance reads all partitions of the source topic and maintains a full replica in a local state store. A regular KTable only reads the subset of partitions assigned to an instance/task; GlobalKTable reads the entire topic's data on every instance.

Suppose the `products` topic has six partitions and the application runs three instances:

~~~text
KTable:
  Instance A reads a subset of assigned partitions
  Instance B reads a subset of assigned partitions
  Instance C reads a subset of assigned partitions

GlobalKTable:
  Instance A holds a replica of all six partitions
  Instance B holds a replica of all six partitions
  Instance C holds a replica of all six partitions
~~~

GlobalKTable is useful when a high-volume event stream needs to look up a small or medium reference table, such as mapping `productId` to product name, `customerId` to segment, or region code to geographic details.

In return, every instance must store the entire table and read the entire changelog. This increases disk, memory, network, and broker load. GlobalKTable has no notion of event time; the join is not a temporal join.

### 1.4. Comparison Table

| Characteristic | KStream | KTable | GlobalKTable |
|---|---|---|---|
| Record semantics | Independent event | State update by key | State update by key |
| Duplicate key records | Retained as new events | Replaces current value | Replaces current value |
| Null value | Usually ignored in joins | Tombstone deletes key | Tombstone deletes key |
| Data per instance | Subset of assigned partitions | Subset of assigned partitions | All partitions |
| Common joins | Stream-stream, stream-table | Table-table, stream-table | Stream-global-table |
| Co-partitioning | Required for stream/table equi-joins | Required for equi-joins | Not required when joining with KStream |
| Local state cost | Per topology/window | Per assigned partitions | Entire table on every instance |

## 2. Choosing a Join by Business Semantics

Before writing code, identify what the data on both sides represents:

- Both sides are events occurring over time: KStream-KStream.
- One side is an event, the other side is the latest state: KStream-KTable.
- Both sides are latest state and the output must update as either changes: KTable-KTable.
- Events need to look up a full reference table, potentially via a foreign key: KStream-GlobalKTable.

| Join Operation | Windowed? | Join Key | Partition Requirement | When Output Emits |
|---|---|---|---|---|
| KStream-KStream | Yes | Equal keys and timestamps within window | Co-partitioned | When a new record matches a record from the other side |
| KStream-KTable | No (by default) | Equal keys | Co-partitioned | When a KStream record arrives |
| KTable-KTable equi-join | No | Equal keys | Co-partitioned | When either table changes |
| KTable-KTable foreign-key join | No | Foreign-key value of left table equals right table key | Kafka Streams handles internal co-partitioning | When a related side changes |
| KStream-GlobalKTable | No | Key extracted by mapper looked up in global table | No co-partitioning required | When a KStream record arrives |

Kafka Streams supports inner/left/outer for KStream-KStream; inner/left for KStream-KTable and KStream-GlobalKTable; and inner/left/outer for KTable-KTable equi-joins. Foreign-key KTable-KTable supports inner and left joins, not outer joins. KTable-GlobalKTable joins are not supported.

## 3. KStream-KStream Join: Connecting Two Event Streams Over Time

A KStream-KStream join is always a windowed join. Without a time bound, the state store would have to retain unmatched records indefinitely and could grow without limit. `JoinWindows` defines the time interval within which two records with the same key are considered related.

For example, an e-commerce service has two topics:

- `orders`: `OrderCreated` events.
- `payments`: `PaymentAuthorized` events.

The application needs to match an order with a payment if both events share the same `orderId` and arrive within a five-minute interval.

~~~text
orders stream                     payments stream
  order-81 @ 10:00:00               order-81 @ 10:02:10
          \                         /
           \                       /
            +-- same key + window -+
                       |
                       v
             OrderWithPayment
~~~

### 3.1. Inner Join

An inner join emits output only when matching records are found on both sides. If `OrderCreated` has no `PaymentAuthorized` within the window, an inner join emits no result for that order.

### 3.2. Left Join

A left join retains records from the left side. If no matching right-side record arrives within the window, the left record can be emitted with a `null` right value after the window and grace period expire, according to the semantics of the API in use.

### 3.3. Outer Join

An outer join retains unmatched records from both sides. A record appearing only in `orders` or only in `payments` can produce an output with one side `null` after the window closes.

With newer `JoinWindows` APIs, left/outer joins emit unmatched results after the window closes and the grace period has elapsed. Older deprecated overloads may have different eager-emit semantics; use the API matching your project's Kafka Streams version and declare the grace period explicitly.

### 3.4. Example Code

~~~java
import java.time.Duration;
import java.util.function.BiFunction;

import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.kstream.JoinWindows;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.StreamJoined;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderJoinConfiguration {

    @Bean
    BiFunction<KStream<String, OrderCreated>,
            KStream<String, PaymentAuthorized>,
            KStream<String, OrderWithPayment>> joinOrders() {

        return (orders, payments) -> orders.join(
                payments,
                OrderWithPayment::new,
                JoinWindows.ofTimeDifferenceAndGrace(
                        Duration.ofMinutes(5),
                        Duration.ofSeconds(30)),
                StreamJoined.with(
                        Serdes.String(),
                        orderCreatedSerde(),
                        paymentAuthorizedSerde()));
    }
}
~~~

`OrderCreated`, `PaymentAuthorized`, `OrderWithPayment`, and the two domain Serdes are illustrative types. In a real project, provide Serdes matching your active schemas. If your Kafka Streams version does not yet include the `ofTimeDifferenceAndGrace` factory, use the compatible API for that version and specify the grace period explicitly; do not copy examples blindly from another version.

In the example, the two streams are joined on a `String` key. `OrderCreated` and `PaymentAuthorized` must use the same `orderId` as the Kafka record key, the same partitioning strategy, and the same partition count so records with the same `orderId` reach the same stream task.

### 3.5. Window and Grace Period

The join window determines the maximum timestamp difference allowed between two records to be joined. The grace period defines how long the system continues accepting late-arriving records after the window ends.

Example:

- Join window: 5 minutes.
- Grace period: 30 seconds.
- `OrderCreated` has timestamp 10:00.
- `PaymentAuthorized` has timestamp 10:04:30: still inside the window.
- `PaymentAuthorized` arrives late after the window and grace have closed: it is no longer joined into that result.

The grace period is a trade-off:

- A longer grace period lets late data be processed, but retains state longer and can delay left/outer outputs.
- A shorter grace period reduces wait time and state size, but drops more late-arriving records.

Choose based on actual producer latency, event-time semantics, and business SLAs. Timestamps must be generated consistently; do not use consumer processing time instead of event time if business logic requires joining by occurrence time.

### 3.6. One Record Can Match Multiple Records

A KStream-KStream join is not always one-to-one. If multiple records with the same key exist within the same window on either side, a new record can emit multiple outputs against stored records from the other side.

For instance, an order might have multiple payment attempts. Decide whether business logic wants to join all attempts, only the successful attempt, or a single transaction. You may need to filter/deduplicate prior to joining or use a dedicated key for payment attempts.

## 4. KStream-KTable Join: Enriching Events with Current State

A KStream-KTable join is a non-windowed table lookup. Each time a KStream record arrives, Kafka Streams looks up the current value in the KTable by key and passes both values to the `ValueJoiner`.

Example:

- `KStream clicks`: `(userId, ClickEvent)`.
- `KTable user-regions`: `(userId, region)`.
- Output: `(userId, ClickWithRegion)`.

~~~text
KStream clicks                    KTable user-regions
  user-17 -> click                  user-17 -> Hanoi
            \                       /
             +---- lookup by key --+
                        |
                        v
             ClickWithRegion(Hanoi)
~~~

### 4.1. Semantics to Remember

- Only KStream records trigger the join.
- KTable records update the state store, but do not on their own re-emit past KStream records.
- Inner join drops a stream record if no corresponding key exists in the table yet.
- Left join emits the stream record even without a table value; `ValueJoiner` receives `null` on the table side.
- A KTable tombstone deletes the key from state; tombstones do not trigger a join by themselves.
- Standard joins use the latest value known to the task at the time the stream record is processed.

This means KStream-KTable is not an event-time join. If an event arrives late and needs to look up the dimension version effective at the time the event occurred, evaluate a versioned KTable with a grace period in supported versions.

### 4.2. Example Code

~~~java
@Bean
BiFunction<KStream<String, Long>,
        KTable<String, String>,
        KStream<String, RegionWithClicks>> enrichClicks() {

    return (clicks, regions) -> clicks.leftJoin(
            regions,
            (count, region) -> new RegionWithClicks(
                    region == null ? "UNKNOWN" : region,
                    count),
            Joined.with(
                    Serdes.String(),
                    Serdes.Long(),
                    Serdes.String()));
}
~~~

In this example, the click stream and region table both use `userId` as the key. A left join ensures clicks still appear when the region profile has not been loaded yet or has been deleted. If `join` were used instead of `leftJoin`, clicks without a matching region would produce no output.

### 4.3. When Is KStream-KTable Not Enough?

Suppose a click event was emitted at 09:00 but arrives at Kafka Streams at 09:10. Meanwhile, the user changed region from Hanoi to Da Nang. A standard join may read the current Da Nang state, even though the event occurred while the user was in Hanoi.

If business logic requires information effective at event time:

- Use a versioned KTable if your Kafka Streams version and join API support temporal lookups.
- Configure a consistent timestamp extractor.
- Configure a grace period to wait for late table updates.
- Specify history retention for the versioned store.
- Test cases where a stream event arrives before a table update carrying an older timestamp.

If you only need the latest state at processing time, standard KStream-KTable is simpler and more appropriate.

## 5. KTable-KTable Join: Building a Continuously Updated Result Table

A KTable-KTable join joins two state tables by key and returns a new KTable. This is a non-windowed join, akin to joining two relational tables. Kafka Streams materializes the state of both tables to maintain the current snapshot.

Example:

- `KTable customers`: `customerId -> Customer`.
- `KTable loyalty`: `customerId -> LoyaltyTier`.
- Result `KTable`: `customerId -> CustomerProfile`.

~~~text
KTable customers                 KTable loyalty
  c-10 -> Customer                 c-10 -> GOLD
             \                     /
              +---- join by key --+
                         |
                         v
             KTable CustomerProfile
~~~

### 5.1. Output Updates From Both Sides

Unlike KStream-KTable, changes on either KTable can update the join output:

1. Customer `c-10` updates their address: the output profile is updated.
2. Loyalty for `c-10` changes from `GOLD` to `PLATINUM`: the output profile is updated.
3. Customer is deleted via a tombstone: the corresponding result is updated/deleted according to join semantics.

The resulting KTable is a changelog table. When converted to a KStream via `toStream()`, each change to the result table is emitted as a changelog record.

### 5.2. Example Code

~~~java
@Bean
BiFunction<KTable<String, Customer>,
        KTable<String, LoyaltyTier>,
        KTable<String, CustomerProfile>> buildCustomerProfile() {

    return (customers, loyalty) -> customers.leftJoin(
            loyalty,
            (customer, tier) -> new CustomerProfile(
                    customer,
                    tier == null ? LoyaltyTier.NONE : tier));
}
~~~

This is a left equi-join by `customerId`. When there is no loyalty record, the profile still exists with the default tier. If an inner join were used, customers without loyalty records would be absent from the result table.

### 5.3. Foreign-Key Join

Two tables do not always share the same key. For example:

- `KTable orders` is keyed by `orderId` and its value contains `customerId`.
- `KTable customers` is keyed by `customerId`.

A KTable-KTable foreign-key join uses an extractor to pull `customerId` from the left table's value and look up the key in the right table:

~~~java
KTable<String, OrderWithCustomer> ordersWithCustomer =
        orders.leftJoin(
                customers,
                Order::customerId,
                (order, customer) -> new OrderWithCustomer(order, customer));
~~~

A foreign-key join does not require the two topics to be co-partitioned the way a regular equi-join does; Kafka Streams manages internal coordination. One update in the right table can trigger updates for every left-side record referencing that key. This fan-out cost should be factored in when a single customer is referenced by many orders or entities.

Foreign-key joins are only available in Kafka Streams versions supporting this API. Verify your dependency version before using it, and remember that foreign-key joins do not support outer joins.

## 6. KStream-GlobalKTable Join: Foreign-Key Lookup

GlobalKTable allows a KStream record to look up a table using a key derived from the record's content, without requiring the stream key and table key to be identical.

Example:

- `KStream orders`: keyed by `orderId`, value contains `customerId`.
- `GlobalKTable customers`: keyed by `customerId`.
- Join mapper extracts `customerId` from `Order` and looks it up in `GlobalKTable`.

~~~java
@Bean
BiFunction<KStream<Long, Order>,
        GlobalKTable<Long, Customer>,
        KStream<Long, EnrichedOrder>> enrichOrder() {

    return (orders, customers) -> orders.join(
            customers,
            (orderId, order) -> order.customerId(),
            (order, customer) -> new EnrichedOrder(order, customer));
}
~~~

The `KeyValueMapper` in the second argument maps the KStream record into the lookup key for the GlobalKTable. Thus, `orderId` can differ from `customerId`.

### 6.1. No Co-Partitioning Required

GlobalKTable reads all partitions of the reference topic on every instance. Each instance holds a local replica of the entire table, so stream records can look up foreign keys without requiring matching keys to sit on the same partition across both topics.

### 6.2. Not a Temporal Join

GlobalKTable has no notion of time and does not synchronize event time between table updates and stream records. When a stream record is processed, the join uses whatever value is currently present in that instance's GlobalKTable replica. Do not use GlobalKTable if you need to query the exact dimension version at the event's timestamp.

### 6.3. Bootstrap and Replication Cost

When a Kafka Streams instance restarts or scales up, it must bootstrap all existing data in the source topic before beginning stream processing for the topology. Large topics can increase startup time and network load.

Every instance stores the full table. If the table is 8 GB and you run 5 instances, total local state storage can approach 40 GB before accounting for overhead, changelogs, and other state stores. Measure real data sizes and calculate replication costs.

### 6.4. When Should You Use It?

GlobalKTable is appropriate when:

- The reference table is small or medium-sized.
- Many stream partitions need to look up arbitrary dimension keys.
- Reference data updates fairly regularly without requiring temporal joins.
- You need star joins against multiple dimension tables.
- The stream's key distribution is skewed and you want to avoid hot partitions on the reference table.

If the table is very large or you only need lookups by the already-partitioned key, KTable is usually more resource-efficient.

## 7. Co-Partitioning: A Critical Requirement for Equi-Joins

KStream-KStream, KStream-KTable, and KTable-KTable equi-joins require co-partitioned data. This ensures records with the same key from both sides arrive at the same stream task.

Two conditions:

1. Input topics have the same number of partitions.
2. Producers on both sides use the same partitioning strategy so the same key always routes to the same partition number.

Example:

~~~text
orders:       P0  P1  P2  P3
payments:     P0  P1  P2  P3

orderId 81 -> partition 2 on both topics
orderId 95 -> partition 0 on both topics
~~~

If `orders` has 6 partitions while `payments` has 3 partitions, Kafka Streams can fail when partitions are assigned to the topology. If partition counts match but producers use different partitioners, Kafka Streams cannot automatically verify that identical keys went into identical partitions.

### 7.1. Keys Are Part of the Data Contract

Align on:

- Key type and serialization format.
- Key normalization rules (e.g., casing, tenant prefix).
- Partition counts of joined topics.
- Partitioner or hashing strategy.
- How partition counts are changed once topics hold data.

If the producer uses `orderId` as the key on `orders` but `paymentId` as the key on `payments`, a key-based equi-join will fail to match even when both payloads contain `orderId`.

### 7.2. Repartitioning When Keys Change

Operations like `selectKey` or `map` that alter the key can mark a stream as needing repartitioning before performing grouping or joining. Kafka Streams can create an internal repartition topic when the topology needs it.

Example:

~~~java
KStream<String, Order> byCustomer =
        orders.selectKey((orderId, order) -> order.customerId());

KStream<String, EnrichedOrder> result =
        byCustomer.join(customers, this::enrich);
~~~

When changing the key to `customerId`, ensure the stream is repartitioned by the new key before the join. For complex topologies, you can call `repartition(Repartitioned...)` to control the partition count, name, and Serde of the internal topic.

If you only change the value while preserving the key, prefer `mapValues` or `flatMapValues` where appropriate. Those operations preserve the key and usually avoid unnecessary repartitioning.

### 7.3. Exceptions to Co-Partitioning

Two cases do not require co-partitioning in the equi-join sense:

- KStream-GlobalKTable: every instance holds the entire GlobalKTable.
- KTable-KTable foreign-key join: Kafka Streams manages internal coordination.

Do not apply these exceptions to KStream-KTable or KTable-KTable equi-joins.

## 8. Configuring Multiple Input Bindings in Spring Cloud Stream

The Kafka Streams binder infers binding types from the function signature. A function taking a `KStream` and a `KTable` gets two input bindings; a function taking a `KStream` and a `GlobalKTable` also gets two input bindings.

Example:

~~~java
@Bean
BiFunction<KStream<String, Long>,
        KTable<String, String>,
        KStream<String, RegionWithClicks>> enrichClicks() {
    return (clicks, regions) -> clicks.leftJoin(
            regions,
            (count, region) -> new RegionWithClicks(
                    region == null ? "UNKNOWN" : region,
                    count),
            Joined.with(
                    Serdes.String(),
                    Serdes.Long(),
                    Serdes.String()));
}
~~~

For a function named `enrichClicks`, the binder creates by default:

- `enrichClicks-in-0`: input `KStream`.
- `enrichClicks-in-1`: input `KTable`.
- `enrichClicks-out-0`: output `KStream`.

Destination configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: enrichClicks
    stream:
      bindings:
        enrichClicks-in-0:
          destination: clicks
        enrichClicks-in-1:
          destination: user-regions
        enrichClicks-out-0:
          destination: enriched-clicks
~~~

The binder inspects generic types in the function signature to materialize a `KStream` or `KTable`. If the second input declares `KTable`, the binder consumes the destination as a changelog table; if it declares `GlobalKTable`, the binder reads all partitions into a global table.

### 8.1. Three or More Inputs

For two inputs, `BiFunction` can be used. For three or more inputs, the Kafka Streams binder supports curried `Function`s:

~~~java
record OrderWithCustomer(Order order, Customer customer) {
    Long productId() {
        return order.productId();
    }
}

record EnrichedOrder(OrderWithCustomer order, Product product) {}

@Bean
Function<KStream<Long, Order>,
        Function<GlobalKTable<Long, Customer>,
                Function<GlobalKTable<Long, Product>,
                        KStream<Long, EnrichedOrder>>>> enrichOrder() {

    return orders -> customers -> products ->
            orders.join(
                    customers,
                    (orderId, order) -> order.customerId(),
                    (order, customer) -> new OrderWithCustomer(order, customer))
            .join(
                    products,
                    (orderId, order) -> order.productId(),
                    (order, product) -> new EnrichedOrder(order, product));
}
~~~

`OrderWithCustomer` keeps both `Order` and `Customer` after the first join while exposing `productId` so the next join can look up `Product`. This snippet illustrates how the binder binds multiple inputs via curried functions. If there are too many inputs, consider splitting the topology into smaller processors for readability and operability.

## 9. Serdes and Schemas for Join Data

Joins must serialize/deserialize keys and values with the correct types. Mismatched Serdes can cause deserialization failures, state store errors, or unreadable outputs.

Options:

- Use Kafka Streams default Serdes when all bindings share the same primitive types.
- Declare Serdes per input binding when each topic has a different value type.
- Provide `Serde` beans so the binder infers them from generic types.
- Pass Serdes directly into `Joined.with`, `StreamJoined.with`, or `Materialized`.

Example Serde configuration for two inputs:

~~~yaml
spring:
  cloud:
    function:
      definition: enrichClicks
    stream:
      bindings:
        enrichClicks-in-0:
          destination: clicks
        enrichClicks-in-1:
          destination: user-regions
        enrichClicks-out-0:
          destination: enriched-clicks
      kafka:
        streams:
          bindings:
            enrichClicks-in-0:
              consumer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: org.apache.kafka.common.serialization.Serdes$LongSerde
            enrichClicks-in-1:
              consumer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: org.apache.kafka.common.serialization.Serdes$StringSerde
~~~

The full prefix for Kafka Streams properties is `spring.cloud.stream.kafka.streams.bindings.<binding-name>.consumer`. In this example, both inputs use `String` keys; `clicks` has `Long` values and `user-regions` has `String` values.

Binder-level default Serdes can be configured via:

~~~properties
spring.cloud.stream.kafka.streams.binder.configuration.default.key.serde=org.apache.kafka.common.serialization.Serdes$StringSerde
spring.cloud.stream.kafka.streams.binder.configuration.default.value.serde=org.apache.kafka.common.serialization.Serdes$StringSerde
~~~

These are application-wide defaults. When multiple inputs have different value types, prefer per-binding Serdes or explicit Serdes in the join to avoid relying on an unsuitable default.

### 9.1. Schema Compatibility

If producers evolve schemas, consumer Serdes must understand both old and new payloads during rolling upgrades. With Avro/Protobuf/JSON Schema, verify schema registry settings, compatibility modes, default fields, and versions.

Joins generally require compatible keys on both sides. If one topic uses `customerId` as a `String` while the other uses `Long` or different normalization, the join will not find matching records even when business values represent the same identifier.

## 10. State Stores and Join Data Lifecycle

Joins are stateful operations. Kafka Streams maintains state to locate counterpart records and preserve result tables.

### 10.1. KStream-KStream State

A stream-stream join stores records in a window store until they are no longer needed for the join window. Window size, grace period, and retention affect state size.

An overly long window increases storage and restore times. An overly short window misses business-valid late-arriving records.

### 10.2. KTable-KTable State

Both KTables are materialized into local state stores to hold the latest snapshot. The join output is also a changelog table and can be materialized if needed for queries or downstream steps.

For an incoming KTable binding, the binder provides the `materializedAs` property to name the state store:

~~~yaml
spring:
  cloud:
    function:
      definition: enrichClicks
    stream:
      kafka:
        streams:
          bindings:
            enrichClicks-in-1:
              consumer:
                materializedAs: user-regions-store
~~~

Stable store names improve topology observability and can support interactive queries when the application configures an appropriate queryable store.

### 10.3. GlobalKTable State

Every instance stores the full GlobalKTable. When a new instance starts, it must read and restore the full global table dataset before processing stream records in the topology. If the table is large, bootstrap duration can slow scaling or recovery after failures.

### 10.4. Changelogs and Recovery

Kafka Streams can write changelogs for state stores to restore state after task migrations or application restarts. Do not arbitrarily delete changelog topics or internal repartition topics. Changing store names or topology structure can create new internal topics and affect state recovery.

## 11. Tombstones and Deletion Handling

In a KTable, a record with a `null` value is a tombstone, signifying key deletion. It is not an ordinary null business value.

Example:

~~~text
customer-profile:
  (c-10, Customer("Lan"))
  (c-10, Customer("Lan Nguyen"))
  (c-10, null)  -> deletes c-10 from KTable
~~~

KStream-KTable join:

- If the table receives a tombstone, the key's state is deleted.
- A tombstone does not emit a join output on its own.
- Subsequent stream events with that key will not find a table value.

KTable-KTable join:

- Deleting on one side can update or delete the corresponding join result.
- Verify inner/left/outer semantics and tombstones on both sides.

GlobalKTable also interprets null values as tombstones. If a dimension entry is deleted, each instance's global replica updates via the changelog. Do not use an object containing null fields as a tombstone if the Serde does not serialize it as a true Kafka record with a `null` value.

## 12. Choosing KTable or GlobalKTable?

| Question | KTable | GlobalKTable |
|---|---|---|
| Is the table large? | Suitable for large partitioned tables | Best kept small/medium since every instance holds all data |
| Joining by the same key? | Ideal for co-partitioned equi-joins | Supports foreign-key lookups |
| Need event-time/versioned lookups? | Can use versioned KTable and grace in supported versions | No temporal semantics |
| Instance count scales up | Each instance holds only assigned partitions | Each instance reads and holds the entire table |
| Key skew/hot partitions | Subject to key distribution | Can avoid certain hot-partition lookups locally |
| Bootstrap | Restores assigned state partitions | Must bootstrap the entire table on every instance |

Do not choose GlobalKTable merely to avoid fixing partitioning on a large topic. If the reference table is very large, replication overhead can outweigh the cost of repartitioning or maintaining a properly co-partitioned KTable.

## 13. Diagnosing Joins That Produce No Output

When the topology runs but output is empty or missing records, inspect in order:

1. Binding type: are inputs actually bound as `KStream`, `KTable`, or `GlobalKTable` matching the function signature?
2. Destination: is each binding reading the right topic? Are records present in those topics?
3. Keys: do both sides share the same key type, values, and normalization rules?
4. Partitions: do equi-joins share the same partition count and partitioning strategy?
5. Serdes: do keys/values deserialize properly? Are schema errors logged?
6. Join type: is an inner join dropping unmatched records? Should it be a left join?
7. Window: for stream-stream joins, do matching records share the same key and have timestamps within `JoinWindows`?
8. Grace: are records arriving after the grace period?
9. Tombstones: was the KTable key deleted before the stream event arrived?
10. Global bootstrap: did `GlobalKTable` finish loading before stream processing started?
11. State restore: is a state store still restoring or failing on disk/permissions?
12. Topology: were repartition topics and internal topics created properly?

Kafka Streams can check input partition counts in certain joins and fail when they are unequal. It cannot verify whether producers on two topics use the same partitioning strategy; that remains the producer design's responsibility.

## 14. Testing Joins

Kafka Streams provides `TopologyTestDriver` in the `kafka-streams-test-utils` artifact. The test driver executes the topology synchronously without a real broker, letting you pipe records into simulated topics, read outputs, and inspect state stores.

### 14.1. Testing KStream-KTable Joins

Build the topology with the `clicks` stream, `regions` table, and `enriched-clicks` output. In the test:

1. Pipe record `user-17 -> Hanoi` to the `regions` topic to populate the KTable.
2. Pipe record `user-17 -> 5` to the `clicks` topic.
3. Read output and assert the result contains region `Hanoi` with click count `5`.
4. Pipe a tombstone for `user-17` to `regions`.
5. Pipe the next click and assert the left join returns the default/null region per application logic.

### 14.2. Testing KStream-KStream Windowed Joins

Use `TestInputTopic` to pipe two records with the same key and explicit timestamps:

- `OrderCreated` at 10:00.
- `PaymentAuthorized` at 10:03.

Assert output is produced when timestamps fall within `JoinWindows`. Then send a record outside the window and assert no match occurs. For left/outer joins, advance event time past the window and grace period to verify unmatched results emit at the expected time.

### 14.3. Testing KTable-KTable Joins

Pipe sequentially:

1. Customer `c-10`.
2. Loyalty `c-10 = GOLD`.
3. Loyalty `c-10 = PLATINUM`.
4. Customer or loyalty tombstone.

Assert the output changelog reflects all updates and deletions. Do not assert only the first output; a KTable produces continuously changing state.

### 14.4. Testing GlobalKTable

Pipe data into the dimension topic and verify `GlobalKTable` loads. Then pipe stream events using foreign keys for lookup. Verify:

- The key mapper returns the expected dimension key.
- No co-partitioning is required between stream and global table.
- Dimension updates are reflected in the local replica.
- The join is not treated as a temporal lookup.

### 14.5. Limitations of TopologyTestDriver

`TopologyTestDriver` does not replace broker integration tests. It does not thoroughly test:

- Consumer groups and partition assignment.
- Rebalances across multiple instances.
- Actual co-partitioning across two topics.
- ACLs, networking, and broker failures.
- State restoration from changelog topics in a cluster.
- Serialization with real broker/schema registry configurations.

Use Testcontainers or a Kafka test cluster to test topology deployment, partition counts, Serdes, and state recovery.

## 15. Observability and Operations

Monitor the following metrics:

| Metric | Meaning |
|---|---|
| Consumer lag by input topic/partition | Input backlog building up |
| Join output rate | Rate of outputs produced by the join |
| Join match/miss rate | How many records find or miss a counterpart |
| Window store size | State retained for stream-stream joins |
| KTable state size | Local state table footprint |
| GlobalKTable bootstrap duration | Time to load the full table on each instance |
| State restore duration | Time to restore state after restarts/rebalances |
| Repartition topic throughput | Overhead from key changes or repartitioning |
| Serde/deserialization errors | Schema, key, or value errors |
| Late record/drop count | Records arriving past window/grace |
| RocksDB/disk usage | Local state store resource usage |

### 15.1. Alerting

Consider alerting when:

- Join output rate drops to 0 while inputs still have traffic.
- Join miss rate spikes sharply.
- Consumer lag grows continuously.
- GlobalKTable bootstrap takes abnormally long.
- State stores approach disk limits or restoration fails.
- Dropped late records exceed threshold.
- Repartition topics exhibit abnormal traffic or lag.

A join miss is not always an error. Inner joins naturally ignore unmatched records; compare against business expectations and use left joins/metrics if unmatched records need visibility.

## 16. Common Mistakes

1. **Using KStream for state data**: updates with the same key are treated as new events. Use KTable when the topic is a changelog.
2. **Using KTable for an event log**: updates with the same key overwrite prior state. Use KStream when every event must be kept.
3. **Using GlobalKTable for overly large tables**: every instance reads and stores the full table. Use KTable if co-partitioning is feasible.
4. **Mistaking KStream-KTable join for a temporal join**: standard joins look up current state at stream-record processing time. Use a versioned KTable when event-time lookups are needed.
5. **Assuming table updates automatically re-emit old stream records**: only KStream triggers KStream-KTable joins. Design a KTable-KTable join if both sides must update the output.
6. **Missing co-partitioning**: matching keys can land on different tasks. Align partition counts and partitioners.
7. **Checking only partition counts**: Kafka does not verify producer partitioning strategies. Audit producer keys/partitioners.
8. **Not setting window/grace explicitly**: late records get dropped or left/outer results emit unexpectedly. Configure windows according to SLAs.
9. **Ignoring tombstones**: reference tables can retain deleted entries. Define deletion semantics and test null values.
10. **Using the wrong Serde**: keys/values fail to deserialize or joins miss keys. Declare Serdes per binding.
11. **Changing keys without repartitioning**: matching keys can land on different tasks. Use appropriate repartitioning.
12. **Underestimating GlobalKTable cost**: every instance bootstraps and stores the entire table. Measure storage, network, and startup time.
13. **Testing only the first output of a KTable join**: misses subsequent updates/tombstones. Test the full changelog.
14. **Relying solely on TopologyTestDriver to validate deployment**: the test driver does not verify group assignment or brokers. Add integration tests.

## 17. Join Design Checklist

When building a join topology in Spring Cloud Stream:

1. Determine whether each topic is an event log or a state changelog.
2. Choose KStream, KTable, or GlobalKTable according to semantics.
3. Identify the join key and whether a foreign-key mapper is needed.
4. For stream-stream joins, set `JoinWindows` and grace periods explicitly.
5. For equi-joins, verify partition counts and partitioning strategies across topics.
6. Repartition if keys change or inputs are not yet co-partitioned.
7. Configure input bindings and Serdes matching generic types.
8. Name materialized state stores if querying or observability is needed.
9. Define inner, left, or outer semantics and handle nulls/tombstones.
10. Test updates, deletes, late records, duplicates, and unmatched cases.
11. Run integration tests on real Kafka for partitions, Serdes, and state recovery.
12. Monitor lag, join misses, state size, bootstrap duration, and late records after deployment.

## Conclusion

KStream represents events; KTable represents the latest state by key; GlobalKTable is a full replica of a changelog on every Kafka Streams instance. KStream-KStream joins match events by key within a time window. KStream-KTable joins look up state as events arrive. KTable-KTable joins produce a continuously updated result table. KStream-GlobalKTable joins enable foreign-key lookups without co-partitioning, at the cost of loading and storing the entire table on every instance.

In the Spring Cloud Stream Kafka Streams binder, the `Function`/`BiFunction` signature determines input binding types and the binder provisions the corresponding `KStream`, `KTable`, or `GlobalKTable`. Join correctness depends on keys, partitioning, Serdes, windows/grace, and state stores. Test matches, non-matches, updates, tombstones, and late records, and verify co-partitioning and GlobalKTable costs against a real broker.

## References

- [Spring Cloud Stream — Kafka Streams Programming Model](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/programming-model.html)
- [Spring Cloud Stream — Kafka Streams Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/configuration-options.html)
- [Spring Cloud Stream — State Store](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/state-store.html)
- [Apache Kafka — Streams DSL and Joins](https://kafka.apache.org/44/streams/developer-guide/dsl-api/)
- [Apache Kafka — Testing a Streams Application](https://kafka.apache.org/44/streams/developer-guide/testing/)
