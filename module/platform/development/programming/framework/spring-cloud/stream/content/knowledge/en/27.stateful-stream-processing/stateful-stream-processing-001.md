# Stateless Transformations in a Kafka Streams Topology

The Kafka Streams DSL lets you build a topology by chaining transformations on `KStream` and `KTable` (written here as KStream and KTable). Many processing steps only need to inspect the current record, check a condition, transform the key/value, or route the record to another branch. Those steps are called **stateless transformations**.

A stateless transformation does not need to remember previously processed records and does not need its own state store to compute a result. Given the same input record, the same data and logic produce the same result, independent of the stream's history. Typical examples include filtering valid orders, normalizing customer codes, changing payload formats, splitting a string into multiple tokens, or routing events by type.

In Spring Cloud Stream, the Kafka Streams binder lets you declare a topology using the functional model with `Supplier`, `Function`, or `Consumer` beans taking KStream/KTable parameters. This lesson focuses on stateless transformations in a topology, how they affect keys, partitions, Serdes, and record ordering, and how to distinguish them from stateful aggregation, joins, and windowing.

## 1. Topology and What Stateless Means

A topology is a continuous processing graph: data flows from a source topic through one or more processor nodes to a sink topic or another destination. The DSL expresses those nodes as chained calls such as filter, mapValues, flatMapValues, branch, and merge.

~~~mermaid
flowchart LR
    A[orders.created] --> B[filter: valid amount]
    B --> C[mapValues: normalize data]
    C --> D[branch: classify]
    D --> E[orders.accepted]
    D --> F[orders.review]
~~~

The steps above process each record without looking up or updating accumulated state from prior records. Kafka Streams still coordinates tasks, consumers, producers, and offsets; "stateless" here refers to the business transformation, not that the application has no runtime state whatsoever.

A transformation is considered stateless when the result for the current record does not depend on:

- The total number of records that arrived previously.
- Previous values of the same key.
- An accumulated time window or time interval.
- Lookup results from a state store maintained by the topology.

Examples:

| Requirement | Transformation |
|---|---|
| Drop events with an invalid amount. | filter |
| Convert currency codes to uppercase. | mapValues |
| Split a line into multiple words. | flatMapValues |
| Change the key to orderId. | selectKey or map |
| Route events to the appropriate branch. | split/branch |
| Merge two input streams. | merge |
| Log/record metrics as records pass through. | peek |

Conversely, count, aggregate, reduce, windowed aggregation, and join need to maintain or look up state by key, window, or table. Those operations belong to the stateful transformations group.

## 2. KStream and KTable Before Choosing a Transformation

KStream represents a sequence of event records. Each record is interpreted as an independent event, usually corresponding to a single occurrence in reality. Two records with the same key are still two separate events.

KTable represents a changelog by key. A new record with the same key updates the current value of that key; a record with a null value can be interpreted as a tombstone to delete the key from the table.

| Characteristic | KStream | KTable |
|---|---|---|
| Record semantics | New event/entry in the stream. | Change to the current value by key. |
| Two records with the same key | Both are events. | The later record updates the earlier record. |
| Null value | A record with a null value; handling depends on the operation. | Usually represents a tombstone/key deletion. |
| Stateless transformation | Creates a new KStream. | Can create a new KTable while preserving changelog semantics. |
| Example | Transaction history, page views, logs. | Current state of an account or customer profile. |

`mapValues` and `filter` can be applied to both KStream and KTable without changing the nature of the abstraction. When transforming a KTable, keep in mind that the output still reflects updates by key rather than a typical append-only event sequence.

## 3. filter and filterNot: Keeping or Dropping Records

filter evaluates a predicate for each record and only keeps records that return true. filterNot keeps records when the predicate returns false. Neither needs a state store.

Example keeping only transactions with positive amounts:

~~~java
KStream<String, Long> positiveAmounts = transactions
    .filter((accountId, amount) -> amount != null && amount > 0);

KStream<String, Long> rejectedAmounts = transactions
    .filterNot((accountId, amount) -> amount != null && amount > 0);
