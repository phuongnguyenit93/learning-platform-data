# Processing Topology and the Role of applicationId

Kafka Streams turns event-processing operations into a **topology**: a directed graph consisting of topic-reading sources, processing steps, and result-writing sinks. A topology describes which steps data flows through, how it is grouped by key, what state needs to be stored, and where results are emitted. Kafka Streams executes the topology across multiple tasks and threads, coordinating instances through Kafka.

In the Spring Cloud Stream Kafka Streams binder, a `Function` or `Consumer` bean accepting `KStream`, `KTable`, or `GlobalKTable` is wired by the binder to the corresponding input/output bindings. Kafka Streams remains the actual processing runtime; the binder handles mapping functions, topics, Serdes, and application configuration.

The **application.id** property identifies a logical Kafka Streams application. It determines the consumer group used to coordinate instances, the namespace for internal topics, and the local state directory. Configuring `application.id` properly is essential for scaling, recovering state, and deploying multiple topologies without them competing for each other's resources.

## 1. A Topology Is an Event-Processing Graph

A topology typically contains three types of nodes:

- **Source:** reads records from one or more Kafka topics.
- **Processor:** filters, transforms, branches, joins, groups, or updates state.
- **Sink:** writes result records to a Kafka topic or passes them to a sink processor.

Example order-processing flow:

~~~text
orders.raw
    |
    v
[Source: KStream]
    |
    v
[filter: drop invalid records]
    |
    v
[mapValues: normalize data]
    |
    v
[Processor: group by customerId]
    |
    +------> [State store + changelog]
    |
    v
[Sink]
    |
    v
orders.summary
~~~

The topology is constructed from code when the application starts. When the topology runs, Kafka Streams divides it into tasks based on the partitions of the input topics and assigns those tasks to stream threads across the participating instances of the same application.

Each task processes a subset of data defined by its source partitions. Multiple tasks can run in parallel across multiple threads and instances. When the number of instances changes, Kafka Streams rebalances and reassigns tasks.

A topology is the logical description of processing. Tasks, threads, and instances are how the runtime executes that topology. Do not confuse a function bean with a Kafka partition or a pod.

## 2. Source, Processor, and Sink in the Kafka Streams DSL

The Kafka Streams DSL constructs topologies by chaining transformations.

| Operation Group | Examples | Purpose |
|---|---|---|
| Reading data | stream, table, globalTable | Create a source from a topic |
| Stateless filtering and transformation | filter, map, mapValues, flatMapValues | Process each record independently |
| Branching and merging | split, branch, merge | Split a stream by condition or merge multiple streams |
| Grouping | groupBy, groupByKey | Determine the key used for aggregation |
| Stateful computation | count, aggregate, reduce | Maintain accumulated results |
| Joins | join, leftJoin, outerJoin | Combine streams and tables |
| Time windowing | windowedBy | Group records by time intervals |
| Writing results | to | Write a stream to a topic |

Example of a topology with only stateless transformations:

~~~java
KStream<String, String> normalized = builder
    .stream("orders.raw")
    .filter((key, value) -> key != null && value != null)
    .mapValues(String::trim)
    .filter((key, value) -> !value.isBlank());

normalized.to("orders.normalized");
~~~

Each record is filtered and normalized independently. This topology does not need a state store to remember results from previous records.

When counting events per customer, the topology must retain state:

~~~java
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.common.utils.Bytes;
import org.apache.kafka.streams.kstream.Grouped;
import org.apache.kafka.streams.kstream.KTable;
import org.apache.kafka.streams.kstream.Materialized;
import org.apache.kafka.streams.kstream.Produced;
import org.apache.kafka.streams.state.KeyValueStore;

KTable<String, Long> orderCounts = builder
    .stream("orders.events")
    .groupByKey(Grouped.with(Serdes.String(), Serdes.String()))
    .count(
        Materialized
            .<String, Long, KeyValueStore<Bytes, byte[]>>as(
                "orders-per-customer"
            )
            .withKeySerde(Serdes.String())
            .withValueSerde(Serdes.Long())
    );

orderCounts.toStream().to(
    "orders.counts",
    Produced.with(Serdes.String(), Serdes.Long())
);
~~~

Each new event increments the count for the corresponding key. Kafka Streams keeps the current value in a state store and emits a changelog so state can be recovered after a failure.

## 3. Distinguishing KStream, KTable, and GlobalKTable