~~~

The predicate receives both key and value. If the condition only depends on the value, you can use a lambda that ignores the key. Decide explicitly how nulls should be handled; do not let an automatic comparison unbox null and cause a NullPointerException.

filter does not modify the record. The record's key, value, and metadata are forwarded according to Kafka Streams semantics. Records that fail the condition are dropped from that output branch; they are not automatically sent to a DLQ. If you need to keep rejected records for investigation, create a separate branch using split/branch or an intentional error-handling topology.

Example filtering by event type:

~~~java
KStream<String, OrderEvent> paidOrders = orders
    .filter((orderId, event) -> event != null
        && "PAID".equals(event.status()));
~~~

If you want to exclude a set of conditions, filterNot can express it directly:

~~~java
KStream<String, OrderEvent> nonCancelledOrders = orders
    .filterNot((orderId, event) -> event != null
        && "CANCELLED".equals(event.status()));
~~~

## 4. mapValues: Transforming the Value While Preserving the Key

mapValues takes each record's value and produces a new value. The original key is preserved. This is usually the right choice when you need to normalize or enrich value content without changing the partitioning key.

~~~java
KStream<String, String> normalizedNames = customerNames
    .mapValues(name -> name == null ? "" : name.trim().toUpperCase());
~~~

Example with order events:

~~~java
record OrderCreated(String orderId, String customerId, long amount) {}
record OrderSummary(String customerId, long amount, String category) {}

KStream<String, OrderSummary> summaries = orderEvents
    .mapValues(event -> new OrderSummary(
        event.customerId(),
        event.amount(),
        event.amount() >= 1_000_000 ? "LARGE" : "STANDARD"
    ));
~~~

In the example, the record's key remains the order key. Including customerId in the value does not change the Kafka record's key. If a later step needs to group by customerId, you must change the key or group by the customerId field and accept a repartition when required.

mapValues is generally more efficient than map when you do not need to change the key because it does not mark the stream as needing repartitioning. An overload of the operation allows the mapper to also receive the original key alongside the value; use that overload when the transformation needs to read the key while still keeping the output key unchanged.

## 5. map: Transforming Both Key and Value

map receives a key and value and returns a new KeyValue. You can change the key, the value, or the data type of both.

~~~java
import org.apache.kafka.streams.KeyValue;

KStream<String, Long> normalized = amounts.map((accountId, amount) ->
    KeyValue.pair(
        accountId.trim().toUpperCase(),
        amount == null ? 0L : amount
    )
);
~~~

Unlike mapValues, map can change the key. This matters because the Kafka partitioner typically uses the key to determine the partition. However, calling map or selectKey does not immediately move records to a new partition. Kafka Streams marks the topology as needing repartitioning when a downstream operation requires data to be distributed by the new key, such as groupByKey or certain types of joins.

If you only change the value, prefer mapValues. If you change the key to prepare for grouping/joining, understand that a repartition topic may be created, incurring extra network I/O, serialization, and latency.

## 6. selectKey: Changing the Key While Preserving the Value

selectKey creates a new stream with a key computed from the current record while keeping the value unchanged.

~~~java
KStream<String, OrderCreated> ordersByCustomer = orders
    .selectKey((oldOrderKey, event) -> event.customerId());
~~~

Before the transformation, records may be partitioned by orderId. After the transformation, the logical key is customerId. If the topology proceeds to groupByKey or join by customerId, Kafka Streams may need to repartition to ensure records with the same customerId arrive at the same partition.

Do not change the key merely for display convenience. The key determines locality, partitioning, and per-entity ordering guarantees. Before changing the key, clarify how downstream steps will use the new key.

## 7. flatMapValues and flatMap: One Record Producing Multiple Records

flatMapValues transforms one record into zero, one, or more new records while preserving the original key. This is a good choice when you need to split or expand a value without changing the key.

~~~java
import java.util.Arrays;

KStream<String, String> wordsByDocument = documents
    .flatMapValues(text -> Arrays.asList(text.split("\\s+")));
~~~