The Kafka Streams DSL provides three core data types. The Spring Cloud Stream Kafka Streams binder can bind these types directly to input topics.

| Type | Meaning | How Records Are Interpreted |
|---|---|---|
| KStream | Continuous event stream | Each record is an independent event |
| KTable | Keyed state table | A newer record updates the current value for the key |
| GlobalKTable | State table replicated to every instance | Every instance has a full copy for key-based lookup |

### KStream: Sequence of Events

Suppose a topic contains two records:

~~~text
key=customer-42, value=5
key=customer-42, value=3
~~~

With `KStream`, these are two independent events. If summed, the result is 8. The second record does not overwrite the first.

`KStream` fits transactions, page views, logs, order creation events, and any data where every record carries its own distinct meaning.

### KTable: Latest State per Key

With `KTable`, the two records above represent updates to the same row. The latest value for `customer-42` is 3.

~~~text
customer-42 -> ACTIVE
customer-42 -> SUSPENDED
customer-42 -> null
~~~

A record with a `null` value is a tombstone, indicating deletion of that key from the `KTable`. Therefore, `KTable` is well suited for topics containing changelogs or current state synchronized from a database.

### GlobalKTable: Global Copy

`GlobalKTable` replicates a topic's data to every instance of the application. It is useful when every stream task needs to look up a small reference table—such as a product catalog or regional configuration—without performing a standard co-partitioned join.

In exchange, every instance must ingest and store the entire `GlobalKTable` dataset. For large tables, network traffic, memory usage, and startup time can grow substantially.

Choose the input data type according to the topic's semantics. Do not use `KTable` merely because a topic has keys; determine whether records are independent events or updates to current state.

## 4. Stateless and Stateful Processing

Stateless operations need only the current record—for example `filter`, `map`, and `mapValues`. When a task moves to another instance, no accumulated data needs to be restored because these operations retain no business state.

Stateful operations must remember information from previous records:

- `count` and `aggregate` by key.
- `reduce` values in a group.
- Joining two streams by key and time window.
- Joining a stream with a `KTable` to enrich with reference data.
- Windowed aggregation by event time.

Kafka Streams automatically creates state stores when using DSL operators that require state. State stores can reside in memory or on local disk depending on the store type and configuration.

Example of counting events per customer:

~~~java
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.common.utils.Bytes;
import org.apache.kafka.streams.StreamsBuilder;
import org.apache.kafka.streams.kstream.Grouped;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.KTable;
import org.apache.kafka.streams.kstream.Materialized;
import org.apache.kafka.streams.kstream.Produced;
import org.apache.kafka.streams.state.KeyValueStore;

StreamsBuilder builder = new StreamsBuilder();
KStream<String, String> orders = builder.stream("orders.events");

KTable<String, Long> counts = orders
    .groupByKey(Grouped.with(Serdes.String(), Serdes.String()))
    .count(
        Materialized
            .<String, Long, KeyValueStore<Bytes, byte[]>>as(
                "orders-per-customer"
            )
            .withKeySerde(Serdes.String())
            .withValueSerde(Serdes.Long())
    );
~~~

The store name is `orders-per-customer`. A stable name helps with observing the topology, configuring the store, and intentionally querying state.

To emit the `KTable` results to an output topic, convert it to a `KStream` via `toStream`:

~~~java
KStream<String, Long> countUpdates = counts.toStream();
countUpdates.to(
    "orders.counts",
    Produced.with(Serdes.String(), Serdes.Long())
);
~~~

A `KTable` represents the current value. The `KStream` produced by `toStream` represents updates to that table. Downstream consumers must understand that each record is a count update, not an independent increment event.

## 5. Keys, Repartitioning, and Joins

Kafka distributes records across partitions based on the key and partitioner. In Kafka Streams, many stateful computations are performed per key. Records with the same key must be processed in the same partition/task for the computation to yield correct results.

When the key changes—for example using `selectKey` or `groupBy` to switch from `orderId` to `customerId`—the topology may require repartitioning before the next step. Repartitioning writes records to an internal topic and reads them back under the new key.

~~~text
orders topic
    |
    v
key = orderId
    |
    v
selectKey(customerId)
    |
    v
repartition topic
    |
    v
groupByKey(customerId)
    |
    v
aggregate
~~~

Not every `map` operation changes the key. `mapValues` only modifies the value and preserves the key. `map` can change both the key and the value. Always check the key after each step before grouping or joining.

Both inputs to a join must be compatibly partitioned. If two topics have different partition counts or partitioners, Kafka Streams cannot automatically guarantee that records with the same key land in the same task. One or both sides must be repartitioned under the same rule before joining.

For windowed joins, explicitly define:

- Which timestamp is used as event time.
- When the join window starts and ends.
- The grace period for late-arriving records.
- State store retention.
- How records arriving outside the window are handled.

Do not set windows unnecessarily wide, because the state store must retain more data. Likewise, do not set the grace period too short if the source has noticeable latency.

## 6. Using Topologies via the Spring Cloud Stream Kafka Streams Binder

The Kafka Streams binder provides a way to connect the Kafka Streams DSL to Spring Cloud Stream's functional model.

Add the binder dependency:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-binder-kafka-streams</artifactId>
</dependency>
~~~

Function beans can use the following signatures:

| Function Type | Role |
|---|---|
| Consumer<KStream<K, V>> | Receives a stream and processes it, declaring no output binding |
| Function<KStream<K, V>, KStream<K2, V2>> | Receives a stream, transforms it, and emits a stream |
| BiFunction<KStream<K, V>, KTable<K2, V2>, KStream<K3, V3>> | Receives two inputs of different types |
| BiConsumer<KStream<K, V>, KTable<K2, V2>> | Receives two inputs, declaring no output |

The binder derives binding names from the function bean name:

- `normalizeOrders-in-0`: first input.
- `normalizeOrders-out-0`: first output.
- `enrichOrders-in-1`: second input of the `enrichOrders` function.

For multi-input functions, the binding index reflects parameter position. For example, a `BiFunction` with two inputs produces `in-0` and `in-1`.

### Example Order-Normalization Function

~~~java
import java.util.function.Function;

import org.apache.kafka.streams.kstream.KStream;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderTopology {

    @Bean
    Function<KStream<String, String>, KStream<String, String>>
            normalizeOrders() {

        return orders -> orders
            .filter((key, value) -> key != null && value != null)
            .mapValues(String::trim)
            .filter((key, value) -> !value.isBlank());
    }
}
~~~

This function reads data from the input binding, drops invalid records, normalizes values, and emits the result to the output binding.

Binding and application ID configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrders

    stream:
      bindings:
        normalizeOrders-in-0:
          destination: orders.raw

        normalizeOrders-out-0:
          destination: orders.normalized

      kafka:
        streams:
          binder:
            brokers: localhost:9092
            applicationId: orders-normalizer-v1
            configuration:
              default.key.serde: org.apache.kafka.common.serialization.Serdes$StringSerde
              default.value.serde: org.apache.kafka.common.serialization.Serdes$StringSerde
~~~

Here:

- Function definition selects the function to activate.
- Input binding reads the `orders.raw` topic.
- Output binding writes to the `orders.normalized` topic.
- `applicationId` identifies the logical Kafka Streams application.
- `default.key.serde` and `default.value.serde` specify the default Serdes for keys and values.

If using DTOs, Avro, Protobuf, or custom types, declare the corresponding Serdes. Do not assume `StringSerde` can serialize a Java object.

### Example Function with Two Inputs

A topology can join an event stream with a customer status table:

~~~java
@Bean
BiFunction<
        KStream<String, String>,
        KTable<String, String>,
        KStream<String, String>> enrichOrders() {

    return (orders, customers) -> orders
        .leftJoin(
            customers,
            (order, customerStatus) ->
                order + "|customerStatus=" + customerStatus
        );
}
~~~

The binder creates two input bindings:

- `enrichOrders-in-0` points to the orders topic and is bound as a `KStream`.
- `enrichOrders-in-1` points to the customer status topic and is bound as a `KTable`.
- `enrichOrders-out-0` is the output stream.

The example above illustrates a join operation. In a real application, define clear DTOs, Serdes, null handling, and missing-data policies. Both inputs must have compatible keys and partitioning to join properly.

## 7. What Is application.id?

Kafka Streams requires an `application.id` for every stream-processing application. It serves as the identifier of a **logical stream-processing application** within a Kafka cluster.

`application.id` plays multiple roles simultaneously:

| Role | How Kafka Streams Uses It |
|---|---|
| Consumer group | Acts as `group.id` to coordinate instances and assign tasks |
| Client ID | Acts as the prefix for default client IDs of internal consumers/producers |
| Local state directory | Creates subdirectories under `state.dir` |
| Internal topics | Acts as the namespace prefix for internal topics such as changelogs and repartitions |
| Application management | Distinguishes one stream application from another |