If a document has key `doc-1` and value `"kafka streams stateless"`, the topology produces three records with the same key `doc-1`, each carrying one word. Because the key does not change, this operation does not require repartitioning solely from splitting the value.

flatMap lets you produce multiple new key/value pairs:

~~~java
KStream<String, Integer> tokens = documents.flatMap((documentId, text) -> {
    List<KeyValue<String, Integer>> result = new ArrayList<>();
    for (String word : text.split("\\s+")) {
        result.add(KeyValue.pair(word.toLowerCase(), 1));
    }
    return result;
});
~~~

The illustrative snippet assumes `java.util.ArrayList`, `java.util.List`, and `org.apache.kafka.streams.KeyValue` have been imported.

In this example, each word becomes the new key. If groupByKey or a join is called afterward, Kafka Streams may need to repartition to bring identical words into the same partition. Use flatMapValues when the key must be kept; only use flatMap when you actually need to change the key.

| Operation | Output records per input record | Can change key? | Repartition due to key change? |
|---|---:|---|---|
| mapValues | 1 | No | No |
| map | 1 | Yes | May be needed in a subsequent grouping/join step |
| flatMapValues | 0..n | No | Not due to key change |
| flatMap | 0..n | Yes | May be needed in a subsequent grouping/join step |
| filter | 0 or 1 | No | No |

## 8. split/branch: Conditional Record Routing

split creates a branching split from a KStream. Predicates are evaluated in declaration order. Each record enters the first branch whose predicate returns true; it is not automatically duplicated across all matching branches.

~~~java
import org.apache.kafka.streams.kstream.Branched;
import org.apache.kafka.streams.kstream.Named;

Map<String, KStream<String, OrderEvent>> branches = orders
    .split(Named.as("order-"))
    .branch(
        (key, event) -> event != null && event.amount() >= 1_000_000,
        Branched.as("large")
    )
    .branch(
        (key, event) -> event != null && event.amount() > 0,
        Branched.as("standard")
    )
    .defaultBranch(Branched.as("invalid"));

KStream<String, OrderEvent> largeOrders = branches.get("order-large");
KStream<String, OrderEvent> standardOrders = branches.get("order-standard");
KStream<String, OrderEvent> invalidOrders = branches.get("order-invalid");
~~~

The `large` branch is checked before `standard` so that records with large amounts are not captured by the `standard` branch. If there is no default branch, records that match no predicate are dropped from the created branches.

Branch only creates logical streams within the topology. To persist them to Kafka, connect each branch to a sink topic using `to(...)` or configure the corresponding output binding in the binder model. Do not confuse a logical branch with an already-created queue/topic.

## 9. merge: Combining Streams

merge combines records from two KStreams into one larger stream:

~~~java
KStream<String, OrderEvent> allOrders =
    onlineOrders.merge(storeOrders);
~~~

Merge does not re-sort all records by timestamp and does not establish a global order between the two sources. Relative order within each input stream is preserved, but records from onlineOrders and storeOrders can interleave according to processing scheduling. If business logic requires ordering by event time or aggregate version, you must design dedicated sorting/validation rules.

Merge does not automatically deduplicate. If both sources emit the same event, the output may still contain both records. To remove duplicates, you need an idempotency key or stateful deduplication with an appropriate retention window; history-based deduplication is a stateful operation.

## 10. peek and foreach: Observation vs. Side Effects

peek performs an observational action on each record and returns the stream unchanged. It is suitable for logging, debugging, or incrementing metrics:

~~~java
KStream<String, OrderEvent> observed = orders.peek((key, event) ->
    log.debug("orderKey={}, eventId={}", key, event.eventId())
);
~~~

foreach also performs an action for each record, but it is a terminal operation and does not return a stream to continue chaining the topology:

~~~java
orders.foreach((key, event) ->
    log.info("Received order {}", event.orderId())
);
~~~

Do not use peek/foreach to write business data to an external system and assume Kafka will include that side effect in the topology's processing guarantee. Kafka Streams cannot roll back an HTTP call or database write just because a Kafka transaction aborts. External side effects can be executed again when records are replayed or tasks recover.