Because `application.id` is used across multiple layers, it is not merely a display name for the service. Changing this value can change the consumer group, internal topic namespace, and local state that the application uses.

Kafka Streams also uses `application.id` as the consumer group ID. Therefore, you can use Kafka consumer group tools to inspect the status and lag of an application by its `application.id`.

`application.id` does not automatically enable exactly-once processing. If a topology requires exactly-once semantics, you must configure `processing.guarantee` for your Kafka Streams version and verify broker, transaction, and sink requirements. Application identity and processing guarantees are two separate configuration concerns.

## 8. Crucial Rule: Same Application, Same application.id

Suppose the `order-enricher` application has three replicas:

~~~text
application.id = order-enricher-prod-v1

Replica A --------\
Replica B ---------+---- Consumer group order-enricher-prod-v1
Replica C --------/              |
                                 v
                      Kafka assigns tasks by
                      partition and topology
~~~

All three replicas must share the same `application.id`. Kafka Streams treats them as instances of the same application, coordinating membership and distributing tasks.

If each pod appends its own unique name to `application.id`:

~~~text
order-enricher-pod-a
order-enricher-pod-b
order-enricher-pod-c
~~~

Kafka will treat them as three independent applications. Each application gets its own consumer group and state, so each can end up reading all input partitions and emitting duplicate results.

Practical rules:

- Replicas of the same production topology use the same `application.id`.
- Two independent topologies require different `application.id` values.
- Do not include pod names, hostnames, or instance IDs in the `application.id` of replicas belonging to the same application.
- Environments sharing the same Kafka cluster should use distinct namespaces, e.g., `orders-enricher-dev` and `orders-enricher-prod`.
- Choose recognizable, stable names using alphanumeric characters, dots, hyphens, or underscores.

Do not reuse the same `application.id` for two logically distinct processors simply because they live in the same Spring Boot project. Each Kafka Streams processor needs an identifier aligned with the topology and state it manages.

## 9. Configuring applicationId in the Spring Cloud Stream Binder

The Spring Cloud Stream Kafka Streams binder supports two primary ways to declare the application ID.

### Single Processor in an Application

If the application has only one Kafka Streams processor, you can set it at the binder level:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            applicationId: orders-normalizer-prod-v1
~~~

`spring.application.name` can serve as a convenient default for a single processor. However, production environments should configure `applicationId` explicitly to avoid unintentionally altering Kafka Streams identity if the Spring application name changes.

If `applicationId` is not declared, the binder can auto-generate a static ID derived from the function bean name, such as `process-applicationID`. While convenient for experimentation and stable across restarts, do not rely on auto-generated values in production because renaming the function changes the application identity. Set the ID explicitly in environment configuration.

### Multiple Processors in the Same Spring Boot Application

Suppose an application defines two independent functions:

~~~java
@Bean
Function<KStream<String, String>, KStream<String, String>>
        normalizeOrders() {
    return input -> input.mapValues(String::trim);
}

@Bean
Function<KStream<String, String>, KStream<String, String>>
        redactOrders() {
    return input -> input.mapValues(value ->
        value.replace("secret", "***")
    );
}
~~~

Each function creates a separate Kafka Streams processor. Each function must be assigned its own application ID:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrders;redactOrders

    stream:
      kafka:
        streams:
          binder:
            functions:
              normalizeOrders:
                applicationId: orders-normalizer-prod-v1

              redactOrders:
                applicationId: orders-redactor-prod-v1
~~~

Per-function configuration gives each processor its own consumer group and internal topic namespace. Replicas of `normalizeOrders` share `orders-normalizer-prod-v1`; replicas of `redactOrders` share `orders-redactor-prod-v1`.

Do not set a single global `applicationId` and expect the binder to automatically namespace multiple functions. When you have multiple processors, declare `applicationId` per function bean name.

Binder-level `configuration` properties apply to all processors in the application. Therefore, do not put a shared `application.id` inside the `configuration` map when functions require different IDs; use the function-specific `functions.<function-name>.applicationId` property.

The binder can also set `applicationId` on an input binding in some legacy models or when using `StreamListener`. With the modern functional model, configuring `functions.<function-name>.applicationId` is typically easier to manage.

## 10. application.id and Binding Group Are Not the Same Concept

Spring Cloud Stream uses binding-level `group` configuration for regular message-channel binders. Kafka Streams, however, uses `application.id` as the consumer group identity of the Kafka Streams runtime.

For the Kafka Streams binder, configure `applicationId` as specified by the binder documentation. Do not rely on a standard `group` property as a substitute for the required `applicationId`.

Distinguish these terms:

| Property | Purpose |
|---|---|
| `application.id` | Identity of the logical Kafka Streams application; coordinates tasks and state |
| Function bean name | Name of the function in the Spring context; used by the binder for default bindings and per-function configuration |
| Binding name | Input/output binding name, e.g., `process-in-0` |
| Topic | Storage location for input or output records |
| Pod/instance name | Identifies a specific deployment instance; never used as the shared `application.id` of replicas |

A single function bean can read multiple topics via multiple input bindings while remaining one Kafka Streams application with one `applicationId`. Conversely, a single Spring Boot process with multiple Kafka Streams functions can instantiate multiple logical applications, each with its own `applicationId`.

## 11. How application.id Affects State Stores and Internal Topics

Stateful topologies must persist state for computation. Kafka Streams typically stores state locally on each instance and writes changelogs to Kafka for recovery.

~~~text
Topology
   |
   +---- State store: orders-per-customer
   |          |
   |          +---- Local state directory
   |          |
   |          +---- Changelog topic
   |
   +---- Repartition processor
              |
              +---- Repartition topic
~~~

Internal topics may include:

- Changelog topic: records state store mutations for state recovery.
- Repartition topic: redistributes records under a new key so stateful steps or joins execute properly.

`application.id` serves as the namespace prefix for these internal topics. This prevents two independent applications from overwriting each other's state or repartition data.

Local state stores reside under `state.dir`, which commonly defaults to `/tmp/kafka-streams`. Kafka Streams creates subdirectories keyed by `application.id` and task. If multiple instances share a filesystem, each instance's `state.dir` must be configured so they do not write into the same directory.

Do not configure a single shared `state.dir` across multiple concurrently running instances. Each instance needs its own local state path to prevent file locking conflicts and RocksDB data corruption.

## 12. Recovering State on Restart or Rebalance

When an instance stops, its tasks can be reassigned to another instance. The new instance needs state to resume computation.

Recovery typically proceeds as follows:

1. Kafka Streams receives a task assignment from the group coordinator.
2. The instance checks the corresponding local state store.
3. If the local state is valid and usable, it can resume from existing state.
4. If the state is missing or invalid, Kafka Streams restores it from the changelog topic.
5. Once restoration completes, the task resumes processing input from the committed offset.

Because `application.id` determines both the changelog namespace and the consumer group, replicas must share the same ID to coordinate and recover state accurately.

When scaling out, tasks may migrate to new replicas. When scaling in, tasks shift to remaining replicas. State restoration can introduce latency during rebalances; for large topologies, monitor restore times and changelog sizes.

Do not delete local state or changelog topics while the application is running. Doing so can cause state inconsistency and prevent the topology from recovering as expected.

## 13. Scaling Applications and Parallelism Limits

Adding replicas does not automatically create more partitions for a topic. Kafka Streams parallelism is bounded by the number of tasks that can be created from the source topic partitions and the topology.

Example with a four-partition topic:

~~~text
orders.events: 4 partitions

3 replicas, 1 stream thread per replica
    |
    +-- Replica A: some tasks
    +-- Replica B: some tasks
    +-- Replica C: some tasks

If the task count is only 4, only 4 active tasks exist in total.
Scaling replicas beyond the task count creates no extra processing tasks.
~~~

You can tune the number of stream threads per instance via `StreamsConfig` settings such as `num.stream.threads`. However, adding threads does not substitute for designing an appropriate partition count.

When planning scaling:

- Identify the partition counts of all source topics.
- Determine the actual number of tasks the topology creates.
- Balance replica count and `num.stream.threads`.
- Measure CPU, memory, network, state restore, and processing latency.
- Monitor rebalances when adding or removing instances.
- Ensure `state.dir` is local and isolated per instance.

For multi-input joins, the partition counts and partitioners of the sources must be compatible. Having more partitions on one topic does not automatically make a join correct or faster if the inputs are not co-partitioned.

## 14. When to Keep or Change application.id

This is a critical deployment decision.