If you need to write to Kafka, prefer DSL sinks like `to()` or binder output bindings so Kafka Streams manages the producer and transactions. If you need to write to an external database/API, use the outbox pattern, idempotency, or an appropriate coordination mechanism.

## 11. Combining Multiple Transformations into a Pipeline

A real-world topology typically chains several stateless operations:

~~~java
KStream<String, OrderCreated> acceptedOrders = orders
    .filter((orderId, event) ->
        event != null && event.amount() > 0)
    .mapValues(event -> new OrderCreated(
        event.orderId(),
        event.customerId().trim(),
        event.amount()
    ))
    .peek((orderId, event) ->
        log.debug("Accepted order {}", event.orderId()));
~~~

This pipeline:

1. Drops null records or records with invalid amounts.
2. Normalizes `customerId` inside the value.
3. Preserves the input key.
4. Logs an observation without modifying the record.

None of these operations need to remember previous records. Each record can be processed independently. If you add `countByKey`, `aggregate`, or `windowedBy`, the topology transitions into a stateful step and requires a state store.

## 12. Using Stateless Topologies in the Spring Cloud Stream Kafka Streams Binder

The Kafka Streams binder supports the functional programming model. A `Function` bean that accepts a `KStream` and returns a `KStream` represents a processor with an input and an output binding.

Example:

~~~java
import java.util.function.Function;

import org.apache.kafka.streams.kstream.KStream;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderValidationTopology {

    @Bean
    Function<KStream<String, Long>, KStream<String, Long>> positiveAmounts() {
        return input -> input
            .filter((accountId, amount) -> amount != null && amount > 0)
            .mapValues(amount -> amount * 100L);
    }
}
~~~

Because the Function bean is named `positiveAmounts`, the binder creates by default:

- `positiveAmounts-in-0`: input binding.
- `positiveAmounts-out-0`: output binding.

Configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: positiveAmounts
    stream:
      bindings:
        positiveAmounts-in-0:
          destination: account.amounts
        positiveAmounts-out-0:
          destination: account.amounts.normalized
      kafka:
        streams:
          binder:
            application-id: account-amount-normalizer
~~~

`application-id` identifies the Kafka Streams application, its logical consumer group, and its state/runtime namespace. Even when a topology only has stateless operations, the application ID should remain stable across deployments so Kafka Streams manages tasks and offsets consistently.

## 13. Serdes When Changing Data Types

Kafka stores byte arrays; Kafka Streams needs a Serializer/Deserializer (Serde) to convert keys/values at inputs, repartition points, and output topics. A transformation may change data types, so you must ensure the corresponding Serde is configured.

For example, if the input topic has String keys and Long values and the output keeps String/Long, built-in Serdes can be used. If `mapValues` turns `OrderCreated` into `OrderSummary`, the output value needs a Serde that reads/writes `OrderSummary`.

In the Kafka Streams binder, per-binding Serde configuration can be placed under:

- Consumer: `spring.cloud.stream.kafka.streams.bindings.<binding-name>.consumer.keySerde` and `valueSerde`.
- Producer: `spring.cloud.stream.kafka.streams.bindings.<binding-name>.producer.keySerde` and `valueSerde`.
- Defaults for multiple outputs can be placed under `spring.cloud.stream.kafka.streams.default.producer`.

Illustrative example with String Serde:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          bindings:
            positiveAmounts-in-0:
              consumer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: org.apache.kafka.common.serialization.Serdes$LongSerde
            positiveAmounts-out-0:
              producer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: org.apache.kafka.common.serialization.Serdes$LongSerde
~~~

If using JSON, Avro, Protobuf, or a type-specific Serde, configure the proper class and corresponding schema registry/client. Do not assume the input Serde automatically matches the output after changing data types.

## 14. Key Changes and Repartitioning: Performance Impact

Kafka distributes records into partitions based on the key and partitioner. If the key is preserved via `mapValues` or `flatMapValues`, the topology can continue processing data within the current partition.