| Scenario | Recommended Action |
|---|---|
| Restarting the same application | Keep `application.id` unchanged |
| Scaling up replicas of the same topology | Keep `application.id` unchanged |
| Changing replica count | Keep `application.id` unchanged |
| Two independent topologies reading the same topic | Use different `application.id` values |
| Running a canary alongside the old application | Use a different ID if two independent groups are needed; isolate outputs to avoid duplicate writes |
| Creating a new application without reusing old state | Use a new `application.id` and plan input offsets and outputs |
| Replaying from the beginning | Follow a controlled reset procedure; do not merely rename `application.id` |

### Keep application.id to Continue Existing State

Keeping the same ID allows the application to continue using the existing consumer group and internal topic namespace. State stores can be restored from changelogs, and input offsets resume from committed positions.

When changing the topology, evaluate compatibility with existing state stores, changelogs, and repartition topics. If the new topology cannot reuse old state, create a migration plan or a new versioned application ID.

### Changing application.id Creates a New Logical Application

Using a new ID causes Kafka Streams to create a new consumer group and a new internal topic namespace. The application does not inherit committed offsets from the old ID. When no offsets exist for the new group, the starting position is governed by `auto.offset.reset`; Kafka Streams and the Kafka Streams binder default to `earliest` in documented configurations.

This means the new application may re-read historical inputs and re-emit outputs. If the output topic remains the same, downstream consumers may receive duplicates alongside results from the previous application.

Before changing the ID, determine:

- Whether inputs should start from `earliest` or `latest`.
- Whether the output topic needs versioning.
- Whether downstream consumers can tolerate duplicate records.
- Whether old state must be retained for reconciliation.
- When and how old internal topics will be retained or deleted.
- When the old application can be stopped and decommissioned.

Do not change `application.id` just to distinguish pods or deployments. Doing so creates an independent consumer group and can cause data to be reprocessed.

## 15. Resetting an Application to Replay Data from the Beginning

Kafka provides the Kafka Streams application reset tool to return an application to a reprocessing state. This is an operational procedure affecting offsets and internal topics and must be executed deliberately.

The reset tool can:

- Reset input topic offsets to a chosen position, defaulting to the beginning of the topic.
- Delete internal topics identified as belonging to the application, including changelog/repartition topics within the tool's scope.
- Clear committed offsets associated with internal topics.

The reset tool does not automatically delete output topics or clear local state directories on application hosts. Consequently, downstream outputs may still hold old results, and local state must be cleaned up through an appropriate procedure.

Safe procedure:

1. Stop all instances of the `application.id` being reset.
2. Confirm the consumer group has no active members.
3. Run the Kafka Streams application reset tool in dry-run mode to inspect planned changes.
4. Verify the exact `application.id`, input topics, and internal topics.
5. Select the target input offset position for replay.
6. Execute the actual reset after verification.
7. Clean local state directories on instances as instructed.
8. Review output topics and downstream consumers before restarting.
9. Monitor state restoration, consumer lag, and outputs after startup.

Example dry-run command:

~~~bash
bin/kafka-streams-application-reset.sh \
  --application-id orders-normalizer-prod-v1 \
  --bootstrap-server localhost:9092 \
  --dry-run
~~~

After reviewing the plan, you can choose to reset inputs to `earliest` using the corresponding tool option. Never run a reset while any instance is still active. Do not assume that deleting committed offsets alone clears local state.

The Kafka Streams binder also provides a `startOffset` property to control where reading begins when no committed offsets exist. The `resetOffsets` property of regular consumer bindings does not perform head/tail seeking for the Kafka Streams binder in the same way it does for the Kafka message-channel binder.

## 16. Managing Topology Versions and Blue/Green Deployments

A topology can change when adding processors, changing keys, changing stores, or modifying aggregations. These changes can impact internal topics and state stores.

A common versioning strategy embeds a version into `application.id`:

~~~text
orders-aggregate-prod-v1
orders-aggregate-prod-v2
~~~

When running v2 in parallel with v1:

- Both versions maintain independent consumer groups and state.
- Both can read the same input topic.
- Each version owns its own internal topics.
- If both write to the same output topic, downstream consumers may receive duplicate results.
- Separate output topics or establish a clear traffic cutover mechanism.
- Once v2 is verified, stop v1 and clean up old state according to retention/cleanup policies.

If a topology change only modifies code while preserving state compatibility and needs to resume from existing offsets, you can keep the same ID. However, verify state store schemas, store names, key/value Serdes, and topology compatibility prior to rollout.

Do not mechanically bump a version suffix on every build. Every ID change establishes a new application identity and may trigger input reprocessing.

## 17. Observing Topologies and application.id in Production

You can inspect the topology, state, and consumption metrics to verify whether the application is operating properly.

### Inspecting Topology via Actuator

The Kafka Streams binder exposes an endpoint returning the topology description:

~~~text
/actuator/kafkastreamstopology
/actuator/kafkastreamstopology/<application-id>
~~~

To use this endpoint, the application requires Spring Boot Actuator and a web dependency, and the endpoint must be exposed:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,kafkastreamstopology
~~~

The endpoint is not exposed by default. In production, secure actuator endpoints with authentication and network policies; never expose all management endpoints publicly to the Internet.

The topology description helps inspect sources, processors, sinks, stores, and repartition nodes. Use it to verify the actual topology against your design, especially after changing functions or adding joins.

### Monitoring Consumer Groups

Because `application.id` is also the group ID, you can check lag via the Kafka CLI:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group orders-normalizer-prod-v1 \
  --describe
~~~

Key metrics to monitor:

- Input lag per partition.
- Number of active and standby tasks.
- Rebalance duration.
- State store restore duration.
- Processing rate and output throughput.
- Deserialization errors, processing exceptions, and producer errors.
- Changelog/repartition topic sizes.
- Local state directory disk usage.

If a topology rebalances repeatedly, inspect instance restarts, session timeouts, processing latency, thread counts, and broker health. If state restoration takes too long, inspect changelog size, local state, and replication.

## 18. Testing Topologies and application.id

Testing can be performed at multiple levels.

### Unit Testing with TopologyTestDriver

`TopologyTestDriver` runs a topology in memory without requiring a live Kafka broker. Tests can create input topics, pipe records in, and read from output topics.

Example testing a normalization topology:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.apache.kafka.streams.KeyValue;
import org.apache.kafka.streams.TopologyTestDriver;
import org.apache.kafka.streams.test.TestInputTopic;
import org.apache.kafka.streams.test.TestOutputTopic;

TopologyTestDriver testDriver =
    new TopologyTestDriver(topology, streamsProperties);

TestInputTopic<String, String> input =
    testDriver.createInputTopic(
        "orders.raw",
        new StringSerializer(),
        new StringSerializer()
    );

TestOutputTopic<String, String> output =
    testDriver.createOutputTopic(
        "orders.normalized",
        new StringDeserializer(),
        new StringDeserializer()
    );

input.pipeInput("order-1", "  PAID  ");

KeyValue<String, String> result = output.readKeyValue();

assertEquals("order-1", result.key);
assertEquals("PAID", result.value);

testDriver.close();
~~~

This example focuses on topology logic. Tests must construct the topology and Serdes corresponding to the code under test.

### Integration Testing with a Real Kafka Broker

Use Testcontainers Kafka or a test broker to verify:

- The binder creates the expected input/output bindings.
- `application.id` is configured properly.
- Replicas using the same ID join the same consumer group.
- Independent functions use distinct IDs.
- Internal topics are created under the expected namespace.
- State is recovered after restarts.
- Rebalances do not lose or unexpectedly duplicate side effects.
- Output topics receive the right keys, values, and record counts.

For tests running concurrently, assign a distinct `application.id` per test if they share a Kafka cluster. Reusing the same ID across parallel tests causes them to contend over consumer groups, internal topics, and committed offsets.

### Testing State Recovery

For topologies with aggregations or joins:

1. Send a batch of events and verify the state store/output.
2. Stop the processor after state has been persisted.
3. Restart with the same `application.id`.
4. Confirm Kafka Streams restores state and resumes from committed offsets.
5. Send subsequent events and confirm the aggregation continues accurately.

Do not test only the output of the initial run. State recovery across restarts is a core property of stateful topologies.

## 19. Common Mistakes When Designing Topologies and application.id