When `map`, `flatMap`, or `selectKey` changes the key, records residing in the old partition may no longer be distributed according to the new key. If a subsequent step requires records with the same key to reside in the same partition, Kafka Streams must repartition via an internal topic.

~~~mermaid
flowchart LR
    A[Input topic partitioned by orderId] --> B[selectKey: customerId]
    B --> C{Grouping/join by new key?}
    C -->|No| D[Continue topology]
    C -->|Yes| E[Repartition topic]
    E --> F[Records distributed by customerId]
    F --> G[Group / join / aggregate]
~~~

Repartitioning incurs serialization, broker writes, re-reads, and can increase latency. Only change the key when business requirements demand it. If a subsequent step only transforms the value, use `mapValues` to avoid creating unnecessary repartitioning.

To inspect the topology, examine the topology description and the internal topics created by Kafka Streams. In production, monitor throughput, network, lag, and the number of internal repartition topics when changing keys.

## 15. Stateless Does Not Mean Deterministic or Error-Free

A function can avoid using a state store and still produce non-deterministic results if it reads system time, random values, mutable variables, or calls external services:

~~~java
KStream<String, OrderEvent> unstable = orders.mapValues(event ->
    event.withProcessedAt(Instant.now())
);
~~~

This transformation does not use a state store, yet the same record replayed at a different time will have a different `processedAt`. If reproducible results are required, use the record's timestamp or a business timestamp already recorded in the event.

Similarly, calling an HTTP API inside `mapValues` makes the topology depend on an external service, can block the stream thread, and causes repeated side effects during replay. Avoid blocking I/O inside stateless mappers. If enrichment is needed, consider emitting an event to a dedicated service, using a KTable/global table for reference data, or designing a separate retry/idempotency mechanism.

Stateless only describes that the operation does not maintain accumulated state across records. It does not by itself guarantee determinism, exactly-once semantics for external APIs, or the absence of exceptions.

## 16. Distinguishing Stateless and Stateful Operators

| Requirement | Stateless | Stateful |
|---|---|---|
| Select records by condition | filter/filterNot | — |
| Change key/value | map/mapValues/selectKey | — |
| Produce multiple records from one record | flatMap/flatMapValues | — |
| Split/merge streams | split/branch/merge | — |
| Observe records | peek | — |
| Count records by key | — | count |
| Compute sums/accumulated values | — | aggregate/reduce |
| Group records by time interval | — | windowedBy |
| Combine streams/tables by key | — | join |
| Deduplicate based on history | — | deduplication with state store/window |

A topology can contain both kinds. For example, `filter` and `mapValues` can run before `groupByKey` and `count`. Once it reaches `count`, the topology begins needing a state store to hold counts per key. The preceding stateless steps do not become stateful merely because they precede an aggregation.

## 17. Testing Stateless Topologies

Kafka Streams provides `TopologyTestDriver` for testing topologies without running a Kafka broker. With the Spring Cloud Stream Kafka Streams binder, you can also test function logic and bindings, though you should distinguish testing the function from runtime/broker integration testing.

With `TopologyTestDriver`, tests should verify:

- Valid records are kept and invalid records are dropped.
- `mapValues` preserves the key and transforms the value accurately.
- `map`/`selectKey` produces the expected new key.
- `flatMapValues` generates the right number of records while preserving the original key.
- `branch` evaluates predicates in the right order and routes to the default branch when needed.
- `merge` is not assumed to provide a global order between two sources.
- Input/output Serdes read and write the expected types properly.
- Null/tombstone records are handled according to the desired semantics.

Conceptual test example with `TopologyTestDriver`:

~~~java
TestInputTopic<String, Long> input =
    testDriver.createInputTopic(
        "account.amounts",
        stringSerializer,
        longSerializer
    );

TestOutputTopic<String, Long> output =
    testDriver.createOutputTopic(
        "account.amounts.normalized",
        stringDeserializer,
        longDeserializer
    );

input.pipeInput("account-1", 10L);
input.pipeInput("account-2", -5L);

assertThat(output.readKeyValue())
    .isEqualTo(KeyValue.pair("account-1", 1000L));