| Symptom | Common Cause | Resolution |
|---|---|---|
| Every pod processes the entire input | Each pod uses a different `application.id` | Use the same ID across all replicas |
| Two processors contend for state or tasks | Two independent topologies share an `application.id` | Assign a separate ID to each processor |
| Restart re-reads all data | `application.id` changed or group has no committed offsets | Verify the ID and `auto.offset.reset` |
| Slow state store restoration | Large changelog or lost local state | Monitor restore times and consider standby/state retention |
| Missing or wrong join data | Inputs are not co-partitioned | Repartition with the same key and partitioner |
| Adding replicas does not increase throughput | Insufficient task/partition count | Adjust partitions and threads after load testing |
| Duplicate outputs appear after blue/green | Two application IDs read and write to the same output | Separate output topics or design a clean cutover |
| Function does not run | Function is not activated in function definition | Check the list of activated functions |
| Cannot deserialize objects | Serde does not match key/value types | Declare Serdes explicitly |
| Old output remains after reset | Reset tool does not delete output topics | Plan output cleanup and downstream handling |
| Topology fails to recover after reset | Local state was not cleared or internal topics were handled improperly | Stop all instances and follow all reset steps |

## 20. Pre-Deployment Checklist

| Item | Question |
|---|---|
| Topology | Do sources, processors, state stores, and sinks match the business flow? |
| Data model | Should the input be `KStream`, `KTable`, or `GlobalKTable`? |
| Key | Are keys stable and suitable for grouping/joining? |
| Partitioning | Are join inputs co-partitioned? |
| Serde | Are key/value Serdes compatible with producers and consumers? |
| application.id | Is it unique per logical processor within the cluster? |
| Replicas | Do all replicas of the same processor share the same `application.id`? |
| Multiple functions | Does every independent function have its own `applicationId`? |
| Internal topics | Do changelog and repartition topics have appropriate replication/retention? |
| Local state | Is `state.dir` isolated per instance? |
| Upgrade | Are topology changes compatible with existing state? |
| Replay | Are reset procedures, dry-run checks, and output/downstream controls defined? |
| Observability | Are the topology endpoint, health, lag, restore time, and error metrics in place? |
| Tests | Are topology unit tests and real-Kafka integration tests present? |

## 21. Lab Exercise and Completion Criteria

Build a topology that counts orders per customer:

1. Create the `orders.events` topic, using `customerId` as the Kafka key.
2. Create a function accepting `KStream<String, String>` via the Kafka Streams binder.
3. Filter out invalid records and validate the key.
4. Use `groupByKey` and `count` to produce a `KTable` of order counts per customer.
5. Materialize the state store under the name `orders-per-customer`.
6. Convert the `KTable` to a `KStream` and write updates to `orders.counts`.
7. Configure Serdes for keys and values.
8. Set `applicationId` to `orders-counter-dev-v1`.
9. Run two replicas with the same `applicationId` and confirm Kafka assigns tasks within the same consumer group.
10. Run an independent processor with a different `applicationId` and confirm it gets its own group and state.
11. Stop one replica, restart it, and observe rebalance and state restoration.
12. Inspect the topology via Actuator and monitor consumer lag.
13. Change `applicationId` in a test environment and observe the creation of a new group/internal topics and the starting read position.
14. Perform a reset dry-run and explain how input offsets, internal topics, output topics, and local state are affected.

You have completed the exercise when you can describe a topology in terms of source-processor-sink; distinguish `KStream`, `KTable`, and `GlobalKTable`; identify when repartitioning is needed; explain state stores and changelogs; configure `applicationId` for single or multiple functions; and accurately predict the impact of scaling, restarting, changing IDs, or resetting the application.

## 22. Official References

- [Spring Cloud Stream Kafka Streams Binder Reference](https://docs.spring.io/spring-cloud-stream-binder-kafka/docs/current/reference/html/kafka-streams.html) — functional binding, application ID, state stores, topology visualization, and binder configuration.
- [Spring Cloud Stream Kafka Streams Programming Model](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/programming-model.html) — Function, Consumer, KStream, KTable, GlobalKTable, and multiple input bindings.
- [Spring Cloud Stream Kafka Streams Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/configuration-options.html) — binder configuration, global and per-function `applicationId`.
- [Apache Kafka Streams — Configuring a Streams Application](https://kafka.apache.org/41/streams/developer-guide/config-streams/) — `application.id`, `bootstrap.servers`, `state.dir`, and runtime configuration.
- [Apache Kafka Streams — Streams DSL](https://kafka.apache.org/41/streams/developer-guide/dsl-api/) — KStream, KTable, stateful/stateless transformations, windowing, joins, and repartitioning.
- [Apache Kafka Streams — Processor API](https://kafka.apache.org/41/streams/developer-guide/processor-api/) — processor topology and custom state stores.
- [Apache Kafka Streams — Application Reset Tool](https://kafka.apache.org/41/streams/developer-guide/app-reset-tool/) — resetting offsets, internal topics, and local state.