assertThat(output.isEmpty()).isTrue();
~~~

The illustrative test assumes the topology has already been built with `testDriver` and the corresponding serializers/deserializers. In a real project, create the driver with `Properties` containing the application ID, dummy bootstrap servers, and default or explicit Serdes; close the driver after the test to release resources.

For topologies with repartitioning, inspect both the keys and downstream results to confirm records with the same new key are routed properly. For branch/merge, test each branch individually and do not assert a cross-source order that the API does not guarantee.

## 18. Topology Observability and Operations

Stateless transformations typically consume fewer resources than aggregations/joins, yet they can still create bottlenecks due to CPU processing, serialization/deserialization, repartitioning, or side effects.

You should monitor:

- Input/output records per second per processor node.
- Number of records filtered out or unmatched by branches.
- Processing latency and stream thread idle time.
- Consumer lag and processing time per partition.
- Repartition topic count, throughput, and internal topic traffic.
- Serialization/deserialization errors.
- Exceptions in mappers/predicates and task restart counts.
- Output/input ratios to detect filters or branches dropping records unexpectedly.

Give processor nodes meaningful names when topologies become complex so metrics and topology descriptions stay readable. Do not log full payloads for every record in production; use sampling, appropriate log levels, and low-cardinality metrics.

## 19. Common Mistakes

1. Using `map` when only the value needs changing, potentially forcing the topology to repartition at a subsequent grouping/join step.
2. Using `flatMap` to split a value even though the key should stay unchanged; `flatMapValues` is usually more suitable.
3. Assuming `selectKey` immediately moves records to a new partition; repartitioning only happens when the topology needs distribution by the new key.
4. Thinking `branch` sends a record to every matching predicate; in reality, a record goes into the first matching branch.
5. Assuming `merge` orders records from two sources by timestamp; there is no such global ordering.
6. Using `peek`/`foreach` to write to a database or call an API and expecting Kafka to roll back side effects.
7. Forgetting to configure Serdes after changing key/value types.
8. Treating a KTable like a KStream and overlooking update/tombstone semantics.
9. Putting logic dependent on system time or randomness inside a mapper while expecting replays to yield identical results.
10. Using `filter` to drop bad messages without a branch to retain them when business requirements demand investigation.
11. Assuming stateless means the topology does not need management of application ID, tasks, partitions, or offsets.

## 20. Workflow for Designing a Stateless Topology

1. Identify the input type: KStream or KTable; current keys/values and Serdes.
2. Specify clearly which records are kept, dropped, or routed to branches.
3. Determine which steps only change values and which genuinely need to change keys.
4. Prefer `mapValues`/`flatMapValues` when keeping the key to avoid unnecessary repartitioning.
5. If changing keys, check whether downstream grouping/joins require repartitioning.
6. Define branch predicates in priority order and create a default branch when needed.
7. Confirm whether `merge` is acceptable without a global order across sources.
8. Select appropriate Serdes for all data types at inputs, internal repartition points, and outputs.
9. Keep mappers/predicates short, deterministic, and free of blocking I/O or external side effects.
10. Test each transformation with `TopologyTestDriver` and use integration tests when broker verification is needed.
11. Observe the topology description, internal topics, processing latency, and input/output ratios after deployment.

Stateless transformations are the fundamental building blocks of a Kafka Streams topology. Once you understand how each operator impacts records, keys, partitions, and Serdes, you can build easily testable pipelines, avoid unnecessary repartitioning, and keep boundaries clear before adding state stores, aggregations, joins, or windowing.

## References

- [Apache Kafka Streams DSL – Stateless transformations](https://kafka.apache.org/documentation/streams/developer-guide/dsl-api/)
- [Spring Cloud Stream Kafka Streams Binder – Functional Style](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/functional.html)
- [Spring Cloud Stream Kafka Streams Binder – Serialization and Deserialization](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/record-serialization-and-deserialization.html)
- [Apache Kafka Streams – Testing](https://kafka.apache.org/documentation/streams/developer-guide/testing/)
